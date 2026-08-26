# -*- coding: utf-8 -*-
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Chat, Message, Update, User
from telegram import ReplyKeyboardMarkup

import bot.handlers as handlers


@pytest.mark.anyio
async def test_bug_report_button_prompts_for_details():
    update = MagicMock(spec=Update)
    update.message = MagicMock(spec=Message)
    update.message.text = handlers._PERSISTENT_BUG_REPORT_LABEL
    update.message.chat_id = 777001
    update.message.reply_text = AsyncMock()
    update.effective_chat = Chat(id=777001, type="private")
    update.effective_user = User(id=77, is_bot=False, first_name="U")

    context = MagicMock()
    handlers._bug_report_prompt_chats.discard(777001)

    with patch.object(handlers, "telegram_chat_id", return_value=777001):
        await handlers.on_text(update, context)

    assert 777001 in handlers._bug_report_prompt_chats
    assert update.message.reply_text.await_count >= 1
    first = update.message.reply_text.await_args_list[0]
    assert "דיווח על תקלה" in first.args[0]


@pytest.mark.anyio
async def test_bug_report_text_forwards_via_admin_bot():
    update = MagicMock(spec=Update)
    update.message = MagicMock(spec=Message)
    update.message.text = "הגרפים לא מופיעים בפתרון"
    update.message.chat_id = 777002
    update.message.reply_text = AsyncMock()
    update.effective_chat = Chat(id=777002, type="private")
    update.effective_user = User(id=88, is_bot=False, first_name="Dana", username="dana")

    context = MagicMock()
    context.bot = MagicMock()
    handlers._bug_report_prompt_chats.add(777002)

    with patch.object(handlers, "telegram_chat_id", return_value=777002):
        with patch.object(handlers, "telegram_user_id", return_value=88):
            with patch.object(
                handlers, "_forward_bug_report_via_admin_bot", new_callable=AsyncMock
            ) as mock_fwd:
                mock_fwd.return_value = True
                await handlers.on_text(update, context)

    assert 777002 not in handlers._bug_report_prompt_chats
    mock_fwd.assert_awaited_once()
    sent_text = mock_fwd.await_args.args[0]
    assert "דיווח תקלה" in sent_text
    assert "הגרפים לא מופיעים" in sent_text
    assert "88" in sent_text
    update.message.reply_text.assert_awaited()
    assert "נשלח לצוות" in update.message.reply_text.await_args.args[0]


@pytest.mark.anyio
async def test_bug_report_cancel():
    update = MagicMock(spec=Update)
    update.message = MagicMock(spec=Message)
    update.message.text = handlers._BUG_REPORT_CANCEL
    update.message.chat_id = 777003
    update.message.reply_text = AsyncMock()
    update.effective_chat = Chat(id=777003, type="private")
    update.effective_user = User(id=99, is_bot=False, first_name="U")

    context = MagicMock()
    handlers._bug_report_prompt_chats.add(777003)

    with patch.object(handlers, "telegram_chat_id", return_value=777003):
        with patch.object(
            handlers, "_forward_bug_report_via_admin_bot", new_callable=AsyncMock
        ) as mock_fwd:
            await handlers.on_text(update, context)

    mock_fwd.assert_not_awaited()
    assert 777003 not in handlers._bug_report_prompt_chats
    assert "בוטל" in update.message.reply_text.await_args.args[0]
    assert isinstance(
        update.message.reply_text.await_args.kwargs.get("reply_markup"),
        ReplyKeyboardMarkup,
    )


@pytest.mark.anyio
async def test_forward_bug_report_direct_via_main_bot():
    main_bot = MagicMock()
    main_bot.send_message = AsyncMock()

    with patch.object(handlers, "ADMIN_USER_IDS", frozenset({11111, 22222})):
        ok = await handlers._forward_bug_report_via_admin_bot("direct report", fallback_bot=main_bot)

    assert ok is True
    assert main_bot.send_message.await_count == 2
    sent_to = {call.kwargs.get("chat_id") for call in main_bot.send_message.await_args_list}
    assert sent_to == {11111, 22222}


