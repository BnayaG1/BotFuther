# -*- coding: utf-8 -*-
"""בדיקות מכסת תמונות וגישת אורח / קופון."""
from __future__ import annotations

import pytest

import bot.access as access
import bot.config as config


@pytest.fixture()
def trial_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_coupons.db"
    monkeypatch.setattr(config, "COUPON_DB_PATH", db_path)
    monkeypatch.setattr(config, "FREE_TRIAL_IMAGES", 2)
    monkeypatch.setattr(config, "IMAGE_COOLDOWN_SEC", 0.0)
    monkeypatch.setattr(config, "IMAGE_GUEST_COOLDOWN_SEC", 0.0)
    monkeypatch.setattr(access, "COUPON_DB_PATH", db_path)
    monkeypatch.setattr(access, "FREE_TRIAL_IMAGES", 2)
    monkeypatch.setattr(access, "IMAGE_COOLDOWN_SEC", 0.0)
    monkeypatch.setattr(access, "IMAGE_GUEST_COOLDOWN_SEC", 0.0)
    access.close_access_db()
    access.init_access_db()
    yield
    access.close_access_db()


@pytest.fixture()
def cooldown_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_cooldown.db"
    monkeypatch.setattr(config, "COUPON_DB_PATH", db_path)
    monkeypatch.setattr(config, "FREE_TRIAL_IMAGES", 2)
    monkeypatch.setattr(config, "IMAGE_COOLDOWN_SEC", 600.0)
    monkeypatch.setattr(config, "IMAGE_GUEST_COOLDOWN_SEC", 1200.0)
    monkeypatch.setattr(access, "COUPON_DB_PATH", db_path)
    monkeypatch.setattr(access, "FREE_TRIAL_IMAGES", 2)
    monkeypatch.setattr(access, "IMAGE_COOLDOWN_SEC", 600.0)
    monkeypatch.setattr(access, "IMAGE_GUEST_COOLDOWN_SEC", 1200.0)
    access.close_access_db()
    access.init_access_db()
    yield
    access.close_access_db()


def test_guest_can_send_unlimited_images_without_coupon(trial_db):
    user_id = 1001
    first = access.consume_image_slot(user_id)
    assert first.status == access.ImageAccessStatus.OK
    assert first.access_source == access.AccessSource.GUEST
    assert first.images_used == 1

    second = access.consume_image_slot(user_id)
    assert second.status == access.ImageAccessStatus.OK
    assert second.images_used == 2

    third = access.consume_image_slot(user_id)
    assert third.status == access.ImageAccessStatus.OK
    assert third.images_used == 3
    assert third.access_source == access.AccessSource.GUEST


def test_check_guest_without_consuming(trial_db):
    user_id = 2002
    check = access.check_image_access(user_id)
    assert check.status == access.ImageAccessStatus.OK
    assert check.access_source == access.AccessSource.GUEST

    access.consume_image_slot(user_id)
    check2 = access.check_image_access(user_id)
    assert check2.status == access.ImageAccessStatus.OK
    assert check2.images_used == 1


def test_coupon_overrides_guest(trial_db):
    user_id = 3003
    access.insert_coupon_codes(
        ["TESTCODE12"],
        daily_quota=6,
        period_days=105,
    )
    result = access.redeem_coupon("TESTCODE12", user_id)
    assert result.status == access.RedeemStatus.OK
    assert result.period_days == 105
    assert result.period_expires_at is not None

    access.consume_image_slot(user_id)
    access.consume_image_slot(user_id)

    check = access.check_image_access(user_id)
    assert check.access_source == access.AccessSource.COUPON
    assert check.images_remaining == 4
    assert check.period_expires_sec is not None
    assert check.period_expires_sec > 0


def test_expired_coupon_access_falls_back_to_guest(trial_db, monkeypatch):
    user_id = 4004
    access.insert_coupon_codes(
        ["EXPIRECODE1"],
        daily_quota=6,
        period_days=105,
    )
    redeem = access.redeem_coupon("EXPIRECODE1", user_id)
    assert redeem.period_expires_at is not None

    monkeypatch.setattr(access.time, "time", lambda: redeem.period_expires_at + 1)

    check = access.check_image_access(user_id)
    assert check.access_source == access.AccessSource.GUEST
    assert check.status == access.ImageAccessStatus.OK

    quota_msg = access.quota_status_reply_hebrew(check)
    assert "חופשית" in quota_msg or "המתנה" in quota_msg


def test_trial_exhausted_reply_mentions_options(trial_db):
    msg = access.image_access_reply_hebrew(
        access.ImageAccessResult(access.ImageAccessStatus.TRIAL_EXHAUSTED)
    )
    assert "2" in msg
    assert "אפשרויות" in msg


def test_guest_cooldown_is_20_minutes(cooldown_db, monkeypatch):
    user_id = 5005
    t0 = 1_700_000_000.0
    monkeypatch.setattr(access.time, "time", lambda: t0)
    first = access.consume_image_slot(user_id)
    assert first.status == access.ImageAccessStatus.OK
    assert first.access_source == access.AccessSource.GUEST

    monkeypatch.setattr(access.time, "time", lambda: t0 + 600)
    blocked = access.consume_image_slot(user_id)
    assert blocked.status == access.ImageAccessStatus.COOLDOWN
    assert blocked.cooldown_remaining_sec is not None
    assert blocked.cooldown_remaining_sec > 500

    msg = access.image_access_reply_hebrew(blocked)
    assert "20 דקות" in msg

    monkeypatch.setattr(access.time, "time", lambda: t0 + 1201)
    allowed = access.consume_image_slot(user_id)
    assert allowed.status == access.ImageAccessStatus.OK
    assert allowed.images_used == 2


def test_coupon_cooldown_is_10_minutes(cooldown_db, monkeypatch):
    user_id = 6006
    access.insert_coupon_codes(
        ["COOLCODE01"],
        daily_quota=6,
        period_days=105,
    )
    assert access.redeem_coupon("COOLCODE01", user_id).status == access.RedeemStatus.OK

    t0 = 1_700_000_000.0
    monkeypatch.setattr(access.time, "time", lambda: t0)
    first = access.consume_image_slot(user_id)
    assert first.status == access.ImageAccessStatus.OK

    monkeypatch.setattr(access.time, "time", lambda: t0 + 60)
    blocked = access.consume_image_slot(user_id)
    assert blocked.status == access.ImageAccessStatus.COOLDOWN
    msg = access.image_access_reply_hebrew(blocked)
    assert "10 דקות" in msg

    monkeypatch.setattr(access.time, "time", lambda: t0 + 601)
    allowed = access.consume_image_slot(user_id)
    assert allowed.status == access.ImageAccessStatus.OK
    assert allowed.images_used == 2


def test_vip_coupon_unlocks_bank_and_skips_cooldown(cooldown_db):
    user_id = 7007
    access.insert_coupon_codes(
        ["VIPCODE1001"],
        daily_quota=access.VIP_UNLIMITED_DAILY_QUOTA,
        period_days=100,
    )
    result = access.redeem_coupon("VIPCODE1001", user_id)
    assert result.status == access.RedeemStatus.OK
    assert result.period_days == 100
    assert access.user_has_bank_unlock(user_id)

    first = access.consume_image_slot(user_id)
    assert first.status == access.ImageAccessStatus.OK
    second = access.consume_image_slot(user_id)
    assert second.status == access.ImageAccessStatus.OK
    reply = access.redeem_reply_hebrew(result)
    assert "מאגר" in reply
    assert "חופשית" in reply or "חופשי" in reply


def test_formulas_free_window_first_24h(trial_db, monkeypatch):
    """חלון נוסחאות: first_seen_at קבוע; פתוח 24ש', נעול אחרי כן בלי קופון."""
    user_id = 8008
    t0 = 1_700_000_000.0
    monkeypatch.setattr(access.time, "time", lambda: t0)

    first = access.ensure_user_first_seen(user_id)
    assert first == t0
    # קריאה חוזרת לא מזיזה את השעון
    monkeypatch.setattr(access.time, "time", lambda: t0 + 3600)
    assert access.ensure_user_first_seen(user_id) == t0

    assert access.has_formulas_free_window(user_id, now=t0 + 100) is True
    assert access.has_formulas_access(user_id) is True

    monkeypatch.setattr(
        access.time, "time", lambda: t0 + access.FORMULAS_FREE_WINDOW_SEC + 1
    )
    assert access.has_formulas_free_window(user_id) is False
    assert access.has_active_coupon_access(user_id) is False
    assert access.has_formulas_access(user_id) is False


def test_formulas_access_via_coupon_after_free_window(trial_db, monkeypatch):
    user_id = 9009
    t0 = 1_700_000_000.0
    monkeypatch.setattr(access.time, "time", lambda: t0)
    access.ensure_user_first_seen(user_id)

    monkeypatch.setattr(
        access.time, "time", lambda: t0 + access.FORMULAS_FREE_WINDOW_SEC + 10
    )
    assert access.has_formulas_access(user_id) is False

    access.insert_coupon_codes(
        ["FORMCODE01"],
        daily_quota=6,
        period_days=105,
    )
    assert access.redeem_coupon("FORMCODE01", user_id).status == access.RedeemStatus.OK
    assert access.has_formulas_access(user_id) is True
