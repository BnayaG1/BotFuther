# -*- coding: utf-8 -*-
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import InlineKeyboardMarkup

import bot.handlers as handlers
import intro
from intro import topics as intro_topics


def test_intro_catalog_and_parse():
    assert len(intro.INTRO_TOPICS) >= 1
    kb = intro.build_intro_menu_keyboard()
    assert isinstance(kb, InlineKeyboardMarkup)
    assert intro.parse_intro_callback("intro:menu") == ("menu", "")
    assert intro.parse_intro_callback("intro:back") == ("back", "")
    assert intro.parse_intro_callback("intro:topic:what_is_statics") == (
        "topic",
        "what_is_statics",
    )
    assert intro.parse_intro_callback("menu:intro") is None
    titles = [t.title for t in intro.INTRO_TOPICS]
    assert titles == [
        "מהי סטטיקה?",
        "כוחות ווקטורים",
        "שיווי משקל",
        "מומנטים",
        "סמכים וריאקציות",
    ]
    for topic in intro.INTRO_TOPICS:
        body = intro.intro_topic_body_hebrew(topic)
        assert topic.title.split("?")[0][:3] in body or "סטטיקה" in body or len(body) > 40


def test_start_keyboard_includes_intro():
    kb = handlers.build_start_keyboard()
    texts = [btn.text for row in kb.inline_keyboard for btn in row]
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert handlers._START_INTRO_LABEL in texts
    assert "מבוא" in texts
    assert "menu:intro" in callbacks


@pytest.mark.anyio
async def test_menu_intro_opens_intro_menu():
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
    assert "מבוא" in kwargs["text"]
    assert isinstance(kwargs.get("reply_markup"), InlineKeyboardMarkup)


@pytest.mark.anyio
async def test_intro_topic_sends_body():
    update = MagicMock()
    query = MagicMock()
    query.data = "intro:topic:equilibrium"
    query.answer = AsyncMock()
    query.message = MagicMock()
    query.message.chat_id = 991002
    query.message.delete = AsyncMock()
    update.callback_query = query

    context = MagicMock()
    context.bot.send_message = AsyncMock()

    await handlers.on_intro_callback(update, context)

    query.answer.assert_awaited()
    kwargs = context.bot.send_message.await_args.kwargs
    assert "שיווי משקל" in kwargs["text"]
    assert "ΣFx" in kwargs["text"]
    assert isinstance(kwargs["reply_markup"], InlineKeyboardMarkup)
    callbacks = [
        b.callback_data for row in kwargs["reply_markup"].inline_keyboard for b in row
    ]
    assert "intro:menu" in callbacks
    assert "intro:back" in callbacks


def test_get_intro_topic_unknown():
    assert intro_topics.get_intro_topic("not_real") is None
    assert intro.get_intro_topic("moments") is not None
