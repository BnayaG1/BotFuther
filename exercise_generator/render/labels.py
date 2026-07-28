# -*- coding: utf-8 -*-
from __future__ import annotations

from matplotlib.patches import Circle

from exercise_generator.render.canvas import Canvas
from exercise_generator.render import style
from exercise_generator.schema import Exercise, LabeledPoint, Support


def draw_point_labels(
    canvas: Canvas,
    supports: list[Support],
    labeled_points: list[LabeledPoint],
) -> None:
    """אותיות (A, B, C…) מעל הנקודות בשורת המידה העליונה."""
    ax = canvas.ax
    y = canvas.y_beam + style.DIM_OFFSET_1 + 0.35
    seen: set[str] = set()
    points: list[tuple[str, float]] = []
    for s in supports:
        if s.label in seen:
            continue
        seen.add(s.label)
        points.append((s.label, float(s.x)))
    for p in labeled_points:
        if p.label in seen:
            continue
        seen.add(p.label)
        points.append((p.label, float(p.x)))

    for label, x_m in points:
        ax.text(
            canvas.x(x_m),
            y,
            label,
            ha="center",
            va="bottom",
            fontsize=11,
            fontweight="bold",
            zorder=10,
        )


def draw_station_dots(canvas: Canvas, exercise: Exercise) -> None:
    """נקודה שחורה קטנה על הקורה בכל נקודה רשמית (סמכים + נקודות מתויגות), בלי קצוות הקורה."""
    xs: set[float] = set()
    for s in exercise.supports:
        xs.add(round(float(s.x), 6))
    for p in exercise.labeled_points:
        xs.add(round(float(p.x), 6))

    L = float(exercise.L)
    ax = canvas.ax
    r = style.STATION_DOT_RADIUS
    y = canvas.y_beam
    for x_m in xs:
        if abs(x_m) < 1e-9 or abs(x_m - L) < 1e-9:
            continue
        ax.add_patch(
            Circle(
                (canvas.x(x_m), y),
                r,
                facecolor="black",
                edgecolor="black",
                linewidth=0.5,
                zorder=11,
            )
        )
