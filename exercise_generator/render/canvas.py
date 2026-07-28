# -*- coding: utf-8 -*-
"""מערכת קואורדינטות מטר → ציר הציור.

הקורה תמיד תופסת את אותו רוחב ויזואלי (``FRAME_L_MAX``): מיקומים במטרים
מוכפלים ב־``scale = FRAME_L_MAX / L``. תוויות מידה נשארות לפי המטרים האמיתיים.
"""
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
    scale: float = 1.0
    y_beam: float = 0.0

    @classmethod
    def create(cls, L: float) -> "Canvas":
        fig, ax = plt.subplots(figsize=style.FIGSIZE, dpi=style.DPI)
        ax.set_position([0.0, 0.0, 1.0, 1.0])
        ax.set_aspect("equal")
        ax.axis("off")
        ax.set_xlim(*style.X_LIM)
        ax.set_ylim(*style.Y_LIM)
        scale = style.FRAME_L_MAX / float(L) if L > 0 else 1.0
        return cls(fig=fig, ax=ax, L=float(L), scale=scale, y_beam=style.BEAM_Y)

    def x(self, meter: float) -> float:
        """מטרים על הקורה → קואורדינטת ציור (קורה תמיד באורך ויזואלי קבוע)."""
        return float(meter) * self.scale

    @property
    def beam_display_length(self) -> float:
        return style.FRAME_L_MAX

    def y(self, above_beam: float) -> float:
        return self.y_beam + float(above_beam)
