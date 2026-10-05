# -*- coding: utf-8 -*-
"""בדיקות רישום שימוש וסשן למנהל."""
from __future__ import annotations

import pytest

import bot.access as access
import bot.admin_usage as admin_usage


@pytest.fixture()
def usage_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_admin_usage.db"
    monkeypatch.setattr(access, "DB_PATH", db_path)
    access.close_access_db()
    access.init_access_db()
    yield
    access.close_access_db()


def test_record_named_action_and_ignore_unknown(usage_db):
    t0 = 1_700_000_000.0
    admin_usage.record_usage(11, "solve", now=t0)
    admin_usage.record_usage(11, "not_a_real_action", now=t0 + 1)
    counts = admin_usage.user_action_counts(11)
    assert counts["solve"] == 1
    assert sum(counts.values()) == 1


def test_records_new_product_actions(usage_db):
    t0 = 1_700_000_100.0
    admin_usage.record_usage(12, "denied", now=t0)
    admin_usage.record_usage(12, "pay", now=t0 + 1)
    admin_usage.record_usage(12, "notebook", now=t0 + 2)
    admin_usage.record_usage(12, "intro_practice", now=t0 + 3)
    counts = admin_usage.user_action_counts(12)
    assert counts["denied"] == 1
    assert counts["pay"] == 1
    assert counts["notebook"] == 1
    assert counts["intro_practice"] == 1


def test_session_gap_closes_and_sums_dwell(usage_db):
    t0 = 1_700_000_000.0
    admin_usage.touch_usage(22, now=t0)
    admin_usage.touch_usage(22, now=t0 + 120)
    dwell_open = admin_usage.user_dwell_sec(22, now=t0 + 120)
    assert dwell_open == pytest.approx(120.0)

    admin_usage.touch_usage(22, now=t0 + 120 + admin_usage.SESSION_GAP_SEC + 1)
    conn = access._connect()
    closed = conn.execute("SELECT COUNT(*) FROM admin_closed_session").fetchone()[0]
    assert closed == 1


def test_overview_counts_active_and_new(usage_db, monkeypatch):
    t0 = 1_720_000_000.0
    monkeypatch.setattr(admin_usage.time, "time", lambda: t0)
    access.ensure_user_first_seen(31, now=t0 - 3600)
    admin_usage.record_usage(31, "formulas", now=t0 - 60)
    admin_usage.record_usage(31, "denied", now=t0 - 30)
    text = admin_usage.format_overview_text(now=t0)
    assert "פעילים <b>1</b>" in text
    assert "נוסחאות — 1" in text
    assert "נחסם — 1" in text
    assert "לימוד: נוסחאות 1" in text
    assert "קשב: נחסם 1" in text
    assert "סקירה" in text
    assert "פעילים ברבע שעה" in text
    assert "פירוט:" in text


def test_overview_new_users_who_engaged(usage_db, monkeypatch):
    t0 = 1_720_000_000.0
    monkeypatch.setattr(admin_usage.time, "time", lambda: t0)
    access.ensure_user_first_seen(41, now=t0 - 120)
    access.ensure_user_first_seen(42, now=t0 - 90)
    admin_usage.record_usage(41, "start", now=t0 - 120)
    admin_usage.record_usage(41, "solve", now=t0 - 60)
    admin_usage.record_usage(42, "main", now=t0 - 80)
    text = admin_usage.format_overview_text(now=t0)
    assert "חדשים <b>2</b> · 1 כבר השתמשו" in text


def test_user_recent_events_and_card(usage_db):
    t0 = 1_720_000_000.0
    access.ensure_user_first_seen(51, username="dana", now=t0 - 86400)
    admin_usage.record_usage(51, "solve", now=t0 - 120)
    admin_usage.record_usage(51, "pay", now=t0 - 30)
    events = admin_usage.user_recent_events(51, limit=5)
    assert [action for _, action in events] == ["pay", "solve"]
    text = admin_usage.format_user_card_text(51, now=t0)
    assert text is not None
    assert "אחרונים" in text
    assert "תשלום" in text
    assert "פתרון" in text


def test_users_page_includes_last_action(usage_db):
    t0 = 1_720_000_000.0
    access.ensure_user_first_seen(61, username="lee", now=t0 - 3600)
    admin_usage.record_usage(61, "practice", now=t0 - 10)
    items, total, _summary = admin_usage.list_users_page(now=t0)
    assert total == 1
    assert items[0]["last_action"] == "practice"
    text = admin_usage.format_users_page_text(items, total, 0, now=t0)
    assert "תרגול" in text
