# -*- coding: utf-8 -*-
"""שליחת טיוטת שרטוט (PNG) + הודעת הסבר עם כפתור אישור."""
from __future__ import annotations

import logging
from io import BytesIO

from telegram.error import BadRequest
from telegram.ext import ContextTypes

from bot.draft_keyboard import (
    DRAFT_FIXED_TEXT,
    DRAFT_INSTRUCTION_TEXT,
    build_draft_approve_keyboard,
)
from bot.draft_session import (
    clear_draft_cleanup_state,
    get_draft_cleanup_message_ids,
    get_draft_message_ref,
    get_draft_photo_message_id,
    register_draft_cleanup_id,
    set_draft_pending,
    set_draft_photo_message_id,
)
from bot.notebook_render import render_exercise_problem_png_bytes

log = logging.getLogger("beam_telegram_bot")


async def _delete_message_silent(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    message_id: int | None,
) -> None:
    if message_id is None:
        return
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=int(message_id))
    except BadRequest as exc:
        err = str(exc).lower()
        if "message to delete not found" in err or "message can't be deleted" in err:
            return
        log.warning(
            "Draft delete BadRequest chat=%s mid=%s: %s", chat_id, message_id, exc
        )
    except Exception as exc:
        log.warning(
            "Draft message delete failed chat=%s mid=%s: %s", chat_id, message_id, exc
        )


async def send_draft_preview(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    extracted: dict,
    *,
    reply_to_message=None,
) -> bool:
    """שולח תמונת שרטוט ואז הודעת הסבר עם אישור. True אם נשלח בהצלחה."""
    png = render_exercise_problem_png_bytes(extracted)
    if not png:
        log.warning("Draft preview render failed chat=%s", chat_id)
        return False

    keyboard = build_draft_approve_keyboard()
    photo_msg = None
    try:
        bio = BytesIO(png)
        bio.name = "draft_preview.png"
        if reply_to_message is not None:
            photo_msg = await reply_to_message.reply_photo(photo=bio)
        else:
            photo_msg = await context.bot.send_photo(chat_id=chat_id, photo=bio)
    except Exception as exc:
        log.warning("Draft preview photo send failed chat=%s: %s", chat_id, exc)
        return False

    try:
        if reply_to_message is not None:
            instruct = await reply_to_message.reply_text(
                DRAFT_INSTRUCTION_TEXT,
                reply_markup=keyboard,
            )
        else:
            instruct = await context.bot.send_message(
                chat_id=chat_id,
                text=DRAFT_INSTRUCTION_TEXT,
                reply_markup=keyboard,
            )
    except Exception as exc:
        log.warning("Draft instruction send failed chat=%s: %s", chat_id, exc)
        if photo_msg is not None:
            await _delete_message_silent(context, chat_id, photo_msg.message_id)
        return False

    set_draft_pending(
        chat_id,
        extracted,
        DRAFT_INSTRUCTION_TEXT,
        message_id=instruct.message_id,
        photo_message_id=photo_msg.message_id,
        clear_edit=True,
    )
    register_draft_cleanup_id(chat_id, photo_msg.message_id)
    register_draft_cleanup_id(chat_id, instruct.message_id)
    return True


async def replace_draft_preview_photo(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    extracted: dict,
) -> tuple[bool, str | None]:
    """מוחק שרטוט קודם ושולח חדש. מחזיר (ok, error_he)."""
    png = render_exercise_problem_png_bytes(extracted)
    if not png:
        return False, "לא הצלחתי לרנדר את השרטוט אחרי העדכון."

    old_photo_id = get_draft_photo_message_id(chat_id)
    try:
        bio = BytesIO(png)
        bio.name = "draft_preview.png"
        sent = await context.bot.send_photo(chat_id=chat_id, photo=bio)
    except Exception as exc:
        log.warning("Draft preview re-send failed chat=%s: %s", chat_id, exc)
        return False, "לא הצלחתי לשלוח את השרטוט המעודכן."

    set_draft_photo_message_id(chat_id, sent.message_id)
    register_draft_cleanup_id(chat_id, sent.message_id)

    if old_photo_id is not None and old_photo_id != sent.message_id:
        await _delete_message_silent(context, chat_id, old_photo_id)
    return True, None


async def refresh_draft_after_correction(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    extracted: dict,
    *,
    user_message_id: int | None = None,
) -> tuple[bool, str | None]:
    """אחרי תיקון NL: מוחק הודעת משתמש + הודעת טיוטה ישנה, שולח שרטוט + «תיקנתי» עם אישור."""
    old_ref = get_draft_message_ref(chat_id)
    old_instruct_id = old_ref[1] if old_ref else None

    ok, render_err = await replace_draft_preview_photo(context, chat_id, extracted)
    if not ok:
        return False, render_err

    keyboard = build_draft_approve_keyboard()
    try:
        instruct = await context.bot.send_message(
            chat_id=chat_id,
            text=DRAFT_FIXED_TEXT,
            reply_markup=keyboard,
        )
    except Exception as exc:
        log.warning("Draft fixed text send failed chat=%s: %s", chat_id, exc)
        return False, "השרטוט עודכן, אבל שליחת הודעת האישור נכשלה."

    photo_id = get_draft_photo_message_id(chat_id)
    set_draft_pending(
        chat_id,
        extracted,
        DRAFT_FIXED_TEXT,
        message_id=instruct.message_id,
        photo_message_id=photo_id,
        clear_edit=True,
    )
    register_draft_cleanup_id(chat_id, instruct.message_id)
    if photo_id is not None:
        register_draft_cleanup_id(chat_id, photo_id)

    # מחיקות אחרי שליחה מוצלחת — כדי שלא נישאר בלי טיוטה אם משהו נכשל באמצע
    await _delete_message_silent(context, chat_id, user_message_id)
    if old_instruct_id is not None and old_instruct_id != instruct.message_id:
        await _delete_message_silent(context, chat_id, old_instruct_id)
    return True, None


async def wipe_draft_conversation(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    *,
    message_ids: list[int] | None = None,
) -> None:
    """מוחק הודעות טיוטה (בוט + תיקוני משתמש) — בלי תמונת המקור של המשתמש."""
    ids = list(message_ids) if message_ids is not None else []
    # ממזגים גם מה שנשמר ב-bundle (אחרי approve) — רשת ביטחון אם הצילום היה חלקי
    ids.extend(get_draft_cleanup_message_ids(chat_id, keep_user_source=True))
    ids = list(dict.fromkeys(int(m) for m in ids if m is not None))
    if not ids:
        log.warning("Draft wipe chat=%s: no message ids to delete", chat_id)
    else:
        log.info("Draft wipe chat=%s messages=%s", chat_id, ids)
    for mid in ids:
        await _delete_message_silent(context, chat_id, mid)
    clear_draft_cleanup_state(chat_id)


async def delete_draft_photo(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
) -> None:
    photo_id = get_draft_photo_message_id(chat_id)
    if photo_id is None:
        return
    set_draft_photo_message_id(chat_id, None)
    await _delete_message_silent(context, chat_id, photo_id)
