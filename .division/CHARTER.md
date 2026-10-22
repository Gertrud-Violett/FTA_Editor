# Charter: FTA Editor

- Project: `fta-editor` · Domain: me-tool · Base branch: `main`
- Assigned by Katey (CEO) on 2026-10-22 · Budget cap: $300 (API-equivalent usage)
- Organization: NHI engineering division (CEO → Director → PM → feature teams)
- Size: L (M: up to two researchers, one critic round; L: full process)

## Brief from the CEO (verbatim, never edited)

Asked by the Director (setup question Q5): "What should the division build or do next for FTA Editor? (What, for whom, done when, constraints.)"

The CEO chose: **Release 1.8.1, then roadmap**: "Ship the merged fixes as 1.8.1, then plan the next features from docs/ROADMAP_MECHANICAL_ENGINEERS.md"

Earlier the same day the CEO wrote: "Proceed with division setup. If version PR is blocking it merge it first"

## Goals and success measures

_The Director fills this in during the spec: three to five measurable outcomes._

## Constraints

- Existing product: FTA Editor v1.8.0 is released (GitHub `Gertrud-Violett/FTA_Editor`, public). `main` also holds the merged known-issue fixes (PR #26), not yet released: they become 1.8.1.
- `fta_web/core/*.py` is hash-pinned (BASELINE.json, DIVERGENCE.md) and `desktop/` is frozen: new behaviour goes in `fta_web/` beside the core.
- The sandbox root is a security boundary; the server stays loopback-only with token, Origin and Host checks.
- No live AI provider call in tests; a live call uses the CEO's stored key and needs the CEO's approval.
- Releases: the Windows exe is built outside Dropbox, tested with the full GUI suite against the exe, then released with notes and a SHA-256. Releasing is a CEO gate.
- en and ja strings for every user-visible text.
- Windows PC in Dropbox: `uv run --frozen` always; Dropbox can lock git files.

## CEO gates (nothing passes these without the CEO)

- Spec approval: freezes the UI, function and performance requirements.
- Any change to an approved UI, function or performance requirement (a change request).
- Budget beyond the cap; publishing, releasing or anything irreversible.
- Delivery acceptance. The CEO merges into `main`; the division never does.
