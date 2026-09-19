# Divergence record — `fta_web/core/` vs. `src/`

> **Path note.** When the web app became the primary path, the legacy desktop
> tree was moved from the repo root into `desktop/`: `src/` → `desktop/src/`,
> `tests/` → `desktop/tests/`, `data/` → `desktop/data/`. Contents and hashes
> are unchanged; `BASELINE.json` and `test_vendor_integrity.py` were updated
> to the new paths. Every `src/` reference below means `desktop/src/`.

`fta_web/core/` holds a **vendored fork** of four modules copied from `src/` at baseline
commit **`e5f655f`**. `src/`, `tests/` and `data/` are frozen and pinned by hash; the fork
is the copy that FTA Editor v1.6 owns and is allowed to patch.

**This file is the complete record of how `fta_web/core/` differs from `src/` at that
baseline. No undocumented divergence is permitted.** Every byte of difference between a
vendored module and its `src/` counterpart must be traceable to an entry below. File
hashes for both sides are recorded in [`BASELINE.json`](./BASELINE.json), whose
`divergences` array lists exactly the IDs that are applied here.

Applied divergences: **D1**, **D5**, **D7**, **D8**, **D9**, **D11**, **D12**, **D13**,
**D14**, **D15**, **D16**, **D17**, **D18**, **D19**, **D20**.
Investigated and **not** applied: **D3** (see the closing section — it is recorded so the
question is not re-opened, but it is deliberately absent from `BASELINE.json`).

---

## D1 — Dead `_get_client()` method raises `AttributeError`

**Defect:** `AIAgentHandler._get_client()` (baseline `src/AI_agent_handler.py` lines
365–382) lazily built an `openai.OpenAI` client cached on `self._client`. `__init__` never
assigns `_client`, so the very first `if self._client is not None:` raised
`AttributeError: 'AIAgentHandler' object has no attribute '_client'`. The method was left
over from before the provider abstraction landed; the live path is `_get_provider()`,
which caches on `self.provider` and is initialised correctly. A repo-wide grep confirmed
`_get_client` had exactly one occurrence — its own `def` — and zero call sites.

**Fix:** Deleted the method in full. No replacement; `_get_provider()` already covers the
behaviour for every supported provider.

**Behavior change:** None observable. The method was unreachable from any code path and
could only ever raise.

**Files:** `fta_web/core/AI_agent_handler.py`

---

## D5 — `NOT` logic gates were accepted by validation but computed as `OR`

**Defect:** The AI validator accepted `logicGate: "NOT"`, but
`FTACore._recalculate_fta_probabilities` (`src/FTA_Editor_core.py` lines 176–185)
branches only on `gate == "AND"` and falls through to the OR union formula for everything
else:

```python
if gate == "AND":
    base = round(self._product(child_probs), 6)
else:
    # OR gate: union formula (default)
    base = round(1 - self._product([1 - p for p in child_probs]), 6)
```

A `NOT` gate therefore silently produced an **OR probability** — a wrong number with no
error, no warning, and nothing in the UI to indicate the gate had been ignored. Baseline
`src/AI_agent_handler.py` admitted `"NOT"` at four places: line 596
(`_parse_proposed_changes`), line 655 (`_validate_node_data`), line 761
(`apply_change_to_fta`'s edit path) and line 986 (`verify_updated_fta_json`). The schema
docstring (line 263) and the system prompt additionally advertised `NOT` to the model as a
valid value, so the AI was actively encouraged to emit it.

**Fix:** Reject `NOT` at validation rather than implement `1 - p` semantics — that was an
explicit product decision, so the probability engine in `FTA_Editor_core.py` is
**unchanged** by this entry.

- All four acceptance lists narrowed from `['AND', 'OR', 'NOT']` to `['AND', 'OR']` (and
  `["", "AND", "OR", "NOT"]` to `["", "AND", "OR"]` in `verify_updated_fta_json`). Note the
  fourth site, `apply_change_to_fta` line 761, was not in the original defect report but was
  found by grep; leaving it would have let a `NOT` through the edit path.
- `_validate_node_data` and `verify_updated_fta_json` return a dedicated message for `NOT`
  that **names the offending node** and states why it is refused, e.g.
  `NOT gates are not supported (node gate_3): the probability engine has no NOT semantics. Use 'AND' or 'OR'.`
  Both also name the node in their generic invalid-gate message, which the baseline did not.
- `FTA_JSON_SCHEMA` now documents `"AND|OR"` and rule 5 spells out that `NOT` is rejected.
- `SYSTEM_PROMPT` gained an explicit rule so the model is never told `NOT` is valid.

**Behavior change:** A tree containing `logicGate: "NOT"` is now **rejected with a clear
error naming the node** instead of being accepted and scored as an OR gate. Any workflow
that previously relied on the silent OR fallback will now surface an error — which is the
point of the fix. `AND` and `OR` are unaffected. Because the two silent-skip sites
(`_parse_proposed_changes`, `apply_change_to_fta`) already used `continue`, a `NOT` there is
now dropped rather than applied.

**Files:** `fta_web/core/AI_agent_handler.py`

---

## D7 — Move cycle-check asked the question backwards

**Defect:** `AIAgentHandler._would_create_circular_reference()` (baseline
`src/AI_agent_handler.py` lines 827-833) delegated to
`_is_descendant_of(core, node_id, potential_parent_id)`, which asks *"is the node being
moved already inside the target parent's subtree?"* That is the inverse of the question a
move guard has to ask. A cycle is created when the **new parent is a descendant of the
node being moved**, not the other way round.

Verified against the unmodified baseline — wrong in every case tested:

| Move | Should be | Baseline said |
|------|-----------|---------------|
| grandchild → root (legal promotion) | allow | **reject** |
| child → its current parent (reorder) | allow | **reject** |
| parent → its own child | **reject** | allow |
| parent → its own grandchild | **reject** | allow |

So it rejected every legal move and permitted every genuinely corrupting one. The
permitted case is the damaging half: `apply_change_to_fta`'s move branch detaches the node
via `_remove_node_from_parent` and then appends it to a parent that lives inside the
subtree just detached, producing a self-referential structure orphaned from the tree.

**Fix:** Swapped the argument order to `_is_descendant_of(core, potential_parent_id,
node_id)`. Also replaced the `core._find_node_by_id_recursive(...) and ...` expression
with an explicit `find_node_by_id(...) is None` guard, so the function returns a real
`bool` rather than leaking a node dict as a truthy value, and uses the public finder
instead of the private one.

**Behavior change:** Only reachable through `apply_change_to_fta`'s `move` branch, which
nothing calls today — `fta_web` implements its own `tree_ops.move_node` with the correct
direction, and the desktop app never wired this path up. Fixed now rather than in P4
because it is verified, the fork owns the file, and a latent tree-corrupting bug should
not wait four phases on someone remembering it.

**Files:** `fta_web/core/AI_agent_handler.py`

---

## D8 — Minified JSON was mangled, then blamed on the file's encoding

**Defect:** `FTACore.load_from_json` (baseline `src/FTA_Editor_core.py` lines 289-301)
applied a double-wrap repair *unconditionally*, before attempting to parse:

```python
if content.startswith("{{"): content = "{" + content[2:]
if content.endswith("}}"):  content = content[:-1]
loaded_data = json.loads(content)
```

The `endswith("}}")` test matches **every minified analysis** — the tree's closing brace
immediately followed by the document's. Stripping one brace turned a perfectly valid file
into invalid JSON. Worse, the resulting `JSONDecodeError` was caught by the
encoding-retry loop, so the user was told:

> Failed to read file with common encodings

which names the wrong cause entirely. The file was fine and the encoding was fine; the
loader broke it. Files this editor writes use `indent=2` and never end in `}}`, so the bug
only bit documents minified by another tool — exactly the interchange case a file format
exists to support.

**Fix:** Parse the document as written first; fall back to the repair only when that
fails. Verified across five shapes — app-written `indent=2`, minified, legacy
double-wrapped, legacy bare minified tree, and genuinely malformed:

| Input | Before | After |
|---|---|---|
| `indent=2` (app-written) | loads | loads |
| minified | **fails** | loads |
| legacy double-wrapped | loads | loads |
| legacy bare tree, minified | **fails** | loads |
| genuinely malformed | rejected | rejected |

**Behavior change:** Minified documents now open instead of being rejected with a
misleading message. Nothing that loaded before stops loading — the legacy repair is still
reachable, just no longer applied to files that never needed it.

**Files:** `fta_web/core/FTA_Editor_core.py`

---

## D9 — Anthropic fallback model list had aged out

**Defect:** `AnthropicProvider.get_default_models()` (baseline
`src/ai_providers.py` line 125) returned the Claude 3 family:
`claude-3-5-sonnet-20241022`, `claude-3-opus-20240229`, `claude-3-sonnet-20240229`,
`claude-3-haiku-20240307`.

This list is the **fallback** used when the live model fetch fails — offline, behind a
proxy, or with a key that cannot list models. That is precisely when a stale entry does
the most damage: the user cannot discover the real model names, accepts the pre-selected
first item, and gets an API error with no obvious cause. A wrong default in the
*degraded* path is worse than a wrong default in the healthy one.

**Fix:** Refreshed to the current family, most-capable first since the settings dialog
pre-selects the leading entry:

```
claude-opus-5, claude-sonnet-5, claude-haiku-4-5, claude-opus-4-8, claude-sonnet-4-6
```

Structural mitigation alongside the data change: the settings dialog's model field is an
**editable** combo rather than a closed dropdown, and the live fetch is always preferred
over this list. A model released after this list was written can be typed in, so the
fallback ageing again degrades gracefully instead of blocking the user.

The OpenAI and Gemini lists are deliberately **not** touched — no equally authoritative
source was available for them, and their leading entries are not known to be retired.
Editability covers them too.

**Behavior change:** The Anthropic model dropdown offers current models when the live
fetch is unavailable. No API call shape changed; `AnthropicProvider.send_message` and
`test_connection` are untouched.

**Files:** `fta_web/core/ai_providers.py`

---

## D11 — Migrated `GeminiProvider` off the end-of-life `google.generativeai` SDK

**Defect:** `GeminiProvider` (baseline `src/ai_providers.py`, class starting line 197) is
built on `google.generativeai`, which Google has ended support for: "All support for the
`google.generativeai` package has ended... switch to the `google.genai` package." Beyond
the deprecation itself, the package is a **PEP 420 namespace package** under `google`,
and PyInstaller's `hiddenimports` silently fails to collect it: the frozen build reported
Gemini "bundled" while the import raised at runtime (`build/README.md`'s former "Known
limitation: Gemini in a frozen build" section documented this). `google.generativeai`
also drags in the ~100 MB `google-api-python-client`/grpc dependency chain for
functionality this app never uses.

**Fix:** Rewrote `GeminiProvider` against `google.genai`, the SDK's unified successor:

- `genai.Client(api_key=...)` replaces the old `genai.configure()` + `GenerativeModel(...)`
  pair.
- `client.models.list()` replaces `genai.list_models()`; each model's `supported_actions`
  field (the REST action names, e.g. `"generateContent"`) replaces the old
  `supported_generation_methods` field — same filter, new field name, verified against the
  installed SDK rather than assumed.
- `client.models.generate_content(model=..., contents=...)` replaces
  `GenerativeModel.generate_content()` for the one-shot connection test.
- `client.chats.create(model=..., config=..., history=...)` plus `Chat.send_message()`
  replaces `GenerativeModel.start_chat(history=...)` plus `ChatSession.send_message()`.
  History entries are `{"role": ..., "parts": [{"text": ...}]}` dicts, matching
  `google.genai.types.ContentDict`/`PartDict`; the *final* turn is sent to
  `send_message()` as a plain string rather than replayed into history, because passing a
  single-element `PartDict` list there raises `"Message must be a valid part type"` — `str`
  is a first-class member of the accepted `Union`, a one-element list-of-dict is not.
- `types.GenerateContentConfig(system_instruction=..., max_output_tokens=...)` replaces
  the constructor kwargs `GenerativeModel(system_instruction=...)` and the per-call
  `generation_config={"max_output_tokens": ...}`.
- `response.text` is unchanged in shape from the old SDK.

`get_default_endpoint()`, `get_default_models()` (already refreshed by D9's sibling
reasoning — see that entry) and the `except ImportError` fallback strings are otherwise
unchanged in intent; only the import path and error text now name `google-genai`.

Because `google.genai` lives under the same `google` namespace-package structure that
broke `hiddenimports` for the old SDK, `build/fta_editor.spec`'s `collect_all()` workaround
now targets `google.genai` and `google.auth` (the latter discovered as a real transitive
import by inspecting `sys.modules` after `import google.genai`, not assumed from the
package name) instead of `google.generativeai` and `google.ai.generativelanguage`.
`fta_web/state.py`'s `_probe_provider_sdks()` real-imports the SDK rather than using
`find_spec` for exactly the reason D9's sibling defect in this file exists elsewhere in
the project: `find_spec` reported the old package "present" in a frozen build while the
import itself raised, and a capability indicator that lies is worse than none.

**Behavior change:** None visible to a working integration — `test_connection` and
`send_message` still return the same `(bool, str)` / `(Optional[str], Optional[str])`
shapes. A frozen build's Gemini provider, previously non-functional
(`"Google Generative AI package not installed"` regardless of key validity), now reaches
the real API. `pyproject.toml`'s `ai` extra now installs `google-genai` instead of
`google-generativeai`; the `desktop` extra gained `google-generativeai` explicitly, since
`src/ai_providers.py` is frozen and still needs the old package — the two apps now
genuinely require different SDKs for the same provider.

**Files:** `fta_web/core/ai_providers.py`, `fta_web/state.py`, `build/fta_editor.spec`,
`pyproject.toml`, `requirements.txt`, `fta_web/requirements.txt`,
`fta_web/tests/test_api_render.py`

---

## D12 — Diagram node boxes: configurable font, box padding and dark theme in `build_dot`

**Defect:** Baseline `src/json_viewer.py` hard-codes `fontname="Noto Sans CJK JP"` and lets
Graphviz auto-fit each node's HTML-like label cell from its own internal width estimate
for that font. In the browser (viz-js/WASM) the text is then painted by whatever font the
browser actually resolves that name to, and the two rarely agree, so labels spilled past
the box border — differently for the 14 pt name row and the 9 pt gate/probability row,
which is why either row could overflow depending on which text was longer. There was
also no way to render the diagram on a dark background: the page background polygon and
the connector colour were fixed white/black.

**Fix:** `build_dot(nodes, edges, font_name=..., scale=..., dark=...)` and
`node_label(node, font_size, small_font_size, cellpadding, pad_spaces)` grew keyword
arguments, all defaulted so the CLI in `main()` is unaffected:

- `font_name` is interpolated into the graph's `node [...]`/`edge [...]` `fontname`
  attributes. It is **not** sanitised here — `fta_web/rendering.py::sanitize_font_name`
  whitelists it at the boundary, and the CLI passes a literal.
- `scale` is a count of trailing blank characters appended to both text rows of every
  node, inside the same `<FONT>` run as the visible text. A computed pixel/point width was
  tried twice and still overflowed, because it depended on guessing how wide the text
  renders in a font chosen by someone else; padding characters are measured by the same
  engine at the same size, so whatever its error is applies equally to the padding.
  `CELLPADDING="6"` and explicit minimum row `HEIGHT`s were added at the same time.
- `dark` sets `bgcolor="#1b1f23"` on the graph and colours tree edges (and therefore
  their arrowheads) white instead of black. Link edges stay blue in both themes so they
  remain distinguishable; node box fills are untouched because their pastel colours and
  black text are legible on either background.

**Behavior change:** With defaults (`scale=4`) every node box is slightly wider than at
baseline; `fontname` defaults to the baseline's `"Noto Sans CJK JP"` inside this module
(`rendering.py` supplies `"Meiryo"` for the web app). Nothing about node ordering, edge
routing, colours-by-probability or `hide_zero` changed. Landed in PR #8 without this entry
and without re-pinning; both were added afterwards, which is why `vendored_at` is
unchanged.

**Files:** `fta_web/core/json_viewer.py` (plus the consuming `fta_web/rendering.py`,
`fta_web/routes/render.py`, `fta_web/static/js/diagram.js`)

---

## D13 — Node names were interpolated raw into the Graphviz HTML-like label

**Defect:** `node_label()` (baseline `src/json_viewer.py` lines 19-42) built the node box
as a Graphviz HTML-like label — which is XML — and interpolated `name`, the gate text and
the probability strings into it unescaped. A name such as `Pressure > 5 bar & T < 50`
produced a DOT document that neither a native `dot` nor viz.js would parse: every node
vanished, the web panel showed "Could not render" and `/api/render` returned 503. Worse,
a name containing markup (`x</FONT></TD></TR><TR><TD HREF="javascript:…">`) survived into
the SVG that `diagram.js` imports into the page, i.e. a hostile `.json` could run script
in the app origin (review items B-1, F-2, F-3, D-H2). A `None` name also rendered as the
literal `None`, and a non-string name would have raised in a later f-string.

**Fix:** `name` and the gate text are passed through `html.escape(str(...), quote=False)`
before being placed in the label; a `None` name falls back to the id. Quotes are left
alone: they are harmless in XML text content and keep the DOT readable.

**Behavior change:** Names with `<`, `>` or `&` now render (as the characters the user
typed) instead of blanking the diagram; markup in a name is displayed as text, never
interpreted. Names without those characters produce byte-identical output.

**Files:** `fta_web/core/json_viewer.py`

---

## D14 — Engine rounding to six decimals flushed small probabilities to zero

**Defect:** `_recalculate_fta_probabilities` (baseline `src/FTA_Editor_core.py` lines
183, 186, 206, 211) applied `round(..., 6)` after the gate, after AND-links and after
OR-links, and `_recalculate_eta_probabilities` (line 234) after every multiplication.
Any value below 5e-7 became 0.0: `AND(1e-3, 1e-4)` → 0.0 instead of 1e-7,
`OR(3e-7, 4e-7)` → 1e-6 instead of 7e-7, ETA `1e-3 × 1e-4` → 0.0. The node was then
listed by `get_zero_probability_nodes()`, painted as a zero node, dropped by Hide Zero
with its subtree, fed 0 into every AND gate above it and exported as 0. Component failure
rates of 1e-6…1e-9/h are the normal working range in reliability engineering, so this was
wrong arithmetic in the common case with no warning (review item B-2 / D-C1).

**Fix:** All five `round(..., 6)` calls replaced by a module-level `_tidy(x)` that returns
`float(f"{x:.12g}")` — twelve *significant* digits, which trims binary float noise
(`0.30000000000000004` → `0.3`, so the existing expectations such as `0.7` and `0.64`
still hold exactly) without ever flushing a small value to zero. Nothing in the engine
rounds to a fixed number of decimals any more; display formatting is the caller's job.

**Behavior change:** Probabilities below 5e-7 are now computed and reported; nothing that
was non-zero before changes by more than the discarded rounding error. A file saved by
the baseline with a rounded `calculatedProbability` is recomputed on load and may show a
non-zero value where it previously showed 0.
`fta_web/tests/core/test_probability_calculation.py`, which re-implements the formula, was
updated to the unrounded arithmetic and its equality assertions wrapped in `approx`
(likewise `test_core_module.py`). New regression tests live in
`fta_web/tests/test_core_fixes.py`.

**Files:** `fta_web/core/FTA_Editor_core.py`

---

## D15 — Duplicate node ids aliased each other's results and were never reported

**Defect:** `load_from_json` never checked id uniqueness, and the recalculation memo was
keyed by `node["id"]` (baseline `src/FTA_Editor_core.py` lines 156-167, 213). With two
children `e1` (0.1) and `e1` (0.9) the memo returned the first node's value for the second,
never wrote the second's `calculatedProbability`, and the root came out 0.19 instead of
0.91. `delete_node_from_data` and `move_node` then act on every node carrying the id
(review item B-4; D-C5 is the desktop symptom).

**Fix:** Two independent measures.

- The memo, the `visiting` set and the new children-only cache (see D17) are keyed by
  `id(node)` — object identity — so two dicts that share an id can never alias.
- `load_from_json` runs a new `_dedupe_node_ids()` pass after `_normalize_node()`: every
  later occurrence of an id already seen is renamed `<id>_dup2`, `<id>_dup3`, … (checked
  against every id in the file so a generated name cannot itself collide). Links are
  left pointing at the first occurrence, which is the node `find_node_by_id` always
  resolved them to. Each rename is appended to the new `FTACore.last_load_warnings` list
  as `{"kind": "duplicate_id", "old_id", "new_id", "name", "message"}` so a caller can
  tell the user what was repaired. The attribute is initialised to `[]` in `__init__` and
  reset on every load.

**Behavior change:** A file with repeated ids now loads with unique ids and correct
arithmetic; the renames are visible on `last_load_warnings`. Files without duplicates are
untouched and produce an empty list. `set_data()` does not dedupe (it is the undo/redo
path and receives trees this core produced), but the identity-keyed memo protects the
arithmetic there as well.

**Files:** `fta_web/core/FTA_Editor_core.py`

---

## D16 — Top-level node id was not canonicalised to `"root"` on load

**Defect:** `_normalize_node` (baseline `src/FTA_Editor_core.py` line 362) invented
`root_0` for a top-level node without an id and kept whatever id (`TOP`, `1`, …) the file
carried otherwise, while every consumer — the web `ROOT_ID` guards, the desktop Treeview,
`add_node_to_data('root', …)` — hard-codes the literal `"root"`. Web: the root could be
"deleted" (a no-op that still dirtied the document) and every AI update was refused.
Desktop: Add Node put the row in the Treeview but never in the data (review item B-8 /
D-C2).

**Fix:** A module constant `ROOT_ID = "root"` and a `_canonicalize_root_id()` pass, run in
`load_from_json` immediately after normalisation and *before* the duplicate check (so a
child that already used `root` is the one renamed to `root_dup2`, never the top). The
top-level id is set to `ROOT_ID` whatever it was, every `links[].target_id` equal to the
old id anywhere in the tree is rewritten, and the change is recorded on
`last_load_warnings` as `{"kind": "root_id", "old_id", "new_id", "message"}`.

**Behavior change:** After a load, `get_data()["id"]` is always `"root"`. Files whose top
event had another id load with the id changed and links intact; saving writes `"root"`.

**Files:** `fta_web/core/FTA_Editor_core.py`

---

## D17 — A link cycle saturated every node on it to 1.0

**Defect:** On re-entry through a link the engine (baseline `src/FTA_Editor_core.py`
lines 163-167) returned the node's *base* `probability`. For a gate node that value is
ignored by the gate and defaults to 1.0, so `G(OR, child 0.01) ↔ B(0.02)` linked both ways
gave G = B = root = 1.0. `routes/tree.py` documents cyclic links as legal (review item
B-5).

**Fix:** The gate result is computed from the children first (it already was) and cached
in a `gate_only` dict for as long as the node is on the stack. A re-entry now returns, in
order: the node's memoised result if the pass already finished it; else its
children-only gate value; else, for a leaf, its own `probability` (a self-link on a leaf
behaves as before); else `None`, which the caller treats as an unresolvable link and
skips. The last case is a descendant linking to an ancestor whose children are still
being evaluated — there is no meaningful number for it yet, and skipping is strictly
better than the ancestor's ignored 1.0. Children that resolve to `None` are likewise
left out of the gate product.

**Behavior change:** With the example above, B = OR(0.02, 0.01), G = OR(0.01, B), and the
root is below 1.0. Trees without cycles are unaffected; a leaf self-link still yields the
same value it did.

**Files:** `fta_web/core/FTA_Editor_core.py`

---

## D18 — `set_metadata()` reset the date whenever it was called without one

**Defect:** `set_metadata(title=…)` or `set_metadata(mode=…)` without a `date` (baseline
`src/FTA_Editor_core.py` lines 70-74) overwrote `self.date` with today. The desktop UI
calls it on every Title focus-out and mode change without refreshing its date field, so
screen and saved file disagreed; the web app worked around it by always sending all
three fields (review item D-H1).

**Fix:** The `else` branch was removed. Only fields that are passed are changed.

**Behavior change:** The date is now only ever what the user or the file set it to.
`fta_web/routes/tree.py`'s `/metadata` handler sends all three fields and is unaffected
(its comment describing the old behaviour is now stale; that file belongs to another
package).

**Files:** `fta_web/core/FTA_Editor_core.py`

---

## D19 — `sanitize_id()` collapsed distinct ids into one DOT node

**Defect:** `sanitize_id` (baseline `src/json_viewer.py` line 17) mapped every character
outside `[0-9A-Za-z_]` to `_`, so `a.b` and `a b`, or two Japanese ids of the same
length, became the same DOT identifier: one box in the diagram and edges cross-wired
between them (review item D-H3).

**Fix:** If the id contained any replaced character, `_` plus the first eight hex digits of
`sha1(original id, UTF-8)` is appended to the replaced form. Ids that are already plain
ASCII words (everything this editor generates: `root`, `root_1_2`, …) are returned
unchanged. The algorithm, for the frontend mirror in `fta_web/static/js/diagram.js`
`sanitizeId()`:

```
safe = id.replace(/[^0-9A-Za-z_]/g, "_")
return safe === id ? safe : safe + "_" + hex(sha1(utf8(id))).slice(0, 8)
```

**Behavior change:** Diagrams whose ids are all ASCII words are byte-identical. Ids with
punctuation or non-ASCII characters now get distinct DOT names; the `<title>` of their SVG
group changes accordingly, so click-to-select on those nodes needs the JS mirror updated
(its `buildIdMap` already tolerates unmapped ids, so nothing breaks in the meantime).

**Files:** `fta_web/core/json_viewer.py`

---

## D20 — Credentials file was written with default permissions

**Defect:** `AICredentialManager` (baseline `src/AI_agent_handler.py` lines 31-58) created
`~/.fta_editor/` with the umask default and wrote `ai_credentials.json` — which holds an
API key in clear — through a plain `open(..., 'w')`, i.e. typically world-readable on a
shared POSIX machine (review item B-10).

**Fix:** The directory is created with `mode=0o700` (and `chmod`ed to it if it already
exists); the file is opened via `os.open(path, O_WRONLY|O_CREAT|O_TRUNC, 0o600)` and
`chmod`ed to `0o600` afterwards so an existing looser file is tightened too. Both `chmod`s
swallow `OSError`, so on Windows — where the mode bits are a no-op and the home
directory's ACL is the protection — nothing changes and nothing fails.

**Behavior change:** None functional; the file's content and location are unchanged.

**Files:** `fta_web/core/AI_agent_handler.py`

---

## D3 — Excel sibling row overwrite: investigated, NOT reproduced, no patch applied

**Reported defect:** `FTACore.export_to_excel()`'s inner `write_node()`
(`src/FTA_Editor_core.py` lines 453–581) was reported to advance `current_row` by one per
sibling regardless of how many rows the previous sibling's subtree consumed, so deep
sibling subtrees would overwrite each other's rows.

**Finding: the defect does not exist.** The report misreads the control flow. `current_row`
is declared `nonlocal`, so **every** recursive invocation of `write_node` shares one cell —
it is a monotonic high-water mark, not a per-level counter. The `if i > 0: current_row += 1`
advance therefore starts from the last row consumed by the *previous sibling's entire
subtree*, not from the previous sibling's own row. The invariant
`row == current_row` holds on entry to every call, and on return `current_row` equals the
last row the subtree occupied. Subtree height is accounted for implicitly.

Verified empirically against the real (unmodified) code:

- The exact scenario in the report — two sibling branches, the first with grandchildren —
  lays out correctly; the second branch starts *below* the first branch's subtree:

  ```
  row 1: ROOT | S1 | S1a  | S1a1
  row 2:      |    |      | S1a2
  row 3:      |    | S1b  | S1b1
  row 4:      | S2 | S2a  |
  ```

- 600 random trees (depth ≤ 5, 0–3 children per node): 0 lost nodes, 0 cell-count mismatches.
- **Exhaustive**: all 626 rooted ordered tree shapes of 1–8 nodes (depths up to 8). For every
  one, the number of non-empty cells equalled the node count and every `(name, depth+1)`
  pair appeared in its expected column. Zero failures.

**Fix:** None. Patching `export_to_excel` would add a permanent, behaviour-neutral diff
against upstream — making future re-vendoring harder — while fixing nothing. The fork's
charter allows patches only for real defects, so no change was made and `FTA_Editor_core.py`
remains **byte-identical to `src/FTA_Editor_core.py`** (sha256
`51ce55d9…2e2ff2` on both sides in `BASELINE.json`).

The layout is nonetheless pinned by regression tests in
`fta_web/tests/test_divergence_fixes.py` so that any future refactor of `write_node` — which
is fragile in the sense that its correctness rests on a non-obvious shared-mutable
invariant, and carries a dead `child_start_row` local plus a `row` parameter that is always
equal to `current_row` — cannot silently introduce the bug that was reported here.

**Behavior change:** None.

**Files:** none (no divergence).
