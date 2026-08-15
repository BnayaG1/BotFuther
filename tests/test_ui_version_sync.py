# -*- coding: utf-8 -*-
"""סנכרון מקלדת/תפריט אחרי דיפלוי."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import Chat, Message, Update, User

from bot.handlers.router import (
    _CHAT_UI_VERSION_KEY,
    _CHAT_UI_VERSION_NOTICE_MSG_ID_KEY,
    sync_chat_ui_to_current_version,
)


@pytest.mark.anyio
async def test_sync_sends_refresh_once_per_version(monkeypatch):
    monkeypatch.setattr("bot.handlers.router.BOT_UI_VERSION", "test-ui-v1")

    sent_msg = MagicMock()
    sent_msg.message_id = 123
    update = MagicMock(spec=Update)
    update.message = MagicMock(spec=Message)
    update.message.text = "שלום"
    update.message.reply_text = AsyncMock(return_value=sent_msg)
    update.effective_chat = Chat(id=42, type="private")
    update.effective_user = User(id=42, is_bot=False, first_name="T")

    context = MagicMock()
    context.chat_data = {}

    await sync_chat_ui_to_current_version(update, context)
    assert context.chat_data[_CHAT_UI_VERSION_KEY] == "test-ui-v1"
    assert context.chat_data[_CHAT_UI_VERSION_NOTICE_MSG_ID_KEY] == 123
    update.message.reply_text.assert_awaited_once()
    assert "עודכן" in update.message.reply_text.await_args.args[0]

    update.message.reply_text.reset_mock()
    await sync_chat_ui_to_current_version(update, context)
    update.message.reply_text.assert_not_awaited()


@pytest.mark.anyio
async def test_sync_skips_start_command(monkeypatch):
    monkeypatch.setattr("bot.handlers.router.BOT_UI_VERSION", "test-ui-v2")

    update = MagicMock(spec=Update)
    update.message = MagicMock(spec=Message)
    update.message.text = "/start"
    update.message.reply_text = AsyncMock()
    update.effective_chat = Chat(id=7, type="private")

    context = MagicMock()
    context.chat_data = {}

    await sync_chat_ui_to_current_version(update, context)
    assert context.chat_data[_CHAT_UI_VERSION_KEY] == "test-ui-v2"
    update.message.reply_text.assert_not_awaited()


@pytest.mark.anyio
async def test_sync_deletes_notice_on_subsequent_interaction(monkeypatch):
    monkeypatch.setattr("bot.handlers.router.BOT_UI_VERSION", "test-ui-v3")

    update = MagicMock(spec=Update)
    update.message = MagicMock(spec=Message)
    update.message.text = "לחיצה נוספת"
    update.effective_chat = Chat(id=99, type="private")

    context = MagicMock()
    context.chat_data = {
        _CHAT_UI_VERSION_KEY: "test-ui-v3",
        _CHAT_UI_VERSION_NOTICE_MSG_ID_KEY: 888,
    }
    context.bot.delete_message = AsyncMock()

    await sync_chat_ui_to_current_version(update, context)
    context.bot.delete_message.assert_awaited_once_with(chat_id=99, message_id=888)
    assert _CHAT_UI_VERSION_NOTICE_MSG_ID_KEY not in context.chat_data

