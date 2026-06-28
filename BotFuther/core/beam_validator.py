# -*- coding: utf-8 -*-
"""אימות נתוני קורה שחולצו מ-OCR — לפני חישוב הנדסי (human-in-the-loop)."""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator


class SupportType(str, Enum):
    PIN = "pin"
    ROLLER = "roller"
    FIXED = "fixed"


class LoadType(str, Enum):
    POINT = "point"
    MOMENT = "moment"
    DISTRIBUTED = "distributed"
    INCLINED = "inclined"


class Support(BaseModel):
    label: str = Field(min_length=1)
    type: SupportType
    x: float = Field(ge=0)


class LabeledPoint(BaseModel):
    label: str = Field(min_length=1)
    x: float = Field(ge=0)


class Load(BaseModel):
    type: LoadType
    x: float | None = None
    start_x: float | None = None
    end_x: float | None = None
    Fy: float | None = None
    Fx: float | None = None
    M: float | None = None
    q: float | None = None
    label_at: str | None = None

    @model_validator(mode="after")
    def check_position_fields(self) -> "Load":
        t = self.type
        if t in (LoadType.POINT, LoadType.MOMENT, LoadType.INCLINED):
            if self.x is None:
                raise ValueError("חסר מיקום x לעומס")
        if t == LoadType.DISTRIBUTED:
            if self.start_x is None or self.end_x is None:
                raise ValueError("עומס מפוזר חייב start_x ו-end_x")
            if self.end_x <= self.start_x:
                raise ValueError("עומס מפוזר: end_x חייב להיות גדול מ-start_x")
        return self


class BeamModel(BaseModel):
    L: float = Field(gt=0, description="אורך קורה במטרים")
    supports: list[Support] = Field(min_length=1)
    loads: list[Load] = Field(default_factory=list)
    labeled_points: list[LabeledPoint] = Field(default_factory=list)

    @field_validator("supports")
    @classmethod
    def at_least_one_support(cls, supports: list[Support]) -> list[Support]:
        if not supports:
            raise ValueError("לא זוהו סמכים")
        return supports


class BeamExercise(BaseModel):
    """מבנה מלא כפי שיוצא מה-OCR (עם exercise_type אופציונלי)."""

    exercise_type: Literal["beam"] = "beam"
    beam: BeamModel
    description_he: str | None = None


class ValidationResult(BaseModel):
    ok: bool
    data: BeamExercise | None = None
    errors: list[str] = Field(default_factory=list)


def _hebrew_field_name(field: str) -> str:
    names = {
        "L": "אורך קורה",
        "supports": "סמכים",
        "loads": "עומסים",
        "type": "סוג",
        "x": "מיקום",
        "start_x": "תחילת מרווח",
        "end_x": "סוף מרווח",
    }
    return names.get(field, field)


def _format_pydantic_errors(exc: ValidationError) -> list[str]:
    errors: list[str] = []
    for err in exc.errors():
        loc = err.get("loc", ())
        msg = str(err.get("msg", ""))
        if loc == ("beam", "L") or loc == ("L",):
            errors.append("לא זוהה אורך קורה (L חייב להיות מספר חיובי)")
            continue
        if loc == ("beam", "supports") or loc == ("supports",):
            errors.append("לא זוהו סמכים")
            continue
        if "לא זוה" in msg or "חסר" in msg:
            errors.append(msg)
            continue
        field = str(loc[-1]) if loc else "שדה"
        errors.append(f"{_hebrew_field_name(field)}: {msg}")
    return errors


def _cross_validate(beam: BeamModel) -> list[str]:
    """בדיקות לוגיות שלא נכנסות ל-Pydantic."""
    issues: list[str] = []
    L = beam.L
    tol = 0.15

    for sup in beam.supports:
        if sup.x > L + tol:
            issues.append(
                f"סמך {sup.label} ב-x={sup.x:g} מ' מחוץ לקורה (L={L:g} מ')"
            )

    has_pin = any(s.type == SupportType.PIN for s in beam.supports)
    has_roller = any(s.type == SupportType.ROLLER for s in beam.supports)
    has_fixed = any(s.type == SupportType.FIXED for s in beam.supports)

    if has_fixed and not has_pin and not has_roller:
        pass  # cantilever — תקין
    elif not has_fixed and not (has_pin or has_roller):
        issues.append("לא זוהה סוג סמך מוכר (pin / roller / fixed)")
    elif not has_fixed and has_pin and not has_roller:
        issues.append("קורה פשוטה דורשת גם סמך נייד (roller)")
    elif not has_fixed and has_roller and not has_pin:
        issues.append("קורה פשוטה דורשת גם סמך מפרק (pin)")

    if not beam.loads:
        issues.append("לא זוהו עומסים על השרטוט")

    for idx, ld in enumerate(beam.loads, start=1):
        if ld.x is not None and (ld.x < -0.01 or ld.x > L + tol):
            issues.append(f"עומס #{idx} ב-x={ld.x:g} מ' מחוץ לקורה")
        if ld.start_x is not None and ld.end_x is not None:
            if ld.start_x < -0.01 or ld.end_x > L + tol:
                issues.append(f"עומס מפוזר #{idx} חורג מגבולות הקורה")

    return issues


def _unwrap_beam_dict(raw: dict[str, Any]) -> dict[str, Any]:
    """מקבל dict מלא מה-OCR או רק את beam."""
    if "beam" in raw and isinstance(raw["beam"], dict):
        return {"exercise_type": raw.get("exercise_type", "beam"), "beam": raw["beam"]}
    if "L" in raw:
        return {"exercise_type": "beam", "beam": raw}
    return raw


def validate_beam_extraction(raw: dict[str, Any]) -> ValidationResult:
    """
    מאמת dict שחולץ מתמונה.

    Returns:
        ValidationResult עם ok=True ו-BeamExercise, או ok=False ורשימת שגיאות.
    """
    if not raw:
        return ValidationResult(ok=False, errors=["לא התקבלו נתונים"])

    payload = _unwrap_beam_dict(raw)
    try:
        exercise = BeamExercise.model_validate(payload)
    except ValidationError as exc:
        return ValidationResult(ok=False, errors=_format_pydantic_errors(exc))

    cross_issues = _cross_validate(exercise.beam)
    if cross_issues:
        return ValidationResult(ok=False, errors=cross_issues)

    return ValidationResult(ok=True, data=exercise)


if __name__ == "__main__":
    # בדיקה מהירה: python -m core.beam_validator
    good = {
        "beam": {
            "L": 15.0,
            "supports": [
                {"label": "A", "type": "pin", "x": 0},
                {"label": "B", "type": "roller", "x": 15},
            ],
            "loads": [
                {"type": "point", "x": 5.2, "Fy": 2},
                {"type": "point", "x": 10.2, "Fy": 5},
            ],
        }
    }
    bad_no_L = {"beam": {"supports": [{"label": "A", "type": "pin", "x": 0}], "loads": []}}
    bad_load_outside = {
        "beam": {
            "L": 10,
            "supports": [
                {"label": "A", "type": "pin", "x": 0},
                {"label": "B", "type": "roller", "x": 10},
            ],
            "loads": [{"type": "point", "x": 12, "Fy": 3}],
        }
    }

    for name, sample in [("תקין", good), ("חסר L", bad_no_L), ("עומס מחוץ לקורה", bad_load_outside)]:
        result = validate_beam_extraction(sample)
        print(f"\n--- {name} ---")
        print(f"ok={result.ok}")
        if result.ok:
            print(f"L={result.data.beam.L}, עומסים={len(result.data.beam.loads)}")
        else:
            for err in result.errors:
                print(f"  • {err}")
