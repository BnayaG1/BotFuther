# -*- coding: utf-8 -*-
"""Static beam calculations: pin at A, roller at B (R_Bx = 0). y up, kN, m.

Internal convention: Fy and w are negative when the load acts downward (y-axis up).
"""
import math
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

Number = Union[int, float]


def beam_plot_x_coords(L: float, positions: List[float]) -> np.ndarray:
    """x samples from beam origin (0) to L, including supports and load points."""
    Lf = float(L)
    dense = np.linspace(0.0, Lf, 600, dtype=float)
    pts = np.asarray(positions, dtype=float)
    xs = np.sort(np.unique(np.concatenate([dense, pts])))
    if xs.size == 0 or float(xs[0]) > 1e-9:
        xs = np.insert(xs, 0, 0.0)
    return xs


def format_number(num: float) -> Number:
    rounded = round(num, 2)
    if rounded == int(rounded):
        return int(rounded)
    return rounded


def inclined_components(
    mag: float, angle_deg: float, incl_dir: str = "dr"
) -> Tuple[float, float]:
    """Return (Fx, Fy) from magnitude, angle from +x (deg), and direction dl|dr."""
    m = abs(float(mag))
    if m <= 1e-12:
        return 0.0, 0.0
    rad = math.radians(float(angle_deg))
    c, s = math.cos(rad), math.sin(rad)
    d = str(incl_dir or "dr").lower()
    fx = (-m * c) if d == "dl" else (m * c)
    return fx, -m * s


def infer_inclined_polar(ld: dict) -> Tuple[float, float, str]:
    """Infer (mag, angle_deg, incl_dir) from an inclined load dict."""
    mag_raw = ld.get("inclMag")
    ang_raw = ld.get("inclAngle")
    if mag_raw is not None and ang_raw is not None:
        mag = abs(float(mag_raw))
        angle = float(ang_raw)
    else:
        fx = float(ld.get("Fx", 0.0) or 0.0)
        fy = float(ld.get("Fy", 0.0) or 0.0)
        mag = math.hypot(fx, fy)
        angle = math.degrees(
            math.atan2(abs(fy), abs(fx) if abs(fx) > 1e-12 else 1e-12)
        )
    fx0 = float(ld.get("Fx", 0.0) or 0.0)
    incl_dir = str(ld.get("inclDir", "dl" if fx0 < 0 else "dr"))
    if incl_dir not in ("dl", "dr"):
        incl_dir = "dl" if fx0 < 0 else "dr"
    return mag, angle, incl_dir


def normalize_inclined_load(ld: dict) -> dict:
    """Ensure Fx/Fy match F·cos(θ) and F·sin(θ) for stored magnitude and angle."""
    out = dict(ld)
    mag, angle, incl_dir = infer_inclined_polar(out)
    fx, fy = inclined_components(mag, angle, incl_dir)
    out["Fx"] = fx
    out["Fy"] = fy
    out["inclMag"] = mag
    out["inclAngle"] = angle
    out["inclDir"] = incl_dir
    return out


def downward_magnitude_to_fy(value: float) -> float:
    """Positive UI magnitude = downward load -> internal Fy < 0 (y up)."""
    return -abs(float(value))


def point_magnitude_to_fy(value: float, direction: str = "down") -> float:
    """Point-load UI magnitude with explicit direction -> internal signed Fy."""
    mag = abs(float(value))
    return mag if direction == "up" else -mag


def downward_intensity_to_w(value: float) -> float:
    """Positive UI magnitude = downward distributed intensity -> internal w < 0."""
    return -abs(float(value))


def _moment_from_udl_about_cut(w: float, x1: float, x2: float, x: float) -> float:
    if x <= x1:
        return 0.0
    if x < x2:
        a = x - x1
        return w * a * a / 2.0
    span = x2 - x1
    centroid = (x1 + x2) / 2.0
    return w * span * (x - centroid)


def compute_reactions(
    loads: List[dict], L: float, ra_pos: float, rb_pos: float
) -> Tuple[float, float, float, float]:
    """
    Pin at A, roller at B: R_Ax, R_Ay, R_By; R_Bx = 0.
    Equilibrium: Sum Fy=0, Sum Fx=0, Sum M_A=0.
    """
    sum_fx = 0.0
    sum_fy = 0.0
    moment_about_ra = 0.0
    for load in loads:
        if load["type"] == "point":
            sum_fy += load["Fy"]
            sum_fx += float(load.get("Fx", 0.0))
            moment_about_ra -= load["Fy"] * (load["x"] - ra_pos)
        elif load["type"] == "distributed":
            span = load["x2"] - load["x1"]
            resultant = load["w"] * span
            centroid = (load["x1"] + load["x2"]) / 2
            sum_fy += resultant
            moment_about_ra -= resultant * (centroid - ra_pos)
        elif load["type"] == "moment":
            moment_about_ra += load["M"]
        elif load["type"] == "inclined":
            sum_fx += load["Fx"]
            sum_fy += load["Fy"]
            moment_about_ra -= load["Fy"] * (load["x"] - ra_pos)
    if L <= 0:
        raise ValueError("אורך הקורה חייב להיות חיובי.")
    if abs(rb_pos - ra_pos) < 1e-9:
        raise ValueError("מיקומי הסמכים חייבים להיות שונים.")
    arm_b = rb_pos - ra_pos
    rb_y = moment_about_ra / arm_b
    ra_y = -sum_fy - rb_y
    ra_x = -sum_fx
    rb_x = 0.0
    return ra_x, ra_y, rb_x, rb_y


def bending_moment(
    x: float,
    loads: List[dict],
    ra_y: float,
    rb_y: float,
    ra_pos: float,
    rb_pos: float,
) -> float:
    M = 0.0
    if x >= ra_pos:
        M += ra_y * (x - ra_pos)
    if x >= rb_pos:
        M += rb_y * (x - rb_pos)
    for load in loads:
        if load["type"] == "point":
            if x >= load["x"]:
                M += load["Fy"] * (x - load["x"])
        elif load["type"] == "distributed":
            M += _moment_from_udl_about_cut(load["w"], load["x1"], load["x2"], x)
        elif load["type"] == "moment":
            if x >= load["x"]:
                M += load["M"]
        elif load["type"] == "inclined":
            if x >= load["x"]:
                M += load["Fy"] * (x - load["x"])
    return M


def shear_force(
    x: float,
    loads: List[dict],
    ra_y: float,
    rb_y: float,
    ra_pos: float,
    rb_pos: float,
) -> float:
    V = 0.0
    if x >= ra_pos:
        V += ra_y
    if x >= rb_pos:
        V += rb_y
    for load in loads:
        if load["type"] == "point":
            if x >= load["x"]:
                V += load["Fy"]
        elif load["type"] == "distributed":
            x1, x2, w = load["x1"], load["x2"], load["w"]
            if x >= x1:
                V += w * (min(x, x2) - x1)
        elif load["type"] == "inclined":
            if x >= load["x"]:
                V += load["Fy"]
    return V


def normal_force(x: float, loads: List[dict], ra_x: float, ra_pos: float) -> float:
    N = 0.0
    if x >= ra_pos:
        N += ra_x
    for load in loads:
        if load["type"] == "inclined" and x >= load["x"]:
            N += load["Fx"]
        if load["type"] == "point" and x >= load["x"]:
            N += float(load.get("Fx", 0.0))
    return N


def solve_cantilever_beam(loads: List[dict], L: float) -> Dict[str, Any]:
    """Independent fixed-left/free-right cantilever solution. Fixed support at x=0."""
    if L <= 0:
        raise ValueError("אורך הקורה חייב להיות חיובי.")
    sum_fx = 0.0
    sum_fy = 0.0
    load_moment_about_wall = 0.0
    positions = [0.0, float(L)]
    for load in loads:
        if load["type"] == "point":
            x = float(load["x"])
            fy = float(load["Fy"])
            fx = float(load.get("Fx", 0.0))
            sum_fx += fx
            sum_fy += fy
            load_moment_about_wall += fy * x
            positions.append(x)
        elif load["type"] == "distributed":
            x1 = float(load["x1"])
            x2 = float(load["x2"])
            w = float(load["w"])
            span = x2 - x1
            resultant = w * span
            centroid = (x1 + x2) / 2.0
            sum_fy += resultant
            load_moment_about_wall += resultant * centroid
            positions.extend([x1, x2])
        elif load["type"] == "moment":
            x = float(load["x"])
            load_moment_about_wall -= float(load["M"])
            positions.append(x)
        elif load["type"] == "inclined":
            x = float(load["x"])
            fx = float(load["Fx"])
            fy = float(load["Fy"])
            sum_fx += fx
            sum_fy += fy
            load_moment_about_wall += fy * x
            positions.append(x)

    reaction_x = -sum_fx
    reaction_y = -sum_fy
    reaction_moment = load_moment_about_wall
    diagram_fixed_moment = load_moment_about_wall
    xs = beam_plot_x_coords(float(L), positions)
    shear = np.array([cantilever_shear_force(x, loads, reaction_y) for x in xs], dtype=float)
    moment = np.array(
        [cantilever_bending_moment(x, loads, reaction_y, diagram_fixed_moment) for x in xs],
        dtype=float,
    )
    normal = np.array([normal_force(x, loads, reaction_x, 0.0) for x in xs], dtype=float)
    return {
        "R_Ax": reaction_x,
        "R_Ay": reaction_y,
        "M_A": reaction_moment,
        "diagram_fixed_moment": diagram_fixed_moment,
        "xs": xs,
        "shear": shear,
        "moment": moment,
        "normal": normal,
    }


def cantilever_shear_force(x: float, loads: List[dict], reaction_y: float) -> float:
    V = float(reaction_y)
    for load in loads:
        if load["type"] == "point":
            if x >= load["x"]:
                V += float(load["Fy"])
        elif load["type"] == "distributed":
            x1, x2, w = float(load["x1"]), float(load["x2"]), float(load["w"])
            if x >= x1:
                V += w * (min(float(x), x2) - x1)
        elif load["type"] == "inclined":
            if x >= load["x"]:
                V += float(load["Fy"])
    return V


def cantilever_bending_moment(
    x: float, loads: List[dict], reaction_y: float, fixed_moment: float
) -> float:
    M = float(fixed_moment) + float(reaction_y) * float(x)
    for load in loads:
        if load["type"] == "point":
            if x >= load["x"]:
                M += float(load["Fy"]) * (float(x) - float(load["x"]))
        elif load["type"] == "distributed":
            M += _moment_from_udl_about_cut(
                float(load["w"]), float(load["x1"]), float(load["x2"]), float(x)
            )
        elif load["type"] == "moment":
            if x >= load["x"]:
                M += float(load["M"])
        elif load["type"] == "inclined":
            if x >= load["x"]:
                M += float(load["Fy"]) * (float(x) - float(load["x"]))
    return M


def get_cantilever_calculation_steps(
    loads: List[dict], L: float, result: Dict[str, Any]
) -> List[str]:
    lines = [
        "מודל: זיז רתום משמאל ב-x=0 וחופשי מימין. התגובות מחושבות בבלוק נפרד ממודל שני הסמכים.",
        f"L={L:g} m; ריתום ב-A: x=0.",
    ]
    sum_fx = sum_fy = moment_about_wall = 0.0
    for i, load in enumerate(loads, 1):
        if load["type"] == "point":
            fx = float(load.get("Fx", 0.0))
            fy = float(load["Fy"])
            m = fy * float(load["x"])
            sum_fx += fx
            sum_fy += fy
            moment_about_wall += m
            lines.append(f"עומס {i} נקודתי: Fx={fx:g}, Fy={fy:g}; Fy*x={m:g} kN·m.")
        elif load["type"] == "distributed":
            span = float(load["x2"]) - float(load["x1"])
            resultant = float(load["w"]) * span
            centroid = (float(load["x1"]) + float(load["x2"])) / 2.0
            m = resultant * centroid
            sum_fy += resultant
            moment_about_wall += m
            lines.append(f"עומס {i} מפולג: R={resultant:g}, x_c={centroid:g}; R*x_c={m:g} kN·m.")
        elif load["type"] == "moment":
            m = -float(load["M"])
            moment_about_wall += m
            lines.append(f"עומס {i} מומנט טהור: תרומה ל-M_A={m:g} kN·m.")
        elif load["type"] == "inclined":
            fx = float(load["Fx"])
            fy = float(load["Fy"])
            m = fy * float(load["x"])
            sum_fx += fx
            sum_fy += fy
            moment_about_wall += m
            lines.append(f"עומס {i} אלכסוני: Fx={fx:g}, Fy={fy:g}; Fy*x={m:g} kN·m.")
    lines.append(f"ΣFy(loads)={sum_fy:g}; ΣFx(loads)={sum_fx:g}; ΣM_loads@A={moment_about_wall:g}.")
    lines.append(f"R_Ay = -ΣFy = {result['R_Ay']:g} kN.")
    lines.append(f"R_Ax = -ΣFx = {result['R_Ax']:g} kN.")
    lines.append(f"M_A = ΣM_loads@A = {result['M_A']:g} kN·m (בסימן דיאגרמת הכפיפה).")
    return lines


def get_calculation_steps(
    loads: List[dict],
    L: float,
    ra_pos: float,
    rb_pos: float,
    ra_x: float,
    ra_y: float,
    rb_x: float,
    rb_y: float,
) -> List[str]:
    lines: List[str] = []
    arm_b = rb_pos - ra_pos
    lines.append(
        "מודל: סמכת צמד ב-A, גליל ב-B. בממשק: גודל חיובי = עומס כלפי מטה (מלמעלה). "
        "בחישוב פנימי: Fy,w שליליים = כלפי מטה (ציר y כלפי מעלה)."
    )
    lines.append(f"L={L:g} m, x_A={ra_pos:g}, x_B={rb_pos:g}, מרווח B-A={arm_b:g} m.")
    sum_fx = sum_fy = moment_about_ra = 0.0
    for i, load in enumerate(loads, 1):
        if load["type"] == "point":
            fy = load["Fy"]
            fx = float(load.get("Fx", 0.0))
            m = fy * (load["x"] - ra_pos)
            sum_fy += fy
            sum_fx += fx
            moment_about_ra += m
            lines.append(f"עומס {i} נקודתי: Fx={fx:g}, Fy={fy:g} kN; תרומה ל-M_A={m:g} kN·m.")
        elif load["type"] == "distributed":
            span = load["x2"] - load["x1"]
            w = load["w"]
            r = w * span
            xc = (load["x1"] + load["x2"]) / 2
            m = r * (xc - ra_pos)
            sum_fy += r
            moment_about_ra += m
            lines.append(f"עומס {i} מפולג: w={w:g}, M_A={m:g} kN·m.")
        elif load["type"] == "moment":
            moment_about_ra += load["M"]
            lines.append(f"עומס {i} מומנט טהור M={load['M']:g} kN·m.")
        elif load["type"] == "inclined":
            fx, fy = load["Fx"], load["Fy"]
            m = fy * (load["x"] - ra_pos)
            sum_fx += fx
            sum_fy += fy
            moment_about_ra += m
            lines.append(f"עומס {i} אלכסוני: Fx={fx:g}, Fy={fy:g}; M_A={m:g} kN·m.")
    lines.append(f"ΣFy (עומסים)={sum_fy:g} kN; ΣFx (עומסים)={sum_fx:g} kN; ΣM_A={moment_about_ra:g} kN·m.")
    lines.append(f"R_By = -ΣM_A/(x_B-x_A) = {rb_y:g} kN.")
    lines.append(f"R_Ay = -ΣFy - R_By = {ra_y:g} kN.")
    lines.append(f"R_Ax = -ΣFx = {ra_x:g} kN; R_Bx = {rb_x:g} kN (גליל).")
    return lines


def build_ai_explanation_payload(
    loads: List[dict],
    L: float,
    ra_pos: float,
    rb_pos: float,
    ra_x: float,
    ra_y: float,
    rb_x: float,
    rb_y: float,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    p: Dict[str, Any] = {
        "schema": "beam_solver.v2_pin_roller",
        "model": {"A": "pin", "B": "roller_no_Rbx"},
        "geometry": {"L_m": L, "x_A": ra_pos, "x_B": rb_pos},
        "loads": loads,
        "reactions_kN": {
            "R_Ax": ra_x,
            "R_Ay": ra_y,
            "R_Bx": rb_x,
            "R_By": rb_y,
        },
        "calculation_steps": get_calculation_steps(
            loads, L, ra_pos, rb_pos, ra_x, ra_y, rb_x, rb_y
        ),
    }
    if extra:
        p["extra"] = extra
    return p


def critical_x_positions(
    loads: List[dict], L: float, ra_pos: float, rb_pos: float
) -> List[float]:
    """כל מיקומי x לאורך הקורה (קצוות, סמכים, עומסים)."""
    pts = [0.0, float(L), float(ra_pos), float(rb_pos)]
    for load in loads:
        if load["type"] in ("point", "moment", "inclined"):
            pts.append(float(load["x"]))
        elif load["type"] == "distributed":
            pts.extend([float(load["x1"]), float(load["x2"])])
    return sorted(set(round(p, 6) for p in pts))


def equilibrium_load_sums(
    loads: List[dict], ra_pos: float, rb_pos: float
) -> Dict[str, float]:
    """תרומות העומסים בלבד לשיווי משקל — אותה קונבנציה כמו compute_reactions."""
    sum_fx = 0.0
    sum_fy = 0.0
    moment_about_ra = 0.0
    moment_about_rb = 0.0
    for load in loads:
        if load["type"] == "point":
            sum_fy += load["Fy"]
            sum_fx += float(load.get("Fx", 0.0))
            moment_about_ra -= load["Fy"] * (load["x"] - ra_pos)
            moment_about_rb -= load["Fy"] * (load["x"] - rb_pos)
        elif load["type"] == "distributed":
            span = load["x2"] - load["x1"]
            resultant = load["w"] * span
            centroid = (load["x1"] + load["x2"]) / 2.0
            sum_fy += resultant
            moment_about_ra -= resultant * (centroid - ra_pos)
            moment_about_rb -= resultant * (centroid - rb_pos)
        elif load["type"] == "moment":
            moment_about_ra += load["M"]
            moment_about_rb += load["M"]
        elif load["type"] == "inclined":
            sum_fx += load["Fx"]
            sum_fy += load["Fy"]
            moment_about_ra -= load["Fy"] * (load["x"] - ra_pos)
            moment_about_rb -= load["Fy"] * (load["x"] - rb_pos)
    return {
        "sum_fx": sum_fx,
        "sum_fy": sum_fy,
        "moment_about_ra": moment_about_ra,
        "moment_about_rb": moment_about_rb,
    }


def internal_forces_at_x(
    x: float,
    L: float,
    loads: List[dict],
    ra_pos: float,
    rb_pos: float,
    ra_x: float,
    ra_y: float,
    rb_y: float,
    eps: float = 1e-5,
) -> Dict[str, float]:
    """ערכי N, Q, M משמאל ומימין לנקודה x (לקפיצות)."""
    xl = max(0.0, x - eps)
    xr = min(float(L), x + eps)
    return {
        "N_left": normal_force(xl, loads, ra_x, ra_pos),
        "N_right": normal_force(xr, loads, ra_x, ra_pos),
        "V_left": shear_force(xl, loads, ra_y, rb_y, ra_pos, rb_pos),
        "V_right": shear_force(xr, loads, ra_y, rb_y, ra_pos, rb_pos),
        "M_left": bending_moment(xl, loads, ra_y, rb_y, ra_pos, rb_pos),
        "M_right": bending_moment(xr, loads, ra_y, rb_y, ra_pos, rb_pos),
    }
