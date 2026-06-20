"""Fetch GovMap sports facilities and split them by validation status.

This script is intentionally standalone. It does not write to the app database
or change application behavior. It fetches the GovMap sports layer, keeps the
fields needed for validation, scores each facility, and writes separate JSON
and CSV files for approved, review_required, and rejected candidates.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


GOVMAP_WFS_URL = "https://www.govmap.gov.il/api/geoserver/wfs"
LAYER_NAME = "govmap:layer_sport"

GOVMAP_FIELDS = [
    "objectid",
    "new_name",
    "new_facilityid",
    "new_s_facility_operator",
    "new_id_facility_owner",
    "new_id_facility_type",
    "new_l_activity_available",
    "new_l_facility_condition",
    "new_s_serving_school",
    "new_id_local_authority",
    "new_s_street",
    "new_s_x",
    "new_s_y",
    "new_b_indoor",
    "new_b_lighting",
    "new_b_fencing",
    "new_b_parking",
    "new_b_disabled_access",
    "new_l_surface_type",
    "new_l_competition_standards",
    "new_l_official_competitions",
    "new_n_seats_num",
    "new_id_year_found",
    "new_s_identification_num",
    "new_s_region",
    "shape",
]

OUTPUT_FIELDS = [
    "source_id",
    "name",
    "city",
    "street",
    "lat",
    "lng",
    "sport_type",
    "facility_type",
    "availability_status",
    "condition_status",
    "operator",
    "owner",
    "serving_school",
    "indoor",
    "lighting",
    "fencing",
    "parking",
    "disabled_access",
    "surface_type",
    "confidence_score",
    "classification",
    "classification_reasons",
]

REMOVED_DUPLICATE_FIELDS = [
    "source_id",
    "canonical_source_id",
    "name",
    "city",
    "facility_type",
    "lat",
    "lng",
    "confidence_score",
    "classification_reasons",
]

DUPLICATE_GROUP_FIELDS = [
    "duplicate_key",
    "duplicate_category",
    "recommended_handling",
    "reason_flags",
    "count",
    "approved_count",
    "review_required_count",
    "rejected_count",
    "city",
    "name",
    "facility_type",
    "examples",
]

FOOTBALL_TYPES = {
    "מגרש כדורגל - לא תקני",
    "מגרש כדורגל – 45X90 מ'",
    "מגרש מיני פיץ'",
    "מגרש שחבק דשא סינטטי",
}

BASKETBALL_TYPES = {
    "מגרש כדורסל – 19X32 מ'",
}

BASKETBALL_TO_BOTH_HIGH_KEYWORDS = [
    "קטרגל",
    "קט רגל",
    "קט-רגל",
    "כדורגל",
    "שחבק",
    "שחב\"ק",
    "שחב״ק",
    "מיני פיץ",
    "מיניפיץ",
    "מיני-פיץ",
    "מיני פיטש",
    "מיניפיטש",
]

BASKETBALL_TO_BOTH_MEDIUM_KEYWORDS = [
    "משולב",
    "רב תכליתי",
    "רב-תכליתי",
    "רב תכלית",
]

BASKETBALL_TO_BOTH_GENERIC_SPORT_NAME_KEYWORDS = [
    "מגרש ספורט",
    "ספורטק",
    "מרכז ספורט",
]

BOTH_TYPES = {
    "מגרש ספורט משולב – 43X32 מ'",
}

AMBIGUOUS_PICKUP_TYPES = {
    "אצטדיון כדורגל – 105X70 מ'",
    "מגרש ספורט במידות אחרות – לא תקני",
    "אחר: מתקן ספורט (לציין בשם המתקן את סוג המתקן)",
    "מגרש חול קבוע לכדורעף או לקטרגל או לכדוריד חופים",
}

REJECTED_TYPES = {
    "אולם ספורט בינוני – 32x19 מ'",
    "אולם ספורט קטן – 20x10 מ'",
    "אולם ספורט קטן – 15x24 מ'",
    "אולם ספורט גדול - 45X24 מ'",
    "מתקן פתוח לכושר גופני",
    "בריכת שחיה - 25X12.5 מ'",
    "בריכת שחיה במידות אחרות",
    "בריכת שחיה - 20X50 מ'",
    "מכון לכושר גופני",
    "מגרש טניס",
    "אצטדיון/מסלול אתלטיקה קלה – 6-4 מסלולים 250 או 300 מ'",
    "אצטדיון/מסלול אתלטיקה קלה – תקני 8 מסלולים 400 מ'",
    "מגרש פטאנק או כדורת דשא",
    "שייט מרכז ימי",
    "מסלול מרוץ ספורט מוטורי",
    "מתקן אקסטרים",
}

NON_PICKUP_KEYWORDS = [
    "הוקי",
    "סקטפארק",
    "סקייטפארק",
    "פארק אופניים",
    "פארק אופנים",
    "פאמפטראק",
    "פאמפטרק",
    "פארק כושר",
    "מתקן כושר",
    "כושר",
    "גלגליות",
    "כדורעף חופים",
]

EDUCATION_KEYWORDS = [
    "בית ספר",
    "בית חינוך",
    "בי\"ס",
    "ביה\"ס",
    "בה\"ס",
    "ביס",
    "ביהס",
    "בהס",
    "תיכון",
    "חט\"ב",
    "חטיבה",
    "חטיבת",
    "חטיבת ביניים",
    "ביניים",
    "יסודי",
    "מקיף",
    "ישיבה",
    "ישיבת",
    "ישבת",
    "תלמוד תורה",
    "אולפנה",
    "אולפנא",
    "אולפנת",
    "חדר",
]

EXPANDED_EDUCATION_KEYWORDS = [
    "חינוך",
    "בית חינוך",
    "מוסד חינוכי",
    "מרכז חינוך",
    "שובו",
    "מדעים",
    "פרחי המדע",
    "שז\"ר",
    "שזר",
    "יבניאלי",
    "נריה בנים",
    "זבולון המר",
    "בני עקיבא",
    "אמי\"ת",
    "אמית",
]

WORD_EDUCATION_KEYWORDS = [
    "אורט",
    "עמל",
]

STADIUM_KEYWORDS = [
    "אצטדיון",
    "איצטדיון",
]

APPROVED_KEYWORDS = [
    "ספורטק",
    "פארק",
    "גן ציבורי",
    "שטח ציבורי פתוח",
    "מגרש שכונתי",
    "מגרש פתוח",
    "מגרש קהילתי",
]

MUNICIPAL_KEYWORDS = [
    "עיריית",
    "עיריה",
    "עירית",
    "מועצה מקומית",
    "מועצה אזורית",
    "מחלקת ספורט",
    "המחלקה לספורט",
    "רשות מקומית",
]

REVIEW_KEYWORDS = [
    "עמותה",
    "אגודה",
]

REJECTED_KEYWORDS = [
    "אוניברסיטה",
    "מכללה",
    "קמפוס",
    "סטודנטים",
    "צה\"ל",
    "בסיס",
    "מחנה",
    "פיקוד",
    "משטרה",
    "שב\"ס",
    "מג\"ב",
    "כפר נוער",
    "פנימיה",
    "בית הלוחם",
    "פרטי",
    "חברים בלבד",
    "מנויים",
    "קאנטרי",
]

ACTIVE_CONDITIONS = {"תקין ופעיל", "פעיל וזקוק לשיפוץ"}
BAD_CONDITIONS = {"לא תקין ולא פעיל", "לא פעיל", "סגור לשימוש"}
OPEN_AVAILABILITY = "פתוח ללא הגבלה"
APPROVAL_BLOCKED_AVAILABILITY = {
    "בתיאום בלבד",
    "כניסה בתשלום במקום",
    "בוקר בלבד",
    "אחה\"צ בלבד",
}
LIMITED_BUT_APPROVABLE_AVAILABILITY = {"מבוקר ועד לילה", "אחה\"צ ולילה"}


@dataclass(frozen=True)
class ClassifiedFacility:
    row: dict[str, Any]
    score: int
    classification: str
    reasons: list[str]


def clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def contains_any(text: str, keywords: list[str]) -> list[str]:
    return [keyword for keyword in keywords if keyword and keyword in text]


def contains_word(text: str, keyword: str) -> bool:
    return re.search(rf"(?<![א-ת]){re.escape(keyword)}(?![א-ת])", text) is not None


def contains_restricted_keywords(text: str) -> list[str]:
    return contains_any(text, REJECTED_KEYWORDS)


def contains_education_keywords(text: str) -> list[str]:
    hits = contains_any(text, EDUCATION_KEYWORDS)
    hits.extend(keyword for keyword in WORD_EDUCATION_KEYWORDS if contains_word(text, keyword))
    return hits


def contains_expanded_education_keywords(text: str) -> list[str]:
    return contains_any(text, EXPANDED_EDUCATION_KEYWORDS)


def extract_coordinates(properties: dict[str, Any], geometry: dict[str, Any] | None) -> tuple[str, str]:
    lng = clean(properties.get("new_s_x"))
    lat = clean(properties.get("new_s_y"))

    coordinates = (geometry or {}).get("coordinates")
    if isinstance(coordinates, list) and len(coordinates) >= 2:
        lng = lng or clean(coordinates[0])
        lat = lat or clean(coordinates[1])

    return lat, lng


def source_id(feature: dict[str, Any], properties: dict[str, Any]) -> str:
    return (
        clean(properties.get("new_facilityid"))
        or clean(properties.get("objectid"))
        or clean(feature.get("id"))
    )


def sport_type_for(facility_type: str) -> str:
    if facility_type in FOOTBALL_TYPES:
        return "football"
    if facility_type in BASKETBALL_TYPES:
        return "basketball"
    if facility_type in BOTH_TYPES:
        return "both"
    return ""


def basketball_to_both_signal(row: dict[str, Any]) -> tuple[str | None, list[str], bool]:
    if row["sport_type"] != "basketball":
        return None, [], False

    text = " ".join(
        [
            row["name"],
            row["facility_type"],
            row["operator"],
            row["owner"],
            row["surface_type"],
        ]
    )
    high_hits = contains_any(text, BASKETBALL_TO_BOTH_HIGH_KEYWORDS)
    medium_hits = contains_any(row["name"], BASKETBALL_TO_BOTH_MEDIUM_KEYWORDS)
    generic_sport_hits = [
        keyword
        for keyword in BASKETBALL_TO_BOTH_GENERIC_SPORT_NAME_KEYWORDS
        if keyword in row["name"] and not contains_any(row["name"], ["כדורסל", "כדור סל", "סטריטבול"])
    ]
    medium_all_hits = medium_hits + generic_sport_hits
    if high_hits:
        return "high", high_hits + medium_all_hits, bool(medium_all_hits)

    if medium_all_hits:
        return "medium", medium_all_hits, False

    return None, [], False


def apply_basketball_to_both_override(row: dict[str, Any]) -> dict[str, Any]:
    confidence, keywords, overlap = basketball_to_both_signal(row)
    if confidence is None:
        row["sport_type_conversion_confidence"] = ""
        row["sport_type_conversion_keywords"] = ""
        row["sport_type_conversion_overlap"] = False
        return row

    row["sport_type"] = "both"
    row["sport_type_conversion_confidence"] = confidence
    row["sport_type_conversion_keywords"] = ";".join(keywords)
    row["sport_type_conversion_overlap"] = overlap
    return row


def normalize_feature(feature: dict[str, Any]) -> dict[str, Any]:
    properties = feature.get("properties") or {}
    geometry = feature.get("geometry")
    lat, lng = extract_coordinates(properties, geometry)

    row = {
        "source_id": source_id(feature, properties),
        "name": clean(properties.get("new_name")),
        "city": clean(properties.get("new_id_local_authority")),
        "street": clean(properties.get("new_s_street")),
        "lat": lat,
        "lng": lng,
        "sport_type": sport_type_for(clean(properties.get("new_id_facility_type"))),
        "facility_type": clean(properties.get("new_id_facility_type")),
        "availability_status": clean(properties.get("new_l_activity_available")),
        "condition_status": clean(properties.get("new_l_facility_condition")),
        "operator": clean(properties.get("new_s_facility_operator")),
        "owner": clean(properties.get("new_id_facility_owner")),
        "serving_school": clean(properties.get("new_s_serving_school")),
        "indoor": clean(properties.get("new_b_indoor")),
        "lighting": clean(properties.get("new_b_lighting")),
        "fencing": clean(properties.get("new_b_fencing")),
        "parking": clean(properties.get("new_b_parking")),
        "disabled_access": clean(properties.get("new_b_disabled_access")),
        "surface_type": clean(properties.get("new_l_surface_type")),
    }
    return apply_basketball_to_both_override(row)


def classify(row: dict[str, Any]) -> ClassifiedFacility:
    score = 50
    reasons: list[str] = []
    hard_reject = False
    approval_blocked = False
    force_review = False

    joined_text = " ".join(
        [
            row["name"],
            row["facility_type"],
            row["operator"],
            row["owner"],
            row["serving_school"],
        ]
    )

    facility_type = row["facility_type"]
    availability = row["availability_status"]
    condition = row["condition_status"]
    serving_school = row["serving_school"]
    non_pickup_hits = contains_any(joined_text, NON_PICKUP_KEYWORDS)
    education_hits = contains_education_keywords(joined_text)
    expanded_education_hits = contains_expanded_education_keywords(joined_text)
    stadium_hits = contains_any(joined_text, STADIUM_KEYWORDS)

    if row["sport_type"]:
        score += 25
        reasons.append("pickup_sport_type")
        if row.get("sport_type_conversion_confidence") == "high":
            reasons.append("basketball_to_both_high")
        elif row.get("sport_type_conversion_confidence") == "medium":
            reasons.append("basketball_to_both_medium")
        if row.get("sport_type_conversion_overlap"):
            reasons.append("basketball_to_both_overlap")
    elif facility_type in AMBIGUOUS_PICKUP_TYPES:
        score -= 10
        approval_blocked = True
        reasons.append("ambiguous_sport_type")
    elif facility_type in REJECTED_TYPES:
        score -= 50
        hard_reject = True
        reasons.append("non_pickup_facility_type")
    else:
        score -= 20
        approval_blocked = True
        reasons.append("unknown_or_other_facility_type")

    if condition in ACTIVE_CONDITIONS:
        score += 15
        reasons.append("active_condition")
    elif condition in BAD_CONDITIONS:
        score -= 50
        hard_reject = True
        reasons.append("inactive_or_closed_condition")
    else:
        score -= 10
        reasons.append("uncertain_condition")

    if availability == OPEN_AVAILABILITY:
        score += 20
        reasons.append("open_without_restriction")
    elif availability in APPROVAL_BLOCKED_AVAILABILITY:
        score -= 30
        approval_blocked = True
        reasons.append("approval_blocked_availability")
    elif availability in LIMITED_BUT_APPROVABLE_AVAILABILITY:
        score += 5
        reasons.append("limited_but_public_availability")
    else:
        score -= 10
        approval_blocked = True
        reasons.append("unknown_availability")

    if serving_school and serving_school != "לא":
        score -= 40
        approval_blocked = True
        force_review = True
        reasons.append("school_association")

    if education_hits:
        score -= 35
        approval_blocked = True
        force_review = True
        reasons.append("education_keyword")

    if expanded_education_hits:
        score -= 35
        approval_blocked = True
        force_review = True
        reasons.append("expanded_education_keyword")

    if stadium_hits or (facility_type in AMBIGUOUS_PICKUP_TYPES and "אצטדיון" in facility_type):
        score -= 15
        approval_blocked = True
        force_review = True
        reasons.append("stadium_review_required")

    municipal_hits = contains_any(joined_text, MUNICIPAL_KEYWORDS)
    if municipal_hits:
        score += 10
        reasons.append("municipal_operator_or_owner")

    approved_hits = contains_any(joined_text, APPROVED_KEYWORDS)
    if approved_hits:
        score += 10
        reasons.append("public_place_keyword")

    review_hits = contains_any(joined_text, REVIEW_KEYWORDS)
    if review_hits:
        score -= 10
        reasons.append("manual_review_keyword")

    rejected_hits = contains_restricted_keywords(joined_text)
    if rejected_hits:
        score -= 45
        hard_reject = True
        reasons.append("restricted_keyword")

    if non_pickup_hits:
        score -= 50
        hard_reject = True
        reasons.append("non_pickup_keyword")

    if row["indoor"] == "כן" and row["sport_type"] == "football":
        score -= 15
        approval_blocked = True
        reasons.append("indoor_football_unusual")

    score = max(0, min(100, score))

    if hard_reject or score < 45 and not force_review:
        classification = "rejected"
    elif force_review:
        classification = "review_required"
    elif score >= 80 and not approval_blocked:
        classification = "approved"
    else:
        classification = "review_required"

    return ClassifiedFacility(row=row, score=score, classification=classification, reasons=reasons)


def fetch_features(count: int, cql_filter: str | None) -> list[dict[str, Any]]:
    params = {
        "SERVICE": "WFS",
        "VERSION": "2.0.0",
        "REQUEST": "GetFeature",
        "TYPENAMES": LAYER_NAME,
        "OUTPUTFORMAT": "application/json",
        "COUNT": str(count),
        "PROPERTYNAME": ",".join(GOVMAP_FIELDS),
    }
    if cql_filter:
        params["CQL_FILTER"] = cql_filter

    response = requests.get(GOVMAP_WFS_URL, params=params, timeout=60)
    response.raise_for_status()
    payload = response.json()
    return payload.get("features") or []


def write_json(path: Path, facilities: list[ClassifiedFacility]) -> None:
    path.write_text(
        json.dumps([output_row(facility) for facility in facilities], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_csv(path: Path, facilities: list[ClassifiedFacility]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(output_row(facility) for facility in facilities)


def write_duplicate_csv(path: Path, groups: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=DUPLICATE_GROUP_FIELDS)
        writer.writeheader()
        writer.writerows(groups)


def write_removed_duplicate_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=REMOVED_DUPLICATE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def output_row(facility: ClassifiedFacility) -> dict[str, Any]:
    row = {field: facility.row.get(field, "") for field in OUTPUT_FIELDS}
    row["confidence_score"] = facility.score
    row["classification"] = facility.classification.upper()
    row["classification_reasons"] = ";".join(facility.reasons)
    return row


def exact_approved_duplicate_key(facility: ClassifiedFacility) -> tuple[str, str, str, str] | None:
    row = facility.row
    if not row["name"] or not row["facility_type"] or not row["lat"] or not row["lng"]:
        return None
    return (row["name"], row["lat"], row["lng"], row["facility_type"])


def removed_duplicate_row(
    duplicate: ClassifiedFacility,
    canonical: ClassifiedFacility,
) -> dict[str, Any]:
    row = duplicate.row
    return {
        "source_id": row["source_id"],
        "canonical_source_id": canonical.row["source_id"],
        "name": row["name"],
        "city": row["city"],
        "facility_type": row["facility_type"],
        "lat": row["lat"],
        "lng": row["lng"],
        "confidence_score": duplicate.score,
        "classification_reasons": ";".join(duplicate.reasons),
    }


def remove_exact_approved_duplicates(
    facilities: list[ClassifiedFacility],
) -> tuple[list[ClassifiedFacility], list[dict[str, Any]]]:
    seen: dict[tuple[str, str, str, str], ClassifiedFacility] = {}
    output: list[ClassifiedFacility] = []
    removed: list[dict[str, Any]] = []

    for facility in sorted(facilities, key=lambda item: item.row["source_id"]):
        if facility.classification != "approved":
            output.append(facility)
            continue

        key = exact_approved_duplicate_key(facility)
        if key is None:
            output.append(facility)
            continue

        canonical = seen.get(key)
        if canonical is None:
            seen[key] = facility
            output.append(facility)
            continue

        removed.append(removed_duplicate_row(facility, canonical))

    return output, removed


def duplicate_key(facility: ClassifiedFacility) -> tuple[str, str, str]:
    row = facility.row
    return (row["name"], row["city"], row["facility_type"])


def classify_duplicate_group(group: list[ClassifiedFacility]) -> tuple[str, str, list[str]]:
    rows = [facility.row for facility in group]
    reasons: list[str] = []
    names = {row["name"] for row in rows}
    cities = {row["city"] for row in rows}
    types = {row["facility_type"] for row in rows}
    streets = {row["street"] for row in rows if row["street"]}
    coordinates = {(row["lat"], row["lng"]) for row in rows if row["lat"] and row["lng"]}
    operators = {row["operator"] for row in rows if row["operator"]}
    schools = {row["serving_school"] for row in rows if row["serving_school"]}

    if len(coordinates) == 1:
        reasons.append("same_coordinates")
    if len(streets) > 1:
        reasons.append("multiple_streets")
    if len(operators) > 1:
        reasons.append("multiple_operators")
    if schools:
        reasons.append("school_values_present")

    if len(names) == 1 and len(cities) == 1 and len(types) == 1 and len(coordinates) == 1:
        return ("likely_true_duplicates", "merge", reasons)

    if len(names) == 1 and len(cities) == 1 and len(types) == 1 and len(group) >= 3:
        return ("likely_sports_complex_multiple_facilities", "keep_separate_with_review", reasons)

    if len(streets) > 1 or len(operators) > 1:
        return ("likely_sports_complex_multiple_facilities", "keep_separate", reasons)

    return ("uncertain", "review", reasons)


def duplicate_group_row(key: tuple[str, str, str], group: list[ClassifiedFacility]) -> dict[str, Any]:
    category, handling, reasons = classify_duplicate_group(group)
    classifications = [facility.classification for facility in group]
    examples = [
        {
            "source_id": facility.row["source_id"],
            "name": facility.row["name"],
            "city": facility.row["city"],
            "street": facility.row["street"],
            "lat": facility.row["lat"],
            "lng": facility.row["lng"],
            "classification": facility.classification.upper(),
            "score": facility.score,
        }
        for facility in group[:10]
    ]
    name, city, facility_type = key
    return {
        "duplicate_key": " | ".join(key),
        "duplicate_category": category,
        "recommended_handling": handling,
        "count": len(group),
        "approved_count": classifications.count("approved"),
        "review_required_count": classifications.count("review_required"),
        "rejected_count": classifications.count("rejected"),
        "city": city,
        "name": name,
        "facility_type": facility_type,
        "examples": json.dumps(examples, ensure_ascii=False),
        "reason_flags": reasons,
    }


def analyze_duplicates(facilities: list[ClassifiedFacility]) -> dict[str, Any]:
    groups: dict[tuple[str, str, str], list[ClassifiedFacility]] = {}
    for facility in facilities:
        key = duplicate_key(facility)
        if all(key):
            groups.setdefault(key, []).append(facility)

    duplicate_groups = [
        duplicate_group_row(key, group)
        for key, group in groups.items()
        if len(group) > 1
    ]
    duplicate_groups.sort(key=lambda group: (-group["count"], group["duplicate_key"]))

    category_summary: dict[str, dict[str, int]] = {}
    for group in duplicate_groups:
        category = group["duplicate_category"]
        summary = category_summary.setdefault(
            category,
            {
                "groups": 0,
                "rows": 0,
                "approved_rows": 0,
                "review_required_rows": 0,
                "rejected_rows": 0,
            },
        )
        summary["groups"] += 1
        summary["rows"] += group["count"]
        summary["approved_rows"] += group["approved_count"]
        summary["review_required_rows"] += group["review_required_count"]
        summary["rejected_rows"] += group["rejected_count"]

    recommended_handling_summary: dict[str, dict[str, int]] = {}
    for group in duplicate_groups:
        handling = group["recommended_handling"]
        summary = recommended_handling_summary.setdefault(handling, {"groups": 0, "rows": 0})
        summary["groups"] += 1
        summary["rows"] += group["count"]

    return {
        "total_duplicate_groups": len(duplicate_groups),
        "total_duplicate_rows": sum(group["count"] for group in duplicate_groups),
        "categories": category_summary,
        "recommended_handling": recommended_handling_summary,
        "groups": duplicate_groups,
    }


def moved_to_review_by_expanded_education_rule(facility: ClassifiedFacility) -> bool:
    if facility.classification != "review_required":
        return False
    if "expanded_education_keyword" not in facility.reasons:
        return False

    other_blocking_reasons = {
        "school_association",
        "education_keyword",
        "stadium_review_required",
        "approval_blocked_availability",
        "ambiguous_sport_type",
        "unknown_or_other_facility_type",
        "unknown_availability",
        "indoor_football_unusual",
        "restricted_keyword",
        "non_pickup_keyword",
        "non_pickup_facility_type",
        "inactive_or_closed_condition",
    }
    if any(reason in facility.reasons for reason in other_blocking_reasons):
        return False

    return min(100, facility.score + 35) >= 80


def write_outputs(output_dir: Path, facilities: list[ClassifiedFacility]) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_facilities, removed_duplicates = remove_exact_approved_duplicates(facilities)

    for classification in ("approved", "review_required", "rejected"):
        classified = [facility for facility in output_facilities if facility.classification == classification]
        write_json(output_dir / f"{classification}.json", classified)
        write_csv(output_dir / f"{classification}.csv", classified)

    duplicate_analysis = analyze_duplicates(output_facilities)
    duplicate_groups = duplicate_analysis["groups"]

    school_related_review = sum(
        1
        for facility in output_facilities
        if facility.classification == "review_required"
        and (
            "school_association" in facility.reasons
            or "education_keyword" in facility.reasons
            or "expanded_education_keyword" in facility.reasons
        )
    )
    additional_expanded_education_review = sum(
        1
        for facility in output_facilities
        if moved_to_review_by_expanded_education_rule(facility)
    )
    stadium_review = sum(
        1
        for facility in output_facilities
        if facility.classification == "review_required"
        and "stadium_review_required" in facility.reasons
    )
    non_pickup_rejected = sum(
        1
        for facility in output_facilities
        if facility.classification == "rejected"
        and "non_pickup_keyword" in facility.reasons
    )
    basketball_to_both_high = sum(
        1
        for facility in output_facilities
        if facility.classification == "approved"
        and "basketball_to_both_high" in facility.reasons
    )
    basketball_to_both_medium = sum(
        1
        for facility in output_facilities
        if facility.classification == "approved"
        and "basketball_to_both_medium" in facility.reasons
    )
    basketball_to_both_overlap = sum(
        1
        for facility in output_facilities
        if facility.classification == "approved"
        and "basketball_to_both_overlap" in facility.reasons
    )

    summary = {
        "total_input": len(facilities),
        "total": len(output_facilities),
        "approved": sum(1 for facility in output_facilities if facility.classification == "approved"),
        "review_required": sum(1 for facility in output_facilities if facility.classification == "review_required"),
        "rejected": sum(1 for facility in output_facilities if facility.classification == "rejected"),
        "school_related_rows_moved_to_review": school_related_review,
        "additional_rows_moved_to_review_by_expanded_education_rule": additional_expanded_education_review,
        "stadium_rows_moved_to_review": stadium_review,
        "non_pickup_facilities_moved_to_rejected": non_pickup_rejected,
        "exact_duplicate_rows_removed_from_approved": len(removed_duplicates),
        "basketball_to_both_high_confidence": basketball_to_both_high,
        "basketball_to_both_medium_confidence": basketball_to_both_medium,
        "basketball_to_both_overlap_rows": basketball_to_both_overlap,
        "basketball_to_both_total_converted": basketball_to_both_high + basketball_to_both_medium,
        "duplicate_groups": duplicate_analysis["total_duplicate_groups"],
        "duplicate_rows": duplicate_analysis["total_duplicate_rows"],
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "duplicate_analysis.json").write_text(
        json.dumps(duplicate_analysis, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_duplicate_csv(output_dir / "duplicate_analysis.csv", duplicate_groups)
    (output_dir / "removed_exact_approved_duplicates.json").write_text(
        json.dumps(removed_duplicates, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_removed_duplicate_csv(output_dir / "removed_exact_approved_duplicates.csv", removed_duplicates)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default="govmap_validation_output",
        help="Directory for split JSON/CSV output files.",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=9000,
        help="Maximum GovMap features to fetch.",
    )
    parser.add_argument(
        "--city",
        help="Optional GovMap local authority value, for example: ירושלים.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cql_filter = f"new_id_local_authority='{args.city}'" if args.city else None
    features = fetch_features(count=args.count, cql_filter=cql_filter)
    facilities = [classify(normalize_feature(feature)) for feature in features]
    summary = write_outputs(Path(args.output_dir), facilities)

    print(
        f"Split {summary['total_input']} facilities: "
        f"{summary['approved']} approved, "
        f"{summary['review_required']} review_required, "
        f"{summary['rejected']} rejected, "
        f"{summary['exact_duplicate_rows_removed_from_approved']} exact approved duplicates removed."
    )


if __name__ == "__main__":
    main()
