# -*- coding: utf-8 -*-
"""בדיקות מצבי גישה: מועדף / מוגבל, פתרון ותרגול."""
from __future__ import annotations

import pytest

import bot.access as access
import bot.config as config


@pytest.fixture()
def access_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_coupons.db"
    monkeypatch.setattr(config, "COUPON_DB_PATH", db_path)
    monkeypatch.setattr(config, "IMAGE_COOLDOWN_SEC", 0.0)
    monkeypatch.setattr(access, "COUPON_DB_PATH", db_path)
    monkeypatch.setattr(access, "FEATURE_COOLDOWN_SEC", 0.0)
    access.close_access_db()
    access.init_access_db()
    yield
    access.close_access_db()


@pytest.fixture()
def cooldown_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_cooldown.db"
    monkeypatch.setattr(config, "COUPON_DB_PATH", db_path)
    monkeypatch.setattr(config, "IMAGE_COOLDOWN_SEC", 600.0)
    monkeypatch.setattr(access, "COUPON_DB_PATH", db_path)
    monkeypatch.setattr(access, "FEATURE_COOLDOWN_SEC", 600.0)
    monkeypatch.setattr(access, "FEATURE_DAILY_LIMIT_SEC", 24 * 3600.0)
    access.close_access_db()
    access.init_access_db()
    yield
    access.close_access_db()


def test_free_window_is_privileged(access_db, monkeypatch):
    user_id = 1001
    t0 = 1_700_000_000.0
    monkeypatch.setattr(access.time, "time", lambda: t0)
    access.ensure_user_first_seen(user_id)
    assert access.get_user_access_phase(user_id) == access.UserAccessPhase.PRIVILEGED
    assert access.consume_solve_slot(user_id).status == access.ImageAccessStatus.OK
    assert access.consume_practice_slot(user_id).status == access.ImageAccessStatus.OK


def test_restricted_after_free_window_without_coupon(access_db, monkeypatch):
    user_id = 1002
    t0 = 1_700_000_000.0
    monkeypatch.setattr(access.time, "time", lambda: t0)
    access.ensure_user_first_seen(user_id)
    monkeypatch.setattr(
        access.time, "time", lambda: t0 + access.FORMULAS_FREE_WINDOW_SEC + 10
    )
    assert access.get_user_access_phase(user_id) == access.UserAccessPhase.RESTRICTED


def test_coupon_is_privileged_after_free_window(access_db, monkeypatch):
    user_id = 1003
    t0 = 1_700_000_000.0
    monkeypatch.setattr(access.time, "time", lambda: t0)
    access.ensure_user_first_seen(user_id)
    monkeypatch.setattr(
        access.time, "time", lambda: t0 + access.FORMULAS_FREE_WINDOW_SEC + 10
    )
    access.insert_coupon_codes(["TESTCODE12"], daily_quota=6, period_days=105)
    assert access.redeem_coupon("TESTCODE12", user_id).status == access.RedeemStatus.OK
    assert access.get_user_access_phase(user_id) == access.UserAccessPhase.PRIVILEGED


def test_privileged_solve_cooldown_10_minutes(cooldown_db, monkeypatch):
    user_id = 2001
    t0 = 1_700_000_000.0
    monkeypatch.setattr(access.time, "time", lambda: t0)
    access.ensure_user_first_seen(user_id)
    assert access.consume_solve_slot(user_id).status == access.ImageAccessStatus.OK

    monkeypatch.setattr(access.time, "time", lambda: t0 + 60)
    blocked = access.consume_solve_slot(user_id)
    assert blocked.status == access.ImageAccessStatus.COOLDOWN
    msg = access.image_access_reply_hebrew(blocked)
    assert "10 דקות" in msg

    monkeypatch.setattr(access.time, "time", lambda: t0 + 601)
    assert access.consume_solve_slot(user_id).status == access.ImageAccessStatus.OK


def test_restricted_solve_once_per_day(cooldown_db, monkeypatch):
    user_id = 2002
    t0 = 1_700_000_000.0
    monkeypatch.setattr(access.time, "time", lambda: t0)
    access.ensure_user_first_seen(user_id)
    monkeypatch.setattr(
        access.time, "time", lambda: t0 + access.FORMULAS_FREE_WINDOW_SEC + 10
    )
    t1 = t0 + access.FORMULAS_FREE_WINDOW_SEC + 10
    assert access.consume_solve_slot(user_id).status == access.ImageAccessStatus.OK

    monkeypatch.setattr(access.time, "time", lambda: t1 + 700)
    blocked = access.consume_solve_slot(user_id)
    assert blocked.status == access.ImageAccessStatus.DAILY_LIMIT

    monkeypatch.setattr(access.time, "time", lambda: t1 + access.FEATURE_DAILY_LIMIT_SEC + 1)
    assert access.consume_solve_slot(user_id).status == access.ImageAccessStatus.OK


def test_solve_and_practice_counters_are_independent(access_db, monkeypatch):
    user_id = 3001
    t0 = 1_700_000_000.0
    monkeypatch.setattr(access.time, "time", lambda: t0)
    access.ensure_user_first_seen(user_id)
    monkeypatch.setattr(
        access.time, "time", lambda: t0 + access.FORMULAS_FREE_WINDOW_SEC + 10
    )
    assert access.consume_solve_slot(user_id).status == access.ImageAccessStatus.OK
    # תרגול עדיין מותר — מונים נפרדים
    assert access.consume_practice_slot(user_id).status == access.ImageAccessStatus.OK
    assert access.consume_practice_slot(user_id).status == access.ImageAccessStatus.DAILY_LIMIT
    assert access.consume_solve_slot(user_id).status == access.ImageAccessStatus.DAILY_LIMIT


def test_formulas_always_open(access_db, monkeypatch):
    user_id = 4001
    t0 = 1_700_000_000.0
    monkeypatch.setattr(access.time, "time", lambda: t0)
    access.ensure_user_first_seen(user_id)
    assert access.has_formulas_access(user_id) is True
    monkeypatch.setattr(
        access.time, "time", lambda: t0 + access.FORMULAS_FREE_WINDOW_SEC + 10
    )
    assert access.has_formulas_access(user_id) is True


def test_vip_coupon_still_unlocks_bank(cooldown_db):
    user_id = 5001
    access.insert_coupon_codes(
        ["VIPCODE1001"],
        daily_quota=access.VIP_UNLIMITED_DAILY_QUOTA,
        period_days=100,
    )
    result = access.redeem_coupon("VIPCODE1001", user_id)
    assert result.status == access.RedeemStatus.OK
    assert access.user_has_bank_unlock(user_id)
    # VIP לא פוטר מ־cooldown של פתרון
    first = access.consume_solve_slot(user_id)
    assert first.status == access.ImageAccessStatus.OK
    second = access.consume_solve_slot(user_id)
    assert second.status == access.ImageAccessStatus.COOLDOWN


def test_expired_coupon_falls_back_to_restricted(access_db, monkeypatch):
    user_id = 6001
    t0 = 1_700_000_000.0
    monkeypatch.setattr(access.time, "time", lambda: t0)
    access.ensure_user_first_seen(user_id)
    monkeypatch.setattr(
        access.time, "time", lambda: t0 + access.FORMULAS_FREE_WINDOW_SEC + 10
    )
    access.insert_coupon_codes(["EXPIRECODE1"], daily_quota=6, period_days=105)
    redeem = access.redeem_coupon("EXPIRECODE1", user_id)
    assert redeem.period_expires_at is not None
    monkeypatch.setattr(access.time, "time", lambda: redeem.period_expires_at + 1)
    assert access.get_user_access_phase(user_id) == access.UserAccessPhase.RESTRICTED


def test_quota_status_for_user_mentions_both_features(access_db, monkeypatch):
    user_id = 7001
    t0 = 1_700_000_000.0
    monkeypatch.setattr(access.time, "time", lambda: t0)
    access.ensure_user_first_seen(user_id)
    msg = access.quota_status_for_user(user_id)
    assert "פתרון" in msg
    assert "תרגול" in msg
