# -*- coding: utf-8 -*-
"""ניווט כללי בין שלבי העוזר האישי — יורחב כשיתווספו שלבים נוספים."""

from __future__ import annotations

from enum import Enum

from personal_assistant.decomposition import (
    DecompositionProgress,
    DecompositionState,
)
from personal_assistant.reactions import ReactionProgress, enter_reactions


class AssistantStepId(str, Enum):
    """מזהי שלבים גדולים בעוזר האישי."""

    DECOMPOSITION = "decomposition"
    REACTIONS = "reactions"


def next_step_after(step: AssistantStepId) -> AssistantStepId | None:
    """מעבר לשלב הבא אחרי סיום השלב הנוכחי."""
    order = (
        AssistantStepId.DECOMPOSITION,
        AssistantStepId.REACTIONS,
    )
    try:
        idx = order.index(step)
    except ValueError:
        return None
    if idx + 1 >= len(order):
        return None
    return order[idx + 1]


def enter_reactions_after_decomposition(
    progress: DecompositionProgress,
) -> ReactionProgress | None:
    """מעבר שלד אחרי DONE של פרוק → כניסה לשלב הריאקציות."""
    if progress.state != DecompositionState.DONE:
        return None
    return enter_reactions(
        progress.extracted,
        decomposed_load_indices=list(progress.load_indices),
    )
