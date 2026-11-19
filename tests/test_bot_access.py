# -*- coding: utf-8 -*-
"""בדיקות מצבי גישה: מכסה חינמית (6 פתרונות / 6 מדריכים), חבילה, המתנה ותרגול חופשי."""
from __future__ import annotations

import pytest

import bot.access as access
import bot.config as config
from bot.generate_coupons import generate_coupon_codes

LIMIT = access.FREE_SOLUTIONS_LIMIT
T0 = 1_700_000_000.0


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
    access.close_access_db()
    access.init_access_db()
    yield
    access.close_access_db()


def _redeem(user_id: int, *, days: int = 30, now: float = T0, vip: bool = False) -> None:
    quota = access.VIP_UNLIMITED_DAILY_QUOTA if vip else 6
    code = generate_coupon_codes(count=1, daily_quota=quota, period_days=days)[0]
    assert access.redeem_coupon(code, user_id, now=now).status == access.RedeemStatus.OK


def test_new_user_starts_at_zero_and_is_free_phase(access_db):
    user_id = 1001
    access.ensure_user_first_seen(user_id, now=T0)
    assert access.get_free_usage(user_id) == (0, 0)
    assert access.get_user_access_phase(user_id, now=T0) == access.UserAccessPhase.RESTRICTED
    assert access.check_solve_access(user_id).status == access.ImageAccessStatus.OK
    assert access.check_guide_access(user_id).status == access.ImageAccessStatus.OK


def test_check_does_not_count(access_db):
    user_id = 1002
    for _ in range(10):
        access.check_solve_access(user_id)
        access.check_guide_access(user_id)
        access.check_solution_entry_access(user_id)
    assert access.get_free_usage(user_id) == (0, 0)


def test_six_solves_then_both_locked(access_db):
    user_id = 1003
    for _ in range(LIMIT):
        assert access.consume_solve_slot(user_id).status == access.ImageAccessStatus.OK
    assert access.get_free_usage(user_id) == (LIMIT, 0)

    blocked_solve = access.consume_solve_slot(user_id)
    blocked_guide = access.consume_guide_slot(user_id)
    assert blocked_solve.status == access.ImageAccessStatus.FREE_LIMIT_REACHED
    assert blocked_guide.status == access.ImageAccessStatus.FREE_LIMIT_REACHED
    assert (
        access.check_solution_entry_access(user_id).status
        == access.ImageAccessStatus.FREE_LIMIT_REACHED
    )
    # נסיון חסום לא מגדיל מונה
    assert access.get_free_usage(user_id) == (LIMIT, 0)


def test_six_guides_then_both_locked(access_db):
    user_id = 1004
    for _ in range(LIMIT):
        assert access.consume_guide_slot(user_id).status == access.ImageAccessStatus.OK
    assert access.get_free_usage(user_id) == (0, LIMIT)
    assert access.consume_solve_slot(user_id).status == access.ImageAccessStatus.FREE_LIMIT_REACHED
    assert access.consume_guide_slot(user_id).status == access.ImageAccessStatus.FREE_LIMIT_REACHED


def test_mixed_usage_below_limit_stays_open(access_db):
    user_id = 1005
    for _ in range(LIMIT - 1):
        assert access.consume_solve_slot(user_id).status == access.ImageAccessStatus.OK
        assert access.consume_guide_slot(user_id).status == access.ImageAccessStatus.OK
    assert access.get_free_usage(user_id) == (LIMIT - 1, LIMIT - 1)
    assert access.check_solve_access(user_id).status == access.ImageAccessStatus.OK
    assert access.check_guide_access(user_id).status == access.ImageAccessStatus.OK


def test_free_limit_is_lifetime(access_db, monkeypatch):
    user_id = 1006
    monkeypatch.setattr(access.time, "time", lambda: T0)
    for _ in range(LIMIT):
        access.consume_solve_slot(user_id)
    monkeypatch.setattr(access.time, "time", lambda: T0 + 365 * 86400)
    assert access.check_solve_access(user_id).status == access.ImageAccessStatus.FREE_LIMIT_REACHED


def test_limit_message_offers_packages(access_db):
    user_id = 1007
    for _ in range(LIMIT):
        access.consume_solve_slot(user_id)
    msg = access.image_access_reply_hebrew(access.check_solve_access(user_id))
    assert "חבילות" in msg
    assert str(LIMIT) in msg


def test_coupon_unlocks_after_limit_and_does_not_count(access_db, monkeypatch):
    user_id = 1008
    monkeypatch.setattr(access.time, "time", lambda: T0)
    for _ in range(LIMIT):
        access.consume_solve_slot(user_id)
    _redeem(user_id, days=30, now=T0)

    assert access.get_user_access_phase(user_id, now=T0) == access.UserAccessPhase.PRIVILEGED
    for _ in range(5):
        assert access.consume_solve_slot(user_id).status == access.ImageAccessStatus.OK
        assert access.consume_guide_slot(user_id).status == access.ImageAccessStatus.OK
    assert access.get_free_usage(user_id) == (LIMIT, 0)

    # אחרי שהחבילה פגה — חוזר לנעול
    monkeypatch.setattr(access.time, "time", lambda: T0 + 31 * 86400)
    assert access.check_solve_access(user_id).status == access.ImageAccessStatus.FREE_LIMIT_REACHED


def test_free_user_cooldown_10_minutes(cooldown_db, monkeypatch):
    user_id = 2001
    monkeypatch.setattr(access.time, "time", lambda: T0)
    assert access.consume_solve_slot(user_id).status == access.ImageAccessStatus.OK

    monkeypatch.setattr(access.time, "time", lambda: T0 + 120)
    blocked = access.consume_solve_slot(user_id)
    assert blocked.status == access.ImageAccessStatus.COOLDOWN
    assert blocked.cooldown_remaining_sec == 480.0
    assert "10 דקות" in access.image_access_reply_hebrew(blocked)
    # המתנה לא מגדילה מונה
    assert access.get_free_usage(user_id) == (1, 0)

    monkeypatch.setattr(access.time, "time", lambda: T0 + 601)
    assert access.consume_solve_slot(user_id).status == access.ImageAccessStatus.OK
    assert access.get_free_usage(user_id) == (2, 0)


def test_cooldown_is_separate_for_solve_and_guide(cooldown_db, monkeypatch):
    user_id = 2002
    monkeypatch.setattr(access.time, "time", lambda: T0)
    assert access.consume_solve_slot(user_id).status == access.ImageAccessStatus.OK
    monkeypatch.setattr(access.time, "time", lambda: T0 + 30)
    assert access.consume_guide_slot(user_id).status == access.ImageAccessStatus.OK
    assert access.check_solve_access(user_id).status == access.ImageAccessStatus.COOLDOWN
    assert access.check_guide_access(user_id).status == access.ImageAccessStatus.COOLDOWN


def test_entry_gate_open_while_one_feature_cools_down(cooldown_db, monkeypatch):
    user_id = 2003
    monkeypatch.setattr(access.time, "time", lambda: T0)
    access.consume_solve_slot(user_id)
    monkeypatch.setattr(access.time, "time", lambda: T0 + 60)
    assert access.check_solution_entry_access(user_id).status == access.ImageAccessStatus.OK

    access.consume_guide_slot(user_id)
    monkeypatch.setattr(access.time, "time", lambda: T0 + 120)
    entry = access.check_solution_entry_access(user_id)
    assert entry.status == access.ImageAccessStatus.COOLDOWN
    # הזמן הקצר מבין השניים: פתרון נפתח ב-T0+600
    assert entry.cooldown_remaining_sec == 480.0


def test_paid_user_keeps_cooldown(cooldown_db, monkeypatch):
    user_id = 2004
    monkeypatch.setattr(access.time, "time", lambda: T0)
    _redeem(user_id, days=105, now=T0)
    assert access.consume_solve_slot(user_id).status == access.ImageAccessStatus.OK
    monkeypatch.setattr(access.time, "time", lambda: T0 + 60)
    blocked = access.consume_solve_slot(user_id)
    assert blocked.status == access.ImageAccessStatus.COOLDOWN
    assert access.get_free_usage(user_id) == (0, 0)


def test_vip_has_no_cooldown(cooldown_db, monkeypatch):
    user_id = 2005
    monkeypatch.setattr(access.time, "time", lambda: T0)
    _redeem(user_id, days=120, now=T0, vip=True)
    assert access.consume_solve_slot(user_id).status == access.ImageAccessStatus.OK
    monkeypatch.setattr(access.time, "time", lambda: T0 + 5)
    assert access.consume_solve_slot(user_id).status == access.ImageAccessStatus.OK


def test_practice_and_intro_always_free(cooldown_db, monkeypatch):
    user_id = 3001
    for i in range(LIMIT):
        monkeypatch.setattr(access.time, "time", lambda i=i: T0 + i * 601)
        assert access.consume_solve_slot(user_id).status == access.ImageAccessStatus.OK
    assert access.check_solve_access(user_id).status == access.ImageAccessStatus.FREE_LIMIT_REACHED
    for _ in range(20):
        assert access.consume_practice_slot(user_id).status == access.ImageAccessStatus.OK
    assert access.check_practice_feature_access(user_id).status == access.ImageAccessStatus.OK
    assert access.has_practice_access(user_id) is True
    assert access.has_intro_access(user_id) is True
    assert access.has_formulas_access(user_id) is True


def test_quota_status_free_user_shows_counts(access_db):
    user_id = 7001
    access.consume_solve_slot(user_id)
    access.consume_guide_slot(user_id)
    access.consume_guide_slot(user_id)
    msg = access.quota_status_for_user(user_id)
    assert f"פתרונות שקיבלת: 1 מתוך {LIMIT}" in msg
    assert f"מדריכים לפתרון: 2 מתוך {LIMIT}" in msg
    assert "תרגול" in msg


def test_quota_status_paid_user(access_db):
    user_id = 7002
    _redeem(user_id, days=30, now=access.time.time())
    msg = access.quota_status_for_user(user_id)
    assert "חבילה בתוקף" in msg


def test_redeem_reply_for_3_5_months():
    res = access.RedeemResult(status=access.RedeemStatus.OK, code="X", period_days=105)
    assert "3.5 חודשים" in access.redeem_reply_hebrew(res)


def test_existing_user_db_gets_new_table(tmp_path, monkeypatch):
    import sqlite3

    db_path = tmp_path / "legacy.db"
    legacy = sqlite3.connect(db_path)
    legacy.execute(
        "CREATE TABLE user_first_seen (user_id INTEGER PRIMARY KEY, first_seen_at REAL NOT NULL)"
    )
    legacy.execute("INSERT INTO user_first_seen VALUES (5, ?)", (T0 - 90 * 86400,))
    legacy.commit()
    legacy.close()

    monkeypatch.setattr(access, "DB_PATH", db_path)
    access.close_access_db()
    access.init_access_db()
    try:
        assert access.get_free_usage(5) == (0, 0)
        assert access.check_solve_access(5).status == access.ImageAccessStatus.OK
    finally:
        access.close_access_db()


def test_list_users_first_seen_ordered(access_db, monkeypatch):
    monkeypatch.setattr(access.time, "time", lambda: T0)
    access.ensure_user_first_seen(101, username="testuser1")
    monkeypatch.setattr(access.time, "time", lambda: T0 + 60)
    access.ensure_user_first_seen(202)
    access.ensure_user_first_seen(101)
    rows = access.list_users_first_seen()
    assert rows == [(101, T0, "testuser1"), (202, T0 + 60, None)]
