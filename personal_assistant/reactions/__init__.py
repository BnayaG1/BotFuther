# -*- coding: utf-8 -*-
"""שלב מציאת הריאקציות — מכונת מצבים; מנתב לתיקיית simply_supported/cantilever."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from personal_assistant.reactions.cantilever import sigma_fx as cantilever_sigma_fx
from personal_assistant.reactions.cantilever import sigma_ma as cantilever_sigma_ma
from personal_assistant.reactions.cantilever import (
    sigma_m_tip as cantilever_sigma_m_tip,
)
from personal_assistant.reactions.opening import build_reactions_opening_message_hebrew
from personal_assistant.reactions.simply_supported import sigma_fx as ss_sigma_fx
from personal_assistant.reactions.simply_supported import sigma_ma as ss_sigma_ma
from personal_assistant.reactions.simply_supported import sigma_mb as ss_sigma_mb


class ReactionBeamKind(str, Enum):
    """סוג תרגיל לשלב הריאקציות."""

    SIMPLY_SUPPORTED = "simply_supported"
    CANTILEVER = "cantilever"
    UNKNOWN = "unknown"


class ReactionEquation(str, Enum):
    """תת-מצבים / משוואות בתוך שלב הריאקציות."""

    ENTRY = "entry"
    SIGMA_FX = "sigma_fx"
    SIGMA_MB = "sigma_mb"
    SIGMA_MA = "sigma_ma"
    SIGMA_MA_FIXED = "sigma_ma_fixed"
    SIGMA_M_TIP = "sigma_m_tip"
    STABILITY_FY = "stability_fy"
    DONE = "done"


class ReactionPhase(str, Enum):
    """2 הודעות לכל משוואה: הסבר ספציפי לתרגיל, ואז פירוק+פתרון."""

    EXPLAIN = "explain"
    SOLUTION = "solution"


_SIMPLY_SUPPORTED_SEQUENCE: tuple[ReactionEquation, ...] = (
    ReactionEquation.ENTRY,
    ReactionEquation.SIGMA_FX,
    ReactionEquation.SIGMA_MB,
    ReactionEquation.SIGMA_MA,
    ReactionEquation.STABILITY_FY,
    ReactionEquation.DONE,
)

_CANTILEVER_SEQUENCE: tuple[ReactionEquation, ...] = (
    ReactionEquation.ENTRY,
    ReactionEquation.SIGMA_FX,
    ReactionEquation.SIGMA_MA_FIXED,
    ReactionEquation.SIGMA_M_TIP,
    ReactionEquation.STABILITY_FY,
    ReactionEquation.DONE,
)

_UNKNOWN_SEQUENCE: tuple[ReactionEquation, ...] = (
    ReactionEquation.ENTRY,
    ReactionEquation.DONE,
)

_EQUATION_LABEL_HE: dict[ReactionEquation, str] = {
    ReactionEquation.ENTRY: "כניסה לשלב הריאקציות",
    ReactionEquation.SIGMA_FX: "ΣFx",
    ReactionEquation.SIGMA_MB: "ΣMb",
    ReactionEquation.SIGMA_MA: "ΣMa",
    ReactionEquation.SIGMA_MA_FIXED: "ΣMa (בריתום)",
    ReactionEquation.SIGMA_M_TIP: "ΣM בקצה הרחוק מהריתום",
    ReactionEquation.STABILITY_FY: "בדיקת יציבות ΣFy",
    ReactionEquation.DONE: "סיום שלב הריאקציות",
}


@dataclass
class ReactionProgress:
    """מצב שלב הריאקציות בעוזר האישי."""

    beam_kind: ReactionBeamKind = ReactionBeamKind.UNKNOWN
    equation: ReactionEquation = ReactionEquation.ENTRY
    phase: ReactionPhase = ReactionPhase.EXPLAIN
    extracted: dict = field(default_factory=dict)
    decomposed_load_indices: list[int] = field(default_factory=list)

    @property
    def uses_prior_decomposition(self) -> bool:
        """השלב משתמש במה שכבר פורק — לא מריץ פירוק חדש."""
        return True


def detect_reaction_beam_kind(extracted: dict) -> ReactionBeamKind:
    """זיהוי 2 סמכים / ריתום מתוך extracted (גיאומטריית supports)."""
    beam = extracted.get("beam") if isinstance(extracted, dict) else None
    if not isinstance(beam, dict):
        return ReactionBeamKind.UNKNOWN

    mode = str(beam.get("support_mode", "")).lower().strip()
    if mode == "cantilever":
        return ReactionBeamKind.CANTILEVER
    if mode == "simply_supported":
        return ReactionBeamKind.SIMPLY_SUPPORTED

    supports = beam.get("supports")
    if not isinstance(supports, list) or not supports:
        return ReactionBeamKind.UNKNOWN

    types = {
        str(s.get("type", "")).lower().strip()
        for s in supports
        if isinstance(s, dict)
    }
    if "fixed" in types:
        return ReactionBeamKind.CANTILEVER
    if "pin" in types and "roller" in types:
        return ReactionBeamKind.SIMPLY_SUPPORTED
    if "pin" in types or "roller" in types:
        return ReactionBeamKind.SIMPLY_SUPPORTED
    return ReactionBeamKind.UNKNOWN


def reactions_equation_sequence(kind: ReactionBeamKind) -> tuple[ReactionEquation, ...]:
    """סדר המשוואות/מצבים לפי סוג התרגיל."""
    if kind == ReactionBeamKind.SIMPLY_SUPPORTED:
        return _SIMPLY_SUPPORTED_SEQUENCE
    if kind == ReactionBeamKind.CANTILEVER:
        return _CANTILEVER_SEQUENCE
    return _UNKNOWN_SEQUENCE


def enter_reactions(
    extracted: dict,
    *,
    decomposed_load_indices: list[int] | None = None,
) -> ReactionProgress:
    """כניסה לשלב: מזהה סוג תרגיל ומתחיל ב-ENTRY."""
    kind = detect_reaction_beam_kind(extracted)
    return ReactionProgress(
        beam_kind=kind,
        equation=ReactionEquation.ENTRY,
        phase=ReactionPhase.EXPLAIN,
        extracted=extracted if isinstance(extracted, dict) else {},
        decomposed_load_indices=list(decomposed_load_indices or []),
    )


def reactions_screen_id(progress: ReactionProgress) -> str:
    """מזהה מסך יציב למצב הנוכחי (לניווט / בדיקות)."""
    return (
        f"reactions:{progress.beam_kind.value}:"
        f"{progress.equation.value}:{progress.phase.value}"
    )


def equation_label_hebrew(equation: ReactionEquation) -> str:
    return _EQUATION_LABEL_HE.get(equation, equation.value)


def build_reactions_screen_placeholder(progress: ReactionProgress) -> str:
    """מסך שלד — תווית מבנית בלבד כשאין עדיין נוסח מלא."""
    kind_he = {
        ReactionBeamKind.SIMPLY_SUPPORTED: "2 סמכים",
        ReactionBeamKind.CANTILEVER: "ריתום",
        ReactionBeamKind.UNKNOWN: "לא מזוהה",
    }.get(progress.beam_kind, progress.beam_kind.value)
    label = equation_label_hebrew(progress.equation)
    return (
        f"[reactions_v2] סוג: {kind_he} | מצב: {label} "
        f"({reactions_screen_id(progress)})"
    )


def set_reaction_phase(
    progress: ReactionProgress, phase: ReactionPhase
) -> ReactionProgress:
    progress.phase = phase
    return progress


def _build_entry_step_hebrew(progress: ReactionProgress) -> str:
    had_decomposition = bool(progress.decomposed_load_indices)
    return build_reactions_opening_message_hebrew(
        beam_kind=progress.beam_kind.value,
        had_decomposition=had_decomposition,
    )


def build_reactions_screen_hebrew(
    progress: ReactionProgress,
    *,
    phase: ReactionPhase | None = None,
    prefix: str = "",
) -> str:
    """נוסח אמיתי ל-ΣFx / ΣMb כשיש; אחרת placeholder."""
    active = phase if phase is not None else progress.phase
    eq = progress.equation
    extracted = progress.extracted

    if eq == ReactionEquation.ENTRY:
        return _build_entry_step_hebrew(progress)

    if eq == ReactionEquation.SIGMA_FX:
        module = (
            cantilever_sigma_fx
            if progress.beam_kind == ReactionBeamKind.CANTILEVER
            else ss_sigma_fx
        )
        if active == ReactionPhase.EXPLAIN:
            return module.build_ax_explain_hebrew(extracted, prefix=prefix)
        return module.build_ax_solution_hebrew(extracted)

    if eq == ReactionEquation.SIGMA_MB:
        if progress.beam_kind != ReactionBeamKind.SIMPLY_SUPPORTED:
            return build_reactions_screen_placeholder(progress)
        if active == ReactionPhase.EXPLAIN:
            return ss_sigma_mb.build_ay_mb_equation_message_hebrew(
                extracted, prefix=prefix
            )
        return ss_sigma_mb.build_ay_mb_assembled_equation_hebrew(extracted)

    if eq == ReactionEquation.SIGMA_MA:
        if progress.beam_kind != ReactionBeamKind.SIMPLY_SUPPORTED:
            return build_reactions_screen_placeholder(progress)
        if active == ReactionPhase.EXPLAIN:
            return ss_sigma_ma.build_by_ma_equation_message_hebrew(
                extracted, prefix=prefix
            )
        return ss_sigma_ma.build_by_ma_assembled_equation_hebrew(extracted)

    if eq == ReactionEquation.SIGMA_MA_FIXED:
        if progress.beam_kind != ReactionBeamKind.CANTILEVER:
            return build_reactions_screen_placeholder(progress)
        if active == ReactionPhase.EXPLAIN:
            return cantilever_sigma_ma.build_ma_equation_message_hebrew(
                extracted, prefix=prefix
            )
        return cantilever_sigma_ma.build_ma_assembled_equation_hebrew(extracted)

    if eq == ReactionEquation.SIGMA_M_TIP:
        if progress.beam_kind != ReactionBeamKind.CANTILEVER:
            return build_reactions_screen_placeholder(progress)
        if active == ReactionPhase.EXPLAIN:
            return cantilever_sigma_m_tip.build_ay_tip_equation_message_hebrew(
                extracted, prefix=prefix
            )
        return cantilever_sigma_m_tip.build_ay_tip_assembled_equation_hebrew(extracted)

    return build_reactions_screen_placeholder(progress)


def advance_reactions(progress: ReactionProgress) -> ReactionProgress:
    """מעבר למסך הבא: מ-EXPLAIN ל-SOLUTION באותה משוואה, ואז למשוואה הבאה.

    הודעת הכניסה לשלב (ENTRY) היא הודעה בודדת — עוברים ממנה ישר למשוואה הבאה.
    """
    if progress.equation != ReactionEquation.ENTRY and progress.phase == ReactionPhase.EXPLAIN:
        progress.phase = ReactionPhase.SOLUTION
        return progress

    seq = reactions_equation_sequence(progress.beam_kind)
    try:
        idx = seq.index(progress.equation)
    except ValueError:
        progress.equation = seq[0]
        progress.phase = ReactionPhase.EXPLAIN
        return progress
    if idx + 1 >= len(seq):
        progress.equation = ReactionEquation.DONE
        progress.phase = ReactionPhase.EXPLAIN
        return progress
    progress.equation = seq[idx + 1]
    progress.phase = ReactionPhase.EXPLAIN
    return progress


def jump_to_reaction_equation(
    progress: ReactionProgress, equation: ReactionEquation
) -> ReactionProgress | None:
    """קפיצה למשוואה אם היא קיימת בסדר של סוג התרגיל."""
    seq = reactions_equation_sequence(progress.beam_kind)
    if equation not in seq:
        return None
    progress.equation = equation
    progress.phase = ReactionPhase.EXPLAIN
    return progress
