# -*- coding: utf-8 -*-
"""שרטוט PNG לטיוטה — מ-dict חילוץ ל-beam_visualizer."""
from __future__ import annotations

import logging
import math
import tempfile
from pathlib import Path

from core.beam_validator import BeamExercise, BeamModel, Load, LoadType, Support, SupportType
from core.beam_visualizer import render_beam_preview

from bot.config import KN_PER_TON

log = logging.getLogger("draft_preview")


def _to_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _inclined_components(ld: dict) -> tuple[float, float]:
    fx = ld.get("Fx", ld.get("fx"))
    fy = ld.get("Fy", ld.get("fy"))
    if fx is not None and fy is not None:
        return _to_float(fx), _to_float(fy)
    mag = _to_float(ld.get("magnitude_ton", 0))
    if mag < 1e-9:
        return 0.0, 0.0
    angle = _to_float(ld.get("angle_deg", 30))
    incl_dir = str(ld.get("incl_dir", "dr") or "dr").lower()
    rad = math.radians(angle)
    fx_m = mag * math.cos(rad)
    fy_m = mag * math.sin(rad)
    if incl_dir == "dl":
        return -abs(fx_m), abs(fy_m)
    return abs(fx_m), abs(fy_m)


def _load_from_vision_dict(ld: dict) -> Load | None:
    t = str(ld.get("type", "point")).lower()
    try:
        if t == "moment":
            return Load(type=LoadType.MOMENT, x=_to_float(ld.get("x")), M=_to_float(ld.get("M", ld.get("m"))))
        if t == "inclined":
            fx, fy = _inclined_components(ld)
            return Load(type=LoadType.INCLINED, x=_to_float(ld.get("x")), Fx=fx, Fy=fy)
        if t == "distributed":
            return Load(
                type=LoadType.DISTRIBUTED,
                start_x=_to_float(ld.get("x1", ld.get("start_x"))),
                end_x=_to_float(ld.get("x2", ld.get("end_x"))),
                q=_to_float(ld.get("w", ld.get("q", ld.get("magnitude")))),
            )
        if t == "point":
            return Load(
                type=LoadType.POINT,
                x=_to_float(ld.get("x")),
                Fy=_to_float(ld.get("Fy", ld.get("fy", 0))),
                Fx=_to_float(ld.get("Fx", ld.get("fx", 0))),
            )
    except Exception as exc:
        log.debug("Skip load for preview: %s", exc)
        return None
    return None


def beam_model_from_extracted(extracted: dict) -> BeamModel | None:
    """ממיר חילוץ vision ל-BeamModel (best-effort לשרטוט)."""
    beam = extracted.get("beam") if isinstance(extracted.get("beam"), dict) else {}
    try:
        L = _to_float(beam.get("L"))
    except (TypeError, ValueError):
        return None
    if L <= 0:
        return None

    supports: list[Support] = []
    for raw in beam.get("supports") or []:
        if not isinstance(raw, dict):
            continue
        st = str(raw.get("type", "pin")).lower()
        try:
            stype = SupportType(st)
        except ValueError:
            stype = SupportType.PIN
        supports.append(
            Support(
                label=str(raw.get("label", "?") or "?"),
                type=stype,
                x=_to_float(raw.get("x")),
            )
        )
    if not supports:
        supports = [
            Support(label="A", type=SupportType.PIN, x=0.0),
            Support(label="B", type=SupportType.ROLLER, x=L),
        ]

    loads: list[Load] = []
    for raw in beam.get("loads") or []:
        if not isinstance(raw, dict):
            continue
        item = _load_from_vision_dict(raw)
        if item is not None:
            loads.append(item)

    return BeamModel(L=L, supports=supports, loads=loads)


def render_extracted_preview(extracted: dict, output_path: str | Path) -> Path | None:
    """מצייר PNG מחילוץ. None אם אין מספיק נתונים."""
    model = beam_model_from_extracted(extracted)
    if model is None:
        return None
    try:
        return render_beam_preview(BeamExercise(beam=model), output_path)
    except Exception as exc:
        log.warning("Preview render failed: %s", exc)
        return None


def _reactions_from_solved(solved: dict) -> dict[str, float]:
    result = solved.get("result") if isinstance(solved.get("result"), dict) else {}
    raw = result.get("reactions_ton") or result.get("reactions_kN") or {}
    out: dict[str, float] = {}
    for key in ("R_Ax", "R_Ay", "R_Bx", "R_By"):
        if key not in raw:
            continue
        try:
            val = float(raw[key])
        except (TypeError, ValueError):
            continue
        if "reactions_kN" in result and "reactions_ton" not in result:
            val /= KN_PER_TON
        out[key] = val
    return out


def render_solve_preview(
    extracted: dict,
    solved: dict,
    output_path: str | Path,
) -> Path | None:
    """PNG של קורה + עומסים + ריאקציות מחושבות."""
    model = beam_model_from_extracted(extracted)
    if model is None:
        return None
    reactions = _reactions_from_solved(solved)
    if not reactions:
        return None
    try:
        return render_beam_preview(
            BeamExercise(beam=model),
            output_path,
            reactions=reactions,
            title="Beam + reactions",
        )
    except Exception as exc:
        log.warning("Solve preview render failed: %s", exc)
        return None


def render_solve_preview_temp(extracted: dict, solved: dict) -> Path | None:
    """PNG זמני עם ריאקציות — המתקשר אחראי למחיקה."""
    fd, name = tempfile.mkstemp(suffix="_beam_solve.png")
    import os

    os.close(fd)
    path = Path(name)
    result = render_solve_preview(extracted, solved, path)
    if result is None:
        path.unlink(missing_ok=True)
    return result


def render_extracted_preview_temp(extracted: dict) -> Path | None:
    """יוצר PNG זמני — המתקשר אחראי למחיקה."""
    fd, name = tempfile.mkstemp(suffix="_beam_preview.png")
    import os

    os.close(fd)
    path = Path(name)
    result = render_extracted_preview(extracted, path)
    if result is None:
        path.unlink(missing_ok=True)
    return result
