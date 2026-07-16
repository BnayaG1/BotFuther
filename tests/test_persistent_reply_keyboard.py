# -*- coding: utf-8 -*-
from __future__ import annotations

import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Chat, Message, Update, User
from telegram import InlineKeyboardMarkup, ReplyKeyboardMarkup

import bot.handlers as handlers
import bot.solution_session as solution_session
from bot.solution_session import SolveMode


def test_cmd_start_keeps_inline_menu():
    assert isinstance(handlers.build_start_keyboard(), InlineKeyboardMarkup)

    src = inspect.getsource(handlers.cmd_start)
    assert "build_start_keyboard" in src


@pytest.mark.anyio
async def test_cmd_start_sends_persistent_keyboard_and_inline_menu():
    update = MagicMock(spec=Update)
    update.message = MagicMock(spec=Message)
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    await handlers.cmd_start(update, context)

    assert update.message.reply_text.await_count == 2
    first_kwargs = update.message.reply_text.await_args_list[0].kwargs
    second_kwargs = update.message.reply_text.await_args_list[1].kwargs
    assert isinstance(first_kwargs.get("reply_markup"), ReplyKeyboardMarkup)
    assert isinstance(second_kwargs.get("reply_markup"), InlineKeyboardMarkup)


@pytest.mark.anyio
async def test_on_text_quota_button_triggers_quota_flow():
    update = MagicMock(spec=Update)
    update.message = MagicMock(spec=Message)
    update.message.text = handlers._PERSISTENT_QUOTA_LABEL
    update.effective_chat = Chat(id=999002, type="private")
    update.effective_user = User(id=222, is_bot=False, first_name="T")
    update.message.reply_text = AsyncMock()

    context = MagicMock()

    fake_access_result = SimpleNamespace(status="OK")

    with patch.object(handlers, "COUPON_ACCESS_ENABLED", True):
        with patch.object(handlers, "check_image_access", return_value=fake_access_result):
            with patch.object(handlers, "quota_status_reply_hebrew", return_value="quota reply"):
                with patch.object(handlers, "telegram_user_id", return_value=222):
                    with patch.object(handlers, "handle_draft_text") as mock_draft:
                        await handlers.on_text(update, context)
                        mock_draft.assert_not_called()

    update.message.reply_text.assert_awaited_once()
    args, kwargs = update.message.reply_text.await_args
    assert args[0] == "quota reply"
    assert isinstance(kwargs.get("reply_markup"), ReplyKeyboardMarkup)


@pytest.mark.anyio
async def test_reply_text_safe_defaults_to_persistent_keyboard():
    message = MagicMock(spec=Message)
    message.reply_text = AsyncMock()
    await handlers._reply_text_safe(message, "hello")
    _, kwargs = message.reply_text.await_args
    assert isinstance(kwargs.get("reply_markup"), ReplyKeyboardMarkup)


@pytest.mark.anyio
async def test_on_text_assistant_button_sets_pending_mode():
    update = MagicMock(spec=Update)
    update.message = MagicMock(spec=Message)
    update.message.text = handlers._PERSISTENT_ASSISTANT_LABEL
    update.effective_chat = Chat(id=999003, type="private")
    update.effective_user = User(id=333, is_bot=False, first_name="T")
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    chat_id = 999003

    with patch.object(handlers, "telegram_chat_id", return_value=chat_id):
        with patch.object(handlers, "has_active_assistant_progress", return_value=False):
            with patch.object(
                handlers, "select_solve_mode", return_value="שלח/י תמונה"
            ) as mock_select:
                await handlers.on_text(update, context)

    mock_select.assert_called_once_with(chat_id, SolveMode.ASSISTANT)
    update.message.reply_text.assert_awaited_once()
    args, kwargs = update.message.reply_text.await_args
    assert "שלב" in args[0] or "תמונה" in args[0]
    assert isinstance(kwargs.get("reply_markup"), ReplyKeyboardMarkup)


def test_persistent_keyboard_excludes_add_exercise_plus_button():
    kb = handlers.build_persistent_keyboard()
    texts = [btn.text for row in kb.keyboard for btn in row]
    assert handlers._BANK_ADD_SECRET not in texts
    assert "➕" not in texts
    assert not any("הוסף תרגיל למאגר" in t for t in texts)


def test_persistent_keyboard_includes_main_button():
    kb = handlers.build_persistent_keyboard()
    texts = [btn.text for row in kb.keyboard for btn in row]
    assert handlers._PERSISTENT_MAIN_LABEL in texts
    assert "ראשי" in texts


@pytest.mark.anyio
async def test_on_text_main_button_shows_start_menu():
    update = MagicMock(spec=Update)
    update.message = MagicMock(spec=Message)
    update.message.text = handlers._PERSISTENT_MAIN_LABEL
    update.effective_chat = Chat(id=999005, type="private")
    update.effective_user = User(id=777, is_bot=False, first_name="T")
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    chat_id = 999005

    with patch.object(handlers, "telegram_chat_id", return_value=chat_id):
        with patch.object(handlers, "has_active_assistant_progress", return_value=False):
            await handlers.on_text(update, context)

    update.message.reply_text.assert_awaited_once()
    args, kwargs = update.message.reply_text.await_args
    assert args[0] == "בחר/י פעולה:"
    assert isinstance(kwargs.get("reply_markup"), InlineKeyboardMarkup)


@pytest.mark.anyio
async def test_on_text_bnaya_g_secret_sets_pending_mode():
    update = MagicMock(spec=Update)
    update.message = MagicMock(spec=Message)
    update.message.text = handlers._BANK_ADD_SECRET
    update.effective_chat = Chat(id=999004, type="private")
    update.effective_user = User(id=666, is_bot=False, first_name="T")
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    chat_id = 999004
    solution_session._pending_solve_mode.pop(chat_id, None)

    with patch.object(handlers, "telegram_chat_id", return_value=chat_id):
        with patch.object(handlers, "has_active_assistant_progress", return_value=False):
            await handlers.on_text(update, context)

    assert solution_session._pending_solve_mode.get(chat_id) == SolveMode.ADD_TO_BANK
    update.message.reply_text.assert_awaited_once()
    args, kwargs = update.message.reply_text.await_args
    assert "למאגר" in args[0]
    assert isinstance(kwargs.get("reply_markup"), ReplyKeyboardMarkup)


def test_persistent_keyboard_never_removed_in_handlers_module():
    """אף מקום בקוד לא צריך להסתיר את המקלדת הקבועה עם ReplyKeyboardRemove."""
    src = inspect.getsource(handlers)
    assert "ReplyKeyboardRemove" not in src


@pytest.mark.anyio
async def test_bug_report_cancel_restores_persistent_keyboard():
    update = MagicMock(spec=Update)
    update.message = MagicMock(spec=Message)
    update.message.text = handlers._BUG_REPORT_CANCEL
    update.message.chat_id = 888001
    update.message.reply_text = AsyncMock()
    update.effective_chat = Chat(id=888001, type="private")
    update.effective_user = User(id=444, is_bot=False, first_name="T")

    context = MagicMock()
    handlers._bug_report_prompt_chats.add(888001)

    with patch.object(handlers, "telegram_chat_id", return_value=888001):
        await handlers.on_text(update, context)

    args, kwargs = update.message.reply_text.await_args
    assert "בוטל" in args[0]
    assert isinstance(kwargs.get("reply_markup"), ReplyKeyboardMarkup)


@pytest.mark.anyio
async def test_bug_report_success_restores_persistent_keyboard():
    update = MagicMock(spec=Update)
    update.message = MagicMock(spec=Message)
    update.message.text = "יש בעיה בתמונה"
    update.message.chat_id = 888002
    update.message.reply_text = AsyncMock()
    update.effective_chat = Chat(id=888002, type="private")
    update.effective_user = User(id=555, is_bot=False, first_name="T")

    context = MagicMock()
    context.bot = MagicMock()
    handlers._bug_report_prompt_chats.add(888002)

    with patch.object(handlers, "telegram_chat_id", return_value=888002):
        with patch.object(handlers, "telegram_user_id", return_value=555):
            with patch.object(
                handlers, "_forward_bug_report_via_admin_bot", new_callable=AsyncMock
            ) as mock_fwd:
                mock_fwd.return_value = True
                await handlers.on_text(update, context)

    args, kwargs = update.message.reply_text.await_args
    assert "נשלח לצוות" in args[0]
    assert isinstance(kwargs.get("reply_markup"), ReplyKeyboardMarkup)
