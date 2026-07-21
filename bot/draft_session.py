# -*- coding: utf-8 -*-
"""מצב טיוטה / חבילת vision לפי chat — נפרד ממנוע החילוץ."""
from __future__ import annotations

_vision_context_by_chat: dict[int, str] = {}
_vision_bundle_by_chat: dict[int, dict] = {}


def clear_vision_context(chat_id: int) -> None:
    _vision_context_by_chat.pop(chat_id, None)
    _vision_bundle_by_chat.pop(chat_id, None)


def get_stored_vision_extracted(chat_id: int) -> dict | None:
    bundle = _vision_bundle_by_chat.get(chat_id)
    if not bundle:
        return None
    extracted = bundle.get("extracted") or {}
    return extracted if isinstance(extracted, dict) and extracted else None


def store_extracted_exercise(chat_id: int, extracted: dict) -> None:
    """שומר חילוץ אחרון (לפני חישוב או להשוואת תשובת תלמיד)."""
    _vision_bundle_by_chat[chat_id] = {
        "extracted": extracted,
        "solved": (_vision_bundle_by_chat.get(chat_id) or {}).get("solved") or {},
    }
    from bot.solution_session import mark_session_draft

    mark_session_draft(chat_id)


def set_draft_pending(
    chat_id: int,
    extracted: dict,
    draft_text: str,
    *,
    message_id: int | None = None,
    clear_edit: bool = False,
) -> None:
    """שומר טיוטה שממתינה לאישור משתמש."""
    prev = _vision_bundle_by_chat.get(chat_id) or {}
    if message_id is None:
        message_id = prev.get("draft_message_id")
    draft_edit = None if clear_edit else prev.get("draft_edit")
    draft_edit_prompt_id = None if clear_edit else prev.get("draft_edit_prompt_id")
    type_picker_idx = None if clear_edit else prev.get("draft_type_picker_idx")
    _vision_bundle_by_chat[chat_id] = {
        "extracted": extracted,
        "solved": prev.get("solved") or {},
        "draft_status": "pending",
        "draft_text": draft_text,
        "draft_message_id": message_id,
        "draft_chat_id": prev.get("draft_chat_id", chat_id),
        "draft_edit": draft_edit if isinstance(draft_edit, dict) else None,
        "draft_edit_prompt_id": draft_edit_prompt_id,
        "draft_type_picker_idx": type_picker_idx,
    }


def get_draft_message_ref(chat_id: int) -> tuple[int, int] | None:
    bundle = _vision_bundle_by_chat.get(chat_id) or {}
    msg_id = bundle.get("draft_message_id")
    chat = bundle.get("draft_chat_id", chat_id)
    if msg_id is None:
        return None
    return int(chat), int(msg_id)


def set_draft_error_message_id(chat_id: int, message_id: int | None) -> None:
    """שומר message_id של הודעת שגיאה שנשלחה אחרי 'חשב' (בנוסף לעריכת הטיוטה)."""
    bundle = _vision_bundle_by_chat.get(chat_id)
    if not bundle:
        return
    bundle["draft_error_message_id"] = int(message_id) if message_id is not None else None


def get_draft_error_message_id(chat_id: int) -> int | None:
    bundle = _vision_bundle_by_chat.get(chat_id) or {}
    mid = bundle.get("draft_error_message_id")
    if mid is None:
        return None
    try:
        return int(mid)
    except Exception:
        return None


def set_draft_edit(chat_id: int, edit: dict | None) -> None:
    bundle = _vision_bundle_by_chat.get(chat_id)
    if not bundle:
        return
    bundle["draft_edit"] = edit


def get_draft_edit(chat_id: int) -> dict | None:
    bundle = _vision_bundle_by_chat.get(chat_id) or {}
    edit = bundle.get("draft_edit")
    return edit if isinstance(edit, dict) else None


def set_draft_type_picker_idx(chat_id: int, idx: int | None) -> None:
    """אינדקס עומס (1-based) שתפריט בחירת הסוג פתוח עבורו — נפרד מעריכת שדה."""
    bundle = _vision_bundle_by_chat.get(chat_id)
    if not bundle:
        return
    if idx is None:
        bundle.pop("draft_type_picker_idx", None)
    else:
        bundle["draft_type_picker_idx"] = int(idx)


def get_draft_type_picker_idx(chat_id: int) -> int | None:
    bundle = _vision_bundle_by_chat.get(chat_id) or {}
    idx = bundle.get("draft_type_picker_idx")
    return int(idx) if idx is not None else None


def get_draft_edit_prompt_id(chat_id: int) -> int | None:
    bundle = _vision_bundle_by_chat.get(chat_id) or {}
    pid = bundle.get("draft_edit_prompt_id")
    return int(pid) if pid is not None else None


def set_draft_edit_prompt_id(chat_id: int, message_id: int | None) -> None:
    bundle = _vision_bundle_by_chat.get(chat_id)
    if not bundle:
        return
    if message_id is None:
        bundle.pop("draft_edit_prompt_id", None)
    else:
        bundle["draft_edit_prompt_id"] = int(message_id)


def is_draft_pending(chat_id: int) -> bool:
    bundle = _vision_bundle_by_chat.get(chat_id) or {}
    return bundle.get("draft_status") == "pending" and bool(bundle.get("extracted"))


def get_stored_vision_solved(chat_id: int) -> dict | None:
    bundle = _vision_bundle_by_chat.get(chat_id)
    if not bundle:
        return None
    solved = bundle.get("solved")
    return solved if isinstance(solved, dict) and solved.get("result") else None


def store_vision_context(chat_id: int, extracted: dict, solved: dict) -> None:
    _vision_bundle_by_chat[chat_id] = {
        "extracted": extracted,
        "solved": solved,
    }
    from bot.vision import summarize_vision_extraction

    brief = summarize_vision_extraction(extracted)
    _vision_context_by_chat[chat_id] = f"[רקע קצר מתמונה]\n{brief}"
    from bot.solution_session import mark_session_solved

    mark_session_solved(chat_id)


def store_vision_fallback_reply(chat_id: int, reply: str) -> None:
    _vision_bundle_by_chat[chat_id] = {"extracted": {}, "solved": {}, "reply_text": reply}
    _vision_context_by_chat[chat_id] = f"[רקע מתמונה]\n{reply[:500]}"
