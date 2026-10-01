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
    text = admin_usage.format_overview_text(now=t0)
    assert "פעילים: <b>1</b>" in text
    assert "נוסחאות — 1" in text
    assert "סקירה" in text
