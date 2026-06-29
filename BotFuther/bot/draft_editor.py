# -*- coding: utf-8 -*-
"""זרימת אישור טיוטה לפני חישוב — human-in-the-loop."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from bot.draft_format import (
    apply_patch_text,
    build_extracted_from_draft,
    extracted_to_draft_text,
    looks_like_full_draft,
    parse_draft_text,
    set_beam_L_user,
    set_distributed_span_user,
    set_load_x_user,
    set_support_x_user,
    sync_beam_distributed_loads,
)
from bot.vision import (
    finalize_beam_extraction,
    get_stored_vision_extracted,
    is_draft_pending,
    set_draft_pending,
    store_vision_context,
)

log = logging.getLogger("draft_editor")

_APPROVE_RE = re.compile(
    r"^(אישור|מאשר|מאשרת|אשר|כן|yes|ok|okay|go|חשב|חישוב|נכון|בסדר)\.?$",
    re.IGNORECASE,
)


@dataclass
class DraftHandleResult:
    handled: bool
    reply: str = ""
    update_draft: bool = False
    approved: bool = False
    extracted: dict | None = None
    solved: dict | None = None
    errors: list[str] | None = None


def is_approval_message(text: str) -> bool:
    return bool(_APPROVE_RE.match(text.strip()))


def looks_like_draft_patch(text: str) -> bool:
    """טקסט שנראה כמו תיקון טיוטה (לא צ'אט כללי)."""
    raw = text.strip()
    if not raw:
        return False
    if is_approval_message(raw):
        return True
    if looks_like_full_draft(raw):
        return True
    low = raw.lower()
    return low.startswith(("l=", "load ", "support "))


def prepare_draft_reply(extracted: dict) -> str:
    """טיוטה לעריכה — ללא חישוב."""
    return extracted_to_draft_text(extracted)


def store_as_pending_draft(chat_id: int, extracted: dict) -> str:
    """שומר טיוטה ממתינה ומחזיר טקסט לשליחה."""
    draft_text = extracted_to_draft_text(extracted)
    set_draft_pending(chat_id, extracted, draft_text)
    return draft_text


def _validate_for_solve(extracted: dict) -> list[str]:
    try:
        from core.beam_validator import validate_beam_extraction

        beam = extracted.get("beam") if isinstance(extracted.get("beam"), dict) else {}
        validator_payload = {
            "exercise_type": "beam",
            "beam": {
                "L": beam.get("L"),
                "supports": beam.get("supports") or [],
                "loads": _loads_for_validator(beam.get("loads") or []),
                "labeled_points": beam.get("labeled_points") or [],
            },
        }
        result = validate_beam_extraction(validator_payload)
        return [] if result.ok else list(result.errors)
    except Exception as exc:
        log.warning("Validator skipped: %s", exc)
        return []


def _loads_for_validator(loads: list[dict]) -> list[dict]:
    out: list[dict] = []
    for ld in loads:
        if not isinstance(ld, dict):
            continue
        item = dict(ld)
        t = str(item.get("type", "")).lower()
        if t == "distributed":
            item["start_x"] = float(item.get("x1", item.get("start_x", 0)))
            item["end_x"] = float(item.get("x2", item.get("end_x", 0)))
            item["q"] = float(item.get("w", item.get("q", 0)))
        out.append(item)
    return out


def approve_and_solve(chat_id: int, extracted: dict) -> tuple[str, dict]:
    """מאמת, מחשב, שומר — מחזיר (תשובה, solved)."""
    from bot.solution_check import format_solve_reply, solve_extracted_beam

    extracted = finalize_beam_extraction(extracted)
    errors = _validate_for_solve(extracted)
    if errors:
        return (errors[0], {})

    solved = solve_extracted_beam(extracted)
    store_vision_context(chat_id, extracted, solved)
    reply = format_solve_reply(extracted, solved)
    return reply, solved


def _parse_edit_number(text: str) -> float | None:
    """מפרס מספר מהודעת עריכה — תומך ב-L=12, x=6.5, 12 מ' וכו'."""
    raw = text.strip()
    for pat in (r"^L\s*=\s*(.+)$", r"^x\s*=\s*(.+)$"):
        m = re.match(pat, raw, re.IGNORECASE)
        if m:
            raw = m.group(1).strip()
            break
    m = re.search(r"-?[\d.,]+", raw.replace("'", "").replace("מ", ""))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", "."))
    except ValueError:
        return None


def apply_field_edit(extracted: dict, edit: dict, text: str) -> tuple[dict, list[str]]:
    """מיישם עריכה של שדה בודד מהטיוטה."""
    from bot.draft_format import apply_patch_text

    kind = edit.get("kind")
    text = text.strip()
    errors: list[str] = []

    if kind == "L":
        val = _parse_edit_number(text)
        if val is None:
            return extracted, ["L לא תקין — שלח מספר"]
        beam = dict(extracted.get("beam") or {})
        set_beam_L_user(beam, val)
        out = dict(extracted)
        out["beam"] = beam
        return out, errors

    if kind == "support":
        idx = int(edit.get("index", 1)) - 1
        val = _parse_edit_number(text)
        if val is None:
            return extracted, ["x לא תקין — שלח מספר"]
        beam = dict(extracted.get("beam") or {})
        supports = [dict(s) for s in (beam.get("supports") or []) if isinstance(s, dict)]
        if idx < 0 or idx >= len(supports):
            return extracted, [f"אין סמך {idx + 1}"]
        label = str(supports[idx].get("label", "")).strip()
        beam["supports"] = supports
        set_support_x_user(beam, val, label=label, index=idx)
        out = dict(extracted)
        out["beam"] = beam
        return out, errors

    if kind == "load":
        idx = int(edit.get("index", 1))
        if text.lower().startswith("load"):
            line = text
        elif "=" in text:
            line = f"load {idx} {text}"
        else:
            line = f"load {idx}: {text}"
        updated, patch_errors = apply_patch_text(extracted, line)
        return updated, patch_errors

    if kind == "load_dir":
        idx = int(edit.get("index", 1))
        d = text.strip().lower()
        if d in ("↙", "down-left", "down left", "left", "שמאל"):
            d = "dl"
        elif d in ("↘", "down-right", "down right", "right", "ימין"):
            d = "dr"
        if d not in ("dl", "dr"):
            return extracted, ["שלח dl (↙) או dr (↘)"]
        updated, patch_errors = apply_patch_text(extracted, f"load {idx} dir={d}")
        return updated, patch_errors

    if kind == "load_x":
        idx = int(edit.get("index", 1))
        beam = extracted.get("beam") if isinstance(extracted.get("beam"), dict) else {}
        loads = beam.get("loads") or []
        ld = loads[idx - 1] if isinstance(loads, list) and 0 <= idx - 1 < len(loads) else {}
        t = str(ld.get("type", "point")).lower().strip() if isinstance(ld, dict) else "point"
        if t == "distributed":
            raw = text.strip().replace(" ", "")
            for dash in ("–", "—", "−"):
                raw = raw.replace(dash, "-")
            m_range = re.match(r"^([\d.,]+)-([\d.,]+)$", raw)
            if m_range:
                try:
                    x1 = float(m_range.group(1).replace(",", "."))
                    x2 = float(m_range.group(2).replace(",", "."))
                except ValueError:
                    return extracted, ["טווח לא תקין — שלח למשל 2-8"]
            else:
                parts = re.split(r"[,;]", text.strip())
                if len(parts) == 2:
                    try:
                        x1 = float(parts[0].replace(",", ".").strip())
                        x2 = float(parts[1].replace(",", ".").strip())
                    except ValueError:
                        return extracted, ["טווח לא תקין — שלח למשל 2-8"]
                else:
                    val = _parse_edit_number(text)
                    if val is None:
                        return extracted, ["מרחק לא תקין — שלח טווח 2-8"]
                    try:
                        x2 = float(ld.get("x2", ld.get("end_x", val)))
                    except (TypeError, ValueError):
                        x2 = val
                    x1 = val
            beam = dict(extracted.get("beam") or {})
            loads = [dict(x) for x in (beam.get("loads") or []) if isinstance(x, dict)]
            i = idx - 1
            if i < 0 or i >= len(loads):
                return extracted, [f"אין עומס מספר {idx}"]
            set_distributed_span_user(loads[i], x1, x2)
            beam["loads"] = loads
            sync_beam_distributed_loads(beam)
            out = dict(extracted)
            out["beam"] = beam
            return out, []
        val = _parse_edit_number(text)
        if val is None:
            return extracted, ["x לא תקין — שלח מספר"]
        beam = dict(extracted.get("beam") or {})
        loads = [dict(x) for x in (beam.get("loads") or []) if isinstance(x, dict)]
        i = idx - 1
        if i < 0 or i >= len(loads):
            return extracted, [f"אין עומס מספר {idx}"]
        set_load_x_user(loads[i], val)
        _clear_draft_new_flag(loads, idx)
        beam["loads"] = loads
        out = dict(extracted)
        out["beam"] = beam
        return out, errors

    if kind == "load_angle":
        idx = int(edit.get("index", 1))
        val = _parse_edit_number(text)
        if val is None:
            return extracted, ["זווית לא תקינה — שלח מספר במעלות"]
        updated, patch_errors = apply_patch_text(extracted, f"load {idx} angle={val}")
        _clear_draft_new_flag(
            (updated.get("beam") or {}).get("loads") or [], idx
        )
        return updated, patch_errors

    if kind == "load_mag":
        idx = int(edit.get("index", 1))
        val = _parse_edit_number(text)
        if val is None:
            return extracted, ["ערך לא תקין — שלח מספר"]
        beam = extracted.get("beam") if isinstance(extracted.get("beam"), dict) else {}
        loads = beam.get("loads") or []
        ld = loads[idx - 1] if isinstance(loads, list) and 0 <= idx - 1 < len(loads) else {}
        if not isinstance(ld, dict):
            ld = {}
        t = str(ld.get("type", "point")).lower().strip()
        # preserve current sign by writing signed values
        if t == "moment":
            cur = float(ld.get("M", ld.get("m", 0.0)) or 0.0)
            signed = abs(val) if cur >= 0 else -abs(val)
            updated, patch_errors = apply_patch_text(extracted, f"load {idx} m={signed}")
            loads_out = (updated.get("beam") or {}).get("loads") or []
            if 0 <= idx - 1 < len(loads_out) and isinstance(loads_out[idx - 1], dict):
                _mark_user_mag(loads_out[idx - 1])
            _clear_draft_new_flag(loads_out, idx)
            return updated, patch_errors
        if t == "distributed":
            cur = float(ld.get("w", ld.get("q", 0.0)) or 0.0)
            signed = abs(val) if cur >= 0 else -abs(val)
            beam = dict(extracted.get("beam") or {})
            loads = [dict(x) for x in (beam.get("loads") or []) if isinstance(x, dict)]
            i = idx - 1
            if i < 0 or i >= len(loads):
                return extracted, [f"אין עומס מספר {idx}"]
            loads[i]["type"] = "distributed"
            loads[i]["w"] = signed
            _mark_user_mag(loads[i])
            if abs(signed) >= 1e-9:
                loads[i].pop("_draft_new", None)
            beam["loads"] = loads
            sync_beam_distributed_loads(beam)
            out = dict(extracted)
            out["beam"] = beam
            return out, []
        if t == "inclined":
            updated, patch_errors = apply_patch_text(extracted, f"load {idx} mag={abs(val)}")
            loads_out = (updated.get("beam") or {}).get("loads") or []
            if 0 <= idx - 1 < len(loads_out) and isinstance(loads_out[idx - 1], dict):
                _mark_user_mag(loads_out[idx - 1])
            _clear_draft_new_flag(loads_out, idx)
            return updated, patch_errors
        # point: prefer Fy if exists, else Fx
        fy = ld.get("Fy", ld.get("fy"))
        fx = ld.get("Fx", ld.get("fx"))
        try:
            fy_v = float(fy) if fy is not None else 0.0
        except (TypeError, ValueError):
            fy_v = 0.0
        try:
            fx_v = float(fx) if fx is not None else 0.0
        except (TypeError, ValueError):
            fx_v = 0.0
        if abs(fy_v) >= 1e-9 or abs(fx_v) < 1e-9:
            signed = abs(val) if fy_v >= 0 else -abs(val)
            updated, patch_errors = apply_patch_text(extracted, f"load {idx} fy={signed}")
            loads_out = (updated.get("beam") or {}).get("loads") or []
            if 0 <= idx - 1 < len(loads_out) and isinstance(loads_out[idx - 1], dict):
                _mark_user_mag(loads_out[idx - 1])
            _clear_draft_new_flag(loads_out, idx)
            return updated, patch_errors
        signed = abs(val) if fx_v >= 0 else -abs(val)
        updated, patch_errors = apply_patch_text(extracted, f"load {idx} fx={signed}")
        loads_out = (updated.get("beam") or {}).get("loads") or []
        if 0 <= idx - 1 < len(loads_out) and isinstance(loads_out[idx - 1], dict):
            _mark_user_mag(loads_out[idx - 1])
        _clear_draft_new_flag(loads_out, idx)
        return updated, patch_errors

    return extracted, ["שדה לא מוכר"]


def toggle_load_direction(extracted: dict, load_idx: int) -> dict:
    """הופך כיוון עומס אלכסוני (dl ↔ dr)."""
    import math

    from bot.vision import finalize_beam_extraction

    beam = dict(extracted.get("beam") or {})
    loads = [dict(ld) for ld in (beam.get("loads") or []) if isinstance(ld, dict)]
    i = load_idx - 1
    if i < 0 or i >= len(loads):
        return extracted
    ld = loads[i]
    if str(ld.get("type", "")).lower() != "inclined":
        return extracted

    cur = str(ld.get("incl_dir", "") or "").lower()
    if cur not in ("dl", "dr"):
        fx = float(ld.get("Fx", 0) or 0)
        cur = "dl" if fx < 0 else "dr"
    new_dir = "dr" if cur == "dl" else "dl"
    mag = float(ld.get("magnitude_ton") or 0)
    if mag < 1e-6:
        fx = float(ld.get("Fx", 0) or 0)
        fy = float(ld.get("Fy", 0) or 0)
        mag = math.hypot(fx, fy)
    angle = float(ld.get("angle_deg", 30))
    rad = math.radians(angle)
    fx_mag = mag * math.cos(rad)
    fy_mag = mag * math.sin(rad)
    if new_dir == "dl":
        ld["Fx"], ld["Fy"] = -abs(fx_mag), abs(fy_mag)
    else:
        ld["Fx"], ld["Fy"] = abs(fx_mag), abs(fy_mag)
    ld["incl_dir"] = new_dir
    ld["magnitude_ton"] = mag
    loads[i] = ld
    beam["loads"] = loads
    out = dict(extracted)
    out["beam"] = beam
    return finalize_beam_extraction(out)


_LOAD_TYPE_CYCLE = ("point", "moment", "distributed", "inclined")


def _empty_load_template(load_type: str, L: float) -> dict:
    """תבנית עומס חדש לפי סוג — נשאר _draft_new עד שהמשתמש ממלא ערכים."""
    Lf = max(float(L), 0.1)
    t = str(load_type).lower().strip()
    if t == "moment":
        return {"type": "moment", "x": 0.0, "M": 0.0, "_draft_new": True}
    if t == "distributed":
        return {
            "type": "distributed",
            "x1": 0.0,
            "x2": round(min(Lf * 0.5, Lf), 3),
            "w": 0.0,
            "shape": "rectangular",
            "_draft_new": True,
        }
    if t == "inclined":
        return {
            "type": "inclined",
            "x": 0.0,
            "magnitude_ton": 0.0,
            "angle_deg": 45.0,
            "incl_dir": "dr",
            "_draft_new": True,
        }
    return {"type": "point", "x": 0.0, "Fy": 0.0, "Fx": 0.0, "_draft_new": True}


def cycle_load_type(extracted: dict, load_idx: int) -> dict:
    """מחליף סוג עומס חדש: נקודתי → מומנט → מפורס → אלכסון → נקודתי."""
    from bot.vision import finalize_beam_extraction

    beam = dict(extracted.get("beam") or {})
    L = float(beam.get("L", 10.0) or 10.0)
    loads = [dict(ld) for ld in (beam.get("loads") or []) if isinstance(ld, dict)]
    i = load_idx - 1
    if i < 0 or i >= len(loads):
        return extracted
    cur = str(loads[i].get("type", "point")).lower().strip()
    try:
        pos = _LOAD_TYPE_CYCLE.index(cur)
    except ValueError:
        pos = -1
    next_type = _LOAD_TYPE_CYCLE[(pos + 1) % len(_LOAD_TYPE_CYCLE)]
    loads[i] = _empty_load_template(next_type, L)
    beam["loads"] = loads
    out = dict(extracted)
    out["beam"] = beam
    return finalize_beam_extraction(out)


def set_load_type(extracted: dict, load_idx: int, new_type: str) -> dict:
    """מחליף סוג עומס — שומר מיקום וגודל ככל האפשר."""
    import math

    from bot.draft_format import _inclined_mag
    from bot.vision import finalize_beam_extraction

    beam = dict(extracted.get("beam") or {})
    L = float(beam.get("L", 10.0) or 10.0)
    Lf = max(L, 0.1)
    loads = [dict(ld) for ld in (beam.get("loads") or []) if isinstance(ld, dict)]
    i = load_idx - 1
    if i < 0 or i >= len(loads):
        return extracted
    ld = loads[i]
    target = str(new_type).lower().strip()
    if target not in _LOAD_TYPE_CYCLE:
        return extracted
    current = str(ld.get("type", "point")).lower().strip()
    if current == target:
        return extracted

    x = float(ld.get("x", ld.get("x1", 0.0)) or 0.0)
    x1 = float(ld.get("x1", x) or 0.0)
    try:
        x2 = float(ld.get("x2", max(x, x1)) or max(x, x1))
    except (TypeError, ValueError):
        x2 = max(x, x1)
    if x2 < x1:
        x1, x2 = x2, x1

    def signed_scalar() -> float:
        if current == "moment":
            return float(ld.get("M", ld.get("m", 0.0)) or 0.0)
        if current == "distributed":
            return float(ld.get("w", ld.get("q", 0.0)) or 0.0)
        if current == "inclined":
            return _inclined_mag(ld) * (1.0 if float(ld.get("Fy", 0) or 0) >= 0 else -1.0)
        fy = float(ld.get("Fy", ld.get("fy", 0.0)) or 0.0)
        if abs(fy) >= 1e-9:
            return fy
        return float(ld.get("Fx", ld.get("fx", 0.0)) or 0.0)

    def abs_scalar() -> float:
        return abs(signed_scalar())

    mag = abs_scalar()
    sign = 1.0 if signed_scalar() >= 0 else -1.0
    label_at = str(ld.get("label_at", "") or "").strip()
    from_label = str(ld.get("from_label", "") or "").strip()
    to_label = str(ld.get("to_label", "") or "").strip()
    was_new = bool(ld.get("_draft_new"))

    if target == "point":
        new_ld: dict = {
            "type": "point",
            "x": x,
            "Fy": sign * mag if mag >= 1e-9 else 0.0,
            "Fx": float(ld.get("Fx", ld.get("fx", 0.0)) or 0.0),
        }
        if current == "point":
            new_ld["Fx"] = float(ld.get("Fx", ld.get("fx", 0.0)) or 0.0)
            new_ld["Fy"] = float(ld.get("Fy", ld.get("fy", 0.0)) or 0.0)
    elif target == "moment":
        new_ld = {"type": "moment", "x": x, "M": sign * mag}
    elif target == "distributed":
        if current == "distributed":
            new_ld = dict(ld)
            new_ld["type"] = "distributed"
        elif was_new:
            new_ld = _empty_load_template("distributed", Lf)
        else:
            span = max(x2 - x1, min(Lf * 0.25, 3.0))
            cx = (x1 + x2) / 2.0 if x2 > x1 else x
            half = span / 2.0
            new_ld = {
                "type": "distributed",
                "x1": max(0.0, cx - half),
                "x2": min(Lf, cx + half),
                "w": sign * mag,
                "shape": str(ld.get("shape", "rectangular") or "rectangular"),
            }
    else:  # inclined
        incl_dir = str(ld.get("incl_dir", "dr") or "dr").lower()
        if incl_dir not in ("dl", "dr"):
            incl_dir = "dr"
        angle = float(ld.get("angle_deg", 45.0) or 45.0)
        if current == "inclined":
            angle = float(ld.get("angle_deg", 45.0) or 45.0)
            incl_dir = str(ld.get("incl_dir", "dr") or "dr").lower()
        new_ld = {
            "type": "inclined",
            "x": x,
            "magnitude_ton": mag,
            "angle_deg": angle,
            "incl_dir": incl_dir,
        }
        if mag >= 1e-9:
            rad = math.radians(angle)
            fx_m = mag * math.cos(rad)
            fy_m = mag * math.sin(rad)
            if incl_dir == "dl":
                new_ld["Fx"], new_ld["Fy"] = -abs(fx_m), abs(fy_m)
            else:
                new_ld["Fx"], new_ld["Fy"] = abs(fx_m), abs(fy_m)

    if label_at:
        new_ld["label_at"] = label_at
    if from_label:
        new_ld["from_label"] = from_label
    if to_label:
        new_ld["to_label"] = to_label
    if was_new and mag < 1e-9:
        new_ld["_draft_new"] = True
    elif mag >= 1e-9:
        new_ld.pop("_draft_new", None)

    loads[i] = new_ld
    beam["loads"] = loads
    out = dict(extracted)
    out["beam"] = beam
    return finalize_beam_extraction(out)


def toggle_any_load_direction(extracted: dict, load_idx: int) -> dict:
    """הופך כיוון/סימן של עומס (מתוך תפריט הסוג או ישירות)."""
    from bot.vision import finalize_beam_extraction

    beam = dict(extracted.get("beam") or {})
    loads = [dict(ld) for ld in (beam.get("loads") or []) if isinstance(ld, dict)]
    i = load_idx - 1
    if i < 0 or i >= len(loads):
        return extracted
    ld = loads[i]
    t = str(ld.get("type", "point")).lower().strip()
    if t == "inclined":
        return toggle_load_direction(extracted, load_idx)
    if t == "moment":
        for k in ("M", "m"):
            if ld.get(k) is not None:
                try:
                    ld[k] = -float(ld[k])
                except (TypeError, ValueError):
                    pass
        if abs(float(ld.get("M", ld.get("m", 0)) or 0.0)) >= 1e-9:
            ld.pop("_draft_new", None)
    elif t == "distributed":
        for k in ("w", "q"):
            if ld.get(k) is not None:
                try:
                    ld[k] = -float(ld[k])
                except (TypeError, ValueError):
                    pass
        if abs(float(ld.get("w", ld.get("q", 0)) or 0.0)) >= 1e-9:
            ld.pop("_draft_new", None)
    else:  # point
        if ld.get("Fy", ld.get("fy")) is not None:
            try:
                ld["Fy"] = -float(ld.get("Fy", ld.get("fy", 0.0)) or 0.0)
            except (TypeError, ValueError):
                pass
        elif ld.get("Fx", ld.get("fx")) is not None:
            try:
                ld["Fx"] = -float(ld.get("Fx", ld.get("fx", 0.0)) or 0.0)
            except (TypeError, ValueError):
                pass
    loads[i] = ld
    beam["loads"] = loads
    out = dict(extracted)
    out["beam"] = beam
    return finalize_beam_extraction(out)


def delete_load(extracted: dict, load_idx: int) -> dict:
    """מסיר עומס מהטיוטה לפי אינדקס 1-based."""
    from bot.vision import finalize_beam_extraction

    beam = dict(extracted.get("beam") or {})
    loads = [dict(ld) for ld in (beam.get("loads") or []) if isinstance(ld, dict)]
    i = load_idx - 1
    if i < 0 or i >= len(loads):
        return extracted
    loads.pop(i)
    beam["loads"] = loads
    out = dict(extracted)
    out["beam"] = beam
    return finalize_beam_extraction(out)


def add_empty_load(extracted: dict) -> dict:
    """מוסיף שורת עומס חדשה ריקה לטיוטה."""
    out = dict(extracted)
    beam = dict(out.get("beam") or {})
    loads = [dict(ld) for ld in (beam.get("loads") or []) if isinstance(ld, dict)]
    loads.append(
        {
            "type": "point",
            "x": 0.0,
            "Fy": 0.0,
            "_draft_new": True,
        }
    )
    beam["loads"] = loads
    out["beam"] = beam
    return out


def _mark_user_mag(ld: dict) -> None:
    """מסמן עריכת כח ידנית — מונע דריסה מ-note או תיקוני חילוץ."""
    ld["_user_mag"] = True
    ld.pop("note", None)


def _clear_draft_new_flag(loads: list[dict], idx: int) -> None:
    i = idx - 1
    if 0 <= i < len(loads) and isinstance(loads[i], dict):
        loads[i].pop("_draft_new", None)


def apply_user_edit(chat_id: int, text: str) -> tuple[dict, str, list[str]]:
    """
    מיישם עריכת משתמש על טיוטה שמורה.
    Returns: (extracted מעודכן, טיוטה חדשה, שגיאות)
    """
    base = get_stored_vision_extracted(chat_id)
    if not base:
        raise ValueError("אין טיוטה פעילה — שלח תמונה קודם")

    errors: list[str] = []
    if looks_like_full_draft(text):
        parsed = parse_draft_text(text)
        if parsed is None:
            errors.append("לא הצלחתי לקרוא את הטיוטה — בדוק פורמט")
            updated = base
        else:
            updated = build_extracted_from_draft(parsed, base)
    else:
        updated, patch_errors = apply_patch_text(base, text)
        errors.extend(patch_errors)

    updated = finalize_beam_extraction(updated)
    draft = extracted_to_draft_text(updated)
    persist_draft(chat_id, updated)
    return updated, draft, errors


def persist_draft(chat_id: int, extracted: dict) -> None:
    """שומר טיוטה ושומר על message_id של ההודעה המקורית."""
    from bot.vision import get_draft_message_ref

    draft = extracted_to_draft_text(extracted)
    ref = get_draft_message_ref(chat_id)
    msg_id = ref[1] if ref else None
    set_draft_pending(chat_id, extracted, draft, message_id=msg_id)


def handle_draft_text(chat_id: int, text: str) -> DraftHandleResult:
    """מטפל בהודעת טקסט כשיש טיוטה ממתינה."""
    if not is_draft_pending(chat_id):
        return DraftHandleResult(handled=False)

    if is_approval_message(text):
        extracted = get_stored_vision_extracted(chat_id)
        if not extracted:
            return DraftHandleResult(
                handled=True,
                reply="אין טיוטה — שלח תמונה.",
            )
        reply, solved = approve_and_solve(chat_id, extracted)
        return DraftHandleResult(
            handled=True,
            approved=True,
            reply=reply,
            solved=solved,
            extracted=extracted,
        )

    updated, draft, errors = apply_user_edit(chat_id, text)
    return DraftHandleResult(
        handled=True,
        update_draft=True,
        extracted=updated,
        errors=errors or None,
    )
