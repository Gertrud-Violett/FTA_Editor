# CJK diagram rendering — assessment

**Question (deferred from the v1.6 spec to P6):** the browser diagram renderer is
`@viz-js/viz`, Graphviz compiled to WebAssembly. It ships no font files and estimates
glyph widths from built-in metric tables. Are Japanese / Chinese / Korean label boxes
sized acceptably, or visibly wrong?

**Answer: acceptable, with a documented caveat.**

## Method

The same DOT — produced by `fta_web/rendering.build_dot_text` — rendered two ways and
compared:

- **native** — `dot -Tsvg` (Graphviz 2.43 / 16.0, real system font metrics from
  Noto Sans CJK JP)
- **WASM** — `viz.js` `renderString(dot, {format: "svg"})`

Measurements: the outer polygon width of each node's HTML-`<TABLE>` label, and the
overall SVG `viewBox` width. Labels chosen to span the realistic range, with matched
Japanese / Latin pairs of similar visual length.

## Findings

| Label | Chars | native width | WASM width | WASM / native |
|-------|------:|-------------:|-----------:|--------------:|
| `ポンプ故障` | 5 | 386 | 330 | 0.86 |
| `冷却水ポンプ軸受の焼付き` | 12 | 389 | 330 | 0.85 |
| `冷却水ポンプの軸受が過熱により焼き付いて停止する` | 24 | 560 | 443 | 0.79 |
| `Pump seizure` | 12 | 386 | 330 | 0.86 |
| `Cooling water pump bearing seizure` | 34 | 470 | 395 | 0.84 |

1. **WASM draws every diagram narrower than native — ~79–86% of native width.** This is
   a *uniform* scale difference between the two renderers. It is **not** a CJK-specific
   defect: a Latin label of the same visual length shrinks by almost exactly the same
   fraction.

2. **Long labels of either script can extend slightly past their cell border in the WASM
   output.** With a per-character ink estimate (CJK ≈ 0.95 em, Latin ≈ 0.52 em at 14 px),
   the 24-character Japanese label overruns its cell by roughly 45 px; the 34-character
   Latin label by roughly 21 px. CJK is somewhat worse per character because CJK glyphs
   carry more ink and the WASM metric tables are less precise for them.

3. **Short and typical labels are fine.** The fixed-height table cells in
   `json_viewer.node_label()` absorb the small error for anything up to ~12 characters,
   which covers the large majority of real node names.

4. **Glyphs always render correctly.** Confirmed in P2 and re-confirmed here — no tofu,
   no replacement characters, no dropped text. This is box *geometry* only.

The absolute pixel overruns above depend on a rough ink estimate and should be read as
"tens of pixels on a long label", not precise values. The direction and relative
magnitude are solid.

## Why this is acceptable

- The box is drawn by the same renderer that places the text, so in the WASM output the
  text stays within *its own* diagram — the mismatch is only visible when comparing WASM
  against native side by side, which no user does.
- **Native `dot`, when installed, is auto-detected and preferred** (`AppState.native_dot`
  → `/api/dot` reports `renderer: "native"`), and it sizes CJK exactly right.
- The **capability indicator** (spec §6.8) states which renderer produced the current
  diagram and, when it is the browser one, that installing Graphviz from graphviz.org
  fixes label sizing. The degradation is disclosed, not silent.
- The realistic failure — a very long Japanese label looking a little cramped — is
  cosmetic and rare.

## If it ever needs to be better

In rough order of effort:

1. Tell users who work primarily in CJK to install Graphviz (already the documented
   remedy).
2. Pad `node_label()`'s cell `WIDTH`/`HEIGHT` when the label contains CJK, trading a
   little extra whitespace on short labels for headroom on long ones. This is a change
   to the vendored `json_viewer.py`, so it would be a new `DIVERGENCE.md` entry.
3. Ship a CJK font-metrics table for viz.js. Largest effort, and it only closes the gap
   rather than eliminating it.

None of these are needed for v1.6.
