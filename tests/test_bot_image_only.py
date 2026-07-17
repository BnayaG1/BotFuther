# -*- coding: utf-8 -*-
"""בדיקות: בוט תמונה בלבד (בלי צ'אט Gemini)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Chat, Message, Update, User

from bot.config import IMAGE_ONLY_TEXT_REPLY
from bot.handlers import build_start_keyboard, build_start_welcome_text, on_text


def test_welcome_text_is_image_only():
    text = build_start_welcome_text()
    assert "היי, אני שמח שהגעת לכאן" in text
    assert "תמונה" in text
    assert "מאגר" in text
    assert "פתרון מחברת" in text
    assert "מדריך" in text
    assert "נוסחאות" in text
    assert "דיווח" in text
    assert "סטטיקה" in text
    assert "24 שעות" in text
    assert '150 ש"ח' in text
    assert "בראש שקט" in text
    assert "מהנדס הדיגיטלי" not in text
    assert "מושג" not in text
    assert "טקסט חופשי" not in text


def test_start_keyboard_has_no_concept_button():
    keyboard = build_start_keyboard()
    labels = [btn.text for row in keyboard.inline_keyboard for btn in row]
    callbacks = [btn.callback_data for row in keyboard.inline_keyboard for btn in row]
    assert any("פתרון מלא" in label for label in labels)
    assert any("קופון" in label for label in labels)
    assert not any("מושג" in label for label in labels)
    assert not any("דיווח" in label for label in labels)
    assert not any("מבוא" in label for label in labels)
    assert "menu:intro" not in callbacks


@pytest.mark.anyio
async def test_on_text_auto_reply_when_not_draft_or_coupon():
    update = MagicMock(spec=Update)
    update.message = MagicMock(spec=Message)
    update.message.text = "מה זה מומנט?"
    update.effective_chat = Chat(id=999001, type="private")
    update.effective_user = User(id=111, is_bot=False, first_name="T")
    update.message.reply_text = AsyncMock()

    context = MagicMock()

    with patch("bot.handlers.telegram_chat_id", return_value=999001):
        with patch("bot.handlers.get_draft_edit", return_value=None):
            with patch("bot.handlers.is_draft_pending", return_value=False):
                with patch("bot.handlers.handle_draft_text") as mock_draft:
                    from bot.draft_editor import DraftHandleResult

                    mock_draft.return_value = DraftHandleResult(handled=False)
                    await on_text(update, context)

    update.message.reply_text.assert_awaited_once()
    args, kwargs = update.message.reply_text.await_args
    assert args[0] == IMAGE_ONLY_TEXT_REPLY
