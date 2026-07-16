# -*- coding: utf-8 -*-
"""בדיקות למאגר התרגילים המוכנים (bot/exercise_bank.py)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import bot.config as config
import bot.exercise_bank as exercise_bank

SIMPLY_SUPPORTED_EXTRACTED = {
    "exercise_type": "beam",
    "beam": {
        "L": 5.0,
        "support_mode": "simply_supported",
        "supports": [
            {"label": "A", "type": "pin", "x": 0.0},
            {"label": "B", "type": "roller", "x": 5.0},
        ],
        "loads": [{"type": "point", "x": 2.0, "Fy": 1.0}],
    },
}

CANTILEVER_EXTRACTED = {
    "exercise_type": "beam",
    "beam": {
        "L": 4.0,
        "support_mode": "cantilever",
        "supports": [{"label": "A", "type": "fixed", "x": 0.0}],
        "loads": [{"type": "point", "x": 4.0, "Fy": 2.0}],
    },
}


@pytest.fixture()
def bank_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_exercises.db"
    images_dir = tmp_path / "exercise_bank_images"
    monkeypatch.setattr(config, "EXERCISE_BANK_DB_PATH", db_path)
    monkeypatch.setattr(config, "EXERCISE_BANK_IMAGES_DIR", images_dir)
    monkeypatch.setattr(exercise_bank, "EXERCISE_BANK_DB_PATH", db_path)
    monkeypatch.setattr(exercise_bank, "EXERCISE_BANK_IMAGES_DIR", images_dir)
    exercise_bank.close_exercise_bank_db()
    exercise_bank.init_exercise_bank_db()
    yield
    exercise_bank.close_exercise_bank_db()


def test_count_exercises_starts_empty(bank_db):
    assert exercise_bank.count_exercises() == 0
    assert exercise_bank.get_random_exercise() is None


def test_add_exercise_returns_incrementing_ids(bank_db):
    first_id = exercise_bank.add_exercise(SIMPLY_SUPPORTED_EXTRACTED, added_by_user_id=1)
    second_id = exercise_bank.add_exercise(CANTILEVER_EXTRACTED, added_by_user_id=2)
    assert second_id == first_id + 1
    assert exercise_bank.count_exercises() == 2


def test_get_exercise_by_id_roundtrips_extracted_dict(bank_db):
    exercise_id = exercise_bank.add_exercise(SIMPLY_SUPPORTED_EXTRACTED, added_by_user_id=7)
    stored = exercise_bank.get_exercise_by_id(exercise_id)
    assert stored == SIMPLY_SUPPORTED_EXTRACTED


def test_add_exercise_derives_beam_kind_column(bank_db):
    simply_id = exercise_bank.add_exercise(SIMPLY_SUPPORTED_EXTRACTED)
    cantilever_id = exercise_bank.add_exercise(CANTILEVER_EXTRACTED)

    conn = exercise_bank._connect()
    rows = {
        row["id"]: row["beam_kind"]
        for row in conn.execute("SELECT id, beam_kind FROM exercises")
    }
    assert rows[simply_id] == "simply_supported"
    assert rows[cantilever_id] == "cantilever"


def test_get_exercise_by_id_missing_returns_none(bank_db):
    assert exercise_bank.get_exercise_by_id(999) is None


def test_get_random_exercise_returns_id_and_dict(bank_db):
    exercise_id = exercise_bank.add_exercise(CANTILEVER_EXTRACTED, added_by_user_id=3)
    result = exercise_bank.get_random_exercise()
    assert result is not None
    got_id, got_extracted = result
    assert got_id == exercise_id
    assert got_extracted == CANTILEVER_EXTRACTED


def test_pick_next_exercise_returns_none_when_bank_empty(bank_db):
    assert exercise_bank.pick_next_exercise_for_user(1) is None


def test_pick_next_exercise_avoids_repeats_until_exhausted(bank_db):
    id_a = exercise_bank.add_exercise(SIMPLY_SUPPORTED_EXTRACTED)
    id_b = exercise_bank.add_exercise(CANTILEVER_EXTRACTED)
    user_id = 321

    first_id, _ = exercise_bank.pick_next_exercise_for_user(user_id)
    second_id, _ = exercise_bank.pick_next_exercise_for_user(user_id)

    assert {first_id, second_id} == {id_a, id_b}


def test_pick_next_exercise_recycles_after_all_sent(bank_db):
    exercise_bank.add_exercise(SIMPLY_SUPPORTED_EXTRACTED)
    exercise_bank.add_exercise(CANTILEVER_EXTRACTED)
    user_id = 654

    seen = {
        exercise_bank.pick_next_exercise_for_user(user_id)[0],
        exercise_bank.pick_next_exercise_for_user(user_id)[0],
    }
    assert len(seen) == 2

    # כל התרגילים נשלחו — הבחירה הבאה ממחזרת ובוחרת מכל המאגר מחדש.
    third_id, _ = exercise_bank.pick_next_exercise_for_user(user_id)
    assert third_id in seen


def test_pick_next_exercise_is_independent_per_user(bank_db):
    id_a = exercise_bank.add_exercise(SIMPLY_SUPPORTED_EXTRACTED)
    exercise_bank.add_exercise(CANTILEVER_EXTRACTED)

    picked_for_user_1, _ = exercise_bank.pick_next_exercise_for_user(1)
    exercise_bank.reset_sent_exercises_for_user(1)
    picked_for_user_2, _ = exercise_bank.pick_next_exercise_for_user(2)

    assert picked_for_user_1 in (id_a, id_a + 1)
    assert picked_for_user_2 in (id_a, id_a + 1)


def test_exercise_bank_cooldown_none_before_first_pick(bank_db, monkeypatch):
    monkeypatch.setattr(exercise_bank, "EXERCISE_BANK_COOLDOWN_SEC", 1200.0)
    exercise_bank.add_exercise(SIMPLY_SUPPORTED_EXTRACTED)
    assert exercise_bank.exercise_bank_cooldown_remaining_sec(42) is None


def test_exercise_bank_cooldown_blocks_then_clears(bank_db, monkeypatch):
    monkeypatch.setattr(exercise_bank, "EXERCISE_BANK_COOLDOWN_SEC", 1200.0)
    exercise_bank.add_exercise(SIMPLY_SUPPORTED_EXTRACTED)
    exercise_bank.add_exercise(CANTILEVER_EXTRACTED)
    user_id = 777
    t0 = 1_700_000_000.0
    monkeypatch.setattr(exercise_bank.time, "time", lambda: t0)
    exercise_bank.pick_next_exercise_for_user(user_id)

    cool = exercise_bank.exercise_bank_cooldown_remaining_sec(user_id, now=t0 + 60)
    assert cool is not None
    assert cool > 1100

    assert (
        exercise_bank.exercise_bank_cooldown_remaining_sec(user_id, now=t0 + 1201)
        is None
    )


@pytest.mark.anyio
async def test_deliver_exercise_bank_after_approve_saves_and_confirms(bank_db):
    context = MagicMock()
    context.bot.delete_message = AsyncMock()
    send_text = AsyncMock(return_value=MagicMock(message_id=555))
    edit_draft = AsyncMock()

    await exercise_bank.deliver_exercise_bank_after_approve(
        context,
        4242,
        extracted=SIMPLY_SUPPORTED_EXTRACTED,
        reply="ok",
        solved={"result": {"reactions_ton": {}}},
        draft_msg_id=99,
        send_text=send_text,
        edit_draft_message=edit_draft,
    )

    assert exercise_bank.count_exercises() == 1
    stored = exercise_bank.get_exercise_by_id(1)
    assert stored == SIMPLY_SUPPORTED_EXTRACTED

    context.bot.delete_message.assert_awaited_once_with(chat_id=4242, message_id=99)
    send_text.assert_awaited_once()
    confirmation = send_text.await_args.args[2]
    assert "נוסף למאגר" in confirmation
    edit_draft.assert_not_awaited()


def test_add_exercise_stores_image_alongside_data(bank_db, tmp_path):
    src = tmp_path / "user_photo.jpg"
    src.write_bytes(b"fake-jpeg-bytes")

    exercise_id = exercise_bank.add_exercise(
        SIMPLY_SUPPORTED_EXTRACTED,
        added_by_user_id=9,
        image_source=src,
    )
    stored = exercise_bank.get_exercise_image_path(exercise_id)
    assert stored is not None
    assert stored.is_file()
    assert stored.read_bytes() == b"fake-jpeg-bytes"
    assert stored.name.startswith(str(exercise_id))


def test_get_exercise_image_path_returns_none_without_image(bank_db):
    exercise_id = exercise_bank.add_exercise(SIMPLY_SUPPORTED_EXTRACTED)
    assert exercise_bank.get_exercise_image_path(exercise_id) is None


@pytest.mark.anyio
async def test_deliver_exercise_bank_after_approve_persists_pending_image(
    bank_db, tmp_path
):
    import bot.solution_session as solution_session

    chat_id = 4245
    pending = tmp_path / "pending_bank.jpg"
    pending.write_bytes(b"original-user-photo")
    solution_session.set_pending_bank_submission_image(chat_id, pending)

    context = MagicMock()
    context.bot.delete_message = AsyncMock()
    send_text = AsyncMock(return_value=MagicMock(message_id=560))
    edit_draft = AsyncMock()

    await exercise_bank.deliver_exercise_bank_after_approve(
        context,
        chat_id,
        extracted=CANTILEVER_EXTRACTED,
        reply="ok",
        solved={"result": {"reactions_ton": {}}},
        draft_msg_id=88,
        send_text=send_text,
        edit_draft_message=edit_draft,
    )

    assert exercise_bank.count_exercises() == 1
    stored = exercise_bank.get_exercise_image_path(1)
    assert stored is not None
    assert stored.read_bytes() == b"original-user-photo"
    assert not pending.exists()
    assert solution_session.peek_pending_bank_submission_image(chat_id) is None


@pytest.mark.anyio
async def test_deliver_duplicate_clears_pending_image_without_saving(
    bank_db, tmp_path
):
    import bot.solution_session as solution_session

    chat_id = 4246
    exercise_bank.add_exercise(SIMPLY_SUPPORTED_EXTRACTED, added_by_user_id=1)
    pending = tmp_path / "dup_pending.jpg"
    pending.write_bytes(b"should-be-deleted")
    solution_session.set_pending_bank_submission_image(chat_id, pending)

    context = MagicMock()
    context.bot.delete_message = AsyncMock()
    send_text = AsyncMock(return_value=MagicMock(message_id=561))
    edit_draft = AsyncMock()

    import copy

    await exercise_bank.deliver_exercise_bank_after_approve(
        context,
        chat_id,
        extracted=copy.deepcopy(SIMPLY_SUPPORTED_EXTRACTED),
        reply="ok",
        solved={"result": {"reactions_ton": {}}},
        draft_msg_id=90,
        send_text=send_text,
        edit_draft_message=edit_draft,
    )

    assert exercise_bank.count_exercises() == 1
    assert not pending.exists()
    assert solution_session.peek_pending_bank_submission_image(chat_id) is None


def test_find_duplicate_exercise_returns_none_when_bank_empty(bank_db):
    assert exercise_bank.find_duplicate_exercise(SIMPLY_SUPPORTED_EXTRACTED) is None


def test_find_duplicate_exercise_detects_identical_data(bank_db):
    existing_id = exercise_bank.add_exercise(SIMPLY_SUPPORTED_EXTRACTED, added_by_user_id=1)
    import copy

    same_data = copy.deepcopy(SIMPLY_SUPPORTED_EXTRACTED)
    assert exercise_bank.find_duplicate_exercise(same_data) == existing_id


def test_find_duplicate_exercise_ignores_metadata_and_load_order(bank_db):
    """הודעות/uncertainties/סדר עומסים לא רלוונטיים — רק הנתונים ההנדסיים."""
    original = {
        "exercise_type": "beam",
        "notes": "טקסט מקורי",
        "confidence": "high",
        "beam": {
            "L": 5.0,
            "support_mode": "simply_supported",
            "supports": [
                {"label": "A", "type": "pin", "x": 0.0},
                {"label": "B", "type": "roller", "x": 5.0},
            ],
            "loads": [
                {"type": "point", "x": 2.0, "Fy": 1.0},
                {"type": "moment", "x": 4.0, "M": 3.0},
            ],
        },
    }
    existing_id = exercise_bank.add_exercise(original, added_by_user_id=1)

    reordered_with_different_metadata = {
        "exercise_type": "beam",
        "notes": "טקסט שונה לגמרי מהתמונה החדשה",
        "confidence": "medium",
        "uncertainties": [{"question_he": "לא ברור"}],
        "beam": {
            "L": 5.001,  # הבדל זעיר (עיגול) — עדיין נחשב זהה
            "support_mode": "simply_supported",
            "supports": [
                {"label": "B", "type": "roller", "x": 5.0},
                {"label": "A", "type": "pin", "x": 0.0},
            ],
            "loads": [
                {"type": "moment", "x": 4.0, "M": 3.0},
                {"type": "point", "x": 2.0, "Fy": 1.0, "_draft_new": False},
            ],
        },
    }
    assert exercise_bank.find_duplicate_exercise(reordered_with_different_metadata) == existing_id


def test_find_duplicate_exercise_returns_none_for_different_geometry(bank_db):
    exercise_bank.add_exercise(SIMPLY_SUPPORTED_EXTRACTED, added_by_user_id=1)
    different = {
        "exercise_type": "beam",
        "beam": {
            "L": 5.0,
            "support_mode": "simply_supported",
            "supports": [
                {"label": "A", "type": "pin", "x": 0.0},
                {"label": "B", "type": "roller", "x": 5.0},
            ],
            "loads": [{"type": "point", "x": 2.0, "Fy": 2.5}],  # עומס שונה
        },
    }
    assert exercise_bank.find_duplicate_exercise(different) is None


def test_find_duplicate_exercise_does_not_confuse_cantilever_with_simply_supported(bank_db):
    exercise_bank.add_exercise(CANTILEVER_EXTRACTED, added_by_user_id=1)
    assert exercise_bank.find_duplicate_exercise(SIMPLY_SUPPORTED_EXTRACTED) is None


@pytest.mark.anyio
async def test_deliver_exercise_bank_after_approve_detects_duplicate_and_skips_insert(bank_db):
    context = MagicMock()
    context.bot.delete_message = AsyncMock()
    send_text = AsyncMock(return_value=MagicMock(message_id=777))
    edit_draft = AsyncMock()

    existing_id = exercise_bank.add_exercise(SIMPLY_SUPPORTED_EXTRACTED, added_by_user_id=1)
    assert exercise_bank.count_exercises() == 1

    import copy

    await exercise_bank.deliver_exercise_bank_after_approve(
        context,
        4244,
        extracted=copy.deepcopy(SIMPLY_SUPPORTED_EXTRACTED),
        reply="ok",
        solved={"result": {"reactions_ton": {}}},
        draft_msg_id=101,
        send_text=send_text,
        edit_draft_message=edit_draft,
    )

    # לא נוספה רשומה כפולה — נשאר רק התרגיל המקורי.
    assert exercise_bank.count_exercises() == 1
    context.bot.delete_message.assert_awaited_once_with(chat_id=4244, message_id=101)
    send_text.assert_awaited_once()
    confirmation = send_text.await_args.args[2]
    assert "כבר קיים במאגר" in confirmation
    assert f"#{existing_id}" in confirmation
    edit_draft.assert_not_awaited()


@pytest.mark.anyio
async def test_deliver_exercise_bank_after_approve_shows_error_without_saving(bank_db):
    context = MagicMock()
    context.bot.delete_message = AsyncMock()
    send_text = AsyncMock(return_value=MagicMock(message_id=556))
    edit_draft = AsyncMock()

    await exercise_bank.deliver_exercise_bank_after_approve(
        context,
        4243,
        extracted=SIMPLY_SUPPORTED_EXTRACTED,
        reply="שגיאת אימות",
        solved={},
        draft_msg_id=100,
        send_text=send_text,
        edit_draft_message=edit_draft,
    )

    assert exercise_bank.count_exercises() == 0
    send_text.assert_awaited_once()
    assert send_text.await_args.args[2] == "שגיאת אימות"
    edit_draft.assert_awaited_once()
    context.bot.delete_message.assert_not_awaited()
