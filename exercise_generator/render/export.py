# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from exercise_generator.render.beam import draw_beam
from exercise_generator.render.canvas import Canvas
from exercise_generator.render.dimensions import draw_dimensions
from exercise_generator.render.labels import draw_point_labels
from exercise_generator.render.loads import draw_loads
from exercise_generator.render.supports import draw_supports
from exercise_generator.schema import Exercise


def render_exercise_png(exercise: Exercise, out_path: Path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas = Canvas.create(exercise.L)
    draw_beam(canvas)
    draw_supports(canvas, exercise.supports)
    draw_loads(canvas, exercise.loads)
    draw_point_labels(canvas, exercise.supports, exercise.labeled_points)
    draw_dimensions(canvas, exercise.dim_row_top, exercise.dim_row_bottom)
    canvas.fig.tight_layout(pad=0.3)
    canvas.fig.savefig(out_path, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(canvas.fig)
    return out_path
