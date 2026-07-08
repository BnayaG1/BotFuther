# -*- coding: utf-8 -*-
"""Unit tests for vision regression comparator (no Gemini API)."""
from __future__ import annotations

import os
import unittest

from bot.vision_regression import compare_beam_to_expected, discover_cases, run_all_cases


class CompareBeamTests(unittest.TestCase):
    def test_L_and_supports_pass(self):
        expected = {
            "beam": {
                "L": 12.0,
                "supports": [
                    {"label": "A", "type": "pin", "x": 0},
                    {"label": "B", "type": "roller", "x": 12},
                ],
                "loads": [],
            }
        }
        got = {
            "beam": {
                "L": 12.1,
                "supports": [
                    {"label": "A", "type": "pin", "x": 0},
                    {"label": "B", "type": "roller", "x": 11.9},
                ],
                "loads": [],
            }
        }
        self.assertEqual(compare_beam_to_expected(expected, got), [])

    def test_roller_wrong_x(self):
        expected = {
            "beam": {
                "L": 12.0,
                "supports": [{"label": "B", "type": "roller", "x": 12}],
                "loads": [],
            }
        }
        got = {
            "beam": {
                "L": 12.0,
                "supports": [{"label": "B", "type": "roller", "x": 11}],
                "loads": [],
            }
        }
        issues = compare_beam_to_expected(expected, got)
        self.assertTrue(any("support B x" in i for i in issues))

    def test_inclined_angle_and_dir(self):
        expected = {
            "beam": {
                "L": 12.0,
                "loads": [
                    {
                        "type": "inclined",
                        "x": 1,
                        "magnitude_ton": 5,
                        "angle_deg": 30,
                        "incl_dir": "dl",
                        "Fx": -4.33,
                        "Fy": 2.5,
                    }
                ],
            },
            "options": {"x_tol": 0.3, "value_tol": 0.5},
        }
        got = {
            "beam": {
                "L": 12.0,
                "loads": [
                    {
                        "type": "inclined",
                        "x": 1,
                        "angle_deg": 60,
                        "incl_dir": "dr",
                        "Fx": 2.5,
                        "Fy": 4.33,
                    }
                ],
            },
        }
        issues = compare_beam_to_expected(expected, got)
        self.assertTrue(any("angle_deg" in i or "incl_dir" in i for i in issues))


@unittest.skipUnless(
    os.getenv("VISION_REGRESSION_LIVE") == "1",
    "set VISION_REGRESSION_LIVE=1 to call Gemini",
)
class LiveRegressionTests(unittest.TestCase):
    def test_all_validator_cases(self):
        cases = discover_cases()
        if not cases:
            self.skipTest("no validator_images/*.expected.json cases")
        results = run_all_cases(cases, live=True)
        failed = [r for r in results if not r.passed and not r.skipped]
        self.assertFalse(
            failed,
            "\n".join(f"{r.stem}: " + "; ".join(r.issues) for r in failed),
        )


if __name__ == "__main__":
    unittest.main()
