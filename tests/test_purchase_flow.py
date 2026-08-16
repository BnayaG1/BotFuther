# -*- coding: utf-8 -*-
"""בדיקות תפריט רכישת חבילות."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Chat, Message, Update, User

import bot.access as access
import bot.config as config
from bot.handlers import cmd_coupon, on_buy_callback
from bot.purchase import PACKAGE_CATALOG, get_package, parse_buy_callback


def test_package_catalog_has_four_options():
    assert len(PACKAGE_CATALOG) == 4
    pkg_month = get_package("6_30")
    assert pkg_month is not None
    assert pkg_month.price_ils == 39
    assert pkg_month.daily_quota == 6
    assert pkg_month.period_days == 30
    pkg_2m = get_package("6_60")
    assert pkg_2m is not None
    assert pkg_2m.price_ils == 74
    assert pkg_2m.period_days == 60
    pkg_3m = get_package("6_90")
    assert pkg_3m is not None
    assert pkg_3m.price_ils == 105
    assert pkg_3m.period_days == 90
    pkg_long = get_package("6_120")
    assert pkg_long is not None
    assert pkg_long.price_ils == 134
    assert pkg_long.daily_quota == 6
    assert pkg_long.period_days == 120


def test_parse_buy_callback():
    assert parse_buy_callback("buy:confirm:6_30") == ("confirm", "6_30")
    assert parse_buy_callback("buy:confirm:6_120") == ("confirm", "6_120")
    assert parse_buy_callback("buy:menu") == ("menu", "")
    assert parse_buy_callback("menu:coupon") is None


@pytest.mark.anyio
async def test_cmd_coupon_shows_purchase_menu():
    update = MagicMock(spec=Update)
    update.message = MagicMock(spec=Message)
    update.effective_chat = Chat(id=100, type="private")
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    with patch.object(config, "COUPON_ACCESS_ENABLED", True):
        await cmd_coupon(update, context)

    update.message.reply_text.assert_awaited_once()
    _args, kwargs = update.message.reply_text.await_args
    assert "כמה חודשים תרצה לקבל?" in _args[0]
    assert kwargs.get("reply_markup") is not None


@pytest.mark.anyio
async def test_buy_confirm_creates_request_and_shows_payment():
    update = MagicMock(spec=Update)
    update.callback_query = MagicMock()
    update.callback_query.data = "buy:confirm:6_30"
    update.callback_query.message = MagicMock(spec=Message)
    update.callback_query.message.chat_id = 200
    update.callback_query.message.delete = AsyncMock()
    update.callback_query.answer = AsyncMock()
    update.effective_user = User(id=42, is_bot=False, first_name="T", username="tester")
    context = MagicMock()
    context.bot.send_message = AsyncMock()

    with patch.object(config, "COUPON_ACCESS_ENABLED", True):
        with patch.object(config, "ADMIN_CHAT_ID", 0):
            with patch("bot.handlers.create_purchase_request") as mock_create:
                mock_create.return_value = access.PurchaseRequest(
                    id=7,
                    user_id=42,
                    chat_id=200,
                    daily_quota=6,
                    period_days=30,
                    price_ils=39,
                    package_label="x",
                    status="pending",
                    created_at=1.0,
                )
                await on_buy_callback(update, context)

    mock_create.assert_called_once()
    update.callback_query.message.delete.assert_awaited_once()
    context.bot.send_message.assert_awaited()
    pay_kwargs = context.bot.send_message.await_args.kwargs
    pay_text = pay_kwargs["text"]
    assert "39" in pay_text
    assert config.BIT_PHONE in pay_text
    assert config.PAYMENT_CONFIRM_WHATSAPP_URL in pay_text
    assert pay_kwargs.get("reply_markup") is not None


@pytest.fixture()
def purchase_db(tmp_path, monkeypatch):
    db_path = tmp_path / "purchase_test.db"
    monkeypatch.setattr(config, "COUPON_DB_PATH", db_path)
    monkeypatch.setattr(access, "COUPON_DB_PATH", db_path)
    access.close_access_db()
    access.init_access_db()
    yield
    access.close_access_db()


def test_create_purchase_request_in_db(purchase_db):
    req = access.create_purchase_request(
        user_id=99,
        chat_id=100,
        daily_quota=6,
        period_days=30,
        price_ils=30,
        package_label="חודש · ₪30",
    )
    assert req.id >= 1
    assert req.daily_quota == 6
    assert req.status == "pending"
