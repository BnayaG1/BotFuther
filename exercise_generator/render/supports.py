# -*- coding: utf-8 -*-
from __future__ import annotations

from matplotlib.patches import Circle, Polygon, Rectangle

from exercise_generator.render.canvas import Canvas
from exercise_generator.render import style
from exercise_generator.schema import Support

# יחסים מקוריים כש־SUPPORT_SIZE היה 0.55
_REF_S = 0.55


def draw_supports(
    canvas: Canvas,
    supports: list[Support],
    *,
    beam_L: float | None = None,
) -> None:
    L = float(beam_L) if beam_L is not None else float(canvas.L)
    for s in supports:
        x = canvas.x(s.x)
        if s.type == "pin":
            _draw_pin(canvas, x)
        elif s.type == "roller":
            _draw_roller(canvas, x)
        elif s.type == "fixed":
            side = "right" if abs(float(s.x) - L) <= 1e-9 else "left"
            _draw_fixed(canvas, x, side=side)


def _draw_pin(canvas: Canvas, x: float) -> None:
    ax = canvas.ax
    s = style.SUPPORT_SIZE
    y_top = canvas.y_beam - style.BEAM_HEIGHT / 2
    half_base = s * 0.55  # חצי בסיס המשולש
    tri = Polygon(
        [(x, y_top), (x - half_base, y_top - s), (x + half_base, y_top - s)],
        closed=True,
        fill=False,
        edgecolor="black",
        linewidth=style.LINE_WIDTH,
        zorder=4,
    )
    ax.add_patch(tri)
    base_y = y_top - s  # צמוד לבסיס המשולש
    ax.plot(
        [x - half_base, x + half_base],
        [base_y, base_y],
        color="black",
        lw=style.LINE_WIDTH,
    )
    hatch_dx = s * (0.12 / _REF_S)
    hatch_dy = s * (0.22 / _REF_S)
    for i in range(7):
        bx = x - half_base + i * (2 * half_base / 6)
        ax.plot([bx, bx - hatch_dx], [base_y, base_y - hatch_dy], color="black", lw=0.9)


def _draw_roller(canvas: Canvas, x: float) -> None:
    ax = canvas.ax
    s = style.SUPPORT_SIZE
    y_top = canvas.y_beam - style.BEAM_HEIGHT / 2
    half_base = s * 0.55
    tri_h = s * 0.75
    tri = Polygon(
        [(x, y_top), (x - half_base, y_top - tri_h), (x + half_base, y_top - tri_h)],
        closed=True,
        fill=False,
        edgecolor="black",
        linewidth=style.LINE_WIDTH,
        zorder=4,
    )
    ax.add_patch(tri)
    r = s * (0.12 / _REF_S)
    cy = y_top - tri_h - r
    ax.add_patch(
        Circle((x - r * 1.2, cy), r, fill=False, edgecolor="black", lw=style.LINE_WIDTH, zorder=4)
    )
    ax.add_patch(
        Circle((x + r * 1.2, cy), r, fill=False, edgecolor="black", lw=style.LINE_WIDTH, zorder=4)
    )


def _draw_fixed(canvas: Canvas, x: float, *, side: str = "left") -> None:
    ax = canvas.ax
    h = style.BEAM_HEIGHT
    y0 = canvas.y_beam - h / 2  # תחתית הקורה
    wall_w = 0.35 * 0.30  # הוקטן ב־70%
    pad_old = 0.9
    # גובה כולל של המלבן — שני שליש מהקודם; הקורה נשארת באמצע
    total_h = (h + 2 * pad_old) * (2 / 3)
    pad = (total_h - h) / 2
    rect_bottom = y0 - pad
    rect_h = total_h
    if side == "right":
        ax.add_patch(
            Rectangle(
                (x, rect_bottom),
                wall_w,
                rect_h,
                facecolor="#c8c8c8",
                edgecolor="black",
                linewidth=style.LINE_WIDTH,
                zorder=4,
            )
        )
        for i in range(6):
            yy = rect_bottom + 0.05 + i * ((rect_h - 0.1) / 5)
            ax.plot([x + wall_w, x + wall_w + 0.25], [yy, yy - 0.2], color="black", lw=0.9)
        return
    ax.add_patch(
        Rectangle(
            (x - wall_w, rect_bottom),
            wall_w,
            rect_h,
            facecolor="#c8c8c8",
            edgecolor="black",
            linewidth=style.LINE_WIDTH,
            zorder=4,
        )
    )
    for i in range(6):
        yy = rect_bottom + 0.05 + i * ((rect_h - 0.1) / 5)
        ax.plot([x - wall_w, x - wall_w - 0.25], [yy, yy - 0.2], color="black", lw=0.9)
