# -*- coding: utf-8 -*-
"""בונה מסך נוכחי — מפנה לתיקיית השלב המתאימה."""

from __future__ import annotations

import personal_assistant.decomposition as decomposition
import personal_assistant.reactions as reactions


def build_current_screen_hebrew(
    progress: reactions.ReactionProgress | decomposition.DecompositionProgress,
    *,
    phase: reactions.ReactionPhase | None = None,
    prefix: str = "",
) -> str:
    """הודעת כניסה למצב הנוכחי — decomposition או reactions."""
    if isinstance(progress, decomposition.DecompositionProgress):
        return decomposition.build_decomposition_screen_hebrew(
            progress, prefix=prefix
        )
    return reactions.build_reactions_screen_hebrew(
        progress, phase=phase, prefix=prefix
    )
