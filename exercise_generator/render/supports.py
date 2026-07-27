# -*- coding: utf-8 -*-
from __future__ import annotations

from matplotlib.patches import Circle, FancyArrow, Polygon, Rectangle

from exercise_generator.render.canvas import Canvas
from exercise_generator.render import style
from exercise_generator.schema import Support


def draw_supports(canvas: Canvas, supports: list[Support]) -> None:
    for s in supports:
        if s.type == "pin":
            _draw_pin(canvas, s.x)
        elif s.type == "roller":
            _draw_roller(canvas, s.x)
        elif s.type == "fixed":
            _draw_fixed(canvas, s.x)


def _draw_pin(canvas: Canvas, x: float) -> None:
    ax = canvas.ax
    s = style.SUPPORT_SIZE
    y_top = canvas.y_beam - style.BEAM_HEIGHT / 2
    tri = Polygon(
        [(x, y_top), (x - s * 0.55, y_top - s), (x + s * 0.55, y_top - s)],
        closed=True,
        fill=False,
        edgecolor="black",
        linewidth=style.LINE_WIDTH,
        zorder=4,
    )
    ax.add_patch(tri)
    base_y = y_top - s - 0.08
    ax.plot([x - s * 0.75, x + s * 0.75], [base_y, base_y], color="black", lw=style.LINE_WIDTH)
    for i in range(7):
        bx = x - s * 0.7 + i * (1.4 * s / 6)
        ax.plot([bx, bx - 0.12], [base_y, base_y - 0.22], color="black", lw=0.9)


def _draw_roller(canvas: Canvas, x: float) -> None:
    ax = canvas.ax
    s = style.SUPPORT_SIZE
    y_top = canvas.y_beam - style.BEAM_HEIGHT / 2
    tri = Polygon(
        [(x, y_top), (x - s * 0.55, y_top - s * 0.75), (x + s * 0.55, y_top - s * 0.75)],
        closed=True,
        fill=False,
        edgecolor="black",
        linewidth=style.LINE_WIDTH,
        zorder=4,
    )
    ax.add_patch(tri)
    r = 0.12
    cy = y_top - s * 0.75 - r
    ax.add_patch(Circle((x - r * 1.2, cy), r, fill=False, edgecolor="black", lw=style.LINE_WIDTH, zorder=4))
    ax.add_patch(Circle((x + r * 1.2, cy), r, fill=False, edgecolor="black", lw=style.LINE_WIDTH, zorder=4))
    ax.plot([x - s * 0.75, x + s * 0.75], [cy - r - 0.05, cy - r - 0.05], color="black", lw=style.LINE_WIDTH)


def _draw_fixed(canvas: Canvas, x: float) -> None:
    ax = canvas.ax
    h = style.BEAM_HEIGHT
    y0 = canvas.y_beam - h / 2
    wall_w = 0.35
    # קיר משמאל לנקודה אם בקצה, אחרת סמל קצר מתחת
    ax.add_patch(
        Rectangle(
            (x - wall_w, y0 - 0.9),
            wall_w,
            h + 0.9,
            fill=False,
            edgecolor="black",
            linewidth=style.LINE_WIDTH,
            zorder=4,
        )
    )
    for i in range(6):
        yy = y0 - 0.85 + i * 0.28
        ax.plot([x - wall_w, x - wall_w - 0.25], [yy, yy - 0.2], color="black", lw=0.9)
