# -*- coding: utf-8 -*-
"""מנוע תיקונים ללולאת האימות — הנחיות ממוקדות + כללים נלמדים."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from bot.config import APP_DIR

log = logging.getLogger("validation_fix_engine")

LEARNED_RULES_PATH = APP_DIR / "learned_extraction_rules.json"
VALIDATOR_IMAGES_DIR = APP_DIR / "validator_images"
ARCHIVE_DIR = VALIDATOR_IMAGES_DIR / "_archive"
FAILURES_DIR = VALIDATOR_IMAGES_DIR / "failures"
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".gif")


def _load_rules_data() -> dict:
    if not LEARNED_RULES_PATH.is_file():
        return {"version": 1, "rules": []}
    try:
        data = json.loads(LEARNED_RULES_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "rules": []}
    if not isinstance(data, dict):
        return {"version": 1, "rules": []}
    data.setdefault("rules", [])
    return data


def _save_rules_data(data: dict) -> None:
    LEARNED_RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    LEARNED_RULES_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def reload_learned_rules() -> int:
    """מחזיר מספר כללים פעילים."""
    return len(_load_rules_data().get("rules") or [])


def _num_close(a: float, b: float, tol: float = 0.2) -> bool:
    return abs(a - b) <= tol


def diagnose_from_issues(
    ground_truth_issues: list[str],
    expected: dict | None,
    extracted: dict | None,
) -> dict[str, Any]:
    """מסקת סוג כשל מובנית ללמידה ותיקון."""
    out: dict[str, Any] = {
        "issues": list(ground_truth_issues),
        "tags": [],
        "exp_L": None,
        "got_L": None,
        "exp_roller_x": None,
        "got_roller_x": None,
    }
    if expected and extracted:
        exp_beam = expected.get("beam") if isinstance(expected.get("beam"), dict) else expected
        got_beam = extracted.get("beam") if isinstance(extracted.get("beam"), dict) else {}
        try:
            out["exp_L"] = float(exp_beam.get("L")) if exp_beam.get("L") is not None else None
            out["got_L"] = float(got_beam.get("L")) if got_beam.get("L") is not None else None
        except (TypeError, ValueError):
            pass
        for sup in (exp_beam.get("supports") or []):
            if isinstance(sup, dict) and str(sup.get("type", "")).lower() == "roller":
                try:
                    out["exp_roller_x"] = float(sup.get("x"))
                except (TypeError, ValueError):
                    pass
        for sup in (got_beam.get("supports") or []):
            if isinstance(sup, dict) and str(sup.get("type", "")).lower() == "roller":
                try:
                    out["got_roller_x"] = float(sup.get("x"))
                except (TypeError, ValueError):
                    pass

    blob = " ".join(ground_truth_issues).lower()
    if out["exp_L"] is not None and out["got_L"] is not None:
        if out["got_L"] < out["exp_L"] - 0.5:
            out["tags"].append("L_too_short")
        elif out["got_L"] > out["exp_L"] + 0.5:
            out["tags"].append("L_too_long")
    if "b" in blob and "13" in blob or (
        out["exp_roller_x"] == 12 and out.get("got_roller_x") == 13
    ):
        out["tags"].append("B_misread_as_13")
    if "support" in blob:
        out["tags"].append("wrong_support")
    if "load" in blob or "udl" in blob or ".x" in blob or "distributed" in blob:
        out["tags"].append("wrong_loads")
    if any(i.startswith("L ") for i in ground_truth_issues):
        out["tags"].append("wrong_length")
    return out


def build_targeted_fix_prompt(
    ground_truth_issues: list[str],
    expected: dict | None,
    extracted: dict | None,
) -> str:
    """הנחיית תיקון מדויקת ל-Gemini מהשוואה לציפייה."""
    lines = [
        "TARGETED FIX — previous extraction FAILED ground-truth check. Re-read the image.",
        "Use FOCUS MODE: Step 1 dimension chain cumulative sums ONLY, then Step 2 loads.",
        "",
        "Errors to fix:",
    ]
    for issue in ground_truth_issues[:12]:
        lines.append(f"- {issue}")

    if expected and isinstance(expected.get("beam"), dict):
        exp_beam = expected["beam"]
        exp_l = exp_beam.get("L")
        if exp_l is not None:
            lines.append(f"\nGround truth L = {exp_l} m (sum ALL dimension segments).")
        lp = exp_beam.get("labeled_points") or []
        if lp:
            pts = ", ".join(
                f"{p.get('label')}={p.get('x')}"
                for p in lp
                if isinstance(p, dict) and p.get("label")
            )
            if pts:
                lines.append(f"Labeled points (dimension chain): {pts}")
        supports = exp_beam.get("supports") or []
        for sup in supports:
            if isinstance(sup, dict):
                lines.append(
                    f"Support {sup.get('label', '?')}: type={sup.get('type')}, x={sup.get('x')}"
                )
        loads = exp_beam.get("loads") or []
        if loads:
            lines.append(f"Expected {len(loads)} load entries — match positions from dimension chain.")

    if extracted and isinstance(extracted.get("beam"), dict):
        got = extracted["beam"]
        got_l = got.get("L")
        if got_l is not None:
            lines.append(f"\nYour last attempt had L={got_l} — correct it.")

    lines.append(
        "\nDimension chain ALWAYS wins. One UDL per span. loads[] sorted left→right."
    )
    return "\n".join(lines)


def _rule_exists(rule_id: str) -> bool:
    for rule in _load_rules_data().get("rules") or []:
        if isinstance(rule, dict) and rule.get("id") == rule_id:
            return True
    return False


def learn_rule_from_diagnosis(
    diagnosis: dict[str, Any],
    *,
    example: str = "",
) -> str | None:
    """רושם כלל חדש ב-learned_extraction_rules.json אם מזוהה דפוס."""
    tags = diagnosis.get("tags") or []
    exp_l = diagnosis.get("exp_L")
    got_l = diagnosis.get("got_L")
    new_id: str | None = None
    description = ""

    if "L_too_short" in tags and exp_l is not None and abs(float(exp_l) - 12) < 0.6:
        new_id = "auto_l12_missing_tail"
        description = "L one meter short (11 vs 12): apply standard L=12 chain from dimension sums."
    elif "L_too_long" in tags or "B_misread_as_13" in tags:
        if exp_l is not None and abs(float(exp_l) - 12) < 0.6:
            new_id = "auto_b_misread_13"
            description = "Letter B misread as 13: L and roller must be 12 not 13."
    elif "wrong_length" in tags and exp_l is not None and got_l is not None:
        delta = float(exp_l) - float(got_l)
        if abs(delta) == 1.0:
            new_id = f"auto_L_offset_{int(delta):+d}"
            description = f"L off by {delta:g} m — reconcile from dimension chain sum."

    if not new_id or _rule_exists(new_id):
        return None

    data = _load_rules_data()
    rules: list[dict] = data.setdefault("rules", [])
    rules.append(
        {
            "id": new_id,
            "description": description,
            "tags": tags,
            "example": example,
            "exp_L": float(exp_l) if exp_l is not None else None,
            "action": (
                "apply_standard_l12"
                if "l12" in new_id or "missing" in new_id
                else "fix_b_misread_13"
            ),
            "created": datetime.now(timezone.utc).isoformat(),
            "hits": 0,
        }
    )
    _save_rules_data(data)
    log.info("Learned extraction rule: %s — %s", new_id, description)
    return new_id


def _rule_should_apply(rule: dict, beam: dict, loads: list[dict]) -> bool:
    """כלל L=12 חל רק על תרגילים שמתאימים — לא על exercise_01 (L=15)."""
    from bot.vision import (
        _looks_like_b_misread_as_13,
        _matches_l12_chain_signature,
        _needs_l12_geometry_fixup,
    )

    action = str(rule.get("action", ""))
    L = float(beam.get("L", 0.0))
    exp_l = rule.get("exp_L")

    if action == "apply_standard_l12":
        if exp_l is not None and abs(float(exp_l) - 12) > 0.6:
            return False
        if L > 13.5:
            return False
        return (
            _matches_l12_chain_signature(beam, loads)
            or _needs_l12_geometry_fixup(beam, loads)
        )
    if action == "fix_b_misread_13":
        if exp_l is not None and abs(float(exp_l) - 12) > 0.6:
            return False
        return _looks_like_b_misread_as_13(beam) and (
            _matches_l12_chain_signature(beam, loads)
            or _needs_l12_geometry_fixup(beam, loads)
            or 12.5 <= L <= 13.5
        )
    return False


def apply_learned_extraction_rules(beam: dict, loads: list[dict]) -> list[dict]:
    """מפעיל כללים מ-learned_extraction_rules.json (נקרא מ-normalize_beam_model)."""
    from bot.vision import (
        _apply_standard_l12_labeled_chain,
        _fix_b_misread_as_13,
    )

    actions: dict[str, Callable[..., Any]] = {
        "apply_standard_l12": lambda b, ld: _apply_standard_l12_labeled_chain(b),
        "fix_b_misread_13": lambda b, ld: _fix_b_misread_as_13(b, ld),
    }

    data = _load_rules_data()
    applied: list[str] = []
    for rule in data.get("rules") or []:
        if not isinstance(rule, dict):
            continue
        if not _rule_should_apply(rule, beam, loads):
            continue
        action_name = str(rule.get("action", ""))
        fn = actions.get(action_name)
        if fn is None:
            continue
        try:
            fn(beam, loads)
            rule["hits"] = int(rule.get("hits", 0)) + 1
            applied.append(str(rule.get("id", action_name)))
        except Exception as exc:
            log.warning("Rule %s failed: %s", rule.get("id"), exc)

    if applied:
        _save_rules_data(data)
        log.info("Applied learned rules: %s", ", ".join(applied))
    return loads


def save_failure_artifact(
    image_name: str,
    expected: dict | None,
    extracted: dict | None,
    issues: list[str],
) -> Path:
    """שומר כשל אחרון לניתוח ידני."""
    FAILURES_DIR.mkdir(parents=True, exist_ok=True)
    stem = Path(image_name).stem
    path = FAILURES_DIR / f"{stem}.last_failure.json"
    path.write_text(
        json.dumps(
            {
                "image": image_name,
                "time": datetime.now(timezone.utc).isoformat(),
                "issues": issues,
                "expected": expected,
                "extracted": extracted,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def _archive_image(stem: str, image_src: Path) -> Path:
    """עותק קבוע ב-_archive — משוחזר אוטומטית אם התמונה נמחקת."""
    import shutil

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    suffix = image_src.suffix.lower() if image_src.suffix else ".jpg"
    archive_path = ARCHIVE_DIR / f"{stem}{suffix}"
    shutil.copy2(image_src, archive_path)
    log.info("Archived validator image: %s", archive_path.name)
    return archive_path


def _find_archived_image(stem: str) -> Path | None:
    if not ARCHIVE_DIR.is_dir():
        return None
    for suffix in IMAGE_SUFFIXES:
        candidate = ARCHIVE_DIR / f"{stem}{suffix}"
        if candidate.is_file():
            return candidate
    return None


def ensure_validator_images(images_dir: Path | None = None) -> list[Path]:
    """משחזר תמונות חסרות מ-_archive לפי קבצי expected.json."""
    import shutil

    dest_dir = images_dir or VALIDATOR_IMAGES_DIR
    if not dest_dir.is_dir():
        return []

    restored: list[Path] = []
    for exp in sorted(dest_dir.glob("*.expected.json")):
        stem = exp.name.replace(".expected.json", "")
        has_image = any(
            (dest_dir / f"{stem}{suffix}").is_file() for suffix in IMAGE_SUFFIXES
        )
        if has_image:
            continue
        archived = _find_archived_image(stem)
        if archived is None:
            log.warning("Missing image for %s — no archive in %s", stem, ARCHIVE_DIR)
            continue
        dest = dest_dir / f"{stem}{archived.suffix.lower()}"
        shutil.copy2(archived, dest)
        restored.append(dest)
        log.info("Restored %s from archive", dest.name)

    return restored


def add_exercise_to_validator(
    name: str,
    image_src: Path,
    expected_src: Path | None = None,
    *,
    images_dir: Path | None = None,
) -> tuple[Path, Path | None]:
    """מעתיק תמונה + expected ל-validator_images/ ושומר עותק קבוע ב-_archive."""
    dest_dir = images_dir or VALIDATOR_IMAGES_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^\w\-]+", "_", name.strip()).strip("_") or "exercise"
    if not stem.startswith("exercise"):
        stem = f"exercise_{stem}"

    img_dest = dest_dir / f"{stem}{image_src.suffix.lower()}"
    import shutil

    shutil.copy2(image_src, img_dest)
    _archive_image(stem, img_dest)

    exp_dest: Path | None = None
    if expected_src and expected_src.is_file():
        exp_dest = dest_dir / f"{stem}.expected.json"
        shutil.copy2(expected_src, exp_dest)
    return img_dest, exp_dest
