# -*- coding: utf-8 -*-
"""הגרלת נתונים לפי חוקים שהוגדרו."""
from __future__ import annotations

import math
import random
from typing import Any

# אורך קורה [מ'] — נגזר מסכום מרווחי הנקודות (או הגרלה ישירה)
L_MIN = 4.0
L_MAX = 12.0
# 80% מספר שלם, 20% עשרוני עם ספרה אחת אחרי הנקודה
CLEAN_INTEGER_PROB = 0.80
L_INTEGER_PROB = CLEAN_INTEGER_PROB  # תאימות לאחור

# מרווח בודד בין נקודות עניין [מ']
SEG_MIN = 1.0
SEG_MAX = 5.0


def make_rng(seed: int | None = None) -> random.Random:
    return random.Random(seed)


def random_clean_measure(
    rng: random.Random,
    *,
    lo: float,
    hi: float,
    integer_prob: float = CLEAN_INTEGER_PROB,
) -> float:
    """ערך «נקי»: 80% שלם, 20% עם ספרה עשרונית אחת (לא .0)."""
    lo_i = int(math.ceil(lo))
    hi_i = int(math.floor(hi))
    if hi_i < lo_i:
        raise ValueError(f"empty integer range for measure [{lo}, {hi}]")

    if rng.random() < integer_prob:
        return float(rng.randint(lo_i, hi_i))

    lo_t = int(math.ceil(lo * 10 - 1e-9))
    hi_t = int(math.floor(hi * 10 + 1e-9))
    candidates = [t for t in range(lo_t, hi_t + 1) if t % 10 != 0]
    if not candidates:
        return float(rng.randint(lo_i, hi_i))
    return round(rng.choice(candidates) / 10.0, 1)


def random_beam_length(rng: random.Random) -> float:
    """אורך קורה בין 4 ל־12 מ': 80% שלם, 20% עם ספרה עשרונית אחת (למשל 8.4)."""
    return random_clean_measure(rng, lo=L_MIN, hi=L_MAX)


def random_point_spacings(
    rng: random.Random,
    *,
    n_segments: int = 4,
    max_tries: int = 250,
) -> tuple[list[float], float]:
    """מרווחים בין נקודות: כל מרווח 80% שלם / 20% עשרוני אחד; סכום = L ב־[4, 12]."""
    if n_segments < 1:
        raise ValueError("n_segments must be >= 1")
    for _ in range(max_tries):
        segs = [
            random_clean_measure(rng, lo=SEG_MIN, hi=SEG_MAX)
            for _ in range(n_segments)
        ]
        L = round(sum(segs), 1)
        if L_MIN - 1e-9 <= L <= L_MAX + 1e-9:
            return segs, L
    # נפילה בטוחה — מקטעים שלמים שסכומם בטווח
    base = max(1, int(L_MIN // n_segments))
    segs = [float(base)] * n_segments
    # התאמה ל־L≈8 אם אפשר
    target = min(L_MAX, max(L_MIN, float(base * n_segments)))
    segs[-1] = round(target - sum(segs[:-1]), 1)
    return segs, round(sum(segs), 1)


def stub_params(rng: random.Random) -> dict[str, Any]:
    """פרמטרים מוגרלים לתרגיל — מתרחב כשיתווספו חוקים."""
    segs, L = random_point_spacings(rng)
    return {"L": L, "spacings": segs}
