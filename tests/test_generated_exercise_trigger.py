# -*- coding: utf-8 -*-
"""בדיקה: אות B שולחת תרגיל מהמחולל."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Chat, Message, Update, User

import bot.handlers as handlers
import bot.solution_session as solution_session


@pytest.mark.anyio
async def test_letter_b_sends_generated_exercise_and_mode_picker(tmp_path: Path):
    chat_id = 55001
    update = MagicMock(spec=Update)
    message = MagicMock(spec=Message)
    message.text = "B"
    message.chat_id = chat_id
    message.chat = Chat(id=chat_id, type="private")
    update.message = message
    update.effective_chat = message.chat
    update.effective_user = User(id=chat_id, is_bot=False, first_name="T")

    context = MagicMock()
    context.bot.send_photo = AsyncMock()
    context.bot.send_message = AsyncMock()

    png = tmp_path / "live.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    extracted = {
        "exercise_type": "beam",
        "beam": {"L": 10.0, "supports": [], "loads": []},
        "meta": {"family": "overhang_stepped_udl", "seed": 1},
    }
    fake_art = MagicMock()
    fake_art.png_path = png
    fake_art.extracted = extracted

    solution_session._pending_bank_exercise.pop(chat_id, None)

    with patch(
        "exercise_generator.pipeline.generate_exercise", return_value=fake_art
    ) as mock_gen:
        await handlers.on_text(update, context)

    mock_gen.assert_called_once()
    context.bot.send_photo.assert_awaited_once()
    context.bot.send_message.assert_awaited_once()
    args, kwargs = context.bot.send_message.await_args
    assert "איך תרצה" in kwargs.get("text", args[0] if args else "")
    pending = solution_session.consume_pending_bank_exercise(chat_id)
    assert pending is not None
    assert pending[0] == handlers._GENERATED_EXERCISE_ID
    assert pending[1]["beam"]["L"] == 10.0
    assert pending[1]["meta"]["skip_vision_normalize"] is True
    assert pending[1]["meta"]["source"] == "exercise_generator"


def test_bank_extracted_for_solve_skips_finalize_for_generator():
    extracted = {
        "exercise_type": "beam",
        "beam": {
            "L": 11.0,
            "support_mode": "simply_supported",
            "supports": [
                {"label": "A", "type": "pin", "x": 1.0},
                {"label": "B", "type": "roller", "x": 9.0},
            ],
            "loads": [
                {
                    "type": "distributed",
                    "x1": 0.0,
                    "x2": 5.0,
                    "w": 4.0,
                    "shape": "rectangular",
                },
                {
                    "type": "distributed",
                    "x1": 5.0,
                    "x2": 11.0,
                    "w": 3.0,
                    "shape": "rectangular",
                },
            ],
            "labeled_points": [{"label": "C", "x": 5.0}],
        },
        "meta": {
            "family": "overhang_stepped_udl",
            "seed": 1,
            "source": "exercise_generator",
            "skip_vision_normalize": True,
        },
    }
    out = handlers._bank_extracted_for_solve(extracted)
    assert out["beam"]["L"] == 11.0
    assert out["beam"]["supports"][0]["label"] == "A"
    assert out["beam"]["supports"][0]["x"] == 1.0
    assert out["beam"]["supports"][1]["label"] == "B"
    assert out["beam"]["supports"][1]["x"] == 9.0
    assert out["beam"]["labeled_points"][0]["x"] == 5.0


@pytest.mark.anyio
async def test_bank_assistant_keeps_generator_geometry():
    chat_id = 55003
    extracted = {
        "exercise_type": "beam",
        "beam": {
            "L": 11.0,
            "support_mode": "simply_supported",
            "supports": [
                {"label": "A", "type": "pin", "x": 1.0},
                {"label": "B", "type": "roller", "x": 9.0},
            ],
            "loads": [],
            "labeled_points": [{"label": "C", "x": 5.0}],
        },
        "meta": {
            "source": "exercise_generator",
            "skip_vision_normalize": True,
        },
    }
    solution_session.set_pending_bank_exercise(
        chat_id, handlers._GENERATED_EXERCISE_ID, extracted
    )

    update = MagicMock(spec=Update)
    query = MagicMock()
    query.data = "menu:bank:assistant"
    query.answer = AsyncMock()
    query.message = MagicMock(spec=Message)
    query.message.chat_id = chat_id
    query.message.delete = AsyncMock()
    update.callback_query = query

    context = MagicMock()
    delivered: dict = {}

    async def _capture_deliver(context, chat_id, *, extracted, **kwargs):
        delivered["extracted"] = extracted

    with patch.object(handlers, "deliver_after_draft_approve", side_effect=_capture_deliver), \
        patch.object(handlers, "solve_extracted_beam", return_value={"result": {"reactions_ton": {}}}), \
        patch.object(handlers, "begin_image_session"), \
        patch.object(handlers, "finalize_beam_extraction") as mock_finalize:
        await handlers.on_menu_callback(update, context)

    mock_finalize.assert_not_called()
    assert delivered["extracted"]["beam"]["supports"][0]["x"] == 1.0
    assert delivered["extracted"]["beam"]["supports"][1]["x"] == 9.0
    assert delivered["extracted"]["beam"]["L"] == 11.0


@pytest.mark.anyio
async def test_letter_b_lowercase_also_works(tmp_path: Path):
    chat_id = 55002
    update = MagicMock(spec=Update)
    message = MagicMock(spec=Message)
    message.text = "b"
    message.chat_id = chat_id
    message.chat = Chat(id=chat_id, type="private")
    update.message = message
    update.effective_chat = message.chat
    update.effective_user = User(id=chat_id, is_bot=False, first_name="T")

    context = MagicMock()
    context.bot.send_photo = AsyncMock()
    context.bot.send_message = AsyncMock()

    png = tmp_path / "live.png"
    png.write_bytes(b"png")
    fake_art = MagicMock()
    fake_art.png_path = png
    fake_art.extracted = {"beam": {"L": 5.0}}

    with patch("exercise_generator.pipeline.generate_exercise", return_value=fake_art):
        await handlers.on_text(update, context)

    context.bot.send_photo.assert_awaited_once()
