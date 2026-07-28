# -*- coding: utf-8 -*-
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import bot.handlers as handlers
import bot.solution_session as solution_session


@pytest.mark.anyio
async def test_wipe_chat_after_anchor_deletes_range_keeps_anchor():
    chat_id = 4242
    solution_session.set_chat_anchor_message_id(chat_id, 10)
    context = MagicMock()
    context.bot.delete_message = AsyncMock()

    await handlers.wipe_chat_after_anchor(context, chat_id, through_message_id=13)

    deleted = sorted(
        call.kwargs["message_id"] for call in context.bot.delete_message.await_args_list
    )
    assert deleted == [11, 12, 13]
    assert solution_session.get_chat_anchor_message_id(chat_id) == 10


@pytest.mark.anyio
async def test_cmd_start_sets_chat_anchor():
    from telegram import Chat, Message, Update, User

    update = MagicMock(spec=Update)
    update.message = MagicMock(spec=Message)
    update.message.reply_text = AsyncMock(
        side_effect=[
            MagicMock(message_id=100),
            MagicMock(message_id=101),
        ]
    )
    update.effective_chat = Chat(id=7777, type="private")
    update.effective_user = User(id=7777, is_bot=False, first_name="T")

    context = MagicMock()
    solution_session.clear_chat_anchor_message_id(7777)

    await handlers.cmd_start(update, context)

    assert solution_session.get_chat_anchor_message_id(7777) == 100
