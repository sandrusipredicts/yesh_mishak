"""Duplicate field detection tooling (ISSUE-043).

Identifies suspicious duplicate sports fields using the ISSUE-042 strategy.
Detection is read-only — it never modifies field data.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from math import asin, cos, radians, sin, sqrt
from typing import Any

DISTANCE_VERY_CLOSE_M = 10
DISTANCE_NEARBY_M = 50
DISTANCE_REVIEW_ZONE_M = 100

NAME_SIMILARITY_STRONG = 0.90
NAME_SIMILARITY_MODERATE = 0.70
NAME_SIMILARITY_WEAK = 0.50

GENERIC_TOKENS = {
    "מגרש", "כדורגל", "כדורסל", "ספורט", "משולב", "ציבורי", "שכונתי",
    "field", "court", "football", "basketball", "sport",
}

RISK_CONFIRMED = 1
RISK_STRONG = 2
RISK_POSSIBLE = 3
RISK_NOT_ENOUGH = 4

RISK_LABELS = {
    RISK_CONFIRMED: "confirmed duplicate candidate",
    RISK_STRONG: "strong duplicate candidate",
    RISK_POSSIBLE: "possible duplicate candidate",
    RISK_NOT_ENOUGH: "not enough evidence",
}


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    earth_radius_m = 6_371_000.0
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * earth_radius_m * asin(sqrt(a))


def normalize_name(name: str) -> str:
    text = unicodedata.normalize("NFC", name)
    text = text.strip().lower()
    text = re.sub(r"[^\w\s]", "", text, flags=re.UNICODE)
    text = " ".join(text.split())
    return text


def _remove_generic_tokens(normalized: str) -> str:
    tokens = normalized.split()
    filtered = [t for t in tokens if t not in GENERIC_TOKENS]
    if len(filtered) < 2:
        return normalized
    return " ".join(filtered)


def name_similarity(name_a: str, name_b: str) -> float:
    norm_a = normalize_name(name_a)
    norm_b = normalize_name(name_b)
    if not norm_a or not norm_b:
        return 0.0
    direct = SequenceMatcher(None, norm_a, norm_b).ratio()
    stripped_a = _remove_generic_tokens(norm_a)
    stripped_b = _remove_generic_tokens(norm_b)
    stripped = SequenceMatcher(None, stripped_a, stripped_b).ratio()
    return max(direct, stripped)


def _is_admin_involved(field: dict[str, Any]) -> bool:
    return bool(field.get("verified")) and field.get("approval_status") == "approved" and field.get("added_by")


def _classify_distance(distance_m: float) -> str:
    if distance_m == 0:
        return "exact"
    if distance_m <= DISTANCE_VERY_CLOSE_M:
        return "very_close"
    if distance_m <= DISTANCE_NEARBY_M:
        return "nearby"
    if distance_m <= DISTANCE_REVIEW_ZONE_M:
        return "review_zone"
    return "far"


def score_pair(
    field_a: dict[str, Any],
    field_b: dict[str, Any],
) -> dict[str, Any] | None:
    lat_a = float(field_a.get("lat") or 0)
    lng_a = float(field_a.get("lng") or 0)
    lat_b = float(field_b.get("lat") or 0)
    lng_b = float(field_b.get("lng") or 0)

    distance_m = _haversine_m(lat_a, lng_a, lat_b, lng_b)
    dist_band = _classify_distance(distance_m)

    name_a_raw = str(field_a.get("name") or "")
    name_b_raw = str(field_b.get("name") or "")
    sim = name_similarity(name_a_raw, name_b_raw)
    exact_name = normalize_name(name_a_raw) == normalize_name(name_b_raw) and normalize_name(name_a_raw) != ""

    same_sport = field_a.get("sport_type") == field_b.get("sport_type")
    admin_involved = _is_admin_involved(field_a) or _is_admin_involved(field_b)

    signals: list[str] = []
    risk = RISK_NOT_ENOUGH
    reason_parts: list[str] = []

    if dist_band == "exact":
        signals.append("exact_coordinates")
    elif dist_band == "very_close":
        signals.append(f"very_close_coordinates ({distance_m:.1f}m)")
    elif dist_band == "nearby":
        signals.append(f"nearby_coordinates ({distance_m:.1f}m)")
    elif dist_band == "review_zone":
        signals.append(f"review_zone_coordinates ({distance_m:.1f}m)")

    if exact_name:
        signals.append("exact_name")
    elif sim >= NAME_SIMILARITY_STRONG:
        signals.append(f"strong_name_similarity ({sim:.2f})")
    elif sim >= NAME_SIMILARITY_MODERATE:
        signals.append(f"moderate_name_similarity ({sim:.2f})")

    if same_sport:
        signals.append("same_sport_type")
    else:
        signals.append("different_sport_type")

    # R2: exact coords + exact name
    if dist_band == "exact" and exact_name:
        risk = RISK_CONFIRMED
        reason_parts.append("Same coordinates and same name")

    # R3: exact coords + different name + same sport
    elif dist_band == "exact" and not exact_name and same_sport:
        risk = RISK_STRONG
        reason_parts.append("Same coordinates, different name, same sport type")

    # R4: very close + similar name (>=0.70) + same sport
    elif dist_band == "very_close" and sim >= NAME_SIMILARITY_MODERATE and same_sport:
        risk = RISK_STRONG
        reason_parts.append("Very close coordinates with similar name and same sport type")

    # R5: very close + exact name + different sport
    elif dist_band == "very_close" and exact_name and not same_sport:
        risk = RISK_STRONG
        reason_parts.append("Very close coordinates with same name but different sport type")

    # R6: nearby + exact name + same sport
    elif dist_band == "nearby" and exact_name and same_sport:
        risk = RISK_STRONG
        reason_parts.append("Nearby coordinates with same name and same sport type")

    # R7: nearby + similar name (>=0.70) + same sport
    elif dist_band == "nearby" and sim >= NAME_SIMILARITY_MODERATE and same_sport:
        risk = RISK_POSSIBLE
        reason_parts.append("Nearby coordinates with similar name and same sport type")

    # R8: nearby + same sport + different name
    elif dist_band == "nearby" and same_sport and sim < NAME_SIMILARITY_MODERATE:
        risk = RISK_POSSIBLE
        reason_parts.append("Nearby coordinates with same sport type but different name")

    # R9: review zone + exact name + same sport
    elif dist_band == "review_zone" and exact_name and same_sport:
        risk = RISK_POSSIBLE
        reason_parts.append("Review-zone distance with same name and same sport type")

    # R13: same name + far + same city
    elif dist_band == "far" and exact_name:
        city_a = " ".join(str(field_a.get("city") or "").strip().lower().split())
        city_b = " ".join(str(field_b.get("city") or "").strip().lower().split())
        if city_a and city_b and city_a == city_b:
            risk = RISK_POSSIBLE
            signals.append("same_city")
            reason_parts.append("Same name and same city but far apart")

    # R14: admin involvement elevates to at least strong
    if admin_involved and risk > RISK_STRONG and risk != RISK_NOT_ENOUGH:
        risk = RISK_STRONG
        signals.append("admin_involved")
        reason_parts.append("Admin-edited field involved — requires admin review")
    elif admin_involved and risk <= RISK_STRONG:
        signals.append("admin_involved")

    if risk == RISK_NOT_ENOUGH:
        return None

    return {
        "field_a": _field_summary(field_a),
        "field_b": _field_summary(field_b),
        "distance_m": round(distance_m, 1),
        "name_similarity": round(sim, 2),
        "matching_signals": signals,
        "risk_level": risk,
        "risk_label": RISK_LABELS[risk],
        "reason": ". ".join(reason_parts) if reason_parts else RISK_LABELS[risk],
    }


def _field_summary(field: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": field.get("id"),
        "name": field.get("name"),
        "lat": field.get("lat"),
        "lng": field.get("lng"),
        "sport_type": field.get("sport_type"),
        "city": field.get("city"),
        "status": field.get("status"),
        "approval_status": field.get("approval_status"),
        "verified": field.get("verified"),
    }


def find_duplicates(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    n = len(fields)
    for i in range(n):
        lat_i = float(fields[i].get("lat") or 0)
        lng_i = float(fields[i].get("lng") or 0)
        for j in range(i + 1, n):
            lat_j = float(fields[j].get("lat") or 0)
            lng_j = float(fields[j].get("lng") or 0)
            # Quick bounding-box pre-filter (~110m per 0.001 degree lat)
            if abs(lat_i - lat_j) > 0.001 and abs(lng_i - lng_j) > 0.001:
                # Both axes are far — skip Haversine and name check
                # unless names match exactly (R13 same-city rule)
                name_i = normalize_name(str(fields[i].get("name") or ""))
                name_j = normalize_name(str(fields[j].get("name") or ""))
                if name_i != name_j or not name_i:
                    continue
            result = score_pair(fields[i], fields[j])
            if result is not None:
                candidates.append(result)

    candidates.sort(key=lambda c: (c["risk_level"], c["distance_m"]))
    return candidates
