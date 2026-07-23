# -*- coding: utf-8 -*-
"""בדיקות למבוא לסטטיקה — פתיחה + כפתורי נושאים."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import InlineKeyboardMarkup

import bot.handlers as handlers
import intro.opening as opening


def test_opening_message_and_topic_buttons():
    text = opening.opening_message_hebrew()
    assert "ברוך הבא למבוא" in text
    assert "ברגע שתתפוס את הראש של הדברים" in text
    assert "לאן תרצה לקחת את זה?" in text
    kb = opening.build_opening_keyboard()
    assert isinstance(kb, InlineKeyboardMarkup)
    buttons = [btn for row in kb.inline_keyboard for btn in row]
    labels = [btn.text for btn in buttons]
    assert labels == ["פירוק עומסים", "Ax", "משוואות שיווי משקל"]
    assert opening.parse_intro_callback("intro:load_decomposition") == "load_decomposition"
    assert opening.parse_intro_callback("intro:ax") == "ax"
    assert opening.parse_intro_callback("intro:equilibrium") == "equilibrium"
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
    assert "לאן תרצה לקחת את זה?" in kwargs["text"]
    assert isinstance(kwargs.get("reply_markup"), InlineKeyboardMarkup)
