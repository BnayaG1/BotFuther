# -*- coding: utf-8 -*-
from __future__ import annotations

import math

from exercise_generator.render.canvas import Canvas
from exercise_generator.render import style
from exercise_generator.schema import (
    DistributedLoad,
    InclinedLoad,
    LoadItem,
    MomentLoad,
    PointLoad,
    Support,
)
from exercise_generator.units import format_force_hebrew, format_moment_hebrew, format_udl_hebrew


def _arrowprops(
    *,
    lw: float,
    mutation_scale: float,
    filled: bool = True,
    shrink_a: float = 2.0,
    shrink_b: float = 2.0,
) -> dict:
    """ראש חץ שפיצי — שווה-שוקיים עם זווית חדה בכיוון ההצבעה."""
    return dict(
        arrowstyle=style.ARROW_STYLE_FILLED if filled else style.ARROW_STYLE_LINE,
        color="black",
        lw=lw,
        mutation_scale=mutation_scale,
        shrinkA=shrink_a,
        shrinkB=shrink_b,
    )


def draw_loads(
    canvas: Canvas,
    loads: list[LoadItem],
    *,
    supports: list[Support] | None = None,
    beam_L: float | None = None,
) -> None:
    shift_all_left = _any_inclined_at_any_udl_end(loads)
    udl_heights = _udl_draw_heights(loads)
    wall_x = _fixed_wall_x(supports)
    L = float(beam_L) if beam_L is not None else float(canvas.L)
    # UDL קודם (מאחורי חצים מרוכזים)
    for ld in loads:
        if isinstance(ld, DistributedLoad):
            _draw_udl(
                canvas,
                ld,
                loads,
                height=udl_heights[id(ld)],
                shift_all_left=shift_all_left,
            )
    for ld in loads:
        if isinstance(ld, PointLoad):
            _draw_point(canvas, ld, loads, wall_x=wall_x, beam_L=L)
        elif isinstance(ld, InclinedLoad):
            _draw_inclined(canvas, ld, loads)
        elif isinstance(ld, MomentLoad):
            _draw_moment(canvas, ld)


def _fixed_wall_x(supports: list[Support] | None) -> float | None:
    if not supports:
        return None
    for s in supports:
        if s.type == "fixed":
            return float(s.x)
    return None


def _udl_draw_heights(loads: list[LoadItem]) -> dict[int, float]:
    """גובה ציור: מפורס יחיד = קבוע; שני מפורסים — הגבוה ב־t/m טיפה גבוה יותר."""
    udls = [ld for ld in loads if isinstance(ld, DistributedLoad)]
    base = style.UDL_BASE_HEIGHT
    taller = base * 1.22  # «קצת» יותר גבוה
    out: dict[int, float] = {}
    if len(udls) <= 1:
        for ld in udls:
            out[id(ld)] = base
        return out
    # שני מפורסים (או יותר) — מי עם |w| גדול יותר גבוה בציור
    by_w = sorted(udls, key=lambda ld: abs(float(ld.w)))
    for ld in by_w[:-1]:
        out[id(ld)] = base
    out[id(by_w[-1])] = taller
    return out


def _any_inclined_at_any_udl_end(loads: list[LoadItem], *, tol: float = 1e-6) -> bool:
    """האם יש אלכסוני בנקודת התחלה/סיום של מפורס כלשהו בתרגיל."""
    udl_ends: list[float] = []
    for ld in loads:
        if isinstance(ld, DistributedLoad):
            udl_ends.append(float(ld.x1))
            udl_ends.append(float(ld.x2))
    for other in loads:
        if isinstance(other, InclinedLoad):
            x = float(other.x)
            if any(abs(x - end) <= tol for end in udl_ends):
                return True
    return False


def _inclined_dr_at_udl_right_end(
    loads: list[LoadItem],
    ld: DistributedLoad,
    *,
    tol: float = 1e-6,
) -> bool:
    """אלכסוני נוטה-ימינה (dr) בנקודה שבה מסתיים מפורס (ב־x2)."""
    x2 = float(ld.x2)
    for other in loads:
        if (
            isinstance(other, InclinedLoad)
            and other.incl_dir == "dr"
            and abs(float(other.x) - x2) <= tol
        ):
            return True
    return False


def _draw_udl(
    canvas: Canvas,
    ld: DistributedLoad,
    loads: list[LoadItem],
    *,
    height: float,
    shift_all_left: bool,
) -> None:
    ax = canvas.ax
    x1_m, x2_m = float(ld.x1), float(ld.x2)
    if x2_m <= x1_m:
        return
    x1, x2 = canvas.x(x1_m), canvas.x(x2_m)
    h = height
    y0 = canvas.y_beam + style.BEAM_HEIGHT / 2 + 0.08
    y_top = y0 + h
    # רק הקו העליון — בלי סגירה תחתונה/צדדים כמלבן
    ax.plot([x1, x2], [y_top, y_top], color="black", lw=style.LINE_WIDTH, zorder=5)
    n = max(3, int((x2_m - x1_m) / max(canvas.L * 0.04, 0.35)))
    n *= 2  # פי 2 חצים (כולל הקטנים)
    # חצים אמצעיים מקוצרים בשני שליש; שני הצדדיים באורך מלא
    mid_arrow_len = h / 3
    for i in range(n + 1):
        t = i / n
        x = x1 + t * (x2 - x1)
        if i == 0 or i == n:
            y_tip = y0
        else:
            y_tip = y_top - mid_arrow_len
        # מוט מחובר לקו העליון + ראש חץ בקצה (בלי shrink שמנתק)
        span = abs(y_top - y_tip)
        head = min(0.14, 0.35 * span) if span > 1e-9 else 0.0
        y_head = y_tip + head
        if span > 1e-9:
            ax.plot(
                [x, x],
                [y_top, y_head],
                color="black",
                lw=1.0,
                solid_capstyle="butt",
                zorder=6,
            )
        if head > 1e-9:
            ax.annotate(
                "",
                xy=(x, y_tip),
                xytext=(x, y_head),
                arrowprops=_arrowprops(
                    lw=1.0,
                    mutation_scale=10,
                    filled=False,
                    shrink_a=0.0,
                    shrink_b=0.0,
                ),
                zorder=6,
            )
    if _inclined_dr_at_udl_right_end(loads, ld):
        # אלכסוני dr בסיום המפורס — t/m בצד ימין למעלה (קרוב לקצה הימני)
        label_x = x1 + 0.90 * (x2 - x1)
        label_y = y_top + 0.10
    elif shift_all_left:
        # אלכסוני בקצה מפורס — משקל בחלק השמאלי, טיפה נמוך יותר
        label_x = x1 + 0.30 * (x2 - x1)
        label_y = y_top + 0.05
    else:
        label_x = 0.5 * (x1 + x2)
        label_y = y_top + 0.15
    ax.text(
        label_x,
        label_y,
        format_udl_hebrew(ld.w),
        ha="center",
        va="bottom",
        fontsize=style.LOAD_LABEL_FONTSIZE,
        linespacing=1.1,
        zorder=7,
    )


def _draw_point(
    canvas: Canvas,
    ld: PointLoad,
    loads: list[LoadItem],
    *,
    wall_x: float | None = None,
    beam_L: float | None = None,
) -> None:
    fx = float(ld.Fx)
    fy = float(ld.Fy)
    if abs(fy) < 1e-12 and abs(fx) >= 1e-12:
        _draw_axial(canvas, ld, loads, wall_x=wall_x, beam_L=beam_L)
        return
    ax = canvas.ax
    x = canvas.x(float(ld.x))
    y0 = canvas.y_beam + style.BEAM_HEIGHT / 2 + 0.05
    length = style.POINT_ARROW_LEN
    ax.annotate(
        "",
        xy=(x, y0),
        xytext=(x, y0 + length),
        arrowprops=_arrowprops(lw=2.0, mutation_scale=14),
        zorder=8,
    )
    ax.text(
        x,
        y0 + length + 0.08,
        format_force_hebrew(abs(fy)),
        ha="center",
        va="bottom",
        fontsize=style.LOAD_LABEL_FONTSIZE,
        linespacing=1.1,
        zorder=8,
    )


def _other_load_at_x(
    loads: list[LoadItem],
    x_m: float,
    *,
    skip: LoadItem,
    tol: float = 1e-6,
) -> bool:
    """האם יש עומס אחר (לא סמך) בנקודה x_m."""
    for other in loads:
        if other is skip:
            continue
        if isinstance(other, DistributedLoad):
            if abs(float(other.x1) - x_m) <= tol or abs(float(other.x2) - x_m) <= tol:
                return True
        elif isinstance(other, (PointLoad, InclinedLoad, MomentLoad)):
            if abs(float(other.x) - x_m) <= tol:
                return True
    return False


def _axial_label_below_due_to_inclined(
    loads: list[LoadItem],
    x_m: float,
    fx: float,
    *,
    tol: float = 0.05,
) -> bool:
    """שתי סיטואציות: צירי← ואלכסוני dr מטר מימין; או צירי→ ואלכסוני dl מטר משמאל."""
    for other in loads:
        if not isinstance(other, InclinedLoad):
            continue
        ox = float(other.x)
        if fx < 0 and other.incl_dir == "dr" and abs(ox - (x_m + 1.0)) <= tol:
            return True
        if fx > 0 and other.incl_dir == "dl" and abs(ox - (x_m - 1.0)) <= tol:
            return True
    return False


def _axial_clip_stem_at_wall(
    x_m: float,
    fx: float,
    *,
    wall_x: float | None,
    beam_L: float,
    tol: float = 0.05,
) -> bool:
    """ריתום + צירי מטר ממנו בכיוון ההפוך מהקיר — לקצר חץ שלא יעבור את הקורה."""
    if wall_x is None:
        return False
    if abs(wall_x) <= tol:
        # קיר שמאל — צירי ב־~1 מ' שמצביע ימינה (הרחק מהקיר)
        return fx > 0 and abs(x_m - 1.0) <= tol
    if abs(wall_x - beam_L) <= tol:
        # קיר ימין — צירי ב־~L-1 שמצביע שמאלה (הרחק מהקיר)
        return fx < 0 and abs(x_m - (beam_L - 1.0)) <= tol
    return False


def _axial_points_at_wall(
    x_m: float,
    fx: float,
    *,
    wall_x: float | None,
    tol: float = 0.05,
) -> bool:
    """צירי שטיפ שלו על נקודת הריתום ומצביע אל הקיר."""
    if wall_x is None:
        return False
    if abs(x_m - wall_x) > tol:
        return False
    if abs(wall_x) <= tol:
        return fx < 0  # קיר שמאל — מצביע שמאלה
    return fx > 0  # קיר ימין — מצביע ימינה


def _draw_axial(
    canvas: Canvas,
    ld: PointLoad,
    loads: list[LoadItem],
    *,
    wall_x: float | None = None,
    beam_L: float | None = None,
) -> None:
    """חץ אופקי על גובה הקורה — Fx>0 ימינה, Fx<0 שמאלה (טיפ בנקודת ההצבה)."""
    ax = canvas.ax
    x_m = float(ld.x)
    x = canvas.x(x_m)
    y = canvas.y_beam
    stem = style.POINT_ARROW_LEN * 1.15  # כאורך חץ אלכסוני
    fx = float(ld.Fx)
    L = float(beam_L) if beam_L is not None else float(canvas.L)
    if fx > 0:
        x_tail = x - stem
    else:
        x_tail = x + stem
    if _axial_clip_stem_at_wall(x_m, fx, wall_x=wall_x, beam_L=L):
        # הזנב נשאר על הקורה — לא עובר את הקצה ליד הריתום
        x_tail = max(canvas.x(0.0), x_tail) if fx > 0 else min(canvas.x(L), x_tail)
    ax.annotate(
        "",
        xy=(x, y),
        xytext=(x_tail, y),
        arrowprops=_arrowprops(lw=2.0, mutation_scale=14),
        zorder=8,
    )
    actual_stem = abs(x - x_tail)
    # מצביע על הריתום / עומס נוסף בנקודה → מעל אמצע; אחרת מעל ראש החץ
    if _axial_points_at_wall(x_m, fx, wall_x=wall_x) or _other_load_at_x(
        loads, x_m, skip=ld
    ):
        label_x = (x + x_tail) / 2
    else:
        # ראש החץ נמצא ליד הטיפ, מוסט מעט לכיוון הזנב — לא מעל נקודת התחנה
        head_inset = min(actual_stem * 0.14, actual_stem * 0.5)
        label_x = x - head_inset if fx > 0 else x + head_inset
    if _axial_label_below_due_to_inclined(loads, x_m, fx):
        label_y = y - 0.22
        va = "top"
    else:
        label_y = y + 0.22
        va = "bottom"
    ax.text(
        label_x,
        label_y,
        format_force_hebrew(abs(fx)),
        ha="center",
        va=va,
        fontsize=style.LOAD_LABEL_FONTSIZE,
        linespacing=1.1,
        zorder=8,
    )


def _udl_touches_x(loads: list[LoadItem], x_m: float, *, tol: float = 1e-6) -> bool:
    """האם עומס מפורס מתחיל או מסתיים ב־x_m."""
    for other in loads:
        if isinstance(other, DistributedLoad):
            if abs(float(other.x1) - x_m) <= tol or abs(float(other.x2) - x_m) <= tol:
                return True
    return False


def _draw_inclined(
    canvas: Canvas,
    ld: InclinedLoad,
    loads: list[LoadItem],
) -> None:
    ax = canvas.ax
    x_m = float(ld.x)
    x = canvas.x(x_m)
    y0 = canvas.y_beam + style.BEAM_HEIGHT / 2 + 0.05
    true_angle = float(ld.angle_deg)
    # זווית < 20°: ציור כאילו 20°, התווית נשארת עם הזווית האמיתית
    draw_angle = max(true_angle, 20.0)
    ang = math.radians(draw_angle)
    length = style.POINT_ARROW_LEN * 1.15
    # dr = down-right: tip at beam, tail up-left
    sign = 1.0 if ld.incl_dir == "dr" else -1.0
    dx = sign * length * math.cos(ang)
    dy = length * math.sin(ang)
    ax.annotate(
        "",
        xy=(x, y0),
        xytext=(x - dx, y0 + dy),
        arrowprops=_arrowprops(lw=2.0, mutation_scale=14),
        zorder=8,
    )
    # מפורס בקצה / זווית > 50° → משקל מעל העומס (זנב); אחרת מעל שפיץ ראש החץ
    if _udl_touches_x(loads, x_m) or true_angle > 50.0:
        label_x, label_y = x - dx, y0 + dy + 0.08
    else:
        # מעל שפיץ ראש החץ (קרוב לקצה התחתון של החץ)
        label_x = x - dx * 0.1
        label_y = y0 + dy * 0.1 + 0.18
    ax.text(
        label_x,
        label_y,
        format_force_hebrew(ld.magnitude_ton),
        ha="center",
        va="bottom",
        fontsize=style.LOAD_LABEL_FONTSIZE,
        linespacing=1.1,
        zorder=8,
    )
    # זווית על הקשת בין האופקי לחץ — כמו בשרטוט
    _draw_inclined_angle_mark(
        ax,
        x=x,
        y=y0,
        draw_angle_deg=draw_angle,
        label_angle_deg=true_angle,
        incl_dir=ld.incl_dir,
    )


def _draw_inclined_angle_mark(
    ax,
    *,
    x: float,
    y: float,
    draw_angle_deg: float,
    label_angle_deg: float,
    incl_dir: str,
) -> None:
    """קשת זווית + תווית במרכז הזווית (בין הקורה לקו החץ), לא על ראש החץ."""
    import numpy as np

    ang = math.radians(draw_angle_deg)
    # רדיוס גדול מספיק כדי שהתווית לא תיפול על ראש החץ
    arc_r = style.POINT_ARROW_LEN * 0.55
    if incl_dir == "dr":
        # חץ מטה-ימינה: הזווית בין אופקי שמאלה לקו החץ (מעל הקורה)
        a0, a1 = math.pi, math.pi - ang
    else:
        # חץ מטה-שמאלה: הזווית בין אופקי ימינה לקו החץ (מעל הקורה)
        a0, a1 = 0.0, ang

    phis = np.linspace(a0, a1, 48)
    xs = x + arc_r * np.cos(phis)
    ys = y + arc_r * np.sin(phis)
    ax.plot(xs, ys, color="black", lw=1.0, zorder=8)

    # תווית בנקודת אמצע הקשת, עם דחיפה קלה החוצה מהקודקוד
    mid = 0.5 * (a0 + a1)
    label_r = arc_r * 0.72
    ax.text(
        x + label_r * math.cos(mid),
        y + label_r * math.sin(mid) - 0.06,
        f"{label_angle_deg:g}°",
        ha="center",
        va="center",
        fontsize=12 * 0.82,
        zorder=9,
    )


def _draw_moment(canvas: Canvas, ld: MomentLoad) -> None:
    ax = canvas.ax
    x = canvas.x(float(ld.x))
    y = canvas.y_beam
    r = style.MOMENT_RADIUS
    import numpy as np

    # בסיס גיאומטריה: אורך קשת מקוצר בשליש
    tip_deg = 320.0
    arc_span_deg = (320.0 - 40.0) * (2 / 3)
    start_deg = tip_deg - arc_span_deg
    tip_span = 0.35
    clockwise = float(ld.M) >= 0
    # #region agent log
    try:
        import json as _json, time as _time
        from pathlib import Path as _Path
        _p = _Path(__file__).resolve().parents[2] / "debug-1522a6.log"
        with _p.open("a", encoding="utf-8") as _f:
            _f.write(_json.dumps({"sessionId":"1522a6","hypothesisId":"A","location":"loads.py:_draw_moment","message":"draw moment sign","data":{"M":float(ld.M),"clockwise_drawn":bool(clockwise),"x":float(ld.x)},"timestamp":int(_time.time()*1000)})+"\n")
    except Exception:
        pass
    # #endregion

    if clockwise:
        # מומנט חיובי: עם כיוון השעון + סיבוב 180° עם כיוון השעון
        tip_deg -= 180.0
        start_deg -= 180.0
        ts = np.linspace(math.radians(tip_deg), math.radians(start_deg), 60)
        t_end = ts[-1]
        t_tail = t_end + tip_span
    else:
        # מומנט שלילי: נגד כיוון השעון + סיבוב 90° עם כיוון השעון (25% מסיבוב מלא)
        tip_deg -= 90.0
        start_deg -= 90.0
        ts = np.linspace(math.radians(start_deg), math.radians(tip_deg), 60)
        t_end = ts[-1]
        t_tail = t_end - tip_span

    xs = x + r * np.cos(ts)
    ys = y + r * np.sin(ts)
    ax.plot(xs, ys, color="black", lw=style.LINE_WIDTH, zorder=8)
    ax.annotate(
        "",
        xy=(x + r * math.cos(t_end), y + r * math.sin(t_end)),
        xytext=(x + r * math.cos(t_tail), y + r * math.sin(t_tail)),
        arrowprops=_arrowprops(lw=1.5, mutation_scale=12),
        zorder=9,
    )
    tip_x = x + r * math.cos(t_end)
    tip_y = y + r * math.sin(t_end)
    if clockwise:
        ax.text(
            x + r * math.cos(t_end) * 1.15 + 0.1,
            y + r * math.sin(t_end) * 1.15,
            format_moment_hebrew(abs(ld.M)),
            ha="left",
            va="bottom",
            fontsize=style.LOAD_LABEL_FONTSIZE,
            linespacing=1.1,
            zorder=9,
        )
    else:
        # מומנט שלילי: המספר+tm צמוד לראש החץ משמאלו
        ax.text(
            tip_x - 0.08,
            tip_y,
            format_moment_hebrew(abs(ld.M)),
            ha="right",
            va="center",
            fontsize=style.LOAD_LABEL_FONTSIZE,
            linespacing=1.1,
            zorder=9,
        )
