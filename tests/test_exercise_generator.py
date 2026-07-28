# -*- coding: utf-8 -*-
"""בדיקות מחולל תרגילי קורות."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from exercise_generator.pipeline import generate_batch, generate_exercise
from exercise_generator.templates.registry import build_family, list_families
from exercise_generator.validate import require_valid, validate_exercise


ALL_FAMILIES = list_families()


@pytest.mark.parametrize("family_id", ALL_FAMILIES)
def test_each_family_builds_and_validates(family_id: str):
    ex = build_family(family_id, seed=42)
    assert ex.family == family_id
    assert ex.seed == 42
    require_valid(ex)
    extracted = ex.to_extracted()
    assert extracted["exercise_type"] == "beam"
    assert extracted["beam"]["L"] == ex.L
    assert extracted["meta"]["family"] == family_id
    assert "supports" in extracted["beam"]
    assert "loads" in extracted["beam"]


def test_distributed_dual_format():
    ex = build_family("overhang_stepped_udl", seed=1)
    extracted = ex.to_extracted()
    dist_in_loads = [ld for ld in extracted["beam"]["loads"] if ld["type"] == "distributed"]
    assert dist_in_loads
    assert "distributed_loads" in extracted["beam"]
    assert len(extracted["beam"]["distributed_loads"]) == len(dist_in_loads)


def test_deterministic_export(tmp_path: Path):
    a = generate_exercise(
        family="overhang_stepped_udl",
        seed=12345,
        out_dir=tmp_path / "a",
        stem="ex_0001",
    )
    b = generate_exercise(
        family="overhang_stepped_udl",
        seed=12345,
        out_dir=tmp_path / "b",
        stem="ex_0001",
    )
    ja = json.loads(a.json_path.read_text(encoding="utf-8"))
    jb = json.loads(b.json_path.read_text(encoding="utf-8"))
    assert ja == jb
    assert a.png_path.is_file() and a.png_path.stat().st_size > 0
    assert b.png_path.is_file() and b.png_path.stat().st_size > 0
    assert a.png_path.read_bytes() == b.png_path.read_bytes()


def test_batch_count(tmp_path: Path):
    arts = generate_batch(
        count=3,
        family="span_point_stepped_udl",
        seed=7,
        out_dir=tmp_path,
    )
    assert len(arts) == 3
    for i, art in enumerate(arts, start=1):
        assert art.json_path.name == f"ex_{i:04d}.json"
        assert art.png_path.is_file()


def test_validate_rejects_bad_udl():
    ex = build_family("overhang_stepped_udl", seed=1)
    # שבור end<=start
    from exercise_generator.schema import DistributedLoad

    ex.loads.append(DistributedLoad(x1=5.0, x2=3.0, w=1.0))
    errs = validate_exercise(ex)
    assert any("end<=start" in e for e in errs)


def test_list_families_complete():
    assert set(ALL_FAMILIES) == {
        "overhang_stepped_udl",
        "span_point_stepped_udl",
        "roller_pin_overhang",
        "double_overhang_mixed",
        "rich_combo",
    }


def test_default_generate_uses_locked_family(tmp_path: Path):
    from exercise_generator.templates.registry import LOCKED_FAMILY

    arts = generate_batch(count=5, seed=99, out_dir=tmp_path)
    assert all(a.exercise.family == LOCKED_FAMILY for a in arts)
    assert LOCKED_FAMILY == "overhang_stepped_udl"


def test_random_beam_length_rules():
    from exercise_generator.randomize import L_MAX, L_MIN, make_rng, random_beam_length

    rng = make_rng(0)
    samples = [random_beam_length(rng) for _ in range(500)]
    assert all(L_MIN - 1e-9 <= L <= L_MAX + 1e-9 for L in samples)

    integers = [L for L in samples if abs(L - round(L)) < 1e-9]
    decimals = [L for L in samples if abs(L - round(L)) >= 1e-9]
    # ~80/20 עם סטייה סבירה על 500 דגימות
    assert 0.70 <= len(integers) / len(samples) <= 0.90
    assert 0.10 <= len(decimals) / len(samples) <= 0.30
    for L in decimals:
        tenths = round(L * 10)
        assert abs(L * 10 - tenths) < 1e-9
        assert tenths % 10 != 0


def test_random_point_spacings_rules():
    from exercise_generator.randomize import (
        L_MAX,
        L_MIN,
        make_rng,
        random_point_spacings,
    )

    rng = make_rng(1)
    all_gaps: list[float] = []
    for _ in range(200):
        segs, L = random_point_spacings(rng, n_segments=4)
        assert len(segs) == 4
        assert abs(sum(segs) - L) < 1e-9
        assert L_MIN - 1e-9 <= L <= L_MAX + 1e-9
        all_gaps.extend(segs)

    integers = [g for g in all_gaps if abs(g - round(g)) < 1e-9]
    decimals = [g for g in all_gaps if abs(g - round(g)) >= 1e-9]
    assert 0.70 <= len(integers) / len(all_gaps) <= 0.90
    assert 0.10 <= len(decimals) / len(all_gaps) <= 0.30
    for g in decimals:
        tenths = round(g * 10)
        assert abs(g * 10 - tenths) < 1e-9
        assert tenths % 10 != 0


def test_locked_family_length_in_range():
    from exercise_generator.randomize import L_MAX, L_MIN

    for seed in range(30):
        ex = build_family("overhang_stepped_udl", seed=seed)
        assert L_MIN <= ex.L <= L_MAX
        require_valid(ex)
        # מרווחי שורת המידות העליונה מסתכמים ל־L
        span = sum(abs(s.x2 - s.x1) for s in ex.dim_row_top.segments)
        assert abs(span - ex.L) < 1e-6


def test_locked_family_png_fixed_size(tmp_path: Path):
    """כל תרגיל — אותו גודל PNG (מסגרת מעטפת קבועה, לא לפי עומסים)."""
    from PIL import Image

    sizes: set[tuple[int, int]] = set()
    for seed in (1, 7, 42, 99, 12345):
        art = generate_exercise(
            family="overhang_stepped_udl",
            seed=seed,
            out_dir=tmp_path / f"s{seed}",
            stem="ex",
        )
        with Image.open(art.png_path) as im:
            sizes.add(im.size)
    assert len(sizes) == 1


def test_beam_display_span_independent_of_L():
    """קורה של 6 מ' ושל 12 מ' — אותו אורך ויזואלי בציור."""
    from exercise_generator.render.canvas import Canvas
    from exercise_generator.render import style

    c6 = Canvas.create(6.0)
    c12 = Canvas.create(12.0)
    assert c6.beam_display_length == style.FRAME_L_MAX
    assert c12.beam_display_length == style.FRAME_L_MAX
    assert abs(c6.x(6.0) - c12.x(12.0)) < 1e-9
    assert abs(c6.x(3.0) - c12.x(6.0)) < 1e-9  # אמצע הקורה באותו מקום


def test_locked_family_four_or_five_loads():
    from exercise_generator.randomize import (
        LOAD_COUNT_FIVE,
        LOAD_COUNT_FOUR,
        NON_DISTRIBUTED_KINDS,
    )
    from exercise_generator.schema import DistributedLoad, InclinedLoad, MomentLoad, PointLoad

    def _kind(ld) -> str:
        if isinstance(ld, DistributedLoad):
            return "distributed"
        if isinstance(ld, PointLoad):
            if abs(ld.Fy) < 1e-12 and abs(ld.Fx) >= 1e-12:
                return "axial"
            return "point"
        if isinstance(ld, InclinedLoad):
            return "inclined"
        if isinstance(ld, MomentLoad):
            return "moment"
        raise TypeError(type(ld))

    for seed in range(40):
        ex = build_family("overhang_stepped_udl", seed=seed)
        n = len(ex.loads)
        assert n in (LOAD_COUNT_FOUR, LOAD_COUNT_FIVE)
        n_dist = sum(1 for ld in ex.loads if isinstance(ld, DistributedLoad))
        assert n_dist in (1, 2)
        other_kinds = {_kind(ld) for ld in ex.loads if not isinstance(ld, DistributedLoad)}
        assert other_kinds <= set(NON_DISTRIBUTED_KINDS)
        assert sum(1 for ld in ex.loads if not isinstance(ld, DistributedLoad)) == n - n_dist


def test_random_inclined_angle_rules():
    from exercise_generator.randomize import (
        INCLINED_ANGLE_TENS_PROB,
        make_rng,
        random_inclined_angle_deg,
    )

    rng = make_rng(0)
    n = 2000
    tens = 0
    decimals = 0
    for _ in range(n):
        a = random_inclined_angle_deg(rng)
        if abs(a - round(a)) < 1e-9:
            tens += 1
            assert int(round(a)) in (10, 20, 30, 40, 50, 60, 70, 80)
            assert int(round(a)) % 10 == 0
        else:
            decimals += 1
            assert 30.0 - 1e-9 <= a <= 70.0 + 1e-9
            tenths = round(a * 10)
            assert abs(a * 10 - tenths) < 1e-9
            assert tenths % 10 != 0
    assert abs(tens / n - INCLINED_ANGLE_TENS_PROB) < 0.05
    assert abs(decimals / n - (1.0 - INCLINED_ANGLE_TENS_PROB)) < 0.05


def test_two_distributed_loads_have_different_w():
    from exercise_generator.schema import DistributedLoad

    saw_two = False
    for seed in range(80):
        ex = build_family("overhang_stepped_udl", seed=seed)
        udls = [ld for ld in ex.loads if isinstance(ld, DistributedLoad)]
        if len(udls) < 2:
            continue
        saw_two = True
        assert udls[0].w != udls[1].w
    assert saw_two


def test_axial_load_in_extracted_and_png(tmp_path: Path):
    """עומס צירי מופיע ב־JSON עם Fx ומייצא PNG תקין."""
    from exercise_generator.schema import PointLoad

    found = False
    for seed in range(200):
        art = generate_exercise(
            family="overhang_stepped_udl",
            seed=seed,
            out_dir=tmp_path / f"s{seed}",
            stem="ex",
        )
        axials = [
            ld
            for ld in art.exercise.loads
            if isinstance(ld, PointLoad)
            and abs(ld.Fy) < 1e-12
            and abs(ld.Fx) >= 1e-12
        ]
        if not axials:
            continue
        found = True
        extracted_loads = art.extracted["beam"]["loads"]
        assert any(
            ld.get("type") == "point"
            and abs(float(ld.get("Fy", 0) or 0)) < 1e-12
            and abs(float(ld.get("Fx", 0) or 0)) >= 1e-12
            for ld in extracted_loads
        )
        assert art.png_path.is_file() and art.png_path.stat().st_size > 0
        break
    assert found, "no axial load in 200 seeds"


def test_load_composition_sixty_forty():
    from exercise_generator.randomize import (
        FOUR_LOADS_PROB,
        NON_DISTRIBUTED_KINDS,
        TWO_DISTRIBUTED_PROB,
        make_rng,
        pick_load_composition,
    )

    rng = make_rng(0)
    n = 2000
    four_loads = 0
    two_dist = 0
    saw_axial = False
    for _ in range(n):
        n_total, n_dist, others = pick_load_composition(rng)
        assert n_total in (4, 5)
        assert n_dist + len(others) == n_total
        assert set(others) <= set(NON_DISTRIBUTED_KINDS)
        if "axial" in others:
            saw_axial = True
        if n_total == 4:
            four_loads += 1
        if n_dist == 2:
            two_dist += 1
            assert len(others) == n_total - 2
        else:
            assert n_dist == 1
            assert len(others) == n_total - 1
    assert abs(four_loads / n - FOUR_LOADS_PROB) < 0.05
    assert abs(two_dist / n - TWO_DISTRIBUTED_PROB) < 0.05
    assert saw_axial


def test_support_configuration_fifty_eighty():
    from exercise_generator.randomize import (
        FIXED_LEFT_PROB,
        SUPPORT_CONFIG_SS_PROB,
        make_rng,
        pick_support_configuration,
    )

    rng = make_rng(0)
    n = 4000
    ss = 0
    left = 0
    right = 0
    for _ in range(n):
        mode, side = pick_support_configuration(rng)
        if mode == "simply_supported":
            ss += 1
            assert side is None
        else:
            assert mode == "cantilever"
            assert side in ("left", "right")
            if side == "left":
                left += 1
            else:
                right += 1
    assert abs(ss / n - SUPPORT_CONFIG_SS_PROB) < 0.04
    cant = left + right
    assert cant > 0
    assert abs(left / cant - FIXED_LEFT_PROB) < 0.05


def test_simply_supported_keeps_pin_roller_and_skip_f():
    """רגרסיה: ענף סמכים — pin+roller, בלי F בתוויות."""
    from exercise_generator.randomize import SUPPORT_CONFIG_SS_PROB

    if SUPPORT_CONFIG_SS_PROB < 1e-9:
        pytest.skip("זמני: 100% ריתום (SUPPORT_CONFIG_SS_PROB=0)")
    saw_ss = False
    for seed in range(120):
        ex = build_family("overhang_stepped_udl", seed=seed)
        if ex.support_mode != "simply_supported":
            continue
        saw_ss = True
        types = sorted(s.type for s in ex.supports)
        assert types == ["pin", "roller"]
        labels = [s.label for s in ex.supports] + [p.label for p in ex.labeled_points]
        assert "F" not in labels
        assert "A" in labels and "B" in labels
        require_valid(ex)
    assert saw_ss


def test_cantilever_structure_and_png(tmp_path: Path):
    """ריתום: סמך fixed יחיד A בקצה; נקודות B,C,D… (בלי F); PNG תקין."""
    saw_left = False
    saw_right = False
    for seed in range(300):
        art = generate_exercise(
            family="overhang_stepped_udl",
            seed=seed,
            out_dir=tmp_path / f"s{seed}",
            stem="ex",
        )
        ex = art.exercise
        if ex.support_mode != "cantilever":
            continue
        require_valid(ex)
        assert len(ex.supports) == 1
        assert ex.supports[0].type == "fixed"
        assert ex.supports[0].label == "A"
        wall = float(ex.supports[0].x)
        assert abs(wall) < 1e-9 or abs(wall - ex.L) < 1e-9
        labels = [p.label for p in ex.labeled_points]
        assert "F" not in labels
        assert "B" in labels
        assert "A" not in labels  # A רק על הריתום
        assert art.png_path.is_file() and art.png_path.stat().st_size > 0
        if abs(wall) < 1e-9:
            saw_left = True
        else:
            saw_right = True
        if saw_left and saw_right:
            break
    assert saw_left and saw_right


def test_udl_weights_integer_1_to_7_distinct():
    from exercise_generator.randomize import UDL_W_MAX, UDL_W_MIN
    from exercise_generator.schema import DistributedLoad

    for seed in range(80):
        ex = build_family("overhang_stepped_udl", seed=seed)
        udls = [ld for ld in ex.loads if isinstance(ld, DistributedLoad)]
        ws = [float(ld.w) for ld in udls]
        assert all(w == int(w) and UDL_W_MIN <= w <= UDL_W_MAX for w in ws)
        assert len(ws) == len(set(ws))


def test_inclined_no_dl_near_right_end():
    from exercise_generator.randomize import INCLINED_NO_DL_RIGHT_M
    from exercise_generator.schema import InclinedLoad

    for seed in range(200):
        ex = build_family("overhang_stepped_udl", seed=seed)
        for ld in ex.loads:
            if isinstance(ld, InclinedLoad) and ld.incl_dir == "dl":
                assert float(ld.x) < float(ex.L) - INCLINED_NO_DL_RIGHT_M - 1e-9
