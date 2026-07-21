# Asset validation evidence

| Field | Value |
| :--- | :--- |
| Issue | E10-04 |
| Validation date | 2026-07-21 final screenshot pass |
| Git commit | See the final handoff commit containing this evidence file |
| Operator | Codex implementation run |

Run from the repository root and paste the complete output below:

```powershell
.\release\scripts\export-approved-artwork.ps1
.\release\scripts\validate-google-play-assets.ps1
```

Additional required commands and device checks are listed in `docs/e10-04-google-play-store-listing-runbook.md`.

## Result

`validate-google-play-assets.ps1` passes the approved source, store icon, feature graphic, all launcher resources, all splash resources, both locales' character limits, the eight-file screenshot count, file sizes, opaque pixel formats, 921 × 1842 dimensions, manifest filenames/order/hashes, and alt-text coverage. No duplicate or placeholder screenshot remains in the official directory.

| Graphic | Dimensions | Pixel format | Size | SHA-256 |
| :--- | :--- | :--- | ---: | :--- |
| `store-icon-512.png` | 512 × 512 | 32-bit ARGB | 497,249 bytes | `90766f0aaff4ba06ab12295cf18d61558bc933e5638a408d69f3c966c02adf24` |
| `feature-graphic-1024x500.png` | 1024 × 500 | 24-bit RGB, opaque | 957,167 bytes | `41976a1e60117feaa714b5f4297f25248206b864be9531dc39c00bbd5f104d89` |

The complete screenshot hashes are recorded in `sha256sums.txt` and `asset-manifest.json`. Play Console upload/preview and signed-candidate device checks remain operator-owned release steps.
