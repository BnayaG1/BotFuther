# -*- coding: utf-8 -*-
"""בחירת מצב פתרון (מחברת / מדריך) — לפני כניסה לזרימת הפתרון."""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from bot.solution_session import SolveMode, set_pending_solve_mode


def solve_mode_picker_intro_hebrew() -> str:
    return "מעולה, בוא/י נבחר איך לפתור את התרגיל."


def build_solve_mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("פתרון מחברת", callback_data="menu:mode:notebook")],
            [InlineKeyboardButton("מדריך לפתרון", callback_data="menu:mode:assistant")],
            [InlineKeyboardButton("חזרה", callback_data="formula:back")],
        ]
    )


def build_bank_solve_mode_keyboard() -> InlineKeyboardMarkup:
    """בחירת מצב פתרון לתרגיל שנשלף מהמאגר (בלי כפתור חזרה — אין טיוטה קודמת)."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("פתרון מחברת", callback_data="menu:bank:notebook")],
            [InlineKeyboardButton("מדריך לפתרון", callback_data="menu:bank:assistant")],
        ]
    )


def solve_mode_prompt_hebrew(mode: SolveMode) -> str:
    if mode == SolveMode.ASSISTANT:
        return (
            "מעולה, שלח/י תמונה של התרגיל.\n"
            "נעבור עליו יחד שלב-אחר-שלב."
        )
    if mode == SolveMode.ADD_TO_BANK:
        return (
            "שלח/י תמונה של התרגיל שתרצה להוסיף למאגר.\n"
            "אזהה את הנתונים ותוכל/י לתקן אותם לפני השמירה."
        )
    return (
        "מעולה — שלח/י עכשיו תמונה של התרגיל.\n"
        "אחזיר פתרון מחברת מלא."
    )


def parse_menu_mode_action(action: str) -> SolveMode | None:
    if not action.startswith("mode:"):
        return None
    mode_key = action.split(":", 1)[-1]
    mapping = {
        "notebook": SolveMode.NOTEBOOK,
        "assistant": SolveMode.ASSISTANT,
    }
    return mapping.get(mode_key)


def parse_bank_mode_action(action: str) -> SolveMode | None:
    """מזהה בחירת מצב פתרון לתרגיל מהמאגר (menu:bank:notebook / menu:bank:assistant)."""
    if not action.startswith("bank:"):
        return None
    mode_key = action.split(":", 1)[-1]
    mapping = {
        "notebook": SolveMode.NOTEBOOK,
        "assistant": SolveMode.ASSISTANT,
    }
    return mapping.get(mode_key)


def select_solve_mode(chat_id: int, mode: SolveMode) -> str:
    set_pending_solve_mode(chat_id, mode)
    return solve_mode_prompt_hebrew(mode)
