# -*- coding: utf-8 -*-
"""רענון טיוטה אחרי תיקון NL — מחיקת הודעות + אישור מחדש."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.draft_keyboard import DRAFT_FIXED_TEXT
from bot.draft_preview import refresh_draft_after_correction, wipe_draft_conversation
from bot.draft_session import (
    clear_vision_context,
    get_draft_cleanup_message_ids,
    get_draft_message_ref,
    get_stored_vision_extracted,
    register_draft_cleanup_id,
    set_draft_pending,
    set_draft_source_user_message_id,
)


@pytest.mark.anyio
async def test_refresh_draft_after_correction_sends_fixed_with_approve():
    chat_id = 4242
    clear_vision_context(chat_id)
    set_draft_pending(
        chat_id,
        {"beam": {"L": 6.0, "loads": []}},
        "old instruct",
        message_id=100,
        photo_message_id=99,
    )

    context = MagicMock()
    context.bot.send_photo = AsyncMock(return_value=MagicMock(message_id=201))
    context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=202))
    context.bot.delete_message = AsyncMock()

    with patch(
        "bot.draft_preview.render_exercise_problem_png_bytes",
        return_value=b"png-bytes",
    ):
        ok, err = await refresh_draft_after_correction(
            context,
            chat_id,
            {"beam": {"L": 6.0, "loads": [{"type": "point", "x": 1, "Fy": 2}]}},
            user_message_id=150,
        )

    assert ok is True
    assert err is None
    context.bot.send_message.assert_awaited()
    kwargs = context.bot.send_message.await_args.kwargs
    assert kwargs["text"] == DRAFT_FIXED_TEXT
    assert kwargs["reply_markup"] is not None
    buttons = [
        btn.callback_data
        for row in kwargs["reply_markup"].inline_keyboard
        for btn in row
    ]
    assert buttons == ["d:a"]

    deleted = {
        call.kwargs.get("message_id") or call.args[1]
        for call in context.bot.delete_message.await_args_list
    }
    # user correction + old instruct + old photo
    assert 150 in deleted
    assert 100 in deleted
    assert 99 in deleted

    ref = get_draft_message_ref(chat_id)
    assert ref == (chat_id, 202)
    stored = get_stored_vision_extracted(chat_id)
    assert stored is not None
    clear_vision_context(chat_id)


@pytest.mark.anyio
async def test_wipe_draft_conversation_keeps_user_source_image():
    chat_id = 4243
    clear_vision_context(chat_id)
    set_draft_source_user_message_id(chat_id, 50)
    set_draft_pending(
        chat_id,
        {"beam": {"L": 6.0}},
        "instruct",
        message_id=101,
        photo_message_id=100,
    )
    register_draft_cleanup_id(chat_id, 100)
    register_draft_cleanup_id(chat_id, 101)
    register_draft_cleanup_id(chat_id, 150)  # user correction
    # ניסיון לרשום את תמונת המקור — חייב להידחות
    register_draft_cleanup_id(chat_id, 50)

    context = MagicMock()
    context.bot.delete_message = AsyncMock()

    ids_before = get_draft_cleanup_message_ids(chat_id, keep_user_source=True)
    assert 50 not in ids_before
    assert 100 in ids_before and 150 in ids_before

    await wipe_draft_conversation(context, chat_id, message_ids=ids_before)

    deleted = {
        call.kwargs.get("message_id")
        for call in context.bot.delete_message.await_args_list
    }
    assert 50 not in deleted
    assert {100, 101, 150}.issubset(deleted)
    clear_vision_context(chat_id)


def test_store_vision_context_preserves_cleanup_ids():
    from bot.draft_session import store_vision_context

    chat_id = 4244
    clear_vision_context(chat_id)
    set_draft_source_user_message_id(chat_id, 9)
    set_draft_pending(
        chat_id,
        {"beam": {"L": 1.0}},
        "t",
        message_id=11,
        photo_message_id=10,
    )
    register_draft_cleanup_id(chat_id, 12)
    store_vision_context(chat_id, {"beam": {"L": 1.0}}, {"result": {}})
    ids = get_draft_cleanup_message_ids(chat_id, keep_user_source=True)
    assert 10 in ids and 11 in ids and 12 in ids
    assert 9 not in ids
    clear_vision_context(chat_id)
