# -*- coding: utf-8 -*-
"""בדיקות תהליך רכישת חבילה (תפריט, אישור, והוראות תשלום בביט)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import CallbackQuery, Chat, Message, Update, User
from telegram.ext import ContextTypes

from bot.purchase import (
    PACKAGE_CATALOG,
    build_package_confirm_keyboard,
    build_payment_keyboard,
    build_purchase_menu_keyboard,
    get_package,
    package_confirm_text_hebrew,
    parse_buy_callback,
    payment_instructions_hebrew,
    purchase_menu_intro_hebrew,
)
from bot.handlers import on_buy_callback


def test_package_catalog_contains_4_packages():
    assert len(PACKAGE_CATALOG) == 4
    pkg = get_package("6_30")
    assert pkg is not None
    assert pkg.period_days == 30
    assert pkg.price_ils == 39


def test_parse_buy_callback():
    assert parse_buy_callback("buy:menu") == ("menu", "")
    assert parse_buy_callback("buy:pkg:6_30") == ("pkg", "6_30")
    assert parse_buy_callback("buy:confirm:6_60") == ("confirm", "6_60")
    assert parse_buy_callback("buy:cancel") == ("cancel", "")
    assert parse_buy_callback("other:data") is None


def test_purchase_keyboards():
    menu_kb = build_purchase_menu_keyboard()
    assert len(menu_kb.inline_keyboard[0]) == 4

    confirm_kb = build_package_confirm_keyboard("6_30")
    assert confirm_kb.inline_keyboard[0][0].callback_data == "buy:confirm:6_30"

    payment_kb = build_payment_keyboard()
    assert payment_kb.inline_keyboard[0][0].url is not None


@pytest.mark.anyio
async def test_on_buy_callback_menu_shows_packages():
    update = MagicMock(spec=Update)
    query = MagicMock(spec=CallbackQuery)
    query.data = "buy:menu"
    query.answer = AsyncMock()
    query.message = MagicMock(spec=Message)
    query.message.chat_id = 9911
    query.message.delete = AsyncMock()
    update.callback_query = query
    update.effective_user = User(id=11, is_bot=False, first_name="T")

    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.bot = MagicMock()
    context.bot.send_message = AsyncMock()

    await on_buy_callback(update, context)

    query.answer.assert_awaited_once()
    query.message.delete.assert_awaited_once()
    context.bot.send_message.assert_awaited_once()
    args, kwargs = context.bot.send_message.await_args
    assert purchase_menu_intro_hebrew() in kwargs.get("text", args[1] if len(args) > 1 else "")


@pytest.mark.anyio
async def test_on_buy_callback_pkg_shows_confirmation():
    update = MagicMock(spec=Update)
    query = MagicMock(spec=CallbackQuery)
    query.data = "buy:pkg:6_30"
    query.answer = AsyncMock()
    query.message = MagicMock(spec=Message)
    query.message.chat_id = 9922
    query.message.delete = AsyncMock()
    update.callback_query = query
    update.effective_user = User(id=22, is_bot=False, first_name="T")

    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.bot = MagicMock()
    context.bot.send_message = AsyncMock()

    await on_buy_callback(update, context)

    query.answer.assert_awaited_once()
    query.message.delete.assert_awaited_once()
    context.bot.send_message.assert_awaited_once()


@pytest.mark.anyio
async def test_on_buy_callback_confirm_shows_payment_instructions():
    update = MagicMock(spec=Update)
    query = MagicMock(spec=CallbackQuery)
    query.data = "buy:confirm:6_30"
    query.answer = AsyncMock()
    query.message = MagicMock(spec=Message)
    query.message.chat_id = 9933
    query.message.delete = AsyncMock()
    update.callback_query = query
    update.effective_user = User(id=33, is_bot=False, first_name="T")

    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.bot = MagicMock()
    context.bot.send_message = AsyncMock()

    await on_buy_callback(update, context)

    query.answer.assert_awaited_once()
    query.message.delete.assert_awaited_once()
    context.bot.send_message.assert_awaited_once()
    args, kwargs = context.bot.send_message.await_args
    assert "לתשלום בביט" in kwargs.get("text", args[1] if len(args) > 1 else "")
