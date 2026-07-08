# -*- coding: utf-8 -*-
"""בדיקות בוט אדמין ליצירת קופונים."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import Update, User

from bot.admin_bot import (
    _PRICE_TO_PACKAGE,
    _admin_menu_button_label,
    _is_admin,
    build_admin_menu_keyboard,
    on_admin_callback,
)
from bot.purchase import PACKAGE_CATALOG


def test_price_buttons_map_to_all_six_packages():
    assert len({pkg.package_id for pkg in PACKAGE_CATALOG}) == 6
    for pkg in PACKAGE_CATALOG:
        label = _admin_menu_button_label(pkg)
        assert _PRICE_TO_PACKAGE[label] == pkg.package_id
        assert _PRICE_TO_PACKAGE[str(pkg.price_ils)] == pkg.package_id


def test_price_button_mapping_examples():
    assert _PRICE_TO_PACKAGE["₪50"] == "10_30"
    assert _PRICE_TO_PACKAGE["₪25"] == "2_30"
    assert _PRICE_TO_PACKAGE["95"] == "10_105"


def test_is_admin_respects_configured_ids(monkeypatch):
    monkeypatch.setattr("bot.admin_bot.ADMIN_USER_IDS", frozenset({843647241}))
    update = MagicMock(spec=Update)
    update.effective_user = User(id=843647241, is_bot=False, first_name="A")
    assert _is_admin(update) is True
    update.effective_user = User(id=1, is_bot=False, first_name="B")
    assert _is_admin(update) is False


def test_admin_menu_keyboard_shows_payment_amounts():
    keyboard = build_admin_menu_keyboard()
    labels = [btn.text for row in keyboard.keyboard for btn in row]
    for pkg in PACKAGE_CATALOG:
        assert _admin_menu_button_label(pkg) in labels


@pytest.mark.anyio
async def test_admin_gen_callback_creates_codes(monkeypatch):
    monkeypatch.setattr("bot.admin_bot.ADMIN_USER_IDS", frozenset({99}))
    monkeypatch.setattr(
        "bot.admin_bot.generate_coupon_codes",
        lambda *, package_id, count: ["CODEONE123"] * count,
    )

    update = MagicMock()
    update.effective_user = User(id=99, is_bot=False, first_name="Admin")
    update.callback_query = MagicMock()
    update.callback_query.data = "admin:gen:10_30:2"
    update.callback_query.message = MagicMock()
    update.callback_query.message.chat_id = 500
    update.callback_query.message.edit_text = AsyncMock()
    update.callback_query.answer = AsyncMock()

    context = MagicMock()
    context.bot.send_message = AsyncMock()

    await on_admin_callback(update, context)

    update.callback_query.answer.assert_awaited()
    context.bot.send_message.assert_awaited_once()
    sent_text = (
        context.bot.send_message.await_args.kwargs.get("text")
        or context.bot.send_message.await_args[0][1]
    )
    assert sent_text.strip() == "CODEONE123\nCODEONE123"
