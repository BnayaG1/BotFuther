# -*- coding: utf-8 -*-
"""בדיקות לחיבור Telegram של מאגר התרגילים: כפתורי תפריט ודילוג מכסה."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import CallbackQuery, Chat, InlineKeyboardMarkup, Message, Update, User

import bot.handlers as handlers
import bot.solution_session as solution_session
from bot.solution_session import SolveMode


def test_start_keyboard_has_give_exercise_but_no_add_button():
    keyboard = handlers.build_start_keyboard()
    callbacks = [btn.callback_data for row in keyboard.inline_keyboard for btn in row]
    labels = [btn.text for row in keyboard.inline_keyboard for btn in row]
    assert "menu:give_exercise" in callbacks
    assert "menu:add_exercise" not in callbacks
    assert any("תרגול" in label for label in labels)
    assert not any(label == "➕" for label in labels)


from bot.access import AccessSource, ImageAccessResult, ImageAccessStatus


@pytest.mark.anyio
async def test_give_exercise_locked_without_access():
    chat_id = 99005
    update = MagicMock(spec=Update)
    query = MagicMock(spec=CallbackQuery)
    query.data = "menu:give_exercise"
    query.answer = AsyncMock()
    query.message = MagicMock(spec=Message)
    query.message.chat_id = chat_id
    query.message.delete = AsyncMock()
    update.callback_query = query
    update.effective_user = User(id=802, is_bot=False, first_name="T")

    context = MagicMock()
    context.bot.send_message = AsyncMock()

    denied = ImageAccessResult(
        status=ImageAccessStatus.DAILY_LIMIT,
        access_source=AccessSource.RESTRICTED,
        feature="practice",
        cooldown_remaining_sec=3600,
        window_reset_sec=3600,
    )

    with patch.object(handlers, "check_practice_feature_access", return_value=denied), \
        patch("exercise_generator.pipeline.generate_exercise") as mock_gen:
        await handlers.on_menu_callback(update, context)

    query.answer.assert_awaited_once_with()
    query.message.delete.assert_awaited_once()
    mock_gen.assert_not_called()
    context.bot.send_message.assert_awaited()
    kwargs = context.bot.send_message.await_args.kwargs
    text = kwargs.get("text") or ""
    if not text and context.bot.send_message.await_args.args:
        text = (
            context.bot.send_message.await_args.args[1]
            if len(context.bot.send_message.await_args.args) > 1
            else ""
        )
    text = kwargs.get("text", text)
    assert "מגבלת" in text



@pytest.mark.anyio
async def test_give_exercise_sends_generated_exercise_and_mode_picker(tmp_path):
    chat_id = 99010
    update = MagicMock(spec=Update)
    query = MagicMock(spec=CallbackQuery)
    query.data = "menu:give_exercise"
    query.answer = AsyncMock()
    query.message = MagicMock(spec=Message)
    query.message.chat_id = chat_id
    query.message.delete = AsyncMock()
    update.callback_query = query
    update.effective_user = User(id=777, is_bot=False, first_name="T")

    context = MagicMock()
    context.bot.send_photo = AsyncMock(return_value=MagicMock(message_id=501))
    context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=502))

    png = tmp_path / "live.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    extracted = {
        "exercise_type": "beam",
        "beam": {"L": 6.0, "supports": [], "loads": []},
        "meta": {"family": "overhang_stepped_udl", "seed": 1},
    }
    fake_art = MagicMock()
    fake_art.png_path = png
    fake_art.extracted = extracted

    solution_session._pending_bank_exercise.pop(chat_id, None)
    solution_session.discard_practice_chat_trail(chat_id)

    ok = ImageAccessResult(
        status=ImageAccessStatus.OK,
        access_source=AccessSource.FREE_WINDOW,
        feature="practice",
    )

    with patch.object(handlers, "check_practice_feature_access", return_value=ok), \
        patch.object(handlers, "consume_practice_slot", return_value=ok), \
        patch(
            "exercise_generator.pipeline.generate_exercise", return_value=fake_art
        ) as mock_gen:
        await handlers.on_menu_callback(update, context)

    query.answer.assert_awaited_once_with()
    query.message.delete.assert_awaited_once()
    mock_gen.assert_called_once()
    context.bot.send_photo.assert_awaited_once()
    assert context.bot.send_photo.await_args.kwargs["chat_id"] == chat_id
    context.bot.send_message.assert_awaited_once()
    assert "לפתור" in context.bot.send_message.await_args.kwargs["text"]
    pending = solution_session.consume_pending_bank_exercise(chat_id)
    assert pending is not None
    assert pending[0] == handlers._GENERATED_EXERCISE_ID
    assert pending[1]["meta"]["source"] == "exercise_generator"
    assert pending[1]["meta"]["skip_vision_normalize"] is True
    tracked = solution_session.pop_practice_chat_message_ids(chat_id)
    assert tracked == [501, 502]


@pytest.mark.anyio
async def test_leaving_to_formulas_deletes_practice_chat_messages():
    chat_id = 99077
    solution_session.begin_practice_chat_trail(chat_id)
    solution_session.append_practice_chat_message_id(chat_id, 11)
    solution_session.append_practice_chat_message_id(chat_id, 22)
    solution_session.set_pending_bank_exercise(
        chat_id, 9, {"beam": {"L": 5.0, "supports": [], "loads": []}}
    )

    update = MagicMock(spec=Update)
    query = MagicMock(spec=CallbackQuery)
    query.data = "menu:formulas"
    query.answer = AsyncMock()
    query.message = MagicMock(spec=Message)
    query.message.chat_id = chat_id
    query.message.delete = AsyncMock()
    update.callback_query = query
    update.effective_user = User(id=901, is_bot=False, first_name="T")

    context = MagicMock()
    context.bot.delete_message = AsyncMock()
    context.bot.send_message = AsyncMock()

    await handlers.on_menu_callback(update, context)

    deleted = {
        call.kwargs["message_id"]
        for call in context.bot.delete_message.await_args_list
    }
    assert deleted == {11, 22}
    assert solution_session._pending_bank_exercise.get(chat_id) is None
    assert not solution_session.has_practice_chat_trail(chat_id)


@pytest.mark.anyio
async def test_bank_mode_choice_delivers_solution_for_pending_exercise():
    chat_id = 99012
    update = MagicMock(spec=Update)
    query = MagicMock(spec=CallbackQuery)
    query.data = "menu:bank:notebook"
    query.answer = AsyncMock()
    query.message = MagicMock(spec=Message)
    query.message.chat_id = chat_id
    query.message.delete = AsyncMock()
    update.callback_query = query

    context = MagicMock()

    extracted = {
        "beam": {
            "L": 5.0,
            "support_mode": "simply_supported",
            "supports": [
                {"label": "A", "type": "pin", "x": 0.0},
                {"label": "B", "type": "roller", "x": 5.0},
            ],
            "loads": [{"type": "point", "x": 2.0, "Fy": 1.0}],
        }
    }
    solution_session.set_pending_bank_exercise(chat_id, 7, extracted)

    with patch.object(handlers, "begin_image_session") as mock_begin, \
        patch.object(handlers, "deliver_after_draft_approve", new=AsyncMock()) as mock_deliver:
        await handlers.on_menu_callback(update, context)

    query.message.delete.assert_awaited_once()
    mock_begin.assert_called_once_with(
        chat_id, solve_mode=SolveMode.NOTEBOOK, from_practice=True
    )
    mock_deliver.assert_awaited_once()
    assert solution_session._pending_bank_exercise.get(chat_id) is None


@pytest.mark.anyio
async def test_bank_mode_choice_without_pending_exercise_sends_hint():
    chat_id = 99013
    update = MagicMock(spec=Update)
    query = MagicMock(spec=CallbackQuery)
    query.data = "menu:bank:assistant"
    query.answer = AsyncMock()
    query.message = MagicMock(spec=Message)
    query.message.chat_id = chat_id
    query.message.delete = AsyncMock()
    update.callback_query = query

    context = MagicMock()
    context.bot.send_message = AsyncMock()

    solution_session._pending_bank_exercise.pop(chat_id, None)

    await handlers.on_menu_callback(update, context)

    query.message.delete.assert_awaited_once()
    context.bot.send_message.assert_awaited_once()
    assert "תרגול" in context.bot.send_message.await_args.kwargs["text"]


@pytest.mark.anyio
async def test_on_image_notebook_mode_checks_solve_access_without_consume():
    chat_id = 88042
    solution_session._pending_solve_mode.pop(chat_id, None)

    update = MagicMock(spec=Update)
    update.message = MagicMock(spec=Message)
    update.message.message_id = 6
    update.message.reply_text = AsyncMock()
    update.effective_chat = Chat(id=chat_id, type="private")
    update.effective_user = User(id=6, is_bot=False, first_name="T")

    context = MagicMock()

    ok_result = ImageAccessResult(
        status=ImageAccessStatus.OK,
        access_source=AccessSource.FREE_WINDOW,
        feature="solve",
    )

    with patch.object(handlers, "check_solve_access", return_value=ok_result) as mock_check:
        with patch.object(handlers, "begin_image_session") as mock_begin:
            mock_begin.return_value = MagicMock()
            with patch.object(
                handlers,
                "save_message_image_to_temp",
                side_effect=RuntimeError("stop"),
            ):
                with patch.object(handlers, "telegram_chat_id", return_value=chat_id):
                    with patch.object(handlers, "telegram_user_id", return_value=6):
                        await handlers.on_image(update, context)

    mock_check.assert_called_once()
    mock_begin.assert_called_once_with(chat_id, solve_mode=SolveMode.NOTEBOOK)

