# -*- coding: utf-8 -*-
"""שרטוט תרגיל מרכז כובד — רכיבים צמודים + קו מוביל ותווית לכל רכיב."""
from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import PathPatch, Polygon
from matplotlib.path import Path

from exercise_generator.center_of_gravity.generator import CogExercise, Component

_FILL = "#d9d9d9"
_PAPER = "#fdf5e6"
_GRID = "#c8c0b0"
_GRID_IN = 2.91 / 25.4
_EDGE = "#111111"
_LINE_WIDTH = 1.6
_LABEL_FONTSIZE = 14
_DPI = 160
_FIG_HEIGHT_IN = 6.5
_LABEL_WIDTH_IN = 2.4
_MARGIN_FRAC = 0.1


def _outline(comp: Component) -> list[tuple[float, float]]:
    w, h = comp.width, comp.height
    p = comp.params
    if comp.kind == "i_section":
        tw, tf = p["tw"], p["tf"]
        l, r = (w - tw) / 2.0, (w + tw) / 2.0
        return [
            (0, 0), (w, 0), (w, tf), (r, tf), (r, h - tf), (w, h - tf),
            (w, h), (0, h), (0, h - tf), (l, h - tf), (l, tf), (0, tf),
        ]
    if comp.kind == "c_section":
        tw, tf = p["tw"], p["tf"]
        return [(0, 0), (w, 0), (w, tf), (tw, tf), (tw, h - tf), (w, h - tf), (w, h), (0, h)]
    if comp.kind == "c_cap":
        tw, tf = p["tw"], p["tf"]
        return [(0, 0), (tf, 0), (tf, h - tw), (w - tf, h - tw), (w - tf, 0), (w, 0), (w, h), (0, h)]
    if comp.kind == "l_section":
        t = p["t"]
        return [(0, 0), (w, 0), (w, t), (t, t), (t, h), (0, h)]
    return [(0, 0), (w, 0), (w, h), (0, h)]


def _anchor(comp: Component, side: str) -> tuple[float, float]:
    w, h = comp.width, comp.height
    p = comp.params
    if comp.kind == "i_section":
        return w / 2.0, h / 2.0
    if comp.kind == "c_section":
        return p["tw"] / 2.0, h / 2.0
    if comp.kind == "c_cap":
        return w / 2.0, h - p["tw"] / 2.0
    if comp.kind == "l_section":
        return p["t"] / 2.0, (h + p["t"]) / 2.0
    if comp.kind == "rhs":
        x = w - p["t"] / 2.0 if side == "right" else p["t"] / 2.0
        return (x if not comp.mirror else w - x), h / 2.0
    return w / 2.0, h / 2.0


def _to_world(comp: Component, pt: tuple[float, float]) -> tuple[float, float]:
    x, y = pt
    if comp.mirror:
        x = comp.width - x
    return comp.x + x, comp.y + y


def _draw_notebook_grid(ax, units_per_in: float) -> None:
    step = units_per_in * _GRID_IN
    xmin, xmax = ax.get_xlim()
    ymin, ymax = ax.get_ylim()
    x = step * (xmin // step)
    while x <= xmax:
        ax.axvline(x, color=_GRID, linewidth=0.6, zorder=0)
        x += step
    y = step * (ymin // step)
    while y <= ymax:
        ax.axhline(y, color=_GRID, linewidth=0.6, zorder=0)
        y += step


def _draw_component(ax, comp: Component) -> None:
    style = {"facecolor": _FILL, "edgecolor": _EDGE, "linewidth": _LINE_WIDTH, "zorder": 2}
    if comp.kind == "rhs":
        t = comp.params["t"]
        outer = [_to_world(comp, pt) for pt in _outline(comp)]
        inner = [_to_world(comp, pt) for pt in (
            (t, t), (comp.width - t, t), (comp.width - t, comp.height - t), (t, comp.height - t),
        )]
        inner = inner[::-1]
        verts = outer + [outer[0]] + inner + [inner[0]]
        codes = (
            [Path.MOVETO] + [Path.LINETO] * (len(outer) - 1) + [Path.CLOSEPOLY]
            + [Path.MOVETO] + [Path.LINETO] * (len(inner) - 1) + [Path.CLOSEPOLY]
        )
        ax.add_patch(PathPatch(Path(verts, codes), **style))
        return
    ax.add_patch(Polygon([_to_world(comp, pt) for pt in _outline(comp)], closed=True, **style))


def _blocked(comp: Component, others: list[Component], side: str) -> bool:
    y = comp.y + comp.height / 2.0
    for other in others:
        if not (other.y < y < other.top):
            continue
        if side == "right" and other.x >= comp.right - 1e-6:
            return True
        if side == "left" and other.right <= comp.x + 1e-6:
            return True
    return False


def _label_groups(comps: list[Component]) -> list[list[Component]]:
    groups: dict[object, list[Component]] = {}
    for idx, comp in enumerate(comps):
        key = ("g", comp.group) if comp.group is not None else ("c", idx)
        groups.setdefault(key, []).append(comp)
    return list(groups.values())


def _group_side(group: list[Component], comps: list[Component]) -> str:
    others = [c for c in comps if c not in group]
    if all(not _blocked(c, others, "right") for c in group):
        return "right"
    if all(not _blocked(c, others, "left") for c in group):
        return "left"
    return "right"


def _spread(ys: list[float], min_gap: float) -> list[float]:
    order = sorted(range(len(ys)), key=lambda i: ys[i])
    out = list(ys)
    for prev, cur in zip(order, order[1:]):
        if out[cur] - out[prev] < min_gap:
            out[cur] = out[prev] + min_gap
    return out


def render_cog_exercise_png(exercise: CogExercise) -> bytes:
    comps = exercise.components
    min_x = min(c.x for c in comps)
    max_x = max(c.right for c in comps)
    min_y = min(c.y for c in comps)
    max_y = max(c.top for c in comps)
    span_h = max_y - min_y
    margin = max(span_h, max_x - min_x) * _MARGIN_FRAC
    units_per_in = (span_h + 2 * margin) / _FIG_HEIGHT_IN

    groups = _label_groups(comps)
    sides = [_group_side(g, comps) for g in groups]
    gap = max(span_h * 0.2, 0.9 * units_per_in)
    label_space = gap + _LABEL_WIDTH_IN * units_per_in
    left = min_x - (label_space if "left" in sides else margin)
    right = max_x + (label_space if "right" in sides else margin)
    if exercise.symmetric:
        half = max(abs(left), abs(right))
        left, right = -half, half

    fig, ax = plt.subplots(figsize=((right - left) / units_per_in, _FIG_HEIGHT_IN), dpi=_DPI)
    fig.patch.set_facecolor(_PAPER)
    ax.set_position([0.0, 0.0, 1.0, 1.0])
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_facecolor(_PAPER)
    ax.set_xlim(left, right)
    ax.set_ylim(min_y - margin, max_y + margin)
    _draw_notebook_grid(ax, units_per_in)

    for comp in comps:
        _draw_component(ax, comp)

    if exercise.symmetric:
        ax.plot([0, 0], [min_y - margin * 0.6, max_y + margin * 0.6], color=_EDGE,
                linewidth=0.9, linestyle=(0, (8, 4, 2, 4)), zorder=4)
        ax.text(0.15 * units_per_in, max_y + margin * 0.55, "Y", fontsize=_LABEL_FONTSIZE,
                va="center", ha="left", color=_EDGE)

    min_gap = 0.45 * units_per_in
    for side in ("right", "left"):
        side_groups = [g for g, s in zip(groups, sides) if s == side]
        if not side_groups:
            continue
        anchors = [[_to_world(c, _anchor(c, side)) for c in g] for g in side_groups]
        ys = _spread([sum(a[1] for a in pts) / len(pts) for pts in anchors], min_gap)
        label_x = max_x + gap if side == "right" else min_x - gap
        text_dx = 0.08 * units_per_in if side == "right" else -0.08 * units_per_in
        for group, pts, ly in zip(side_groups, anchors, ys):
            for ax_x, ax_y in pts:
                ax.plot([ax_x, label_x], [ax_y, ly], color=_EDGE, linewidth=1.1, zorder=5)
                ax.plot([ax_x], [ax_y], marker="o", markersize=4, color=_EDGE, zorder=6)
            ax.text(label_x + text_dx, ly, group[0].label, fontsize=_LABEL_FONTSIZE, va="center",
                    ha="left" if side == "right" else "right", color=_EDGE, zorder=6)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=_DPI, facecolor=fig.get_facecolor())
    plt.close(fig)
    return buf.getvalue()
