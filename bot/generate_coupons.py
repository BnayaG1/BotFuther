# -*- coding: utf-8 -*-
"""יצירת קודי קופון חד-פעמיים ב-SQLite.

דוגמה:
    python -m bot.generate_coupons --package 2_30 --count 20
    python -m bot.generate_coupons --quota 5 --days 105 --count 10
    python -m bot.generate_coupons --package 10_105 --count 5 --out codes.txt
"""
from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

from bot.access import (
    VALID_DAILY_QUOTAS,
    VALID_PERIOD_DAYS,
    insert_coupon_codes,
    normalize_coupon_code,
)
from bot.config import APP_DIR, COUPON_DB_PATH
from bot.purchase import PACKAGE_CATALOG, get_package


def _make_code(length: int = 10) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_coupon_codes(
    *,
    package_id: str,
    count: int,
    length: int = 10,
) -> list[str]:
    """יוצר קודי קופון חדשים לחבילה ושומר ב-DB. מחזיר את הקודים שנוספו."""
    if count < 1:
        raise ValueError("count must be >= 1")
    pkg = get_package(package_id)
    if pkg is None:
        raise ValueError(f"Unknown package: {package_id}")

    codes: list[str] = []
    seen: set[str] = set()
    while len(codes) < count:
        code = normalize_coupon_code(_make_code(length))
        if code in seen:
            continue
        seen.add(code)
        codes.append(code)

    added = insert_coupon_codes(
        codes,
        daily_quota=pkg.daily_quota,
        period_days=pkg.period_days,
    )
    return codes[:added]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate one-time coupon codes")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--package",
        choices=[p.package_id for p in PACKAGE_CATALOG],
        help="Package id, e.g. 2_30, 5_105",
    )
    group.add_argument(
        "--quota",
        type=int,
        choices=sorted(VALID_DAILY_QUOTAS),
        help="Daily image quota (use with --days)",
    )
    parser.add_argument(
        "--days",
        type=int,
        choices=sorted(VALID_PERIOD_DAYS),
        help="Subscription period in days: 30 or 105",
    )
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--length", type=int, default=10)
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Optional file to append generated codes",
    )
    args = parser.parse_args(argv)

    if args.count < 1:
        print("count must be >= 1", file=sys.stderr)
        return 1

    if args.package:
        pkg = get_package(args.package)
        if pkg is None:
            print(f"Unknown package: {args.package}", file=sys.stderr)
            return 1
        daily_quota = pkg.daily_quota
        period_days = pkg.period_days
        package_id = pkg.package_id
    else:
        if args.days is None:
            print("--days is required when using --quota", file=sys.stderr)
            return 1
        daily_quota = int(args.quota)
        period_days = int(args.days)
        package_id = f"{daily_quota}_{period_days}"

    codes: list[str] = []
    seen: set[str] = set()
    while len(codes) < args.count:
        code = normalize_coupon_code(_make_code(args.length))
        if code in seen:
            continue
        seen.add(code)
        codes.append(code)

    try:
        added_codes = generate_coupon_codes(
            package_id=package_id,
            count=args.count,
            length=args.length,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    added = len(added_codes)
    print(f"DB: {COUPON_DB_PATH}")
    print(
        f"Requested: {args.count}, inserted: {added}, "
        f"package: {package_id} ({daily_quota}/day, {period_days} days)"
    )

    lines = [f"{package_id}\t{c}" for c in added_codes]
    for line in lines:
        print(line)

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("a", encoding="utf-8") as fh:
            for line in lines:
                fh.write(line + "\n")
        print(f"Wrote {len(lines)} lines to {args.out}")

    return 0


if __name__ == "__main__":
    if str(APP_DIR) not in sys.path:
        sys.path.insert(0, str(APP_DIR))
    raise SystemExit(main())
