# -*- coding: utf-8 -*-
"""הגרלת תרגיל מרכז כובד — 3 רכיבים צמודים, לפי מבנה תרגילי הכיתה.

כל רכיב: 2/3 פרופיל, 1/3 צורה בסיסית (פח מלבני). לכל תרגיל יש 35%
סיכוי להיות אסימטרי. מספר הפרופילים שיצא קובע את תבניות המבנה האפשריות:
- 0 פרופילים — חתך גאומטרי ממלבנים (ס״מ), ממורכז או מדורג.
- 1 פרופיל — פח / פרופיל / פח, ממורכז או עם בליטות מנוגדות.
- 2 פרופילים — ערימה של שני פרופילים זהים + פח, UPB ככובע על I + פח,
  זוג פרופילים צמודים + פח, או RHS/I עם UPB בצד / LPN בפינה + פח (אסימטרי).
- 3 פרופילים — שני I זהים + UPB ככובע, או RHS/I עם UPB בצד ו־LPN בפינה הנגדית.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from exercise_generator.center_of_gravity import catalog

COMPONENT_COUNT = 3
PROFILE_PROBABILITY = 2.0 / 3.0
ASYMMETRIC_PROBABILITY = 0.35


@dataclass
class Component:
    kind: str
    label: str
    width: float
    height: float
    params: dict[str, float] = field(default_factory=dict)
    is_profile: bool = True
    mirror: bool = False
    x: float = 0.0
    y: float = 0.0
    group: int | None = None

    @property
    def top(self) -> float:
        return self.y + self.height

    @property
    def right(self) -> float:
        return self.x + self.width


@dataclass
class CogExercise:
    components: list[Component]
    symmetric: bool
    unit: str = "mm"


def _fmt(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def _round_up(value: float, step: int = 10) -> int:
    return int(-(-value // step) * step)


# ---------- יצירת רכיבים ----------

def _i_profile(rng: random.Random, family: str | None = None, size: str | None = None) -> Component:
    family = family or rng.choice(catalog.I_FAMILIES)
    table = getattr(catalog, family)
    size = size or rng.choice(list(table))
    h, b, tw, tf = table[size]
    return Component(
        kind="i_section",
        label=f"{family} {size}",
        width=b,
        height=h,
        params={"tw": tw, "tf": tf, "family": family, "size": size},
    )


def _upb_vertical(size: str, *, mirror: bool) -> Component:
    h, b, tw, tf = catalog.UPB[size]
    return Component(
        kind="c_section",
        label=f"UPB {size}",
        width=b,
        height=h,
        params={"tw": tw, "tf": tf, "size": size},
        mirror=mirror,
    )


def _upb_cap(size: str) -> Component:
    h, b, tw, tf = catalog.UPB[size]
    return Component(
        kind="c_cap",
        label=f"UPB {size}",
        width=h,
        height=b,
        params={"tw": tw, "tf": tf, "size": size},
    )


def _rhs(spec: tuple[float, float, float]) -> Component:
    h, b, t = spec
    return Component(
        kind="rhs",
        label=f"RHS {_fmt(h)}/{_fmt(b)}/{_fmt(t)}",
        width=b,
        height=h,
        params={"t": t},
    )


def _lpn(spec: tuple[float, float, float], *, vertical_leg_right: bool) -> Component:
    a, b, s = spec
    return Component(
        kind="l_section",
        label=f"LPN {_fmt(a)}/{_fmt(b)}/{_fmt(s)}",
        width=a,
        height=b,
        params={"t": s},
        mirror=vertical_leg_right,
    )


def _plate(width: float, rng: random.Random, *, extra: bool = True) -> Component:
    w = _round_up(width) + (rng.choice(catalog.PLATE_EXTRA_WIDTH) if extra else 0)
    t = rng.choice(catalog.PLATE_THICKNESS)
    return Component(kind="rect", label=f"PL {w}/{t}", width=float(w), height=float(t), is_profile=False)


def _main_profile(rng: random.Random) -> Component:
    if rng.random() < 0.5:
        return _i_profile(rng)
    return _rhs(rng.choice(catalog.RHS))


def _copy(comp: Component) -> Component:
    return Component(
        kind=comp.kind,
        label=comp.label,
        width=comp.width,
        height=comp.height,
        params=dict(comp.params),
        is_profile=comp.is_profile,
        mirror=comp.mirror,
    )


def _fitting_cap(below: Component, rng: random.Random) -> Component:
    """UPB שהשוקיים שלו עוברות מחוץ לרוחב הרכיב שמתחתיו."""
    fits = [
        size for size, (h, _b, _tw, tf) in catalog.UPB.items()
        if h - 2 * tf >= below.width + 10
    ]
    size = rng.choice(fits[:3]) if fits else list(catalog.UPB)[-1]
    return _upb_cap(size)


def _side_upb(main_height: float, rng: random.Random, *, on_right: bool) -> Component:
    fits = [s for s, (h, *_r) in catalog.UPB.items() if 0.8 * main_height <= h <= 1.3 * main_height]
    if not fits:
        fits = [min(catalog.UPB, key=lambda s: abs(catalog.UPB[s][0] - main_height))]
    return _upb_vertical(rng.choice(fits), mirror=not on_right)


def _corner_lpn(main_width: float, rng: random.Random, *, flush_right: bool) -> Component:
    fits = [spec for spec in catalog.LPN if 0.4 * main_width <= spec[0] <= main_width]
    if not fits:
        fits = [min(catalog.LPN, key=lambda spec: spec[0])]
    return _lpn(rng.choice(fits), vertical_leg_right=flush_right)


# ---------- מיקום ----------

def _stack_centered(parts: list[Component]) -> None:
    y = 0.0
    for comp in parts:
        comp.x = -comp.width / 2.0
        if comp.kind == "c_cap":
            comp.y = y - comp.height + comp.params["tw"]
            y = comp.top
            continue
        comp.y = y
        y = comp.top


# ---------- תבניות ----------

def _geometric(rng: random.Random) -> CogExercise:
    def rect(w: int, h: int) -> Component:
        return Component(kind="rect", label=f"{w}×{h} cm", width=float(w), height=float(h), is_profile=False)

    fw_lo, fw_hi = catalog.GEO_FLANGE_WIDTH
    ft_lo, ft_hi = catalog.GEO_FLANGE_THICKNESS
    wt_lo, wt_hi = catalog.GEO_WEB_THICKNESS
    wh_lo, wh_hi = catalog.GEO_WEB_HEIGHT
    web = rect(rng.randint(wt_lo, wt_hi), rng.randint(wh_lo, wh_hi))
    top = rect(rng.randint(max(fw_lo, int(web.width) + 4), fw_hi), rng.randint(ft_lo, ft_hi))
    bottom = rect(rng.randint(max(fw_lo, int(web.width) + 4), fw_hi), rng.randint(ft_lo, ft_hi))
    parts = [bottom, web, top]
    _stack_centered(parts)
    return CogExercise(components=parts, symmetric=True, unit="cm")


def _asymmetric_geometric(rng: random.Random) -> CogExercise:
    def rect(w: int, h: int) -> Component:
        return Component(kind="rect", label=f"{w}×{h} cm", width=float(w), height=float(h), is_profile=False)

    fw_lo, fw_hi = catalog.GEO_FLANGE_WIDTH
    ft_lo, ft_hi = catalog.GEO_FLANGE_THICKNESS
    wt_lo, wt_hi = catalog.GEO_WEB_THICKNESS
    wh_lo, wh_hi = catalog.GEO_WEB_HEIGHT
    web = rect(rng.randint(wt_lo, wt_hi), rng.randint(wh_lo, wh_hi))
    top = rect(rng.randint(max(fw_lo, int(web.width) + 4), fw_hi), rng.randint(ft_lo, ft_hi))
    bottom = rect(rng.randint(max(fw_lo, int(web.width) + 4), fw_hi), rng.randint(ft_lo, ft_hi))

    bottom.x = 0.0
    bottom.y = 0.0
    web.x = bottom.right - web.width
    web.y = bottom.top
    top.x = web.x
    top.y = web.top
    return CogExercise(components=[bottom, web, top], symmetric=False, unit="cm")


def _plate_profile_plate(rng: random.Random) -> CogExercise:
    main = _main_profile(rng)
    parts = [_plate(main.width, rng), main, _plate(main.width, rng)]
    _stack_centered(parts)
    return CogExercise(components=parts, symmetric=True)


def _asymmetric_plate_profile_plate(rng: random.Random) -> CogExercise:
    main = _main_profile(rng)
    bottom = _plate(main.width, rng)
    top = _plate(main.width, rng)
    for plate in (bottom, top):
        if plate.width <= main.width:
            plate.width = float(_round_up(main.width) + 20)
            plate.label = f"PL {_fmt(plate.width)}/{_fmt(plate.height)}"

    main.x = -main.width / 2.0
    bottom.x = main.x
    bottom.y = 0.0
    main.y = bottom.top
    top.x = main.right - top.width
    top.y = main.top
    return CogExercise(components=[bottom, main, top], symmetric=False)


def _identical_stack_plate(rng: random.Random) -> CogExercise:
    main = _main_profile(rng)
    twin = _copy(main)
    main.group = twin.group = 1
    main.label = twin.label = f"2 {main.label}"
    plate = _plate(main.width, rng)
    parts = [plate, main, twin] if rng.random() < 0.5 else [main, twin, plate]
    _stack_centered(parts)
    return CogExercise(components=parts, symmetric=True)


def _cap_on_profile_plate(rng: random.Random) -> CogExercise:
    main = _i_profile(rng)
    plate = _plate(main.width, rng)
    parts = [plate, main, _fitting_cap(main, rng)]
    _stack_centered(parts)
    return CogExercise(components=parts, symmetric=True)


def _pair_plate(rng: random.Random) -> CogExercise:
    if rng.random() < 0.6:
        left = _i_profile(rng)
        right = _copy(left)
    else:
        size = rng.choice(list(catalog.UPB))
        left = _upb_vertical(size, mirror=True)
        right = _upb_vertical(size, mirror=False)
    left.group = right.group = 1
    left.label = right.label = f"2 {left.label}"
    left.x, right.x = -left.width, 0.0
    plate = _plate(left.width + right.width, rng)
    plate.x = -plate.width / 2.0
    if rng.random() < 0.5:
        plate.y = 0.0
        left.y = right.y = plate.top
    else:
        left.y = right.y = 0.0
        plate.y = left.top
    return CogExercise(components=[left, right, plate], symmetric=True)


def _asymmetric(rng: random.Random, *, profiles: int) -> CogExercise:
    main = _main_profile(rng)
    side_right = rng.random() < 0.5
    main.x = -main.width / 2.0

    if profiles == 3:
        main.y = 0.0
        side = _side_upb(main.height, rng, on_right=side_right)
        side.x = main.right if side_right else main.x - side.width
        side.y = 0.0
        corner = _corner_lpn(main.width, rng, flush_right=not side_right)
        corner.x = main.right - corner.width if not side_right else main.x
        corner.y = main.top
        return CogExercise(components=[main, side, corner], symmetric=False)

    if rng.random() < 0.5:
        plate = _plate(main.width, rng, extra=False)
        plate.x, plate.y = main.x, 0.0
        main.y = plate.top
        side = _side_upb(main.top, rng, on_right=side_right)
        side.x = main.right if side_right else main.x - side.width
        side.y = 0.0
        return CogExercise(components=[plate, main, side], symmetric=False)

    plate = _plate(main.width, rng)
    plate.x, plate.y = -plate.width / 2.0, 0.0
    main.y = plate.top
    flush_right = rng.random() < 0.5
    corner = _corner_lpn(main.width, rng, flush_right=flush_right)
    corner.x = main.right - corner.width if flush_right else main.x
    corner.y = main.top
    return CogExercise(components=[plate, main, corner], symmetric=False)


def _three_profiles_stack(rng: random.Random) -> CogExercise:
    main = _i_profile(rng)
    twin = _copy(main)
    main.group = twin.group = 1
    main.label = twin.label = f"2 {main.label}"
    parts = [main, twin, _fitting_cap(main, rng)]
    _stack_centered(parts)
    return CogExercise(components=parts, symmetric=True)


def generate_cog_exercise(rng: random.Random | None = None) -> CogExercise:
    rng = rng or random.Random()
    profiles = sum(rng.random() < PROFILE_PROBABILITY for _ in range(COMPONENT_COUNT))
    asymmetric = rng.random() < ASYMMETRIC_PROBABILITY
    if profiles == 0:
        return _asymmetric_geometric(rng) if asymmetric else _geometric(rng)
    if profiles == 1:
        return _asymmetric_plate_profile_plate(rng) if asymmetric else _plate_profile_plate(rng)
    if profiles == 2:
        if asymmetric:
            return _asymmetric(rng, profiles=2)
        builder = rng.choices(
            [_identical_stack_plate, _cap_on_profile_plate, _pair_plate],
            weights=[3, 2, 3],
        )[0]
        return builder(rng)
    return _asymmetric(rng, profiles=3) if asymmetric else _three_profiles_stack(rng)
