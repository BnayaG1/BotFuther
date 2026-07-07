# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any

import matplotlib.pyplot as plt
from matplotlib.patches import Polygon

from notebook.constants import _INK


def _draw_support_triangle(
    ax: Any, x: float, *, tri_h: float, tri_w: float, support_lw: float
) -> float:
    """משולש סגור (קודקוד על הקורה y=0). מחזיר y של הבסיס."""
    y_base = -tri_h
    ax.add_patch(
        Polygon(
            [(x - tri_w, y_base), (x, 0.0), (x + tri_w, y_base)],
            closed=True,
            fill=False,
            edgecolor=_INK,
            linewidth=support_lw,
            joinstyle="round",
            zorder=4,
        )
    )
    return y_base


def _draw_pin_support(
    ax: Any,
    x: float,
    *,
    tri_h: float,
    tri_w: float,
    support_lw: float,
    pin_hatch_len: float,
    pin_hatch_lean: float,
    pin_hatch_lw: float,
) -> None:
    """סמך שמאל (ציר): 5 קווי קרקע — לאורך הבסיס, נוטים שמאלה."""
    y_base = _draw_support_triangle(
        ax, x, tri_h=tri_h, tri_w=tri_w, support_lw=support_lw
    )
    y_ground = y_base - pin_hatch_len
    for xa in (
        x + tri_w,
        x + tri_w * 0.5,
        x,
        x - tri_w * 0.5,
        x - tri_w,
    ):
        (ln,) = ax.plot(
            [xa - pin_hatch_lean, xa],
            [y_ground, y_base],
            color=_INK,
            linewidth=pin_hatch_lw,
            solid_capstyle="round",
            zorder=5,
        )
        ln.set_clip_on(False)


def _draw_roller_support(
    ax: Any,
    x: float,
    *,
    tri_h: float,
    tri_w: float,
    support_lw: float,
    roller_circle_r: float,
    roller_circle_lw: float,
) -> None:
    """סמך ימין (גלגל): שני עיגולים מתחת לפינות המשולש."""
    y_base = _draw_support_triangle(
        ax, x, tri_h=tri_h, tri_w=tri_w, support_lw=support_lw
    )
    r = roller_circle_r
    for xa in (x - tri_w, x + tri_w):
        circ = plt.Circle(
            (xa, y_base - r),
            r,
            fill=False,
            edgecolor=_INK,
            linewidth=roller_circle_lw,
            zorder=6,
        )
        circ.set_clip_on(False)
        ax.add_patch(circ)

