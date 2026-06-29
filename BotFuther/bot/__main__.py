# -*- coding: utf-8 -*-
from __future__ import annotations
import logging
import sys
import threading
import os
from flask import Flask
from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters
from telegram.request import HTTPXRequest

from bot.config import APP_DIR, TELEGRAM_KEY_NAMES, VISION_ASYNC_ENABLED, VISION_BEAM_CROP, VISION_FAST_FALLBACK_STAGED
from bot.env import load_env_files, log_startup_config, require_env, resolve_primary_model
from bot.gemini_chat import gemini_runtime
from bot.handlers import cmd_ping, cmd_reset, cmd_start, on_draft_callback, on_error, on_image, on_menu_callback, on_text

# Flask פשוט כדי למנוע מ-Render לסגור את השרת
app = Flask(__name__)
@app.route('/')
def home(): return "Bot is running!"

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s — %(message)s", level=logging.INFO)
log = logging.getLogger("beam_telegram_bot")

def main() -> None:
    env_files = load_env_files()
    log_startup_config(env_files)
    
    token = require_env(*TELEGRAM_KEY_NAMES, label="Telegram bot token")
    gemini_runtime()

    request = HTTPXRequest(connect_timeout=30.0, read_timeout=90.0, write_timeout=90.0, pool_timeout=30.0)
    app_bot = Application.builder().token(token).request(request).get_updates_request(request).build()
    
    app_bot.add_handler(CommandHandler("start", cmd_start))
    app_bot.add_handler(CommandHandler("help", cmd_start))
    app_bot.add_handler(CommandHandler("reset", cmd_reset))
    app_bot.add_handler(CommandHandler("ping", cmd_ping))
    app_bot.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, on_image))
    app_bot.add_handler(CallbackQueryHandler(on_menu_callback, pattern=r"^menu:"))
    app_bot.add_handler(CallbackQueryHandler(on_draft_callback, pattern=r"^d:"))
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.PHOTO & ~filters.Document.IMAGE, on_text))
    app_bot.add_error_handler(on_error)

    log.info("Bot is running. Starting Flask and Polling...")
    
    # הפעלת Flask ב-Thread נפרד
    port = int(os.environ.get("PORT", 8080))
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=port), daemon=True).start()
    
    app_bot.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    if str(APP_DIR) not in sys.path:
        sys.path.insert(0, str(APP_DIR))
    main()