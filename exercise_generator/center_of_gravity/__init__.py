# -*- coding: utf-8 -*-
"""מחולל תרגילי מרכז כובד — 3 רכיבים (פרופילים / צורות בסיסיות) כ־PNG."""

from exercise_generator.center_of_gravity.generator import CogExercise, Component, generate_cog_exercise
from exercise_generator.center_of_gravity.render import render_cog_exercise_png
from exercise_generator.center_of_gravity.solution_page import render_cog_solution_png
from exercise_generator.center_of_gravity.solve import CogSolution, solve_cog_exercise

__all__ = [
    "CogExercise",
    "CogSolution",
    "Component",
    "generate_cog_exercise",
    "render_cog_exercise_png",
    "render_cog_solution_png",
    "solve_cog_exercise",
]
