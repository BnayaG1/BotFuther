# -*- coding: utf-8 -*-
"""מחולל תרגילים ייעודי לעומס מפורס — קורה באורך 10, סמך קבוע ב-0, סמך נייד ב-10, עומס מפורס מלבני."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from exercise_generator.geometry import row_from_breaks
from exercise_generator.randomize import make_rng
from exercise_generator.render import render_exercise_png
from exercise_generator.schema import (
    DistributedLoad,
    Exercise,
    LabeledPoint,
    PointLoad,
    Support,
)
from exercise_generator.validate import require_valid


@dataclass
class GeneratedArtifact:
    exercise: Exercise
    json_path: Path
    png_path: Path
    extracted: dict


def build_distributed_exercise(*, seed: int | None = None) -> Exercise:
    """
    בונה תרגיל עומס מפורס:
    - אורך קורה: 10.0
    - סמך קבוע (pin) ב-A (x=0.0)
    - סמך נייד (roller) ב-B (x=10.0)
    - עומס מפורס מלבני יחיד (ללא עומס אלכסוני) בתוך הטווח שבין 2.0 ל-8.0 (טווח 6 מטר באמצע הקורה)
    - אורך עומס מפורס: 4, 5, או 6 מטרים
    - משקל עומס מפורס: בין 2 ל-8 טון/מטר (מספר שלם)
    """
    rng = make_rng(seed)
    w = float(rng.randint(2, 8))
    length = float(rng.choice([4.0, 5.0, 6.0]))

    # הטווח המותר לעומס המפורס הוא מ-x=2.0 עד x=8.0 (אורך 6 מטר)
    max_start_x = 8.0 - length
    start_offset_choices = [0.0]
    if max_start_x > 2.0:
        # אם יש חופש תנועה בתוך הטווח
        possible_starts = [round(2.0 + i * 0.5, 1) for i in range(int((max_start_x - 2.0) / 0.5) + 1)]
        x1 = float(rng.choice(possible_starts))
    else:
        x1 = 2.0

    x2 = x1 + length

    L = 10.0
    supports = [
        Support(label="A", type="pin", x=0.0),
        Support(label="B", type="roller", x=10.0),
    ]
    loads = [
        DistributedLoad(
            x1=x1,
            x2=x2,
            w=w,
            shape="rectangular",
        )
    ]
    labeled_points = [
        LabeledPoint(label="A", x=0.0),
        LabeledPoint(label="B", x=10.0),
    ]

    breaks = [0.0, 10.0]
    if x1 > 0.0:
        breaks.append(x1)
    if x2 < 10.0:
        breaks.append(x2)
    breaks = sorted(list(set(breaks)))

    return Exercise(
        L=L,
        support_mode="simply_supported",
        supports=supports,
        loads=loads,
        labeled_points=labeled_points,
        dim_row_top=row_from_breaks(breaks),
        dim_row_bottom=row_from_breaks([0.0, 10.0]),
        family="intro_distributed_load",
        seed=seed,
    )



def generate_exercise(
    *,
    family: str | None = None,
    seed: int | None = None,
    out_dir: Path | str | None = None,
    stem: str = "ex_distributed_0001",
) -> GeneratedArtifact:
    """בונה תרגיל ייעודי לעומס מפורס, מאמת, כותב JSON+PNG."""
    rng = make_rng(seed)
    effective_seed = seed if seed is not None else rng.randint(1, 10**9)
    exercise = build_distributed_exercise(seed=effective_seed)
    require_valid(exercise)

    out = Path(out_dir) if out_dir is not None else Path("output")
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / f"{stem}.json"
    png_path = out / f"{stem}.png"

    extracted = exercise.to_extracted()
    json_path.write_text(
        json.dumps(extracted, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    render_exercise_png(exercise, png_path)

    return GeneratedArtifact(
        exercise=exercise,
        json_path=json_path,
        png_path=png_path,
        extracted=extracted,
    )


def build_equivalent_point_load_exercise(exercise: Exercise) -> Exercise:
    """בונה תרגיל שבו העומס המפורס מוחלף בכח שקול אנכי בדיוק באמצע העומס המפורס."""
    dist_load = next(
        (ld for ld in exercise.loads if isinstance(ld, DistributedLoad)), None
    )
    if not dist_load:
        return exercise

    w = float(dist_load.w)
    dist = abs(dist_load.x2 - dist_load.x1)
    equivalent_force = round(w * dist, 2)
    mid_x = round((dist_load.x1 + dist_load.x2) / 2.0, 2)

    new_loads = []
    for ld in exercise.loads:
        if ld is dist_load:
            new_loads.append(PointLoad(x=mid_x, Fy=equivalent_force))
        else:
            new_loads.append(ld)

    breaks = [0.0, 10.0]
    if dist_load.x1 > 0.0:
        breaks.append(dist_load.x1)
    if mid_x not in breaks:
        breaks.append(mid_x)
    if dist_load.x2 < 10.0:
        breaks.append(dist_load.x2)
    breaks = sorted(list(set(breaks)))

    return Exercise(
        L=exercise.L,
        support_mode=exercise.support_mode,
        supports=exercise.supports,
        loads=new_loads,
        labeled_points=exercise.labeled_points,
        dim_row_top=row_from_breaks(breaks),
        dim_row_bottom=row_from_breaks([0.0, 10.0]),
        family=exercise.family + "_equivalent",
        seed=exercise.seed,
    )


def generate_equivalent_point_load_exercise(
    exercise: Exercise,
    out_dir: Path | str | None = None,
    stem: str = "live_equivalent",
) -> Path:
    """יוצר תרגיל עם כח שקול ומחולל תמונה שלו."""
    equiv_ex = build_equivalent_point_load_exercise(exercise)
    require_valid(equiv_ex)

    out = Path(out_dir) if out_dir is not None else Path("output")
    out.mkdir(parents=True, exist_ok=True)
    png_path = out / f"{stem}.png"
    render_exercise_png(equiv_ex, png_path)
    return png_path


def build_distributed_on_support_exercise(*, seed: int | None = None) -> Exercise:
    """
    בונה תרגיל עומס מפורס על סמך:
    - אורך קורה: L = 10.0
    - בחירה רנדומלית איזה סמך זז: 'left' (סמך A) או 'right' (סמך B)
    - אם סמך שמאל זז (x_A בטווח 1.0 עד 4.0): סמך ימין B ב-10.0.
      העומס המפורס מתפרס מעל סמך A (x1 < x_A < x2).
    - אם סמך ימין זז (x_B בטווח 6.0 עד 9.0, כלומר 1.0 עד 4.0 מטר מימין לקורה/מ-10.0): סמך שמאל A ב-0.0.
      העומס המפורס מתפרס מעל סמך B (x1 < x_B < x2).
    """
    rng = make_rng(seed)
    w = float(rng.randint(2, 8))
    L = 10.0
    moved_support = rng.choice(["left", "right"])

    if moved_support == "left":
        # סמך A זז ימינה בין 1.0 ל-4.0 מטר (x_A in [1.0, 4.0])
        # סמך B ב-10.0
        x_A = float(rng.choice([1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]))
        x_B = 10.0

        # עומס מפורס מתפרס על סמך A: קצה שמאל x1 < x_A, קצה ימין x2 > x_A
        # x1 בין 0.0 ל-x_A - 0.5
        possible_x1 = [round(i * 0.5, 1) for i in range(int((x_A - 0.5) / 0.5) + 1)]
        x1 = float(rng.choice(possible_x1))
        # x2 בין x_A + 1.0 ל-x_A + 3.0 (לא יותר מ-x_B - 1.0)
        max_x2 = min(x_A + 3.0, x_B - 1.0)
        possible_x2 = [round(x_A + 1.0 + i * 0.5, 1) for i in range(int((max_x2 - (x_A + 1.0)) / 0.5) + 1)]
        x2 = float(rng.choice(possible_x2)) if possible_x2 else round(x_A + 1.0, 1)
    else:
        # סמך B זז שמאלה בין 1.0 ל-4.0 מטר מ-10.0 (x_B in [6.0, 9.0])
        # סמך A ב-0.0
        x_A = 0.0
        x_B = float(rng.choice([6.0, 6.5, 7.0, 7.5, 8.0, 8.5, 9.0]))

        # עומס מפורס מתפרס על סמך B: קצה שמאל x1 < x_B, קצה ימין x2 > x_B
        # x1 בין x_B - 3.0 ל-x_B - 1.0 (לא פחות מ-x_A + 1.0)
        min_x1 = max(x_B - 3.0, x_A + 1.0)
        possible_x1 = [round(min_x1 + i * 0.5, 1) for i in range(int(((x_B - 1.0) - min_x1) / 0.5) + 1)]
        x1 = float(rng.choice(possible_x1)) if possible_x1 else round(x_B - 1.0, 1)
        # x2 בין x_B + 0.5 ל-10.0
        possible_x2 = [round(x_B + 0.5 + i * 0.5, 1) for i in range(int((10.0 - (x_B + 0.5)) / 0.5) + 1)]
        x2 = float(rng.choice(possible_x2))

    supports = [
        Support(label="A", type="pin", x=x_A),
        Support(label="B", type="roller", x=x_B),
    ]
    loads = [
        DistributedLoad(
            x1=x1,
            x2=x2,
            w=w,
            shape="rectangular",
        )
    ]
    labeled_points = [
        LabeledPoint(label="A", x=x_A),
        LabeledPoint(label="B", x=x_B),
    ]

    breaks = [0.0, 10.0]
    for px in (x_A, x_B, x1, x2):
        if px not in breaks:
            breaks.append(px)
    breaks = sorted(breaks)

    return Exercise(
        L=L,
        support_mode="simply_supported",
        supports=supports,
        loads=loads,
        labeled_points=labeled_points,
        dim_row_top=row_from_breaks(breaks),
        dim_row_bottom=row_from_breaks([0.0, 10.0]),
        family="intro_distributed_on_support",
        seed=seed,
    )


def generate_on_support_exercise(
    *,
    family: str | None = None,
    seed: int | None = None,
    out_dir: Path | str | None = None,
    stem: str = "ex_distributed_on_support_0001",
) -> GeneratedArtifact:
    """בונה תרגיל עומס מפורס על סמך, מאמת, כותב JSON+PNG."""
    rng = make_rng(seed)
    effective_seed = seed if seed is not None else rng.randint(1, 10**9)
    exercise = build_distributed_on_support_exercise(seed=effective_seed)
    require_valid(exercise)

    out = Path(out_dir) if out_dir is not None else Path("output")
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / f"{stem}.json"
    png_path = out / f"{stem}.png"

    extracted = exercise.to_extracted()
    json_path.write_text(
        json.dumps(extracted, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    render_exercise_png(exercise, png_path)

    return GeneratedArtifact(
        exercise=exercise,
        json_path=json_path,
        png_path=png_path,
        extracted=extracted,
    )


__all__ = [
    "GeneratedArtifact",
    "build_distributed_exercise",
    "build_distributed_on_support_exercise",
    "build_equivalent_point_load_exercise",
    "generate_equivalent_point_load_exercise",
    "generate_exercise",
    "generate_on_support_exercise",
]


