# -*- coding: utf-8 -*-
"""עזרי גיאומטריה — מקטעים, נקודות מידה, L."""
from __future__ import annotations

from exercise_generator.schema import DimensionRow, DimensionSegment, Exercise


def total_length_from_segments(segments: list[tuple[float, float]]) -> float:
    """segments כ־(x1, x2) ממוינים."""
    if not segments:
        return 0.0
    return float(max(x2 for _x1, x2 in segments) - min(x1 for x1, _x2 in segments))


def row_from_breaks(breaks: list[float]) -> DimensionRow:
    """בונה שורת מידות מנקודות שבירה ממוינות."""
    pts = sorted(float(x) for x in breaks)
    segs: list[DimensionSegment] = []
    for i in range(len(pts) - 1):
        segs.append(DimensionSegment(x1=pts[i], x2=pts[i + 1]))
    return DimensionRow(segments=segs)


def assert_length_matches(exercise: Exercise, tol: float = 1e-6) -> None:
    if exercise.dim_row_top.segments:
        span = sum(abs(s.x2 - s.x1) for s in exercise.dim_row_top.segments)
        if abs(span - exercise.L) > tol:
            raise ValueError(
                f"Top dimension span {span:g} != L={exercise.L:g}"
            )
