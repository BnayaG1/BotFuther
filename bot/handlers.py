# -*- coding: utf-8 -*-
"""Handlers טלגרם — חילוץ מתמונות + טיוטה + פתרון מלא."""
from __future__ import annotations

import asyncio
import logging
import time

from telegram import (
    ForceReply,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from bot.config import (
    ADMIN_CHAT_ID,
    BOT_DISPLAY_NAME,
    COUPON_ACCESS_ENABLED,
    FREE_TRIAL_IMAGES,
    IMAGE_ONLY_TEXT_REPLY,
    VISION_ASYNC_ENABLED,
)
from bot.access import (
    ImageAccessStatus,
    check_image_access,
    consume_image_slot,
    coupon_prompt_text_hebrew,
    create_purchase_request,
    image_access_reply_hebrew,
    looks_like_coupon_code,
    ping_reply_hebrew,
    quota_status_reply_hebrew,
    redeem_coupon,
    redeem_reply_hebrew,
)
from bot.purchase import (
    admin_purchase_notification_hebrew,
    build_package_confirm_keyboard,
    build_payment_keyboard,
    build_purchase_menu_keyboard,
    get_package,
    parse_buy_callback,
    payment_instructions_hebrew,
    package_confirm_text_hebrew,
    purchase_menu_intro_hebrew,
)
from bot.draft_editor import (
    add_empty_load,
    apply_field_edit,
    approve_and_solve,
    delete_load,
    handle_draft_text,
    looks_like_draft_patch,
    persist_draft,
    set_load_type,
    toggle_any_load_direction,
)
from bot.draft_keyboard import (
    build_draft_keyboard,
    build_load_dir_prompt_keyboard,
    draft_display_text,
    edit_prompt,
    parse_draft_callback,
)
from bot.notebook_render import render_notebook_png_temp
from bot.gemini_chat import friendly_gemini_error
from bot.solution_session import begin_image_session, reset_user_session
from bot.images import TempImageFile, prepare_image_for_vision, save_message_image_to_temp
from bot.system_prompt import reload_system_instruction_if_changed
from bot.vision import (
    finalize_beam_extraction,
    format_vision_extract_only_reply,
    get_draft_edit,
    get_draft_edit_prompt_id,
    get_draft_message_ref,
    get_draft_type_picker_idx,
    get_stored_vision_extracted,
    is_draft_pending,
    package_extraction_response,
    set_draft_edit,
    set_draft_edit_prompt_id,
    set_draft_type_picker_idx,
    set_draft_pending,
)
from bot.vision_queue import (
    run_vision_extract,
    schedule_vision_job,
    send_vision_ack,
    typing_while_waiting,
)

log = logging.getLogger("beam_telegram_bot")

_TEXT_UNHANDLED = (
    "שלח תמונה 📸 של תרגיל, או עדכן את הטיוטה הפעילה בכפתורים."
)

_IMAGE_DEDUP_SEC = 120.0
_recent_image_keys: dict[tuple[int, int], float] = {}
_coupon_prompt_chats: set[int] = set()

def telegram_chat_id(update: Update) -> int:
    chat = update.effective_chat
    if chat is None:
        raise ValueError("אין מזהה צ'אט")
    return int(chat.id)


def telegram_user_id(update: Update) -> int:
    user = update.effective_user
    if user is None:
        raise ValueError("אין מזהה משתמש")
    return int(user.id)


async def _reply_text_safe(
    message,
    text: str,
    *,
    parse_mode: str = "Markdown",
    reply_markup: object | None = None,
) -> None:
    """שולח הודעה; אם Markdown נשבר — fallback לטקסט רגיל."""
    try:
        await message.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
    except BadRequest as exc:
        if "parse entities" not in str(exc).lower():
            raise
        log.warning("Telegram Markdown failed, sending plain text: %s", exc)
        await message.reply_text(text, reply_markup=reply_markup)

async def _send_text_safe(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    text: str,
    *,
    parse_mode: str = "Markdown",
    reply_markup: object | None = None,
) -> None:
    """שולח הודעה חדשה לצ'אט (לא reply) עם fallback אם Markdown נשבר."""
    try:
        await context.bot.send_message(
            chat_id=chat_id, text=text, parse_mode=parse_mode, reply_markup=reply_markup
        )
    except BadRequest as exc:
        if "parse entities" not in str(exc).lower():
            raise
        await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)


async def _deliver_approved_solve(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    *,
    extracted: dict,
    reply: str,
    solved: dict,
    draft_msg_id: int | None,
) -> None:
    """אחרי אישור טיוטה: טקסט פתרון ואז תמונת מחברת מלאה."""
    has_result = bool((solved or {}).get("result"))
    notebook_path = None

    if reply:
        await _send_text_safe(context, chat_id, reply)

    if has_result:
        notebook_path = render_notebook_png_temp(extracted, solved)
        if notebook_path is not None:
            try:
                with notebook_path.open("rb") as photo:
                    await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo,
                        caption="📓 פתרון מחברת מלא",
                    )
            except Exception as exc:
                log.warning("Failed to send notebook chat=%s: %s", chat_id, exc)

    if draft_msg_id is not None:
        if has_result:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=draft_msg_id)
            except BadRequest:
                pass
        else:
            await _edit_draft_message_safe(
                context,
                chat_id,
                draft_msg_id,
                extracted,
                errors=[reply] if reply else None,
            )

    if notebook_path is not None:
        notebook_path.unlink(missing_ok=True)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    text = build_start_welcome_text()
    keyboard = build_start_keyboard()
    try:
        await update.message.reply_text(
            text,
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
    except BadRequest as exc:
        if "parse entities" not in str(exc).lower():
            raise
        await update.message.reply_text(text, reply_markup=keyboard)


def build_start_welcome_text() -> str:
    lines = [
        "היי! 👋\n"
        "ברוך הבא למהנדס הדיגיטלי.\n\n"
        "סטטיקה הוא מקצוע מאתגר — ולעיתים קרובות לוקח זמן להבין ולהתקדם.\n"
        "הבוט הזה נועד *לייעל ולקצר* את תהליך הלמידה שלך.\n\n"
        "*מה אני עושה?*\n"
        "אתה שולח/ת **תמונה** של תרגיל סטטיקה (קורה, עומסים, 2 סמכים, ריתום) — "
        "ואני מחזיר טיוטה לאישור ופתרון מחברת מלא.\n\n"
        "*איך מתחילים?*\n"
        "צלם/י את התרגיל או שלח/י כקובץ 📎, ואטפל בשאר.",
    ]
    if COUPON_ACCESS_ENABLED and FREE_TRIAL_IMAGES > 0:
        lines.append(
            f"\n\n*ניסיון חינם:* מקבל/ת *{FREE_TRIAL_IMAGES} תמונות ניסיון* לפני שצריך קופון.\n"
            "אחרי הניסיון — אפשר לרכוש חבילה או להפעיל קוד קופון מהתפריט."
        )
    elif COUPON_ACCESS_ENABLED:
        lines.append(
            "\n\n*מכסה:* נדרש קוד קופון — «🎟️ הזן קוד קופון» בתפריט או /coupon."
        )
    lines.append("\n\nמוכן/ה? שלח/י תמונה 📸")
    return "".join(lines)


def build_upgrade_options_keyboard() -> InlineKeyboardMarkup:
    """אפשרויות המשך אחרי סיום ניסיון חינם."""
    rows: list[list[InlineKeyboardButton]] = []
    if COUPON_ACCESS_ENABLED:
        rows.append(
            [InlineKeyboardButton("🛒 רכישת חבילה", callback_data="buy:menu")]
        )
        rows.append(
            [InlineKeyboardButton("🎟️ יש לי קוד", callback_data="buy:redeem")]
        )
    return InlineKeyboardMarkup(rows)


def build_start_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton("📸 שלח תמונה של תרגיל", callback_data="menu:new")],
    ]
    if COUPON_ACCESS_ENABLED:
        rows.append(
            [InlineKeyboardButton("🎟️ הזנת קוד קופון", callback_data="buy:redeem")]
        )
        rows.append(
            [InlineKeyboardButton("🛒 רכישת חבילה", callback_data="menu:coupon")]
        )
    return InlineKeyboardMarkup(rows)


def build_persistent_keyboard() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton("🎟️ קופון"), KeyboardButton("📊 מכסה")],
        [KeyboardButton("🔄 איפוס תרגיל"), KeyboardButton("🛠️ דיווח על תקלה")],
    ]
    return ReplyKeyboardMarkup(
        rows,
        is_persistent=True,
        resize_keyboard=True,
        one_time_keyboard=False,
    )


_MENU_REPLIES: dict[str, str] = {
    "new": "מעולה — שלח עכשיו תמונה 📸 של התרגיל.",
}

_COUPON_FORCE_REPLY = ForceReply(
    selective=True,
    input_field_placeholder="קוד קופון",
)


async def _send_purchase_menu(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    *,
    message=None,
) -> None:
    text = purchase_menu_intro_hebrew()
    keyboard = build_purchase_menu_keyboard()
    try:
        if message is not None:
            await message.reply_text(
                text,
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
    except BadRequest:
        if message is not None:
            await message.reply_text(text, reply_markup=keyboard)
        else:
            await context.bot.send_message(
                chat_id=chat_id, text=text, reply_markup=keyboard
            )


async def _send_coupon_redeem_prompt(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    *,
    message=None,
) -> None:
    _coupon_prompt_chats.add(chat_id)
    text = coupon_prompt_text_hebrew()
    try:
        if message is not None:
            await message.reply_text(
                text,
                reply_markup=_COUPON_FORCE_REPLY,
                parse_mode="Markdown",
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=_COUPON_FORCE_REPLY,
                parse_mode="Markdown",
            )
    except BadRequest:
        if message is not None:
            await message.reply_text(text, reply_markup=_COUPON_FORCE_REPLY)
        else:
            await context.bot.send_message(
                chat_id=chat_id, text=text, reply_markup=_COUPON_FORCE_REPLY
            )


async def on_buy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return
    parsed = parse_buy_callback(query.data)
    if parsed is None:
        await query.answer()
        return
    action, arg = parsed
    if not COUPON_ACCESS_ENABLED and action not in ("cancel",):
        await query.answer("מערכת הקופונים כבויה.", show_alert=True)
        return

    chat_id = query.message.chat_id if query.message else telegram_chat_id(update)

    if action == "cancel":
        await query.answer()
        if query.message:
            try:
                await query.message.edit_text("בוטל.")
            except BadRequest:
                pass
        return

    if action == "menu":
        await query.answer()
        text = purchase_menu_intro_hebrew()
        keyboard = build_purchase_menu_keyboard()
        if query.message:
            try:
                await query.message.edit_text(
                    text, reply_markup=keyboard, parse_mode="Markdown"
                )
            except BadRequest:
                await query.message.reply_text(
                    text, reply_markup=keyboard, parse_mode="Markdown"
                )
        return

    if action == "redeem":
        await query.answer()
        await _send_coupon_redeem_prompt(context, chat_id)
        return

    if action == "pkg":
        pkg = get_package(arg)
        if pkg is None:
            await query.answer("חבילה לא נמצאה", show_alert=True)
            return
        await query.answer()
        text = package_confirm_text_hebrew(pkg)
        keyboard = build_package_confirm_keyboard(pkg.package_id)
        if query.message:
            try:
                await query.message.edit_text(
                    text, reply_markup=keyboard, parse_mode="Markdown"
                )
            except BadRequest:
                await query.message.reply_text(
                    text, reply_markup=keyboard, parse_mode="Markdown"
                )
        return

    if action == "confirm":
        pkg = get_package(arg)
        if pkg is None:
            await query.answer("חבילה לא נמצאה", show_alert=True)
            return
        user = update.effective_user
        if user is None:
            await query.answer("שגיאה", show_alert=True)
            return
        req = create_purchase_request(
            user_id=user.id,
            chat_id=chat_id,
            daily_quota=pkg.daily_quota,
            period_days=pkg.period_days,
            price_ils=pkg.price_ils,
            package_label=pkg.label_hebrew(),
        )
        await query.answer("פרטי התשלום נשלחו")
        pay_text = payment_instructions_hebrew(pkg)
        pay_keyboard = build_payment_keyboard()
        if query.message:
            try:
                await query.message.edit_text(
                    pay_text,
                    reply_markup=pay_keyboard,
                    parse_mode="Markdown",
                )
            except BadRequest:
                await query.message.reply_text(
                    pay_text,
                    reply_markup=pay_keyboard,
                    parse_mode="Markdown",
                )
        if ADMIN_CHAT_ID:
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_CHAT_ID,
                    text=admin_purchase_notification_hebrew(
                        user_id=user.id,
                        username=user.username,
                        first_name=user.first_name,
                        pkg=pkg,
                        request_id=req.id,
                    ),
                )
            except Exception as exc:
                log.warning("Failed to notify admin chat=%s: %s", ADMIN_CHAT_ID, exc)
        return

    await query.answer()


async def on_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data or not query.data.startswith("menu:"):
        return
    action = query.data.split(":", 1)[-1]
    if action == "coupon":
        if not COUPON_ACCESS_ENABLED:
            await query.answer("מערכת הקופונים כבויה.", show_alert=True)
            return
        await query.answer()
        chat_id = query.message.chat_id if query.message else telegram_chat_id(update)
        await _send_purchase_menu(context, chat_id, message=query.message)
        return
    reply = _MENU_REPLIES.get(action)
    if not reply:
        await query.answer()
        return
    await query.answer()
    if query.message:
        await query.message.reply_text(reply)


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    chat_id = telegram_chat_id(update)
    reset_user_session(chat_id)
    await update.message.reply_text(
        "המצב אופס. שלח/י תמונה חדשה 📸 של התרגיל.",
        reply_markup=build_persistent_keyboard(),
    )


async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    await update.message.reply_text(ping_reply_hebrew())


async def cmd_coupon(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not COUPON_ACCESS_ENABLED:
        await update.message.reply_text(
            "מערכת הקופונים כבויה כרגע.",
            reply_markup=build_persistent_keyboard(),
        )
        return
    chat_id = telegram_chat_id(update)
    await _send_purchase_menu(
        context, chat_id, message=update.message
    )


async def cmd_quota(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not COUPON_ACCESS_ENABLED:
        await update.message.reply_text(
            "מערכת הקופונים כבויה כרגע.",
            reply_markup=build_persistent_keyboard(),
        )
        return
    result = check_image_access(telegram_user_id(update))
    await update.message.reply_text(
        quota_status_reply_hebrew(result),
        reply_markup=build_persistent_keyboard(),
    )

async def _edit_draft_message_safe(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    message_id: int,
    extracted: dict,
    *,
    edit: dict | None = None,
    errors: list[str] | None = None,
) -> None:
    text = draft_display_text(
        extracted,
        edit=edit,
        errors=errors,
        type_picker_idx=get_draft_type_picker_idx(chat_id),
    )
    picker_idx = get_draft_type_picker_idx(chat_id)
    keyboard = build_draft_keyboard(extracted, type_picker_idx=picker_idx)
    try:
        await context.bot.edit_message_text(
            text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
    except BadRequest as exc:
        err = str(exc).lower()
        if "message is not modified" in err:
            return
        if "parse entities" not in err:
            raise
        await context.bot.edit_message_text(
            text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=keyboard,
        )


def _is_load_type_picker_open(chat_id: int) -> bool:
    return get_draft_type_picker_idx(chat_id) is not None


async def _close_load_type_picker_on_draft(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    extracted: dict,
) -> None:
    """סוגר את תפריט בחירת סוג העומס בהודעת הטיוטה."""
    if not _is_load_type_picker_open(chat_id):
        return
    set_draft_type_picker_idx(chat_id, None)
    ref = get_draft_message_ref(chat_id)
    if ref:
        await _edit_draft_message_safe(context, ref[0], ref[1], extracted)


async def _dismiss_edit_prompt(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
) -> None:
    pid = get_draft_edit_prompt_id(chat_id)
    if pid is None:
        return
    set_draft_edit_prompt_id(chat_id, None)
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=pid)
    except BadRequest:
        pass


async def _dismiss_user_message(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    message_id: int | None,
) -> None:
    if message_id is None:
        return
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except BadRequest:
        pass


async def _apply_pending_edit(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    text: str,
    *,
    pending_edit: dict | None = None,
    user_message_id: int | None = None,
) -> bool:
    """מיישם עריכת שדה; מחזיר True אם הטיפול בוצע (גם בשגיאת קלט)."""
    edit = pending_edit or get_draft_edit(chat_id)
    if not edit or not is_draft_pending(chat_id):
        return False

    ref = get_draft_message_ref(chat_id)
    extracted = get_stored_vision_extracted(chat_id) or {}

    if text.lower() in ("/cancel", "ביטול"):
        await _dismiss_edit_prompt(context, chat_id)
        set_draft_edit(chat_id, None)
        if ref:
            await _edit_draft_message_safe(context, ref[0], ref[1], extracted)
        return True

    updated, errors = apply_field_edit(extracted, edit, text)
    updated = finalize_beam_extraction(updated)
    if errors:
        if ref:
            await _edit_draft_message_safe(
                context,
                ref[0],
                ref[1],
                extracted,
                edit=edit,
                errors=errors,
            )
        return True

    await _dismiss_edit_prompt(context, chat_id)
    await _dismiss_user_message(context, chat_id, user_message_id)
    set_draft_edit(chat_id, None)
    persist_draft(chat_id, updated)
    if ref:
        try:
            await _edit_draft_message_safe(context, ref[0], ref[1], updated)
        except BadRequest as exc:
            log.warning("Draft message edit failed: %s", exc)
    return True


async def send_draft_with_keyboard(
    message,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    extracted: dict,
) -> None:
    text = draft_display_text(extracted)
    keyboard = build_draft_keyboard(extracted)
    try:
        sent = await message.reply_text(
            text, reply_markup=keyboard, parse_mode="Markdown"
        )
    except BadRequest:
        sent = await message.reply_text(text, reply_markup=keyboard)
    set_draft_pending(
        chat_id,
        extracted,
        text,
        message_id=sent.message_id,
        clear_edit=True,
    )


_FORCE_REPLY = ForceReply(
    selective=False,
    input_field_placeholder="ערך חדש",
)


async def _start_draft_edit(
    context: ContextTypes.DEFAULT_TYPE,
    query,
    chat_id: int,
    edit: dict,
    extracted: dict,
) -> None:
    """שולח הודעת עריכה קצרה אחת (נמחקת אחרי תיקון מוצלח)."""
    kind = edit.get("kind")
    await query.answer()

    await _dismiss_edit_prompt(context, chat_id)
    await _close_load_type_picker_on_draft(context, chat_id, extracted)
    set_draft_edit(chat_id, dict(edit))

    prompt_text = edit_prompt(edit, extracted)
    try:
        if kind == "load_dir":
            idx = int(edit.get("index", 1))
            sent = await context.bot.send_message(
                chat_id=chat_id,
                text=prompt_text,
                reply_markup=build_load_dir_prompt_keyboard(idx),
                parse_mode="Markdown",
            )
        else:
            sent = await context.bot.send_message(
                chat_id=chat_id,
                text=prompt_text,
                reply_markup=_FORCE_REPLY,
                parse_mode="Markdown",
            )
    except BadRequest as exc:
        log.warning("Edit prompt Markdown failed: %s", exc)
        if kind == "load_dir":
            idx = int(edit.get("index", 1))
            sent = await context.bot.send_message(
                chat_id=chat_id,
                text=prompt_text,
                reply_markup=build_load_dir_prompt_keyboard(idx),
            )
        else:
            sent = await context.bot.send_message(
                chat_id=chat_id,
                text=prompt_text,
                reply_markup=_FORCE_REPLY,
            )
    set_draft_edit_prompt_id(chat_id, sent.message_id)
    log.info("Edit prompt sent chat=%s kind=%s msg=%s", chat_id, kind, sent.message_id)


async def on_draft_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return

    cb = parse_draft_callback(query.data)
    if cb is None:
        await query.answer()
        return

    chat_id = query.message.chat_id if query.message else telegram_chat_id(update)
    extracted = get_stored_vision_extracted(chat_id)
    if not extracted or not is_draft_pending(chat_id):
        await query.answer("אין טיוטה פעילה", show_alert=True)
        return

    ref = get_draft_message_ref(chat_id)
    msg_id = ref[1] if ref else (query.message.message_id if query.message else None)

    if cb.action == "approve":
        await query.answer()
        reply, solved = approve_and_solve(chat_id, extracted)
        await _deliver_approved_solve(
            context,
            chat_id,
            extracted=extracted,
            reply=reply,
            solved=solved,
            draft_msg_id=msg_id,
        )
        await _dismiss_edit_prompt(context, chat_id)
        set_draft_edit(chat_id, None)
        set_draft_type_picker_idx(chat_id, None)
        return

    if cb.action == "cancel_edit":
        await query.answer()
        await _dismiss_edit_prompt(context, chat_id)
        set_draft_edit(chat_id, None)
        set_draft_type_picker_idx(chat_id, None)
        if msg_id is not None:
            await _edit_draft_message_safe(context, chat_id, msg_id, extracted)
        return

    if cb.action == "set_load_dir":
        await query.answer()
        edit = {"kind": "load_dir", "index": cb.index}
        set_draft_edit(chat_id, edit)
        await _apply_pending_edit(context, chat_id, cb.dir, pending_edit=edit)
        return

    if cb.action == "pick_load_type":
        await query.answer()
        loads = (extracted.get("beam") or {}).get("loads") or []
        ld = (
            loads[cb.index - 1]
            if isinstance(loads, list) and 0 <= cb.index - 1 < len(loads)
            else {}
        )
        if isinstance(ld, dict) and ld.get("_draft_new"):
            updated = extracted
        else:
            updated = toggle_any_load_direction(extracted, cb.index)
        set_draft_type_picker_idx(chat_id, cb.index)
        persist_draft(chat_id, updated)
        if msg_id is not None:
            await _edit_draft_message_safe(context, chat_id, msg_id, updated)
        return

    if cb.action == "set_load_type":
        await query.answer()
        updated = set_load_type(extracted, cb.index, cb.dir)
        persist_draft(chat_id, updated)
        set_draft_type_picker_idx(chat_id, None)
        if msg_id is not None:
            await _edit_draft_message_safe(context, chat_id, msg_id, updated)
        return

    if cb.action == "toggle_dir":
        await query.answer()
        updated = toggle_any_load_direction(extracted, cb.index)
        persist_draft(chat_id, updated)
        if msg_id is not None:
            await _edit_draft_message_safe(context, chat_id, msg_id, updated)
        return

    if cb.action == "edit_L":
        await _start_draft_edit(context, query, chat_id, {"kind": "L"}, extracted)
        return

    if cb.action == "edit_support":
        await _start_draft_edit(
            context,
            query,
            chat_id,
            {"kind": "support", "index": cb.index},
            extracted,
        )
        return

    if cb.action == "edit_load":
        await _start_draft_edit(
            context,
            query,
            chat_id,
            {"kind": "load", "index": cb.index},
            extracted,
        )
        return

    if cb.action == "edit_load_dir":
        await _start_draft_edit(
            context,
            query,
            chat_id,
            {"kind": "load_dir", "index": cb.index},
            extracted,
        )
        return

    if cb.action == "edit_load_mag":
        await _start_draft_edit(
            context,
            query,
            chat_id,
            {"kind": "load_mag", "index": cb.index},
            extracted,
        )
        return

    if cb.action == "edit_load_x":
        await _start_draft_edit(
            context,
            query,
            chat_id,
            {"kind": "load_x", "index": cb.index},
            extracted,
        )
        return

    if cb.action == "edit_load_angle":
        await _start_draft_edit(
            context,
            query,
            chat_id,
            {"kind": "load_angle", "index": cb.index},
            extracted,
        )
        return

    if cb.action == "delete_load":
        await query.answer()
        updated = delete_load(extracted, cb.index)
        set_draft_edit(chat_id, None)
        set_draft_type_picker_idx(chat_id, None)
        persist_draft(chat_id, updated)
        if msg_id is not None:
            await _edit_draft_message_safe(context, chat_id, msg_id, updated)
        return

    if cb.action == "add_load":
        await query.answer()
        updated = add_empty_load(extracted)
        set_draft_edit(chat_id, None)
        set_draft_type_picker_idx(chat_id, None)
        persist_draft(chat_id, updated)
        if msg_id is not None:
            await _edit_draft_message_safe(context, chat_id, msg_id, updated)
        return


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    chat_id = telegram_chat_id(update)
    text = update.message.text.strip()

    if text == "🎟️ קופון":
        await cmd_coupon(update, context)
        return
    if text == "📊 מכסה":
        await cmd_quota(update, context)
        return
    if text == "🔄 איפוס תרגיל":
        await cmd_reset(update, context)
        return
    if text == "🛠️ דיווח על תקלה":
        await update.message.reply_text(
            "תודה! הדיווח התקבל. נטפל בזה בהקדם.",
            reply_markup=build_persistent_keyboard(),
        )
        return

    pending_edit = get_draft_edit(chat_id)
    if pending_edit and pending_edit.get("kind") == "load_type_picker":
        idx = int(pending_edit.get("index", 0) or 0)
        set_draft_edit(chat_id, None)
        if idx >= 1:
            set_draft_type_picker_idx(chat_id, idx)
        pending_edit = None
    if pending_edit and is_draft_pending(chat_id):
        await _apply_pending_edit(
            context, chat_id, text, user_message_id=update.message.message_id
        )
        return

    if COUPON_ACCESS_ENABLED:
        in_coupon_prompt = chat_id in _coupon_prompt_chats
        if in_coupon_prompt or looks_like_coupon_code(text):
            if in_coupon_prompt:
                _coupon_prompt_chats.discard(chat_id)
            result = redeem_coupon(text, telegram_user_id(update))
            await _reply_text_safe(
                update.message,
                redeem_reply_hebrew(result),
                reply_markup=build_persistent_keyboard(),
            )
            return

    if is_draft_pending(chat_id) and not looks_like_draft_patch(text):
        await _reply_text_safe(
            update.message,
            _TEXT_UNHANDLED,
            reply_markup=build_persistent_keyboard(),
        )
        return

    draft_result = handle_draft_text(chat_id, text)
    if draft_result.handled:
        ref = get_draft_message_ref(chat_id)
        if draft_result.approved:
            msg_id = ref[1] if ref else None
            extracted = draft_result.extracted or get_stored_vision_extracted(chat_id) or {}
            await _deliver_approved_solve(
                context,
                chat_id,
                extracted=extracted,
                reply=draft_result.reply,
                solved=draft_result.solved or {},
                draft_msg_id=msg_id,
            )
            set_draft_edit(chat_id, None)
        elif draft_result.update_draft and ref and draft_result.extracted:
            try:
                await _edit_draft_message_safe(
                    context,
                    ref[0],
                    ref[1],
                    draft_result.extracted,
                    errors=draft_result.errors,
                )
            except BadRequest as exc:
                log.warning("Draft message edit failed: %s", exc)
        return

    await _reply_text_safe(
        update.message,
        IMAGE_ONLY_TEXT_REPLY,
        reply_markup=build_persistent_keyboard(),
    )


async def reply_from_vision_extract(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    image_bytes: bytes,
    mime_type: str,
) -> None:
    """מסלול סינכרוני (VISION_ASYNC_ENABLED=0) — מחכה עד סיום החילוץ."""
    if not update.message:
        return

    chat_id = telegram_chat_id(update)
    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(typing_while_waiting(context, chat_id, stop_typing))

    reply: str | None = None
    use_draft = False
    extracted_partial: dict | None = None
    try:
        result = await run_vision_extract(chat_id, image_bytes, mime_type)
        use_draft = result.use_draft
        extracted_partial = result.extracted
        reply = result.reply
        log.info("Vision extract chat %s OK (sync)", chat_id)
    except Exception as exc:
        log.warning("Vision extract failed: %s", exc)
        if extracted_partial is not None:
            extracted_partial = package_extraction_response(
                extracted_partial,
                partial=True,
                validation_issues=[str(exc)],
            )
            reply = format_vision_extract_only_reply(extracted_partial)
        else:
            reply = (
                f"לא הצלחתי לקרוא את התמונה.\n({friendly_gemini_error(exc)})\n\n"
                "טיפים:\n"
                "• שלח כקובץ 📎 לאיכות טובה יותר\n"
                "• ודא שכל המספרים, החצים והסמכים בתוך המסגרת"
            )
    finally:
        stop_typing.set()
        typing_task.cancel()

    if use_draft and extracted_partial is not None:
        await send_draft_with_keyboard(
            update.message, context, chat_id, extracted_partial
        )
        return

    if reply is None:
        reply = "לא הצלחתי לעבד את התמונה."

    if len(reply) > 4000:
        reply = reply[:3997] + "..."
    await _reply_text_safe(update.message, reply)


async def on_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    chat_id = telegram_chat_id(update)
    msg_id = int(update.message.message_id)
    dedup_key = (chat_id, msg_id)
    now = time.monotonic()
    prev = _recent_image_keys.get(dedup_key)
    if prev is not None and now - prev < _IMAGE_DEDUP_SEC:
        log.info("Skipping duplicate image update chat=%s msg=%s", chat_id, msg_id)
        return
    _recent_image_keys[dedup_key] = now
    if len(_recent_image_keys) > 500:
        cutoff = now - _IMAGE_DEDUP_SEC
        for key, ts in list(_recent_image_keys.items()):
            if ts < cutoff:
                _recent_image_keys.pop(key, None)

    reload_system_instruction_if_changed()

    log.info("Image from chat %s", chat_id)

    if COUPON_ACCESS_ENABLED:
        user_id = telegram_user_id(update)
        access = consume_image_slot(user_id)
        if access.status != ImageAccessStatus.OK:
            log.info(
                "Image blocked user=%s status=%s",
                user_id,
                access.status.value,
            )
            reply_markup = None
            if access.status in (
                ImageAccessStatus.TRIAL_EXHAUSTED,
                ImageAccessStatus.ACCESS_EXPIRED,
            ):
                reply_markup = build_upgrade_options_keyboard()
            await _reply_text_safe(
                update.message,
                image_access_reply_hebrew(access),
                reply_markup=reply_markup,
            )
            return
        log.info(
            "Image allowed user=%s used=%s/%s remaining=%s",
            user_id,
            access.images_used,
            access.tier_limit,
            access.images_remaining,
        )

    begin_image_session(chat_id)

    if VISION_ASYNC_ENABLED and update.message:
        await send_vision_ack(update.message)

    temp_image: TempImageFile | None = None
    try:
        temp_image = await save_message_image_to_temp(update, context)
        temp_image = await asyncio.to_thread(prepare_image_for_vision, temp_image)
        image_bytes = temp_image.read_bytes()
        mime_type = temp_image.mime_type
        if VISION_ASYNC_ENABLED:
            schedule_vision_job(context, chat_id, image_bytes, mime_type)
        else:
            await reply_from_vision_extract(
                update,
                context,
                image_bytes,
                mime_type,
            )
    except Exception as exc:
        log.exception("Failed to process image")
        await update.message.reply_text(f"לא הצלחתי לעבד את התמונה:\n{exc}")
    finally:
        if temp_image is not None:
            temp_image.cleanup()
            log.info("Deleted temp image: %s", temp_image.path.name)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.exception("Telegram handler error", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "אירעה שגיאה פנימית. נסה לשלוח את התמונה שוב."
            )
        except Exception:
            pass
