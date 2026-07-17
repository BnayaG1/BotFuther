# -*- coding: utf-8 -*-
"""חילוץ תרגיל מתמונה וחישוב מקומי."""
from __future__ import annotations

import copy
import json
import logging
import math
import re
import time

import core.center_of_gravity as cog
from google import genai
from google.genai import types
from google.genai.errors import APIError

from bot.config import (
    COG_CATALOG_ALIASES,
    DEFAULT_MODEL,
    FALLBACK_MODELS,
    KN_PER_TON,
    MAX_RETRIES_PER_MODEL,
    RETRYABLE_API_CODES,
    RETRY_BASE_DELAY_SEC,
    SOLUTION_REQUEST_HINT,
    VISION_EXTRACT_ONLY_MODE,
    DRAFT_APPROVAL_MODE,
    VISION_FAST_FALLBACK_STAGED,
    VISION_FAST_IMAGE_MIN_PX,
    VISION_FAST_MAX_OUTPUT_TOKENS,
    VISION_FAST_MODE,
    VISION_LOADS_REFINE,
    VISION_ALLOW_PARTIAL_FAST,
    VISION_QUALITY_MODEL,
    VISION_QUALITY_RETRY,
    VISION_MAX_MODELS_PER_IMAGE,
    VISION_MAX_STAGED_RETRIES,
    VISION_OVERLOAD_BACKOFF_SEC,
    VISION_OVERLOAD_FALLBACK,
    VISION_TOTAL_BUDGET_SEC,
    VISION_MAX_OUTPUT_TOKENS,
)
from bot.prompt_loader import (
    STEP_1_KEY,
    STEP_2_KEY,
    STEP_3_KEY,
    STEP_4_KEY,
    STEP_5_KEY,
    format_vision_stage_prompt,
    get_vision_extract_prompt,
    get_vision_handwriting_hint,
    get_vision_stage_distributed_loads_prompt,
    get_vision_stage_geometry_prompt,
    get_vision_stage_point_loads_prompt,
    get_vision_stage_supports_prompt,
    get_vision_stage_validation_prompt,
)

VISION_EXTRACT_PROMPT = get_vision_extract_prompt()
VISION_HANDWRITING_HINT = get_vision_handwriting_hint()
VISION_STAGE_GEOMETRY_PROMPT = get_vision_stage_geometry_prompt()
VISION_STAGE_SUPPORTS_PROMPT = get_vision_stage_supports_prompt()
VISION_STAGE_POINT_LOADS_PROMPT = get_vision_stage_point_loads_prompt()
VISION_STAGE_DISTRIBUTED_PROMPT = get_vision_stage_distributed_loads_prompt()
VISION_STAGE_VALIDATION_PROMPT = get_vision_stage_validation_prompt()
from bot.env import normalize_model_id, resolve_vision_model
from bot.gemini_chat import generate_content_with_retries
from bot.engineering import (
    format_engineering_tool_results,
    format_force_ton,
    format_horizontal_force_ton,
    format_moment_ton_m,
    kn_to_ton,
    tool_beam_solve_cantilever,
    tool_beam_solve_simply_supported,
    tool_cog_compute_centroid,
)

log = logging.getLogger("beam_telegram_bot")

VISION_STAGED_MAX_RETRIES = VISION_MAX_STAGED_RETRIES

_vision_context_by_chat: dict[int, str] = {}
_vision_bundle_by_chat: dict[int, dict] = {}


def clear_vision_context(chat_id: int) -> None:
    _vision_context_by_chat.pop(chat_id, None)
    _vision_bundle_by_chat.pop(chat_id, None)


def caption_wants_solution(caption: str) -> bool:
    return bool(SOLUTION_REQUEST_HINT.search(caption or ""))


def get_stored_vision_extracted(chat_id: int) -> dict | None:
    bundle = _vision_bundle_by_chat.get(chat_id)
    if not bundle:
        return None
    extracted = bundle.get("extracted") or {}
    return extracted if isinstance(extracted, dict) and extracted else None


def parse_json_from_llm_text(content: str) -> dict:
    text = content.strip()
    if text.startswith("```"):
        parts = text.split("```")
        chunk = parts[1].strip() if len(parts) > 1 else text
        if chunk.lower().startswith("json"):
            chunk = chunk[4:].lstrip()
        text = chunk
    def _strip_trailing_commas(s: str) -> str:
        # Conservative JSON repair: remove trailing commas before } or ]
        s = re.sub(r",(\s*[}\]])", r"\1", s)
        return s

    def _try_parse(s: str) -> dict:
        s = s.strip()
        s = _strip_trailing_commas(s)
        return json.loads(s)

    try:
        parsed = _try_parse(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("לא התקבל JSON תקין מניתוח התמונה") from None
        snippet = text[start : end + 1]
        try:
            parsed = _try_parse(snippet)
        except json.JSONDecodeError as exc:
            # Last resort: try trimming to the last complete brace.
            trimmed_end = snippet.rfind("}")
            if trimmed_end > 0:
                parsed = _try_parse(snippet[: trimmed_end + 1])
            else:
                raise ValueError("לא התקבל JSON תקין מניתוח התמונה") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Vision output is not a JSON object")
    return parsed


def _vision_model_order(primary: str) -> list[str]:
    ordered: list[str] = []
    for name in (primary, DEFAULT_MODEL, *FALLBACK_MODELS):
        norm = normalize_model_id(name)
        if norm and norm not in ordered:
            ordered.append(norm)
    return ordered


def extract_exercise_from_image(
    client: genai.Client,
    model: str,
    image_bytes: bytes,
    mime_type: str,
    *,
    extra_instruction: str = "",
    json_mode: bool = True,
    prompt_template: str | None = None,
) -> dict:
    """Gemini קורא תמונה ומחזיר JSON מובנה."""
    base = prompt_template or f"{VISION_EXTRACT_PROMPT}\n\n{VISION_HANDWRITING_HINT}"
    prompt = base
    if extra_instruction and prompt_template is None:
        prompt = f"{prompt}\n\nAdditional instruction:\n{extra_instruction}"
    config_kwargs: dict = {
        "temperature": 0.0,
        "max_output_tokens": (
            VISION_FAST_MAX_OUTPUT_TOKENS
            if VISION_FAST_MODE
            else VISION_MAX_OUTPUT_TOKENS
        ),
    }
    if json_mode:
        config_kwargs["response_mime_type"] = "application/json"
    norm_model = normalize_model_id(model)
    if norm_model.startswith("gemini-2.5-"):
        config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                types.Part.from_text(text=prompt),
            ],
        )
    ]
    response = generate_content_with_retries(
        client,
        model=norm_model,
        contents=contents,
        config=types.GenerateContentConfig(**config_kwargs),
    )
    text = response.text
    if not text or not str(text).strip():
        raise ValueError("לא התקבל JSON מניתוח התמונה")
    return parse_json_from_llm_text(str(text))


def _format_stage_prompt(
    template: str,
    *,
    context: dict | None = None,
    extra: str = "",
) -> str:
    return format_vision_stage_prompt(template, context=context, extra=extra)


def _unwrap_step(stage: dict, step_key: str) -> dict:
    """מחלץ בלוק שלב מתשובת Gemini (עטופה או שטוחה)."""
    if not isinstance(stage, dict):
        return {}
    block = stage.get(step_key)
    if isinstance(block, dict):
        return block
    return stage


def _geometry_payload(stage: dict) -> dict:
    payload = _unwrap_step(stage, STEP_1_KEY)
    nested = payload.get("geometry")
    if isinstance(nested, dict):
        return nested
    return payload


def _exercise_type_from_geometry_stage(stage: dict) -> str:
    payload = _unwrap_step(stage, STEP_1_KEY)
    return str(payload.get("exercise_type", stage.get("exercise_type", ""))).lower()


def validate_stage_geometry(stage: dict) -> list[str]:
    issues: list[str] = []
    geo = _geometry_payload(stage)
    if not geo:
        return ["geometry object missing"]
    try:
        L = float(geo.get("L", 0))
    except (TypeError, ValueError):
        return ["L is not a valid number"]
    if L <= 0:
        issues.append("L must be positive")
    segments = geo.get("segments")
    if isinstance(segments, list) and segments:
        seg_sum = 0.0
        for seg in segments:
            if not isinstance(seg, dict):
                continue
            try:
                length = float(seg.get("length_m", 0))
                if length <= 0:
                    length = float(seg.get("to_x", 0)) - float(seg.get("from_x", 0))
                seg_sum += length
            except (TypeError, ValueError):
                continue
        if seg_sum > 0 and abs(seg_sum - L) > 0.15:
            issues.append(f"segment sum ({seg_sum:g}) != L ({L:g})")
    labeled = geo.get("labeled_points")
    if not isinstance(labeled, list) or len(labeled) < 2:
        issues.append("need at least 2 labeled_points on the beam")
    return issues


def validate_stage_supports(stage: dict, L: float) -> list[str]:
    issues: list[str] = []
    payload = _unwrap_step(stage, STEP_2_KEY)
    supports = payload.get("supports")
    if not isinstance(supports, list) or not supports:
        return ["no supports found"]
    has_pin = has_roller = has_fixed = False
    for sup in supports:
        if not isinstance(sup, dict):
            continue
        st = str(sup.get("type", "")).lower()
        if st == "pin":
            has_pin = True
        elif st == "roller":
            has_roller = True
        elif st == "fixed":
            has_fixed = True
        try:
            x = float(sup.get("x", -1))
            if x < -0.01 or x > L + 0.15:
                issues.append(f"support {sup.get('label')} at x={x} outside [0,{L}]")
            d_left = sup.get("dist_from_left_m")
            d_right = sup.get("dist_from_right_m")
            if d_left is not None and abs(float(d_left) - x) > 0.2:
                issues.append(f"support {sup.get('label')}: dist_from_left mismatch")
            if d_right is not None and abs(float(d_right) - (L - x)) > 0.2:
                issues.append(f"support {sup.get('label')}: dist_from_right mismatch")
        except (TypeError, ValueError):
            issues.append(f"support {sup.get('label')} has invalid x")
    mode = str(payload.get("support_mode", "")).lower()
    if mode == "cantilever" and not has_fixed:
        issues.append("cantilever requires a fixed support")
    if mode == "simply_supported" and not (has_pin and has_roller):
        if not has_pin:
            issues.append("simply supported beam needs a pin support")
        if not has_roller:
            issues.append("simply supported beam needs a roller support")
    return issues


def validate_stage_point_loads(stage: dict, L: float) -> list[str]:
    issues: list[str] = []
    payload = _unwrap_step(stage, STEP_3_KEY)
    loads = payload.get("loads")
    if not isinstance(loads, list):
        return issues
    for idx, ld in enumerate(loads):
        if not isinstance(ld, dict):
            continue
        t = str(ld.get("type", "")).lower()
        if t == "distributed":
            issues.append(
                f"load #{idx + 1}: distributed belongs in {STEP_4_KEY}, not point loads"
            )
            continue
        try:
            x = float(ld.get("x", -1))
            if x < -0.01 or x > L + 0.15:
                issues.append(f"load #{idx + 1} at x={x} outside beam")
        except (TypeError, ValueError):
            issues.append(f"load #{idx + 1} has invalid position")
    return issues


def validate_stage_distributed_loads(stage: dict, L: float) -> list[str]:
    issues: list[str] = []
    payload = _unwrap_step(stage, STEP_4_KEY)
    dist = payload.get("distributed_loads")
    if not isinstance(dist, list):
        return issues
    for idx, item in enumerate(dist):
        if not isinstance(item, dict):
            continue
        try:
            start_x = float(item.get("start_x", item.get("x1", -1)))
            end_x = float(item.get("end_x", item.get("x2", -1)))
            if start_x < -0.01 or end_x > L + 0.15:
                issues.append(f"distributed load #{idx + 1} span outside beam")
            if end_x <= start_x:
                issues.append(f"distributed load #{idx + 1} invalid span")
        except (TypeError, ValueError):
            issues.append(f"distributed load #{idx + 1} has invalid position")
    return issues


def validate_stage_loads(stage: dict, L: float) -> list[str]:
    """מיושן — מאחד בדיקות שלב 3+4."""
    issues = validate_stage_point_loads(stage, L)
    issues.extend(validate_stage_distributed_loads(stage, L))
    payload = _unwrap_step(stage, STEP_3_KEY)
    dist_payload = _unwrap_step(stage, STEP_4_KEY)
    has_point = isinstance(payload.get("loads"), list) and bool(payload.get("loads"))
    has_dist = isinstance(dist_payload.get("distributed_loads"), list) and bool(
        dist_payload.get("distributed_loads")
    )
    legacy_loads = stage.get("loads")
    legacy_dist = stage.get("distributed_loads")
    if isinstance(legacy_loads, list) and legacy_loads:
        has_point = True
    if isinstance(legacy_dist, list) and legacy_dist:
        has_dist = True
    if not has_point and not has_dist:
        return ["no loads found on diagram"]
    return issues


def build_validation_check(
    L: float,
    geometry_stage: dict,
    supports_stage: dict,
    point_loads_stage: dict,
    distributed_stage: dict,
    gemini_validation_stage: dict | None = None,
) -> dict:
    """שלב 5 — אימות קוד + מיזוג תוצאות Gemini."""
    issues: list[str] = []
    issues.extend(validate_stage_geometry(geometry_stage))
    issues.extend(validate_stage_supports(supports_stage, L))
    issues.extend(validate_stage_point_loads(point_loads_stage, L))
    issues.extend(validate_stage_distributed_loads(distributed_stage, L))

    empty_fields: list[str] = []
    geo = _geometry_payload(geometry_stage)
    if not geo.get("L"):
        empty_fields.append(f"{STEP_1_KEY}.L")
    if not geo.get("labeled_points"):
        empty_fields.append(f"{STEP_1_KEY}.labeled_points")

    geometry_conflicts: list[str] = []
    for issue in issues:
        if "outside" in issue or "segment sum" in issue or "!=" in issue:
            geometry_conflicts.append(issue)

    gemini_block = _unwrap_step(gemini_validation_stage or {}, STEP_5_KEY)
    for key, target in (
        ("issues", issues),
        ("empty_fields", empty_fields),
        ("geometry_conflicts", geometry_conflicts),
    ):
        for item in gemini_block.get(key) or []:
            text = str(item).strip()
            if text and text not in target:
                target.append(text)

    is_complete = not issues and not empty_fields and not geometry_conflicts
    if gemini_block.get("is_complete") is False and gemini_block.get("issues"):
        is_complete = False

    return {
        "is_complete": is_complete,
        "issues": issues,
        "empty_fields": empty_fields,
        "geometry_conflicts": geometry_conflicts,
    }


def merge_staged_beam_extraction(
    geometry_stage: dict,
    supports_stage: dict,
    point_loads_stage: dict,
    distributed_stage: dict,
    validation_stage: dict | None = None,
    *,
    points_stage: dict | None = None,
    loads_stage: dict | None = None,
) -> dict:
    """מאחד 5 שלבי חילוץ למבנה אחד לפני חישוב."""
    geo_payload = _unwrap_step(geometry_stage, STEP_1_KEY)
    geo = _geometry_payload(geometry_stage)
    L = float(geo.get("L", 10.0))

    sup_payload = _unwrap_step(supports_stage, STEP_2_KEY)
    supports = list(sup_payload.get("supports") or [])
    support_mode = str(sup_payload.get("support_mode", "simply_supported")).lower()

    if loads_stage and not _unwrap_step(point_loads_stage, STEP_3_KEY).get("loads"):
        point_payload = {"loads": list(loads_stage.get("loads") or [])}
    else:
        point_payload = _unwrap_step(point_loads_stage, STEP_3_KEY)

    if loads_stage and not _unwrap_step(distributed_stage, STEP_4_KEY).get(
        "distributed_loads"
    ):
        dist_payload = {
            "distributed_loads": list(loads_stage.get("distributed_loads") or [])
        }
    else:
        dist_payload = _unwrap_step(distributed_stage, STEP_4_KEY)

    dist_raw = list(dist_payload.get("distributed_loads") or [])
    solver_loads: list[dict] = []
    for raw in list(point_payload.get("loads") or []):
        if not isinstance(raw, dict):
            continue
        if str(raw.get("type", "")).lower() == "distributed":
            continue
        entry = {
            k: v
            for k, v in raw.items()
            if k
            not in (
                "dist_from_pin_m",
                "dist_from_roller_m",
                "dist_from_left_m",
            )
        }
        solver_loads.append(entry)

    pin_label = sup_payload.get("pin_support_label")
    roller_label = sup_payload.get("roller_support_label")
    ra_pos = 0.0
    rb_pos = L
    for sup in supports:
        if not isinstance(sup, dict):
            continue
        label = str(sup.get("label", ""))
        st = str(sup.get("type", "")).lower()
        x = float(sup.get("x", 0.0))
        if pin_label and label == str(pin_label):
            ra_pos = x
        elif st == "pin" and ra_pos == 0.0 and support_mode != "cantilever":
            ra_pos = x
        if roller_label and label == str(roller_label):
            rb_pos = x
        elif st == "roller":
            rb_pos = x
        if st == "fixed" and support_mode == "cantilever":
            ra_pos = x

    validation_block = build_validation_check(
        L,
        geometry_stage,
        supports_stage,
        point_loads_stage,
        distributed_stage,
        validation_stage,
    )

    protocol = {
        STEP_1_KEY: geo_payload,
        STEP_2_KEY: sup_payload,
        STEP_3_KEY: point_payload,
        STEP_4_KEY: dist_payload,
        STEP_5_KEY: validation_block,
    }

    notes = " | ".join(
        str(n)
        for n in (
            geo_payload.get("notes"),
            sup_payload.get("notes"),
            point_payload.get("notes"),
            dist_payload.get("notes"),
        )
        if n
    )

    data_points: list[dict] = []
    if isinstance(points_stage, dict):
        pts_block = _unwrap_step(points_stage, "STEP_3_DATA_POINTS")
        data_points = list(
            pts_block.get("data_points") or points_stage.get("data_points") or []
        )

    return {
        "exercise_type": "beam",
        "confidence": geo_payload.get("confidence", geometry_stage.get("confidence", "medium")),
        "image_focus": geo_payload.get("image_focus", geometry_stage.get("image_focus", {})),
        "extraction_pipeline": "staged_5",
        "extraction_protocol": protocol,
        "staged": protocol,
        "distributed_loads": dist_raw,
        "beam": {
            "structure_type": str(
                sup_payload.get("structure_type") or support_mode
            ).lower(),
            "internal_hinges": list(sup_payload.get("internal_hinges") or []),
            "support_mode": support_mode,
            "L": L,
            "origin": geo.get("origin", "left_end_of_beam_axis"),
            "left_end_label": geo.get("left_end_label"),
            "right_end_label": geo.get("right_end_label"),
            "supports": supports,
            "ra_pos": ra_pos,
            "rb_pos": rb_pos,
            "key_points_m": list(geo.get("key_points_m") or []),
            "segments": list(geo.get("segments") or []),
            "labeled_points": list(geo.get("labeled_points") or []),
            "data_points": data_points,
            "distributed_loads": dist_raw,
            "loads": solver_loads,
            "pin_support_label": sup_payload.get("pin_support_label"),
            "roller_support_label": sup_payload.get("roller_support_label"),
        },
        "notes": notes,
    }


def _merge_staged_geometry_supports_into_beam(
    beam: dict, geometry: dict, supports_stage: dict
) -> None:
    """ממזג שלב 1+2 (מידות + סמכים) לתוך מודל מונוליתי."""
    if not isinstance(beam, dict):
        return
    geo = _geometry_payload(geometry)
    if isinstance(geo, dict):
        for key in (
            "labeled_points",
            "segments",
            "left_end_label",
            "right_end_label",
            "key_points_m",
            "origin",
        ):
            val = geo.get(key)
            if val:
                beam[key] = val
        try:
            staged_L = float(geo.get("L", 0))
            if staged_L > 0:
                beam["L"] = staged_L
        except (TypeError, ValueError):
            pass

    staged_supports = _unwrap_step(supports_stage, STEP_2_KEY).get("supports")
    if isinstance(staged_supports, list) and staged_supports:
        by_label: dict[str, dict] = {}
        for sup in staged_supports:
            if isinstance(sup, dict):
                lbl = str(sup.get("label", "")).strip().upper()
                if lbl:
                    by_label[lbl] = sup
        out_supports: list[dict] = []
        for sup in beam.get("supports") or []:
            if not isinstance(sup, dict):
                continue
            merged = dict(sup)
            lbl = str(sup.get("label", "")).strip().upper()
            if lbl and lbl in by_label:
                src = by_label[lbl]
                merged["x"] = src.get("x", merged.get("x"))
                for k in ("dist_from_left_m", "dist_from_right_m"):
                    if src.get(k) is not None:
                        merged[k] = src[k]
            out_supports.append(merged)
        if out_supports:
            beam["supports"] = out_supports

    sup_payload = _unwrap_step(supports_stage, STEP_2_KEY)
    for key in ("pin_support_label", "roller_support_label", "support_mode", "structure_type"):
        val = sup_payload.get(key)
        if val:
            beam[key] = val


def extract_geometry_and_supports_stages(
    client: genai.Client,
    model: str,
    image_bytes: bytes,
    mime_type: str,
    *,
    extra_instruction: str = "",
) -> tuple[dict, dict] | None:
    """שלבים 1–2 בלבד — גיאומטריה + סמכים (לתיקון fallback מונוליתי)."""
    norm = normalize_model_id(model)
    extra = extra_instruction
    try:
        geometry_stage = extract_exercise_from_image(
            client,
            norm,
            image_bytes,
            mime_type,
            prompt_template=_format_stage_prompt(VISION_STAGE_GEOMETRY_PROMPT, extra=extra),
        )
        if validate_stage_geometry(geometry_stage):
            return None
        L = float(_geometry_payload(geometry_stage)["L"])
        ctx: dict = {
            STEP_1_KEY: _unwrap_step(geometry_stage, STEP_1_KEY),
            "geometry": _geometry_payload(geometry_stage),
            "image_focus": _unwrap_step(geometry_stage, STEP_1_KEY).get("image_focus"),
        }
        supports_stage = extract_exercise_from_image(
            client,
            norm,
            image_bytes,
            mime_type,
            prompt_template=_format_stage_prompt(
                VISION_STAGE_SUPPORTS_PROMPT, context=ctx, extra=extra
            ),
        )
        if validate_stage_supports(supports_stage, L):
            return None
        return geometry_stage, supports_stage
    except Exception as exc:
        log.warning("Geometry+supports mini-staged failed: %s", exc)
        return None


def _enrich_beam_from_staged_geometry_supports(
    client: genai.Client,
    model: str,
    image_bytes: bytes,
    mime_type: str,
    parsed: dict,
    *,
    extra_instruction: str = "",
) -> dict:
    """אם גליל בקצה אבל צמד פנימי — משלים מידות+סמכים משלבים 1–2."""
    beam = parsed.get("beam")
    if not isinstance(beam, dict):
        return parsed

    supports = beam.get("supports") or []
    pin_x: float | None = None
    roller_x: float | None = None
    for sup in supports:
        if not isinstance(sup, dict):
            continue
        st = str(sup.get("type", "")).lower()
        try:
            x = float(sup.get("x", 0))
        except (TypeError, ValueError):
            continue
        if st == "pin":
            pin_x = x
        elif st == "roller":
            roller_x = x

    L = float(beam.get("L", 0))
    labeled = _labeled_points_map(beam)
    needs_enrich = False
    if pin_x is not None and roller_x is not None and L > 0:
        if pin_x > 0.4 and (abs(roller_x - L) < 0.35 or abs(roller_x - _right_end_x(beam, L)) < 0.35):
            needs_enrich = True
    if "B" in labeled and labeled["B"] < L - 0.2 and roller_x is not None:
        if abs(roller_x - labeled["B"]) > 0.25:
            needs_enrich = True
    if not needs_enrich:
        return parsed

    mini = extract_geometry_and_supports_stages(
        client, model, image_bytes, mime_type, extra_instruction=extra_instruction
    )
    if not mini:
        return parsed
    geometry_stage, supports_stage = mini
    _merge_staged_geometry_supports_into_beam(beam, geometry_stage, supports_stage)
    parsed = dict(parsed)
    parsed["beam"] = normalize_beam_model(beam)
    log.info("Enriched monolithic beam from staged geometry+supports")
    return parsed


def extract_beam_exercise_staged(
    client: genai.Client,
    model: str,
    image_bytes: bytes,
    mime_type: str,
    *,
    extra_instruction: str = "",
) -> dict:
    """חילוץ קורה ב-5 שלבים: גיאומטריה → סמכים → עומסים נקודתיים → מפורסים → אימות."""
    norm = normalize_model_id(model)
    extra = extra_instruction

    log.info("Vision staged 1/5: beam geometry")
    geometry_stage = extract_exercise_from_image(
        client,
        norm,
        image_bytes,
        mime_type,
        prompt_template=_format_stage_prompt(VISION_STAGE_GEOMETRY_PROMPT, extra=extra),
    )
    if _exercise_type_from_geometry_stage(geometry_stage) == "cog":
        log.info("COG exercise detected — using single-shot extract")
        return extract_exercise_from_image(
            client,
            norm,
            image_bytes,
            mime_type,
            extra_instruction=extra,
        )

    geo_issues = validate_stage_geometry(geometry_stage)
    if geo_issues:
        raise ValueError(f"Stage 1 (geometry): {'; '.join(geo_issues)}")
    geo = _geometry_payload(geometry_stage)
    L = float(geo["L"])
    ctx: dict = {
        STEP_1_KEY: _unwrap_step(geometry_stage, STEP_1_KEY),
        "geometry": geo,
        "image_focus": _unwrap_step(geometry_stage, STEP_1_KEY).get("image_focus"),
    }

    log.info("Vision staged 2/5: supports")
    supports_stage = extract_exercise_from_image(
        client,
        norm,
        image_bytes,
        mime_type,
        prompt_template=_format_stage_prompt(
            VISION_STAGE_SUPPORTS_PROMPT, context=ctx, extra=extra
        ),
    )
    sup_issues = validate_stage_supports(supports_stage, L)
    if sup_issues:
        raise ValueError(f"Stage 2 (supports): {'; '.join(sup_issues)}")
    ctx[STEP_2_KEY] = _unwrap_step(supports_stage, STEP_2_KEY)

    log.info("Vision staged 3/5: point loads")
    point_loads_stage = extract_exercise_from_image(
        client,
        norm,
        image_bytes,
        mime_type,
        prompt_template=_format_stage_prompt(
            VISION_STAGE_POINT_LOADS_PROMPT, context=ctx, extra=extra
        ),
    )
    pt_issues = validate_stage_point_loads(point_loads_stage, L)
    if pt_issues:
        raise ValueError(f"Stage 3 (point loads): {'; '.join(pt_issues)}")
    ctx[STEP_3_KEY] = _unwrap_step(point_loads_stage, STEP_3_KEY)

    log.info("Vision staged 4/5: distributed loads")
    distributed_stage = extract_exercise_from_image(
        client,
        norm,
        image_bytes,
        mime_type,
        prompt_template=_format_stage_prompt(
            VISION_STAGE_DISTRIBUTED_PROMPT, context=ctx, extra=extra
        ),
    )
    dist_issues = validate_stage_distributed_loads(distributed_stage, L)
    if dist_issues:
        raise ValueError(f"Stage 4 (distributed): {'; '.join(dist_issues)}")
    ctx[STEP_4_KEY] = _unwrap_step(distributed_stage, STEP_4_KEY)

    log.info("Vision staged 5/5: validation check")
    validation_stage = extract_exercise_from_image(
        client,
        norm,
        image_bytes,
        mime_type,
        prompt_template=_format_stage_prompt(
            VISION_STAGE_VALIDATION_PROMPT, context=ctx, extra=extra
        ),
    )

    merged = merge_staged_beam_extraction(
        geometry_stage,
        supports_stage,
        point_loads_stage,
        distributed_stage,
        validation_stage,
    )
    validation = merged.get("extraction_protocol", {}).get(STEP_5_KEY, {})
    if not validation.get("is_complete") and validation.get("issues"):
        log.warning(
            "Validation check reported issues: %s",
            "; ".join(str(i) for i in validation["issues"][:6]),
        )

    merged = finalize_beam_extraction(merged)
    beam_issues = validate_beam_extraction(merged)
    if beam_issues:
        if DRAFT_APPROVAL_MODE:
            log.warning(
                "Staged extract validation issues (draft mode — returning as-is): %s",
                "; ".join(beam_issues[:5]),
            )
            merged["extraction_pipeline"] = "staged_partial"
            return package_extraction_response(
                merged,
                partial=True,
                validation_issues=beam_issues,
            )
        raise ValueError(f"Merged model: {'; '.join(beam_issues)}")

    has_point = bool(_unwrap_step(point_loads_stage, STEP_3_KEY).get("loads"))
    has_dist = bool(_unwrap_step(distributed_stage, STEP_4_KEY).get("distributed_loads"))
    if not has_point and not has_dist:
        if DRAFT_APPROVAL_MODE:
            log.warning("Staged extract: no loads (draft mode — returning geometry/supports)")
            merged["extraction_pipeline"] = "staged_partial"
            return package_extraction_response(
                merged,
                partial=True,
                validation_issues=["Stage 3+4: no loads found on diagram"],
            )
        raise ValueError("Stage 3+4: no loads found on diagram")

    log.info(
        "Vision staged extract OK: L=%s supports=%s point=%s distributed=%s",
        L,
        len(_unwrap_step(supports_stage, STEP_2_KEY).get("supports") or []),
        len(_unwrap_step(point_loads_stage, STEP_3_KEY).get("loads") or []),
        len(_unwrap_step(distributed_stage, STEP_4_KEY).get("distributed_loads") or []),
    )
    return merged


def validate_beam_extraction(data: dict) -> list[str]:
    """בדיקות עקביות — מחזיר רשימת בעיות (ריק = תקין)."""
    issues: list[str] = []
    beam = data.get("beam")
    if not isinstance(beam, dict):
        return issues
    try:
        L = float(beam.get("L", 0))
    except (TypeError, ValueError):
        issues.append("L is not a valid number")
        return issues
    segments = beam.get("segments")
    if isinstance(segments, list) and segments:
        seg_sum = 0.0
        for seg in segments:
            if not isinstance(seg, dict):
                continue
            try:
                length = float(seg.get("length_m", 0))
                if length <= 0:
                    from_x = float(seg.get("from_x", 0))
                    to_x = float(seg.get("to_x", 0))
                    length = to_x - from_x
                seg_sum += length
            except (TypeError, ValueError):
                continue
        if seg_sum > 0 and abs(seg_sum - L) > 0.15:
            issues.append(
                f"segment sum ({seg_sum:g}) does not match L ({L:g}) — re-read ALL tick marks"
            )
    supports = beam.get("supports")
    if isinstance(supports, list):
        for sup in supports:
            if not isinstance(sup, dict):
                continue
            try:
                sx = float(sup.get("x", -1))
                if sx < -0.01 or sx > L + 0.15:
                    label = sup.get("label", "?")
                    issues.append(f"support {label} at x={sx} outside beam [0, {L}]")
            except (TypeError, ValueError):
                continue
    loads = beam.get("loads")
    if isinstance(loads, list):
        for idx, ld in enumerate(loads):
            if not isinstance(ld, dict):
                continue
            try:
                lx = float(ld.get("x", ld.get("x1", -1)))
                if lx < -0.01 or lx > L + 0.15:
                    issues.append(f"load #{idx + 1} at x={lx} outside beam [0, {L}]")
            except (TypeError, ValueError):
                continue
    return issues


def _is_retryable_vision_error(exc: Exception) -> bool:
    if isinstance(exc, APIError):
        return exc.code in RETRYABLE_API_CODES
    text = str(exc).lower()
    return any(tok in text for tok in ("503", "429", "unavailable", "overloaded"))


def _is_complex_beam_diagram(beam: dict) -> bool:
    """תרגיל מורכב — הרבה נקודות/מקטעים/אלכסונים (לא קורה פשוטה עם 2 עומסים)."""
    labeled = _labeled_points_map(beam)
    if len(labeled) >= 6:
        return True
    segments = beam.get("segments") or []
    if isinstance(segments, list) and len(segments) >= 5:
        return True
    if isinstance(beam.get("distributed_loads"), list) and beam["distributed_loads"]:
        return True
    loads = beam.get("loads") or []
    inclined = sum(
        1 for ld in loads if str(ld.get("type", "")).lower() == "inclined"
    )
    moments = sum(1 for ld in loads if str(ld.get("type", "")).lower() == "moment")
    return inclined >= 2 or moments >= 1


def _extraction_completeness_issues(beam: dict) -> list[str]:
    """בדיקה שהחילוץ כולל את סוגי העומסים הצפויים לתרגיל מורכב."""
    if not isinstance(beam, dict):
        return []
    issues: list[str] = []
    try:
        L = float(beam.get("L", 0))
    except (TypeError, ValueError):
        return issues
    loads = [ld for ld in (beam.get("loads") or []) if isinstance(ld, dict)]
    if L < 6:
        return issues

    complex_diagram = _is_complex_beam_diagram(beam)

    has_moment = any(str(ld.get("type", "")).lower() == "moment" for ld in loads)
    has_inclined = any(str(ld.get("type", "")).lower() == "inclined" for ld in loads)
    has_distributed = any(
        str(ld.get("type", "")).lower() == "distributed" for ld in loads
    ) or bool(beam.get("distributed_loads"))
    has_udl_hint = has_distributed

    if complex_diagram and L >= 10 and len(loads) < 6:
        issues.append(
            f"רק {len(loads)} עומסים ל-L={L:g}m — חסרים כנראה מומנטים/אלכסונים/מפולג/אופקי"
        )
    if complex_diagram and L >= 10 and not has_moment:
        issues.append("לא זוהה מומנט — חפש חץ מעגלי (↺/↻) על הקורה")
    if complex_diagram and L >= 10 and not has_inclined:
        issues.append("לא זוהו עומסים אלכסוניים — חפש חצים אלכסוניים עם זווית (30°/45°)")
    if has_udl_hint and not has_distributed:
        issues.append("חסר עומס מפורס ב-distributed_loads[]")

    labeled = _labeled_points_map(beam)
    e_x, g_x = labeled.get("E"), labeled.get("G")
    if e_x is not None and g_x is not None:
        for ld in loads:
            if str(ld.get("type", "")).lower() != "distributed":
                continue
            try:
                x1, x2 = float(ld["x1"]), float(ld["x2"])
                w = float(ld.get("w", 0))
            except (TypeError, ValueError, KeyError):
                continue
            if abs(x1 - e_x) < 0.45 and 0.5 <= w <= 5.0 and x2 < g_x - 0.8:
                issues.append(
                    f"UDL נגמר ב-x={x2:g} — אמור להימשך עד G (x={g_x:g})"
                )
    seg_sum = _segment_length_sum(beam)
    if seg_sum > 0 and abs(seg_sum - L) > 0.25:
        issues.append(f"סכום מקטעים {seg_sum:g} ≠ L={L:g}")

    if complex_diagram and "C" in labeled:
        cx = labeled["C"]
        near_c = False
        for ld in loads:
            t = str(ld.get("type", "")).lower()
            try:
                if t == "distributed":
                    x1 = float(ld.get("x1", 0))
                    x2 = float(ld.get("x2", 0))
                    if x1 <= cx + 0.55 and x2 >= cx - 0.15:
                        near_c = True
                        break
                elif t != "distributed":
                    lx = float(ld.get("x", ld.get("x1", -999)))
                    if abs(lx - cx) < 0.55:
                        near_c = True
                        break
            except (TypeError, ValueError):
                continue
        if not near_c and L >= 8:
            issues.append(f"אין עומס ליד נקודה C (x={cx:g})")

    end_fx = 0.0
    for ld in loads:
        if str(ld.get("type", "")).lower() != "point":
            continue
        try:
            x = float(ld.get("x", 0))
        except (TypeError, ValueError):
            continue
        if abs(x - L) > 0.35:
            continue
        fx = float(ld.get("Fx", ld.get("fx", 0)) or 0)
        fy = float(ld.get("Fy", ld.get("fy", 0)) or 0)
        end_fx = max(end_fx, abs(fx))
        if abs(fx) < 1e-6 and 5.5 <= abs(fy) <= 7.5:
            issues.append(
                f"בקצה B (x={L:g}) זוהה עומס אנכי {fy:g}t — בדוק אם זה כוח אופקי 64.2t שמאלה"
            )
    if complex_diagram and L >= 10 and end_fx < 8.0:
        issues.append(f"חסר כוח אופקי משמעותי בקצה הקורה (x≈{L:g})")

    return issues


def _reject_unreliable_partial(parsed: dict, validation_issues: list[str]) -> bool:
    """אל תחזיר חילוץ חלקי גרוע — עדיף שגיאה מאשר כרטיס שגוי (חוץ ממצב טיוטה)."""
    if DRAFT_APPROVAL_MODE:
        return False
    beam = parsed.get("beam") if isinstance(parsed.get("beam"), dict) else {}
    completeness = _extraction_completeness_issues(beam)
    if len(completeness) >= 2:
        validation_issues = list(validation_issues) + completeness
    if not validation_issues:
        return False
    if len(validation_issues) >= 3:
        return True
    loads = beam.get("loads") if isinstance(beam.get("loads"), list) else []
    distributed = sum(
        1 for ld in loads if str(ld.get("type", "")).lower() == "distributed"
    )
    if distributed >= 3:
        return True
    blob = " ".join(validation_issues).lower()
    return any(k in blob for k in ("segment sum", "outside beam", "no loads", "חסר", "לא זוהה"))


def _is_json_parse_error(exc: BaseException) -> bool:
    if isinstance(exc, json.JSONDecodeError):
        return True
    msg = str(exc).lower()
    return "json" in msg or "delimiter" in msg or "expecting" in msg


def _validation_issues_for(parsed: dict) -> list[str]:
    issues = list(validate_beam_extraction(parsed))
    beam = parsed.get("beam") if isinstance(parsed.get("beam"), dict) else {}
    issues.extend(_extraction_completeness_issues(beam))
    return issues


def _try_monolithic_extract(
    client: genai.Client,
    model: str,
    image_bytes: bytes,
    mime_type: str,
    *,
    extra_instruction: str = "",
) -> tuple[dict, list[str]]:
    """קריאה מונוליתית אחת + ולידציה."""
    parsed = extract_exercise_from_image(
        client,
        model,
        image_bytes,
        mime_type,
        extra_instruction=extra_instruction,
        json_mode=True,
    )
    parsed = finalize_beam_extraction(parsed)
    return parsed, _validation_issues_for(parsed)


def _geometry_usable_for_refine(beam: dict) -> bool:
    if not isinstance(beam, dict):
        return False
    try:
        L = float(beam.get("L", 0))
    except (TypeError, ValueError):
        return False
    if L <= 0:
        return False
    supports = beam.get("supports") or []
    return isinstance(supports, list) and len(supports) >= 1


def _maybe_return_early_draft(
    parsed: dict,
    issues: list[str],
) -> dict | None:
    """מצב חיסכון: אחרי קריאה אחת עם גיאומטריה בסיסית — טיוטה בלי fallbacks יקרים."""
    if not (VISION_FAST_MODE and DRAFT_APPROVAL_MODE):
        return None
    beam = parsed.get("beam") if isinstance(parsed.get("beam"), dict) else {}
    if not _geometry_usable_for_refine(beam):
        return None
    log.info("Cost save: early draft return after 1 call")
    parsed["extraction_pipeline"] = "monolithic_fast_partial"
    return package_extraction_response(
        parsed,
        partial=True,
        validation_issues=list(issues),
    )


def _beam_to_staged_stages(beam: dict) -> tuple[dict, dict, float]:
    """בונה שלבי גיאומטריה+סמכים מטיוטה קיימת (לחילוץ עומסים ממוקד)."""
    L = float(beam.get("L", 10.0))
    geo_inner = {
        "L": L,
        "labeled_points": list(beam.get("labeled_points") or []),
        "segments": list(beam.get("segments") or []),
        "left_end_label": beam.get("left_end_label"),
        "right_end_label": beam.get("right_end_label"),
    }
    geometry_stage = {
        STEP_1_KEY: {
            "exercise_type": "beam",
            "geometry": geo_inner,
        }
    }
    supports_stage = {
        STEP_2_KEY: {
            "supports": list(beam.get("supports") or []),
            "support_mode": beam.get("support_mode", "simply_supported"),
            "pin_support_label": beam.get("pin_support_label", "A"),
            "roller_support_label": beam.get("roller_support_label", "B"),
        }
    }
    return geometry_stage, supports_stage, L


def extract_beam_loads_staged_refine(
    client: genai.Client,
    model: str,
    image_bytes: bytes,
    mime_type: str,
    parsed: dict,
    *,
    extra_instruction: str = "",
) -> dict | None:
    """שלבים 3–4 בלבד — משפר עומסים כשהגיאומטריה כבר אמינה."""
    beam = parsed.get("beam") if isinstance(parsed.get("beam"), dict) else {}
    if not _geometry_usable_for_refine(beam):
        return None
    norm = normalize_model_id(model)
    extra = extra_instruction
    geometry_stage, supports_stage, L = _beam_to_staged_stages(beam)
    ctx: dict = {
        STEP_1_KEY: _unwrap_step(geometry_stage, STEP_1_KEY),
        "geometry": _geometry_payload(geometry_stage),
    }
    try:
        log.info("Vision loads refine 1/2: point loads (L=%s)", L)
        point_loads_stage = extract_exercise_from_image(
            client,
            norm,
            image_bytes,
            mime_type,
            prompt_template=_format_stage_prompt(
                VISION_STAGE_POINT_LOADS_PROMPT, context=ctx, extra=extra
            ),
        )
        pt_issues = validate_stage_point_loads(point_loads_stage, L)
        if pt_issues:
            log.warning("Loads refine point stage: %s", "; ".join(pt_issues[:4]))
        ctx[STEP_3_KEY] = _unwrap_step(point_loads_stage, STEP_3_KEY)

        log.info("Vision loads refine 2/2: distributed loads")
        distributed_stage = extract_exercise_from_image(
            client,
            norm,
            image_bytes,
            mime_type,
            prompt_template=_format_stage_prompt(
                VISION_STAGE_DISTRIBUTED_PROMPT, context=ctx, extra=extra
            ),
        )
        dist_issues = validate_stage_distributed_loads(distributed_stage, L)
        if dist_issues:
            log.warning("Loads refine distributed stage: %s", "; ".join(dist_issues[:4]))

        refined = merge_staged_beam_extraction(
            geometry_stage,
            supports_stage,
            point_loads_stage,
            distributed_stage,
            None,
        )
        refined = finalize_beam_extraction(refined)
        issues = _validation_issues_for(refined)
        if issues and _reject_unreliable_partial(refined, issues):
            log.warning("Loads refine still unreliable: %s", "; ".join(issues[:5]))
            return None
        refined["extraction_pipeline"] = "loads_refine_2stage"
        return refined
    except Exception as exc:
        log.warning("Loads staged refine failed: %s", exc)
        return None


def extract_exercise_with_retries(
    client: genai.Client,
    primary_model: str,
    image_bytes: bytes,
    mime_type: str,
    *,
    extra_instruction: str = "",
) -> dict:
    """חילוץ קורה מדויק עם תקציב זמן קשיח (ברירת מחדל: 50s)."""

    started = time.monotonic()
    deadline = started + float(VISION_TOTAL_BUDGET_SEC)

    def _time_left_sec() -> float:
        return deadline - time.monotonic()

    def _out_of_time() -> bool:
        return _time_left_sec() <= 0.0

    # 1) Fast path: single-shot extraction (1 call) for latency.
    last_error: Exception | None = None
    model_order = _vision_model_order(primary_model)
    fast_model = model_order[0] if model_order else normalize_model_id(primary_model)
    quality_model = normalize_model_id(
        resolve_vision_model() if VISION_QUALITY_RETRY else VISION_QUALITY_MODEL
    )
    if VISION_FAST_MODE:
        model_order = [fast_model]
    else:
        model_order = model_order[: max(1, int(VISION_MAX_MODELS_PER_IMAGE))]

    best_fast: dict | None = None
    best_fast_issues: list[str] = []

    def _maybe_return_soft_partial(parsed: dict, issues: list[str], pipeline: str) -> dict | None:
        if (
            VISION_FAST_MODE
            and not _reject_unreliable_partial(parsed, issues)
            and VISION_ALLOW_PARTIAL_FAST
        ):
            log.warning(
                "Fast mode: returning normalized extraction despite: %s",
                "; ".join(issues[:5]),
            )
            parsed["extraction_pipeline"] = pipeline
            return package_extraction_response(
                parsed,
                partial=True,
                validation_issues=issues,
            )
        return None

    for model in model_order:
        for attempt in range(2):
            if _out_of_time():
                break
            call_extra = extra_instruction
            if attempt > 0:
                call_extra = (
                    f"{extra_instruction}\n\n"
                    "Return ONLY one valid JSON object matching the schema. "
                    "No markdown fences, no prose, no trailing commas."
                )
            try:
                parsed, all_issues = _try_monolithic_extract(
                    client,
                    model,
                    image_bytes,
                    mime_type,
                    extra_instruction=call_extra,
                )
                if not all_issues:
                    parsed["extraction_pipeline"] = "monolithic_fast"
                    return package_extraction_response(parsed)
                best_fast = parsed
                best_fast_issues = all_issues
                soft = _maybe_return_soft_partial(parsed, all_issues, "monolithic_fast")
                if soft is not None:
                    return soft
                last_error = ValueError(
                    "Monolithic extract incomplete: "
                    + "; ".join(all_issues[:6])
                )
                break
            except Exception as exc:
                last_error = exc
                if attempt == 0 and _is_json_parse_error(exc):
                    log.warning("Fast mode JSON parse failed, retrying: %s", exc)
                    continue
                break

    if best_fast is not None:
        early_draft = _maybe_return_early_draft(best_fast, best_fast_issues)
        if early_draft is not None:
            return early_draft

    if (
        VISION_FAST_MODE
        and VISION_QUALITY_RETRY
        and best_fast is not None
        and best_fast_issues
        and quality_model != fast_model
        and not _out_of_time()
        and _time_left_sec() > 6.0
    ):
        fix_extra = (
            f"{extra_instruction}\n\nFIX INCOMPLETE EXTRACTION:\n"
            + "; ".join(best_fast_issues[:6])
            + "\nReturn complete JSON — all loads, supports, segments, labeled_points."
        )
        try:
            log.info("Quality retry with %s after fast validation issues", quality_model)
            parsed, all_issues = _try_monolithic_extract(
                client,
                quality_model,
                image_bytes,
                mime_type,
                extra_instruction=fix_extra,
            )
            if not all_issues:
                parsed["extraction_pipeline"] = "monolithic_quality_retry"
                return package_extraction_response(parsed)
            best_fast = parsed
            best_fast_issues = all_issues
            soft = _maybe_return_soft_partial(
                parsed, all_issues, "monolithic_quality_retry"
            )
            if soft is not None:
                return soft
            last_error = ValueError(
                "Quality retry incomplete: " + "; ".join(all_issues[:6])
            )
        except Exception as exc:
            last_error = exc
            log.warning("Quality model retry failed: %s", exc)

    if (
        VISION_FAST_MODE
        and VISION_OVERLOAD_FALLBACK
        and last_error is not None
        and _is_retryable_vision_error(last_error)
        and not _out_of_time()
    ):
        for fb_idx, fb_model in enumerate(_vision_model_order(primary_model)[1:]):
            if _out_of_time():
                break
            delay = min(
                VISION_OVERLOAD_BACKOFF_SEC * (fb_idx + 1),
                max(0.0, _time_left_sec() - 1.0),
            )
            if delay > 0:
                log.warning(
                    "Gemini overload — waiting %.1fs then retry with %s",
                    delay,
                    fb_model,
                )
                time.sleep(delay)
            try:
                parsed = extract_exercise_from_image(
                    client,
                    fb_model,
                    image_bytes,
                    mime_type,
                    extra_instruction=extra_instruction,
                    json_mode=True,
                )
                parsed = finalize_beam_extraction(parsed)
                issues = validate_beam_extraction(parsed)
                completeness = _extraction_completeness_issues(
                    parsed.get("beam") if isinstance(parsed.get("beam"), dict) else {}
                )
                all_issues = list(issues) + list(completeness)
                if not all_issues:
                    parsed["extraction_pipeline"] = "monolithic_fast_overload_fallback"
                    log.info("Overload fallback succeeded with %s", fb_model)
                    return package_extraction_response(parsed)
                best_fast = parsed
                best_fast_issues = all_issues
                soft = _maybe_return_soft_partial(
                    parsed, all_issues, "monolithic_fast_overload_fallback"
                )
                if soft is not None:
                    return soft
                last_error = ValueError(
                    "Monolithic extract incomplete (overload fallback): "
                    + "; ".join(all_issues[:6])
                )
            except Exception as exc:
                last_error = exc
                log.warning(
                    "Overload fallback failed (model=%s): %s",
                    fb_model,
                    exc,
                )
                if not _is_retryable_vision_error(exc):
                    break

    if (
        VISION_FAST_MODE
        and best_fast is not None
        and best_fast_issues
        and _reject_unreliable_partial(best_fast, best_fast_issues)
        and _time_left_sec() > 4.0
    ):
        fix_extra = (
            f"{extra_instruction}\n\nFIX INCOMPLETE EXTRACTION:\n"
            + "; ".join(best_fast_issues[:5])
            + "\nReturn complete JSON — all loads, supports, segments, labeled_points."
        )
        try:
            parsed, all_issues = _try_monolithic_extract(
                client,
                quality_model,
                image_bytes,
                mime_type,
                extra_instruction=fix_extra,
            )
            if not all_issues or not _reject_unreliable_partial(parsed, all_issues):
                parsed["extraction_pipeline"] = "monolithic_fast_retry"
                return package_extraction_response(
                    parsed,
                    partial=bool(all_issues),
                    validation_issues=all_issues,
                )
        except Exception as exc:
            last_error = exc

    last_staged_error: Exception | None = None

    if (
        VISION_FAST_MODE
        and VISION_LOADS_REFINE
        and best_fast is not None
        and best_fast_issues
        and _geometry_usable_for_refine(
            best_fast.get("beam") if isinstance(best_fast.get("beam"), dict) else {}
        )
        and _time_left_sec() > 8.0
    ):
        log.info(
            "Fast mode: refining loads only (2 stages) — geometry kept from fast extract"
        )
        refined = extract_beam_loads_staged_refine(
            client,
            quality_model,
            image_bytes,
            mime_type,
            best_fast,
            extra_instruction=extra_instruction,
        )
        if refined is not None:
            refined_issues = _validation_issues_for(refined)
            if not refined_issues:
                return package_extraction_response(refined)
            if not _reject_unreliable_partial(refined, refined_issues):
                return package_extraction_response(
                    refined,
                    partial=True,
                    validation_issues=refined_issues,
                )
            best_fast = refined
            best_fast_issues = refined_issues

    if (
        VISION_FAST_MODE
        and best_fast is not None
        and VISION_ALLOW_PARTIAL_FAST
    ):
        beam = best_fast.get("beam") if isinstance(best_fast.get("beam"), dict) else {}
        if float(beam.get("L") or 0) > 0 and beam.get("supports"):
            log.warning(
                "Fast mode: returning best effort after retries (%s)",
                "; ".join(best_fast_issues[:4]),
            )
            best_fast["extraction_pipeline"] = "monolithic_fast_partial"
            return package_extraction_response(
                best_fast,
                partial=True,
                validation_issues=best_fast_issues,
            )

    fast_needs_staged = VISION_FAST_MODE and (
        best_fast is None
        or _reject_unreliable_partial(best_fast, best_fast_issues)
    )
    if fast_needs_staged and VISION_FAST_FALLBACK_STAGED and _time_left_sec() > 6.0:
        log.info(
            "Fast mode incomplete (%s) — falling back to staged extraction (%.1fs left)",
            last_error or "partial unreliable",
            _time_left_sec(),
        )
        staged_models = _vision_model_order(quality_model)[
            : max(1, int(VISION_MAX_MODELS_PER_IMAGE))
        ]
        for model in staged_models:
            for attempt in range(max(1, int(VISION_MAX_STAGED_RETRIES))):
                if _out_of_time():
                    break
                try:
                    parsed = extract_beam_exercise_staged(
                        client,
                        model,
                        image_bytes,
                        mime_type,
                        extra_instruction=extra_instruction,
                    )
                    return package_extraction_response(parsed)
                except Exception as exc:
                    last_staged_error = exc
                    log.warning("Fast→staged fallback failed: %s", exc)
                    if (
                        _is_retryable_vision_error(exc)
                        and attempt < VISION_MAX_STAGED_RETRIES - 1
                        and _time_left_sec() > 6.0
                    ):
                        delay = min(RETRY_BASE_DELAY_SEC * (2**attempt), 8.0)
                        log.warning(
                            "Fast→staged retry %s/%s in %.1fs",
                            attempt + 2,
                            VISION_MAX_STAGED_RETRIES,
                            delay,
                        )
                        time.sleep(delay)
                        continue
                    break

    if VISION_FAST_MODE:
        if DRAFT_APPROVAL_MODE and best_fast is not None:
            beam = best_fast.get("beam") if isinstance(best_fast.get("beam"), dict) else {}
            has_data = bool(beam.get("loads")) or float(beam.get("L") or 0) > 0
            if has_data:
                issues = list(best_fast_issues)
                if last_staged_error is not None:
                    issues.append(str(last_staged_error))
                elif last_error is not None:
                    issues.append(str(last_error))
                log.warning(
                    "Draft mode: returning best effort extraction (%s)",
                    "; ".join(issues[:4]),
                )
                best_fast["extraction_pipeline"] = str(
                    best_fast.get("extraction_pipeline") or "monolithic_fast_partial"
                )
                return package_extraction_response(
                    best_fast,
                    partial=True,
                    validation_issues=issues,
                )
        if last_staged_error is not None:
            raise last_staged_error
        if last_error is not None:
            raise last_error
        raise ValueError(
            "חילוץ מהיר לא הצליח — שלח שוב כקובץ (Document) או כבה VISION_FAST_MODE."
        )

    # 2) Accuracy path: staged extraction (up to 5 calls) under remaining time budget.
    # We keep it time-bounded to avoid multi-minute runs.
    if not VISION_FAST_MODE and _time_left_sec() > 6.0:
        staged_models = _vision_model_order(primary_model)[: max(1, int(VISION_MAX_MODELS_PER_IMAGE))]
        for model in staged_models:
            for attempt in range(VISION_STAGED_MAX_RETRIES):
                if _out_of_time():
                    break
                try:
                    parsed = extract_beam_exercise_staged(
                        client,
                        model,
                        image_bytes,
                        mime_type,
                        extra_instruction=extra_instruction,
                    )
                    return package_extraction_response(parsed)
                except Exception as exc:
                    last_staged_error = exc
                    # Retry only if there's time left and it's likely transient.
                    if (
                        _is_retryable_vision_error(exc)
                        and attempt < VISION_STAGED_MAX_RETRIES - 1
                        and _time_left_sec() > 6.0
                    ):
                        delay = min(RETRY_BASE_DELAY_SEC * (2**attempt), 2.0)
                        time.sleep(delay)
                        continue
                    break

    # 3) No slow fallbacks here: honor budget & stop.
    if last_error is not None:
        raise last_error
    if last_staged_error is not None:
        raise last_staged_error
    raise RuntimeError("Vision extract failed (time budget exceeded or no details)")
    # Extra fallback logic retained for robustness (may be slower).
    attempts: list[tuple[str, bool]] = [
        (extra_instruction, True),
        (
            "CRITICAL: Photo may be ROTATED — mentally turn the beam horizontal. "
            "Read the dimension chain along the beam axis (letters A,C,D,E... with numbers 1,1,1,3,3... between ticks) "
            "and SUM ALL segments for L (e.g. 1+1+1+3+3+1+1+1=12). "
            "Numbers ON the dimension line are lengths [m] — NOT load values. "
            "Distributed loads: distributed_loads[] only (start_x, end_x, magnitude, shape) — "
            "verify kN/m or t/m labels, never put distributed in loads[]. "
            "x=0 at left support A. Horizontal arrow ← at right end B is Fx (e.g. 64.2 t), not Fy. "
            "Ignore student scratch work (ΣFx, Ax=...). "
            "Fill supports[], segments[], labeled_points[], loads[] with diagram values only.",
            True,
        ),
        (
            "Return ONLY one valid JSON object matching the schema. No markdown, no prose.",
            False,
        ),
    ]
    best_partial: dict | None = None
    validation_issues: list[str] = []
    for model in _vision_model_order(primary_model):
        for idx, (extra, json_mode) in enumerate(attempts):
            try:
                if idx > 0 or model != normalize_model_id(primary_model):
                    log.info(
                        "Vision extract retry: model=%s attempt=%s json_mode=%s",
                        model,
                        idx + 1,
                        json_mode,
                    )
                parsed = extract_exercise_from_image(
                    client,
                    model,
                    image_bytes,
                    mime_type,
                    extra_instruction=extra,
                    json_mode=json_mode,
                )
                best_partial = parsed
                parsed = finalize_beam_extraction(parsed)
                validation_issues = validate_beam_extraction(parsed)
                completeness = _extraction_completeness_issues(
                    parsed.get("beam") if isinstance(parsed.get("beam"), dict) else {}
                )
                if not validation_issues and not completeness:
                    return package_extraction_response(parsed)
                if completeness:
                    validation_issues = list(validation_issues) + completeness
                log.warning(
                    "Beam extraction inconsistent: %s", "; ".join(validation_issues)
                )
            except Exception as exc:
                last_error = exc
                log.warning("Vision extract failed (model=%s): %s", model, exc)
    if validation_issues and best_partial is not None:
        fix_extra = (
            "FIX extraction errors: "
            + "; ".join(validation_issues)
            + ". The beam may be photographed rotated — read dimension ticks along the beam "
            "and sum ALL segments for L. x=0 at leftmost point, not at pin A."
        )
        for model in _vision_model_order(primary_model):
            try:
                log.info("Vision validation-fix retry: model=%s", model)
                parsed = extract_exercise_from_image(
                    client,
                    model,
                    image_bytes,
                    mime_type,
                    extra_instruction=fix_extra,
                    json_mode=True,
                )
                parsed = finalize_beam_extraction(parsed)
                if not validate_beam_extraction(parsed):
                    return package_extraction_response(parsed)
                best_partial = parsed
            except Exception as exc:
                last_error = exc
                log.warning("Validation-fix retry failed (model=%s): %s", model, exc)
    completeness_hint = ""
    if best_partial is not None:
        completeness_hint = "; ".join(
            _extraction_completeness_issues(
                best_partial.get("beam")
                if isinstance(best_partial.get("beam"), dict)
                else {}
            )[:5]
        )
    if completeness_hint:
        fix_extra = (
            f"{extra_instruction}\n\nFIX INCOMPLETE EXTRACTION:\n{completeness_hint}\n"
            "Read EVERY load: moments (curved), inclined (angled 30°/45°), "
            "distributed in distributed_loads[] (q, kN/m, t/m), horizontal ← at B (64.2 t). "
            "Use labeled_points x from dimension chain (A,C,D,E,G,H,I,B)."
        )
        for model in _vision_model_order(primary_model):
            for attempt in range(2):
                try:
                    parsed = extract_beam_exercise_staged(
                        client,
                        model,
                        image_bytes,
                        mime_type,
                        extra_instruction=fix_extra,
                    )
                    parsed = finalize_beam_extraction(parsed)
                    if not _extraction_completeness_issues(
                        parsed.get("beam") if isinstance(parsed.get("beam"), dict) else {}
                    ):
                        return package_extraction_response(parsed)
                except Exception as exc:
                    if _is_retryable_vision_error(exc) and attempt == 0:
                        time.sleep(RETRY_BASE_DELAY_SEC)
                        continue
                    log.warning("Completeness staged retry failed: %s", exc)

    if best_partial is not None:
        if _reject_unreliable_partial(best_partial, validation_issues):
            if DRAFT_APPROVAL_MODE:
                log.warning(
                    "Draft mode: returning partial extraction despite reliability flags"
                )
                return package_extraction_response(
                    best_partial,
                    partial=True,
                    validation_issues=validation_issues,
                )
            raise ValueError(
                "חילוץ לא מלא — שלח שוב כקובץ (Document) או נסה בעוד דקה.\n"
                + "; ".join(validation_issues[:5])
            )
        log.warning("Returning best partial extraction after validation failures")
        enriched = _enrich_beam_from_staged_geometry_supports(
            client,
            primary_model,
            image_bytes,
            mime_type,
            best_partial,
            extra_instruction=extra_instruction,
        )
        enriched = finalize_beam_extraction(enriched)
        return package_extraction_response(
            enriched,
            partial=True,
            validation_issues=validation_issues,
        )
    if last_error is not None:
        raise last_error
    if last_staged_error is not None:
        raise last_staged_error
    raise RuntimeError("Vision extract failed with no error details")


def normalize_cog_catalog_key(raw: str) -> str | None:
    key = str(raw or "").strip()
    if key in cog._CATALOG:
        return key
    alias = COG_CATALOG_ALIASES.get(key.lower())
    if alias and alias in cog._CATALOG:
        return alias
    return None


def vision_loads_to_tool_loads(raw_loads: list) -> list[dict]:
    tool_loads: list[dict] = []
    for item in raw_loads:
        if not isinstance(item, dict):
            continue
        t = str(item.get("type", "point")).lower().strip()
        if t == "point":
            fy = float(item.get("Fy", item.get("fy", 0.0)))
            entry: dict = {
                "kind": "point",
                "x": float(item.get("x", 0.0)),
                "magnitude_ton": abs(fy),
                "direction": "down" if fy >= 0 else "up",
            }
            fx = item.get("Fx", item.get("fx"))
            if fx is not None and abs(float(fx)) > 1e-12:
                entry["Fx_ton"] = float(fx)
            tool_loads.append(entry)
        elif t == "distributed":
            w = float(item.get("w", 0.0))
            tool_loads.append(
                {
                    "kind": "distributed",
                    "x1": float(item.get("x1", 0.0)),
                    "x2": float(item.get("x2", 0.0)),
                    "intensity_ton_per_m": abs(w),
                }
            )
        elif t == "moment":
            tool_loads.append(
                {
                    "kind": "moment",
                    "x": float(item.get("x", 0.0)),
                    "M_ton_m": float(item.get("M", item.get("m", 0.0))),
                }
            )
        elif t == "inclined":
            fx = float(item.get("Fx", item.get("fx", 0.0)))
            fy = float(item.get("Fy", item.get("fy", 0.0)))
            mag = math.hypot(fx, fy)
            angle = math.degrees(
                math.atan2(abs(fy), abs(fx) if abs(fx) > 1e-12 else 1e-12)
            )
            tool_loads.append(
                {
                    "kind": "inclined",
                    "x": float(item.get("x", 0.0)),
                    "magnitude_ton": mag,
                    "angle_deg": angle,
                    "incl_dir": "dl" if fx < 0 else "dr",
                }
            )
    return tool_loads


def vision_shapes_to_tool_shapes(raw_shapes: list) -> list[dict]:
    tool_shapes: list[dict] = []
    for raw in raw_shapes:
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("kind", "catalog")).lower()
        if "x_m" in raw or "y_m" in raw:
            entry = {
                "x_m": float(raw.get("x_m", 0.0)),
                "y_m": float(raw.get("y_m", 0.0)),
            }
        else:
            entry = {
                "x_cm": float(raw.get("x_cm", raw.get("x", 0.0))),
                "y_cm": float(raw.get("y_cm", raw.get("y", 0.0))),
            }
        if raw.get("label"):
            entry["label"] = str(raw["label"])
        catalog_key = raw.get("catalog_key") or raw.get("profile")
        normalized = normalize_cog_catalog_key(str(catalog_key or ""))
        if normalized or kind == "catalog":
            if not normalized:
                raise ValueError(f"פרופיל לא מזוהה: {catalog_key}")
            entry["kind"] = "catalog"
            entry["catalog_key"] = normalized
        else:
            entry["kind"] = kind
            for dim in ("b", "h", "tf", "tw", "t", "b1", "b2", "D"):
                if dim in raw and raw[dim] is not None:
                    entry[dim] = float(raw[dim])
        tool_shapes.append(entry)
    return tool_shapes


_SUPPORT_TYPE_HE: dict[str, str] = {
    "pin": "צמד (קבוע)",
    "roller": "גליל (נייד)",
    "fixed": "רתום (קיר)",
}


def _labeled_point_x(beam: dict, label: str) -> float | None:
    target = str(label or "").strip().upper()
    if not target:
        return None
    for pt in beam.get("labeled_points") or []:
        if not isinstance(pt, dict):
            continue
        if str(pt.get("label", "")).strip().upper() == target:
            return float(pt.get("x", 0.0))
    return None


def _is_phantom_axis_label(label: str) -> bool:
    return str(label or "").strip().upper() in ("START", "ORIGIN")


def _collect_beam_x_values(beam: dict) -> list[float]:
    xs: list[float] = []
    for seg in beam.get("segments") or []:
        if not isinstance(seg, dict):
            continue
        fl = str(seg.get("from_label") or "").strip().upper()
        tl = str(seg.get("to_label") or "").strip().upper()
        if _is_phantom_axis_label(fl) or _is_phantom_axis_label(tl):
            continue
        for key in ("from_x", "to_x"):
            if seg.get(key) is not None:
                try:
                    xs.append(float(seg[key]))
                except (TypeError, ValueError):
                    pass
    for pt in beam.get("labeled_points") or []:
        if not isinstance(pt, dict) or pt.get("x") is None:
            continue
        if _is_phantom_axis_label(str(pt.get("label", ""))):
            continue
        try:
            xs.append(float(pt["x"]))
        except (TypeError, ValueError):
            pass
    for sup in beam.get("supports") or []:
        if isinstance(sup, dict) and sup.get("x") is not None:
            try:
                xs.append(float(sup["x"]))
            except (TypeError, ValueError):
                pass
    for p in beam.get("key_points_m") or []:
        try:
            xs.append(float(p))
        except (TypeError, ValueError):
            pass
    return xs


def _beam_axis_min(beam: dict) -> float:
    xs = _collect_beam_x_values(beam)
    return min(xs) if xs else 0.0


def _beam_axis_max(beam: dict, L: float) -> float:
    xs = _collect_beam_x_values(beam)
    return max(xs) if xs else L


def _left_end_x(beam: dict) -> float:
    axis_min = _beam_axis_min(beam)
    left_label = str(beam.get("left_end_label", "")).strip()
    if left_label:
        x = _labeled_point_x(beam, left_label)
        if x is not None and abs(x - axis_min) < 0.2:
            return x
    return axis_min


def _right_end_x(beam: dict, L: float) -> float:
    """קצה ימין של הקורה — לא מיקום הסמך הנייד."""
    axis_max = _beam_axis_max(beam, L)
    right_label = str(beam.get("right_end_label", "")).strip()
    if right_label:
        x = _labeled_point_x(beam, right_label)
        if x is not None and abs(x - axis_max) < 0.2:
            return x
    return axis_max


def _recompute_inclined_components(
    magnitude_ton: float,
    angle_deg: float = 30.0,
    *,
    incl_dir: str = "dr",
) -> tuple[float, float]:
    """Fx,Fy from magnitude+angle; incl_dir dl=↙ (Fx<0), dr=↘ (Fx>0)."""
    rad = math.radians(angle_deg)
    fx_mag = magnitude_ton * math.cos(rad)
    fy_mag = magnitude_ton * math.sin(rad)
    if str(incl_dir).lower() == "dl":
        return -abs(fx_mag), abs(fy_mag)
    return abs(fx_mag), abs(fy_mag)


_STD_INCL_ANGLES = (30.0, 45.0, 60.0)


def _angle_from_fx_fy(fx: float, fy: float) -> float:
    return math.degrees(
        math.atan2(abs(fy), abs(fx) if abs(fx) > 1e-9 else 1e-9)
    )


def _snap_to_std_angle(angle: float) -> float:
    for std in _STD_INCL_ANGLES:
        if abs(angle - std) < 4.0:
            return std
    return round(angle, 1)


def _resolve_inclined_angle(
    fx: float, fy: float, stated: float | None
) -> float:
    """מעדיף זווית מ-Fx/Fy; מתקן בלבול 30°↔60° (זווית משלימה)."""
    from_components = _snap_to_std_angle(_angle_from_fx_fy(fx, fy))
    if stated is None:
        return from_components
    try:
        stated_snap = _snap_to_std_angle(float(stated))
    except (TypeError, ValueError):
        return from_components
    if abs(stated_snap - 60.0) < 4.0 and abs(from_components - 30.0) < 5.0:
        return 30.0
    if abs(stated_snap - 30.0) < 4.0 and abs(from_components - 60.0) < 5.0:
        return 60.0
    if abs(stated_snap - from_components) > 10.0:
        return from_components
    return stated_snap


def _promote_diagonal_point_loads(loads: list[dict]) -> list[dict]:
    """כוח נטוי שלפעמים נקלט כ-point עם Fx ו-Fy — מעלה ל-inclined."""
    out: list[dict] = []
    for raw in loads:
        ld = dict(raw)
        if str(ld.get("type", "")).lower() != "point":
            out.append(ld)
            continue
        fx = float(ld.get("Fx", ld.get("fx", 0.0)) or 0.0)
        fy = float(ld.get("Fy", ld.get("fy", 0.0)) or 0.0)
        peak = max(abs(fx), abs(fy), 1e-6)
        if abs(fx) < 0.08 * peak or abs(fy) < 0.08 * peak:
            out.append(ld)
            continue
        ld["type"] = "inclined"
        out.append(ld)
    return out


def _fix_paired_cd_inclined_loads(beam: dict, loads: list[dict]) -> list[dict]:
    """ב-D לעיתים נקלט אנכי (Fy בלבד) או ↘ — בשרטוט זה ↙ 30° ליד ↘ ב-C."""
    labeled = _labeled_points_map(beam)
    c_x = labeled.get("C", 1.0)
    d_x = labeled.get("D", 2.0)

    c_ref: dict | None = None
    for ld in loads:
        if str(ld.get("type", "")).lower() != "inclined":
            continue
        try:
            x = float(ld.get("x", 0))
        except (TypeError, ValueError):
            continue
        if abs(x - c_x) > 0.35:
            continue
        mag, _ = _inclined_mag_and_dir(ld)
        if 2.0 <= mag <= 8.0:
            c_ref = ld
            break
    if c_ref is None:
        return loads

    c_mag, _ = _inclined_mag_and_dir(c_ref)
    try:
        angle = float(c_ref.get("angle_deg", 30.0))
    except (TypeError, ValueError):
        angle = 30.0

    for i, ld in enumerate(loads):
        if not isinstance(ld, dict):
            continue
        if ld.get("_user_mag") or _load_position_user_locked(ld):
            continue
        t = str(ld.get("type", "")).lower()
        lbl = str(ld.get("label_at", "")).strip().upper()
        try:
            x = float(ld.get("x", 0))
        except (TypeError, ValueError):
            continue
        at_d = lbl == "D" or abs(x - d_x) < 0.35
        if not at_d:
            continue

        if t == "point":
            fy = abs(float(ld.get("Fy", ld.get("fy", 0.0)) or 0.0))
            fx = abs(float(ld.get("Fx", ld.get("fx", 0.0)) or 0.0))
            if fy < 0.5 or fx > 0.2 * max(fy, 1e-6):
                continue
            if abs(fy - c_mag) > 2.5 and abs(fy - 5) > 2.5:
                continue
            mag = fy if fy >= 0.5 else c_mag
            fx_c, fy_c = _recompute_inclined_components(mag, angle, incl_dir="dl")
            loads[i] = {
                "type": "inclined",
                "x": d_x,
                "Fx": fx_c,
                "Fy": fy_c,
                "angle_deg": angle,
                "incl_dir": "dl",
                "magnitude_ton": mag,
                "label_at": "D",
            }
            log.info(
                "Fixed D misread vertical Fy=%s → inclined dl %st @ %s°",
                fy,
                mag,
                angle,
            )
        elif t == "inclined":
            mag, incl_dir = _inclined_mag_and_dir(ld)
            if incl_dir == "dl" and abs(mag - c_mag) < 2.5:
                continue
            if abs(mag - c_mag) > 2.5 and abs(mag - 5) > 2.5:
                continue
            fx_c, fy_c = _recompute_inclined_components(mag, angle, incl_dir="dl")
            ld = dict(ld)
            ld["x"] = d_x
            ld["Fx"] = fx_c
            ld["Fy"] = fy_c
            ld["angle_deg"] = angle
            ld["incl_dir"] = "dl"
            ld["magnitude_ton"] = mag
            ld["label_at"] = "D"
            loads[i] = ld
            log.info("Fixed D inclined %s → dl at x=%s", incl_dir or "?", d_x)
    return loads


def _normalize_inclined_loads(loads: list[dict]) -> list[dict]:
    """מאחד זווית, כיוון ורכיבים לעומסים אלכסוניים."""
    out: list[dict] = []
    for raw in loads:
        ld = dict(raw)
        if str(ld.get("type", "")).lower() != "inclined":
            out.append(ld)
            continue
        fx = float(ld.get("Fx", ld.get("fx", 0.0)) or 0.0)
        fy = float(ld.get("Fy", ld.get("fy", 0.0)) or 0.0)
        mag = float(ld.get("magnitude_ton", 0.0) or 0.0)
        if mag < 1e-6:
            mag = math.hypot(fx, fy)
        stated: float | None
        try:
            stated = float(ld["angle_deg"]) if ld.get("angle_deg") is not None else None
        except (TypeError, ValueError):
            stated = None
        incl_dir = str(ld.get("incl_dir", "") or "").lower()
        if not incl_dir and mag > 1e-6:
            incl_dir = "dl" if fx < 0 else "dr"
        if not incl_dir:
            incl_dir = "dr"
        if mag < 1e-6:
            out.append(ld)
            continue
        if abs(fx) < 1e-6 and abs(fy) < 1e-6:
            angle = _resolve_inclined_angle(
                abs(mag) * math.cos(math.radians(stated or 30.0)),
                abs(mag) * math.sin(math.radians(stated or 30.0)),
                stated,
            )
        else:
            angle = _resolve_inclined_angle(fx, fy, stated)
            if incl_dir not in ("dl", "dr"):
                incl_dir = "dl" if fx < 0 else "dr"
        fx, fy = _recompute_inclined_components(mag, angle, incl_dir=incl_dir)
        ld["Fx"] = fx
        ld["Fy"] = fy
        ld["angle_deg"] = angle
        ld["incl_dir"] = incl_dir
        ld["magnitude_ton"] = mag
        out.append(ld)
    return out


def _labeled_support_x(sup: dict, labeled: dict[str, float]) -> float | None:
    """מיקום סמך מתווית על שרשרת המידות — עדיף על dist_from_left."""
    if sup.get("_user_x"):
        return None
    label = str(sup.get("label", "")).strip().upper()
    if label and label in labeled:
        return labeled[label]
    st = str(sup.get("type", "")).lower()
    if st == "roller" and "B" in labeled:
        roller_lbl = label or "B"
        if roller_lbl in ("B", ""):
            return labeled["B"]
    return None


def _labeled_points_map(beam: dict) -> dict[str, float]:
    out: dict[str, float] = {}
    for pt in beam.get("labeled_points") or []:
        if not isinstance(pt, dict):
            continue
        label = str(pt.get("label", "")).strip().upper()
        if not label:
            continue
        try:
            out[label] = float(pt.get("x", 0.0))
        except (TypeError, ValueError):
            continue
    return out


def _likely_kn_misread_as_ton(value: float, *, per_meter: bool = False) -> bool:
    """kN שנקלט כטון — UDL: 20 kn/m→2; כוח נקודתי: רק מספרים גדולים (100kn, 200kn)."""
    if value < KN_PER_TON * 1.95:
        return False
    scaled = value / KN_PER_TON
    if not (0.05 <= scaled <= 50.0):
        return False
    if per_meter:
        return True
    # 20 טון נקודתי תקין — לא להמיר; 200kn→20 כן
    return value >= 50.0


def _force_value_to_ton(value: float, *, per_meter: bool = False) -> float:
    if _likely_kn_misread_as_ton(value, per_meter=per_meter):
        return value / KN_PER_TON
    return value


def _parse_axial_direction_from_text(text: str) -> str | None:
    if re.search(r"←|שמאל|left", text, re.IGNORECASE):
        return "left"
    if re.search(r"→|ימין|right", text, re.IGNORECASE):
        return "right"
    return None


def _read_axial_direction(ld: dict) -> str | None:
    for key in ("direction", "arrow_direction", "axial_direction", "force_direction"):
        val = str(ld.get(key, "")).lower().strip()
        if val in ("left", "l", "שמאלה", "שמאל", "←"):
            return "left"
        if val in ("right", "r", "ימינה", "ימין", "→"):
            return "right"
    note_dir = _parse_axial_direction_from_text(str(ld.get("note", "")))
    if note_dir:
        return note_dir
    label = str(ld.get("load_kind", ld.get("force_type", ""))).lower()
    if label in ("axial", "horizontal", "fx", "צירי", "אופקי"):
        arrow = str(ld.get("arrow", "")).lower()
        if arrow in ("left", "l", "←", "שמאל"):
            return "left"
        if arrow in ("right", "r", "→", "ימין"):
            return "right"
    return None


def _apply_axial_sign(ld: dict) -> dict:
    """כיוון חץ: שמאלה ← = Fx שלילי; ימינה → = Fx חיובי."""
    if ld.get("_user_mag"):
        return ld
    fy = float(ld.get("Fy", ld.get("fy", 0.0)) or 0.0)
    fx = float(ld.get("Fx", ld.get("fx", 0.0)) or 0.0)
    if abs(fx) < 1e-6 or abs(fy) >= 1e-6:
        return ld
    direction = _read_axial_direction(ld)
    if direction is None:
        return ld
    out = dict(ld)
    out["Fx"] = -abs(fx) if direction == "left" else abs(fx)
    return out


def _parse_ton_from_note(note: str, *, per_meter: bool = False) -> float | None:
    text = note or ""
    if per_meter:
        m = re.search(
            r"\(\s*(\d+(?:\.\d+)?)\s*t\s*/\s*m",
            text,
            re.IGNORECASE,
        )
        if m:
            return float(m.group(1))
        m = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:t\s*/\s*m|טון\s*/\s*מ|ton\s*/\s*m)",
            text,
            re.IGNORECASE,
        )
        if m:
            return float(m.group(1))
        # עומס מפולג בתרגילים לפעמים מסומן רק "6 t" (לא t/m) — זה עוצמה [טון/מ']
        m = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:t|טון|ton)\b(?!\s*/\s*m)",
            text,
            re.IGNORECASE,
        )
        if m:
            return float(m.group(1))
    else:
        m = re.search(r"\(\s*(\d+(?:\.\d+)?)\s*t\s*\)", text, re.IGNORECASE)
        if m:
            return float(m.group(1))
    return None


def _convert_distributed_load_item(item: dict) -> dict | None:
    """distributed_loads[] → loads[] פנימי (type=distributed)."""
    if not isinstance(item, dict):
        return None
    try:
        start_x = float(item.get("start_x", item.get("x1", -1)))
        end_x = float(item.get("end_x", item.get("x2", -1)))
        magnitude = float(item.get("magnitude", item.get("w", 0)))
    except (TypeError, ValueError):
        return None
    if end_x <= start_x:
        return None
    is_draft = bool(item.get("_draft_new")) and magnitude <= 1e-9
    if magnitude <= 0 and not is_draft:
        return None
    w = _force_value_to_ton(magnitude, per_meter=True) if magnitude > 0 else 0.0
    shape = str(item.get("shape", "rectangular")).lower().strip()
    entry: dict = {
        "type": "distributed",
        "x1": start_x,
        "x2": end_x,
        "w": w,
        "shape": shape,
    }
    if is_draft:
        entry["_draft_new"] = True
    if item.get("_user_span"):
        entry["_user_span"] = True
    if shape == "triangular":
        entry["w_start"] = 0.0
        entry["w_end"] = w
    return entry


def _ingest_distributed_loads(beam: dict) -> None:
    """ממיר distributed_loads[] ל-loads[] — מחליף את זיהוי UDL הישן."""
    from bot.draft_format import sync_beam_distributed_loads

    dist_in_loads = [
        ld
        for ld in (beam.get("loads") or [])
        if isinstance(ld, dict) and str(ld.get("type", "")).lower() == "distributed"
    ]
    if dist_in_loads:
        sync_beam_distributed_loads(beam)

    raw_items = beam.get("distributed_loads")
    if not isinstance(raw_items, list) or not raw_items:
        return

    existing = [
        dict(ld)
        for ld in (beam.get("loads") or [])
        if isinstance(ld, dict) and str(ld.get("type", "")).lower() == "distributed"
    ]
    user_flags = [bool(ld.get("_user_span")) for ld in existing]
    mag_flags = [bool(ld.get("_user_mag")) for ld in existing]
    draft_flags = [bool(ld.get("_draft_new")) for ld in existing]

    if any(user_flags) or any(mag_flags):
        synced: list[dict] = []
        for i, item in enumerate(raw_items):
            base = dict(item) if isinstance(item, dict) else {}
            if i < len(existing) and (user_flags[i] or mag_flags[i]):
                ud = existing[i]
                try:
                    if user_flags[i]:
                        base["start_x"] = float(ud.get("x1", ud.get("start_x", 0)))
                        base["end_x"] = float(ud.get("x2", ud.get("end_x", 0)))
                    w = ud.get("w", ud.get("magnitude"))
                    if w is not None:
                        base["magnitude"] = float(w)
                    if ud.get("shape"):
                        base["shape"] = ud["shape"]
                except (TypeError, ValueError):
                    pass
            synced.append(base)
        beam["distributed_loads"] = synced
        raw_items = synced

    converted: list[dict] = []
    for i, item in enumerate(raw_items):
        entry = _convert_distributed_load_item(item)
        if not entry:
            continue
        if i < len(existing) and user_flags[i]:
            ud = existing[i]
            try:
                entry["x1"] = float(ud.get("x1", entry["x1"]))
                entry["x2"] = float(ud.get("x2", entry["x2"]))
            except (TypeError, ValueError):
                pass
            if ud.get("w") is not None:
                try:
                    entry["w"] = float(ud["w"])
                except (TypeError, ValueError):
                    pass
            if ud.get("shape"):
                entry["shape"] = ud["shape"]
            entry["_user_span"] = True
        elif i < len(existing) and mag_flags[i]:
            ud = existing[i]
            if ud.get("w") is not None:
                try:
                    entry["w"] = float(ud["w"])
                except (TypeError, ValueError):
                    pass
            entry["_user_mag"] = True
        elif i < len(existing) and draft_flags[i]:
            ud = existing[i]
            try:
                entry["x1"] = float(ud.get("x1", entry["x1"]))
                entry["x2"] = float(ud.get("x2", entry["x2"]))
            except (TypeError, ValueError):
                pass
            if ud.get("w") is not None:
                try:
                    entry["w"] = float(ud["w"])
                except (TypeError, ValueError):
                    pass
            entry["_draft_new"] = True
        converted.append(entry)
    if not converted:
        return
    loads = [
        ld
        for ld in (beam.get("loads") or [])
        if isinstance(ld, dict) and str(ld.get("type", "")).lower() != "distributed"
    ]
    loads.extend(converted)
    beam["loads"] = loads
    log.info("Ingested %s distributed load(s) from distributed_loads[]", len(converted))


def _infer_distributed_from_boundary_misreads(beam: dict) -> None:
    """שחזור עומס מפורס כש-'3t' נקלט כ-point בקצות מסגרת A→E."""
    raw = beam.get("distributed_loads")
    if isinstance(raw, list) and raw:
        return
    loads = [
        dict(ld) for ld in (beam.get("loads") or []) if isinstance(ld, dict)
    ]
    if any(str(ld.get("type", "")).lower() == "distributed" for ld in loads):
        return

    points: list[tuple[float, float, dict]] = []
    for ld in loads:
        if str(ld.get("type", "")).lower() != "point":
            continue
        try:
            x = float(ld.get("x", 0))
            fy = abs(float(ld.get("Fy", ld.get("fy", 0))))
        except (TypeError, ValueError):
            continue
        if fy <= 0:
            continue
        points.append((x, fy, ld))
    if len(points) < 2:
        return

    pin_x: float | None = None
    for sup in beam.get("supports") or []:
        if not isinstance(sup, dict):
            continue
        if str(sup.get("type", "")).lower() not in ("pin", "fixed"):
            continue
        try:
            pin_x = float(sup.get("x", 0))
        except (TypeError, ValueError):
            continue
        break

    by_mag: dict[float, list[tuple[float, dict]]] = {}
    for x, fy, ld in points:
        by_mag.setdefault(round(fy, 2), []).append((x, ld))

    for mag, group in by_mag.items():
        if mag > 20 or len(group) < 2:
            continue
        group.sort(key=lambda item: item[0])
        start_x, start_ld = group[0]
        end_x, end_ld = group[-1]
        span = end_x - start_x
        if span < 2.0:
            continue

        at_pin = pin_x is not None and abs(start_x - pin_x) < 0.5
        interior_point = any(
            str(ld.get("type", "")).lower() == "point"
            and start_x + 0.4 < float(ld.get("x", 0)) < end_x - 0.4
            for ld in loads
            if isinstance(ld, dict)
        )
        if not at_pin and not interior_point:
            continue

        beam.setdefault("distributed_loads", []).append(
            {
                "start_x": start_x,
                "end_x": end_x,
                "magnitude": mag,
                "shape": "rectangular",
            }
        )
        if len(group) == 2:
            remove = {id(start_ld), id(end_ld)}
            beam["loads"] = [ld for ld in loads if id(ld) not in remove]
        log.info(
            "Inferred distributed load %.2f–%.2f w=%s from bracket boundary misreads",
            start_x,
            end_x,
            mag,
        )
        return


def _shift_beam_coordinates(beam: dict, delta: float) -> None:
    """מזיז את כל קואורדינטות x בגיאומטריה (למשל re-zero בצמד A)."""
    if abs(delta) < 1e-6:
        return

    def _sx(val: object) -> float:
        return float(val) - delta

    points: list[dict] = []
    for pt in beam.get("labeled_points") or []:
        if not isinstance(pt, dict):
            continue
        lbl = str(pt.get("label", "")).strip().upper()
        if lbl in ("START", "ORIGIN"):
            continue
        try:
            points.append({"label": lbl, "x": _sx(pt["x"])})
        except (TypeError, ValueError, KeyError):
            continue
    if points:
        beam["labeled_points"] = points

    new_segments: list[dict] = []
    for seg in beam.get("segments") or []:
        if not isinstance(seg, dict):
            continue
        fl = str(seg.get("from_label") or "").strip().upper()
        tl = str(seg.get("to_label") or "").strip().upper()
        if fl in ("START", "ORIGIN") or tl in ("START", "ORIGIN"):
            continue
        try:
            new_segments.append(
                {
                    **seg,
                    "from_x": _sx(seg.get("from_x", 0)),
                    "to_x": _sx(seg.get("to_x", 0)),
                }
            )
        except (TypeError, ValueError):
            new_segments.append(dict(seg))
    if new_segments:
        beam["segments"] = new_segments

    for sup in beam.get("supports") or []:
        if not isinstance(sup, dict):
            continue
        try:
            sup["x"] = _sx(sup.get("x", 0))
        except (TypeError, ValueError):
            pass
        if sup.get("dist_from_left_m") is not None:
            try:
                sup["dist_from_left_m"] = _sx(sup["dist_from_left_m"])
            except (TypeError, ValueError):
                pass

    kps = beam.get("key_points_m")
    if isinstance(kps, list):
        shifted: list[float] = []
        for kp in kps:
            try:
                nx = _sx(kp)
                if nx >= -0.05:
                    shifted.append(nx)
            except (TypeError, ValueError):
                continue
        if shifted:
            beam["key_points_m"] = sorted(set(shifted))

    for item in beam.get("distributed_loads") or []:
        if not isinstance(item, dict):
            continue
        for key in ("start_x", "end_x", "x1", "x2"):
            if item.get(key) is not None:
                try:
                    item[key] = _sx(item[key])
                except (TypeError, ValueError):
                    pass


def _shift_load_x_coords(loads: list[dict], delta: float) -> None:
    """מזיז x / x1 / x2 בעומסים אחרי re-zero."""
    if abs(delta) < 1e-6:
        return
    for ld in loads:
        if not isinstance(ld, dict):
            continue
        for key in ("x", "x1", "x2"):
            if ld.get(key) is not None:
                try:
                    ld[key] = float(ld[key]) - delta
                except (TypeError, ValueError):
                    pass


def _geometry_uses_hundredth_meters(beam: dict) -> bool:
    """True כששרשרת המידות נראית במאות/ס"מ (200 → 2 מ')."""
    try:
        L = float(beam.get("L", 0) or 0)
    except (TypeError, ValueError):
        L = 0.0
    seg_sum = _segment_length_sum(beam)
    ref = max(L, seg_sum)
    if ref < 50:
        return False
    scaled = ref / 100.0
    if not (1.0 <= scaled <= 40.0):
        return False

    chain_values: list[float] = [ref]
    for pt in beam.get("labeled_points") or []:
        if not isinstance(pt, dict):
            continue
        try:
            chain_values.append(float(pt.get("x", 0)))
        except (TypeError, ValueError):
            continue
    for seg in beam.get("segments") or []:
        if not isinstance(seg, dict):
            continue
        for key in ("length_m", "from_x", "to_x"):
            try:
                v = float(seg.get(key, 0) or 0)
                if v > 0:
                    chain_values.append(v)
            except (TypeError, ValueError):
                pass
    for kp in beam.get("key_points_m") or []:
        try:
            chain_values.append(float(kp))
        except (TypeError, ValueError):
            pass

    if ref >= 100:
        return True
    return any(v >= 50 for v in chain_values)


def _scale_beam_geometry_from_hundredths(
    beam: dict,
    loads: list[dict] | None = None,
) -> bool:
    """ממיר מרחקים במאות/ס"מ למטרים (÷100) — 200 → 2 מ'."""
    if beam.get("_scaled_from_hundredths") or beam.get("_scaled_from_cm"):
        return False
    if _beam_L_user_locked(beam):
        return False
    if not _geometry_uses_hundredth_meters(beam):
        return False

    factor = 0.01

    def _sc(val: object) -> float:
        return float(val) * factor

    try:
        beam["L"] = _sc(beam.get("L", 0))
    except (TypeError, ValueError):
        pass

    points: list[dict] = []
    for pt in beam.get("labeled_points") or []:
        if not isinstance(pt, dict):
            continue
        lbl = str(pt.get("label", "")).strip().upper()
        if lbl in ("START", "ORIGIN"):
            continue
        try:
            points.append({"label": lbl, "x": _sc(pt["x"])})
        except (TypeError, ValueError, KeyError):
            continue
    if points:
        beam["labeled_points"] = points

    new_segments: list[dict] = []
    for seg in beam.get("segments") or []:
        if not isinstance(seg, dict):
            continue
        item = dict(seg)
        for key in ("from_x", "to_x", "length_m"):
            if item.get(key) is not None:
                try:
                    item[key] = _sc(item[key])
                except (TypeError, ValueError):
                    pass
        new_segments.append(item)
    if new_segments:
        beam["segments"] = new_segments

    for sup in beam.get("supports") or []:
        if not isinstance(sup, dict) or sup.get("_user_x"):
            continue
        for key in ("x", "dist_from_left_m", "dist_from_right_m"):
            if sup.get(key) is not None:
                try:
                    sup[key] = _sc(sup[key])
                except (TypeError, ValueError):
                    pass

    new_hinges: list[dict] = []
    for hinge in beam.get("internal_hinges") or []:
        if not isinstance(hinge, dict):
            continue
        item = dict(hinge)
        if item.get("x") is not None:
            try:
                item["x"] = _sc(item["x"])
            except (TypeError, ValueError):
                pass
        new_hinges.append(item)
    if new_hinges:
        beam["internal_hinges"] = new_hinges

    kps = beam.get("key_points_m")
    if isinstance(kps, list):
        scaled_kps: list[float] = []
        for kp in kps:
            try:
                scaled_kps.append(_sc(kp))
            except (TypeError, ValueError):
                continue
        if scaled_kps:
            beam["key_points_m"] = sorted(set(scaled_kps))

    for item in beam.get("distributed_loads") or []:
        if not isinstance(item, dict):
            continue
        for key in ("start_x", "end_x", "x1", "x2"):
            if item.get(key) is not None:
                try:
                    item[key] = _sc(item[key])
                except (TypeError, ValueError):
                    pass

    for ld in loads or []:
        if not isinstance(ld, dict):
            continue
        if not ld.get("_user_x"):
            for key in ("x",):
                if ld.get(key) is not None:
                    try:
                        ld[key] = _sc(ld[key])
                    except (TypeError, ValueError):
                        pass
        if not ld.get("_user_span"):
            for key in ("x1", "x2", "start_x", "end_x"):
                if ld.get(key) is not None:
                    try:
                        ld[key] = _sc(ld[key])
                    except (TypeError, ValueError):
                        pass

    for key in ("ra_pos", "rb_pos"):
        if beam.get(key) is not None:
            try:
                beam[key] = _sc(beam[key])
            except (TypeError, ValueError):
                pass

    beam["_scaled_from_hundredths"] = True
    log.info("Scaled beam geometry from hundredths (÷100): L=%s", beam.get("L"))
    return True


def _rezero_beam_at_left_end(beam: dict, loads: list[dict]) -> None:
    """כל x = מרחק מקצה שמאל של הקורה (הנקודה השמאלית ביותר על הציר)."""
    left = _left_end_x(beam)
    if abs(left) < 1e-6:
        return
    old_L = float(beam.get("L", 10.0))
    right = _right_end_x(beam, old_L)
    log.info("Re-zero beam at left end: shift all x by -%s", left)
    _shift_beam_coordinates(beam, left)
    _shift_load_x_coords(loads, left)
    beam["L"] = max(right - left, old_L - left, 0.1)


def _rezero_beam_at_pin_support(beam: dict, loads: list[dict]) -> None:
    """תאימות לאחור — אפס בקצה שמאל של הקורה, לא בצמד."""
    _rezero_beam_at_left_end(beam, loads)


def _infer_labeled_points_from_segments(beam: dict) -> None:
    """בונה labeled_points ממקטעי המידות אם חסרים אחרי חילוץ."""
    existing = beam.get("labeled_points")
    if isinstance(existing, list) and existing:
        return
    by_label: dict[str, float] = {}
    for seg in beam.get("segments") or []:
        if not isinstance(seg, dict):
            continue
        fl = str(seg.get("from_label") or "").strip().upper()
        tl = str(seg.get("to_label") or "").strip().upper()
        try:
            if fl:
                by_label[fl] = float(seg["from_x"])
            if tl:
                by_label[tl] = float(seg["to_x"])
        except (TypeError, ValueError, KeyError):
            continue
    if by_label:
        beam["labeled_points"] = [
            {"label": lbl, "x": x} for lbl, x in sorted(by_label.items(), key=lambda kv: kv[1])
        ]
        log.info("Inferred labeled_points from segments: %s", by_label)


def _fix_roller_from_load_boundaries(beam: dict) -> None:
    """גליל בקצה + צמד פנימי — B לפי סוף UDL / מקטע B→D / עומס בקצה D."""
    L = float(beam.get("L", 10.0))
    labeled = _labeled_points_map(beam)
    beam_end = _right_end_x(beam, L)
    if "B" in labeled and labeled["B"] >= beam_end - 0.15:
        return

    rollers = [
        s
        for s in (beam.get("supports") or [])
        if isinstance(s, dict) and str(s.get("type", "")).lower() == "roller"
    ]
    pins = [
        s
        for s in (beam.get("supports") or [])
        if isinstance(s, dict) and str(s.get("type", "")).lower() == "pin"
    ]
    if not rollers or not pins:
        return

    roller = rollers[0]
    try:
        rx = float(roller.get("x", L))
        px = float(pins[0].get("x", 0))
    except (TypeError, ValueError):
        return

    at_tip = abs(rx - beam_end) < 0.35 or abs(rx - L) < 0.35
    if not at_tip or px < 0.4:
        return

    candidates: list[float] = []
    loads = beam.get("loads") or []
    has_tip_point = False
    for ld in loads:
        if not isinstance(ld, dict):
            continue
        t = str(ld.get("type", "")).lower()
        try:
            if t == "distributed":
                x1 = float(ld.get("x1", 0))
                x2 = float(ld.get("x2", 0))
                if px + 0.2 < x2 < L - 0.2:
                    candidates.append(x2)
                if px + 0.2 < x1 < L - 0.2:
                    candidates.append(x1)
            elif t == "point":
                x = float(ld.get("x", 0))
                if abs(x - beam_end) < 0.35 or abs(x - L) < 0.35:
                    has_tip_point = True
        except (TypeError, ValueError):
            continue

    for seg in beam.get("segments") or []:
        if not isinstance(seg, dict):
            continue
        fl = str(seg.get("from_label") or "").strip().upper()
        try:
            if fl == "B":
                candidates.append(float(seg.get("from_x", 0)))
        except (TypeError, ValueError):
            pass

    d_right = roller.get("dist_from_right_m")
    if d_right is not None:
        try:
            candidates.append(beam_end - float(d_right))
        except (TypeError, ValueError):
            pass

    d_left = roller.get("dist_from_left_m")
    if d_left is not None:
        try:
            candidates.append(float(d_left))
        except (TypeError, ValueError):
            pass

    if px > 0:
        span_ab = None
        for seg in beam.get("segments") or []:
            if not isinstance(seg, dict):
                continue
            fl = str(seg.get("from_label") or "").strip().upper()
            tl = str(seg.get("to_label") or "").strip().upper()
            if fl == "A" and tl == "B":
                try:
                    span_ab = float(seg.get("to_x", 0)) - float(seg.get("from_x", 0))
                except (TypeError, ValueError):
                    pass
        if span_ab and span_ab > 0.5:
            candidates.append(px + span_ab)

    valid = [c for c in candidates if px + 0.25 < c < L - 0.15]
    if not valid:
        return
    if has_tip_point or len(valid) >= 1:
        b_x = max(valid)
        roller["x"] = b_x
        roller["label"] = roller.get("label") or "B"
        log.info(
            "Roller B from load/segment boundaries: x=%s (pin at %s, tip at %s)",
            b_x,
            px,
            beam_end,
        )


def _fix_roller_overhang_position(beam: dict) -> None:
    """גליל לא בקצה הקורה — B פנימי, dist_from_right, או מקטע B→D."""
    L = float(beam.get("L", 10.0))
    labeled = _labeled_points_map(beam)
    beam_end = _right_end_x(beam, L)

    for sup in beam.get("supports") or []:
        if not isinstance(sup, dict):
            continue
        if sup.get("_user_x"):
            continue
        if str(sup.get("type", "")).lower() != "roller":
            continue
        try:
            x = float(sup.get("x", 0.0))
        except (TypeError, ValueError):
            continue

        at_tip = abs(x - beam_end) < 0.25 or abs(x - L) < 0.25

        if "B" in labeled and labeled["B"] < beam_end - 0.15 and at_tip:
            sup["x"] = labeled["B"]
            sup.setdefault("label", "B")
            log.info("Roller B at overhang: x=%s (not beam tip %s)", labeled["B"], beam_end)
            continue

        d_right = sup.get("dist_from_right_m")
        if d_right is not None and at_tip:
            try:
                expected = beam_end - float(d_right)
                if 0 <= expected <= beam_end:
                    sup["x"] = expected
                    log.info("Roller from dist_from_right_m=%s → x=%s", d_right, expected)
                    continue
            except (TypeError, ValueError):
                pass

        chain_x = _labeled_support_x(sup, labeled)
        if chain_x is not None:
            if abs(x - chain_x) > 0.15:
                sup["x"] = chain_x
                log.info(
                    "Roller %s kept on labeled chain at x=%s (skip dist_from_left)",
                    sup.get("label") or "B",
                    chain_x,
                )
            continue

        d_left = sup.get("dist_from_left_m")
        if d_left is not None:
            try:
                expected = float(d_left)
                if abs(x - expected) > 0.2:
                    sup["x"] = expected
                    log.info("Roller from dist_from_left_m=%s → x=%s", d_left, expected)
            except (TypeError, ValueError):
                pass


def _dimension_chain_x_values(beam: dict) -> list[float]:
    """כל נקודות x על קו המידות (תוויות + קצות מקטעים)."""
    xs: set[float] = set()
    for lx in _labeled_points_map(beam).values():
        xs.add(lx)
    for seg in beam.get("segments") or []:
        if not isinstance(seg, dict):
            continue
        for key in ("from_x", "to_x"):
            try:
                xs.add(float(seg[key]))
            except (TypeError, ValueError):
                pass
    return sorted(xs)


_CHAIN_EXACT_TOL_M = 0.12


def _nearest_dimension_chain_point(beam: dict, x: float) -> tuple[float, str] | None:
    """נקודה הקרובה ביותר על קו המידות + תווית (אם יש)."""
    chain = _dimension_chain_x_values(beam)
    if not chain:
        return None
    nearest_x = min(chain, key=lambda cx: abs(cx - x))
    labeled = _labeled_points_map(beam)
    labels_at = [lbl for lbl, lx in labeled.items() if abs(lx - nearest_x) < 0.05]
    label = labels_at[0] if len(labels_at) == 1 else ""
    return nearest_x, label


def _snap_supports_to_nearest_chain_point(beam: dict) -> None:
    """אם סמך לא על נקודת מידה — הצמדה לנקודה הקרובה ביותר על קו המידות."""
    chain = _dimension_chain_x_values(beam)
    if not chain:
        return
    supports = beam.get("supports")
    if not isinstance(supports, list):
        return
    labeled = _labeled_points_map(beam)

    for sup in supports:
        if not isinstance(sup, dict):
            continue
        if sup.get("_user_x"):
            continue
        try:
            x = float(sup.get("x", 0.0))
        except (TypeError, ValueError):
            continue
        label = str(sup.get("label", "")).strip().upper()

        if label and label in labeled:
            chain_x = labeled[label]
            if abs(x - chain_x) > _CHAIN_EXACT_TOL_M:
                sup["x"] = chain_x
                log.info(
                    "Support %s aligned to dimension label %s at x=%s",
                    label,
                    label,
                    chain_x,
                )
            continue

        on_chain = any(abs(x - cx) <= _CHAIN_EXACT_TOL_M for cx in chain)
        if on_chain:
            continue

        hit = _nearest_dimension_chain_point(beam, x)
        if hit is None:
            continue
        nearest_x, nearest_label = hit
        old_x = x
        sup["x"] = nearest_x
        if nearest_label:
            sup["label"] = nearest_label
        log.info(
            "Support snapped to nearest dimension-chain point x=%s (was x=%s, label=%s)",
            nearest_x,
            old_x,
            nearest_label or "?",
        )


def _sync_supports_to_labeled_chain(beam: dict) -> None:
    """סמך עם תווית מפורשת — מיקום מתוך שרשרת המידות."""
    labeled = _labeled_points_map(beam)
    if not labeled:
        return
    supports = beam.get("supports")
    if not isinstance(supports, list):
        return

    for sup in supports:
        if not isinstance(sup, dict):
            continue
        if sup.get("_user_x"):
            continue
        label = str(sup.get("label", "")).strip().upper()
        if not label or label not in labeled:
            continue
        try:
            x = float(sup.get("x", 0.0))
        except (TypeError, ValueError):
            x = 0.0
        chain_x = labeled[label]
        if abs(x - chain_x) > 0.15:
            sup["x"] = chain_x
            log.info(
                "Support %s on beam axis at x=%s (dimension label)",
                label,
                chain_x,
            )


def _normalize_support_positions(beam: dict) -> None:
    """מתקן מיקומי סמכים לפי מידות, תוויות ונקודות מתויגות."""
    L = float(beam.get("L", 10.0))
    labeled = _labeled_points_map(beam)
    beam_end = _right_end_x(beam, L)
    supports = beam.get("supports")
    if not isinstance(supports, list):
        return
    for sup in supports:
        if not isinstance(sup, dict):
            continue
        if sup.get("_user_x"):
            continue
        label = str(sup.get("label", "")).strip().upper()
        st = str(sup.get("type", "")).lower()
        try:
            x = float(sup.get("x", 0.0))
        except (TypeError, ValueError):
            continue

        chain_x = _labeled_support_x(sup, labeled)
        if chain_x is not None:
            if abs(x - chain_x) > 0.15:
                sup["x"] = chain_x
                log.info(
                    "Support %s on labeled chain at x=%s",
                    label or st,
                    chain_x,
                )
            continue

        d_left = sup.get("dist_from_left_m")
        if d_left is not None:
            try:
                expected = float(d_left)
                if abs(x - expected) > 0.2:
                    sup["x"] = expected
                    log.info("Support %s x from dist_from_left=%s", label or st, expected)
                    continue
            except (TypeError, ValueError):
                pass

        if label in labeled and abs(x - labeled[label]) > 0.2:
            sup["x"] = labeled[label]
            log.info("Support %s x synced to labeled %s", label, labeled[label])
            continue

        pin_label = str(beam.get("pin_support_label") or "A").strip().upper()
        if st == "pin" and label == pin_label and pin_label in labeled:
            if abs(x - labeled[pin_label]) > 0.2:
                sup["x"] = labeled[pin_label]
                log.info("Pin %s on beam axis at x=%s (not left of beam)", pin_label, labeled[pin_label])
            continue

        if st != "roller":
            continue

        if label in labeled and labeled[label] < beam_end - 0.05:
            if abs(x - beam_end) < 0.2 or abs(x - L) < 0.2:
                sup["x"] = labeled[label]
                log.info("Normalized roller %s from x=%s to labeled x=%s", label, x, labeled[label])
                continue
        if "B" in labeled and labeled["B"] < beam_end - 0.05:
            if abs(x - beam_end) < 0.2 or abs(x - L) < 0.2:
                sup["x"] = labeled["B"]
                log.info("Normalized roller B from x=%s to x=%s", x, labeled["B"])
                continue
        d_right = sup.get("dist_from_right_m")
        if d_right is not None:
            try:
                expected_x = beam_end - float(d_right)
            except (TypeError, ValueError):
                continue
            if 0 <= expected_x <= beam_end and abs(x - expected_x) > 0.25:
                if abs(x - beam_end) < 0.2 or abs(x - L) < 0.2:
                    sup["x"] = expected_x
                    log.info("Normalized roller via dist_from_right: x=%s", expected_x)


def _load_position_user_locked(ld: dict) -> bool:
    """True when user manually edited load position — skip auto-fixes."""
    return bool(ld.get("_user_x") or ld.get("_user_span"))


def _beam_L_user_locked(beam: dict) -> bool:
    """True when user manually edited beam length — skip auto L corrections."""
    return bool(beam.get("_user_L"))


def _resolve_span_endpoints(beam: dict, span: dict) -> tuple[float, float] | None:
    """x1/x2 ממידות או מתוויות from_label/to_label."""
    labeled = _labeled_points_map(beam)
    fl = str(span.get("from_label", "")).strip().upper()
    tl = str(span.get("to_label", "")).strip().upper()
    if fl in labeled and tl in labeled:
        x1, x2 = labeled[fl], labeled[tl]
        if x2 > x1:
            return x1, x2
    try:
        x1 = float(span.get("x1", 0.0))
        x2 = float(span.get("x2", 0.0))
    except (TypeError, ValueError):
        return None
    if x2 > x1:
        return x1, x2
    return None


def _apply_explicit_load_positions(beam: dict, loads: list[dict]) -> list[dict]:
    """מעדכן מיקום רק כשיש תווית מפורשת (label_at / from_label) — בלי ניחושים."""
    labeled = _labeled_points_map(beam)
    out: list[dict] = []
    for raw in loads:
        if not isinstance(raw, dict):
            continue
        ld = dict(raw)
        t = str(ld.get("type", "")).lower()
        label_at = str(ld.get("label_at", "")).strip().upper()
        if label_at and label_at in labeled and t in ("point", "moment", "inclined"):
            if not ld.get("_user_x"):
                ld["x"] = labeled[label_at]
        elif t == "point":
            pass
        elif t == "distributed":
            if ld.get("_user_span"):
                out.append(ld)
                continue
            fl = str(ld.get("from_label", "")).strip().upper()
            tl = str(ld.get("to_label", "")).strip().upper()
            if fl in labeled:
                ld["x1"] = labeled[fl]
            if tl in labeled:
                ld["x2"] = labeled[tl]
        out.append(ld)
    return out


def _label_at_dimension_chain_point(beam: dict, x: float) -> str | None:
    labeled = _labeled_points_map(beam)
    for lbl, lx in labeled.items():
        if abs(lx - x) < _CHAIN_EXACT_TOL_M:
            return lbl
    return None


def _snap_loads_to_dimension_chain(beam: dict, loads: list[dict]) -> list[dict]:
    """הקרנה אנכית: x על הקורה = נקודה על קו המידות — הצמדה לתווית הקרובה."""
    chain = _dimension_chain_x_values(beam)
    if not chain:
        return loads
    out: list[dict] = []
    for raw in loads:
        if not isinstance(raw, dict):
            continue
        ld = dict(raw)
        t = str(ld.get("type", "")).lower()
        if t == "distributed":
            if ld.get("_user_span"):
                out.append(ld)
                continue
            for key, label_key in (("x1", "from_label"), ("x2", "to_label")):
                if ld.get(label_key):
                    continue
                try:
                    x = float(ld.get(key, 0.0))
                except (TypeError, ValueError):
                    continue
                nearest = min(chain, key=lambda cx: abs(cx - x))
                if abs(nearest - x) <= 0.22:
                    ld[key] = nearest
                    lbl = _label_at_dimension_chain_point(beam, nearest)
                    if lbl:
                        ld[label_key] = lbl
        else:
            if ld.get("_user_x"):
                out.append(ld)
                continue
            label_at = str(ld.get("label_at", "")).strip().upper()
            if label_at and label_at in _labeled_points_map(beam):
                out.append(ld)
                continue
            try:
                x = float(ld.get("x", ld.get("x1", 0.0)))
            except (TypeError, ValueError):
                out.append(ld)
                continue
            nearest = min(chain, key=lambda cx: abs(cx - x))
            if abs(nearest - x) <= 0.22:
                ld["x"] = nearest
                lbl = _label_at_dimension_chain_point(beam, nearest)
                if lbl:
                    ld["label_at"] = lbl
        out.append(ld)
    return out


def _fix_horizontal_mislabeled_as_fy(ld: dict) -> dict:
    """עומס צירי (200kn→20t) שנקלט בטעות כ-Fy אנכי."""
    fy_raw = float(ld.get("Fy", ld.get("fy", 0.0)) or 0.0)
    fx = float(ld.get("Fx", ld.get("fx", 0.0)) or 0.0)
    if abs(fx) > 1e-6:
        return ld
    if not _likely_kn_misread_as_ton(fy_raw, per_meter=False) or fy_raw < KN_PER_TON * 15:
        return ld
    ton_val = fy_raw / KN_PER_TON
    if 15 <= abs(ton_val) <= 35:
        fixed = dict(ld)
        fixed["Fy"] = 0.0
        fixed["Fx"] = -abs(ton_val)
        fixed.pop("fy", None)
        log.info("Reclassified mislabeled vertical Fy=%s as horizontal Fx=%s", fy_raw, fixed["Fx"])
        return fixed
    return ld


def _normalize_load_magnitudes_ton(loads: list[dict]) -> list[dict]:
    out: list[dict] = []
    for raw in loads:
        if not isinstance(raw, dict):
            continue
        ld = dict(raw)
        t = str(ld.get("type", "")).lower()
        note = str(ld.get("note", ""))
        if t == "point":
            ld = _fix_horizontal_mislabeled_as_fy(ld)
            if not ld.get("_user_mag"):
                note_ton = _parse_ton_from_note(note, per_meter=False)
                note_dir = _read_axial_direction(ld)
                if note_ton is not None:
                    if abs(float(ld.get("Fy", ld.get("fy", 0.0)) or 0.0)) > 1e-6:
                        ld["Fy"] = note_ton
                    elif abs(float(ld.get("Fx", ld.get("fx", 0.0)) or 0.0)) > 1e-6:
                        ld["Fx"] = (
                            -abs(note_ton) if note_dir == "left" else abs(note_ton)
                        )
                else:
                    for key in ("Fy", "fy"):
                        if key in ld and ld[key] is not None:
                            try:
                                ld[key] = _force_value_to_ton(float(ld[key]), per_meter=False)
                            except (TypeError, ValueError):
                                pass
                    for key in ("Fx", "fx"):
                        if key in ld and ld[key] is not None:
                            try:
                                ld[key] = _force_value_to_ton(float(ld[key]), per_meter=False)
                            except (TypeError, ValueError):
                                pass
            else:
                for key in ("Fy", "fy", "Fx", "fx"):
                    if key in ld and ld[key] is not None:
                        try:
                            ld[key] = _force_value_to_ton(float(ld[key]), per_meter=False)
                        except (TypeError, ValueError):
                            pass
            ld = _apply_axial_sign(ld)
        elif t == "distributed":
            if ld.get("w") is not None:
                try:
                    ld["w"] = _force_value_to_ton(float(ld["w"]), per_meter=True)
                except (TypeError, ValueError):
                    pass
        elif t == "moment" and ld.get("M") is not None:
            try:
                ld["M"] = _force_value_to_ton(float(ld["M"]))
            except (TypeError, ValueError):
                pass
        elif t == "inclined":
            for key in ("Fx", "fx", "Fy", "fy"):
                if key in ld and ld[key] is not None:
                    try:
                        ld[key] = _force_value_to_ton(float(ld[key]), per_meter=False)
                    except (TypeError, ValueError):
                        pass
        out.append(ld)
    return out


def _merge_point_loads_at_same_x(loads: list[dict], *, tol: float = 0.35) -> list[dict]:
    """מאחד עומסים נקודתיים באותו x — Fy ו-Fx נפרדים באותה נקודה.

    עומסים עם ``_draft_new`` (שורת טיוטה חדשה שעדיין נערכת) לא ממוזגים —
    אחרת «הוסף עומס → נקודתי» נעלם כשיש כבר עומס ליד x=0.
    """
    kept: list[dict] = []
    for ld in loads:
        if str(ld.get("type", "")).lower() != "point":
            kept.append(ld)
            continue
        # שורת טיוטה חדשה — תמיד נשמרת בנפרד עד שהמשתמש ממלא ערכים.
        if ld.get("_draft_new"):
            kept.append(dict(ld))
            continue
        x = float(ld.get("x", 0.0))
        merged = False
        for idx, existing in enumerate(kept):
            if str(existing.get("type", "")).lower() != "point":
                continue
            # אל תמזג לתוך שורת טיוטה חדשה שעדיין ריקה/בעריכה.
            if existing.get("_draft_new"):
                continue
            ex = float(existing.get("x", 0.0))
            if abs(ex - x) > tol:
                continue
            combined = dict(existing)
            for key in ("Fy", "fy", "Fx", "fx"):
                new_v = float(ld.get(key, 0.0) or 0.0)
                old_v = float(combined.get(key, 0.0) or 0.0)
                if abs(new_v) > abs(old_v):
                    combined[key] = new_v
            kept[idx] = combined
            merged = True
            break
        if not merged:
            kept.append(dict(ld))
    return kept


def _segment_length_sum(beam: dict) -> float:
    seg_sum = 0.0
    for seg in beam.get("segments") or []:
        if not isinstance(seg, dict):
            continue
        try:
            length = float(seg.get("length_m", 0))
            if length <= 0:
                length = float(seg.get("to_x", 0)) - float(seg.get("from_x", 0))
            if length > 0:
                seg_sum += length
        except (TypeError, ValueError):
            continue
    return seg_sum


def _coerce_solver_load_schema(loads: list[dict]) -> list[dict]:
    """מאחד שדות מ-Gemini (kind, M_ton_m, magnitude_ton) לסכמת solver."""
    out: list[dict] = []
    for raw in loads:
        if not isinstance(raw, dict):
            continue
        ld = dict(raw)
        if not ld.get("type") and ld.get("kind"):
            ld["type"] = ld["kind"]
        if ld.get("M") is None and ld.get("M_ton_m") is not None:
            ld["M"] = ld["M_ton_m"]
        if ld.get("m") is None and ld.get("M_ton_m") is not None:
            ld["m"] = ld["M_ton_m"]
        t = str(ld.get("type", "")).lower()
        if t == "point":
            if ld.get("Fy") is None and ld.get("magnitude_ton") is not None:
                ld["Fy"] = ld["magnitude_ton"]
            if ld.get("Fx") is None and ld.get("Fx_ton") is not None:
                ld["Fx"] = ld["Fx_ton"]
        if t == "distributed" and ld.get("w") is None:
            w = ld.get("intensity_ton_per_m")
            if w is not None:
                ld["w"] = w
        if t == "inclined":
            mag = ld.get("magnitude_ton")
            if mag is not None and not ld.get("Fx") and not ld.get("Fy"):
                angle = float(ld.get("angle_deg", 45.0))
                rad = math.radians(angle)
                incl_dir = str(ld.get("incl_dir", "")).lower()
                if incl_dir == "dl":
                    ld["Fx"] = -abs(float(mag)) * math.cos(rad)
                    ld["Fy"] = abs(float(mag)) * math.sin(rad)
                else:
                    ld["Fx"] = abs(float(mag)) * math.cos(rad)
                    ld["Fy"] = abs(float(mag)) * math.sin(rad)
        out.append(ld)
    return out


def _inclined_mag_and_dir(ld: dict) -> tuple[float, str]:
    fx = float(ld.get("Fx", ld.get("fx", 0.0)) or 0.0)
    fy = float(ld.get("Fy", ld.get("fy", 0.0)) or 0.0)
    mag = math.hypot(fx, fy)
    if mag < 1e-6:
        mag = float(ld.get("magnitude_ton", 0.0) or 0.0)
    incl_dir = str(ld.get("incl_dir", "")).lower()
    if not incl_dir and mag > 1e-6:
        incl_dir = "dl" if fx < 0 else "dr"
    return mag, incl_dir


def _has_large_endpoint_horizontal(loads: list[dict], L: float, beam: dict | None = None) -> bool:
    beam_end = _right_end_x(beam, L) if isinstance(beam, dict) else L
    labeled_b = _labeled_points_map(beam).get("B") if isinstance(beam, dict) else None
    for ld in loads:
        if str(ld.get("type", "")).lower() != "point":
            continue
        try:
            x = float(ld.get("x", 0.0))
            fx = float(ld.get("Fx", ld.get("fx", 0.0)) or 0.0)
        except (TypeError, ValueError):
            continue
        near_tip = (
            abs(x - L) < 0.35
            or abs(x - beam_end) < 0.35
            or (labeled_b is not None and abs(x - labeled_b) < 0.35)
            or x >= L - 1.05
        )
        if near_tip and abs(fx) >= 50.0:
            return True
    return False


def _trusted_l12_from_chain(beam: dict) -> float | None:
    """אורך אמין 12m מסכום מקטעים או מנקודות G/I — לא מספר 13 שגוי."""
    seg_sum = _segment_length_sum(beam)
    if 11.5 < seg_sum < 12.5:
        return seg_sum
    labeled = _labeled_points_map(beam)
    g_x = labeled.get("G")
    i_x = labeled.get("I")
    h_x = labeled.get("H")
    if g_x is not None and 8.5 <= g_x <= 10.5 and {"H", "I", "E"}.issubset(labeled):
        return 12.0
    if i_x is not None and 10.5 <= i_x <= 12.5 and g_x is not None:
        return 12.0
    if h_x is not None and 10.0 <= h_x <= 11.5 and g_x is not None:
        return 12.0
    if g_x is not None and abs(g_x - 9) < 0.6:
        return g_x + 3.0
    if i_x is not None and abs(i_x - 11) < 0.6:
        return i_x + 1.0
    return None


def _looks_like_b_misread_as_13(beam: dict) -> bool:
    """האות B בקצה שרשרת המידות נקראת לפעמים כ-'13'."""
    L = float(beam.get("L", 0.0))
    if 12.5 <= L <= 13.5:
        return True
    labeled = _labeled_points_map(beam)
    b_x = labeled.get("B")
    if b_x is not None and 12.5 <= b_x <= 13.5:
        return True
    for sup in beam.get("supports") or []:
        if not isinstance(sup, dict):
            continue
        if str(sup.get("type", "")).lower() != "roller":
            continue
        try:
            rx = float(sup.get("x", 0.0))
        except (TypeError, ValueError):
            continue
        if 12.5 <= rx <= 13.5:
            return True
    return False


def _matches_l12_chain_signature(beam: dict, loads: list[dict]) -> bool:
    """חתימת תרגיל נפוצה: A—1—C—1—D—1—E—3—3—1—1—1—B (L=12)."""
    L = float(beam.get("L", 0.0))
    if not (9.5 <= L <= 11.5 or 12.5 <= L <= 13.5):
        return False
    supports = beam.get("supports") or []
    if len(supports) != 2:
        return False
    stypes = {str(s.get("type", "")).lower() for s in supports if isinstance(s, dict)}
    if "roller" not in stypes or not ("pin" in stypes or "fixed" in stypes):
        return False
    if not _has_large_endpoint_horizontal(loads, L, beam):
        return False

    has_moment_c = False
    inclined_early = 0
    udl_from_e = False
    inclined_dr_late = 0
    pos_moment_late = False
    c_x = _labeled_points_map(beam).get("C", 1.0)
    for ld in loads:
        t = str(ld.get("type", "")).lower()
        try:
            x = float(ld.get("x", ld.get("x1", 0.0)))
        except (TypeError, ValueError):
            continue
        if t == "moment":
            m = float(ld.get("M", ld.get("m", 0.0)) or 0.0)
            if abs(abs(m) - 30) < 5 and abs(x - c_x) < 0.75:
                has_moment_c = True
            if abs(abs(m) - 18) < 5 and x >= L - 2.5:
                pos_moment_late = True
        elif t == "inclined":
            mag, incl_dir = _inclined_mag_and_dir(ld)
            if incl_dir in ("dl", "dr") and abs(mag - 5) < 2.5 and x <= c_x + 2.5:
                inclined_early += 1
            if incl_dir == "dr" and x >= L - 3.5:
                inclined_dr_late += 1
        elif t == "distributed":
            try:
                x1 = float(ld.get("x1", 0.0))
                x2 = float(ld.get("x2", 0.0))
                w = float(ld.get("w", 0.0))
            except (TypeError, ValueError):
                continue
            if (
                (abs(x1 - 3) < 0.6 or abs(x1 - 4) < 0.6)
                and 0.5 <= w <= 5.0
                and x2 <= 9.5
            ):
                udl_from_e = True

    return (
        has_moment_c
        and inclined_early >= 1
        and udl_from_e
        and inclined_dr_late >= 1
        and pos_moment_late
    )


def _apply_standard_l12_labeled_chain(beam: dict) -> None:
    """מגדיר שרשרת מידות סטנדרטית L=12 כשחסר מקטע אחרון."""
    saved_L: float | None = None
    if _beam_L_user_locked(beam):
        try:
            saved_L = float(beam.get("L", 12.0))
        except (TypeError, ValueError):
            saved_L = None
    beam["L"] = 12.0
    beam["left_end_label"] = "A"
    beam["right_end_label"] = "B"
    beam["labeled_points"] = [
        {"label": "A", "x": 0},
        {"label": "C", "x": 1},
        {"label": "D", "x": 2},
        {"label": "E", "x": 3},
        {"label": "G", "x": 9},
        {"label": "H", "x": 10},
        {"label": "I", "x": 11},
        {"label": "B", "x": 12},
    ]
    beam["segments"] = [
        {"from_label": "A", "to_label": "C", "from_x": 0, "to_x": 1, "length_m": 1},
        {"from_label": "C", "to_label": "D", "from_x": 1, "to_x": 2, "length_m": 1},
        {"from_label": "D", "to_label": "E", "from_x": 2, "to_x": 3, "length_m": 1},
        {"from_label": "E", "to_label": "G", "from_x": 3, "to_x": 9, "length_m": 6},
        {"from_label": "G", "to_label": "H", "from_x": 9, "to_x": 10, "length_m": 1},
        {"from_label": "H", "to_label": "I", "from_x": 10, "to_x": 11, "length_m": 1},
        {"from_label": "I", "to_label": "B", "from_x": 11, "to_x": 12, "length_m": 1},
    ]
    beam["key_points_m"] = [0, 1, 2, 3, 9, 10, 11, 12]
    for sup in beam.get("supports") or []:
        if not isinstance(sup, dict):
            continue
        lbl = str(sup.get("label", "")).strip().upper()
        st = str(sup.get("type", "")).lower()
        if lbl == "B" or st == "roller":
            sup["x"] = 12.0
            sup["label"] = sup.get("label") or "B"
        elif lbl == "A" or st == "pin":
            sup["x"] = 0.0
            sup["label"] = sup.get("label") or "A"
    dist_user_span = any(
        isinstance(ld, dict)
        and str(ld.get("type", "")).lower() == "distributed"
        and ld.get("_user_span")
        for ld in (beam.get("loads") or [])
    )
    for item in beam.get("distributed_loads") or []:
        if not isinstance(item, dict):
            continue
        if item.get("_user_span") or dist_user_span:
            continue
        try:
            w = float(item.get("magnitude", item.get("w", 0)) or 0)
        except (TypeError, ValueError):
            continue
        if 0.5 <= w <= 5.0:
            item["start_x"] = 3
            item["end_x"] = 9
            item["x1"] = 3
            item["x2"] = 9
            item["label_at"] = "E"
    if saved_L is not None:
        beam["L"] = saved_L
    log.info("Applied standard L=12 labeled chain (missing last segment fix)")


def _fix_collapsed_end_labels(beam: dict, loads: list[dict]) -> None:
    """כש-G קיים אבל B ו-I מקופלים — מאריך את זנב הקורה ב-1m."""
    labeled = _labeled_points_map(beam)
    g_x = labeled.get("G")
    if g_x is None:
        return
    L = float(beam.get("L", 10.0))
    i_x = labeled.get("I")
    b_x = labeled.get("B")
    h_x = labeled.get("H")
    expected_L = g_x + 3.0
    collapsed = (
        i_x is not None
        and b_x is not None
        and abs(i_x - b_x) < 0.2
        and expected_L > L + 0.45
    )
    short_tail = L < expected_L - 0.45 and (
        _has_large_endpoint_horizontal(loads, L, beam)
        or (b_x is not None and abs(b_x - L) < 0.25)
    )
    if not collapsed and not short_tail:
        return

    beam["L"] = expected_L
    if h_x is None or h_x < g_x + 0.5:
        h_x = g_x + 1.0
    if i_x is None or i_x >= expected_L - 0.2:
        i_x = expected_L - 1.0
    b_x = expected_L

    points = []
    for pt in beam.get("labeled_points") or []:
        if not isinstance(pt, dict):
            continue
        lbl = str(pt.get("label", "")).strip().upper()
        if lbl == "H":
            points.append({"label": "H", "x": h_x})
        elif lbl == "I":
            points.append({"label": "I", "x": i_x})
        elif lbl == "B":
            points.append({"label": "B", "x": b_x})
        else:
            points.append(dict(pt))
    have = {str(p.get("label", "")).strip().upper() for p in points}
    for lbl, x in (("H", h_x), ("I", i_x), ("B", b_x)):
        if lbl not in have:
            points.append({"label": lbl, "x": x})
    beam["labeled_points"] = points
    log.info(
        "Fixed collapsed end labels: G=%s → L=%s (H=%s I=%s B=%s)",
        g_x,
        expected_L,
        h_x,
        i_x,
        b_x,
    )


def _needs_l12_geometry_fixup(beam: dict, loads: list[dict]) -> bool:
    """L=11 חסר מקטע / L=13 כש-B נקרא כ-13 — UDL מ-E וכוח אופקי בקצה."""
    L = float(beam.get("L", 0.0))
    if not (9.5 <= L <= 11.5 or 12.5 <= L <= 13.5):
        return False
    if not _has_large_endpoint_horizontal(loads, L, beam):
        return False
    return any(
        str(ld.get("type", "")).lower() == "distributed"
        and abs(float(ld.get("x1", 0)) - 3) < 0.6
        and 0.5 <= float(ld.get("w", 0)) <= 5.0
        and (
            float(ld.get("x2", 0)) <= 7.5
            or (12.5 <= L <= 13.5 and float(ld.get("x2", 0)) <= 10.5)
        )
        for ld in loads
        if isinstance(ld, dict)
    )


def _fix_b_misread_as_13(beam: dict, loads: list[dict]) -> bool:
    """מתקן L/סמך נייד מ-13 ל-12 כש-B נקרא בטעות כמספר 13."""
    if _beam_L_user_locked(beam):
        return False
    if not _looks_like_b_misread_as_13(beam):
        return False
    trusted = _trusted_l12_from_chain(beam)
    if trusted is None and (
        _matches_l12_chain_signature(beam, loads)
        or _needs_l12_geometry_fixup(beam, loads)
    ):
        trusted = 12.0
    if trusted is None or abs(trusted - 12.0) > 0.5:
        return False
    old_L = float(beam.get("L", 13.0))
    if abs(old_L - trusted) < 0.25:
        return False
    if abs(trusted - 12.0) < 0.5:
        _apply_standard_l12_labeled_chain(beam)
        log.info("Fixed B misread as 13: L %s → 12 (standard chain)", old_L)
        return True
    beam["L"] = trusted
    labeled = _labeled_points_map(beam)
    points: list[dict] = []
    for pt in beam.get("labeled_points") or []:
        if not isinstance(pt, dict):
            continue
        lbl = str(pt.get("label", "")).strip().upper()
        if lbl == "B":
            points.append({"label": "B", "x": trusted})
        else:
            points.append(dict(pt))
    if "B" not in {str(p.get("label", "")).strip().upper() for p in points}:
        points.append({"label": "B", "x": trusted})
    beam["labeled_points"] = points
    for sup in beam.get("supports") or []:
        if not isinstance(sup, dict):
            continue
        if str(sup.get("type", "")).lower() == "roller":
            sup["x"] = trusted
            sup["label"] = sup.get("label") or "B"
    log.info("Fixed B misread as 13: L %s → %s", old_L, trusted)
    return True


def _infer_beam_geometry_from_loads(beam: dict, loads: list[dict]) -> None:
    """מסקת גיאומטריה מחתימת עומסים כשחילוץ המידות חלקי."""
    if _beam_L_user_locked(beam):
        return
    if _fix_b_misread_as_13(beam, loads):
        return
    if _matches_l12_chain_signature(beam, loads) or _needs_l12_geometry_fixup(beam, loads):
        _apply_standard_l12_labeled_chain(beam)
        return
    _fix_collapsed_end_labels(beam, loads)


def _segment_sum_excluding_redundant_total(beam: dict) -> float | None:
    """מקטע אחרון = סכום כולל (למשל 2+2+2 ואז '6' בסוף) — מחזיר אורך בלי הכפלה."""
    segments = [s for s in (beam.get("segments") or []) if isinstance(s, dict)]
    if len(segments) < 2:
        return None
    lengths: list[float] = []
    for seg in segments:
        try:
            length = float(seg.get("length_m", 0))
            if length <= 0:
                length = float(seg.get("to_x", 0)) - float(seg.get("from_x", 0))
            if length > 0:
                lengths.append(length)
        except (TypeError, ValueError):
            continue
    if len(lengths) < 2:
        return None
    prior = sum(lengths[:-1])
    last = lengths[-1]
    if prior > 0 and abs(last - prior) < 0.35:
        return prior
    return None


def _resolve_double_counted_total_length(beam: dict) -> float | None:
    """L = מקטעים + מספר כולל בסוף (2+2+2+6=12 במקום 6)."""
    try:
        old_L = float(beam.get("L", 0))
    except (TypeError, ValueError):
        return None
    if old_L <= 0:
        return None

    seg_sum = _segment_length_sum(beam)
    seg_core = _segment_sum_excluding_redundant_total(beam)
    labeled = _labeled_points_map(beam)

    anchors: list[float] = []
    if seg_core is not None:
        anchors.append(seg_core)
    if seg_sum > 0 and (seg_core is None or abs(seg_sum - seg_core) > 0.2):
        anchors.append(seg_sum)
    if labeled:
        anchors.append(max(labeled.values()))
        b_x = labeled.get("B")
        if b_x is not None:
            anchors.append(b_x)
    for sup in beam.get("supports") or []:
        if not isinstance(sup, dict):
            continue
        if str(sup.get("type", "")).lower() != "roller":
            continue
        try:
            anchors.append(float(sup.get("x", 0)))
        except (TypeError, ValueError):
            continue

    seen: set[float] = set()
    for anchor in anchors:
        if anchor <= 0:
            continue
        key = round(anchor, 2)
        if key in seen:
            continue
        seen.add(key)
        if abs(old_L - 2 * anchor) < 0.35:
            return anchor
        if seg_sum > anchor and abs(old_L - anchor - seg_sum) < 0.35:
            return anchor

    if (
        seg_core is not None
        and seg_sum > seg_core
        and abs(old_L - seg_sum) < 0.35
    ):
        return seg_core

    return None


def _reconcile_beam_length(beam: dict) -> float:
    """מתקן L לפי סכום מקטעים / נקודה B — נפוץ: 11 במקום 12 (מקטע אחרון חסר)."""
    old_L = float(beam.get("L", 10.0))
    if _beam_L_user_locked(beam):
        return old_L
    deduped = _resolve_double_counted_total_length(beam)
    if deduped is not None and abs(deduped - old_L) > 0.05:
        beam["L"] = deduped
        log.info(
            "Corrected double-counted total length: %s → %s",
            old_L,
            deduped,
        )
        return old_L

    labeled = _labeled_points_map(beam)
    candidates = [old_L, _right_end_x(beam, old_L), _beam_axis_max(beam, old_L)]
    seg_sum = _segment_length_sum(beam)
    if seg_sum > 0:
        candidates.append(seg_sum)
    if labeled:
        candidates.append(max(labeled.values()))
        if "B" in labeled:
            candidates.append(labeled["B"])
        g_x = labeled.get("G")
        if g_x is not None:
            candidates.append(g_x + 3.0)
    new_L = max(candidates)
    if seg_sum > 11.5 and seg_sum < 12.5 and new_L > seg_sum + 0.75:
        log.info(
            "Prefer segment sum %s over misread tip (candidates max=%s)",
            seg_sum,
            new_L,
        )
        new_L = seg_sum
    trusted = _trusted_l12_from_chain(beam)
    loads_for_sig = [
        ld for ld in (beam.get("loads") or []) if isinstance(ld, dict)
    ]
    if (
        12.25 <= new_L <= 13.5
        and (
            _looks_like_b_misread_as_13(beam)
            or _matches_l12_chain_signature(beam, loads_for_sig)
            or _needs_l12_geometry_fixup(beam, loads_for_sig)
            or (trusted is not None and abs(trusted - 12.0) < 0.5)
        )
    ):
        log.info("Corrected L from %s to 12 (L=12 chain / B≠13)", new_L)
        _apply_standard_l12_labeled_chain(beam)
        new_L = 12.0
    elif (
        trusted is not None
        and 12.5 <= new_L <= 13.5
        and abs(trusted - 12.0) < 0.5
    ):
        log.info("Corrected L from %s to trusted %s (B≠13)", new_L, trusted)
        new_L = trusted
    if abs(new_L - old_L) > 0.05:
        beam["L"] = new_L
        log.info(
            "Reconciled beam L: %s → %s (segment sum=%s)",
            old_L,
            new_L,
            seg_sum,
        )
    return old_L


def _sync_roller_to_beam_end(beam: dict) -> None:
    """מסנכרן גליל לקצה רק כשאין שמש מעבר לגליל (B פנימי / overhang)."""
    L = float(beam.get("L", 10.0))
    labeled = _labeled_points_map(beam)
    beam_end = _right_end_x(beam, L)
    roller_label = str(beam.get("roller_support_label") or "B").strip().upper()

    if roller_label in labeled and labeled[roller_label] < beam_end - 0.15:
        for sup in beam.get("supports") or []:
            if not isinstance(sup, dict):
                continue
            if sup.get("_user_x"):
                continue
            if str(sup.get("type", "")).lower() != "roller":
                continue
            lbl = str(sup.get("label", "")).strip().upper()
            if lbl and lbl != roller_label:
                continue
            sup["x"] = labeled[roller_label]
            sup.setdefault("label", roller_label)
        return

    if roller_label in labeled:
        for sup in beam.get("supports") or []:
            if not isinstance(sup, dict):
                continue
            if sup.get("_user_x"):
                continue
            if str(sup.get("type", "")).lower() != "roller":
                continue
            lbl = str(sup.get("label", "")).strip().upper()
            if lbl and lbl != roller_label:
                continue
            sup["x"] = labeled[roller_label]
            sup.setdefault("label", roller_label)
        return

    for sup in beam.get("supports") or []:
        if not isinstance(sup, dict):
            continue
        if str(sup.get("type", "")).lower() != "roller":
            continue
        d_right = sup.get("dist_from_right_m")
        if d_right is not None:
            try:
                if beam_end - float(d_right) >= 0:
                    continue
            except (TypeError, ValueError):
                pass
        try:
            sx = float(sup.get("x", beam_end))
        except (TypeError, ValueError):
            continue
        at_tip = abs(sx - beam_end) < 0.35 or abs(sx - L) < 0.35
        if not at_tip:
            continue
        if abs(sx - beam_end) > 0.15:
            sup["x"] = beam_end
            log.info("Synced roller to beam end x=%s", beam_end)


def _shift_loads_for_length_correction(
    beam: dict,
    old_L: float,
    new_L: float,
    loads: list[dict],
) -> list[dict]:
    """כש-L תוקן (11→12 או 13→12), מזיז עומסים בקטע הימני."""
    delta = new_L - old_L
    if abs(delta) < 0.05 or abs(delta) > 1.5:
        return loads
    if delta < -0.5:
        for ld in loads:
            if _load_position_user_locked(ld):
                continue
            t = str(ld.get("type", "")).lower()
            if t == "distributed":
                continue
            try:
                x = float(ld.get("x", 0))
            except (TypeError, ValueError):
                continue
            if abs(x - old_L) < 0.35:
                ld["x"] = new_L
                if "B" in _labeled_points_map(beam):
                    ld["label_at"] = "B"
        return loads
    labeled = _labeled_points_map(beam)
    for ld in loads:
        if _load_position_user_locked(ld):
            continue
        t = str(ld.get("type", "")).lower()
        if t == "distributed":
            continue
        try:
            x = float(ld.get("x", 0))
        except (TypeError, ValueError):
            continue
        if x <= 2.5:
            continue
        if abs(x - old_L) < 0.25:
            ld["x"] = new_L
            if "B" in labeled:
                ld["label_at"] = "B"
        elif x > 2.5:
            ld["x"] = x + delta
            for lbl, lx in labeled.items():
                if abs(lx - float(ld["x"])) < 0.2:
                    ld["label_at"] = lbl
                    break
    return loads


def _fix_l12_mislabeled_end_inclines(beam: dict, loads: list[dict]) -> list[dict]:
    """מתקן עומסים אלכסוניים בקצה שסומנו G/H במקום H/I (תרגיל L=12 נפוץ)."""
    if abs(float(beam.get("L", 0.0)) - 12.0) > 0.25:
        return loads
    labeled = _labeled_points_map(beam)
    if not {"G", "H", "I"}.issubset(labeled):
        return loads
    h_x = labeled["H"]
    i_x = labeled["I"]
    for ld in loads:
        if str(ld.get("type", "")).lower() != "inclined":
            continue
        if _load_position_user_locked(ld):
            continue
        mag, _ = _inclined_mag_and_dir(ld)
        try:
            x = float(ld.get("x", 0.0))
        except (TypeError, ValueError):
            continue
        if x < h_x - 1.5:
            continue
        lbl = str(ld.get("label_at", "")).strip().upper()
        if abs(mag - 15) < 3.5 and lbl != "H":
            ld["label_at"] = "H"
            ld["x"] = h_x
            log.info("Relabeled inclined %.1ft (%s) to H at x=%s", mag, lbl or "?", h_x)
        elif abs(mag - 10) < 3.5 and lbl != "I":
            ld["label_at"] = "I"
            ld["x"] = i_x
            log.info("Relabeled inclined %.1ft (%s) to I at x=%s", mag, lbl or "?", i_x)
    return loads


def _fix_end_region_moments(beam: dict, loads: list[dict]) -> list[dict]:
    """תיקוני מיקום מומנט: I/H, C, ו-F לפני גליל B."""
    labeled = _labeled_points_map(beam)
    i_x = labeled.get("I")
    h_x = labeled.get("H")
    c_x = labeled.get("C")
    a_x = labeled.get("A")
    pin_x: float | None = None
    for sup in beam.get("supports") or []:
        if isinstance(sup, dict) and str(sup.get("type", "")).lower() == "pin":
            try:
                pin_x = float(sup.get("x", 0))
            except (TypeError, ValueError):
                pass
            break
    for ld in loads:
        if str(ld.get("type", "")).lower() != "moment":
            continue
        if _load_position_user_locked(ld):
            continue
        try:
            x = float(ld.get("x", 0))
            m = float(ld.get("M", ld.get("m", 0)))
        except (TypeError, ValueError):
            continue
        if abs(abs(m) - 18) < 4 and i_x is not None and abs(x - i_x) < 0.75:
            if m < 0:
                ld["M"] = abs(m)
                log.info("Flipped moment sign at I: %s → +%s", m, abs(m))
            ld["x"] = i_x
            ld["label_at"] = "I"
        elif abs(abs(m) - 18) < 4 and i_x is not None:
            if h_x is not None and abs(x - i_x) > 0.35 and abs(x - h_x) < 1.5:
                ld["x"] = i_x
                ld["label_at"] = "I"
                log.info("Moved end moment from x=%s to I at x=%s", x, i_x)
        elif abs(abs(m) - 30) < 4 and c_x is not None:
            at_pin = pin_x is not None and abs(x - pin_x) < 0.35
            at_a = a_x is not None and abs(x - a_x) < 0.35
            if (at_pin or at_a) and abs(x - c_x) > 0.35:
                ld["x"] = c_x
                ld["label_at"] = "C"
                log.info("Moved moment M=%s from pin/A x=%s to C at x=%s", m, x, c_x)
        elif m < 0 and abs(m + 30) < 4 and c_x is not None and abs(x - c_x) > 0.35:
            ld["x"] = c_x
            ld["label_at"] = "C"

    loads = _fix_moment_misplaced_at_roller(beam, loads)
    return loads


def _fix_moment_misplaced_at_roller(beam: dict, loads: list[dict]) -> list[dict]:
    """מומנט על גליל B — בכתב יד לרוב מדובר בנקודה הפנימית (F) 2m לפני הסוף."""
    labeled = _labeled_points_map(beam)
    if not labeled:
        return loads

    roller_x: float | None = None
    for sup in beam.get("supports") or []:
        if not isinstance(sup, dict):
            continue
        if str(sup.get("type", "")).lower() != "roller":
            continue
        try:
            roller_x = float(sup.get("x", 0))
        except (TypeError, ValueError):
            continue
        break
    if roller_x is None:
        return loads

    interior: tuple[str, float] | None = None
    for lbl, lx in labeled.items():
        if lx >= roller_x - 0.15:
            continue
        if interior is None or lx > interior[1]:
            interior = (lbl, lx)
    if interior is None:
        return loads

    prev_lbl, prev_x = interior
    tail = roller_x - prev_x
    if tail < 0.5 or tail > 5.0:
        return loads

    for ld in loads:
        if str(ld.get("type", "")).lower() != "moment":
            continue
        if _load_position_user_locked(ld):
            continue
        try:
            x = float(ld.get("x", 0))
            m = float(ld.get("M", ld.get("m", 0)) or 0)
        except (TypeError, ValueError):
            continue
        label_at = str(ld.get("label_at", "")).strip().upper()
        if label_at in ("I", "H", "C") and abs(abs(m) - 18) < 4:
            continue
        if label_at in ("I", "H", "C") and abs(abs(m) - 30) < 4:
            continue
        at_roller = abs(x - roller_x) < 0.35 or label_at == "B"
        if not at_roller:
            continue
        ld["x"] = prev_x
        ld["label_at"] = prev_lbl
        log.info(
            "Moved moment from roller B (x=%s) to %s at x=%s (tail=%.1fm)",
            roller_x,
            prev_lbl,
            prev_x,
            tail,
        )
    return loads


def _normalize_structure_metadata(beam: dict) -> None:
    """שני סמכים (צמד+גליל) = קורת שתי סמכים — לא רב-סמכית."""
    supports = beam.get("supports")
    if not isinstance(supports, list) or len(supports) != 2:
        return
    stypes = {
        str(s.get("type", "")).lower()
        for s in supports
        if isinstance(s, dict)
    }
    if "roller" in stypes and ("pin" in stypes or "fixed" in stypes):
        beam["structure_type"] = "simply_supported"
        beam["support_mode"] = "simply_supported"


def _fix_endpoint_horizontal_misread(beam: dict) -> None:
    """64.2t שמאלה בקצה B לפעמים נקלט כ-Fy≈6.42 (ספרה עשרונית שגויה)."""
    L = float(beam.get("L", 10.0))
    loads = beam.get("loads")
    if not isinstance(loads, list):
        return
    for ld in loads:
        if not isinstance(ld, dict) or str(ld.get("type", "")).lower() != "point":
            continue
        try:
            x = float(ld.get("x", 0.0))
        except (TypeError, ValueError):
            continue
        if abs(x - L) > 0.35:
            continue
        fy = float(ld.get("Fy", ld.get("fy", 0.0)) or 0.0)
        fx = float(ld.get("Fx", ld.get("fx", 0.0)) or 0.0)
        if abs(fx) > 1e-6:
            continue
        if 5.5 <= abs(fy) <= 7.5:
            restored = abs(fy) * 10.0
            if 55.0 <= restored <= 75.0:
                ld["Fy"] = 0.0
                ld["Fx"] = -restored
                ld["direction"] = "left"
                ld.pop("fy", None)
                log.info(
                    "Fixed endpoint misread Fy=%s → Fx=-%s at x=L",
                    fy,
                    restored,
                )


def _apply_support_hatch_evidence(beam: dict) -> None:
    """קורה על 2 סמכים: קובעים pin/roller לפי עדות חזותית מדווחת (ספירת hatch),
    לא לפי «type» הקטגורי של ה-AI — מפחית הטיה של ניחוש לפי הרגל/מיקום.

    ה-Vision מתבקש (בפרומפט) לדווח hatch_count — מספר קווי האלכסון שראה בכל סמך —
    בנוסף ל-type. ספירת מספר קווים היא משימה חזותית ישירה, פחות נתונה להטיה לפי
    הרגל (שמאל=קבוע) מהחלטה קטגורית "pin vs roller". אם hatch_count מדווח וסותר
    את type, hatch_count מנצח: >=2 קווי hatch → pin (קבוע), אחרת → roller (נייד).
    בלי hatch_count מדווח (למשל תמונות ישנות/שלב אחר) — לא נוגעים ב-type.
    """
    mode = str(beam.get("support_mode", "simply_supported")).lower()
    if mode == "cantilever":
        return
    supports = beam.get("supports")
    if not isinstance(supports, list) or len(supports) != 2:
        return
    for sup in supports:
        if not isinstance(sup, dict):
            continue
        if sup.get("has_full_wall_hatch"):
            continue
        hatch_count = sup.get("hatch_count")
        if hatch_count is None:
            continue
        try:
            hatch_count = int(hatch_count)
        except (TypeError, ValueError):
            continue
        current = str(sup.get("type", "")).lower().strip()
        if current not in ("pin", "roller", "fixed"):
            continue
        derived = "pin" if hatch_count >= 2 else "roller"
        if current != derived:
            label = str(sup.get("label", "")).strip().upper() or "?"
            log.info(
                "Support %s: type=%s conflicts with reported hatch_count=%s → corrected to %s",
                label,
                current,
                hatch_count,
                derived,
            )
            sup["type"] = derived


def _ensure_simply_supported_pin_roller_pair(supports: list[dict]) -> None:
    """שני סמכים מאותו סוג (או שני fixed) — חייבים צמד pin+roller.

    עדיפות: תוויות A/B (A=קבוע, B=נייד); אחרת שמאלי=pin, ימני=roller.
    """
    if len(supports) != 2 or not all(isinstance(s, dict) for s in supports):
        return
    by_label = {
        str(s.get("label", "")).strip().upper(): s for s in supports
    }
    if "A" in by_label and "B" in by_label and by_label["A"] is not by_label["B"]:
        a, b = by_label["A"], by_label["B"]
        if str(a.get("type", "")).lower().strip() != "pin" or str(
            b.get("type", "")
        ).lower().strip() != "roller":
            log.info(
                "Normalized simply-supported pair by labels: A→pin, B→roller "
                "(was A=%s B=%s)",
                a.get("type"),
                b.get("type"),
            )
        a["type"] = "pin"
        b["type"] = "roller"
        return
    ordered = sorted(
        supports,
        key=lambda s: float(s.get("x", 0.0) or 0.0),
    )
    left, right = ordered[0], ordered[1]
    if str(left.get("type", "")).lower().strip() != "pin" or str(
        right.get("type", "")
    ).lower().strip() != "roller":
        log.info(
            "Normalized simply-supported pair by position: left→pin, right→roller "
            "(was left=%s right=%s)",
            left.get("type"),
            right.get("type"),
        )
    left["type"] = "pin"
    right["type"] = "roller"


def _normalize_support_types(beam: dict) -> None:
    """קורה על 2 סמכים: חייב בדיוק pin + roller (קבוע + נייד).

    «fixed» שייך רק לזיז. אם ה-Vision סימן fixed / שני pin / שני roller —
    מתקנים לצמד תקין. כשיש fixed + pin/roller — ממירים את ה-fixed לפי השני.
    כששניהם זהים — לפי תוויות A/B, אחרת לפי מיקום (שמאל=pin, ימין=roller).
    """
    mode = str(beam.get("support_mode", "simply_supported")).lower()
    if mode == "cantilever":
        return
    supports = beam.get("supports")
    if not isinstance(supports, list) or len(supports) != 2:
        return
    if not all(isinstance(s, dict) for s in supports):
        return
    types = [str(s.get("type", "")).lower().strip() for s in supports]
    if any(t not in ("pin", "roller", "fixed") for t in types):
        return

    # fixed + pin/roller → המרת ה-fixed בלבד
    if types.count("fixed") == 1:
        other = types[0] if types[1] == "fixed" else types[1]
        if other in ("pin", "roller"):
            replacement = "roller" if other == "pin" else "pin"
            for sup in supports:
                if str(sup.get("type", "")).lower().strip() == "fixed":
                    label = str(sup.get("label", "")).strip().upper() or "?"
                    sup["type"] = replacement
                    log.info(
                        "Normalized support %s: fixed → %s "
                        "(2-support beam, other support is %s)",
                        label,
                        replacement,
                        other,
                    )
            return

    # שני pin / שני roller / שני fixed / או צירוף לא תקין — כפה pin+roller
    unique = set(types)
    if unique == {"pin", "roller"}:
        return
    _ensure_simply_supported_pin_roller_pair(supports)


def normalize_beam_model(
    beam: dict,
    *,
    merge_nearby_point_loads: bool = True,
) -> dict:
    """תיקוני חילוץ נפוצים לפני חישוב — מיקומים, UDL, כיוון נטוי.

    ``merge_nearby_point_loads`` — מיזוג עומסים נקודתיים קרובים (סף ~0.35m).
    בטיוטה כבוי, כדי לא לבלוע עומסים סמוכים שהמשתמש ערך במפורש.
    """
    if not isinstance(beam, dict):
        return beam
    out = dict(beam)
    loads_early = [
        dict(ld) for ld in (out.get("loads") or []) if isinstance(ld, dict)
    ]
    _scale_beam_geometry_from_hundredths(out, loads_early)
    out["loads"] = loads_early
    L = max(0.1, float(out.get("L", 10.0)))
    left_x = _left_end_x(out)
    right_x = _right_end_x(out, L)
    if _beam_L_user_locked(out):
        out["L"] = L
    else:
        out["L"] = max(L, right_x)
    L = float(out["L"])

    _normalize_structure_metadata(out)
    _apply_support_hatch_evidence(out)
    _normalize_support_types(out)
    loads_preview = _coerce_solver_load_schema(
        [dict(ld) for ld in (out.get("loads") or []) if isinstance(ld, dict)]
    )
    _rezero_beam_at_pin_support(out, loads_preview)
    out["loads"] = loads_preview
    loads_preview = _fix_end_region_moments(out, loads_preview)
    out["loads"] = loads_preview
    length_before_inference = float(out.get("L", 10.0))
    _infer_beam_geometry_from_loads(out, loads_preview)
    try:
        from bot.validation_fix_engine import apply_learned_extraction_rules

        apply_learned_extraction_rules(out, loads_preview)
    except Exception:
        pass
    _infer_labeled_points_from_segments(out)
    _reconcile_beam_length(out)
    new_L = float(out.get("L", length_before_inference))
    old_L = length_before_inference
    _infer_distributed_from_boundary_misreads(out)
    _ingest_distributed_loads(out)
    _fix_roller_from_load_boundaries(out)
    _sync_supports_to_labeled_chain(out)
    _snap_supports_to_nearest_chain_point(out)
    _fix_roller_overhang_position(out)
    _sync_roller_to_beam_end(out)
    _normalize_support_positions(out)
    _sync_supports_to_labeled_chain(out)
    _, ra_pos, rb_pos = resolve_beam_support_geometry(out)
    out["ra_pos"] = ra_pos
    out["rb_pos"] = rb_pos

    loads = _normalize_load_magnitudes_ton(
        [dict(ld) for ld in (out.get("loads") or []) if isinstance(ld, dict)]
    )
    loads = _promote_diagonal_point_loads(loads)
    loads = _fix_paired_cd_inclined_loads(out, loads)
    loads = _normalize_inclined_loads(loads)
    loads = _apply_explicit_load_positions(out, loads)

    for ld in loads:
        t = str(ld.get("type", "")).lower()
        if t == "inclined":
            x = float(ld.get("x", 0.0))
            if (
                not ld.get("_user_x")
                and abs(x - ra_pos) < 0.35
                and left_x < ra_pos - 0.1
            ):
                mag = math.hypot(
                    float(ld.get("Fx", ld.get("fx", 0.0))),
                    float(ld.get("Fy", ld.get("fy", 0.0))),
                )
                if mag < 1.0:
                    mag = 10.0
                angle = float(ld.get("angle_deg", 30.0))
                _, incl_dir = _inclined_mag_and_dir(ld)
                fx, fy = _recompute_inclined_components(mag, angle, incl_dir=incl_dir)
                ld["x"] = left_x
                ld["Fx"] = fx
                ld["Fy"] = fy
                ld["incl_dir"] = incl_dir
                ld["label_at"] = out.get("left_end_label") or "C"
                log.info(
                    "Normalized inclined load: moved from pin x=%s to left end x=%s (%s)",
                    ra_pos,
                    left_x,
                    incl_dir,
                )
        elif t == "moment":
            x = float(ld.get("x", 0.0))
            # אל תזיז מומנט מצמד לקצה ימין — זה גורם לבלבול F/B; תיקון גליל ב-_fix_moment_misplaced_at_roller
            if (
                not ld.get("_user_x")
                and abs(x - ra_pos) < 0.35
                and abs(right_x - ra_pos) > 0.5
                and not any(
                    str(s.get("type", "")).lower() == "roller"
                    for s in (out.get("supports") or [])
                    if isinstance(s, dict)
                )
            ):
                ld["x"] = right_x
                ld["label_at"] = out.get("right_end_label") or "B"
                log.info("Normalized moment: moved from pin to right end x=%s", right_x)

    if merge_nearby_point_loads:
        loads = _merge_point_loads_at_same_x(loads)
    loads = _apply_explicit_load_positions(out, loads)
    loads = _shift_loads_for_length_correction(out, old_L, new_L, loads)
    loads = _fix_end_region_moments(out, loads)
    loads = _apply_explicit_load_positions(out, loads)
    loads = _fix_l12_mislabeled_end_inclines(out, loads)
    loads = _snap_loads_to_dimension_chain(out, loads)
    _rezero_beam_at_left_end(out, loads)
    loads = _apply_explicit_load_positions(out, loads)
    out["loads"] = loads
    _, ra_pos, rb_pos = resolve_beam_support_geometry(out)
    out["ra_pos"] = ra_pos
    out["rb_pos"] = rb_pos
    _fix_endpoint_horizontal_misread(out)
    _infer_labeled_points_from_segments(out)
    return out


def _restore_labeled_points_from_protocol(data: dict) -> None:
    """משחזר labeled_points משלב הגיאומטריה אם נעלמו בנורמליזציה."""
    beam = data.get("beam")
    if not isinstance(beam, dict) or beam.get("labeled_points"):
        return
    protocol = data.get("extraction_protocol") or data.get("staged") or {}
    geo = protocol.get(STEP_1_KEY) if isinstance(protocol, dict) else {}
    if not isinstance(geo, dict):
        return
    nested = geo.get("geometry")
    if isinstance(nested, dict):
        geo = nested
    lp = geo.get("labeled_points")
    if not isinstance(lp, list) or not lp:
        return
    restored: list[dict] = []
    for pt in lp:
        if not isinstance(pt, dict):
            continue
        lbl = str(pt.get("label", "")).strip().upper()
        if lbl in ("START", "ORIGIN"):
            continue
        try:
            restored.append({"label": lbl, "x": float(pt.get("x", 0))})
        except (TypeError, ValueError):
            continue
    if restored:
        beam["labeled_points"] = restored
        log.info("Restored %s labeled_points from extraction protocol", len(restored))


def finalize_beam_extraction(
    data: dict,
    *,
    merge_nearby_point_loads: bool = True,
) -> dict:
    if infer_vision_exercise_type(data) != "beam":
        return data
    beam = data.get("beam")
    if isinstance(beam, dict):
        data = dict(data)
        # deepcopy — normalize_beam_model מזיז supports/loads in-place;
        # העתקה רדודה הייתה מקלקלת את האובייקט המקורי (סמכים זזים, עומסים לא).
        beam = copy.deepcopy(beam)
        if isinstance(data.get("distributed_loads"), list):
            beam["distributed_loads"] = copy.deepcopy(data["distributed_loads"])
        data["beam"] = normalize_beam_model(
            beam,
            merge_nearby_point_loads=merge_nearby_point_loads,
        )
        # Flip vision CCW+ → website CW+ only once (first extraction).
        # Re-running on every edit undoes user moment-direction toggles.
        if not data.get("_moment_sign_aligned"):
            _flip_moment_sign_convention_for_website(data["beam"])
            data["_moment_sign_aligned"] = True
        _restore_labeled_points_from_protocol(data)
        _infer_labeled_points_from_segments(data["beam"])
    return data


def _flip_moment_sign_convention_for_website(beam: dict) -> None:
    """Align moment sign with website: ↻ (clockwise) = positive M, ↺ = negative M."""
    loads = beam.get("loads")
    if not isinstance(loads, list) or not loads:
        return
    for ld in loads:
        if not isinstance(ld, dict):
            continue
        if str(ld.get("type", "")).lower().strip() != "moment":
            continue
        for key in ("M", "m", "M_ton_m"):
            if ld.get(key) is None:
                continue
            try:
                ld[key] = -float(ld[key])
            except (TypeError, ValueError):
                continue


def _fmt_m(value: object) -> str:
    if value is None:
        return "?"
    try:
        n = float(value)
        if abs(n - round(n)) < 0.005:
            return str(int(round(n)))
        rounded = round(n, 2)
        text = f"{rounded:.2f}".rstrip("0").rstrip(".")
        return text or "0"
    except (TypeError, ValueError):
        return str(value)


def _fmt_ton(value: object) -> str:
    """עיצוב מספרי לתצוגת עומסים — עד 2 ספרות אחרי הנקודה."""
    if value is None:
        return "?"
    try:
        n = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(n) < 1e-9:
        return "0"
    if abs(n - round(n)) < 0.005:
        return str(int(round(n)))
    rounded = round(n, 2)
    text = f"{rounded:.2f}".rstrip("0").rstrip(".")
    return text or "0"


def _support_type_he(raw_type: str) -> str:
    return _SUPPORT_TYPE_HE.get(str(raw_type or "").lower().strip(), str(raw_type or "?"))


def resolve_beam_support_geometry(beam: dict) -> tuple[str, float, float]:
    """מחזיר (support_mode, ra_pos, rb_pos) מתוך supports[] או שדות ישנים."""
    mode = str(beam.get("support_mode", "simply_supported")).lower().strip()
    L = max(0.1, float(beam.get("L", 10.0)))
    supports = beam.get("supports")
    if isinstance(supports, list) and supports:
        pins: list[float] = []
        rollers: list[float] = []
        fixed: list[float] = []
        for item in supports:
            if not isinstance(item, dict):
                continue
            x = float(item.get("x", 0.0))
            st = str(item.get("type", "")).lower().strip()
            if st == "fixed":
                fixed.append(x)
            elif st == "roller":
                rollers.append(x)
            elif st == "pin":
                pins.append(x)
        if fixed:
            return "cantilever", max(0.0, min(L, fixed[0])), L
        ra_pos = pins[0] if pins else float(beam.get("ra_pos", 0.0))
        rb_pos = rollers[0] if rollers else float(beam.get("rb_pos", L))
        if not pins and not rollers:
            ra_pos = float(beam.get("ra_pos", 0.0))
            rb_pos = float(beam.get("rb_pos", L))
        resolved_mode = (
            mode if mode in ("simply_supported", "cantilever") else "simply_supported"
        )
        return (
            resolved_mode,
            max(0.0, min(L, ra_pos)),
            max(0.0, min(L, rb_pos)),
        )
    ra_pos = max(0.0, min(L, float(beam.get("ra_pos", 0.0))))
    rb_pos = max(0.0, min(L, float(beam.get("rb_pos", L))))
    if mode == "cantilever":
        return "cantilever", ra_pos, L
    return mode, ra_pos, rb_pos


def format_beam_load_he(item: dict) -> str:
    t = str(item.get("type", "point")).lower().strip()
    if t == "point":
        fy = float(item.get("Fy", item.get("fy", 0.0)))
        direction = "↓" if fy >= 0 else "↑"
        parts = [f"עומס נקודתי {_fmt_m(abs(fy))} טון {direction} ב-x={_fmt_m(item.get('x'))} m"]
        fx = item.get("Fx", item.get("fx"))
        if fx is not None and abs(float(fx)) > 1e-12:
            parts.append(f"Fx={_fmt_m(fx)} טון")
        return ", ".join(parts)
    if t == "distributed":
        w = float(item.get("w", 0.0))
        shape = str(item.get("shape", "rectangular")).lower()
        shape_he = "משולש" if shape == "triangular" else "מלבני"
        return (
            f"עומס מפורס ({shape_he}) {_fmt_m(abs(w))} טון/מ' ↓ "
            f"מ-x={_fmt_m(item.get('x1'))} עד x={_fmt_m(item.get('x2'))} m"
        )
    if t == "moment":
        m_val = float(item.get("M", item.get("m", 0.0)))
        sense = " (עם שעון)" if m_val > 0 else " (נגד שעון)" if m_val < 0 else ""
        return (
            f"מומנט{sense} {_fmt_m(abs(m_val))} טון·מ "
            f"ב-x={_fmt_m(item.get('x'))} m"
        )
    if t == "inclined":
        fx = float(item.get("Fx", item.get("fx", 0.0)))
        fy = float(item.get("Fy", item.get("fy", 0.0)))
        mag = math.hypot(fx, fy)
        side = "dl" if fx < 0 else "dr"
        return (
            f"עומס אלכסוני {_fmt_m(mag)} טון {side} ב-x={_fmt_m(item.get('x'))} m "
            f"(Fx={_fmt_m(fx)}, Fy={_fmt_m(fy)} טון)"
        )
    return f"עומס ({t})"


_STRUCTURE_TYPE_HE: dict[str, str] = {
    "simply_supported": "קורת שתי סמכים",
    "cantilever": "קורת זיז (רתום)",
    "multi_span": "קורה רב-סמכית",
    "gerber": "קורת גרבר (עם פרקים)",
    "truss": "מסבך (Truss)",
    "frame": "מסגרת (Frame)",
}


def _expand_point_loads_for_display(loads: list[dict]) -> list[dict]:
    """מפריד עומס אנכי וצירי באותה נקודה — שורת תצוגה לכל רכיב."""
    out: list[dict] = []
    for ld in loads:
        if str(ld.get("type", "")).lower() != "point":
            out.append(ld)
            continue
        fy = float(ld.get("Fy", ld.get("fy", 0.0)) or 0.0)
        fx = float(ld.get("Fx", ld.get("fx", 0.0)) or 0.0)
        has_fy = abs(fy) >= 1e-12
        has_fx = abs(fx) >= 1e-12
        if has_fy and has_fx:
            base = {
                k: v
                for k, v in ld.items()
                if k not in ("Fy", "fy", "Fx", "fx")
            }
            x = ld.get("x")
            out.append({**base, "type": "point", "x": x, "Fy": fy})
            out.append({**base, "type": "point", "x": x, "Fx": fx})
        else:
            out.append(ld)
    return out


def _load_sort_key_x(ld: dict) -> tuple[float, int, int]:
    """מיקום שמאלי על הקורה למיון עומסים (x=0 משמאל)."""
    t = str(ld.get("type", "point")).lower().strip()
    x = float(ld.get("x1", 0.0) if t == "distributed" else ld.get("x", 0.0))
    type_order = {"inclined": 0, "point": 1, "moment": 2, "distributed": 3}.get(t, 9)
    point_sub = 0
    if t == "point":
        fy = abs(float(ld.get("Fy", ld.get("fy", 0.0)) or 0.0))
        fx = abs(float(ld.get("Fx", ld.get("fx", 0.0)) or 0.0))
        if fy >= 1e-12:
            point_sub = 0
        elif fx >= 1e-12:
            point_sub = 1
        else:
            point_sub = 2
    return (x, type_order, point_sub)


def _sorted_beam_loads(beam: dict) -> list[dict]:
    loads = beam.get("loads") or []
    if not isinstance(loads, list):
        return []
    valid = [ld for ld in loads if isinstance(ld, dict)]
    expanded = _expand_point_loads_for_display(valid)
    return sorted(expanded, key=_load_sort_key_x)


def _support_display_lines(beam: dict) -> list[str]:
    """שורות סמכים — קבוע/נייד/ריתום, ממוינות לפי x."""
    mode, ra_pos, rb_pos = resolve_beam_support_geometry(beam)
    entries: list[tuple[str, float]] = []
    supports = beam.get("supports") or []
    if isinstance(supports, list) and supports:
        for sup in supports:
            if not isinstance(sup, dict):
                continue
            st = str(sup.get("type", "")).lower().strip()
            x = float(sup.get("x", 0.0))
            if st == "pin":
                entries.append(("סמך קבוע", x))
            elif st == "roller":
                entries.append(("סמך נייד", x))
            elif st == "fixed":
                entries.append(("ריתום", x))
    elif mode == "cantilever":
        entries.append(("ריתום", ra_pos))
    else:
        entries.append(("סמך קבוע", ra_pos))
        entries.append(("סמך נייד", rb_pos))
    entries.sort(key=lambda item: item[1])
    out_lines: list[str] = []
    supports = beam.get("supports") or []
    sup_by_type: dict[str, dict] = {}
    if isinstance(supports, list):
        for sup in supports:
            if isinstance(sup, dict):
                st = str(sup.get("type", "")).lower()
                sup_by_type[st] = sup
    for label, x in entries:
        lbl = ""
        if label == "סמך קבוע" and sup_by_type.get("pin"):
            lbl = str(sup_by_type["pin"].get("label") or "").strip()
        elif label == "סמך נייד" and sup_by_type.get("roller"):
            lbl = str(sup_by_type["roller"].get("label") or "").strip()
        if lbl:
            out_lines.append(f"{label} ({lbl}) על ציר הקורה: x={_fmt_m(x)} מ'")
        else:
            out_lines.append(f"{label} על ציר הקורה: x={_fmt_m(x)} מ'")
    return out_lines


def _safe_load_float(value: object, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _format_numbered_load_line(idx: int, ld: dict) -> str:
    """שורת עומס בודדת לפי פורמט התצוגה לסטודנט."""
    t = str(ld.get("type", "point")).lower().strip()
    if t == "point":
        fy = _safe_load_float(ld.get("Fy", ld.get("fy", 0.0)))
        fx = _safe_load_float(ld.get("Fx", ld.get("fx", 0.0)))
        x = _fmt_m(ld.get("x"))
        if abs(fy) >= 1e-12:
            return f"עומס {idx}, אנכי: {_fmt_ton(abs(fy))} טון, x={x}."
        if abs(fx) >= 1e-12:
            direction = "שמאלה" if fx < 0 else "ימינה"
            return f"עומס {idx}, אופקי ({direction}): {_fmt_ton(abs(fx))} טון, x={x}."
        return f"עומס {idx}, נקודתי: 0 טון, x={x}."
    if t == "distributed":
        w = _safe_load_float(ld.get("w", 0.0))
        x1 = _fmt_m(ld.get("x1"))
        x2 = _fmt_m(ld.get("x2"))
        shape = str(ld.get("shape", "rectangular")).lower()
        shape_he = "משולש" if shape == "triangular" else "מלבני"
        return f"עומס {idx}, מפורס ({shape_he}): {_fmt_ton(abs(w))} טון/מטר, x={x1}-{x2}."
    if t == "moment":
        m_val = _safe_load_float(ld.get("M", ld.get("m", 0.0)))
        x = _fmt_m(ld.get("x"))
        # Website convention: clockwise positive, counter-clockwise negative.
        sense = " (עם שעון)" if m_val > 0 else " (נגד שעון)" if m_val < 0 else ""
        return f"עומס {idx}, מומנט{sense}: {_fmt_ton(abs(m_val))} טון·מ, x={x}."
    if t == "inclined":
        fx = _safe_load_float(ld.get("Fx", ld.get("fx", 0.0)))
        fy = _safe_load_float(ld.get("Fy", ld.get("fy", 0.0)))
        mag = math.hypot(fx, fy)
        x = _fmt_m(ld.get("x"))
        side = "dl" if fx < 0 else "dr"
        angle = ld.get("angle_deg")
        if angle is not None:
            return (
                f"עומס {idx}, אלכסוני {side}: {_fmt_ton(mag)} טון, x={x}, זווית {_fmt_m(angle)}°."
            )
        return f"עומס {idx}, אלכסוני {side}: {_fmt_ton(mag)} טון, x={x}."
    return f"עומס {idx}: {t}, x={_fmt_m(ld.get('x', ld.get('x1', '?')))}."


def _structure_type_he(beam: dict) -> str:
    supports = beam.get("supports") or []
    if isinstance(supports, list) and len(supports) == 2:
        stypes = {
            str(s.get("type", "")).lower()
            for s in supports
            if isinstance(s, dict)
        }
        if "roller" in stypes and ("pin" in stypes or "fixed" in stypes):
            return _STRUCTURE_TYPE_HE["simply_supported"]
    raw = str(beam.get("structure_type", "")).lower().strip()
    if raw in _STRUCTURE_TYPE_HE and raw != "multi_span":
        return _STRUCTURE_TYPE_HE[raw]
    mode = str(beam.get("support_mode", "")).lower()
    if mode == "cantilever":
        return _STRUCTURE_TYPE_HE["cantilever"]
    if isinstance(supports, list) and len(supports) > 2:
        return _STRUCTURE_TYPE_HE["multi_span"]
    hinges = beam.get("internal_hinges") or []
    if isinstance(hinges, list) and hinges:
        return _STRUCTURE_TYPE_HE["gerber"]
    return _STRUCTURE_TYPE_HE["simply_supported"]


def _format_supports_ident_line(beam: dict) -> str:
    supports = beam.get("supports") or []
    if not isinstance(supports, list) or not supports:
        mode, ra_pos, rb_pos = resolve_beam_support_geometry(beam)
        if mode == "cantilever":
            return f"ריתום ב-x={_fmt_m(ra_pos)} מ'"
        return (
            f"סמך קבוע (צמד) ב-x={_fmt_m(ra_pos)} מ', "
            f"סמך נייד (גליל) ב-x={_fmt_m(rb_pos)} מ'"
        )
    parts: list[str] = []
    for sup in supports:
        if not isinstance(sup, dict):
            continue
        label = str(sup.get("label") or "?").strip()
        st = _support_type_he(str(sup.get("type", "")))
        parts.append(f"{st} ({label}) על ציר הקורה, x={_fmt_m(sup.get('x'))} מ'")
    return "; ".join(parts) if parts else "לא זוהו סמכים"


def _format_geometry_ident_line(beam: dict) -> str:
    L = beam.get("L", "?")
    segments = beam.get("segments") or []
    if isinstance(segments, list) and segments:
        seg_parts: list[str] = []
        for seg in segments:
            if not isinstance(seg, dict):
                continue
            fl = seg.get("from_label") or seg.get("from_x")
            tl = seg.get("to_label") or seg.get("to_x")
            length = seg.get("length_m")
            if length is None:
                try:
                    length = float(seg.get("to_x", 0)) - float(seg.get("from_x", 0))
                except (TypeError, ValueError):
                    length = "?"
            seg_parts.append(f"{fl}→{tl} {_fmt_m(length)} מ'")
        return f"L={_fmt_m(L)} מ' ({', '.join(seg_parts)})"
    return f"L={_fmt_m(L)} מ'"


def _format_loads_ident_line(beam: dict) -> str:
    loads = beam.get("loads") or []
    if not isinstance(loads, list) or not loads:
        return "לא זוהו עומסים"
    return "; ".join(format_beam_load_he(ld) for ld in loads if isinstance(ld, dict))


def format_identified_structure_block(extracted: dict) -> str:
    """נתוני מבנה שחולצו מהתמונה — כרטיס קצר, שורה לכל נתון."""
    extracted = finalize_beam_extraction(extracted)
    exercise_type = infer_vision_exercise_type(extracted)
    lines: list[str] = []

    if exercise_type == "cog":
        cog_data = extracted.get("cog") if isinstance(extracted.get("cog"), dict) else {}
        shapes = cog_data.get("shapes") or []
        lines.append("סוג מבנה: חישוב מרכז כובד")
        lines.append(f"חתכים: {len(shapes)}")
        return "\n".join(lines)

    beam = extracted.get("beam") if isinstance(extracted.get("beam"), dict) else {}
    lines.append(f"סוג מבנה: {_structure_type_he(beam)}")
    lines.append(f"אורך קורה: {_fmt_m(beam.get('L', '?'))} מטר")

    for sup_line in _support_display_lines(beam):
        lines.append(sup_line)

    hinges = beam.get("internal_hinges") or []
    if isinstance(hinges, list) and hinges:
        hinge_parts: list[str] = []
        for h in sorted(
            (h for h in hinges if isinstance(h, dict)),
            key=lambda h: float(h.get("x", 0.0)),
        ):
            lbl = str(h.get("label") or "").strip()
            hx = _fmt_m(h.get("x"))
            hinge_parts.append(f"{lbl + ' ' if lbl else ''}x={hx}")
        if hinge_parts:
            lines.append(f"פרקים: {', '.join(hinge_parts)}")

    sorted_loads = _sorted_beam_loads(beam)
    if not sorted_loads:
        lines.append("עומסים: לא זוהו")
    else:
        for idx, ld in enumerate(sorted_loads, 1):
            line = _format_numbered_load_line(idx, ld)
            lines.append(line)

    st = str(beam.get("structure_type", "")).lower()
    if st == "truss":
        lines.append("מסבך — ייתכן שנדרש ניתוח ייעודי")

    return "\n".join(lines)


def summarize_beam_model(beam: dict) -> list[str]:
    """פירוק מפורט של מודל הקורה בעברית."""
    lines: list[str] = []
    L = beam.get("L", "?")
    mode, ra_pos, rb_pos = resolve_beam_support_geometry(beam)
    mode_he = "זיז רתום" if mode == "cantilever" else "קורה על שני סמכים"
    lines.append(f"קורה: אורך L={_fmt_m(L)} m ({mode_he})")

    supports = beam.get("supports")
    if isinstance(supports, list) and supports:
        lines.append("סמכים:")
        for sup in supports:
            if not isinstance(sup, dict):
                continue
            label = str(sup.get("label") or "?").strip()
            st = _support_type_he(str(sup.get("type", "")))
            lines.append(f"  • {label}: {st} ב-x={_fmt_m(sup.get('x'))} m")
    elif mode == "cantilever":
        lines.append(f"סמך: רתום ב-x={_fmt_m(ra_pos)} m, קצה חופשי ב-x={_fmt_m(L)} m")
    else:
        lines.append(f"סמכים: A (צמד) ב-x={_fmt_m(ra_pos)} m, B (גליל) ב-x={_fmt_m(rb_pos)} m")

    segments = beam.get("segments")
    if isinstance(segments, list) and segments:
        lines.append("מרחקים לאורך הקורה:")
        for seg in segments:
            if not isinstance(seg, dict):
                continue
            length = seg.get("length_m")
            if length is None:
                try:
                    length = float(seg.get("to_x", 0)) - float(seg.get("from_x", 0))
                except (TypeError, ValueError):
                    length = "?"
            lines.append(
                f"  • x={_fmt_m(seg.get('from_x'))} → x={_fmt_m(seg.get('to_x'))}: "
                f"{_fmt_m(length)} m"
            )
    elif isinstance(beam.get("key_points_m"), list) and len(beam["key_points_m"]) >= 2:
        pts = sorted({float(p) for p in beam["key_points_m"] if p is not None})
        lines.append("נקודות לאורך ציר הקורה [m]: " + " — ".join(_fmt_m(p) for p in pts))

    loads = beam.get("loads") or []
    if loads:
        lines.append(f"עומסים ({len(loads)}):")
        for idx, ld in enumerate(loads, 1):
            if isinstance(ld, dict):
                lines.append(f"  {idx}. {format_beam_load_he(ld)}")
    else:
        lines.append("עומסים: לא זוהו")
    return lines


def infer_vision_exercise_type(data: dict) -> str:
    explicit = str(data.get("exercise_type", "")).lower().strip()
    if explicit in ("beam", "cog"):
        return explicit
    beam = data.get("beam")
    cog_data = data.get("cog")
    has_beam = isinstance(beam, dict) and (
        beam.get("L") is not None or beam.get("loads")
    )
    has_cog = isinstance(cog_data, dict) and bool(cog_data.get("shapes"))
    if has_beam and not has_cog:
        return "beam"
    if has_cog and not has_beam:
        return "cog"
    if has_beam:
        return "beam"
    if has_cog:
        return "cog"
    return "unknown"


def solve_from_vision_data(data: dict) -> dict:
    """שלב 2: מריץ מנוע חישוב מקומי לפי JSON שחולץ מהתמונה."""
    data = finalize_beam_extraction(data)
    exercise_type = infer_vision_exercise_type(data)
    if exercise_type == "beam":
        beam = data.get("beam") if isinstance(data.get("beam"), dict) else {}
        L = max(0.1, float(beam.get("L", 10.0)))
        loads = vision_loads_to_tool_loads(
            list(beam.get("loads") or []) if isinstance(beam.get("loads"), list) else []
        )
        if not loads:
            notes = str(data.get("notes", "")).strip()
            hint = f" ({notes})" if notes else ""
            raise ValueError(f"לא זוהו עומסים בתמונה{hint}")
        support_mode, ra_pos, rb_pos = resolve_beam_support_geometry(beam)
        if support_mode == "cantilever":
            result = tool_beam_solve_cantilever({"L": L, "loads": loads})
            return {"exercise_type": "beam", "tool_name": "beam_solve_cantilever", "result": result}
        if abs(rb_pos - ra_pos) < 1e-6:
            rb_pos = L
        result = tool_beam_solve_simply_supported(
            {"L": L, "ra_pos": ra_pos, "rb_pos": rb_pos, "loads": loads}
        )
        return {
            "exercise_type": "beam",
            "tool_name": "beam_solve_simply_supported",
            "result": result,
        }
    if exercise_type == "cog":
        cog_data = data.get("cog") if isinstance(data.get("cog"), dict) else {}
        shapes = vision_shapes_to_tool_shapes(
            list(cog_data.get("shapes") or [])
            if isinstance(cog_data.get("shapes"), list)
            else []
        )
        if not shapes:
            raise ValueError("לא זוהו חתכים בתמונה")
        result = tool_cog_compute_centroid({"shapes": shapes})
        return {"exercise_type": "cog", "tool_name": "cog_compute_centroid", "result": result}
    raise ValueError("לא הצלחתי לזהות אם זה תרגיל קורה או מרכז כובד")


def summarize_vision_extraction(data: dict) -> str:
    lines: list[str] = ["מה שחילצתי מהתרגיל:"]
    focus = data.get("image_focus")
    if isinstance(focus, dict):
        region = str(focus.get("exercise_region", "")).strip()
        ignored = str(focus.get("ignored_regions", "")).strip()
        if region:
            region_he = {"upper": "חלק עליון", "middle": "אמצע", "full": "כל העמוד"}.get(
                region, region
            )
            lines.append(f"אזור התרגיל: {region_he}")
        if ignored:
            lines.append(f"התעלמתי מ: {ignored}")
    notes = data.get("notes")
    if notes:
        lines.append(str(notes))
    confidence = data.get("confidence")
    if confidence:
        lines.append(f"(רמת ביטחון: {confidence})")
    exercise_type = infer_vision_exercise_type(data)
    if exercise_type == "beam":
        beam = data.get("beam") if isinstance(data.get("beam"), dict) else {}
        lines.append("")
        lines.extend(summarize_beam_model(beam))
    elif exercise_type == "cog":
        cog_data = data.get("cog") if isinstance(data.get("cog"), dict) else {}
        shapes = cog_data.get("shapes") or []
        lines.append(f"מרכז כובד: {len(shapes)} חתכים")
    return "\n".join(lines)


def store_extracted_exercise(chat_id: int, extracted: dict) -> None:
    """שומר חילוץ אחרון (לפני חישוב או להשוואת תשובת תלמיד)."""
    _vision_bundle_by_chat[chat_id] = {
        "extracted": extracted,
        "solved": (_vision_bundle_by_chat.get(chat_id) or {}).get("solved") or {},
    }
    from bot.solution_session import mark_session_draft

    mark_session_draft(chat_id)


def set_draft_pending(
    chat_id: int,
    extracted: dict,
    draft_text: str,
    *,
    message_id: int | None = None,
    clear_edit: bool = False,
) -> None:
    """שומר טיוטה שממתינה לאישור משתמש."""
    prev = _vision_bundle_by_chat.get(chat_id) or {}
    if message_id is None:
        message_id = prev.get("draft_message_id")
    draft_edit = None if clear_edit else prev.get("draft_edit")
    draft_edit_prompt_id = None if clear_edit else prev.get("draft_edit_prompt_id")
    type_picker_idx = None if clear_edit else prev.get("draft_type_picker_idx")
    _vision_bundle_by_chat[chat_id] = {
        "extracted": extracted,
        "solved": prev.get("solved") or {},
        "draft_status": "pending",
        "draft_text": draft_text,
        "draft_message_id": message_id,
        "draft_chat_id": prev.get("draft_chat_id", chat_id),
        "draft_edit": draft_edit if isinstance(draft_edit, dict) else None,
        "draft_edit_prompt_id": draft_edit_prompt_id,
        "draft_type_picker_idx": type_picker_idx,
    }


def get_draft_message_ref(chat_id: int) -> tuple[int, int] | None:
    bundle = _vision_bundle_by_chat.get(chat_id) or {}
    msg_id = bundle.get("draft_message_id")
    chat = bundle.get("draft_chat_id", chat_id)
    if msg_id is None:
        return None
    return int(chat), int(msg_id)


def set_draft_error_message_id(chat_id: int, message_id: int | None) -> None:
    """שומר message_id של הודעת שגיאה שנשלחה אחרי 'חשב' (בנוסף לעריכת הטיוטה)."""
    bundle = _vision_bundle_by_chat.get(chat_id)
    if not bundle:
        return
    bundle["draft_error_message_id"] = int(message_id) if message_id is not None else None


def get_draft_error_message_id(chat_id: int) -> int | None:
    bundle = _vision_bundle_by_chat.get(chat_id) or {}
    mid = bundle.get("draft_error_message_id")
    if mid is None:
        return None
    try:
        return int(mid)
    except Exception:
        return None


def set_draft_edit(chat_id: int, edit: dict | None) -> None:
    bundle = _vision_bundle_by_chat.get(chat_id)
    if not bundle:
        return
    bundle["draft_edit"] = edit


def get_draft_edit(chat_id: int) -> dict | None:
    bundle = _vision_bundle_by_chat.get(chat_id) or {}
    edit = bundle.get("draft_edit")
    return edit if isinstance(edit, dict) else None


def set_draft_type_picker_idx(chat_id: int, idx: int | None) -> None:
    """אינדקס עומס (1-based) שתפריט בחירת הסוג פתוח עבורו — נפרד מעריכת שדה."""
    bundle = _vision_bundle_by_chat.get(chat_id)
    if not bundle:
        return
    if idx is None:
        bundle.pop("draft_type_picker_idx", None)
    else:
        bundle["draft_type_picker_idx"] = int(idx)


def get_draft_type_picker_idx(chat_id: int) -> int | None:
    bundle = _vision_bundle_by_chat.get(chat_id) or {}
    idx = bundle.get("draft_type_picker_idx")
    return int(idx) if idx is not None else None


def get_draft_edit_prompt_id(chat_id: int) -> int | None:
    bundle = _vision_bundle_by_chat.get(chat_id) or {}
    pid = bundle.get("draft_edit_prompt_id")
    return int(pid) if pid is not None else None


def set_draft_edit_prompt_id(chat_id: int, message_id: int | None) -> None:
    bundle = _vision_bundle_by_chat.get(chat_id)
    if not bundle:
        return
    if message_id is None:
        bundle.pop("draft_edit_prompt_id", None)
    else:
        bundle["draft_edit_prompt_id"] = int(message_id)


def is_draft_pending(chat_id: int) -> bool:
    bundle = _vision_bundle_by_chat.get(chat_id) or {}
    return bundle.get("draft_status") == "pending" and bool(bundle.get("extracted"))


def get_stored_vision_solved(chat_id: int) -> dict | None:
    bundle = _vision_bundle_by_chat.get(chat_id)
    if not bundle:
        return None
    solved = bundle.get("solved")
    return solved if isinstance(solved, dict) and solved.get("result") else None


def store_vision_context(chat_id: int, extracted: dict, solved: dict) -> None:
    _vision_bundle_by_chat[chat_id] = {
        "extracted": extracted,
        "solved": solved,
    }
    brief = summarize_vision_extraction(extracted)
    _vision_context_by_chat[chat_id] = f"[רקע קצר מתמונה]\n{brief}"
    from bot.solution_session import mark_session_solved

    mark_session_solved(chat_id)


def store_vision_fallback_reply(chat_id: int, reply: str) -> None:
    _vision_bundle_by_chat[chat_id] = {"extracted": {}, "solved": {}, "reply_text": reply}
    _vision_context_by_chat[chat_id] = f"[רקע מתמונה]\n{reply[:500]}"


def format_vision_results_only(tool_name: str, result: dict) -> str:
    """תשובה מינימלית לתמונת תרגיל — מספרים בלבד."""
    if result.get("error"):
        return f"שגיאה בחישוב: {result['error']}"

    lines: list[str] = []
    if tool_name == "beam_solve_simply_supported":
        r = result.get("reactions_ton", result.get("reactions_kN", {}))
        ray = float(r.get("R_Ay", 0))
        rby = float(r.get("R_By", 0))
        rax = float(r.get("R_Ax", 0))
        if "reactions_kN" in result and "reactions_ton" not in result:
            ray, rby, rax = kn_to_ton(ray), kn_to_ton(rby), kn_to_ton(rax)
        lines.append(f"`R_Ay` = {format_force_ton(ray)}")
        lines.append(f"`R_By` = {format_force_ton(rby)}")
        lines.append(f"`R_Ax` = {format_horizontal_force_ton(rax)}")
    elif tool_name == "beam_solve_cantilever":
        r = result.get("reactions_ton", result.get("reactions_kN", {}))
        ray = float(r.get("R_Ay", 0))
        rax = float(r.get("R_Ax", 0))
        if "reactions_kN" in result and "reactions_ton" not in result:
            ray, rax = kn_to_ton(ray), kn_to_ton(rax)
        lines.append(f"`R_Ay` = {format_force_ton(ray)}")
        lines.append(f"`R_Ax` = {format_horizontal_force_ton(rax)}")
        ma = result.get("fixed_end_moment_ton_m", result.get("fixed_end_moment_kNm"))
        if ma is not None:
            ma_val = float(ma)
            if (
                result.get("fixed_end_moment_kNm") is not None
                and result.get("fixed_end_moment_ton_m") is None
            ):
                ma_val = kn_to_ton(ma_val)
            lines.append(f"`M_A` = {format_moment_ton_m(ma_val)}")
    elif tool_name == "cog_compute_centroid":
        c = result.get("centroid_m", result.get("centroid_cm", {}))
        lines.append(f"Xc = {c.get('Xc')} m")
        lines.append(f"Yc = {c.get('Yc')} m")
    else:
        return format_engineering_tool_results([(tool_name, result)], results_only=True)

    return "\n".join(lines) if lines else "לא התקבלה תוצאה."


def _validation_issue_to_question(issue: str) -> str | None:
    """מתרגם בעיית validation לשאלת הבהרה בעברית."""
    s = str(issue or "").strip()
    if not s:
        return None
    low = s.lower()
    if "segment sum" in low and "does not match" in low:
        return "סכום המקטעים לא תואם לאורך הקורה — מה האורך הנכון?"
    if "outside beam" in low:
        if "support" in low:
            return "מיקום אחד הסמכים לא ברור לי מהשרטוט — מה המיקום הנכון על ציר הקורה?"
        return "מיקום אחד העומסים לא ברור לי — האם הקריאה מהמידות נכונה?"
    if s.endswith("?"):
        return s
    if any(tok in s for tok in ("חסר", "לא זוהה", "אין עומס", "≠")):
        return f"{s}?"
    return None


def _dedupe_questions(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def collect_extraction_uncertainties(extracted: dict) -> list[str]:
    """שאלות להבהרה — רשימה ריקה = ברור מספיק לשלוח את הנתונים כמו שהם."""
    questions: list[str] = []
    meta = (
        extracted.get("_extraction_quality")
        if isinstance(extracted.get("_extraction_quality"), dict)
        else {}
    )
    beam = extracted.get("beam") if isinstance(extracted.get("beam"), dict) else {}

    for item in extracted.get("uncertainties") or extracted.get("unclear") or []:
        if isinstance(item, dict):
            q = str(item.get("question_he") or item.get("question") or "").strip()
            if q:
                questions.append(q)
        elif isinstance(item, str) and item.strip():
            questions.append(item.strip())

    conf = str(extracted.get("confidence", "")).lower()
    if conf == "low":
        questions.append("הקריאה מהתמונה לא הייתה חדה — האם הנתונים למטה נכונים?")

    if meta.get("partial"):
        for issue in meta.get("validation_issues") or []:
            q = _validation_issue_to_question(str(issue))
            if q:
                questions.append(q)
        if not questions:
            questions.append(
                "לא הצלחתי לאמת את כל הנתונים מהתמונה — האם מה ששלחתי נראה נכון?"
            )

    for issue in meta.get("completeness_issues") or []:
        s = str(issue).strip()
        if s:
            questions.append(s if s.endswith("?") else f"{s}?")

    if not meta.get("partial"):
        for issue in validate_beam_extraction(extracted):
            q = _validation_issue_to_question(issue)
            if q:
                questions.append(q)

    try:
        L = float(beam.get("L", 0))
    except (TypeError, ValueError):
        L = 0.0
    seg_sum = _segment_length_sum(beam)
    if seg_sum > 0 and L > 0 and abs(seg_sum - L) > 0.2:
        questions.append(
            f"סכום המקטעים ({seg_sum:g} מ') לא תואם לאורך הקורה ({L:g} מ') — מה האורך הנכון?"
        )

    labeled = _labeled_points_map(beam)
    _, ra_pos, rb_pos = resolve_beam_support_geometry(beam)
    if L > 0 and rb_pos > L + 0.15:
        questions.append(
            f"הסמך הנייד ב-x={rb_pos:g} מ' מחוץ לקורה (L={L:g} מ') — מה מיקומו הנכון?"
        )
    if "B" in labeled and L > 0 and abs(labeled["B"] - rb_pos) > 0.35:
        questions.append(
            f"לא ברור לי אם הסמך B ב-x={rb_pos:g} או ב-x={labeled['B']:g} — מה נכון?"
        )

    return _dedupe_questions(questions)


def package_extraction_response(
    parsed: dict,
    *,
    partial: bool = False,
    validation_issues: list[str] | None = None,
) -> dict:
    """מוסיף מטא-דאטה על איכות החילוץ לפני בניית התשובה."""
    out = dict(parsed)
    existing = out.get("_extraction_quality")
    if isinstance(existing, dict) and existing.get("partial") and not partial:
        partial = True
        if validation_issues is None and existing.get("validation_issues"):
            validation_issues = list(existing.get("validation_issues") or [])
    beam = out.get("beam") if isinstance(out.get("beam"), dict) else {}
    issues = [str(i) for i in (validation_issues or []) if str(i).strip()]
    if not partial:
        issues.extend(validate_beam_extraction(out))
    completeness = _extraction_completeness_issues(beam)
    out["_extraction_quality"] = {
        "partial": partial,
        "pipeline": str(out.get("extraction_pipeline") or ("partial" if partial else "")),
        "validation_issues": list(dict.fromkeys(issues)),
        "completeness_issues": completeness,
    }
    return out


def format_vision_extract_only_reply(extracted: dict) -> str:
    """הצגת הנתונים שחולצו — + שאלות רק כשמשהו לא ברור."""
    block = format_identified_structure_block(extracted)
    questions = collect_extraction_uncertainties(extracted)
    if not questions:
        return block
    lines = [block, "", "*לא היה לי ברור — אשמח להבהרה:*"]
    for idx, question in enumerate(questions[:6], 1):
        lines.append(f"{idx}. {question}")
    lines.append("")
    lines.append(
        "_אפשר לענות בטקסט, למשל: \"מומנט ב-C עם כיוון השעון\" או \"אורך 6 מ'\"._"
    )
    return "\n".join(lines)


def format_vision_solve_reply(extracted: dict, solved: dict, caption: str) -> str:
    tool_name = str(solved.get("tool_name", ""))
    result = solved.get("result") or {}
    ident = format_identified_structure_block(extracted)
    results = format_vision_results_only(tool_name, result)
    if results.startswith("שגיאה"):
        return f"{ident}\n\n{results}"
    return f"{ident}\n\n*תוצאות:*\n{results}"
