# -*- coding: utf-8 -*-
"""JSON חילוץ ↔ טקסט לעריכה (human-in-the-loop)."""
from __future__ import annotations

import math
import re
from typing import Any



def _labeled_x_map(beam: dict) -> dict[str, float]:
    out: dict[str, float] = {}
    for pt in beam.get("labeled_points") or []:
        if not isinstance(pt, dict):
            continue
        lbl = str(pt.get("label", "")).strip().upper()
        if not lbl or lbl in ("START", "ORIGIN"):
            continue
        try:
            out[lbl] = float(pt.get("x", 0))
        except (TypeError, ValueError):
            continue
    return out


def x_from_left_end(
    beam: dict,
    x: float | None,
    *,
    label: str = "",
    support: dict | None = None,
    load: dict | None = None,
) -> float:
    """x כמרחק מקצה שמאל — לפי תווית על שרשרת המידות אם קיימת."""
    if isinstance(support, dict) and support.get("_user_x"):
        try:
            return float(support.get("x", x or 0))
        except (TypeError, ValueError):
            return 0.0
    if isinstance(load, dict) and load.get("_user_x"):
        try:
            return float(load.get("x", x or 0))
        except (TypeError, ValueError):
            return 0.0
    labeled = _labeled_x_map(beam)
    lbl = str(label or "").strip().upper()
    if lbl and lbl in labeled:
        return labeled[lbl]
    try:
        return float(x or 0)
    except (TypeError, ValueError):
        return 0.0


def set_support_x_user(
    beam: dict,
    x: float,
    *,
    label: str = "",
    index: int | None = None,
) -> None:
    """עדכון ידני של מיקום סמך — מסנכרן labeled_points ושומר מפני דריסה בנורמליזציה."""
    lbl = str(label or "").strip().upper()
    xf = float(x)
    supports = beam.get("supports")
    touched: list[dict] = []
    if isinstance(supports, list):
        if index is not None and 0 <= index < len(supports):
            sup = supports[index]
            if isinstance(sup, dict):
                touched.append(sup)
        if lbl:
            for sup in supports:
                if not isinstance(sup, dict):
                    continue
                if str(sup.get("label", "")).strip().upper() == lbl and sup not in touched:
                    touched.append(sup)
        for sup in touched:
            sup["x"] = xf
            sup["_user_x"] = True
            sup.pop("dist_from_left_m", None)
            sup.pop("dist_from_right_m", None)
            if lbl:
                sup["label"] = lbl

    if not lbl:
        return
    points = beam.get("labeled_points")
    if not isinstance(points, list):
        points = []
    updated: list[dict] = []
    found = False
    for pt in points:
        if not isinstance(pt, dict):
            continue
        plbl = str(pt.get("label", "")).strip().upper()
        if plbl == lbl:
            updated.append({"label": lbl, "x": xf})
            found = True
        else:
            updated.append(dict(pt))
    if not found:
        updated.append({"label": lbl, "x": xf})
    beam["labeled_points"] = updated


def set_beam_L_user(beam: dict, L: float) -> None:
    """עדכון ידני של אורך קורה — מונע דריסה בנורמליזציה."""
    beam["L"] = max(0.1, float(L))
    beam["_user_L"] = True


def set_load_x_user(ld: dict, x: float) -> None:
    """עדכון ידני של מיקום עומס — מונע דריסה מ-label_at בנורמליזציה."""
    ld["x"] = float(x)
    ld["_user_x"] = True
    ld.pop("label_at", None)


def set_distributed_span_user(ld: dict, x1: float, x2: float) -> None:
    """עדכון ידני של טווח עומס מפורס — מונע דריסה מ-from_label/to_label בנורמליזציה."""
    xf1 = float(x1)
    xf2 = float(x2)
    if xf2 < xf1:
        xf1, xf2 = xf2, xf1
    ld["type"] = "distributed"
    ld["x1"] = xf1
    ld["x2"] = xf2
    ld["start_x"] = xf1
    ld["end_x"] = xf2
    ld["_user_span"] = True
    ld.pop("from_label", None)
    ld.pop("to_label", None)


def sync_beam_distributed_loads(beam: dict) -> None:
    """מסנכרן distributed_loads[] מ-loads[] לאחר עריכת טווח ידנית."""
    loads = beam.get("loads") or []
    dist_in_loads = [
        ld
        for ld in loads
        if isinstance(ld, dict) and str(ld.get("type", "")).lower() == "distributed"
    ]
    if not dist_in_loads:
        return
    raw = beam.get("distributed_loads")
    if not isinstance(raw, list):
        raw = []
    synced: list[dict] = []
    for i, ld in enumerate(dist_in_loads):
        base = dict(raw[i]) if i < len(raw) and isinstance(raw[i], dict) else {}
        try:
            x1 = float(ld.get("x1", ld.get("start_x", base.get("start_x", 0))))
            x2 = float(ld.get("x2", ld.get("end_x", base.get("end_x", 0))))
        except (TypeError, ValueError):
            continue
        w = ld.get("w", ld.get("magnitude", base.get("magnitude", 0)))
        try:
            mag = float(w)
        except (TypeError, ValueError):
            mag = float(base.get("magnitude", 0) or 0)
        item: dict = {
            **base,
            "start_x": x1,
            "end_x": x2,
            "magnitude": mag,
            "shape": str(ld.get("shape", base.get("shape", "rectangular"))).lower(),
        }
        item.pop("_draft_new", None)
        item.pop("_user_span", None)
        if ld.get("_draft_new"):
            item["_draft_new"] = True
        if ld.get("_user_span"):
            item["_user_span"] = True
        synced.append(item)
    beam["distributed_loads"] = synced


def distributed_span_from_left(ld: dict, beam: dict) -> tuple[float, float]:
    """x1/x2 כמרחק מקצה שמאל — מכבד עריכה ידנית."""
    if ld.get("_user_span"):
        try:
            return float(ld.get("x1", 0)), float(ld.get("x2", 0))
        except (TypeError, ValueError):
            return 0.0, 0.0
    from_lbl = str(ld.get("from_label", "") or "")
    to_lbl = str(ld.get("to_label", "") or "")
    x1 = x_from_left_end(beam, ld.get("x1", ld.get("start_x", 0)), label=from_lbl)
    x2 = x_from_left_end(beam, ld.get("x2", ld.get("end_x", 0)), label=to_lbl)
    return x1, x2


def _fmt_num(value: float, *, max_decimals: int = 2) -> str:
    """עיגול לתצוגה — עד 2 ספרות אחרי הנקודה (9.998 → 10, 2.91 נשאר)."""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return "0"
    if not math.isfinite(num):
        return "0"
    if abs(num - round(num)) < 0.005:
        return str(int(round(num)))
    rounded = round(num, max_decimals)
    text = f"{rounded:.{max_decimals}f}".rstrip("0").rstrip(".")
    return text or "0"


def _inclined_mag(ld: dict) -> float:
    mag = ld.get("magnitude_ton")
    if mag is not None:
        try:
            return abs(float(mag))
        except (TypeError, ValueError):
            pass
    fx = float(ld.get("Fx", ld.get("fx", 0.0)) or 0.0)
    fy = float(ld.get("Fy", ld.get("fy", 0.0)) or 0.0)
    return math.hypot(fx, fy)


def _inclined_dir(ld: dict) -> str:
    d = str(ld.get("incl_dir", "") or "").lower()
    if d in ("dl", "dr"):
        return d
    fx = float(ld.get("Fx", ld.get("fx", 0.0)) or 0.0)
    return "dl" if fx < 0 else "dr"


def _recompute_inclined_components(
    magnitude_ton: float,
    angle_deg: float = 30.0,
    *,
    incl_dir: str = "dr",
) -> tuple[float, float]:
    """Fx,Fy from magnitude+angle; incl_dir dl=↙ (Fx<0), dr=↘ (Fx>0)."""
    rad = math.radians(angle_deg)
    fx_mag = magnitude_ton * math.cos(rad)
    fy_mag = magnitude_ton * math.sin(rad)
    if str(incl_dir).lower() == "dl":
        return -abs(fx_mag), abs(fy_mag)
    return abs(fx_mag), abs(fy_mag)


def _sync_inclined_components(ld: dict) -> dict:
    """מעדכן Fx/Fy לפי mag+angle+dir — כדי ש-finalize לא ידרוס זווית מעריכה."""
    out = dict(ld)
    mag = float(out.get("magnitude_ton", 0.0) or 0.0)
    if mag < 1e-6:
        fx = float(out.get("Fx", out.get("fx", 0.0)) or 0.0)
        fy = float(out.get("Fy", out.get("fy", 0.0)) or 0.0)
        mag = math.hypot(fx, fy)
    angle = float(out.get("angle_deg", 30.0) or 30.0)
    incl_dir = _inclined_dir(out)
    fx, fy = _recompute_inclined_components(mag, angle, incl_dir=incl_dir)
    out["Fx"] = fx
    out["Fy"] = fy
    out["magnitude_ton"] = mag
    out["incl_dir"] = incl_dir
    out["angle_deg"] = angle
    return out

