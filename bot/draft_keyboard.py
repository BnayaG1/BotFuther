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
        "fixed": "ריתום",
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
        f"*אורך הקורה*   {l_val}m",
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
            x_val = x_from_left_end(beam, sup.get("x"), label=label, support=sup)
            x = _fmt_num(x_val)
            if st == "ריתום":
                L_val = float(beam.get("L", 0) or 0)
                side = "שמאל" if (x_val <= L_val / 2 if L_val > 0 else x_val == 0) else "ימין"
                lines.append(f"   {st}  ·  {side}")
            else:
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
            return f"מפורס  ·  x={_fmt_num(x1)}-{_fmt_num(x2)}m"
        if ld.get("_user_x"):
            x = _fmt_num(
                x_from_left_end(beam, ld.get("x", ld.get("x1", 0)), label=label_at, load=ld)
            )
            if t == "moment":
                kind = "מומנט"
            elif t == "inclined":
                kind = "אלכסוני"
            elif is_axial_point_load(ld):
                kind = "צירי"
            else:
                kind = "נקודתי"
            return f"{kind}  ·  x = {x}m"
        if t == "moment":
            return "מומנט"
        if t == "inclined":
            return "אלכסוני"
        if t == "distributed":
            return "מפורס"
        if is_axial_point_load(ld):
            return "צירי"
        return "נקודתי"

    t = str(ld.get("type", "point")).lower()

    if t == "moment":
        raw_m = float(ld.get("M", ld.get("m", 0)) or 0.0)
        arrow = "↻" if raw_m >= 0 else "↺"
        m = _fmt_num(abs(raw_m))
        return f"מומנט {m}t/m {arrow}"

    if t == "inclined":
        mag = _fmt_num(_inclined_mag(ld))
        angle = _fmt_num(float(ld.get("angle_deg", 30)))
        side = "↙" if _inclined_dir(ld) == "dl" else "↘"
        return f"אלכסוני {mag}t {angle}° {side}"

    if t == "distributed":
        raw_w = float(ld.get("w", ld.get("q", 0)) or 0.0)
        arrow = _distributed_dir_icon(ld)
        w = _fmt_num(abs(raw_w))
        return f"מפורס {w}t/m {arrow}"

    if t == "point":
        if is_axial_point_load(ld):
            fx = float(ld.get("Fx", ld.get("fx", 0)) or 0.0)
            arrow = "→" if fx >= 0 else "←"
            m_val = _fmt_num(abs(fx))
            return f"צירי {m_val}t {arrow}"

        fy = float(ld.get("Fy", ld.get("fy", 0)) or 0.0)
        arrow = "↓" if fy >= 0 else "↑"
        m_val = _fmt_num(abs(fy))
        return f"נקודתי {m_val}t {arrow}"

    return f"עומס"


DRAFT_INSTRUCTION_TEXT = (
    "זו מה שחילצתי.\n"
    "אם משהו לא מדויק — כתוב במילים מה לתקן "
    "(אורך קורה, הזזת עומס/סמך, מפורס, כיוון או סוג עומס) ואשלח תיקון.\n"
    "אם זה התרגיל שלך - לחץ אישור."
)

DRAFT_FIXED_TEXT = (
    "תוקן.\n"
    "אם עדיין משהו לא נכון תגיד ואתקן, ואם הכל תקין - לחץ אישור"
)


def build_draft_approve_keyboard() -> InlineKeyboardMarkup:
    """מקלדת טיוטה מינימלית — אישור בלבד."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("אישור", callback_data="d:a")]]
    )


def build_draft_keyboard(
    extracted: dict,
    *,
    menu_view: str = "main",
    type_picker_idx: int | None = None,
) -> InlineKeyboardMarkup:
    beam = extracted.get("beam") if isinstance(extracted.get("beam"), dict) else {}
    rows: list[list[InlineKeyboardButton]] = []
    loads = beam.get("loads") or []
    supports = beam.get("supports") or []
    if menu_view.startswith("support_"):
        try:
            sup_idx = int(menu_view.split("_")[1])
        except (IndexError, ValueError):
            sup_idx = 1
        rows.append([
            InlineKeyboardButton("שינוי מיקום", callback_data=f"d:eS{sup_idx}"),
        ])
        rows.append([InlineKeyboardButton("חזור", callback_data="d:m_main")])
        return InlineKeyboardMarkup(rows)

    if menu_view.startswith("load_"):
        try:
            load_idx = int(menu_view.split("_")[1])
        except (IndexError, ValueError):
            load_idx = 1
        if 1 <= load_idx <= len(loads) and isinstance(loads[load_idx - 1], dict):
            ld = loads[load_idx - 1]
            t = str(ld.get("type", "point")).lower().strip()

            if t == "moment":
                left_dir, right_dir = "↺", "↻"
                mid_txt = "שינוי t/m"
            elif t == "inclined":
                left_dir, right_dir = "↙", "↘"
                mid_txt = "שינוי t"
            elif t == "distributed":
                left_dir, right_dir = "↑↑", "↓↓"
                mid_txt = "שינוי t/m"
            elif is_axial_point_load(ld):
                left_dir, right_dir = "←", "→"
                mid_txt = "שינוי t"
            else:
                left_dir, right_dir = "↑", "↓"
                mid_txt = "שינוי t"

            # שורה ראשונה: כיוון שמאל | שינוי t/m | כיוון ימין
            row1 = [
                InlineKeyboardButton(left_dir, callback_data=f"d:sD{load_idx}l"),
                InlineKeyboardButton(mid_txt, callback_data=f"d:em{load_idx}"),
                InlineKeyboardButton(right_dir, callback_data=f"d:sD{load_idx}r"),
            ]
            rows.append(row1)

            # שורה שנייה: מיקום (באלכסוני מוסיפים גם זווית)
            if t == "inclined":
                rows.append([
                    InlineKeyboardButton("מיקום", callback_data=f"d:ex{load_idx}"),
                    InlineKeyboardButton("זווית", callback_data=f"d:ea{load_idx}"),
                ])
            else:
                rows.append([InlineKeyboardButton("מיקום", callback_data=f"d:ex{load_idx}")])

            if type_picker_idx == load_idx:
                rows.extend(_build_load_type_picker_rows(load_idx, ld))

            # שורה שלישית: מחק עומס זה
            rows.append([InlineKeyboardButton("מחק עומס זה", callback_data=f"d:dl{load_idx}")])
            # שורה רביעית: חזרה
            rows.append([InlineKeyboardButton("חזרה", callback_data="d:m_main")])
            return InlineKeyboardMarkup(rows)

    if type_picker_idx is not None and type_picker_idx == ADD_LOAD_TYPE_PICKER_IDX:
        rows.extend(_build_load_type_picker_rows(ADD_LOAD_TYPE_PICKER_IDX, {}, adding_new=True))
        rows.append([InlineKeyboardButton("חזרה", callback_data="d:m_main")])
        return InlineKeyboardMarkup(rows)

    # תפריט נתונים ראשי מלא בברירת מחדל
    rows.append([InlineKeyboardButton("אורך קורה", callback_data="d:eL")])

    valid_sups = [s for s in supports if isinstance(s, dict)]
    if len(valid_sups) == 2:
        roller_btn = None
        pin_btn = None
        for idx, sup in enumerate(supports, 1):
            if not isinstance(sup, dict):
                continue
            st = _support_type_he(str(sup.get("type", "pin")), beam=beam, support=sup)
            btn_text = f"סמך {st}"
            btn = InlineKeyboardButton(btn_text, callback_data=f"d:mS{idx}")
            if st == "נייד":
                roller_btn = btn
            elif st == "קבוע":
                pin_btn = btn

        if roller_btn and pin_btn:
            rows.append([
                roller_btn,
                InlineKeyboardButton("החלף סמכים", callback_data="d:swS"),
                pin_btn,
            ])
        else:
            for idx, sup in enumerate(supports, 1):
                if not isinstance(sup, dict):
                    continue
                st = _support_type_he(str(sup.get("type", "pin")), beam=beam, support=sup)
                btn_text = "ריתום" if st == "ריתום" else f"סמך {st}"
                rows.append([InlineKeyboardButton(btn_text, callback_data=f"d:mS{idx}")])
    else:
        for idx, sup in enumerate(supports, 1):
            if not isinstance(sup, dict):
                continue
            st = _support_type_he(str(sup.get("type", "pin")), beam=beam, support=sup)
            btn_text = "ריתום" if st == "ריתום" else f"סמך {st}"
            rows.append([InlineKeyboardButton(btn_text, callback_data=f"d:mS{idx}")])

    for idx, ld in enumerate(loads, 1):
        if isinstance(ld, dict):
            summary = _load_summary_he(beam, idx, ld)
            rows.append([InlineKeyboardButton(summary, callback_data=f"d:mL{idx}")])

    rows.append([InlineKeyboardButton("הוספת עומס", callback_data="d:ad")])
    rows.append([InlineKeyboardButton("אישור תרגיל", callback_data="d:a")])
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
    action: str  # approve | edit_L | edit_support | edit_load | edit_load_dir | cancel_edit | set_load_dir | menu_edit | menu_main | menu_load
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
    if body == "m_edit":
        return DraftCallback(action="menu_edit")
    if body == "m_main":
        return DraftCallback(action="menu_main")
    if body.startswith("mL") and body[2:].isdigit():
        return DraftCallback(action="menu_load", index=int(body[2:]))
    if body == "eL":
        return DraftCallback(action="edit_L")
    if body.startswith("mS") and body[2:].isdigit():
        return DraftCallback(action="menu_support", index=int(body[2:]))
    if body.startswith("eS") and body[2:].isdigit():
        return DraftCallback(action="edit_support", index=int(body[2:]))
    if body == "swS":
        return DraftCallback(action="swap_supports")
    if body.startswith("sS") and len(body) >= 4 and body[2:-1].isdigit():
        idx = int(body[2:-1])
        side = body[-1]
        return DraftCallback(action="set_support_side", index=idx, dir=side)
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
    if body.startswith("sD") and len(body) >= 4 and body[2:-1].isdigit():
        idx = int(body[2:-1])
        side = body[-1]
        return DraftCallback(action="set_load_dir_direct", index=idx, dir=side)
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
    if body == "wC":
        return DraftCallback(action="wizard_cancel")
    if body.startswith("wT:"):
        return DraftCallback(action="wizard_type", dir=body[3:])
    if body.startswith("wD:"):
        return DraftCallback(action="wizard_dir", dir=body[3:])
    return None


def edit_prompt(edit: dict[str, Any], extracted: dict) -> str:
    kind = edit.get("kind")
    if kind == "L":
        return "אורך קורה L — הקלד מספר (למשל `13` או `L=13`)"
    if kind == "support":
        return "תכתוב את המרחק במטרים של הסמך מהקצה השמאלי של הקורה"
    if kind == "load_dir":
        idx = int(edit.get("index", 1))
        return f"כיוון עומס {idx}"
    if kind == "load":
        idx = int(edit.get("index", 1))
        return f"עומס {idx} — הקלד תיקון"
    if kind == "load_mag":
        return "תשלח את המשקל הנכון של העומס כמספר בלבד"
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
        return "תשלח את המרחק של העומס מהקצה השמאלי של הקורה"
    if kind == "load_angle":
        return "תרשום את הזווית של העומס"
    return "הקלד ערך חדש"


def build_add_load_wizard_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("אנכי", callback_data="d:wT:point")],
        [InlineKeyboardButton("אלכסוני", callback_data="d:wT:inclined")],
        [InlineKeyboardButton("צירי", callback_data="d:wT:axial")],
        [InlineKeyboardButton("מומנט", callback_data="d:wT:moment")],
        [InlineKeyboardButton("מפורס", callback_data="d:wT:distributed")],
        [InlineKeyboardButton("חזור", callback_data="d:wC")],
    ])


def build_add_load_wizard_dir_keyboard(load_type: str) -> InlineKeyboardMarkup:
    cancel_btn = [InlineKeyboardButton("ביטול הוספה", callback_data="d:wC")]
    if load_type == "point":
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("למטה ↓", callback_data="d:wD:down"),
             InlineKeyboardButton("למעלה ↑", callback_data="d:wD:up")],
            cancel_btn
        ])
    if load_type == "axial":
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("ימינה →", callback_data="d:wD:right"),
             InlineKeyboardButton("שמאלה ←", callback_data="d:wD:left")],
            cancel_btn
        ])
    if load_type == "moment":
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("עם השעון ↻", callback_data="d:wD:cw"),
             InlineKeyboardButton("נגד השעון ↺", callback_data="d:wD:ccw")],
            cancel_btn
        ])
    if load_type == "inclined":
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("↘ ימינה ולמטה", callback_data="d:wD:dr"),
             InlineKeyboardButton("↙ שמאלה ולמטה", callback_data="d:wD:dl")],
            cancel_btn
        ])
    return InlineKeyboardMarkup([cancel_btn])
