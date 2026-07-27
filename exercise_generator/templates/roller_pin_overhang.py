# -*- coding: utf-8 -*-
"""משפחה 3: גליל משמאל + צמד פנימי + זיז ימני."""
from __future__ import annotations

from exercise_generator.geometry import row_from_breaks
from exercise_generator.schema import (
    DistributedLoad,
    Exercise,
    LabeledPoint,
    PointLoad,
    Support,
)

FAMILY_ID = "roller_pin_overhang"


def build_example(*, seed: int | None = None) -> Exercise:
    # ממדים בדוגמה היו בס"מ יחסית — כאן במטרים ביחס דומה: 1.6+0.5+1.3+1.2=4.6
    # ננרמל לערכים נוחים: 1.6, 0.5, 1.3, 1.2 → L=4.6
    # למען קריאות שרטוט נשתמש ב־160→1.6 כפול 10? הדוגמה: 160,50,130,120
    # נשמור יחס במטרים חלקי 100: 1.6, 0.5, 1.3, 1.2 — קצר מדי.
    # נשתמש במטרים ישירים מהמספרים/100*10 = 1.6*10? נשתמש: 1.60, 0.50, 1.30, 1.20 → scale ×10:
    d1, d2, d3, d4 = 1.6, 0.5, 1.3, 1.2
    # scale for nicer drawing
    s = 10.0
    d1, d2, d3, d4 = d1 * s, d2 * s, d3 * s, d4 * s
    L = d1 + d2 + d3 + d4
    x_p1 = d1
    x_p2 = d1 + d2
    xb = d1 + d2 + d3
    return Exercise(
        L=L,
        support_mode="simply_supported",
        supports=[
            Support("A", "roller", 0.0),
            Support("B", "pin", xb),
        ],
        loads=[
            DistributedLoad(x1=0.0, x2=x_p1, w=0.6),
            PointLoad(x=x_p1, Fy=1.2),
            PointLoad(x=x_p2, Fy=1.3),
            DistributedLoad(x1=xb, x2=L, w=0.9),
        ],
        labeled_points=[LabeledPoint("C", L)],
        dim_row_top=row_from_breaks([0.0, x_p1, x_p2, xb, L]),
        dim_row_bottom=row_from_breaks([0.0, xb, L]),
        family=FAMILY_ID,
        seed=seed,
    )
