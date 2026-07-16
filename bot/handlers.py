# -*- coding: utf-8 -*-
"""Handlers טלגרם — חילוץ מתמונות + טיוטה + פתרון מלא."""
from __future__ import annotations

import asyncio
import copy
import logging
import shutil
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
    ADMIN_BOT_TOKEN,
    ADMIN_CHAT_ID,
    ADMIN_USER_IDS,
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
    has_active_coupon_access,
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
from bot.formulas import (
    build_formulas_locked_keyboard,
    build_formulas_menu_keyboard,
    build_topic_followup_keyboard,
    formulas_locked_reply_hebrew,
    formulas_menu_intro_hebrew,
    get_topic,
    parse_formula_callback,
    topic_image_caption_hebrew,
    topic_pending_caption_hebrew,
)
from intro import (
    build_intro_menu_keyboard,
    build_intro_topic_followup_keyboard,
    get_intro_topic,
    intro_menu_intro_hebrew,
    intro_topic_body_hebrew,
    parse_intro_callback,
)
from bot.draft_editor import (
    add_load_of_type,
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
    ADD_LOAD_TYPE_PICKER_IDX,
    build_draft_keyboard,
    build_load_dir_prompt_keyboard,
    draft_display_text,
    edit_prompt,
    parse_draft_callback,
    should_open_type_picker_on_direction_click,
)
from bot.notebook_render import render_exercise_problem_png_temp, render_notebook_png_temp
from bot.gemini_chat import friendly_gemini_error
from bot.assistant import (
    build_bank_solve_mode_keyboard,
    build_solve_mode_keyboard,
    parse_bank_mode_action,
    parse_menu_mode_action,
    select_solve_mode,
    solve_mode_picker_intro_hebrew,
)
from personal_assistant.runtime import (
    deliver_after_draft_approve,
    handle_assistant_action,
    has_active_assistant_progress,
    parse_assistant_callback,
)
from bot.exercise_bank import (
    count_exercises,
    exercise_bank_cooldown_remaining_sec,
    get_exercise_image_path,
    pick_next_exercise_for_user,
)
from bot.solution_check import solve_extracted_beam
from bot.solution_session import (
    SolveMode,
    begin_image_session,
    consume_pending_bank_exercise,
    consume_pending_solve_mode,
    reset_user_session,
    set_pending_bank_exercise,
    set_pending_bank_submission_image,
)
from bot.images import TempImageFile, prepare_image_for_vision, save_message_image_to_temp
from bot.system_prompt import reload_system_instruction_if_changed
from bot.vision import (
    finalize_beam_extraction,
    format_vision_extract_only_reply,
    get_draft_error_message_id,
    get_draft_edit,
    get_draft_edit_prompt_id,
    get_draft_message_ref,
    get_draft_type_picker_idx,
    get_stored_vision_extracted,
    is_draft_pending,
    package_extraction_response,
    set_draft_error_message_id,
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
_bug_report_prompt_chats: set[int] = set()

_BUG_REPORT_FORCE_REPLY = ForceReply(
    selective=True,
    input_field_placeholder="תאר/י את התקלה",
)

_BUG_REPORT_CANCEL = "ביטול דיווח"
_PERSISTENT_ASSISTANT_LABEL = "עוזר אישי"
_BANK_ADD_SECRET = "BnayaG"
_PERSISTENT_FORMULAS_LABEL = "נוסחאות"
_PERSISTENT_QUOTA_LABEL = "מכסה"
_PERSISTENT_COUPON_LABEL = "קופון"
_PERSISTENT_BUG_REPORT_LABEL = "דיווח על תקלה"
_PERSISTENT_MAIN_LABEL = "ראשי"
_START_SEND_IMAGE_LABEL = "פתרון מלא"
_START_GIVE_EXERCISE_LABEL = "תרגול"
_START_INTRO_LABEL = "מבוא"
_START_REDEEM_COUPON_LABEL = "הזנת קוד קופון"
_START_PURCHASE_LABEL = "רכישת חבילה"


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
    if reply_markup is None:
        reply_markup = build_persistent_keyboard()
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
) -> object:
    """שולח הודעה חדשה לצ'אט (לא reply) עם fallback אם Markdown נשבר."""
    if reply_markup is None:
        reply_markup = build_persistent_keyboard()
    try:
        return await context.bot.send_message(
            chat_id=chat_id, text=text, parse_mode=parse_mode, reply_markup=reply_markup
        )
    except BadRequest as exc:
        if "parse entities" not in str(exc).lower():
            raise
        return await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)


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
        sent = await _send_text_safe(context, chat_id, reply)
        # אם זה לא פתרון (למשל שגיאת validator) — נשמור message_id כדי למחוק בניסיון הבא.
        if not has_result:
            try:
                set_draft_error_message_id(chat_id, int(getattr(sent, "message_id", 0)))
            except Exception:
                pass
        else:
            set_draft_error_message_id(chat_id, None)

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
            )

    if notebook_path is not None:
        notebook_path.unlink(missing_ok=True)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    text = build_start_welcome_text()
    keyboard = build_start_keyboard()
    try:
        # שולחים את המקלדת הקבועה (התפריט הזמין תמיד) עם הודעת הפתיחה.
        await update.message.reply_text(
            text, reply_markup=build_persistent_keyboard(), parse_mode="Markdown"
        )
    except BadRequest as exc:
        if "parse entities" not in str(exc).lower():
            raise
        await update.message.reply_text(text, reply_markup=build_persistent_keyboard())
    # תפריט כפתורים Inline (לא "מקלדת למטה").
    await update.message.reply_text("בחר/י פעולה:", reply_markup=keyboard)


def build_start_welcome_text() -> str:
    return (
        "היי, אני שמח שהגעת לכאן. בניתי את הבוט הזה כדי לעזור לנו לעבור את תרגילי "
        "הסטטיקה קצת יותר בקלות, בלי להיתקע שעות על אותה שאלה.\n\n"
        "השימוש בבוט פשוט: אפשר להעלות תמונה של תרגיל שאתה עובד עליו, או לבחור תרגיל "
        "מתוך המאגר המובנה שלי, שם הנתונים כבר מוגדרים. בכל מקרה, אתה יכול לבחור בין "
        "פתרון מחברת מלא לבין ליווי צמוד של עוזר אישי. העוזר האישי הזה מלווה אותך "
        "צעד-צעד עם כפתורים נוחים ומסביר את הדרך, ובנוסף יש לך אופציה נגישה לשלוף "
        "נוסחאות ספציפיות בהתאם למה שאתה צריך באותו רגע.\n\n"
        "אם יש בעיות או בקשות ספציפיות, יש אופציה לדיווח שדרכה תוכל לפנות אליי ישירות.\n\n"
        "הבוט זמין עבורך 24/7 עם כל החבילה המלאה. כדי שתוכל להתרשם ולראות איך זה "
        "עובד באמת, פתחתי לך גישה מלאה לכל האפשרויות ל-24 שעות הקרובות ללא התחייבות. "
        "אם זה יחסוך לך כאבי ראש, תוכל להצטרף לכל הסמסטר, 3.5 חודשים, במחיר של "
        '150 ש"ח – פחות ממחיר של שיעור פרטי אחד.\n\n'
        "מוזמן להתחיל להשתמש, מקווה שזה יעזור לך לעבור את הקורס בראש שקט."
    )


def build_upgrade_options_keyboard() -> InlineKeyboardMarkup:
    """אפשרויות המשך אחרי סיום ניסיון חינם."""
    rows: list[list[InlineKeyboardButton]] = []
    if COUPON_ACCESS_ENABLED:
        rows.append(
            [InlineKeyboardButton("רכישת חבילה", callback_data="buy:menu")]
        )
        rows.append(
            [InlineKeyboardButton("יש לי קוד", callback_data="buy:redeem")]
        )
    return InlineKeyboardMarkup(rows)


def build_start_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(_START_INTRO_LABEL, callback_data="menu:intro")],
        [InlineKeyboardButton(_START_SEND_IMAGE_LABEL, callback_data="menu:new")],
        [InlineKeyboardButton(_START_GIVE_EXERCISE_LABEL, callback_data="menu:give_exercise")],
        [InlineKeyboardButton(_PERSISTENT_FORMULAS_LABEL, callback_data="menu:formulas")],
    ]
    if COUPON_ACCESS_ENABLED:
        rows.append(
            [InlineKeyboardButton(_START_REDEEM_COUPON_LABEL, callback_data="buy:redeem")]
        )
        rows.append(
            [InlineKeyboardButton(_START_PURCHASE_LABEL, callback_data="menu:coupon")]
        )
    return InlineKeyboardMarkup(rows)


def build_persistent_keyboard() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(_PERSISTENT_FORMULAS_LABEL), KeyboardButton(_PERSISTENT_QUOTA_LABEL)],
        [KeyboardButton(_PERSISTENT_COUPON_LABEL), KeyboardButton(_PERSISTENT_ASSISTANT_LABEL)],
        [KeyboardButton(_PERSISTENT_BUG_REPORT_LABEL), KeyboardButton(_PERSISTENT_MAIN_LABEL)],
    ]
    return ReplyKeyboardMarkup(
        rows,
        is_persistent=True,
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def build_bug_report_cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(_BUG_REPORT_CANCEL)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def _bug_report_admin_text(
    *,
    user_id: int,
    chat_id: int,
    username: str | None,
    first_name: str | None,
    report_text: str,
) -> str:
    uname = f"@{username}" if username else "—"
    name = first_name or "—"
    body = (report_text or "").strip()
    return (
        "🛠️ דיווח תקלה חדש\n"
        f"משתמש: {name} ({uname})\n"
        f"user_id: {user_id}\n"
        f"chat_id: {chat_id}\n"
        "────────────\n"
        f"{body}"
    )


async def _forward_bug_report_via_admin_bot(
    text: str,
    *,
    fallback_bot=None,
) -> bool:
    """שולח דיווח דרך בוט האדמין לכל ADMIN_USER_IDS. Fallback ל־ADMIN_CHAT_ID בבוט הראשי."""
    if ADMIN_BOT_TOKEN and ADMIN_USER_IDS:
        try:
            from telegram import Bot

            admin_bot = Bot(token=ADMIN_BOT_TOKEN)
            ok_any = False
            for admin_id in sorted(ADMIN_USER_IDS):
                try:
                    await admin_bot.send_message(chat_id=admin_id, text=text)
                    ok_any = True
                except Exception as exc:
                    log.warning(
                        "Admin-bot bug report failed admin_id=%s: %s",
                        admin_id,
                        exc,
                    )
            if ok_any:
                return True
        except Exception as exc:
            log.warning("Admin-bot client failed for bug report: %s", exc)

    if fallback_bot is not None and ADMIN_CHAT_ID:
        try:
            await fallback_bot.send_message(chat_id=ADMIN_CHAT_ID, text=text)
            return True
        except Exception as exc:
            log.warning("Fallback bug report to ADMIN_CHAT_ID failed: %s", exc)
    return False


async def _prompt_bug_report(message) -> None:
    chat_id = int(message.chat_id)
    _bug_report_prompt_chats.add(chat_id)
    await message.reply_text(
        "🛠️ *דיווח על תקלה*\n\n"
        "כתוב/י כאן במילים שלך מה קרה (או מה לא עובד).\n"
        "אחרי השליחה הדיווח יועבר אוטומטית לצוות.\n\n"
        "אפשר לבטל עם «ביטול דיווח».",
        parse_mode="Markdown",
        reply_markup=build_bug_report_cancel_keyboard(),
    )
    try:
        await message.reply_text(
            "כאן אפשר לרשום את פרטי התקלה 👇",
            reply_markup=_BUG_REPORT_FORCE_REPLY,
        )
    except BadRequest:
        pass


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


async def _send_formulas_locked(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    *,
    message=None,
    edit_message=None,
) -> None:
    text = formulas_locked_reply_hebrew()
    keyboard = build_formulas_locked_keyboard()
    try:
        if edit_message is not None:
            await edit_message.edit_text(
                text,
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
            return
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
        if edit_message is not None:
            try:
                await edit_message.edit_text(text, reply_markup=keyboard)
                return
            except BadRequest:
                pass
        if message is not None:
            await message.reply_text(text, reply_markup=keyboard)
        else:
            await context.bot.send_message(
                chat_id=chat_id, text=text, reply_markup=keyboard
            )


async def _send_intro_menu(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    *,
    message=None,
    edit_message=None,
) -> None:
    """מציג תפריט מבוא לסטטיקה — פתוח לכולם."""
    text = intro_menu_intro_hebrew()
    keyboard = build_intro_menu_keyboard()
    try:
        if edit_message is not None:
            await edit_message.edit_text(
                text,
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
            return
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
        if edit_message is not None:
            try:
                await edit_message.edit_text(text, reply_markup=keyboard)
                return
            except BadRequest:
                pass
        if message is not None:
            await message.reply_text(text, reply_markup=keyboard)
        else:
            await context.bot.send_message(
                chat_id=chat_id, text=text, reply_markup=keyboard
            )


async def _send_formulas_menu(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    *,
    user_id: int | None = None,
    message=None,
    edit_message=None,
) -> None:
    """מציג תפריט נוסחאות רק למנויי קופון; אחרת הודעת נעילה + כפתורי רכישה."""
    uid = int(user_id) if user_id is not None else None
    if COUPON_ACCESS_ENABLED and (uid is None or not has_active_coupon_access(uid)):
        await _send_formulas_locked(
            context,
            chat_id,
            message=message,
            edit_message=edit_message,
        )
        return

    text = formulas_menu_intro_hebrew()
    keyboard = build_formulas_menu_keyboard()
    try:
        if edit_message is not None:
            await edit_message.edit_text(
                text,
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
            return
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
        if edit_message is not None:
            try:
                await edit_message.edit_text(text, reply_markup=keyboard)
                return
            except BadRequest:
                pass
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


async def _delete_callback_message(query) -> None:
    """מוחק את ההודעה עם כפתורי הבחירה אחרי שהמשתמש המשיך (לא עוזר אישי / טיוטה)."""
    message = getattr(query, "message", None)
    if message is None:
        return
    try:
        await message.delete()
        return
    except BadRequest as exc:
        log.debug("Could not delete callback message: %s", exc)
    try:
        await message.edit_reply_markup(reply_markup=None)
    except BadRequest as exc:
        log.debug("Could not clear callback keyboard: %s", exc)


async def _send_main_action_menu(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    *,
    message=None,
) -> None:
    """תפריט ראשי בלבד — «בחר/י פעולה:» + כפתורים, בלי הודעת פתיחה."""
    keyboard = build_start_keyboard()
    text = "בחר/י פעולה:"
    if message is not None:
        await _reply_text_safe(message, text, reply_markup=keyboard)
        return
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=keyboard,
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
        await _delete_callback_message(query)
        await _send_text_safe(context, chat_id, "בוטל.")
        return

    if action == "menu":
        await query.answer()
        await _delete_callback_message(query)
        await _send_purchase_menu(context, chat_id)
        return

    if action == "redeem":
        await query.answer()
        await _delete_callback_message(query)
        await _send_coupon_redeem_prompt(context, chat_id)
        return

    if action == "pkg":
        pkg = get_package(arg)
        if pkg is None:
            await query.answer("חבילה לא נמצאה", show_alert=True)
            return
        await query.answer()
        await _delete_callback_message(query)
        text = package_confirm_text_hebrew(pkg)
        keyboard = build_package_confirm_keyboard(pkg.package_id)
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
        except BadRequest:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=keyboard,
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
        await _delete_callback_message(query)
        pay_text = payment_instructions_hebrew(pkg)
        pay_keyboard = build_payment_keyboard()
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=pay_text,
                reply_markup=pay_keyboard,
                parse_mode="Markdown",
            )
        except BadRequest:
            await context.bot.send_message(
                chat_id=chat_id,
                text=pay_text,
                reply_markup=pay_keyboard,
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
        await _delete_callback_message(query)
        await _send_purchase_menu(context, chat_id)
        return
    if action == "formulas":
        await query.answer()
        chat_id = query.message.chat_id if query.message else telegram_chat_id(update)
        await _delete_callback_message(query)
        await _send_formulas_menu(
            context,
            chat_id,
            user_id=telegram_user_id(update),
        )
        return
    if action == "intro":
        await query.answer()
        chat_id = query.message.chat_id if query.message else telegram_chat_id(update)
        await _delete_callback_message(query)
        await _send_intro_menu(context, chat_id)
        return
    if action == "give_exercise":
        if count_exercises() <= 0:
            await query.answer("אין עדיין תרגילים מוכנים במאגר.", show_alert=True)
            return
        user_id = telegram_user_id(update)
        cool = exercise_bank_cooldown_remaining_sec(user_id)
        if cool is not None:
            mins = max(1, int((cool + 59) // 60))
            await query.answer(
                f"אפשר לקבל תרגיל נוסף בעוד כ-{mins} דקות.",
                show_alert=True,
            )
            return
        await query.answer()
        chat_id = query.message.chat_id if query.message else telegram_chat_id(update)
        await _delete_callback_message(query)
        picked = pick_next_exercise_for_user(user_id)
        if picked is None:
            await _send_text_safe(context, chat_id, "אין עדיין תרגילים מוכנים במאגר.")
            return
        exercise_id, extracted = picked
        stored_image = get_exercise_image_path(exercise_id)
        photo_sent = False
        if stored_image is not None:
            try:
                with stored_image.open("rb") as photo:
                    await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo,
                    )
                photo_sent = True
            except Exception as exc:
                log.warning(
                    "Failed to send stored exercise photo chat=%s id=%s: %s",
                    chat_id,
                    exercise_id,
                    exc,
                )
        if not photo_sent:
            # תרגילים ישנים בלי תמונה שמורה — רינדור מהנתונים כגיבוי.
            problem_path = render_exercise_problem_png_temp(extracted)
            if problem_path is not None:
                try:
                    with problem_path.open("rb") as photo:
                        await context.bot.send_photo(
                            chat_id=chat_id,
                            photo=photo,
                        )
                    photo_sent = True
                except Exception as exc:
                    log.warning(
                        "Failed to send exercise photo chat=%s: %s", chat_id, exc
                    )
                finally:
                    problem_path.unlink(missing_ok=True)
        if not photo_sent:
            from bot.draft_format import extracted_to_draft_text

            # רק תיאור הנתונים — בלי כותרת/מספר תרגיל (לא רלוונטיות כאן).
            draft_lines = extracted_to_draft_text(extracted).split("\n")
            data_text = "\n".join(draft_lines[2 : draft_lines.index("---")]).strip()
            await _send_text_safe(
                context,
                chat_id,
                data_text,
            )
        set_pending_bank_exercise(chat_id, exercise_id, extracted)
        keyboard = build_bank_solve_mode_keyboard()
        await context.bot.send_message(
            chat_id=chat_id,
            text="איך תרצה/י לפתור את התרגיל?",
            reply_markup=keyboard,
        )
        return
    if action == "new":
        await query.answer()
        chat_id = query.message.chat_id if query.message else telegram_chat_id(update)
        await _delete_callback_message(query)
        text = solve_mode_picker_intro_hebrew()
        keyboard = build_solve_mode_keyboard()
        await _send_text_safe(context, chat_id, text)
        await context.bot.send_message(
            chat_id=chat_id,
            text="בחר/י מצב:",
            reply_markup=keyboard,
        )
        return
    if action.startswith("mode:"):
        mode = parse_menu_mode_action(action)
        if mode is None:
            await query.answer()
            return
        await query.answer()
        chat_id = query.message.chat_id if query.message else telegram_chat_id(update)
        await _delete_callback_message(query)
        prompt = select_solve_mode(chat_id, mode)
        await _send_text_safe(context, chat_id, prompt)
        return
    if action.startswith("bank:"):
        mode = parse_bank_mode_action(action)
        if mode is None:
            await query.answer()
            return
        await query.answer()
        chat_id = query.message.chat_id if query.message else telegram_chat_id(update)
        await _delete_callback_message(query)
        pending = consume_pending_bank_exercise(chat_id)
        if pending is None:
            await _send_text_safe(
                context, chat_id, "אין תרגיל ממתין מהמאגר — לחץ/י שוב על «תרגול»."
            )
            return
        _exercise_id, bank_extracted = pending
        normalized = finalize_beam_extraction(copy.deepcopy(bank_extracted))
        try:
            bank_solved = solve_extracted_beam(normalized)
        except Exception:
            bank_solved = {"result": {"reactions_ton": {}}}
        begin_image_session(chat_id, solve_mode=mode)
        await deliver_after_draft_approve(
            context,
            chat_id,
            extracted=normalized,
            reply="",
            solved=bank_solved,
            draft_msg_id=None,
            deliver_notebook=_deliver_approved_solve,
            send_text=_send_text_safe,
            edit_draft_message=_edit_draft_message_safe,
        )
        return
    await query.answer()


async def on_assistant_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return
    action = parse_assistant_callback(query.data)
    if action is None:
        await query.answer("פעולה לא מוכרת.", show_alert=True)
        return
    chat_id = query.message.chat_id if query.message else telegram_chat_id(update)
    if not has_active_assistant_progress(chat_id):
        await query.answer("אין מסלול עוזר פעיל כרגע.", show_alert=True)
        return
    await query.answer()
    await handle_assistant_action(
        context,
        chat_id,
        action,
        send_text=_send_text_safe,
        reply_message=None,
    )


async def on_intro_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return
    parsed = parse_intro_callback(query.data)
    if parsed is None:
        await query.answer()
        return
    action, payload = parsed
    chat_id = query.message.chat_id if query.message else telegram_chat_id(update)

    if action == "menu":
        await query.answer()
        await _delete_callback_message(query)
        await _send_intro_menu(context, chat_id)
        return

    if action == "back":
        await query.answer()
        await _delete_callback_message(query)
        await _send_main_action_menu(context, chat_id)
        return

    if action == "topic":
        topic = get_intro_topic(payload)
        if topic is None:
            await query.answer("נושא לא נמצא.", show_alert=True)
            return
        await query.answer()
        await _delete_callback_message(query)
        text = intro_topic_body_hebrew(topic)
        keyboard = build_intro_topic_followup_keyboard()
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
        except BadRequest:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=keyboard,
            )
        return

    await query.answer()


async def on_formula_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return
    parsed = parse_formula_callback(query.data)
    if parsed is None:
        await query.answer()
        return
    action, payload = parsed
    chat_id = query.message.chat_id if query.message else telegram_chat_id(update)
    user_id = telegram_user_id(update)

    if action in ("menu",):
        await query.answer()
        await _delete_callback_message(query)
        await _send_formulas_menu(
            context,
            chat_id,
            user_id=user_id,
        )
        return

    if action == "back":
        await query.answer()
        await _delete_callback_message(query)
        await _send_main_action_menu(context, chat_id)
        return

    if action == "topic":
        topic = get_topic(payload)
        if topic is None:
            await query.answer("נושא לא נמצא.", show_alert=True)
            return
        if COUPON_ACCESS_ENABLED and not has_active_coupon_access(user_id):
            await query.answer("נוסחאות למנויי חבילה בלבד.", show_alert=True)
            await _delete_callback_message(query)
            await _send_formulas_locked(context, chat_id)
            return
        await query.answer()
        await _delete_callback_message(query)
        image_path = topic.image_path()
        followup = build_topic_followup_keyboard()
        if image_path is not None:
            try:
                with image_path.open("rb") as fh:
                    await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=fh,
                        caption=topic_image_caption_hebrew(topic),
                        reply_markup=followup,
                    )
            except Exception:
                log.exception("Failed sending formula image for %s", topic.topic_id)
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=topic_pending_caption_hebrew(topic),
                    reply_markup=followup,
                    parse_mode="Markdown",
                )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=topic_pending_caption_hebrew(topic),
                reply_markup=followup,
                parse_mode="Markdown",
            )
        return

    await query.answer()


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


async def cmd_formulas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """פקודת /formulas — תפריט נוסחאות (מופיע גם בתפריט הפקודות של טלגרם)."""
    if not update.message:
        return
    chat_id = telegram_chat_id(update)
    await _send_formulas_menu(
        context,
        chat_id,
        user_id=telegram_user_id(update),
        message=update.message,
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
    updated = finalize_beam_extraction(updated, merge_nearby_point_loads=False)
    if errors:
        if ref:
            await _edit_draft_message_safe(
                context,
                ref[0],
                ref[1],
                extracted,
                edit=edit,
            )
        await _send_text_safe(context, chat_id, f"⚠️ {errors[0]}")
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
        # אם נשלחה הודעת שגיאה קודמת אחרי "חשב" — מוחקים אותה לפני ניסיון חישוב נוסף.
        prev_err_mid = get_draft_error_message_id(chat_id)
        if prev_err_mid is not None:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=prev_err_mid)
            except BadRequest:
                pass
            set_draft_error_message_id(chat_id, None)
        reply, solved, extracted = approve_and_solve(chat_id, extracted)
        await deliver_after_draft_approve(
            context,
            chat_id,
            extracted=extracted,
            reply=reply,
            solved=solved,
            draft_msg_id=msg_id,
            deliver_notebook=_deliver_approved_solve,
            send_text=_send_text_safe,
            edit_draft_message=_edit_draft_message_safe,
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
        if isinstance(ld, dict) and should_open_type_picker_on_direction_click(ld):
            # עומס חדש/ריק — עדיין אין כיוון להפוך; פותחים את תפריט בחירת הסוג.
            updated = extracted
            set_draft_type_picker_idx(chat_id, cb.index)
        else:
            # עומס קיים עם ערך — לחיצה על «כיוון» פשוט הופכת כיוון, בלי תפריט נוסף.
            updated = toggle_any_load_direction(extracted, cb.index)
            set_draft_type_picker_idx(chat_id, None)
        persist_draft(chat_id, updated)
        if msg_id is not None:
            await _edit_draft_message_safe(context, chat_id, msg_id, updated)
        return

    if cb.action == "set_load_type":
        await query.answer()
        if cb.index == ADD_LOAD_TYPE_PICKER_IDX:
            updated = add_load_of_type(extracted, cb.dir)
        else:
            updated = set_load_type(extracted, cb.index, cb.dir)
        persist_draft(chat_id, updated)
        set_draft_type_picker_idx(chat_id, None)
        if msg_id is not None:
            await _edit_draft_message_safe(context, chat_id, msg_id, updated)
        return

    if cb.action == "toggle_dir":
        if cb.index == ADD_LOAD_TYPE_PICKER_IDX:
            await query.answer()
            return
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
        set_draft_edit(chat_id, None)
        set_draft_type_picker_idx(chat_id, ADD_LOAD_TYPE_PICKER_IDX)
        if msg_id is not None:
            await _edit_draft_message_safe(context, chat_id, msg_id, extracted)
        return


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    chat_id = telegram_chat_id(update)
    text = update.message.text.strip()

    if text == _PERSISTENT_ASSISTANT_LABEL:
        prompt = select_solve_mode(chat_id, SolveMode.ASSISTANT)
        await _reply_text_safe(update.message, prompt)
        return

    if text == _PERSISTENT_MAIN_LABEL:
        await _send_main_action_menu(
            context,
            chat_id,
            message=update.message,
        )
        return

    if text == _BANK_ADD_SECRET:
        prompt = select_solve_mode(chat_id, SolveMode.ADD_TO_BANK)
        await _reply_text_safe(update.message, prompt)
        return

    if has_active_assistant_progress(chat_id):
        await _reply_text_safe(
            update.message,
            "מעולה, כאן משתמשים בכפתור למעלה — «המשך».",
        )
        return

    if chat_id in _bug_report_prompt_chats:
        if text in (_BUG_REPORT_CANCEL, _PERSISTENT_BUG_REPORT_LABEL):
            if text == _BUG_REPORT_CANCEL:
                _bug_report_prompt_chats.discard(chat_id)
                await update.message.reply_text(
                    "הדיווח בוטל.",
                    reply_markup=build_persistent_keyboard(),
                )
                return
            # לחיצה חוזרת על הכפתור — פשוט מזכירים לכתוב, נשארים במצב הדיווח
            await update.message.reply_text(
                "כתוב/י עכשיו את תיאור התקלה, או לחץ/י «ביטול דיווח».",
                reply_markup=build_bug_report_cancel_keyboard(),
            )
            return

        _bug_report_prompt_chats.discard(chat_id)
        user = update.effective_user
        report = _bug_report_admin_text(
            user_id=telegram_user_id(update),
            chat_id=chat_id,
            username=user.username if user else None,
            first_name=user.first_name if user else None,
            report_text=text,
        )
        sent = await _forward_bug_report_via_admin_bot(
            report, fallback_bot=context.bot
        )
        if sent:
            await update.message.reply_text(
                "✅ תודה! הדיווח נשלח לצוות. נטפל בזה בהקדם.",
                reply_markup=build_persistent_keyboard(),
            )
        else:
            log.warning("Bug report could not be delivered (chat=%s)", chat_id)
            await update.message.reply_text(
                "קיבלנו את הדיווח מקומית, אבל השליחה לצוות נכשלה זמנית. "
                "נסי/ה שוב עוד רגע או כתוב/י לנו בוואטסאפ אם דחוף.",
                reply_markup=build_persistent_keyboard(),
            )
        return

    if text == _PERSISTENT_COUPON_LABEL:
        await cmd_coupon(update, context)
        return
    if text == _PERSISTENT_QUOTA_LABEL:
        await cmd_quota(update, context)
        return
    if text == _PERSISTENT_FORMULAS_LABEL:
        await _send_formulas_menu(
            context,
            chat_id,
            user_id=telegram_user_id(update),
            message=update.message,
        )
        return
    if text == _PERSISTENT_BUG_REPORT_LABEL:
        await _prompt_bug_report(update.message)
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
            )
            return

    if is_draft_pending(chat_id) and not looks_like_draft_patch(text):
        await _reply_text_safe(
            update.message,
            _TEXT_UNHANDLED,
        )
        return

    draft_result = handle_draft_text(chat_id, text)
    if draft_result.handled:
        ref = get_draft_message_ref(chat_id)
        if draft_result.approved:
            msg_id = ref[1] if ref else None
            extracted = draft_result.extracted or get_stored_vision_extracted(chat_id) or {}
            await deliver_after_draft_approve(
                context,
                chat_id,
                extracted=extracted,
                reply=draft_result.reply,
                solved=draft_result.solved or {},
                draft_msg_id=msg_id,
                deliver_notebook=_deliver_approved_solve,
                send_text=_send_text_safe,
                edit_draft_message=_edit_draft_message_safe,
            )
            set_draft_edit(chat_id, None)
        elif draft_result.update_draft and ref and draft_result.extracted:
            try:
                await _edit_draft_message_safe(
                    context,
                    ref[0],
                    ref[1],
                    draft_result.extracted,
                )
            except BadRequest as exc:
                log.warning("Draft message edit failed: %s", exc)
            if draft_result.errors:
                await _send_text_safe(context, chat_id, f"⚠️ {draft_result.errors[0]}")
        return

    await _reply_text_safe(
        update.message,
        IMAGE_ONLY_TEXT_REPLY,
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

    pending_mode = consume_pending_solve_mode(chat_id)
    solve_mode = pending_mode or SolveMode.NOTEBOOK
    # הוספת תרגיל למאגר לא צורכת מכסה — לא שייכת לפתרון תרגיל בפועל.
    is_bank_submission = pending_mode == SolveMode.ADD_TO_BANK

    if COUPON_ACCESS_ENABLED and not is_bank_submission:
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
            if isinstance(reply_markup, InlineKeyboardMarkup):
                await _reply_text_safe(
                    update.message,
                    "התפריט למטה זמין תמיד 👇",
                )
            return
        log.info(
            "Image allowed user=%s used=%s/%s remaining=%s",
            user_id,
            access.images_used,
            access.tier_limit,
            access.images_remaining,
        )

    begin_image_session(chat_id, solve_mode=solve_mode)

    if VISION_ASYNC_ENABLED and update.message:
        await send_vision_ack(update.message)

    temp_image: TempImageFile | None = None
    try:
        temp_image = await save_message_image_to_temp(update, context)
        if is_bank_submission:
            # שומרים עותק של תמונת המקור לפני prepare_image_for_vision שמוחק אותה.
            bank_copy = temp_image.path.with_name(
                f"bank_src_{chat_id}_{msg_id}_{int(time.time() * 1000)}"
                f"{temp_image.path.suffix or '.jpg'}"
            )
            try:
                shutil.copy2(temp_image.path, bank_copy)
                set_pending_bank_submission_image(chat_id, bank_copy)
                log.info("Preserved bank submission image: %s", bank_copy.name)
            except OSError as exc:
                log.warning(
                    "Failed to preserve bank submission image chat=%s: %s",
                    chat_id,
                    exc,
                )
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
        await _reply_text_safe(
            update.message,
            f"לא הצלחתי לעבד את התמונה:\n{exc}",
        )
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
