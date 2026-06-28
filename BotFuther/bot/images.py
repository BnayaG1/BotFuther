# -*- coding: utf-8 -*-
"""הורדת תמונות מטלגרם, דחיסה, ותיקייה זמנית."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from google.genai import types
from PIL import Image, ImageEnhance, ImageOps
from telegram import Update
from telegram.ext import ContextTypes

from bot.config import (
    FALLBACK_MODELS,
    IMAGE_JPEG_QUALITY,
    IMAGE_MAX_PX,
    IMAGE_MIN_VISION_PX,
    TEMP_IMAGE_DIR,
    VISION_BEAM_CROP,
    VISION_FAST_IMAGE_MIN_PX,
    VISION_FAST_MODE,
)
from bot.gemini_chat import gemini_runtime, generate_content_with_retries
from bot.vision import parse_json_from_llm_text

log = logging.getLogger("beam_telegram_bot")

BEAM_CROP_PROMPT = """Analyze this statics / structural mechanics exercise photo.

Find the tight bounding box around ONLY the beam diagram:
beam axis, supports, loads, moments, dimension chain, and labels on the diagram.

EXCLUDE from the box: question titles, Hebrew/English text blocks, student scratch
calculations, page margins, other exercises, tables unrelated to the beam.

Return JSON only (no markdown):
{
  "found": true or false,
  "left": 0.0-1.0,
  "top": 0.0-1.0,
  "right": 0.0-1.0,
  "bottom": 0.0-1.0,
  "confidence": "high" | "medium" | "low"
}

Coordinates are normalized fractions of image width/height:
- left/right measured from the left edge (left < right)
- top/bottom measured from the top edge (top < bottom)

If there is no beam diagram, set "found": false and omit the coordinate fields."""


class BeamCropError(Exception):
    """שגיאה בחיתוך שרטוט קורה מתמונה."""


class BeamNotFoundError(BeamCropError):
    """לא זוהה שרטוט קורה בתמונה."""


@dataclass
class TempImageFile:
    path: Path
    mime_type: str

    def read_bytes(self) -> bytes:
        return self.path.read_bytes()

    def cleanup(self) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except OSError as exc:
            log.warning("Failed to delete temp image %s: %s", self.path, exc)


def _telegram_chat_id(update: Update) -> int:
    chat = update.effective_chat
    if chat is None:
        raise ValueError("אין מזהה צ'אט")
    return int(chat.id)


def mime_to_suffix(mime_type: str) -> str:
    mapping = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }
    return mapping.get(mime_type.lower(), ".img")


def ensure_temp_image_dir() -> Path:
    TEMP_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    return TEMP_IMAGE_DIR


async def save_message_image_to_temp(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> TempImageFile:
    """מוריד תמונה מטלגרם לקובץ זמני על הדיסק."""
    message = update.message
    if message is None:
        raise ValueError("אין הודעה")

    chat_id = _telegram_chat_id(update)
    msg_id = int(message.message_id)
    temp_dir = ensure_temp_image_dir()

    if message.photo:
        photo = message.photo[-1]
        mime_type = "image/jpeg"
        tg_file = await context.bot.get_file(photo.file_id)
    else:
        doc = message.document
        if not doc or not doc.mime_type or not doc.mime_type.startswith("image/"):
            raise ValueError("לא נמצאה תמונה בהודעה")
        mime_type = doc.mime_type
        tg_file = await context.bot.get_file(doc.file_id)

    suffix = mime_to_suffix(mime_type)
    temp_path = temp_dir / f"tg_{chat_id}_{msg_id}_{int(time.time() * 1000)}{suffix}"
    await tg_file.download_to_drive(custom_path=str(temp_path))
    log.info("Saved temp image: %s", temp_path.name)
    return TempImageFile(path=temp_path, mime_type=mime_type)


def _to_rgb_work_image(img: Image.Image) -> Image.Image:
    if img.mode in ("RGBA", "LA"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[-1])
        return background
    if img.mode == "P":
        work = img.convert("RGBA")
        background = Image.new("RGB", work.size, (255, 255, 255))
        background.paste(work, mask=work.split()[-1])
        return background
    if img.mode != "RGB":
        return img.convert("RGB")
    return img.copy()


def _beam_crop_output_path(source: Path) -> Path:
    return source.with_name(f"{source.stem}_beam_crop.jpg")


def _maybe_crop_image_path(source: Path) -> Path:
    """חותך שרטוט קורה; אם לא נמצא — מחזיר את המקור ללא שינוי."""
    if not VISION_BEAM_CROP:
        return source
    try:
        cropped = crop_beam_from_image(source, output_path=_beam_crop_output_path(source))
        if cropped.resolve() != source.resolve():
            log.info("Beam crop applied: %s", cropped.name)
        return cropped
    except BeamNotFoundError as exc:
        log.info("Beam crop skipped (no diagram): %s", exc)
        return source
    except BeamCropError as exc:
        log.warning("Beam crop failed, using full image: %s", exc)
        return source


def _maybe_crop_temp_image(temp: TempImageFile) -> TempImageFile:
    cropped_path = _maybe_crop_image_path(temp.path)
    if cropped_path.resolve() == temp.path.resolve():
        return temp
    temp.path.unlink(missing_ok=True)
    return TempImageFile(path=cropped_path, mime_type="image/jpeg")


def prepare_image_for_vision(
    temp: TempImageFile,
    *,
    max_px: int = IMAGE_MAX_PX,
    min_px: int | None = None,
) -> TempImageFile:
    """מכין תמונה ל-Gemini Vision — חיתוך קורה, חדות/ניגודיות, JPEG איכות גבוה."""
    temp = _maybe_crop_temp_image(temp)
    if min_px is None:
        min_px = VISION_FAST_IMAGE_MIN_PX if VISION_FAST_MODE else IMAGE_MIN_VISION_PX
    original_path = temp.path
    prepared_path = original_path.with_name(f"{original_path.stem}_vision.jpg")
    before_bytes = original_path.stat().st_size

    with Image.open(original_path) as img:
        work = _to_rgb_work_image(img)
        work = ImageEnhance.Contrast(work).enhance(1.2)
        work = ImageEnhance.Sharpness(work).enhance(1.4)

        width, height = work.size
        longest = max(width, height)
        if longest < min_px:
            scale = min_px / float(longest)
            work = work.resize(
                (max(1, int(width * scale)), max(1, int(height * scale))),
                Image.Resampling.LANCZOS,
            )
            width, height = work.size
            longest = max(width, height)
        if longest > max_px:
            scale = max_px / float(longest)
            work = work.resize(
                (max(1, int(width * scale)), max(1, int(height * scale))),
                Image.Resampling.LANCZOS,
            )

        work.save(
            prepared_path,
            format="JPEG",
            quality=IMAGE_JPEG_QUALITY,
            optimize=True,
            progressive=True,
        )

    original_path.unlink(missing_ok=True)
    after_bytes = prepared_path.stat().st_size
    log.info(
        "Prepared vision image %s: %dx%d, %dKB -> %dKB (JPEG q=%s)",
        prepared_path.name,
        work.size[0],
        work.size[1],
        before_bytes // 1024,
        after_bytes // 1024,
        IMAGE_JPEG_QUALITY,
    )
    return TempImageFile(path=prepared_path, mime_type="image/jpeg")


def prepare_image_path_for_vision(
    source_path: Path,
    *,
    max_px: int = IMAGE_MAX_PX,
    min_px: int | None = None,
) -> tuple[bytes, str]:
    """מכין bytes ל-Gemini מקובץ על הדיסק — בלי למחוק את המקור."""
    if min_px is None:
        min_px = VISION_FAST_IMAGE_MIN_PX if VISION_FAST_MODE else IMAGE_MIN_VISION_PX
    work_path = _maybe_crop_image_path(source_path.resolve())
    with Image.open(work_path) as img:
        work = _to_rgb_work_image(img)
        work = ImageEnhance.Contrast(work).enhance(1.2)
        work = ImageEnhance.Sharpness(work).enhance(1.4)

        width, height = work.size
        longest = max(width, height)
        if longest < min_px:
            scale = min_px / float(longest)
            work = work.resize(
                (max(1, int(width * scale)), max(1, int(height * scale))),
                Image.Resampling.LANCZOS,
            )
            width, height = work.size
            longest = max(width, height)
        if longest > max_px:
            scale = max_px / float(longest)
            work = work.resize(
                (max(1, int(width * scale)), max(1, int(height * scale))),
                Image.Resampling.LANCZOS,
            )

        from io import BytesIO

        buf = BytesIO()
        work.save(
            buf,
            format="JPEG",
            quality=IMAGE_JPEG_QUALITY,
            optimize=True,
            progressive=True,
        )
        return buf.getvalue(), "image/jpeg"


def _suffix_to_mime(path: Path) -> str:
    mapping = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }
    return mapping.get(path.suffix.lower(), "image/jpeg")


def _image_bytes_for_gemini(img: Image.Image) -> tuple[bytes, str]:
    """ממיר תמונה ל-JPEG לשליחה ל-Gemini (כולל תיקון EXIF)."""
    buf = BytesIO()
    img.save(
        buf,
        format="JPEG",
        quality=IMAGE_JPEG_QUALITY,
        optimize=True,
    )
    return buf.getvalue(), "image/jpeg"


def _request_beam_bbox(
    image_bytes: bytes,
    mime_type: str,
    *,
    client=None,
    model: str | None = None,
) -> dict:
    if client is None:
        client, _ = gemini_runtime()
    if model is None:
        # חיתוך — מודל קל כדי לא להעמיס על flash הראשי
        _, primary = gemini_runtime()
        model = FALLBACK_MODELS[0] if FALLBACK_MODELS else primary
    crop_contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                types.Part.from_text(text=BEAM_CROP_PROMPT),
            ],
        )
    ]
    crop_config = types.GenerateContentConfig(
        temperature=0.0,
        max_output_tokens=256,
        response_mime_type="application/json",
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )
    response = generate_content_with_retries(
        client,
        model=model,
        contents=crop_contents,
        config=crop_config,
    )
    text = response.text
    if not text or not str(text).strip():
        raise BeamCropError("Gemini לא החזיר קואורדינטות לחיתוך הקורה")
    parsed = parse_json_from_llm_text(str(text))
    if not isinstance(parsed, dict):
        raise BeamCropError("תשובת Gemini לחיתוך אינה אובייקט JSON תקין")
    return parsed


def _bbox_dict_to_pixels(
    bbox: dict,
    width: int,
    height: int,
    *,
    padding_ratio: float,
) -> tuple[int, int, int, int]:
    """ממיר left/top/right/bottom מנורמלים ל-(left, upper, right, lower) בפיקסלים."""
    try:
        left = float(bbox["left"])
        top = float(bbox["top"])
        right = float(bbox["right"])
        bottom = float(bbox["bottom"])
    except (KeyError, TypeError, ValueError) as exc:
        raise BeamCropError("קואורדינטות חיתוך חסרות או לא תקינות") from exc

    for name, value in (("left", left), ("top", top), ("right", right), ("bottom", bottom)):
        if not 0.0 <= value <= 1.0:
            raise BeamCropError(f"קואורדינטת {name} מחוץ לטווח 0–1: {value}")

    if right <= left or bottom <= top:
        raise BeamCropError("תיבת החיתוך ריקה או הפוכה (right≤left או bottom≤top)")

    pad_x = int(width * padding_ratio)
    pad_y = int(height * padding_ratio)
    x0 = max(0, int(left * width) - pad_x)
    y0 = max(0, int(top * height) - pad_y)
    x1 = min(width, int(right * width) + pad_x)
    y1 = min(height, int(bottom * height) + pad_y)

    if x1 - x0 < 8 or y1 - y0 < 8:
        raise BeamCropError("תיבת החיתוך קטנה מדי לאחר המרה לפיקסלים")

    return x0, y0, x1, y1


def crop_beam_from_image(
    image_path: str | Path,
    *,
    output_path: str | Path | None = None,
    padding_ratio: float = 0.02,
    min_confidence: str = "low",
    client=None,
    model: str | None = None,
) -> Path:
    """מאתר שרטוט קורה בתמונה (Gemini) וחותך אותו עם Pillow.

    Args:
        image_path: נתיב לקובץ תמונה מקורי.
        output_path: יעד לשמירה; ברירת מחדל — ``{stem}_beam_crop.jpg`` ליד המקור.
        padding_ratio: שוליים יחסיים סביב התיבה (0.02 = 2%).
        min_confidence: ``high`` | ``medium`` | ``low`` — דחיית תוצאות חלשות מדי.
        client, model: אופציונלי — לקוח Gemini; אחרת ``gemini_runtime()``.

    Returns:
        נתיב לקובץ JPEG החתוך.

    Raises:
        FileNotFoundError: הקובץ לא קיים.
        BeamNotFoundError: לא זוהתה קורה בתמונה.
        BeamCropError: תשובת Gemini לא תקינה או חיתוך בלתי אפשרי.
    """
    source = Path(image_path).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"תמונה לא נמצאה: {source}")

    confidence_rank = {"low": 0, "medium": 1, "high": 2}
    min_rank = confidence_rank.get(min_confidence.lower(), 0)

    try:
        with Image.open(source) as opened:
            img = ImageOps.exif_transpose(_to_rgb_work_image(opened))
            width, height = img.size
            vision_bytes, vision_mime = _image_bytes_for_gemini(img)

        bbox = _request_beam_bbox(
            vision_bytes,
            vision_mime,
            client=client,
            model=model,
        )

        found = bbox.get("found")
        if found is False or str(found).lower() == "false":
            raise BeamNotFoundError("לא זוהה שרטוט קורה בתמונה")

        confidence = str(bbox.get("confidence", "low")).lower()
        if confidence_rank.get(confidence, 0) < min_rank:
            raise BeamNotFoundError(
                f"זיהוי קורה לא מספיק בטוח (confidence={confidence})"
            )

        x0, y0, x1, y1 = _bbox_dict_to_pixels(
            bbox,
            width,
            height,
            padding_ratio=padding_ratio,
        )
        cropped = img.crop((x0, y0, x1, y1))

        if output_path is None:
            dest = source.with_name(f"{source.stem}_beam_crop.jpg")
        else:
            dest = Path(output_path).resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)
        cropped.save(dest, format="JPEG", quality=IMAGE_JPEG_QUALITY, optimize=True)

        log.info(
            "Beam crop saved: %s (%dx%d -> %dx%d, box=%s)",
            dest.name,
            width,
            height,
            cropped.size[0],
            cropped.size[1],
            bbox,
        )
        return dest

    except (BeamNotFoundError, BeamCropError, FileNotFoundError):
        raise
    except Exception as exc:
        raise BeamCropError(f"חיתוך קורה נכשל: {exc}") from exc
