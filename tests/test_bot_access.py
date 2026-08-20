# -*- coding: utf-8 -*-
"""בדיקות מצבי גישה: מועדף / מוגבל, פתרון ותרגול."""
from __future__ import annotations

import pytest

import bot.access as access
import bot.config as config


@pytest.fixture()
def access_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_access.db"
    monkeypatch.setattr(access, "DB_PATH", db_path)
    monkeypatch.setattr(config, "IMAGE_COOLDOWN_SEC", 0.0)
    monkeypatch.setattr(access, "FEATURE_COOLDOWN_SEC", 0.0)
    access.close_access_db()
    access.init_access_db()
    yield
    access.close_access_db()


@pytest.fixture()
def cooldown_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_cooldown.db"
    monkeypatch.setattr(access, "DB_PATH", db_path)
    monkeypatch.setattr(config, "IMAGE_COOLDOWN_SEC", 600.0)
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


def test_restricted_after_free_window(access_db, monkeypatch):
    user_id = 1002
    t0 = 1_700_000_000.0
    monkeypatch.setattr(access.time, "time", lambda: t0)
    access.ensure_user_first_seen(user_id)
    monkeypatch.setattr(
        access.time, "time", lambda: t0 + access.FORMULAS_FREE_WINDOW_SEC + 10
    )
    assert access.get_user_access_phase(user_id) == access.UserAccessPhase.RESTRICTED


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


def test_daily_limit_reply(access_db, monkeypatch):
    user_id = 2003
    t0 = 1_700_000_000.0
    monkeypatch.setattr(access.time, "time", lambda: t0)
    access.ensure_user_first_seen(user_id)
    monkeypatch.setattr(
        access.time, "time", lambda: t0 + access.FORMULAS_FREE_WINDOW_SEC + 10
    )
    assert access.consume_solve_slot(user_id).status == access.ImageAccessStatus.OK
    blocked = access.consume_solve_slot(user_id)
    assert blocked.status == access.ImageAccessStatus.DAILY_LIMIT
    msg = access.image_access_reply_hebrew(blocked)
    assert "מגבלת" in msg


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


def test_quota_status_for_user_mentions_both_features(access_db, monkeypatch):
    user_id = 7001
    t0 = 1_700_000_000.0
    monkeypatch.setattr(access.time, "time", lambda: t0)
    access.ensure_user_first_seen(user_id)
    msg = access.quota_status_for_user(user_id)
    assert "פתרון" in msg
    assert "תרגול" in msg


def test_list_users_first_seen_ordered(access_db, monkeypatch):
    t0 = 1_700_000_000.0
    monkeypatch.setattr(access.time, "time", lambda: t0)
    access.ensure_user_first_seen(101, username="testuser1")
    monkeypatch.setattr(access.time, "time", lambda: t0 + 60)
    access.ensure_user_first_seen(202)
    access.ensure_user_first_seen(101)
    rows = access.list_users_first_seen()
    assert rows == [(101, t0, "testuser1"), (202, t0 + 60, None)]



def test_10min_cooldown_enforced_always_except_vip(access_db, monkeypatch):
    user_id = 9001
    t0 = 1_700_000_000.0
    monkeypatch.setattr(access, "FEATURE_COOLDOWN_SEC", 600.0)
    monkeypatch.setattr(access.time, "time", lambda: t0)
    access.ensure_user_first_seen(user_id)

    # 1. בחלון חינם 24ש' — 10 דקות צינון בין תרגול לתרגול ובין פתרון לפתרון
    assert access.consume_practice_slot(user_id).status == access.ImageAccessStatus.OK
    # 2 דקות אחרי — חסום בצינון
    monkeypatch.setattr(access.time, "time", lambda: t0 + 120)
    cool_res = access.consume_practice_slot(user_id)
    assert cool_res.status == access.ImageAccessStatus.COOLDOWN
    assert cool_res.cooldown_remaining_sec == 480.0

    # 11 דקות אחרי — שוב פתוח
    monkeypatch.setattr(access.time, "time", lambda: t0 + 660)
    assert access.consume_practice_slot(user_id).status == access.ImageAccessStatus.OK

    # 2. כנ"ל לגבי פתרון
    t_solve = t0 + 660
    assert access.consume_solve_slot(user_id).status == access.ImageAccessStatus.OK
    monkeypatch.setattr(access.time, "time", lambda: t_solve + 100)
    assert access.consume_solve_slot(user_id).status == access.ImageAccessStatus.COOLDOWN


def test_has_intro_access_rules(access_db, monkeypatch):
    user_id = 9901
    t0 = 1_700_000_000.0
    monkeypatch.setattr(access.time, "time", lambda: t0)
    access.ensure_user_first_seen(user_id, now=t0)

    # בחלון 24ש' ראשונות — פתוח
    assert access.has_intro_access(user_id, now=t0 + 3600) is True

    # אחרי 24ש' ללא קופון — חסום
    t_expired = t0 + access.FORMULAS_FREE_WINDOW_SEC + 100
    assert access.has_intro_access(user_id, now=t_expired) is False

    # עם קופון — פתוח שוב
    from bot.generate_coupons import generate_coupon_codes
    code = generate_coupon_codes(count=1, period_days=30)[0]
    access.redeem_coupon(code, user_id, now=t_expired)
    assert access.has_intro_access(user_id, now=t_expired) is True



