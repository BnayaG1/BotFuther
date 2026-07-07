# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, List, Optional, Tuple

import numpy as np
from matplotlib.patches import Arc

import solver

from notebook.constants import _NOTEBOOK_GRID_Y, _RED


def _weaker_distributed_load_index(loads: List[dict]) -> Optional[int]:
    """אינדקס העומס המפורס החלש — רק כשיש בדיוק שניים."""
    indices = [i for i, ld in enumerate(loads) if ld.get("type") == "distributed"]
    if len(indices) != 2:
        return None
    i0, i1 = indices
    w0 = abs(float(loads[i0].get("w", 0.0) or 0.0))
    w1 = abs(float(loads[i1].get("w", 0.0) or 0.0))
    if abs(w0 - w1) < 1e-9:
        return None
    return i0 if w0 < w1 else i1


def _draw_udl_line(
    ax: Any,
    x1: float,
    x2: float,
    stem: float,
    q_label: str | None,
    *,
    y_drop: float,
    load_lw_udl_line: float,
    load_lw_udl_arr: float,
    load_lw_udl_mid: float,
    fs_body: float,
) -> None:
    """מפולג כמו לוח הקורה: קו עליון, חצים שראשם בקורה או בקו העומס."""
    y_top = max(stem - float(y_drop), stem * 0.35)
    arr_mid = (stem - float(y_drop)) * (12.0 / 48.0)
    arr_mid = max(arr_mid, stem * 0.08)
    ax.plot([x1, x2], [y_top, y_top], color=_RED, linewidth=load_lw_udl_line, zorder=5)

    def _udl_arrow(x: float, y0: float, y1: float, lw: float) -> None:
        # חשוב: shrinkA/B=0 כדי שהחץ "יתחבר" לקו העליון ולקורה בלי רווחים.
        ax.annotate(
            "",
            xy=(x, y1),
            xytext=(x, y0),
            arrowprops=dict(
                arrowstyle="-|>",
                color=_RED,
                lw=lw,
                mutation_scale=10,
                shrinkA=0,
                shrinkB=0,
            ),
            zorder=6,
        )

    _udl_arrow(x1, y_top, 0.0, load_lw_udl_arr)
    _udl_arrow(x2, y_top, 0.0, load_lw_udl_arr)
    span = x2 - x1
    if span > 1e-9:
        for frac in (0.25, 0.5, 0.75):
            xc = x1 + frac * span
            # חצים פנימיים צריכים לרדת מהקו העליון למטה (לא לעלות).
            _udl_arrow(xc, y_top, y_top - arr_mid, load_lw_udl_mid)
    if q_label:
        ax.text(
            (x1 + x2) / 2,
            y_top + 0.1,
            q_label,
            ha="center",
            va="bottom",
            fontsize=fs_body,
            color=_RED,
            fontweight="normal",
            zorder=6,
        )


def _moment_arc_thetas(
    m: float, *, moment_arc_span_deg: float, moment_arc_mid_deg: float
) -> Tuple[float, float]:
    """זוויות קשת מומנט — אורך ×1.35, רדיוס קבוע; חיובי/שלילי בחצאי מעגל נפרדים."""
    half = moment_arc_span_deg / 2.0
    # חיובי: אותה קשת כמו למטה, מוחזרת למעלה; שלילי בחצי המעגל הנגדי.
    if m >= 0:
        mid = moment_arc_mid_deg
    else:
        mid = moment_arc_mid_deg + 180.0
    t1 = mid - half
    t2 = mid + half
    if t2 >= 360.0:
        t2 -= 360.0
    if t1 < 0.0:
        t1 += 360.0
    return t1, t2


def _draw_moment_arc(
    ax: Any,
    x: float,
    m: float,
    *,
    moment_rad: float,
    moment_arc_span_deg: float,
    moment_arc_mid_deg: float,
    load_lw_moment_arc: float,
    load_lw_moment_head: float,
    fs_body: float,
    show_value: bool,
) -> None:
    """קשת ממורכזת בנקודה על הקורה; ראש חץ בסוף הקשת."""
    rad = moment_rad
    t1, t2 = _moment_arc_thetas(
        m, moment_arc_span_deg=moment_arc_span_deg, moment_arc_mid_deg=moment_arc_mid_deg
    )
    ax.add_patch(
        Arc(
            (x, 0.0),
            rad * 2,
            rad * 2,
            angle=0,
            theta1=t1,
            theta2=t2,
            color=_RED,
            lw=load_lw_moment_arc,
            zorder=5,
        )
    )
    # במומנט חיובי: מעבירים את ראש החץ לקצה השני של הקשת.
    t_head = t1 if m >= 0 else t2
    t_head_rad = np.deg2rad(t_head)
    xe = x + rad * np.cos(t_head_rad)
    ye = rad * np.sin(t_head_rad)
    tx = -rad * np.sin(t_head_rad)
    ty = rad * np.cos(t_head_rad)
    if m >= 0:
        tx = -tx
        ty = -ty
    tlen = float(np.hypot(tx, ty)) or 1.0
    ah = 0.055
    ax.annotate(
        "",
        xy=(xe, ye),
        xytext=(xe - tx / tlen * ah * 2.2, ye - ty / tlen * ah * 2.2),
        arrowprops=dict(
            arrowstyle="-|>", color=_RED, lw=load_lw_moment_head, mutation_scale=9
        ),
        zorder=6,
    )
    if show_value:
        label_y = rad + 0.14 if m >= 0 else -(rad + 0.14)
        ax.text(
            x + 0.06 * (1 if m >= 0 else -1),
            label_y,
            f"{solver.format_number(abs(m))}",
            fontsize=fs_body,
            color=_RED,
            fontweight="normal",
            ha="left" if m >= 0 else "right",
            va="bottom" if m >= 0 else "top",
            zorder=6,
        )


def _draw_loads_like_canvas(
    ax: Any,
    loads: List[dict],
    load_scale: float,
    *,
    draw_arrow: Any,
    draw_arrow_h: Any,
    notebook_load_len_mult: float,
    load_lw_point: float,
    load_lw_axial: float,
    load_lw_incl: float,
    load_lw_udl_line: float,
    load_lw_udl_arr: float,
    load_lw_udl_mid: float,
    load_lw_moment_arc: float,
    load_lw_moment_head: float,
    moment_rad: float,
    moment_arc_span_deg: float,
    moment_arc_mid_deg: float,
    fs_body: float,
    show_values: bool = False,
) -> None:
    """עומסים כמו בלוח הקורה הראשי — כל חץ מצביע אל נקודת ההצבה על הקורה (y=0)."""
    # חשוב: לא לתת לגובה החצים "להתפוצץ" כשיש שילוב עומסים גדול (למשל נקודתי+מפוזר),
    # אחרת החצים נמתחים למעלה מחוץ לאזור השרטוט במחברת.
    stem = min(load_scale * notebook_load_len_mult, 0.62)
    weaker_udl_i = _weaker_distributed_load_index(loads)
    for i, ld in enumerate(loads):
        if ld["type"] == "point":
            x = float(ld["x"])
            fy = float(ld["Fy"])
            fx = float(ld.get("Fx", 0.0))
            fy_mag = abs(fy)
            if fy_mag > 1e-6 and abs(fx) < 1e-6:
                if fy < 0:
                    # Fy<0 = עומס כלפי מטה (מהקנבס) → חץ מלמעלה אל הקורה.
                    draw_arrow(ax, x, stem, 0.0, _RED, lw=load_lw_point)
                    if show_values:
                        ax.text(
                            x + 0.04,
                            stem + 0.06,
                            f"{solver.format_number(fy_mag)}",
                            fontsize=fs_body,
                            color=_RED,
                        )
                else:
                    # Fy>0 = עומס כלפי מעלה → חץ מלמטה אל הקורה.
                    draw_arrow(ax, x, -stem, 0.0, _RED, lw=load_lw_point)
                    if show_values:
                        ax.text(
                            x + 0.04,
                            -stem - 0.06,
                            f"{solver.format_number(fy_mag)}",
                            fontsize=fs_body,
                            color=_RED,
                        )
            elif fy_mag < 1e-6 and abs(fx) >= 1e-6:
                if fx > 0:
                    draw_arrow_h(ax, x - stem, x, 0.0, _RED, lw=load_lw_axial)
                else:
                    draw_arrow_h(ax, x + stem, x, 0.0, _RED, lw=load_lw_axial)
                if show_values:
                    ax.text(
                        x + (stem / 2 if fx < 0 else -stem / 2),
                        0.08,
                        f"{solver.format_number(abs(fx))}",
                        fontsize=fs_body,
                        color=_RED,
                        ha="center",
                    )
            elif fy_mag > 1e-6:
                mag = float(np.hypot(fx, fy)) or 1.0
                tail_x = x - fx / mag * stem
                tail_y = -fy / mag * stem
                ax.annotate(
                    "",
                    xy=(x, 0.0),
                    xytext=(tail_x, tail_y),
                    arrowprops=dict(
                        arrowstyle="-|>",
                        color=_RED,
                        lw=load_lw_incl,
                        mutation_scale=10,
                    ),
                    zorder=5,
                )
                if show_values:
                    ax.text(
                        (x + tail_x) / 2,
                        tail_y + (0.08 if fy < 0 else -0.08),
                        f"{solver.format_number(mag)}",
                        fontsize=fs_body,
                        color=_RED,
                        ha="center",
                    )
            else:
                draw_arrow(ax, x, stem, 0.0, _RED, lw=load_lw_point)
        elif ld["type"] == "distributed":
            q_lbl = f"{solver.format_number(abs(float(ld['w'])))}" if show_values else None
            y_drop = _NOTEBOOK_GRID_Y if weaker_udl_i is not None and i == weaker_udl_i else 0.0
            _draw_udl_line(
                ax,
                float(ld["x1"]),
                float(ld["x2"]),
                stem,
                q_lbl,
                y_drop=y_drop,
                load_lw_udl_line=load_lw_udl_line,
                load_lw_udl_arr=load_lw_udl_arr,
                load_lw_udl_mid=load_lw_udl_mid,
                fs_body=fs_body,
            )
        elif ld["type"] == "moment":
            _draw_moment_arc(
                ax,
                float(ld["x"]),
                float(ld["M"]),
                moment_rad=moment_rad,
                moment_arc_span_deg=moment_arc_span_deg,
                moment_arc_mid_deg=moment_arc_mid_deg,
                load_lw_moment_arc=load_lw_moment_arc,
                load_lw_moment_head=load_lw_moment_head,
                fs_body=fs_body,
                show_value=show_values,
            )
        elif ld["type"] == "inclined":
            # זהה לקוד ב-beam_notebook (שומר התנהגות): מצויר כוקטור ל-y=0.
            x = float(ld["x"])
            fx = float(ld.get("Fx", 0.0))
            fy = float(ld.get("Fy", 0.0))
            mag = float(np.hypot(fx, fy)) or 1.0
            tail_x = x - fx / mag * stem
            tail_y = -fy / mag * stem
            ax.annotate(
                "",
                xy=(x, 0.0),
                xytext=(tail_x, tail_y),
                arrowprops=dict(
                    arrowstyle="-|>", color=_RED, lw=load_lw_incl, mutation_scale=10
                ),
                zorder=5,
            )
            if show_values:
                ax.text(
                    (x + tail_x) / 2,
                    tail_y + (0.08 if fy < 0 else -0.08),
                    f"{solver.format_number(mag)}",
                    fontsize=fs_body,
                    color=_RED,
                    ha="center",
                )

