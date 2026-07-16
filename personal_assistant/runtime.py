# -*- coding: utf-8 -*-
"""שכבת Telegram לעוזר האישי — פתיחה, פרוק (הסבר+פתרון במסך אחד), ריאקציות."""

from __future__ import annotations

import copy
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from personal_assistant.decomposition import (
    DecompositionProgress,
    DecompositionState,
    advance_decomposition,
    decomposition_load_entries,
    enter_decomposition,
    next_action_goes_to_reactions,
)
from personal_assistant.flow import enter_reactions_after_decomposition
from personal_assistant.opening import build_opening_messages_hebrew
from personal_assistant.reactions import (
    ReactionBeamKind,
    ReactionEquation,
    ReactionPhase,
    ReactionProgress,
    advance_reactions,
    enter_reactions,
    jump_to_reaction_equation,
)
from personal_assistant.screens import build_current_screen_hebrew
from bot.exercise_bank import deliver_exercise_bank_after_approve
from bot.solution_session import (
    SolveMode,
    append_assistant_message_id,
    clear_assistant_prev_stack,
    get_solve_mode,
    pop_assistant_message_ids,
)
from bot.vision import set_draft_error_message_id

log = logging.getLogger("beam_telegram_bot")

SendTextFn = Callable[..., Awaitable[object]]
EditDraftFn = Callable[..., Awaitable[None]]
DeliverNotebookFn = Callable[..., Awaitable[None]]


@dataclass
class OpeningProgress:
    """מצב פתיחה — לפני כניסה לשלב הפרוק."""

    extracted: dict = field(default_factory=dict)


AssistantProgress = OpeningProgress | DecompositionProgress | ReactionProgress

_ASSISTANT_NEXT = "next"
_ASSISTANT_BEGIN_DECOMPOSITION = "begin_decomposition"
_ASSISTANT_UNAVAILABLE = "unavailable"
_ASSISTANT_GOTO_PREFIX = "goto:"
_ASSISTANT_BACK = "back"
_ASSISTANT_NOOP = "noop"
_ASSISTANT_TO_REACTIONS = "to_reactions"
_ASSISTANT_FINISH = "finish"

_EXERCISE_FINISHED_TEXT = (
    "איזה יופי, סיימנו את התרגיל.\n"
    "איך תרצה להמשיך?"
)

# תואם לתוויות/callbacks של התפריט הראשי ב-handlers.
_FINISH_GIVE_EXERCISE_LABEL = "תרגול"
_FINISH_SEND_IMAGE_LABEL = "פתרון מלא"
_FINISH_FORMULAS_LABEL = "נוסחאות"

_REACTION_JUMP_TARGETS: dict[ReactionBeamKind, tuple[tuple[str, ReactionEquation], ...]] = {
    ReactionBeamKind.SIMPLY_SUPPORTED: (
        ("Ax", ReactionEquation.SIGMA_FX),
        ("Ay", ReactionEquation.SIGMA_MB),
        ("By", ReactionEquation.SIGMA_MA),
    ),
    ReactionBeamKind.CANTILEVER: (
        ("Ax", ReactionEquation.SIGMA_FX),
        ("Ma", ReactionEquation.SIGMA_MA_FIXED),
        ("Ay", ReactionEquation.SIGMA_M_TIP),
    ),
}

# פתרון הריאקציה האחרונה בתרגיל — שם «המשך» הופך ל«סיימתי».
_LAST_REACTION_EQUATION: dict[ReactionBeamKind, ReactionEquation] = {
    ReactionBeamKind.SIMPLY_SUPPORTED: ReactionEquation.SIGMA_MA,
    ReactionBeamKind.CANTILEVER: ReactionEquation.SIGMA_M_TIP,
}

_JUMPABLE_EQUATION_VALUES = {
    equation.value
    for pairs in _REACTION_JUMP_TARGETS.values()
    for _label, equation in pairs
}

_progress_by_chat: dict[int, AssistantProgress] = {}
_history_by_chat: dict[int, list[AssistantProgress]] = {}


def clear_personal_assistant_progress(chat_id: int) -> None:
    _progress_by_chat.pop(int(chat_id), None)
    _history_by_chat.pop(int(chat_id), None)


def _push_personal_assistant_history(chat_id: int, progress: AssistantProgress) -> None:
    """שומר תמונת-מצב (עצמאית) של המסך הנוכחי, לפני שמתקדמים ממנו — לכפתור ↩️."""
    _history_by_chat.setdefault(int(chat_id), []).append(copy.deepcopy(progress))


def _pop_personal_assistant_history(chat_id: int) -> AssistantProgress | None:
    stack = _history_by_chat.get(int(chat_id))
    if not stack:
        return None
    return stack.pop()


clear_assistant_v2_progress = clear_personal_assistant_progress


def set_personal_assistant_progress(chat_id: int, progress: AssistantProgress) -> None:
    _progress_by_chat[int(chat_id)] = progress


def get_personal_assistant_progress(chat_id: int) -> AssistantProgress | None:
    return _progress_by_chat.get(int(chat_id))


def has_active_assistant_progress(chat_id: int) -> bool:
    return int(chat_id) in _progress_by_chat


def build_back_button() -> InlineKeyboardButton:
    return InlineKeyboardButton("🔙 חזרה", callback_data="assist:back")


def _build_spacer_button() -> InlineKeyboardButton:
    """כפתור ריק — רק כדי שהעמודה השמאלית (ריאקציה 3) לא תתפרס על כל השורה."""
    return InlineKeyboardButton(" ", callback_data=f"assist:{_ASSISTANT_NOOP}")


def is_last_reaction_solution(progress: ReactionProgress) -> bool:
    """True בפתרון הריאקציה האחרונה (By / Ay-tip) — לפני מסכי יציבות/DONE."""
    last_eq = _LAST_REACTION_EQUATION.get(progress.beam_kind)
    if last_eq is None:
        return False
    return (
        progress.equation == last_eq
        and progress.phase == ReactionPhase.SOLUTION
    )


def build_next_only_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("המשך", callback_data="assist:next")],
            [build_back_button()],
        ]
    )


def build_exercise_finished_keyboard() -> InlineKeyboardMarkup:
    """אחרי «סיימתי» — אותן פעולות כמו בתפריט הראשי (בלי רכישה/קופון)."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(_FINISH_GIVE_EXERCISE_LABEL, callback_data="menu:give_exercise")],
            [InlineKeyboardButton(_FINISH_SEND_IMAGE_LABEL, callback_data="menu:new")],
            [InlineKeyboardButton(_FINISH_FORMULAS_LABEL, callback_data="menu:formulas")],
        ]
    )


def build_begin_decomposition_keyboard() -> InlineKeyboardMarkup:
    """פתיחה כשיש עומסים לפרוק — בלי קיצור לריאקציות (רק אחרי סיום הפרוק)."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "נתחיל בפירוק העומסים",
                    callback_data="assist:begin_decomposition",
                )
            ],
        ]
    )


def build_continue_to_reactions_keyboard() -> InlineKeyboardMarkup:
    """פתיחה כשאין עומסים לפרוק — כפתור יחיד לשלב הריאקציות."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "המשך לריאקציות",
                    callback_data=f"assist:{_ASSISTANT_TO_REACTIONS}",
                )
            ],
        ]
    )


def build_opening_keyboard(extracted: dict) -> InlineKeyboardMarkup:
    if len(decomposition_load_entries(extracted)) == 0:
        return build_continue_to_reactions_keyboard()
    return build_begin_decomposition_keyboard()


def build_next_load_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("לעומס הבא", callback_data="assist:next")],
            [build_back_button()],
        ]
    )


def build_to_reactions_keyboard() -> InlineKeyboardMarkup:
    """אחרי העומס האחרון / דילוג — מעבר להודעת סיום פרוק / אין עומסים."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("לשלב הריאקציות", callback_data="assist:next")],
            [build_back_button()],
        ]
    )


def build_reactions_keyboard(progress: ReactionProgress) -> InlineKeyboardMarkup:
    """עמודה שמאלית: 3 כפתורי ריאקציה. עמודה ימנית: המשך/סיימתי + חזרה (2 שורות)."""
    targets = _REACTION_JUMP_TARGETS.get(progress.beam_kind, ())
    if not targets:
        return build_next_only_keyboard()

    if is_last_reaction_solution(progress):
        continue_button = InlineKeyboardButton(
            "סיימתי", callback_data=f"assist:{_ASSISTANT_FINISH}"
        )
    else:
        continue_button = InlineKeyboardButton("המשך", callback_data="assist:next")
    right_column = [continue_button, build_back_button(), _build_spacer_button()]
    rows: list[list[InlineKeyboardButton]] = []
    for i, (label, equation) in enumerate(targets):
        jump_button = InlineKeyboardButton(
            label, callback_data=f"assist:{_ASSISTANT_GOTO_PREFIX}{equation.value}"
        )
        right_button = right_column[i] if i < len(right_column) else _build_spacer_button()
        rows.append([jump_button, right_button])
    return InlineKeyboardMarkup(rows)


def keyboard_for_progress(progress: AssistantProgress) -> InlineKeyboardMarkup:
    if isinstance(progress, OpeningProgress):
        return build_opening_keyboard(progress.extracted)
    if isinstance(progress, DecompositionProgress):
        if progress.is_skip:
            return build_to_reactions_keyboard()
        if progress.has_more_loads:
            return build_next_load_keyboard()
        return build_to_reactions_keyboard()
    if isinstance(progress, ReactionProgress):
        return build_reactions_keyboard(progress)
    return build_next_only_keyboard()


def parse_assistant_callback(data: str) -> str | None:
    if not data.startswith("assist:"):
        return None
    action = data.split(":", 1)[-1]
    if action in (
        _ASSISTANT_NEXT,
        _ASSISTANT_BEGIN_DECOMPOSITION,
        _ASSISTANT_BACK,
        _ASSISTANT_NOOP,
        _ASSISTANT_TO_REACTIONS,
        _ASSISTANT_FINISH,
    ):
        return action
    if action.startswith(_ASSISTANT_GOTO_PREFIX):
        equation_value = action[len(_ASSISTANT_GOTO_PREFIX) :]
        if equation_value in _JUMPABLE_EQUATION_VALUES:
            return action
    return _ASSISTANT_UNAVAILABLE


def is_assistant_mode(chat_id: int) -> bool:
    return get_solve_mode(chat_id) == SolveMode.ASSISTANT


def is_add_to_bank_mode(chat_id: int) -> bool:
    return get_solve_mode(chat_id) == SolveMode.ADD_TO_BANK


def start_opening(chat_id: int, extracted: dict) -> OpeningProgress:
    progress = OpeningProgress(
        extracted=extracted if isinstance(extracted, dict) else {}
    )
    set_personal_assistant_progress(chat_id, progress)
    return progress


def start_personal_assistant(chat_id: int, extracted: dict) -> DecompositionProgress:
    """כניסה ישירה לפרוק (בדיקות / אחרי כפתור הפתיחה)."""
    progress = enter_decomposition(extracted)
    set_personal_assistant_progress(chat_id, progress)
    return progress


start_assistant_v2 = start_personal_assistant


def screen_text_for_progress(progress: AssistantProgress) -> str:
    if isinstance(progress, OpeningProgress):
        _plan, menu = build_opening_messages_hebrew(progress.extracted)
        return menu
    if isinstance(progress, ReactionProgress):
        if progress.equation == ReactionEquation.DONE:
            return "סיימנו את מה שזמין כרגע."
        return build_current_screen_hebrew(progress)
    return build_current_screen_hebrew(progress)


def advance_on_next(progress: AssistantProgress) -> AssistantProgress:
    """מקדם מצב אחד קדימה; מסיום פרוק מחליף לריאקציות."""
    if isinstance(progress, OpeningProgress):
        return progress

    if isinstance(progress, DecompositionProgress):
        if next_action_goes_to_reactions(progress):
            # מדילוג / אחרי פתרון אחרון — מסמנים DONE ומעבירים
            progress.state = DecompositionState.DONE
            reactions = enter_reactions_after_decomposition(progress)
            return reactions if reactions is not None else progress
        advanced = advance_decomposition(progress)
        if advanced.state == DecompositionState.DONE:
            reactions = enter_reactions_after_decomposition(advanced)
            return reactions if reactions is not None else advanced
        return advanced

    if isinstance(progress, ReactionProgress):
        if progress.equation != ReactionEquation.DONE:
            advance_reactions(progress)
        return progress

    return progress


async def _delete_tracked_messages(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int
) -> None:
    ids = pop_assistant_message_ids(chat_id)
    for mid in ids:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=int(mid))
        except Exception:
            pass


async def _send_with_keyboard(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    text: str,
    *,
    send_text: SendTextFn,
    reply_markup: InlineKeyboardMarkup,
) -> None:
    sent = await send_text(context, chat_id, text, reply_markup=reply_markup)
    try:
        append_assistant_message_id(chat_id, int(getattr(sent, "message_id", 0)))
    except Exception:
        pass


async def _send_progress_screen(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    progress: AssistantProgress,
    *,
    send_text: SendTextFn,
) -> None:
    text = screen_text_for_progress(progress)
    await _send_with_keyboard(
        context,
        chat_id,
        text,
        send_text=send_text,
        reply_markup=keyboard_for_progress(progress),
    )


async def handle_assistant_action(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    action: str,
    *,
    send_text: SendTextFn,
    reply_message=None,
) -> None:
    del reply_message
    progress = get_personal_assistant_progress(chat_id)
    if progress is None:
        return

    if action == _ASSISTANT_BEGIN_DECOMPOSITION:
        if not isinstance(progress, OpeningProgress):
            await send_text(
                context,
                chat_id,
                "הפעולה הזו זמינה רק בפתיחה.",
            )
            return
        _push_personal_assistant_history(chat_id, progress)
        await _delete_tracked_messages(context, chat_id)
        decomp = start_personal_assistant(chat_id, progress.extracted)
        await _send_progress_screen(context, chat_id, decomp, send_text=send_text)
        return

    if action == _ASSISTANT_NOOP:
        return

    if action == _ASSISTANT_UNAVAILABLE:
        await send_text(
            context,
            chat_id,
            "הפעולה הזו עדיין לא זמינה — השתמשו בכפתור שמתחת להודעה.",
        )
        return

    if action == _ASSISTANT_BACK:
        if isinstance(progress, OpeningProgress):
            await send_text(
                context,
                chat_id,
                "הפעולה הזו עדיין לא זמינה — השתמשו בכפתור שמתחת להודעה.",
            )
            return
        restored = _pop_personal_assistant_history(chat_id)
        if restored is None:
            await send_text(
                context,
                chat_id,
                "אין הודעה קודמת לחזור אליה.",
            )
            return
        await _delete_tracked_messages(context, chat_id)
        set_personal_assistant_progress(chat_id, restored)
        await _send_progress_screen(context, chat_id, restored, send_text=send_text)
        return

    if action == _ASSISTANT_TO_REACTIONS:
        # קיצור רק בפתיחה כשאין עומסים לפרוק («המשך לריאקציות»).
        # כשיש עומסים — עוברים דרך «לשלב הריאקציות» אחרי סיום הפרוק.
        if not isinstance(progress, OpeningProgress):
            await send_text(
                context,
                chat_id,
                "הפעולה הזו עדיין לא זמינה — השתמשו בכפתור שמתחת להודעה.",
            )
            return
        if len(decomposition_load_entries(progress.extracted)) > 0:
            await send_text(
                context,
                chat_id,
                "קודם סיימו את פירוק העומסים — לחצו «נתחיל בפירוק העומסים».",
            )
            return
        _push_personal_assistant_history(chat_id, progress)
        await _delete_tracked_messages(context, chat_id)
        reactions = enter_reactions(progress.extracted, decomposed_load_indices=[])
        set_personal_assistant_progress(chat_id, reactions)
        await _send_progress_screen(context, chat_id, reactions, send_text=send_text)
        return

    if action == _ASSISTANT_FINISH:
        if not isinstance(progress, ReactionProgress) or not is_last_reaction_solution(
            progress
        ):
            await send_text(
                context,
                chat_id,
                "הפעולה הזו עדיין לא זמינה — השתמשו בכפתור שמתחת להודעה.",
            )
            return
        await _delete_tracked_messages(context, chat_id)
        clear_personal_assistant_progress(chat_id)
        clear_assistant_prev_stack(chat_id)
        await send_text(
            context,
            chat_id,
            _EXERCISE_FINISHED_TEXT,
            reply_markup=build_exercise_finished_keyboard(),
        )
        return

    if action.startswith(_ASSISTANT_GOTO_PREFIX):
        equation_value = action[len(_ASSISTANT_GOTO_PREFIX) :]
        jumped = (
            jump_to_reaction_equation(progress, ReactionEquation(equation_value))
            if isinstance(progress, ReactionProgress)
            else None
        )
        if jumped is None:
            await send_text(
                context,
                chat_id,
                "הפעולה הזו עדיין לא זמינה — השתמשו בכפתור שמתחת להודעה.",
            )
            return
        _push_personal_assistant_history(chat_id, progress)
        await _delete_tracked_messages(context, chat_id)
        set_personal_assistant_progress(chat_id, jumped)
        await _send_progress_screen(context, chat_id, jumped, send_text=send_text)
        return

    if action != _ASSISTANT_NEXT:
        await send_text(
            context,
            chat_id,
            "הפעולה הזו עדיין לא זמינה — השתמשו בכפתור שמתחת להודעה.",
        )
        return

    if isinstance(progress, OpeningProgress):
        await send_text(
            context,
            chat_id,
            "קודם לחצו על «נתחיל בפירוק העומסים».",
        )
        return

    _push_personal_assistant_history(chat_id, progress)
    await _delete_tracked_messages(context, chat_id)
    progress = advance_on_next(progress)
    set_personal_assistant_progress(chat_id, progress)
    await _send_progress_screen(context, chat_id, progress, send_text=send_text)


async def deliver_assistant_after_approve(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    *,
    extracted: dict,
    reply: str,
    solved: dict,
    draft_msg_id: int | None,
    send_text: SendTextFn,
    edit_draft_message: EditDraftFn,
) -> None:
    has_result = bool((solved or {}).get("result"))
    if not has_result:
        if reply:
            sent = await send_text(context, chat_id, reply)
            try:
                set_draft_error_message_id(chat_id, int(getattr(sent, "message_id", 0)))
            except Exception:
                pass
        if draft_msg_id is not None:
            await edit_draft_message(
                context,
                chat_id,
                draft_msg_id,
                extracted,
                errors=[reply] if reply else None,
            )
        return

    clear_assistant_prev_stack(chat_id)
    clear_personal_assistant_progress(chat_id)
    start_opening(chat_id, extracted)
    plan_text, menu_text = build_opening_messages_hebrew(extracted)

    sent = await send_text(context, chat_id, plan_text)
    try:
        append_assistant_message_id(chat_id, int(getattr(sent, "message_id", 0)))
    except Exception:
        pass

    if draft_msg_id is not None:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=draft_msg_id)
        except BadRequest:
            pass

    await _send_with_keyboard(
        context,
        chat_id,
        menu_text,
        send_text=send_text,
        reply_markup=build_opening_keyboard(extracted),
    )


async def deliver_after_draft_approve(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    *,
    extracted: dict,
    reply: str,
    solved: dict,
    draft_msg_id: int | None,
    deliver_notebook: DeliverNotebookFn,
    send_text: SendTextFn,
    edit_draft_message: EditDraftFn,
) -> None:
    if is_assistant_mode(chat_id):
        await deliver_assistant_after_approve(
            context,
            chat_id,
            extracted=extracted,
            reply=reply,
            solved=solved,
            draft_msg_id=draft_msg_id,
            send_text=send_text,
            edit_draft_message=edit_draft_message,
        )
        return
    if is_add_to_bank_mode(chat_id):
        await deliver_exercise_bank_after_approve(
            context,
            chat_id,
            extracted=extracted,
            reply=reply,
            solved=solved,
            draft_msg_id=draft_msg_id,
            send_text=send_text,
            edit_draft_message=edit_draft_message,
        )
        return
    await deliver_notebook(
        context,
        chat_id,
        extracted=extracted,
        reply=reply,
        solved=solved,
        draft_msg_id=draft_msg_id,
    )
