# -*- coding: utf-8 -*-
"""עיבוד תמונות ברקע — תשובה מיידית ואז חילוץ עם retries ממושכים."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass

from telegram.ext import ContextTypes

from bot.config import (
    DRAFT_APPROVAL_MODE,
    VISION_ASYNC_ACK_TEXT,
    VISION_EXTRACT_ONLY_MODE,
    VISION_GLOBAL_CONCURRENCY,
    VISION_JOB_RETRY_ATTEMPTS,
    VISION_JOB_RETRY_BASE_SEC,
)
from bot.draft_keyboard import build_draft_keyboard, draft_display_text
from bot.env import resolve_vision_model
from bot.gemini_chat import friendly_gemini_error, gemini_runtime
from bot.prompt_loader import build_vision_extra_instruction
from bot.solution_check import format_solve_reply, solve_extracted_beam
from bot.system_prompt import get_vision_learned_hint
from bot.vision import (
    _is_retryable_vision_error,
    extract_exercise_with_retries,
    finalize_beam_extraction,
    format_vision_extract_only_reply,
    package_extraction_response,
    set_draft_pending,
    store_extracted_exercise,
    store_vision_context,
)

log = logging.getLogger("beam_telegram_bot")

_VISION_CACHE_TTL_SEC = 60 * 30
_VISION_CACHE_MAX_ITEMS = 200
_vision_cache: dict[str, tuple[float, str]] = {}

_chat_locks: dict[int, asyncio.Lock] = {}
_pending_ack_by_chat: dict[int, int] = {}
_global_vision_sem: asyncio.Semaphore | None = None


def _vision_global_sem() -> asyncio.Semaphore:
    global _global_vision_sem
    if _global_vision_sem is None:
        n = max(1, int(VISION_GLOBAL_CONCURRENCY))
        _global_vision_sem = asyncio.Semaphore(n)
        log.info("Vision global concurrency limit: %s", n)
    return _global_vision_sem


def vision_cache_key(image_bytes: bytes, mime_type: str, extra_instruction: str) -> str:
    h = hashlib.sha256()
    h.update(mime_type.encode("utf-8", errors="ignore"))
    h.update(b"\0")
    h.update(extra_instruction.encode("utf-8", errors="ignore"))
    h.update(b"\0")
    h.update(image_bytes)
    return h.hexdigest()


def vision_cache_get(key: str) -> str | None:
    item = _vision_cache.get(key)
    if not item:
        return None
    ts, reply = item
    if time.monotonic() - ts > _VISION_CACHE_TTL_SEC:
        _vision_cache.pop(key, None)
        return None
    return reply


def vision_cache_put(key: str, reply: str) -> None:
    _vision_cache[key] = (time.monotonic(), reply)
    if len(_vision_cache) <= _VISION_CACHE_MAX_ITEMS:
        return
    oldest = sorted(_vision_cache.items(), key=lambda kv: kv[1][0])[
        : max(1, len(_vision_cache) - _VISION_CACHE_MAX_ITEMS)
    ]
    for k, _ in oldest:
        _vision_cache.pop(k, None)


def _chat_lock(chat_id: int) -> asyncio.Lock:
    lock = _chat_locks.get(chat_id)
    if lock is None:
        lock = asyncio.Lock()
        _chat_locks[chat_id] = lock
    return lock


async def typing_while_waiting(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    stop: asyncio.Event,
) -> None:
    while not stop.is_set():
        try:
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        except Exception:
            pass
        try:
            await asyncio.wait_for(stop.wait(), timeout=4.0)
        except asyncio.TimeoutError:
            continue


@dataclass
class VisionJobResult:
    use_draft: bool = False
    extracted: dict | None = None
    reply: str | None = None


async def run_vision_extract(
    chat_id: int,
    image_bytes: bytes,
    mime_type: str,
) -> VisionJobResult:
    async with _vision_global_sem():
        return await _run_vision_extract_inner(chat_id, image_bytes, mime_type)


async def _run_vision_extract_inner(
    chat_id: int,
    image_bytes: bytes,
    mime_type: str,
) -> VisionJobResult:
    learned = get_vision_learned_hint()
    extra = build_vision_extra_instruction(learned_hint=learned)
    cache_key = vision_cache_key(image_bytes, mime_type, extra)
    cached = vision_cache_get(cache_key)
    if cached is not None and not DRAFT_APPROVAL_MODE:
        log.info("Vision cache hit chat %s (async)", chat_id)
        return VisionJobResult(reply=cached)

    client, _ = gemini_runtime()
    vision_model = resolve_vision_model()
    last_exc: Exception | None = None
    extracted: dict | None = None
    attempts = max(1, int(VISION_JOB_RETRY_ATTEMPTS))
    for attempt in range(attempts):
        try:
            extracted = await asyncio.to_thread(
                extract_exercise_with_retries,
                client,
                vision_model,
                image_bytes,
                mime_type,
                extra_instruction=extra,
            )
            break
        except Exception as exc:
            last_exc = exc
            if attempt >= attempts - 1 or not _is_retryable_vision_error(exc):
                raise
            delay = VISION_JOB_RETRY_BASE_SEC * (attempt + 1)
            log.warning(
                "Vision job overload chat %s — retry %s/%s in %.1fs: %s",
                chat_id,
                attempt + 2,
                attempts,
                delay,
                exc,
            )
            await asyncio.sleep(delay)
    if extracted is None:
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("Vision extract returned no data")
    extracted = finalize_beam_extraction(extracted)
    if not (
        isinstance(extracted.get("_extraction_quality"), dict)
        and extracted["_extraction_quality"].get("partial")
    ):
        extracted = package_extraction_response(extracted)

    use_draft = DRAFT_APPROVAL_MODE and not VISION_EXTRACT_ONLY_MODE
    if use_draft:
        store_extracted_exercise(chat_id, extracted)
        set_draft_pending(chat_id, extracted, draft_display_text(extracted))
        return VisionJobResult(use_draft=True, extracted=extracted)

    if VISION_EXTRACT_ONLY_MODE:
        reply = format_vision_extract_only_reply(extracted)
    else:
        try:
            solved = solve_extracted_beam(extracted)
            store_vision_context(chat_id, extracted, solved)
            reply = format_solve_reply(extracted, solved)
        except Exception as solve_exc:
            log.warning("Solve after extract failed: %s", solve_exc)
            reply = format_vision_extract_only_reply(extracted)
            reply += f"\n\nלא הצלחתי לחשב ריאקציות: {solve_exc}"

    vision_cache_put(cache_key, reply)
    log.info("Vision extract chat %s OK (async)", chat_id)
    return VisionJobResult(reply=reply)


async def send_draft_to_chat(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    extracted: dict,
) -> None:
    text = draft_display_text(extracted)
    keyboard = build_draft_keyboard(extracted)
    try:
        sent = await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
    except Exception:
        sent = await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=keyboard,
        )
    set_draft_pending(
        chat_id,
        extracted,
        text,
        message_id=sent.message_id,
        clear_edit=True,
    )


async def _deliver_result(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    *,
    result: VisionJobResult,
) -> None:
    await dismiss_vision_ack(context, chat_id)
    if result.use_draft and result.extracted is not None:
        await send_draft_to_chat(context, chat_id, result.extracted)
        return
    reply = result.reply or "לא הצלחתי לעבד את התמונה."
    if len(reply) > 4000:
        reply = reply[:3997] + "..."
    await context.bot.send_message(chat_id=chat_id, text=reply)


async def process_vision_job(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    image_bytes: bytes,
    mime_type: str,
) -> None:
    async with _chat_lock(chat_id):
        stop_typing = asyncio.Event()
        typing_task = asyncio.create_task(
            typing_while_waiting(context, chat_id, stop_typing)
        )
        extracted_partial: dict | None = None
        try:
            result = await run_vision_extract(chat_id, image_bytes, mime_type)
            extracted_partial = result.extracted
            await _deliver_result(context, chat_id, result=result)
        except Exception as exc:
            log.warning("Vision extract failed (async) chat %s: %s", chat_id, exc)
            await dismiss_vision_ack(context, chat_id)
            if extracted_partial is not None:
                extracted_partial = package_extraction_response(
                    extracted_partial,
                    partial=True,
                    validation_issues=[str(exc)],
                )
                reply = format_vision_extract_only_reply(extracted_partial)
            else:
                reply = (
                    f"לא הצלחתי לקרוא את התמונה.\n({friendly_gemini_error(exc)})\n\n"
                    "טיפים:\n"
                    "• שלח כקובץ לאיכות טובה יותר\n"
                    "• ודא שכל המספרים, החצים והסמכים בתוך המסגרת\n"
                    "• נסה שוב בעוד דקה"
                )
            await context.bot.send_message(chat_id=chat_id, text=reply)
        finally:
            stop_typing.set()
            typing_task.cancel()


def schedule_vision_job(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    image_bytes: bytes,
    mime_type: str,
) -> None:
    task = asyncio.create_task(
        process_vision_job(context, chat_id, image_bytes, mime_type),
        name=f"vision-{chat_id}",
    )

    def _done(t: asyncio.Task) -> None:
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None:
            log.exception("Vision background task failed chat %s", chat_id, exc_info=exc)

    task.add_done_callback(_done)


async def dismiss_vision_ack(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
) -> None:
    """מוחק את הודעת 'קיבלתי, מעבד...' לפני שליחת התוצאה."""
    msg_id = _pending_ack_by_chat.pop(chat_id, None)
    if msg_id is None:
        return
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
    except Exception as exc:
        log.debug("Vision ack delete skipped chat %s: %s", chat_id, exc)


async def send_vision_ack(message) -> None:
    sent = await message.reply_text(VISION_ASYNC_ACK_TEXT)
    _pending_ack_by_chat[message.chat_id] = sent.message_id
