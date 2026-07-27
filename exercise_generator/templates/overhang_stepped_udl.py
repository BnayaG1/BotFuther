# -*- coding: utf-8 -*-
"""תבנית נעולה: שני סמכים + זיזים + עומס מפורס מדורג (2 מפלסים)."""
from __future__ import annotations

import random

from exercise_generator.geometry import row_from_breaks
from exercise_generator.randomize import make_rng, random_point_spacings
from exercise_generator.schema import (
    DistributedLoad,
    Exercise,
    LabeledPoint,
    Support,
)

FAMILY_ID = "overhang_stepped_udl"


def build_example(
    *,
    seed: int | None = None,
    rng: random.Random | None = None,
) -> Exercise:
    r = rng if rng is not None else make_rng(seed)
    # 4 מרווחים: שמאל→A, A→C, C→B, B→ימין — כל מרווח לפי חוק 80/20
    (left_oh, a_to_c, c_to_b, right_oh), L = random_point_spacings(r, n_segments=4)
    xa = left_oh
    xc = left_oh + a_to_c
    xb = left_oh + a_to_c + c_to_b
    return Exercise(
        L=L,
        support_mode="simply_supported",
        supports=[
            Support("A", "pin", xa),
            Support("B", "roller", xb),
        ],
        loads=[
            DistributedLoad(x1=0.0, x2=xc, w=4.0),
            DistributedLoad(x1=xc, x2=L, w=3.0),
        ],
        labeled_points=[LabeledPoint("C", xc)],
        dim_row_top=row_from_breaks([0.0, xa, xc, xb, L]),
        dim_row_bottom=row_from_breaks([0.0, xa, xb, L]),
        family=FAMILY_ID,
        seed=seed,
    )
