# -*- coding: utf-8 -*-
"""תיקון טיוטת תרגיל בשפה חופשית — Gemini classifier + ביצוע דטרמיניסטי."""
from __future__ import annotations

import copy
import json
import logging
import math

from google.genai import types

from bot.draft_format import (
    _inclined_mag,
    _sync_inclined_components,
    set_beam_L_user,
    set_distributed_span_user,
    set_load_x_user,
    set_support_x_user,
    sync_beam_distributed_loads,
)
from bot.gemini_chat import (
    friendly_gemini_error,
    gemini_runtime,
    generate_content_with_retries,
)
from bot.vision import finalize_beam_extraction, parse_json_from_llm_text

log = logging.getLogger("beam_telegram_bot")

# ---------------------------------------------------------------------------
# Classifier prompt — Gemini מזהה פקודה ומחזיר JSON קטן בלבד
# ---------------------------------------------------------------------------

_CLASSIFIER_PROMPT = """\
אתה מפרש הוראות תיקון לתרגיל קורה (בעברית) ומחזיר JSON קטן עם הפעולה המבוקשת בלבד.
אל תשנה את נתוני הקורה — רק זהה מה המשתמש רוצה.
החזר JSON אחד בלבד, בלי markdown, בלי הסברים.

מבנה הקורה הנוכחי:
{beam_summary}

הוראת המשתמש: "{instruction}"

פעולות נתמכות:

1. שינוי אורך קורה:
   {{"action":"set_beam_length","value":10.0}}
   {{"action":"set_beam_length","delta":-2.0}}
   (delta: חיובי=הארכה, שלילי=קיצור)

2. הזזת עומס:
   {{"action":"move_load","load_type":"moment","side":"left","target_x":4.0}}
   {{"action":"move_load","load_type":"point","side":"right","delta_x":1.0}}
   load_type: "point"=אנכי/נקודתי, "axial"=צירי/אופקי, "inclined"=אלכסוני/משופע, "moment"=מומנט, "distributed"=מפורס
   side: "left"=השמאלי, "right"=הימני, null=יחיד מסוגו

3. הזזת סמך:
   {{"action":"move_support","support_type":"pin","side":"left","target_x":2.0}}
   {{"action":"move_support","support_type":"roller","delta_x":1.0}}
   support_type: "pin"=קבוע/נעץ, "roller"=נייד/גליל, "fixed"=קיבוע

4. שינוי טווח עומס מפורס:
   {{"action":"resize_distributed","side":"right","x1":1.0,"x2":5.0}}
   {{"action":"resize_distributed","side":"right","edge":"right","delta":2.0}}
   (edge: "left"/"right" = איזה קצה להזיז; delta חיובי=הארכה, שלילי=קיצור)

5. שינוי זווית עומס אלכסוני:
   {{"action":"set_angle","side":null,"angle_deg":45.0}}

6. היפוך/שינוי כיוון עומס:
   {{"action":"flip_direction","load_type":"axial","side":null,"direction":"left"}}
   {{"action":"flip_direction","load_type":"inclined","side":"right","direction":"dl"}}
   direction: "up","down","left","right","dl"=↙,"dr"=↘, null=היפוך אוטומטי

7. המרת סוג עומס:
   {{"action":"change_load_type","from_type":"inclined","to_type":"point","side":null,"all":true}}
   all: true אם המשתמש ביקש להמיר את כולם

8. הוספת עומס:
   {{"action":"add_load","load_type":"point","x":3.0,"magnitude":5.0,"direction":"down"}}

9. מחיקת עומס:
   {{"action":"delete_load","load_type":"moment","side":"right"}}

10. שינוי גודל/משקל:
    {{"action":"set_magnitude","load_type":"point","side":"left","magnitude":8.0}}
"""


# ---------------------------------------------------------------------------
# Build beam summary for classifier context
# ---------------------------------------------------------------------------

def _build_beam_summary(extracted: dict) -> str:
    """סיכום קצר של הקורה לתוך prompt ה-classifier."""
    beam = extracted.get("beam") if isinstance(extracted, dict) else None
    if not isinstance(beam, dict):
        return "אין נתוני קורה"

    try:
        L = float(beam.get("L", 0) or 0)
    except (TypeError, ValueError):
        L = 0.0

    lines = [f"L = {L} מטר"]

    for i, sup in enumerate(beam.get("supports") or []):
        if not isinstance(sup, dict):
            continue
        t = sup.get("type", "?")
        x = sup.get("x", "?")
        lines.append(f"סמך {i + 1}: {t} ב-x={x}")

    for i, ld in enumerate(beam.get("loads") or []):
        if not isinstance(ld, dict):
            continue
        t = str(ld.get("type", "?")).lower()
        if t == "distributed":
            x1 = ld.get("x1", "?")
            x2 = ld.get("x2", "?")
            w = ld.get("w", "?")
            lines.append(f"עומס {i + 1}: מפורס x1={x1}..x2={x2}, w={w} ט/מ")
        elif t == "moment":
            lines.append(f"עומס {i + 1}: מומנט x={ld.get('x', '?')}, M={ld.get('M', '?')} ט·מ")
        elif t == "inclined":
            lines.append(
                f"עומס {i + 1}: אלכסוני x={ld.get('x', '?')}, "
                f"{ld.get('magnitude_ton', '?')} טון, {ld.get('angle_deg', '?')}°, "
                f"כיוון={ld.get('incl_dir', '?')}"
            )
        elif t == "point":
            try:
                fx = abs(float(ld.get("Fx", ld.get("fx", 0)) or 0))
                fy = abs(float(ld.get("Fy", ld.get("fy", 0)) or 0))
            except (TypeError, ValueError):
                fx = fy = 0.0
            if fx >= 1e-9 and fy < 1e-9:
                lines.append(f"עומס {i + 1}: צירי x={ld.get('x', '?')}, Fx={ld.get('Fx', '?')} טון")
            else:
                lines.append(f"עומס {i + 1}: אנכי x={ld.get('x', '?')}, Fy={ld.get('Fy', '?')} טון")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Load / support helpers
# ---------------------------------------------------------------------------

def _load_x(ld: dict) -> float:
    t = str(ld.get("type", "")).lower()
    if t == "distributed":
        try:
            x1 = float(ld.get("x1", ld.get("start_x", 0)) or 0)
            x2 = float(ld.get("x2", ld.get("end_x", x1)) or x1)
            return 0.5 * (x1 + x2)
        except (TypeError, ValueError):
            return 0.0
    try:
        return float(ld.get("x", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def _is_axial(ld: dict) -> bool:
    if str(ld.get("type", "")).lower() != "point":
        return False
    try:
        fx = abs(float(ld.get("Fx", ld.get("fx", 0)) or 0))
        fy = abs(float(ld.get("Fy", ld.get("fy", 0)) or 0))
    except (TypeError, ValueError):
        return False
    return fx >= 1e-9 and fy < 1e-9


def _load_matches(ld: dict, load_type: str) -> bool:
    t = str(ld.get("type", "")).lower()
    lt = (load_type or "").lower().strip()
    if lt == "moment":
        return t == "moment"
    if lt in ("inclined", "diagonal"):
        return t == "inclined"
    if lt == "distributed":
        return t == "distributed"
    if lt in ("axial", "horizontal"):
        return _is_axial(ld)
    if lt in ("point", "vertical"):
        return t == "point" and not _is_axial(ld)
    return False


def _find_load_idx(
    loads: list,
    load_type: str | None,
    side: str | None,
) -> int | None:
    """מחזיר אינדקס עומס לפי סוג + ימני/שמאלי."""
    candidates: list[tuple[int, dict]] = []
    for i, ld in enumerate(loads):
        if not isinstance(ld, dict):
            continue
        if load_type and not _load_matches(ld, load_type):
            continue
        candidates.append((i, ld))
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0][0]
    if not side:
        return None
    if side == "right":
        return max(candidates, key=lambda it: _load_x(it[1]))[0]
    if side == "left":
        return min(candidates, key=lambda it: _load_x(it[1]))[0]
    return None


def _find_support_idx(
    supports: list,
    support_type: str | None,
    side: str | None,
) -> int | None:
    """מחזיר אינדקס סמך לפי סוג + ימני/שמאלי."""
    candidates: list[tuple[int, dict]] = []
    for i, sup in enumerate(supports):
        if not isinstance(sup, dict):
            continue
        t = str(sup.get("type", "")).lower()
        if support_type and t != support_type.lower():
            continue
        candidates.append((i, sup))
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0][0]
    if not side:
        return None

    def sup_x(s: dict) -> float:
        try:
            return float(s.get("x", 0) or 0)
        except (TypeError, ValueError):
            return 0.0

    if side == "right":
        return max(candidates, key=lambda it: sup_x(it[1]))[0]
    if side == "left":
        return min(candidates, key=lambda it: sup_x(it[1]))[0]
    return None


# ---------------------------------------------------------------------------
# Rescale helper (used by set_beam_length)
# ---------------------------------------------------------------------------

def _rescale_beam_elements(beam: dict, old_L: float, new_L: float) -> None:
    """מסקל פרופורציונלית עומסים וסמכים ל-L החדש."""
    if old_L <= 0:
        return
    ratio = new_L / old_L

    for sup in (beam.get("supports") or []):
        if isinstance(sup, dict) and "x" in sup:
            try:
                sup["x"] = round(float(sup["x"]) * ratio, 4)
                sup["_user_x"] = True
            except (TypeError, ValueError):
                pass

    for ld in (beam.get("loads") or []):
        if not isinstance(ld, dict):
            continue
        if "x" in ld:
            try:
                ld["x"] = round(float(ld["x"]) * ratio, 4)
                ld["_user_x"] = True
                ld.pop("label_at", None)
            except (TypeError, ValueError):
                pass
        for key in ("x1", "x2", "start_x", "end_x"):
            if key in ld:
                try:
                    ld[key] = round(float(ld[key]) * ratio, 4)
                except (TypeError, ValueError):
                    pass

    for pt in (beam.get("labeled_points") or []):
        if isinstance(pt, dict) and "x" in pt:
            try:
                pt["x"] = round(float(pt["x"]) * ratio, 4)
            except (TypeError, ValueError):
                pass


# ---------------------------------------------------------------------------
# convert_inclined_loads_to_vertical  (kept as a public utility)
# ---------------------------------------------------------------------------

def convert_inclined_loads_to_vertical(extracted: dict) -> dict:
    """כל עומס inclined → point אנכי עם אותו משקל כ-Fy."""
    data = copy.deepcopy(extracted) if isinstance(extracted, dict) else {}
    beam = data.get("beam")
    if not isinstance(beam, dict):
        return data
    loads = beam.get("loads")
    if not isinstance(loads, list):
        return data
    out_loads: list = []
    for raw in loads:
        if not isinstance(raw, dict):
            out_loads.append(raw)
            continue
        if str(raw.get("type", "")).lower().strip() != "inclined":
            out_loads.append(dict(raw))
            continue
        mag = _inclined_mag(raw)
        x = float(raw.get("x", 0.0) or 0.0)
        new_ld: dict = {"type": "point", "x": x, "Fy": abs(mag), "Fx": 0.0}
        for key in ("label_at", "from_label", "to_label"):
            if raw.get(key):
                new_ld[key] = raw[key]
        out_loads.append(new_ld)
    beam = dict(beam)
    beam["loads"] = out_loads
    data["beam"] = beam
    return data


# ---------------------------------------------------------------------------
# Action executors
# ---------------------------------------------------------------------------

def _exec_set_beam_length(data: dict, beam: dict, L: float, action: dict) -> dict | None:
    value = action.get("value")
    delta = action.get("delta")
    if value is not None:
        new_L = float(value)
    elif delta is not None:
        new_L = L + float(delta)
    else:
        return None
    new_L = max(0.5, new_L)
    if abs(new_L - L) < 1e-9:
        return None
    beam = dict(beam)
    _rescale_beam_elements(beam, L, new_L)
    set_beam_L_user(beam, new_L)
    data["beam"] = beam
    return data


def _exec_move_load(
    data: dict, beam: dict, L: float, loads: list, action: dict
) -> dict | None:
    idx = _find_load_idx(loads, action.get("load_type"), action.get("side"))
    if idx is None:
        return None
    chosen = dict(loads[idx])
    cur_x = _load_x(chosen)
    target_x = action.get("target_x")
    delta_x = action.get("delta_x")
    if target_x is not None:
        new_x = max(0.0, min(L, float(target_x)))
    elif delta_x is not None:
        new_x = max(0.0, min(L, cur_x + float(delta_x)))
    else:
        return None
    if abs(new_x - cur_x) < 1e-9:
        return None
    set_load_x_user(chosen, new_x)
    new_loads = [dict(ld) if isinstance(ld, dict) else ld for ld in loads]
    new_loads[idx] = chosen
    beam = dict(beam)
    beam["loads"] = new_loads
    data["beam"] = beam
    return data


def _exec_move_support(
    data: dict, beam: dict, L: float, supports: list, action: dict
) -> dict | None:
    idx = _find_support_idx(supports, action.get("support_type"), action.get("side"))
    if idx is None:
        return None
    chosen = supports[idx]
    try:
        cur_x = float(chosen.get("x", 0) or 0)
    except (TypeError, ValueError):
        cur_x = 0.0
    target_x = action.get("target_x")
    delta_x = action.get("delta_x")
    if target_x is not None:
        new_x = max(0.0, min(L, float(target_x)))
    elif delta_x is not None:
        new_x = max(0.0, min(L, cur_x + float(delta_x)))
    else:
        return None
    if abs(new_x - cur_x) < 1e-9:
        return None
    beam = dict(beam)
    beam["supports"] = [dict(s) if isinstance(s, dict) else s for s in supports]
    set_support_x_user(beam, new_x, index=idx)
    data["beam"] = beam
    return data


def _exec_resize_distributed(
    data: dict, beam: dict, L: float, loads: list, action: dict
) -> dict | None:
    side = action.get("side")
    x1_new = action.get("x1")
    x2_new = action.get("x2")
    edge = action.get("edge")
    delta = action.get("delta")

    dist_cands = [
        (i, ld)
        for i, ld in enumerate(loads)
        if isinstance(ld, dict) and str(ld.get("type", "")).lower() == "distributed"
    ]
    if not dist_cands:
        return None

    if len(dist_cands) == 1:
        idx = dist_cands[0][0]
    elif side == "right":
        idx = max(
            dist_cands,
            key=lambda it: float(it[1].get("x2", it[1].get("end_x", 0)) or 0),
        )[0]
    elif side == "left":
        idx = min(
            dist_cands,
            key=lambda it: float(it[1].get("x1", it[1].get("start_x", 0)) or 0),
        )[0]
    else:
        return None

    chosen = dict(loads[idx])
    try:
        cur_x1 = float(chosen.get("x1", chosen.get("start_x", 0)) or 0)
        cur_x2 = float(chosen.get("x2", chosen.get("end_x", cur_x1)) or cur_x1)
    except (TypeError, ValueError):
        return None

    if x1_new is not None and x2_new is not None:
        nx1 = max(0.0, min(L, float(x1_new)))
        nx2 = max(0.0, min(L, float(x2_new)))
    elif edge is not None and delta is not None:
        d = float(delta)
        if edge == "left":
            nx1 = max(0.0, cur_x1 + d)
            nx2 = cur_x2
        else:
            nx1 = cur_x1
            nx2 = min(L, cur_x2 + d)
    else:
        return None

    if nx2 < nx1:
        nx1, nx2 = nx2, nx1
    if nx2 - nx1 < 0.05:
        return None

    set_distributed_span_user(chosen, nx1, nx2)
    new_loads = [dict(ld) if isinstance(ld, dict) else ld for ld in loads]
    new_loads[idx] = chosen
    beam = dict(beam)
    beam["loads"] = new_loads
    sync_beam_distributed_loads(beam)
    data["beam"] = beam
    return data


def _exec_set_angle(data: dict, beam: dict, loads: list, action: dict) -> dict | None:
    angle_deg = action.get("angle_deg")
    if angle_deg is None:
        return None
    angle = float(angle_deg)
    if angle <= 0 or angle >= 90:
        return None
    idx = _find_load_idx(loads, "inclined", action.get("side"))
    if idx is None:
        return None
    chosen = dict(loads[idx])
    if str(chosen.get("type", "")).lower() != "inclined":
        return None
    try:
        cur = float(chosen.get("angle_deg", 30) or 30)
    except (TypeError, ValueError):
        cur = 30.0
    if abs(cur - angle) < 1e-9:
        return None
    chosen["angle_deg"] = angle
    chosen = _sync_inclined_components(chosen)
    chosen["_user_mag"] = True
    new_loads = [dict(ld) if isinstance(ld, dict) else ld for ld in loads]
    new_loads[idx] = chosen
    beam = dict(beam)
    beam["loads"] = new_loads
    data["beam"] = beam
    return data


def _exec_flip_direction(
    data: dict, beam: dict, loads: list, action: dict
) -> dict | None:
    load_type = action.get("load_type")
    side = action.get("side")
    direction = action.get("direction")

    idx = _find_load_idx(loads, load_type, side)
    if idx is None:
        return None

    chosen = dict(loads[idx])
    t = str(chosen.get("type", "")).lower()

    if t == "inclined":
        target_dir = direction if direction in ("dl", "dr") else None
        if target_dir:
            mag = float(chosen.get("magnitude_ton") or 0)
            if mag < 1e-6:
                mag = math.hypot(
                    float(chosen.get("Fx", 0) or 0),
                    float(chosen.get("Fy", 0) or 0),
                )
            angle = float(chosen.get("angle_deg", 30) or 30)
            rad = math.radians(angle)
            fx_mag = mag * math.cos(rad)
            fy_mag = math.sin(rad) * mag
            if target_dir == "dl":
                chosen["Fx"], chosen["Fy"] = -abs(fx_mag), abs(fy_mag)
            else:
                chosen["Fx"], chosen["Fy"] = abs(fx_mag), abs(fy_mag)
            chosen["incl_dir"] = target_dir
            chosen["magnitude_ton"] = mag
        else:
            cur_dir = str(chosen.get("incl_dir", "dr") or "dr").lower()
            chosen["incl_dir"] = "dl" if cur_dir == "dr" else "dr"
            chosen = _sync_inclined_components(chosen)

    elif _is_axial(chosen):
        try:
            fx = float(chosen.get("Fx", chosen.get("fx", 0)) or 0)
        except (TypeError, ValueError):
            fx = 0.0
        mag = abs(fx) if abs(fx) >= 1e-9 else 5.0
        if direction == "left":
            chosen["Fx"] = -mag
        elif direction == "right":
            chosen["Fx"] = mag
        else:
            chosen["Fx"] = -fx if abs(fx) >= 1e-9 else mag
        chosen["Fy"] = 0.0

    elif t == "point":  # vertical
        try:
            fy = float(chosen.get("Fy", chosen.get("fy", 0)) or 0)
        except (TypeError, ValueError):
            fy = 0.0
        mag = abs(fy) if abs(fy) >= 1e-9 else 5.0
        if direction == "up":
            chosen["Fy"] = -mag
        elif direction == "down":
            chosen["Fy"] = mag
        else:
            chosen["Fy"] = -fy if abs(fy) >= 1e-9 else mag
        chosen["Fx"] = 0.0

    elif t == "moment":
        try:
            m = float(chosen.get("M", 0) or 0)
        except (TypeError, ValueError):
            m = 0.0
        chosen["M"] = -m if abs(m) >= 1e-9 else 10.0

    else:
        return None

    new_loads = [dict(ld) if isinstance(ld, dict) else ld for ld in loads]
    new_loads[idx] = chosen
    beam = dict(beam)
    beam["loads"] = new_loads
    data["beam"] = beam
    return data


def _exec_change_load_type(
    data: dict, beam: dict, loads: list, action: dict
) -> dict | None:
    from_type = action.get("from_type")
    to_type = (action.get("to_type") or "").lower()
    side = action.get("side")
    all_loads = bool(action.get("all", False))

    if all_loads and from_type == "inclined" and to_type in ("point", "vertical"):
        return convert_inclined_loads_to_vertical(data)

    idx = _find_load_idx(loads, from_type, side)
    if idx is None:
        return None

    chosen = dict(loads[idx])
    t = str(chosen.get("type", "")).lower()
    x = float(chosen.get("x", 0) or 0)

    if to_type in ("point", "vertical"):
        if t == "inclined":
            mag = _inclined_mag(chosen)
        else:
            mag = abs(float(chosen.get("Fy", chosen.get("M", 0)) or 0)) or 5.0
        chosen = {"type": "point", "x": x, "Fy": abs(mag), "Fx": 0.0}

    elif to_type in ("axial", "horizontal"):
        if t == "inclined":
            mag = _inclined_mag(chosen)
        else:
            mag = abs(float(chosen.get("Fy", 0) or 0)) or 5.0
        chosen = {"type": "point", "x": x, "Fy": 0.0, "Fx": abs(mag)}

    elif to_type == "moment":
        mag = abs(float(chosen.get("Fy", chosen.get("M", 0)) or 0)) or 10.0
        chosen = {"type": "moment", "x": x, "M": mag}

    elif to_type == "inclined":
        if t == "inclined":
            mag = _inclined_mag(chosen)
        else:
            mag = abs(float(chosen.get("Fy", 0) or 0)) or 5.0
        chosen = {
            "type": "inclined",
            "x": x,
            "magnitude_ton": mag,
            "angle_deg": 30.0,
            "incl_dir": "dr",
        }
        chosen = _sync_inclined_components(chosen)

    else:
        return None

    chosen["_user_mag"] = True
    new_loads = [dict(ld) if isinstance(ld, dict) else ld for ld in loads]
    new_loads[idx] = chosen
    beam = dict(beam)
    beam["loads"] = new_loads
    data["beam"] = beam
    return data


def _exec_add_load(
    data: dict, beam: dict, L: float, loads: list, action: dict
) -> dict | None:
    load_type = str(action.get("load_type", "point") or "point").lower()
    x = float(action.get("x", L * 0.5) or L * 0.5)
    magnitude = float(action.get("magnitude", 5.0) or 5.0)
    direction = str(action.get("direction", "down") or "down").lower()
    x = max(0.0, min(L, x))

    if load_type in ("point", "vertical"):
        fy = -abs(magnitude) if direction == "up" else abs(magnitude)
        new_ld: dict = {"type": "point", "x": x, "Fy": fy, "Fx": 0.0,
                        "_user_x": True, "_user_mag": True}
    elif load_type in ("axial", "horizontal"):
        fx = -abs(magnitude) if direction == "left" else abs(magnitude)
        new_ld = {"type": "point", "x": x, "Fy": 0.0, "Fx": fx,
                  "_user_x": True, "_user_mag": True}
    elif load_type == "moment":
        new_ld = {"type": "moment", "x": x, "M": magnitude,
                  "_user_x": True, "_user_mag": True}
    elif load_type == "inclined":
        incl_dir = "dl" if direction in ("left", "dl") else "dr"
        new_ld = {
            "type": "inclined", "x": x, "magnitude_ton": magnitude,
            "angle_deg": 30.0, "incl_dir": incl_dir,
            "_user_x": True, "_user_mag": True,
        }
        new_ld = _sync_inclined_components(new_ld)
    elif load_type == "distributed":
        half = min(L * 0.2, 2.0)
        x1 = max(0.0, x - half)
        x2 = min(L, x + half)
        if x2 - x1 < 0.1:
            x1, x2 = 0.0, min(L, max(0.1, L * 0.3))
        new_ld = {"type": "distributed", "x1": x1, "x2": x2, "w": magnitude,
                  "shape": "rectangular", "_user_span": True, "_user_mag": True}
    else:
        return None

    new_loads = [dict(ld) if isinstance(ld, dict) else ld for ld in loads]
    new_loads.append(new_ld)
    beam = dict(beam)
    beam["loads"] = new_loads
    if load_type == "distributed":
        sync_beam_distributed_loads(beam)
    data["beam"] = beam
    return data


def _exec_delete_load(data: dict, beam: dict, loads: list, action: dict) -> dict | None:
    idx = _find_load_idx(loads, action.get("load_type"), action.get("side"))
    if idx is None:
        return None
    new_loads = [dict(ld) if isinstance(ld, dict) else ld
                 for i, ld in enumerate(loads) if i != idx]
    beam = dict(beam)
    beam["loads"] = new_loads
    data["beam"] = beam
    return data


def _exec_set_magnitude(data: dict, beam: dict, loads: list, action: dict) -> dict | None:
    magnitude = action.get("magnitude")
    if magnitude is None:
        return None
    mag = float(magnitude)
    idx = _find_load_idx(loads, action.get("load_type"), action.get("side"))
    if idx is None:
        return None
    chosen = dict(loads[idx])
    t = str(chosen.get("type", "")).lower()
    if t == "moment":
        chosen["M"] = mag
    elif t == "inclined":
        chosen["magnitude_ton"] = mag
        chosen = _sync_inclined_components(chosen)
    elif t == "point":
        if _is_axial(chosen):
            try:
                fx = float(chosen.get("Fx", chosen.get("fx", 0)) or 0)
            except (TypeError, ValueError):
                fx = 0.0
            chosen["Fx"] = -mag if fx < 0 else mag
            chosen["Fy"] = 0.0
        else:
            try:
                fy = float(chosen.get("Fy", chosen.get("fy", 0)) or 0)
            except (TypeError, ValueError):
                fy = 0.0
            chosen["Fy"] = -mag if fy < 0 else mag
            chosen["Fx"] = 0.0
    elif t == "distributed":
        chosen["w"] = mag
    else:
        return None
    chosen["_user_mag"] = True
    new_loads = [dict(ld) if isinstance(ld, dict) else ld for ld in loads]
    new_loads[idx] = chosen
    beam = dict(beam)
    beam["loads"] = new_loads
    data["beam"] = beam
    return data


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def _execute_action(extracted: dict, action: dict) -> dict | None:
    """מבצע את הפעולה המזוהה על ה-JSON — דטרמיניסטי לחלוטין."""
    act = str(action.get("action", "")).strip()
    data = copy.deepcopy(extracted)
    beam = data.get("beam")
    if not isinstance(beam, dict):
        return None

    try:
        L = float(beam.get("L", 0) or 0)
    except (TypeError, ValueError):
        L = 0.0

    loads: list = beam.get("loads") or []
    supports: list = beam.get("supports") or []

    dispatch = {
        "set_beam_length": lambda: _exec_set_beam_length(data, beam, L, action),
        "move_load": lambda: _exec_move_load(data, beam, L, loads, action),
        "move_support": lambda: _exec_move_support(data, beam, L, supports, action),
        "resize_distributed": lambda: _exec_resize_distributed(data, beam, L, loads, action),
        "set_angle": lambda: _exec_set_angle(data, beam, loads, action),
        "flip_direction": lambda: _exec_flip_direction(data, beam, loads, action),
        "change_load_type": lambda: _exec_change_load_type(data, beam, loads, action),
        "add_load": lambda: _exec_add_load(data, beam, L, loads, action),
        "delete_load": lambda: _exec_delete_load(data, beam, loads, action),
        "set_magnitude": lambda: _exec_set_magnitude(data, beam, loads, action),
    }

    handler = dispatch.get(act)
    if handler is None:
        log.warning("Draft NL: unknown action=%r", act)
        return None
    return handler()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def apply_nl_draft_edit(
    extracted: dict, user_instruction: str
) -> tuple[dict | None, list[str]]:
    """מעדכן extracted לפי טקסט חופשי. מחזיר (updated, errors)."""
    instruction = (user_instruction or "").strip()
    if not instruction:
        return None, ["כתוב מה לתקן בטיוטה."]

    current = extracted if isinstance(extracted, dict) else {}
    beam_summary = _build_beam_summary(current)
    prompt = _CLASSIFIER_PROMPT.format(
        beam_summary=beam_summary,
        instruction=instruction,
    )

    action_dict: dict | None = None
    gemini_error: str | None = None
    try:
        client, model = gemini_runtime()
        response = generate_content_with_retries(
            client,
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json",
            ),
        )
        text = getattr(response, "text", None) or ""
        action_dict = parse_json_from_llm_text(str(text))
    except Exception as exc:
        log.warning("Draft NL classify failed: %s", exc)
        gemini_error = friendly_gemini_error(exc)

    if not isinstance(action_dict, dict):
        return None, [gemini_error or "לא הצלחתי להבין את התיקון — נסה לנסח שוב."]

    log.info("Draft NL action=%s params=%s", action_dict.get("action"), action_dict)

    updated = _execute_action(current, action_dict)
    if updated is None:
        return None, ["לא הצלחתי לבצע את הפעולה — נסה לנסח שוב."]

    return _finalize_or_raw(updated), []


def _finalize_or_raw(parsed: dict) -> dict:
    try:
        return finalize_beam_extraction(parsed, merge_nearby_point_loads=False)
    except Exception as exc:
        log.warning("Draft NL finalize failed: %s", exc)
        return parsed
