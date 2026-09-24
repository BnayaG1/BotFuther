# -*- coding: utf-8 -*-
"""ייצוא PNG של פתרון מחברת מלא — מחילוץ + חישוב קיים."""
from __future__ import annotations

import io
import logging
import os
import tempfile
from pathlib import Path

from bot.engineering import ui_loads_to_solver
from bot.vision import finalize_beam_extraction, resolve_beam_support_geometry, vision_loads_to_tool_loads

log = logging.getLogger("notebook_render")


def _prepare_extracted_for_render(extracted: dict) -> dict:
    """מכין extracted לרינדור מחברת/שרטוט.

    תרגילי מחולל מדויקים — ``finalize_beam_extraction`` משחית בהם סמכים.
    מדלגים עליו כשמסומן במטא (כמו ``_bank_extracted_for_solve`` ב־router).
    """
    data = extracted if isinstance(extracted, dict) else {}
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    skip = bool(meta.get("skip_vision_normalize")) or meta.get("source") == "exercise_generator"
    if skip:
        return data
    return finalize_beam_extraction(data, merge_nearby_point_loads=False)


def _solver_loads_from_extracted(extracted: dict) -> list[dict]:
    """עומסים בקנה מידה טון — תואם reactions_ton ותווית t במחברת."""
    beam = extracted.get("beam") if isinstance(extracted.get("beam"), dict) else {}
    raw = beam.get("loads") or []
    tool = vision_loads_to_tool_loads(
        [dict(ld) for ld in raw if isinstance(ld, dict)]
    )
    return ui_loads_to_solver(tool, in_tons=True)


def render_notebook_png_bytes(extracted: dict, solved: dict) -> bytes | None:
    """PNG של פתרון מחברת."""
    try:
        from notebook_solution import render_png_bytes

        return render_png_bytes(extracted, solved)
    except Exception as exc:
        log.warning("Notebook render failed: %s", exc)
        return None


def render_notebook_png_temp(extracted: dict, solved: dict) -> Path | None:
    """PNG זמני של מחברת — המתקשר אחראי למחיקה."""
    png_bytes = render_notebook_png_bytes(extracted, solved)
    if not png_bytes:
        return None
    fd, name = tempfile.mkstemp(suffix="_beam_notebook.png")
    os.close(fd)
    path = Path(name)
    try:
        path.write_bytes(png_bytes)
    except OSError as exc:
        log.warning("Notebook temp write failed: %s", exc)
        path.unlink(missing_ok=True)
        return None
    return path


def render_exercise_problem_png_bytes(extracted: dict) -> bytes | None:
    """PNG של שרטוט התרגיל בלבד (קורה + עומסים) — בלי ריאקציות/דיאגרמות.

    לשימוש לפני שהמשתמש בחר מצב פתרון (מציג את השאלה בלבד, לא את התשובה).
    """
    extracted = _prepare_extracted_for_render(extracted)
    beam = extracted.get("beam") if isinstance(extracted.get("beam"), dict) else {}
    try:
        L = float(beam.get("L", 0))
    except (TypeError, ValueError):
        return None
    if L <= 0:
        return None

    loads = _solver_loads_from_extracted(extracted)
    if not loads:
        return None

    try:
        import matplotlib.pyplot as plt

        from exercise_generator.problem_figure import build_problem_figure

        support_mode, ra_pos, rb_pos = resolve_beam_support_geometry(beam)
        if support_mode == "cantilever":
            fig = build_problem_figure(L, loads, mode="cantilever", ra_pos=ra_pos)
        else:
            fig = build_problem_figure(
                L, loads, mode="simply_supported", ra_pos=ra_pos, rb_pos=rb_pos
            )
        buf = io.BytesIO()
        fig.savefig(
            buf,
            format="png",
            dpi=150,
            transparent=True,
            facecolor="none",
            bbox_inches="tight",
            pad_inches=0.04,
        )
        plt.close(fig)
        return buf.getvalue()
    except Exception as exc:
        log.warning("Exercise problem render failed: %s", exc)
        return None


def render_exercise_problem_png_temp(extracted: dict) -> Path | None:
    """PNG זמני של שרטוט התרגיל — המתקשר אחראי למחיקה."""
    png_bytes = render_exercise_problem_png_bytes(extracted)
    if not png_bytes:
        return None
    fd, name = tempfile.mkstemp(suffix="_exercise_problem.png")
    os.close(fd)
    path = Path(name)
    try:
        path.write_bytes(png_bytes)
    except OSError as exc:
        log.warning("Exercise problem temp write failed: %s", exc)
        path.unlink(missing_ok=True)
        return None
    return path
