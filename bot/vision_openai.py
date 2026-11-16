# -*- coding: utf-8 -*-
"""מסלול OpenAI לתמונת תרגיל: שער (gate) -> חילוץ בקריאה אחת -> ולידציה בקוד -> טיוטה.

הפלט הוא ``extracted`` בפורמט הטיוטה הקיים (beam.supports / beam.loads) —
התצוגה, העריכה והחישוב אחרי אישור הם המנגנונים הקיימים. הקובץ לא מחשב דבר.
"""
from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from io import BytesIO
from typing import Literal

import httpx
from PIL import Image
from pydantic import BaseModel

from bot.config import (
    KN_PER_TON,
    OPENAI_BASE_URL,
    OPENAI_EXTRACT_MODEL,
    OPENAI_GATE_MODEL,
    OPENAI_IMAGE_MAX_PX,
    OPENAI_TIMEOUT_SEC,
    VISION_PROVIDER,
)
from bot.draft_format import _recompute_inclined_components, sync_beam_distributed_loads
from bot.env import env
from bot.prompt_loader import load_prompt_text
from bot.vision import resolve_beam_support_geometry

log = logging.getLogger("beam_telegram_bot")

# --- הודעות למשתמש (עברית) ---
MSG_NOT_STATICS = (
    "התמונה שנשלחה אינה תרגיל סטטיקה.\n"
    "שלח/י תמונה של קורה עם הסמכים והעומסים."
)
MSG_UNSUPPORTED_SUPPORTS = (
    "זה תרגיל סטטיקה, אבל הבוט תומך רק בקורה על שני סמכים (נעץ וגליל) "
    "או בקורה עם סמך אחד רתום (ריתום)."
)
MSG_UNSUPPORTED_DATA = "לא ניתן להמשיך. נתונים חסרים או שאינם נתמכים:"
MSG_READY = "הטיוטה מוכנה לבדיקה. עבור/י על הנתונים, תקן/י אם צריך ולחץ/י אישור."

_MAX_LISTED_ITEMS = 12
_POS_TOL_M = 0.01


# --- סכמות pydantic (כל שדה שלא נראה בתמונה חייב להיות null) ---
class GateVerdict(BaseModel):
    is_statics: bool
    support_type: Literal["two_supports", "fixed", "other", "none"]
    reason: str


class DraftSupport(BaseModel):
    type: Literal["pin", "roller", "fixed", "other"] | None
    x: float | None


class DraftLoad(BaseModel):
    type: Literal["point", "distributed", "moment", "inclined", "other"] | None
    description: str | None
    x: float | None
    x_end: float | None
    magnitude: float | None
    unit: Literal["kN", "ton", "kN/m", "ton/m", "kN*m", "ton*m"] | None
    direction: (
        Literal["down", "up", "left", "right", "cw", "ccw", "down_right", "down_left"] | None
    )
    angle_deg: float | None
    shape: Literal["rectangular", "triangular_peak_right", "triangular_peak_left"] | None


class DraftExtraction(BaseModel):
    beam_length: float | None
    length_unit: Literal["m", "cm", "mm"] | None
    supports: list[DraftSupport]
    loads: list[DraftLoad]


@dataclass
class OpenAIOutcome:
    status: Literal["not_statics", "unsupported_supports", "unsupported_data", "ready"]
    message: str
    extracted: dict | None = None


def openai_provider_enabled() -> bool:
    """True רק כש-VISION_PROVIDER=openai וקיים OPENAI_API_KEY; אחרת נשארים על Gemini."""
    if VISION_PROVIDER != "openai":
        return False
    if not env("OPENAI_API_KEY"):
        log.warning("VISION_PROVIDER=openai but OPENAI_API_KEY is missing — using Gemini")
        return False
    return True


# --- קריאות API ---
def _to_data_url(image_bytes: bytes, mime_type: str) -> str:
    """מקטין רק אם הצלע הארוכה גדולה מהמקסימום; אף פעם לא מגדיל."""
    try:
        with Image.open(BytesIO(image_bytes)) as img:
            longest = max(img.size)
            if longest > OPENAI_IMAGE_MAX_PX:
                scale = OPENAI_IMAGE_MAX_PX / float(longest)
                small = img.convert("RGB").resize(
                    (max(1, int(img.width * scale)), max(1, int(img.height * scale))),
                    Image.Resampling.LANCZOS,
                )
                buf = BytesIO()
                small.save(buf, format="JPEG", quality=90)
                image_bytes, mime_type = buf.getvalue(), "image/jpeg"
    except OSError as exc:
        log.warning("OpenAI image downscale skipped: %s", exc)
    b64 = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime_type or 'image/jpeg'};base64,{b64}"


def _client() -> httpx.Client:
    """קריאות REST ישירות דרך httpx (כבר תלות של הבוט) — בלי חבילת openai."""
    return httpx.Client(
        base_url=OPENAI_BASE_URL,
        headers={"Authorization": f"Bearer {env('OPENAI_API_KEY')}"},
        timeout=OPENAI_TIMEOUT_SEC,
    )


def _strict_schema(node):
    """מתאים סכמת pydantic לפורמט strict של OpenAI: כל השדות חובה, בלי שדות נוספים."""
    if isinstance(node, dict):
        if "properties" in node:
            node["additionalProperties"] = False
            node["required"] = list(node["properties"].keys())
        for value in node.values():
            _strict_schema(value)
    elif isinstance(node, list):
        for item in node:
            _strict_schema(item)
    return node


def _structured_call(
    client: httpx.Client,
    *,
    model: str,
    system: str,
    data_url: str,
    detail: str,
    schema: type[BaseModel],
    max_tokens: int,
):
    """קריאה אחת עם פלט JSON קשיח; האימות הסופי ב-pydantic."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Analyze this image."},
                    {"type": "image_url", "image_url": {"url": data_url, "detail": detail}},
                ],
            },
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": schema.__name__,
                "strict": True,
                "schema": _strict_schema(schema.model_json_schema()),
            },
        },
        "reasoning_effort": "low",
        "max_completion_tokens": max_tokens,
    }
    response = client.post("/chat/completions", json=payload)
    if response.status_code >= 400:
        raise ValueError(f"OpenAI HTTP {response.status_code}: {response.text[:300]}")
    message = response.json()["choices"][0]["message"]
    if message.get("refusal"):
        raise ValueError(f"OpenAI refused: {message['refusal']}")
    content = message.get("content")
    if not content:
        raise ValueError("OpenAI returned empty content")
    return schema.model_validate_json(content)


# --- ולידציה בקוד ובניית טיוטה ---
_LENGTH_TO_M = {"m": 1.0, "cm": 0.01, "mm": 0.001}
_SUPPORT_HE = {"pin": "נעץ", "roller": "גליל", "fixed": "ריתום"}
_KIND_HE = {
    "point": "נקודתי",
    "distributed": "מפורס",
    "moment": "מומנט",
    "inclined": "אלכסוני",
}
_UNITS_FOR_KIND = {
    "point": ("kN", "ton"),
    "inclined": ("kN", "ton"),
    "distributed": ("kN/m", "ton/m"),
    "moment": ("kN*m", "ton*m"),
}
_DIRS_FOR_KIND = {
    "point": ("down", "up", "left", "right"),
    "moment": ("cw", "ccw"),
    "inclined": ("down_right", "down_left"),
    "distributed": ("down", "up"),
}


def _r(value: float) -> float:
    return round(float(value), 6)


def _fmt(value: float) -> str:
    return f"{value:g}"


def _issues_message(header: str, issues: list[str]) -> str:
    shown = issues[:_MAX_LISTED_ITEMS]
    lines = [header] + [f"- {item}" for item in shown]
    if len(issues) > len(shown):
        lines.append(f"- ועוד {len(issues) - len(shown)} פריטים")
    return "\n".join(lines)


def build_draft_from_extraction(ex: DraftExtraction) -> OpenAIOutcome:
    """ולידציה בקוד (לא במודל) ובניית ``extracted`` בפורמט הטיוטה הקיים."""
    support_issues: list[str] = []
    data_issues: list[str] = []

    # אורך ויחידות
    factor = _LENGTH_TO_M.get(ex.length_unit or "")
    L: float | None = None
    if ex.beam_length is None or ex.beam_length <= 0:
        data_issues.append("אורך הקורה לא מופיע בתמונה")
    else:
        if factor is None:
            # בלי יחידה כתובה: מתחת ל-100 — מטרים, מ-100 ומעלה — סנטימטרים (כל המידות באותה יחידה)
            factor = 1.0 if ex.beam_length < 100 else 0.01
        L = ex.beam_length * factor

    def pos_m(value: float | None, name: str) -> float | None:
        if value is None:
            data_issues.append(f"{name}: המיקום חסר")
            return None
        if factor is None or L is None:
            return None
        xm = value * factor
        if xm < -_POS_TOL_M or xm > L + _POS_TOL_M:
            data_issues.append(
                f"{name}: המיקום x={_fmt(round(xm, 3))} מ' מחוץ לקורה [0, {_fmt(round(L, 3))}]"
            )
            return None
        return min(max(xm, 0.0), L)

    # סמכים
    kinds = [s.type for s in ex.supports]
    n = len(kinds)
    if n == 0:
        support_issues.append("לא זוהו סמכים בתמונה")
    elif n >= 3:
        support_issues.append(f"זוהו {n} סמכים")
    elif "other" in kinds:
        support_issues.append("זוהה סמך שאינו נעץ, גליל או ריתום")
    elif None in kinds:
        data_issues.append("סוג אחד הסמכים לא ברור בתמונה")
    elif n == 2 and sorted(kinds) != ["pin", "roller"]:
        found = " + ".join(_SUPPORT_HE[k] for k in kinds)
        support_issues.append(f"שני הסמכים אינם צמד נעץ וגליל (זוהה: {found})")
    elif n == 1 and kinds[0] != "fixed":
        support_issues.append(f"זוהה סמך יחיד מסוג {_SUPPORT_HE[kinds[0]]} (נדרש ריתום)")
    if support_issues:
        return OpenAIOutcome(
            "unsupported_supports",
            _issues_message(MSG_UNSUPPORTED_SUPPORTS, support_issues),
        )

    supports_out: list[dict] = []
    if None not in kinds:
        for sup in sorted(ex.supports, key=lambda s: 0 if s.type in ("pin", "fixed") else 1):
            label = "B" if sup.type == "roller" else "A"
            xm = pos_m(sup.x, f"סמך {_SUPPORT_HE[sup.type]}")
            if xm is None:
                continue
            if sup.type == "fixed" and L is not None:
                if xm <= _POS_TOL_M:
                    xm = 0.0
                elif xm >= L - _POS_TOL_M:
                    xm = L
                else:
                    support_issues.append("הריתום נמצא באמצע הקורה ולא בקצה")
                    continue
            supports_out.append({"label": label, "type": sup.type, "x": _r(xm), "_user_x": True})
    if len(supports_out) == 2 and abs(supports_out[0]["x"] - supports_out[1]["x"]) <= _POS_TOL_M:
        support_issues.append("שני הסמכים באותו מיקום")
    if support_issues:
        return OpenAIOutcome(
            "unsupported_supports",
            _issues_message(MSG_UNSUPPORTED_SUPPORTS, support_issues),
        )

    # עומסים
    loads_out: list[dict] = []
    if not ex.loads:
        data_issues.append("לא זוהו עומסים בתמונה")
    for idx, ld in enumerate(ex.loads, 1):
        kind = ld.type
        if kind is None:
            data_issues.append(f"עומס {idx}: סוג העומס לא ברור")
            continue
        if kind == "other":
            data_issues.append(
                f"עומס {idx}: סוג עומס לא נתמך ({ld.description or 'לא ידוע'})"
            )
            continue
        name = f"עומס {_KIND_HE[kind]} {idx}"
        before = len(data_issues)

        x1 = pos_m(ld.x, name)
        x2: float | None = None
        if kind == "distributed":
            x2 = pos_m(ld.x_end, f"{name} (סוף הטווח)")
            if x1 is not None and x2 is not None and x2 - x1 <= _POS_TOL_M:
                data_issues.append(f"{name}: טווח העומס לא תקין")

        direction = ld.direction
        has_mag = ld.magnitude is not None
        mag_ton: float | None = None
        # עוצמה/יחידה/כיוון לא ברורים — השורה נשארת ריקה לתיקון בטיוטה (בלי ניחוש, בלי עצירה)
        if direction is not None and direction not in _DIRS_FOR_KIND[kind]:
            direction = None
        if (
            has_mag
            and ld.magnitude > 0
            and direction is not None
            and ld.unit in _UNITS_FOR_KIND[kind]
        ):
            mag_ton = ld.magnitude / KN_PER_TON if ld.unit.startswith("kN") else ld.magnitude

        shape = "rectangular"
        if kind == "distributed":
            if direction == "up":
                data_issues.append(f"{name}: עומס מפורס כלפי מעלה אינו נתמך")
            if ld.shape is None:
                data_issues.append(f"{name}: צורת העומס המפורס לא ברורה")
            elif ld.shape == "triangular_peak_left":
                data_issues.append(f"{name}: עומס משולש עם שיא בצד שמאל אינו נתמך")
            elif ld.shape == "triangular_peak_right":
                shape = "triangular"

        angle = ld.angle_deg
        if kind == "inclined" and angle is not None and not (0.0 < angle < 90.0):
            angle = None
        if kind == "inclined" and angle is None:
            mag_ton = None  # בלי זווית אי אפשר לפרק לרכיבים — השורה נשארת ריקה

        if len(data_issues) != before or x1 is None:
            continue

        # פורמט הטיוטה הקיים; עוצמה חסרה = שורה ריקה (_draft_new) למילוי ע"י המשתמש.
        if kind == "point":
            entry: dict = {"type": "point", "x": _r(x1), "Fy": 0.0, "Fx": 0.0, "_user_x": True}
            if mag_ton is None:
                entry["_draft_new"] = True
                if direction in ("left", "right"):
                    entry["_draft_axial"] = True
            else:
                m = _r(mag_ton)
                if direction == "down":
                    entry["Fy"] = m
                elif direction == "up":
                    entry["Fy"] = -m
                elif direction == "right":
                    entry["Fx"] = m
                else:
                    entry["Fx"] = -m
                entry["direction"] = direction
                entry["_user_mag"] = True
        elif kind == "moment":
            entry = {"type": "moment", "x": _r(x1), "M": 0.0, "_user_x": True}
            if mag_ton is None:
                entry["_draft_new"] = True
            else:
                entry["M"] = _r(mag_ton) if direction == "cw" else -_r(mag_ton)
                entry["_user_mag"] = True
        elif kind == "inclined":
            incl_dir = "dl" if direction == "down_left" else "dr"
            entry = {
                "type": "inclined",
                "x": _r(x1),
                "magnitude_ton": 0.0,
                "angle_deg": float(angle) if angle is not None else 45.0,
                "incl_dir": incl_dir,
                "_user_x": True,
            }
            if mag_ton is None:
                entry["_draft_new"] = True
            else:
                fx, fy = _recompute_inclined_components(mag_ton, float(angle), incl_dir=incl_dir)
                entry.update(
                    {"magnitude_ton": _r(mag_ton), "Fx": _r(fx), "Fy": _r(fy), "_user_mag": True}
                )
        else:
            w = _r(mag_ton) if mag_ton is not None else 0.0
            entry = {
                "type": "distributed",
                "x1": _r(x1),
                "x2": _r(x2),
                "start_x": _r(x1),
                "end_x": _r(x2),
                "w": w,
                "shape": shape,
                "_user_span": True,
            }
            if shape == "triangular":
                entry["w_start"] = 0.0
                entry["w_end"] = w
            if mag_ton is None:
                entry["_draft_new"] = True
            else:
                entry["_user_mag"] = True
        loads_out.append(entry)

    if data_issues:
        return OpenAIOutcome(
            "unsupported_data", _issues_message(MSG_UNSUPPORTED_DATA, data_issues)
        )

    mode = "cantilever" if supports_out[0]["type"] == "fixed" else "simply_supported"
    beam: dict = {
        "structure_type": mode,
        "support_mode": mode,
        "L": _r(L),
        "_user_L": True,
        "origin": "left_end_of_beam_axis",
        "supports": supports_out,
        "loads": loads_out,
    }
    sync_beam_distributed_loads(beam)
    _, beam["ra_pos"], beam["rb_pos"] = resolve_beam_support_geometry(beam)
    extracted = {
        "exercise_type": "beam",
        "beam": beam,
        "extraction_pipeline": "openai_single",
        # המומנטים כבר בסימן האתר (עם השעון = חיובי) — מונע היפוך ב-finalize.
        "_moment_sign_aligned": True,
    }
    return OpenAIOutcome("ready", MSG_READY, extracted)


# --- נקודת כניסה ---
def analyze_exercise_image(image_bytes: bytes, mime_type: str) -> OpenAIOutcome:
    """שער -> (רק אם עבר) חילוץ בקריאה אחת -> ולידציה. סינכרוני; להריץ ב-to_thread."""
    client = _client()
    data_url = _to_data_url(image_bytes, mime_type)

    gate = _structured_call(
        client,
        model=OPENAI_GATE_MODEL,
        system=load_prompt_text("vision/openai_gate.txt"),
        data_url=data_url,
        detail="auto",
        schema=GateVerdict,
        max_tokens=1500,
    )
    log.info("OpenAI gate: %s", gate.model_dump())
    if not gate.is_statics:
        return OpenAIOutcome("not_statics", MSG_NOT_STATICS)
    if gate.support_type not in ("two_supports", "fixed"):
        reason = gate.reason.strip()[:200]
        message = MSG_UNSUPPORTED_SUPPORTS + (f"\n- {reason}" if reason else "")
        return OpenAIOutcome("unsupported_supports", message)

    extraction = _structured_call(
        client,
        model=OPENAI_EXTRACT_MODEL,
        system=load_prompt_text("vision/openai_extract.txt"),
        data_url=data_url,
        detail="high",
        schema=DraftExtraction,
        max_tokens=8000,
    )
    log.info("OpenAI extraction: %s", extraction.model_dump())
    return build_draft_from_extraction(extraction)
