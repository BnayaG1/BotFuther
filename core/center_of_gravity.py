# -*- coding: utf-8 -*-
"""מרכז כובד — שלד מינימלי (בנייה מחדש)."""

from __future__ import annotations

import math
import os
import random
from pathlib import Path
from typing import Any, List, MutableMapping

try:
    import streamlit as st
    import streamlit.components.v1 as components
except ImportError:
    st = None  # type: ignore[assignment,misc]
    components = None  # type: ignore[assignment,misc]

_CANVAS_LIMIT = 50.0
_SLIDER_MIN = -100.0
_SLIDER_MAX = 100.0
_COG_A4_PAGE_WIDTH = 794
_COG_A4_PAGE_MIN_HEIGHT = 1123

_CATALOG: dict[str, dict[str, Any]] = {
    "IPE": {
        "type": "i_section",
        "profile": "IPE",
        "b": 100.0,
        "h": 150.0,
        "tf": 10.0,
        "tw": 6.0,
    },
    "IPN": {
        "type": "i_section",
        "profile": "IPN",
        "b": 80.0,
        "h": 120.0,
        "tf": 8.0,
        "tw": 5.5,
    },
    "IPB": {
        "type": "i_section",
        "profile": "IPB",
        "b": 140.0,
        "h": 200.0,
        "tf": 14.0,
        "tw": 9.0,
    },
    "UPB": {
        "type": "c_section",
        "profile": "UPB",
        "b": 80.0,
        "h": 50.0,
        "tf": 8.0,
        "tw": 6.0,
    },
    "LPN שווה": {
        "type": "l_section",
        "profile": "LPN שווה",
        "b": 50.0,
        "b1": 50.0,
        "b2": 50.0,
        "t": 6.0,
        "equal": True,
    },
    "LPN שונה": {
        "type": "l_section",
        "profile": "LPN שונה",
        "b": 60.0,
        "b1": 60.0,
        "b2": 40.0,
        "t": 6.0,
        "equal": False,
    },
    "צינור עגול": {
        "type": "tube",
        "profile": "צינור עגול",
        "D": 60.0,
        "t": 4.0,
        "b": 60.0,
    },
    "RHS מלבני": {
        "type": "rhs",
        "profile": "RHS מלבני",
        "b": 80.0,
        "h": 50.0,
        "t": 5.0,
    },
}

_CATALOG_GROUPS: dict[str, list[str]] = {
    "חתכי I": ["IPE", "IPN", "IPB"],
    "חתכי U": ["UPB"],
    "זווית (L)": ["LPN שווה", "LPN שונה"],
    "חלולים": ["צינור עגול", "RHS מלבני"],
}

_CATALOG_PROFILE_KEYS = frozenset(_CATALOG.keys())

_SYMMETRIC_CATALOG_KEYS = [
    "IPE",
    "IPN",
    "IPB",
    "RHS מלבני",
    "צינור עגול",
]

_PRACTICE_CATALOG_KEYS = list(_CATALOG.keys())

_PRACTICE_SYMMETRIC_KEYS = [
    key for key in _SYMMETRIC_CATALOG_KEYS if key in _CATALOG
]

ShapeDict = MutableMapping[str, Any]


def _init_session() -> None:
    if "cog_shapes" not in st.session_state:
        st.session_state.cog_shapes = []
    if "focus_first_shape" not in st.session_state:
        st.session_state.focus_first_shape = False
    if "_cog_canvas_event_ts" not in st.session_state:
        st.session_state._cog_canvas_event_ts = None
    _purge_non_profile_shapes()


def _is_real_profile_shape(shape: ShapeDict) -> bool:
    profile = shape.get("profile")
    if not profile or str(profile) not in _CATALOG_PROFILE_KEYS:
        return False
    catalog_type = _CATALOG[str(profile)].get("type")
    return str(shape.get("type", "")) == str(catalog_type)


def _purge_non_profile_shapes() -> None:
    if "cog_shapes" not in st.session_state:
        return
    kept = [s for s in st.session_state.cog_shapes if _is_real_profile_shape(s)]
    if len(kept) != len(st.session_state.cog_shapes):
        st.session_state.cog_shapes = kept
        selected = st.session_state.get("cog_selected_shape_id")
        if selected is not None and not any(int(s["id"]) == int(selected) for s in kept):
            st.session_state.cog_selected_shape_id = None


def _trigger_first_shape_focus() -> None:
    if len(st.session_state.cog_shapes) == 1:
        st.session_state.focus_first_shape = True


def _next_shape_id() -> int:
    return len(st.session_state.cog_shapes) + 1


def _shape_layout_width(shape: ShapeDict) -> float:
    stype = shape.get("type")
    if stype == "tube":
        return float(shape["D"])
    if stype == "l_section":
        return float(shape.get("b1", shape.get("b", 50.0)))
    return float(shape.get("b", 50.0))


def get_next_spawn_coords() -> tuple[float, float]:
    if not st.session_state.cog_shapes:
        return 0.0, 0.0

    last_shape = st.session_state.cog_shapes[-1]
    next_x = float(last_shape["x"]) + _shape_layout_width(last_shape) + 5.0
    return next_x, 0.0


def _spec_layout_width(spec: dict[str, Any]) -> float:
    stype = spec.get("type")
    if stype == "tube":
        return float(spec["D"])
    if stype == "l_section":
        return float(spec.get("b1", spec.get("b", 50.0)))
    return float(spec.get("b", 50.0))


def _spec_layout_height(spec: dict[str, Any]) -> float:
    stype = spec.get("type")
    if stype == "tube":
        return float(spec["D"])
    if stype == "l_section":
        return float(spec.get("b2", spec.get("b", 50.0)))
    return float(spec.get("h", 50.0))


def _shape_outer_bbox(shape: ShapeDict) -> tuple[float, float, float, float]:
    verts = _solid_vertices(shape)
    if verts is not None:
        xs, ys = verts
        return min(xs), min(ys), max(xs), max(ys)
    b, h = _shape_snap_dimensions(shape)
    x = float(shape["x"])
    y = float(shape["y"])
    return x, y, x + b, y + h


def _group_bbox(shapes: List[ShapeDict]) -> tuple[float, float, float, float]:
    boxes = [_shape_outer_bbox(s) for s in shapes]
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def _group_is_vertically_symmetric(shapes: List[ShapeDict]) -> bool:
    """True when the assembly is mirror-symmetric about the vertical midline."""
    if len(shapes) < 2:
        return False
    min_x, _, max_x, _ = _group_bbox(shapes)
    mid_x = (min_x + max_x) / 2.0
    total_a = sum(float(s["A"]) for s in shapes)
    if total_a <= 0.0:
        return False
    moment = sum(float(s["A"]) * (float(s["xc"]) - mid_x) for s in shapes)
    span = max(max_x - min_x, 1.0)
    return abs(moment) < total_a * span * 0.02


def _anchor_group_to_origin(shapes: List[ShapeDict], *, center: bool) -> None:
    min_x, min_y, max_x, _ = _group_bbox(shapes)
    anchor_x = min_x + (max_x - min_x) / 2.0 if center else min_x
    dx = -anchor_x
    dy = -min_y
    for shape in shapes:
        shape["x"] = float(shape["x"]) + dx
        shape["y"] = float(shape["y"]) + dy
        _update_local_statics(shape)


def _stack_shape_specs(
    rng: random.Random,
    keys: list[str],
    *,
    centered: bool,
) -> list[dict[str, Any]]:
    placed: list[dict[str, Any]] = []
    y = 0.0
    for idx, key in enumerate(keys):
        spec = dict(_CATALOG[key])
        width = _spec_layout_width(spec)
        height = _spec_layout_height(spec)
        if centered:
            x = -width / 2.0
        elif idx == 0:
            x = 0.0
        else:
            x = rng.uniform(0.0, max(width * 0.45, 8.0))
        placed.append({**spec, "x": x, "y": y})
        y += height
    return placed


def _practice_symmetric_stack(rng: random.Random, count: int) -> list[dict[str, Any]]:
    key = rng.choice(_PRACTICE_SYMMETRIC_KEYS)
    return _stack_shape_specs(rng, [key] * count, centered=True)


def _practice_asymmetric_stack(rng: random.Random, count: int) -> list[dict[str, Any]]:
    keys = rng.sample(_PRACTICE_CATALOG_KEYS, count)
    return _stack_shape_specs(rng, keys, centered=False)


def _generate_practice_exercise() -> None:
    rng = random.Random()
    count = rng.choice([2, 3])
    symmetric_layout = rng.random() < 0.5

    if symmetric_layout:
        raw = _practice_symmetric_stack(rng, count)
    else:
        raw = _practice_asymmetric_stack(rng, count)

    shapes: list[ShapeDict] = []
    for idx, spec in enumerate(raw, start=1):
        shape: ShapeDict = {"id": idx, **spec}
        _update_local_statics(shape)
        shapes.append(shape)

    symmetric = _group_is_vertically_symmetric(shapes)
    _anchor_group_to_origin(shapes, center=symmetric)

    st.session_state.cog_shapes = shapes
    st.session_state.cog_selected_shape_id = None


def _append_catalog_shape(catalog_key: str) -> None:
    spec = dict(_CATALOG[catalog_key])
    next_x, next_y = get_next_spawn_coords()
    shape = {"id": _next_shape_id(), "x": next_x, "y": next_y, **spec}
    _update_local_statics(shape)
    st.session_state.cog_shapes.append(shape)
    _trigger_first_shape_focus()


def _delete_shape(shape_id: int) -> None:
    st.session_state.cog_shapes = [
        s for s in st.session_state.cog_shapes if s["id"] != shape_id
    ]
    if st.session_state.get("cog_selected_shape_id") == shape_id:
        st.session_state.cog_selected_shape_id = None


def _find_shape_index(shape_id: int) -> int | None:
    for idx, shape in enumerate(st.session_state.cog_shapes):
        if shape["id"] == shape_id:
            return idx
    return None


def _i_section_vertices(shape: ShapeDict) -> tuple[list[float], list[float]]:
    x = float(shape["x"])
    y = float(shape["y"])
    b = float(shape["b"])
    h = float(shape["h"])
    tf = float(shape["tf"])
    tw = float(shape["tw"])
    w_half = tw / 2.0
    x_mid = x + b / 2.0
    xs = [
        x,
        x,
        x_mid - w_half,
        x_mid - w_half,
        x,
        x,
        x + b,
        x + b,
        x_mid + w_half,
        x_mid + w_half,
        x + b,
        x + b,
    ]
    ys = [
        y,
        y + tf,
        y + tf,
        y + h - tf,
        y + h - tf,
        y + h,
        y + h,
        y + h - tf,
        y + h - tf,
        y + tf,
        y + tf,
        y,
    ]
    return xs, ys


def _c_section_vertices(shape: ShapeDict) -> tuple[list[float], list[float]]:
    x = float(shape["x"])
    y = float(shape["y"])
    b = float(shape["b"])
    h = float(shape["h"])
    tf = float(shape["tf"])
    tw = float(shape["tw"])
    xs = [x, x + b, x + b, x + b - tw, x + b - tw, x + tw, x + tw, x]
    ys = [y, y, y + h, y + h, y + tf, y + tf, y + h, y + h]
    return xs, ys


def _l_section_vertices(shape: ShapeDict) -> tuple[list[float], list[float]]:
    x = float(shape["x"])
    y = float(shape["y"])
    t = float(shape["t"])
    b1 = float(shape.get("b1", shape.get("b", 50.0)))
    b2 = float(shape.get("b2", shape.get("b", 50.0)))
    xs = [x, x + b1, x + b1, x + t, x + t, x, x]
    ys = [y, y, y + t, y + t, y + b2, y + b2, y]
    return xs, ys


def _solid_vertices(shape: ShapeDict) -> tuple[list[float], list[float]] | None:
    stype = shape.get("type")
    builders = {
        "i_section": _i_section_vertices,
        "c_section": _c_section_vertices,
        "l_section": _l_section_vertices,
    }
    builder = builders.get(str(stype))
    if builder is None:
        return None
    return builder(shape)


def _polygon_centroid(xs: list[float], ys: list[float]) -> tuple[float, float]:
    n = len(xs)
    if n < 3:
        return float(xs[0]), float(ys[0])
    area2 = 0.0
    cx = 0.0
    cy = 0.0
    for i in range(n):
        j = (i + 1) % n
        cross = xs[i] * ys[j] - xs[j] * ys[i]
        area2 += cross
        cx += (xs[i] + xs[j]) * cross
        cy += (ys[i] + ys[j]) * cross
    area2 *= 0.5
    if abs(area2) < 1e-12:
        return sum(xs) / n, sum(ys) / n
    cx /= 6.0 * area2
    cy /= 6.0 * area2
    return cx, cy


def _shape_profile_label(shape: ShapeDict) -> str:
    profile = shape.get("profile")
    if profile:
        return str(profile)
    return _shape_type_label(shape)


def _build_global_report_rows(shapes: List[ShapeDict]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for shape in shapes:
        _update_local_statics(shape)
        area = float(shape["A"])
        xi = float(shape["xc"])
        yi = float(shape["yc"])
        rows.append(
            {
                "ID": f"M{shape['id']}",
                "Profile": _shape_profile_label(shape),
                "Area (A)": area,
                "x_i": xi,
                "y_i": yi,
                "A*x_i": area * xi,
                "A*y_i": area * yi,
            }
        )
    return rows


def _compute_global_centroid(
    rows: list[dict[str, Any]],
) -> tuple[float | None, float | None, float, float, float]:
    if not rows:
        return None, None, 0.0, 0.0, 0.0
    sum_a = sum(float(r["Area (A)"]) for r in rows)
    sum_ax = sum(float(r["A*x_i"]) for r in rows)
    sum_ay = sum(float(r["A*y_i"]) for r in rows)
    if sum_a <= 0:
        return None, None, sum_a, sum_ax, sum_ay
    return sum_ax / sum_a, sum_ay / sum_a, sum_a, sum_ax, sum_ay


def _shape_type_label(shape: ShapeDict) -> str:
    profile = shape.get("profile")
    if profile:
        return str(profile)
    return {
        "i_section": "חתך I",
        "c_section": "חתך U",
        "l_section": "זווית L",
        "rhs": "RHS חלול",
        "tube": "צינור עגול",
    }.get(str(shape.get("type", "")), str(shape.get("type", "")))


def _shape_area(shape: ShapeDict) -> float:
    stype = shape.get("type")
    if stype == "rhs":
        b = float(shape["b"])
        h = float(shape["h"])
        t = float(shape["t"])
        return 2.0 * t * (b + h - 2.0 * t)
    if stype == "tube":
        d = float(shape["D"])
        t = float(shape["t"])
        ro = d / 2.0
        ri = max(ro - t, 0.0)
        return math.pi * (ro * ro - ri * ri)
    if stype == "l_section":
        b1 = float(shape.get("b1", shape["b"]))
        b2 = float(shape.get("b2", shape["b"]))
        t = float(shape["t"])
        return b1 * t + b2 * t - t * t
    if stype == "i_section":
        b = float(shape["b"])
        h = float(shape["h"])
        tf = float(shape["tf"])
        tw = float(shape["tw"])
        return 2.0 * b * tf + (h - 2.0 * tf) * tw
    if stype == "c_section":
        b = float(shape["b"])
        h = float(shape["h"])
        tf = float(shape["tf"])
        tw = float(shape["tw"])
        return b * tf + 2.0 * (h - tf) * tw
    return 0.0


def _compute_local_centroid(shape: ShapeDict) -> tuple[float, float]:
    stype = shape.get("type")
    x = float(shape["x"])
    y = float(shape["y"])

    if stype == "i_section":
        b = float(shape["b"])
        h = float(shape["h"])
        return x + b / 2.0, y + h / 2.0

    if stype == "rhs":
        return x + float(shape["b"]) / 2.0, y + float(shape["h"]) / 2.0

    if stype == "tube":
        d = float(shape["D"])
        ro = d / 2.0
        return x + ro, y + ro

    verts = _solid_vertices(shape)
    if verts is None:
        return x, y
    xs, ys = verts
    return _polygon_centroid(xs, ys)


def _update_local_statics(shape: ShapeDict) -> None:
    """מחשב ושומר A, xc, yc במילון הצורה לשימוש בטבלת מרכז כובד גלובלי."""
    shape["A"] = float(_shape_area(shape))
    xc, yc = _compute_local_centroid(shape)
    shape["xc"] = float(xc)
    shape["yc"] = float(yc)


def _sync_all_local_statics(shapes: List[ShapeDict]) -> None:
    for shape in shapes:
        _update_local_statics(shape)


_FRONTEND_ROOT = Path(__file__).resolve().parent / "frontend"
_FRONTEND_BUILD = _FRONTEND_ROOT / "build"
_LEGACY_COG_ROOT = Path(__file__).resolve().parent / "beam_canvas_component" / "cog"
_COG_DEV_URL = os.environ.get("COG_CANVAS_DEV_URL", "").strip()
_COG_BUILD_ID = "2026-06-07-v3"
_COMPONENTS: dict[str, Any] = {}


def _declare_path_component(name: str, component_dir: str) -> Any:
    """declare_component ללא cache קבוע — נטען מחדש עם index.html בכל הפעלה."""
    resolved = str(Path(component_dir).resolve())
    cache_key = f"{name}:{resolved}"
    if cache_key not in _COMPONENTS:
        _COMPONENTS[cache_key] = components.declare_component(name, path=resolved)
    return _COMPONENTS[cache_key]


def _cog_konva_component_from_path(build_dir: str):  # type: ignore[misc]
    return _declare_path_component("cog_konva_canvas", build_dir)


def _cog_konva_component_from_url(dev_url: str):  # type: ignore[misc]
    return components.declare_component("cog_konva_canvas", url=dev_url)


def _cog_legacy_component_from_path(legacy_dir: str):  # type: ignore[misc]
    return _declare_path_component("cog_shapes_canvas", legacy_dir)


def _resolve_cog_canvas_backend() -> tuple[str, Any | None]:
    if _COG_DEV_URL:
        return "konva_dev", _cog_konva_component_from_url(_COG_DEV_URL)
    if (_FRONTEND_BUILD / "index.html").is_file():
        return "konva_build", _cog_konva_component_from_path(
            str(_FRONTEND_BUILD.resolve())
        )
    if (_LEGACY_COG_ROOT / "index.html").is_file():
        return "legacy_html", _cog_legacy_component_from_path(
            str(_LEGACY_COG_ROOT.resolve())
        )
    return "missing", None


def _apply_canvas_shapes(raw_shapes: list[Any]) -> None:
    by_id = {int(s["id"]): s for s in raw_shapes if isinstance(s, dict) and "id" in s}
    updated: list[ShapeDict] = []
    for shape in st.session_state.cog_shapes:
        sid = int(shape["id"])
        incoming = by_id.get(sid)
        if incoming is None:
            updated.append(shape)
            continue
        merged = dict(shape)
        if "x" in incoming:
            merged["x"] = float(incoming["x"])
        if "y" in incoming:
            merged["y"] = float(incoming["y"])
        _update_local_statics(merged)
        updated.append(merged)
    st.session_state.cog_shapes = updated


def _process_canvas_result(result: Any) -> bool:
    """מעבד אירוע מהקנבס פעם אחת לפי ts. True = יש לבצע rerun."""
    if not isinstance(result, dict):
        return False
    ts = result.get("ts")
    if ts is None:
        return False
    if ts == st.session_state.get("_cog_canvas_event_ts"):
        return False

    st.session_state._cog_canvas_event_ts = ts

    if result.get("deleteAll"):
        st.session_state.cog_shapes = []
        st.session_state.cog_selected_shape_id = None
        return True

    delete_id = result.get("deleteShapeId")
    if delete_id is not None:
        _delete_shape(int(delete_id))
        return True

    if result.get("selectedId") is not None:
        new_sel = int(result["selectedId"])
        if new_sel != st.session_state.get("cog_selected_shape_id"):
            st.session_state.cog_selected_shape_id = new_sel
            return True
    elif "selectedId" in result and result.get("selectedId") is None:
        if st.session_state.get("cog_selected_shape_id") is not None:
            st.session_state.cog_selected_shape_id = None
            return True

    if result.get("moved") and isinstance(result.get("shapes"), list):
        _apply_canvas_shapes(result["shapes"])
        return True
    return False


def render_canvas() -> Any:
    """קנבס Konva (React) או גיבוי HTML — סנכרון דו-כיווני ל-Python."""
    backend, comp = _resolve_cog_canvas_backend()
    if comp is None:
        st.warning(
            "רכיב הקנבס לא זמין. התקן Node.js, ואז הרץ:\n\n"
            "`cd frontend` → `npm install` → `npm run build`\n\n"
            "לפיתוח: `npm start` + "
            "`$env:COG_CANVAS_DEV_URL=\"http://localhost:3000\"` לפני Streamlit."
        )
        return None

    if backend == "legacy_html" and not st.session_state.get("_cog_legacy_notice"):
        st.info(
            "קנבס גיבוי (HTML) פעיל. לגרירה חלקה ב-Konva: התקן Node.js מ-https://nodejs.org "
            "והרץ `npm install` ו-`npm run build` בתיקיית `frontend`."
        )
        st.session_state._cog_legacy_notice = True

    shapes_out = [dict(s) for s in st.session_state.cog_shapes]
    for shape in shapes_out:
        _update_local_statics(shape)

    if backend == "legacy_html":
        result = comp(
            shapes=shapes_out,
            selectedId=st.session_state.get("cog_selected_shape_id"),
            key="cog_canvas_board",
            default=None,
            height=610,
        )
    else:
        result = comp(
            shapes=shapes_out,
            selectedId=st.session_state.get("cog_selected_shape_id"),
            width=900,
            height=550,
            key="cog_konva_board",
            default=None,
        )

    if _process_canvas_result(result):
        st.rerun()

    return result


def _shape_snap_dimensions(shape: ShapeDict) -> tuple[float, float]:
    """ממדי תוחם חיצוני (b, h) לחישובי מגנוט פינות לראשית."""
    stype = shape.get("type")
    if stype == "tube":
        d = float(shape["D"])
        return d, d
    if stype == "l_section":
        return (
            float(shape.get("b1", shape.get("b", 50.0))),
            float(shape.get("b2", shape.get("b", 50.0))),
        )
    return float(shape.get("b", 50.0)), float(shape.get("h", 50.0))


def _snap_shape_corner_to_origin(shape: ShapeDict, corner: str) -> None:
    b, h = _shape_snap_dimensions(shape)
    offsets = {
        "bottom_left": (0.0, 0.0),
        "bottom_right": (-b, 0.0),
        "top_left": (0.0, -h),
        "top_right": (-b, -h),
    }
    if corner not in offsets:
        return
    nx, ny = offsets[corner]
    shape["x"] = float(nx)
    shape["y"] = float(ny)


def _render_origin_snap_buttons(shape: ShapeDict, idx: int) -> None:
    sid = int(shape["id"])
    st.write("#### מגנוט לראשית (0,0)")
    st.caption("יישור פינת התוחם החיצוני של הפרופיל לנקודת הראשית המוחלטת.")
    r1c1, r1c2 = st.columns(2)
    r2c1, r2c2 = st.columns(2)
    buttons = (
        ("bottom_left", "שמאל-תחתון", r1c1),
        ("bottom_right", "ימין-תחתון", r1c2),
        ("top_left", "שמאל-עליון", r2c1),
        ("top_right", "ימין-עליון", r2c2),
    )
    for corner, label, col in buttons:
        with col:
            if st.button(
                label,
                key=f"cog_snap_{corner}_{sid}",
                use_container_width=True,
            ):
                snapped = st.session_state.cog_shapes[idx]
                _snap_shape_corner_to_origin(snapped, corner)
                _update_local_statics(snapped)
                st.session_state.cog_shapes[idx] = snapped
                st.rerun()


def _render_xy_sliders(shape: ShapeDict, sid: int) -> None:
    shape["x"] = st.slider(
        "מיקום X (פינה שמאלית-תחתונה)",
        min_value=_SLIDER_MIN,
        max_value=_SLIDER_MAX,
        value=float(shape.get("x", 0.0)),
        step=1.0,
        key=f"cog_x_{sid}",
    )
    shape["y"] = st.slider(
        "מיקום Y (פינה שמאלית-תחתונה)",
        min_value=_SLIDER_MIN,
        max_value=_SLIDER_MAX,
        value=float(shape.get("y", 0.0)),
        step=1.0,
        key=f"cog_y_{sid}",
    )


def _render_flange_web_inputs(shape: ShapeDict, sid: int) -> None:
    r1, r2 = st.columns(2)
    with r1:
        shape["b"] = st.number_input(
            "רוחב (b)",
            min_value=1.0,
            value=float(shape.get("b", 50.0)),
            step=1.0,
            key=f"cog_b_{sid}",
        )
        shape["tf"] = st.number_input(
            "עובי כנף (tf)",
            min_value=1.0,
            value=float(shape.get("tf", 10.0)),
            step=1.0,
            key=f"cog_tf_{sid}",
        )
    with r2:
        shape["h"] = st.number_input(
            "גובה (h)",
            min_value=1.0,
            value=float(shape.get("h", 50.0)),
            step=1.0,
            key=f"cog_h_{sid}",
        )
        shape["tw"] = st.number_input(
            "עובי דפנית (tw)",
            min_value=1.0,
            value=float(shape.get("tw", 10.0)),
            step=1.0,
            key=f"cog_tw_{sid}",
        )


def _render_rhs_inputs(shape: ShapeDict, sid: int) -> None:
    r1, r2 = st.columns(2)
    with r1:
        shape["b"] = st.number_input(
            "רוחב (b)",
            min_value=1.0,
            value=float(shape.get("b", 50.0)),
            step=1.0,
            key=f"cog_b_{sid}",
        )
        shape["t"] = st.number_input(
            "עובי (t)",
            min_value=0.5,
            value=float(shape.get("t", 5.0)),
            step=0.5,
            key=f"cog_t_{sid}",
        )
    with r2:
        shape["h"] = st.number_input(
            "גובה (h)",
            min_value=1.0,
            value=float(shape.get("h", 50.0)),
            step=1.0,
            key=f"cog_h_{sid}",
        )


def _render_tube_inputs(shape: ShapeDict, sid: int) -> None:
    r1, r2 = st.columns(2)
    with r1:
        shape["D"] = st.number_input(
            "קוטר (D)",
            min_value=2.0,
            value=float(shape.get("D", 60.0)),
            step=1.0,
            key=f"cog_D_{sid}",
        )
    with r2:
        shape["t"] = st.number_input(
            "עובי (t)",
            min_value=0.5,
            value=float(shape.get("t", 4.0)),
            step=0.5,
            key=f"cog_t_{sid}",
        )
    shape["b"] = float(shape["D"])


def _render_l_section_inputs(shape: ShapeDict, sid: int) -> None:
    r1, r2 = st.columns(2)
    with r1:
        shape["b1"] = st.number_input(
            "שוק 1 (b1)",
            min_value=1.0,
            value=float(shape.get("b1", shape.get("b", 50.0))),
            step=1.0,
            key=f"cog_b1_{sid}",
        )
        shape["t"] = st.number_input(
            "עובי (t)",
            min_value=0.5,
            value=float(shape.get("t", 6.0)),
            step=0.5,
            key=f"cog_t_{sid}",
        )
    with r2:
        shape["b2"] = st.number_input(
            "שוק 2 (b2)",
            min_value=1.0,
            value=float(shape.get("b2", shape.get("b", 50.0))),
            step=1.0,
            key=f"cog_b2_{sid}",
        )
    shape["b"] = float(shape["b1"])


def _render_shape_dimension_fields(shape: ShapeDict) -> None:
    sid = int(shape["id"])
    stype = shape.get("type")
    if stype in ("i_section", "c_section"):
        _render_flange_web_inputs(shape, sid)
    elif stype == "rhs":
        _render_rhs_inputs(shape, sid)
    elif stype == "tube":
        _render_tube_inputs(shape, sid)
    elif stype == "l_section":
        _render_l_section_inputs(shape, sid)


def _round_dim(value: Any) -> int:
    return int(round(float(value)))


def _format_shape_identity_label(shape: ShapeDict) -> str:
    """תווית קצרה — סוג + מידות (כמו על הלוח)."""
    profile = str(shape.get("profile", "")).strip()
    stype = shape.get("type")
    if stype == "i_section":
        return f"{profile} {_round_dim(shape.get('h'))}"
    if stype == "c_section":
        return f"{profile} {_round_dim(shape.get('b'))}×{_round_dim(shape.get('h'))}"
    if stype == "l_section":
        b1 = _round_dim(shape.get("b1", shape.get("b")))
        b2 = _round_dim(shape.get("b2", shape.get("b")))
        prefix = "LPN" if profile.startswith("LPN") else (profile or "L")
        return f"{prefix} {b1}/{b2}"
    if stype == "rhs":
        return f"RHS {_round_dim(shape.get('b'))}/{_round_dim(shape.get('h'))}"
    if stype == "tube":
        return f"Ø{_round_dim(shape.get('D', shape.get('b')))}"
    return profile or str(stype)


def render_shape_details(canvas_result: Any) -> None:
    selected_id = st.session_state.get("cog_selected_shape_id")
    if selected_id is None:
        st.caption("לחץ על נקודת M בשרטוט.")
        return

    idx = _find_shape_index(int(selected_id))
    if idx is None:
        st.session_state.cog_selected_shape_id = None
        st.caption("לחץ על נקודת M בשרטוט.")
        return

    shape = st.session_state.cog_shapes[idx]
    sid = int(shape["id"])
    _update_local_statics(shape)
    st.session_state.cog_shapes[idx] = shape

    st.markdown(f"**{_format_shape_identity_label(shape)}**")
    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric("A", f"{shape['A']:.1f}", label_visibility="visible")
    with m2:
        st.metric("xᵢ", f"{shape['xc']:.1f}")
    with m3:
        st.metric("yᵢ", f"{shape['yc']:.1f}")
    st.caption(f"מיקום: ({float(shape['x']):.0f}, {float(shape['y']):.0f})")

    if st.button(
        "מחק",
        key=f"cog_del_profile_{sid}",
        use_container_width=True,
    ):
        _delete_shape(sid)
        st.rerun()


def _render_add_shapes_tab() -> None:
    category = st.selectbox(
        "קטגוריית פרופיל",
        list(_CATALOG_GROUPS.keys()),
        key="cog_catalog_category",
    )
    profiles = _CATALOG_GROUPS[category]
    profile_key = st.selectbox(
        "בחר פרופיל",
        profiles,
        key="cog_catalog_profile",
    )
    st.caption("הפרופיל יתווסף מימין לצורה האחרונה, צמוד לציר X.")
    if st.button("הוסף לשרטוט", type="primary", use_container_width=True):
        _append_catalog_shape(profile_key)
        st.rerun()


def _render_practice_section() -> None:
    st.divider()
    st.subheader("תרגול")
    st.caption(
        "לחץ ליצירת תרגיל עם 2–3 פרופילים אקראיים על הלוח. "
        "חשב את מרכז הכובד הגלובלי והשווה לדוח למטה."
    )
    if st.button(
        "תרגיל חדש",
        type="primary",
        use_container_width=True,
        key="cog_practice_new",
    ):
        _generate_practice_exercise()
        st.rerun()

    selected_id = st.session_state.get("cog_selected_shape_id")
    if selected_id is not None and st.session_state.cog_shapes:
        if st.button(
            f"מחק פרופיל M{int(selected_id)}",
            type="primary",
            use_container_width=True,
            key="cog_practice_delete_selected",
        ):
            _delete_shape(int(selected_id))
            st.rerun()
    elif st.session_state.cog_shapes:
        st.caption("לחץ על נקודת M בשרטוט כדי לבחור פרופיל למחיקה.")


def render_controls() -> None:
    """עמודת הזרקה — כפתורים/בוררים להוספת פרופילים בלבד."""
    st.subheader("הוספת פרופילים")
    _render_add_shapes_tab()
    _render_practice_section()


def _fmt_cog_num(value: float, decimals: int = 2) -> str:
    return f"{float(value):.{decimals}f}"


def _cog_latex_product_terms(rows: list[dict[str, Any]], arm_key: str) -> str:
    parts: list[str] = []
    for row in rows:
        a = _fmt_cog_num(row["Area (A)"])
        arm = _fmt_cog_num(row[arm_key])
        parts.append(rf"({a})({arm})")
    return " + ".join(parts)


def _cog_html_frac(numerator: str, denominator: str) -> str:
    return (
        f'<span class="cog-frac">'
        f'<span class="cog-frac-num">{numerator}</span>'
        f'<span class="cog-frac-den">{denominator}</span>'
        f"</span>"
    )


def _cog_html_formula_line(
    var: str,
    n: int,
    product_terms: str,
    sum_a_tex: str,
    sum_arm: float,
    sum_a: float,
    result: float,
) -> str:
    sigma_num = rf'<span class="cog-sigma">&#8721;<sub>i=1</sub><sup>{n}</sup> A<sub>i</sub>&middot;{var}<sub>i</sub></span>'
    sigma_den = rf'<span class="cog-sigma">&#8721;<sub>i=1</sub><sup>{n}</sup> A<sub>i</sub></span>'
    return (
        f'<div class="cog-formula-line">'
        f"{var}<sub>c</sub> = {_cog_html_frac(sigma_num, sigma_den)}"
        f" = {_cog_html_frac(product_terms, sum_a_tex)}"
        f" = {_cog_html_frac(_fmt_cog_num(sum_arm), _fmt_cog_num(sum_a))}"
        f' = <span class="cog-formula-result">{_fmt_cog_num(result, 3)} cm</span>'
        f"</div>"
    )


def _render_cog_data_table_html(rows: list[dict[str, Any]], sum_a: float, sum_ax: float, sum_ay: float) -> str:
    body_rows: list[str] = []
    for idx, row in enumerate(rows, start=1):
        body_rows.append(
            f"<tr>"
            f"<td>{idx}</td>"
            f"<td>{row['Profile']}</td>"
            f"<td>{_fmt_cog_num(row['Area (A)'])}</td>"
            f"<td>{_fmt_cog_num(row['x_i'])}</td>"
            f"<td>{_fmt_cog_num(row['y_i'])}</td>"
            f"<td>{_fmt_cog_num(row['A*x_i'])}</td>"
            f"<td>{_fmt_cog_num(row['A*y_i'])}</td>"
            f"</tr>"
        )
    return f"""
<table class="cog-nb-table">
<thead><tr>
  <th>#</th><th>פרופיל</th><th>A [cm²]</th><th>x [cm]</th><th>y [cm]</th>
  <th>A·x</th><th>A·y</th>
</tr></thead>
<tbody>
{"".join(body_rows)}
</tbody>
<tfoot><tr>
  <td colspan="2">Σ</td>
  <td>{_fmt_cog_num(sum_a)}</td>
  <td>—</td><td>—</td>
  <td>{_fmt_cog_num(sum_ax)}</td>
  <td>{_fmt_cog_num(sum_ay)}</td>
</tr></tfoot>
</table>
"""


def _render_cog_result_card(xc: float, yc: float) -> str:
    return f"""
<div class="cog-result-card">
  <div class="cog-result-title">תוצאה סופית — מרכז כובד גלובלי</div>
  <div class="cog-result-values">
    <div class="cog-result-item">
      <div class="lbl">X<sub>c</sub> [cm]</div>
      <div class="val">{_fmt_cog_num(xc, 3)}</div>
    </div>
    <div class="cog-result-item">
      <div class="lbl">Y<sub>c</sub> [cm]</div>
      <div class="val">{_fmt_cog_num(yc, 3)}</div>
    </div>
  </div>
</div>
"""


def _render_a4_page_inner_html(
    rows: list[dict[str, Any]],
    n: int,
    xc: float,
    yc: float,
    sum_a: float,
    sum_ax: float,
    sum_ay: float,
) -> str:
    x_terms = _cog_latex_product_terms(rows, "x_i")
    y_terms = _cog_latex_product_terms(rows, "y_i")
    sum_a_tex = " + ".join(_fmt_cog_num(r["Area (A)"]) for r in rows)
    x_formula = _cog_html_formula_line("X", n, x_terms, sum_a_tex, sum_ax, sum_a, xc)
    y_formula = _cog_html_formula_line("Y", n, y_terms, sum_a_tex, sum_ay, sum_a, yc)
    table_html = _render_cog_data_table_html(rows, sum_a, sum_ax, sum_ay)
    result_html = _render_cog_result_card(xc, yc)

    return f"""
<div class="cog-a4-page" id="cog-a4-page">
  <h2 class="cog-a4-page-title">פתרון מחברת — מרכז כובד גלובלי</h2>

  <div class="cog-nb-step">
    <h3 class="cog-nb-step-title">שלב 1 — טבלת נתונים</h3>
    <p class="cog-nb-step-caption">נתוני כל פרופיל: שטח, זרועות מרכז כובד מקומי, ומומנטים שטחיים.</p>
    {table_html}
  </div>

  <div class="cog-nb-step">
    <h3 class="cog-nb-step-title">שלב 2 — דרך הפתרון (הצבת מספרים)</h3>
    <p class="cog-nb-step-caption">הצבת ערכי הטבלה בנוסחאות מרכז הכובד הגלובלי.</p>
    <div class="cog-formula-block">
      {x_formula}
      {y_formula}
    </div>
  </div>

  <div class="cog-nb-step">
    <h3 class="cog-nb-step-title">שלב 3 — תוצאה סופית</h3>
    {result_html}
  </div>
</div>
"""


def _render_a4_empty_page_html() -> str:
    return """
<div class="cog-a4-page" id="cog-a4-page">
  <h2 class="cog-a4-page-title">פתרון מחברת — מרכז כובד גלובלי</h2>
  <p class="cog-nb-empty-msg">הוסף פרופילים מהסרגל (או לחץ «תרגיל חדש») כדי לראות כאן את הפתרון המלא.</p>
</div>
"""


def render_global_calculation_report() -> None:
    """פתרון מחברת הנדסי — מרכז כובד גלובלי צעד-אחר-צעד."""
    shapes = list(st.session_state.cog_shapes)

    if not shapes:
        page_html = _render_a4_empty_page_html()
    else:
        rows = _build_global_report_rows(shapes)
        xc, yc, sum_a, sum_ax, sum_ay = _compute_global_centroid(rows)
        if xc is None or yc is None:
            st.warning("לא ניתן לחשב מרכז כובד — בדוק את נתוני הפרופילים.")
            page_html = _render_a4_empty_page_html()
        else:
            n = len(rows)
            page_html = _render_a4_page_inner_html(rows, n, xc, yc, sum_a, sum_ax, sum_ay)

    page_key = str(len(shapes)) + ":" + str(hash(page_html))
    from beam_ui import render_notebook_pan_board

    render_notebook_pan_board(
        page_html,
        page_key,
        component_key="cog_notebook_board",
    )


def render_cog_page() -> None:
    _init_session()
    if "cog_selected_shape_id" not in st.session_state:
        st.session_state.cog_selected_shape_id = None

    with st.sidebar:
        st.caption(f"גרסת CoG: **{_COG_BUILD_ID}**")
        st.caption("הלוחות = רכיבי שרטוט (iframe), לא ווידג'טים רגילים של Streamlit.")
        if st.button("רענון רכיבים", key="cog_reload_components", use_container_width=True):
            _COMPONENTS.clear()
            st.cache_resource.clear()
            st.rerun()

    st.header("מרכז כובד - חתכים מורכבים")
    col_details, col_canvas, col_controls = st.columns([1.8, 5.4, 2.5], gap="medium")
    with col_controls:
        render_controls()
    with col_canvas:
        canvas_result = render_canvas()
    with col_details:
        render_shape_details(canvas_result)

    st.divider()
    st.subheader("פתרון מחברת")
    render_global_calculation_report()
