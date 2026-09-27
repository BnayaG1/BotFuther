# -*- coding: utf-8 -*-
"""פתרון תרגיל מרכז כובד — שטח, זרועות, מרכז כובד גלובלי ומומנטי אינרציה.

הזרועות נמדדות מראשית הצירים של התרגיל: ציר Y בציר הסימטריה (או בקצה
השמאלי בתרגיל אסימטרי), ציר X בתחתית החתך. כל הערכים מוחזרים בסנטימטרים.

לכל רכיב מחושבים Ix, Iy סביב הצירים המרכזיים שלו עצמו, והמעבר לצירים
המרכזיים של החתך כולו נעשה בשטיינר: Ixx = Σ(Ix + A·dy²), Iyy = Σ(Iy + A·dx²),
כאשר dx, dy הם המרחקים בין מרכז הכובד של הרכיב למרכז הכובד הגלובלי.
"""
from __future__ import annotations

from dataclasses import dataclass

from exercise_generator.center_of_gravity.generator import CogExercise, Component
from exercise_generator.center_of_gravity.render import _outline

_MM_TO_CM = 0.1


@dataclass
class SolutionRow:
    """שורה בטבלת הפתרון — רכיב אחד."""

    index: int
    label: str
    area: float
    cx: float
    cy: float
    ix: float
    iy: float
    dx: float = 0.0
    dy: float = 0.0

    @property
    def a_cx(self) -> float:
        return self.area * self.cx

    @property
    def a_cy(self) -> float:
        return self.area * self.cy

    @property
    def steiner_x(self) -> float:
        """תרומת הרכיב ל-Ixx: Ix + A·dy²."""
        return self.ix + self.area * self.dy * self.dy

    @property
    def steiner_y(self) -> float:
        """תרומת הרכיב ל-Iyy: Iy + A·dx²."""
        return self.iy + self.area * self.dx * self.dx


@dataclass
class CogSolution:
    rows: list[SolutionRow]
    sum_area: float
    sum_a_cx: float
    sum_a_cy: float
    cx: float
    cy: float
    i_xx: float
    i_yy: float
    origin_x: float
    origin_y: float
    symmetric: bool


def _polygon_properties(
    points: list[tuple[float, float]]
) -> tuple[float, float, float, float, float]:
    """שטח, מרכז כובד ומומנטי אינרציה מרכזיים של מצולע."""
    twice_area = 0.0
    sum_x = 0.0
    sum_y = 0.0
    sum_ix = 0.0
    sum_iy = 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]):
        cross = x0 * y1 - x1 * y0
        twice_area += cross
        sum_x += (x0 + x1) * cross
        sum_y += (y0 + y1) * cross
        sum_ix += (y0 * y0 + y0 * y1 + y1 * y1) * cross
        sum_iy += (x0 * x0 + x0 * x1 + x1 * x1) * cross
    if abs(twice_area) < 1e-12:
        return 0.0, 0.0, 0.0, 0.0, 0.0
    area = abs(twice_area) / 2.0
    cx = sum_x / (3.0 * twice_area)
    cy = sum_y / (3.0 * twice_area)
    sign = 1.0 if twice_area > 0 else -1.0
    ix = sign * sum_ix / 12.0 - area * cy * cy
    iy = sign * sum_iy / 12.0 - area * cx * cx
    return area, cx, cy, ix, iy


def component_properties(comp: Component) -> tuple[float, float, float, float, float]:
    """שטח, מרכז כובד מקומי ומומנטי אינרציה מרכזיים של רכיב."""
    if comp.kind == "rhs":
        t = float(comp.params["t"])
        inner_w = max(comp.width - 2.0 * t, 0.0)
        inner_h = max(comp.height - 2.0 * t, 0.0)
        area = comp.width * comp.height - inner_w * inner_h
        ix = (comp.width * comp.height ** 3 - inner_w * inner_h ** 3) / 12.0
        iy = (comp.height * comp.width ** 3 - inner_h * inner_w ** 3) / 12.0
        return area, comp.width / 2.0, comp.height / 2.0, ix, iy
    return _polygon_properties(_outline(comp))


def component_area_centroid(comp: Component) -> tuple[float, float, float]:
    """שטח ומרכז כובד מקומי של רכיב (ביחס לפינה השמאלית-תחתונה שלו)."""
    area, cx_local, cy_local, _ix, _iy = component_properties(comp)
    return area, cx_local, cy_local


def component_global_centroid(comp: Component) -> tuple[float, float, float]:
    """שטח ומרכז כובד במערכת הצירים של התרגיל."""
    area, cx_local, cy_local = component_area_centroid(comp)
    cx = comp.width - cx_local if comp.mirror else cx_local
    return area, comp.x + cx, comp.y + cy_local


def _row_label(comp: Component) -> str:
    label = comp.label
    return label[2:].strip() if label.startswith("2 ") else label


def solve_cog_exercise(exercise: CogExercise) -> CogSolution:
    comps = exercise.components
    scale = _MM_TO_CM if exercise.unit == "mm" else 1.0
    min_x = min(c.x for c in comps)
    min_y = min(c.y for c in comps)
    origin_x = 0.0 if exercise.symmetric else min_x

    rows: list[SolutionRow] = []
    for index, comp in enumerate(comps, start=1):
        area, cx_local, cy_local, ix, iy = component_properties(comp)
        gx = comp.x + (comp.width - cx_local if comp.mirror else cx_local)
        gy = comp.y + cy_local
        rows.append(
            SolutionRow(
                index=index,
                label=_row_label(comp),
                area=area * scale * scale,
                cx=(gx - origin_x) * scale,
                cy=(gy - min_y) * scale,
                ix=ix * scale ** 4,
                iy=iy * scale ** 4,
            )
        )

    sum_area = sum(row.area for row in rows)
    sum_a_cx = sum(row.a_cx for row in rows)
    sum_a_cy = sum(row.a_cy for row in rows)
    if sum_area <= 0:
        raise ValueError("סכום השטחים אינו חיובי — לא ניתן לחשב מרכז כובד")
    cx = sum_a_cx / sum_area
    cy = sum_a_cy / sum_area
    for row in rows:
        row.dx = abs(row.cx - cx)
        row.dy = abs(row.cy - cy)
    return CogSolution(
        rows=rows,
        sum_area=sum_area,
        sum_a_cx=sum_a_cx,
        sum_a_cy=sum_a_cy,
        cx=cx,
        cy=cy,
        i_xx=sum(row.steiner_x for row in rows),
        i_yy=sum(row.steiner_y for row in rows),
        origin_x=origin_x,
        origin_y=min_y,
        symmetric=exercise.symmetric,
    )
