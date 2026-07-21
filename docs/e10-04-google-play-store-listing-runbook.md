# E10-04 Google Play Store listing and asset runbook

## 1. Scope and release-engineering rule

E10-04 prepares the Google Play listing package and replaces stock Capacitor launcher/splash resources. The supplied `release/brand/source/approved-artwork.png` is the sole visual source of truth.

No branding, logo, artwork, mockup, fake UI, or synthetic screenshot may be created. Application behavior must remain unchanged. Code changes are out of scope unless a verified Play listing blocker cannot be resolved through assets, metadata, configuration, or manual console work and the product owner explicitly approves the code change.

## 2. Repository deliverables

```text
release/
├── brand/
│   ├── README.md
│   ├── provenance.md
│   └── source/approved-artwork.png
├── google-play/
│   ├── README.md
│   ├── asset-manifest.json
│   ├── declarations/
│   ├── evidence/
│   ├── graphics/
│   │   ├── store-icon-512.png
│   │   ├── feature-graphic-1024x500.png
│   │   └── screenshots/phone/{he-IL,en-US}/
│   └── metadata/{he-IL,en-US}/
└── scripts/
    ├── export-approved-artwork.ps1
    └── validate-google-play-assets.ps1
```

Android runtime graphics remain in `frontend/android/app/src/main/res/` because Android resource packaging requires that location.

## 3. Google Play listing assets and specifications

| Asset/field | Required quantity | Specification | E10-04 status |
| :--- | :--- | :--- | :--- |
| App icon | 1 | 512 × 512; 32-bit PNG with alpha channel; sRGB; maximum 1,024 KB; full square without a baked circular mask or drop shadow | Exported from approved source |
| Feature graphic | 1 | 1024 × 500; JPEG or opaque 24-bit PNG; no alpha; maximum 15 MB | Opaque PNG exported as centered crop |
| Phone screenshots | 2–8 for the default listing; localized sets may inherit | JPEG or opaque 24-bit PNG; maximum 8 MB each; each side 320–3840 px; long side no more than 2× short side | Eight owner-approved Redmi captures exported at 921 × 1842 |
| App name | 1 per locale | Maximum 30 characters | Added for `he-IL` and `en-US` |
| Short description | 1 per locale | Maximum 80 characters | Added for `he-IL` and `en-US` |
| Full description | 1 per locale | Maximum 4,000 characters | Added for `he-IL` and `en-US` |
| Release notes | 1 per release/locale | Maximum 500 characters in the Play release workflow | Initial text added |
| Support email | 1 | Required, monitored address | Proposed `support@yesh-mishak.com`; owner verification pending |
| Website | 0–1 | Public HTTPS URL recommended | Proposed `https://yesh-mishak.com/`; verification pending |
| Privacy-policy URL | 1 for this app/data profile | Public, HTTPS, non-editable webpage, accessible without login and consistent with Data safety | Proposed `/privacy`; legal/deployment verification pending |

Phone screenshots are the only required visual set for the current phone application. If the uploaded artifact becomes available to tablets, Chromebooks, Android TV, Wear OS, or Android Automotive, the release owner must review the device catalog and add every console-requested device-specific asset before launch. For stronger phone merchandising, use at least four approved 1080 × 1920 screenshots per locale when the supplied set permits it.

## 4. Deterministic artwork integration

1. Verify source SHA-256 is `767DEDCA3FDF794FAF09ED8B6D73C65B7C03EBD3E0391FEEDBF05C01085B785E`.
2. Run `release/scripts/export-approved-artwork.ps1` from the repository root.
3. Confirm the store icon is a direct square resize and the feature graphic is a centered cover crop.
4. Confirm launcher resources exist at all five Android densities. Legacy round icons may contain only the circular alpha mask required by Android.
5. Confirm all portrait and landscape splash densities show only a centered cover crop of the source.
6. Run `release/scripts/validate-google-play-assets.ps1`.
7. Review representative outputs visually at actual size and Android launcher masks; record approval.

The adaptive-icon background `#010232` is sampled from approved source pixel `(0,0)` and is only a fallback for mask/parallax edges. It must not replace or cover the opaque approved foreground.

## 5. Screenshot integration procedure

The project owner will provide the already-approved image files separately.

Current integration result: nine final Redmi captures were received on 2026-07-21. Google Play allows no more than eight phone screenshots, so attachments 1–8 form the official set in supplied order; attachment 9 is omitted as a near-duplicate of attachment 2's My Games screen. The source captures are 921 × 2048. The official exports remove only Redmi system chrome with a deterministic crop of 80 pixels from the top and 126 pixels from the bottom, producing opaque 921 × 1842 PNGs at the exact 2:1 limit. No app UI was resized, generated, reconstructed, annotated, or overlaid. The English listing inherits this compliant default set.

1. Verify replacement/re-exported files are explicitly approved originals and are real captures from the intended release candidate.
2. Place Hebrew images in `graphics/screenshots/phone/he-IL/` and English images in `graphics/screenshots/phone/en-US/`.
3. Use zero-padded filenames to preserve order. Do not annotate, frame, reconstruct, translate pixels, or create substitutes.
4. Inspect for personal data, test credentials, notifications, location history, debug banners, emulator controls, browser chrome, and unrelated OS UI.
5. Record build/commit, locale, device/OS, screen, dimensions, and approval in `evidence/capture-manifest.md`.
6. Add truthful locale-specific alt text to each `screenshot-alt-text.yml`; describe only visible content.
7. Run validation and add screenshot hashes to `evidence/sha256sums.txt`.

If any approved screenshot fails Play dimensions or exposes sensitive information, stop and request a new approved export. Deterministic removal of unrelated device system chrome is permitted only when recorded in the capture manifest; do not repair, reconstruct, or synthesize app UI.

## 6. Metadata and declaration procedure

1. Product owner reviews both locale directories for factual accuracy, natural language, and unsupported claims.
2. Confirm `he-IL` is the intended default language. Check RTL rendering after pasting into Play Console.
3. Verify every listed feature against the signed candidate; remove text for disabled, staged, or unreliable features.
4. Complete `declarations/store-settings.md`, `content-declarations.md`, and `data-safety-inventory.md` using the production SDK inventory and a release-build network trace.
5. Legal/privacy owner completes `privacy-alignment-checklist.md` and verifies the public URL.
6. Supply reviewer access through Play Console using `reviewer-access.template.md`; never commit credentials.
7. Complete current Play Console questionnaires, even if the console adds questions not present in this repository.

## 7. Build, test, and device verification

Repository checks:

```powershell
cd frontend
npm install
npm run lint
npm run build
npx cap sync android
cd android
.\gradlew.bat assembleDebug
```

Use the documented production/release workflow for the signed AAB; debug assembly does not prove signing or store readiness. If `google-services.json`, production environment values, or signing material are unavailable, record the build as blocked rather than inventing files or credentials.

Physical/emulator checks on at least one supported Android phone:

- Clean install: launcher icon is approved artwork with no stock Capacitor mark, white fringe, square corner leak, or unexpected crop.
- Round and squircle launchers: focal content remains recognizable under common OEM masks.
- Cold launch in portrait and landscape: splash contains only approved artwork, fills the window, and has no stretch, blank flash, or placeholder.
- Warm launch/resume: no unexpected splash regression or behavior change.
- Light/dark mode, RTL/LTR, small/large display scaling, and Android 12+ system splash behavior are acceptable.
- App functionality, permissions, authentication, map, game flows, notifications, links, and back navigation are unchanged.
- Signed AAB package name/version, target API, signing identity, and Play pre-launch report match the release record.

## 8. Edge cases and stop conditions

- Source hash or dimensions changed: stop and obtain renewed artwork approval.
- Screenshot absent: repository validation may warn, but E10-04 cannot be accepted or uploaded until valid approved sets exist.
- A locale has one screenshot: fail; Play requires at least two.
- Screenshot aspect ratio exceeds 2:1, includes alpha, or exceeds 8 MB: request an approved compliant export.
- Store icon exceeds 1,024 KB or feature graphic contains alpha: regenerate deterministically from the unchanged approved source.
- Adaptive mask cuts critical content or shows an edge: owner must approve a different crop derived from the same source; do not redesign.
- Android 12 splash renders differently from legacy resource expectations: diagnose theme/resource behavior; make the smallest configuration change only if required and explicitly review it as behavior-affecting.
- Play Console rejects metadata or adds a new mandatory declaration: capture the exact error and update repository documentation/copy; do not guess policy answers.
- Privacy policy, Data safety answers, SDK/network behavior, and listing claims disagree: hard release stop.
- Credentials or personal data appear in repository/evidence: remove from the release package and rotate credentials if exposed.

## 9. Acceptance criteria

E10-04 is accepted only when all are true:

- The approved source file and provenance are committed; no unapproved/generated visual asset is used.
- All stock Capacitor launcher and splash visuals are replaced at every existing Android density/orientation.
- Store icon and feature graphic meet exact dimensions, formats, alpha policy, and size limits.
- Two to eight owner-approved phone screenshots per published locale pass automated and human review.
- Hebrew and English copy passes character limits, product review, and Play Console Preview.
- Store settings, content rating, audience, ads, UGC, app access, Data safety, privacy, and account-deletion answers are completed and approved.
- Public privacy/support endpoints work from a logged-out external browser.
- Asset validator, frontend lint/build, Capacitor sync, Android build, installed-device visual checks, and functional regression smoke tests pass for the candidate.
- Completion evidence contains hashes, build/commit identity, screenshot provenance/order, owner approvals, and console-preview/upload proof.
- `git diff` contains no unrelated application behavior change, credential, generated build output, or unapproved artwork.

## 10. Completion evidence and handoff

The release owner attaches or links:

1. Final Git commit and clean-tree status.
2. Validator output and `sha256sums.txt`.
3. Frontend/Android build logs and signed AAB artifact hash.
4. Device screenshots or video proving launcher masks and portrait/landscape cold start.
5. Approved screenshot capture manifest and alt-text files.
6. Named product, artwork-rights, legal/privacy, Data safety, and release approvals.
7. Play Console listing previews, completed app-content dashboard, upload result, and pre-launch report.
8. Any accepted exception with owner, rationale, expiry/follow-up issue, and rollback plan.

Until those items exist, this repository package is implementation-ready but not proof of Play publication readiness.
