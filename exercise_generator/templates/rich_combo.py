# -*- coding: utf-8 -*-
"""משפחה 5: אלכסוני + מפורס + מרוכז + מומנט + נקודות מתויגות."""
from __future__ import annotations

from exercise_generator.geometry import row_from_breaks
from exercise_generator.schema import (
    DistributedLoad,
    Exercise,
    InclinedLoad,
    LabeledPoint,
    MomentLoad,
    PointLoad,
    Support,
)

FAMILY_ID = "rich_combo"


def build_example(*, seed: int | None = None) -> Exercise:
    # 4.2 + 4.0 + 4.0 + 2.0 + 2.0 = 16.2
    c_to_a, a_to_d, d_to_e, e_to_f, f_to_b = 4.2, 4.0, 4.0, 2.0, 2.0
    L = c_to_a + a_to_d + d_to_e + e_to_f + f_to_b
    xa = c_to_a
    xd = c_to_a + a_to_d
    xe = xd + d_to_e
    xf = xe + e_to_f
    xb = L
    return Exercise(
        L=L,
        support_mode="simply_supported",
        supports=[
            Support("A", "pin", xa),
            Support("B", "roller", xb),
        ],
        loads=[
            InclinedLoad(x=0.0, magnitude_ton=10.0, angle_deg=30.0, incl_dir="dr"),
            DistributedLoad(x1=xa, x2=xe, w=3.0),
            PointLoad(x=xd, Fy=6.0),
            MomentLoad(x=xf, M=3.0),
        ],
        labeled_points=[
            LabeledPoint("C", 0.0),
            LabeledPoint("D", xd),
            LabeledPoint("E", xe),
            LabeledPoint("F", xf),
        ],
        dim_row_top=row_from_breaks([0.0, xa, xd, xe, xf, xb]),
        dim_row_bottom=row_from_breaks([0.0, xa, xb]),
        family=FAMILY_ID,
        seed=seed,
    )
