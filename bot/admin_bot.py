# -*- coding: utf-8 -*-
"""בוט אדמין ליצירת קודי קופון — גישה למורשים בלבד."""
from __future__ import annotations

import logging
import re

from telegram import (
    ForceReply,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

from bot.access import init_access_db
from bot.config import ADMIN_BOT_TOKEN, ADMIN_USER_IDS
from bot.generate_coupons import generate_coupon_codes
from bot.purchase import PACKAGE_CATALOG, PackageOption, get_package, _period_label

log = logging.getLogger("beam_admin_bot")

_PENDING_CUSTOM_QTY: dict[int, str] = {}
_QUICK_COUNTS = (3, 5, 10, 20)
_MAX_BATCH = 100

_UNAUTHORIZED_TEXT = "גישה נדחתה."


def _welcome_text() -> str:
    return "ניהול קופונים"


def _admin_menu_button_label(pkg: PackageOption) -> str:
    return f"₪{pkg.price_ils}"


def _admin_package_label(pkg: PackageOption) -> str:
    period = _period_label(pkg.period_days)
    return f"{pkg.daily_quota} תמונות/יום · {period}"


_PRICE_TO_PACKAGE: dict[str, str] = {
    _admin_menu_button_label(pkg): pkg.package_id for pkg in PACKAGE_CATALOG
}
# גם ללא סימן ₪ — למקרה שהמשתמש מקליד ידנית
for pkg in PACKAGE_CATALOG:
    _PRICE_TO_PACKAGE[str(pkg.price_ils)] = pkg.package_id


def _is_admin(update: Update) -> bool:
    user = update.effective_user
    if user is None:
        return False
    if not ADMIN_USER_IDS:
        return False
    return int(user.id) in ADMIN_USER_IDS


def build_admin_menu_keyboard() -> ReplyKeyboardMarkup:
    sorted_packages = sorted(PACKAGE_CATALOG, key=lambda p: p.price_ils)
    rows: list[list[KeyboardButton]] = []
    row: list[KeyboardButton] = []
    for pkg in sorted_packages:
        row.append(KeyboardButton(_admin_menu_button_label(pkg)))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([KeyboardButton("תפריט")])
    return ReplyKeyboardMarkup(
        rows,
        is_persistent=True,
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def _confirm_keyboard(package_id: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                "קוד 1",
                callback_data=f"admin:gen:{package_id}:1",
            )
        ],
    ]
    count_row = [
        InlineKeyboardButton(str(n), callback_data=f"admin:gen:{package_id}:{n}")
        for n in _QUICK_COUNTS
    ]
    rows.append(count_row)
    rows.append(
        [
            InlineKeyboardButton(
                "כמות",
                callback_data=f"admin:custom:{package_id}",
            )
        ]
    )
    rows.append([InlineKeyboardButton("ביטול", callback_data="admin:cancel")])
    return InlineKeyboardMarkup(rows)


def _package_summary(pkg: PackageOption) -> str:
    period = _period_label(pkg.period_days)
    return f"*₪{pkg.price_ils}* · {pkg.daily_quota}/יום · {period}"


def _format_codes_message(codes: list[str]) -> str:
    return "\n".join(codes)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not _is_admin(update):
        await update.message.reply_text(_UNAUTHORIZED_TEXT)
        return
    _PENDING_CUSTOM_QTY.pop(update.effective_chat.id, None)
    await update.message.reply_text(
        _welcome_text(),
        reply_markup=build_admin_menu_keyboard(),
    )


async def on_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return
    if not _is_admin(update):
        await query.answer("אין הרשאה", show_alert=True)
        return

    data = query.data
    if data == "admin:cancel":
        await query.answer()
        chat_id = query.message.chat_id if query.message else None
        if chat_id is not None:
            _PENDING_CUSTOM_QTY.pop(chat_id, None)
        if query.message:
            await query.message.edit_text("בוטל.")
        return

    if data.startswith("admin:custom:"):
        package_id = data.split(":", 2)[2]
        pkg = get_package(package_id)
        if pkg is None:
            await query.answer("חבילה לא נמצאה", show_alert=True)
            return
        chat_id = query.message.chat_id if query.message else None
        if chat_id is None:
            await query.answer()
            return
        _PENDING_CUSTOM_QTY[chat_id] = package_id
        await query.answer()
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"₪{pkg.price_ils} · כמות",
            reply_markup=ForceReply(
                selective=True,
                input_field_placeholder=f"1–{_MAX_BATCH}",
            ),
        )
        return

    if data.startswith("admin:gen:"):
        parts = data.split(":")
        if len(parts) != 4:
            await query.answer()
            return
        package_id = parts[2]
        try:
            count = int(parts[3])
        except ValueError:
            await query.answer("כמות לא תקינה", show_alert=True)
            return
        pkg = get_package(package_id)
        if pkg is None:
            await query.answer("חבילה לא נמצאה", show_alert=True)
            return
        if count < 1 or count > _MAX_BATCH:
            await query.answer(f"כמות חייבת להיות 1–{_MAX_BATCH}", show_alert=True)
            return

        await query.answer("מייצר...")
        codes = generate_coupon_codes(
            count=count,
            daily_quota=pkg.daily_quota,
            period_days=pkg.period_days,
        )
        text = _format_codes_message(codes)
        chat_id = query.message.chat_id if query.message else None
        if query.message:
            try:
                await query.message.edit_text("בוצע.")
            except Exception:
                pass
        if chat_id is not None:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=build_admin_menu_keyboard(),
            )
        log.info("Admin generated %s codes for package %s", len(codes), package_id)
        return

    await query.answer()


async def on_admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    if not _is_admin(update):
        await update.message.reply_text(_UNAUTHORIZED_TEXT)
        return

    chat_id = update.effective_chat.id
    text = update.message.text.strip()

    if text == "תפריט":
        _PENDING_CUSTOM_QTY.pop(chat_id, None)
        await update.message.reply_text(
            _welcome_text(),
            reply_markup=build_admin_menu_keyboard(),
            parse_mode="Markdown",
        )
        return

    pending_pkg = _PENDING_CUSTOM_QTY.get(chat_id)
    if pending_pkg is not None:
        if not re.fullmatch(r"\d{1,3}", text):
            await update.message.reply_text(f"1–{_MAX_BATCH}")
            return
        count = int(text)
        if count < 1 or count > _MAX_BATCH:
            await update.message.reply_text(f"1–{_MAX_BATCH}")
            return
        _PENDING_CUSTOM_QTY.pop(chat_id, None)
        pkg = get_package(pending_pkg)
        if pkg is None:
            await update.message.reply_text("חבילה לא נמצאה.")
            return
        codes = generate_coupon_codes(
            count=count,
            daily_quota=pkg.daily_quota,
            period_days=pkg.period_days,
        )
        await update.message.reply_text(
            _format_codes_message(codes),
            reply_markup=build_admin_menu_keyboard(),
        )
        log.info("Admin generated %s codes for package %s (custom qty)", len(codes), pending_pkg)
        return

    package_id = _PRICE_TO_PACKAGE.get(text)
    if package_id is None:
        return

    pkg = get_package(package_id)
    if pkg is None:
        await update.message.reply_text("חבילה לא נמצאה.")
        return

    await update.message.reply_text(
        _package_summary(pkg),
        reply_markup=_confirm_keyboard(package_id),
        parse_mode="Markdown",
    )


def build_admin_application() -> Application:
    if not ADMIN_BOT_TOKEN:
        raise RuntimeError("ADMIN_BOT_TOKEN is not set")
    request = HTTPXRequest(
        connect_timeout=30.0,
        read_timeout=90.0,
        write_timeout=90.0,
        pool_timeout=30.0,
    )
    app = (
        Application.builder()
        .token(ADMIN_BOT_TOKEN)
        .request(request)
        .get_updates_request(request)
        .build()
    )
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CallbackQueryHandler(on_admin_callback, pattern=r"^admin:"))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, on_admin_text)
    )
    return app


def run_admin_bot() -> None:
    if not ADMIN_BOT_TOKEN:
        log.info("Admin bot disabled — ADMIN_BOT_TOKEN not set")
        return
    if not ADMIN_USER_IDS:
        log.warning("Admin bot disabled — ADMIN_USER_IDS is empty")
        return
    init_access_db()
    log.info("Admin bot starting (authorized users: %s)", sorted(ADMIN_USER_IDS))
    app = build_admin_application()
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    import sys
    from pathlib import Path

    from bot.config import APP_DIR

    if str(APP_DIR) not in sys.path:
        sys.path.insert(0, str(APP_DIR))
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        level=logging.INFO,
    )
    run_admin_bot()
