# -*- coding: utf-8 -*-
"""Core calculation layer — beam statics (no AI, no Telegram)."""

from core import center_of_gravity
from core.distributed_moments import (
    UDL_SPLIT_ABOUT_PIVOT_HE,
    DistributedMomentSegment,
    distributed_crosses_pivot,
    distributed_moment_segments_about,
)
from core.statics_calculator import (
    compute_reactions,
    solve_cantilever_beam,
)

__all__ = [
    "center_of_gravity",
    "UDL_SPLIT_ABOUT_PIVOT_HE",
    "DistributedMomentSegment",
    "distributed_crosses_pivot",
    "distributed_moment_segments_about",
    "compute_reactions",
    "solve_cantilever_beam",
]
