# GPS Accuracy Requirements

## 1. Purpose
In location-based applications, not all geospatial actions require the same level of GPS accuracy. GPS data obtained from browsers and mobile hardware can vary significantly in reliability due to environmental factors (e.g., indoor usage, urban canyons), sensor limitations, and network-based triangulation. Treating every successful geolocation result as equally reliable can lead to a poor user experience, such as showing the user in the wrong location or blocking actions incorrectly.

This document defines clear GPS Accuracy Standards for the application to guide current and future location-based features.

---

## 2. Location Data Assumptions
To accurately evaluate location telemetry, location readings should be evaluated using the following properties:

- **latitude** (decimal degrees): The geographic latitude of the coordinate.
- **longitude** (decimal degrees): The geographic longitude of the coordinate.
- **accuracy** (meters): The accuracy radius of the latitude and longitude, representing a 95% confidence level.
- **timestamp** (Unix milliseconds or ISO 8601): The time at which the location fix was acquired.
- **source** (string, optional): The origin/method of the location reading (e.g., `'gps'`, `'network'`, `'wifi'`, or `'browser'`).

---

## 3. Accuracy Levels
We define three distinct levels of GPS accuracy to support different feature requirements:

### High Accuracy
- **Intended Use**: Operations requiring strict location verification, such as check-ins and proximity validations.
- **Target Accuracy**: <= 50m
- **Maximum Acceptable Accuracy**: <= 100m
- **Worse Than Allowed Behavior**: Block the action immediately, inform the user that their current location reading is not accurate enough, and request them to refresh/retry.

### Medium Accuracy
- **Intended Use**: Map features and localized browsing where approximate location is helpful but not critical, such as showing the user marker on the map and querying fields in a nearby radius.
- **Target Accuracy**: <= 100m
- **Maximum Acceptable Accuracy**: <= 500m
- **Worse Than Allowed Behavior**: Fall back to displaying an approximate location indicator/circle or a fallback coordinate, or notify the user/expand the search radius in future implementations.

### Low Accuracy
- **Intended Use**: Launching external utilities where high precision is not required from the app because the target application will perform its own high-accuracy resolution (e.g., launching external navigation apps like Waze or Google Maps).
- **Target Accuracy**: <= 500m
- **Maximum Acceptable Accuracy**: <= 2000m
- **Worse Than Allowed Behavior**: Allow navigation launch and rely on the external native navigation app to resolve the user's current location.

---

## 4. Use Case Mapping
The table below maps every current location usage in the app, as well as future proximity-based features, to an accuracy level.

| Use Case | Required Level | Target Accuracy | Max Acceptable Accuracy | Behavior If Worse |
| :--- | :--- | :---: | :---: | :--- |
| **User Marker** | Medium | <= 100m | <= 500m | Show approximate marker or fallback |
| **Nearby Fields** | Medium | <= 100m | <= 500m | Expand radius or show warning in future implementation |
| **Navigation Launch** | Low | <= 500m | <= 2000m | Allow navigation launch and rely on external navigation app |
| **Check-in / proximity validation** | High | <= 50m | <= 100m | Block action and request refresh if worse (Future feature) |

---

## 5. Current Scope
This document defines standards and does not enforce them in code.
- **Under ISSUE-257, this is a documentation-only change.**
- **No changes to runtime validation logic or user interfaces are introduced in this ticket.**

---

## 6. Future Implementation Guidance
Future implementation of location-related features should leverage a centralized validation helper rather than scattered ad-hoc checks.

### Shared Validator API
Future code should use a shared accuracy validator, for example:

```typescript
validateLocationAccuracy(location, useCase)
```

### Future Use Case Constants
The validator should support the following constants to determine which accuracy threshold to evaluate:
- `USER_MARKER`
- `NEARBY_FIELDS`
- `NAVIGATION_LAUNCH`
- `PROXIMITY_VALIDATION`

---

## 7. Out of Scope
The following areas are explicitly out of scope for the current task (ISSUE-257):
- No frontend behavior changes
- No backend changes
- No Android native changes
- No iOS changes
- No permission-flow changes
- No new UI warnings
- No enforcement logic yet

---

## 8. Definition of Done Checklist
This document satisfies all requirements for ISSUE-257:

- [x] Every current location usage is mapped to an accuracy level.
- [x] Accuracy thresholds are documented.
- [x] Fallback behavior is documented.
- [x] Future validator direction is documented.
- [x] Scope is documentation-only.
