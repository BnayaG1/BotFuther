# -*- coding: utf-8 -*-
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import CallbackQuery, Message, Update

import bot.assistant as assistant
import bot.handlers as handlers
import bot.solution_session as solution_session
from bot.assistant import AssistantBeamKind


SIMPLY_SUPPORTED_EXTRACTED = {
    "exercise_type": "beam",
    "beam": {
        "L": 10.0,
        "support_mode": "simply_supported",
        "supports": [
            {"label": "A", "type": "pin", "x": 0.0},
            {"label": "B", "type": "roller", "x": 10.0},
        ],
        "loads": [
            {"type": "point", "x": 5.0, "Fy": 10.0},
            {"type": "inclined", "x": 8.0, "magnitude_ton": 5.0, "angle_deg": 30, "incl_dir": "dr"},
            {"type": "distributed", "x1": 2.0, "x2": 4.0, "w": 3.0},
        ],
    },
}

CANTILEVER_EXTRACTED = {
    "exercise_type": "beam",
    "beam": {
        "L": 8.0,
        "support_mode": "cantilever",
        "supports": [
            {"label": "A", "type": "fixed", "x": 0.0},
        ],
        "loads": [
            {"type": "distributed", "x1": 1.0, "x2": 3.0, "w": 2.0},
            {"type": "inclined", "x": 6.0, "magnitude_ton": 4.0, "angle_deg": 45, "incl_dir": "dl"},
        ],
    },
}


def test_detect_simply_supported_from_draft():
    assert assistant.detect_assistant_beam_kind(SIMPLY_SUPPORTED_EXTRACTED) == (
        AssistantBeamKind.SIMPLY_SUPPORTED
    )


def test_detect_cantilever_from_draft():
    assert assistant.detect_assistant_beam_kind(CANTILEVER_EXTRACTED) == (
        AssistantBeamKind.CANTILEVER
    )


def test_master_demo_exercise_is_simply_supported_with_two_distributed_loads():
    assert assistant.detect_assistant_beam_kind(assistant.MASTER_DEMO_EXTRACTED) == (
        AssistantBeamKind.SIMPLY_SUPPORTED
    )
    beam = assistant.MASTER_DEMO_EXTRACTED["beam"]
    assert beam["L"] == 9.0
    entries = assistant.decomposition_load_entries(assistant.MASTER_DEMO_EXTRACTED)
    assert len(entries) == 2
    assert [idx for idx, _ in entries] == [0, 1]


def test_decomposition_loads_sorted_left_to_right():
    entries = assistant.decomposition_load_entries(SIMPLY_SUPPORTED_EXTRACTED)
    assert [idx for idx, _ in entries] == [2, 1]
    xs = [assistant._load_left_x(ld, SIMPLY_SUPPORTED_EXTRACTED["beam"]) for _, ld in entries]
    assert xs == sorted(xs)


def test_step_one_title_is_decomposition_for_both_kinds():
    supported = assistant.assistant_steps_for_kind(AssistantBeamKind.SIMPLY_SUPPORTED)[0]
    cantilever = assistant.assistant_steps_for_kind(AssistantBeamKind.CANTILEVER)[0]
    assert "פרוק עומסים" in supported.title
    assert supported.title == cantilever.title


def test_assistant_plan_steps_differ_by_kind():
    msg_supported, kind_supported = assistant.build_assistant_plan_message_hebrew(
        SIMPLY_SUPPORTED_EXTRACTED
    )
    msg_cantilever, kind_cantilever = assistant.build_assistant_plan_message_hebrew(
        CANTILEVER_EXTRACTED
    )

    assert kind_supported == AssistantBeamKind.SIMPLY_SUPPORTED
    assert kind_cantilever == AssistantBeamKind.CANTILEVER
    assert "2 סמכים" in msg_supported or "שני סמכים" in msg_supported
    assert "ריתום" in msg_cantilever
    assert "בשלב הראשון" in msg_supported
    assert "משמאל לימין" in msg_supported
    assert "1. פרוק עומסים" not in msg_supported


def test_explain_inclined_describes_process_not_answer():
    ld = SIMPLY_SUPPORTED_EXTRACTED["beam"]["loads"][1]
    text = assistant.explain_inclined_load_hebrew(ld)
    assert "Fx" in text
    assert "Fy" in text
    assert "טון" not in text
    assert "=" not in text


def test_explain_distributed_describes_process_not_answer():
    ld = SIMPLY_SUPPORTED_EXTRACTED["beam"]["loads"][2]
    text = assistant.explain_distributed_load_hebrew(ld, SIMPLY_SUPPORTED_EXTRACTED["beam"])
    assert "הכח השקול" in text
    assert "t/m" in text
    assert "R =" not in text
    assert "=" not in text


def test_explain_later_step_gives_procedure():
    progress = solution_session.AssistantProgress(
        beam_kind=AssistantBeamKind.SIMPLY_SUPPORTED.value,
        extracted=SIMPLY_SUPPORTED_EXTRACTED,
        step_index=1,
    )
    text = assistant.explain_current_step_hebrew(progress)
    assert "Ax" in text
    assert "בקרוב" not in text


def test_assistant_step_keyboard_includes_choose_step():
    kb = assistant.build_assistant_step_keyboard()
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    texts = [btn.text for row in kb.inline_keyboard for btn in row]
    assert "assist:choose" in callbacks
    assert "assist:explain" in callbacks
    assert "בחר שלב" in texts


def test_assistant_step_keyboard_omits_explain_after_explanation():
    kb = assistant.build_assistant_step_keyboard(include_explain=False)
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    texts = [btn.text for row in kb.inline_keyboard for btn in row]
    assert "assist:explain" not in callbacks
    assert "assist:show" not in callbacks
    assert "assist:next" in callbacks
    assert "בחר שלב" in texts


def test_step_picker_lists_all_steps_for_beam_kind():
    progress = solution_session.AssistantProgress(
        beam_kind=AssistantBeamKind.SIMPLY_SUPPORTED.value,
        extracted=SIMPLY_SUPPORTED_EXTRACTED,
    )
    kb = assistant.build_assistant_step_picker_keyboard(progress)
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert callbacks[:7] == [f"assist:goto:{n}" for n in range(1, 8)]
    assert "assist:back" in callbacks


def test_jump_to_assistant_step_resets_sub_index():
    progress = solution_session.AssistantProgress(
        beam_kind=AssistantBeamKind.SIMPLY_SUPPORTED.value,
        extracted=SIMPLY_SUPPORTED_EXTRACTED,
        step_index=0,
        sub_index=2,
        decomposition_indices=[2, 1],
    )
    updated = assistant.jump_to_assistant_step(progress, 4)
    assert updated is not None
    assert updated.step_index == 3
    assert updated.sub_index == 0


def test_parse_assistant_callback_accepts_goto_and_choose():
    assert assistant.parse_assistant_callback("assist:choose") == "choose"
    assert assistant.parse_assistant_callback("assist:goto:5") == "goto:5"
    assert assistant.parse_assistant_callback("assist:goto:0") is None
    assert assistant.parse_assistant_callback("assist:show") == "show"
    assert assistant.parse_assistant_callback("assist:yes") == "yes"


def test_step_phrase_uses_ordinals_not_digits():
    assert assistant.step_phrase_hebrew(1) == "השלב הראשון"
    assert assistant.step_phrase_hebrew(2, total=7) == "השלב השני מתוך 7"


def test_step_header_collaborative_tone():
    progress = solution_session.AssistantProgress(
        beam_kind=AssistantBeamKind.SIMPLY_SUPPORTED.value,
        extracted=SIMPLY_SUPPORTED_EXTRACTED,
    )
    header = assistant._step_header_hebrew(progress, friendly=False)
    assert "עכשיו אנחנו נעבור על השלב הראשון" in header
    assert "שלב 1" not in header
def test_step_prompt_omits_friendly_opener_when_requested():
    progress = solution_session.AssistantProgress(
        beam_kind=AssistantBeamKind.SIMPLY_SUPPORTED.value,
        extracted=SIMPLY_SUPPORTED_EXTRACTED,
        decomposition_indices=[2, 1],
    )
    text = assistant.build_step_prompt_hebrew(progress, friendly=False)
    assert not text.startswith("מעולה")
    assert "העומס הראשון ברשימה" in text


def test_distributed_decomposition_prompt_includes_equivalent_load_context():
    progress = solution_session.AssistantProgress(
        beam_kind=AssistantBeamKind.SIMPLY_SUPPORTED.value,
        extracted=SIMPLY_SUPPORTED_EXTRACTED,
        decomposition_indices=[2, 1],
    )
    text = assistant.build_decomposition_prompt_hebrew(progress, friendly=False)

    assert "העומס השקול" in text
    assert "הריאקציות בהמשך" in text
    assert "עומס מפורס" in text
    assert "רוצה הסבר איך לפרוק אותו, או שנמשיך?" in text
    assert "נתמקד בעומס" not in text


def test_inclined_decomposition_prompt_includes_component_context():
    progress = solution_session.AssistantProgress(
        beam_kind=AssistantBeamKind.SIMPLY_SUPPORTED.value,
        extracted=SIMPLY_SUPPORTED_EXTRACTED,
        sub_index=1,
        decomposition_indices=[2, 1],
    )
    text = assistant.build_decomposition_prompt_hebrew(progress, friendly=False)

    assert "רכיבים אופקיים ואנכיים" in text
    assert "הריאקציות בהמשך" in text
    assert "עומס אלכסוני" in text
    assert "רוצה הסבר איך לפרוק אותו, או שנמשיך?" in text
    assert "עברנו לפירוק של הכח הבעייתי הבא" in text
    assert "נתמקד בעומס" not in text


def test_deliver_assistant_uses_friendly_opener_only_on_plan_message():
    plan_text, _ = assistant.build_assistant_plan_message_hebrew(SIMPLY_SUPPORTED_EXTRACTED)
    assert plan_text.startswith("מעולה")
    step_text = assistant.build_step_prompt_hebrew(
        solution_session.AssistantProgress(
            beam_kind=AssistantBeamKind.SIMPLY_SUPPORTED.value,
            extracted=SIMPLY_SUPPORTED_EXTRACTED,
        ),
        friendly=False,
    )
    assert not step_text.startswith("מעולה")


@pytest.mark.anyio
async def test_deliver_assistant_starts_progress_and_first_load():
    chat_id = 99001
    solution_session.begin_image_session(chat_id, solve_mode=solution_session.SolveMode.ASSISTANT)

    context = MagicMock()
    context.bot.delete_message = AsyncMock()
    send_text = AsyncMock()

    await assistant.deliver_assistant_after_approve(
        context,
        chat_id,
        extracted=SIMPLY_SUPPORTED_EXTRACTED,
        reply="ok",
        solved={"result": {"reactions_ton": {}}},
        draft_msg_id=44,
        send_text=send_text,
        edit_draft_message=AsyncMock(),
    )

    progress = solution_session.get_assistant_progress(chat_id)
    assert progress is not None
    assert progress.decomposition_indices == [2, 1]
    assert progress.sub_index == 0
    assert send_text.await_count == 3


@pytest.mark.anyio
async def test_assistant_next_moves_to_second_load():
    chat_id = 99002
    assistant.start_assistant_progress(
        chat_id, SIMPLY_SUPPORTED_EXTRACTED, AssistantBeamKind.SIMPLY_SUPPORTED
    )
    context = MagicMock()
    send_text = AsyncMock()

    await assistant.handle_assistant_action(
        context,
        chat_id,
        "next",
        send_text=send_text,
        reply_message=None,
    )

    progress = solution_session.get_assistant_progress(chat_id)
    assert progress is not None
    assert progress.sub_index == 1
    send_text.assert_awaited()


def test_next_decomposition_message_for_new_type_includes_context():
    progress = solution_session.AssistantProgress(
        beam_kind=AssistantBeamKind.SIMPLY_SUPPORTED.value,
        extracted=SIMPLY_SUPPORTED_EXTRACTED,
        step_index=0,
        sub_index=1,
        decomposition_indices=[2, 1],
    )
    text = assistant.build_next_decomposition_item_message_hebrew(progress, prefix="יופי,")
    assert "עברנו לפירוק של הכח הבעייתי הבא" in text
    assert "שוב" not in text
    assert "בשביל לפתור את המשך התרגיל" in text
    assert "עומס אלכסוני" in text
    assert "רוצה הסבר איך לפרוק אותו, או שנמשיך?" in text


def test_next_decomposition_message_for_repeated_type_says_again_and_omits_context():
    extracted = {
        "exercise_type": "beam",
        "beam": {
            "L": 10.0,
            "support_mode": "simply_supported",
            "supports": [
                {"label": "A", "type": "pin", "x": 0.0},
                {"label": "B", "type": "roller", "x": 10.0},
            ],
            "loads": [
                {"type": "distributed", "x1": 1.0, "x2": 2.0, "w": 3.0},
                {"type": "distributed", "x1": 4.0, "x2": 5.0, "w": 2.0},
            ],
        },
    }
    progress = solution_session.AssistantProgress(
        beam_kind=AssistantBeamKind.SIMPLY_SUPPORTED.value,
        extracted=extracted,
        step_index=0,
        sub_index=1,
        decomposition_indices=[0, 1],
    )
    text = assistant.build_next_decomposition_item_message_hebrew(progress, prefix="מעולה,")
    assert "שוב מפורס" in text
    assert "בשביל לפתור את המשך התרגיל" not in text


@pytest.mark.anyio
async def test_assistant_explain_does_not_advance():
    chat_id = 99003
    assistant.start_assistant_progress(
        chat_id, SIMPLY_SUPPORTED_EXTRACTED, AssistantBeamKind.SIMPLY_SUPPORTED
    )
    context = MagicMock()
    send_text = AsyncMock()

    await assistant.handle_assistant_action(
        context,
        chat_id,
        "explain",
        send_text=send_text,
        reply_message=None,
    )

    progress = solution_session.get_assistant_progress(chat_id)
    assert progress is not None
    assert progress.sub_index == 0
    assert send_text.await_count == 1
    explain_body = send_text.await_args.args[2]
    assert not explain_body.startswith("מעולה")
    assert "הכח השקול" in explain_body
    assert "R =" not in explain_body
    actions_kwargs = send_text.await_args.kwargs
    action_callbacks = [
        btn.callback_data
        for row in actions_kwargs["reply_markup"].inline_keyboard
        for btn in row
    ]
    assert "assist:explain" not in action_callbacks
    assert "assist:show" in action_callbacks
    assert "assist:next" in action_callbacks


@pytest.mark.anyio
async def test_assistant_explain_ax_includes_show_solution_button():
    chat_id = 99111
    assistant.start_assistant_progress(
        chat_id, SIMPLY_SUPPORTED_EXTRACTED, AssistantBeamKind.SIMPLY_SUPPORTED
    )
    progress = solution_session.get_assistant_progress(chat_id)
    assert progress is not None
    progress.step_index = 1
    progress.reaction_sub_index = 0
    solution_session.set_assistant_progress(chat_id, progress)

    context = MagicMock()
    send_text = AsyncMock()

    await assistant.handle_assistant_action(
        context,
        chat_id,
        "explain",
        send_text=send_text,
        reply_message=None,
    )

    body = send_text.await_args.args[2]
    assert "Ax" in body
    markup = send_text.await_args.kwargs["reply_markup"]
    callbacks = [
        btn.callback_data for row in markup.inline_keyboard for btn in row
    ]
    texts = [btn.text for row in markup.inline_keyboard for btn in row]
    assert "assist:show" in callbacks
    assert "assist:yes" in callbacks
    assert "כן" in texts
    yes_idx = texts.index("כן")
    next_idx = texts.index("המשך")
    assert yes_idx < next_idx


@pytest.mark.anyio
async def test_assistant_yes_on_ax_shows_equation():
    chat_id = 99112
    assistant.start_assistant_progress(
        chat_id, SIMPLY_SUPPORTED_EXTRACTED, AssistantBeamKind.SIMPLY_SUPPORTED
    )
    progress = solution_session.get_assistant_progress(chat_id)
    assert progress is not None
    progress.step_index = 1
    progress.reaction_sub_index = 0
    solution_session.set_assistant_progress(chat_id, progress)

    context = MagicMock()
    send_text = AsyncMock()

    await assistant.handle_assistant_action(
        context,
        chat_id,
        "yes",
        send_text=send_text,
        reply_message=None,
    )

    body = send_text.await_args.args[2]
    assert "Ax" in body
    assert "= 0" in body
    callbacks = [
        btn.callback_data
        for row in send_text.await_args.kwargs["reply_markup"].inline_keyboard
        for btn in row
    ]
    assert "assist:yes" not in callbacks
    assert "assist:show" in callbacks


@pytest.mark.anyio
async def test_assistant_yes_on_ax_with_single_horizontal_load_uses_single_load_wording():
    chat_id = 99114
    extracted = {
        "exercise_type": "beam",
        "beam": {
            "L": 10.0,
            "support_mode": "simply_supported",
            "supports": [
                {"label": "A", "type": "pin", "x": 0.0},
                {"label": "B", "type": "roller", "x": 10.0},
            ],
            "loads": [
                {"type": "point", "x": 4.0, "Fy": 2.0, "Fx": 3.0},
            ],
        },
    }
    assistant.start_assistant_progress(chat_id, extracted, AssistantBeamKind.SIMPLY_SUPPORTED)
    progress = solution_session.get_assistant_progress(chat_id)
    assert progress is not None
    progress.step_index = 1
    progress.reaction_sub_index = 0
    solution_session.set_assistant_progress(chat_id, progress)

    context = MagicMock()
    send_text = AsyncMock()

    await assistant.handle_assistant_action(
        context,
        chat_id,
        "yes",
        send_text=send_text,
        reply_message=None,
    )

    body = send_text.await_args.args[2]
    assert "יש רק עומס צירי אחד" in body
    assert "זה יראה ככה" in body
    assert "Ax" in body
    assert "= 0" in body


@pytest.mark.anyio
async def test_assistant_yes_on_ax_when_no_horizontal_loads_shows_ax_zero_message():
    chat_id = 99113
    extracted = {
        "exercise_type": "beam",
        "beam": {
            "L": 10.0,
            "support_mode": "simply_supported",
            "supports": [
                {"label": "A", "type": "pin", "x": 0.0},
                {"label": "B", "type": "roller", "x": 10.0},
            ],
            "loads": [
                {"type": "point", "x": 5.0, "Fy": 10.0},
                {"type": "distributed", "x1": 2.0, "x2": 4.0, "w": 3.0},
            ],
        },
    }
    assistant.start_assistant_progress(chat_id, extracted, AssistantBeamKind.SIMPLY_SUPPORTED)
    progress = solution_session.get_assistant_progress(chat_id)
    assert progress is not None
    progress.step_index = 1
    progress.reaction_sub_index = 0
    solution_session.set_assistant_progress(chat_id, progress)

    context = MagicMock()
    send_text = AsyncMock()

    await assistant.handle_assistant_action(
        context,
        chat_id,
        "yes",
        send_text=send_text,
        reply_message=None,
    )

    body = send_text.await_args.args[2]
    assert "אין כוחות על ציר הx" in body
    assert "Ax = 0" in body
    assert "⬆️" in body


@pytest.mark.anyio
async def test_assistant_choose_shows_step_picker():
    chat_id = 99005
    assistant.start_assistant_progress(
        chat_id, SIMPLY_SUPPORTED_EXTRACTED, AssistantBeamKind.SIMPLY_SUPPORTED
    )
    context = MagicMock()
    send_text = AsyncMock()
    await assistant.handle_assistant_action(
        context,
        chat_id,
        "choose",
        send_text=send_text,
        reply_message=None,
    )

    send_text.assert_awaited()
    body = send_text.await_args.args[2]
    assert "בחר/י" in body or "לאיזה שלב" in body
    kwargs = send_text.await_args.kwargs
    callbacks = [
        btn.callback_data
        for row in kwargs["reply_markup"].inline_keyboard
        for btn in row
    ]
    assert "assist:goto:1" in callbacks
    assert "assist:goto:7" in callbacks


@pytest.mark.anyio
async def test_reactions_next_from_ax_to_ay_has_custom_message_for_simply_supported():
    chat_id = 99120
    assistant.start_assistant_progress(
        chat_id, SIMPLY_SUPPORTED_EXTRACTED, AssistantBeamKind.SIMPLY_SUPPORTED
    )
    progress = solution_session.get_assistant_progress(chat_id)
    assert progress is not None
    progress.step_index = 1
    progress.reaction_sub_index = 0
    solution_session.set_assistant_progress(chat_id, progress)

    context = MagicMock()
    send_text = AsyncMock()
    await assistant.handle_assistant_action(
        context,
        chat_id,
        "next",
        send_text=send_text,
        reply_message=None,
    )

    body = send_text.await_args.args[2]
    assert "נמצא עכשיו את הריאקציה הבאה בתור" in body
    assert "Ay" in body


@pytest.mark.anyio
async def test_ay_sub_button_shows_same_screen_as_next_from_ax():
    """לחיצה על Ay בתפריט = אותה הודעת כניסה כמו המשך מ-Ax (בלי קידומת עידוד)."""
    chat_id = 99124
    assistant.start_assistant_progress(
        chat_id, SIMPLY_SUPPORTED_EXTRACTED, AssistantBeamKind.SIMPLY_SUPPORTED
    )
    progress = solution_session.get_assistant_progress(chat_id)
    assert progress is not None
    progress.step_index = 1
    progress.reaction_sub_index = 0
    solution_session.set_assistant_progress(chat_id, progress)

    context = MagicMock()
    send_next = AsyncMock()
    await assistant.handle_assistant_action(
        context, chat_id, "next", send_text=send_next, reply_message=None
    )
    next_body = send_next.await_args.args[2]
    # הסרת קידומת עידוד להשוואה לתוכן המסך
    next_core = next_body.split("נמצא עכשיו", 1)[-1]
    next_core = "נמצא עכשיו" + next_core

    progress = solution_session.get_assistant_progress(chat_id)
    assert progress is not None
    progress.reaction_sub_index = 0
    solution_session.set_assistant_progress(chat_id, progress)

    send_sub = AsyncMock()
    await assistant.handle_assistant_action(
        context, chat_id, "sub:1", send_text=send_sub, reply_message=None
    )
    sub_body = send_sub.await_args.args[2]
    assert sub_body == next_core
    assert "נתחיל מתת-שלב" not in sub_body


def test_current_screen_ay_matches_reaction_builder():
    progress = solution_session.AssistantProgress(
        beam_kind=AssistantBeamKind.SIMPLY_SUPPORTED.value,
        extracted=SIMPLY_SUPPORTED_EXTRACTED,
        step_index=1,
        reaction_sub_index=1,
    )
    assert assistant.build_current_screen_hebrew(progress) == (
        assistant.build_reaction_substep_screen_hebrew(progress)
    )
    assert "נמצא עכשיו את הריאקציה הבאה בתור - Ay" in (
        assistant.build_current_screen_hebrew(progress)
    )


def test_goto_reactions_opens_ax_screen_same_as_builder():
    progress = solution_session.AssistantProgress(
        beam_kind=AssistantBeamKind.SIMPLY_SUPPORTED.value,
        extracted=SIMPLY_SUPPORTED_EXTRACTED,
        step_index=0,
    )
    updated = assistant.jump_to_assistant_step(progress, 2)
    assert updated is not None
    assert updated.reaction_sub_index == 0
    text = assistant.build_current_screen_hebrew(updated)
    assert "הגענו לשלב השני - מציאת הריאקציות" in text
    assert "נתחיל מAx" in text


@pytest.mark.anyio
async def test_explain_ay_for_simply_supported_has_custom_balance_about_b_message():
    chat_id = 99121
    assistant.start_assistant_progress(
        chat_id, SIMPLY_SUPPORTED_EXTRACTED, AssistantBeamKind.SIMPLY_SUPPORTED
    )
    progress = solution_session.get_assistant_progress(chat_id)
    assert progress is not None
    progress.step_index = 1
    progress.reaction_sub_index = 1
    solution_session.set_assistant_progress(chat_id, progress)

    context = MagicMock()
    send_text = AsyncMock()

    await assistant.handle_assistant_action(
        context,
        chat_id,
        "explain",
        send_text=send_text,
        reply_message=None,
    )

    body = send_text.await_args.args[2]
    assert "בשביל למצוא את Ay" in body
    assert "הנקודה B" in body
    assert "By מתבטל" in body

    callbacks = [
        btn.callback_data
        for row in send_text.await_args.kwargs["reply_markup"].inline_keyboard
        for btn in row
    ]
    assert "assist:yes" in callbacks


@pytest.mark.anyio
async def test_yes_on_ay_builds_mb_equation_message_for_simply_supported():
    chat_id = 99122
    assistant.start_assistant_progress(
        chat_id, assistant.MASTER_DEMO_EXTRACTED, AssistantBeamKind.SIMPLY_SUPPORTED
    )
    progress = solution_session.get_assistant_progress(chat_id)
    assert progress is not None
    progress.step_index = 1
    progress.reaction_sub_index = 1
    solution_session.set_assistant_progress(chat_id, progress)

    context = MagicMock()
    send_text = AsyncMock()

    await assistant.handle_assistant_action(
        context,
        chat_id,
        "yes",
        send_text=send_text,
        reply_message=None,
    )

    body = send_text.await_args.args[2]
    assert "ΣMB" in body
    assert "3 עומסים אנכיים" in body
    assert "מומנט טהור ועומס צירי" in body
    assert "נתחיל בכח הראשון משמאל" in body
    assert "הכח הבא הוא" in body
    assert "Ay" in body
    markup = send_text.await_args.kwargs["reply_markup"]
    callbacks = [
        btn.callback_data for row in markup.inline_keyboard for btn in row
    ]
    texts = [btn.text for row in markup.inline_keyboard for btn in row]
    assert "assist:show" in callbacks
    assert "הצג פתרון" in texts
    # פריסה: [↩️?] / Ax|הצג פתרון / Ay|פתרתי / By|בחר שלב
    rows = markup.inline_keyboard
    data_rows = rows[1:] if rows and rows[0] and rows[0][0].callback_data == "assist:prev" else rows
    assert len(data_rows) == 3
    assert data_rows[0][0].text == "Ax"
    assert data_rows[0][1].text == "הצג פתרון"
    assert data_rows[1][0].text == "Ay"
    assert data_rows[1][1].text == "המשך"
    assert data_rows[2][0].text == "By"
    assert data_rows[2][1].text == "בחר שלב"


@pytest.mark.anyio
async def test_show_on_ay_displays_ay_value():
    chat_id = 99123
    assistant.start_assistant_progress(
        chat_id, assistant.MASTER_DEMO_EXTRACTED, AssistantBeamKind.SIMPLY_SUPPORTED
    )
    progress = solution_session.get_assistant_progress(chat_id)
    assert progress is not None
    progress.step_index = 1
    progress.reaction_sub_index = 1
    solution_session.set_assistant_progress(chat_id, progress)

    context = MagicMock()
    send_text = AsyncMock()

    await assistant.handle_assistant_action(
        context,
        chat_id,
        "show",
        send_text=send_text,
        reply_message=None,
    )

    body = send_text.await_args.args[2]
    assert body.startswith("ככה נראית המשוואה שלנו:")
    assert "+7Ay" in body
    assert "-(6.5·15)" in body
    assert "-(3·2)" in body
    assert "-(2·4)" in body
    assert "כשפותחים את כל האיברים המשוואה תיראה ככה:" in body
    assert "+7Ay-97.5-6-8=0" in body
    assert "-=" not in body
    assert "+7Ay-(6.5·15)-(3·2)-(2·4)=0" in body
    assert "והתוצאה:" in body
    assert "Ay = 15.93t" in body
    markup = send_text.await_args.kwargs["reply_markup"]
    callbacks = [
        btn.callback_data for row in markup.inline_keyboard for btn in row
    ]
    assert "assist:show" not in callbacks
    assert "assist:next" in callbacks


def test_build_ay_mb_assembled_equation_for_master_demo():
    text = assistant.build_ay_mb_assembled_equation_hebrew(assistant.MASTER_DEMO_EXTRACTED)
    assert text == (
        "ככה נראית המשוואה שלנו:\n"
        "+7Ay-(6.5·15)-(3·2)-(2·4)=0\n"
        "כשפותחים את כל האיברים המשוואה תיראה ככה:\n"
        "+7Ay-97.5-6-8=0\n"
        "והתוצאה:\n"
        "Ay = 15.93t"
    )


def test_build_ay_mb_equation_message_counts_vertical_loads():
    text = assistant.build_ay_mb_equation_message_hebrew(SIMPLY_SUPPORTED_EXTRACTED)
    assert "ΣMB" in text
    assert "עומסים אנכיים" in text
    assert "עומס מפורס" in text or "עומס נקודתי" in text or "עומס אלכסוני" in text


def test_vertical_force_rotation_about_b_matches_geometry():
    # B ב-x=9; כוח למטה משמאל → נגד כיוון השעון
    assert assistant._vertical_force_rotates_clockwise_about(9.0, 2.5, vertical_down=True) is False
    # כוח למעלה משמאל (Ay) → עם כיוון השעון
    assert assistant._vertical_force_rotates_clockwise_about(9.0, 2.0, vertical_down=False) is True
    # כוח למטה מימין לנקודה → עם כיוון השעון
    assert assistant._vertical_force_rotates_clockwise_about(5.0, 8.0, vertical_down=True) is True
    # כוח למעלה מימין לנקודה → נגד כיוון השעון
    assert assistant._vertical_force_rotates_clockwise_about(5.0, 8.0, vertical_down=False) is False


def test_ay_mb_message_uses_correct_clock_words_for_master_demo():
    text = assistant.build_ay_mb_equation_message_hebrew(assistant.MASTER_DEMO_EXTRACTED)
    # Ay למעלה משמאל ל-B
    assert "מסתובבת עם כיוון השעון" in text
    assert "+7Ay" in text
    # עומסים אנכיים למטה משמאל ל-B
    assert "מסתובב נגד כיוון השעון" in text
    assert "כ-(6.5·15)" in text
    assert "כ-(3·2)" in text
    assert "כ-(2·4)" in text


def test_solve_does_not_corrupt_master_demo_or_ay_lever_arms():
    """solve/finalize לא יקלקלו את MASTER_DEMO ולא יחזירו מרחקים ל-x=7 במקום B."""
    import copy

    from bot.solution_check import solve_extracted_beam
    from bot.vision import finalize_beam_extraction

    pristine = copy.deepcopy(assistant.MASTER_DEMO_EXTRACTED)
    master = finalize_beam_extraction(copy.deepcopy(assistant.MASTER_DEMO_EXTRACTED))
    solve_extracted_beam(master)

    assert assistant.MASTER_DEMO_EXTRACTED["beam"]["supports"] == pristine["beam"]["supports"]
    assert assistant.MASTER_DEMO_EXTRACTED["beam"]["loads"] == pristine["beam"]["loads"]

    text = assistant.build_ay_mb_equation_message_hebrew(master)
    assert "+7Ay" in text
    assert "כ-(6.5·15)" in text
    assert "כ-(3·2)" in text
    assert "כ-(2·4)" in text
    assert "כ-(4.5·15)" not in text
    assert "כ-(1·2)" not in text
    assert "כ-(0·4)" not in text


@pytest.mark.anyio
async def test_assistant_goto_jumps_to_selected_step():
    chat_id = 99006
    assistant.start_assistant_progress(
        chat_id, SIMPLY_SUPPORTED_EXTRACTED, AssistantBeamKind.SIMPLY_SUPPORTED
    )
    context = MagicMock()
    send_text = AsyncMock()

    with patch.object(assistant, "present_assistant_step", new_callable=AsyncMock) as mock_present:
        await assistant.handle_assistant_action(
            context,
            chat_id,
            "goto:5",
            send_text=send_text,
            reply_message=None,
        )

    progress = solution_session.get_assistant_progress(chat_id)
    assert progress is not None
    assert progress.step_index == 4
    assert progress.sub_index == 0
    mock_present.assert_awaited_once()


@pytest.mark.anyio
async def test_on_assistant_callback_routes_next():
    from personal_assistant import runtime

    chat_id = 99004
    runtime.clear_personal_assistant_progress(chat_id)
    runtime.start_personal_assistant(chat_id, SIMPLY_SUPPORTED_EXTRACTED)

    update = MagicMock(spec=Update)
    query = MagicMock(spec=CallbackQuery)
    query.data = "assist:next"
    query.answer = AsyncMock()
    query.message = MagicMock(spec=Message)
    query.message.chat_id = chat_id
    query.message.reply_text = AsyncMock()
    update.callback_query = query

    context = MagicMock()

    with patch.object(handlers, "handle_assistant_action", new_callable=AsyncMock) as mock_handle:
        await handlers.on_assistant_callback(update, context)

    mock_handle.assert_awaited_once()
    assert mock_handle.await_args.args[2] == "next"
    runtime.clear_personal_assistant_progress(chat_id)
