# -*- coding: utf-8 -*-
"""כלי חישוב Beam Solver + COG, schemas, והצגת תוצאות בעברית."""
from __future__ import annotations

import logging

import core.center_of_gravity as cog
import core.statics_calculator as solver
from google.genai import types

from bot.config import (
    BEAM_LOAD_ITEM_SCHEMA,
    CM2_PER_M2,
    CM_PER_M,
    COG_SHAPE_ITEM_SCHEMA,
    KN_PER_TON,
)
from bot.prompt_loader import get_statics_iron_rules_summary

log = logging.getLogger("beam_telegram_bot")


def _read_optional_ton(ld: dict, ton_key: str, legacy_kn_key: str) -> float | None:
    if ton_key in ld and ld[ton_key] is not None:
        return float(ld[ton_key])
    if legacy_kn_key in ld and ld[legacy_kn_key] is not None:
        return kn_to_ton(float(ld[legacy_kn_key]))
    return None


def _beam_tool_loads_schema() -> dict:
    return {
        "type": "array",
        "items": BEAM_LOAD_ITEM_SCHEMA,
        "description": "רשימת עומסים על הקורה",
    }


def _beam_geometry_schema(*, require_rb: bool) -> dict:
    props = {
        "L": {"type": "number", "description": "אורך הקורה [m]"},
        "ra_pos": {
            "type": "number",
            "description": "מיקום סמך A (צמד) [m], ברירת מחדל 0",
        },
        "loads": _beam_tool_loads_schema(),
    }
    if require_rb:
        props["rb_pos"] = {
            "type": "number",
            "description": "מיקום סמך B (גליל) [m], ברירת מחדל L",
        }
    required = ["L", "loads"]
    return {"type": "object", "properties": props, "required": required}


def code_execution_tool() -> types.Tool:
    """כלי הרצת קוד של Google — חישובים מספריים מדויקים (Python בסביבת Gemini)."""
    return types.Tool(code_execution=types.ToolCodeExecution())


def engineering_solver_tools() -> list[types.Tool]:
    iron = get_statics_iron_rules_summary()
    return [
        types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name="beam_solve_simply_supported",
                    description=(
                        "חישוב ריאקציות בקורה על שני סמכים (צמד ב-A, גליל ב-B) "
                        "באמצעות מנוע Beam Solver. מחזיר ריאקציות ושלבי חישוב. "
                        f"לפני הפעלה: {iron}"
                    ),
                    parameters=_beam_geometry_schema(require_rb=False),
                ),
                types.FunctionDeclaration(
                    name="beam_solve_cantilever",
                    description=(
                        "חישוב תגובות בזיז רתום משמאל (x=0) וחופשי מימין "
                        f"באמצעות מנוע Beam Solver. לפני הפעלה: {iron}"
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "L": {"type": "number", "description": "אורך הקורה [m]"},
                            "loads": _beam_tool_loads_schema(),
                        },
                        "required": ["L", "loads"],
                    },
                ),
                types.FunctionDeclaration(
                    name="beam_internal_forces",
                    description=(
                        "כוחות פנימיים N, Q, M משמאל ומימין לנקודה x "
                        "בקורה על שני סמכים (לאחר חישוב ריאקציות). "
                        f"מהלכים לפי חוקי הסימנים: {iron}"
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "L": {"type": "number", "description": "אורך הקורה [m]"},
                            "x": {"type": "number", "description": "נקודת חתך [m]"},
                            "ra_pos": {"type": "number", "description": "מיקום סמך A [m]"},
                            "rb_pos": {
                                "type": "number",
                                "description": "מיקום סמך B [m], ברירת מחדל L",
                            },
                            "loads": _beam_tool_loads_schema(),
                        },
                        "required": ["L", "x", "loads"],
                    },
                ),
                types.FunctionDeclaration(
                    name="cog_compute_centroid",
                    description=(
                        "חישוב מרכז כובד גלובלי Xc,Yc לקבוצת חתכים/פרופילים "
                        "באמצעות מנוע מרכז הכובד של Beam Solver. יחידות: m, m²."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "shapes": {
                                "type": "array",
                                "items": COG_SHAPE_ITEM_SCHEMA,
                                "description": "רשימת חתכים עם מיקום ומידות",
                            },
                        },
                        "required": ["shapes"],
                    },
                ),
            ]
        )
    ]


def gemini_tools(*, with_engineering: bool, chat_only: bool = False) -> list[types.Tool]:
    """Gemini API אינו מאפשר code_execution ו-function_calling באותה בקשה."""
    if with_engineering:
        return engineering_solver_tools()
    if chat_only:
        return []
    return [code_execution_tool()]


def fmt_solver_num(value: float) -> int | float:
    return solver.format_number(float(value))


def kn_to_ton(kn: float) -> int | float:
    return fmt_solver_num(float(kn) / KN_PER_TON)


def ton_to_kn(ton: float) -> float:
    return float(ton) * KN_PER_TON


def m_to_cm(m: float) -> float:
    return float(m) * CM_PER_M


def cm_to_m(cm: float) -> int | float:
    return fmt_solver_num(float(cm) / CM_PER_M)


def cm2_to_m2(cm2: float) -> int | float:
    return fmt_solver_num(float(cm2) / CM2_PER_M2)


def _read_ton(ld: dict, ton_key: str, legacy_kn_key: str) -> float:
    if ton_key in ld and ld[ton_key] is not None:
        return float(ld[ton_key])
    if legacy_kn_key in ld and ld[legacy_kn_key] is not None:
        return float(ld[legacy_kn_key]) / KN_PER_TON
    return 0.0


def ui_loads_to_solver(raw_loads: list, *, in_tons: bool = False) -> list[dict]:
    """ממיר עומסים מפורמט הכלי לפורמט solver.py.

    in_tons=False (ברירת מחדל): ערכים ב-kN לחישוב מנוע.
    in_tons=True: ערכים בטון — ל-beam_notebook (תווית t, אותם מספרים כמו בתשובת הבוט).
    """
    def _force(ton_val: float) -> float:
        return float(ton_val) if in_tons else ton_to_kn(ton_val)

    internal: list[dict] = []
    for ld in raw_loads:
        if not isinstance(ld, dict):
            continue
        kind = str(ld.get("kind", "")).lower()
        if kind == "point":
            mag_ton = _read_ton(ld, "magnitude_ton", "magnitude_kN")
            direction = str(ld.get("direction", "down"))
            item: dict = {
                "type": "point",
                "x": float(ld["x"]),
                "Fy": solver.point_magnitude_to_fy(_force(mag_ton), direction),
            }
            fx_ton = _read_optional_ton(ld, "Fx_ton", "Fx_kN")
            if fx_ton is not None and abs(fx_ton) > 1e-12:
                item["Fx"] = _force(fx_ton)
            internal.append(item)
        elif kind == "distributed":
            x1 = float(ld.get("x1", 0.0))
            x2 = float(ld.get("x2", 0.0))
            if x2 < x1:
                x1, x2 = x2, x1
            intensity_ton = _read_ton(ld, "intensity_ton_per_m", "intensity_kN_per_m")
            internal.append(
                {
                    "type": "distributed",
                    "x1": x1,
                    "x2": x2,
                    "w": solver.downward_intensity_to_w(_force(intensity_ton)),
                }
            )
        elif kind == "moment":
            m_ton = _read_ton(ld, "M_ton_m", "M_kNm")
            internal.append(
                {
                    "type": "moment",
                    "x": float(ld["x"]),
                    "M": _force(m_ton),
                }
            )
        elif kind == "inclined":
            mag_ton = _read_ton(ld, "magnitude_ton", "magnitude_kN")
            angle = float(ld.get("angle_deg", 0.0))
            incl_dir = str(ld.get("incl_dir", "dr"))
            internal.append(
                solver.normalize_inclined_load(
                    {
                        "type": "inclined",
                        "x": float(ld["x"]),
                        "inclMag": _force(mag_ton),
                        "inclAngle": angle,
                        "inclDir": incl_dir,
                    }
                )
            )
    return internal


def tool_beam_solve_simply_supported(args: dict) -> dict:
    L = float(args["L"])
    ra_pos = float(args.get("ra_pos", 0.0))
    rb_pos = float(args.get("rb_pos", L))
    loads = ui_loads_to_solver(list(args.get("loads") or []))
    ra_x, ra_y, rb_x, rb_y = solver.compute_reactions(loads, L, ra_pos, rb_pos)
    eq = solver.equilibrium_load_sums(loads, ra_pos, rb_pos)
    steps = solver.get_calculation_steps(
        loads, L, ra_pos, rb_pos, ra_x, ra_y, rb_x, rb_y
    )
    return {
        "engine": "beam_solver",
        "model": "pin_at_A_roller_at_B",
        "geometry_m": {
            "L": fmt_solver_num(L),
            "x_A": fmt_solver_num(ra_pos),
            "x_B": fmt_solver_num(rb_pos),
        },
        "reactions_ton": {
            "R_Ax": fmt_solver_num(kn_to_ton(ra_x)),
            "R_Ay": fmt_solver_num(kn_to_ton(ra_y)),
            "R_Bx": fmt_solver_num(kn_to_ton(rb_x)),
            "R_By": fmt_solver_num(kn_to_ton(rb_y)),
        },
        "load_sums_only": {
            "sum_Fx_ton": fmt_solver_num(kn_to_ton(eq["sum_fx"])),
            "sum_Fy_ton": fmt_solver_num(kn_to_ton(eq["sum_fy"])),
            "moment_about_A_ton_m": fmt_solver_num(kn_to_ton(eq["moment_about_ra"])),
        },
        "calculation_steps": steps,
    }


def tool_beam_solve_cantilever(args: dict) -> dict:
    L = float(args["L"])
    loads = ui_loads_to_solver(list(args.get("loads") or []))
    result = solver.solve_cantilever_beam(loads, L)
    steps = solver.get_cantilever_calculation_steps(loads, L, result)
    return {
        "engine": "beam_solver",
        "model": "cantilever_fixed_at_x0",
        "geometry_m": {"L": fmt_solver_num(L)},
        "reactions_ton": {
            "R_Ax": fmt_solver_num(kn_to_ton(result["R_Ax"])),
            "R_Ay": fmt_solver_num(kn_to_ton(result["R_Ay"])),
        },
        "fixed_end_moment_ton_m": fmt_solver_num(kn_to_ton(result["M_A"])),
        "calculation_steps": steps,
    }


def tool_beam_internal_forces(args: dict) -> dict:
    L = float(args["L"])
    x = float(args["x"])
    ra_pos = float(args.get("ra_pos", 0.0))
    rb_pos = float(args.get("rb_pos", L))
    loads = ui_loads_to_solver(list(args.get("loads") or []))
    ra_x, ra_y, rb_x, rb_y = solver.compute_reactions(loads, L, ra_pos, rb_pos)
    forces = solver.internal_forces_at_x(
        x, L, loads, ra_pos, rb_pos, ra_x, ra_y, rb_y
    )
    return {
        "engine": "beam_solver",
        "x_m": fmt_solver_num(x),
        "reactions_ton": {
            "R_Ax": kn_to_ton(ra_x),
            "R_Ay": kn_to_ton(ra_y),
            "R_By": kn_to_ton(rb_y),
        },
        "internal_forces_ton": {
            key: kn_to_ton(val) for key, val in forces.items()
        },
        "units": {"N": "טון", "V": "טון", "M": "טון·מ"},
    }


def _cog_catalog_keys() -> str:
    return ", ".join(sorted(cog._CATALOG.keys()))


def ui_shapes_to_cog(raw_shapes: list) -> list[dict]:
    """ממיר חתכים מפורמט הכלי לפורמט center_of_gravity.py."""
    shapes: list[dict] = []
    for idx, raw in enumerate(raw_shapes):
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("kind", "catalog")).lower()
        if "x_m" in raw or "y_m" in raw:
            x = m_to_cm(float(raw.get("x_m", 0.0)))
            y = m_to_cm(float(raw.get("y_m", 0.0)))
        else:
            x = float(raw.get("x_cm", raw.get("x", 0.0)))
            y = float(raw.get("y_cm", raw.get("y", 0.0)))

        if kind == "catalog" or raw.get("catalog_key"):
            key = str(raw.get("catalog_key", "")).strip()
            if key not in cog._CATALOG:
                raise ValueError(
                    f"פרופיל לא מוכר: {key}. אפשרויות: {_cog_catalog_keys()}"
                )
            shape = dict(cog._CATALOG[key])
        else:
            shape = {"type": kind}
            dims_in_m = "x_m" in raw or "y_m" in raw
            for dim in ("b", "h", "tf", "tw", "t", "b1", "b2", "D"):
                if dim in raw and raw[dim] is not None:
                    val = float(raw[dim])
                    shape[dim] = m_to_cm(val) if dims_in_m else val
            if kind not in (
                "i_section",
                "c_section",
                "l_section",
                "rhs",
                "tube",
            ):
                raise ValueError(f"סוג חתך לא נתמך: {kind}")

        shape["id"] = idx + 1
        shape["x"] = x
        shape["y"] = y
        label = raw.get("label")
        if label:
            shape["profile"] = str(label)
        shapes.append(shape)
    if not shapes:
        raise ValueError("חובה לספק לפחות חתך אחד")
    return shapes


def tool_cog_compute_centroid(args: dict) -> dict:
    shapes = ui_shapes_to_cog(list(args.get("shapes") or []))
    rows = cog._build_global_report_rows(shapes)
    xc, yc, sum_a, sum_ax, sum_ay = cog._compute_global_centroid(rows)
    if xc is None or yc is None:
        raise ValueError("לא ניתן לחשב מרכז כובד — סכום שטחים אפסי או שלילי")

    parts_rows: list[dict] = []
    for row in rows:
        parts_rows.append(
            {
                "label": row["Profile"],
                "area_m2": cm2_to_m2(float(row["Area (A)"])),
                "xi_m": cm_to_m(float(row["x_i"])),
                "yi_m": cm_to_m(float(row["y_i"])),
            }
        )

    sum_a_m2 = cm2_to_m2(sum_a)
    cm3_per_m3 = CM_PER_M**3
    sum_ax_m3 = fmt_solver_num(sum_ax / cm3_per_m3)
    sum_ay_m3 = fmt_solver_num(sum_ay / cm3_per_m3)
    xc_m = cm_to_m(xc)
    yc_m = cm_to_m(yc)
    steps = [
        "מרכז כובד גלובלי: Xc = Σ(A·xi)/ΣA , Yc = Σ(A·yi)/ΣA",
        f"ΣA = {sum_a_m2} m²",
        f"Σ(A·xi) = {sum_ax_m3} m³",
        f"Σ(A·yi) = {sum_ay_m3} m³",
        f"Xc = {sum_ax_m3}/{sum_a_m2} = {xc_m} m",
        f"Yc = {sum_ay_m3}/{sum_a_m2} = {yc_m} m",
    ]

    return {
        "engine": "center_of_gravity",
        "centroid_m": {
            "Xc": xc_m,
            "Yc": yc_m,
        },
        "sums": {
            "sum_A_m2": sum_a_m2,
            "sum_Ax_m3": sum_ax_m3,
            "sum_Ay_m3": sum_ay_m3,
        },
        "parts": parts_rows,
        "calculation_steps": steps,
        "catalog_profiles": list(cog._CATALOG.keys()),
    }


ENGINEERING_TOOL_HANDLERS = {
    "beam_solve_simply_supported": tool_beam_solve_simply_supported,
    "beam_solve_cantilever": tool_beam_solve_cantilever,
    "beam_internal_forces": tool_beam_internal_forces,
    "cog_compute_centroid": tool_cog_compute_centroid,
}


def execute_engineering_tool(name: str, args: dict) -> dict:
    handler = ENGINEERING_TOOL_HANDLERS.get(name)
    if handler is None:
        return {"error": f"unknown tool: {name}"}
    try:
        return handler(args)
    except (KeyError, TypeError, ValueError) as exc:
        log.warning("Engineering tool %s failed: %s", name, exc)
        return {"error": str(exc)}


def format_force_ton(value_ton: float) -> str:
    n = float(value_ton)
    mag = solver.format_number(abs(n))
    if abs(n) < 1e-9:
        return "0 טון"
    return f"{mag} טון {'↑' if n > 0 else '↓'}"


def format_horizontal_force_ton(value_ton: float) -> str:
    n = float(value_ton)
    mag = solver.format_number(abs(n))
    if abs(n) < 1e-9:
        return "0 טון"
    return f"{mag} טון {'→' if n > 0 else '←'}"


def format_moment_ton_m(value_ton_m: float) -> str:
    return f"{solver.format_number(float(value_ton_m))} טון·מ"


def format_engineering_tool_results(
    pairs: list[tuple[str, dict]],
    *,
    results_only: bool = False,
) -> str:
    """תשובה מיידית בעברית אחרי חישוב — בלי סיבוב שני ל-Gemini."""
    lines: list[str] = []
    for name, res in pairs:
        if res.get("error"):
            lines.append(f"שגיאה בחישוב: {res['error']}")
            continue
        if name == "cog_compute_centroid":
            c = res.get("centroid_m", res.get("centroid_cm", {}))
            if not results_only:
                lines.append("תוצאות מרכז כובד (Beam Solver):")
            lines.append(f"Xc = {c.get('Xc')} m")
            lines.append(f"Yc = {c.get('Yc')} m")
            if not results_only:
                sums = res.get("sums", {})
                if sums:
                    lines.append(
                        f"ΣA = {sums.get('sum_A_m2', sums.get('sum_A_cm2'))} m² | "
                        f"Σ(A·x) = {sums.get('sum_Ax_m3', sums.get('sum_Ax_cm3'))} | "
                        f"Σ(A·y) = {sums.get('sum_Ay_m3', sums.get('sum_Ay_cm3'))}"
                    )
                parts = res.get("parts") or []
                if parts:
                    lines.append("\nרכיבים:")
                    for i, p in enumerate(parts, 1):
                        area = p.get("area_m2", p.get("area_cm2"))
                        xi = p.get("xi_m", p.get("xi_cm"))
                        yi = p.get("yi_m", p.get("yi_cm"))
                        lines.append(
                            f"{i}. {p.get('label')}: A={area} m², "
                            f"xi={xi} m, yi={yi} m"
                        )
        elif name == "beam_solve_simply_supported":
            geo = res.get("geometry_m", {})
            r = res.get("reactions_ton", res.get("reactions_kN", {}))
            if not results_only:
                lines.append("תוצאות Beam Solver (שני סמכים):")
                if geo:
                    lines.append(
                        f"L={geo.get('L')} m, A={geo.get('x_A')} m, B={geo.get('x_B')} m"
                    )
            ray = float(r.get("R_Ay", 0))
            if "reactions_kN" in res and "reactions_ton" not in res:
                ray = kn_to_ton(ray)
            lines.append(f"R_Ay = {format_force_ton(ray)}")
            rby = float(r.get("R_By", 0))
            if "reactions_kN" in res and "reactions_ton" not in res:
                rby = kn_to_ton(rby)
            lines.append(f"R_By = {format_force_ton(rby)}")
            rax = float(r.get("R_Ax", 0))
            if "reactions_kN" in res and "reactions_ton" not in res:
                rax = kn_to_ton(rax)
            if abs(rax) > 1e-9:
                lines.append(f"R_Ax = {format_horizontal_force_ton(rax)}")
        elif name == "beam_solve_cantilever":
            r = res.get("reactions_ton", res.get("reactions_kN", {}))
            if not results_only:
                lines.append("תוצאות Beam Solver (זיז רתום):")
            ray = float(r.get("R_Ay", 0))
            rax = float(r.get("R_Ax", 0))
            if "reactions_kN" in res and "reactions_ton" not in res:
                ray = kn_to_ton(ray)
                rax = kn_to_ton(rax)
            lines.append(f"R_Ay = {format_force_ton(ray)}")
            if abs(rax) > 1e-9:
                lines.append(f"R_Ax = {format_horizontal_force_ton(rax)}")
            ma = res.get("fixed_end_moment_ton_m", res.get("fixed_end_moment_kNm"))
            if ma is not None:
                ma_val = float(ma)
                if res.get("fixed_end_moment_kNm") is not None and res.get("fixed_end_moment_ton_m") is None:
                    ma_val = kn_to_ton(ma_val)
                lines.append(f"M_A = {format_moment_ton_m(ma_val)}")
        elif name == "beam_internal_forces":
            f = res.get("internal_forces_ton", res.get("internal_forces", {}))
            x = res.get("x_m", "?")
            if not results_only:
                lines.append(f"כוחות פנימיים ב-x={x} m:")
            legacy = "internal_forces_ton" not in res

            def _f(key: str) -> float:
                val = float(f.get(key, 0))
                return kn_to_ton(val) if legacy else val

            lines.append(
                f"N: {format_force_ton(_f('N_left'))} / "
                f"{format_force_ton(_f('N_right'))} (שמאל/ימין)"
            )
            lines.append(
                f"Q: {format_force_ton(_f('V_left'))} / "
                f"{format_force_ton(_f('V_right'))} (שמאל/ימין)"
            )
            lines.append(
                f"M: {format_moment_ton_m(_f('M_left'))} / "
                f"{format_moment_ton_m(_f('M_right'))} (שמאל/ימין)"
            )
    if not lines:
        return "החישוב הסתיים אך לא התקבלה תוצאה להצגה."
    return "\n".join(lines)
