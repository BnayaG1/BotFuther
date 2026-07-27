# -*- coding: utf-8 -*-
from __future__ import annotations

from exercise_generator.render.canvas import Canvas
from exercise_generator.render import style
from exercise_generator.schema import LabeledPoint, Support


def draw_point_labels(
    canvas: Canvas,
    supports: list[Support],
    labeled_points: list[LabeledPoint],
) -> None:
    ax = canvas.ax
    y_below = canvas.y_beam - style.BEAM_HEIGHT / 2 - 0.35
    seen: set[str] = set()
    for s in supports:
        if s.label in seen:
            continue
        seen.add(s.label)
        ax.text(
            s.x,
            y_below,
            s.label,
            ha="center",
            va="top",
            fontsize=11,
            fontweight="bold",
            zorder=10,
        )
    for p in labeled_points:
        if p.label in seen:
            # נקודה מתויגת שאינה סמך — מעל הקורה
            if not any(s.label == p.label for s in supports):
                pass
            else:
                continue
        seen.add(p.label)
        ax.text(
            p.x,
            canvas.y_beam + style.BEAM_HEIGHT / 2 + style.LABEL_OFFSET_Y,
            p.label,
            ha="center",
            va="bottom",
            fontsize=11,
            fontweight="bold",
            zorder=10,
        )
