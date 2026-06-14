# Task J E2E Test Report

Date: 2026-06-14
Branch: `codex/task-j-e2e-testing`

## Scope

Task J was run as a local smoke/E2E verification pass. No product code was changed.

Because this workspace does not include live Supabase credentials, real Google login credentials, or two real browser-authenticated users, database writes and true multi-user validation were not performed against Supabase. Browser flows that could be automated were tested with Playwright via the local browser automation tool and mocked backend responses.

No Playwright dependency was added to the project because the frontend does not currently include Playwright and adding it would be heavier than a report-only testing task.

## Validation Commands

- `python -m compileall -q backend/app`: Pass
- `npm run lint`: Pass
- `npm run build`: Pass

## 1. New User / Onboarding

Result: Blocked / Partial Pass

Steps performed:
- Opened the app with empty localStorage.
- Checked whether onboarding appears.
- Re-ran with a mocked logged-in user in localStorage.
- Selected city `ירוחם`.
- Clicked `Let's go`.
- Refreshed the page.

Evidence:
```json
{
  "firstLoad": {
    "loginVisible": true,
    "onboardingVisible": false,
    "pageErrors": [],
    "consoleErrors": []
  },
  "onboardingAfterLogin": {
    "mapVisibleAfterSubmit": true,
    "onboardingHiddenAfterRefresh": true,
    "storedCity": "ירוחם"
  }
}
```

Bugs found:
- The requested test says a new user should see onboarding immediately, but the current app shows the login page first when no `access_token` and `currentUserId` exist.

Recommended fixes:
- Clarify expected order: login first, then onboarding; or change the app to allow onboarding before login.

## 2. Add Field

Result: UI Pass / Live DB Blocked

Steps performed:
- Clicked `+`.
- Filled field details.
- Clicked the location map to choose lat/lng.
- Submitted the form.
- Verified request payload and success message.

Evidence:
```json
{
  "postedField": {
    "name": "מגרש שכונה",
    "lat": 30.98581386166403,
    "lng": 34.92768287658692,
    "sport_type": "football",
    "surface_type": "asphalt",
    "has_nets": true,
    "has_water": false,
    "opening_hours": "תמיד פתוח",
    "notes": "יש תאורה בערב"
  },
  "successText": "Sent for VAR approval",
  "fieldsRefetched": true,
  "pageErrors": [],
  "consoleErrors": []
}
```

Bugs found:
- None in the local UI flow.

Blocked:
- Supabase verification of pending row creation and admin approval was not performed because live credentials/admin access were not available in this run.

Recommended fixes:
- Run this flow with a real backend token and verify:
  - `fields.approval_status = 'pending'`
  - `fields.verified = false`
  - after approval, `GET /fields` returns the field.

## 3. Open Game

Result: UI Partial Pass / Backend Contract Bug

Steps performed:
- Clicked an approved field marker.
- Clicked `Open Game`.
- Filled `sport_type`, `players_present`, `max_players`, `age_note`.
- Submitted the form.
- Verified UI shows an active game and pin color updates.

Evidence:
```json
{
  "postedGame": {
    "field_id": "field-1",
    "sport_type": "football",
    "players_present": 4,
    "max_players": 10,
    "age_note": "18+"
  },
  "gameCreated": true,
  "uiTextExcerpt": "1 מתוך 10 שחקנים ... 1 / 10 players ... Creator User",
  "markerColor": "rgb(220, 38, 38)",
  "pageErrors": [],
  "consoleErrors": []
}
```

Bugs found:
- Frontend sends `players_present: 4`, but backend `GameCreate` does not define `players_present` and `create_game()` currently inserts `"players_present": 1`.
- This means the UI can ask for 4 present players but the backend-created game starts at 1.

Recommended fixes:
- Either remove `players_present` from the Open Game UI/payload, or update backend `GameCreate` and `create_game()` to validate and use the submitted `players_present`.

## 4. Join / Leave Game

Result: UI Pass with Mocked Backend / Live Multi-User Blocked

Steps performed:
- Loaded an active game as a mocked second user.
- Verified `I'm coming` appears.
- Clicked join.
- Verified participant name appears and player count increases.
- Clicked leave.
- Verified participant name disappears and player count decreases.

Evidence:
```json
{
  "beforeHasJoin": true,
  "afterJoinText": "2 מתוך 10 שחקנים ... Creator User ... Second User ... Leave",
  "afterLeaveText": "1 מתוך 10 שחקנים ... Creator User ... I'm coming",
  "joinCalls": 1,
  "leaveCalls": 1,
  "pageErrors": [],
  "consoleErrors": []
}
```

Bugs found:
- None in mocked UI flow.

Blocked:
- Real Supabase verification with two authenticated users was not performed.

Recommended fixes:
- Run with two real users and verify `game_players` rows and `games.players_present` changes in Supabase.

## 5. Extend Game

Result: UI Pass with Mocked Backend / Live Auth Blocked

Steps performed:
- Loaded an active game as creator.
- Verified `Extra round` appears.
- Clicked `Extra round`.
- Loaded the same game as non-creator.
- Verified `Extra round` does not appear.

Evidence:
```json
{
  "creatorSeesExtraRound": true,
  "creatorExtendCalls": 1,
  "nonCreatorSeesExtraRound": false,
  "pageErrors": [],
  "consoleErrors": []
}
```

Bugs found:
- None in mocked UI flow.

Blocked:
- Real backend authorization verification was not performed with live tokens.

Recommended fixes:
- Confirm with real users that backend returns 403 for non-creator `POST /games/{game_id}/extend`.

## 6. Notifications Settings

Result: UI Pass with Mocked Backend / Live DB Blocked

Steps performed:
- Clicked bell.
- Enabled distance, city, and specific field notifications.
- Set distance to 5 km.
- Set city to `ירוחם`.
- Selected one field.
- Saved.
- Reopened settings and verified values loaded as saved.

Evidence:
```json
{
  "savedPayload": {
    "distance_enabled": true,
    "distance_radius_km": 5,
    "city_enabled": true,
    "city_name": "ירוחם",
    "specific_fields_enabled": true,
    "selected_field_ids": ["field-1"]
  },
  "radiusReloaded": "5",
  "cityReloaded": "ירוחם",
  "fieldStillSelected": true,
  "pageErrors": [],
  "consoleErrors": []
}
```

Bugs found:
- None in mocked UI flow.

Blocked:
- Supabase persistence verification was not performed.

Recommended fixes:
- Run against the live backend and verify rows in `notification_preferences` for `radius`, `city`, and `specific_field`.

## Summary

Overall result: Partial Pass

Passed locally with mocked backend:
- Onboarding after login and persistence
- Add field UI and payload
- Open game UI rendering
- Join/leave UI actions
- Creator-only extend UI
- Notifications settings save/reload UI

Blocked by missing live test environment:
- Google login with real token
- Supabase row verification
- Admin field approval
- Real two-user join/leave
- Real creator/non-creator extend authorization

Primary bug found:
- Open Game frontend collects/sends `players_present`, but backend ignores it and creates the game with `players_present = 1`.
