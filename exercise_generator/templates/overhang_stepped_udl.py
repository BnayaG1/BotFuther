# -*- coding: utf-8 -*-
"""תבנית נעולה: סמכים או ריתום + 4/5 עומסים (מפורסים + מרוכז/אלכסוני/מומנט/צירי)."""
from __future__ import annotations

import random
import string

from exercise_generator.geometry import row_from_breaks
from exercise_generator.randomize import (
    INCLINED_NO_DL_RIGHT_M,
    MOMENT_M,
    make_rng,
    pick_load_composition,
    pick_support_configuration,
    random_force_magnitude,
    random_inclined_angle_deg,
    random_point_spacings,
    random_udl_weights,
    shuffled_load_kinds,
)
from exercise_generator.schema import (
    DistributedLoad,
    Exercise,
    InclinedLoad,
    LabeledPoint,
    LoadItem,
    MomentLoad,
    PointLoad,
    Support,
)

FAMILY_ID = "overhang_stepped_udl"


def _build_load(
    kind: str,
    x1: float,
    x2: float,
    rng: random.Random,
    *,
    udl_w: float = 4.0,
    beam_L: float | None = None,
) -> LoadItem:
    if kind == "distributed":
        return DistributedLoad(x1=x1, x2=x2, w=udl_w)
    if kind == "point":
        return PointLoad(x=x1, Fy=random_force_magnitude(rng))
    if kind == "axial":
        mag = random_force_magnitude(rng)
        fx = mag if rng.random() < 0.5 else -mag
        return PointLoad(x=x1, Fy=0.0, Fx=fx)
    if kind == "inclined":
        incl_dir = "dr" if rng.random() < 0.5 else "dl"
        # ב־0.9 מ' מימין הקורה — רק נוטה ימינה (לא לגעת בחותמת)
        if beam_L is not None and float(x1) >= float(beam_L) - INCLINED_NO_DL_RIGHT_M - 1e-9:
            incl_dir = "dr"
        return InclinedLoad(
            x=x1,
            magnitude_ton=random_force_magnitude(rng),
            angle_deg=random_inclined_angle_deg(rng),
            incl_dir=incl_dir,
        )
    if kind == "moment":
        m = MOMENT_M if rng.random() < 0.5 else -MOMENT_M
        return MomentLoad(x=x1, M=m)
    raise ValueError(f"unknown load kind: {kind!r}")


def _point_letters() -> list[str]:
    # C, D, E, G… (בלי F) — לסמכים: A/B שמורים ל-pin/roller
    return [c for c in string.ascii_uppercase[2:] if c != "F"]


def _cantilever_point_letters() -> list[str]:
    # B, C, D, E, G… (בלי F; A שמור לריתום)
    return [c for c in string.ascii_uppercase[1:] if c != "F"]


def _assemble_loads(
    r: random.Random,
    kinds: list[str],
    xs: list[float],
    udl_weights: list[float],
    L: float,
) -> list[LoadItem]:
    loads: list[LoadItem] = []
    udl_i = 0
    for i, kind in enumerate(kinds):
        if kind == "distributed":
            w = udl_weights[udl_i]
            udl_i += 1
            loads.append(_build_load(kind, xs[i], xs[i + 1], r, udl_w=w, beam_L=L))
        else:
            loads.append(_build_load(kind, xs[i], xs[i + 1], r, beam_L=L))
    return loads


def _build_simply_supported(
    r: random.Random,
    *,
    seed: int | None,
    n_total: int,
    kinds: list[str],
    udl_weights: list[float],
) -> Exercise:
    """ענף סמכים — pin@A + roller@B + זיזים (התנהגות היום)."""
    # n_total אזורי עומס + זיז ימין; A אחרי האזור הראשון, B לפני הזיז הימני
    segs, L = random_point_spacings(r, n_segments=n_total + 1)
    xs = [0.0]
    for seg in segs:
        xs.append(round(xs[-1] + seg, 1))
    # xs: [0, x1, ..., x_n, L] — A=x1, B=x_n
    xa = xs[1]
    xb = xs[n_total]

    loads = _assemble_loads(r, kinds, xs, udl_weights, L)

    labeled: list[LabeledPoint] = []
    # כל תחנה שאינה סמך — כולל קצוות הקורה — משמאל לימין: C, D, E, G… (בלי F)
    letters = _point_letters()
    letter_i = 0
    for x in xs:
        if abs(x - xa) < 1e-9 or abs(x - xb) < 1e-9:
            continue
        label = letters[letter_i]
        labeled.append(LabeledPoint(label, x))
        letter_i += 1

    return Exercise(
        L=L,
        support_mode="simply_supported",
        supports=[
            Support("A", "pin", xa),
            Support("B", "roller", xb),
        ],
        loads=loads,
        labeled_points=labeled,
        dim_row_top=row_from_breaks(xs),
        dim_row_bottom=row_from_breaks([0.0, xa, xb, L]),
        family=FAMILY_ID,
        seed=seed,
    )


def _build_cantilever(
    r: random.Random,
    *,
    seed: int | None,
    n_total: int,
    kinds: list[str],
    udl_weights: list[float],
    fixed_side: str,
) -> Exercise:
    """ענף ריתום — קיר בקצה + קצה חופשי."""
    segs, L = random_point_spacings(r, n_segments=n_total)
    xs = [0.0]
    for seg in segs:
        xs.append(round(xs[-1] + seg, 1))

    wall_x = 0.0 if fixed_side == "left" else float(L)
    loads = _assemble_loads(r, kinds, xs, udl_weights, L)

    labeled: list[LabeledPoint] = []
    letters = _cantilever_point_letters()
    letter_i = 0
    for x in xs:
        if abs(x - wall_x) < 1e-9:
            continue
        labeled.append(LabeledPoint(letters[letter_i], x))
        letter_i += 1

    return Exercise(
        L=L,
        support_mode="cantilever",
        supports=[Support("A", "fixed", wall_x)],
        loads=loads,
        labeled_points=labeled,
        dim_row_top=row_from_breaks(xs),
        dim_row_bottom=row_from_breaks([0.0, L]),
        family=FAMILY_ID,
        seed=seed,
    )


def build_example(
    *,
    seed: int | None = None,
    rng: random.Random | None = None,
) -> Exercise:
    r = rng if rng is not None else make_rng(seed)
    mode, fixed_side = pick_support_configuration(r)
    n_total, n_dist, other_kinds = pick_load_composition(r)
    kinds = shuffled_load_kinds(r, n_dist, other_kinds)
    assert len(kinds) == n_total

    # מפורסים: שלמים ב־[1,7], כולם שונים זה מזה
    udl_weights = random_udl_weights(r, n_dist)

    if mode == "cantilever":
        assert fixed_side in ("left", "right")
        return _build_cantilever(
            r,
            seed=seed,
            n_total=n_total,
            kinds=kinds,
            udl_weights=udl_weights,
            fixed_side=fixed_side,
        )
    return _build_simply_supported(
        r,
        seed=seed,
        n_total=n_total,
        kinds=kinds,
        udl_weights=udl_weights,
    )
