# -*- coding: utf-8 -*-
"""שרטוט תרגיל עליון למחברת — נבנה מחדש על מנוע שרטוט הבחינה.

מחליף את ציור המחברת הישן (קו דק + עומסים אדומים + חיצי ריאקציות)
בשרטוט שחור-לבן בסגנון תרגול/בחינה.
"""
from __future__ import annotations

from typing import Any, List, Literal, Tuple

import matplotlib

matplotlib.use("Agg")

import core.statics_calculator as solver
from exercise_generator.geometry import row_from_breaks
from exercise_generator.render.beam import draw_beam
from exercise_generator.render.canvas import Canvas
from exercise_generator.render.dimensions import draw_dimensions
from exercise_generator.render.labels import draw_point_labels, draw_station_dots
from exercise_generator.render.loads import draw_loads
from exercise_generator.render.supports import draw_supports
from exercise_generator.schema import (
    DistributedLoad,
    Exercise,
    InclinedLoad,
    LabeledPoint,
    LoadItem,
    MomentLoad,
    PointLoad,
    Support,
)

_SupportMode = Literal["simply_supported", "cantilever"]

# הגדלת ציור התרגיל במחברת ביחס למסגרת הבחינה המקורית
_NOTEBOOK_PROBLEM_SCALE = 1.10


def _zoom_canvas(canvas: Canvas, scale: float) -> None:
    """מגדיל את תוכן הציור ב־scale (זום למרכז המסגרת)."""
    if scale <= 0 or abs(scale - 1.0) < 1e-9:
        return
    ax = canvas.ax
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    cx = 0.5 * (x0 + x1)
    cy = 0.5 * (y0 + y1)
    half_w = 0.5 * (x1 - x0) / scale
    half_h = 0.5 * (y1 - y0) / scale
    ax.set_xlim(cx - half_w, cx + half_w)
    ax.set_ylim(cy - half_h, cy + half_h)


def _station_points(
    loads: List[dict],
    L: float,
    *,
    ra_pos: float | None = None,
    rb_pos: float | None = None,
    cantilever: bool = False,
) -> List[Tuple[float, str]]:
    """נקודות מסומנות (x, אות) משמאל לימין."""
    Lf = float(L)
    if cantilever:
        xs = solver.critical_x_positions(loads, Lf, 0.0, Lf)
        labels: dict[float, str] = {0.0: "A"}
        letters = "BCDEGHIJKLMNOPQRSTUVWXYZ"
        li = 0
        out: List[Tuple[float, str]] = []
        for x in xs:
            k = round(float(x), 6)
            if k not in labels:
                labels[k] = letters[li] if li < len(letters) else f"P{li}"
                li += 1
            out.append((float(x), labels[k]))
        return out

    ra = float(ra_pos if ra_pos is not None else 0.0)
    rb = float(rb_pos if rb_pos is not None else Lf)
    xs = solver.critical_x_positions(loads, Lf, ra, rb)
    labels = {round(ra, 6): "A", round(rb, 6): "B"}
    letters = "CDEGHIJKLMNOPQRSTUVWXYZ"
    li = 0
    out = []
    for x in xs:
        k = round(float(x), 6)
        if k not in labels:
            labels[k] = letters[li] if li < len(letters) else f"P{li}"
            li += 1
        out.append((float(x), labels[k]))
    return out


def _solver_loads_to_exercise_loads(loads: List[dict]) -> List[LoadItem]:
    """ממיר עומסי solver (Fy/w שלילי = מטה) לעומסי Exercise (חיובי = מטה)."""
    out: List[LoadItem] = []
    for ld in loads:
        if not isinstance(ld, dict):
            continue
        t = ld.get("type")
        if t == "point":
            fy_s = float(ld.get("Fy", 0.0) or 0.0)
            fx = float(ld.get("Fx", 0.0) or 0.0)
            out.append(
                PointLoad(
                    x=float(ld.get("x", 0.0) or 0.0),
                    Fy=-fy_s,
                    Fx=fx,
                )
            )
        elif t == "distributed":
            w_s = float(ld.get("w", 0.0) or 0.0)
            shape = str(ld.get("shape") or "rectangular")
            if shape not in ("rectangular", "triangular"):
                shape = "rectangular"
            out.append(
                DistributedLoad(
                    x1=float(ld.get("x1", 0.0) or 0.0),
                    x2=float(ld.get("x2", 0.0) or 0.0),
                    w=-w_s,
                    shape=shape,  # type: ignore[arg-type]
                )
            )
        elif t == "inclined":
            mag, angle, incl_dir = solver.infer_inclined_polar(ld)
            direction = "dl" if str(incl_dir).lower() == "dl" else "dr"
            out.append(
                InclinedLoad(
                    x=float(ld.get("x", 0.0) or 0.0),
                    magnitude_ton=abs(float(mag)),
                    angle_deg=float(angle),
                    incl_dir=direction,  # type: ignore[arg-type]
                )
            )
        elif t == "moment":
            out.append(
                MomentLoad(
                    x=float(ld.get("x", 0.0) or 0.0),
                    M=float(ld.get("M", 0.0) or 0.0),
                )
            )
    return out


def build_exercise_from_beam(
    L: float,
    loads: List[dict],
    *,
    mode: _SupportMode = "simply_supported",
    ra_pos: float = 0.0,
    rb_pos: float | None = None,
) -> Exercise:
    """בונה Exercise מנתוני קורה של המנוע — לשרטוט בלבד."""
    Lf = float(L)
    rb = float(rb_pos if rb_pos is not None else Lf)
    ex_loads = _solver_loads_to_exercise_loads(loads)

    if mode == "cantilever":
        stations = _station_points(loads, Lf, cantilever=True)
        supports = [Support("A", "fixed", 0.0)]
        labeled = [
            LabeledPoint(label, x)
            for x, label in stations
            if label != "A"
        ]
        breaks = [x for x, _ in stations]
        if not breaks or abs(breaks[0]) > 1e-9:
            breaks = [0.0] + breaks
        if abs(breaks[-1] - Lf) > 1e-9:
            breaks = breaks + [Lf]
        return Exercise(
            L=Lf,
            support_mode="cantilever",
            supports=supports,
            loads=ex_loads,
            labeled_points=labeled,
            dim_row_top=row_from_breaks(breaks),
            dim_row_bottom=row_from_breaks([0.0, Lf]),
            family="notebook_schematic",
        )

    stations = _station_points(loads, Lf, ra_pos=ra_pos, rb_pos=rb)
    ra, rb_f = float(ra_pos), float(rb)
    if ra <= rb_f:
        supports = [
            Support("A", "pin", ra),
            Support("B", "roller", rb_f),
        ]
    else:
        supports = [
            Support("A", "pin", rb_f),
            Support("B", "roller", ra),
        ]
    labeled = [
        LabeledPoint(label, x)
        for x, label in stations
        if label not in ("A", "B")
    ]
    breaks = [x for x, _ in stations]
    if not breaks or abs(breaks[0]) > 1e-9:
        breaks = [0.0] + breaks
    if abs(breaks[-1] - Lf) > 1e-9:
        breaks = breaks + [Lf]
    # שורת מידה תחתונה: קצוות + סמכים
    bottom_breaks = sorted({0.0, ra, rb_f, Lf})
    return Exercise(
        L=Lf,
        support_mode="simply_supported",
        supports=supports,
        loads=ex_loads,
        labeled_points=labeled,
        dim_row_top=row_from_breaks(breaks),
        dim_row_bottom=row_from_breaks(bottom_breaks),
        family="notebook_schematic",
    )


def draw_exercise_on_canvas(exercise: Exercise) -> Canvas:
    """מצייר תרגיל על Canvas חדש (בלי חותמת מותג)."""
    canvas = Canvas.create(exercise.L)
    draw_beam(canvas)
    draw_supports(canvas, exercise.supports, beam_L=exercise.L)
    draw_loads(
        canvas,
        exercise.loads,
        supports=exercise.supports,
        beam_L=exercise.L,
    )
    draw_station_dots(canvas, exercise)
    draw_point_labels(canvas, exercise.supports, exercise.labeled_points)
    draw_dimensions(canvas, exercise.dim_row_top, exercise.dim_row_bottom)
    _zoom_canvas(canvas, _NOTEBOOK_PROBLEM_SCALE)
    # רקע שקוף להטמעה בנייר המחברת
    canvas.fig.patch.set_facecolor("none")
    canvas.fig.patch.set_alpha(0.0)
    canvas.ax.set_facecolor("none")
    canvas.ax.patch.set_alpha(0.0)
    return canvas


def build_problem_figure(
    L: float,
    loads: List[dict],
    *,
    mode: _SupportMode = "simply_supported",
    ra_pos: float = 0.0,
    rb_pos: float | None = None,
) -> Any:
    """Figure של שרטוט התרגיל החדש — לתצוגת מחברת / תמונת שאלה."""
    exercise = build_exercise_from_beam(
        L,
        loads,
        mode=mode,
        ra_pos=ra_pos,
        rb_pos=rb_pos,
    )
    return draw_exercise_on_canvas(exercise).fig
