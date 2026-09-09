# Divergence record — `fta_web/core/` vs. `src/`

`fta_web/core/` holds a **vendored fork** of four modules copied from `src/` at baseline
commit **`e5f655f`**. `src/`, `tests/` and `data/` are frozen and pinned by hash; the fork
is the copy that FTA Editor v1.6 owns and is allowed to patch.

**This file is the complete record of how `fta_web/core/` differs from `src/` at that
baseline. No undocumented divergence is permitted.** Every byte of difference between a
vendored module and its `src/` counterpart must be traceable to an entry below. File
hashes for both sides are recorded in [`BASELINE.json`](./BASELINE.json), whose
`divergences` array lists exactly the IDs that are applied here.

Applied divergences: **D1**, **D5**, **D7**, **D8**.
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
