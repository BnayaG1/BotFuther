# -*- coding: utf-8 -*-
"""מערכת קואורדינטות מטר → ציר הציור."""
from __future__ import annotations

from dataclasses import dataclass

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from exercise_generator.render import style


@dataclass
class Canvas:
    fig: Figure
    ax: Axes
    L: float
    y_beam: float = 0.0

    @classmethod
    def create(cls, L: float) -> "Canvas":
        fig, ax = plt.subplots(figsize=style.FIGSIZE, dpi=style.DPI)
        ax.set_aspect("equal")
        ax.axis("off")
        margin_x = max(1.2, 0.08 * L)
        ax.set_xlim(-margin_x, L + margin_x)
        ax.set_ylim(*style.Y_LIM)
        return cls(fig=fig, ax=ax, L=L, y_beam=style.BEAM_Y)

    def x(self, meter: float) -> float:
        return float(meter)

    def y(self, above_beam: float) -> float:
        return self.y_beam + float(above_beam)
