# -*- coding: utf-8 -*-
"""לחיצה על «כיוון» בעומס קיים בטיוטה: הופכת כיוון בלי לפתוח תפריט בחירת סוג."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import CallbackQuery, Message, Update

import bot.handlers as handlers
from bot.draft_editor import toggle_any_load_direction
from bot.draft_keyboard import draft_display_text
from bot.solution_session import reset_user_session
from bot.vision import get_draft_type_picker_idx, set_draft_pending

EXTRACTED = {
    "beam": {
        "L": 10.0,
        "support_mode": "simply_supported",
        "supports": [
            {"label": "A", "type": "pin", "x": 0.0},
            {"label": "B", "type": "roller", "x": 10.0},
        ],
        "loads": [{"type": "point", "x": 4.0, "Fy": 3.0}],
    }
}


def _make_query(data: str, chat_id: int, msg_id: int) -> MagicMock:
    query = MagicMock(spec=CallbackQuery)
    query.data = data
    query.answer = AsyncMock()
    query.message = MagicMock(spec=Message)
    query.message.chat_id = chat_id
    query.message.message_id = msg_id
    return query


@pytest.mark.anyio
async def test_direction_click_on_existing_load_toggles_without_opening_type_picker():
    chat_id = 77001
    reset_user_session(chat_id)
    set_draft_pending(chat_id, EXTRACTED, draft_display_text(EXTRACTED), message_id=101)

    update = MagicMock(spec=Update)
    query = _make_query("d:td1", chat_id, 101)
    update.callback_query = query

    context = MagicMock()

    with patch.object(handlers, "_edit_draft_message_safe", new=AsyncMock()) as mock_edit:
        await handlers.on_draft_callback(update, context)

    mock_edit.assert_awaited_once()
    updated_extracted = mock_edit.await_args.args[3]
    ld = updated_extracted["beam"]["loads"][0]
    assert float(ld["Fy"]) == -3.0
    assert get_draft_type_picker_idx(chat_id) is None


@pytest.mark.anyio
async def test_direction_click_on_new_empty_load_still_opens_type_picker():
    chat_id = 77002
    reset_user_session(chat_id)
    extracted_with_new_load = {
        "beam": {
            "L": 10.0,
            "support_mode": "simply_supported",
            "supports": EXTRACTED["beam"]["supports"],
            "loads": [
                {"type": "point", "x": 4.0, "Fy": 3.0},
                {"type": "point", "x": 0.0, "Fy": 0.0, "_draft_new": True},
            ],
        }
    }
    set_draft_pending(
        chat_id,
        extracted_with_new_load,
        draft_display_text(extracted_with_new_load),
        message_id=102,
    )

    update = MagicMock(spec=Update)
    query = _make_query("d:td2", chat_id, 102)
    update.callback_query = query

    context = MagicMock()

    with patch.object(handlers, "_edit_draft_message_safe", new=AsyncMock()):
        await handlers.on_draft_callback(update, context)

    assert get_draft_type_picker_idx(chat_id) == 2


def _beam_with_load(load: dict) -> dict:
    return {
        # מסמן שהתמרת סימן המומנט (vision CCW+ → website CW+) כבר בוצעה — כמו
        # בטיוטה אמיתית שכבר עברה finalize_beam_extraction פעם אחת. בלעדיו,
        # ה-toggle כאן היה מתבצע על גבי היפוך המומנט החד-פעמי ומטשטש את הבדיקה.
        "_moment_sign_aligned": True,
        "beam": {
            "L": 10.0,
            "support_mode": "simply_supported",
            "supports": [
                {"label": "A", "type": "pin", "x": 0.0},
                {"label": "B", "type": "roller", "x": 10.0},
            ],
            "loads": [load],
        }
    }


def test_toggle_direction_on_vertical_point_load_flips_fy():
    extracted = _beam_with_load({"type": "point", "x": 4.0, "Fy": 3.0})
    out = toggle_any_load_direction(extracted, 1)
    ld = out["beam"]["loads"][0]
    assert float(ld["Fy"]) == -3.0


def test_toggle_direction_on_axial_point_load_flips_fx_not_fy():
    """עומס צירי (רק Fx, Fy=0) — לחיצה על כיוון חייבת להפוך את Fx, לא את ה-Fy האפסי."""
    extracted = _beam_with_load({"type": "point", "x": 4.0, "Fy": 0.0, "Fx": 6.0})
    out = toggle_any_load_direction(extracted, 1)
    ld = out["beam"]["loads"][0]
    assert float(ld["Fx"]) == -6.0
    assert float(ld.get("Fy", 0.0)) == 0.0


def test_toggle_direction_on_axial_point_load_without_fy_key_flips_fx():
    extracted = _beam_with_load({"type": "point", "x": 4.0, "Fx": -8.5})
    out = toggle_any_load_direction(extracted, 1)
    ld = out["beam"]["loads"][0]
    assert float(ld["Fx"]) == 8.5


def test_toggle_direction_on_moment_load_flips_m():
    extracted = _beam_with_load({"type": "moment", "x": 4.0, "M": 12.0})
    out = toggle_any_load_direction(extracted, 1)
    ld = out["beam"]["loads"][0]
    assert float(ld["M"]) == -12.0


def test_toggle_direction_on_distributed_load_flips_w():
    extracted = _beam_with_load(
        {"type": "distributed", "x1": 1.0, "x2": 5.0, "w": 2.5, "shape": "rectangular"}
    )
    out = toggle_any_load_direction(extracted, 1)
    ld = out["beam"]["loads"][0]
    assert float(ld["w"]) == -2.5


@pytest.mark.anyio
async def test_direction_click_with_stale_draft_new_flag_toggles_without_picker():
    """עומס עם ערך אבל _draft_new שלא נוקה — לחיצה על כיוון מחליפה, לא פותחת תפריט."""
    chat_id = 77003
    reset_user_session(chat_id)
    extracted = {
        "beam": {
            "L": 10.0,
            "support_mode": "simply_supported",
            "supports": EXTRACTED["beam"]["supports"],
            "loads": [{"type": "point", "x": 4.0, "Fy": 3.0, "_draft_new": True}],
        }
    }
    set_draft_pending(chat_id, extracted, draft_display_text(extracted), message_id=103)

    update = MagicMock(spec=Update)
    query = _make_query("d:td1", chat_id, 103)
    update.callback_query = query
    context = MagicMock()

    with patch.object(handlers, "_edit_draft_message_safe", new=AsyncMock()) as mock_edit:
        await handlers.on_draft_callback(update, context)

    mock_edit.assert_awaited_once()
    updated_extracted = mock_edit.await_args.args[3]
    ld = updated_extracted["beam"]["loads"][0]
    assert float(ld["Fy"]) == -3.0
    assert get_draft_type_picker_idx(chat_id) is None


def test_toggle_direction_on_axial_with_direction_metadata_persists_after_finalize():
    """עומס צירי מחילוץ עם direction=right — היפוך כיוון לא נדרס ב-finalize."""
    extracted = _beam_with_load(
        {"type": "point", "x": 10.0, "Fy": 0.0, "Fx": 6.0, "direction": "right"}
    )
    out = toggle_any_load_direction(extracted, 1)
    ld = out["beam"]["loads"][0]
    assert float(ld["Fx"]) == -6.0
    assert float(ld.get("Fy", 0.0)) == 0.0
    assert ld.get("_user_mag") is True
    assert "direction" not in ld


@pytest.mark.anyio
async def test_direction_click_on_axial_load_toggles_without_opening_type_picker():
    chat_id = 77004
    reset_user_session(chat_id)
    extracted = {
        "beam": {
            "L": 10.0,
            "support_mode": "simply_supported",
            "supports": EXTRACTED["beam"]["supports"],
            "loads": [
                {
                    "type": "point",
                    "x": 10.0,
                    "Fy": 0.0,
                    "Fx": 8.0,
                    "direction": "right",
                }
            ],
        }
    }
    set_draft_pending(chat_id, extracted, draft_display_text(extracted), message_id=104)

    update = MagicMock(spec=Update)
    query = _make_query("d:td1", chat_id, 104)
    update.callback_query = query
    context = MagicMock()

    with patch.object(handlers, "_edit_draft_message_safe", new=AsyncMock()) as mock_edit:
        await handlers.on_draft_callback(update, context)

    mock_edit.assert_awaited_once()
    updated_extracted = mock_edit.await_args.args[3]
    ld = updated_extracted["beam"]["loads"][0]
    assert float(ld["Fx"]) == -8.0
    assert get_draft_type_picker_idx(chat_id) is None


def test_toggle_direction_on_inclined_load_flips_fx_and_fy_via_incl_dir():
    extracted = _beam_with_load(
        {
            "type": "inclined",
            "x": 4.0,
            "magnitude_ton": 10.0,
            "angle_deg": 30.0,
            "incl_dir": "dr",
            "Fx": 8.660254,
            "Fy": 5.0,
        }
    )
    out = toggle_any_load_direction(extracted, 1)
    ld = out["beam"]["loads"][0]
    assert ld["incl_dir"] == "dl"
    assert float(ld["Fx"]) < 0
    assert float(ld["Fy"]) > 0


def test_empty_axial_direction_click_does_not_open_type_picker():
    from bot.draft_editor import add_load_of_type
    from bot.draft_keyboard import should_open_type_picker_on_direction_click

    extracted = add_load_of_type(EXTRACTED, "axial")
    ld = extracted["beam"]["loads"][-1]
    assert should_open_type_picker_on_direction_click(ld) is False


@pytest.mark.anyio
async def test_direction_click_on_empty_axial_load_toggles_without_picker():
    from bot.draft_editor import add_load_of_type

    chat_id = 77005
    reset_user_session(chat_id)
    extracted = add_load_of_type(EXTRACTED, "axial")
    idx = len(extracted["beam"]["loads"])
    set_draft_pending(chat_id, extracted, draft_display_text(extracted), message_id=105)

    update = MagicMock(spec=Update)
    query = _make_query(f"d:td{idx}", chat_id, 105)
    update.callback_query = query
    context = MagicMock()

    with patch.object(handlers, "_edit_draft_message_safe", new=AsyncMock()) as mock_edit:
        await handlers.on_draft_callback(update, context)

    mock_edit.assert_awaited_once()
    updated_extracted = mock_edit.await_args.args[3]
    ld = updated_extracted["beam"]["loads"][-1]
    assert ld.get("direction") == "left"
    assert float(ld.get("Fy", 0.0)) == 0.0
    assert float(ld.get("Fx", 0.0)) == 0.0
    assert get_draft_type_picker_idx(chat_id) is None


def test_toggle_empty_axial_flips_direction_metadata():
    from bot.draft_editor import add_load_of_type, axial_dir_icon

    extracted = add_load_of_type(EXTRACTED, "axial")
    idx = len(extracted["beam"]["loads"])
    out = toggle_any_load_direction(extracted, idx)
    ld = out["beam"]["loads"][-1]
    assert ld.get("direction") == "left"
    assert float(ld.get("Fy", 0.0)) == 0.0
    assert float(ld.get("Fx", 0.0)) == 0.0
    assert axial_dir_icon(ld) == "\u2190"

    out2 = toggle_any_load_direction(out, idx)
    ld2 = out2["beam"]["loads"][-1]
    assert ld2.get("direction") == "right"
    assert axial_dir_icon(ld2) == "\u2192"
