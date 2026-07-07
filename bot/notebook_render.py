# -*- coding: utf-8 -*-
"""ייצוא PNG של פתרון מחברת מלא — מחילוץ + חישוב קיים."""
from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from bot.config import KN_PER_TON
from bot.engineering import ui_loads_to_solver
from bot.vision import finalize_beam_extraction, resolve_beam_support_geometry, vision_loads_to_tool_loads

log = logging.getLogger("notebook_render")


def _solver_loads_from_extracted(extracted: dict) -> list[dict]:
    """עומסים בקנה מידה טון — תואם reactions_ton ותווית t במחברת."""
    beam = extracted.get("beam") if isinstance(extracted.get("beam"), dict) else {}
    raw = beam.get("loads") or []
    tool = vision_loads_to_tool_loads(
        [dict(ld) for ld in raw if isinstance(ld, dict)]
    )
    return ui_loads_to_solver(tool, in_tons=True)


def _reactions_ton_from_solved(solved: dict) -> tuple[float, float, float, float]:
    result = solved.get("result") if isinstance(solved.get("result"), dict) else {}
    raw = result.get("reactions_ton") or result.get("reactions_kN") or {}
    in_kn = "reactions_kN" in result and "reactions_ton" not in result

    def _read(key: str) -> float:
        if key not in raw:
            return 0.0
        try:
            val = float(raw[key])
        except (TypeError, ValueError):
            return 0.0
        return val / KN_PER_TON if in_kn else val

    return _read("R_Ax"), _read("R_Ay"), _read("R_Bx"), _read("R_By")


def render_notebook_png_bytes(extracted: dict, solved: dict) -> bytes | None:
    """בונה PNG של דף מחברת מלא. None אם אין מספיק נתונים."""
    if not (solved or {}).get("result"):
        return None
    extracted = finalize_beam_extraction(extracted)
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

    tool_name = str(solved.get("tool_name", "")).strip()
    try:
        import beam_notebook
        import solver

        if tool_name == "beam_solve_cantilever":
            result = solver.solve_cantilever_beam(loads, L)
            _, _, pdf_bytes = beam_notebook.build_cantilever_page_html(
                loads, L, result, wide_layout=True
            )
            return beam_notebook._pdf_to_png_bytes(
                pdf_bytes, dpi=beam_notebook._BOT_EXPORT_DPI
            )

        support_mode, ra_pos, rb_pos = resolve_beam_support_geometry(beam)
        if support_mode == "cantilever":
            result = solver.solve_cantilever_beam(loads, L)
            _, _, pdf_bytes = beam_notebook.build_cantilever_page_html(
                loads, L, result, wide_layout=True
            )
            return beam_notebook._pdf_to_png_bytes(
                pdf_bytes, dpi=beam_notebook._BOT_EXPORT_DPI
            )

        ra_x, ra_y, rb_x, rb_y = _reactions_ton_from_solved(solved)
        if abs(ra_x) + abs(ra_y) + abs(rb_x) + abs(rb_y) < 1e-9:
            ra_x, ra_y, rb_x, rb_y = solver.compute_reactions(
                loads, L, ra_pos, rb_pos
            )
        _, _, pdf_bytes = beam_notebook.build_page_html(
            loads, L, ra_pos, rb_pos, ra_x, ra_y, rb_x, rb_y, wide_layout=True
        )
        return beam_notebook._pdf_to_png_bytes(
            pdf_bytes, dpi=beam_notebook._BOT_EXPORT_DPI
        )
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
