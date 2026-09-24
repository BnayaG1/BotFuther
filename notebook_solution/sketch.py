# -*- coding: utf-8 -*-
"""שרטוט התרגיל בכתב יד — פינה שמאלית עליונה, מיקומים לפי מטרים."""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from notebook_solution.page import _CELL_PX
from notebook_solution.problem import LoadMark, Problem, SupportMark

_INK = (36, 44, 62)
_FONT_FILES = (
    Path(r"C:\Windows\Fonts\segoepr.ttf"),
    Path(r"C:\Windows\Fonts\Inkfree.ttf"),
    Path(r"C:\Windows\Fonts\comic.ttf"),
    Path(__file__).resolve().parents[1] / ".notebook_fonts" / "Heebo-Regular.ttf",
)

_ORIGIN_X = _CELL_PX * 4
_ORIGIN_Y = _CELL_PX * 3
_BEAM_X0 = _ORIGIN_X + _CELL_PX * 5
_BEAM_SPAN = _CELL_PX * 58
_BEAM_Y = _ORIGIN_Y + _CELL_PX * 15
_DIST_PEAK_MIN = 48.0
_DIST_PEAK_MAX = 72.0
_POINT_MIN_SHAFT = 92
_POINT_ABOVE_DIST = 22


def draw_exercise(image: Image.Image, problem: Problem) -> None:
    draw = ImageDraw.Draw(image)
    fonts = _fonts()
    span = _BEAM_SPAN

    def at(x_m: float) -> float:
        return _BEAM_X0 + (float(x_m) / problem.length) * span

    _dimensions(draw, problem, at, fonts["dim"])
    for support in problem.supports:
        _support(draw, support, at(support.x), problem.length)
    _pen(draw, (at(0.0), _BEAM_Y), (at(problem.length), _BEAM_Y), width=4)
    dist_peaks = _distributed_peaks(problem.loads)
    for idx, load in enumerate(problem.loads):
        _load(draw, load, at, fonts["load"], problem.loads, dist_peaks, idx)
    for x_m, label in problem.stations:
        _text(draw, label, at(x_m), _BEAM_Y + 78, fonts["letter"])


def _fonts() -> dict[str, ImageFont.ImageFont]:
    path = next((item for item in _FONT_FILES if item.is_file()), None)
    if path is None:
        base = ImageFont.load_default()
        return {"load": base, "letter": base, "dim": base}
    return {
        "load": ImageFont.truetype(str(path), 30),
        "letter": ImageFont.truetype(str(path), 28),
        "dim": ImageFont.truetype(str(path), 24),
    }


def _pen(draw: ImageDraw.ImageDraw, a: tuple[float, float], b: tuple[float, float], *, width: int = 2) -> None:
    """קו עט. הקצוות נשארים על הנקודה המדויקת."""
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    length = math.hypot(dx, dy)
    if length < 1.5:
        draw.line([a, b], fill=_INK, width=width)
        return
    nx, ny = -dy / length, dx / length
    steps = max(4, int(length / 18))
    amp = 1.15
    points: list[tuple[float, float]] = []
    for i in range(steps + 1):
        t = i / steps
        wave = math.sin(math.pi * t) * math.sin((a[0] * 0.17 + a[1] * 0.11 + i) * 0.9)
        points.append((a[0] + dx * t + nx * amp * wave, a[1] + dy * t + ny * amp * wave))
    draw.line(points, fill=_INK, width=width, joint="curve")


def _head(draw: ImageDraw.ImageDraw, tail: tuple[float, float], tip: tuple[float, float]) -> None:
    angle = math.atan2(tip[1] - tail[1], tip[0] - tail[0])
    head = 13
    spread = 0.42
    left = (tip[0] - head * math.cos(angle - spread), tip[1] - head * math.sin(angle - spread))
    right = (tip[0] - head * math.cos(angle + spread), tip[1] - head * math.sin(angle + spread))
    draw.polygon([tip, left, right], fill=_INK)


def _arrow(draw: ImageDraw.ImageDraw, tail: tuple[float, float], tip: tuple[float, float], *, width: int = 2) -> None:
    _pen(draw, tail, tip, width=width)
    _head(draw, tail, tip)


def _text(draw: ImageDraw.ImageDraw, text: str, x: float, y: float, font: ImageFont.ImageFont) -> None:
    draw.text((x, y), text, font=font, fill=_INK, anchor="mm")


def _fmt(value: float) -> str:
    mag = abs(float(value))
    if abs(mag - round(mag)) < 1e-6:
        return str(int(round(mag)))
    return f"{mag:.2f}".rstrip("0").rstrip(".")


def _support(draw: ImageDraw.ImageDraw, support: SupportMark, x: float, length: float) -> None:
    if support.kind == "fixed":
        _fixed(draw, x, side="right" if support.x > length / 2 else "left")
    elif support.kind == "roller":
        _roller(draw, x)
    else:
        _pin(draw, x)


def _pin(draw: ImageDraw.ImageDraw, x: float) -> None:
    top = _BEAM_Y + 3
    base = top + 40
    half = 22
    _pen(draw, (x, top), (x - half, base), width=2)
    _pen(draw, (x - half, base), (x + half, base), width=2)
    _pen(draw, (x + half, base), (x, top), width=2)
    _ground(draw, x - half, x + half, base)


def _roller(draw: ImageDraw.ImageDraw, x: float) -> None:
    top = _BEAM_Y + 3
    base = top + 32
    half = 20
    _pen(draw, (x, top), (x - half, base), width=2)
    _pen(draw, (x - half, base), (x + half, base), width=2)
    _pen(draw, (x + half, base), (x, top), width=2)
    r = 7
    cy = base + r + 2
    for cx in (x - 9, x + 9):
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=_INK, width=2)


def _fixed(draw: ImageDraw.ImageDraw, x: float, *, side: str) -> None:
    top = _BEAM_Y - 28
    bot = _BEAM_Y + 28
    wall = 14
    if side == "right":
        draw.rectangle((x, top, x + wall, bot), outline=_INK, width=2)
        edge = x + wall
        sign = 1
    else:
        draw.rectangle((x - wall, top, x, bot), outline=_INK, width=2)
        edge = x - wall
        sign = -1
    for i in range(5):
        y = top + 6 + i * 10
        _pen(draw, (edge, y), (edge + sign * 12, y + 8), width=2)


def _ground(draw: ImageDraw.ImageDraw, x0: float, x1: float, y: float) -> None:
    _pen(draw, (x0, y), (x1, y), width=2)
    step = (x1 - x0) / 5
    for i in range(6):
        bx = x0 + i * step
        _pen(draw, (bx, y), (bx - 7, y + 9), width=2)


def _distributed_downward(load: LoadMark) -> bool:
    return (load.w1 + load.w2) / 2.0 > -1e-9


def _distributed_intensity(load: LoadMark) -> float:
    return max(abs(load.w1), abs(load.w2), abs(load.w))


def _distributed_peaks(loads: list[LoadMark]) -> list[float]:
    """גובה שיא לפי tm: כשיש שניים ומעלה, הכבד יותר גבוה קצת. כולם צמודים לקורה."""
    dist = [(i, _distributed_intensity(ld)) for i, ld in enumerate(loads) if ld.kind == "distributed"]
    peaks = [_DIST_PEAK_MAX] * len(loads)
    if len(dist) <= 1:
        return peaks
    intensities = [w for _, w in dist]
    w_max = max(intensities)
    w_min = min(intensities)
    span = w_max - w_min
    for i, w in dist:
        if span < 1e-9:
            peaks[i] = _DIST_PEAK_MAX
        else:
            t = (w - w_min) / span
            peaks[i] = _DIST_PEAK_MIN + t * (_DIST_PEAK_MAX - _DIST_PEAK_MIN)
    return peaks


def _distributed_vertical_clearance(
    loads: list[LoadMark], dist_peaks: list[float]
) -> tuple[float, float]:
    """מרווח מעל/מתחת לקורה (px) שתופסים עומסים מפורסים — לשרטוט עומס נקודתי."""
    above = 0.0
    below = 0.0
    label = 28.0
    for i, ld in enumerate(loads):
        if ld.kind != "distributed":
            continue
        peak = dist_peaks[i]
        if _distributed_downward(ld):
            above = max(above, 8.0 + peak + label)
        else:
            below = max(below, 8.0 + peak * 0.55 + label)
    return above, below


def _load(
    draw: ImageDraw.ImageDraw,
    load: LoadMark,
    at,
    font: ImageFont.ImageFont,
    loads: list[LoadMark],
    dist_peaks: list[float],
    load_idx: int,
) -> None:
    if load.kind == "distributed":
        _distributed(draw, load, at, font, dist_peaks[load_idx])
    elif load.kind == "point":
        _point(draw, load, at, font, _distributed_vertical_clearance(loads, dist_peaks))
    elif load.kind == "inclined":
        _inclined(draw, load, at, font)
    elif load.kind == "moment":
        _moment(draw, load, at, font, _moment_lift(load, loads, dist_peaks))


def _point(
    draw: ImageDraw.ImageDraw,
    load: LoadMark,
    at,
    font: ImageFont.ImageFont,
    dist_clear: tuple[float, float],
) -> None:
    dist_above, dist_below = dist_clear
    x = at(load.x)
    if abs(load.fy) >= 1e-9:
        down = load.fy > 0
        tip_y = _BEAM_Y - 4 if down else _BEAM_Y + 4
        if down:
            shaft = max(_POINT_MIN_SHAFT, dist_above + _POINT_ABOVE_DIST)
            tail_y = tip_y - shaft
        else:
            shaft = max(_POINT_MIN_SHAFT, dist_below + _POINT_ABOVE_DIST)
            tail_y = tip_y + shaft
        _arrow(draw, (x, tail_y), (x, tip_y), width=2)
        label_y = tail_y - 18 if down else tail_y + 18
        _text(draw, f"{_fmt(load.fy)}t", x, label_y, font)
    if abs(load.fx) >= 1e-9:
        right = load.fx > 0
        y = _BEAM_Y + 22
        tip_x = (x - 6) if right else (x + 6)
        tail_x = tip_x - 58 if right else tip_x + 58
        _arrow(draw, (tail_x, y), (tip_x, y), width=2)
        _text(draw, f"{_fmt(load.fx)}t", (tail_x + tip_x) / 2, y + 18, font)


def _distributed(
    draw: ImageDraw.ImageDraw,
    load: LoadMark,
    at,
    font: ImageFont.ImageFont,
    peak: float,
) -> None:
    x1, x2 = at(load.x1), at(load.x2)
    base = _BEAM_Y - 8

    def height(w: float) -> float:
        if abs(w) < 1e-9:
            return 0.0
        return peak if w > 0 else -peak * 0.55

    h1, h2 = height(load.w1), height(load.w2)
    _pen(draw, (x1, base - h1), (x2, base - h2), width=2)
    n = max(3, int(abs(x2 - x1) / 36))
    for i in range(n + 1):
        t = i / n
        x = x1 + (x2 - x1) * t
        h = h1 + (h2 - h1) * t
        if h > 22:
            _arrow(draw, (x, base - h), (x, base - 10), width=2)
        elif h < -22:
            _arrow(draw, (x, base - h), (x, base + 10), width=2)
    label = f"{_fmt(load.w2 if abs(load.w2) >= abs(load.w1) else load.w1)}tm"
    _text(draw, label, (x1 + x2) / 2, base - max(h1, h2, 0) - 18, font)


def _inclined(draw: ImageDraw.ImageDraw, load: LoadMark, at, font: ImageFont.ImageFont) -> None:
    x = at(load.x)
    y = _BEAM_Y - 4
    angle = math.radians(max(15.0, min(75.0, abs(load.angle_deg))))
    length = 88
    sign = 1.0 if load.incl_dir == "dr" else -1.0
    dx = sign * length * math.cos(angle)
    dy = -length * math.sin(angle)
    tail = (x - dx, y + dy)
    tip = (x, y)
    _arrow(draw, tail, tip, width=2)
    _angle_mark(draw, x, y, angle, load.incl_dir)
    # קו מהשליש העליון: שעה 1:30, או 10:30 אם העומס בשליש הימני של הקורה.
    start = (tail[0] + (tip[0] - tail[0]) / 3, tail[1] + (tip[1] - tail[1]) / 3)
    target_y = _ORIGIN_Y + _CELL_PX * 2
    rise = max(start[1] - target_y, _CELL_PX * 6)
    toward_left = x >= _BEAM_X0 + _BEAM_SPAN * (2.0 / 3.0)
    side = -1.0 if toward_left else 1.0
    end = (start[0] + side * rise, start[1] - rise)
    _pen(draw, start, end, width=1)
    label_x = end[0] + side * 22
    _text(draw, f"{_fmt(load.angle_deg)}°", label_x, end[1] - 16, font)
    _text(draw, f"{_fmt(load.magnitude)}t", label_x, end[1] + 10, font)


def _angle_mark(draw, x, y, angle, incl_dir) -> None:
    radius = 26
    if incl_dir == "dr":
        a0, a1 = math.pi, math.pi - angle
    else:
        a0, a1 = 0.0, angle
    steps = 10
    points = []
    for i in range(steps + 1):
        t = a0 + (a1 - a0) * i / steps
        points.append((x + radius * math.cos(t), y - radius * math.sin(t)))
    if len(points) >= 2:
        draw.line(points, fill=_INK, width=2)


def _moment_lift(load: LoadMark, loads: list[LoadMark], dist_peaks: list[float]) -> float:
    peak = 0.0
    found = False
    for i, other in enumerate(loads):
        if other.kind != "distributed":
            continue
        if other.x1 - 1e-6 <= load.x <= other.x2 + 1e-6:
            found = True
            peak = max(peak, dist_peaks[i])
    if not found:
        return 0.0
    return 14.0 + peak


def _moment(draw: ImageDraw.ImageDraw, load: LoadMark, at, font: ImageFont.ImageFont, lift: float) -> None:
    cx, cy, radius = at(load.x), _BEAM_Y - 6 - lift, 30
    clockwise = load.moment > 0
    start, end = (math.pi * 1.05, math.pi * 1.95) if clockwise else (math.pi * 1.95, math.pi * 1.05)
    steps = 16
    points = []
    for i in range(steps + 1):
        t = start + (end - start) * i / steps
        points.append((cx + radius * math.cos(t), cy + radius * math.sin(t)))
    if len(points) >= 2:
        draw.line(points, fill=_INK, width=2, joint="curve")
        _head(draw, points[-3], points[-1])
    _text(draw, f"{_fmt(load.moment)}tm", cx, cy - radius - 16, font)


def _dimensions(draw: ImageDraw.ImageDraw, problem: Problem, at, font: ImageFont.ImageFont) -> None:
    marks = problem.stations
    if len(marks) < 2:
        return
    rows: list[list[tuple[float, float]]] = []
    if len(marks) > 2:
        rows.append([(marks[i][0], marks[i + 1][0]) for i in range(len(marks) - 1)])
    rows.append([(0.0, problem.length)])
    y0 = _BEAM_Y + 112
    for row_i, segments in enumerate(rows):
        y = y0 + row_i * 46
        for x1_m, x2_m in segments:
            if x2_m - x1_m <= 1e-6:
                continue
            x1, x2 = at(x1_m), at(x2_m)
            for x in (x1, x2):
                _pen(draw, (x, _BEAM_Y + 92), (x, y + 4), width=1)
            _pen(draw, (x1, y), (x2, y), width=2)
            _tick(draw, x1, y)
            _tick(draw, x2, y)
            _text(draw, _fmt(x2_m - x1_m), (x1 + x2) / 2, y - 14, font)


def _tick(draw: ImageDraw.ImageDraw, x: float, y: float) -> None:
    _pen(draw, (x - 5, y + 5), (x + 5, y - 5), width=2)
