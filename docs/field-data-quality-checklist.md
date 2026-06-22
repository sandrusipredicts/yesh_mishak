# Field Data Quality Review Checklist

## Purpose

Use this checklist to periodically review field records and find data quality issues that can confuse players, break map discovery, or create duplicate admin work.

The review focuses on practical fixes for:

* Duplicate fields
* Wrong coordinates
* Missing coordinates
* Wrong city
* Wrong name
* Closed fields
* Private fields

## When To Run This Review

Run this review:

* After a field import.
* Before publishing a new city or neighborhood batch.
* Monthly for active cities.
* When users submit multiple field reports for the same area.
* Before major product demos or community launches.

## Who Should Run It

Primary reviewer:

* Admin or product reviewer who understands local field coverage and can update field records.

Optional helpers:

* Local community manager for city-specific knowledge.
* Engineer only when data export, bulk update, or production access is needed.

## Required Tools And Data Sources

Use the best available sources for the city being reviewed:

* Admin field list or database export.
* App map view.
* Google Maps, Apple Maps, or another reliable map provider.
* Municipal sports facility listings when available.
* Recent user field reports.
* Field photos, if available.
* Local reviewer knowledge.

Do not rely on a single source when deciding to remove or reject a field. Confirm destructive or high-impact changes with at least two sources when possible.

## Severity Levels

| Severity | Meaning | Typical Action |
| --- | --- | --- |
| Critical | Field is unusable, unsafe, private, permanently closed, or mapped to a clearly wrong place. | Fix immediately, close, reject, or escalate. |
| High | Field is discoverable but misleading, duplicated, or assigned to the wrong city. | Fix during the current review cycle. |
| Medium | Field is usable but has naming, metadata, or minor location quality issues. | Fix if clear; otherwise note for follow-up. |
| Low | Cosmetic or confidence issue that does not block users from finding the field. | Note and batch with future cleanup. |

## Step-By-Step Checklist

### 1. Prepare The Review Batch

* Pick one city, neighborhood, or import batch.
* Export or open the field list with at least: `id`, `name`, `city`, `lat`, `lng`, `status`, `approval_status`, `verified`, `notes`, and `created_at`.
* Add temporary review columns: `issue_type`, `severity`, `recommended_action`, `evidence`, `reviewer`, `review_date`, and `status`.
* Filter out records that are already rejected unless the review goal includes rejected records.

### 2. Check Missing Coordinates

Look for:

* Empty `lat` or `lng`.
* Zero coordinates such as `0,0`.
* Coordinates that are not valid numbers.
* Coordinates outside the expected country or city area.

Recommended actions:

* If the correct location is known, update coordinates and mark as fixed.
* If the field exists but location is unclear, mark `needs_research`.
* If no reliable evidence confirms the field exists, mark for rejection or removal according to the admin process.

### 3. Check Wrong Coordinates

Look for:

* Pins placed on roads, buildings, water, or unrelated facilities.
* Pins far from the named field or city.
* Multiple fields with identical coordinates that do not represent a multi-court complex.
* Coordinates that match city centers instead of actual fields.

Recommended actions:

* Move the pin to the playable field area when confirmed.
* Add evidence link or note, such as a map URL or municipal source.
* If the field cannot be confidently located, mark `needs_research`.
* If the location points to private or closed property, handle under the private or closed field rules.

### 4. Check Duplicate Fields

Look for:

* Same or similar names in the same area.
* Different names sharing the same coordinates.
* Records within a short walking distance that describe the same court or sports complex.
* Imports that created Hebrew/English duplicates for the same location.

Recommended actions:

* Keep the most complete and accurate record.
* Merge useful notes manually into the kept record when possible.
* Reject, archive, or mark the duplicate record according to the admin process.
* Record the kept field ID and duplicate field ID in the review output.

### 5. Check Wrong City

Look for:

* Coordinates outside the listed city boundary.
* Neighborhood names stored as city names.
* Nearby city confusion, especially around city borders.
* Imported city values that do not match local naming conventions.

Recommended actions:

* Update `city` to the correct municipality or approved city label.
* If the correct city is uncertain, mark `needs_research`.
* If the field belongs outside the current launch/review area, leave a note so it is handled in the right city batch.

### 6. Check Wrong Name

Look for:

* Placeholder names such as `Field 1`, `Unnamed`, or imported IDs.
* Typos or mistranslations.
* Names that describe the wrong facility.
* Names that are too vague when several fields exist nearby.
* Names that expose private personal information.

Recommended actions:

* Use the public facility name from map or municipal sources.
* Prefer names users can recognize in the real world.
* Add a distinguishing area, school, park, or street only when needed.
* Remove personal information from names.
* If no reliable name exists, use a practical descriptive name and add a note.

### 7. Check Closed Fields

Look for:

* Facilities marked permanently closed by map providers or municipal sources.
* User reports saying the field no longer exists, is fenced off, or was replaced.
* Satellite or street-view evidence that the field was removed.
* Fields under long-term construction with no clear reopening date.

Recommended actions:

* For permanent closure, set the field status to closed or reject it according to the admin process.
* For temporary closure or renovation, mark as renovation if the app supports it.
* Add evidence and date checked.
* Avoid removing a field based on one unverified user report unless the report is strongly supported by other evidence.

### 8. Check Private Fields

Look for:

* Fields inside schools, apartment complexes, paid clubs, military areas, or gated facilities.
* Signs or listings that indicate members-only or residents-only access.
* User reports saying access is not public.
* Map evidence showing restricted entrances or private property.

Recommended actions:

* If public access is not allowed, reject or mark the field as private according to the admin process.
* If access is limited but allowed at specific times, add a clear note if the product supports notes.
* Escalate uncertain cases before removing popular fields.

## Recommended Actions By Issue Type

| Issue Type | Recommended Action | Evidence Needed |
| --- | --- | --- |
| Duplicate fields | Keep best record; mark duplicate for rejection/archive; note related IDs. | Matching coordinates, nearby map pins, same facility name, or reviewer confirmation. |
| Wrong coordinates | Update `lat` and `lng`; note source. | Map URL, municipal listing, field photo, or local confirmation. |
| Missing coordinates | Add coordinates or mark `needs_research`. | Reliable source for exact location. |
| Wrong city | Update city label. | Coordinates, city boundary, or official listing. |
| Wrong name | Rename to recognizable public name. | Map provider, municipal listing, signage, or local confirmation. |
| Closed field | Mark closed/rejected depending on process. | Map closure, municipal notice, street-view/satellite evidence, or multiple user reports. |
| Private field | Mark private/rejected depending on process. | Access restriction evidence, official listing, signage, or local confirmation. |

## QA Review Output Format

Each review cycle should produce a table or spreadsheet with these columns:

| Column | Description |
| --- | --- |
| `review_date` | Date the record was reviewed. |
| `reviewer` | Name or initials of the reviewer. |
| `field_id` | Field record ID. |
| `field_name` | Current field name. |
| `city` | Current city value. |
| `lat` | Current latitude. |
| `lng` | Current longitude. |
| `issue_type` | One of the required issue types or `none`. |
| `severity` | Critical, High, Medium, or Low. |
| `evidence` | Short source note or URL. |
| `recommended_action` | Exact action to take. |
| `action_owner` | Person responsible for the fix. |
| `status` | `open`, `fixed`, `needs_research`, `escalated`, or `wont_fix`. |
| `notes` | Any useful context. |

## Example Review Table

| review_date | reviewer | field_id | field_name | city | issue_type | severity | evidence | recommended_action | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-06-22 | OR | `field-123` | Sport Court 1 | Tel Aviv | Wrong name | Medium | Google Maps lists "Gan Meir Basketball Court" | Rename to public map name | open |
| 2026-06-22 | OR | `field-456` | Central Field | Ramat Gan | Duplicate fields | High | Same coordinates as `field-789` | Keep `field-789`; reject duplicate `field-456` | open |
| 2026-06-22 | OR | `field-777` | School Court | Givatayim | Private fields | Critical | School property; no public access shown | Reject or mark private | escalated |
| 2026-06-22 | OR | `field-888` | Park Football | Holon | Wrong coordinates | High | Pin is on nearby road; court visible 80m east | Move pin to court center | fixed |

## Definition Of Done For A Review Cycle

A review cycle is done when:

* The selected city, neighborhood, or import batch has been fully reviewed.
* All required issue types were checked.
* Every reviewed field has a review status.
* Critical and High issues have an action owner.
* Fixed records were verified after update.
* Unclear records are marked `needs_research` or `escalated` with evidence notes.
* Duplicate decisions include both the kept field ID and duplicate field ID.
* A final review summary is saved with counts by issue type and severity.

## Final Review Summary Template

Use this short summary at the end of each review cycle:

```text
Review area:
Review dates:
Reviewer:
Total fields reviewed:
Fields with no issue:
Critical issues:
High issues:
Medium issues:
Low issues:
Duplicates found:
Coordinate fixes:
Closed/private fields escalated:
Remaining needs_research:
Notes:
```
