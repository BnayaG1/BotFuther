# -*- coding: utf-8 -*-
"""ולידציה מבנית מינימלית — בלי מדיניות הנדסית מלאה."""
from __future__ import annotations

from collections import defaultdict

from exercise_generator.randomize import MAX_LOADS_PER_POINT
from exercise_generator.schema import DistributedLoad, Exercise, InclinedLoad, MomentLoad, PointLoad


def _load_touch_xs(ld) -> list[float]:
    if isinstance(ld, DistributedLoad):
        return [float(ld.x1), float(ld.x2)]
    if isinstance(ld, (PointLoad, InclinedLoad, MomentLoad)):
        return [float(ld.x)]
    return []


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

    # לא יותר מ־MAX_LOADS_PER_POINT עומסים על אותה נקודה
    touches: dict[float, int] = defaultdict(int)
    for ld in exercise.loads:
        for x in _load_touch_xs(ld):
            touches[round(x, 6)] += 1
    for x, n in touches.items():
        if n > MAX_LOADS_PER_POINT:
            errors.append(
                f"too many loads at x={x:g} ({n} > {MAX_LOADS_PER_POINT})"
            )

    # מפורסים — משקלי t/m חייבים להיות שונים זה מזה
    udl_ws = [round(float(ld.w), 6) for ld in exercise.loads if isinstance(ld, DistributedLoad)]
    if len(udl_ws) != len(set(udl_ws)):
        errors.append("distributed loads must have distinct t/m weights")

    # תצורת סמכים מול ריתום
    types = [s.type for s in exercise.supports]
    if exercise.support_mode == "cantilever":
        if len(exercise.supports) != 1 or types != ["fixed"]:
            errors.append("cantilever requires exactly one fixed support")
    elif exercise.support_mode == "simply_supported":
        if sorted(types) != ["pin", "roller"]:
            errors.append("simply_supported requires pin and roller")

    if exercise.dim_row_top.segments:
        span = sum(abs(s.x2 - s.x1) for s in exercise.dim_row_top.segments)
        if abs(span - exercise.L) > 1e-4:
            errors.append(f"top dimensions span {span:g} != L={exercise.L:g}")

    return errors


def require_valid(exercise: Exercise) -> None:
    errs = validate_exercise(exercise)
    if errs:
        raise ValueError("; ".join(errs))
