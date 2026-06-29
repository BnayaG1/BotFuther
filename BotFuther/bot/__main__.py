# -*- coding: utf-8 -*-
"""Entry point: python -m bot"""
from __future__ import annotations

import logging
import sys

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters
from telegram.request import HTTPXRequest

from bot.config import (
    APP_DIR,
    TELEGRAM_KEY_NAMES,
    VISION_ASYNC_ENABLED,
    VISION_BEAM_CROP,
    VISION_FAST_FALLBACK_STAGED,
)
from bot.env import load_env_files, log_startup_config, require_env, resolve_primary_model
from bot.gemini_chat import gemini_runtime
from bot.instance_lock import (
    abort_if_telegram_poller_active,
    acquire_bot_instance_lock,
    release_bot_instance_lock,
)
from bot.handlers import (
    cmd_ping,
    cmd_reset,
    cmd_start,
    on_draft_callback,
    on_error,
    on_image,
    on_menu_callback,
    on_text,
)

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("beam_telegram_bot")


def main() -> None:
    env_files = load_env_files()
    acquire_bot_instance_lock()
    abort_if_telegram_poller_active()
    log_startup_config(env_files)
    log.info(
        "Vision config: model=%s async=%s crop=%s staged_fallback=%s",
        resolve_primary_model(),
        VISION_ASYNC_ENABLED,
        VISION_BEAM_CROP,
        VISION_FAST_FALLBACK_STAGED,
    )

    token = require_env(*TELEGRAM_KEY_NAMES, label="Telegram bot token")
    gemini_runtime()

    request = HTTPXRequest(
        connect_timeout=30.0,
        read_timeout=90.0,
        write_timeout=90.0,
        pool_timeout=30.0,
    )
    app = (
        Application.builder()
        .token(token)
        .request(request)
        .get_updates_request(request)
        .build()
    )
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("ping", cmd_ping))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, on_image))
    app.add_handler(CallbackQueryHandler(on_menu_callback, pattern=r"^menu:"))
    app.add_handler(CallbackQueryHandler(on_draft_callback, pattern=r"^d:"))
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & ~filters.PHOTO & ~filters.Document.IMAGE,
            on_text,
        )
    )
    app.add_error_handler(on_error)

    log.info("Bot is running — image extraction only. Press Ctrl+C to stop.")
    try:
        app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)
    finally:
        release_bot_instance_lock()


if __name__ == "__main__":
    if str(APP_DIR) not in sys.path:
        sys.path.insert(0, str(APP_DIR))
    main()
