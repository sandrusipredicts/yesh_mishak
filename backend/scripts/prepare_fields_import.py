"""Prepare GovMap approved facilities for direct fields-table import.

Reads approved.csv from the GovMap validation output, validates the final
required fields, and writes a CSV, SQL insert file, and summary JSON. This
script does not connect to the database.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


VALID_SPORT_TYPES = {"football", "basketball", "both"}
MIN_ISRAEL_LAT = Decimal("29")
MAX_ISRAEL_LAT = Decimal("34")
MIN_ISRAEL_LNG = Decimal("34")
MAX_ISRAEL_LNG = Decimal("36")

ITM_A = 6378137.0
ITM_E2 = 0.00669438002290
ITM_LAT0 = math.radians(31.73439361111111)
ITM_LON0 = math.radians(35.20451694444445)
ITM_K0 = 1.0000067
ITM_FALSE_EASTING = 219529.584
ITM_FALSE_NORTHING = 626907.39

OUTPUT_COLUMNS = [
    "name",
    "lat",
    "lng",
    "sport_type",
    "surface_type",
    "has_lighting",
    "has_water",
    "opening_hours",
    "status",
    "verified",
    "added_by",
    "notes",
    "image_url",
    "approval_status",
    "city",
    "has_fencing",
    "has_parking",
]

INVALID_COORDINATE_COLUMNS = [
    "input_line",
    "source_id",
    "name",
    "city",
    "raw_lat",
    "raw_lng",
    "normalized_lat",
    "normalized_lng",
    "sport_type",
    "facility_type",
    "operator",
    "owner",
    "reasons",
]

SQL_COLUMNS = [
    "name",
    "lat",
    "lng",
    "sport_type",
    "surface_type",
    "has_lighting",
    "has_water",
    "opening_hours",
    "status",
    "verified",
    "added_by",
    "created_at",
    "notes",
    "image_url",
    "approval_status",
    "city",
    "has_fencing",
    "has_parking",
]


def clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def hebrew_bool(value: str) -> bool:
    return clean(value) == "כן"


def parse_coordinate(value: str) -> Decimal | None:
    try:
        coordinate = Decimal(clean(value))
    except InvalidOperation:
        return None
    return coordinate


def meridional_arc(latitude: float) -> float:
    e4 = ITM_E2 * ITM_E2
    e6 = e4 * ITM_E2
    return ITM_A * (
        (1 - ITM_E2 / 4 - 3 * e4 / 64 - 5 * e6 / 256) * latitude
        - (3 * ITM_E2 / 8 + 3 * e4 / 32 + 45 * e6 / 1024) * math.sin(2 * latitude)
        + (15 * e4 / 256 + 45 * e6 / 1024) * math.sin(4 * latitude)
        - (35 * e6 / 3072) * math.sin(6 * latitude)
    )


def itm_to_wgs84(easting: float, northing: float) -> tuple[float, float]:
    m0 = meridional_arc(ITM_LAT0)
    m = m0 + (northing - ITM_FALSE_NORTHING) / ITM_K0
    mu = m / (ITM_A * (1 - ITM_E2 / 4 - 3 * ITM_E2**2 / 64 - 5 * ITM_E2**3 / 256))
    e1 = (1 - math.sqrt(1 - ITM_E2)) / (1 + math.sqrt(1 - ITM_E2))

    phi1 = (
        mu
        + (3 * e1 / 2 - 27 * e1**3 / 32) * math.sin(2 * mu)
        + (21 * e1**2 / 16 - 55 * e1**4 / 32) * math.sin(4 * mu)
        + (151 * e1**3 / 96) * math.sin(6 * mu)
        + (1097 * e1**4 / 512) * math.sin(8 * mu)
    )

    ep2 = ITM_E2 / (1 - ITM_E2)
    sin_phi1 = math.sin(phi1)
    cos_phi1 = math.cos(phi1)
    tan_phi1 = math.tan(phi1)
    n1 = ITM_A / math.sqrt(1 - ITM_E2 * sin_phi1**2)
    r1 = ITM_A * (1 - ITM_E2) / (1 - ITM_E2 * sin_phi1**2) ** 1.5
    t1 = tan_phi1**2
    c1 = ep2 * cos_phi1**2
    d = (easting - ITM_FALSE_EASTING) / (n1 * ITM_K0)

    latitude = phi1 - (n1 * tan_phi1 / r1) * (
        d**2 / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1**2 - 9 * ep2) * d**4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1**2 - 252 * ep2 - 3 * c1**2) * d**6 / 720
    )
    longitude = ITM_LON0 + (
        d
        - (1 + 2 * t1 + c1) * d**3 / 6
        + (5 - 2 * c1 + 28 * t1 - 3 * c1**2 + 8 * ep2 + 24 * t1**2) * d**5 / 120
    ) / cos_phi1

    return math.degrees(latitude), math.degrees(longitude)


def normalize_coordinates(raw_lat: str, raw_lng: str) -> tuple[str | None, str | None, bool]:
    lat = parse_coordinate(raw_lat)
    lng = parse_coordinate(raw_lng)
    if lat is None or lng is None:
        return None, None, False

    lat_float = float(lat)
    lng_float = float(lng)
    if -90 <= lat_float <= 90 and -180 <= lng_float <= 180:
        return f"{lat_float:.7f}", f"{lng_float:.7f}", False

    converted_lat, converted_lng = itm_to_wgs84(easting=lng_float, northing=lat_float)
    if -90 <= converted_lat <= 90 and -180 <= converted_lng <= 180:
        return f"{converted_lat:.7f}", f"{converted_lng:.7f}", True

    return None, None, False


def coordinates_in_israel(lat: str | None, lng: str | None) -> bool:
    if lat is None or lng is None:
        return False
    try:
        lat_decimal = Decimal(lat)
        lng_decimal = Decimal(lng)
    except InvalidOperation:
        return False
    return (
        MIN_ISRAEL_LAT <= lat_decimal <= MAX_ISRAEL_LAT
        and MIN_ISRAEL_LNG <= lng_decimal <= MAX_ISRAEL_LNG
    )


def validate_input_row(row: dict[str, str]) -> list[str]:
    reasons: list[str] = []

    if not clean(row.get("name")):
        reasons.append("missing_name")
    if not clean(row.get("city")):
        reasons.append("missing_city")

    lat, lng, _ = normalize_coordinates(clean(row.get("lat")), clean(row.get("lng")))
    if lat is None:
        reasons.append("missing_or_invalid_lat")
    if lng is None:
        reasons.append("missing_or_invalid_lng")
    if lat is not None and lng is not None and not coordinates_in_israel(lat, lng):
        reasons.append("coordinates_outside_israel")

    sport_type = clean(row.get("sport_type"))
    if sport_type not in VALID_SPORT_TYPES:
        reasons.append("invalid_sport_type")

    return reasons


def map_row(row: dict[str, str]) -> dict[str, Any]:
    lat, lng, converted = normalize_coordinates(clean(row.get("lat")), clean(row.get("lng")))
    return {
        "name": clean(row.get("name")),
        "lat": lat,
        "lng": lng,
        "sport_type": clean(row.get("sport_type")),
        "surface_type": clean(row.get("surface_type")) or None,
        "has_lighting": hebrew_bool(clean(row.get("lighting"))),
        "has_water": False,
        "opening_hours": None,
        "status": "open",
        "verified": True,
        "added_by": None,
        "notes": None,
        "image_url": None,
        "approval_status": "approved",
        "city": clean(row.get("city")),
        "has_fencing": hebrew_bool(clean(row.get("fencing"))),
        "has_parking": hebrew_bool(clean(row.get("parking"))),
        "_converted_itm_coordinates": converted,
    }


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, Decimal):
        return str(value)
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


def sql_row(row: dict[str, Any]) -> str:
    values: list[str] = []
    for column in SQL_COLUMNS:
        if column == "created_at":
            values.append("NOW()")
        elif column in {"lat", "lng"}:
            values.append(str(row[column]))
        else:
            values.append(sql_literal(row.get(column)))
    return f"({', '.join(values)})"


def read_approved_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as csv_file:
        return list(csv.DictReader(csv_file))


def write_import_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: csv_value(row.get(column)) for column in OUTPUT_COLUMNS})


def write_import_sql(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("-- No valid rows to import.\n", encoding="utf-8")
        return

    columns = ", ".join(SQL_COLUMNS)
    values = ",\n".join(sql_row(row) for row in rows)
    sql = (
        "-- Generated from GovMap approved.csv. Review before running.\n"
        f"INSERT INTO fields ({columns})\n"
        f"VALUES\n{values};\n"
    )
    path.write_text(sql, encoding="utf-8")


def write_invalid_coordinates_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=INVALID_COORDINATE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def write_summary(path: Path, summary: dict[str, Any]) -> None:
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def prepare_import(input_path: Path, output_dir: Path) -> dict[str, Any]:
    input_rows = read_approved_rows(input_path)
    valid_rows: list[dict[str, Any]] = []
    rejected_rows: list[dict[str, Any]] = []
    invalid_coordinate_rows: list[dict[str, Any]] = []
    invalid_reason_counts: dict[str, int] = {}

    for index, row in enumerate(input_rows, start=2):
        reasons = validate_input_row(row)
        if reasons:
            normalized_lat, normalized_lng, _ = normalize_coordinates(
                clean(row.get("lat")),
                clean(row.get("lng")),
            )
            if "coordinates_outside_israel" in reasons:
                invalid_coordinate_rows.append(
                    {
                        "input_line": index,
                        "source_id": clean(row.get("source_id")),
                        "name": clean(row.get("name")),
                        "city": clean(row.get("city")),
                        "raw_lat": clean(row.get("lat")),
                        "raw_lng": clean(row.get("lng")),
                        "normalized_lat": normalized_lat or "",
                        "normalized_lng": normalized_lng or "",
                        "sport_type": clean(row.get("sport_type")),
                        "facility_type": clean(row.get("facility_type")),
                        "operator": clean(row.get("operator")),
                        "owner": clean(row.get("owner")),
                        "reasons": ";".join(reasons),
                    }
                )
            rejected_rows.append(
                {
                    "input_line": index,
                    "source_id": clean(row.get("source_id")),
                    "name": clean(row.get("name")),
                    "city": clean(row.get("city")),
                    "sport_type": clean(row.get("sport_type")),
                    "reasons": reasons,
                }
            )
            for reason in reasons:
                invalid_reason_counts[reason] = invalid_reason_counts.get(reason, 0) + 1
            continue

        valid_rows.append(map_row(row))

    output_dir.mkdir(parents=True, exist_ok=True)
    fields_csv = output_dir / "fields_import.csv"
    fields_sql = output_dir / "fields_import.sql"
    summary_json = output_dir / "import_summary.json"
    invalid_coordinates_csv = output_dir / "invalid_coordinates.csv"

    write_import_csv(fields_csv, valid_rows)
    write_import_sql(fields_sql, valid_rows)
    write_invalid_coordinates_csv(invalid_coordinates_csv, invalid_coordinate_rows)

    summary = {
        "input_file": str(input_path),
        "output_dir": str(output_dir),
        "input_rows": len(input_rows),
        "valid_rows": len(valid_rows),
        "rejected_rows": len(rejected_rows),
        "invalid_coordinates_rows": len(invalid_coordinate_rows),
        "converted_itm_coordinate_rows": sum(
            1 for row in valid_rows if row.get("_converted_itm_coordinates")
        ),
        "invalid_reason_counts": invalid_reason_counts,
        "rejected_row_examples": rejected_rows[:25],
        "output_files": {
            "fields_import_csv": str(fields_csv),
            "fields_import_sql": str(fields_sql),
            "invalid_coordinates_csv": str(invalid_coordinates_csv),
            "import_summary_json": str(summary_json),
        },
    }
    write_summary(summary_json, summary)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        default="backend/govmap_validation_output/approved.csv",
        help="Path to approved.csv from govmap_facility_splitter.py.",
    )
    parser.add_argument(
        "--output-dir",
        default="backend/govmap_validation_output/fields_import",
        help="Directory for fields_import.csv, fields_import.sql, and import_summary.json.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = prepare_import(Path(args.input), Path(args.output_dir))
    print(
        f"Prepared {summary['valid_rows']} fields import rows; "
        f"rejected {summary['rejected_rows']} invalid rows."
    )


if __name__ == "__main__":
    main()
