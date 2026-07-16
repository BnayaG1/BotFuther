# -*- coding: utf-8 -*-
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import CallbackQuery, Chat, InlineKeyboardMarkup, Message, Update, User

import bot.assistant as assistant
import bot.handlers as handlers
import bot.solution_session as solution_session
from bot.solution_session import SolveMode


def test_build_solve_mode_keyboard():
    kb = assistant.build_solve_mode_keyboard()
    assert isinstance(kb, InlineKeyboardMarkup)
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "menu:mode:notebook" in callbacks
    assert "menu:mode:assistant" in callbacks


def test_solve_mode_prompts_ask_for_image():
    assert "תמונה" in assistant.solve_mode_prompt_hebrew(SolveMode.NOTEBOOK)
    assert "תמונה" in assistant.solve_mode_prompt_hebrew(SolveMode.ASSISTANT)
    assert "מחברת" in assistant.solve_mode_prompt_hebrew(SolveMode.NOTEBOOK)
    assert "שלב-אחר-שלב" in assistant.solve_mode_prompt_hebrew(SolveMode.ASSISTANT)


def test_parse_menu_mode_action():
    assert assistant.parse_menu_mode_action("mode:notebook") == SolveMode.NOTEBOOK
    assert assistant.parse_menu_mode_action("mode:assistant") == SolveMode.ASSISTANT
    assert assistant.parse_menu_mode_action("mode:unknown") is None
    assert assistant.parse_menu_mode_action("new") is None


@pytest.mark.anyio
async def test_menu_new_shows_mode_picker():
    update = MagicMock(spec=Update)
    query = MagicMock(spec=CallbackQuery)
    query.data = "menu:new"
    query.answer = AsyncMock()
    query.message = MagicMock(spec=Message)
    query.message.chat_id = 88000
    query.message.delete = AsyncMock()
    update.callback_query = query

    context = MagicMock()
    context.bot.send_message = AsyncMock()
    await handlers.on_menu_callback(update, context)

    query.answer.assert_awaited_once()
    query.message.delete.assert_awaited_once()
    assert context.bot.send_message.await_count >= 2
    intro_text = context.bot.send_message.await_args_list[0].kwargs.get("text")
    if intro_text is None:
        intro_text = context.bot.send_message.await_args_list[0].args[1]
    assert "בוא/י נבחר" in intro_text
    picker_kwargs = context.bot.send_message.await_args_list[1].kwargs
    assert picker_kwargs.get("text") == "בחר/י מצב:"
    kb = picker_kwargs.get("reply_markup")
    assert isinstance(kb, InlineKeyboardMarkup)
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "menu:mode:notebook" in callbacks
    assert "menu:mode:assistant" in callbacks


@pytest.mark.anyio
async def test_menu_mode_notebook_sets_pending_and_prompts():
    chat_id = 88001
    update = MagicMock(spec=Update)
    query = MagicMock(spec=CallbackQuery)
    query.data = "menu:mode:notebook"
    query.answer = AsyncMock()
    query.message = MagicMock(spec=Message)
    query.message.chat_id = chat_id
    query.message.delete = AsyncMock()
    update.callback_query = query

    context = MagicMock()
    context.bot.send_message = AsyncMock()
    solution_session._pending_solve_mode.pop(chat_id, None)

    with patch.object(handlers, "telegram_chat_id", return_value=chat_id):
        await handlers.on_menu_callback(update, context)

    assert solution_session._pending_solve_mode.get(chat_id) == SolveMode.NOTEBOOK
    query.message.delete.assert_awaited_once()
    context.bot.send_message.assert_awaited()
    sent = context.bot.send_message.await_args.kwargs.get("text")
    if sent is None:
        sent = context.bot.send_message.await_args.args[1]
    assert "תמונה" in sent


@pytest.mark.anyio
async def test_menu_mode_assistant_sets_pending_and_prompts():
    chat_id = 88002
    update = MagicMock(spec=Update)
    query = MagicMock(spec=CallbackQuery)
    query.data = "menu:mode:assistant"
    query.answer = AsyncMock()
    query.message = MagicMock(spec=Message)
    query.message.chat_id = chat_id
    query.message.delete = AsyncMock()
    update.callback_query = query

    context = MagicMock()
    context.bot.send_message = AsyncMock()
    solution_session._pending_solve_mode.pop(chat_id, None)

    with patch.object(handlers, "telegram_chat_id", return_value=chat_id):
        await handlers.on_menu_callback(update, context)

    assert solution_session._pending_solve_mode.get(chat_id) == SolveMode.ASSISTANT
    query.message.delete.assert_awaited_once()
    context.bot.send_message.assert_awaited()
    sent = context.bot.send_message.await_args.kwargs.get("text")
    if sent is None:
        sent = context.bot.send_message.await_args.args[1]
    assert "שלב-אחר-שלב" in sent


@pytest.mark.anyio
async def test_on_image_without_pending_defaults_to_notebook():
    chat_id = 88003
    update = MagicMock(spec=Update)
    update.message = MagicMock(spec=Message)
    update.message.message_id = 1
    update.message.reply_text = AsyncMock()
    update.effective_chat = Chat(id=chat_id, type="private")
    update.effective_user = User(id=1, is_bot=False, first_name="T")

    context = MagicMock()
    solution_session._pending_solve_mode.pop(chat_id, None)

    with patch.object(handlers, "COUPON_ACCESS_ENABLED", False):
        with patch.object(handlers, "begin_image_session") as mock_begin:
            mock_begin.return_value = MagicMock()
            with patch.object(
                handlers,
                "save_message_image_to_temp",
                side_effect=RuntimeError("stop"),
            ):
                with patch.object(handlers, "telegram_chat_id", return_value=chat_id):
                    await handlers.on_image(update, context)

    mock_begin.assert_called_once_with(chat_id, solve_mode=SolveMode.NOTEBOOK)


@pytest.mark.anyio
async def test_on_image_after_assistant_pick_uses_assistant_mode():
    chat_id = 88004
    solution_session.set_pending_solve_mode(chat_id, SolveMode.ASSISTANT)

    update = MagicMock(spec=Update)
    update.message = MagicMock(spec=Message)
    update.message.message_id = 2
    update.message.reply_text = AsyncMock()
    update.effective_chat = Chat(id=chat_id, type="private")
    update.effective_user = User(id=2, is_bot=False, first_name="T")

    context = MagicMock()

    with patch.object(handlers, "COUPON_ACCESS_ENABLED", False):
        with patch.object(handlers, "begin_image_session") as mock_begin:
            mock_begin.return_value = MagicMock()
            with patch.object(
                handlers,
                "save_message_image_to_temp",
                side_effect=RuntimeError("stop"),
            ):
                with patch.object(handlers, "telegram_chat_id", return_value=chat_id):
                    await handlers.on_image(update, context)

    mock_begin.assert_called_once_with(chat_id, solve_mode=SolveMode.ASSISTANT)
    assert chat_id not in solution_session._pending_solve_mode


@pytest.mark.anyio
async def test_deliver_after_draft_approve_notebook_uses_full_solve():
    context = MagicMock()
    send_text = AsyncMock()
    edit_draft = AsyncMock()
    deliver_notebook = AsyncMock()

    with patch.object(assistant, "is_assistant_mode", return_value=False):
        await assistant.deliver_after_draft_approve(
            context,
            88005,
            extracted={},
            reply="ok",
            solved={"result": {}},
            draft_msg_id=10,
            deliver_notebook=deliver_notebook,
            send_text=send_text,
            edit_draft_message=edit_draft,
        )

    deliver_notebook.assert_awaited_once()
    send_text.assert_not_awaited()


@pytest.mark.anyio
async def test_deliver_after_draft_approve_assistant_skips_full_solve():
    context = MagicMock()
    send_text = AsyncMock()
    edit_draft = AsyncMock()
    deliver_notebook = AsyncMock()

    with patch.object(assistant, "is_assistant_mode", return_value=True):
        with patch.object(
            assistant, "deliver_assistant_after_approve", new_callable=AsyncMock
        ) as mock_assistant:
            await assistant.deliver_after_draft_approve(
                context,
                88006,
                extracted={},
                reply="ok",
                solved={"result": {}},
                draft_msg_id=11,
                deliver_notebook=deliver_notebook,
                send_text=send_text,
                edit_draft_message=edit_draft,
            )

    mock_assistant.assert_awaited_once()
    deliver_notebook.assert_not_awaited()


@pytest.mark.anyio
async def test_assistant_after_approve_does_not_render_notebook():
    context = MagicMock()
    context.bot.delete_message = AsyncMock()
    send_text = AsyncMock()
    edit_draft = AsyncMock()

    with patch("bot.notebook_render.render_notebook_png_temp") as mock_render:
        with patch.object(assistant, "present_assistant_step", new_callable=AsyncMock):
            await assistant.deliver_assistant_after_approve(
                context,
                88007,
                extracted={
                    "exercise_type": "beam",
                    "beam": {
                        "L": 10.0,
                        "support_mode": "simply_supported",
                        "supports": [
                            {"label": "A", "type": "pin", "x": 0.0},
                            {"label": "B", "type": "roller", "x": 10.0},
                        ],
                        "loads": [],
                    },
                },
                reply="ok",
                solved={"result": {"reactions": []}},
                draft_msg_id=12,
                send_text=send_text,
                edit_draft_message=edit_draft,
            )

    mock_render.assert_not_called()
    send_text.assert_awaited()
    bodies = [call.args[2] for call in send_text.await_args_list]
    assert any("בשלב הראשון" in b for b in bodies)
    context.bot.delete_message.assert_awaited_once_with(
        chat_id=88007, message_id=12
    )
