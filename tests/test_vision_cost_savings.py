# -*- coding: utf-8 -*-
"""בדיקות: חיסכון בעלות Vision — קריאה אחת + טיוטה מוקדמת."""
from __future__ import annotations

import importlib
from unittest.mock import MagicMock, patch

import bot.config as config
from bot.vision import extract_exercise_with_retries


def _sample_beam_partial() -> dict:
    return {
        "beam": {
            "L": 12.0,
            "supports": [
                {"label": "A", "type": "pin", "x": 0.0},
                {"label": "B", "type": "roller", "x": 12.0},
            ],
            "loads": [{"type": "point", "x": 6.0, "Fy": 2.0}],
        }
    }


def test_config_cost_saving_defaults(monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    for key in (
        "VISION_FAST_FALLBACK_STAGED",
        "VISION_QUALITY_RETRY",
        "VISION_LOADS_REFINE",
        "VISION_OVERLOAD_FALLBACK",
    ):
        monkeypatch.delenv(key, raising=False)
    importlib.reload(config)
    assert config.MAX_RETRIES_PER_MODEL == 1
    assert config.VISION_FAST_FALLBACK_STAGED is False
    assert config.VISION_QUALITY_RETRY is False
    assert config.VISION_LOADS_REFINE is False
    assert config.VISION_OVERLOAD_FALLBACK is False


def test_clean_first_call_returns_monolithic_fast_single_extract():
    client = MagicMock()
    parsed = _sample_beam_partial()

    with patch("bot.vision._try_monolithic_extract", return_value=(parsed, [])) as mock_extract:
        with patch("bot.vision.VISION_FAST_MODE", True):
            with patch("bot.vision.DRAFT_APPROVAL_MODE", True):
                result = extract_exercise_with_retries(
                    client,
                    "gemini-2.5-flash-lite",
                    b"fake-image",
                    "image/jpeg",
                )

    mock_extract.assert_called_once()
    assert result.get("extraction_pipeline") == "monolithic_fast"
    quality = result.get("_extraction_quality") or {}
    assert quality.get("partial") is False


def test_early_draft_return_skips_expensive_fallbacks():
    client = MagicMock()
    parsed = _sample_beam_partial()
    issues = ["לא זוהו עומסים אלכסוניים"]

    with patch(
        "bot.vision._try_monolithic_extract",
        return_value=(parsed, issues),
    ) as mock_extract:
        with patch("bot.vision.extract_beam_loads_staged_refine") as mock_refine:
            with patch("bot.vision.extract_beam_exercise_staged") as mock_staged:
                with patch("bot.vision.VISION_FAST_MODE", True):
                    with patch("bot.vision.DRAFT_APPROVAL_MODE", True):
                        with patch("bot.vision.VISION_QUALITY_RETRY", False):
                            with patch("bot.vision.VISION_LOADS_REFINE", False):
                                with patch("bot.vision.VISION_FAST_FALLBACK_STAGED", False):
                                    result = extract_exercise_with_retries(
                                        client,
                                        "gemini-2.5-flash-lite",
                                        b"fake-image",
                                        "image/jpeg",
                                    )

    mock_extract.assert_called_once()
    mock_refine.assert_not_called()
    mock_staged.assert_not_called()
    assert result.get("extraction_pipeline") == "monolithic_fast_partial"
    quality = result.get("_extraction_quality") or {}
    assert quality.get("partial") is True
    assert issues[0] in (quality.get("validation_issues") or [])
