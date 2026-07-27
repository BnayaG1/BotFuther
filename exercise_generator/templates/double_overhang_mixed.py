# -*- coding: utf-8 -*-
"""משפחה 4: זיזים C–A…B–D + כוחות ומפורסים."""
from __future__ import annotations

from exercise_generator.geometry import row_from_breaks
from exercise_generator.schema import (
    DistributedLoad,
    Exercise,
    LabeledPoint,
    PointLoad,
    Support,
)

FAMILY_ID = "double_overhang_mixed"


def build_example(*, seed: int | None = None) -> Exercise:
    # דוגמה: 150, 320, 160, 160 — נחלק ב־100 → מטרים: 1.5, 3.2, 1.6, 1.6 → ×10
    s = 10.0
    c_to_a, a_to_p, p_to_b, b_to_d = 1.5 * s, 3.2 * s, 1.6 * s, 1.6 * s
    L = c_to_a + a_to_p + p_to_b + b_to_d
    xa = c_to_a
    xp = c_to_a + a_to_p
    xb = c_to_a + a_to_p + p_to_b
    return Exercise(
        L=L,
        support_mode="simply_supported",
        supports=[
            Support("A", "pin", xa),
            Support("B", "roller", xb),
        ],
        loads=[
            PointLoad(x=0.0, Fy=12.0),
            DistributedLoad(x1=xa, x2=xp, w=4.5),
            PointLoad(x=xp, Fy=13.5),
            DistributedLoad(x1=xb, x2=L, w=3.6),
        ],
        labeled_points=[
            LabeledPoint("C", 0.0),
            LabeledPoint("D", L),
        ],
        dim_row_top=row_from_breaks([0.0, xa, xp, xb, L]),
        dim_row_bottom=row_from_breaks([0.0, xa, xb, L]),
        family=FAMILY_ID,
        seed=seed,
    )
