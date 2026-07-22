# -*- coding: utf-8 -*-
"""מבנה שלב הריאקציות בעוזר האישי — נוסחי Ax/Ay + שלד."""

from personal_assistant.flow import (
    AssistantStepId,
    enter_reactions_after_decomposition,
    next_step_after,
)
from personal_assistant.screens import build_current_screen_hebrew
from personal_assistant.decomposition import (
    DecompositionState,
    enter_decomposition,
)
from personal_assistant.reactions import (
    ReactionBeamKind,
    ReactionEquation,
    ReactionPhase,
    advance_reactions,
    detect_reaction_beam_kind,
    enter_reactions,
    jump_to_reaction_equation,
    reactions_equation_sequence,
    reactions_screen_id,
    set_reaction_phase,
)


SIMPLY = {
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
            {"type": "point", "x": 6.0, "Fy": 2.0},
            {
                "type": "inclined",
                "x": 4.0,
                "magnitude_ton": 5.0,
                "angle_deg": 30.0,
                "incl_dir": "dr",
            },
        ],
    },
}

CANTILEVER = {
    "exercise_type": "beam",
    "beam": {
        "L": 8.0,
        "support_mode": "cantilever",
        "supports": [{"label": "A", "type": "fixed", "x": 0.0}],
        "loads": [
            {
                "type": "inclined",
                "x": 3.0,
                "magnitude_ton": 4.0,
                "angle_deg": 45.0,
                "incl_dir": "dl",
            },
        ],
    },
}


def test_detect_simply_supported_and_cantilever():
    assert detect_reaction_beam_kind(SIMPLY) == ReactionBeamKind.SIMPLY_SUPPORTED
    assert detect_reaction_beam_kind(CANTILEVER) == ReactionBeamKind.CANTILEVER


def test_simply_supported_equation_order():
    seq = reactions_equation_sequence(ReactionBeamKind.SIMPLY_SUPPORTED)
    assert seq == (
        ReactionEquation.ENTRY,
        ReactionEquation.SIGMA_FX,
        ReactionEquation.SIGMA_MB,
        ReactionEquation.SIGMA_MA,
        ReactionEquation.STABILITY_FY,
        ReactionEquation.DONE,
    )


def test_cantilever_equation_order():
    seq = reactions_equation_sequence(ReactionBeamKind.CANTILEVER)
    assert seq == (
        ReactionEquation.ENTRY,
        ReactionEquation.SIGMA_FX,
        ReactionEquation.SIGMA_MA_FIXED,
        ReactionEquation.SIGMA_M_TIP,
        ReactionEquation.STABILITY_FY,
        ReactionEquation.DONE,
    )


def test_reactions_entry_shows_opening_message():
    progress = enter_reactions(SIMPLY, decomposed_load_indices=[0, 1])
    text = build_current_screen_hebrew(progress)
    assert "סיימנו את פירוק העומסים" in text
    assert "מציאת הריאקציות" in text
    assert "2 סמכים" in text
    assert "נשתמש בעומסים שפירקנו" in text
    assert "לחץ/י כדי להתחיל" in text


def test_reactions_entry_skip_no_decomposition_note():
    no_decomp_loads = {
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
    progress = enter_reactions(no_decomp_loads, decomposed_load_indices=[])
    text = build_current_screen_hebrew(progress)
    assert "מכיוון שלא היה עומסים לפרק, אנחנו עוברים" in text
    assert "מציאת הריאקציות" in text
    assert "עכשיו" not in text
    assert "לחץ/י כדי להתחיל" in text
    assert "סיימנו את פירוק העומסים" not in text
    assert "נשתמש בעומסים שפירקנו" not in text
    assert "הגענו לשלב הריאקציות" not in text


def test_reactions_entry_skipped_with_loads_present():
    """דילוג על פירוק כשיש עומסים — לא מציגים «לא היה עומסים לפרק»."""
    progress = enter_reactions(SIMPLY, decomposed_load_indices=[])
    text = build_current_screen_hebrew(progress)
    assert "הגענו לשלב הריאקציות" in text
    assert "באיזו ריאקציה להתחיל" in text
    assert "המשך" in text
    assert "מכיוון שלא היה עומסים לפרק" not in text
    assert "סיימנו את פירוק העומסים" not in text


def test_enter_and_advance_simply_supported_to_done():
    progress = enter_reactions(SIMPLY, decomposed_load_indices=[0, 1])
    assert progress.beam_kind == ReactionBeamKind.SIMPLY_SUPPORTED
    assert progress.equation == ReactionEquation.ENTRY
    assert progress.uses_prior_decomposition is True
    assert progress.decomposed_load_indices == [0, 1]

    seen: list[ReactionEquation] = [progress.equation]
    while progress.equation != ReactionEquation.DONE:
        advance_reactions(progress)
        if progress.equation != seen[-1]:
            seen.append(progress.equation)

    assert seen == list(reactions_equation_sequence(ReactionBeamKind.SIMPLY_SUPPORTED))
    advance_reactions(progress)
    assert progress.equation == ReactionEquation.DONE


def test_enter_and_advance_cantilever_to_done():
    progress = enter_reactions(CANTILEVER)
    seen: list[ReactionEquation] = [progress.equation]
    while progress.equation != ReactionEquation.DONE:
        advance_reactions(progress)
        if progress.equation != seen[-1]:
            seen.append(progress.equation)
    assert seen == list(reactions_equation_sequence(ReactionBeamKind.CANTILEVER))


def test_jump_to_equation_only_within_sequence():
    progress = enter_reactions(SIMPLY)
    assert jump_to_reaction_equation(progress, ReactionEquation.SIGMA_MB) is not None
    assert progress.equation == ReactionEquation.SIGMA_MB
    assert jump_to_reaction_equation(progress, ReactionEquation.SIGMA_M_TIP) is None
    assert progress.equation == ReactionEquation.SIGMA_MB


def test_sigma_fx_screens_contain_ax_copy_simply_and_cantilever():
    for extracted in (SIMPLY, CANTILEVER):
        progress = enter_reactions(extracted)
        jump_to_reaction_equation(progress, ReactionEquation.SIGMA_FX)

        set_reaction_phase(progress, ReactionPhase.EXPLAIN)
        explain = build_current_screen_hebrew(progress)
        assert "Ax" in explain
        assert "ΣFx" in explain

        set_reaction_phase(progress, ReactionPhase.SOLUTION)
        solution = build_current_screen_hebrew(progress)
        assert "Ax = " in solution
        assert "t" in solution


def test_sigma_mb_ay_copy_only_for_simply_supported():
    progress = enter_reactions(SIMPLY)
    jump_to_reaction_equation(progress, ReactionEquation.SIGMA_MB)

    set_reaction_phase(progress, ReactionPhase.EXPLAIN)
    explain = build_current_screen_hebrew(progress)
    assert "ΣMB" in explain
    assert "Ay" in explain

    set_reaction_phase(progress, ReactionPhase.SOLUTION)
    solution = build_current_screen_hebrew(progress)
    assert "Ay =" in solution
    assert "=0" in solution

    # ריתום: אין ΣMB — אין מסך Ay
    cant = enter_reactions(CANTILEVER)
    assert jump_to_reaction_equation(cant, ReactionEquation.SIGMA_MB) is None
    jump_to_reaction_equation(cant, ReactionEquation.SIGMA_FX)
    fx_explain = build_current_screen_hebrew(cant)
    assert "Ax" in fx_explain


def test_sigma_ma_by_copy_only_for_simply_supported():
    progress = enter_reactions(SIMPLY)
    jump_to_reaction_equation(progress, ReactionEquation.SIGMA_MA)

    set_reaction_phase(progress, ReactionPhase.EXPLAIN)
    explain = build_current_screen_hebrew(progress)
    assert "ΣMA" in explain
    assert "By" in explain

    set_reaction_phase(progress, ReactionPhase.SOLUTION)
    solution = build_current_screen_hebrew(progress)
    assert "By =" in solution
    assert "=0" in solution


def test_sigma_ma_fixed_and_m_tip_copy_only_for_cantilever():
    progress = enter_reactions(CANTILEVER)

    jump_to_reaction_equation(progress, ReactionEquation.SIGMA_MA_FIXED)
    set_reaction_phase(progress, ReactionPhase.EXPLAIN)
    ma_explain = build_current_screen_hebrew(progress)
    assert "Ma" in ma_explain
    set_reaction_phase(progress, ReactionPhase.SOLUTION)
    ma_solution = build_current_screen_hebrew(progress)
    assert "Ma =" in ma_solution

    jump_to_reaction_equation(progress, ReactionEquation.SIGMA_M_TIP)
    set_reaction_phase(progress, ReactionPhase.EXPLAIN)
    ay_explain = build_current_screen_hebrew(progress)
    assert "Ay" in ay_explain
    set_reaction_phase(progress, ReactionPhase.SOLUTION)
    ay_solution = build_current_screen_hebrew(progress)
    assert "Ay =" in ay_solution

    # 2 סמכים: אין ΣMa (בריתום) ואין ΣM בקצה הרחוק
    simply = enter_reactions(SIMPLY)
    assert jump_to_reaction_equation(simply, ReactionEquation.SIGMA_MA_FIXED) is None
    assert jump_to_reaction_equation(simply, ReactionEquation.SIGMA_M_TIP) is None


def test_cantilever_has_ax_not_ay_in_sequence_screens():
    progress = enter_reactions(CANTILEVER)
    advance_reactions(progress)  # FX
    text = build_current_screen_hebrew(progress)
    assert "Ax" in text
    assert reactions_screen_id(progress).endswith("sigma_fx:explain")


def test_screen_id_includes_phase():
    progress = enter_reactions(SIMPLY)
    advance_reactions(progress)  # FX
    assert reactions_screen_id(progress) == "reactions:simply_supported:sigma_fx:explain"
    text = build_current_screen_hebrew(progress)
    assert "Ax" in text


def test_advance_reactions_steps_through_both_phases_before_next_equation():
    progress = enter_reactions(SIMPLY)
    advance_reactions(progress)  # ENTRY -> SIGMA_FX (EXPLAIN)
    assert progress.equation == ReactionEquation.SIGMA_FX
    assert progress.phase == ReactionPhase.EXPLAIN

    advance_reactions(progress)  # SIGMA_FX EXPLAIN -> SOLUTION (same equation)
    assert progress.equation == ReactionEquation.SIGMA_FX
    assert progress.phase == ReactionPhase.SOLUTION

    advance_reactions(progress)  # SIGMA_FX SOLUTION -> SIGMA_MB (EXPLAIN)
    assert progress.equation == ReactionEquation.SIGMA_MB
    assert progress.phase == ReactionPhase.EXPLAIN


def test_flow_decomposition_to_reactions_and_enter_after_done():
    assert next_step_after(AssistantStepId.DECOMPOSITION) == AssistantStepId.REACTIONS
    assert next_step_after(AssistantStepId.REACTIONS) is None

    decomp = enter_decomposition(SIMPLY)
    assert enter_reactions_after_decomposition(decomp) is None
    from personal_assistant.decomposition import advance_decomposition

    while decomp.state != DecompositionState.DONE:
        advance_decomposition(decomp)
    reactions = enter_reactions_after_decomposition(decomp)
    assert reactions is not None
    assert reactions.beam_kind == ReactionBeamKind.SIMPLY_SUPPORTED
    assert reactions.decomposed_load_indices == decomp.load_indices
