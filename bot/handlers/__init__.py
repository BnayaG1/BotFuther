# -*- coding: utf-8 -*-
"""Telegram handlers package — implementation lives in ``router``.

Patches on ``bot.handlers.X`` are mirrored onto ``router`` so tests keep working.
"""
from __future__ import annotations

import sys
from types import ModuleType

from bot.handlers import router as _router

# Export the full router surface (including _private names used by tests).
for _name, _value in vars(_router).items():
    if not _name.startswith("__"):
        globals()[_name] = _value


class _HandlersPackage(ModuleType):
    """Mirror attribute writes (unittest.mock patches) onto router."""

    def __setattr__(self, name: str, value: object) -> None:
        ModuleType.__setattr__(self, name, value)
        if not name.startswith("__"):
            setattr(_router, name, value)


sys.modules[__name__].__class__ = _HandlersPackage
