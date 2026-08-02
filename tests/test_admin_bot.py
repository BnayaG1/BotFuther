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
    cmd_users,
    on_admin_callback,
)
from bot.purchase import PACKAGE_CATALOG


def test_price_buttons_map_to_packages():
    assert len({pkg.package_id for pkg in PACKAGE_CATALOG}) == 2
    for pkg in PACKAGE_CATALOG:
        label = _admin_menu_button_label(pkg)
        assert _PRICE_TO_PACKAGE[label] == pkg.package_id
        assert _PRICE_TO_PACKAGE[str(pkg.price_ils)] == pkg.package_id


def test_price_button_mapping_examples():
    assert _PRICE_TO_PACKAGE["₪30"] == "6_30"
    assert _PRICE_TO_PACKAGE["30"] == "6_30"
    assert _PRICE_TO_PACKAGE["₪90"] == "6_120"
    assert _PRICE_TO_PACKAGE["90"] == "6_120"


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
    price_labels = [lbl for lbl in labels if lbl.startswith("₪")]
    assert price_labels == ["₪30", "₪90"]
    assert "תפריט" in labels


@pytest.mark.anyio
async def test_admin_gen_callback_creates_codes(monkeypatch):
    monkeypatch.setattr("bot.admin_bot.ADMIN_USER_IDS", frozenset({99}))
    monkeypatch.setattr(
        "bot.admin_bot.generate_coupon_codes",
        lambda *, count, daily_quota, period_days: ["CODEONE123"] * count,
    )

    update = MagicMock()
    update.effective_user = User(id=99, is_bot=False, first_name="Admin")
    update.callback_query = MagicMock()
    update.callback_query.data = "admin:gen:6_30:2"
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


@pytest.mark.anyio
async def test_cmd_users_lists_first_seen(monkeypatch):
    monkeypatch.setattr("bot.admin_bot.ADMIN_USER_IDS", frozenset({99}))
    monkeypatch.setattr(
        "bot.admin_bot.list_users_first_seen",
        lambda: [(111, 1_700_000_000.0), (222, 1_700_000_060.0)],
    )

    update = MagicMock()
    update.effective_user = User(id=99, is_bot=False, first_name="Admin")
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()

    await cmd_users(update, MagicMock())

    update.message.reply_text.assert_awaited_once()
    text = update.message.reply_text.await_args.args[0]
    assert "סה״כ משתמשים: 2" in text
    assert "111" in text
    assert "222" in text


@pytest.mark.anyio
async def test_cmd_users_rejects_non_admin(monkeypatch):
    monkeypatch.setattr("bot.admin_bot.ADMIN_USER_IDS", frozenset({99}))

    update = MagicMock()
    update.effective_user = User(id=1, is_bot=False, first_name="Nope")
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()

    await cmd_users(update, MagicMock())

    update.message.reply_text.assert_awaited_once_with("גישה נדחתה.")
