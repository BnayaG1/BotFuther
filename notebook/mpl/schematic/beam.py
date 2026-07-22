# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import core.statics_calculator as solver

from notebook.constants import _BEAM_MAIN_LW, _INK


def _draw_beam_schematic(
    ax: Any,
    L: float,
    loads: List[dict],
    ra_pos: float,
    rb_pos: float,
    ra_x: float,
    ra_y: float,
    rb_y: float,
    *,
    show_values: bool,
    set_limits: bool,
    station_labels_fn: Any,
    notebook_layout_fn: Any,
    draw_notebook_dimension_lines_fn: Any,
    draw_pin_support_fn: Any,
    draw_roller_support_fn: Any,
    draw_loads_like_canvas_fn: Any,
    beam_x_pad_fn: Any,
    fs_small: float,
    fs_body: float,
    ink_color: str = _INK,
) -> None:
    """שרטוט קורה + עומסים. show_values=False: רק אותיות נקודות על קו מידות (A,B,C…)."""
    Lf = float(L)
    ax.plot([0, Lf], [0, 0], color=ink_color, linewidth=_BEAM_MAIN_LW, zorder=2, solid_capstyle="round")

    if abs(ra_pos - rb_pos) < 1e-9:
        draw_pin_support_fn(ax, ra_pos)
    else:
        if ra_pos <= rb_pos:
            draw_pin_support_fn(ax, ra_pos)
            draw_roller_support_fn(ax, rb_pos)
        else:
            draw_pin_support_fn(ax, rb_pos)
            draw_roller_support_fn(ax, ra_pos)

    load_scale = max(0.28, 0.05 * max(abs(ra_y), abs(rb_y), 8.0))
    draw_loads_like_canvas_fn(ax, loads, load_scale, show_values=show_values)

    if show_values:
        if abs(ra_y) > 1e-9:
            ax.text(
                ra_pos + 0.05,
                0.28,
                f"{solver.format_number(ra_y)} = Ay",
                fontsize=fs_small,
                color=ink_color,
                fontweight="normal",
            )
        if abs(rb_y) > 1e-9:
            ax.text(
                rb_pos - 0.05,
                0.28,
                f"By = {solver.format_number(rb_y)}",
                fontsize=fs_small,
                color=ink_color,
                fontweight="normal",
                ha="right",
            )
        if abs(ra_x) > 1e-9:
            magx = 0.22
            if ra_x > 0:
                ax.annotate(
                    "",
                    xy=(ra_pos + magx, 0.04),
                    xytext=(ra_pos, 0.04),
                    arrowprops=dict(arrowstyle="-|>", color=ink_color, lw=1.1),
                )
                ax.text(
                    ra_pos + magx + 0.02,
                    0.1,
                    f"{solver.format_number(ra_x)} = Ax",
                    fontsize=fs_small,
                    color=ink_color,
                )
            else:
                ax.annotate(
                    "",
                    xy=(ra_pos - magx, 0.04),
                    xytext=(ra_pos, 0.04),
                    arrowprops=dict(arrowstyle="-|>", color=ink_color, lw=1.1),
                )
                ax.text(
                    ra_pos - magx - 0.2,
                    0.1,
                    f"{solver.format_number(ra_x)} = Ax",
                    fontsize=fs_small,
                    color=ink_color,
                )

    stations = station_labels_fn(loads, L, ra_pos, rb_pos)
    layout = notebook_layout_fn()
    dim_bottom = draw_notebook_dimension_lines_fn(
        ax, stations, layout, support_pair=(ra_pos, rb_pos)
    )

    pad_x = beam_x_pad_fn(Lf)
    ax.set_xlim(-pad_x, Lf + pad_x)
    if set_limits:
        ax.set_ylim(min(layout["y_bottom"], dim_bottom), layout["y_top"])
    ax.axis("off")

