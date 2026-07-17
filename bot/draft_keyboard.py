# -*- coding: utf-8 -*-
"""כפתורים inline לעריכת טיוטה + עדכון אותה הודעה."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from bot.draft_editor import axial_dir_icon, is_axial_point_load, load_picker_kind
from bot.draft_format import (
    _fmt_num,
    _inclined_dir,
    _inclined_mag,
    _load_to_draft_line,
    distributed_span_from_left,
    x_from_left_end,
)

# אינדקס 0 = תפריט בחירת סוג לפני הוספת עומס חדש (עדיין אין שורה בטבלה).
ADD_LOAD_TYPE_PICKER_IDX = 0


def _is_simply_supported_two_supports(beam: dict) -> bool:
    """קורה על שני סמכים (צמד+גליל) — לא זיז רתום."""
    mode = str(beam.get("support_mode", "simply_supported")).lower().strip()
    if mode == "cantilever":
        return False
    supports = beam.get("supports") or []
    if not isinstance(supports, list) or len(supports) != 2:
        return False
    stypes = {
        str(s.get("type", "")).lower().strip()
        for s in supports
        if isinstance(s, dict)
    }
    if "roller" in stypes and ("pin" in stypes or "fixed" in stypes):
        return True
    return mode == "simply_supported"


def _support_type_he(support_type: str, *, beam: dict | None = None, support: dict | None = None) -> str:
    st = str(support_type).lower().strip()
    if beam and _is_simply_supported_two_supports(beam):
        if st == "pin":
            return "קבוע"
        if st == "roller":
            return "נייד"
        # גליל שזוהה בטעות כקיבוע — מציגים «נייד» אם הסמך השני הוא קבוע (נעץ).
        if st == "fixed" and support is not None:
            supports = [
                s for s in (beam.get("supports") or []) if isinstance(s, dict) and s is not support
            ]
            if len(supports) == 1 and str(supports[0].get("type", "")).lower().strip() == "pin":
                return "נייד"
        return {"pin": "קבוע", "roller": "נייד"}.get(st, support_type)
    mapping = {
        "pin": "נעץ",
        "roller": "גליל",
        "fixed": "קיבוע",
    }
    return mapping.get(st, support_type)


def draft_data_only_text(extracted: dict) -> str:
    """רק נתוני המבנה — ללא כותרות אימות, אזהרות או הוראות.

    חשוב: לא מריצים כאן finalize מחדש — הטקסט והמקלדת חייבים לקרוא
    מאותו snapshot שנשמר בטיוטה, אחרת מרחקים/ערכים מתפצלים.
    """
    beam = extracted.get("beam") if isinstance(extracted.get("beam"), dict) else {}
    l_val = _fmt_num(float(beam.get("L", 0)))

    lines = [
        f"*אורך הקורה*   {l_val} מ'",
        "",
    ]

    supports = beam.get("supports") or []
    if supports:
        lines.append("*סמכים*")
        for sup in supports:
            if not isinstance(sup, dict):
                continue
            label = str(sup.get("label", "?")).strip()
            st = _support_type_he(str(sup.get("type", "pin")), beam=beam, support=sup)
            x = _fmt_num(x_from_left_end(beam, sup.get("x"), label=label, support=sup))
            lines.append(f"   {label}  ·  {st}  ·  x = {x} מ'")
        lines.append("")

    loads = beam.get("loads") or []
    if loads:
        lines.append("*עומסים*")
        for idx, ld in enumerate(loads, 1):
            if isinstance(ld, dict):
                lines.append(f"   {idx}. {_load_summary_he(beam, idx, ld)}")
        lines.append("")

    return "\n".join(lines).rstrip()


def draft_display_text(
    extracted: dict,
    *,
    edit: dict | None = None,
    errors: list[str] | None = None,
    type_picker_idx: int | None = None,
) -> str:
    """טקסט טיוטה — אך ורק נתונים (ללא הערות, אזהרות או הוראות)."""
    return draft_data_only_text(extracted)


def _load_summary_he(beam: dict, idx: int, ld: dict) -> str:
    if _is_draft_empty_load(ld):
        t = str(ld.get("type", "point")).lower()
        label_at = str(ld.get("label_at", "") or "")
        if t == "distributed" and (ld.get("_user_span") or ld.get("_draft_new")):
            x1, x2 = distributed_span_from_left(ld, beam)
            return f"חדש  ·  מ־{_fmt_num(x1)} עד {_fmt_num(x2)} מ'"
        if ld.get("_user_x"):
            x = _fmt_num(
                x_from_left_end(beam, ld.get("x", ld.get("x1", 0)), label=label_at, load=ld)
            )
            if t == "moment":
                kind = "מומנט"
            elif t == "inclined":
                kind = "אלכסון"
            elif is_axial_point_load(ld):
                kind = "צירי"
            else:
                kind = "נקודתי"
            return f"{kind}  ·  x = {x} מ'"
        return "חדש"

    t = str(ld.get("type", "point")).lower()
    label_at = str(ld.get("label_at", "") or "")
    x = _fmt_num(x_from_left_end(beam, ld.get("x", ld.get("x1", 0)), label=label_at, load=ld))

    if t == "moment":
        raw_m = float(ld.get("M", ld.get("m", 0)) or 0.0)
        arrow = "↻" if raw_m >= 0 else "↺"
        m = _fmt_num(abs(raw_m))
        return f"מומנט {arrow}  ·  {m} ט·מ  ·  x = {x} מ'"

    if t == "inclined":
        # הצגה ברורה: גודל/זווית/כיוון (בלי פירוק לרכיבים כדי לא להעמיס).
        mag = _fmt_num(_inclined_mag(ld))
        angle = _fmt_num(float(ld.get("angle_deg", 30)))
        side = "↙" if _inclined_dir(ld) == "dl" else "↘"
        return f"אלכסון {side}  ·  {mag} טון  ·  {angle}°  ·  x = {x} מ'"

    if t == "distributed":
        x1, x2 = distributed_span_from_left(ld, beam)
        x1s, x2s = _fmt_num(x1), _fmt_num(x2)
        raw_w = float(ld.get("w", ld.get("q", 0)) or 0.0)
        arrow = _distributed_dir_icon(ld)
        w = _fmt_num(abs(raw_w))
        return f"מפוזר {arrow}  ·  {w} ט/מ  ·  מ־{x1s} עד {x2s} מ'"

    if t == "point":
        fy = ld.get("Fy", ld.get("fy"))
        fx = ld.get("Fx", ld.get("fx"))
        parts: list[str] = ["צירי" if is_axial_point_load(ld) else "נקודתי"]
        if fy is not None and abs(float(fy)) > 1e-9:
            arrow = "↓" if float(fy) > 0 else "↑"
            parts.append(f"{arrow} {_fmt_num(abs(float(fy)))} טון")
        if fx is not None and abs(float(fx)) > 1e-9:
            arrow = "→" if float(fx) > 0 else "←"
            parts.append(f"{arrow} {_fmt_num(abs(float(fx)))} טון")
        parts.append(f"x = {x} מ'")
        return "  ·  ".join(parts)

    return _load_to_draft_line(idx, ld).replace("@", "x =")


def build_draft_keyboard(
    extracted: dict,
    *,
    type_picker_idx: int | None = None,
) -> InlineKeyboardMarkup:
    beam = extracted.get("beam") if isinstance(extracted.get("beam"), dict) else {}
    rows: list[list[InlineKeyboardButton]] = []

    rows.append([InlineKeyboardButton("אורך L", callback_data="d:eL")])

    supports = beam.get("supports") or []
    sup_row: list[InlineKeyboardButton] = []
    for idx, sup in enumerate(supports, 1):
        if not isinstance(sup, dict):
            continue
        sup_row.append(
            InlineKeyboardButton(
                f"סמך {str(sup.get('label', idx)).strip()}",
                callback_data=f"d:eS{idx}",
            )
        )
        if len(sup_row) == 2:
            rows.append(sup_row)
            sup_row = []
    if sup_row:
        rows.append(sup_row)

    loads = beam.get("loads") or []
    if loads:
        rows.append(_build_load_table_header_row())
        for idx, ld in enumerate(loads, 1):
            if isinstance(ld, dict):
                rows.append(_build_load_row_buttons(beam, idx, ld))

    if type_picker_idx is not None:
        if type_picker_idx == ADD_LOAD_TYPE_PICKER_IDX:
            rows.extend(
                _build_load_type_picker_rows(
                    ADD_LOAD_TYPE_PICKER_IDX,
                    {},
                    adding_new=True,
                )
            )
        elif 1 <= type_picker_idx <= len(loads):
            ld = loads[type_picker_idx - 1]
            if not isinstance(ld, dict):
                ld = {}
            rows.extend(_build_load_type_picker_rows(type_picker_idx, ld))
        else:
            rows.append([InlineKeyboardButton("הוסף", callback_data="d:ad")])
            rows.append([InlineKeyboardButton("חשב", callback_data="d:a")])
    else:
        rows.append([InlineKeyboardButton("הוסף", callback_data="d:ad")])
        rows.append([InlineKeyboardButton("חשב", callback_data="d:a")])
    return InlineKeyboardMarkup(rows)


def _distributed_dir_icon(ld: dict) -> str:
    """סימון עומס מפורס — שני חצים אנכיים זה לצד זה."""
    w = float(ld.get("w", ld.get("q", 0)) or 0.0)
    return "↓↓" if w >= 0 else "↑↑"


def _draft_new_dir_icon(ld: dict) -> str:
    """אייקון כיוון לעומס חדש — לפי הסוג שנבחר (לחיצות על «כיוון» מחליפות סוג)."""
    t = str(ld.get("type", "point")).lower().strip()
    if t == "moment":
        return "↻"
    if t == "distributed":
        return _distributed_dir_icon(ld)
    if t == "inclined":
        return "↘"
    if is_axial_point_load(ld):
        return axial_dir_icon(ld)
    return "↓"


def _load_has_magnitude(ld: dict) -> bool:
    """True אם לעומס יש כוח/מומנט/עוצמה בפועל (לא שורה ריקה)."""
    t = str(ld.get("type", "point")).lower().strip()
    if t == "moment":
        return abs(float(ld.get("M", ld.get("m", 0)) or 0.0)) >= 1e-9
    if t == "inclined":
        return _inclined_mag(ld) >= 1e-9
    if t == "distributed":
        return abs(float(ld.get("w", ld.get("q", 0)) or 0.0)) >= 1e-9
    try:
        fy = float(ld.get("Fy", ld.get("fy", 0.0)) or 0.0)
    except (TypeError, ValueError):
        fy = 0.0
    try:
        fx = float(ld.get("Fx", ld.get("fx", 0.0)) or 0.0)
    except (TypeError, ValueError):
        fx = 0.0
    return abs(fy) >= 1e-9 or abs(fx) >= 1e-9


def should_open_type_picker_on_direction_click(ld: dict) -> bool:
    """פתיחת תפריט סוג — רק לעומס חדש (_draft_new) שעדיין בלי ערך וללא סוג שנבחר."""
    if not ld.get("_draft_new"):
        return False
    if _load_has_magnitude(ld):
        return False
    if ld.get("_draft_axial") or is_axial_point_load(ld):
        return False
    t = str(ld.get("type", "point")).lower().strip()
    if t != "point":
        return False
    return True


def _is_draft_empty_load(ld: dict) -> bool:
    if _load_has_magnitude(ld):
        return False
    return True


# רוחב עמודות קבוע — כל שורת עומס באותה פריסת טבלה; פח תמיד בימין.
_LOAD_COL_DIR = 6
_LOAD_COL_MAG = 7
_LOAD_COL_DIST = 9
_LOAD_COL_ANGLE = 6
_LOAD_COL_DELETE = 4
_LOAD_NOOP_CB = "d:n"


def _pad_load_btn_label(text: str, min_width: int) -> str:
    """מרחיב תווית כפתור (טלגרם מחלק רוחב לפי אורך הטקסט)."""
    s = str(text)
    if len(s) >= min_width:
        return s
    pad = min_width - len(s)
    left = pad // 2
    right = pad - left
    return (" " * left) + s + (" " * right)


def _load_field_button(text: str, callback_data: str, *, min_width: int) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        _pad_load_btn_label(text, min_width),
        callback_data=callback_data,
    )


def _load_delete_button(idx: int) -> InlineKeyboardButton:
    """כפתור מחיקה — ריבוע קבוע בקצה ימין של השורה."""
    return InlineKeyboardButton(
        _pad_load_btn_label("מחק", _LOAD_COL_DELETE),
        callback_data=f"d:dl{idx}",
    )


def _load_noop_button(text: str, *, min_width: int) -> InlineKeyboardButton:
    return _load_field_button(text, _LOAD_NOOP_CB, min_width=min_width)


def _build_load_table_header_row() -> list[InlineKeyboardButton]:
    return [
        _load_noop_button("כיוון", min_width=_LOAD_COL_DIR),
        _load_noop_button("כח", min_width=_LOAD_COL_MAG),
        _load_noop_button("מרחק", min_width=_LOAD_COL_DIST),
        _load_noop_button("מעלות", min_width=_LOAD_COL_ANGLE),
        _load_noop_button(" ", min_width=_LOAD_COL_DELETE),
    ]


def _compact_btn_num(val: str) -> str:
    return val.replace(" ", "")


def _load_distance_text(beam: dict, ld: dict) -> str:
    t = str(ld.get("type", "point")).lower().strip()
    if t == "distributed":
        x1, x2 = distributed_span_from_left(ld, beam)
        return f"{_fmt_num(x1)}-{_fmt_num(x2)}"
    label_at = str(ld.get("label_at", "") or "")
    x_val = _fmt_num(x_from_left_end(beam, ld.get("x", ld.get("x1", 0)), label=label_at, load=ld))
    return x_val


def _build_load_row_buttons(beam: dict, idx: int, ld: dict) -> list[InlineKeyboardButton]:
    """שורת עומס: כיוון | כח | מרחק | מעלות | 🗑 — עמודות קבועות לכל סוג."""
    empty = _is_draft_empty_load(ld)
    t = str(ld.get("type", "point")).lower().strip()

    if empty:
        dir_txt = _draft_new_dir_icon(ld) if ld.get("_draft_new") else "·"
        show_dist = bool(ld.get("_user_x") or ld.get("_user_span")) or (
            t == "distributed" and bool(ld.get("_draft_new"))
        )
        if show_dist:
            dist_txt = _compact_btn_num(_load_distance_text(beam, ld))
        else:
            dist_txt = "·"
        dist_cb = f"d:ex{idx}"
        angle_btn = (
            _load_field_button("·°", f"d:ea{idx}", min_width=_LOAD_COL_ANGLE)
            if t == "inclined" and ld.get("_draft_new")
            else _load_noop_button("·", min_width=_LOAD_COL_ANGLE)
        )
        return [
            _load_field_button(dir_txt, f"d:td{idx}", min_width=_LOAD_COL_DIR),
            _load_field_button("·", f"d:em{idx}", min_width=_LOAD_COL_MAG),
            _load_field_button(dist_txt, dist_cb, min_width=_LOAD_COL_DIST),
            angle_btn,
            _load_delete_button(idx),
        ]

    dir_txt = "↕"
    if t == "moment":
        m = float(ld.get("M", ld.get("m", 0)) or 0.0)
        dir_txt = "↻" if m >= 0 else "↺"
    elif t == "inclined":
        dir_txt = "↙" if _inclined_dir(ld) == "dl" else "↘"
    elif t == "distributed":
        dir_txt = _distributed_dir_icon(ld)
    else:
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
        if abs(fy_v) >= 1e-9:
            dir_txt = "↓" if fy_v > 0 else "↑"
        elif abs(fx_v) >= 1e-9:
            dir_txt = "→" if fx_v > 0 else "←"
        else:
            dir_txt = "↓"

    mag_txt = "0"
    if t == "moment":
        mag_txt = _fmt_num(abs(float(ld.get("M", ld.get("m", 0)) or 0.0)))
    elif t == "inclined":
        mag_txt = _fmt_num(_inclined_mag(ld))
    elif t == "distributed":
        mag_txt = _fmt_num(abs(float(ld.get("w", ld.get("q", 0)) or 0.0)))
    else:
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
        mag_txt = _fmt_num(abs(fy_v) if abs(fy_v) >= 1e-9 else abs(fx_v))

    dist_txt = _compact_btn_num(_load_distance_text(beam, ld))

    if t == "inclined":
        angle_btn = _load_field_button(
            f"{_fmt_num(float(ld.get('angle_deg', 30)))}°",
            f"d:ea{idx}",
            min_width=_LOAD_COL_ANGLE,
        )
    else:
        angle_btn = _load_noop_button("·", min_width=_LOAD_COL_ANGLE)

    return [
        _load_field_button(dir_txt, f"d:td{idx}", min_width=_LOAD_COL_DIR),
        _load_field_button(_compact_btn_num(mag_txt), f"d:em{idx}", min_width=_LOAD_COL_MAG),
        _load_field_button(dist_txt, f"d:ex{idx}", min_width=_LOAD_COL_DIST),
        angle_btn,
        _load_delete_button(idx),
    ]


def build_load_dir_prompt_keyboard(idx: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("↙ dl", callback_data=f"d:Dl{idx}"),
                InlineKeyboardButton("↘ dr", callback_data=f"d:Dr{idx}"),
            ],
            [InlineKeyboardButton("ביטול", callback_data="d:x")],
        ]
    )


def _type_picker_btn(label: str, idx: int, code: str, *, selected: bool) -> InlineKeyboardButton:
    prefix = "> " if selected else ""
    return InlineKeyboardButton(f"{prefix}{label}", callback_data=f"d:y{idx}{code}")


def _build_load_type_picker_rows(
    idx: int,
    ld: dict,
    *,
    adding_new: bool = False,
) -> list[list[InlineKeyboardButton]]:
    """שורות בחירת סוג עומס — נפתח בלחיצה על «הוסף עומס» או על כיוון בעומס חדש."""
    cur = load_picker_kind(ld) if not adding_new else ""
    rows = [
        [
            _type_picker_btn("↕ נקודתי", idx, "p", selected=cur == "point"),
            _type_picker_btn("↻ מומנט", idx, "m", selected=cur == "moment"),
        ],
        [
            _type_picker_btn("↓↓ מפורס", idx, "u", selected=cur == "distributed"),
            _type_picker_btn("↘ אלכסון", idx, "i", selected=cur == "inclined"),
        ],
    ]
    if adding_new:
        rows.append([_type_picker_btn("→ צירי", idx, "a", selected=False)])
    else:
        rows.append(
            [
                InlineKeyboardButton("היפוך כיוון", callback_data=f"d:y{idx}f"),
                _type_picker_btn("→ צירי", idx, "a", selected=cur == "axial"),
            ]
        )
    return rows


def load_type_picker_prompt(idx: int) -> str:
    return (
        f"עומס *{idx}* — בחר סוג\n"
        "_לחיצה על «כיוון» הופכת כיוון; «חזרה» או שדה אחר סוגרים את התפריט_"
    )


@dataclass
class DraftCallback:
    action: str  # approve | edit_L | edit_support | edit_load | edit_load_dir | cancel_edit | set_load_dir
    index: int = 0
    dir: str = ""


def parse_draft_callback(data: str) -> DraftCallback | None:
    if not data or not data.startswith("d:"):
        return None
    body = data[2:]
    if body == "a":
        return DraftCallback(action="approve")
    if body == "ad":
        return DraftCallback(action="add_load")
    if body == "x":
        return DraftCallback(action="cancel_edit")
    if body == "eL":
        return DraftCallback(action="edit_L")
    if body.startswith("eS") and body[2:].isdigit():
        return DraftCallback(action="edit_support", index=int(body[2:]))
    if body.startswith("eP") and body[2:].isdigit():
        return DraftCallback(action="edit_load", index=int(body[2:]))
    if body.startswith("i") and body[1:].isdigit():
        return DraftCallback(action="edit_load_dir", index=int(body[1:]))
    if body.startswith("td") and body[2:].isdigit():
        return DraftCallback(action="pick_load_type", index=int(body[2:]))
    if body.startswith("em") and body[2:].isdigit():
        return DraftCallback(action="edit_load_mag", index=int(body[2:]))
    if body.startswith("ex") and body[2:].isdigit():
        return DraftCallback(action="edit_load_x", index=int(body[2:]))
    if body.startswith("ea") and body[2:].isdigit():
        return DraftCallback(action="edit_load_angle", index=int(body[2:]))
    if body.startswith("dl") and body[2:].isdigit():
        return DraftCallback(action="delete_load", index=int(body[2:]))
    if body.startswith("Dl") and body[2:].isdigit():
        return DraftCallback(action="set_load_dir", index=int(body[2:]), dir="dl")
    if body.startswith("Dr") and body[2:].isdigit():
        return DraftCallback(action="set_load_dir", index=int(body[2:]), dir="dr")
    m_type = re.match(r"^y(\d+)([pmuifa])$", body)
    if m_type:
        idx = int(m_type.group(1))
        code = m_type.group(2)
        if code == "f":
            return DraftCallback(action="toggle_dir", index=idx)
        type_map = {
            "p": "point",
            "m": "moment",
            "u": "distributed",
            "i": "inclined",
            "a": "axial",
        }
        return DraftCallback(action="set_load_type", index=idx, dir=type_map[code])
    return None


def edit_prompt(edit: dict[str, Any], extracted: dict) -> str:
    kind = edit.get("kind")
    if kind == "L":
        return "אורך קורה L — הקלד מספר (למשל `13` או `L=13`)"
    if kind == "support":
        idx = int(edit.get("index", 1)) - 1
        supports = (extracted.get("beam") or {}).get("supports") or []
        label = supports[idx].get("label", "?") if 0 <= idx < len(supports) else "?"
        return f"סמך {label} — הקלד x חדש"
    if kind == "load_dir":
        idx = int(edit.get("index", 1))
        return f"כיוון עומס {idx}"
    if kind == "load":
        idx = int(edit.get("index", 1))
        return f"עומס {idx} — הקלד תיקון"
    if kind == "load_mag":
        idx = int(edit.get("index", 1))
        return f"עומס {idx} — הקלד גודל (מספר בלבד)"
    if kind == "load_x":
        idx = int(edit.get("index", 1))
        beam = extracted.get("beam") if isinstance(extracted.get("beam"), dict) else {}
        loads = beam.get("loads") or []
        ld = loads[idx - 1] if isinstance(loads, list) and 0 <= idx - 1 < len(loads) else {}
        if isinstance(ld, dict) and str(ld.get("type", "")).lower() == "distributed":
            return (
                f"עומס {idx} (מפורס) — הקלד טווח *התחלה-סוף* "
                f"(למשל `3-9` או `3,9`)\n"
                f"מספר בודד = שינוי נקודת ההתחלה בלבד"
            )
        return f"עומס {idx} — הקלד מיקום x (מספר בלבד)"
    if kind == "load_angle":
        idx = int(edit.get("index", 1))
        return f"עומס {idx} — הקלד זווית במעלות (מספר בלבד)"
    return "הקלד ערך חדש"
