# -*- coding: utf-8 -*-
"""CLI: python -m exercise_generator --count 10 --out output/batch1"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from exercise_generator.pipeline import generate_batch
from exercise_generator.templates.registry import LOCKED_FAMILY, list_families


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m exercise_generator",
        description=(
            "מחולל תרגילי קורות — שרטוט נעול ב־render/; "
            f"ברירת מחדל לנתונים: {LOCKED_FAMILY}."
        ),
    )
    p.add_argument(
        "--count",
        type=int,
        default=1,
        help="מספר תרגילים לייצור (ברירת מחדל: 1)",
    )
    p.add_argument(
        "--family",
        type=str,
        default=None,
        choices=list_families(),
        help=(
            f"כפיית תבנית נתונים (ברירת מחדל נעולה: {LOCKED_FAMILY}; "
            "מיועד לפיתוח בלבד)"
        ),
    )
    p.add_argument(
        "--seed",
        type=int,
        default=None,
        help="seed דטרמיניסטי (לחיבור חוקי הגרלת נתונים בהמשך)",
    )
    p.add_argument(
        "--out",
        type=str,
        default="output",
        help="תיקיית פלט (ברירת מחדל: output/)",
    )
    p.add_argument(
        "--list-families",
        action="store_true",
        help="הדפסת מזהי תבניות הנתונים (כולל הנעולה) ויציאה",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.list_families:
        for fid in list_families():
            mark = " (locked)" if fid == LOCKED_FAMILY else ""
            print(f"{fid}{mark}")
        return 0

    out_dir = Path(args.out)
    artifacts = generate_batch(
        count=args.count,
        family=args.family,
        seed=args.seed,
        out_dir=out_dir,
    )
    print(f"Generated {len(artifacts)} exercise(s) -> {out_dir.resolve()}")
    for a in artifacts:
        print(f"  {a.json_path.name}  {a.png_path.name}  [{a.exercise.family}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
