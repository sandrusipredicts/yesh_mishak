# Approved brand source

`source/approved-artwork.png` is the sole approved visual source for E10-04.

Permitted transformations for this issue are limited to deterministic resizing, center-cropping, Android launcher masking, and pixel-format conversion. Do not add text, logos, overlays, effects, replacement backgrounds, synthetic UI, or generated visual content.

Rebuild all derived graphics from the repository root with:

```powershell
.\release\scripts\export-approved-artwork.ps1
```

If the source is changed, obtain explicit owner approval and update `provenance.md`, `google-play/asset-manifest.json`, and the recorded hashes before exporting again.
