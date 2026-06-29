# -*- coding: utf-8 -*-
"""Regression tests for vision extraction — compare live output to expected JSON.

Usage:
  python -m bot.vision_regression              # run all cases (calls Gemini)
  python -m bot.vision_regression --list       # list discovered cases
  python -m bot.vision_regression --case NAME  # single case
  python -m bot.vision_regression --record NAME  # save extraction as expected.json
  python -m bot.vision_regression --compare-only  # diff last_run vs expected (no API)
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bot.config import APP_DIR
from bot.env import load_env_files, resolve_primary_model
from bot.gemini_chat import create_gemini_client
from bot.images import mime_to_suffix, prepare_image_path_for_vision
from bot.prompt_loader import build_vision_extra_instruction
from bot.validation_fix_engine import (
    IMAGE_SUFFIXES,
    VALIDATOR_IMAGES_DIR,
    _num_close,
    ensure_validator_images,
    save_failure_artifact,
)
from bot.vision import (
    extract_exercise_with_retries,
    finalize_beam_extraction,
    infer_vision_exercise_type,
    package_extraction_response,
)

log = logging.getLogger("vision_regression")

DEFAULT_X_TOL = 0.3
DEFAULT_VALUE_TOL = 0.35


@dataclass
class RegressionCase:
    stem: str
    image_path: Path
    expected_path: Path


@dataclass
class CaseResult:
    stem: str
    passed: bool
    issues: list[str] = field(default_factory=list)
    elapsed_sec: float = 0.0
    extracted: dict[str, Any] | None = None
    skipped: bool = False
    skip_reason: str = ""


def _beam_from_payload(data: dict[str, Any]) -> dict[str, Any]:
    beam = data.get("beam")
    if isinstance(beam, dict):
        return beam
    return data


def _options_from_expected(expected_doc: dict[str, Any]) -> dict[str, Any]:
    opts = expected_doc.get("options")
    return opts if isinstance(opts, dict) else {}


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _load_magnitude(ld: dict[str, Any]) -> float | None:
    mag = _float_or_none(ld.get("magnitude_ton"))
    if mag is not None:
        return abs(mag)
    fx = _float_or_none(ld.get("Fx", ld.get("fx"))) or 0.0
    fy = _float_or_none(ld.get("Fy", ld.get("fy"))) or 0.0
    if abs(fx) < 1e-9 and abs(fy) < 1e-9:
        return None
    return math.hypot(fx, fy)


def _load_x(ld: dict[str, Any]) -> float | None:
    t = str(ld.get("type", "")).lower()
    if t == "distributed":
        return _float_or_none(ld.get("x1"))
    return _float_or_none(ld.get("x"))


def _support_key(sup: dict[str, Any]) -> str:
    label = str(sup.get("label", "")).strip().upper()
    if label:
        return f"label:{label}"
    st = str(sup.get("type", "")).lower()
    x = _float_or_none(sup.get("x"))
    return f"{st}@{x}"


def _compare_supports(
    exp_supports: list[dict[str, Any]],
    got_supports: list[dict[str, Any]],
    *,
    x_tol: float,
) -> list[str]:
    issues: list[str] = []
    exp_by_key = {_support_key(s): s for s in exp_supports if isinstance(s, dict)}
    got_by_key = {_support_key(s): s for s in got_supports if isinstance(s, dict)}

    for key, exp in exp_by_key.items():
        got = got_by_key.get(key)
        label = str(exp.get("label") or key)
        if got is None:
            issues.append(f"support missing: {label}")
            continue
        exp_type = str(exp.get("type", "")).lower()
        got_type = str(got.get("type", "")).lower()
        if exp_type and got_type and exp_type != got_type:
            issues.append(f"support {label} type: expected {exp_type}, got {got_type}")
        exp_x = _float_or_none(exp.get("x"))
        got_x = _float_or_none(got.get("x"))
        if exp_x is not None and got_x is not None and not _num_close(exp_x, got_x, x_tol):
            issues.append(
                f"support {label} x: expected {exp_x:g}, got {got_x:g}"
            )

    extra = set(got_by_key) - set(exp_by_key)
    for key in sorted(extra):
        got = got_by_key[key]
        label = str(got.get("label") or key)
        issues.append(f"unexpected support: {label} at x={got.get('x')}")
    return issues


def _loads_match(
    exp: dict[str, Any],
    got: dict[str, Any],
    *,
    x_tol: float,
    value_tol: float,
) -> list[str]:
    issues: list[str] = []
    t = str(exp.get("type", "")).lower()
    got_t = str(got.get("type", "")).lower()
    if t != got_t:
        return [f"type expected {t}, got {got_t}"]

    exp_x = _load_x(exp)
    got_x = _load_x(got)
    if exp_x is not None and got_x is not None and not _num_close(exp_x, got_x, x_tol):
        issues.append(f"x expected {exp_x:g}, got {got_x:g}")

    if t == "point":
        for key in ("Fy", "fy", "Fx", "fx"):
            exp_v = _float_or_none(exp.get(key))
            if exp_v is None:
                continue
            got_key = "Fy" if key.lower() == "fy" else "Fx" if key.lower() == "fx" else key
            got_v = _float_or_none(got.get(got_key, got.get(key.lower())))
            if got_v is None:
                issues.append(f"{key} expected {exp_v:g}, missing")
            elif not _num_close(exp_v, got_v, value_tol):
                issues.append(f"{key} expected {exp_v:g}, got {got_v:g}")
    elif t == "moment":
        exp_m = _float_or_none(exp.get("M", exp.get("m")))
        got_m = _float_or_none(got.get("M", got.get("m")))
        if exp_m is not None:
            if got_m is None:
                issues.append(f"M expected {exp_m:g}, missing")
            elif not _num_close(exp_m, got_m, value_tol):
                issues.append(f"M expected {exp_m:g}, got {got_m:g}")
    elif t == "distributed":
        for key in ("x2", "w"):
            exp_v = _float_or_none(exp.get(key))
            if exp_v is None:
                continue
            got_v = _float_or_none(got.get(key))
            if got_v is None:
                issues.append(f"{key} expected {exp_v:g}, missing")
            elif not _num_close(abs(exp_v), abs(got_v), value_tol):
                issues.append(f"{key} expected {exp_v:g}, got {got_v:g}")
    elif t == "inclined":
        exp_mag = _load_magnitude(exp)
        got_mag = _load_magnitude(got)
        if exp_mag is not None and got_mag is not None:
            if not _num_close(exp_mag, got_mag, value_tol):
                issues.append(f"magnitude expected {exp_mag:g}, got {got_mag:g}")
        exp_angle = _float_or_none(exp.get("angle_deg"))
        got_angle = _float_or_none(got.get("angle_deg"))
        if exp_angle is not None and got_angle is not None:
            if not _num_close(exp_angle, got_angle, 5.0):
                issues.append(f"angle_deg expected {exp_angle:g}, got {got_angle:g}")
        exp_dir = str(exp.get("incl_dir", "")).lower()
        got_dir = str(got.get("incl_dir", "")).lower()
        if not got_dir and got_mag:
            fx = _float_or_none(got.get("Fx", got.get("fx"))) or 0.0
            got_dir = "dl" if fx < 0 else "dr"
        if exp_dir and got_dir and exp_dir != got_dir:
            issues.append(f"incl_dir expected {exp_dir}, got {got_dir}")
    return issues


def _find_got_load(
    exp: dict[str, Any],
    got_loads: list[dict[str, Any]],
    *,
    x_tol: float,
    used: set[int],
) -> dict[str, Any] | None:
    exp_x = _load_x(exp)
    exp_t = str(exp.get("type", "")).lower()
    best_idx: int | None = None
    best_dist = float("inf")
    for idx, got in enumerate(got_loads):
        if idx in used:
            continue
        if str(got.get("type", "")).lower() != exp_t:
            continue
        got_x = _load_x(got)
        if exp_x is None or got_x is None:
            continue
        dist = abs(exp_x - got_x)
        if dist <= x_tol and dist < best_dist:
            best_dist = dist
            best_idx = idx
    if best_idx is None:
        return None
    used.add(best_idx)
    return got_loads[best_idx]


def _compare_loads(
    exp_loads: list[dict[str, Any]],
    got_loads: list[dict[str, Any]],
    *,
    x_tol: float,
    value_tol: float,
    min_loads: int | None,
) -> list[str]:
    issues: list[str] = []
    if min_loads is not None and len(got_loads) < min_loads:
        issues.append(f"load count: expected at least {min_loads}, got {len(got_loads)}")

    used: set[int] = set()
    for i, exp in enumerate(exp_loads, 1):
        if not isinstance(exp, dict):
            continue
        got = _find_got_load(exp, got_loads, x_tol=x_tol, used=used)
        exp_t = str(exp.get("type", "load"))
        exp_x = _load_x(exp)
        tag = f"load #{i} ({exp_t} @ x={exp_x})"
        if got is None:
            issues.append(f"{tag}: not found in extraction")
            continue
        sub = _loads_match(exp, got, x_tol=x_tol, value_tol=value_tol)
        for s in sub:
            issues.append(f"{tag}: {s}")

    if len(got_loads) > len(exp_loads):
        issues.append(
            f"extra loads: expected {len(exp_loads)}, got {len(got_loads)}"
        )
    return issues


def compare_beam_to_expected(
    expected_doc: dict[str, Any],
    extracted: dict[str, Any],
) -> list[str]:
    """השוואת מודל קורה לציפייה — מחזיר רשימת בעיות (ריק = עבר)."""
    opts = _options_from_expected(expected_doc)
    x_tol = float(opts.get("x_tol", DEFAULT_X_TOL))
    value_tol = float(opts.get("value_tol", DEFAULT_VALUE_TOL))
    min_loads = opts.get("min_loads")
    min_loads_i = int(min_loads) if min_loads is not None else None

    exp_beam = _beam_from_payload(expected_doc)
    got_beam = _beam_from_payload(extracted)
    issues: list[str] = []

    exp_L = _float_or_none(exp_beam.get("L"))
    got_L = _float_or_none(got_beam.get("L"))
    if exp_L is not None:
        if got_L is None:
            issues.append(f"L expected {exp_L:g}, missing")
        elif not _num_close(exp_L, got_L, x_tol):
            issues.append(f"L expected {exp_L:g}, got {got_L:g}")

    exp_supports = [
        s for s in (exp_beam.get("supports") or []) if isinstance(s, dict)
    ]
    got_supports = [
        s for s in (got_beam.get("supports") or []) if isinstance(s, dict)
    ]
    if exp_supports:
        issues.extend(
            _compare_supports(exp_supports, got_supports, x_tol=x_tol)
        )

    exp_loads = [ld for ld in (exp_beam.get("loads") or []) if isinstance(ld, dict)]
    got_loads = [ld for ld in (got_beam.get("loads") or []) if isinstance(ld, dict)]
    if exp_loads:
        issues.extend(
            _compare_loads(
                exp_loads,
                got_loads,
                x_tol=x_tol,
                value_tol=value_tol,
                min_loads=min_loads_i,
            )
        )

    labeled_exp = exp_beam.get("labeled_points")
    if isinstance(labeled_exp, list):
        labeled_got = _beam_from_payload(extracted).get("labeled_points") or []
        got_map = {
            str(p.get("label", "")).strip().upper(): _float_or_none(p.get("x"))
            for p in labeled_got
            if isinstance(p, dict) and p.get("label")
        }
        for pt in labeled_exp:
            if not isinstance(pt, dict):
                continue
            lbl = str(pt.get("label", "")).strip().upper()
            exp_x = _float_or_none(pt.get("x"))
            if not lbl or exp_x is None:
                continue
            got_x = got_map.get(lbl)
            if got_x is None:
                issues.append(f"labeled point {lbl} missing")
            elif not _num_close(exp_x, got_x, x_tol):
                issues.append(f"labeled {lbl} x: expected {exp_x:g}, got {got_x:g}")

    return issues


def discover_cases(images_dir: Path | None = None) -> list[RegressionCase]:
    """מוצא זוגות תמונה + expected.json."""
    root = images_dir or VALIDATOR_IMAGES_DIR
    ensure_validator_images(root)
    cases: list[RegressionCase] = []
    if not root.is_dir():
        return cases

    for expected_path in sorted(root.glob("*.expected.json")):
        stem = expected_path.name[: -len(".expected.json")]
        image_path: Path | None = None
        for suffix in IMAGE_SUFFIXES:
            candidate = root / f"{stem}{suffix}"
            if candidate.is_file():
                image_path = candidate
                break
        if image_path is None:
            log.warning("No image for %s — skip", stem)
            continue
        cases.append(
            RegressionCase(
                stem=stem,
                image_path=image_path,
                expected_path=expected_path,
            )
        )
    return cases


def _last_run_path(case: RegressionCase) -> Path:
    return case.expected_path.with_name(f"{case.stem}.last_run.json")


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must be a JSON object")
    return data


def _strip_for_record(extracted: dict[str, Any]) -> dict[str, Any]:
    """מבנה מינימלי לשמירה כ-expected."""
    out: dict[str, Any] = {
        "exercise_type": infer_vision_exercise_type(extracted),
    }
    beam = extracted.get("beam")
    if isinstance(beam, dict):
        out["beam"] = beam
    cog = extracted.get("cog")
    if isinstance(cog, dict):
        out["cog"] = cog
    out["options"] = {
        "x_tol": DEFAULT_X_TOL,
        "value_tol": DEFAULT_VALUE_TOL,
    }
    return out


def extract_from_image_path(image_path: Path) -> dict[str, Any]:
    """חילוץ מלא כמו הבוט — קורא ל-Gemini."""
    load_env_files()
    client = create_gemini_client()
    model = resolve_primary_model()
    image_bytes, mime_type = prepare_image_path_for_vision(image_path)
    extra = build_vision_extra_instruction()
    parsed = extract_exercise_with_retries(
        client,
        model,
        image_bytes,
        mime_type,
        extra_instruction=extra,
    )
    parsed = finalize_beam_extraction(parsed)
    return package_extraction_response(parsed)


def run_case(
    case: RegressionCase,
    *,
    live: bool = True,
    record: bool = False,
) -> CaseResult:
    """מריץ case אחד — live (Gemini) או compare-only מ-last_run."""
    if not case.expected_path.is_file() and not record:
        return CaseResult(
            stem=case.stem,
            passed=False,
            issues=[f"missing expected file: {case.expected_path}"],
            skipped=True,
            skip_reason="no expected",
        )

    started = time.monotonic()
    extracted: dict[str, Any] | None = None

    if live:
        try:
            extracted = extract_from_image_path(case.image_path)
        except Exception as exc:
            return CaseResult(
                stem=case.stem,
                passed=False,
                issues=[f"extraction failed: {exc}"],
                elapsed_sec=time.monotonic() - started,
            )
        last_run = _last_run_path(case)
        last_run.write_text(
            json.dumps(extracted, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    else:
        last_run = _last_run_path(case)
        if not last_run.is_file():
            return CaseResult(
                stem=case.stem,
                passed=False,
                issues=[f"missing {last_run.name} — run without --compare-only first"],
                skipped=True,
                skip_reason="no last_run",
                elapsed_sec=time.monotonic() - started,
            )
        extracted = _load_json(last_run)
        extracted = finalize_beam_extraction(extracted)

    if record:
        expected_doc = _strip_for_record(extracted or {})
        case.expected_path.write_text(
            json.dumps(expected_doc, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return CaseResult(
            stem=case.stem,
            passed=True,
            issues=[],
            elapsed_sec=time.monotonic() - started,
            extracted=extracted,
        )

    expected_doc = _load_json(case.expected_path)
    issues = compare_beam_to_expected(expected_doc, extracted or {})
    elapsed = time.monotonic() - started

    if issues and extracted is not None:
        save_failure_artifact(
            case.image_path.name,
            expected_doc,
            extracted,
            issues,
        )

    return CaseResult(
        stem=case.stem,
        passed=not issues,
        issues=issues,
        elapsed_sec=elapsed,
        extracted=extracted,
    )


def run_all_cases(
    cases: list[RegressionCase],
    *,
    live: bool = True,
    record: bool = False,
) -> list[CaseResult]:
    return [run_case(c, live=live, record=record) for c in cases]


def _print_result(result: CaseResult) -> None:
    status = "PASS" if result.passed else ("SKIP" if result.skipped else "FAIL")
    print(f"[{status}] {result.stem} ({result.elapsed_sec:.1f}s)")
    if result.skip_reason:
        print(f"       skip: {result.skip_reason}")
    for issue in result.issues:
        print(f"       - {issue}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Vision extraction regression — compare to validator_images/*.expected.json",
    )
    parser.add_argument(
        "--images-dir",
        type=Path,
        default=VALIDATOR_IMAGES_DIR,
        help=f"directory with image + expected pairs (default: {VALIDATOR_IMAGES_DIR})",
    )
    parser.add_argument("--case", metavar="STEM", help="run a single case by stem name")
    parser.add_argument("--list", action="store_true", help="list cases and exit")
    parser.add_argument(
        "--record",
        metavar="STEM",
        help="run extraction and write {stem}.expected.json (bootstrap)",
    )
    parser.add_argument(
        "--compare-only",
        action="store_true",
        help="compare last_run.json to expected — no Gemini API calls",
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="less logging")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(levelname)s %(name)s — %(message)s",
    )

    images_dir: Path = args.images_dir
    if not images_dir.is_absolute():
        images_dir = (APP_DIR / images_dir).resolve()

    cases = discover_cases(images_dir)

    if args.list:
        if not cases:
            print(f"No cases in {images_dir}")
            print("Add: {stem}.jpg + {stem}.expected.json")
            print("Or bootstrap: python -m bot.vision_regression --record exercise_01")
            return 0
        for case in cases:
            print(f"{case.stem}: {case.image_path.name} + {case.expected_path.name}")
        return 0

    if args.record:
        stem = args.record
        image_path: Path | None = None
        for suffix in IMAGE_SUFFIXES:
            candidate = images_dir / f"{stem}{suffix}"
            if candidate.is_file():
                image_path = candidate
                break
        if image_path is None:
            archive = images_dir / "_archive"
            for suffix in IMAGE_SUFFIXES:
                candidate = archive / f"{stem}{suffix}"
                if candidate.is_file():
                    image_path = candidate
                    break
        if image_path is None:
            print(f"Image not found for stem: {stem}", file=sys.stderr)
            return 1
        case = RegressionCase(
            stem=stem,
            image_path=image_path,
            expected_path=images_dir / f"{stem}.expected.json",
        )
        result = run_case(case, live=True, record=True)
        _print_result(result)
        print(f"Wrote {case.expected_path}")
        return 0 if result.passed else 1

    if args.case:
        cases = [c for c in cases if c.stem == args.case]
        if not cases:
            print(f"Case not found: {args.case}", file=sys.stderr)
            return 1

    if not cases:
        print(f"No regression cases in {images_dir}", file=sys.stderr)
        print("Bootstrap: python -m bot.vision_regression --record exercise_01", file=sys.stderr)
        return 1

    live = not args.compare_only
    results = run_all_cases(cases, live=live, record=False)

    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed and not r.skipped)
    skipped = sum(1 for r in results if r.skipped)

    print()
    for result in results:
        _print_result(result)

    print()
    print(f"Summary: {passed} passed, {failed} failed, {skipped} skipped / {len(results)} total")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
