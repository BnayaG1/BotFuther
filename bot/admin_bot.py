# -*- coding: utf-8 -*-
"""בוט אדמין — בקרה, שימוש, משתמשים ויצירת קופונים."""
from __future__ import annotations

import logging

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.ext import ContextTypes

from bot.admin_usage import (
    USERS_PAGE_SIZE,
    format_overview_text,
    format_user_card_text,
    format_users_page_text,
    list_users_page,
)
from bot.config import ADMIN_USER_IDS, get_admin_user_ids
from bot.generate_coupons import generate_coupon_codes
from bot.purchase import ADMIN_PACKAGE_CATALOG, get_package


log = logging.getLogger("beam_admin")

_UNAUTHORIZED_TEXT = "גישה נדחתה."
_NO_PREVIEW = LinkPreviewOptions(is_disabled=True)

ADMIN_KB_ENGINEER = "למהנדס"
ADMIN_KB_OVERVIEW = "סקירה"
ADMIN_KB_USERS = "משתמשים"
ADMIN_KB_COUPONS = "קופונים"


def _is_admin(update: Update) -> bool:
    user = update.effective_user
    if user is None:
        return False
    admin_ids = ADMIN_USER_IDS if ADMIN_USER_IDS else get_admin_user_ids()
    if not admin_ids:
        return False
    return int(user.id) in admin_ids


def build_admin_persistent_reply_keyboard() -> ReplyKeyboardMarkup:
    buttons = [
        [ADMIN_KB_ENGINEER, ADMIN_KB_OVERVIEW],
        [ADMIN_KB_USERS, ADMIN_KB_COUPONS],
    ]
    return ReplyKeyboardMarkup(
        buttons,
        resize_keyboard=True,
        is_persistent=True,
    )


def build_admin_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            f"{pkg.label_hebrew()}",
            callback_data=f"admin:pick:{pkg.package_id}",
        )
        for pkg in ADMIN_PACKAGE_CATALOG
    ]
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(rows)


def build_quantity_keyboard(package_id: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("קוד 1", callback_data=f"admin:gen:{package_id}:1"),
            InlineKeyboardButton("2 קודים", callback_data=f"admin:gen:{package_id}:2"),
            InlineKeyboardButton("5 קודים", callback_data=f"admin:gen:{package_id}:5"),
            InlineKeyboardButton("10 קודים", callback_data=f"admin:gen:{package_id}:10"),
        ],
        [
            InlineKeyboardButton("הזן כמות", callback_data=f"admin:custom:{package_id}"),
            InlineKeyboardButton("ביטול", callback_data="admin:cancel"),
        ],
    ]
    return InlineKeyboardMarkup(rows)


def build_users_page_keyboard(items: list[dict], total: int, offset: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for item in items:
        uid = int(item["user_id"])
        uname = item.get("username")
        name = f"@{uname}" if uname else str(uid)
        short = (item.get("access_short") or "").strip()
        label = f"{name} · {short}" if short else name
        if len(label) > 40:
            label = label[:39] + "…"
        rows.append(
            [InlineKeyboardButton(label, callback_data=f"admin:user:{uid}:{offset}")]
        )
    nav: list[InlineKeyboardButton] = []
    if offset > 0:
        prev_off = max(0, offset - USERS_PAGE_SIZE)
        nav.append(InlineKeyboardButton("הקודם", callback_data=f"admin:users:{prev_off}"))
    if offset + len(items) < total:
        next_off = offset + USERS_PAGE_SIZE
        nav.append(InlineKeyboardButton("הבא", callback_data=f"admin:users:{next_off}"))
    if nav:
        rows.append(nav)
    return InlineKeyboardMarkup(rows)


def build_user_card_keyboard(offset: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("חזרה לרשימה", callback_data=f"admin:users:{max(0, int(offset))}")]]
    )


def build_overview_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("רענון", callback_data="admin:overview"),
                InlineKeyboardButton("משתמשים", callback_data="admin:users:0"),
            ]
        ]
    )


async def _admin_show(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup=None,
) -> None:
    query = update.callback_query
    if query and query.message:
        try:
            await query.message.edit_text(
                text,
                reply_markup=reply_markup,
                parse_mode="HTML",
                link_preview_options=_NO_PREVIEW,
            )
            return
        except Exception:
            pass
        try:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode="HTML",
                link_preview_options=_NO_PREVIEW,
            )
            return
        except Exception:
            pass
    if update.message:
        await update.message.reply_text(
            text,
            reply_markup=reply_markup,
            parse_mode="HTML",
            link_preview_options=_NO_PREVIEW,
        )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not _is_admin(update):
        await update.message.reply_text(_UNAUTHORIZED_TEXT)
        return
    await update.message.reply_text(
        "\u2060",
        reply_markup=build_admin_persistent_reply_keyboard(),
    )


async def cmd_overview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update):
        if update.callback_query:
            await update.callback_query.answer(_UNAUTHORIZED_TEXT, show_alert=True)
        elif update.message:
            await update.message.reply_text(_UNAUTHORIZED_TEXT)
        return
    if update.callback_query:
        await update.callback_query.answer()
    await _admin_show(update, context, format_overview_text(), build_overview_keyboard())


async def cmd_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update):
        if update.callback_query:
            await update.callback_query.answer(_UNAUTHORIZED_TEXT, show_alert=True)
        elif update.message:
            await update.message.reply_text(_UNAUTHORIZED_TEXT)
        return
    offset = 0
    query = update.callback_query
    if query and query.data and query.data.startswith("admin:users:"):
        try:
            offset = max(0, int(query.data.split(":")[2]))
        except (IndexError, ValueError):
            offset = 0
    items, total, summary = list_users_page(offset=offset, limit=USERS_PAGE_SIZE)
    if query:
        await query.answer()
    await _admin_show(
        update,
        context,
        format_users_page_text(items, total, offset, summary),
        build_users_page_keyboard(items, total, offset) if items else None,
    )


async def cmd_coupons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not _is_admin(update):
        await update.message.reply_text(_UNAUTHORIZED_TEXT)
        return
    await update.message.reply_text(
        "בחר חבילה ליצירת קוד קופון:",
        reply_markup=build_admin_menu_keyboard(),
    )


async def cmd_user_card(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    offset: int = 0,
) -> None:
    if not _is_admin(update):
        if update.callback_query:
            await update.callback_query.answer(_UNAUTHORIZED_TEXT, show_alert=True)
        return
    text = format_user_card_text(int(user_id))
    if text is None:
        if update.callback_query:
            await update.callback_query.answer("משתמש לא נמצא.", show_alert=True)
        elif update.message:
            await update.message.reply_text(
                f"משתמש <code>{user_id}</code> לא נמצא במערכת.",
                parse_mode="HTML",
            )
        return
    if update.callback_query:
        await update.callback_query.answer()
    await _admin_show(update, context, text, build_user_card_keyboard(offset))


async def on_admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    if not _is_admin(update):
        await update.message.reply_text(_UNAUTHORIZED_TEXT)
        return

    text = update.message.text.strip()
    if text == ADMIN_KB_OVERVIEW:
        await cmd_overview(update, context)
        return
    if text in (ADMIN_KB_USERS, "רשימת משתמשים") or ("משתמשים" in text and len(text) < 20):
        await cmd_users(update, context)
        return
    if text == ADMIN_KB_COUPONS or "קופון" in text or "יצירת" in text:
        await cmd_coupons(update, context)
        return

    pending_pkg_id = context.user_data.get("admin_awaiting_custom_qty")
    if pending_pkg_id:
        if text.isdigit() and 1 <= int(text) <= 500:
            count = int(text)
            pkg = get_package(pending_pkg_id)
            context.user_data.pop("admin_awaiting_custom_qty", None)
            if not pkg:
                await update.message.reply_text("חבילה לא נמצאה.")
                return
            codes = generate_coupon_codes(
                count=count,
                daily_quota=pkg.daily_quota,
                period_days=pkg.period_days,
            )
            code_text = "\n".join(f"<code>{c}</code>" for c in codes)
            await update.message.reply_text(code_text, parse_mode="HTML")
            return
        await update.message.reply_text("אנא הכנס מספר תקין בין 1 ל-500.")
        return

    for pkg in ADMIN_PACKAGE_CATALOG:
        if text == pkg.label_hebrew() or text == pkg.label_admin_keyboard() or pkg.package_id in text:
            await update.message.reply_text(
                f"נבחרה חבילה: <b>{pkg.label_hebrew()}</b>\nכמה קודים תרצה לייצר?",
                reply_markup=build_quantity_keyboard(pkg.package_id),
                parse_mode="HTML",
            )
            return

    await update.message.reply_text(
        "\u2060",
        reply_markup=build_admin_persistent_reply_keyboard(),
    )


async def cmd_dbpath(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """פקודת אבחון — מציגה את נתיב ה-DB הפעיל."""
    if not update.message:
        return
    if not _is_admin(update):
        await update.message.reply_text(_UNAUTHORIZED_TEXT)
        return
    from bot.access import DB_PATH
    import sqlite3
    try:
        conn = sqlite3.connect(str(DB_PATH))
        count = conn.execute("SELECT COUNT(*) FROM user_first_seen").fetchone()[0]
        conn.close()
        await update.message.reply_text(
            f"DB path: <code>{DB_PATH}</code>\nמשתמשים בטבלה: <b>{count}</b>",
            parse_mode="HTML",
        )
    except Exception as e:
        await update.message.reply_text(f"שגיאה: <code>{e}</code>\nנתיב: <code>{DB_PATH}</code>", parse_mode="HTML")


async def cmd_user_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not _is_admin(update):
        await update.message.reply_text(_UNAUTHORIZED_TEXT)
        return
    args = context.args
    if not args:
        await update.message.reply_text("שימוש: /user <USER_ID>")
        return
    try:
        target_uid = int(args[0])
    except ValueError:
        await update.message.reply_text("מזהה משתמש לא תקין.")
        return

    text = format_user_card_text(target_uid)
    if not text:
        await update.message.reply_text(
            f"משתמש <code>{target_uid}</code> לא נמצא במערכת.",
            parse_mode="HTML",
        )
        return
    await update.message.reply_text(text, parse_mode="HTML")


async def on_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return
    if not _is_admin(update):
        await query.answer(_UNAUTHORIZED_TEXT, show_alert=True)
        return

    data = query.data
    if data == "admin:cancel":
        context.user_data.pop("admin_awaiting_custom_qty", None)
        await query.answer()
        if query.message:
            user_msg = query.message.reply_to_message
            try:
                await query.message.delete()
            except Exception:
                pass
            if user_msg:
                try:
                    await user_msg.delete()
                except Exception:
                    pass
        return

    if data == "admin:overview":
        await cmd_overview(update, context)
        return

    if data.startswith("admin:users:"):
        await cmd_users(update, context)
        return

    if data.startswith("admin:user:"):
        parts = data.split(":")
        if len(parts) < 3:
            await query.answer()
            return
        try:
            target_uid = int(parts[2])
            offset = int(parts[3]) if len(parts) > 3 else 0
        except ValueError:
            await query.answer()
            return
        await cmd_user_card(update, context, target_uid, offset)
        return

    if data.startswith("admin:pick:"):
        package_id = data.split(":", 2)[2]
        pkg = get_package(package_id)
        if not pkg:
            await query.answer("חבילה לא נמצאה", show_alert=True)
            return
        context.user_data.pop("admin_awaiting_custom_qty", None)
        await query.answer()
        if query.message:
            await query.message.edit_text(
                f"נבחרה חבילה: <b>{pkg.label_hebrew()}</b>\nכמה קודים תרצה לייצר?",
                reply_markup=build_quantity_keyboard(package_id),
                parse_mode="HTML",
            )
        return

    if data.startswith("admin:custom:"):
        package_id = data.split(":", 2)[2]
        pkg = get_package(package_id)
        if not pkg:
            await query.answer("חבילה לא נמצאה", show_alert=True)
            return
        context.user_data["admin_awaiting_custom_qty"] = package_id
        await query.answer()
        if query.message:
            await query.message.edit_text(
                f"חבילה: <b>{pkg.label_hebrew()}</b>\nכתוב כמה קודים תרצה לייצר (1–500):",
                parse_mode="HTML",
            )
        return

    if data.startswith("admin:gen:"):
        parts = data.split(":")
        if len(parts) < 4:
            await query.answer()
            return
        package_id = parts[2]
        count = int(parts[3])
        pkg = get_package(package_id)
        if not pkg:
            await query.answer("חבילה לא נמצאה", show_alert=True)
            return

        await query.answer()
        codes = generate_coupon_codes(
            count=count,
            daily_quota=pkg.daily_quota,
            period_days=pkg.period_days,
        )

        code_text = "\n".join(f"<code>{c}</code>" for c in codes)
        chat_id = query.message.chat_id if query.message else update.effective_user.id
        await context.bot.send_message(chat_id=chat_id, text=code_text, parse_mode="HTML")
        return
