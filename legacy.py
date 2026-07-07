# -*- coding: utf-8 -*-
"""Legacy notebook APIs kept for backwards compatibility (Streamlit / old downloads)."""
from __future__ import annotations

from typing import Any, Dict, List

import matplotlib.pyplot as plt
import numpy as np

import solver

from notebook.constants import _BLUE, _GREEN, _PAPER, _RED, _U_FORCE, _U_MOMENT


def build_diagram_figure(
    L: float,
    loads: List[dict],
    ra_pos: float,
    rb_pos: float,
    ra_x: float,
    ra_y: float,
    rb_x: float,
    rb_y: float,
    *,
    notebook_mpl_rc: Any,
    draw_beam_schematic: Any,
    beam_x_pad: Any,
    station_labels_fn: Any,
    plot_n_on_beam: Any,
    plot_q_on_beam: Any,
    plot_m_on_beam: Any,
    diagram_titles: Any,
) -> Any:
    """תמונה משולבת להורדה (קורה + דיאגרמות)."""
    notebook_mpl_rc()
    fig = plt.figure(figsize=(7.8, 6.5), facecolor=_PAPER)
    gs = fig.add_gridspec(
        4, 1, height_ratios=[0.95, 0.88, 0.88, 0.88], hspace=0.12, left=0.14, right=0.995, top=0.98, bottom=0.06
    )
    ax_beam = fig.add_subplot(gs[0])
    ax_beam.set_facecolor(_PAPER)
    draw_beam_schematic(ax_beam, L, loads, ra_pos, rb_pos, ra_x, ra_y, rb_y)
    positions = solver.critical_x_positions(loads, L, ra_pos, rb_pos)
    xs = solver.beam_plot_x_coords(L, positions)
    moments = np.array([solver.bending_moment(x, loads, ra_y, rb_y, ra_pos, rb_pos) for x in xs])
    shears = np.array([solver.shear_force(x, loads, ra_y, rb_y, ra_pos, rb_pos) for x in xs])
    normals = np.array([solver.normal_force(x, loads, ra_x, ra_pos) for x in xs])
    Lf = float(L)
    x_pad = beam_x_pad(Lf)
    crit = station_labels_fn(loads, L, ra_pos, rb_pos)

    ax_n = fig.add_subplot(gs[1])
    plot_n_on_beam(ax_n, xs, normals, Lf, x_pad, crit, transparent=False, paper=True)
    diagram_titles(fig, ax_n, "N(x)", _U_FORCE, _GREEN, Lf=Lf)

    ax_v = fig.add_subplot(gs[2], sharex=ax_n)
    plot_q_on_beam(ax_v, xs, shears, Lf, x_pad, crit, transparent=False, paper=True)
    diagram_titles(fig, ax_v, "Q(x)", _U_FORCE, _BLUE, Lf=Lf)

    ax_m = fig.add_subplot(gs[3], sharex=ax_n)
    plot_m_on_beam(ax_m, xs, moments, Lf, x_pad, crit, transparent=False, paper=True)
    diagram_titles(fig, ax_m, "M(x)", _U_MOMENT, _RED, Lf=Lf)

    return fig


def build_calc_html(
    loads: List[dict],
    L: float,
    ra_pos: float,
    rb_pos: float,
    ra_x: float,
    ra_y: float,
    rb_x: float,
    rb_y: float,
    *,
    equilibrium_sections_fn: Any,
    values_at_stations_fn: Any,
    nb_step_html_fn: Any,
    sym_sigma_fn: Any,
    join_eq_value_lines_minus_only_fn: Any,
    nb_step_fn: Any,
    esc_num_fn: Any,
    nb_answer_box_fn: Any,
    sym_delta_fn: Any,
    moment_handwriting_note_fn: Any,
    shear_zero_card_html_fn: Any,
    shear_zero_notes_fn: Any,
) -> str:
    eq = equilibrium_sections_fn(loads, ra_pos, rb_pos, ra_x, ra_y, rb_y)
    rows = values_at_stations_fn(loads, L, ra_pos, rb_pos, ra_x, ra_y, rb_x, rb_y)
    s = eq["sums"]
    parts: List[str] = [
        '<div class="nb-col-calc nb-flow">',
        '<div class="nb-block">',
        '<h2 class="nb-calc-title">מציאת ריאקציות — כוחות תגובה בסמכים</h2>',
    ]
    parts.append(nb_step_html_fn(f"{sym_sigma_fn()}F<sub>x</sub> = 0", "nb-eq nb-eq-start"))
    if eq["fx_lines"]:
        parts.append(
            nb_step_fn(
                join_eq_value_lines_minus_only_fn(eq["fx_lines"], float(s["sum_fx"])),
                "nb-eq",
            )
        )
    parts.append(
        nb_step_fn(
            f"Ax = −ΣFx = −({solver.format_number(s['sum_fx'])}) = "
            f"{solver.format_number(ra_x)} {_U_FORCE}",
            "nb-eq",
        )
    )
    if abs(ra_x) > 1e-9:
        parts.append(nb_answer_box_fn(f"Ax = {esc_num_fn(ra_x)} {_U_FORCE}", ans_name="Ax"))
    parts.append(nb_step_fn(""))
    parts.append(nb_step_html_fn(f"{sym_sigma_fn()}M<sub>A</sub> = 0", "nb-eq nb-eq-start"))
    parts.append(nb_step_fn("סכום המומנטים סביב A:", "nb-sub nb-black"))
    if eq["ma_lines"]:
        parts.append(
            nb_step_fn(
                join_eq_value_lines_minus_only_fn(
                    eq["ma_lines"], float(s["moment_about_ra"])
                ),
                "nb-eq",
            )
        )
    parts.append(
        nb_step_fn(
            f"By = {solver.format_number(s['moment_about_ra'])}/{solver.format_number(eq['arm_b'])} "
            f"= {solver.format_number(rb_y)} {_U_FORCE}",
            "nb-eq",
        )
    )
    parts.append(nb_answer_box_fn(f"By = {esc_num_fn(rb_y)} {_U_FORCE}", ans_name="By"))
    parts.append(nb_step_fn(""))
    parts.append(nb_step_html_fn(f"{sym_sigma_fn()}M<sub>B</sub> = 0", "nb-eq nb-eq-start"))
    parts.append(nb_step_fn("סכום המומנטים סביב B:", "nb-sub nb-black"))
    if eq["mb_lines"]:
        parts.append(
            nb_step_fn(
                join_eq_value_lines_minus_only_fn(
                    eq["mb_lines"], float(s["moment_about_rb"])
                ),
                "nb-eq",
            )
        )
    parts.append(
        nb_step_fn(
            f"Ay = −({solver.format_number(s['moment_about_rb'])}) / "
            f"({solver.format_number(eq['arm_a'])}) = {solver.format_number(ra_y)} {_U_FORCE}",
            "nb-eq",
        )
    )
    parts.append(nb_answer_box_fn(f"Ay = {esc_num_fn(ra_y)} {_U_FORCE}", ans_name="Ay"))
    parts.append(
        nb_step_html_fn(
            f"{sym_sigma_fn()}F<sub>y</sub> + Ay + By = {solver.format_number(eq['fy_check'])}",
            "nb-eq",
        )
    )
    parts.append("</div>")

    parts.append('<div class="nb-block">')
    parts.append('<p class="nb-block-label nb-lbl-green">בדיקות חתך — כוח צירי (Δ)</p>')
    for r in rows:
        lab = r["label"]
        n_val = float(r["N"])
        n_l = float(r.get("N_left", n_val))
        n_r = float(r.get("N_right", n_val))
        if abs(n_l - n_r) > 1e-4:
            parts.append(
                nb_step_html_fn(
                    f"{sym_delta_fn()}<sub>{lab}</sub>: N<sub>L</sub> = {solver.format_number(n_l)}, "
                    f"N<sub>R</sub> = {solver.format_number(n_r)} {_U_FORCE}",
                    "nb-delta",
                )
            )
        else:
            parts.append(
                nb_step_html_fn(
                    f"{sym_delta_fn()}<sub>{lab}</sub> — N<sub>{lab}</sub> = "
                    f"{solver.format_number(n_val)} {_U_FORCE}",
                    "nb-delta",
                )
            )

    parts.append('<p class="nb-block-label nb-lbl-blue">גזירה Q</p>')
    for r in rows:
        parts.append(
            nb_step_html_fn(
                f"Q<sub>{r['label']}</sub> = {solver.format_number(r['Q'])} {_U_FORCE}",
                "nb-shear",
            )
        )

    parts.append('<p class="nb-block-label nb-lbl-red">מומנטים M</p>')
    for r in rows:
        parts.append(
            nb_step_html_fn(
                f"M<sub>{r['label']}</sub> = {solver.format_number(r['M'])} {_U_MOMENT}",
                "nb-moment",
            )
        )
    parts.append(moment_handwriting_note_fn())
    xzero = shear_zero_card_html_fn(loads, L, ra_pos, rb_pos, ra_y, rb_y)
    if xzero:
        parts.append(xzero)
    else:
        for zn in shear_zero_notes_fn(loads, L, ra_pos, rb_pos, ra_y, rb_y):
            parts.append(nb_step_fn(zn, "nb-shear"))
    parts.append("</div></div>")
    return "\n".join(parts)
