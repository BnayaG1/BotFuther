# -*- coding: utf-8 -*-
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Chat, InlineKeyboardMarkup, Message, Update, User

import bot.formulas as formulas
import bot.handlers as handlers


def test_formulas_catalog_and_parse():
    assert len(formulas.FORMULA_TOPICS) >= 1
    kb = formulas.build_formulas_menu_keyboard()
    assert isinstance(kb, InlineKeyboardMarkup)
    assert formulas.parse_formula_callback("formula:menu") == ("menu", "")
    assert formulas.parse_formula_callback("formula:back") == ("back", "")
    assert formulas.parse_formula_callback("formula:topic:load_shapes_q_m") == (
        "topic",
        "load_shapes_q_m",
    )
    assert formulas.parse_formula_callback("buy:menu") is None
    titles = [t.title for t in formulas.FORMULA_TOPICS]
    assert titles == [
        "נוסחות לתרגילי סמכים",
        "נוסחאות לתרגילי ריתום",
        "סרטוט הגרפים",
        "נוסחאות לחישוב שטחים",
        "וקטורים\\אלכסוניים",
        "הערות ודגשים חשובים",
    ]
    for topic in formulas.FORMULA_TOPICS:
        assert topic.image_path() is not None
        assert topic.image_path().is_file()


def test_start_keyboard_includes_formulas():
    kb = handlers.build_start_keyboard()
    texts = [btn.text for row in kb.inline_keyboard for btn in row]
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "📐 נוסחאות" in texts
    assert "menu:formulas" in callbacks


def test_persistent_keyboard_includes_formulas():
    kb = handlers.build_persistent_keyboard()
    texts = [btn.text for row in kb.keyboard for btn in row]
    assert "📐 נוסחאות" in texts


@pytest.mark.anyio
async def test_on_text_formulas_button_opens_menu():
    update = MagicMock(spec=Update)
    update.message = MagicMock(spec=Message)
    update.message.text = "📐 נוסחאות"
    update.effective_chat = Chat(id=999010, type="private")
    update.effective_user = User(id=1010, is_bot=False, first_name="T")
    update.message.reply_text = AsyncMock()

    context = MagicMock()

    with patch.object(handlers, "telegram_chat_id", return_value=999010):
        with patch.object(handlers, "telegram_user_id", return_value=1010):
            with patch.object(handlers, "has_active_coupon_access", return_value=True):
                with patch.object(handlers, "COUPON_ACCESS_ENABLED", True):
                    await handlers.on_text(update, context)

    update.message.reply_text.assert_awaited()
    args, kwargs = update.message.reply_text.await_args
    assert "נוסחאות" in args[0]
    assert "מנויי חבילה" not in args[0]
    assert isinstance(kwargs.get("reply_markup"), InlineKeyboardMarkup)


@pytest.mark.anyio
async def test_formulas_locked_without_coupon():
    update = MagicMock(spec=Update)
    update.message = MagicMock(spec=Message)
    update.message.text = "📐 נוסחאות"
    update.effective_chat = Chat(id=999012, type="private")
    update.effective_user = User(id=1012, is_bot=False, first_name="T")
    update.message.reply_text = AsyncMock()

    context = MagicMock()

    with patch.object(handlers, "telegram_chat_id", return_value=999012):
        with patch.object(handlers, "telegram_user_id", return_value=1012):
            with patch.object(handlers, "has_active_coupon_access", return_value=False):
                with patch.object(handlers, "COUPON_ACCESS_ENABLED", True):
                    await handlers.on_text(update, context)

    update.message.reply_text.assert_awaited()
    args, kwargs = update.message.reply_text.await_args
    assert "מנויי חבילה" in args[0] or "🔒" in args[0]
    kb = kwargs.get("reply_markup")
    assert isinstance(kb, InlineKeyboardMarkup)
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "buy:menu" in callbacks
    assert "buy:redeem" in callbacks


@pytest.mark.anyio
async def test_cmd_formulas_opens_menu():
    update = MagicMock(spec=Update)
    update.message = MagicMock(spec=Message)
    update.message.reply_text = AsyncMock()
    update.effective_chat = Chat(id=999011, type="private")

    context = MagicMock()
    with patch.object(handlers, "telegram_chat_id", return_value=999011):
        with patch.object(handlers, "telegram_user_id", return_value=1011):
            with patch.object(handlers, "has_active_coupon_access", return_value=True):
                with patch.object(handlers, "COUPON_ACCESS_ENABLED", True):
                    await handlers.cmd_formulas(update, context)

    update.message.reply_text.assert_awaited()
    args, kwargs = update.message.reply_text.await_args
    assert "נוסחאות" in args[0]
    assert isinstance(kwargs.get("reply_markup"), InlineKeyboardMarkup)


def test_bot_commands_menu_includes_formulas():
    from bot.__main__ import _BOT_COMMANDS

    names = [c.command for c in _BOT_COMMANDS]
    assert "formulas" in names
    assert "start" in names


def test_formulas_locked_message_and_keyboard():
    text = formulas.formulas_locked_reply_hebrew()
    assert "מנויי חבילה" in text or "🔒" in text
    kb = formulas.build_formulas_locked_keyboard()
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "buy:menu" in callbacks
    assert "buy:redeem" in callbacks
