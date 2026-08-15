# -*- coding: utf-8 -*-
"""Handlers טלגרם — מימוש מרוכז; חבילת ``bot.handlers`` מייצאת מכאן."""
from __future__ import annotations

import asyncio
import copy
import logging
import math
import shutil
import tempfile
import time
from pathlib import Path

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
    BOT_UI_VERSION,
    COUPON_ACCESS_ENABLED,
    DRAFT_APPROVAL_MODE,
    IMAGE_ONLY_TEXT_REPLY,
    VISION_ASYNC_ENABLED,
)
from bot.access import (
    ImageAccessResult,
    ImageAccessStatus,
    check_practice_feature_access,
    check_solve_access,
    consume_practice_slot,
    consume_solve_slot,
    coupon_prompt_text_hebrew,
    create_purchase_request,
    ensure_user_first_seen,
    has_active_coupon_access,
    image_access_reply_hebrew,
    looks_like_coupon_code,
    ping_reply_hebrew,
    quota_status_for_user,
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
try:
    from intro import (
        build_how_to_approach_keyboard,
        build_inclined_load_keyboard,
        build_mavo_continue_keyboard,
        build_opening_keyboard,
        generate_fixed_mavo_exercise_png,
        generate_mavo_exercise_png,
        how_to_approach_message_hebrew,
        intro_topic_body_hebrew,
        mavo_followup_message_hebrew,
        opening_message_hebrew,
        parse_intro_callback,
    )

    INTRO_AVAILABLE = True
except ImportError:
    INTRO_AVAILABLE = False
    build_how_to_approach_keyboard = None  # type: ignore[assignment]
    build_inclined_load_keyboard = None  # type: ignore[assignment]
    build_mavo_continue_keyboard = None  # type: ignore[assignment]
    build_opening_keyboard = None  # type: ignore[assignment]
    generate_fixed_mavo_exercise_png = None  # type: ignore[assignment]
    generate_mavo_exercise_png = None  # type: ignore[assignment]
    how_to_approach_message_hebrew = None  # type: ignore[assignment]
    intro_topic_body_hebrew = None  # type: ignore[assignment]
    mavo_followup_message_hebrew = None  # type: ignore[assignment]
    opening_message_hebrew = None  # type: ignore[assignment]
    parse_intro_callback = None  # type: ignore[assignment]


from bot.draft_editor import (
    apply_field_edit,
    approve_and_solve,
    handle_draft_text,
    is_approval_message,
    persist_draft,
)
from bot.draft_keyboard import (
    DRAFT_INSTRUCTION_TEXT,
    build_draft_approve_keyboard,
    build_load_dir_prompt_keyboard,
    edit_prompt,
    parse_draft_callback,
)
from bot.draft_nl_edit import apply_nl_draft_edit
from bot.draft_preview import (
    refresh_draft_after_correction,
    send_draft_preview,
    wipe_draft_conversation,
)
from bot.notebook_render import render_notebook_png_temp
from bot.gemini_chat import friendly_gemini_error
from bot.solve_mode import (
    build_bank_solve_mode_keyboard,
    parse_bank_mode_action,
    parse_menu_mode_action,
    select_solve_mode,
)
from personal_assistant.runtime import (
    deliver_after_draft_approve,
    handle_assistant_action,
    has_active_assistant_progress,
    parse_assistant_callback,
)
from bot.solution_check import solve_extracted_beam
from bot.solution_session import (
    SolveMode,
    append_formulas_chat_message_id,
    append_practice_chat_message_id,
    begin_formulas_chat_trail,
    begin_image_session,
    begin_practice_chat_trail,
    clear_assistant_prev_stack,
    clear_exercise_image_message_id,
    clear_pending_bank_exercise,
    consume_pending_bank_exercise,
    consume_pending_solve_mode,
    discard_formulas_chat_trail,
    discard_practice_chat_trail,
    end_practice_session,
    get_chat_anchor_message_id,
    get_exercise_image_message_id,
    get_solution_session,
    has_formulas_chat_trail,
    has_practice_chat_trail,
    pop_assistant_message_ids,
    pop_formulas_chat_message_ids,
    pop_practice_chat_message_ids,
    reset_user_session,
    set_chat_anchor_message_id,
    set_pending_bank_exercise,
    set_pending_bank_submission_image,
)
from bot.images import TempImageFile, prepare_image_for_vision, save_message_image_to_temp
from bot.system_prompt import reload_system_instruction_if_changed
from bot.draft_session import (
    get_draft_cleanup_message_ids,
    get_draft_error_message_id,
    get_draft_edit,
    get_draft_edit_prompt_id,
    get_draft_message_ref,
    get_draft_type_picker_idx,
    get_stored_vision_extracted,
    is_draft_pending,
    register_draft_cleanup_id,
    set_draft_error_message_id,
    set_draft_edit,
    set_draft_edit_prompt_id,
    set_draft_pending,
    set_draft_source_user_message_id,
    set_draft_type_picker_idx,
)
from bot.vision import (
    finalize_beam_extraction,
    format_vision_extract_only_reply,
    package_extraction_response,
)
from bot.vision_queue import (
    run_vision_extract,
    schedule_vision_job,
    send_vision_ack,
    typing_while_waiting,
)

log = logging.getLogger("beam_telegram_bot")

_TEXT_UNHANDLED = (
    "שלח תמונה של תרגיל, או כתוב מה לתקן בטיוטה הפעילה."
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
_PERSISTENT_ASSISTANT_LABEL = "מדריך לפתרון"
# קיצור זמני: שליחת אות B מייצרת תרגיל מהמחולל ושולחת אותו
_GENERATED_EXERCISE_TRIGGER = "B"
_GENERATED_EXERCISE_ID = 0


def _bank_extracted_for_solve(extracted: dict) -> dict:
    """מכין extracted ממאגר/מחולל לפני מדריך/פתרון.

    תרגילי מחולל התרגילים כבר מדויקים — ``finalize_beam_extraction`` (תיקוני vision)
    משחית בהם מיקומי סמכים ומידות. מדלגים עליו כשמסומן במטא.
    """
    data = copy.deepcopy(extracted) if isinstance(extracted, dict) else {}
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    skip = bool(meta.get("skip_vision_normalize")) or meta.get("source") == "exercise_generator"
    if skip:
        return data
    return finalize_beam_extraction(data)
_PERSISTENT_FORMULAS_LABEL = "נוסחאות"
_PERSISTENT_QUOTA_LABEL = "מכסה"
_PERSISTENT_COUPON_LABEL = "קופון"
_PERSISTENT_BUG_REPORT_LABEL = "דיווח על תקלה"
_PERSISTENT_MAIN_LABEL = "ראשי"
_START_INTRO_LABEL = "לימוד בסיס"

_START_SEND_IMAGE_LABEL = "פתרון לתרגיל"
_START_GIVE_EXERCISE_LABEL = "תרגול"
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
):
    """שולח הודעה; אם Markdown נשבר — fallback לטקסט רגיל. מחזיר את ההודעה שנשלחה."""
    if reply_markup is None:
        reply_markup = build_persistent_keyboard()
    try:
        return await message.reply_text(
            text, parse_mode=parse_mode, reply_markup=reply_markup
        )
    except BadRequest as exc:
        if "parse entities" not in str(exc).lower():
            raise
        log.warning("Telegram Markdown failed, sending plain text: %s", exc)
        return await message.reply_text(text, reply_markup=reply_markup)

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
    """שולח פתרון + מחברת. מחיקת הטיוטה נעשית לפני הקריאה (ב-approve)."""
    has_result = bool((solved or {}).get("result"))
    notebook_path = None
    session = get_solution_session(chat_id)
    track_practice = bool(session is not None and session.from_practice)

    if not has_result and draft_msg_id is not None:
        await _edit_draft_message_safe(
            context,
            chat_id,
            draft_msg_id,
            extracted,
        )

    if reply:
        sent = await _send_text_safe(context, chat_id, reply)
        if track_practice:
            _track_sent_message(chat_id, sent)
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
                kb = InlineKeyboardMarkup(
                    [[InlineKeyboardButton("ראשי", callback_data="menu:main")]]
                )
                with notebook_path.open("rb") as photo:
                    sent = await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo,
                        caption="פתרון מחברת מלא",
                        reply_markup=kb,
                    )
                if track_practice:
                    _track_sent_message(chat_id, sent)
            except Exception as exc:
                log.warning("Failed to send notebook chat=%s: %s", chat_id, exc)

    if notebook_path is not None:
        notebook_path.unlink(missing_ok=True)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    # מתחיל שעון 24ש' לנוסחאות (first_seen) — תואם להודעת ה-welcome.
    user = update.effective_user
    if user is not None:
        ensure_user_first_seen(int(user.id))
    context.chat_data[_CHAT_UI_VERSION_KEY] = str(BOT_UI_VERSION or "").strip() or "default"
    chat_id = telegram_chat_id(update)
    leave_session = get_solution_session(chat_id)
    if has_practice_chat_trail(chat_id) or (
        leave_session is not None and leave_session.from_practice
    ):
        await cleanup_practice_chat(context, chat_id)
    await _leave_formulas_chat_if_needed(context, chat_id)
    text = build_start_welcome_text()
    keyboard = build_start_keyboard()
    try:
        # שולחים את המקלדת הקבועה (התפריט הזמין תמיד) עם הודעת הפתיחה.
        welcome = await update.message.reply_text(
            text, reply_markup=build_persistent_keyboard(), parse_mode="Markdown"
        )
    except BadRequest as exc:
        if "parse entities" not in str(exc).lower():
            raise
        welcome = await update.message.reply_text(
            text, reply_markup=build_persistent_keyboard()
        )
    set_chat_anchor_message_id(chat_id, getattr(welcome, "message_id", None))
    # תפריט כפתורים Inline (לא "מקלדת למטה").
    await update.message.reply_text("בחר/י פעולה:", reply_markup=keyboard)


def build_start_welcome_text() -> str:
    return (
        "היי, אני שמח שהגעת לכאן. בניתי את הבוט הזה כדי לעזור לנו לעבור את תרגילי "
        "הסטטיקה קצת יותר בקלות, בלי להיתקע שעות על אותה שאלה.\n\n"
        "השימוש בבוט פשוט: אפשר להעלות תמונה של תרגיל שאתה עובד עליו, או לבחור "
        "«תרגול» ולקבל תרגיל מוכן, שם הנתונים כבר מוגדרים. בכל מקרה, אתה יכול לבחור בין "
        "פתרון מחברת מלא לבין ליווי צמוד של מדריך. המדריך הזה מלווה אותך "
        "צעד-צעד עם כפתורים נוחים ומסביר את הדרך, ובנוסף יש לך אופציה נגישה לשלוף "
        "נוסחאות ספציפיות בהתאם למה שאתה צריך באותו רגע.\n\n"
        "אם יש בעיות או בקשות ספציפיות, יש אופציה לדיווח שדרכה תוכל לפנות אליי ישירות.\n\n"
        "הבוט זמין עבורך 24/7 עם כל החבילה המלאה. כדי שתוכל להתרשם ולראות איך זה "
        "עובד באמת, פתחתי לך גישה מלאה לכל האפשרויות ל-24 שעות הקרובות ללא התחייבות.\n\n"
        "אחרי 24 השעות אפשר להמשיך עם מנוי: חודש ב־₪30, או 4 חודשים ב־₪90 "
        "(גישה מועדפת לפתרון ותרגול, עם המתנה של 10 דקות בין שימושים).\n\n"
        "מוזמן להתחיל להשתמש, מקווה שזה יעזור לך לעבור את הקורס בראש שקט."
    )


def build_upgrade_options_keyboard() -> InlineKeyboardMarkup:
    """כפתור רכישת חבילה — מוביל לאופציות החבילות."""
    rows: list[list[InlineKeyboardButton]] = []
    if COUPON_ACCESS_ENABLED:
        rows.append(
            [InlineKeyboardButton("רכישת חבילה", callback_data="buy:menu")]
        )
    return InlineKeyboardMarkup(rows)


def _purchase_cta_markup(access: ImageAccessResult) -> InlineKeyboardMarkup | None:
    """מקלדת רכישה כשהחסימה היא בגלל חוסר קופון/מנוי (לא cooldown)."""
    if access.status == ImageAccessStatus.COOLDOWN:
        return None
    if access.status == ImageAccessStatus.OK:
        return None
    return build_upgrade_options_keyboard()


def build_start_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if INTRO_AVAILABLE:
        rows.append(
            [InlineKeyboardButton(_START_INTRO_LABEL, callback_data="menu:intro")]
        )
    rows.extend(
        [
            [InlineKeyboardButton(_START_SEND_IMAGE_LABEL, callback_data="menu:new")],
            [
                InlineKeyboardButton(
                    _START_GIVE_EXERCISE_LABEL, callback_data="menu:give_exercise"
                )
            ],
            [
                InlineKeyboardButton(
                    _PERSISTENT_FORMULAS_LABEL, callback_data="menu:formulas"
                )
            ],
        ]
    )
    if COUPON_ACCESS_ENABLED:
        rows.append(
            [InlineKeyboardButton(_START_PURCHASE_LABEL, callback_data="menu:coupon")]
        )
    return InlineKeyboardMarkup(rows)




def build_persistent_keyboard() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(_PERSISTENT_MAIN_LABEL)],
        [KeyboardButton(_PERSISTENT_BUG_REPORT_LABEL), KeyboardButton(_PERSISTENT_FORMULAS_LABEL)],
    ]
    return ReplyKeyboardMarkup(
        rows,
        is_persistent=True,
        resize_keyboard=True,
        one_time_keyboard=False,
    )


_CHAT_UI_VERSION_KEY = "bot_ui_version"
_CHAT_UI_VERSION_NOTICE_MSG_ID_KEY = "bot_ui_version_notice_msg_id"


async def sync_chat_ui_to_current_version(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """אחרי דיפלוי — בהודעה הראשונה מרענן מקלדת/תפריט כדי לא להישאר על גרסה ישנה."""
    notice_msg_id = context.chat_data.pop(_CHAT_UI_VERSION_NOTICE_MSG_ID_KEY, None)
    if notice_msg_id and update.effective_chat:
        try:
            await context.bot.delete_message(
                chat_id=update.effective_chat.id,
                message_id=notice_msg_id,
            )
        except Exception as exc:
            log.debug("UI sync notice message deletion failed chat=%s: %s", update.effective_chat.id, exc)

    message = update.message
    if message is None:
        return
    current = str(BOT_UI_VERSION or "").strip() or "default"
    if context.chat_data.get(_CHAT_UI_VERSION_KEY) == current:
        return
    context.chat_data[_CHAT_UI_VERSION_KEY] = current

    # /start כבר שולח את המקלדת העדכנית — רק מסמנים גרסה.
    text = (message.text or "").strip()
    if text.startswith("/start") or text.startswith("/help"):
        return

    try:
        sent_msg = await message.reply_text(
            "הבוט עודכן אצלך לגרסה העדכנית.",
            reply_markup=build_persistent_keyboard(),
        )
        if sent_msg and hasattr(sent_msg, "message_id"):
            context.chat_data[_CHAT_UI_VERSION_NOTICE_MSG_ID_KEY] = sent_msg.message_id
    except BadRequest as exc:
        log.warning("UI sync reply failed chat=%s: %s", telegram_chat_id(update), exc)


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
        "דיווח תקלה חדש\n"
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
        "*דיווח על תקלה*\n\n"
        "כתוב/י כאן במילים שלך מה קרה (או מה לא עובד).\n"
        "אחרי השליחה הדיווח יועבר אוטומטית לצוות.\n\n"
        "אפשר לבטל עם «ביטול דיווח».",
        parse_mode="Markdown",
        reply_markup=build_bug_report_cancel_keyboard(),
    )
    try:
        await message.reply_text(
            "כאן אפשר לרשום את פרטי התקלה:",
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


async def _send_content_locked(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    *,
    message=None,
    edit_message=None,
) -> None:
    """נעילת נוסחאות/תרגול אחרי חלון 24ש' בלי קופון."""
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


# תאימות לשם הישן
_send_formulas_locked = _send_content_locked


async def _send_formulas_menu(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    *,
    user_id: int | None = None,
    message=None,
    edit_message=None,
) -> None:
    """מציג תפריט נוסחאות — פתוח תמיד."""
    _ = user_id

    if not has_formulas_chat_trail(chat_id):
        begin_formulas_chat_trail(chat_id)

    text = formulas_menu_intro_hebrew()
    keyboard = build_formulas_menu_keyboard()
    sent = None
    try:
        if edit_message is not None:
            sent = await edit_message.edit_text(
                text,
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
        elif message is not None:
            sent = await message.reply_text(
                text,
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
        else:
            sent = await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
    except BadRequest:
        if edit_message is not None:
            try:
                sent = await edit_message.edit_text(text, reply_markup=keyboard)
            except BadRequest:
                sent = None
        elif message is not None:
            sent = await message.reply_text(text, reply_markup=keyboard)
        else:
            sent = await context.bot.send_message(
                chat_id=chat_id, text=text, reply_markup=keyboard
            )
    if sent is None and edit_message is not None:
        append_formulas_chat_message_id(
            chat_id, getattr(edit_message, "message_id", None)
        )
    else:
        append_formulas_chat_message_id(chat_id, getattr(sent, "message_id", None))


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


async def _remove_callback_keyboard(query) -> None:
    """מסיר את מקלדת האינליין בהודעה בלי למחוק את הטקסט."""
    message = getattr(query, "message", None)
    if message is None:
        return
    try:
        await message.edit_reply_markup(reply_markup=None)
    except BadRequest as exc:
        log.debug("Could not clear callback keyboard: %s", exc)


async def cleanup_formulas_chat(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
) -> None:
    """מוחק מהצ'אט את כל הודעות הנוסחאות של הסשן הנוכחי."""
    ids = pop_formulas_chat_message_ids(chat_id)
    seen: set[int] = set()
    for mid in ids:
        mid_i = int(mid)
        if mid_i <= 0 or mid_i in seen:
            continue
        seen.add(mid_i)
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=mid_i)
        except Exception:
            pass


async def _leave_formulas_chat_if_needed(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
) -> None:
    if has_formulas_chat_trail(chat_id):
        await cleanup_formulas_chat(context, chat_id)


async def cleanup_practice_chat(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    *,
    clear_progress: bool = True,
    keep_exercise_image: bool = False,
) -> None:
    """מוחק מהצ'אט את כל הודעות התרגול הנוכחי (תמונה/מצב/מחברת/מדריך)."""
    ex_img_id = get_exercise_image_message_id(chat_id)
    ids = pop_practice_chat_message_ids(chat_id)
    ids.extend(pop_assistant_message_ids(chat_id))
    seen: set[int] = set()
    for mid in ids:
        mid_i = int(mid)
        if mid_i <= 0 or mid_i in seen:
            continue
        seen.add(mid_i)
        if keep_exercise_image and ex_img_id is not None and mid_i == ex_img_id:
            continue
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=mid_i)
        except Exception:
            pass
    if clear_progress:
        clear_pending_bank_exercise(chat_id)
        try:
            from personal_assistant.runtime import clear_personal_assistant_progress

            clear_personal_assistant_progress(chat_id)
        except Exception:
            pass
        clear_assistant_prev_stack(chat_id)
        end_practice_session(chat_id)
        if not keep_exercise_image:
            clear_exercise_image_message_id(chat_id)


_CHAT_WIPE_MAX_MESSAGES = 400


async def wipe_chat_after_anchor(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    *,
    through_message_id: int | None,
) -> None:
    """מוחק את כל ההודעות אחרי הודעת הבוט הראשונה (כולל through_message_id)."""
    anchor = get_chat_anchor_message_id(chat_id)
    if anchor is None or through_message_id is None:
        await cleanup_practice_chat(context, chat_id)
        await cleanup_formulas_chat(context, chat_id)
        reset_user_session(chat_id)
        return

    start_id = int(anchor) + 1
    end_id = int(through_message_id)
    if end_id >= start_id:
        if end_id - start_id + 1 > _CHAT_WIPE_MAX_MESSAGES:
            start_id = end_id - _CHAT_WIPE_MAX_MESSAGES + 1
        for mid in range(start_id, end_id + 1):
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=mid)
            except BadRequest:
                pass

    # מנקים מצב מקומי — ההודעות כבר נמחקו מהצ'אט
    discard_practice_chat_trail(chat_id)
    discard_formulas_chat_trail(chat_id)
    reset_user_session(chat_id)


def _track_sent_message(chat_id: int, sent: object | None) -> None:
    try:
        mid = int(getattr(sent, "message_id", 0) or 0)
    except (TypeError, ValueError):
        return
    append_practice_chat_message_id(chat_id, mid)


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


async def _send_intro_opening(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
) -> None:
    """שולח את הודעת הפתיחה של מבוא לסטטיקה + כפתור המשך."""
    if not INTRO_AVAILABLE:
        return
    await context.bot.send_message(
        chat_id=chat_id,
        text=opening_message_hebrew(),
        reply_markup=build_opening_keyboard(),
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
    leave_session = get_solution_session(chat_id)
    if has_practice_chat_trail(chat_id) or (
        leave_session is not None and leave_session.from_practice
    ):
        await cleanup_practice_chat(context, chat_id)
    await _leave_formulas_chat_if_needed(context, chat_id)

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
    chat_id = query.message.chat_id if query.message else telegram_chat_id(update)

    # יציאה מתרגול לנושא אחר — מוחקים את הודעות התרגיל מהצ'אט.
    if action in ("new", "formulas", "intro", "coupon", "main") or action.startswith("mode:"):
        leave_session = get_solution_session(chat_id)
        if has_practice_chat_trail(chat_id) or (
            leave_session is not None and leave_session.from_practice
        ):
            await cleanup_practice_chat(context, chat_id)

    # יציאה מנוסחאות לנושא אחר — מוחקים את הודעות הנוסחאות מהצ'אט.
    if action in ("new", "intro", "coupon", "give_exercise", "main") or action.startswith(
        "mode:"
    ):
        await _leave_formulas_chat_if_needed(context, chat_id)

    if action == "main":
        await query.answer()
        await _delete_callback_message(query)
        await _send_main_action_menu(context, chat_id)
        return

    if action == "coupon":
        if not COUPON_ACCESS_ENABLED:
            await query.answer("מערכת הקופונים כבויה.", show_alert=True)
            return
        await query.answer()
        await _delete_callback_message(query)
        await _send_purchase_menu(context, chat_id)
        return
    if action == "formulas":
        await query.answer()
        await _delete_callback_message(query)
        # כניסה מחדש — מנקים סשן נוסחאות קודם אם נשאר בצ'אט.
        await cleanup_formulas_chat(context, chat_id)
        await _send_formulas_menu(
            context,
            chat_id,
            user_id=telegram_user_id(update),
        )
        return
    if action == "intro":
        if not INTRO_AVAILABLE:
            await query.answer("המבוא בפיתוח ולא זמין כאן כרגע.", show_alert=True)
            return
        await query.answer()
        await _delete_callback_message(query)
        await _send_intro_opening(context, chat_id)
        return
    if action == "give_exercise":
        await query.answer()
        await _delete_callback_message(query)
        await _deliver_generated_exercise(
            context,
            chat_id,
            user_id=telegram_user_id(update),
        )
        return
    if action == "new":
        if COUPON_ACCESS_ENABLED:
            access = check_solve_access(telegram_user_id(update))
            if access.status != ImageAccessStatus.OK:
                await query.answer()
                await _delete_callback_message(query)
                await _send_text_safe(
                    context,
                    chat_id,
                    image_access_reply_hebrew(access),
                    reply_markup=_purchase_cta_markup(access),
                )
                return
        await query.answer()
        await _delete_callback_message(query)
        select_solve_mode(chat_id, SolveMode.NOTEBOOK)
        await _send_text_safe(context, chat_id, "שלח את התרגיל שלך")
        return
    if action.startswith("mode:"):
        mode = parse_menu_mode_action(action)
        if mode is None:
            await query.answer()
            return
        if COUPON_ACCESS_ENABLED:
            access = check_solve_access(telegram_user_id(update))
            if access.status != ImageAccessStatus.OK:
                await query.answer()
                await _delete_callback_message(query)
                await _send_text_safe(
                    context,
                    chat_id,
                    image_access_reply_hebrew(access),
                    reply_markup=_purchase_cta_markup(access),
                )
                return
        await query.answer()
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
        await _delete_callback_message(query)
        pending = consume_pending_bank_exercise(chat_id)
        if pending is None:
            await _send_text_safe(
                context, chat_id, "אין תרגיל ממתין מהמאגר — לחץ/י שוב על «תרגול»."
            )
            return
        _exercise_id, bank_extracted = pending
        if int(_exercise_id) == _GENERATED_EXERCISE_ID:
            if isinstance(bank_extracted, dict):
                meta = dict(bank_extracted.get("meta") or {})
                meta.setdefault("source", "exercise_generator")
                meta["skip_vision_normalize"] = True
                bank_extracted = {**bank_extracted, "meta": meta}
        normalized = _bank_extracted_for_solve(bank_extracted)
        try:
            bank_solved = solve_extracted_beam(normalized)
        except Exception:
            bank_solved = {"result": {"reactions_ton": {}}}
        begin_image_session(chat_id, solve_mode=mode, from_practice=True)
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
        await query.answer("אין מסלול מדריך פעיל כרגע.", show_alert=True)
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
    if not INTRO_AVAILABLE or parse_intro_callback is None:
        await query.answer()
        return
    topic_id = parse_intro_callback(query.data)
    if topic_id is None:
        await query.answer()
        return
    await query.answer()

    if topic_id == "how_to_approach":
        chat_id = query.message.chat_id if query.message else telegram_chat_id(update)
        await _delete_callback_message(query)

        await cleanup_practice_chat(context, chat_id)
        await _leave_formulas_chat_if_needed(context, chat_id)
        begin_practice_chat_trail(chat_id)

        text = how_to_approach_message_hebrew() if how_to_approach_message_hebrew is not None else ""
        if text:
            kb = build_how_to_approach_keyboard() if build_how_to_approach_keyboard is not None else None
            sent_msg = await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=kb,
            )
            _track_sent_message(chat_id, sent_msg)
        return

    if topic_id in ("support_exercises", "fixed_support_exercises"):
        chat_id = query.message.chat_id if query.message else telegram_chat_id(update)
        await _remove_callback_keyboard(query)

        is_fixed = topic_id == "fixed_support_exercises"
        gen_func = generate_fixed_mavo_exercise_png if is_fixed else generate_mavo_exercise_png
        prefix = "exgen_fixed_mavo_" if is_fixed else "exgen_mavo_"
        ex_label = "ריתום" if is_fixed else "סמכים"

        if gen_func is not None:
            with tempfile.TemporaryDirectory(prefix=prefix) as td:
                png_path = gen_func(Path(td))
                with png_path.open("rb") as photo:
                    sent_photo = await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo,
                        reply_markup=build_persistent_keyboard(),
                    )
                _track_sent_message(chat_id, sent_photo)

        if mavo_followup_message_hebrew is not None:
            followup_text = mavo_followup_message_hebrew(ex_label)
            kb = build_mavo_continue_keyboard() if build_mavo_continue_keyboard is not None else None
            sent_followup = await context.bot.send_message(
                chat_id=chat_id,
                text=followup_text,
                reply_markup=kb,
            )
            _track_sent_message(chat_id, sent_followup)
        return

    if topic_id == "mavo_continue":
        return

    if topic_id == "distributed_load":
        chat_id = query.message.chat_id if query.message else telegram_chat_id(update)
        user_id = telegram_user_id(update)
        await _delete_callback_message(query)

        await cleanup_practice_chat(context, chat_id)
        await _leave_formulas_chat_if_needed(context, chat_id)
        begin_practice_chat_trail(chat_id)

        body = intro_topic_body_hebrew("distributed_load") if intro_topic_body_hebrew else None
        if body:
            sent_first = await context.bot.send_message(
                chat_id=chat_id,
                text=body,
                reply_markup=build_persistent_keyboard(),
            )
            _track_sent_message(chat_id, sent_first)

        try:
            from intro.distributed_load import build_distributed_explanation_text
            from intro.distributed_load.generator import (
                generate_equivalent_point_load_exercise,
                generate_exercise as generate_distributed_exercise,
            )
        except ImportError as exc:
            log.exception("distributed_load generator import failed: %s", exc)
            await _send_text_safe(context, chat_id, "מחולל התרגילים לעומס מפורס לא זמין כרגע.")
            return
        try:
            with tempfile.TemporaryDirectory(prefix="exgen_distributed_") as td:
                artifact = generate_distributed_exercise(out_dir=Path(td), stem="live")
                png_path = artifact.png_path
                extracted = copy.deepcopy(artifact.extracted)
                meta = dict(extracted.get("meta") or {})
                meta["source"] = "exercise_generator_distributed"
                meta["skip_vision_normalize"] = True
                extracted["meta"] = meta
                with png_path.open("rb") as photo:
                    sent = await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo,
                        reply_markup=build_persistent_keyboard(),
                    )
                _track_sent_message(chat_id, sent)

                exp_text = build_distributed_explanation_text(extracted)
                sent_exp = await context.bot.send_message(
                    chat_id=chat_id,
                    text=exp_text,
                    reply_markup=build_persistent_keyboard(),
                )
                _track_sent_message(chat_id, sent_exp)

                equiv_png_path = generate_equivalent_point_load_exercise(
                    artifact.exercise, out_dir=Path(td), stem="live_equivalent"
                )
                with equiv_png_path.open("rb") as photo:
                    sent_equiv = await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo,
                        reply_markup=build_persistent_keyboard(),
                    )
                _track_sent_message(chat_id, sent_equiv)

                from intro.distributed_load import (
                    build_distributed_load_keyboard,
                    practice_prompt_hebrew as distributed_practice_prompt_hebrew,
                )
                sent_prompt = await context.bot.send_message(
                    chat_id=chat_id,
                    text=distributed_practice_prompt_hebrew(),
                    reply_markup=build_distributed_load_keyboard(),
                )
                _track_sent_message(chat_id, sent_prompt)
        except Exception as exc:
            log.exception("Failed to generate distributed exercise chat=%s: %s", chat_id, exc)
            await _send_text_safe(context, chat_id, "לא הצלחתי להכין תרגיל כרגע. נסי/ה שוב בעוד רגע.")
            return

        if COUPON_ACCESS_ENABLED and user_id is not None:
            consume_practice_slot(int(user_id))
        return

    if topic_id == "inclined_load":
        chat_id = query.message.chat_id if query.message else telegram_chat_id(update)
        user_id = telegram_user_id(update)
        await _delete_callback_message(query)

        await cleanup_practice_chat(context, chat_id)
        await _leave_formulas_chat_if_needed(context, chat_id)
        begin_practice_chat_trail(chat_id)

        body = intro_topic_body_hebrew("inclined_load") if intro_topic_body_hebrew else None
        if body:
            sent_first = await context.bot.send_message(
                chat_id=chat_id,
                text=body,
                reply_markup=build_persistent_keyboard(),
            )
            _track_sent_message(chat_id, sent_first)

        try:
            from intro.inclined_load import (
                build_inclined_explanation_text,
                build_inclined_load_keyboard,
            )
            from intro.inclined_load.generator import (
                generate_decomposed_exercise,
                generate_exercise as generate_inclined_exercise,
            )
        except ImportError as exc:
            log.exception("inclined_load generator import failed: %s", exc)
            await _send_text_safe(context, chat_id, "מחולל התרגילים לעומס אלכסוני לא זמין כרגע.")
            return
        try:
            with tempfile.TemporaryDirectory(prefix="exgen_inclined_") as td:
                artifact = generate_inclined_exercise(out_dir=Path(td), stem="live")
                png_path = artifact.png_path
                extracted = copy.deepcopy(artifact.extracted)
                meta = dict(extracted.get("meta") or {})
                meta["source"] = "exercise_generator_inclined"
                meta["skip_vision_normalize"] = True
                extracted["meta"] = meta
                with png_path.open("rb") as photo:
                    sent = await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo,
                        reply_markup=build_persistent_keyboard(),
                    )
                _track_sent_message(chat_id, sent)

                # שליחת ההסבר הדינמי
                exp_text = build_inclined_explanation_text(extracted)
                sent = await context.bot.send_message(
                    chat_id=chat_id,
                    text=exp_text,
                    reply_markup=build_persistent_keyboard(),
                )
                _track_sent_message(chat_id, sent)
                _track_sent_message(chat_id, sent)

                # שליחת הודעה רביעית: תמונת התרגיל המפורק + מקלדת תרגול/חזרה
                decomposed_png_path = generate_decomposed_exercise(
                    artifact.exercise, out_dir=Path(td), stem="live_decomposed"
                )
                keyboard = build_inclined_load_keyboard() if build_inclined_load_keyboard else None
                with decomposed_png_path.open("rb") as photo:
                    sent = await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo,
                        reply_markup=keyboard,
                    )
                _track_sent_message(chat_id, sent)
        except Exception as exc:
            log.exception("Failed to generate inclined exercise chat=%s: %s", chat_id, exc)
            await _send_text_safe(context, chat_id, "לא הצלחתי להכין תרגיל כרגע. נסי/ה שוב בעוד רגע.")
            return

        if COUPON_ACCESS_ENABLED and user_id is not None:
            consume_practice_slot(int(user_id))
        return

    if topic_id == "distributed_on_support":
        chat_id = query.message.chat_id if query.message else telegram_chat_id(update)
        user_id = telegram_user_id(update)
        await _delete_callback_message(query)
        try:
            from intro.distributed_load.generator import (
                generate_on_support_exercise as generate_distributed_on_support_exercise,
            )
        except ImportError as exc:
            log.exception("distributed_load generator import failed: %s", exc)
            await _send_text_safe(context, chat_id, "מחולל התרגילים לעומס מפורס על סמך לא זמין כרגע.")
            return

        await cleanup_practice_chat(context, chat_id)
        await _leave_formulas_chat_if_needed(context, chat_id)
        begin_practice_chat_trail(chat_id)
        try:
            with tempfile.TemporaryDirectory(prefix="exgen_dist_support_") as td:
                artifact = generate_distributed_on_support_exercise(out_dir=Path(td), stem="live")
                png_path = artifact.png_path
                extracted = copy.deepcopy(artifact.extracted)
                meta = dict(extracted.get("meta") or {})
                meta["source"] = "exercise_generator_distributed_on_support"
                meta["skip_vision_normalize"] = True
                extracted["meta"] = meta
                with png_path.open("rb") as photo:
                    sent = await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo,
                        reply_markup=build_persistent_keyboard(),
                    )
                _track_sent_message(chat_id, sent)

                from intro.distributed_load import build_distributed_on_support_explanation_text
                explanation_text = build_distributed_on_support_explanation_text(extracted)
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("ראשי", callback_data="menu:main")],
                ])
                sent_msg = await context.bot.send_message(chat_id=chat_id, text=explanation_text, reply_markup=kb)
                _track_sent_message(chat_id, sent_msg)
        except Exception as exc:
            log.exception("Failed to generate distributed on support exercise chat=%s: %s", chat_id, exc)
            await _send_text_safe(context, chat_id, "לא הצלחתי להכין תרגיל כרגע. נסי/ה שוב בעוד רגע.")
            return

        if COUPON_ACCESS_ENABLED and user_id is not None:
            consume_practice_slot(int(user_id))
        return

    if topic_id == "practice_distributed":
        chat_id = query.message.chat_id if query.message else telegram_chat_id(update)
        user_id = telegram_user_id(update)
        await _delete_callback_message(query)
        try:
            from intro.distributed_load.generator import generate_exercise as generate_distributed_exercise
        except ImportError as exc:
            log.exception("distributed_load generator import failed: %s", exc)
            await _send_text_safe(context, chat_id, "מחולל התרגילים לעומס מפורס לא זמין כרגע.")
            return

        await cleanup_practice_chat(context, chat_id)
        await _leave_formulas_chat_if_needed(context, chat_id)
        begin_practice_chat_trail(chat_id)
        try:
            with tempfile.TemporaryDirectory(prefix="exgen_distributed_") as td:
                artifact = generate_distributed_exercise(out_dir=Path(td), stem="live")
                png_path = artifact.png_path
                extracted = copy.deepcopy(artifact.extracted)
                with png_path.open("rb") as photo:
                    sent = await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo,
                        reply_markup=build_persistent_keyboard(),
                    )
                _track_sent_message(chat_id, sent)

                beam = extracted.get("beam") if isinstance(extracted.get("beam"), dict) else {}
                loads = beam.get("loads") if isinstance(beam.get("loads"), list) else []
                dist_load = next((ld for ld in loads if isinstance(ld, dict) and ld.get("type") == "distributed"), None)
                if dist_load:
                    w = float(dist_load.get("w", 4.0))
                    x1 = float(dist_load.get("x1", 2.0))
                    x2 = float(dist_load.get("x2", 6.0))
                    dist = abs(x2 - x1)
                    mid_x = (x1 + x2) / 2.0
                    equivalent_force = w * dist
                    context.chat_data["distributed_practice_active"] = {
                        "w": w,
                        "dist": dist,
                        "equivalent_force": equivalent_force,
                        "mid_x": mid_x,
                        "awaiting_input": True,
                    }

                from intro.distributed_load import practice_question_prompt_hebrew
                sent_msg = await context.bot.send_message(
                    chat_id=chat_id,
                    text=practice_question_prompt_hebrew(),
                    reply_markup=build_persistent_keyboard(),
                )
                _track_sent_message(chat_id, sent_msg)
        except Exception as exc:
            log.exception("Failed to generate distributed practice exercise chat=%s: %s", chat_id, exc)
            await _send_text_safe(context, chat_id, "לא הצלחתי להכין תרגיל כרגע. נסי/ה שוב בעוד רגע.")
            return

        if COUPON_ACCESS_ENABLED and user_id is not None:
            consume_practice_slot(int(user_id))
        return

    if topic_id == "practice_inclined":
        chat_id = query.message.chat_id if query.message else telegram_chat_id(update)
        user_id = telegram_user_id(update)
        await _delete_callback_message(query)
        try:
            from intro.inclined_load import practice_prompt_hebrew
            from intro.inclined_load.generator import generate_exercise as generate_inclined_exercise
        except ImportError as exc:
            log.exception("inclined_load generator import failed: %s", exc)
            await _send_text_safe(context, chat_id, "מחולל התרגילים לעומס אלכסוני לא זמין כרגע.")
            return

        await cleanup_practice_chat(context, chat_id)
        await _leave_formulas_chat_if_needed(context, chat_id)
        begin_practice_chat_trail(chat_id)
        try:
            with tempfile.TemporaryDirectory(prefix="exgen_inclined_") as td:
                artifact = generate_inclined_exercise(out_dir=Path(td), stem="live")
                png_path = artifact.png_path
                extracted = copy.deepcopy(artifact.extracted)
                with png_path.open("rb") as photo:
                    sent = await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo,
                        reply_markup=build_persistent_keyboard(),
                    )
                _track_sent_message(chat_id, sent)

                beam = extracted.get("beam") if isinstance(extracted.get("beam"), dict) else {}
                loads = beam.get("loads") if isinstance(beam.get("loads"), list) else []
                inc_load = next((ld for ld in loads if isinstance(ld, dict) and ld.get("type") == "inclined"), None)
                if inc_load:
                    mag = float(inc_load.get("magnitude_ton", 10.0))
                    angle = float(inc_load.get("angle_deg", 30.0))
                    rad = math.radians(angle)
                    fy = mag * math.sin(rad)
                    fx = mag * math.cos(rad)
                    context.chat_data["inclined_practice_active"] = {
                        "magnitude_ton": mag,
                        "angle_deg": angle,
                        "fy": fy,
                        "fx": fx,
                        "awaiting_input": True,
                    }

                prompt_text = practice_prompt_hebrew() if practice_prompt_hebrew else (
                    "בוא נראה שהבנת את זה.\n"
                    "תשלח לי את הפתרונות כמספרים, עם פסיק באמצע לא משנה הסדר.\n"
                    "(לדגומא: 4.87,5.65)"
                )
                sent_msg = await context.bot.send_message(
                    chat_id=chat_id,
                    text=prompt_text,
                    reply_markup=build_persistent_keyboard(),
                )
                _track_sent_message(chat_id, sent_msg)
        except Exception as exc:
            log.exception("Failed to generate inclined practice exercise chat=%s: %s", chat_id, exc)
            await _send_text_safe(context, chat_id, "לא הצלחתי להכין תרגיל כרגע. נסי/ה שוב בעוד רגע.")
            return

        if COUPON_ACCESS_ENABLED and user_id is not None:
            consume_practice_slot(int(user_id))
        return

    if topic_id == "distributed_try_again":
        chat_id = query.message.chat_id if query.message else telegram_chat_id(update)
        await _delete_callback_message(query)
        if "distributed_practice_active" in context.chat_data:
            context.chat_data["distributed_practice_active"]["awaiting_input"] = True
        try:
            from intro.distributed_load import try_again_prompt_hebrew
            prompt_text = try_again_prompt_hebrew()
        except ImportError:
            prompt_text = (
                "בוא ננסה שוב.\n"
                "תשלח לי את הפתרונות כמספרים, עם פסיק באמצע לא משנה הסדר.\n"
                "(לדגומא: 4.87,5.65)"
            )
        sent = await context.bot.send_message(
            chat_id=chat_id,
            text=prompt_text,
            reply_markup=build_persistent_keyboard(),
        )
        _track_sent_message(chat_id, sent)
        return

    if topic_id == "distributed_show_solution":
        chat_id = query.message.chat_id if query.message else telegram_chat_id(update)
        await _delete_callback_message(query)
        active_dist = context.chat_data.pop("distributed_practice_active", None)
        if active_dist:
            w = active_dist["w"]
            dist = active_dist["dist"]
            req_force = active_dist["equivalent_force"]
            req_dist = active_dist.get("mid_x", 0.0)

            force_str = f"{int(req_force)}" if req_force.is_integer() else f"{req_force:g}"
            dist_str = f"{int(req_dist)}" if req_dist.is_integer() else f"{req_dist:g}"

            sol_text = (
                f"הפתרונות של העומס המפורס בתרגיל:\n"
                f"\n"
                f"הכח השקול: {force_str}t\n"
                f"המרחק מצד שמאל: {dist_str}m"
            )
        else:
            sol_text = "לא נמצאו נתוני תרגיל פעיל."

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("תרגול", callback_data="intro:practice_distributed")],
            [InlineKeyboardButton("ראשי", callback_data="menu:main")],
        ])
        sent = await context.bot.send_message(
            chat_id=chat_id,
            text=sol_text,
            reply_markup=kb,
        )
        _track_sent_message(chat_id, sent)
        return

    if topic_id == "inclined_try_again":
        chat_id = query.message.chat_id if query.message else telegram_chat_id(update)
        await _delete_callback_message(query)
        if "inclined_practice_active" in context.chat_data:
            context.chat_data["inclined_practice_active"]["awaiting_input"] = True
        try:
            from intro.inclined_load import try_again_prompt_hebrew
            prompt_text = try_again_prompt_hebrew()
        except ImportError:
            prompt_text = (
                "בוא ננסה שוב.\n"
                "תשלח לי את הפתרונות כמספרים, עם פסיק באמצע לא משנה הסדר.\n"
                "(לדגומא: 4.87,5.65)"
            )
        sent = await context.bot.send_message(
            chat_id=chat_id,
            text=prompt_text,
            reply_markup=build_persistent_keyboard(),
        )
        _track_sent_message(chat_id, sent)
        return

    if topic_id == "inclined_show_solution":
        chat_id = query.message.chat_id if query.message else telegram_chat_id(update)
        await _delete_callback_message(query)
        active_inclined = context.chat_data.pop("inclined_practice_active", None)
        if active_inclined:
            mag = active_inclined["magnitude_ton"]
            angle = active_inclined["angle_deg"]
            fy = active_inclined["fy"]
            fx = active_inclined["fx"]

            mag_str = f"{int(mag)}" if mag.is_integer() else f"{mag:.2f}"
            angle_str = f"{int(angle)}" if angle.is_integer() else f"{angle:.1f}"

            fy_rounded = round(fy, 2)
            fx_rounded = round(fx, 2)
            fy_str = f"{int(fy_rounded)}" if fy_rounded.is_integer() else f"{fy_rounded:g}"
            fx_str = f"{int(fx_rounded)}" if fx_rounded.is_integer() else f"{fx_rounded:g}"

            sol_text = (
                f"הפתרונות של העומס האלכסוני בתרגיל:\n"
                f"\n"
                f"האנכי: {mag_str}sin({angle_str}) = {fy_str}t\n"
                f"הצירי: {mag_str}cos({angle_str}) = {fx_str}t"
            )
        else:
            sol_text = "לא נמצאו נתוני תרגיל פעיל."

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("תרגול", callback_data="intro:practice_inclined")],
            [InlineKeyboardButton("ראשי", callback_data="menu:main")],
        ])
        sent = await context.bot.send_message(
            chat_id=chat_id,
            text=sol_text,
            reply_markup=kb,
        )
        _track_sent_message(chat_id, sent)
        return

    if topic_id == "main":
        if query.message and build_opening_keyboard is not None and opening_message_hebrew is not None:
            try:
                await query.message.edit_text(
                    opening_message_hebrew(),
                    reply_markup=build_opening_keyboard(),
                )
            except BadRequest:
                chat_id = query.message.chat_id if query.message else telegram_chat_id(update)
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=opening_message_hebrew(),
                    reply_markup=build_opening_keyboard(),
                )
        return

    body = intro_topic_body_hebrew(topic_id) if intro_topic_body_hebrew else None
    if not body:
        return
    chat_id = query.message.chat_id if query.message else telegram_chat_id(update)
    await _delete_callback_message(query)
    await context.bot.send_message(
        chat_id=chat_id,
        text=body,
        reply_markup=build_persistent_keyboard(),
    )

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
    leave_session = get_solution_session(chat_id)
    if has_practice_chat_trail(chat_id) or (
        leave_session is not None and leave_session.from_practice
    ):
        await cleanup_practice_chat(context, chat_id)

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
        await cleanup_formulas_chat(context, chat_id)
        await _send_main_action_menu(context, chat_id)
        return

    if action == "topic":
        topic = get_topic(payload)
        if topic is None:
            await query.answer("נושא לא נמצא.", show_alert=True)
            return
        await query.answer()
        await _delete_callback_message(query)
        if not has_formulas_chat_trail(chat_id):
            begin_formulas_chat_trail(chat_id)
        image_path = topic.image_path()
        followup = build_topic_followup_keyboard()
        if image_path is not None:
            try:
                with image_path.open("rb") as fh:
                    sent = await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=fh,
                        caption=topic_image_caption_hebrew(topic),
                        reply_markup=followup,
                    )
                append_formulas_chat_message_id(chat_id, getattr(sent, "message_id", None))
            except Exception:
                log.exception("Failed sending formula image for %s", topic.topic_id)
                sent = await context.bot.send_message(
                    chat_id=chat_id,
                    text=topic_pending_caption_hebrew(topic),
                    reply_markup=followup,
                    parse_mode="Markdown",
                )
                append_formulas_chat_message_id(chat_id, getattr(sent, "message_id", None))
        else:
            sent = await context.bot.send_message(
                chat_id=chat_id,
                text=topic_pending_caption_hebrew(topic),
                reply_markup=followup,
                parse_mode="Markdown",
            )
            append_formulas_chat_message_id(chat_id, getattr(sent, "message_id", None))
        return

    await query.answer()



async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    chat_id = telegram_chat_id(update)
    reset_user_session(chat_id)
    await update.message.reply_text(
        "המצב אופס. שלח/י תמונה חדשה של התרגיל.",
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
    await _leave_formulas_chat_if_needed(context, chat_id)
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
    text = quota_status_for_user(telegram_user_id(update))
    await update.message.reply_text(
        text,
        reply_markup=build_persistent_keyboard(),
    )


async def cmd_formulas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """פקודת /formulas — תפריט נוסחאות (מופיע גם בתפריט הפקודות של טלגרם)."""
    if not update.message:
        return
    chat_id = telegram_chat_id(update)
    await cleanup_formulas_chat(context, chat_id)
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
    del extracted, edit, errors  # הודעת הטיוטה היא הסבר קבוע + אישור
    text = DRAFT_INSTRUCTION_TEXT
    keyboard = build_draft_approve_keyboard()
    try:
        await context.bot.edit_message_text(
            text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=keyboard,
        )
    except BadRequest as exc:
        err = str(exc).lower()
        if "message is not modified" in err:
            return
        raise


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
        await _send_text_safe(context, chat_id, f"{errors[0]}")
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
    ok = await send_draft_preview(
        context, chat_id, extracted, reply_to_message=message
    )
    if ok:
        return
    keyboard = build_draft_approve_keyboard()
    sent = await message.reply_text(
        DRAFT_INSTRUCTION_TEXT, reply_markup=keyboard
    )
    set_draft_pending(
        chat_id,
        extracted,
        DRAFT_INSTRUCTION_TEXT,
        message_id=sent.message_id,
        clear_edit=True,
    )
    register_draft_cleanup_id(chat_id, sent.message_id)


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
        if COUPON_ACCESS_ENABLED:
            access = consume_solve_slot(telegram_user_id(update))
            if access.status != ImageAccessStatus.OK:
                await _send_text_safe(
                    context,
                    chat_id,
                    image_access_reply_hebrew(access),
                    reply_markup=_purchase_cta_markup(access),
                )
                return
        # אם נשלחה הודעת שגיאה קודמת אחרי "חשב" — מוחקים אותה לפני ניסיון חישוב נוסף.
        prev_err_mid = get_draft_error_message_id(chat_id)
        if prev_err_mid is not None:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=prev_err_mid)
            except BadRequest:
                pass
            set_draft_error_message_id(chat_id, None)
        # צילום message_ids לפני approve — תמונת המקור לא נכללת
        cleanup_ids = get_draft_cleanup_message_ids(chat_id, keep_user_source=True)
        if msg_id is not None:
            cleanup_ids.append(int(msg_id))
        if query.message is not None:
            cleanup_ids.append(int(query.message.message_id))
        cleanup_ids = list(dict.fromkeys(cleanup_ids))
        reply, solved, extracted = approve_and_solve(chat_id, extracted)
        if (solved or {}).get("result"):
            # קודם מחיקת כל שיחת הטיוטה (חוץ מתמונת המשתמש), אחר כך פתרונות
            await wipe_draft_conversation(
                context, chat_id, message_ids=cleanup_ids
            )
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

    # מקלדת הטיוטה החדשה היא אישור בלבד — מתעלמים משאר d:* ישנים.
    await query.answer()
    return


async def _deliver_generated_exercise(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    *,
    user_id: int | None = None,
) -> None:
    """מייצר תרגיל חדש מהמחולל, שולח PNG, ומציע מצב פתרון כמו מאגר."""
    if COUPON_ACCESS_ENABLED and user_id is not None:
        access = check_practice_feature_access(int(user_id))
        if access.status != ImageAccessStatus.OK:
            await cleanup_practice_chat(context, chat_id)
            await _leave_formulas_chat_if_needed(context, chat_id)
            await _send_text_safe(
                context,
                chat_id,
                image_access_reply_hebrew(access),
                reply_markup=_purchase_cta_markup(access),
            )
            return
    try:
        from exercise_generator.pipeline import generate_exercise
    except ImportError as exc:
        log.exception("exercise_generator import failed: %s", exc)
        await _send_text_safe(
            context,
            chat_id,
            "מחולל התרגילים לא זמין כרגע. נסי/ה שוב מאוחר יותר.",
        )
        return

    await cleanup_practice_chat(context, chat_id)
    await _leave_formulas_chat_if_needed(context, chat_id)
    begin_practice_chat_trail(chat_id)
    try:
        with tempfile.TemporaryDirectory(prefix="exgen_") as td:
            artifact = generate_exercise(out_dir=Path(td), stem="live")
            png_path = artifact.png_path
            extracted = copy.deepcopy(artifact.extracted)
            meta = dict(extracted.get("meta") or {})
            meta["source"] = "exercise_generator"
            meta["skip_vision_normalize"] = True
            extracted["meta"] = meta
            with png_path.open("rb") as photo:
                sent = await context.bot.send_photo(chat_id=chat_id, photo=photo)
            _track_sent_message(chat_id, sent)
    except Exception as exc:
        log.exception("Failed to generate/send exercise chat=%s: %s", chat_id, exc)
        await _send_text_safe(
            context,
            chat_id,
            "לא הצלחתי להכין תרגיל כרגע. נסי/ה שוב בעוד רגע.",
        )
        return

    if COUPON_ACCESS_ENABLED and user_id is not None:
        consume_practice_slot(int(user_id))

    set_pending_bank_exercise(chat_id, _GENERATED_EXERCISE_ID, extracted)
    sent = await context.bot.send_message(
        chat_id=chat_id,
        text="איך תרצה/י לפתור את התרגיל?",
        reply_markup=build_bank_solve_mode_keyboard(),
    )
    _track_sent_message(chat_id, sent)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    chat_id = telegram_chat_id(update)
    text = update.message.text.strip()

    chat_data = getattr(context, "chat_data", None)
    active_inclined = chat_data.get("inclined_practice_active") if isinstance(chat_data, dict) else None
    active_inclined = chat_data.get("inclined_practice_active") if isinstance(chat_data, dict) else None
    if isinstance(active_inclined, dict):
        if text in (
            _PERSISTENT_MAIN_LABEL,
            _START_INTRO_LABEL,
            _PERSISTENT_FORMULAS_LABEL,
            _PERSISTENT_ASSISTANT_LABEL,
            _PERSISTENT_COUPON_LABEL,
            _PERSISTENT_QUOTA_LABEL,
            _PERSISTENT_BUG_REPORT_LABEL,
        ):
            context.chat_data.pop("inclined_practice_active", None)
        else:
            _track_sent_message(chat_id, update.message)
            parts = text.replace(" ", "").split(",")
            u1, u2 = None, None
            if len(parts) == 2:
                try:
                    u1 = float(parts[0])
                    u2 = float(parts[1])
                except ValueError:
                    u1, u2 = None, None

            if u1 is not None and u2 is not None:
                fy = active_inclined["fy"]
                fx = active_inclined["fx"]

                is_correct = (
                    (abs(u1 - fy) < 0.15 and abs(u2 - fx) < 0.15)
                    or (abs(u1 - fx) < 0.15 and abs(u2 - fy) < 0.15)
                )

                if is_correct:
                    context.chat_data.pop("inclined_practice_active", None)
                    kb = InlineKeyboardMarkup([
                        [InlineKeyboardButton("תרגול", callback_data="intro:practice_inclined")],
                        [InlineKeyboardButton("ראשי", callback_data="menu:main")],
                    ])
                    sent = await context.bot.send_message(
                        chat_id=chat_id,
                        text="צדקת! התוצאות שהבאת נכונים.\nאיך תרצה להמשיך?",
                        reply_markup=kb,
                    )
                    _track_sent_message(chat_id, sent)
                    return
                else:
                    active_inclined["awaiting_input"] = False
                    mag = active_inclined.get("magnitude_ton", 10.0)
                    angle = active_inclined.get("angle_deg", 30.0)
                    mag_str = f"{int(mag)}" if mag.is_integer() else f"{mag:.2f}"
                    angle_str = f"{int(angle)}" if angle.is_integer() else f"{angle:.1f}"

                    err_text = (
                        "נראה שטעית איפשהו, אולי לא הכנסת את המספרים הנכונים למחשבון.\n"
                        "זה צריך להיראות ככה:\n"
                        f"אנכי - {mag_str}sin({angle_str})\n"
                        f"צירי - {mag_str}cos({angle_str})\n"
                        "תרצה לנסות שוב או שאני יישלח את הפתרונות?"
                    )
                    kb = InlineKeyboardMarkup([
                        [InlineKeyboardButton("אנסה שוב", callback_data="intro:inclined_try_again")],
                        [InlineKeyboardButton("הצג פתרון", callback_data="intro:inclined_show_solution")],
                    ])
                    sent = await context.bot.send_message(
                        chat_id=chat_id,
                        text=err_text,
                        reply_markup=kb,
                    )
                    _track_sent_message(chat_id, sent)
                    return
            else:
                context.chat_data["inclined_practice_active"]["awaiting_input"] = True
                try:
                    from intro.inclined_load import invalid_format_prompt_hebrew
                    format_err_text = invalid_format_prompt_hebrew()
                except ImportError:
                    format_err_text = (
                        "בשביל שאצליח להבין את התשובות שרשמת, זה צריך להיראות בנוסח הבא - מספר,מספר.\n"
                        "לדוגמא - 4.67,5"
                    )
                sent = await context.bot.send_message(
                    chat_id=chat_id,
                    text=format_err_text,
                    reply_markup=build_persistent_keyboard(),
                )
                _track_sent_message(chat_id, sent)
                return

    active_dist = chat_data.get("distributed_practice_active") if isinstance(chat_data, dict) else None
    if isinstance(active_dist, dict):
        if text in (
            _PERSISTENT_MAIN_LABEL,
            _START_INTRO_LABEL,
            _PERSISTENT_FORMULAS_LABEL,
            _PERSISTENT_ASSISTANT_LABEL,
            _PERSISTENT_COUPON_LABEL,
            _PERSISTENT_QUOTA_LABEL,
            _PERSISTENT_BUG_REPORT_LABEL,
        ):
            context.chat_data.pop("distributed_practice_active", None)
        else:
            _track_sent_message(chat_id, update.message)
            parts = text.replace(" ", "").split(",")
            u1, u2 = None, None
            if len(parts) == 2:
                try:
                    u1 = float(parts[0])
                    u2 = float(parts[1])
                except ValueError:
                    u1, u2 = None, None

            if u1 is not None and u2 is not None:
                req_force = active_dist["equivalent_force"]
                req_dist = active_dist.get("mid_x", 0.0)

                is_correct = (
                    (abs(u1 - req_force) < 0.15 and abs(u2 - req_dist) < 0.15)
                    or (abs(u1 - req_dist) < 0.15 and abs(u2 - req_force) < 0.15)
                )

                if is_correct:
                    context.chat_data.pop("distributed_practice_active", None)
                    kb = InlineKeyboardMarkup([
                        [InlineKeyboardButton("תרגול", callback_data="intro:practice_distributed")],
                        [InlineKeyboardButton("ראשי", callback_data="menu:main")],
                    ])
                    sent = await context.bot.send_message(
                        chat_id=chat_id,
                        text="צדקת! התוצאות שהבאת נכונים.\nאיך תרצה להמשיך?",
                        reply_markup=kb,
                    )
                    _track_sent_message(chat_id, sent)
                    return
                else:
                    active_dist["awaiting_input"] = False
                    w = active_dist["w"]
                    dist = active_dist["dist"]
                    w_str = f"{int(w)}" if w.is_integer() else f"{w:.2f}"
                    dist_str = f"{int(dist)}" if dist.is_integer() else f"{dist:.2f}"

                    err_text = (
                        "נראה שטעית איפשהו, אולי לא הכנסת את המספרים הנכונים למחשבון.\n"
                        "זה צריך להיראות ככה:\n"
                        f"כח שקול - {w_str}*{dist_str}\n"
                        f"מרחק מצד שמאל - המרחק מ-0 עד אמצע העומס\n"
                        "תרצה לנסות שוב או שאני יישלח את הפתרונות?"
                    )
                    kb = InlineKeyboardMarkup([
                        [InlineKeyboardButton("אנסה שוב", callback_data="intro:distributed_try_again")],
                        [InlineKeyboardButton("הצג פתרון", callback_data="intro:distributed_show_solution")],
                    ])
                    sent = await context.bot.send_message(
                        chat_id=chat_id,
                        text=err_text,
                        reply_markup=kb,
                    )
                    _track_sent_message(chat_id, sent)
                    return
            else:
                context.chat_data["distributed_practice_active"]["awaiting_input"] = True
                try:
                    from intro.distributed_load import invalid_format_prompt_hebrew
                    format_err_text = invalid_format_prompt_hebrew()
                except ImportError:
                    format_err_text = (
                        "בשביל שאצליח להבין את התשובות שרשמת, זה צריך להיראות בנוסח הבא - מספר,מספר.\n"
                        "לדוגמא - 4.67,5"
                    )
                sent = await context.bot.send_message(
                    chat_id=chat_id,
                    text=format_err_text,
                    reply_markup=build_persistent_keyboard(),
                )
                _track_sent_message(chat_id, sent)
                return

    if text.upper() == _GENERATED_EXERCISE_TRIGGER:
        await _deliver_generated_exercise(
            context,
            chat_id,
            user_id=telegram_user_id(update),
        )
        return

    if text == _PERSISTENT_ASSISTANT_LABEL:
        leave_session = get_solution_session(chat_id)
        if has_practice_chat_trail(chat_id) or (
            leave_session is not None and leave_session.from_practice
        ):
            await cleanup_practice_chat(context, chat_id)
        await _leave_formulas_chat_if_needed(context, chat_id)
        if COUPON_ACCESS_ENABLED:
            access = check_solve_access(telegram_user_id(update))
            if access.status != ImageAccessStatus.OK:
                await _reply_text_safe(
                    update.message,
                    image_access_reply_hebrew(access),
                    reply_markup=_purchase_cta_markup(access),
                )
                return
        prompt = select_solve_mode(chat_id, SolveMode.ASSISTANT)
        await _reply_text_safe(update.message, prompt)
        return

    if text == _PERSISTENT_MAIN_LABEL:
        through_mid = getattr(update.message, "message_id", None)
        await wipe_chat_after_anchor(
            context,
            chat_id,
            through_message_id=int(through_mid) if through_mid is not None else None,
        )
        await _send_main_action_menu(context, chat_id)
        return

    if text == _START_INTRO_LABEL:
        leave_session = get_solution_session(chat_id)
        if has_practice_chat_trail(chat_id) or (
            leave_session is not None and leave_session.from_practice
        ):
            await cleanup_practice_chat(context, chat_id)
        await _leave_formulas_chat_if_needed(context, chat_id)
        await _send_intro_opening(context, chat_id)
        return

    if text == _PERSISTENT_FORMULAS_LABEL:
        leave_session = get_solution_session(chat_id)
        if has_practice_chat_trail(chat_id) or (
            leave_session is not None and leave_session.from_practice
        ):
            await cleanup_practice_chat(context, chat_id)
        await cleanup_formulas_chat(context, chat_id)
        await _send_formulas_menu(
            context,
            chat_id,
            user_id=telegram_user_id(update),
            message=update.message,
        )
        return
    if text == _PERSISTENT_BUG_REPORT_LABEL:
        await _leave_formulas_chat_if_needed(context, chat_id)
        await _prompt_bug_report(update.message)
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
                "תודה! הדיווח נשלח לצוות. נטפל בזה בהקדם.",
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
        leave_session = get_solution_session(chat_id)
        if has_practice_chat_trail(chat_id) or (
            leave_session is not None and leave_session.from_practice
        ):
            await cleanup_practice_chat(context, chat_id)
        await _leave_formulas_chat_if_needed(context, chat_id)
        await cmd_coupon(update, context)
        return
    if text == _PERSISTENT_QUOTA_LABEL:
        await _leave_formulas_chat_if_needed(context, chat_id)
        await cmd_quota(update, context)
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

    if is_draft_pending(chat_id):
        if is_approval_message(text):
            # לפני approve — ids למחיקה (בלי תמונת מקור של המשתמש)
            ref = get_draft_message_ref(chat_id)
            msg_id = ref[1] if ref else None
            cleanup_ids = get_draft_cleanup_message_ids(
                chat_id, keep_user_source=True
            )
            if msg_id is not None:
                cleanup_ids.append(int(msg_id))
            if update.message is not None:
                cleanup_ids.append(int(update.message.message_id))
            cleanup_ids = list(dict.fromkeys(cleanup_ids))
            draft_result = handle_draft_text(chat_id, text)
            if draft_result.handled and draft_result.approved:
                if COUPON_ACCESS_ENABLED:
                    access = consume_solve_slot(telegram_user_id(update))
                    if access.status != ImageAccessStatus.OK:
                        await _reply_text_safe(
                            update.message,
                            image_access_reply_hebrew(access),
                            reply_markup=_purchase_cta_markup(access),
                        )
                        return
                extracted = draft_result.extracted or get_stored_vision_extracted(chat_id) or {}
                if (draft_result.solved or {}).get("result"):
                    await wipe_draft_conversation(
                        context, chat_id, message_ids=cleanup_ids
                    )
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
            return

        extracted = get_stored_vision_extracted(chat_id) or {}
        user_mid = int(update.message.message_id) if update.message else None
        register_draft_cleanup_id(chat_id, user_mid)
        updated, errors = apply_nl_draft_edit(extracted, text)
        if errors or updated is None:
            err_msg = await _reply_text_safe(
                update.message,
                (errors[0] if errors else "לא הצלחתי לעדכן את הטיוטה."),
            )
            if err_msg is not None:
                register_draft_cleanup_id(chat_id, getattr(err_msg, "message_id", None))
            return
        persist_draft(chat_id, updated)
        ok, render_err = await refresh_draft_after_correction(
            context,
            chat_id,
            updated,
            user_message_id=user_mid,
        )
        if not ok:
            err_msg = await _reply_text_safe(
                update.message,
                render_err or "הטיוטה עודכנה, אבל שליחת השרטוט נכשלה.",
            )
            if err_msg is not None:
                register_draft_cleanup_id(chat_id, getattr(err_msg, "message_id", None))
            return
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
                "• שלח כקובץ לאיכות טובה יותר\n"
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

    leave_session = get_solution_session(chat_id)
    if has_practice_chat_trail(chat_id) or (
        leave_session is not None and leave_session.from_practice
    ):
        await cleanup_practice_chat(context, chat_id)
    await _leave_formulas_chat_if_needed(context, chat_id)

    pending_mode = consume_pending_solve_mode(chat_id)
    solve_mode = pending_mode or SolveMode.NOTEBOOK
    # הוספת תרגיל למאגר לא צורכת מכסה — לא שייכת לפתרון תרגיל בפועל.
    is_bank_submission = pending_mode == SolveMode.ADD_TO_BANK

    if COUPON_ACCESS_ENABLED and not is_bank_submission:
        user_id = telegram_user_id(update)
        access = check_solve_access(user_id)
        if access.status != ImageAccessStatus.OK:
            log.info(
                "Image blocked user=%s status=%s",
                user_id,
                access.status.value,
            )
            reply_markup = _purchase_cta_markup(access)
            await _reply_text_safe(
                update.message,
                image_access_reply_hebrew(access),
                reply_markup=reply_markup,
            )
            if isinstance(reply_markup, InlineKeyboardMarkup):
                await _reply_text_safe(
                    update.message,
                    "התפריט למטה זמין תמיד",
                )
            return
        log.info(
            "Image allowed user=%s phase=%s feature=%s",
            user_id,
            getattr(access.phase, "value", None),
            access.feature,
        )

    begin_image_session(chat_id, solve_mode=solve_mode)
    if DRAFT_APPROVAL_MODE and not is_bank_submission:
        set_draft_source_user_message_id(chat_id, msg_id)

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

