# -*- coding: utf-8 -*-
from __future__ import annotations

import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Chat, Message, Update, User
from telegram import InlineKeyboardMarkup, ReplyKeyboardMarkup

import bot.handlers as handlers


def test_cmd_start_and_build_start_keyboard_unchanged_shape():
    # Guardrail: persistent ReplyKeyboard must not leak into /start path.
    assert isinstance(handlers.build_start_keyboard(), InlineKeyboardMarkup)

    src = inspect.getsource(handlers.cmd_start)
    assert "build_start_keyboard" in src
    assert "build_persistent_keyboard" not in src


@pytest.mark.anyio
async def test_on_text_quota_button_triggers_quota_flow():
    update = MagicMock(spec=Update)
    update.message = MagicMock(spec=Message)
    update.message.text = "📊 מכסה"
    update.effective_chat = Chat(id=999002, type="private")
    update.effective_user = User(id=222, is_bot=False, first_name="T")
    update.message.reply_text = AsyncMock()

    context = MagicMock()

    fake_access_result = SimpleNamespace(status="OK")

    with patch.object(handlers, "COUPON_ACCESS_ENABLED", True):
        with patch.object(handlers, "check_image_access", return_value=fake_access_result):
            with patch.object(handlers, "quota_status_reply_hebrew", return_value="quota reply"):
                with patch.object(handlers, "telegram_user_id", return_value=222):
                    with patch.object(handlers, "handle_draft_text") as mock_draft:
                        await handlers.on_text(update, context)
                        mock_draft.assert_not_called()

    update.message.reply_text.assert_awaited_once()
    args, kwargs = update.message.reply_text.await_args
    assert args[0] == "quota reply"
    assert isinstance(kwargs.get("reply_markup"), ReplyKeyboardMarkup)
