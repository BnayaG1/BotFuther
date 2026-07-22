# -*- coding: utf-8 -*-
"""Compatibility shim — mode picker is ``bot.solve_mode``; teaching flow is ``personal_assistant``.

Prefer importing from those modules directly.
"""
from bot.solve_mode import (  # noqa: F401
    build_bank_solve_mode_keyboard,
    build_solve_mode_keyboard,
    parse_bank_mode_action,
    parse_menu_mode_action,
    select_solve_mode,
    solve_mode_picker_intro_hebrew,
    solve_mode_prompt_hebrew,
)
