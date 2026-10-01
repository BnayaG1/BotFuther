# -*- coding: utf-8 -*-
"""משוואות שיווי משקל — כמו במחברת הישנה, בכתב יד ליד הציור."""
from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

import core.statics_calculator as solver
from core.distributed_moments import distributed_moment_segments_about
from notebook_solution.math_format import _expand_calc_parentheses, _join_calc_terms
from notebook_solution.page import _CELL_PX
from notebook_solution.sketch import (
    _BEAM_SPAN,
    _BEAM_X0,
    _BEAM_Y,
    _FONT_FILES,
    _INK,
    _pen,
    draw_notebook_text,
    notebook_text_width,
)

_U_FORCE = "t"
_U_MOMENT = "tm"
_LINE_H = 36
_GROUP_GAP = 22
_BODY_GAP = 18


def draw_equilibrium(
    image: Image.Image,
    extracted: dict,
    solved: dict,
    *,
    show_solution: bool = True,
) -> float:
    groups = _groups(extracted, solved, show_solution=show_solution)
    if not groups:
        return float(_BEAM_Y)
    draw = ImageDraw.Draw(image)
    fonts = _fonts()
    x0 = _BEAM_X0 + _BEAM_SPAN + _CELL_PX * 3 * 2.0
    y = float(_BEAM_Y)
    for i, group in enumerate(groups):
        if i:
            y += _GROUP_GAP
            if group.get("extra_gap"):
                y += _LINE_H
        y = _draw_group(draw, x0, y, group, fonts)
    return y


def _groups(
    extracted: dict,
    solved: dict,
    *,
    show_solution: bool = True,
) -> list[dict]:
    del solved
    data = extracted if isinstance(extracted, dict) else {}
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    skip = bool(meta.get("skip_vision_normalize")) or meta.get("source") == "exercise_generator"
    if not skip:
        from bot.vision import finalize_beam_extraction

        data = finalize_beam_extraction(data, merge_nearby_point_loads=False)
    beam = data.get("beam") if isinstance(data.get("beam"), dict) else {}
    try:
        length = float(beam.get("L", 0) or 0)
    except (TypeError, ValueError):
        return []
    if length <= 0:
        return []

    from bot.engineering import ui_loads_to_solver
    from bot.vision import resolve_beam_support_geometry, vision_loads_to_tool_loads

    raw = beam.get("loads") or []
    loads = ui_loads_to_solver(
        vision_loads_to_tool_loads([dict(ld) for ld in raw if isinstance(ld, dict)]),
        in_tons=True,
    )
    mode, ra_pos, rb_pos = resolve_beam_support_geometry(beam)
    if mode == "cantilever":
        res = solver.solve_cantilever_beam(loads, length, wall_pos=float(ra_pos))
        ax = float(res.get("R_Ax", 0.0))
        ay = float(res.get("R_Ay", 0.0))
        by = 0.0
        ma = float(res.get("M_A", 0.0))
    else:
        ax, ay, _bx, by = solver.compute_reactions(
            loads, length, float(ra_pos), float(rb_pos)
        )
        ma = 0.0

    support = "cantilever" if mode == "cantilever" else "supports"
    return _build_groups(
        loads,
        support_mode=support,
        length=length,
        ra_pos=float(ra_pos),
        rb_pos=float(rb_pos),
        ax=ax,
        ay=ay,
        by=by,
        ma=ma,
        show_solution=show_solution,
    )


def _build_groups(
    loads: list[dict],
    *,
    support_mode: str,
    length: float,
    ra_pos: float,
    rb_pos: float,
    ax: float,
    ay: float,
    by: float,
    ma: float,
    show_solution: bool = True,
) -> list[dict]:
    groups: list[dict] = [_fx_group(loads, ax, show_solution=show_solution)]
    if support_mode == "cantilever":
        wall = float(ra_pos)
        right_wall = wall > float(length) / 2.0
        m_terms = _m_terms_about(loads, wall, invert_arm=right_wall)
        parts = ["Ma"]
        if m_terms:
            parts.extend(m_terms)
        groups.append(
            _sigma_group(
                "ΣMA = 0:",
                _join_calc_terms(parts),
                "Ma",
                ma,
                _U_MOMENT,
                show_solution=show_solution,
            )
        )
        fy_parts = ["Ay"]
        fy_parts.extend(_fy_terms(loads))
        groups.append(
            _sigma_group(
                "ΣFy = 0:",
                _join_calc_terms(fy_parts),
                "Ay",
                ay,
                _U_FORCE,
                show_solution=show_solution,
            )
        )
        return groups

    if abs(rb_pos - ra_pos) > 1e-9:
        ma_parts = list(_m_terms_about(loads, ra_pos)) or ["0"]
        by_term = _reaction_vertical_moment_term("By", rb_pos, ra_pos)
        if by_term:
            ma_parts.append(by_term)
        groups.append(
            _sigma_group(
                "ΣMa = 0:",
                _join_calc_terms(ma_parts),
                "By",
                by,
                _U_FORCE,
                show_solution=show_solution,
            )
        )
        mb_parts = list(_m_terms_about(loads, rb_pos)) or ["0"]
        ay_term = _reaction_vertical_moment_term("Ay", ra_pos, rb_pos)
        if ay_term:
            mb_parts.append(ay_term)
        groups.append(
            _sigma_group(
                "ΣMb = 0:",
                _join_calc_terms(mb_parts),
                "Ay",
                ay,
                _U_FORCE,
                show_solution=show_solution,
            )
        )
    if show_solution:
        groups.append(_fy_check_group(loads, ay, by))
    return groups


def _fx_group(
    loads: list[dict],
    ax: float,
    *,
    show_solution: bool = True,
) -> dict:
    axial: list[tuple[float, float]] = []
    for ld in loads:
        if ld.get("type") not in ("point", "inclined"):
            continue
        fx = float(ld.get("Fx", 0.0) or 0.0)
        if abs(fx) > 1e-9:
            axial.append((float(ld.get("x", 0.0) or 0.0), fx))
    axial.sort(key=lambda p: p[0])
    if not axial:
        if not show_solution:
            return {
                "header": "ΣFx = 0:",
                "lines": ["Ax = 0"],
                "answer": "",
            }
        return {
            "header": "ΣFx = 0:",
            "lines": [],
            "answer": f"Ax = 0 {_U_FORCE}",
        }
    parts = ["Ax"]
    for _, fx in axial:
        mag = solver.format_number(abs(fx))
        parts.append(f"+ {mag}" if fx >= 0 else f"− {mag}")
    return _sigma_group(
        "ΣFx = 0:",
        _join_calc_terms(parts),
        "Ax",
        ax,
        _U_FORCE,
        show_solution=show_solution,
    )


def _fy_terms(loads: list[dict]) -> list[str]:
    items: list[tuple[float, float]] = []
    for ld in loads:
        kind = ld.get("type")
        if kind in ("point", "inclined"):
            fy = float(ld.get("Fy", 0.0) or 0.0)
            if abs(fy) > 1e-9:
                items.append((float(ld.get("x", 0.0) or 0.0), fy))
        elif kind == "distributed":
            w = float(ld.get("w", 0.0) or 0.0)
            w1 = ld.get("w1")
            w2 = ld.get("w2")
            x1 = float(ld.get("x1", 0.0) or 0.0)
            x2 = float(ld.get("x2", 0.0) or 0.0)
            span = x2 - x1
            if span <= 1e-9:
                continue
            if w1 is not None or w2 is not None:
                wa = float(w1 if w1 is not None else 0.0)
                wb = float(w2 if w2 is not None else w)
                force = (wa + wb) * 0.5 * span
                denom = wa + wb
                xc = (x1 + x2) / 2.0 if abs(denom) < 1e-15 else x1 + span * (wa + 2.0 * wb) / (3.0 * denom)
            else:
                force = w * span
                xc = (x1 + x2) / 2.0
            if abs(force) < 1e-9:
                continue
            items.append((xc, force))
    items.sort(key=lambda p: p[0])
    out: list[str] = []
    for _, fy in items:
        mag = solver.format_number(abs(fy))
        out.append(f"+ {mag}" if fy >= 0 else f"− {mag}")
    return out


def _signed_num(value: float) -> str:
    mag = solver.format_number(abs(value))
    return f"− {mag}" if value < 0 else str(mag)


def _fy_check_group(loads: list[dict], ay: float, by: float | None) -> dict:
    parts = [_signed_num(ay)]
    if by is not None:
        parts.append(f"+ {solver.format_number(abs(by))}" if by >= 0 else f"− {solver.format_number(abs(by))}")
    parts.extend(_fy_terms(loads))
    return {
        "header": "ΣFy = 0:",
        "lines": [f"{_join_calc_terms(parts)} = 0"],
        "answer": "",
        "extra_gap": True,
    }


def _sigma_group(
    header: str,
    eq: str,
    name: str,
    value: float,
    unit: str,
    *,
    show_solution: bool = True,
) -> dict:
    answer = f"{name} = {solver.format_number(value)} {unit}".strip()
    eq_clean = str(eq).strip()
    if not show_solution:
        return {
            "header": header,
            "lines": [f"{eq_clean} = 0"],
            "answer": "",
        }
    if eq_clean == answer or eq_clean == f"{name} = {solver.format_number(value)}":
        return {"header": header, "lines": [], "answer": answer}
    lines = [f"{eq_clean} = 0"]
    if "(" in eq_clean:
        expanded = _expand_calc_parentheses(eq_clean)
        if expanded.strip() != eq_clean:
            lines.append(f"{expanded.strip()} = 0")
    return {"header": header, "lines": lines, "answer": answer}


def _moment_term(resultant: float, arm: float) -> str:
    if abs(resultant) < 1e-9 or abs(arm) < 1e-9:
        return ""
    moment = -resultant * arm
    body = f"({solver.format_number(abs(resultant))}·{solver.format_number(abs(arm))})"
    return f"+ {body}" if moment >= 0 else f"− {body}"


def _reaction_vertical_moment_term(name: str, reaction_pos: float, ref_pos: float) -> str:
    arm = float(reaction_pos) - float(ref_pos)
    if abs(arm) < 1e-9:
        return ""
    moment = -arm
    body = f"{name}·{solver.format_number(abs(arm))}"
    return f"+ {body}" if moment >= 0 else f"− {body}"


def _m_terms_about(loads: list[dict], x_ref: float, *, invert_arm: bool = False) -> list[str]:
    items: list[tuple[float, str]] = []
    xref = float(x_ref)
    for ld in loads:
        kind = ld.get("type")
        if kind in ("point", "inclined"):
            fy = float(ld.get("Fy", 0.0) or 0.0)
            x = float(ld.get("x", 0.0) or 0.0)
            arm = (xref - x) if invert_arm else (x - xref)
            term = _moment_term(fy, arm)
            if term:
                items.append((x, term))
        elif kind == "distributed":
            w = float(ld.get("w", 0.0) or 0.0)
            w1 = ld.get("w1")
            w2 = ld.get("w2")
            x1 = float(ld.get("x1", 0.0) or 0.0)
            x2 = float(ld.get("x2", 0.0) or 0.0)
            for seg in distributed_moment_segments_about(
                w,
                x1,
                x2,
                xref,
                w1=None if w1 is None else float(w1),
                w2=None if w2 is None else float(w2),
            ):
                arm = -seg.arm if invert_arm else seg.arm
                term = _moment_term(seg.force, arm)
                if term:
                    items.append((seg.x1, term))
        elif kind == "moment":
            mm = float(ld.get("M", 0.0) or 0.0)
            if abs(mm) < 1e-9:
                continue
            x = float(ld.get("x", 0.0) or 0.0)
            body = f"({solver.format_number(abs(mm))})"
            term = f"+ {body}" if mm >= 0 else f"− {body}"
            items.append((x, term))
    items.sort(key=lambda pair: pair[0])
    return [term for _, term in items]


def _fonts() -> dict[str, ImageFont.ImageFont]:
    path = next((item for item in _FONT_FILES if item.is_file()), None)
    if path is None:
        base = ImageFont.load_default()
        return {"text": base}
    return {"text": ImageFont.truetype(str(path), 26)}


def _text_w(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> float:
    box = draw.textbbox((0, 0), text, font=font)
    return float(box[2] - box[0])


def _draw_group(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    group: dict,
    fonts: dict,
) -> float:
    font = fonts["text"]
    header = group["header"]
    header_w = notebook_text_width(draw, header, font)
    body_x = x + header_w + _BODY_GAP
    draw_notebook_text(draw, (x, y), header, font, _INK, "lm")
    lines = list(group["lines"])
    if lines:
        draw.text((body_x, y), lines[0], font=font, fill=_INK, anchor="lm")
        if group.get("extra_gap"):
            mark_x = body_x + _text_w(draw, lines[0], font) + 22
            _check(draw, mark_x, y)
        y += _LINE_H
        for line in lines[1:]:
            draw.text((body_x, y), line, font=font, fill=_INK, anchor="lm")
            y += _LINE_H
    if group.get("answer"):
        _answer(draw, body_x, y, group["answer"], font)
        return y + _LINE_H
    return y


def _check(draw: ImageDraw.ImageDraw, x: float, y: float) -> None:
    _pen(draw, (x - 6, y), (x + 2, y + 10), width=3)
    _pen(draw, (x + 2, y + 10), (x + 16, y - 10), width=3)


def _answer(draw: ImageDraw.ImageDraw, x: float, y: float, text: str, font: ImageFont.ImageFont) -> None:
    w = _text_w(draw, text, font)
    pad_x, pad_y = 10, 12
    left, right = x - pad_x, x + w + pad_x
    top, bot = y - pad_y, y + pad_y
    _pen(draw, (left, top), (right, top), width=2)
    _pen(draw, (right, top), (right, bot), width=2)
    _pen(draw, (right, bot), (left, bot), width=2)
    _pen(draw, (left, bot), (left, top), width=2)
    draw.text((x, y), text, font=font, fill=_INK, anchor="lm")
