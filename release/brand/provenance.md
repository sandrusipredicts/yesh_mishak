# Artwork provenance and transformation record

## Source of truth

| Field | Value |
| :--- | :--- |
| File | `release/brand/source/approved-artwork.png` |
| Supplied by | Project owner through the E10-04 Codex task |
| Approval statement | "This is the approved artwork. Use only this asset. Do not redesign it." |
| Date received | 2026-07-21 |
| Dimensions | 1254 × 1254 px |
| Encoding | PNG, 24-bit RGB, opaque |
| Size | 1,630,278 bytes |
| SHA-256 | `767DEDCA3FDF794FAF09ED8B6D73C65B7C03EBD3E0391FEEDBF05C01085B785E` |

The repository copy is byte-for-byte identical to the owner-supplied file at integration time.

## Allowed derived exports

- Google Play store icon: resize to 512 × 512 and convert to 32-bit PNG.
- Google Play feature graphic: centered 1024 × 500 cover crop and convert to opaque 24-bit PNG.
- Android launcher icons: square resize; the legacy round export adds only the required circular transparency mask.
- Android adaptive foregrounds: square resize of the approved artwork. The edge fallback color `#010232` is sampled from source pixel `(0,0)` and is not a new artwork element.
- Android splash resources: centered cover crop to each existing Capacitor density/orientation size.

No generative image output, mockup, fake UI, synthetic screenshot, text overlay, logo construction, or visual redesign is included in the final repository assets.

## Owner attestations still required

Before upload, the release owner must record that the project has the rights to publish the supplied artwork and that the generated crops are approved in `google-play/evidence/owner-approvals.md`.
