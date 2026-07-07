# -*- coding: utf-8 -*-
"""שרטוט סכימת קורה מנתונים מאומתים — לשלב אישור (human-in-the-loop)."""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Arc, Circle, FancyArrowPatch, Polygon, Rectangle

from core.beam_validator import BeamExercise, BeamModel, LoadType, SupportType


def _format_value(value: float | None, suffix: str = "") -> str:
    if value is None:
        return ""
    if abs(value - round(value)) < 1e-6:
        text = f"{int(round(value))}"
    else:
        text = f"{value:g}"
    return f"{text}{suffix}"


def _draw_beam_line(ax, L: float, y: float = 0.0) -> None:
    margin = max(L * 0.08, 0.5)
    ax.plot([-margin, L + margin], [y, y], color="black", linewidth=3, solid_capstyle="round")
    ax.text(-margin * 0.6, y, "A", ha="center", va="center", fontsize=11, fontweight="bold")
    ax.text(L + margin * 0.6, y, "B", ha="center", va="center", fontsize=11, fontweight="bold")


def _draw_pin_support(ax, x: float, y: float, size: float) -> None:
    tri = Polygon(
        [(x, y), (x - size, y - size * 1.4), (x + size, y - size * 1.4)],
        closed=True,
        facecolor="white",
        edgecolor="black",
        linewidth=1.5,
    )
    ax.add_patch(tri)
    ax.plot([x - size * 1.1, x + size * 1.1], [y - size * 1.45, y - size * 1.45], color="black", lw=1.2)


def _draw_roller_support(ax, x: float, y: float, size: float) -> None:
    _draw_pin_support(ax, x, y, size)
    ax.add_patch(
        Circle((x, y - size * 1.85), radius=size * 0.35, fill=False, edgecolor="black", linewidth=1.2)
    )


def _draw_fixed_support(ax, x: float, y: float, size: float, side: str = "left") -> None:
    wall_x = x - size * 0.15 if side == "left" else x + size * 0.15
    ax.plot([wall_x, wall_x], [y + size, y - size * 1.6], color="black", linewidth=2)
    for i in range(4):
        yy = y + size - i * size * 0.55
        dx = size * 0.45 if side == "left" else -size * 0.45
        ax.plot([wall_x, wall_x + dx], [yy, yy - size * 0.25], color="black", linewidth=1)
    if side == "left":
        tri = Polygon(
            [(x, y), (x + size, y + size * 0.55), (x + size, y - size * 0.55)],
            closed=True,
            facecolor="white",
            edgecolor="black",
            linewidth=1.5,
        )
    else:
        tri = Polygon(
            [(x, y), (x - size, y + size * 0.55), (x - size, y - size * 0.55)],
            closed=True,
            facecolor="white",
            edgecolor="black",
            linewidth=1.5,
        )
    ax.add_patch(tri)


def _draw_support(ax, support, L: float, y: float, size: float) -> None:
    x = support.x
    label = support.label
    st = support.type

    if st == SupportType.PIN:
        _draw_pin_support(ax, x, y, size)
    elif st == SupportType.ROLLER:
        _draw_roller_support(ax, x, y, size)
    else:
        side = "left" if x <= L * 0.2 else "right"
        _draw_fixed_support(ax, x, y, size, side=side)

    ax.text(x, y - size * 2.6, label, ha="center", va="top", fontsize=10, fontweight="bold")


def _draw_point_load(ax, x: float, y: float, fy: float, arrow_scale: float) -> None:
    mag = abs(fy) if fy else 1.0
    length = min(max(mag * arrow_scale, 0.4), 2.5)
    direction = -1 if fy >= 0 else 1  # positive Fy = downward in statics
    y_start = y + length * 0.35 * direction * -1 + (length if direction < 0 else 0)
    y_end = y + (length if direction < 0 else -length)

    arrow = FancyArrowPatch(
        (x, y_start),
        (x, y_end),
        arrowstyle="-|>",
        mutation_scale=14,
        linewidth=1.8,
        color="#c0392b",
    )
    ax.add_patch(arrow)
    ax.text(
        x + 0.15,
        (y_start + y_end) / 2,
        _format_value(fy, " t") if fy is not None else "?",
        color="#c0392b",
        fontsize=10,
        fontweight="bold",
        va="center",
    )


def _draw_distributed_load(ax, start_x: float, end_x: float, y: float, q: float, arrow_scale: float) -> None:
    mag = abs(q) if q else 1.0
    height = min(max(mag * arrow_scale * 0.35, 0.25), 1.2)
    direction = -1 if (q or 0) >= 0 else 1
    top_y = y + height if direction < 0 else y - height

    ax.add_patch(
        Rectangle(
            (start_x, min(y, top_y)),
            end_x - start_x,
            abs(top_y - y),
            facecolor="#fadbd8",
            edgecolor="#c0392b",
            linewidth=1.2,
            alpha=0.35,
        )
    )

    n_arrows = max(3, int((end_x - start_x) / max((end_x - start_x) * 0.25, 0.5)))
    xs = [start_x + (end_x - start_x) * i / (n_arrows - 1) for i in range(n_arrows)]
    for x in xs:
        arrow = FancyArrowPatch(
            (x, top_y),
            (x, y),
            arrowstyle="-|>",
            mutation_scale=10,
            linewidth=1.2,
            color="#c0392b",
        )
        ax.add_patch(arrow)

    mid_x = (start_x + end_x) / 2
    ax.text(
        mid_x,
        top_y + (0.15 if direction < 0 else -0.35),
        _format_value(q, " t/m"),
        ha="center",
        color="#c0392b",
        fontsize=10,
        fontweight="bold",
    )


def _draw_moment(ax, x: float, y: float, moment: float, size: float) -> None:
    mag = abs(moment) if moment else 1.0
    radius = min(max(mag * size * 0.08, 0.35), 0.9)
    theta1, theta2 = (20, 300) if (moment or 0) >= 0 else (240, 520)
    arc = Arc((x, y + radius * 0.9), 2 * radius, 2 * radius, angle=0, theta1=theta1, theta2=theta2, color="#8e44ad", linewidth=2)
    ax.add_patch(arc)
    ax.text(
        x,
        y + radius * 2.2,
        _format_value(moment, " t·m"),
        ha="center",
        color="#8e44ad",
        fontsize=10,
        fontweight="bold",
    )


def _draw_inclined_load(ax, x: float, y: float, fx: float, fy: float, arrow_scale: float) -> None:
    fy = fy or 0.0
    mag = math.hypot(fx, fy) or 1.0
    length = min(max(mag * arrow_scale * 0.25, 0.5), 2.0)
    dx = (fx / mag) * length
    dy = -(fy / mag) * length  # screen y is inverted vs statics
    arrow = FancyArrowPatch(
        (x - dx, y - dy),
        (x, y),
        arrowstyle="-|>",
        mutation_scale=14,
        linewidth=1.8,
        color="#d35400",
    )
    ax.add_patch(arrow)
    ax.text(x - dx * 0.5, y - dy * 0.5 - 0.2, _format_value(mag, " t"), color="#d35400", fontsize=10, fontweight="bold")


def _draw_reaction_vertical(
    ax, x: float, y: float, force: float, label: str, *, size: float, arrow_scale: float
) -> None:
    if abs(force) < 1e-6:
        return
    length = min(max(abs(force) * arrow_scale, 0.35), 2.2)
    color = "#1a5276"
    if force >= 0:
        y_start, y_end = y - size * 2.8 - length, y - size * 2.2
    else:
        y_start, y_end = y - size * 2.2, y - size * 2.8 + length
    arrow = FancyArrowPatch(
        (x, y_start),
        (x, y_end),
        arrowstyle="-|>",
        mutation_scale=12,
        linewidth=1.8,
        color=color,
    )
    ax.add_patch(arrow)
    ax.text(
        x + 0.2,
        (y_start + y_end) / 2,
        f"{label}={_format_value(force, ' t')}",
        color=color,
        fontsize=9,
        fontweight="bold",
        va="center",
    )


def _draw_reaction_horizontal(
    ax, x: float, y: float, force: float, label: str, *, size: float, arrow_scale: float
) -> None:
    if abs(force) < 1e-6:
        return
    length = min(max(abs(force) * arrow_scale, 0.35), 2.0)
    color = "#1a5276"
    base_y = y - size * 3.4
    if force >= 0:
        x_start, x_end = x - length, x
    else:
        x_start, x_end = x, x + length
    arrow = FancyArrowPatch(
        (x_start, base_y),
        (x_end, base_y),
        arrowstyle="-|>",
        mutation_scale=12,
        linewidth=1.8,
        color=color,
    )
    ax.add_patch(arrow)
    ax.text(
        (x_start + x_end) / 2,
        base_y - 0.25,
        f"{label}={_format_value(force, ' t')}",
        color=color,
        fontsize=9,
        fontweight="bold",
        ha="center",
    )


def _draw_reactions_on_supports(
    ax,
    supports,
    y: float,
    reactions: dict[str, float],
    *,
    size: float,
    arrow_scale: float,
) -> None:
    """מצייר ריאקציות לפי תוויות סמכים (A, B, ...)."""
    labels = [str(s.label or "").strip().upper() for s in supports]
    mapping: list[tuple[str, str, str]] = []
    if "A" in labels:
        mapping.append(("A", "R_Ay", "R_Ax"))
    if "B" in labels:
        mapping.append(("B", "R_By", "R_Bx"))
    if not mapping and supports:
        keys_y = [("R_Ay", "R_Ax"), ("R_By", "R_Bx")]
        for idx, support in enumerate(supports[:2]):
            vy, vx = keys_y[idx] if idx < len(keys_y) else ("", "")
            if vy:
                mapping.append((str(support.label or "?").upper(), vy, vx))

    for label, vy_key, vx_key in mapping:
        sup = next((s for s in supports if str(s.label or "").strip().upper() == label), None)
        if sup is None:
            continue
        x = sup.x
        _draw_reaction_vertical(
            ax, x, y, float(reactions.get(vy_key, 0)), vy_key, size=size, arrow_scale=arrow_scale
        )
        _draw_reaction_horizontal(
            ax, x, y, float(reactions.get(vx_key, 0)), vx_key, size=size, arrow_scale=arrow_scale
        )


def render_beam_preview(
    data: BeamExercise | BeamModel,
    output_path: str | Path = "beam_preview.png",
    *,
    dpi: int = 120,
    reactions: dict[str, float] | None = None,
    title: str | None = None,
) -> Path:
    """
    מצייר סכימת קורה ושומר PNG.

    Args:
        data: BeamExercise או BeamModel מה-Validator.
        output_path: נתיב לקובץ PNG (ברירת מחדל: beam_preview.png).

    Returns:
        Path לקובץ שנשמר.
    """
    beam = data.beam if isinstance(data, BeamExercise) else data
    L = beam.L
    y = 0.0
    size = max(L * 0.035, 0.25)
    arrow_scale = max(L * 0.06, 0.15)

    fig, ax = plt.subplots(figsize=(max(8, L * 0.55), 4))
    ax.set_aspect("equal", adjustable="box")
    ax.axis("off")

    _draw_beam_line(ax, L, y=y)

    for support in beam.supports:
        _draw_support(ax, support, L, y, size)

    for load in beam.loads:
        if load.type == LoadType.POINT:
            _draw_point_load(ax, load.x or 0.0, y, load.Fy or 0.0, arrow_scale)
        elif load.type == LoadType.DISTRIBUTED:
            _draw_distributed_load(
                ax,
                load.start_x or 0.0,
                load.end_x or L,
                y,
                load.q or 0.0,
                arrow_scale,
            )
        elif load.type == LoadType.MOMENT:
            _draw_moment(ax, load.x or 0.0, y, load.M or 0.0, size)
        elif load.type == LoadType.INCLINED:
            _draw_inclined_load(ax, load.x or 0.0, y, load.Fx or 0.0, load.Fy or 0.0, arrow_scale)

    if reactions:
        _draw_reactions_on_supports(
            ax, beam.supports, y, reactions, size=size, arrow_scale=arrow_scale
        )

    ax.set_xlim(-L * 0.12, L * 1.12)
    ax.set_ylim(-size * 5.5, max(L * 0.15, 2.0))
    title_text = title if title else f"Beam preview — L = {L:g} m"
    ax.set_title(title_text, fontsize=13, fontweight="bold", pad=12)

    out = Path(output_path)
    fig.tight_layout()
    fig.savefig(out, dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


def _mock_exercise() -> BeamExercise:
    return BeamExercise(
        exercise_type="beam",
        description_he="קורה לדוגמה — בדיקת visualizer",
        beam=BeamModel(
            L=12.0,
            supports=[
                {"label": "A", "type": "pin", "x": 0},
                {"label": "B", "type": "roller", "x": 12},
            ],
            labeled_points=[
                {"label": "A", "x": 0},
                {"label": "C", "x": 4},
                {"label": "D", "x": 8},
                {"label": "B", "x": 12},
            ],
            loads=[
                {"type": "point", "x": 4, "Fy": 3, "label_at": "C"},
                {"type": "distributed", "start_x": 6, "end_x": 10, "q": 2},
                {"type": "moment", "x": 8, "M": 5, "label_at": "D"},
            ],
        ),
    )


if __name__ == "__main__":
    from core.beam_validator import validate_beam_extraction

    raw = _mock_exercise().model_dump()
    result = validate_beam_extraction(raw)
    if not result.ok:
        raise SystemExit(f"Mock data invalid: {result.errors}")

    path = render_beam_preview(result.data, "beam_preview.png")
    print(f"Saved preview to: {path.resolve()}")
