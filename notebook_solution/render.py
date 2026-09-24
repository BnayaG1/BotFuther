# -*- coding: utf-8 -*-
"""רינדור פתרון המחברת."""
from __future__ import annotations

from notebook_solution.decompose import draw_decomposition
from notebook_solution.diagrams import draw_diagrams
from notebook_solution.equilibrium import draw_equilibrium
from notebook_solution.page import image_to_png, new_page
from notebook_solution.problem import parse_problem
from notebook_solution.sketch import draw_exercise
from notebook_solution.stamp import paste_brand_stamp


def render_png_bytes(extracted: dict, solved: dict) -> bytes | None:
    """PNG של דף המחברת. שרטוט התרגיל בפינה השמאלית העליונה כשיש נתונים."""
    image = new_page()
    problem = parse_problem(extracted if isinstance(extracted, dict) else {})
    if problem is not None:
        extracted_data = extracted if isinstance(extracted, dict) else {}
        solved_data = solved if isinstance(solved, dict) else {}
        draw_exercise(image, problem)
        draw_decomposition(image, problem)
        eq_bottom = draw_equilibrium(image, extracted_data, solved_data)
        draw_diagrams(image, extracted_data, solved_data, problem, eq_bottom)
        paste_brand_stamp(image)
    return image_to_png(image)
