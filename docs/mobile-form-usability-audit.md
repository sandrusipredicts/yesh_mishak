# ISSUE-142: Mobile Form Usability Audit

## Summary

- **Overall form usability verdict**: PARTIAL
- **Total forms reviewed**: 9 (Login, Register, Create Game, Field Report, Add Field, Notification Preferences, Admin Users, Admin Fields, Admin Games)
- **Total findings**: 14
- **Critical findings (P0)**: 0
- **High findings (P1)**: 3
- **Medium findings (P2)**: 8
- **Low findings (P3)**: 3

Form usability remediation can begin. No form is completely broken for mobile use, but three P1 issues significantly harm the mobile experience: native `window.prompt` for admin moderation blocks the rendering thread, native `window.confirm` for close-game lacks styling and Hebrew support, and the registration form provides no visible password requirements hint. The remaining issues are moderate friction or polish items. All findings are addressable with frontend-only changes.

## Dependency Verification

| Dependency | Source Reviewed | Relevance |
| :--- | :--- | :--- |
| ISSUE-136 | `docs/mobile-design-guide.md` | Form spacing, labels, touch targets — verified: 44x44px standard applied |
| ISSUE-138 | `docs/mobile-keyboard-interaction-spec.md` | Keyboard behavior expectations — verified: all rules defined |
| ISSUE-139 | `docs/mobile-keyboard-handling-implementation.md` | Keyboard fixes already implemented — verified: modal scroll, 16px inputs, numeric keypad, viewport-aware autocomplete |
| ISSUE-141 | `docs/mobile-touch-target-implementation.md` | Touch target fixes already implemented — verified: all 18 TTMOB findings resolved |

## Form Usability Standards Used

- Labels must clearly describe the field.
- Required fields must be obvious (either all fields are required, or optional fields are explicitly marked).
- Error messages must be visible, readable, and actionable.
- Global errors must not be the only error signal for field-specific failures where avoidable.
- Submit buttons must clearly communicate action and loading state.
- Loading/disabled states must prevent duplicate submissions.
- Inputs must use correct `type`/`inputMode`/`autoComplete` where appropriate.
- Hebrew RTL text must wrap without ambiguity.
- Native `window.prompt`/`window.confirm` should be avoided for important form workflows where they harm mobile usability.

## Form Audit Matrix

| Form | Status | Findings | Severity | Evidence | Recommendation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Login | PARTIAL | 2 | P2, P3 | `LoginPage.jsx` | Error at bottom; no password recovery |
| Register | PARTIAL | 3 | P1, P2, P2 | `LoginPage.jsx` | No password hint; validation bubbles; error at bottom |
| Create Game | PARTIAL | 2 | P2, P2 | `OpenGameModal.jsx` | Global error only; no age note guidance |
| Field Report | PASS | 0 | — | `FieldReportModal.jsx` | Good labels, validation, loading state |
| Add Field | PARTIAL | 2 | P2, P3 | `AddFieldModal.jsx` | No cancel button; optional fields unclear |
| Notification Preferences | PARTIAL | 1 | P2 | `NotificationsModal.jsx` | City validation only on submit |
| Admin Users | PARTIAL | 1 | P1 | `AdminUsers.jsx` | Native `window.prompt` for moderation reasons |
| Admin Fields | PASS | 0 | — | `AdminFields.jsx` | Approve/reject actions clear |
| Admin Games | PARTIAL | 1 | P1 | `AdminGames.jsx` via `GamePanel.jsx` | Close game uses `window.confirm` |
| Admin Field Reports | PASS | 0 | — | `AdminFieldReports.jsx` | Read-only view with filters |

## Detailed Findings

### FUMOB-001: Registration form lacks visible password requirements

- **Severity**: P1
- **Form**: Register
- **Status**: Open
- **Evidence**:
  - File: `frontend/src/components/LoginPage.jsx` lines 302-325
  - Component: Registration form password and confirm-password fields
  - Code or behavior observed: Both password fields have `minLength={8}` and `maxLength={128}` but no visible hint text explains these requirements. Users discover the constraint only when native validation bubbles appear (in English on Hebrew locale) or when the API rejects the password.
- **Mobile Impact**: On mobile, native validation constraint bubbles are often hard to read, may appear in English regardless of app language, and disappear quickly. Users have no idea what password is acceptable before typing.
- **User/Admin Impact**: Registration abandonment risk. Users may attempt multiple passwords before guessing the 8-character minimum.
- **Recommendation**: Add a visible hint below the password field showing the minimum length requirement (e.g., "8 characters minimum"). Use translated text from i18n.
- **Suggested Follow-up Issue**: Add visible password requirements hint to registration form

### FUMOB-002: Native `window.prompt` used for admin moderation reasons

- **Severity**: P1
- **Form**: Admin Users
- **Status**: Open (previously identified as `ADMOB-001`)
- **Evidence**:
  - File: `frontend/src/components/admin/AdminUsers.jsx` line 88
  - Component: `handleModeration` function
  - Code or behavior observed: `window.prompt(t('admin.moderationReasonPrompt'))` is called when banning or suspending a user. On mobile, this freezes the rendering thread, produces an unstyled browser dialog, and displays in the browser's default language (often English) regardless of the app's Hebrew locale.
- **Mobile Impact**: Thread freeze prevents scrolling or interaction. Dialog styling is inconsistent with the app. Reason input in the native prompt is tiny and lacks the app's RTL text direction.
- **User/Admin Impact**: Admin may accidentally dismiss the prompt (losing typed reason), or submit an inadequate reason. The thread freeze is jarring on mobile.
- **Recommendation**: Replace `window.prompt` with a custom React modal that matches the app's styling, supports Hebrew RTL, and includes proper validation.
- **Suggested Follow-up Issue**: Replace native window.prompt for admin moderation with custom modal

### FUMOB-003: Native `window.confirm` used for close-game action

- **Severity**: P1
- **Form**: Game Details (via GamePanel)
- **Status**: Open (previously identified as `GDMOB-003`)
- **Evidence**:
  - File: `frontend/src/components/GamePanel.jsx` line 211
  - Component: `handleCloseGame` function
  - Code or behavior observed: `window.confirm(t('game.closeConfirm'))` is called before closing a game. This is a destructive action that ends the game for all participants.
- **Mobile Impact**: Native confirm dialog freezes the thread, lacks styling, and button labels (OK/Cancel) may appear in English on a Hebrew-locale device. There is no way to undo closing a game.
- **User/Admin Impact**: Risk of accidental game closure. The generic OK/Cancel buttons do not communicate the severity of the action.
- **Recommendation**: Replace `window.confirm` with a custom React confirmation modal that uses translated, action-specific button labels (e.g., "Close Game" / "Cancel") and matches the app's visual style.
- **Suggested Follow-up Issue**: Replace native close-game confirmation with custom modal

### FUMOB-004: Login and registration error messages placed at bottom of panel

- **Severity**: P2
- **Form**: Login, Register
- **Status**: Open (related to `ML-REGISTER-003`)
- **Evidence**:
  - File: `frontend/src/components/LoginPage.jsx` lines 339-340
  - Component: `.login-error` rendered after the Google button and loading status
  - Code or behavior observed: The error element is positioned after all form content including the Google button and divider. On mobile, especially during registration with 6 fields, the error may be below the visible viewport when the keyboard is open.
- **Mobile Impact**: After a failed login/registration attempt, users may not see the error message without scrolling down past the form and Google button.
- **User/Admin Impact**: Users may think the form submission did nothing, leading to repeated taps on the submit button (prevented by `disabled` state, but still confusing).
- **Recommendation**: Move error rendering to just above the submit button within each form, or add inline error indicators near the failed field.
- **Suggested Follow-up Issue**: Improve login/registration error message placement

### FUMOB-005: Registration uses browser native validation bubbles

- **Severity**: P2
- **Form**: Register
- **Status**: Open (previously identified as `ML-REGISTER-002`)
- **Evidence**:
  - File: `frontend/src/components/LoginPage.jsx` lines 255-330
  - Component: Registration form with `required`, `minLength`, `type="email"`, `type="tel"` attributes
  - Code or behavior observed: The form relies on HTML5 native constraint validation via `required`, `minLength={3}`, `minLength={8}`, `type="email"`, and `type="tel"`. Native validation bubbles appear in the browser's UI language, which may be English even when the app is in Hebrew.
- **Mobile Impact**: Validation messages appear as small, ephemeral browser bubbles that are inconsistent with the app's design and language. On some mobile browsers they disappear quickly or are partially hidden by the keyboard.
- **User/Admin Impact**: Language inconsistency between Hebrew app UI and English validation messages creates confusion. Users may not understand why submission failed.
- **Recommendation**: Implement custom JavaScript validation with translated error messages rendered inline, matching the app's design language.
- **Suggested Follow-up Issue**: Add localized inline validation for registration form

### FUMOB-006: Create Game form uses global-only error placement

- **Severity**: P2
- **Form**: Create Game
- **Status**: Open (previously identified as `CGMOB-004`)
- **Evidence**:
  - File: `frontend/src/components/OpenGameModal.jsx` line 220
  - Component: Single `modal-error` paragraph before the submit button
  - Code or behavior observed: All validation errors (sport required, players invalid, date/time issues) are shown as a single global error message. There is no inline indication of which field has the problem.
- **Mobile Impact**: On a scrollable modal, the global error may not be near the problematic field. Users must read the error text, identify the field, scroll to it, and fix it.
- **User/Admin Impact**: Higher cognitive load for form correction, especially when the keyboard is open and the viewport is reduced.
- **Recommendation**: Add inline error indicators next to the problematic field in addition to (or instead of) the global error.
- **Suggested Follow-up Issue**: Implement inline validation errors in Create Game modal

### FUMOB-007: Create Game age note field lacks input guidance

- **Severity**: P2
- **Form**: Create Game
- **Status**: Open
- **Evidence**:
  - File: `frontend/src/components/OpenGameModal.jsx` lines 210-218
  - Component: Age note input with `placeholder="18+"`
  - Code or behavior observed: The age note field has a label from i18n and a placeholder of `"18+"`. The placeholder is hardcoded (not translated) and may be ambiguous — does it mean "minimum age 18" or "ages 18 and above"? The field is optional but this is not indicated.
- **Mobile Impact**: Users may not understand what to type. The placeholder disappears once they start typing, leaving no guidance.
- **User/Admin Impact**: Low — this is an optional field and the placeholder provides some guidance. But the hardcoded English placeholder is inconsistent with a Hebrew interface.
- **Recommendation**: Translate the placeholder via i18n. Consider adding a helper text label clarifying the field's purpose.
- **Suggested Follow-up Issue**: Translate and clarify Create Game age note placeholder

### FUMOB-008: Add Field form has no cancel button

- **Severity**: P2
- **Form**: Add Field
- **Status**: Open
- **Evidence**:
  - File: `frontend/src/components/AddFieldModal.jsx` lines 235-237
  - Component: Only a submit button (`primary-panel-button`) exists; no secondary/cancel button
  - Code or behavior observed: The modal has a close button (`x`) but no explicit Cancel button in the form actions area. Other modals (Field Report) have both Submit and Cancel buttons.
- **Mobile Impact**: Users must find and tap the small close button (now 44px after ISSUE-141, but still less discoverable than an explicit Cancel button within the form flow).
- **User/Admin Impact**: Inconsistent with other form modals. Users filling a long form may accidentally submit when they intended to cancel, if they don't notice the close button.
- **Recommendation**: Add a Cancel button alongside the Submit button, matching the Field Report modal pattern with `field-report-actions` layout.
- **Suggested Follow-up Issue**: Add cancel button to Add Field modal

### FUMOB-009: Add Field form does not distinguish required vs optional fields

- **Severity**: P3
- **Form**: Add Field
- **Status**: Open
- **Evidence**:
  - File: `frontend/src/components/AddFieldModal.jsx` lines 139-231
  - Component: Form with 7 fields where only Name and Surface Type have `required`; Opening Hours, Notes, Has Nets, Has Water are optional but not marked
  - Code or behavior observed: There is no visual indicator distinguishing required fields from optional ones. All labels look identical.
- **Mobile Impact**: Users may fill every field unnecessarily, increasing form completion time on mobile. Or they may skip a required field and encounter a validation error.
- **User/Admin Impact**: Minor — the form is short enough to fill entirely, and the required validation will catch omissions.
- **Recommendation**: Add an "(optional)" label suffix to optional fields, or add an asterisk (*) to required fields with a legend.
- **Suggested Follow-up Issue**: Mark optional fields in Add Field form

### FUMOB-010: Notification preferences city validation only triggers on submit

- **Severity**: P2
- **Form**: Notification Preferences
- **Status**: Open
- **Evidence**:
  - File: `frontend/src/components/NotificationsModal.jsx` lines 242-245
  - Component: `handleSubmit` validates city only if `cityEnabled && !isValidCity`
  - Code or behavior observed: If a user enables city notifications and types a partial or invalid city name, they receive no feedback until they tap Save. The CityAutocomplete does show suggestions, but a user could type a non-matching city and not realize it's invalid.
- **Mobile Impact**: On mobile, users may dismiss the autocomplete suggestions (e.g., by scrolling or tapping elsewhere) with a partial city name, then submit. The error appears at the bottom of a potentially scrolled modal.
- **User/Admin Impact**: Users must re-scroll to the city field after seeing the submit error, then re-select from autocomplete.
- **Recommendation**: Add immediate visual feedback when the city text does not match any valid city (e.g., a warning border or helper text). Alternatively, validate on blur.
- **Suggested Follow-up Issue**: Add inline city validation to notification preferences

### FUMOB-011: Login form has no password recovery option

- **Severity**: P3
- **Form**: Login
- **Status**: Open
- **Evidence**:
  - File: `frontend/src/components/LoginPage.jsx` lines 227-253
  - Component: Login form with username and password only
  - Code or behavior observed: There is no "Forgot password?" link or recovery flow visible on the login form. Users who forget their password have no self-service option.
- **Mobile Impact**: Mobile users are more likely to be logged out (app restarts, token expiry) and need to re-authenticate. Without password recovery, they are stuck.
- **User/Admin Impact**: Users who forget their password cannot access the app without admin intervention.
- **Recommendation**: Add a "Forgot password?" link or text, even if the backend flow is not yet implemented (it can link to a "contact admin" message).
- **Suggested Follow-up Issue**: Add password recovery flow or help text

### FUMOB-012: Admin games Close action lacks confirmation context

- **Severity**: P2
- **Form**: Admin Games
- **Status**: Open
- **Evidence**:
  - File: `frontend/src/components/admin/AdminGames.jsx` lines 69-85
  - Component: Close button in `GamesTable` calls `onClose(game.id)` without any confirmation
  - Code or behavior observed: The admin Close button directly calls `handleClose` with no confirmation dialog. Unlike the user-facing close in `GamePanel.jsx` (which at least has `window.confirm`), the admin close has zero confirmation before a destructive action.
- **Mobile Impact**: On mobile with dense table rows and enlarged touch targets, accidental taps on the Close button are more likely. There is no undo.
- **User/Admin Impact**: Admin may accidentally close an active game, affecting all players. No confirmation or undo exists.
- **Recommendation**: Add a confirmation step (custom React modal preferred, or at minimum `window.confirm`) before admin-closing a game.
- **Suggested Follow-up Issue**: Add confirmation to admin close-game action

### FUMOB-013: Registration password confirm has no match indicator

- **Severity**: P2
- **Form**: Register
- **Status**: Open
- **Evidence**:
  - File: `frontend/src/components/LoginPage.jsx` lines 314-325
  - Component: Confirm password field has no real-time match validation
  - Code or behavior observed: The `password_confirm` field is sent to the API but there is no client-side check that it matches `password`. Users only discover a mismatch when the API returns an error, which appears at the bottom of the page.
- **Mobile Impact**: On mobile with the keyboard covering the form, users cannot see both password fields simultaneously. Mismatches are common on touch keyboards.
- **User/Admin Impact**: Failed registration attempts with confusing API error messages. Users must scroll to see the error and then re-enter both passwords.
- **Recommendation**: Add real-time client-side password match validation, showing an inline error on the confirm field when values don't match.
- **Suggested Follow-up Issue**: Add client-side password match validation

### FUMOB-014: Add Field location defaults to hardcoded coordinates

- **Severity**: P3
- **Form**: Add Field
- **Status**: Open
- **Evidence**:
  - File: `frontend/src/components/AddFieldModal.jsx` line 9
  - Component: `const DEFAULT_POSITION = [30.9872, 34.9314]` (Yeruham, Israel)
  - Code or behavior observed: The map starts at a hardcoded default position. If the user does not tap "Use current location" or manually pan the map, the field will be created at the default coordinates, which may be far from the actual field location.
- **Mobile Impact**: On mobile, the small map picker may not clearly show that the pin is at a default position rather than the user's current location. Users may not realize they need to interact with the map.
- **User/Admin Impact**: Fields created at incorrect coordinates. Admins must review and correct locations.
- **Recommendation**: Either auto-request geolocation on modal open, or display a warning/hint that the user should set the location before submitting.
- **Suggested Follow-up Issue**: Improve location picker default behavior in Add Field modal

## Login Form Review

- **Email/phone/Google login clarity**: Login offers username/password and Google OAuth. Clear separation via divider with "or" text. Google button is rendered by the Google SDK.
- **Password field usability**: Standard `type="password"` with `autoComplete="current-password"`. No show/hide toggle.
- **Error messages**: Single global error at the bottom of the panel (after Google button). See FUMOB-004.
- **Submit button text/state**: Shows "Sign In" / "Signing in..." with `disabled` during loading. Clear.
- **Loading/disabled state**: `isLoading` state disables submit button and shows status text. Prevents double submission.
- **Autocomplete attributes**: `autoComplete="username"` and `autoComplete="current-password"`. Correct.
- **Mobile readability**: Hebrew labels are properly translated. RTL alignment works.
- **Hebrew/RTL alignment**: Labels wrap correctly. No overflow issues observed.

**Verdict**: PARTIAL — error placement and lack of password recovery are the main issues.

## Register Form Review

- **Required field clarity**: All 6 fields have `required` attribute. No visual required indicator (asterisk). However, since all fields are required, this is acceptable.
- **Step/mode clarity**: Login and Register are tabs. The active tab is visually distinct (dark background). Clear.
- **Error placement**: Global error at bottom of panel (FUMOB-004). No inline field errors.
- **Long form completion**: 6 fields on a single page. On short screens with keyboard open, users must scroll to reach submit. ISSUE-139 addressed the scrolling (100dvh, overflow-y: auto), so the submit button is reachable.
- **Submit state**: Shows "Create Account" / disabled during loading. Clear.
- **Input types/autocomplete**: Correct types (`text`, `email`, `tel`, `password`) and autocomplete attributes (`name`, `username`, `email`, `tel`, `new-password`). Well-implemented.
- **Password requirements**: `minLength={8}`, `maxLength={128}` on both password fields. No visible hint (FUMOB-001).
- **Hebrew copy clarity**: All labels are translated to Hebrew. Field names are clear.

**Verdict**: PARTIAL — missing password requirements hint and reliance on native validation are the main issues.

## Create Game Form Review

- **Now/Future mode clarity**: Radio group with "Now" and "Future" options. Clear labels. Date/time fields appear conditionally for "Future" mode. Good.
- **Date/time field clarity**: Standard `type="date"` and `type="time"` inputs appear only in "Future" mode. Uses native pickers which handle RTL and Hebrew.
- **Participant count clarity**: Players Present and Max Players fields have clear Hebrew labels. `inputMode="numeric"` shows numeric keypad (ISSUE-139). Good.
- **Required fields**: Sport type `required`, players `required`, date/time `required` in future mode. All fields are required — no ambiguity.
- **Validation error placement**: Single global error message above submit button (FUMOB-006). No inline errors. `CGMOB-004` still open.
- **Submit/cancel clarity**: Submit button with loading text. Close button (x) available but no explicit Cancel. Acceptable for this modal since it's a creation action.
- **Numeric input behavior**: `inputMode="numeric"` and `pattern="[0-9]*"` applied in ISSUE-139. Numeric keypad shows correctly.
- **Remaining issues from CGMOB**: `CGMOB-001` resolved (ISSUE-139), `CGMOB-002` resolved (ISSUE-139), `CGMOB-003` resolved (ISSUE-141), `CGMOB-004` still open (inline validation), `CGMOB-005` resolved (ISSUE-139).

**Verdict**: PARTIAL — global-only error placement is the main remaining issue.

## Field Report Form Review

- **Report reason selection**: Select dropdown with 8 categorized options plus a placeholder "Choose category". Clear.
- **Required fields**: Both category and description are `required`. Validation checks both with translated error messages.
- **Error messages**: Inline `modal-error` above the action buttons. Well-placed.
- **Submit/cancel state**: Both Cancel and Submit buttons present. Submit shows "Submitting..." with `disabled` state. Submit disabled during submission. Close button also disabled during submission to prevent abandonment.
- **Destructive/sensitive copy clarity**: Not applicable — this is a report, not a destructive action.
- **Mobile layout**: Actions in a 2-column grid (stacks to 1-column below 520px per CSS). Good responsive behavior.

**Verdict**: PASS — this form is well-implemented for mobile use.

## Admin Forms Review

- **Admin search/filter usability**: Search input in AdminUsers has a clear label and placeholder. Admin tab filters in AdminFields and AdminFieldReports have clear labels. Good.
- **User action reason prompts**: `window.prompt` used for ban/suspend reason (FUMOB-002). Significant mobile usability issue.
- **Field moderation forms/actions**: Approve/Reject buttons in AdminFields are clear with loading states (`workingFieldId` disables buttons). Status change via select dropdown is functional.
- **Game management controls**: Admin Extend button is clear. Admin Close button lacks any confirmation (FUMOB-012) — more dangerous than the user-facing close which at least has `window.confirm`.
- **Native prompt/confirm usability**: `window.prompt` in AdminUsers (FUMOB-002). `window.confirm` in GamePanel (FUMOB-003, user-facing but also affects admin context). See detailed findings.
- **Error/loading states**: All admin components show loading states, error messages with retry buttons, and empty states. Well-implemented.
- **Risk of accidental admin mistakes**: Admin close-game has no confirmation (FUMOB-012). Admin ban/suspend has `window.prompt` which can be accidentally dismissed. Admin field approve/reject has no undo but the action buttons are clearly labeled.

**Verdict**: PARTIAL — native prompt/confirm and missing close-game confirmation are the main issues.

## Related Forms Review

### Add Field Form
- Modal form with 7 fields and a map location picker. No cancel button (FUMOB-008). Optional fields not marked (FUMOB-009). Default location is hardcoded (FUMOB-014). Otherwise well-structured with clear labels and a loading submit state.

### Notification Preferences Form
- Complex form with toggles, range slider, city autocomplete, and field selection. City validation only on submit (FUMOB-010). Otherwise has good loading/saving states and clear toggle labels.

### CityAutocomplete
- Suggestion list with filtered results. `touchstart` listener added in ISSUE-139 for touch-safe dismissal. Autocomplete options now meet 44px touch target (ISSUE-141). `autoComplete="off"` correctly set. Keyboard navigation (ArrowUp/Down, Enter, Escape) works. Good implementation.

### My Games Filters
- Simple toggle filter. Not a form — just a button that filters the games list. No usability concerns beyond touch target (resolved in ISSUE-141).

## Known Existing Findings Mapped

| Previous ID | Source | Form/Screen | Description | Current Status | Becomes FUMOB? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `CGMOB-004` | ISSUE-131 | Create Game | Global error only, no inline validation | Still open | Yes — `FUMOB-006` |
| `ADMOB-001` | ISSUE-134 | Admin Users | Native `window.prompt` for moderation | Still open | Yes — `FUMOB-002` |
| `GDMOB-003` | ISSUE-132 | Game Details | Native `window.confirm` for close game | Still open | Yes — `FUMOB-003` |
| `ML-REGISTER-002` | ISSUE-128 | Registration | Native validation bubbles in English | Still open | Yes — `FUMOB-005` |
| `ML-REGISTER-003` | ISSUE-128 | Registration | Global API error at bottom | Still open | Yes — `FUMOB-004` (combined with login) |
| `CGMOB-001` | ISSUE-131 | Create Game | Modal keyboard trap | Resolved (ISSUE-139) | No |
| `CGMOB-002` | ISSUE-131 | Create Game | iOS auto-zoom | Resolved (ISSUE-139) | No |
| `CGMOB-003` | ISSUE-131 | Create Game | Touch targets below 44px | Resolved (ISSUE-141) | No |
| `CGMOB-005` | ISSUE-131 | Create Game | Numeric keypad | Resolved (ISSUE-139) | No |
| `NTMOB-004` | ISSUE-133 | Notifications | Touch dismissal | Resolved (ISSUE-139) | No |
| `NTMOB-005` | ISSUE-133 | Notifications | Autocomplete clipped | Resolved (ISSUE-139) | No |
| `ML-LOGIN-001` | ISSUE-127 | Login | Submit below viewport | Resolved (ISSUE-139) | No |
| `ML-REGISTER-001` | ISSUE-128 | Registration | Submit unreachable | Resolved (ISSUE-139) | No |
| All TTMOB-* | ISSUE-140 | All screens | Touch target violations | Resolved (ISSUE-141) | No |

## Recommended Remediation Plan

### Priority 1 — P1 Native Prompt/Confirm Replacement
1. **FUMOB-002** — Admin Users — P1 — Replace `window.prompt` with custom React modal for ban/suspend reason input. This is the most impactful mobile usability issue because it affects admin workflows with destructive consequences.
   - Suggested branch: `issue-XXX-admin-moderation-modal`
   - Suggested issue: Replace native window.prompt for admin moderation with custom modal

2. **FUMOB-003** — Game Details — P1 — Replace `window.confirm` with custom React confirmation modal for close-game action. Destructive action needs clear, translated confirmation.
   - Suggested branch: `issue-XXX-close-game-confirm-modal`
   - Suggested issue: Replace native close-game confirmation with custom modal

### Priority 2 — P1 Password Requirements
3. **FUMOB-001** — Registration — P1 — Add visible password requirements hint. Users should know the 8-character minimum before typing.
   - Suggested branch: `issue-XXX-password-requirements-hint`
   - Suggested issue: Add visible password requirements hint to registration form

### Priority 3 — P2 Error Placement and Validation
4. **FUMOB-004** — Login/Register — P2 — Move error messages to inside each form, above the submit button.
   - Suggested branch: `issue-XXX-login-error-placement`
   - Suggested issue: Improve login/registration error message placement

5. **FUMOB-005** — Registration — P2 — Replace native validation bubbles with custom inline validation.
   - Suggested branch: `issue-XXX-registration-inline-validation`
   - Suggested issue: Add localized inline validation for registration form

6. **FUMOB-006** — Create Game — P2 — Add inline validation errors near problematic fields.
   - Suggested branch: `issue-XXX-create-game-inline-validation`
   - Suggested issue: Implement inline validation errors in Create Game modal

7. **FUMOB-013** — Registration — P2 — Add client-side password match check.
   - Suggested branch: `issue-XXX-password-match-validation`
   - Suggested issue: Add client-side password match validation

### Priority 4 — P2 Form Interaction Improvements
8. **FUMOB-008** — Add Field — P2 — Add Cancel button alongside Submit.
   - Suggested branch: `issue-XXX-add-field-cancel-button`
   - Suggested issue: Add cancel button to Add Field modal

9. **FUMOB-010** — Notifications — P2 — Add immediate city validation feedback.
   - Suggested branch: `issue-XXX-city-validation-feedback`
   - Suggested issue: Add inline city validation to notification preferences

10. **FUMOB-012** — Admin Games — P2 — Add confirmation to admin close-game.
    - Suggested branch: `issue-XXX-admin-close-game-confirm`
    - Suggested issue: Add confirmation to admin close-game action

11. **FUMOB-007** — Create Game — P2 — Translate and clarify age note placeholder.
    - Suggested branch: `issue-XXX-age-note-placeholder`
    - Suggested issue: Translate and clarify Create Game age note placeholder

### Priority 5 — P3 Polish
12. **FUMOB-009** — Add Field — P3 — Mark optional fields.
    - Suggested issue: Mark optional fields in Add Field form

13. **FUMOB-011** — Login — P3 — Add password recovery link/help.
    - Suggested issue: Add password recovery flow or help text

14. **FUMOB-014** — Add Field — P3 — Improve location default behavior.
    - Suggested issue: Improve location picker default behavior in Add Field modal

## Risks and Unknowns

- **Real-device typing behavior**: Password input, autocomplete suggestion dismissal, and native picker behavior cannot be fully verified without real device testing. Emulated viewports approximate but do not replicate touch keyboard behavior.
- **Production data**: Longer Hebrew names, field names, or error messages from the API may cause text wrapping or overflow that is not visible with test data.
- **Native prompts/confirms**: Behavior of `window.prompt` and `window.confirm` varies by browser and OS version. Some mobile browsers may style them differently or block them entirely in PWA/webview contexts.
- **Product copy decisions**: Some fixes (FUMOB-001 password hint, FUMOB-007 age note, FUMOB-011 password recovery) require product decisions about copy and wording that go beyond frontend engineering.
- **Admin form improvements**: Replacing `window.prompt` (FUMOB-002) requires creating a new React modal component, which is a moderate scope change. Replacing `window.confirm` (FUMOB-003, FUMOB-012) is similar but smaller.

## Final Verdict

Form usability remediation can begin immediately. No form is completely broken — all forms can be completed on mobile, and keyboard/touch-target issues were resolved in ISSUE-139 and ISSUE-141.

Mobile forms are **not fully ready** for production release due to:
1. Native `window.prompt`/`window.confirm` used for destructive admin and game actions (P1)
2. Missing password requirements visibility in registration (P1)
3. Error placement and validation UX below modern mobile standards (P2)

The P1 issues should be fixed first: native prompt/confirm replacements and password requirements hint. The P2 validation and error placement issues should follow. P3 polish items can be addressed as time permits.
