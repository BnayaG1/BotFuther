# -*- coding: utf-8 -*-
"""סגנון שרטוט בחינה — שחור-לבן.

מסגרת התמונה קבועה לכל תרגיל. הקורה תמיד באורך ויזואלי ``FRAME_L_MAX``
(מיקומים במטרים מנורמלים ב־canvas), כך ש־6 מ' ו־12 מ' תופסים אותו שטח בתמונה.
המעטפת האנכית לפי גובה מקסימלי של כל סוגי העומסים.
"""
from __future__ import annotations

import math

BEAM_HEIGHT = 0.35 * (2 / 3)  # הוקטן בשליש (~0.233)
SUPPORT_SIZE = 0.55 * 0.85  # הוקטן ב־15%
STATION_DOT_RADIUS = (0.055 / 2) * 0.86  # נקודה שחורה על הקורה בכל תחנה
UDL_BASE_HEIGHT = 0.9
POINT_ARROW_LEN = 1.35
MOMENT_RADIUS = 0.55
LINE_WIDTH = 1.4
LOAD_LABEL_FONTSIZE = 8 * 1.5  # מספר + t/tm על העומסים
# ראש חץ שפיצי (שווה-שוקיים, זווית חדה בקצה) — יחס אורך/רוחב כפול מברירת המחדל
ARROW_HEAD_LENGTH = 0.8
ARROW_HEAD_WIDTH = 0.2
ARROW_STYLE_FILLED = (
    f"-|>,head_length={ARROW_HEAD_LENGTH},head_width={ARROW_HEAD_WIDTH}"
)
ARROW_STYLE_LINE = (
    f"->,head_length={ARROW_HEAD_LENGTH},head_width={ARROW_HEAD_WIDTH}"
)
# מיקום אנכי של ציר הקורה
BEAM_Y = 1.35
# מרווח מתחת לקורה/סמכים עד שורות המידות (קרובות לקורה)
DIM_OFFSET_1 = -1.75
DIM_OFFSET_2 = -2.55
LABEL_OFFSET_Y = 0.55

# אורך קורה מקסימלי במסגרת (תואם randomize.L_MAX)
FRAME_L_MAX = 12.0
# שוליים אופקיים: חץ אלכסוני בזווית תצוגה מינימלית (20°) + מרווח קטן שלא ייחתך
_INCLINED_LEN = POINT_ARROW_LEN * 1.15
_INCLINED_REACH = _INCLINED_LEN * math.cos(math.radians(20.0))
X_MARGIN = round(_INCLINED_REACH + 0.28, 2)  # ~1.74
X_LIM = (-X_MARGIN, FRAME_L_MAX + X_MARGIN)

# מעטפת אנכית — מקסימום מעל (כל סוגי העומסים) ומקסימום מתחת (מידות)
_BEAM_TOP = BEAM_Y + BEAM_HEIGHT / 2
_POINT_TOP = _BEAM_TOP + 0.05 + POINT_ARROW_LEN
_INCLINED_TOP = _BEAM_TOP + 0.05 + _INCLINED_LEN + 0.32  # מרווח לתווית משקל מעל הזנב
_UDL_TOP = _BEAM_TOP + 0.08 + UDL_BASE_HEIGHT * 1.22 + 0.15 + 0.35
_LABEL_TOP = _BEAM_TOP + LABEL_OFFSET_Y + 0.35
_Y_TOP = max(_POINT_TOP, _INCLINED_TOP, _UDL_TOP, _LABEL_TOP) + 0.12 + 0.18  # טיפה יותר מרווח מלמעלה
_Y_BOTTOM = BEAM_Y + DIM_OFFSET_2 - 0.28 - 0.18 - 0.08 - 0.22  # טיפה יותר מרווח מלמטה
Y_LIM = (_Y_BOTTOM, _Y_TOP)

_DATA_W = X_LIM[1] - X_LIM[0]
_DATA_H = Y_LIM[1] - Y_LIM[0]
DPI = 160
FIG_WIDTH_IN = 12.0
FIGSIZE = (FIG_WIDTH_IN, FIG_WIDTH_IN * _DATA_H / _DATA_W)

# חותמת מותג — פינה ימנית-עליונה
STAMP_TEXT = "המהנדס הדיגיטלי"
STAMP_INK_RGB = (110, 110, 110)  # שחור רך (לא שחור מלא)
STAMP_WIDTH_FRAC = 0.095  # ~9.5% מרוחב התמונה
STAMP_PAD_FRAC = 0.01  # מרווח מהשוליים
STAMP_SPIDER_RELATIVE = "assets/digital_engineer_spider.png"
