# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, List, Tuple

import numpy as np

from notebook.constants import _BLUE, _GREEN, _INK, _RED

_EMPTY_DIAGRAM_TOL = 1e-9


def _diagram_is_empty(values: np.ndarray, *, tol: float = _EMPTY_DIAGRAM_TOL) -> bool:
    """True כשאין דיאגרמה משמעותית — רק קו הקורה."""
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return True
    return float(np.max(np.abs(arr))) < tol


def _draw_empty_diagram_beam(
    ax: Any,
    Lf: float,
    crit: List[Tuple[float, str]],
    *,
    draw_beam_reference: Any,
    invert_y: bool,
) -> None:
    """פאנל ריק: רק קו הקורה (בלי מילוי דיאגרמה)."""
    if invert_y:
        ax.invert_yaxis()
    ymin, ymax = ax.get_ylim()
    draw_beam_reference(ax, Lf, crit, ymin, ymax)
    (ln,) = ax.plot(
        [0.0, float(Lf)],
        [0.0, 0.0],
        color=_INK,
        linewidth=2.4,
        zorder=6,
        solid_capstyle="round",
    )
    ln.set_clip_on(False)


def _plot_n_on_beam_clean(
    ax: Any,
    xs: np.ndarray,
    normals: np.ndarray,
    Lf: float,
    x_pad: float,
    crit: List[Tuple[float, str]],
    *,
    configure_beam_diagram_ax: Any,
    plot_zero_baseline_cartesian: Any,
    draw_beam_reference: Any,
    diag_lw: float,
    fill_alpha: float,
    transparent: bool = True,
) -> None:
    xs = np.asarray(xs, dtype=float)
    normals = np.asarray(normals, dtype=float)
    if len(xs) and xs[0] > 1e-9:
        xs = np.concatenate(([0.0], xs))
        normals = np.concatenate(([float(normals[0])], normals))

    configure_beam_diagram_ax(ax, Lf, x_pad, normals, transparent=transparent, paper=False)
    if _diagram_is_empty(normals):
        _draw_empty_diagram_beam(
            ax, Lf, crit, draw_beam_reference=draw_beam_reference, invert_y=True
        )
        return

    plot_zero_baseline_cartesian(ax, Lf)
    ax.fill_between(xs, normals, 0, step="post", color=_GREEN, alpha=fill_alpha, zorder=2)
    # להתחיל מהקורה (y=0) גם אם יש קפיצה בתחילת הגרף
    if len(xs):
        ax.plot([0.0, 0.0], [0.0, float(normals[0])], color=_GREEN, linewidth=diag_lw, zorder=3)
    ax.step(xs, normals, where="post", color=_GREEN, linewidth=diag_lw, zorder=3)
    ax.invert_yaxis()
    ymin, ymax = ax.get_ylim()
    draw_beam_reference(ax, Lf, crit, ymin, ymax)


def _plot_q_on_beam_clean(
    ax: Any,
    xs: np.ndarray,
    shears: np.ndarray,
    Lf: float,
    x_pad: float,
    crit: List[Tuple[float, str]],
    *,
    configure_beam_diagram_ax: Any,
    plot_zero_baseline_cartesian: Any,
    draw_beam_reference: Any,
    diag_lw: float,
    fill_alpha: float,
    transparent: bool = True,
) -> None:
    xs = np.asarray(xs, dtype=float)
    shears = np.asarray(shears, dtype=float)
    if len(xs) and xs[0] > 1e-9:
        xs = np.concatenate(([0.0], xs))
        shears = np.concatenate(([float(shears[0])], shears))

    configure_beam_diagram_ax(ax, Lf, x_pad, shears, transparent=transparent, paper=False)
    if _diagram_is_empty(shears):
        _draw_empty_diagram_beam(
            ax, Lf, crit, draw_beam_reference=draw_beam_reference, invert_y=False
        )
        return

    plot_zero_baseline_cartesian(ax, Lf)
    ax.fill_between(xs, shears, 0, step="post", color=_BLUE, alpha=fill_alpha, zorder=2)
    if len(xs):
        ax.plot([0.0, 0.0], [0.0, float(shears[0])], color=_BLUE, linewidth=diag_lw, zorder=3)
    ax.step(xs, shears, where="post", color=_BLUE, linewidth=diag_lw, zorder=3)
    ymin, ymax = ax.get_ylim()
    draw_beam_reference(ax, Lf, crit, ymin, ymax)


def _plot_m_on_beam_clean(
    ax: Any,
    xs: np.ndarray,
    moments: np.ndarray,
    Lf: float,
    x_pad: float,
    crit: List[Tuple[float, str]],
    *,
    configure_beam_diagram_ax: Any,
    beam_diagram_ylim_moment: Any,
    plot_zero_baseline_cartesian: Any,
    draw_beam_reference: Any,
    diag_lw: float,
    fill_alpha: float,
    transparent: bool = True,
) -> None:
    xs = np.asarray(xs, dtype=float)
    moments = np.asarray(moments, dtype=float)
    if len(xs) and xs[0] > 1e-9:
        xs = np.concatenate(([0.0], xs))
        moments = np.concatenate(([float(moments[0])], moments))

    configure_beam_diagram_ax(ax, Lf, x_pad, moments, transparent=transparent, paper=False)
    ymin, ymax = beam_diagram_ylim_moment(moments)
    ax.set_ylim(ymin, ymax)
    if _diagram_is_empty(moments):
        _draw_empty_diagram_beam(
            ax, Lf, crit, draw_beam_reference=draw_beam_reference, invert_y=True
        )
        return

    plot_zero_baseline_cartesian(ax, Lf)
    if len(xs):
        ax.plot([0.0, 0.0], [0.0, float(moments[0])], color=_RED, linewidth=diag_lw, zorder=3)
    ax.fill_between(xs, moments, 0, color=_RED, alpha=fill_alpha, zorder=2)
    ax.plot(xs, moments, color=_RED, linewidth=diag_lw, zorder=3, solid_capstyle="round")
    ax.invert_yaxis()
    ymin2, ymax2 = ax.get_ylim()
    draw_beam_reference(ax, Lf, crit, ymin2, ymax2)
