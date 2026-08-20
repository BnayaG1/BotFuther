# -*- coding: utf-8 -*-
"""בדיקות מערכת קודי קופון (1, 2, 3, 4 חודשים) ופדיונם."""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import CallbackQuery, Chat, Message, Update, User

import bot.access as access
from bot.generate_coupons import generate_coupon_codes
from bot.handlers import on_buy_callback, on_text


@pytest.fixture()
def access_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_coupons.db"
    monkeypatch.setattr(access, "DB_PATH", db_path)
    access.close_access_db()
    access.init_access_db()
    yield
    access.close_access_db()


def test_generate_and_redeem_1_2_3_4_month_coupons(access_db, monkeypatch):
    t0 = 1_700_000_000.0
    monkeypatch.setattr(access.time, "time", lambda: t0)

    # 1. חודש אחד (30 יום)
    c30 = generate_coupon_codes(count=1, period_days=30)[0]
    res1 = access.redeem_coupon(c30, user_id=101, now=t0)
    assert res1.status == access.RedeemStatus.OK
    assert res1.period_days == 30
    assert res1.period_expires_at == t0 + 30 * 86400

    # 2. חודשיים (60 יום)
    c60 = generate_coupon_codes(count=1, period_days=60)[0]
    res2 = access.redeem_coupon(c60, user_id=102, now=t0)
    assert res2.status == access.RedeemStatus.OK
    assert res2.period_days == 60
    assert res2.period_expires_at == t0 + 60 * 86400

    # 3. שלוש חודשים (90 יום)
    c90 = generate_coupon_codes(count=1, period_days=90)[0]
    res3 = access.redeem_coupon(c90, user_id=103, now=t0)
    assert res3.status == access.RedeemStatus.OK
    assert res3.period_days == 90
    assert res3.period_expires_at == t0 + 90 * 86400

    # 4. ארבעה חודשים (120 יום)
    c120 = generate_coupon_codes(count=1, period_days=120)[0]
    res4 = access.redeem_coupon(c120, user_id=104, now=t0)
    assert res4.status == access.RedeemStatus.OK
    assert res4.period_days == 120
    assert res4.period_expires_at == t0 + 120 * 86400


def test_redeem_coupon_twice_fails(access_db, monkeypatch):
    t0 = 1_700_000_000.0
    code = generate_coupon_codes(count=1, period_days=30)[0]
    res1 = access.redeem_coupon(code, user_id=201, now=t0)
    assert res1.status == access.RedeemStatus.OK

    res2 = access.redeem_coupon(code, user_id=202, now=t0)
    assert res2.status == access.RedeemStatus.ALREADY_REDEEMED


def test_redeem_invalid_code_fails(access_db):
    res = access.redeem_coupon("NONEXISTENT123", user_id=301)
    assert res.status == access.RedeemStatus.INVALID_CODE


def test_coupon_grants_privileged_phase_during_period(access_db, monkeypatch):
    user_id = 401
    t0 = 1_700_000_000.0
    monkeypatch.setattr(access.time, "time", lambda: t0)
    access.ensure_user_first_seen(user_id, now=t0)

    # מעבר אחרי חלון חינם 24ש'
    t1 = t0 + access.FORMULAS_FREE_WINDOW_SEC + 10
    monkeypatch.setattr(access.time, "time", lambda: t1)
    assert access.get_user_access_phase(user_id, now=t1) == access.UserAccessPhase.RESTRICTED

    # פדיון קופון 60 יום
    code = generate_coupon_codes(count=1, period_days=60)[0]
    access.redeem_coupon(code, user_id, now=t1)

    # עכשיו הוא ב-PRIVILEGED
    assert access.get_user_access_phase(user_id, now=t1) == access.UserAccessPhase.PRIVILEGED

    # 50 יום אחרי הפדיון — עדיין ב-PRIVILEGED
    t2 = t1 + 50 * 86400
    assert access.get_user_access_phase(user_id, now=t2) == access.UserAccessPhase.PRIVILEGED

    # 61 יום אחרי הפדיון — פג תוקף -> RESTRICTED
    t3 = t1 + 61 * 86400
    assert access.get_user_access_phase(user_id, now=t3) == access.UserAccessPhase.RESTRICTED


@pytest.mark.anyio
async def test_on_text_redeems_valid_coupon_code(access_db):
    code = generate_coupon_codes(count=1, period_days=30)[0]

    update = MagicMock(spec=Update)
    update.message = MagicMock(spec=Message)
    update.message.text = code
    update.effective_chat = Chat(id=99001, type="private")
    update.effective_user = User(id=501, is_bot=False, first_name="T")
    update.message.reply_text = AsyncMock()

    context = MagicMock()

    with patch("bot.handlers.router.telegram_chat_id", return_value=99001):
        with patch("bot.handlers.router.telegram_user_id", return_value=501):
            with patch("bot.handlers.router.is_draft_pending", return_value=False):
                await on_text(update, context)

    update.message.reply_text.assert_awaited_once()
    args, _ = update.message.reply_text.await_args
    assert "קוד הקופון נקלט בהצלחה" in args[0]


def test_vip_coupon_skips_cooldown_and_unlocks_bank(access_db, monkeypatch):
    user_id = 601
    t0 = 1_700_000_000.0
    monkeypatch.setattr(access.time, "time", lambda: t0)

    code = generate_coupon_codes(count=1, daily_quota=access.VIP_UNLIMITED_DAILY_QUOTA, period_days=120)[0]
    res = access.redeem_coupon(code, user_id, now=t0)
    assert res.status == access.RedeemStatus.OK

    assert access.user_has_bank_unlock(user_id)
    assert access.consume_solve_slot(user_id).status == access.ImageAccessStatus.OK

    # 5 שניות אחרי — פדוי מחדש בלי צינון 10 דקות (בגלל VIP)
    monkeypatch.setattr(access.time, "time", lambda: t0 + 5)
    assert access.consume_solve_slot(user_id).status == access.ImageAccessStatus.OK


