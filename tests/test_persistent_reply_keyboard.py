# -*- coding: utf-8 -*-
from __future__ import annotations

import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Chat, Message, Update, User
from telegram import InlineKeyboardMarkup, ReplyKeyboardMarkup

import bot.handlers as handlers
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

    with patch.object(handlers, "quota_status_for_user", return_value="quota reply"):
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
        with patch.object(handlers, "telegram_user_id", return_value=333):
            with patch.object(handlers, "check_solve_access", return_value=handlers.ImageAccessResult(status=handlers.ImageAccessStatus.OK)):

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
    assert "BnayaG" not in texts
    assert "➕" not in texts
    assert not any("הוסף תרגיל למאגר" in t for t in texts)


def test_persistent_keyboard_includes_main_button():
    kb = handlers.build_persistent_keyboard()
    texts = [btn.text for row in kb.keyboard for btn in row]
    assert handlers._PERSISTENT_MAIN_LABEL in texts
    assert "ראשי" in texts
    assert handlers._PERSISTENT_QUOTA_LABEL not in texts
    assert handlers._PERSISTENT_ASSISTANT_LABEL not in texts
    assert handlers._START_INTRO_LABEL not in texts


@pytest.mark.anyio
async def test_on_text_main_button_shows_start_menu():
    update = MagicMock(spec=Update)
    update.message = MagicMock(spec=Message)
    update.message.text = handlers._PERSISTENT_MAIN_LABEL
    update.message.message_id = 50
    update.effective_chat = Chat(id=999005, type="private")
    update.effective_user = User(id=777, is_bot=False, first_name="T")
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.bot.send_message = AsyncMock()
    context.bot.delete_message = AsyncMock()
    chat_id = 999005

    with patch.object(handlers, "telegram_chat_id", return_value=chat_id):
        with patch.object(handlers, "has_active_assistant_progress", return_value=False):
            with patch.object(handlers, "wipe_chat_after_anchor", new_callable=AsyncMock) as mock_wipe:
                await handlers.on_text(update, context)

    mock_wipe.assert_awaited_once()
    assert mock_wipe.await_args.kwargs.get("through_message_id") == 50
    context.bot.send_message.assert_awaited_once()
    args, kwargs = context.bot.send_message.await_args
    assert kwargs.get("text") == "בחר/י פעולה:" or (args and args[0] == chat_id)
    assert kwargs.get("text") == "בחר/י פעולה:"
    assert isinstance(kwargs.get("reply_markup"), InlineKeyboardMarkup)


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


@pytest.mark.anyio
async def test_on_text_intro_button_triggers_intro_opening():
    update = MagicMock(spec=Update)
    update.message = MagicMock(spec=Message)
    update.message.text = handlers._START_INTRO_LABEL
    update.effective_chat = Chat(id=777001, type="private")
    update.effective_user = User(id=888, is_bot=False, first_name="T")

    context = MagicMock()

    with patch.object(handlers, "telegram_chat_id", return_value=777001):
        with patch.object(handlers, "_send_intro_opening", new_callable=AsyncMock) as mock_intro:
            await handlers.on_text(update, context)
            mock_intro.assert_awaited_once_with(context, 777001)


@pytest.mark.anyio
async def test_on_text_persistent_buttons_work_during_assistant_progress():
    update = MagicMock(spec=Update)
    update.message = MagicMock(spec=Message)
    update.message.text = handlers._PERSISTENT_FORMULAS_LABEL
    update.effective_chat = Chat(id=777002, type="private")
    update.effective_user = User(id=889, is_bot=False, first_name="T")

    context = MagicMock()

    with patch.object(handlers, "telegram_chat_id", return_value=777002):
        with patch.object(handlers, "has_active_assistant_progress", return_value=True):
            with patch.object(handlers, "_send_formulas_menu", new_callable=AsyncMock) as mock_formulas:
                await handlers.on_text(update, context)
                mock_formulas.assert_awaited_once()


def test_persistent_keyboard_admin_vs_regular():
    # Regular user
    kb_user = handlers.build_persistent_keyboard(is_admin=False)
    texts_user = [btn.text for row in kb_user.keyboard for btn in row]
    assert handlers._PERSISTENT_ADMIN_LABEL not in texts_user
    assert handlers._PERSISTENT_MAIN_LABEL in texts_user

    # Admin user
    kb_admin = handlers.build_persistent_keyboard(is_admin=True)
    texts_admin = [btn.text for row in kb_admin.keyboard for btn in row]
    assert handlers._PERSISTENT_ADMIN_LABEL in texts_admin
    assert handlers._PERSISTENT_MAIN_LABEL in texts_admin
    assert handlers._PERSISTENT_BUG_REPORT_LABEL in texts_admin
    assert handlers._PERSISTENT_FORMULAS_LABEL in texts_admin


@pytest.mark.anyio
async def test_on_text_admin_button_triggers_admin_system(monkeypatch):
    monkeypatch.setattr("bot.config.ADMIN_USER_IDS", frozenset({9999}))
    monkeypatch.setattr(handlers, "ADMIN_USER_IDS", frozenset({9999}))
    update = MagicMock(spec=Update)
    update.message = MagicMock(spec=Message)
    update.message.text = handlers._PERSISTENT_ADMIN_LABEL
    update.effective_chat = Chat(id=9999, type="private")
    update.effective_user = User(id=9999, is_bot=False, first_name="Admin")
    update.message.reply_text = AsyncMock()

    context = MagicMock()

    with patch.object(handlers, "telegram_chat_id", return_value=9999):
        with patch.object(handlers, "telegram_user_id", return_value=9999):
            await handlers.on_text(update, context)

    assert update.message.reply_text.await_count == 2
    args0, kwargs0 = update.message.reply_text.await_args_list[0]
    assert "אדמין" in args0[0]
    args1, kwargs1 = update.message.reply_text.await_args_list[1]
    assert "מקלדת ניהול" in args1[0]
    admin_kb = kwargs1.get("reply_markup")
    assert isinstance(admin_kb, ReplyKeyboardMarkup)
    admin_texts = [btn.text for row in admin_kb.keyboard for btn in row]
    assert handlers._PERSISTENT_ENGINEER_LABEL in admin_texts


@pytest.mark.anyio
async def test_on_text_engineer_button_returns_to_main_system(monkeypatch):
    monkeypatch.setattr("bot.config.ADMIN_USER_IDS", frozenset({9999}))
    monkeypatch.setattr(handlers, "ADMIN_USER_IDS", frozenset({9999}))
    update = MagicMock(spec=Update)
    update.message = MagicMock(spec=Message)
    update.message.text = handlers._PERSISTENT_ENGINEER_LABEL
    update.effective_chat = Chat(id=9999, type="private")
    update.effective_user = User(id=9999, is_bot=False, first_name="Admin")
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {"admin_awaiting_custom_qty": "30_days"}

    with patch.object(handlers, "telegram_chat_id", return_value=9999):
        with patch.object(handlers, "telegram_user_id", return_value=9999):
            with patch.object(handlers, "cmd_start", new_callable=AsyncMock) as mock_start:
                await handlers.on_text(update, context)

    assert "admin_awaiting_custom_qty" not in context.user_data
    mock_start.assert_awaited_once()
    update.message.reply_text.assert_awaited_once()
    args, kwargs = update.message.reply_text.await_args
    assert "חזרת למערכת הראשית" in args[0]
    user_kb = kwargs.get("reply_markup")
    assert isinstance(user_kb, ReplyKeyboardMarkup)


