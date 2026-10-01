# -*- coding: utf-8 -*-
"""רינדור פתרון המחברת."""
from __future__ import annotations

from notebook_solution.decompose import draw_decomposition
from notebook_solution.diagrams import (
    draw_diagrams,
    draw_normal_diagram,
    draw_normal_shear_diagrams,
)
from notebook_solution.equilibrium import draw_equilibrium
from notebook_solution.page import _CELL_PX, image_to_png, new_page
from notebook_solution.problem import parse_problem
from notebook_solution.sketch import draw_exercise
from notebook_solution.stamp import paste_brand_stamp


def render_exercise_crop_png_bytes(extracted: dict) -> bytes | None:
    """שרטוט תרגיל חתוך במראה המחברת, ללא שאר הדף."""
    problem = parse_problem(extracted if isinstance(extracted, dict) else {})
    if problem is None:
        return None
    image = new_page()
    draw_exercise(image, problem)
    image = image.crop((0, 0, 74 * _CELL_PX, 34 * _CELL_PX))
    return image_to_png(image)


def render_exercise_png_bytes(extracted: dict) -> bytes | None:
    """דף מחברת עם שרטוט התרגיל בלבד בפינה השמאלית העליונה."""
    problem = parse_problem(extracted if isinstance(extracted, dict) else {})
    if problem is None:
        return None
    image = new_page()
    draw_exercise(image, problem)
    return image_to_png(image)


def render_exercise_decomposition_png_bytes(extracted: dict) -> bytes | None:
    """דף מחברת עם שרטוט התרגיל משמאל ופירוק עומסים מימין."""
    problem = parse_problem(extracted if isinstance(extracted, dict) else {})
    if problem is None:
        return None
    image = new_page()
    draw_exercise(image, problem)
    draw_decomposition(image, problem)
    return image_to_png(image)


def render_exercise_equations_png_bytes(extracted: dict) -> bytes | None:
    """דף מחברת עם תרגיל, פירוק עומסים ומשוואות מוצבות ללא פתרון."""
    problem = parse_problem(extracted if isinstance(extracted, dict) else {})
    if problem is None:
        return None
    image = new_page()
    draw_exercise(image, problem)
    draw_decomposition(image, problem)
    draw_equilibrium(image, extracted, {}, show_solution=False)
    return image_to_png(image)


def render_exercise_reactions_png_bytes(extracted: dict) -> bytes | None:
    """דף מחברת עם פתרון המשוואות ומציאת הריאקציות, ללא דיאגרמות."""
    problem = parse_problem(extracted if isinstance(extracted, dict) else {})
    if problem is None:
        return None
    image = new_page()
    draw_exercise(image, problem)
    draw_decomposition(image, problem)
    draw_equilibrium(image, extracted, {})
    return image_to_png(image)


def render_exercise_normal_diagram_png_bytes(extracted: dict) -> bytes | None:
    """דף מחברת עם הפתרון עד הריאקציות ודיאגרמת N(x) בלבד."""
    problem = parse_problem(extracted if isinstance(extracted, dict) else {})
    if problem is None:
        return None
    image = new_page()
    draw_exercise(image, problem)
    draw_decomposition(image, problem)
    draw_equilibrium(image, extracted, {})
    draw_normal_diagram(image, extracted, problem)
    return image_to_png(image)


def render_exercise_shear_diagram_png_bytes(extracted: dict) -> bytes | None:
    """דף מחברת עם הפתרון עד הריאקציות ודיאגרמות N(x) ו־Q(x)."""
    problem = parse_problem(extracted if isinstance(extracted, dict) else {})
    if problem is None:
        return None
    image = new_page()
    draw_exercise(image, problem)
    draw_decomposition(image, problem)
    draw_equilibrium(image, extracted, {})
    draw_normal_shear_diagrams(image, extracted, problem)
    return image_to_png(image)


def render_exercise_moment_diagram_png_bytes(extracted: dict) -> bytes | None:
    """דף מחברת עם הפתרון ודיאגרמות N(x), Q(x) ו־M(x), ללא פירוט נוסף."""
    problem = parse_problem(extracted if isinstance(extracted, dict) else {})
    if problem is None:
        return None
    image = new_page()
    draw_exercise(image, problem)
    draw_decomposition(image, problem)
    eq_bottom = draw_equilibrium(image, extracted, {})
    draw_diagrams(
        image,
        extracted,
        {},
        problem,
        eq_bottom,
        include_details=False,
    )
    return image_to_png(image)


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
