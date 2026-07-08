# Background Location Requirements Review

## 1. Purpose
This document reviews the requirements for background location access within the application. It evaluates whether the app currently needs background location privileges, assesses the associated business and technical implications, and defines the policy for future adoption of background location tracking.

---

## 2. Current Decision
**Background Location is NOT required for the current MVP.**

### Rationale
- **Foreground Context**: All current location-based user flows function entirely while the application is active and visible in the foreground, or when the user explicitly interacts with a feature.
- **User Marker**: The user's position on the map is only relevant and displayed while the map screen is actively open.
- **Nearby Fields**: Querying fields can be driven by the active map viewport bounds (foreground-only), user-saved preferences (city/field), or a default/fallback map center.
- **Navigation Launch**: The application only provides destination deep links to external navigation apps (Waze/Google Maps), delegating all active navigation tracking and origin resolution to those dedicated external utilities.
- **Notifications**: Location-based notifications are matched server-side against the user's saved notifications preferences (fixed coordinates and radius) when a game is created. This eliminates the need to track the user's coordinates in the background.
- **No Continuous Tracking**: No existing feature or workflow requires the application to continuously monitor or log the user's location when the app is minimized, closed, or when the device is locked.

---

## 3. Current Use-Case Review

| Use Case | Needs Background Location? | Reason |
| :--- | :---: | :--- |
| **User Marker** | **No** | Only rendered and updated while the map page is actively in view. |
| **Nearby Fields** | **No** | Viewport bounds are calculated in the foreground. Default/fallback centers and saved preferences are used for out-of-bounds cases. |
| **Navigation Launch** | **No** | Link generation is destination-based and opens external native navigation applications which manage coordinates independently. |
| **Game Creation** | **No** | Location data is derived from the selected field coordinates or a single foreground pin placement, not continuous tracking. |
| **Join Game** | **No** | Triggered by direct user action in the foreground while the game panel is open. |
| **Notifications** | **No** | Distance-based notification matching is handled server-side using fixed, saved preference points and radius configurations. |
| **Location Refresh** | **No** | Executed as a one-shot foreground process (e.g. manual click of "My Location" button or foreground resume revalidation). |
| **Future Proximity Validation** | **No** | Check-in or proximity checks will require a fresh foreground-only location fix at the moment of the action, not background monitoring. |

---

## 4. Future Feature Triggers
Should any of the following features be proposed, a reconsideration of background location may be justified:

- **Automatic Check-in**: Checking the user into a game automatically when they physically arrive at the field, even if the app is closed.
- **Background Proximity Validation**: Passively validating that players remain within field boundaries during a match without requiring them to open the app.
- **Real-time Proximity Sharing**: Sharing live location updates with friends or team members when heading to a scheduled match.
- **Device/User Safety features**: Live location tracking during matches for emergency alerts or verification.
- **Sports Activity Tracking**: Passive tracking of routes, distances, and metrics during a game or activity.
- **Dynamic Geo-fenced Notifications**: Real-time push notifications triggered when passing near an active field, where saved static preferences are insufficient.

### Mandatory Review Checklist for Future Triggers
Before implementing any background location features, the proposal must document and prove:
1. **Clear User-Visible Value**: How does background access directly benefit the user's experience?
2. **Business Justification**: ROI of adding the feature versus the cost of implementation and user attrition.
3. **Privacy Justification**: An explicit data minimisation plan showing why foreground alternatives cannot work, how data is encrypted, and how it is purged.
4. **Battery Impact Review**: Measured power consumption impact of background GPS wakeups on various devices.
5. **Store Policy Review**: Compliance with strict Google Play and Apple App Store review policies.
6. **Explicit User Consent**: Designing explicit, dual-prompt opt-in flows explaining why background access is needed.
7. **Alternative Design Analysis**: Proof that foreground-only, manual refresh, or server-side geo-fencing alternatives were investigated and ruled out.

---

## 5. Business Justification Review
Requesting background location access currently has a weak business justification and presents significant product risks:

- **Permission Friction**: Requesting background location permissions triggers system warnings that significantly damage user trust.
- **Increased Opt-out/Uninstall Rates**: Users are highly sensitive to background tracking prompts and frequently uninstall apps that request it without immediate, clear value.
- **App Store Review Delays**: Google and Apple scrutinize background location usage heavily. Declaring background location triggers manual reviews, detailed video demonstrations, and increases rejection risk.
- **Friction in Funnel**: Lower permission conversion rates directly impact user onboarding and active engagement.
- **QA and Maintenance Overhead**: Continuous background tracking behaves differently across OS battery optimization states (e.g., Doze mode on Android, iOS background task suspension), introducing high QA complexity.

---

## 6. Platform / Store Considerations

### Android
- **ACCESS_BACKGROUND_LOCATION**: Starting in Android 10, background location access requires declaring the explicit `ACCESS_BACKGROUND_LOCATION` permission in `AndroidManifest.xml` alongside `ACCESS_FINE_LOCATION`.
- **Runtime Prompt Restrictions**: In Android 11+, the OS runtime dialog does not offer the "Allow all the time" option directly. The user must be guided with an in-app rationale to open the app's system settings and toggle the permission manually.
- **Policy Verification**: Google Play requires developer declaration forms detailing the background location use case, supported by a video showing the foreground-to-background transition.

### iOS
- **Always Authorization**: iOS requires the user to grant `Always` location authorization. 
- **Configuration**: Background location updates require configuring background modes (`location` key in `UIBackgroundModes` within `Info.plist`) and setting the native `allowsBackgroundLocationUpdates` property to `true`.
- **Blue Bar Indicator**: iOS displays a visible blue bar or icon in the status bar when an app uses location services in the background, raising immediate user privacy awareness and potential concern.

---

## 7. Alternatives to Background Location
Before any background location logic is proposed, the app should leverage these existing, highly efficient alternatives:

- **Foreground-Only Location**: Acquiring a location fix only when the app is active and in-use (e.g., one-shot `getCurrentPosition`).
- **Manual Refresh**: Providing a clean "Refresh location" button for the user to trigger location checks explicitly.
- **Static Saved Preferences**: Storing user-selected cities, fields, or search radiuses in the database, allowing server-side matching without device-side tracking.
- **Server-Side Notification Matching**: Querying static user preferences on the server when games are created.
- **External App Delegation**: Directing navigation flows directly to external applications (Waze, Google Maps) which already possess background navigation capabilities.
- **Foreground Resume Refresh**: Scheduling a quick location update when the app returns from the background to the foreground.

---

## 8. Decision Policy
Background Location must not be added to the codebase unless **all** of the following conditions are met:

1. A specific, approved product feature requires location tracking while the app is closed.
2. The feature cannot be implemented using foreground-only location, manual refresh, or server-side preferences.
3. The user receives clear, tangible value from the passive tracking feature.
4. The business justification outweighs permission friction and store review rejection risks.
5. A comprehensive privacy, battery, and store compliance review is fully documented.
6. Platform-specific (Android and iOS) permissions and workflows are separately designed and approved.
7. The feature includes an explicit explanation screen, user opt-in, a graceful fallback for denial, and a toggle to disable the tracking easily within settings.

---

## 9. Current Requirement Status
- **Background Location**: Not required.
- **Android `ACCESS_BACKGROUND_LOCATION`**: Not required.
- **iOS Always Location**: Not required.
- **Native Background Services/Tasks**: Not required.

*Future Status*: This decision will only be revisited if a concrete background-dependent feature is formally approved.

---

## 10. Out of Scope
The following activities are explicitly out of scope for ISSUE-261:
- No codebase implementation of background services.
- No permission changes in frontend.
- No additions of `ACCESS_BACKGROUND_LOCATION` to `AndroidManifest.xml`.
- No updates to iOS `Info.plist` files.
- No setup of Capacitor background task plugins.
- No analytics tracking.
- No automated tests or UI modifications.
- No app-store submission adjustments.

---

## 11. Definition of Done Checklist
- [x] Current location need reviewed and documented.
- [x] Future location need reviewed and triggers defined.
- [x] Business justification and product friction risks reviewed.
- [x] Current decision (NOT required) clearly documented.
- [x] Current location use cases mapped to background necessity.
- [x] Future triggers and mandatory checklists documented.
- [x] Platform (Android and iOS) considerations documented.
- [x] Alternatives to background location documented.
- [x] Scope confirmed as documentation-only.
