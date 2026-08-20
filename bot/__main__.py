# -*- coding: utf-8 -*-
from __future__ import annotations
import asyncio
import logging
import sys
import threading
import os
from flask import Flask
from telegram import BotCommand, Update
from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    TypeHandler,
    filters,
)
from telegram.request import HTTPXRequest

from bot.config import (
    ADMIN_BOT_TOKEN,
    ADMIN_USER_IDS,
    APP_DIR,
    TELEGRAM_KEY_NAMES,
    get_admin_user_ids,
)

from bot.env import load_env_files, log_startup_config, require_env
from bot.gemini_chat import gemini_runtime
from bot.access import init_access_db
from bot.exercise_bank import init_exercise_bank_db
from bot.handlers import (
    INTRO_AVAILABLE,
    cmd_coupon,
    cmd_formulas,
    cmd_ping,
    cmd_quota,
    cmd_reset,
    cmd_start,
    on_assistant_callback,
    on_buy_callback,
    on_draft_callback,
    on_error,
    on_formula_callback,
    on_image,
    on_intro_callback,
    on_menu_callback,
    on_text,
    sync_chat_ui_to_current_version,
)


from bot.instance_lock import acquire_bot_instance_lock

# Flask פשוט כדי למנוע מ-Render לסגור את השרת
app = Flask(__name__)
@app.route('/')
def home(): return "Bot is running!"

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s — %(message)s", level=logging.INFO)
# Avoid logging full Telegram API URLs (they embed the bot token).
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
log = logging.getLogger("beam_telegram_bot")

_POLLING_KW = {"drop_pending_updates": True, "allowed_updates": Update.ALL_TYPES}

_BOT_COMMANDS = [
    BotCommand("start", "תפריט ראשי"),
    BotCommand("formulas", "נוסחאות"),
    BotCommand("quota", "מכסה"),
    BotCommand("reset", "איפוס תרגיל"),
    BotCommand("help", "עזרה"),
]



async def _post_init_set_commands(application: Application) -> None:
    await application.bot.set_my_commands(_BOT_COMMANDS)
    log.info("Telegram bot commands menu set (%s)", [c.command for c in _BOT_COMMANDS])


async def _run_both_bots(main_app: Application, admin_app: Application) -> None:
    """שני בוטים ב-asyncio על main thread — run_polling ב-thread נופל ב-Linux."""
    async with main_app, admin_app:
        await main_app.start()
        await admin_app.start()
        await main_app.updater.start_polling(**_POLLING_KW)
        await admin_app.updater.start_polling(**_POLLING_KW)
        log.info("Both bots polling started")
        try:
            await asyncio.Event().wait()
        finally:
            await main_app.updater.stop()
            await admin_app.updater.stop()
            await main_app.stop()
            await admin_app.stop()


def main() -> None:
    env_files = load_env_files()
    log_startup_config(env_files)
    acquire_bot_instance_lock()

    # Read tokens AFTER env is loaded
    main_token = require_env(*TELEGRAM_KEY_NAMES, label="Telegram bot token")
    admin_token = os.getenv("ADMIN_BOT_TOKEN", "").strip()

    gemini_runtime()
    init_access_db()
    init_exercise_bank_db()

    request = HTTPXRequest(connect_timeout=30.0, read_timeout=90.0, write_timeout=90.0, pool_timeout=30.0)
    app_bot = (
        Application.builder()
        .token(main_token)
        .request(request)
        .get_updates_request(request)
        .post_init(_post_init_set_commands)
        .build()
    )

    # לפני כל טיפול — מרענן מקלדת/תפריט אם המשתמש עדיין על גרסת ממשק ישנה.
    app_bot.add_handler(TypeHandler(Update, sync_chat_ui_to_current_version), group=-1)
    app_bot.add_handler(CommandHandler("start", cmd_start))
    app_bot.add_handler(CommandHandler("help", cmd_start))
    app_bot.add_handler(CommandHandler("reset", cmd_reset))
    app_bot.add_handler(CommandHandler("ping", cmd_ping))
    app_bot.add_handler(CommandHandler("quota", cmd_quota))
    app_bot.add_handler(CommandHandler("formulas", cmd_formulas))
    app_bot.add_handler(CommandHandler("formula", cmd_formulas))
    app_bot.add_handler(CommandHandler("coupon", cmd_coupon))

    app_bot.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, on_image))
    app_bot.add_handler(CallbackQueryHandler(on_menu_callback, pattern=r"^menu:"))
    app_bot.add_handler(CallbackQueryHandler(on_buy_callback, pattern=r"^buy:"))

    if INTRO_AVAILABLE:
        app_bot.add_handler(CallbackQueryHandler(on_intro_callback, pattern=r"^intro:"))
    app_bot.add_handler(CallbackQueryHandler(on_formula_callback, pattern=r"^formula:"))
    app_bot.add_handler(CallbackQueryHandler(on_draft_callback, pattern=r"^d:"))
    app_bot.add_handler(CallbackQueryHandler(on_assistant_callback, pattern=r"^assist:"))
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.PHOTO & ~filters.Document.IMAGE, on_text))
    app_bot.add_error_handler(on_error)

    log.info("Bot is running. Starting Flask and Polling...")

    # הפעלת Flask ב-Thread נפרד
    port = int(os.environ.get("PORT", 8080))
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=port), daemon=True).start()

    if admin_token:
        from bot.admin_bot import build_admin_application
        admin_ids = get_admin_user_ids()
        log.info("Admin bot starting (authorized users: %s)", sorted(admin_ids) if admin_ids else "ALL")
        admin_app = build_admin_application(admin_token)
        asyncio.run(_run_both_bots(app_bot, admin_app))
    else:
        log.info("Admin bot disabled — ADMIN_BOT_TOKEN not set")
        app_bot.run_polling(**_POLLING_KW)


if __name__ == "__main__":
    if str(APP_DIR) not in sys.path:
        sys.path.insert(0, str(APP_DIR))
    main()