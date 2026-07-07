# -*- coding: utf-8 -*-
from __future__ import annotations
import asyncio
import logging
import sys
import threading
import os
from flask import Flask
from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters
from telegram.request import HTTPXRequest

from bot.config import (
    ADMIN_BOT_TOKEN,
    ADMIN_USER_IDS,
    APP_DIR,
    TELEGRAM_KEY_NAMES,
)
from bot.env import load_env_files, log_startup_config, require_env
from bot.gemini_chat import gemini_runtime
from bot.access import init_access_db
from bot.handlers import cmd_coupon, cmd_ping, cmd_quota, cmd_reset, cmd_start, on_buy_callback, on_draft_callback, on_error, on_image, on_menu_callback, on_text
from bot.instance_lock import acquire_bot_instance_lock

# Flask פשוט כדי למנוע מ-Render לסגור את השרת
app = Flask(__name__)
@app.route('/')
def home(): return "Bot is running!"

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s — %(message)s", level=logging.INFO)
log = logging.getLogger("beam_telegram_bot")

_POLLING_KW = {"drop_pending_updates": True, "allowed_updates": Update.ALL_TYPES}


async def _run_both_bots(main_app: Application, admin_app: Application) -> None:
    """שני בוטים ב-asyncio על main thread — run_polling ב-thread נופל ב-Linux."""
    async with main_app, admin_app:
        await main_app.start()
        await admin_app.start()
        await main_app.updater.start_polling(**_POLLING_KW)
        await admin_app.updater.start_polling(**_POLLING_KW)
        log.info("Admin bot polling started (authorized users: %s)", sorted(ADMIN_USER_IDS))
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
    
    token = require_env(*TELEGRAM_KEY_NAMES, label="Telegram bot token")
    gemini_runtime()
    init_access_db()

    request = HTTPXRequest(connect_timeout=30.0, read_timeout=90.0, write_timeout=90.0, pool_timeout=30.0)
    app_bot = Application.builder().token(token).request(request).get_updates_request(request).build()
    
    app_bot.add_handler(CommandHandler("start", cmd_start))
    app_bot.add_handler(CommandHandler("help", cmd_start))
    app_bot.add_handler(CommandHandler("reset", cmd_reset))
    app_bot.add_handler(CommandHandler("ping", cmd_ping))
    app_bot.add_handler(CommandHandler("coupon", cmd_coupon))
    app_bot.add_handler(CommandHandler("quota", cmd_quota))
    app_bot.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, on_image))
    app_bot.add_handler(CallbackQueryHandler(on_menu_callback, pattern=r"^menu:"))
    app_bot.add_handler(CallbackQueryHandler(on_buy_callback, pattern=r"^buy:"))
    app_bot.add_handler(CallbackQueryHandler(on_draft_callback, pattern=r"^d:"))
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.PHOTO & ~filters.Document.IMAGE, on_text))
    app_bot.add_error_handler(on_error)

    log.info("Bot is running. Starting Flask and Polling...")

    # הפעלת Flask ב-Thread נפרד
    port = int(os.environ.get("PORT", 8080))
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=port), daemon=True).start()

    if ADMIN_BOT_TOKEN and ADMIN_USER_IDS:
        from bot.admin_bot import build_admin_application

        log.info("Admin bot starting (authorized users: %s)", sorted(ADMIN_USER_IDS))
        admin_app = build_admin_application()
        asyncio.run(_run_both_bots(app_bot, admin_app))
    elif ADMIN_BOT_TOKEN:
        log.warning("ADMIN_BOT_TOKEN set but ADMIN_USER_IDS empty — admin bot not started")
        app_bot.run_polling(**_POLLING_KW)
    else:
        app_bot.run_polling(**_POLLING_KW)

if __name__ == "__main__":
    if str(APP_DIR) not in sys.path:
        sys.path.insert(0, str(APP_DIR))
    main()
