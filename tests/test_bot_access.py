# -*- coding: utf-8 -*-
"""בדיקות מכסת תמונות וניסיון חינם."""
from __future__ import annotations

import pytest

import bot.access as access
import bot.config as config


@pytest.fixture()
def trial_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_coupons.db"
    monkeypatch.setattr(config, "COUPON_DB_PATH", db_path)
    monkeypatch.setattr(config, "FREE_TRIAL_IMAGES", 2)
    monkeypatch.setattr(access, "COUPON_DB_PATH", db_path)
    monkeypatch.setattr(access, "FREE_TRIAL_IMAGES", 2)
    access.close_access_db()
    access.init_access_db()
    yield
    access.close_access_db()


def test_new_user_gets_two_trial_images(trial_db):
    user_id = 1001
    first = access.consume_image_slot(user_id)
    assert first.status == access.ImageAccessStatus.OK
    assert first.images_remaining == 1
    assert first.access_source == access.AccessSource.TRIAL

    second = access.consume_image_slot(user_id)
    assert second.status == access.ImageAccessStatus.OK
    assert second.images_remaining == 0

    third = access.consume_image_slot(user_id)
    assert third.status == access.ImageAccessStatus.TRIAL_EXHAUSTED


def test_check_trial_without_consuming(trial_db):
    user_id = 2002
    check = access.check_image_access(user_id)
    assert check.status == access.ImageAccessStatus.OK
    assert check.images_remaining == 2

    access.consume_image_slot(user_id)
    check2 = access.check_image_access(user_id)
    assert check2.images_remaining == 1


def test_coupon_overrides_trial(trial_db):
    user_id = 3003
    access.insert_coupon_codes(
        ["TESTCODE12"],
        daily_quota=5,
        period_days=30,
    )
    result = access.redeem_coupon("TESTCODE12", user_id)
    assert result.status == access.RedeemStatus.OK
    assert result.period_days == 30
    assert result.period_expires_at is not None

    access.consume_image_slot(user_id)
    access.consume_image_slot(user_id)

    check = access.check_image_access(user_id)
    assert check.access_source == access.AccessSource.COUPON
    assert check.images_remaining == 3
    assert check.period_expires_sec is not None
    assert check.period_expires_sec > 0


def test_expired_coupon_access_falls_back_to_trial(trial_db, monkeypatch):
    user_id = 4004
    access.insert_coupon_codes(
        ["EXPIRECODE1"],
        daily_quota=2,
        period_days=30,
    )
    redeem = access.redeem_coupon("EXPIRECODE1", user_id)
    assert redeem.period_expires_at is not None

    monkeypatch.setattr(access.time, "time", lambda: redeem.period_expires_at + 1)

    check = access.check_image_access(user_id)
    assert check.access_source == access.AccessSource.TRIAL
    assert check.images_remaining == 2

    quota_msg = access.quota_status_reply_hebrew(check)
    assert "ניסיון" in quota_msg


def test_trial_exhausted_reply_mentions_options(trial_db):
    msg = access.image_access_reply_hebrew(
        access.ImageAccessResult(access.ImageAccessStatus.TRIAL_EXHAUSTED)
    )
    assert "2" in msg
    assert "אפשרויות" in msg
