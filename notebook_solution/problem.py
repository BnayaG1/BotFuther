# -*- coding: utf-8 -*-
"""קריאת נתוני התרגיל מתוך extracted. חיובי למטה בשרטוט."""
from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class SupportMark:
    label: str
    kind: str
    x: float


@dataclass
class LoadMark:
    kind: str
    x: float = 0.0
    x1: float = 0.0
    x2: float = 0.0
    fy: float = 0.0
    fx: float = 0.0
    w: float = 0.0
    w1: float = 0.0
    w2: float = 0.0
    moment: float = 0.0
    angle_deg: float = 0.0
    incl_dir: str = "dr"
    magnitude: float = 0.0


@dataclass
class Problem:
    length: float
    supports: list[SupportMark] = field(default_factory=list)
    loads: list[LoadMark] = field(default_factory=list)
    stations: list[tuple[float, str]] = field(default_factory=list)


def parse_problem(extracted: dict) -> Problem | None:
    """None אם אין אורך וסמכים — אין מה לשרטט."""
    data = extracted if isinstance(extracted, dict) else {}
    beam = data.get("beam") if isinstance(data.get("beam"), dict) else data
    if not isinstance(beam, dict):
        return None
    try:
        length = float(beam.get("L", 0) or 0)
    except (TypeError, ValueError):
        return None
    if length <= 0:
        return None

    supports = _supports(beam, length)
    if not supports:
        return None
    loads = _loads(beam)
    stations = _stations(length, supports, loads, beam.get("labeled_points"))
    return Problem(length=length, supports=supports, loads=loads, stations=stations)


def _num(item: dict, *keys: str, default: float = 0.0) -> float:
    for key in keys:
        if key not in item or item[key] is None:
            continue
        try:
            return float(item[key])
        except (TypeError, ValueError):
            continue
    return default


def _supports(beam: dict, length: float) -> list[SupportMark]:
    raw = beam.get("supports")
    marks: list[SupportMark] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("type", "")).lower().strip()
            if kind not in ("pin", "roller", "fixed"):
                continue
            label = str(item.get("label") or "").strip()
            marks.append(SupportMark(label, kind, _clamp(_num(item, "x"), length)))
    if marks:
        return _fill_labels(marks)
    mode = str(beam.get("support_mode", "")).lower().strip()
    ra = _clamp(_num(beam, "ra_pos"), length)
    rb = _clamp(_num(beam, "rb_pos", default=length), length)
    if mode == "cantilever":
        return [SupportMark("A", "fixed", ra)]
    if mode == "simply_supported":
        return _fill_labels([
            SupportMark("A", "pin", ra),
            SupportMark("B", "roller", rb),
        ])
    return []


def _fill_labels(marks: list[SupportMark]) -> list[SupportMark]:
    used = {m.label for m in marks if m.label}
    letters = (ch for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if ch not in used)
    out: list[SupportMark] = []
    for mark in marks:
        label = mark.label or next(letters, "?")
        out.append(SupportMark(label, mark.kind, mark.x))
    return out


def _loads(beam: dict) -> list[LoadMark]:
    raw = beam.get("loads")
    items = [dict(ld) for ld in raw if isinstance(ld, dict)] if isinstance(raw, list) else []
    have_dist = any(str(ld.get("type", "")).lower() in ("distributed", "udl") for ld in items)
    if not have_dist and isinstance(beam.get("distributed_loads"), list):
        for item in beam["distributed_loads"]:
            if isinstance(item, dict):
                items.append(item)
    out: list[LoadMark] = []
    for item in items:
        mark = _one_load(item)
        if mark is not None:
            out.append(mark)
    return out


def _one_load(item: dict) -> LoadMark | None:
    kind = str(item.get("type") or item.get("kind") or "").lower().strip()
    if kind in ("distributed", "udl"):
        x1 = _num(item, "x1", "start_x")
        x2 = _num(item, "x2", "end_x")
        if x2 < x1:
            x1, x2 = x2, x1
        if x2 - x1 <= 1e-9:
            return None
        w = _num(item, "w", "magnitude")
        shape = str(item.get("shape") or "rectangular").lower()
        if "w_start" in item or "w_end" in item:
            w1 = _num(item, "w_start", default=0.0)
            w2 = _num(item, "w_end", default=w)
        elif shape == "triangular":
            w1, w2 = 0.0, w
        else:
            w1 = w2 = w
        if abs(w1) < 1e-9 and abs(w2) < 1e-9:
            return None
        return LoadMark(kind="distributed", x1=x1, x2=x2, w=w, w1=w1, w2=w2)
    if kind == "point":
        fy = _num(item, "Fy", "fy")
        fx = _num(item, "Fx", "fx")
        if abs(fy) < 1e-9 and abs(fx) < 1e-9:
            return None
        return LoadMark(kind="point", x=_num(item, "x"), fy=fy, fx=fx)
    if kind == "moment":
        moment = _num(item, "M", "m")
        if abs(moment) < 1e-9:
            return None
        return LoadMark(kind="moment", x=_num(item, "x"), moment=moment)
    if kind == "inclined":
        mag = _num(item, "magnitude_ton", "inclMag", "magnitude")
        angle = _num(item, "angle_deg", "inclAngle", default=30.0)
        incl = str(item.get("incl_dir") or item.get("inclDir") or "").lower()
        fx = _num(item, "Fx", "fx")
        fy = _num(item, "Fy", "fy")
        if mag <= 1e-9:
            mag = math.hypot(fx, fy)
        if mag <= 1e-9:
            return None
        if incl not in ("dr", "dl"):
            incl = "dl" if fx < 0 else "dr"
        if "angle_deg" not in item and "inclAngle" not in item and abs(fx) + abs(fy) > 1e-9:
            angle = math.degrees(math.atan2(abs(fy), abs(fx) if abs(fx) > 1e-12 else 1e-12))
        return LoadMark(
            kind="inclined",
            x=_num(item, "x"),
            magnitude=mag,
            angle_deg=angle,
            incl_dir=incl,
        )
    return None


def _stations(
    length: float,
    supports: list[SupportMark],
    loads: list[LoadMark],
    labeled: object,
) -> list[tuple[float, str]]:
    xs = {0.0, round(length, 4)}
    labels: dict[float, str] = {}
    for support in supports:
        key = round(support.x, 4)
        xs.add(key)
        labels[key] = support.label
    if isinstance(labeled, list):
        for item in labeled:
            if not isinstance(item, dict):
                continue
            key = round(_num(item, "x"), 4)
            xs.add(key)
            text = str(item.get("label") or "").strip()
            if text:
                labels.setdefault(key, text)
    for load in loads:
        if load.kind == "distributed":
            xs.add(round(load.x1, 4))
            xs.add(round(load.x2, 4))
        else:
            xs.add(round(load.x, 4))
    used = set(labels.values())
    letters = [ch for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if ch not in used]
    li = 0
    ordered = sorted(xs)
    out: list[tuple[float, str]] = []
    for x in ordered:
        label = labels.get(x)
        if not label:
            label = letters[li] if li < len(letters) else f"P{li}"
            li += 1
        out.append((x, label))
    return out


def _clamp(value: float, length: float) -> float:
    return max(0.0, min(length, value))
