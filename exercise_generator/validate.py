# -*- coding: utf-8 -*-
"""ולידציה מבנית מינימלית — בלי מדיניות הנדסית מלאה."""
from __future__ import annotations

from exercise_generator.schema import DistributedLoad, Exercise, InclinedLoad, MomentLoad, PointLoad


def validate_exercise(exercise: Exercise) -> list[str]:
    errors: list[str] = []
    if exercise.L <= 0:
        errors.append("L must be positive")

    xs_supports = [s.x for s in exercise.supports]
    if len(xs_supports) != len(set(round(x, 6) for x in xs_supports)):
        errors.append("duplicate support positions")

    for s in exercise.supports:
        if s.x < -1e-9 or s.x > exercise.L + 1e-9:
            errors.append(f"support {s.label} x={s.x} outside [0, L]")

    for ld in exercise.loads:
        if isinstance(ld, DistributedLoad):
            if ld.x2 <= ld.x1:
                errors.append(f"distributed end<=start ({ld.x1}, {ld.x2})")
            if ld.x1 < -1e-9 or ld.x2 > exercise.L + 1e-9:
                errors.append("distributed span outside beam")
        elif isinstance(ld, (PointLoad, InclinedLoad, MomentLoad)):
            x = float(getattr(ld, "x", 0.0))
            if x < -1e-9 or x > exercise.L + 1e-9:
                errors.append(f"load x={x} outside beam")

    if exercise.dim_row_top.segments:
        span = sum(abs(s.x2 - s.x1) for s in exercise.dim_row_top.segments)
        if abs(span - exercise.L) > 1e-4:
            errors.append(f"top dimensions span {span:g} != L={exercise.L:g}")

    return errors


def require_valid(exercise: Exercise) -> None:
    errs = validate_exercise(exercise)
    if errs:
        raise ValueError("; ".join(errs))
