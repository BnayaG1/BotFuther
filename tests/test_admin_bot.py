# -*- coding: utf-8 -*-
"""בדיקות בוט אדמין."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import Update, User

from bot.admin_bot import (
    _is_admin,
    build_admin_menu_keyboard,
    cmd_users,
    on_admin_callback,
)


def test_is_admin_respects_configured_ids(monkeypatch):
    monkeypatch.setattr("bot.admin_bot.ADMIN_USER_IDS", frozenset({843647241}))
    update = MagicMock(spec=Update)
    update.effective_user = User(id=843647241, is_bot=False, first_name="A")
    assert _is_admin(update) is True
    update.effective_user = User(id=1, is_bot=False, first_name="B")
    assert _is_admin(update) is False


def test_admin_menu_keyboard_includes_vip_option():
    keyboard = build_admin_menu_keyboard()
    labels = [btn.text for row in keyboard.inline_keyboard for btn in row]
    callbacks = [btn.callback_data for row in keyboard.inline_keyboard for btn in row]
    assert any("VIP ללא הגבלות" in label for label in labels)
    assert "admin:pick:vip_unlimited" in callbacks
    assert len(callbacks) == 5  # 4 רגילות + VIP אחד


def test_admin_persistent_reply_keyboard():
    from bot.admin_bot import (
        ADMIN_KB_COUPONS,
        ADMIN_KB_ENGINEER,
        ADMIN_KB_OVERVIEW,
        ADMIN_KB_USERS,
        build_admin_persistent_reply_keyboard,
    )
    kb = build_admin_persistent_reply_keyboard()
    labels = [btn.text for row in kb.keyboard for btn in row]
    assert ADMIN_KB_ENGINEER in labels
    assert ADMIN_KB_OVERVIEW in labels
    assert ADMIN_KB_USERS in labels
    assert ADMIN_KB_COUPONS in labels
    assert "₪39" not in labels
    assert "VIP" not in labels
    assert kb.is_persistent is True



@pytest.mark.anyio
async def test_on_admin_text_package_button(monkeypatch):
    from bot.admin_bot import on_admin_text
    monkeypatch.setattr("bot.admin_bot.ADMIN_USER_IDS", frozenset({99}))

    update = MagicMock()
    update.effective_user = User(id=99, is_bot=False, first_name="Admin")
    update.message = MagicMock()
    update.message.text = "חודש · ₪39"
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {}
    await on_admin_text(update, context)

    update.message.reply_text.assert_awaited_once()
    args, kwargs = update.message.reply_text.await_args
    assert "נבחרה חבילה: <b>חודש · ₪39</b>" in args[0]
    assert kwargs.get("reply_markup") is not None




@pytest.mark.anyio
async def test_admin_gen_callback_creates_vip_code(monkeypatch):
    monkeypatch.setattr("bot.admin_bot.ADMIN_USER_IDS", frozenset({99}))
    monkeypatch.setattr(
        "bot.admin_bot.generate_coupon_codes",
        lambda *, count, daily_quota, period_days: ["VIPCODE123"] * count,
    )

    update = MagicMock()
    update.effective_user = User(id=99, is_bot=False, first_name="Admin")
    update.callback_query = MagicMock()
    update.callback_query.data = "admin:gen:vip_unlimited:1"
    update.callback_query.message = MagicMock()
    update.callback_query.message.chat_id = 500
    update.callback_query.answer = AsyncMock()

    context = MagicMock()
    context.bot.send_message = AsyncMock()

    await on_admin_callback(update, context)

    update.callback_query.answer.assert_awaited()
    context.bot.send_message.assert_awaited_once()
    kwargs = context.bot.send_message.await_args.kwargs
    assert "VIPCODE123" in kwargs.get("text", "")


@pytest.mark.anyio
async def test_cmd_users_lists_first_seen(monkeypatch):
    monkeypatch.setattr("bot.admin_bot.ADMIN_USER_IDS", frozenset({99}))
    monkeypatch.setattr(
        "bot.admin_bot.list_users_page",
        lambda **kwargs: (
            [
                {
                    "user_id": 111,
                    "username": "john_doe",
                    "first_seen_at": 1_700_000_000.0,
                    "last_seen_at": 1_700_000_000.0,
                    "access_line": "VIP · עוד 10 ימים",
                    "access_short": "VIP",
                    "usage_line": "פתרון 2",
                    "dwell_sec": 120,
                },
                {
                    "user_id": 222,
                    "username": None,
                    "first_seen_at": 1_700_000_060.0,
                    "last_seen_at": None,
                    "access_line": "בלי גישה",
                    "access_short": "בלי",
                    "usage_line": "",
                    "dwell_sec": 0,
                },
            ],
            2,
            {"total": 2, "vip": 1, "coupon": 0, "window": 0, "none": 1},
        ),
    )

    update = MagicMock()
    update.effective_user = User(id=99, is_bot=False, first_name="Admin")
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    update.callback_query = None

    await cmd_users(update, MagicMock())

    update.message.reply_text.assert_awaited_once()
    text = update.message.reply_text.await_args.args[0]
    assert "2 רשומים" in text
    assert "@john_doe" in text
    assert "222" in text
    assert "VIP · עוד 10 ימים" in text
    assert "בלי גישה" in text


@pytest.mark.anyio
async def test_cmd_user_detail_returns_user_info(monkeypatch):
    monkeypatch.setattr("bot.admin_bot.ADMIN_USER_IDS", frozenset({99}))
    monkeypatch.setattr(
        "bot.admin_bot.format_user_card_text",
        lambda uid, **kwargs: (
            f"<b>משתמש {uid}</b>\n"
            f'<a href="https://t.me/super_user">@super_user</a>'
        ),
    )

    update = MagicMock()
    update.effective_user = User(id=99, is_bot=False, first_name="Admin")
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.args = ["555"]

    from bot.admin_bot import cmd_user_detail
    await cmd_user_detail(update, context)

    update.message.reply_text.assert_awaited_once()
    text = update.message.reply_text.await_args.args[0]
    assert "555" in text
    assert "@super_user" in text
    assert "https://t.me/super_user" in text



@pytest.mark.anyio
async def test_cmd_users_rejects_non_admin(monkeypatch):
    monkeypatch.setattr("bot.admin_bot.ADMIN_USER_IDS", frozenset({99}))

    update = MagicMock()
    update.effective_user = User(id=1, is_bot=False, first_name="Nope")
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    update.callback_query = None

    await cmd_users(update, MagicMock())

    update.message.reply_text.assert_awaited_once_with("גישה נדחתה.")
