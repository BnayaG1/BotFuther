# -*- coding: utf-8 -*-
"""פיצול עומס מפורס סביב נקודת מומנט לתצוגת חישוב (מחברת / מדריך)."""
from __future__ import annotations

from dataclasses import dataclass

# משפט קצר לפני שני חלקי המפורס — רק כשיש פיצול
UDL_SPLIT_ABOUT_PIVOT_HE = (
    "העומס המפורס הזה חוצה את הנקודה שסביבה המשוואה ולכן נחלק אותו ל2 - "
    "החלק שלפניה והחלק שאחריה."
)


@dataclass(frozen=True)
class DistributedMomentSegment:
    """מקטע מפורס אחרי פיצול (או מקטע בודד אם לא חוצה)."""

    x1: float
    x2: float
    force: float  # w * span (סימן לפי w)
    centroid: float
    arm: float  # centroid - x_ref
    dist: float  # |arm|


def distributed_crosses_pivot(x1: float, x2: float, x_ref: float, *, eps: float = 1e-9) -> bool:
    xa, xb = (float(x1), float(x2)) if float(x2) >= float(x1) else (float(x2), float(x1))
    xref = float(x_ref)
    return xa < xref - eps and xb > xref + eps


def distributed_moment_segments_about(
    w: float,
    x1: float,
    x2: float,
    x_ref: float,
    *,
    eps: float = 1e-9,
) -> list[DistributedMomentSegment]:
    """מחזיר מקטעי מפורס לחישוב מומנט סביב x_ref.

    אם המפורס חוצה את x_ref — שני מקטעים (לפני/אחרי); אחרת מקטע אחד.
    """
    xa = float(x1)
    xb = float(x2)
    if xb < xa:
        xa, xb = xb, xa
    span = xb - xa
    if abs(float(w)) < eps or span <= eps:
        return []
    xref = float(x_ref)

    def _one(seg_a: float, seg_b: float) -> DistributedMomentSegment | None:
        seg_span = seg_b - seg_a
        if seg_span <= eps:
            return None
        force = float(w) * seg_span
        centroid = 0.5 * (seg_a + seg_b)
        arm = centroid - xref
        return DistributedMomentSegment(
            x1=seg_a,
            x2=seg_b,
            force=force,
            centroid=centroid,
            arm=arm,
            dist=abs(arm),
        )

    if distributed_crosses_pivot(xa, xb, xref, eps=eps):
        left = _one(xa, xref)
        right = _one(xref, xb)
        return [s for s in (left, right) if s is not None]
    one = _one(xa, xb)
    return [one] if one is not None else []
