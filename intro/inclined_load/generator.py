# -*- coding: utf-8 -*-
"""מחולל תרגילים ייעודי לעומס אלכסוני — קורה באורך 10, סמך קבוע ב-0, סמך נייד ב-10, עומס אלכסוני ב-5."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import math
from exercise_generator.geometry import row_from_breaks
from exercise_generator.randomize import make_rng, random_inclined_angle_deg
from exercise_generator.render import render_exercise_png
from exercise_generator.schema import (
    Exercise,
    InclinedLoad,
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


def build_inclined_exercise(*, seed: int | None = None) -> Exercise:
    """
    בונה תרגיל עומס אלכסוני:
    - אורך קורה: 10.0
    - סמך קבוע (pin) ב-A (x=0.0)
    - סמך נייד (roller) ב-B (x=10.0)
    - עומס אלכסוני יחיד באמצע הקורה (x=5.0)
    """
    rng = make_rng(seed)
    magnitude_ton = float(rng.choice([4, 5, 6, 8, 10, 12, 15]))
    angle_deg = random_inclined_angle_deg(rng)
    incl_dir = rng.choice(["dr", "dl"])

    L = 10.0
    supports = [
        Support(label="A", type="pin", x=0.0),
        Support(label="B", type="roller", x=10.0),
    ]
    loads = [
        InclinedLoad(
            x=5.0,
            magnitude_ton=magnitude_ton,
            angle_deg=angle_deg,
            incl_dir=incl_dir,
        )
    ]
    labeled_points = [
        LabeledPoint(label="A", x=0.0),
        LabeledPoint(label="C", x=5.0),
        LabeledPoint(label="B", x=10.0),
    ]

    return Exercise(
        L=L,
        support_mode="simply_supported",
        supports=supports,
        loads=loads,
        labeled_points=labeled_points,
        dim_row_top=row_from_breaks([0.0, 5.0, 10.0]),
        dim_row_bottom=row_from_breaks([0.0, 10.0]),
        family="intro_inclined_load",
        seed=seed,
    )


def build_decomposed_exercise(exercise: Exercise) -> Exercise:
    """בונה תרגיל מפורק שבו העומס האלכסוני מוחלף בעומס אנכי ועומס צירי."""
    inc_load = next(
        (ld for ld in exercise.loads if isinstance(ld, InclinedLoad)), None
    )
    if not inc_load:
        return exercise

    mag = float(inc_load.magnitude_ton)
    angle = float(inc_load.angle_deg)
    incl_dir = str(inc_load.incl_dir)

    rad = math.radians(angle)
    fy = round(mag * math.sin(rad), 2)
    fx = round(mag * math.cos(rad), 2)
    fx_val = fx if incl_dir == "dr" else -fx

    new_loads = []
    for ld in exercise.loads:
        if ld is inc_load:
            new_loads.append(PointLoad(x=ld.x, Fy=fy))
            new_loads.append(PointLoad(x=ld.x, Fx=fx_val))
        else:
            new_loads.append(ld)

    return Exercise(
        L=exercise.L,
        support_mode=exercise.support_mode,
        supports=exercise.supports,
        loads=new_loads,
        labeled_points=exercise.labeled_points,
        dim_row_top=exercise.dim_row_top,
        dim_row_bottom=exercise.dim_row_bottom,
        family=exercise.family + "_decomposed",
        seed=exercise.seed,
    )


def generate_decomposed_exercise(
    exercise: Exercise,
    out_dir: Path | str | None = None,
    stem: str = "live_decomposed",
) -> Path:
    """יוצר תרגיל מפורק ומחולל תמונה שלו."""
    decomposed_ex = build_decomposed_exercise(exercise)
    require_valid(decomposed_ex)

    out = Path(out_dir) if out_dir is not None else Path("output")
    out.mkdir(parents=True, exist_ok=True)
    png_path = out / f"{stem}.png"
    render_exercise_png(decomposed_ex, png_path)
    return png_path


def generate_exercise(
    *,
    family: str | None = None,
    seed: int | None = None,
    out_dir: Path | str | None = None,
    stem: str = "ex_inclined_0001",
) -> GeneratedArtifact:
    """בונה תרגיל ייעודי לעומס אלכסוני לפי הכללים המדויקים, מאמת, כותב JSON+PNG."""
    rng = make_rng(seed)
    effective_seed = seed if seed is not None else rng.randint(1, 10**9)
    exercise = build_inclined_exercise(seed=effective_seed)
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
    "build_decomposed_exercise",
    "build_inclined_exercise",
    "generate_decomposed_exercise",
    "generate_exercise",
]
