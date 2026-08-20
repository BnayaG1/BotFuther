# -*- coding: utf-8 -*-
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Chat, InlineKeyboardMarkup, Message, Update, User

import bot.formulas as formulas
import bot.handlers as handlers
from bot.access import AccessSource, ImageAccessResult, ImageAccessStatus


def test_formulas_catalog_and_parse():
    assert len(formulas.FORMULA_TOPICS) >= 1
    kb = formulas.build_formulas_menu_keyboard()
    assert isinstance(kb, InlineKeyboardMarkup)
    assert formulas.parse_formula_callback("formula:menu") == ("menu", "")
    assert formulas.parse_formula_callback("formula:back") == ("back", "")
    assert formulas.parse_formula_callback("formula:topic:load_shapes_q_m") == (
        "topic",
        "load_shapes_q_m",
    )
    assert formulas.parse_formula_callback("buy:menu") is None
    titles = [t.title for t in formulas.FORMULA_TOPICS]
    assert titles == [
        "משוואות לתרגילי סמכים",
        "משוואות לתרגילי ריתום",
        "סרטוט הגרפים",
        "נוסחאות לחישוב שטחים",
        "וקטורים\\אלכסוניים",
        "הערות ודגשים חשובים",
    ]
    for topic in formulas.FORMULA_TOPICS:
        assert topic.image_path() is not None
        assert topic.image_path().is_file()


def test_start_keyboard_includes_formulas():
    kb = handlers.build_start_keyboard()
    texts = [btn.text for row in kb.inline_keyboard for btn in row]
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert handlers._PERSISTENT_FORMULAS_LABEL in texts
    assert "menu:formulas" in callbacks


def test_persistent_keyboard_includes_formulas():
    kb = handlers.build_persistent_keyboard()
    texts = [btn.text for row in kb.keyboard for btn in row]
    assert handlers._PERSISTENT_FORMULAS_LABEL in texts
    assert handlers._PERSISTENT_ASSISTANT_LABEL not in texts
    assert handlers._PERSISTENT_QUOTA_LABEL not in texts
    assert "🔄 איפוס תרגיל" not in texts


@pytest.mark.anyio
async def test_on_text_formulas_button_opens_menu():
    update = MagicMock(spec=Update)
    update.message = MagicMock(spec=Message)
    update.message.text = handlers._PERSISTENT_FORMULAS_LABEL
    update.effective_chat = Chat(id=999010, type="private")
    update.effective_user = User(id=1010, is_bot=False, first_name="T")
    update.message.reply_text = AsyncMock()

    context = MagicMock()

    with patch.object(handlers, "telegram_chat_id", return_value=999010):
        with patch.object(handlers, "telegram_user_id", return_value=1010):
            await handlers.on_text(update, context)

    update.message.reply_text.assert_awaited()
    args, kwargs = update.message.reply_text.await_args
    assert "נוסחאות" in args[0]
    assert "מנויי חבילה" not in args[0]
    assert isinstance(kwargs.get("reply_markup"), InlineKeyboardMarkup)


@pytest.mark.anyio
async def test_formulas_open_without_coupon_access():
    """נוסחאות פתוחות תמיד."""
    update = MagicMock(spec=Update)
    update.message = MagicMock(spec=Message)
    update.message.text = handlers._PERSISTENT_FORMULAS_LABEL
    update.effective_chat = Chat(id=999012, type="private")
    update.effective_user = User(id=1012, is_bot=False, first_name="T")
    update.message.reply_text = AsyncMock()

    context = MagicMock()

    with patch.object(handlers, "telegram_chat_id", return_value=999012):
        with patch.object(handlers, "telegram_user_id", return_value=1012):
            await handlers.on_text(update, context)

    update.message.reply_text.assert_awaited()
    args, kwargs = update.message.reply_text.await_args
    assert "נוסחאות" in args[0]
    assert "מנויי חבילה" not in args[0]
    kb = kwargs.get("reply_markup")
    assert isinstance(kb, InlineKeyboardMarkup)
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert any(cb.startswith("formula:") for cb in callbacks)


@pytest.mark.anyio
async def test_formulas_open_during_free_window():
    update = MagicMock(spec=Update)
    update.message = MagicMock(spec=Message)
    update.message.text = handlers._PERSISTENT_FORMULAS_LABEL
    update.effective_chat = Chat(id=999013, type="private")
    update.effective_user = User(id=1013, is_bot=False, first_name="T")
    update.message.reply_text = AsyncMock()

    context = MagicMock()

    with patch.object(handlers, "telegram_chat_id", return_value=999013):
        with patch.object(handlers, "telegram_user_id", return_value=1013):
            await handlers.on_text(update, context)

    update.message.reply_text.assert_awaited()
    args, kwargs = update.message.reply_text.await_args
    assert "נוסחאות" in args[0]
    assert "מנויי חבילה" not in args[0]
    assert isinstance(kwargs.get("reply_markup"), InlineKeyboardMarkup)


@pytest.mark.anyio
async def test_cmd_formulas_opens_menu():
    update = MagicMock(spec=Update)
    update.message = MagicMock(spec=Message)
    update.message.reply_text = AsyncMock()
    update.effective_chat = Chat(id=999011, type="private")

    context = MagicMock()
    with patch.object(handlers, "telegram_chat_id", return_value=999011):
        with patch.object(handlers, "telegram_user_id", return_value=1011):
            await handlers.cmd_formulas(update, context)

    update.message.reply_text.assert_awaited()
    args, kwargs = update.message.reply_text.await_args
    assert "נוסחאות" in args[0]
    assert isinstance(kwargs.get("reply_markup"), InlineKeyboardMarkup)


def test_bot_commands_menu_includes_formulas():
    from bot.__main__ import _BOT_COMMANDS

    names = [c.command for c in _BOT_COMMANDS]
    assert "formulas" in names
    assert "start" in names


def test_formulas_locked_message_and_keyboard():
    text = formulas.formulas_locked_reply_hebrew()
    assert "מנויי חבילה" in text
    assert "24" in text
    assert "תרגול" in text
    assert "נוסחאות" in text
    kb = formulas.build_formulas_locked_keyboard()
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "buy:menu" in callbacks
    assert "buy:redeem" not in callbacks


@pytest.mark.anyio
async def test_formula_back_opens_main_action_menu_without_welcome():
    update = MagicMock(spec=Update)
    query = MagicMock()
    query.data = "formula:back"
    query.answer = AsyncMock()
    query.message = MagicMock(spec=Message)
    query.message.chat_id = 999020
    query.message.delete = AsyncMock()
    update.callback_query = query
    update.effective_user = User(id=1020, is_bot=False, first_name="T")

    context = MagicMock()
    context.bot.send_message = AsyncMock()
    context.bot.delete_message = AsyncMock()

    with patch.object(handlers, "telegram_user_id", return_value=1020):
        await handlers.on_formula_callback(update, context)

    query.message.delete.assert_awaited_once()
    context.bot.send_message.assert_awaited_once()
    kwargs = context.bot.send_message.await_args.kwargs
    assert kwargs["text"] == "בחר/י פעולה:"
    assert isinstance(kwargs.get("reply_markup"), InlineKeyboardMarkup)
    welcome = handlers.build_start_welcome_text()
    assert welcome not in kwargs["text"]


@pytest.mark.anyio
async def test_formula_back_deletes_formulas_chat_messages():
    import bot.solution_session as solution_session

    chat_id = 999021
    solution_session.begin_formulas_chat_trail(chat_id)
    solution_session.append_formulas_chat_message_id(chat_id, 31)
    solution_session.append_formulas_chat_message_id(chat_id, 32)

    update = MagicMock(spec=Update)
    query = MagicMock()
    query.data = "formula:back"
    query.answer = AsyncMock()
    query.message = MagicMock(spec=Message)
    query.message.chat_id = chat_id
    query.message.delete = AsyncMock()
    update.callback_query = query
    update.effective_user = User(id=1021, is_bot=False, first_name="T")

    context = MagicMock()
    context.bot.send_message = AsyncMock()
    context.bot.delete_message = AsyncMock()

    with patch.object(handlers, "telegram_user_id", return_value=1021):
        await handlers.on_formula_callback(update, context)

    deleted = {
        call.kwargs["message_id"]
        for call in context.bot.delete_message.await_args_list
    }
    assert deleted == {31, 32}
    assert not solution_session.has_formulas_chat_trail(chat_id)


@pytest.mark.anyio
async def test_leaving_formulas_to_main_deletes_chat_messages():
    import bot.solution_session as solution_session

    chat_id = 999022
    solution_session.begin_formulas_chat_trail(chat_id)
    solution_session.append_formulas_chat_message_id(chat_id, 41)
    solution_session.append_formulas_chat_message_id(chat_id, 42)

    update = MagicMock(spec=Update)
    update.message = MagicMock(spec=Message)
    update.message.text = handlers._PERSISTENT_MAIN_LABEL
    update.effective_chat = Chat(id=chat_id, type="private")
    update.effective_user = User(id=1022, is_bot=False, first_name="T")
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.bot.delete_message = AsyncMock()
    context.bot.send_message = AsyncMock()

    with patch.object(handlers, "telegram_chat_id", return_value=chat_id):
        await handlers.on_text(update, context)

    deleted = {
        call.kwargs["message_id"]
        for call in context.bot.delete_message.await_args_list
    }
    assert deleted == {41, 42}
    assert not solution_session.has_formulas_chat_trail(chat_id)


@pytest.mark.anyio
async def test_leaving_formulas_to_give_exercise_deletes_chat_messages():
    import bot.solution_session as solution_session

    chat_id = 999023
    solution_session.begin_formulas_chat_trail(chat_id)
    solution_session.append_formulas_chat_message_id(chat_id, 51)
    solution_session.append_formulas_chat_message_id(chat_id, 52)
    solution_session.discard_practice_chat_trail(chat_id)

    update = MagicMock(spec=Update)
    query = MagicMock()
    query.data = "menu:give_exercise"
    query.answer = AsyncMock()
    query.message = MagicMock(spec=Message)
    query.message.chat_id = chat_id
    query.message.delete = AsyncMock()
    update.callback_query = query
    update.effective_user = User(id=1023, is_bot=False, first_name="T")

    context = MagicMock()
    context.bot.delete_message = AsyncMock()
    context.bot.send_photo = AsyncMock(return_value=MagicMock(message_id=601))
    context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=602))

    png = MagicMock()
    png.open = MagicMock()
    png.open.return_value.__enter__ = MagicMock(return_value=MagicMock())
    png.open.return_value.__exit__ = MagicMock(return_value=False)
    fake_art = MagicMock()
    fake_art.png_path = png
    fake_art.extracted = {"beam": {"L": 6.0, "supports": [], "loads": []}}

    ok = ImageAccessResult(
        status=ImageAccessStatus.OK,
        access_source=AccessSource.FREE_WINDOW,
        feature="practice",
    )
    with patch.object(handlers, "check_practice_feature_access", return_value=ok), \
        patch.object(handlers, "consume_practice_slot", return_value=ok), \
        patch(
            "exercise_generator.pipeline.generate_exercise", return_value=fake_art
        ):
        await handlers.on_menu_callback(update, context)

    deleted = {
        call.kwargs["message_id"]
        for call in context.bot.delete_message.await_args_list
    }
    assert 51 in deleted and 52 in deleted
    assert not solution_session.has_formulas_chat_trail(chat_id)
