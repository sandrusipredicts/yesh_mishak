# Google Play listing package — E10-04

This directory is the source-controlled handoff package for the Yesh Mishak Google Play listing. It contains only the approved artwork, deterministic exports, listing copy, declaration worksheets, and evidence templates.

## Current status

| Deliverable | Status | Repository location |
| :--- | :--- | :--- |
| Approved visual source | Complete | `../brand/source/approved-artwork.png` |
| 512 × 512 store icon | Complete | `graphics/store-icon-512.png` |
| 1024 × 500 feature graphic | Complete | `graphics/feature-graphic-1024x500.png` |
| Android launcher resources | Complete; device verification pending | `../../frontend/android/app/src/main/res/mipmap-*` |
| Android splash resources | Complete; device verification pending | `../../frontend/android/app/src/main/res/drawable*` |
| Hebrew listing copy | Draft ready for owner approval | `metadata/he-IL/` |
| English listing copy | Draft ready for owner approval | `metadata/en-US/` |
| Approved phone screenshots | Complete; eight compliant Redmi captures | `graphics/screenshots/phone/he-IL/` |
| Privacy/Data safety alignment | Review required | `declarations/` |
| Play Console upload evidence | Pending manual upload | `evidence/` |

The official Hebrew phone set contains attachments 1–8 in the owner's supplied order. Each 921 × 2048 Redmi capture was deterministically cropped to 921 × 1842 by removing only 80 pixels of top system chrome and 126 pixels of bottom system chrome. No app UI was resized, generated, reconstructed, annotated, or overlaid. Attachment 9 is not included because Google Play permits at most eight phone screenshots and it is a near-duplicate of attachment 2's My Games screen.

## Rebuild and validate

From the repository root:

```powershell
.\release\scripts\export-approved-artwork.ps1
.\release\scripts\validate-google-play-assets.ps1
```

The export script must not be run with a different source file. The English listing inherits the compliant default Hebrew graphics rather than duplicating the same binaries.

## Manual release-owner actions

1. Confirm rights to publish the supplied artwork and approve the exact store icon, feature crop, launcher masks, and portrait/landscape splash crops.
2. Confirm the eight-file Hebrew display order in Play Console Preview and keep the English listing configured to inherit the default screenshot set.
3. Approve the Hebrew and English copy and confirm Hebrew (`he-IL`) as the default Play listing language.
4. Confirm category, countries/regions, pricing, ads declaration, target audience, content rating, and app-access answers in Play Console.
5. Resolve every open item in the Data safety and privacy alignment worksheets; legal/privacy owner approval is required.
6. Verify the public privacy URL and account-deletion instructions from a logged-out browser.
7. Build and install the signed release candidate; verify launcher icons, cold/warm splash behavior, RTL/LTR flows, screenshots, and listing-to-app consistency.
8. Upload assets and copy to Play Console, use Preview on phone and desktop, and record evidence before submitting for review.

See `docs/e10-04-google-play-store-listing-runbook.md` for the full operator procedure and acceptance criteria.
