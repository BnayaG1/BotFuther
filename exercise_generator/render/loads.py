# -*- coding: utf-8 -*-
from __future__ import annotations

import math

from matplotlib.patches import FancyArrow, FancyBboxPatch

from exercise_generator.render.canvas import Canvas
from exercise_generator.render import style
from exercise_generator.schema import (
    DistributedLoad,
    InclinedLoad,
    LoadItem,
    MomentLoad,
    PointLoad,
)
from exercise_generator.units import format_force_hebrew, format_moment_hebrew, format_udl_hebrew


def draw_loads(canvas: Canvas, loads: list[LoadItem]) -> None:
    # UDL קודם (מאחורי חצים מרוכזים)
    for ld in loads:
        if isinstance(ld, DistributedLoad):
            _draw_udl(canvas, ld)
    for ld in loads:
        if isinstance(ld, PointLoad):
            _draw_point(canvas, ld)
        elif isinstance(ld, InclinedLoad):
            _draw_inclined(canvas, ld)
        elif isinstance(ld, MomentLoad):
            _draw_moment(canvas, ld)


def _udl_height(w: float, w_ref: float = 4.0) -> float:
    return style.UDL_BASE_HEIGHT * max(0.35, min(1.6, abs(w) / w_ref))


def _draw_udl(canvas: Canvas, ld: DistributedLoad) -> None:
    ax = canvas.ax
    x1, x2 = float(ld.x1), float(ld.x2)
    if x2 <= x1:
        return
    h = _udl_height(ld.w)
    y0 = canvas.y_beam + style.BEAM_HEIGHT / 2 + 0.08
    ax.add_patch(
        FancyBboxPatch(
            (x1, y0),
            x2 - x1,
            h,
            boxstyle="square,pad=0",
            linewidth=style.LINE_WIDTH,
            edgecolor="black",
            facecolor="none",
            zorder=5,
        )
    )
    n = max(3, int((x2 - x1) / max(canvas.L * 0.04, 0.35)))
    for i in range(n + 1):
        t = i / n
        x = x1 + t * (x2 - x1)
        ax.annotate(
            "",
            xy=(x, y0),
            xytext=(x, y0 + h),
            arrowprops=dict(arrowstyle="->", color="black", lw=1.0),
            zorder=6,
        )
    mid = 0.5 * (x1 + x2)
    ax.text(
        mid,
        y0 + h + 0.15,
        format_udl_hebrew(ld.w),
        ha="center",
        va="bottom",
        fontsize=8,
        linespacing=1.1,
        zorder=7,
    )


def _draw_point(canvas: Canvas, ld: PointLoad) -> None:
    ax = canvas.ax
    x = float(ld.x)
    y0 = canvas.y_beam + style.BEAM_HEIGHT / 2 + 0.05
    length = style.POINT_ARROW_LEN
    ax.annotate(
        "",
        xy=(x, y0),
        xytext=(x, y0 + length),
        arrowprops=dict(arrowstyle="-|>", color="black", lw=2.0, mutation_scale=14),
        zorder=8,
    )
    ax.text(
        x + 0.15,
        y0 + length * 0.55,
        format_force_hebrew(abs(ld.Fy)),
        ha="left",
        va="center",
        fontsize=8,
        linespacing=1.1,
        zorder=8,
    )


def _draw_inclined(canvas: Canvas, ld: InclinedLoad) -> None:
    ax = canvas.ax
    x = float(ld.x)
    y0 = canvas.y_beam + style.BEAM_HEIGHT / 2 + 0.05
    ang = math.radians(float(ld.angle_deg))
    length = style.POINT_ARROW_LEN * 1.15
    # dr = down-right: tip at beam, tail up-left
    sign = 1.0 if ld.incl_dir == "dr" else -1.0
    dx = sign * length * math.cos(ang)
    dy = length * math.sin(ang)
    ax.annotate(
        "",
        xy=(x, y0),
        xytext=(x - dx, y0 + dy),
        arrowprops=dict(arrowstyle="-|>", color="black", lw=2.0, mutation_scale=14),
        zorder=8,
    )
    ax.text(
        x - dx * 0.35 + 0.2,
        y0 + dy * 0.7,
        format_force_hebrew(ld.magnitude_ton) + f"\n{ld.angle_deg:g}°",
        ha="left",
        va="bottom",
        fontsize=8,
        linespacing=1.1,
        zorder=8,
    )


def _draw_moment(canvas: Canvas, ld: MomentLoad) -> None:
    ax = canvas.ax
    x = float(ld.x)
    y = canvas.y_beam
    r = style.MOMENT_RADIUS
    # קשת עם חץ — בכיוון השעון אם M>0
    theta1, theta2 = 40, 320
    import numpy as np

    ts = np.linspace(math.radians(theta1), math.radians(theta2), 60)
    xs = x + r * np.cos(ts)
    ys = y + r * np.sin(ts)
    ax.plot(xs, ys, color="black", lw=style.LINE_WIDTH, zorder=8)
    # חץ בקצה
    t_end = ts[-1]
    ax.annotate(
        "",
        xy=(x + r * math.cos(t_end), y + r * math.sin(t_end)),
        xytext=(
            x + r * math.cos(t_end - 0.35),
            y + r * math.sin(t_end - 0.35),
        ),
        arrowprops=dict(arrowstyle="-|>", color="black", lw=1.5, mutation_scale=12),
        zorder=9,
    )
    ax.text(
        x + r + 0.15,
        y + 0.2,
        format_moment_hebrew(abs(ld.M)),
        ha="left",
        va="bottom",
        fontsize=8,
        linespacing=1.1,
        zorder=9,
    )
