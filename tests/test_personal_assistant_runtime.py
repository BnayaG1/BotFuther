# -*- coding: utf-8 -*-
"""חיבור Telegram לעוזר האישי — פתיחה + פרוק (הסבר+פתרון במסך אחד)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from personal_assistant import runtime
from personal_assistant.decomposition import (
    DecompositionProgress,
    DecompositionState,
)
from personal_assistant.opening import build_opening_messages_hebrew
from personal_assistant.reactions import (
    ReactionBeamKind,
    ReactionEquation,
    ReactionPhase,
    ReactionProgress,
)
from personal_assistant.runtime import OpeningProgress
from bot.solution_session import SolveMode, begin_image_session


EXTRACTED = {
    "exercise_type": "beam",
    "beam": {
        "L": 9.0,
        "support_mode": "simply_supported",
        "supports": [
            {"label": "A", "type": "pin", "x": 2.0},
            {"label": "B", "type": "roller", "x": 9.0},
        ],
        "loads": [
            {"type": "distributed", "x1": 0.0, "x2": 5.0, "w": 3.0},
            {"type": "inclined", "x": 7.0, "magnitude_ton": 5.0, "angle_deg": 30.0, "incl_dir": "dr"},
        ],
    },
}


@pytest.fixture(autouse=True)
def _clear_pa():
    for cid in (88020, 88021, 88022, 88023, 88026, 88027, 88037, 88038, 88040, 88041):
        runtime.clear_personal_assistant_progress(cid)
    yield
    for cid in (88020, 88021, 88022, 88023, 88026, 88027, 88037, 88038, 88040, 88041):
        runtime.clear_personal_assistant_progress(cid)


def test_opening_messages_are_two():
    plan, menu = build_opening_messages_hebrew(EXTRACTED)
    assert "מדובר בתרגיל" in plan
    assert "2 עומסים בעייתיים" in plan
    assert "איך תרצה להמשיך" in menu


def test_parse_and_keyboards():
    assert runtime.parse_assistant_callback("assist:next") == "next"
    assert (
        runtime.parse_assistant_callback("assist:begin_decomposition")
        == "begin_decomposition"
    )
    assert runtime.parse_assistant_callback("assist:explain") == "unavailable"
    assert runtime.parse_assistant_callback("assist:goto:sigma_mb") == "goto:sigma_mb"
    assert runtime.parse_assistant_callback("assist:goto:not_real") == "unavailable"
    assert runtime.parse_assistant_callback("assist:noop") == "noop"
    assert runtime.parse_assistant_callback("assist:to_reactions") == "to_reactions"
    assert runtime.parse_assistant_callback("assist:finish") == "finish"

    assert [b.callback_data for row in runtime.build_next_load_keyboard().inline_keyboard for b in row] == [
        "assist:next",
        "assist:back",
    ]
    assert [
        b.callback_data for row in runtime.build_to_reactions_keyboard().inline_keyboard for b in row
    ] == ["assist:next", "assist:back"]

def test_last_reaction_solution_shows_finish_button_simply_supported():
    progress = ReactionProgress(
        beam_kind=ReactionBeamKind.SIMPLY_SUPPORTED,
        equation=ReactionEquation.SIGMA_MA,
        phase=ReactionPhase.SOLUTION,
    )
    assert runtime.is_last_reaction_solution(progress)
    kb = runtime.build_reactions_keyboard(progress)
    assert kb.inline_keyboard[0][1].text == "סיימתי"
    assert kb.inline_keyboard[0][1].callback_data == "assist:finish"


def test_last_reaction_solution_shows_finish_button_cantilever():
    progress = ReactionProgress(
        beam_kind=ReactionBeamKind.CANTILEVER,
        equation=ReactionEquation.SIGMA_M_TIP,
        phase=ReactionPhase.SOLUTION,
    )
    assert runtime.is_last_reaction_solution(progress)
    kb = runtime.build_reactions_keyboard(progress)
    assert kb.inline_keyboard[0][1].text == "סיימתי"
    assert kb.inline_keyboard[0][1].callback_data == "assist:finish"


def test_earlier_reaction_solution_keeps_continue_button():
    progress = ReactionProgress(
        beam_kind=ReactionBeamKind.SIMPLY_SUPPORTED,
        equation=ReactionEquation.SIGMA_MA,
        phase=ReactionPhase.EXPLAIN,
    )
    assert not runtime.is_last_reaction_solution(progress)
    kb = runtime.build_reactions_keyboard(progress)
    assert kb.inline_keyboard[0][1].text == "המשך"
    assert kb.inline_keyboard[0][1].callback_data == "assist:next"


def test_exercise_finished_keyboard_matches_main_menu_actions():
    kb = runtime.build_exercise_finished_keyboard()
    assert [[b.text, b.callback_data] for row in kb.inline_keyboard for b in row] == [
        ["תרגול", "menu:give_exercise"],
        ["פתרון מלא", "menu:new"],
        ["נוסחאות", "menu:formulas"],
    ]


def test_reactions_keyboard_layout_simply_supported():
    progress = ReactionProgress(beam_kind=ReactionBeamKind.SIMPLY_SUPPORTED)
    kb = runtime.build_reactions_keyboard(progress)
    rows = kb.inline_keyboard
    assert [[b.text for b in row] for row in rows] == [
        ["Ax", "המשך"],
        ["Ay", "חזרה"],
        ["By", " "],
    ]
    assert [b.callback_data for b in rows[0]] == [
        "assist:goto:sigma_fx",
        "assist:next",
    ]
    assert [b.callback_data for b in rows[1]] == [
        "assist:goto:sigma_mb",
        "assist:back",
    ]
    assert [b.callback_data for b in rows[2]] == [
        "assist:goto:sigma_ma",
        "assist:noop",
    ]


def test_reactions_keyboard_layout_cantilever():
    progress = ReactionProgress(beam_kind=ReactionBeamKind.CANTILEVER)
    kb = runtime.build_reactions_keyboard(progress)
    rows = kb.inline_keyboard
    assert [[b.text for b in row] for row in rows] == [
        ["Ax", "המשך"],
        ["Ma", "חזרה"],
        ["Ay", " "],
    ]
    assert [b.callback_data for b in rows[0]] == [
        "assist:goto:sigma_fx",
        "assist:next",
    ]
    assert [b.callback_data for b in rows[1]] == [
        "assist:goto:sigma_ma_fixed",
        "assist:back",
    ]
    assert [b.callback_data for b in rows[2]] == [
        "assist:goto:sigma_m_tip",
        "assist:noop",
    ]


def test_reactions_keyboard_unknown_beam_kind_falls_back_to_next_only():
    progress = ReactionProgress(beam_kind=ReactionBeamKind.UNKNOWN)
    kb = runtime.build_reactions_keyboard(progress)
    assert [b.callback_data for row in kb.inline_keyboard for b in row] == [
        "assist:next",
        "assist:back",
    ]
    assert kb.inline_keyboard == runtime.keyboard_for_progress(progress).inline_keyboard


@pytest.mark.anyio
async def test_handle_goto_jumps_to_chosen_reaction():
    chat_id = 88024
    runtime.clear_personal_assistant_progress(chat_id)
    progress = ReactionProgress(beam_kind=ReactionBeamKind.SIMPLY_SUPPORTED)
    runtime.set_personal_assistant_progress(chat_id, progress)

    context = MagicMock()
    context.bot.delete_message = AsyncMock()
    send_text = AsyncMock(return_value=MagicMock(message_id=201))

    await runtime.handle_assistant_action(
        context, chat_id, "goto:sigma_mb", send_text=send_text
    )

    updated = runtime.get_personal_assistant_progress(chat_id)
    assert isinstance(updated, ReactionProgress)
    assert updated.equation == ReactionEquation.SIGMA_MB
    assert updated.phase == ReactionPhase.EXPLAIN
    kb = send_text.await_args.kwargs["reply_markup"]
    assert [[b.text for b in row] for row in kb.inline_keyboard] == [
        ["Ax", "המשך"],
        ["Ay", "חזרה"],
        ["By", " "],
    ]
    runtime.clear_personal_assistant_progress(chat_id)


@pytest.mark.anyio
async def test_handle_goto_for_non_reaction_progress_is_unavailable():
    chat_id = 88025
    runtime.clear_personal_assistant_progress(chat_id)
    runtime.start_opening(chat_id, EXTRACTED)

    context = MagicMock()
    context.bot.delete_message = AsyncMock()
    send_text = AsyncMock(return_value=MagicMock(message_id=202))

    await runtime.handle_assistant_action(
        context, chat_id, "goto:sigma_mb", send_text=send_text
    )

    text = send_text.await_args.args[2]
    assert "לא זמינה" in text
    runtime.clear_personal_assistant_progress(chat_id)


@pytest.mark.anyio
async def test_handle_finish_sends_completion_menu_and_clears_progress():
    chat_id = 88040
    progress = ReactionProgress(
        beam_kind=ReactionBeamKind.SIMPLY_SUPPORTED,
        equation=ReactionEquation.SIGMA_MA,
        phase=ReactionPhase.SOLUTION,
        extracted=EXTRACTED,
    )
    runtime.set_personal_assistant_progress(chat_id, progress)

    context = MagicMock()
    context.bot.delete_message = AsyncMock()
    send_text = AsyncMock(return_value=MagicMock(message_id=401))

    await runtime.handle_assistant_action(
        context, chat_id, "finish", send_text=send_text
    )

    assert runtime.get_personal_assistant_progress(chat_id) is None
    text = send_text.await_args.args[2]
    assert "איזה יופי, סיימנו את התרגיל" in text
    assert "איך תרצה להמשיך" in text
    kb = send_text.await_args.kwargs["reply_markup"]
    assert [[b.text, b.callback_data] for row in kb.inline_keyboard for b in row] == [
        ["תרגול", "menu:give_exercise"],
        ["פתרון מלא", "menu:new"],
        ["נוסחאות", "menu:formulas"],
    ]


@pytest.mark.anyio
async def test_handle_finish_unavailable_before_last_solution():
    chat_id = 88041
    progress = ReactionProgress(
        beam_kind=ReactionBeamKind.SIMPLY_SUPPORTED,
        equation=ReactionEquation.SIGMA_MB,
        phase=ReactionPhase.SOLUTION,
        extracted=EXTRACTED,
    )
    runtime.set_personal_assistant_progress(chat_id, progress)

    context = MagicMock()
    context.bot.delete_message = AsyncMock()
    send_text = AsyncMock(return_value=MagicMock(message_id=402))

    await runtime.handle_assistant_action(
        context, chat_id, "finish", send_text=send_text
    )

    assert runtime.get_personal_assistant_progress(chat_id) is progress
    text = send_text.await_args.args[2]
    assert "לא זמינה" in text


def test_advance_decomp_flow_to_reactions():
    chat_id = 88020
    progress = runtime.start_personal_assistant(chat_id, EXTRACTED)
    assert isinstance(progress, DecompositionProgress)
    text = runtime.screen_text_for_progress(progress)
    assert "יש 2 עומסים בעייתיים" in text
    assert "הכח השקול" in text
    kb = runtime.keyboard_for_progress(progress)
    assert [b.text for row in kb.inline_keyboard for b in row] == [
        "לעומס הבא",
        "חזרה",
    ]

    progress = runtime.advance_on_next(progress)
    assert isinstance(progress, DecompositionProgress)
    text = runtime.screen_text_for_progress(progress)
    assert "אלכסוני" in text
    assert "Fx =" in text
    kb = runtime.keyboard_for_progress(progress)
    assert [b.text for row in kb.inline_keyboard for b in row] == [
        "לשלב הריאקציות",
        "חזרה",
    ]

    progress = runtime.advance_on_next(progress)
    assert isinstance(progress, ReactionProgress)
    assert progress.equation == ReactionEquation.ENTRY
    text = runtime.screen_text_for_progress(progress)
    assert "סיימנו את פירוק העומסים" in text
    assert "מציאת הריאקציות" in text
    assert "מכיוון שלא היה עומסים לפרק" not in text

def test_empty_decomposition_next_enters_reactions():
    empty = {
        "exercise_type": "beam",
        "beam": {
            "L": 5.0,
            "support_mode": "simply_supported",
            "supports": [
                {"label": "A", "type": "pin", "x": 0.0},
                {"label": "B", "type": "roller", "x": 5.0},
            ],
            "loads": [{"type": "point", "x": 2.0, "Fy": 1.0}],
        },
    }
    progress = runtime.start_personal_assistant(88021, empty)
    assert progress.state == DecompositionState.DONE
    assert "אין עומסים" in runtime.screen_text_for_progress(progress)
    kb = runtime.keyboard_for_progress(progress)
    assert [b.text for row in kb.inline_keyboard for b in row] == [
        "לשלב הריאקציות",
        "חזרה",
    ]
    progress = runtime.advance_on_next(progress)
    assert isinstance(progress, ReactionProgress)
    text = runtime.screen_text_for_progress(progress)
    assert "מכיוון שלא היה עומסים לפרק" in text
    assert "מציאת הריאקציות" in text
    assert "סיימנו את פירוק העומסים" not in text
    kb = runtime.keyboard_for_progress(progress)
    assert kb.inline_keyboard[0][1].text == "המשך"
    assert kb.inline_keyboard[0][1].callback_data == "assist:next"

@pytest.mark.anyio
async def test_handle_next_advances_to_next_load():
    chat_id = 88022
    begin_image_session(chat_id, solve_mode=SolveMode.ASSISTANT)
    runtime.start_personal_assistant(chat_id, EXTRACTED)

    context = MagicMock()
    context.bot.delete_message = AsyncMock()
    send_text = AsyncMock(return_value=MagicMock(message_id=101))

    await runtime.handle_assistant_action(context, chat_id, "next", send_text=send_text)
    text = send_text.await_args.args[2]
    assert "אלכסוני" in text
    assert "Fx =" in text
    kb = send_text.await_args.kwargs["reply_markup"]
    assert [b.text for row in kb.inline_keyboard for b in row] == [
        "לשלב הריאקציות",
        "חזרה",
    ]


@pytest.mark.anyio
async def test_deliver_sends_opening_with_begin_button():
    chat_id = 88020
    begin_image_session(chat_id, solve_mode=SolveMode.ASSISTANT)
    context = MagicMock()
    context.bot.delete_message = AsyncMock()
    send_text = AsyncMock(return_value=MagicMock(message_id=50))
    edit_draft = AsyncMock()

    await runtime.deliver_assistant_after_approve(
        context,
        chat_id,
        extracted=EXTRACTED,
        reply="ok",
        solved={"result": {"reactions": []}},
        draft_msg_id=12,
        send_text=send_text,
        edit_draft_message=edit_draft,
    )

    assert isinstance(runtime.get_personal_assistant_progress(chat_id), OpeningProgress)
    bodies = [c.args[2] for c in send_text.await_args_list]
    assert len(bodies) == 2
    assert "מדובר בתרגיל" in bodies[0]
    assert "איך תרצה להמשיך" in bodies[1]
    last_kb = send_text.await_args_list[-1].kwargs.get("reply_markup")
    callbacks = [b.callback_data for row in last_kb.inline_keyboard for b in row]
    assert callbacks == ["assist:begin_decomposition"]


@pytest.mark.anyio
async def test_begin_decomposition_enters_combined_load_screen():
    chat_id = 88023
    begin_image_session(chat_id, solve_mode=SolveMode.ASSISTANT)
    runtime.start_opening(chat_id, EXTRACTED)

    context = MagicMock()
    context.bot.delete_message = AsyncMock()
    send_text = AsyncMock(return_value=MagicMock(message_id=77))

    await runtime.handle_assistant_action(
        context, chat_id, "begin_decomposition", send_text=send_text
    )

    progress = runtime.get_personal_assistant_progress(chat_id)
    assert isinstance(progress, DecompositionProgress)
    text = send_text.await_args.args[2]
    assert "יש 2 עומסים בעייתיים" in text
    assert "הכח השקול" in text
    kb = send_text.await_args.kwargs.get("reply_markup")
    assert [b.callback_data for row in kb.inline_keyboard for b in row] == [
        "assist:next",
        "assist:back",
    ]


def test_opening_keyboard_has_no_back_button():
    callbacks = [
        b.callback_data
        for row in runtime.build_begin_decomposition_keyboard().inline_keyboard
        for b in row
    ]
    assert "assist:back" not in callbacks
    assert callbacks == ["assist:begin_decomposition"]


def test_opening_keyboard_no_loads_is_continue_to_reactions_only():
    empty = {
        "exercise_type": "beam",
        "beam": {
            "L": 5.0,
            "support_mode": "simply_supported",
            "supports": [
                {"label": "A", "type": "pin", "x": 0.0},
                {"label": "B", "type": "roller", "x": 5.0},
            ],
            "loads": [{"type": "point", "x": 2.0, "Fy": 3.0}],
        },
    }
    kb = runtime.build_opening_keyboard(empty)
    rows = kb.inline_keyboard
    assert len(rows) == 1
    assert len(rows[0]) == 1
    assert rows[0][0].text == "המשך לריאקציות"
    assert rows[0][0].callback_data == "assist:to_reactions"


def test_opening_keyboard_with_loads_keeps_decomposition_buttons():
    kb = runtime.build_opening_keyboard(EXTRACTED)
    callbacks = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert callbacks == ["assist:begin_decomposition"]
    assert "assist:to_reactions" not in callbacks

@pytest.mark.anyio
async def test_deliver_no_loads_sends_continue_to_reactions_button():
    chat_id = 88037
    begin_image_session(chat_id, solve_mode=SolveMode.ASSISTANT)
    empty = {
        "exercise_type": "beam",
        "beam": {
            "L": 5.0,
            "support_mode": "simply_supported",
            "supports": [
                {"label": "A", "type": "pin", "x": 0.0},
                {"label": "B", "type": "roller", "x": 5.0},
            ],
            "loads": [{"type": "point", "x": 2.0, "Fy": 3.0}],
        },
    }
    context = MagicMock()
    context.bot.delete_message = AsyncMock()
    send_text = AsyncMock(return_value=MagicMock(message_id=51))
    edit_draft = AsyncMock()

    await runtime.deliver_assistant_after_approve(
        context,
        chat_id,
        extracted=empty,
        reply="ok",
        solved={"result": {"reactions": []}},
        draft_msg_id=None,
        send_text=send_text,
        edit_draft_message=edit_draft,
    )

    bodies = [c.args[2] for c in send_text.await_args_list]
    assert "שנמשיך?" in bodies[-1]
    assert "איך תרצה להמשיך" not in bodies[-1]
    last_kb = send_text.await_args_list[-1].kwargs.get("reply_markup")
    assert [b.text for row in last_kb.inline_keyboard for b in row] == [
        "המשך לריאקציות"
    ]
    assert [b.callback_data for row in last_kb.inline_keyboard for b in row] == [
        "assist:to_reactions"
    ]


@pytest.mark.anyio
async def test_back_button_restores_previous_decomposition_screen():
    chat_id = 88026
    runtime.clear_personal_assistant_progress(chat_id)
    begin_image_session(chat_id, solve_mode=SolveMode.ASSISTANT)
    runtime.start_personal_assistant(chat_id, EXTRACTED)
    first_text = runtime.screen_text_for_progress(
        runtime.get_personal_assistant_progress(chat_id)
    )

    context = MagicMock()
    context.bot.delete_message = AsyncMock()
    send_text = AsyncMock(return_value=MagicMock(message_id=301))

    await runtime.handle_assistant_action(context, chat_id, "next", send_text=send_text)
    advanced_text = send_text.await_args.args[2]
    assert advanced_text != first_text

    await runtime.handle_assistant_action(context, chat_id, "back", send_text=send_text)
    restored_text = send_text.await_args.args[2]
    assert restored_text == first_text
    restored_progress = runtime.get_personal_assistant_progress(chat_id)
    assert isinstance(restored_progress, DecompositionProgress)
    runtime.clear_personal_assistant_progress(chat_id)


@pytest.mark.anyio
async def test_back_button_from_first_decomposition_screen_returns_to_opening():
    chat_id = 88027
    runtime.clear_personal_assistant_progress(chat_id)
    begin_image_session(chat_id, solve_mode=SolveMode.ASSISTANT)
    runtime.start_opening(chat_id, EXTRACTED)

    context = MagicMock()
    context.bot.delete_message = AsyncMock()
    send_text = AsyncMock(return_value=MagicMock(message_id=302))

    await runtime.handle_assistant_action(
        context, chat_id, "begin_decomposition", send_text=send_text
    )
    assert isinstance(runtime.get_personal_assistant_progress(chat_id), DecompositionProgress)

    await runtime.handle_assistant_action(context, chat_id, "back", send_text=send_text)
    restored_progress = runtime.get_personal_assistant_progress(chat_id)
    assert isinstance(restored_progress, OpeningProgress)
    kb = send_text.await_args.kwargs.get("reply_markup")
    assert [b.callback_data for row in kb.inline_keyboard for b in row] == [
        "assist:begin_decomposition",
    ]
    runtime.clear_personal_assistant_progress(chat_id)


@pytest.mark.anyio
async def test_back_button_with_no_history_sends_message():
    chat_id = 88028
    runtime.clear_personal_assistant_progress(chat_id)
    progress = ReactionProgress(beam_kind=ReactionBeamKind.SIMPLY_SUPPORTED)
    runtime.set_personal_assistant_progress(chat_id, progress)

    context = MagicMock()
    context.bot.delete_message = AsyncMock()
    send_text = AsyncMock(return_value=MagicMock(message_id=303))

    await runtime.handle_assistant_action(context, chat_id, "back", send_text=send_text)
    text = send_text.await_args.args[2]
    assert "אין הודעה קודמת" in text
    runtime.clear_personal_assistant_progress(chat_id)


@pytest.mark.anyio
async def test_back_button_on_opening_progress_is_unavailable():
    chat_id = 88029
    runtime.clear_personal_assistant_progress(chat_id)
    runtime.start_opening(chat_id, EXTRACTED)

    context = MagicMock()
    context.bot.delete_message = AsyncMock()
    send_text = AsyncMock(return_value=MagicMock(message_id=304))

    await runtime.handle_assistant_action(context, chat_id, "back", send_text=send_text)
    text = send_text.await_args.args[2]
    assert "לא זמינה" in text
    runtime.clear_personal_assistant_progress(chat_id)


@pytest.mark.anyio
async def test_noop_button_does_nothing():
    chat_id = 88031
    runtime.clear_personal_assistant_progress(chat_id)
    progress = ReactionProgress(beam_kind=ReactionBeamKind.SIMPLY_SUPPORTED)
    runtime.set_personal_assistant_progress(chat_id, progress)

    context = MagicMock()
    context.bot.delete_message = AsyncMock()
    send_text = AsyncMock()

    await runtime.handle_assistant_action(context, chat_id, "noop", send_text=send_text)

    send_text.assert_not_awaited()
    context.bot.delete_message.assert_not_awaited()
    assert runtime.get_personal_assistant_progress(chat_id) is progress
    runtime.clear_personal_assistant_progress(chat_id)


@pytest.mark.anyio
async def test_to_reactions_from_opening_without_loads_enters_reactions():
    chat_id = 88032
    runtime.clear_personal_assistant_progress(chat_id)
    begin_image_session(chat_id, solve_mode=SolveMode.ASSISTANT)
    empty = {
        "exercise_type": "beam",
        "beam": {
            "L": 5.0,
            "support_mode": "simply_supported",
            "supports": [
                {"label": "A", "type": "pin", "x": 0.0},
                {"label": "B", "type": "roller", "x": 5.0},
            ],
            "loads": [{"type": "point", "x": 2.0, "Fy": 1.0}],
        },
    }
    runtime.start_opening(chat_id, empty)

    context = MagicMock()
    context.bot.delete_message = AsyncMock()
    send_text = AsyncMock(return_value=MagicMock(message_id=401))

    await runtime.handle_assistant_action(
        context, chat_id, "to_reactions", send_text=send_text
    )

    progress = runtime.get_personal_assistant_progress(chat_id)
    assert isinstance(progress, ReactionProgress)
    assert progress.equation == ReactionEquation.ENTRY
    assert progress.decomposed_load_indices == []
    text = send_text.await_args.args[2]
    assert "מכיוון שלא היה עומסים לפרק" in text

    await runtime.handle_assistant_action(context, chat_id, "back", send_text=send_text)
    restored = runtime.get_personal_assistant_progress(chat_id)
    assert isinstance(restored, OpeningProgress)
    runtime.clear_personal_assistant_progress(chat_id)


@pytest.mark.anyio
async def test_to_reactions_blocked_when_opening_has_loads():
    chat_id = 88032
    runtime.clear_personal_assistant_progress(chat_id)
    begin_image_session(chat_id, solve_mode=SolveMode.ASSISTANT)
    runtime.start_opening(chat_id, EXTRACTED)

    context = MagicMock()
    context.bot.delete_message = AsyncMock()
    send_text = AsyncMock(return_value=MagicMock(message_id=401))

    await runtime.handle_assistant_action(
        context, chat_id, "to_reactions", send_text=send_text
    )
    text = send_text.await_args.args[2]
    assert "פירוק העומסים" in text
    assert isinstance(runtime.get_personal_assistant_progress(chat_id), OpeningProgress)
    runtime.clear_personal_assistant_progress(chat_id)


@pytest.mark.anyio
async def test_to_reactions_unavailable_from_mid_decomposition():
    chat_id = 88033
    runtime.clear_personal_assistant_progress(chat_id)
    begin_image_session(chat_id, solve_mode=SolveMode.ASSISTANT)
    runtime.start_personal_assistant(chat_id, EXTRACTED)

    context = MagicMock()
    context.bot.delete_message = AsyncMock()
    send_text = AsyncMock(return_value=MagicMock(message_id=402))

    await runtime.handle_assistant_action(
        context, chat_id, "to_reactions", send_text=send_text
    )

    text = send_text.await_args.args[2]
    assert "לא זמינה" in text
    assert isinstance(
        runtime.get_personal_assistant_progress(chat_id), DecompositionProgress
    )
    runtime.clear_personal_assistant_progress(chat_id)


@pytest.mark.anyio
async def test_last_load_next_shows_finished_decomposition_message():
    chat_id = 88038
    runtime.clear_personal_assistant_progress(chat_id)
    begin_image_session(chat_id, solve_mode=SolveMode.ASSISTANT)
    runtime.start_personal_assistant(chat_id, EXTRACTED)

    context = MagicMock()
    context.bot.delete_message = AsyncMock()
    send_text = AsyncMock(return_value=MagicMock(message_id=410))

    # עומס ראשון → שני (אחרון) → ריאקציות
    await runtime.handle_assistant_action(context, chat_id, "next", send_text=send_text)
    await runtime.handle_assistant_action(context, chat_id, "next", send_text=send_text)

    progress = runtime.get_personal_assistant_progress(chat_id)
    assert isinstance(progress, ReactionProgress)
    text = send_text.await_args.args[2]
    assert "סיימנו את פירוק העומסים" in text
    assert "מכיוון שלא היה עומסים לפרק" not in text
    runtime.clear_personal_assistant_progress(chat_id)


@pytest.mark.anyio
async def test_to_reactions_shortcut_unavailable_once_already_in_reactions():
    chat_id = 88034
    runtime.clear_personal_assistant_progress(chat_id)
    progress = ReactionProgress(beam_kind=ReactionBeamKind.SIMPLY_SUPPORTED)
    runtime.set_personal_assistant_progress(chat_id, progress)

    context = MagicMock()
    context.bot.delete_message = AsyncMock()
    send_text = AsyncMock(return_value=MagicMock(message_id=403))

    await runtime.handle_assistant_action(
        context, chat_id, "to_reactions", send_text=send_text
    )
    text = send_text.await_args.args[2]
    assert "לא זמינה" in text
    runtime.clear_personal_assistant_progress(chat_id)


def test_clear_personal_assistant_progress_clears_history():
    chat_id = 88030
    progress = ReactionProgress(beam_kind=ReactionBeamKind.SIMPLY_SUPPORTED)
    runtime.set_personal_assistant_progress(chat_id, progress)
    runtime._push_personal_assistant_history(chat_id, progress)
    assert runtime._pop_personal_assistant_history(chat_id) is not None
    runtime._push_personal_assistant_history(chat_id, progress)

    runtime.clear_personal_assistant_progress(chat_id)
    assert runtime._pop_personal_assistant_history(chat_id) is None


def test_is_add_to_bank_mode_reflects_solve_mode():
    chat_id = 88035
    begin_image_session(chat_id, solve_mode=SolveMode.ADD_TO_BANK)
    assert runtime.is_add_to_bank_mode(chat_id) is True
    assert runtime.is_assistant_mode(chat_id) is False


@pytest.mark.anyio
async def test_deliver_after_draft_approve_routes_add_to_bank_mode():
    chat_id = 88036
    begin_image_session(chat_id, solve_mode=SolveMode.ADD_TO_BANK)

    context = MagicMock()
    send_text = AsyncMock()
    edit_draft = AsyncMock()
    deliver_notebook = AsyncMock()

    with patch.object(
        runtime, "deliver_exercise_bank_after_approve", new_callable=AsyncMock
    ) as mock_bank:
        await runtime.deliver_after_draft_approve(
            context,
            chat_id,
            extracted=EXTRACTED,
            reply="ok",
            solved={"result": {"reactions_ton": {}}},
            draft_msg_id=42,
            deliver_notebook=deliver_notebook,
            send_text=send_text,
            edit_draft_message=edit_draft,
        )

    mock_bank.assert_awaited_once_with(
        context,
        chat_id,
        extracted=EXTRACTED,
        reply="ok",
        solved={"result": {"reactions_ton": {}}},
        draft_msg_id=42,
        send_text=send_text,
        edit_draft_message=edit_draft,
    )
    deliver_notebook.assert_not_awaited()
