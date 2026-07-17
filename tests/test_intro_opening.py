# -*- coding: utf-8 -*-
"""בדיקות למבוא לסטטיקה — פתיחה + כפתור המשך."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import InlineKeyboardMarkup

import bot.handlers as handlers
import intro.opening as opening


def test_opening_message_and_continue_button():
    text = opening.opening_message_hebrew()
    assert "הכל חייב להתאפס" in text
    assert "לחץ המשך" in text
    kb = opening.build_opening_keyboard()
    assert isinstance(kb, InlineKeyboardMarkup)
    buttons = [btn for row in kb.inline_keyboard for btn in row]
    assert any(btn.text == "המשך" and btn.callback_data == "intro:continue" for btn in buttons)
    assert opening.parse_intro_callback("intro:continue") == "continue"
    assert opening.parse_intro_callback("menu:intro") is None


@pytest.mark.anyio
async def test_menu_intro_sends_opening():
    update = MagicMock()
    query = MagicMock()
    query.data = "menu:intro"
    query.answer = AsyncMock()
    query.message = MagicMock()
    query.message.chat_id = 991001
    query.message.delete = AsyncMock()
    update.callback_query = query
    update.effective_chat = MagicMock(id=991001)

    context = MagicMock()
    context.bot.send_message = AsyncMock()

    await handlers.on_menu_callback(update, context)

    query.answer.assert_awaited()
    context.bot.send_message.assert_awaited()
    kwargs = context.bot.send_message.await_args.kwargs
    assert "הכל חייב להתאפס" in kwargs["text"]
    assert isinstance(kwargs.get("reply_markup"), InlineKeyboardMarkup)
