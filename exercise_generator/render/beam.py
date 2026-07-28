# -*- coding: utf-8 -*-
from __future__ import annotations

from matplotlib.patches import FancyBboxPatch

from exercise_generator.render.canvas import Canvas
from exercise_generator.render import style


def draw_beam(canvas: Canvas) -> None:
    ax = canvas.ax
    h = style.BEAM_HEIGHT
    y0 = canvas.y_beam - h / 2
    length = canvas.beam_display_length
    beam = FancyBboxPatch(
        (0.0, y0),
        length,
        h,
        boxstyle="square,pad=0",
        linewidth=style.LINE_WIDTH,
        edgecolor="black",
        facecolor="white",
        zorder=2,
    )
    ax.add_patch(beam)
    ax.plot(
        [0.0, length],
        [canvas.y_beam, canvas.y_beam],
        linestyle=(0, (2, 2)),
        color="black",
        linewidth=0.8,
        zorder=3,
    )
