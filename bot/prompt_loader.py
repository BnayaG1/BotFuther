# -*- coding: utf-8 -*-
"""
טעינה והרכבה של פרומפטי חילוץ תמונה — bot/prompts/vision/.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

log = logging.getLogger("beam_telegram_bot")

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def load_prompt_text(relative_path: str) -> str:
    path = PROMPTS_DIR / relative_path
    if not path.is_file():
        raise FileNotFoundError(f"Prompt file missing: {path}")
    return path.read_text(encoding="utf-8").strip()


@lru_cache(maxsize=64)
def _cached_prompt(relative_path: str) -> str:
    return load_prompt_text(relative_path)


def get_statics_iron_rules_summary() -> str:
    return (
        "חוקי ברזל: פירוק וקטורים ראשון (Fx=F·cosα, Fy=F·sinα); "
        "N←קפיצה למעלה, →למטה; M↻למעלה, ↺למטה; "
        "עומס מרוכז→Q קבוע/M לינארי; UDL→Q לינארי/M פרבולי; "
        "שטחים: משולש b·h/2, טרפז h(b1+b2)/2, M_max=Q²/(2q)."
    )


# --- Vision (English) ---

STEP_1_KEY = "STEP_1_BEAM_GEOMETRY"
STEP_2_KEY = "STEP_2_SUPPORTS"
STEP_3_KEY = "STEP_3_POINT_LOADS"
STEP_4_KEY = "STEP_4_DISTRIBUTED_LOADS"
STEP_5_KEY = "STEP_5_VALIDATION_CHECK"

EXTRACTION_STEP_KEYS: tuple[str, ...] = (
    STEP_1_KEY,
    STEP_2_KEY,
    STEP_3_KEY,
    STEP_4_KEY,
    STEP_5_KEY,
)


def get_vision_extraction_pipeline_intro() -> str:
    return _cached_prompt("vision/00_extraction_pipeline.txt")


def get_vision_linear_scan_protocol() -> str:
    return _cached_prompt("vision/01_linear_scan.txt")


def get_vision_engineering_scan_protocol() -> str:
    template = _cached_prompt("vision/02_engineering_scan.txt")
    return template.format(linear_scan_protocol=get_vision_linear_scan_protocol())


def get_vision_handwriting_hint() -> str:
    template = _cached_prompt("vision/03_handwriting.txt")
    return template.format(
        scan_protocol=get_vision_engineering_scan_protocol(),
        load_position_projection=get_vision_load_position_projection(),
        distributed_loads_protocol=get_vision_distributed_loads_protocol(),
    )


def get_vision_stage_geometry_prompt() -> str:
    return _cached_prompt("vision/stages/01_geometry.txt")


def get_vision_stage_supports_prompt() -> str:
    return _cached_prompt("vision/stages/02_supports.txt")


def get_vision_stage_point_loads_prompt() -> str:
    return _cached_prompt("vision/stages/03_point_loads.txt")


def get_vision_stage_distributed_loads_prompt() -> str:
    return _cached_prompt("vision/stages/04_distributed_loads.txt")


def get_vision_stage_validation_prompt() -> str:
    return _cached_prompt("vision/stages/05_validation_check.txt")


def get_vision_stage_points_prompt() -> str:
    """מיושן — שלב 3 נקודות הוחלף ב-STEP_3_POINT_LOADS."""
    return get_vision_stage_point_loads_prompt()


def get_vision_stage_loads_prompt() -> str:
    """מיושן — עומסים מפוצלים לשלב 3+4."""
    return get_vision_stage_point_loads_prompt()


def format_vision_stage_prompt(template: str, *, context: dict | None = None, extra: str = "") -> str:
    """ממלא placeholders משותפים לכל שלבי החילוץ."""
    ctx_json = json.dumps(context or {}, ensure_ascii=False, indent=2)
    extra_block = f"\nAdditional:\n{extra}" if extra.strip() else ""
    return template.format(
        pipeline_intro=get_vision_extraction_pipeline_intro(),
        handwriting_hint=get_vision_handwriting_hint(),
        distributed_loads_protocol=get_vision_distributed_loads_protocol(),
        context=ctx_json,
        extra=extra_block,
    )


def get_vision_extract_prompt() -> str:
    return _cached_prompt("vision/04_extract_monolithic.txt")


def get_vision_focus_mode_en() -> str:
    return _cached_prompt("vision/05_focus_mode_en.txt")


def get_vision_load_position_projection() -> str:
    return _cached_prompt("vision/06_load_position_projection.txt")


def get_vision_distributed_loads_protocol() -> str:
    return _cached_prompt("vision/07_distributed_loads_he.txt")


def build_vision_extra_instruction(*, learned_hint: str = "") -> str:
    """הנחיות לכל תמונה — focus + מיקום עומסים + עומסים מפורסים + לקחים."""
    parts = [
        get_vision_focus_mode_en(),
        get_vision_load_position_projection(),
        get_vision_distributed_loads_protocol(),
    ]
    if learned_hint:
        parts.append(learned_hint)
    return "\n\n".join(parts)


def invalidate_prompt_cache() -> None:
    _cached_prompt.cache_clear()
