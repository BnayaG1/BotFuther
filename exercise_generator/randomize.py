# -*- coding: utf-8 -*-
"""הגרלת נתונים לפי חוקים שהוגדרו."""
from __future__ import annotations

import math
import random
from typing import Any, Literal

# אורך קורה [מ'] — נגזר מסכום מרווחי הנקודות (או הגרלה ישירה)
L_MIN = 4.0
L_MAX = 12.0
# 80% מספר שלם, 20% עשרוני עם ספרה אחת אחרי הנקודה
CLEAN_INTEGER_PROB = 0.80
L_INTEGER_PROB = CLEAN_INTEGER_PROB  # תאימות לאחור

# מרווח בודד בין נקודות עניין [מ']
SEG_MIN = 1.0
SEG_MAX = 5.0

# עומסים: כמה בסך הכול, וכמה מהם מפורסים
LOAD_COUNT_FOUR = 4
LOAD_COUNT_FIVE = 5
FOUR_LOADS_PROB = 0.60  # 60% → 4 עומסים; 40% → 5 עומסים
TWO_DISTRIBUTED_PROB = 0.60  # 60% → 2 מפורסים; 40% → 1 מפורס
NonDistributedKind = Literal["point", "inclined", "moment", "axial"]
NON_DISTRIBUTED_KINDS: tuple[NonDistributedKind, ...] = (
    "point",
    "inclined",
    "moment",
    "axial",
)

# ערכי עומס — ברירות מחדל / תאימות; גודל כוח מוגרל ב־random_force_magnitude
POINT_FY = 6.0
AXIAL_FX = 6.0
INCLINED_MAG_TON = 10.0
FORCE_MAG_MIN = 2.0
FORCE_MAG_MAX = 16.0
FORCE_MAG_INTEGER_PROB = 0.75  # 75% שלם ב־[2,16]; 25% עשרוני אחד
# ליד קצה ימין — אין אלכסוני נוטה שמאלה (מתנגש בחותמת המותג)
INCLINED_NO_DL_RIGHT_M = 0.9
# מקסימום עומסים שנוגעים באותה נקודה על הקורה
MAX_LOADS_PER_POINT = 2
INCLINED_ANGLE_DEG = 30.0  # ברירת מחדל / תאימות; ההגרלה ב־random_inclined_angle_deg
INCLINED_ANGLE_TENS_PROB = 0.70  # 70% עשרות 10..80; 30% עשרוני ב־[30,70]
MOMENT_M = 3.0
UDL_W = 4.0  # ברירת מחדל / תאימות
UDL_W_ALT = 3.0  # ברירת מחדל / תאימות
UDL_W_MIN = 1
UDL_W_MAX = 7  # משקל מפורס: שלם ב־[1,7]; כמה מפורסים — ערכים שונים
# אורך מפורס [מ']: מ־1 עד L; משקל משולש עם שיא ב־L/2
UDL_SPAN_MIN = 1.0
UDL_SPAN_STEP = 1.0  # צעדים של מטר — לא ליצור נקודות קרובות מ־SEG_MIN

# תצורת סמכים / ריתום
SUPPORT_CONFIG_SS_PROB = 0.50  # 50% סמכים; 50% ריתום
FIXED_LEFT_PROB = 0.80  # בריתום: 80% שמאל; 20% ימין
# בתרגיל סמכים: לכל סמך 50% בקצה הקורה, 50% בנקודה שאינה קצה
SUPPORT_AT_END_PROB = 0.50
SupportConfigMode = Literal["simply_supported", "cantilever"]
FixedSide = Literal["left", "right"]


def make_rng(seed: int | None = None) -> random.Random:
    return random.Random(seed)


def pick_support_configuration(
    rng: random.Random,
) -> tuple[SupportConfigMode, FixedSide | None]:
    """50% simply_supported; 50% cantilever עם 80% קיר שמאל / 20% ימין."""
    if rng.random() < SUPPORT_CONFIG_SS_PROB:
        return "simply_supported", None
    side: FixedSide = "left" if rng.random() < FIXED_LEFT_PROB else "right"
    return "cantilever", side


def _is_near(a: float, b: float, *, tol: float = 1e-9) -> bool:
    return abs(float(a) - float(b)) < tol


def pick_simply_supported_positions(
    rng: random.Random,
    stations: list[float],
) -> tuple[float, float]:
    """מיקומי pin@A / roller@B (xa < xb) בתרגיל סמכים.

    לכל סמך בנפרד:
      - A: 50% בקצה השמאלי (x=0), אחרת בנקודה פנימית
      - B: 50% בקצה הימני (x=L), אחרת בנקודה פנימית מימין ל־A
    נשמר מרווח מינימלי בין הסמכים כדי שלא יצטופפו בקצה אחד.
    """
    pts = sorted(float(x) for x in stations)
    if len(pts) < 3:
        raise ValueError("need at least 3 stations (0, interior, L)")
    left_end = pts[0]
    L = pts[-1]
    interior = pts[1:-1]
    if not interior:
        raise ValueError("need at least one interior station")

    min_span = max(float(SEG_MIN), 0.35 * float(L))

    def _try_once() -> tuple[float, float] | None:
        a_at_left = rng.random() < SUPPORT_AT_END_PROB
        b_at_right = rng.random() < SUPPORT_AT_END_PROB

        if a_at_left and b_at_right:
            return float(left_end), float(L)

        if a_at_left and not b_at_right:
            cand_b = [x for x in interior if (x - left_end) >= min_span - 1e-9]
            if not cand_b:
                return None
            return float(left_end), float(rng.choice(cand_b))

        if (not a_at_left) and b_at_right:
            cand_a = [x for x in interior if (L - x) >= min_span - 1e-9]
            if not cand_a:
                return None
            return float(rng.choice(cand_a)), float(L)

        pairs = [
            (a, b)
            for a in interior
            for b in interior
            if (b - a) >= min_span - 1e-9
        ]
        if not pairs:
            return None
        xa, xb = rng.choice(pairs)
        return float(xa), float(xb)

    for _ in range(120):
        got = _try_once()
        if got is not None:
            return got

    return float(left_end), float(L)


def random_udl_weights(rng: random.Random, n: int) -> list[float]:
    """n משקלי מפורס שלמים ב־[UDL_W_MIN, UDL_W_MAX], כולם שונים."""
    if n < 1:
        return []
    pool = list(range(UDL_W_MIN, UDL_W_MAX + 1))
    if n > len(pool):
        raise ValueError(f"cannot pick {n} distinct UDL weights from {UDL_W_MIN}..{UDL_W_MAX}")
    return [float(w) for w in rng.sample(pool, n)]


def random_udl_span_length(rng: random.Random, beam_L: float) -> float:
    """אורך מפורס ב־[1, L]: הסיכוי הגבוה ביותר ב־L/2, ויורד כשמתרחקים."""
    L = float(beam_L)
    if L <= UDL_SPAN_MIN + 1e-12:
        return round(max(L, UDL_SPAN_MIN), 1)
    step = float(UDL_SPAN_STEP)
    i0 = int(round(UDL_SPAN_MIN / step))
    i1 = int(math.floor(L / step + 1e-9))
    candidates = [round(i * step, 1) for i in range(i0, i1 + 1)]
    L_r = round(L, 1)
    if not any(abs(c - L_r) < 1e-9 for c in candidates):
        candidates.append(L_r)
    candidates = [c for c in candidates if UDL_SPAN_MIN - 1e-9 <= c <= L + 1e-9]
    if not candidates:
        return L_r
    peak = 0.5 * L
    weights = [peak - abs(c - peak) + 1.0 for c in candidates]
    return float(rng.choices(candidates, weights=weights, k=1)[0])


def udl_spans_overlap(
    a1: float,
    a2: float,
    b1: float,
    b2: float,
    *,
    tol: float = 1e-9,
) -> bool:
    """True אם שני מרווחי מפורס חופפים בפנים (מגע בקצה בלבד מותר)."""
    return float(a1) < float(b2) - tol and float(b1) < float(a2) - tol


def _udl_endpoint_ok(
    x: float,
    stations: list[float] | None,
    *,
    min_gap: float = SEG_MIN,
    tol: float = 1e-6,
) -> bool:
    """קצה מפורס חייב לחפוף נקודה קיימת או להיות לפחות min_gap ממנה."""
    if not stations:
        return True
    for s in stations:
        d = abs(float(x) - float(s))
        if d <= tol:
            return True
        if d < float(min_gap) - tol:
            return False
    return True


def place_udl_span(
    rng: random.Random,
    beam_L: float,
    length: float,
    *,
    stations: list[float] | None = None,
    min_gap: float = SEG_MIN,
) -> tuple[float, float] | None:
    """ממקם מפורס באורך length על הקורה — מחזיר (x1, x2) או None.

    אם נתונות stations — הקצוות לא יוצרים מרווח קטן מ־min_gap מול נקודות קיימות.
    """
    L = float(beam_L)
    ell = min(max(float(length), float(UDL_SPAN_MIN)), L)
    ell = round(ell, 1)
    max_start = round(L - ell, 1)
    if max_start <= 1e-9:
        return 0.0, round(L, 1)

    step = float(UDL_SPAN_STEP)
    starts: set[float] = set()
    n = int(math.floor(max_start / step + 1e-9))
    for i in range(n + 1):
        starts.add(round(i * step, 1))
    if stations:
        for s in stations:
            sr = round(float(s), 1)
            if -1e-9 <= sr <= max_start + 1e-9:
                starts.add(sr)

    valid: list[tuple[float, float]] = []
    for x1 in sorted(starts):
        x2 = round(x1 + ell, 1)
        if x2 > L + 1e-9:
            continue
        if not _udl_endpoint_ok(x1, stations, min_gap=min_gap):
            continue
        if not _udl_endpoint_ok(x2, stations, min_gap=min_gap):
            continue
        valid.append((float(x1), float(x2)))

    if valid:
        return rng.choice(valid)
    return None


def random_force_magnitude(rng: random.Random) -> float:
    """משקל עומס אנכי/צירי/אלכסוני: 75% שלם ב־[2,16]; 25% עשרוני אחד ב־[2,16]."""
    return random_clean_measure(
        rng,
        lo=FORCE_MAG_MIN,
        hi=FORCE_MAG_MAX,
        integer_prob=FORCE_MAG_INTEGER_PROB,
    )


def random_inclined_angle_deg(rng: random.Random) -> float:
    """זווית אלכסונית: 70% עשרות ב־[10,80]; 30% עשרוני אחד ב־(30,70)."""
    if rng.random() < INCLINED_ANGLE_TENS_PROB:
        return float(rng.choice((10, 20, 30, 40, 50, 60, 70, 80)))
    # עשרוני אחד בין 30 ל־70 (לא מספר שלם)
    tenths = [t for t in range(301, 701) if t % 10 != 0]
    return rng.choice(tenths) / 10.0


def pick_total_loads(rng: random.Random) -> int:
    """60% → 4 עומסים; 40% → 5 עומסים."""
    return LOAD_COUNT_FOUR if rng.random() < FOUR_LOADS_PROB else LOAD_COUNT_FIVE


def _pick_other_kinds(
    rng: random.Random,
    n_other: int,
) -> list[NonDistributedKind]:
    pool: list[NonDistributedKind] = list(NON_DISTRIBUTED_KINDS)
    rng.shuffle(pool)
    if n_other <= len(pool):
        return pool[:n_other]
    # יותר מ־3 שאינם מפורסים — כל הסוגים + כפילויות אקראיות
    extras = [
        rng.choice(NON_DISTRIBUTED_KINDS) for _ in range(n_other - len(pool))
    ]
    return pool + extras


def pick_load_composition(
    rng: random.Random,
) -> tuple[int, int, list[NonDistributedKind]]:
    """מחזיר (סה״כ עומסים, מספר מפורסים, סוגי העומסים שאינם מפורסים).

    - סה״כ: 60% → 4 עומסים; 40% → 5 עומסים
    - מפורסים: 60% → 2; 40% → 1
    - השאר מתוך {מרוכז, אלכסוני, מומנט, צירי}
    """
    n_total = pick_total_loads(rng)
    n_dist = 2 if rng.random() < TWO_DISTRIBUTED_PROB else 1
    n_other = n_total - n_dist
    return n_total, n_dist, _pick_other_kinds(rng, n_other)


def shuffled_load_kinds(
    rng: random.Random,
    n_dist: int,
    other_kinds: list[NonDistributedKind],
) -> list[str]:
    """רשימת סוגי עומסים בסדר אקראי משמאל לימין על הקורה."""
    kinds: list[str] = ["distributed"] * n_dist + list(other_kinds)
    rng.shuffle(kinds)
    return kinds


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
    n_total, n_dist, other_kinds = pick_load_composition(rng)
    return {
        "L": L,
        "spacings": segs,
        "n_loads": n_total,
        "n_distributed": n_dist,
        "other_load_kinds": other_kinds,
        "load_kinds": shuffled_load_kinds(rng, n_dist, other_kinds),
    }
