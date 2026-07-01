# Android Network Security Configuration Implementation

## Summary

This implements the Network Security Config portion of the policy defined in [`docs/android-network-security-requirements.md`](android-network-security-requirements.md) (ISSUE-202). It adds an explicit, system-CA-only, no-cleartext Network Security Config and wires it into the Android manifest. It does not touch backend CORS and does not change the Android API base URL — both remain separate follow-up work, as scoped by ISSUE-202 and this issue's hard rules.

## Scope

**In scope (implemented):**
- Add `frontend/android/app/src/main/res/xml/network_security_config.xml`.
- Reference it from `frontend/android/app/src/main/AndroidManifest.xml` via `android:networkSecurityConfig`.

**Explicitly out of scope (not implemented here):**
- Backend CORS configuration.
- Android API base URL / `VITE_API_URL` changes.
- Any cleartext exception, global or domain-specific.
- Certificate pinning.
- Gradle changes (none were required; the build validated the config without any).
- Package ID, `MainActivity`, or Capacitor `appId` changes.

## Files Changed

### 1. Added: `frontend/android/app/src/main/res/xml/network_security_config.xml`

```xml
<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
    <base-config cleartextTrafficPermitted="false">
        <trust-anchors>
            <certificates src="system" />
        </trust-anchors>
    </base-config>
</network-security-config>
```

This is the exact policy-approved shape from ISSUE-202/this issue's instructions:
- `cleartextTrafficPermitted="false"` on `<base-config>` — cleartext traffic is explicitly denied for all domains, with no `<domain-config>` overrides of any kind.
- `<trust-anchors><certificates src="system" /></trust-anchors>` — only the Android system CA store is trusted. User-installed/custom CAs are not trusted, since no `src="user"` entry was added.
- No pinning (`<pin-set>`) was added.
- No debug-only override manifest/resource was added, so this single config applies to every build variant, including debug and release.

### 2. Updated: `frontend/android/app/src/main/AndroidManifest.xml`

```diff
     <application
         android:allowBackup="true"
         android:icon="@mipmap/ic_launcher"
         android:label="@string/app_name"
+        android:networkSecurityConfig="@xml/network_security_config"
         android:roundIcon="@mipmap/ic_launcher_round"
         android:supportsRtl="true"
         android:theme="@style/AppTheme">
```

This is the only manifest change. No other attribute was added or removed; in particular, `android:usesCleartextTraffic` was not added, and no other application/activity attributes were touched.

## Validation

| Command | Result |
| --- | --- |
| `npm run build` | PASS — Vite build succeeded, no changes to app behavior (frontend source was not touched). |
| `npx cap sync android` | PASS — assets copied, push-notifications plugin detected, no sync errors. |
| `.\gradlew.bat :app:processDebugMainManifest` (JBR JDK) | PASS — manifest merge succeeded with no errors. |
| Merged manifest inspection (`app/build/intermediates/merged_manifest/debug/processDebugMainManifest/AndroidManifest.xml`) | Confirmed `android:networkSecurityConfig="@xml/network_security_config"` is present in the merged manifest, and `android:usesCleartextTraffic` is still absent. |
| `.\gradlew.bat assembleDebug` (JBR JDK) | PASS — `BUILD SUCCESSFUL`. This exercises `processDebugResources` (aapt2), which validates that `network_security_config.xml` is well-formed and a legal resource; a malformed or invalid Network Security Config would have failed this step. |

No Gradle file was modified. The build succeeded without any Gradle change, confirming none was required for this resource addition.

No APK, build output, or temp file was committed; only the two source files above and this report are part of the change set.

## Effect on ISSUE-201 Blockers

This change is intentionally narrow and does not resolve either ISSUE-201 blocker on its own:

- **CORS blocker:** unaffected. This config governs the Android OS's cleartext/TLS trust policy; it has no bearing on the backend's `CORS_ORIGINS` allowlist. That remains a separate backend change.
- **Mixed Content blocker:** unaffected. As documented in ISSUE-202, Network Security Config governs OS-level cleartext socket permission, not Chromium's Mixed Content policy for an HTTPS-loaded WebView page requesting an HTTP resource. Login (and any other API call) will still be blocked client-side by Mixed Content until the Android API base URL points at an HTTPS backend. This issue does not change the API base URL, per its hard rules.

What this change does provide: an explicit, auditable statement — enforced by the OS, not just by convention — that this app never permits cleartext traffic and never trusts non-system CAs, in every build variant including debug. Previously this was true only by default (absence of any override); now it is explicit and cannot be silently weakened by a future change adding `usesCleartextTraffic="true"` without also removing this file or its manifest reference, which makes such a regression more visible in review.

## Risks

| Risk | Assessment |
| --- | --- |
| Config accidentally overridden later by a careless `usesCleartextTraffic="true"` addition | Reduced versus before: a reviewer now sees both the explicit `network_security_config.xml` and any conflicting manifest attribute in the same diff, making the contradiction easier to catch. |
| Debug workflows that still rely on the LAN HTTP backend from ISSUE-200/201 | Will now fail even the native cleartext path (previously they failed only via WebView Mixed Content but would have been undefined for any native HTTP call a plugin might make). This is intended: per ISSUE-202, plain LAN HTTP is not an approved debug validation target. Debug validation should use an HTTPS backend or HTTPS tunnel, per ISSUE-202. |
| None identified for production/release | This config only makes the existing default explicit; no behavior change for a correctly-configured HTTPS production backend. |

## Follow-up Work (unchanged from ISSUE-202)

1. Configure backend `CORS_ORIGINS` to explicitly allow `https://localhost` (no wildcard) — separate issue.
2. Point the Android API base URL at an HTTPS backend (deployed staging/production, or an HTTPS tunnel) — separate issue.
3. Revalidate Android API communication (repeat ISSUE-201-style login/fields/games/notifications checks) once both of the above land.

## Final Verdict

**Implemented as scoped.** The Network Security Config now explicitly disables cleartext traffic and restricts trust to system CAs, matching the ISSUE-202 policy exactly, with no cleartext exception, no user CA trust, and no certificate pinning added. Backend CORS and the Android API base URL remain untouched, as required. This change alone does not make Android API communication succeed — the CORS and HTTPS-target follow-up work identified in ISSUE-202 is still required before a revalidation can return GO.
