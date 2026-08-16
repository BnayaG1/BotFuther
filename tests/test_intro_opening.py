# -*- coding: utf-8 -*-
"""בדיקות למבוא לסטטיקה — פתיחה + כפתורי נושאים."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import InlineKeyboardMarkup, ReplyKeyboardMarkup

import bot.handlers as handlers
import intro.opening as opening


def test_opening_message_and_topic_buttons():
    text = opening.opening_message_hebrew()
    assert text == "לאן תרצה לקחת את זה?"
    kb = opening.build_opening_keyboard()
    assert isinstance(kb, InlineKeyboardMarkup)
    buttons = [btn for row in kb.inline_keyboard for btn in row]
    labels = [btn.text for btn in buttons]
    assert labels == ["מבוא", "עומס מפורס", "עומס אלכסוני"]

    sub_kb = opening.build_how_to_approach_keyboard()
    assert isinstance(sub_kb, InlineKeyboardMarkup)
    sub_buttons = [btn for row in sub_kb.inline_keyboard for btn in row]
    sub_labels = [btn.text for btn in sub_buttons]
    assert sub_labels == ["ריתום", "סמכים"]

    assert opening.parse_intro_callback("intro:how_to_approach") == "how_to_approach"
    assert opening.parse_intro_callback("intro:distributed_load") == "distributed_load"
    assert opening.parse_intro_callback("intro:inclined_load") == "inclined_load"
    assert opening.parse_intro_callback("intro:practice_inclined") == "practice_inclined"
    assert opening.parse_intro_callback("intro:fixed_support_exercises") == "fixed_support_exercises"
    assert opening.parse_intro_callback("intro:support_exercises") == "support_exercises"
    assert opening.parse_intro_callback("intro:main") == "main"
    assert opening.parse_intro_callback("menu:intro") is None


def test_build_mavo_exercise():
    ex = opening.build_mavo_exercise()
    assert ex.L == 10.0
    assert len(ex.supports) == 2
    assert ex.supports[0].type == "pin" and ex.supports[0].x == 0.0
    assert ex.supports[1].type == "roller" and ex.supports[1].x == 10.0
    assert len(ex.loads) == 2
    assert ex.loads[0].x == 3.0 and ex.loads[0].Fy == 10.0
    assert ex.loads[1].x == 8.0 and ex.loads[1].Fx == 5.0
    assert len(ex.dim_row_top.segments) == 3
    assert ex.dim_row_top.segments[0].x1 == 0.0 and ex.dim_row_top.segments[0].x2 == 3.0
    assert ex.dim_row_top.segments[1].x1 == 3.0 and ex.dim_row_top.segments[1].x2 == 8.0
    assert ex.dim_row_top.segments[2].x1 == 8.0 and ex.dim_row_top.segments[2].x2 == 10.0
    assert len(ex.dim_row_bottom.segments) == 1
    assert ex.dim_row_bottom.segments[0].x1 == 0.0 and ex.dim_row_bottom.segments[0].x2 == 10.0


def test_build_fixed_mavo_exercise():
    ex = opening.build_fixed_mavo_exercise()
    assert ex.L == 10.0
    assert ex.support_mode == "cantilever"
    assert len(ex.supports) == 1
    assert ex.supports[0].type == "fixed" and ex.supports[0].x == 0.0
    assert len(ex.loads) == 2
    assert ex.loads[0].x == 3.0 and ex.loads[0].Fy == 10.0
    assert ex.loads[1].x == 8.0 and ex.loads[1].Fx == 5.0
    assert len(ex.dim_row_top.segments) == 3
    assert len(ex.dim_row_bottom.segments) == 1


@pytest.mark.anyio
async def test_menu_intro_sends_opening():
    update = MagicMock()
    query = MagicMock()
    query.data = "menu:intro"
    query.answer = AsyncMock()
    query.message = MagicMock()
    query.message.chat_id = 991001
    query.message.delete = AsyncMock()
    update.callback_query = query
    update.effective_chat = MagicMock(id=991001)

    context = MagicMock()
    context.bot.send_message = AsyncMock()

    await handlers.on_menu_callback(update, context)

    query.answer.assert_awaited()
    context.bot.send_message.assert_awaited()
    kwargs = context.bot.send_message.await_args.kwargs
    assert kwargs["text"] == "לאן תרצה לקחת את זה?"
    assert isinstance(kwargs.get("reply_markup"), InlineKeyboardMarkup)


@pytest.mark.anyio
async def test_on_intro_callback_how_to_approach():
    update = MagicMock()
    query = MagicMock()
    query.data = "intro:how_to_approach"
    query.answer = AsyncMock()
    query.message = MagicMock()
    query.message.chat_id = 991008
    query.message.delete = AsyncMock()
    update.callback_query = query
    update.effective_chat = MagicMock(id=991008)

    context = MagicMock()
    context.bot.send_message = AsyncMock()
    context.bot.send_photo = AsyncMock()

    await handlers.on_intro_callback(update, context)

    query.answer.assert_awaited()
    assert context.bot.send_message.call_count == 2
    call_args_list = context.bot.send_message.call_args_list
    assert call_args_list[0].kwargs["text"] == opening.how_to_approach_message_hebrew()
    assert call_args_list[1].kwargs["text"] == opening.how_to_approach_second_message_hebrew()
    assert isinstance(call_args_list[0].kwargs.get("reply_markup"), InlineKeyboardMarkup)
    assert isinstance(call_args_list[1].kwargs.get("reply_markup"), InlineKeyboardMarkup)
    context.bot.send_photo.assert_not_called()


@pytest.mark.anyio
async def test_on_intro_callback_support_exercises():
    update = MagicMock()
    query = MagicMock()
    query.data = "intro:support_exercises"
    query.answer = AsyncMock()
    query.message = MagicMock()
    query.message.chat_id = 991009
    query.message.delete = AsyncMock()
    update.callback_query = query
    update.effective_chat = MagicMock(id=991009)

    context = MagicMock()
    context.bot.send_message = AsyncMock()
    context.bot.send_photo = AsyncMock()

    await handlers.on_intro_callback(update, context)

    query.answer.assert_awaited()
    query.message.delete.assert_awaited_once()
    context.bot.send_photo.assert_awaited_once()
    context.bot.send_message.assert_awaited_once()
    msg_args = context.bot.send_message.await_args.kwargs
    assert "תרגיל סמכים פשוט" in msg_args["text"]
    assert isinstance(msg_args.get("reply_markup"), InlineKeyboardMarkup)


@pytest.mark.anyio
async def test_on_intro_callback_fixed_support_exercises():
    update = MagicMock()
    query = MagicMock()
    query.data = "intro:fixed_support_exercises"
    query.answer = AsyncMock()
    query.message = MagicMock()
    query.message.chat_id = 991010
    query.message.delete = AsyncMock()
    update.callback_query = query
    update.effective_chat = MagicMock(id=991010)

    context = MagicMock()
    context.bot.send_message = AsyncMock()
    context.bot.send_photo = AsyncMock()

    await handlers.on_intro_callback(update, context)

    query.answer.assert_awaited()
    query.message.delete.assert_awaited_once()
    context.bot.send_photo.assert_awaited_once()
    context.bot.send_message.assert_awaited_once()
    msg_args = context.bot.send_message.await_args.kwargs
    assert "תרגיל ריתום פשוט" in msg_args["text"]
    assert isinstance(msg_args.get("reply_markup"), InlineKeyboardMarkup)


@pytest.mark.anyio
async def test_on_intro_callback_inclined_load():
    update = MagicMock()
    query = MagicMock()
    query.data = "intro:inclined_load"
    query.answer = AsyncMock()
    query.message = MagicMock()
    query.message.chat_id = 991002
    query.message.delete = AsyncMock()
    update.callback_query = query
    update.effective_chat = MagicMock(id=991002)

    context = MagicMock()
    context.bot.send_message = AsyncMock()
    context.bot.send_photo = AsyncMock()

    await handlers.on_intro_callback(update, context)

    query.answer.assert_awaited()
    assert context.bot.send_message.await_count == 2
    first_send = context.bot.send_message.await_args_list[0].kwargs
    second_send = context.bot.send_message.await_args_list[1].kwargs
    assert isinstance(first_send.get("reply_markup"), ReplyKeyboardMarkup)
    assert isinstance(second_send.get("reply_markup"), ReplyKeyboardMarkup)
    assert "בסטטיקה, העיקרון הוא" in first_send["text"]
    assert "בתרגיל לדוגמא שנשלח עכשיו" in second_send["text"]
    assert "ומעכשיו נתייחס לעומס האלכסוני כאילו הוא נראה ככה בתרגיל:" in second_send["text"]
    assert context.bot.send_photo.await_count == 2
    first_photo_send = context.bot.send_photo.await_args_list[0].kwargs
    assert isinstance(first_photo_send.get("reply_markup"), ReplyKeyboardMarkup)
    second_photo_send = context.bot.send_photo.await_args_list[1].kwargs
    assert isinstance(second_photo_send.get("reply_markup"), InlineKeyboardMarkup)


@pytest.mark.anyio
async def test_on_intro_callback_practice_inclined():
    update = MagicMock()
    query = MagicMock()
    query.data = "intro:practice_inclined"
    query.answer = AsyncMock()
    query.message = MagicMock()
    query.message.chat_id = 991003
    query.message.delete = AsyncMock()
    update.callback_query = query
    update.effective_chat = MagicMock(id=991003)

    context = MagicMock()
    context.chat_data = {}
    context.bot.send_message = AsyncMock()
    context.bot.send_photo = AsyncMock()
    context.bot.delete_message = AsyncMock()

    await handlers.on_intro_callback(update, context)

    query.answer.assert_awaited()
    context.bot.send_photo.assert_awaited_once()
    context.bot.send_message.assert_awaited_once()
    kwargs = context.bot.send_message.await_args.kwargs
    assert "בוא נראה שהבנת את זה" in kwargs["text"]


def test_build_inclined_exercise_spec():
    from intro.inclined_load.generator import build_inclined_exercise

    ex = build_inclined_exercise(seed=42)
    assert ex.L == 10.0
    assert len(ex.supports) == 2
    assert ex.supports[0].type == "pin"
    assert ex.supports[0].x == 0.0
    assert ex.supports[1].type == "roller"
    assert ex.supports[1].x == 10.0
    assert len(ex.loads) == 1
    assert ex.loads[0].type == "inclined"
    assert ex.loads[0].x == 5.0


@pytest.mark.anyio
async def test_inclined_practice_evaluation_correct_and_incorrect():
    # 1. Start practice inclined
    update = MagicMock()
    query = MagicMock()
    query.data = "intro:practice_inclined"
    query.answer = AsyncMock()
    query.message = MagicMock()
    query.message.chat_id = 991005
    query.message.delete = AsyncMock()
    update.callback_query = query
    update.effective_chat = MagicMock(id=991005)

    context = MagicMock()
    context.chat_data = {}
    context.bot.send_message = AsyncMock()
    context.bot.send_photo = AsyncMock()

    await handlers.on_intro_callback(update, context)

    assert "inclined_practice_active" in context.chat_data
    active_data = context.chat_data["inclined_practice_active"]
    fy = active_data["fy"]
    fx = active_data["fx"]

    # 2. Test incorrect input
    text_update = MagicMock()
    text_update.message = MagicMock()
    text_update.message.text = "1.00, 2.00"
    text_update.effective_chat = MagicMock(id=991005)

    await handlers.on_text(text_update, context)

    assert context.bot.send_message.call_count == 2
    err_send = context.bot.send_message.await_args_list[-1].kwargs
    assert "נראה שטעית איפשהו" in err_send["text"]
    assert "אנכי -" in err_send["text"]
    assert "צירי -" in err_send["text"]
    kb = err_send["reply_markup"]
    assert isinstance(kb, InlineKeyboardMarkup)
    labels = [btn.text for row in kb.inline_keyboard for btn in row]
    assert labels == ["אנסה שוב", "הצג פתרון"]

    # 3. Test "אנסה שוב" callback
    try_again_update = MagicMock()
    q2 = MagicMock()
    q2.data = "intro:inclined_try_again"
    q2.answer = AsyncMock()
    q2.message = MagicMock()
    q2.message.delete = AsyncMock()
    q2.message.chat_id = 991005
    try_again_update.callback_query = q2

    await handlers.on_intro_callback(try_again_update, context)
    assert context.chat_data["inclined_practice_active"]["awaiting_input"] is True
    try_again_msg = context.bot.send_message.await_args_list[-1].kwargs
    assert "בוא ננסה שוב." in try_again_msg["text"]

    # 4. Test correct input
    text_update_correct = MagicMock()
    text_update_correct.message = MagicMock()
    text_update_correct.message.text = f"{round(fy, 2)}, {round(fx, 2)}"
    text_update_correct.effective_chat = MagicMock(id=991005)

    await handlers.on_text(text_update_correct, context)

    ok_send = context.bot.send_message.await_args_list[-1].kwargs
    assert "צדקת!" in ok_send["text"]
    ok_kb = ok_send["reply_markup"]
    assert isinstance(ok_kb, InlineKeyboardMarkup)
    ok_labels = [btn.text for row in ok_kb.inline_keyboard for btn in row]
    assert ok_labels == ["תרגול", "ראשי"]
    callbacks = [btn.callback_data for row in ok_kb.inline_keyboard for btn in row]
    assert "menu:main" in callbacks
    assert "inclined_practice_active" not in context.chat_data


@pytest.mark.anyio
async def test_inclined_practice_invalid_format():
    update = MagicMock()
    query = MagicMock()
    query.data = "intro:practice_inclined"
    query.answer = AsyncMock()
    query.message = MagicMock()
    query.message.chat_id = 991006
    query.message.delete = AsyncMock()
    update.callback_query = query
    update.effective_chat = MagicMock(id=991006)

    context = MagicMock()
    context.chat_data = {}
    context.bot.send_message = AsyncMock()
    context.bot.send_photo = AsyncMock()

    await handlers.on_intro_callback(update, context)

    # Send non-number / invalid format text
    bad_text_update = MagicMock()
    bad_text_update.message = MagicMock()
    bad_text_update.message.text = "לא יודע"
    bad_text_update.effective_chat = MagicMock(id=991006)

    await handlers.on_text(bad_text_update, context)

    fmt_send = context.bot.send_message.await_args_list[-1].kwargs
    assert "בשביל שאצליח להבין את התשובות שרשמת, זה צריך להיראות בנוסח הבא - מספר,מספר." in fmt_send["text"]
    assert "לדוגמא - 4.67,5" in fmt_send["text"]
    assert context.chat_data["inclined_practice_active"]["awaiting_input"] is True


@pytest.mark.anyio
async def test_inclined_practice_cleanup_on_main_or_practice():
    chat_id = 991007
    update = MagicMock()
    query = MagicMock()
    query.data = "intro:practice_inclined"
    query.answer = AsyncMock()
    query.message = MagicMock()
    query.message.chat_id = chat_id
    query.message.delete = AsyncMock()
    update.callback_query = query
    update.effective_chat = MagicMock(id=chat_id)

    context = MagicMock()
    context.chat_data = {}
    context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=1001))
    context.bot.send_photo = AsyncMock(return_value=MagicMock(message_id=1000))
    context.bot.delete_message = AsyncMock()

    await handlers.on_intro_callback(update, context)

    # User sends text
    user_text_update = MagicMock()
    user_text_update.message = MagicMock(message_id=2001)
    user_text_update.message.text = "1.0, 2.0"
    user_text_update.effective_chat = MagicMock(id=chat_id)

    await handlers.on_text(user_text_update, context)

    # Check user message id 2001 was tracked in practice trail
    from bot import solution_session
    tracked_ids = solution_session._practice_chat_message_ids.get(chat_id, [])
    assert 2001 in tracked_ids

    # Click menu:main
    main_update = MagicMock()
    q_main = MagicMock()
    q_main.data = "menu:main"
    q_main.answer = AsyncMock()
    q_main.message = MagicMock()
    q_main.message.chat_id = chat_id
    q_main.message.delete = AsyncMock()
    main_update.callback_query = q_main
    main_update.effective_chat = MagicMock(id=chat_id)

    await handlers.on_menu_callback(main_update, context)

    # Verify delete_message was called for user message 2001
    deleted_mids = [call.kwargs.get("message_id") for call in context.bot.delete_message.await_args_list]
    assert 2001 in deleted_mids


@pytest.mark.anyio
async def test_on_intro_callback_distributed_load():
    update = MagicMock()
    query = MagicMock()
    query.data = "intro:distributed_load"
    query.answer = AsyncMock()
    query.message = MagicMock()
    query.message.chat_id = 991010
    query.message.delete = AsyncMock()
    update.callback_query = query
    update.effective_chat = MagicMock(id=991010)

    context = MagicMock()
    context.bot.send_message = AsyncMock()
    context.bot.send_photo = AsyncMock()

    await handlers.on_intro_callback(update, context)

    query.answer.assert_awaited()
    assert context.bot.send_message.await_count == 3
    first_send = context.bot.send_message.await_args_list[0].kwargs
    second_send = context.bot.send_message.await_args_list[1].kwargs
    third_send = context.bot.send_message.await_args_list[2].kwargs
    assert "עכשיו נעבור על עומס מפורס ונבין מה הוא." in first_send["text"]
    assert "בתרגיל שיצא לנו יש עומס מפורס במשקל של" in second_send["text"]
    assert "הכח השקול יהיה המשקל" in second_send["text"]
    assert "כשנמצא את זה נתייחס במציאת הריאקציות לעומס הזה כאילו הוא נראה ככה:" in second_send["text"]
    assert "תרצה לתרגל את זה, או שנראה מה עושים כשעומס מפורס מתפרס על סמך?" in third_send["text"]
    assert third_send.get("reply_markup") is not None
    assert context.bot.send_photo.await_count == 2


@pytest.mark.anyio
async def test_on_intro_callback_practice_distributed():
    update = MagicMock()
    query = MagicMock()
    query.data = "intro:practice_distributed"
    query.answer = AsyncMock()
    query.message = MagicMock()
    query.message.chat_id = 991011
    query.message.delete = AsyncMock()
    update.callback_query = query
    update.effective_chat = MagicMock(id=991011)

    context = MagicMock()
    context.chat_data = {}
    context.bot.send_photo = AsyncMock()
    context.bot.send_message = AsyncMock()

    await handlers.on_intro_callback(update, context)

    query.answer.assert_awaited()
    context.bot.send_photo.assert_awaited_once()
    context.bot.send_message.assert_awaited_once()
    msg_send = context.bot.send_message.await_args.kwargs
    assert "בתרגיל שנשלח פה למעלה יש עומס מפורס." in msg_send["text"]
    assert "distributed_practice_active" in context.chat_data
    assert context.chat_data["distributed_practice_active"]["awaiting_input"] is True


@pytest.mark.anyio
async def test_distributed_practice_evaluation_correct_and_incorrect():
    chat_id = 991012
    update = MagicMock()
    query = MagicMock()
    query.data = "intro:practice_distributed"
    query.answer = AsyncMock()
    query.message = MagicMock()
    query.message.chat_id = chat_id
    query.message.delete = AsyncMock()
    update.callback_query = query
    update.effective_chat = MagicMock(id=chat_id)

    context = MagicMock()
    context.chat_data = {}
    context.bot.send_message = AsyncMock()
    context.bot.send_photo = AsyncMock()

    await handlers.on_intro_callback(update, context)

    active_data = context.chat_data["distributed_practice_active"]
    req_force = active_data["equivalent_force"]
    req_dist = active_data["mid_x"]

    # 1. Incorrect input
    bad_ans_update = MagicMock()
    bad_ans_update.message = MagicMock()
    bad_ans_update.message.text = "1.0, 2.0"
    bad_ans_update.effective_chat = MagicMock(id=chat_id)

    await handlers.on_text(bad_ans_update, context)

    err_send = context.bot.send_message.await_args_list[-1].kwargs
    assert "נראה שטעית איפשהו" in err_send["text"]
    assert "כח שקול -" in err_send["text"]

    # 2. Try again callback
    try_again_update = MagicMock()
    q2 = MagicMock()
    q2.data = "intro:distributed_try_again"
    q2.answer = AsyncMock()
    q2.message = MagicMock()
    q2.message.delete = AsyncMock()
    q2.message.chat_id = chat_id
    try_again_update.callback_query = q2

    await handlers.on_intro_callback(try_again_update, context)
    assert context.chat_data["distributed_practice_active"]["awaiting_input"] is True

    # 3. Correct input
    ok_ans_update = MagicMock()
    ok_ans_update.message = MagicMock()
    ok_ans_update.message.text = f"{req_force},{req_dist}"
    ok_ans_update.effective_chat = MagicMock(id=chat_id)

    await handlers.on_text(ok_ans_update, context)

    ok_send = context.bot.send_message.await_args_list[-1].kwargs
    assert "צדקת!" in ok_send["text"]
    assert "distributed_practice_active" not in context.chat_data


@pytest.mark.anyio
async def test_distributed_practice_invalid_format():
    chat_id = 991013
    update = MagicMock()
    query = MagicMock()
    query.data = "intro:practice_distributed"
    query.answer = AsyncMock()
    query.message = MagicMock()
    query.message.chat_id = chat_id
    query.message.delete = AsyncMock()
    update.callback_query = query
    update.effective_chat = MagicMock(id=chat_id)

    context = MagicMock()
    context.chat_data = {}
    context.bot.send_message = AsyncMock()
    context.bot.send_photo = AsyncMock()

    await handlers.on_intro_callback(update, context)

    bad_fmt_update = MagicMock()
    bad_fmt_update.message = MagicMock()
    bad_fmt_update.message.reply_text = AsyncMock()
    bad_fmt_update.message.text = "לא יודע"
    bad_fmt_update.effective_chat = MagicMock(id=chat_id)

    await handlers.on_text(bad_fmt_update, context)

    fmt_send = context.bot.send_message.await_args_list[-1].kwargs
    assert "בשביל שאצליח להבין את התשובות שרשמת, זה צריך להיראות בנוסח הבא - מספר,מספר." in fmt_send["text"]








def test_build_distributed_exercise_spec():
    from intro.distributed_load.generator import build_distributed_exercise

    for s in range(50):
        ex = build_distributed_exercise(seed=s)
        assert ex.L == 10.0
        assert len(ex.supports) == 2
        assert ex.supports[0].type == "pin"
        assert ex.supports[0].x == 0.0
        assert ex.supports[1].type == "roller"
        assert ex.supports[1].x == 10.0
        assert len(ex.loads) == 1
        ld = ex.loads[0]
        assert ld.type == "distributed"
        assert 2.0 <= ld.w <= 8.0
        assert ld.w.is_integer()
        length = ld.x2 - ld.x1
        assert length in (4.0, 5.0, 6.0)
        assert ld.x1 >= 2.0
        assert ld.x2 <= 8.0


def test_build_distributed_on_support_exercise_spec():
    from intro.distributed_load.generator import build_distributed_on_support_exercise

    for s in range(50):
        ex = build_distributed_on_support_exercise(seed=s)
        assert ex.L == 10.0
        assert len(ex.supports) == 2
        assert len(ex.loads) == 1
        ld = ex.loads[0]
        assert ld.type == "distributed"
        xA = ex.supports[0].x
        xB = ex.supports[1].x
        if xA > 0.0:
            # סמך שמאל זז
            assert 1.0 <= xA <= 4.0
            assert xB == 10.0
            assert ld.x1 < xA < ld.x2
        else:
            # סמך ימין זז
            assert xA == 0.0
            assert 6.0 <= xB <= 9.0
            assert ld.x1 < xB < ld.x2


@pytest.mark.anyio
async def test_on_intro_callback_distributed_on_support():
    update = MagicMock()
    query = MagicMock()
    query.data = "intro:distributed_on_support"
    query.answer = AsyncMock()
    query.message = MagicMock()
    query.message.delete = AsyncMock()
    query.message.chat_id = 12345
    update.callback_query = query
    update.effective_chat = MagicMock(id=12345)

    context = MagicMock()
    context.chat_data = {}
    context.bot.send_photo = AsyncMock()
    context.bot.send_message = AsyncMock()

    await handlers.on_intro_callback(update, context)

    query.answer.assert_awaited()
    context.bot.send_photo.assert_awaited_once()
    context.bot.send_message.assert_awaited_once()
    exp_send = context.bot.send_message.await_args.kwargs
    assert "כשיש לנו בתרגיל 2 סמכים" in exp_send["text"]
    assert "המשקל בשתי החלקים של העומס יישאר זהה" in exp_send["text"]
    assert exp_send.get("reply_markup") is not None
