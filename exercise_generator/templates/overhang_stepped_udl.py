# -*- coding: utf-8 -*-
"""תבנית נעולה: סמכים או ריתום + 4/5 עומסים (מפורסים + מרוכז/אלכסוני/מומנט/צירי)."""
from __future__ import annotations

import random
import string

from exercise_generator.geometry import row_from_breaks
from exercise_generator.randomize import (
    INCLINED_NO_DL_RIGHT_M,
    MAX_LOADS_PER_POINT,
    MOMENT_M,
    UDL_SPAN_MIN,
    make_rng,
    pick_load_composition,
    pick_simply_supported_positions,
    pick_support_configuration,
    random_force_magnitude,
    random_inclined_angle_deg,
    random_point_spacings,
    random_udl_span_length,
    random_udl_weights,
    shuffled_load_kinds,
    udl_spans_overlap,
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


def _free_udl_gaps(
    L: float,
    placed: list[tuple[float, float]],
    *,
    min_len: float = UDL_SPAN_MIN,
) -> list[tuple[float, float]]:
    gaps: list[tuple[float, float]] = []
    free_lo = 0.0
    for a, b in sorted(placed):
        if float(a) - free_lo >= min_len - 1e-9:
            gaps.append((free_lo, float(a)))
        free_lo = max(free_lo, float(b))
    if float(L) - free_lo >= min_len - 1e-9:
        gaps.append((free_lo, float(L)))
    return gaps


def _assemble_loads(
    r: random.Random,
    kinds: list[str],
    xs: list[float],
    udl_weights: list[float],
    L: float,
) -> list[LoadItem]:
    from collections import defaultdict

    loads: list[LoadItem] = []
    touches: dict[float, int] = defaultdict(int)
    placed_udls: list[tuple[float, float]] = []
    pending_udl: list[float] = []
    udl_i = 0
    for kind in kinds:
        if kind == 'distributed':
            pending_udl.append(udl_weights[udl_i])
            udl_i += 1

    pts = sorted({round(float(x), 1) for x in xs} | {0.0, round(float(L), 1)})

    def _overlaps_existing(x1: float, x2: float) -> bool:
        return any(udl_spans_overlap(x1, x2, a, b) for a, b in placed_udls)

    def _commit_udl(x1: float, x2: float, w: float) -> None:
        loads.append(DistributedLoad(x1=x1, x2=x2, w=w))
        touches[round(x1, 6)] += 1
        touches[round(x2, 6)] += 1
        placed_udls.append((float(x1), float(x2)))

    def _candidate_spans(*, others_left: int) -> list[tuple[float, float]]:
        reserve = float(UDL_SPAN_MIN) * others_left
        out: list[tuple[float, float]] = []
        for i in range(len(pts)):
            for j in range(i + 1, len(pts)):
                a, b = pts[i], pts[j]
                if b - a < UDL_SPAN_MIN - 1e-9:
                    continue
                if _overlaps_existing(a, b):
                    continue
                k1, k2 = round(a, 6), round(b, 6)
                if touches[k1] >= MAX_LOADS_PER_POINT or touches[k2] >= MAX_LOADS_PER_POINT:
                    continue
                trial = placed_udls + [(float(a), float(b))]
                left_free = sum(g2 - g1 for g1, g2 in _free_udl_gaps(L, trial))
                if left_free + 1e-9 < reserve:
                    continue
                out.append((float(a), float(b)))
        return out

    def _place_one_udl(w: float, *, others_left: int) -> None:
        cands = _candidate_spans(others_left=others_left)
        if not cands:
            raise ValueError('could not place non-overlapping distributed load')
        peak = 0.5 * float(L)
        weights = [peak - abs((b - a) - peak) + 1.0 for a, b in cands]
        a, b = r.choices(cands, weights=weights, k=1)[0]
        _commit_udl(a, b, w)

    n_udl = len(pending_udl)
    for ui, w in enumerate(pending_udl):
        _place_one_udl(w, others_left=n_udl - ui - 1)

    for i, kind in enumerate(kinds):
        if kind == 'distributed':
            continue
        x_at = float(xs[i])
        ck = round(x_at, 6)
        if touches[ck] >= MAX_LOADS_PER_POINT:
            for cand in xs:
                ckk = round(float(cand), 6)
                if touches[ckk] < MAX_LOADS_PER_POINT:
                    x_at = float(cand)
                    break
        ld = _build_load(kind, x_at, x_at, r, beam_L=L)
        loads.append(ld)
        touches[round(float(getattr(ld, 'x', 0.0)), 6)] += 1
    return loads


def _merge_stations(
    L: float,
    base_xs: list[float],
    supports: list[Support],
    loads: list[LoadItem],
) -> list[float]:
    """מאחד נקודות מידה: קצוות, סמכים, בסיס, וקצות/מיקומי עומסים."""
    pts: set[float] = {0.0, round(float(L), 1)}
    for x in base_xs:
        pts.add(round(float(x), 1))
    for s in supports:
        pts.add(round(float(s.x), 1))
    for ld in loads:
        if isinstance(ld, DistributedLoad):
            pts.add(round(float(ld.x1), 1))
            pts.add(round(float(ld.x2), 1))
        else:
            pts.add(round(float(getattr(ld, "x", 0.0)), 1))
    return sorted(pts)


def _labeled_non_support_points(
    stations: list[float],
    supports: list[Support],
    letters: list[str],
) -> list[LabeledPoint]:
    support_xs = {round(float(s.x), 6) for s in supports}
    labeled: list[LabeledPoint] = []
    letter_i = 0
    for x in stations:
        if round(float(x), 6) in support_xs:
            continue
        if letter_i >= len(letters):
            break
        labeled.append(LabeledPoint(letters[letter_i], float(x)))
        letter_i += 1
    return labeled


def _build_simply_supported(
    r: random.Random,
    *,
    seed: int | None,
    n_total: int,
    kinds: list[str],
    udl_weights: list[float],
) -> Exercise:
    """ענף סמכים — pin@A + roller@B; לכל סמך 50% בקצה / 50% בנקודה אחרת."""
    segs, L = random_point_spacings(r, n_segments=n_total + 1)
    xs = [0.0]
    for seg in segs:
        xs.append(round(xs[-1] + seg, 1))
    xa, xb = pick_simply_supported_positions(r, xs)
    supports = [
        Support("A", "pin", xa),
        Support("B", "roller", xb),
    ]

    loads = _assemble_loads(r, kinds, xs, udl_weights, L)
    stations = _merge_stations(L, xs, supports, loads)
    labeled = _labeled_non_support_points(stations, supports, _point_letters())
    bottom_breaks = sorted({0.0, float(xa), float(xb), float(L)})

    return Exercise(
        L=L,
        support_mode="simply_supported",
        supports=supports,
        loads=loads,
        labeled_points=labeled,
        dim_row_top=row_from_breaks(stations),
        dim_row_bottom=row_from_breaks(bottom_breaks),
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
    supports = [Support("A", "fixed", wall_x)]
    loads = _assemble_loads(r, kinds, xs, udl_weights, L)
    stations = _merge_stations(L, xs, supports, loads)
    labeled = _labeled_non_support_points(
        stations, supports, _cantilever_point_letters()
    )

    return Exercise(
        L=L,
        support_mode="cantilever",
        supports=supports,
        loads=loads,
        labeled_points=labeled,
        dim_row_top=row_from_breaks(stations),
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
