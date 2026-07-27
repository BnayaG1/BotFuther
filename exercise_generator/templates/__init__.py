# -*- coding: utf-8 -*-
"""תבניות נתונים לתרגילים.

המראה נקבע ב־``render/`` (נעול). כאן רק בניית נתונים.
``LOCKED_FAMILY`` היא התבנית הפעילה בברירת מחדל.
"""

from exercise_generator.templates.registry import (
    LOCKED_FAMILY,
    build_family,
    list_families,
    pick_family,
)

__all__ = ["LOCKED_FAMILY", "build_family", "list_families", "pick_family"]
