# -*- coding: utf-8 -*-
"""בדיקות שכבת פתרון — מנוע + השוואת ריאקציות."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from bot.solution_check import (
    compare_student_reactions,
    format_student_feedback,
    parse_student_reactions,
    solve_extracted_beam,
)

VALIDATOR = Path(__file__).resolve().parent.parent / "validator_images"


class TestParseStudentReactions(unittest.TestCase):
    def test_parses_mixed_formats(self) -> None:
        text = "R_Ay = 2.91, R_By: 4.09"
        got = parse_student_reactions(text)
        self.assertAlmostEqual(got["R_Ay"], 2.91)
        self.assertAlmostEqual(got["R_By"], 4.09)

    def test_empty_text(self) -> None:
        self.assertEqual(parse_student_reactions(""), {})


class TestSolveExpectedFixtures(unittest.TestCase):
    def test_exercise_01_reactions(self) -> None:
        exp = json.loads(
            (VALIDATOR / "exercise_01.expected.json").read_text(encoding="utf-8")
        )
        solved = solve_extracted_beam(
            {"exercise_type": "beam", "beam": exp["beam"]}
        )
        r = solved["result"]["reactions_ton"]
        self.assertAlmostEqual(float(r["R_Ay"]), 2.91, places=1)
        self.assertAlmostEqual(float(r["R_By"]), 4.09, places=1)
        self.assertAlmostEqual(float(r["R_Ax"]), 0.0, places=2)

    def test_exercise_l12_has_axial_reaction(self) -> None:
        exp = json.loads(
            (VALIDATOR / "exercise_l12_complex.expected.json").read_text(
                encoding="utf-8"
            )
        )
        solved = solve_extracted_beam(
            {"exercise_type": "beam", "beam": exp["beam"]}
        )
        r = solved["result"]["reactions_ton"]
        self.assertGreater(abs(float(r["R_Ax"])), 30.0)


class TestCompareStudentReactions(unittest.TestCase):
    def test_match_within_tol(self) -> None:
        computed = {"R_Ay": 2.91, "R_By": 4.09}
        student = {"R_Ay": 2.9, "R_By": 4.1}
        self.assertEqual(compare_student_reactions(computed, student), [])

    def test_mismatch_reported(self) -> None:
        computed = {"R_Ay": 2.91, "R_By": 4.09}
        student = {"R_Ay": 3.5}
        issues = compare_student_reactions(computed, student)
        self.assertTrue(any("R_Ay" in i for i in issues))

    def test_feedback_hebrew(self) -> None:
        solved = {
            "tool_name": "beam_solve_simply_supported",
            "result": {
                "reactions_ton": {"R_Ax": 0, "R_Ay": 2.91, "R_Bx": 0, "R_By": 4.09}
            },
        }
        ok = format_student_feedback(solved, {"R_Ay": 2.91, "R_By": 4.09})
        self.assertIn("נכון", ok)


if __name__ == "__main__":
    unittest.main()
