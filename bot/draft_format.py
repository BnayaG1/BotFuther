# -*- coding: utf-8 -*-
"""JSON חילוץ ↔ טקסט לעריכה (human-in-the-loop)."""
from __future__ import annotations

import math
import re
from typing import Any

_KV_RE = re.compile(r"(\w+)\s*=\s*(-?[\d.]+|[\w]+)", re.IGNORECASE)
_L_RE = re.compile(r"^L\s*=\s*([\d.]+)\s*$", re.IGNORECASE)
_SUPPORT_RE = re.compile(
    r"^support\s+(\d+)\s*:\s*(\w+)\s+(pin|roller|fixed)\s+x\s*=\s*([\d.]+)",
    re.IGNORECASE,
)
_LOAD_RE = re.compile(r"^load\s+(\d+)\s*:\s*(.+)$", re.IGNORECASE)


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


def _load_to_draft_line(idx: int, ld: dict) -> str:
    t = str(ld.get("type", "point")).lower()
    parts: list[str] = [f"load {idx}:"]

    if t == "moment":
        parts.append("moment")
        parts.append(f"x={_fmt_num(float(ld.get('x', 0)))}")
        parts.append(f"M={_fmt_num(float(ld.get('M', ld.get('m', 0))))}")
    elif t == "inclined":
        parts.append("inclined")
        parts.append(f"x={_fmt_num(float(ld.get('x', 0)))}")
        parts.append(f"mag={_fmt_num(_inclined_mag(ld))}")
        parts.append(f"angle={_fmt_num(float(ld.get('angle_deg', 30)))}")
        parts.append(f"dir={_inclined_dir(ld)}")
    elif t == "distributed":
        x1 = ld.get("x1", ld.get("start_x", 0))
        x2 = ld.get("x2", ld.get("end_x", 0))
        w = ld.get("w", ld.get("q", ld.get("magnitude", 0)))
        parts.append("distributed")
        parts.append(f"x1={_fmt_num(float(x1))}")
        parts.append(f"x2={_fmt_num(float(x2))}")
        parts.append(f"w={_fmt_num(float(w))}")
    elif t == "point":
        parts.append("point")
        parts.append(f"x={_fmt_num(float(ld.get('x', 0)))}")
        fy = ld.get("Fy", ld.get("fy"))
        fx = ld.get("Fx", ld.get("fx"))
        if fy is not None and abs(float(fy)) > 1e-9:
            parts.append(f"Fy={_fmt_num(float(fy))}")
        if fx is not None and abs(float(fx)) > 1e-9:
            parts.append(f"Fx={_fmt_num(float(fx))}")
    else:
        parts.append(t)
        if ld.get("x") is not None:
            parts.append(f"x={_fmt_num(float(ld.get('x', 0)))}")

    label = str(ld.get("label_at", "") or "").strip()
    if label:
        parts.append(f"label={label}")
    return " ".join(parts)


def extracted_to_draft_text(extracted: dict) -> str:
    """ממיר חילוץ לטקסט שניתן לערוך."""
    beam = extracted.get("beam") if isinstance(extracted.get("beam"), dict) else {}
    lines = [
        "*טיוטה — בדוק וערוך:*",
        "",
        f"L={_fmt_num(float(beam.get('L', 0)))}",
        "",
    ]

    supports = beam.get("supports") or []
    if supports:
        lines.append("*סמכים:*")
        for idx, sup in enumerate(supports, 1):
            if not isinstance(sup, dict):
                continue
            label = str(sup.get("label", idx)).strip()
            st = str(sup.get("type", "pin")).lower()
            x = _fmt_num(float(sup.get("x", 0)))
            lines.append(f"support {idx}: {label} {st} x={x}")
        lines.append("")

    loads = beam.get("loads") or []
    if loads:
        lines.append("*עומסים:*")
        for idx, ld in enumerate(loads, 1):
            if isinstance(ld, dict):
                lines.append(_load_to_draft_line(idx, ld))
        lines.append("")

    lines.extend(
        [
            "---",
            "תיקון קצר: `L=12` או `load 3 dir=dl`",
            "או העתק/ערוך את כל הטיוטה למעלה",
            "שלח *אישור* לחישוב ריאקציות",
        ]
    )
    return "\n".join(lines)


def _parse_kv_blob(blob: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, val in _KV_RE.findall(blob):
        out[key.lower()] = val
    return out


def _parse_load_line(idx: int, blob: str) -> dict[str, Any]:
    kv = _parse_kv_blob(blob)
    kind = blob.strip().split()[0].lower() if blob.strip() else "point"
    if kind not in ("moment", "inclined", "distributed", "point"):
        kind = kv.get("type", "point")

    ld: dict[str, Any] = {"type": kind}
    if "x" in kv:
        ld["x"] = float(kv["x"])
    if "label" in kv:
        ld["label_at"] = kv["label"].upper()

    if kind == "moment":
        ld["M"] = float(kv.get("m", 0))
    elif kind == "inclined":
        ld["x"] = float(kv.get("x", 0))
        ld["magnitude_ton"] = float(kv.get("mag", kv.get("magnitude", 0)))
        ld["angle_deg"] = float(kv.get("angle", 30))
        ld["incl_dir"] = kv.get("dir", "dr").lower()
    elif kind == "distributed":
        ld["x1"] = float(kv.get("x1", 0))
        ld["x2"] = float(kv.get("x2", 0))
        ld["w"] = float(kv.get("w", kv.get("q", 0)))
        ld["shape"] = "rectangular"
        ld["_user_span"] = True
        ld.pop("from_label", None)
        ld.pop("to_label", None)
    elif kind == "point":
        if "fy" in kv:
            ld["Fy"] = float(kv["fy"])
        if "fx" in kv:
            ld["Fx"] = float(kv["fx"])
    ld["_draft_idx"] = idx
    return ld


def parse_draft_text(text: str) -> dict[str, Any] | None:
    """מפרס טיוטה מלאה. None אם אין מספיק מבנה."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("---")]
    if not lines:
        return None

    parsed: dict[str, Any] = {"L": None, "supports": [], "loads": []}
    found_structure = False

    for line in lines:
        if line.startswith("#") or line.startswith("📋") or line.startswith("*"):
            continue
        m_l = _L_RE.match(line)
        if m_l:
            parsed["L"] = float(m_l.group(1))
            found_structure = True
            continue
        m_sup = _SUPPORT_RE.match(line)
        if m_sup:
            parsed["supports"].append(
                {
                    "label": m_sup.group(2).upper(),
                    "type": m_sup.group(3).lower(),
                    "x": float(m_sup.group(4)),
                }
            )
            found_structure = True
            continue
        m_load = _LOAD_RE.match(line)
        if m_load:
            parsed["loads"].append(_parse_load_line(int(m_load.group(1)), m_load.group(2)))
            found_structure = True

    if not found_structure or parsed["L"] is None:
        return None
    return parsed


def build_extracted_from_draft(parsed: dict[str, Any], base: dict | None = None) -> dict:
    """בונה dict חילוץ מטיוטה מפורשת."""
    out = dict(base) if isinstance(base, dict) else {}
    out["exercise_type"] = "beam"
    beam = dict(out.get("beam") or {}) if isinstance(out.get("beam"), dict) else {}
    beam["L"] = float(parsed["L"])
    beam["_user_L"] = True
    supports = []
    for sup in parsed.get("supports") or []:
        if not isinstance(sup, dict):
            continue
        item = dict(sup)
        item["_user_x"] = True
        supports.append(item)
    beam["supports"] = supports
    for idx, sup in enumerate(supports):
        if isinstance(sup, dict):
            set_support_x_user(
                beam,
                float(sup.get("x", 0)),
                label=str(sup.get("label", "")),
                index=idx,
            )
    loads = []
    for ld in parsed.get("loads") or []:
        item = {k: v for k, v in ld.items() if k != "_draft_idx"}
        loads.append(item)
    beam["loads"] = loads
    out["beam"] = beam
    return out


def apply_patch_text(extracted: dict, text: str) -> tuple[dict, list[str]]:
    """
    מיישם תיקונים קצרים על extracted קיים.
    Returns: (extracted מעודכן, הודעות שגיאה)
    """
    errors: list[str] = []
    beam = dict(extracted.get("beam") or {})
    loads = [dict(ld) for ld in (beam.get("loads") or []) if isinstance(ld, dict)]
    supports = [dict(s) for s in (beam.get("supports") or []) if isinstance(s, dict)]
    changed = False

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("---"):
            continue

        m_l = _L_RE.match(line)
        if m_l:
            set_beam_L_user(beam, float(m_l.group(1)))
            changed = True
            continue

        m_sup = _SUPPORT_RE.match(line)
        if m_sup:
            idx = int(m_sup.group(1)) - 1
            while len(supports) <= idx:
                supports.append({"label": "?", "type": "pin", "x": 0.0})
            sup_label = m_sup.group(2).upper()
            sup_x = float(m_sup.group(4))
            supports[idx] = {
                "label": sup_label,
                "type": m_sup.group(3).lower(),
                "x": sup_x,
                "_user_x": True,
            }
            set_support_x_user(
                beam,
                sup_x,
                label=sup_label,
                index=idx,
            )
            changed = True
            continue

        m_load = _LOAD_RE.match(line)
        if m_load:
            idx = int(m_load.group(1)) - 1
            new_ld = _parse_load_line(idx + 1, m_load.group(2))
            new_ld.pop("_draft_idx", None)
            while len(loads) <= idx:
                loads.append({"type": "point", "x": 0.0, "Fy": 0.0})
            loads[idx] = new_ld
            changed = True
            continue

        patch_load = re.match(r"^load\s+(\d+)\s+(.+)$", line, re.IGNORECASE)
        if patch_load:
            idx = int(patch_load.group(1)) - 1
            if idx < 0 or idx >= len(loads):
                errors.append(f"אין עומס מספר {idx + 1}")
                continue
            kv = _parse_kv_blob(patch_load.group(2))
            ld = dict(loads[idx])
            if "x" in kv:
                set_load_x_user(ld, float(kv["x"]))
            if "m" in kv:
                ld["M"] = float(kv["m"])
                ld["_user_mag"] = True
                ld.pop("note", None)
            if "mag" in kv:
                ld["magnitude_ton"] = float(kv["mag"])
                ld["_user_mag"] = True
                ld.pop("note", None)
            if "angle" in kv:
                ld["angle_deg"] = float(kv["angle"])
            if "dir" in kv:
                ld["incl_dir"] = kv["dir"].lower()
            if "fy" in kv:
                ld["Fy"] = float(kv["fy"])
                ld["_user_mag"] = True
                ld.pop("note", None)
            if "fx" in kv:
                ld["Fx"] = float(kv["fx"])
                ld["_user_mag"] = True
                ld.pop("note", None)
            if "x1" in kv:
                ld["x1"] = float(kv["x1"])
            if "x2" in kv:
                ld["x2"] = float(kv["x2"])
            if str(ld.get("type", "")).lower() == "distributed" and (
                "x1" in kv or "x2" in kv
            ):
                set_distributed_span_user(
                    ld,
                    float(ld.get("x1", 0)),
                    float(ld.get("x2", ld.get("x1", 0))),
                )
            if "w" in kv:
                ld["w"] = float(kv["w"])
                ld["_user_mag"] = True
                if abs(float(kv["w"])) >= 1e-9:
                    ld.pop("_draft_new", None)
            if "type" in kv:
                new_type = kv["type"].lower()
                if new_type in ("point", "moment", "distributed", "inclined"):
                    ld = _parse_load_line(idx + 1, f"{new_type} " + patch_load.group(2))
                    ld.pop("_draft_idx", None)
            if "label" in kv:
                ld["label_at"] = kv["label"].upper()
            if str(ld.get("type", "")).lower() == "inclined" and (
                "angle" in kv or "mag" in kv or "dir" in kv
            ):
                ld = _sync_inclined_components(ld)
            loads[idx] = ld
            changed = True
            continue

    if not changed and not errors:
        errors.append("לא זוהה תיקון — נסה L=12 או load 3 dir=dl")

    beam["loads"] = loads
    beam["supports"] = supports
    out = dict(extracted)
    out["beam"] = beam
    return out, errors


def looks_like_full_draft(text: str) -> bool:
    low = text.lower()
    return "l=" in low and ("load 1:" in low or "load 1 " in low or "support 1:" in low)


if __name__ == "__main__":
    sample = {
        "exercise_type": "beam",
        "beam": {
            "L": 12.0,
            "supports": [
                {"label": "A", "type": "pin", "x": 0},
                {"label": "B", "type": "roller", "x": 12},
            ],
            "loads": [
                {"type": "moment", "x": 1, "M": 30, "label_at": "C"},
                {"type": "inclined", "x": 2, "magnitude_ton": 5, "angle_deg": 30, "incl_dir": "dl"},
            ],
        },
    }
    draft = extracted_to_draft_text(sample)
    print(draft)
    print("\n--- parse ---")
    parsed = parse_draft_text(draft)
    print(parsed)
