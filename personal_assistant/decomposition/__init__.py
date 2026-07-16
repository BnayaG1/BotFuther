# -*- coding: utf-8 -*-
"""שלב פרוק עומסים בעייתיים — הסבר → פתרון לפי כמות עומסים."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

from bot.draft_format import (
    _fmt_num,
    _inclined_dir,
    _inclined_mag,
    distributed_span_from_left,
)

_DECOMPOSE_TYPES = frozenset({"distributed", "inclined"})


class DecompositionState(str, Enum):
    ACTIVE = "active"
    DONE = "done"  # אין עומסים / סיימנו את כל העומסים (לפני מעבר לריאקציות)


@dataclass
class DecompositionProgress:
    """מצב שלב הפרוק בעוזר האישי."""

    extracted: dict = field(default_factory=dict)
    load_indices: list[int] = field(default_factory=list)
    load_cursor: int = 0
    state: DecompositionState = DecompositionState.ACTIVE

    @property
    def load_count(self) -> int:
        return len(self.load_indices)

    @property
    def has_more_loads(self) -> bool:
        return self.load_cursor + 1 < len(self.load_indices)

    @property
    def is_skip(self) -> bool:
        """אין עומסים בעייתיים — מסך דילוג בלבד."""
        return self.load_count == 0


def _beam_from_extracted(extracted: dict) -> dict:
    beam = extracted.get("beam") if isinstance(extracted, dict) else None
    return beam if isinstance(beam, dict) else {}


def _load_left_x(ld: dict, beam: dict) -> float:
    t = str(ld.get("type", "")).lower()
    if t == "distributed":
        x1, x2 = distributed_span_from_left(ld, beam)
        return min(float(x1), float(x2))
    try:
        return float(ld.get("x", ld.get("x1", 0.0)) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def decomposition_load_entries(extracted: dict) -> list[tuple[int, dict]]:
    """עומסים לפרוק — ממוינים משמאל לימין על הקורה."""
    beam = _beam_from_extracted(extracted)
    loads = beam.get("loads") or []
    entries: list[tuple[int, dict]] = []
    if not isinstance(loads, list):
        return entries
    for idx, ld in enumerate(loads):
        if not isinstance(ld, dict):
            continue
        if str(ld.get("type", "")).lower() not in _DECOMPOSE_TYPES:
            continue
        entries.append((idx, ld))
    entries.sort(key=lambda item: _load_left_x(item[1], beam))
    return entries


def _decomposition_load_type_label_hebrew(ld: dict) -> str:
    t = str(ld.get("type", "")).lower()
    if t == "distributed":
        return "מפורס"
    if t == "inclined":
        return "אלכסוני"
    return "עומס"


def _load_summary_hebrew(ld: dict, beam: dict) -> str:
    t = str(ld.get("type", "")).lower()
    if t == "inclined":
        x = _fmt_num(float(ld.get("x", 0.0)))
        mag = _fmt_num(_inclined_mag(ld))
        angle = _fmt_num(float(ld.get("angle_deg", 30.0) or 30.0))
        dir_he = "שמאלה-מטה" if _inclined_dir(ld) == "dl" else "ימינה-מטה"
        return f"עומס אלכסוני {mag} טון, {angle} מעלות, {dir_he}, ב-x={x} מ'"
    if t == "distributed":
        x1, x2 = distributed_span_from_left(ld, beam)
        w = float(ld.get("w", ld.get("q", ld.get("magnitude", 0.0))) or 0.0)
        return (
            f"עומס מפורס, {_fmt_num(abs(w))} טון/מ', "
            f"מ-x={_fmt_num(x1)} עד x={_fmt_num(x2)} מ'"
        )
    return "עומס"


def current_load(progress: DecompositionProgress) -> dict:
    beam = _beam_from_extracted(progress.extracted)
    loads = beam.get("loads") or []
    if not progress.load_indices:
        return {}
    if progress.load_cursor < 0 or progress.load_cursor >= len(progress.load_indices):
        return {}
    load_idx = progress.load_indices[progress.load_cursor]
    if not isinstance(loads, list) or load_idx < 0 or load_idx >= len(loads):
        return {}
    ld = loads[load_idx]
    return ld if isinstance(ld, dict) else {}


def _distributed_equivalent_force_ton(ld: dict, beam: dict) -> tuple[float, float]:
    x1, x2 = distributed_span_from_left(ld, beam)
    w = float(ld.get("w", ld.get("q", ld.get("magnitude", 0.0))) or 0.0)
    length = abs(float(x2) - float(x1))
    return abs(float(w)), length


def explain_distributed_load_hebrew(ld: dict, beam: dict) -> str:
    w_abs, length = _distributed_equivalent_force_ton(ld, beam)
    w_txt = _fmt_num(w_abs)
    length_txt = _fmt_num(length)
    return f"הכח השקול = {w_txt} × {length_txt}"


def explain_inclined_load_hebrew(ld: dict) -> str:
    mag = float(_inclined_mag(ld))
    angle = float(ld.get("angle_deg", 30.0) or 30.0)
    mag_txt = _fmt_num(mag)
    angle_txt = _fmt_num(angle)
    return (
        "בשביל שנוכל למצוא את הריאקציות בהמשך, אנחנו נצטרך לפרק את העומס הזה "
        "מאלכסוני, ל2 כוחות שונים שאחד יהיה אנכי לציר(או למעלה או למטה), "
        "ואחד צירי(או ימינה או שמאלה).\n\n"
        f"Fx = {mag_txt} × cos({angle_txt}°)\n"
        f"Fy = {mag_txt} × sin({angle_txt}°)"
    )


def solution_distributed_load_hebrew(ld: dict, beam: dict) -> str:
    w_abs, length = _distributed_equivalent_force_ton(ld, beam)
    force_txt = _fmt_num(w_abs * length)
    return f"והתוצאה - {force_txt}t"


def solution_inclined_load_hebrew(ld: dict) -> str:
    mag = float(_inclined_mag(ld))
    angle = float(ld.get("angle_deg", 30.0) or 30.0)
    fx = abs(mag * math.cos(math.radians(angle)))
    fy = abs(mag * math.sin(math.radians(angle)))
    dir_key = _inclined_dir(ld)
    fx_dir = "ימינה" if dir_key == "dr" else "שמאלה"
    return (
        f"Fx = {_fmt_num(fx)}t ({fx_dir})\n"
        f"Fy = {_fmt_num(fy)}t (מטה)"
    )


def _count_prefix_hebrew(progress: DecompositionProgress) -> str:
    n = progress.load_count
    if n <= 0:
        return ""
    if n == 1:
        return "יש עומס בעייתי אחד בתרגיל."
    if progress.load_cursor == 0:
        return (
            f"יש {n} עומסים בעייתיים בתרגיל. "
            "נתחיל בעומס הראשון משמאל."
        )
    return (
        f"עברנו לעומס הבא ({progress.load_cursor + 1} מתוך {n})."
    )


def build_skip_decomposition_hebrew() -> str:
    return (
        "בתרגיל הזה אין עומסים מפורסים או אלכסוניים לפרוק.\n"
        "אפשר להמשיך לשלב מציאת הריאקציות."
    )


def build_load_screen_hebrew(progress: DecompositionProgress) -> str:
    """מסך אחד לעומס — הסבר ופתרון יחד."""
    beam = _beam_from_extracted(progress.extracted)
    ld = current_load(progress)
    label = _decomposition_load_type_label_hebrew(ld)
    t = str(ld.get("type", "")).lower()
    if t == "distributed":
        explain_body = explain_distributed_load_hebrew(ld, beam)
        solution_body = solution_distributed_load_hebrew(ld, beam)
    elif t == "inclined":
        explain_body = explain_inclined_load_hebrew(ld)
        solution_body = solution_inclined_load_hebrew(ld)
    else:
        explain_body = "עדיין אין הסבר לעומס הזה."
        solution_body = "אין פתרון להצגה לעומס הזה."

    prefix = _count_prefix_hebrew(progress)
    lines = [
        prefix,
        "",
        f"העומס הנוכחי הוא {label}.",
        _load_summary_hebrew(ld, beam),
        "",
        explain_body,
        "",
        solution_body,
    ]
    return "\n".join(line for line in lines if line is not None)


def enter_decomposition(extracted: dict) -> DecompositionProgress:
    """כניסה לשלב הפרוק."""
    entries = decomposition_load_entries(extracted)
    indices = [idx for idx, _ in entries]
    if not indices:
        return DecompositionProgress(
            extracted=extracted if isinstance(extracted, dict) else {},
            load_indices=[],
            load_cursor=0,
            state=DecompositionState.DONE,
        )
    return DecompositionProgress(
        extracted=extracted if isinstance(extracted, dict) else {},
        load_indices=indices,
        load_cursor=0,
        state=DecompositionState.ACTIVE,
    )


def decomposition_screen_id(progress: DecompositionProgress) -> str:
    return f"decomposition:{progress.state.value}:cursor={progress.load_cursor}"


def build_decomposition_screen_hebrew(
    progress: DecompositionProgress, *, prefix: str = ""
) -> str:
    del prefix  # לא בשימוש בזרימה החדשה
    if progress.is_skip or (
        progress.state == DecompositionState.DONE and progress.load_count == 0
    ):
        return build_skip_decomposition_hebrew()
    return build_load_screen_hebrew(progress)


def advance_decomposition(progress: DecompositionProgress) -> DecompositionProgress:
    """מעבר לעומס הבא או ל-DONE. בדילוג / DONE נשארים."""
    if progress.is_skip or progress.state == DecompositionState.DONE:
        progress.state = DecompositionState.DONE
        return progress

    if progress.has_more_loads:
        progress.load_cursor += 1
        progress.state = DecompositionState.ACTIVE
        return progress

    progress.state = DecompositionState.DONE
    return progress


def next_action_goes_to_reactions(progress: DecompositionProgress) -> bool:
    """האם «המשך» מהמסך הנוכחי מעביר לריאקציות."""
    if progress.is_skip:
        return True
    if not progress.has_more_loads:
        return True
    if progress.state == DecompositionState.DONE:
        return True
    return False
