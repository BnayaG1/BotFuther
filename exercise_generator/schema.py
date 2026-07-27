# -*- coding: utf-8 -*-
"""מודל נתונים פנימי + המרה ל־extracted JSON של המאגר."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

SupportType = Literal["pin", "roller", "fixed"]
LoadType = Literal["point", "distributed", "inclined", "moment"]
ShapeType = Literal["rectangular", "triangular"]


@dataclass
class Support:
    label: str
    type: SupportType
    x: float


@dataclass
class LabeledPoint:
    label: str
    x: float


@dataclass
class PointLoad:
    type: Literal["point"] = "point"
    x: float = 0.0
    Fy: float = 0.0  # טון, חיובי = מטה בשרטוט
    Fx: float = 0.0


@dataclass
class DistributedLoad:
    type: Literal["distributed"] = "distributed"
    x1: float = 0.0
    x2: float = 0.0
    w: float = 0.0  # טון/מ', חיובי = מטה
    shape: ShapeType = "rectangular"


@dataclass
class InclinedLoad:
    type: Literal["inclined"] = "inclined"
    x: float = 0.0
    magnitude_ton: float = 0.0
    angle_deg: float = 30.0
    incl_dir: Literal["dr", "dl"] = "dr"  # down-right / down-left


@dataclass
class MomentLoad:
    type: Literal["moment"] = "moment"
    x: float = 0.0
    M: float = 0.0  # טון·מ'; חיובי = בכיוון השעון בשרטוט


LoadItem = PointLoad | DistributedLoad | InclinedLoad | MomentLoad


@dataclass
class DimensionSegment:
    """מקטע מידה בשורה העליונה."""

    x1: float
    x2: float
    label: str | None = None  # אם None — מציגים את האורך


@dataclass
class DimensionRow:
    segments: list[DimensionSegment] = field(default_factory=list)


@dataclass
class Exercise:
    """תרגיל פנימי — לפני ייצוא ל־extracted."""

    L: float
    support_mode: Literal["simply_supported", "cantilever"]
    supports: list[Support]
    loads: list[LoadItem] = field(default_factory=list)
    labeled_points: list[LabeledPoint] = field(default_factory=list)
    dim_row_top: DimensionRow = field(default_factory=DimensionRow)
    dim_row_bottom: DimensionRow = field(default_factory=DimensionRow)
    family: str = ""
    seed: int | None = None

    def to_extracted(self) -> dict[str, Any]:
        loads_out: list[dict[str, Any]] = []
        distributed_loads: list[dict[str, Any]] = []
        for ld in self.loads:
            if isinstance(ld, DistributedLoad):
                loads_out.append(
                    {
                        "type": "distributed",
                        "x1": ld.x1,
                        "x2": ld.x2,
                        "w": ld.w,
                        "shape": ld.shape,
                    }
                )
                distributed_loads.append(
                    {
                        "start_x": ld.x1,
                        "end_x": ld.x2,
                        "magnitude": ld.w,
                        "shape": ld.shape,
                    }
                )
            elif isinstance(ld, PointLoad):
                entry: dict[str, Any] = {"type": "point", "x": ld.x, "Fy": ld.Fy}
                if abs(ld.Fx) > 1e-12:
                    entry["Fx"] = ld.Fx
                loads_out.append(entry)
            elif isinstance(ld, InclinedLoad):
                loads_out.append(
                    {
                        "type": "inclined",
                        "x": ld.x,
                        "magnitude_ton": ld.magnitude_ton,
                        "angle_deg": ld.angle_deg,
                        "incl_dir": ld.incl_dir,
                    }
                )
            elif isinstance(ld, MomentLoad):
                loads_out.append({"type": "moment", "x": ld.x, "M": ld.M})

        beam: dict[str, Any] = {
            "L": self.L,
            "support_mode": self.support_mode,
            "supports": [asdict(s) for s in self.supports],
            "loads": loads_out,
        }
        if distributed_loads:
            beam["distributed_loads"] = distributed_loads
        if self.labeled_points:
            beam["labeled_points"] = [asdict(p) for p in self.labeled_points]

        return {
            "exercise_type": "beam",
            "beam": beam,
            "meta": {
                "family": self.family,
                "seed": self.seed,
                # נתונים סינתטיים מדויקים — לא להריץ עליהם finalize/vision normalize
                "source": "exercise_generator",
                "skip_vision_normalize": True,
            },
        }
