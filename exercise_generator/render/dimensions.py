# -*- coding: utf-8 -*-
from __future__ import annotations

from exercise_generator.render.canvas import Canvas
from exercise_generator.render import style
from exercise_generator.schema import DimensionRow


def draw_dimensions(canvas: Canvas, top: DimensionRow, bottom: DimensionRow) -> None:
    _draw_row(canvas, top, style.DIM_OFFSET_1)
    _draw_row(canvas, bottom, style.DIM_OFFSET_2)


def _draw_row(canvas: Canvas, row: DimensionRow, y_off: float) -> None:
    if not row.segments:
        return
    ax = canvas.ax
    y = canvas.y_beam + y_off
    tick = 0.18
    for seg in row.segments:
        x1, x2 = float(seg.x1), float(seg.x2)
        ax.plot([x1, x2], [y, y], color="black", lw=1.0, zorder=3)
        ax.plot([x1, x1], [y - tick, y + tick], color="black", lw=1.0, zorder=3)
        ax.plot([x2, x2], [y - tick, y + tick], color="black", lw=1.0, zorder=3)
        ax.plot([x1 - 0.08, x1 + 0.08], [y + tick, y - tick], color="black", lw=0.9)
        ax.plot([x2 - 0.08, x2 + 0.08], [y + tick, y - tick], color="black", lw=0.9)
        label = seg.label if seg.label is not None else _fmt_len(abs(x2 - x1))
        ax.text((x1 + x2) / 2, y - 0.28, label, ha="center", va="top", fontsize=9, zorder=3)


def _fmt_len(v: float) -> str:
    if abs(v - round(v)) < 1e-9:
        return f"{int(round(v))}.0"
    text = f"{v:.2f}".rstrip("0").rstrip(".")
    return text
