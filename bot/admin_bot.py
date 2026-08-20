# -*- coding: utf-8 -*-
"""בוט אדמין — ניהול ויצירת קודי קופון למורשים בלבד."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)
from telegram.request import HTTPXRequest

from bot.access import get_user_info, init_access_db, list_users_first_seen
from bot.config import ADMIN_BOT_TOKEN, ADMIN_USER_IDS, get_admin_user_ids
from bot.generate_coupons import generate_coupon_codes
from bot.purchase import ADMIN_PACKAGE_CATALOG, PACKAGE_CATALOG, PackageOption, get_package

log = logging.getLogger("beam_admin_bot")

_UNAUTHORIZED_TEXT = "גישה נדחתה."


def _is_admin(update: Update) -> bool:
    user = update.effective_user
    if user is None:
        return False
    admin_ids = ADMIN_USER_IDS if ADMIN_USER_IDS else get_admin_user_ids()
    if not admin_ids:
        return True
    return int(user.id) in admin_ids






def build_admin_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            f"{pkg.label_hebrew()}",
            callback_data=f"admin:pick:{pkg.package_id}",
        )
        for pkg in ADMIN_PACKAGE_CATALOG
    ]
    # 2 כפתורים בשורה
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
            InlineKeyboardButton("חזרה לתפריט", callback_data="admin:menu"),
        ],
    ]
    return InlineKeyboardMarkup(rows)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not _is_admin(update):
        await update.message.reply_text(_UNAUTHORIZED_TEXT)
        return
    await update.message.reply_text(
        "בוט אדמין ליצירת קופונים.\n"
        "בחר חבילה ליצירת קוד קופון:",
        reply_markup=build_admin_menu_keyboard(),
    )


async def cmd_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not _is_admin(update):
        await update.message.reply_text(_UNAUTHORIZED_TEXT)
        return
    rows = list_users_first_seen()
    if not rows:
        await update.message.reply_text("אין משתמשים במערכת.")
        return
    lines = [f"<b>סה״כ משתמשים: {len(rows)}</b>\n"]
    for row in rows:
        uid = row[0]
        ts = row[1]
        uname = row[2] if len(row) > 2 else None
        dt = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
        if uname:
            user_link = f"<a href=\"https://t.me/{uname}\">@{uname}</a>"
        else:
            user_link = f"<a href=\"tg://user?id={uid}\">פתח שיחה בטלגרם</a>"
        lines.append(f"• ID: <code>{uid}</code> | {user_link} ({dt})")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


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

    info = get_user_info(target_uid)
    if not info:
        await update.message.reply_text(f"משתמש <code>{target_uid}</code> לא נמצא במערכת.", parse_mode="HTML")
        return

    uid = info["user_id"]
    uname = info["username"]
    dt = datetime.fromtimestamp(info["first_seen_at"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M")

    if uname:
        chat_link = f"<a href=\"https://t.me/{uname}\">@{uname} (לחץ לפתיחת שיחה)</a>"
    else:
        chat_link = f"<a href=\"tg://user?id={uid}\">פתח שיחה אישית בטלגרם</a>"

    coupon_str = "אין קופון פעיל"
    if info["active_coupon"]:
        cp = info["active_coupon"]
        exp_dt = datetime.fromtimestamp(cp["expires_at"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
        vip_tag = " [VIP]" if cp["is_vip"] else ""
        coupon_str = f"קוד: <code>{cp['code']}</code> ({cp['period_days']} ימים){vip_tag} — בתוקף עד {exp_dt}"

    bank_str = "פתוח" if info["bank_unlocked"] else "סגור"

    text = (
        f"<b>פרטי משתמש: {uid}</b>\n\n"
        f"• <b>שיחה ישירה בטלגרם</b>: {chat_link}\n"
        f"• <b>תאריך הצטרפות</b>: {dt}\n"
        f"• <b>סטטוס קופון</b>: {coupon_str}\n"
        f"• <b>מאגר תרגילים</b>: {bank_str}"
    )
    await update.message.reply_text(text, parse_mode="HTML")



async def on_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return
    if not _is_admin(update):
        await query.answer(_UNAUTHORIZED_TEXT, show_alert=True)
        return

    data = query.data
    if data == "admin:menu":
        await query.answer()
        if query.message:
            await query.message.edit_text(
                "בחר חבילה ליצירת קוד קופון:",
                reply_markup=build_admin_menu_keyboard(),
            )
        return

    if data.startswith("admin:pick:"):
        package_id = data.split(":", 2)[2]
        pkg = get_package(package_id)
        if not pkg:
            await query.answer("חבילה לא נמצאה", show_alert=True)
            return
        await query.answer()
        if query.message:
            await query.message.edit_text(
                f"נבחרה חבילה: <b>{pkg.label_hebrew()}</b>\nכמה קודים תרצה לייצר?",
                reply_markup=build_quantity_keyboard(package_id),
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
        reply_msg = (
            f"נוצרו <b>{count}</b> קודי קופון לחבילה {pkg.label_hebrew()}:\n\n"
            f"{code_text}"
        )
        chat_id = query.message.chat_id if query.message else update.effective_user.id
        await context.bot.send_message(
            chat_id=chat_id,
            text=reply_msg,
            parse_mode="HTML",
            reply_markup=build_admin_menu_keyboard(),
        )
        return


def build_admin_application(token: str | None = None) -> Application:
    import os as _os
    resolved_token = token or _os.getenv("ADMIN_BOT_TOKEN", "").strip() or ADMIN_BOT_TOKEN
    if not resolved_token:
        raise RuntimeError("ADMIN_BOT_TOKEN is not set")
    request = HTTPXRequest(
        connect_timeout=30.0,
        read_timeout=90.0,
        write_timeout=90.0,
        pool_timeout=30.0,
    )
    app = (
        Application.builder()
        .token(resolved_token)
        .request(request)
        .get_updates_request(request)
        .build()
    )
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("users", cmd_users))
    app.add_handler(CommandHandler("user", cmd_user_detail))
    app.add_handler(CallbackQueryHandler(on_admin_callback, pattern=r"^admin:"))
    return app



def run_admin_bot() -> None:
    import os
    token = os.getenv("ADMIN_BOT_TOKEN", "").strip() or ADMIN_BOT_TOKEN
    if not token:
        log.info("Admin bot disabled — ADMIN_BOT_TOKEN not set")
        return
    admin_ids = get_admin_user_ids() or ADMIN_USER_IDS
    init_access_db()
    log.info("Admin bot starting (authorized users: %s)", sorted(admin_ids) if admin_ids else "ALL")
    app = build_admin_application()
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

