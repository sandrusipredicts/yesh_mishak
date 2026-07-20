# E09-03 Engagement dashboard

## Scope

E09-03 is a read-only visualization layer over the anonymous analytics and
sharing infrastructure that already existed before this issue.

The dashboard exposes only:

- app-open volume;
- screen-view volume;
- source application platform breakdown;
- share-action volume;
- share success rate;
- share-action outcome breakdown; and
- response generation and client refresh timestamps.

It does not add analytics events, event properties, identifiers, client
instrumentation, ingestion behavior, retry behavior, retention policy,
background work, or privacy semantics.

## Read path

1. `GET /admin/engagement` validates the existing admin session and accepts
   only a 7, 30, or 90 day bounded window.
2. The endpoint calls the existing `get_analytics_event_metrics` and
   `get_share_event_metrics` service functions.
3. Those services execute the existing PostgreSQL aggregation RPCs with a
   half-open timestamp window.
4. The endpoint derives dashboard totals, rates, and display groups from the
   already-aggregated RPC rows.
5. The frontend validates the aggregate response and visualizes it.

Neither `analytics_events` nor `share_events` raw rows are selected into
Python.

## New endpoint justification

`GET /admin/engagement` is the only new backend endpoint.

The existing `GET /admin/monitoring` endpoint could not be reused cleanly as
the dashboard endpoint because:

- its public window is intentionally limited to 5–1,440 minutes;
- it queries unrelated operational sources such as API reliability, response
  time, push delivery, and scheduled jobs; and
- expanding it to 90 days would change the behavior and cost profile of the
  existing Admin Monitoring feature.

The new endpoint remains in the existing admin router, reuses the existing
admin dependency and analytics services, is GET-only, and has no mutation
path. It is also excluded from the pre-existing API request-metric writer,
just like `/admin/monitoring`, so a dashboard read does not insert an
`api_request_metrics` row.

## RPC decision

E09-03 adds no RPC.

The existing RPCs already return the required database-side aggregates:

- `get_analytics_event_metrics` returns daily event counts by event name and
  source application platform.
- `get_share_event_metrics` returns share and link-open counts by the approved
  anonymous sharing dimensions.

The backend combines those aggregate groups into the approved cards,
platform rows, daily rows, outcome rows, and share-success rate. Link-open
rows are not included in the share-action total or denominator.

## Shared frontend component justification

`AdminDashboardComponents.jsx` and `adminDashboardShared.js` extract the
Admin Monitoring implementations for:

- loading and initial error states;
- refresh errors and non-overlapping refresh requests;
- request cancellation and last-good data;
- metric cards;
- section and source notices;
- toolbar and status presentation; and
- number, rate, and UTC timestamp formatting.

These behaviors were local to `AdminMonitoring`. A separate Engagement
consumer would otherwise have duplicated them. `AdminMonitoring` and
`AdminEngagement` now both consume the extracted implementations. No
single-consumer framework or chart abstraction was introduced.

## Metric semantics

- **App opens**: count of anonymous `app_open` events.
- **Screen views**: count of anonymous `screen_view` events.
- **Platform**: the source application platform (`web`, `android`, or `ios`);
  it is not a user or destination platform.
- **Share actions**: count of `share_action` events. `link_open` events are
  excluded.
- **Successful share actions**: outcomes `shared` or `copied`.
- **Share success rate**: successful share actions divided by all share
  actions. It is `0` when no share actions exist.
- **Data freshness**: when the backend generated the bounded aggregate
  response. It is not the latest raw-event timestamp.

All windows are rolling UTC windows with inclusive starts and exclusive ends.

## Explicit exclusions

The dashboard does not calculate DAU, WAU, MAU, users, sessions, retention,
login success, join conversion, notification click-through, push delivery,
top entities, field views, or repeat behavior. The current anonymous
telemetry does not support those semantics, and E09-03 does not expand
tracking to obtain them.
