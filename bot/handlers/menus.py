# -*- coding: utf-8 -*-
"""Menus / callback handlers — see ``router``."""
from bot.handlers.router import (
    on_assistant_callback,
    on_buy_callback,
    on_formula_callback,
    on_intro_callback,
    on_menu_callback,
)

__all__ = [
    "on_buy_callback",
    "on_menu_callback",
    "on_assistant_callback",
    "on_intro_callback",
    "on_formula_callback",
]
