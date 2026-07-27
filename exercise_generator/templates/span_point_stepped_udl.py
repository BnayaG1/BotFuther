# -*- coding: utf-8 -*-
"""משפחה 2: A–B + כוח מרוכז + עומס מפורס מדורג (3 מפלסים)."""
from __future__ import annotations

from exercise_generator.geometry import row_from_breaks
from exercise_generator.schema import (
    DistributedLoad,
    Exercise,
    LabeledPoint,
    PointLoad,
    Support,
)

FAMILY_ID = "span_point_stepped_udl"


def build_example(*, seed: int | None = None) -> Exercise:
    # 3+4+4+4 = 15; point@3, C@7, D@11, B@15
    L = 15.0
    xp, xc, xd = 3.0, 7.0, 11.0
    return Exercise(
        L=L,
        support_mode="simply_supported",
        supports=[
            Support("A", "pin", 0.0),
            Support("B", "roller", L),
        ],
        loads=[
            PointLoad(x=xp, Fy=10.0),
            DistributedLoad(x1=0.0, x2=xc, w=3.0),
            DistributedLoad(x1=xc, x2=xd, w=2.0),
            DistributedLoad(x1=xd, x2=L, w=1.0),
        ],
        labeled_points=[
            LabeledPoint("C", xc),
            LabeledPoint("D", xd),
        ],
        dim_row_top=row_from_breaks([0.0, xp, xc, xd, L]),
        dim_row_bottom=row_from_breaks([0.0, L]),
        family=FAMILY_ID,
        seed=seed,
    )
