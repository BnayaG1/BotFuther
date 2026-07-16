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


@pytest.mark.anyio
async def test_give_exercise_shows_toast_when_bank_empty():
    update = MagicMock(spec=Update)
    query = MagicMock(spec=CallbackQuery)
    query.data = "menu:give_exercise"
    query.answer = AsyncMock()
    query.message = MagicMock(spec=Message)
    update.callback_query = query

    context = MagicMock()

    with patch.object(handlers, "count_exercises", return_value=0):
        await handlers.on_menu_callback(update, context)

    query.answer.assert_awaited_once()
    args, kwargs = query.answer.await_args
    assert "אין עדיין תרגילים" in args[0]
    assert kwargs.get("show_alert") is True


@pytest.mark.anyio
async def test_give_exercise_shows_toast_when_cooldown_active():
    update = MagicMock(spec=Update)
    query = MagicMock(spec=CallbackQuery)
    query.data = "menu:give_exercise"
    query.answer = AsyncMock()
    query.message = MagicMock(spec=Message)
    query.message.delete = AsyncMock()
    update.callback_query = query
    update.effective_user = User(id=888, is_bot=False, first_name="T")

    context = MagicMock()

    with patch.object(handlers, "count_exercises", return_value=3), \
        patch.object(handlers, "exercise_bank_cooldown_remaining_sec", return_value=900.0), \
        patch.object(handlers, "pick_next_exercise_for_user") as mock_pick:
        await handlers.on_menu_callback(update, context)

    query.answer.assert_awaited_once()
    args, kwargs = query.answer.await_args
    assert "דקות" in args[0]
    assert kwargs.get("show_alert") is True
    mock_pick.assert_not_called()
    query.message.delete.assert_not_awaited()


@pytest.mark.anyio
async def test_give_exercise_sends_stored_photo_and_mode_picker():
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
    context.bot.send_photo = AsyncMock()
    context.bot.send_message = AsyncMock()

    extracted = {"beam": {"L": 6.0, "supports": [], "loads": []}}
    solution_session._pending_bank_exercise.pop(chat_id, None)

    fake_path = MagicMock()
    fake_path.open = MagicMock()
    fake_path.open.return_value.__enter__ = MagicMock(return_value=MagicMock())
    fake_path.open.return_value.__exit__ = MagicMock(return_value=False)

    with patch.object(handlers, "count_exercises", return_value=3), \
        patch.object(handlers, "exercise_bank_cooldown_remaining_sec", return_value=None), \
        patch.object(
            handlers, "pick_next_exercise_for_user", return_value=(42, extracted)
        ) as mock_pick, \
        patch.object(handlers, "get_exercise_image_path", return_value=fake_path) as mock_img, \
        patch.object(handlers, "render_exercise_problem_png_temp") as mock_render:
        await handlers.on_menu_callback(update, context)

    query.answer.assert_awaited_once_with()
    query.message.delete.assert_awaited_once()
    mock_pick.assert_called_once_with(777)
    mock_img.assert_called_once_with(42)
    mock_render.assert_not_called()
    context.bot.send_photo.assert_awaited_once()
    assert context.bot.send_photo.await_args.kwargs["chat_id"] == chat_id
    context.bot.send_message.assert_awaited_once()
    assert "לפתור" in context.bot.send_message.await_args.kwargs["text"]
    assert solution_session._pending_bank_exercise.get(chat_id) == (42, extracted)


@pytest.mark.anyio
async def test_give_exercise_falls_back_to_render_when_no_stored_image():
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
    context.bot.send_photo = AsyncMock()
    context.bot.send_message = AsyncMock()

    extracted = {"beam": {"L": 6.0, "supports": [], "loads": []}}
    solution_session._pending_bank_exercise.pop(chat_id, None)

    fake_path = MagicMock()

    with patch.object(handlers, "count_exercises", return_value=3), \
        patch.object(handlers, "exercise_bank_cooldown_remaining_sec", return_value=None), \
        patch.object(
            handlers, "pick_next_exercise_for_user", return_value=(42, extracted)
        ) as mock_pick, \
        patch.object(handlers, "get_exercise_image_path", return_value=None), \
        patch.object(handlers, "render_exercise_problem_png_temp", return_value=fake_path):
        await handlers.on_menu_callback(update, context)

    query.answer.assert_awaited_once_with()
    query.message.delete.assert_awaited_once()
    mock_pick.assert_called_once_with(777)
    context.bot.send_photo.assert_awaited_once()
    assert context.bot.send_photo.await_args.kwargs["chat_id"] == chat_id
    context.bot.send_message.assert_awaited_once()
    assert "לפתור" in context.bot.send_message.await_args.kwargs["text"]
    assert solution_session._pending_bank_exercise.get(chat_id) == (42, extracted)
    fake_path.unlink.assert_called_once_with(missing_ok=True)


@pytest.mark.anyio
async def test_give_exercise_falls_back_to_text_when_render_fails():
    chat_id = 99011
    update = MagicMock(spec=Update)
    query = MagicMock(spec=CallbackQuery)
    query.data = "menu:give_exercise"
    query.answer = AsyncMock()
    query.message = MagicMock(spec=Message)
    query.message.chat_id = chat_id
    query.message.delete = AsyncMock()
    update.callback_query = query
    update.effective_user = User(id=778, is_bot=False, first_name="T")

    context = MagicMock()
    context.bot.send_message = AsyncMock()

    extracted = {"beam": {"L": 6.0, "supports": [], "loads": []}}
    solution_session._pending_bank_exercise.pop(chat_id, None)

    with patch.object(handlers, "count_exercises", return_value=1), \
        patch.object(handlers, "exercise_bank_cooldown_remaining_sec", return_value=None), \
        patch.object(
            handlers, "pick_next_exercise_for_user", return_value=(7, extracted)
        ), \
        patch.object(handlers, "get_exercise_image_path", return_value=None), \
        patch.object(handlers, "render_exercise_problem_png_temp", return_value=None):
        await handlers.on_menu_callback(update, context)

    query.message.delete.assert_awaited_once()
    assert context.bot.send_message.await_count == 2
    first_call_text = context.bot.send_message.await_args_list[0].kwargs["text"]
    assert "תרגיל #" not in first_call_text
    assert first_call_text.strip() != ""


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
    mock_begin.assert_called_once_with(chat_id, solve_mode=SolveMode.NOTEBOOK)
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
async def test_bnaya_g_secret_sets_pending_mode_and_prompts():
    chat_id = 88040
    update = MagicMock(spec=Update)
    update.message = MagicMock(spec=Message)
    update.message.text = handlers._BANK_ADD_SECRET
    update.message.reply_text = AsyncMock()
    update.effective_chat = Chat(id=chat_id, type="private")
    update.effective_user = User(id=1, is_bot=False, first_name="T")

    context = MagicMock()
    solution_session._pending_solve_mode.pop(chat_id, None)

    with patch.object(handlers, "telegram_chat_id", return_value=chat_id):
        with patch.object(handlers, "has_active_assistant_progress", return_value=False):
            await handlers.on_text(update, context)

    assert solution_session._pending_solve_mode.get(chat_id) == SolveMode.ADD_TO_BANK
    update.message.reply_text.assert_awaited_once()
    assert "למאגר" in update.message.reply_text.await_args.args[0]


@pytest.mark.anyio
async def test_on_image_add_to_bank_skips_quota_consumption():
    chat_id = 88041
    solution_session.set_pending_solve_mode(chat_id, SolveMode.ADD_TO_BANK)

    update = MagicMock(spec=Update)
    update.message = MagicMock(spec=Message)
    update.message.message_id = 5
    update.message.reply_text = AsyncMock()
    update.effective_chat = Chat(id=chat_id, type="private")
    update.effective_user = User(id=5, is_bot=False, first_name="T")

    context = MagicMock()

    with patch.object(handlers, "COUPON_ACCESS_ENABLED", True):
        with patch.object(handlers, "consume_image_slot") as mock_consume:
            with patch.object(handlers, "begin_image_session") as mock_begin:
                mock_begin.return_value = MagicMock()
                with patch.object(
                    handlers,
                    "save_message_image_to_temp",
                    side_effect=RuntimeError("stop"),
                ):
                    with patch.object(handlers, "telegram_chat_id", return_value=chat_id):
                        await handlers.on_image(update, context)

    mock_consume.assert_not_called()
    mock_begin.assert_called_once_with(chat_id, solve_mode=SolveMode.ADD_TO_BANK)


@pytest.mark.anyio
async def test_on_image_notebook_mode_still_consumes_quota():
    chat_id = 88042
    solution_session._pending_solve_mode.pop(chat_id, None)

    update = MagicMock(spec=Update)
    update.message = MagicMock(spec=Message)
    update.message.message_id = 6
    update.message.reply_text = AsyncMock()
    update.effective_chat = Chat(id=chat_id, type="private")
    update.effective_user = User(id=6, is_bot=False, first_name="T")

    context = MagicMock()

    from bot.access import AccessSource, ImageAccessResult, ImageAccessStatus

    ok_result = ImageAccessResult(
        status=ImageAccessStatus.OK,
        tier_limit=2,
        images_used=1,
        images_remaining=1,
        access_source=AccessSource.TRIAL,
    )

    with patch.object(handlers, "COUPON_ACCESS_ENABLED", True):
        with patch.object(handlers, "consume_image_slot", return_value=ok_result) as mock_consume:
            with patch.object(handlers, "begin_image_session") as mock_begin:
                mock_begin.return_value = MagicMock()
                with patch.object(
                    handlers,
                    "save_message_image_to_temp",
                    side_effect=RuntimeError("stop"),
                ):
                    with patch.object(handlers, "telegram_chat_id", return_value=chat_id):
                        await handlers.on_image(update, context)

    mock_consume.assert_called_once()
    mock_begin.assert_called_once_with(chat_id, solve_mode=SolveMode.NOTEBOOK)
