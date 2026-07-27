# -*- coding: utf-8 -*-
"""generate() → Exercise → PNG + JSON.

תצורת השרטוט נעולה ב־``render/``. ברירת המחדל תמיד ``LOCKED_FAMILY``;
``family`` אופציונלי רק לכפייה מפורשת (למשל CLI בפיתוח).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from exercise_generator.randomize import make_rng
from exercise_generator.render import render_exercise_png
from exercise_generator.schema import Exercise
from exercise_generator.templates.registry import (
    LOCKED_FAMILY,
    build_family,
    pick_family,
)
from exercise_generator.validate import require_valid


@dataclass
class GeneratedArtifact:
    exercise: Exercise
    json_path: Path
    png_path: Path
    extracted: dict


def generate_exercise(
    *,
    family: str | None = None,
    seed: int | None = None,
    out_dir: Path | str | None = None,
    stem: str = "ex_0001",
) -> GeneratedArtifact:
    """בונה תרגיל (ברירת מחדל: LOCKED_FAMILY), מאמת, כותב JSON+PNG."""
    rng = make_rng(seed)
    family_id = pick_family(rng, family)
    # seed יציב ל־meta גם כשלא הועבר במפורש (לחיבור חוקי הגרלה בהמשך)
    effective_seed = seed if seed is not None else rng.randint(1, 10**9)
    exercise = build_family(family_id, seed=effective_seed)
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


def generate_batch(
    *,
    count: int,
    family: str | None = None,
    seed: int | None = None,
    out_dir: Path | str = "output",
) -> list[GeneratedArtifact]:
    if count < 1:
        raise ValueError("count must be >= 1")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    base_rng = make_rng(seed)
    results: list[GeneratedArtifact] = []
    for i in range(count):
        item_seed = base_rng.randint(1, 10**9)
        stem = f"ex_{i + 1:04d}"
        results.append(
            generate_exercise(
                family=family,
                seed=item_seed,
                out_dir=out,
                stem=stem,
            )
        )
    return results


__all__ = ["GeneratedArtifact", "LOCKED_FAMILY", "generate_batch", "generate_exercise"]
