# API Reference

**Version**: 1.9.0 | **Updated**: November 5, 2026

Complete API documentation for programmatic use of FTA/ETA Editor.

## Overview

This document covers:
- **The web app's HTTP API, 1.7 to 1.9**: [below](#http-api-17-to-19).
  The 1.6 endpoints are specified in [V1.6_WEB_SPEC.md §5](V1.6_WEB_SPEC.md#5-http-api).
- **The CCF groups API (1.9)**: [below](#ccf-groups-api-19).
- **The 1.7 Python analysis modules** (`WebCore`, cut sets, importance,
  uncertainty, lint): [below](#python-analysis-modules-17).
- **FTACore**: Core business logic for FTA/ETA operations
- **AIAgentHandler**: AI assistant integration (new in v1.5)
- **FTAStructureAnalyzer**: FTA data conversion utilities

---

## HTTP API (1.7 to 1.9)

Every endpoint is under `/api` and needs the launch token (the `X-FTA-Token`
header). Every endpoint returns the 1.6 envelope:

```json
{"ok": true, "...payload keys": "..."}
{"ok": false, "error": {"code": "INVALID_FIELD", "message": "...", "detail": {"field": "..."}}}
```

`message` is localised to the request language. `detail` is omitted when it
is empty.

### Document additions

**New node keys.** All of them are optional; a node without them behaves as
in 1.6. The vocabulary and validators are in `fta_web/node_schema.py`, and
`static/js/schema.js` mirrors them.

| Key | Type | Values |
|---|---|---|
| `gateType` | string | `AND`, `OR`, `KOFN`, `XOR`, `INHIBIT`, `PAND`, `TRANSFER` (case-insensitive on input, stored upper-case) |
| `k` | integer ≥ 1 | vote threshold for `KOFN` |
| `transferTo` | string | target node id for `TRANSFER` (same document). A dangling id is a lint issue, not a 400. |
| `eventKind` | string | `basic`, `house`, `undeveloped`, `conditioning` |
| `houseState` | boolean | ON/OFF of a house event |
| `quant` | object | `{model: fixed\|rate\|standby\|repairable, lambda, T, tau, mu, mttr, source, unc: {dist: none\|lognormal, median, mean, ef}}` |
| `trace` | object | `{requirementId, testRef, owner, status: draft\|reviewed\|approved, evidence, tags: [string]}` |
| `fmea` | object | `{id, item, mode, cause, severity, occurrence, detection, rpn, source}` |

Units and ranges:

- `lambda` and `mu` are per hour and ≥ 0.
- `T`, `tau` and `mttr` are hours and > 0.
- `unc.median` and `unc.mean` are > 0. `unc.ef` is ≥ 1.
- `severity`, `occurrence` and `detection` are integers 1–10. `rpn` is an
  integer ≥ 0.
- Strings are at most 4,000 characters. `tags` holds at most 64 entries; each
  is trimmed, cut to 200 characters and de-duplicated.
- No stored text (a name, type, notes, link target, the title or date, a
  1.7 string) may hold an unpaired surrogate, which can never be saved:
  `400 INVALID_FIELD` naming the field.
- Unknown sub-keys are a 400 whose `detail.fields` lists them.

`logicGate` stays AND/OR, and it is always the projection of `gateType`:

- INHIBIT and PAND project to AND.
- KOFN, XOR and TRANSFER project to OR.

When a loaded file (or an AI update) has a `gateType` that does not project
to its `logicGate` (the 1.6 desktop app edits only `logicGate`), `logicGate`
wins: `gateType`, `k` and `transferTo` are removed from that node and a
`LOAD_REPAIR` session warning is recorded with `kind: "gate_type_reset"` and
`params` `{old_id, new_id, name, gateType, logicGate, dropped, cause, message}`.
This applies only when `logicGate` is AND or OR, the values the desktop app
writes; any other `logicGate` beside a `gateType` is set to its projection,
without a notice.

Without a `gateType`, `logicGate` is read as in 1.6: AND, and anything else
OR. An advanced gate name there (`KOFN`, `XOR`, `INHIBIT`, `PAND`,
`TRANSFER`, any case) is *promoted*: `gateType` becomes that gate,
`logicGate` its projection, and a `LOAD_REPAIR` warning with
`kind: "gate_type_promoted"` (`params` `{old_id, new_id, name, gateType,
logicGate, cause, message}`) is recorded.

`cause` is `"desktop"` for a loaded file and `"ai"` for an AI edit
(`POST /api/ai/update`, `POST /api/ai/changes/apply`), and the message says
which. A notice with `cause: "ai"` belongs to that edit: undoing the AI update
removes it and redo brings it back.

Loading a file also repairs, each with a `LOAD_REPAIR` warning:

- a repeated link (same target, same relation), which the engine counted
  twice: dropped (`kind: "duplicate_link"`, `params` `{targetId, relation}`);
- text that cannot be saved (an unpaired surrogate) in a node, the title or
  the date: replaced with U+FFFD (`kind: "invalid_text"`, `params.fields`
  lists the dotted keys).

A loaded `mode` is stored as `FTA` or `ETA`: `"eta"` in any case or spacing
is `ETA`, anything else `FTA`.

`probability` is overwritten with the derived value on every recalculation
for `quant` models other than `fixed`, for house leaves (1.0 when
`houseState` is true, else 0.0) and for `TRANSFER` nodes (the target's
calculated value; 0.0 when the target is missing or cyclic). The 1.6 desktop
app reads `probability`, so it shows the same values. It still computes a
`TRANSFER` node that has children from those children.

**Document block `analysis`**, saved beside `tree`:

```json
"analysis": {
  "missionTime": 8760.0,
  "timeUnit": "h",
  "cutsets": {"maxOrder": 6, "maxCount": 5000, "cutoff": 1e-15},
  "mc": {"n": 10000, "seed": null},
  "fmeaOccurrenceTable": {"1": 1e-7, "2": 1e-6, "3": 1e-5, "4": 1e-4, "5": 5e-4,
                          "6": 2e-3, "7": 1e-2, "8": 2e-2, "9": 5e-2, "10": 1e-1}
}
```

| Key | Constraint |
|---|---|
| `missionTime` | hours, > 0 |
| `timeUnit` | `h`, `d` or `y`; display only |
| `cutsets.maxOrder` | 1–20 |
| `cutsets.maxCount` | 1–1,000,000 |
| `cutsets.cutoff` | [0, 1) |
| `mc.n` | 1–1,000,000 (the HTTP endpoint caps a run at 100,000) |
| `mc.seed` | 0 … 2⁶³−1, or `null` for a random seed |
| `fmeaOccurrenceTable` | keys `"1"`…`"10"`, values in [0, 1] |

- On load, an invalid or unknown setting is reset to its default and reported
  as a `LOAD_REPAIR` session warning (`kind: "analysis_invalid"`). The rest of
  the file still loads.
- `analysis` is part of undo and redo.
- A file without `analysis` gets the defaults.

**`GET /api/state`** gains:

- `analysis`: the block above.
- `sessionWarnings`: the load repairs and removed links collected this
  session, as issue objects `{severity, code, nodeId, message, params}`.
  They are not saved. Load repairs are not undone; the notices an edit raises
  about itself -- `LINKS_REMOVED` from a delete (by hand or by the AI) and the
  `gate_type_reset` and `gate_type_promoted` notices of an AI edit
  (`params.cause: "ai"`) -- are undone and redone with that edit. At most
  500 are kept.
- `capabilities.reportExport`: whether `python-docx` is installed.
- `capabilities.fmeaXlsx`: whether `openpyxl` is installed, which `.xlsx`
  FMEA import needs.
- `revision` and `documentSerial`: which version of which document this is
  (see [Protecting work](#protecting-work-revision-examples-preferences)).
- `prefs`: what the page remembers between launches,
  `{aiPanelCollapsed: bool}`.

**Mutation payload.** Every endpoint that changes the document returns
`tree, zeroNodes, dirty, canUndo, canRedo`, and now also `analysis`,
`sessionWarnings`, `revision` and `documentSerial`. An edit that changes nothing (a `PATCH`,
`POST /api/metadata` or `POST /api/analysis/settings` with the current
values, a move to the node's current place) returns the same payload
without an undo step and without marking the document modified.

**Tree depth.** A node may sit at most `MAX_TREE_DEPTH` (200) levels below
the root. `POST /api/nodes` and `POST /api/nodes/<id>/move` refuse a deeper
node with `400 INVALID_FIELD` (`detail: {field, limit}`), and
`POST /api/file/open` and `POST /api/import/json` refuse a deeper file with
`400 INVALID_JSON` (`detail: {reason: "too_deep", depth, limit}`) before
it replaces the open document.

### Nodes: new fields and PATCH semantics

`GET /api/nodes/<id>`, and the `node` returned by create and PATCH, carry:

- every key of the table above: the raw value, or `null` when absent;
- `quantDerived: {q, model, formula, formulaKey, params, warnings}`.
  - `q` is the derived probability, or `null` when the model cannot be
    evaluated.
  - `params` holds the resolved inputs. A `T` taken from the mission time
    is marked `TFromMission: true`; only an absent `T` is taken from it. An
    own `T` that is not a valid number (from a loaded file) is `null` here
    and reported as `QUANT_PARAM_MISSING`.
  - `warnings` is a list of `{code, nodeId, params}`: `QUANT_PARAM_MISSING`,
    `STANDBY_LARGE_LT`, and the gate warnings for this node from the last
    recalculation.

`POST /api/nodes` accepts the new keys, with the same validation as PATCH.

`PATCH /api/nodes/<id>` rules:

- A top-level key set to `null` **removes** that key from the node.
- `quant`, `trace` and `fmea` **merge partially**:
  - A sub-key set to `null` removes that sub-key.
  - A nested object merges recursively, so `{"quant": {"unc": {"ef": 3}}}`
    keeps `unc.dist`.
  - Any other value replaces the old one.
  - A sub-object that ends up empty is removed.
- The other new keys replace their value.
- Setting `gateType` also sets `logicGate` to its projection. An explicit
  `logicGate` in the same request that contradicts it is
  `400 INVALID_FIELD` with `detail.field: "logicGate"`.
- Setting only `logicGate` on a node that has a `gateType` sets `gateType`
  to the same AND/OR, so the two never disagree.
- Validation errors are `400 INVALID_FIELD` with the dotted `detail.field`,
  for example `quant.tau`.
- A link may appear only once per target and relation: a repeat is
  `400 INVALID_FIELD` (`detail: {field: "links", index}`). The engine would
  count it twice.

```http
PATCH /api/nodes/root_0_1
{"quant": {"model": "rate", "lambda": 2.5e-6}, "trace": {"tags": ["pump"]}}
```

**AI update** (`POST /api/ai/update`): a full-tree AI rewrite usually drops
the 1.7 keys. They are restored by node id wherever the new tree lacks them,
and the response includes `mergedFields`, the number of fields restored.
`gateType` and `k` are restored only while they still project to the node's
new `logicGate`.

- The model is asked to keep every existing node, but nothing makes it: its
  whole tree replaces the current one, in one undo step. `updateSummary`
  says what that did: `added` and `removed` (`[{id, name}]`) and `changed`
  (`[{id, name, fields}]`, `fields` among `name`, `probability`, `gate` and
  `quant`; a probability the engine derives is not counted as changed).
- `409 AI_DOCUMENT_CHANGED`: the document changed while the model was
  writing (an edit, an undo, New or Open). Nothing is applied.
- `400 AI_UPDATE_REJECTED` also covers what the tree API would refuse: a
  probability that is not a number in [0, 1], non-text notes, an invalid
  1.7 key, unsavable text, or a tree deeper than `MAX_TREE_DEPTH`.

**AI proposals** (`POST /api/ai/changes/apply`): a proposal made for another
document (New, Open or Import replaced it since), one carrying what
`PATCH /api/nodes` would refuse, and an edit of a probability the engine
derives (a rate, standby or repairable model, a house event, a transfer
gate) are listed in `rejected` with the reason. The rest of the batch is
applied; when every one is rejected the request is a 400 and nothing
changes.

- **Links (1.7.3).** The `data` of an `add` or `edit` proposal may carry
  `links`: `[{"target_id", "relation"}]`, the node's complete new list. It
  replaces the links the node has, `[]` removes them all, and a proposal
  without the key (or with `null`) leaves them as they are. They are
  validated as `PATCH /api/nodes` validates `links` (a list of objects,
  relation `AND` or `OR`, no link twice) and, beyond that, every target must
  exist in the tree at that point of the batch and none may be the node
  itself. Until 1.7.3 the key was ignored and the proposal still reported as
  applied; a links-only edit answered `No valid fields to update`.
- **A proposal is applied as a whole or not at all.** One whose links fail
  the checks above is listed in `rejected` with the reason
  (`Not applied: the suggested link target 'x' does not exist in this
  analysis.`) and nothing of it is written, its other fields included. No
  proposal is applied in part.
- Each record in `applied` has `message` and `ignored`: the keys of the
  proposal's `data` that applying never writes (`children` when not empty,
  the 1.7 keys, anything unknown), sorted; `[]` for an ordinary proposal.
  They are not an error, and `message` names them.
- `POST /api/ai/chat` and `POST /api/ai/analyze` return each proposal that
  sets links with `linkChanges`:
  `{"added": [{"targetId", "targetName", "relation"}], "removed": [...],
  "problem": null}`, compared with the tree the model was shown. `problem`
  is the reason it will be rejected, when that is already known (a target
  that neither exists nor is added by an earlier proposal).

**What the model is sent (1.7.3).** `chat`, `analyze` and `update` send the
tree as text, as before, and in FTA mode append an "Analysis results"
section to it (`ai_bridge.analysis_section`), computed from the same snapshot
with one cut-set expansion under the summary's limits (at most 2,000 sets
and 2 s, outside the document lock):

- the headline and its method, MCUB or tree walk, with one sentence saying
  that an MCUB headline already counts each repeated event once;
- the tree-walk value and the rare-event sum;
- the repeated events (`id "name"`, at most 20);
- the 10 most probable minimal cut sets with probability and share;
- approximations (Priority-AND, XOR arity, non-coherence, large λτ) and
  whether the cut sets were truncated or capped;
- the mission time and the display unit.

Numbers have six significant figures and the text is the same for the same
document. Nothing is added in ETA mode, or when the cut sets fail or run out
of time; the request then goes out as it did in 1.7.2.

### Analysis endpoints

All of them compute on a deep copy taken under the state lock, so editing is
not blocked while they run. The computing endpoints return
`409 MODE_UNSUPPORTED` (`detail.mode: "ETA"`) for an event tree.

#### `POST /api/analysis/settings`

An undoable, validated, partial edit of `analysis`. It works in both modes.

- The body is a partial object, `{"missionTime": 17520}` or
  `{"cutsets": {"maxOrder": 4}}`, or the same wrapped as
  `{"analysis": {...}}`.
- `null` resets a setting to its default. For `mc.seed`, `null` sets it to
  null.
- Response: the mutation payload, including the new `analysis`. The tree is
  recalculated, because rate events default their T to the mission time.
- Errors: `400 INVALID_FIELD` with `detail.field` such as
  `"analysis.cutsets.maxOrder"`. An empty body is also a 400.

#### `GET /api/analysis/summary`

The headline figures (`engine.summary`):

```json
{"ok": true, "treeWalk": 1.2e-4, "mcub": 1.1e-4, "rareEvent": 1.1e-4,
 "headline": 1.1e-4, "headlineMethod": "mcub",
 "repeatedEvents": [{"id": "root_0_1", "name": "Pump A fails"}],
 "nonCoherent": false, "approximations": [{"code": "PAND_APPROX", "nodeId": "root_2", "params": {"n": 2}}],
 "truncated": false, "truncatedBy": [], "capped": false, "elapsedMs": 3.1}
```

- `headlineMethod` is `mcub` when there are repeated events or an XOR gate,
  and `treeWalk` otherwise.
- The endpoint uses cheaper cut-set limits: at most
  `min(analysis.cutsets.maxCount, 2000)` sets and a 2 s budget. Two things can
  cut the cut sets short, and they are reported separately:
  - `truncated` / `truncatedBy` (`order`, `count`, `cutoff`): the
    **document's own** limits dropped sets, as the Cut Sets tab would.
    `count` counts here only when the document's `maxCount` is 2,000 or less.
  - `capped`: only the summary's own caps (2,000 sets under a larger document
    `maxCount`, or the 2 s budget) cut the run short. The full analysis may
    be complete; the headline is just computed from fewer sets.
- If the cut sets fail or run out of time, `mcub` and `rareEvent` are `null`,
  `headline` is the tree walk, `truncated` is `true` and `truncatedBy` is
  `["time"]` (with `capped: true`) or `["error"]`.
- The UI shows a subtle `≈` marker beside the headline in advanced mode when
  the MCUB headline is capped or truncated; its tooltip says which.
- `approximations` lists `PAND_APPROX` for every reachable Priority-AND gate:
  cut sets expand PAND as plain AND (no 1/n!), so an MCUB headline is
  conservative for PAND. The UI badge tooltip uses `repeatedEvents`,
  `nonCoherent` and this list to say why the MCUB is used.

#### `POST /api/analysis/cutsets`

Body `{maxOrder?, maxCount?, cutoff?, limit?}`, all optional.

- The limits default to `analysis.cutsets` and have the same bounds.
- `limit` is the number of cut sets returned: default 500, at most 100,000.
- The time budget is 30 s.

```json
{"ok": true,
 "cutSets": [{"rank": 1, "events": [{"id": "root_0_1", "name": "Pump A fails", "q": 1e-3}],
              "order": 1, "probability": 1e-3, "share": 0.91}],
 "total": 12, "returned": 12, "truncated": false, "truncatedBy": [],
 "mcub": 1.1e-3, "rareEvent": 1.1e-3, "treeWalk": 1.1e-3,
 "repeatedEvents": [], "nonCoherent": false, "approximations": [],
 "warnings": [], "limits": {"maxOrder": 6, "maxCount": 5000, "cutoff": 1e-15},
 "elapsedMs": 4.2}
```

- `total`, `mcub` and `rareEvent` cover every cut set, not only the returned
  ones.
- `truncatedBy` lists any of `order`, `count` and `cutoff`. When it is not
  empty, `warnings` holds a `CUTSETS_TRUNCATED` entry.
- `share` is P(C) divided by the rare-event sum.
- An empty cut set (`order: 0`, `events: []`) means the top event always
  occurs.
- `422 ANALYSIS_TOO_LARGE` is returned when a voting gate expands to more than
  20,000 combinations (`detail: {reason: "kofn", nodeId, k, n, combinations,
  limit}`) or the time budget runs out (`detail.reason: "time"`).

#### `POST /api/analysis/importance`

The body is the same as for `/cutsets`; `limit` is ignored.

```json
{"ok": true, "basis": "mcub", "topValue": 1.1e-3, "cutSetTotal": 12,
 "truncated": false, "truncatedBy": [], "warnings": [],
 "events": [{"id": "root_0_1", "name": "Pump A fails", "q": 1e-3,
             "fv": 0.91, "birnbaum": 0.99, "raw": 900.0, "rrw": 11.0,
             "rrwInfinite": false, "cutSetCount": 1}]}
```

- Events are sorted by FV, largest first.
- `rrw` is `null` with `rrwInfinite: true` when removing the event makes the
  top event impossible.
- Errors are the same as for `/cutsets`.

#### `POST /api/analysis/uncertainty`

Body `{n?, seed?, timeLimit?, bins?}`:

| Field | Default | Limit |
|---|---|---|
| `n` | `analysis.mc.n` | at most 100,000 |
| `seed` | `analysis.mc.seed`; if null, one is drawn and returned | |
| `timeLimit` | 30 s | (0, 60] s |
| `bins` | 40 | 1–200 |

```json
{"ok": true, "requested": 10000, "completed": 10000, "seed": 1234, "method": "tree",
 "mean": 1.4e-3, "median": 1.0e-3, "p05": 3.1e-4, "p95": 3.9e-3, "std": 1.3e-3,
 "pointEstimate": 1.1e-3,
 "histogram": {"edges": [], "counts": [], "logBins": true},
 "truncatedByTime": false, "cutsetsTruncated": false,
 "uncertainEvents": ["root_0_1"], "certainEvents": ["root_0_2"],
 "repeatedEvents": [], "nonCoherent": false, "warnings": [], "elapsedMs": 812.0}
```

- `method` is `tree` for a coherent tree without repeated events, and
  `cutsets` otherwise.
- `warnings` can contain:
  - `MC_NO_UNCERTAINTY`: no event has a usable lognormal;
  - `MC_CUTSETS_TRUNCATED` (`params: {used, total, coverage}`);
  - `MC_EVENT_NOT_SAMPLED` (`params: {count, eventIds, names}`): method
    `cutsets` only; uncertain events in none of the sampled cut sets,
    whose uncertainty is therefore not in the result;
  - `CUTSETS_TRUNCATED`.
- Only one run at a time: a concurrent request gets `409 BUSY`.
- `422 ANALYSIS_TOO_LARGE` is returned as for `/cutsets`.

#### `GET /api/analysis/validate`

It works in both modes and does not return `MODE_UNSUPPORTED`.

```json
{"ok": true, "mode": "FTA",
 "counts": {"error": 1, "warning": 2, "info": 0},
 "issues": [{"severity": "error", "code": "KOFN_ARITY", "nodeId": "root_3",
             "message": "K-out-of-N gate needs 1 <= k <= n (k = 4, n = 3).",
             "params": {"k": 4, "n": 3}}]}
```

- Issues are sorted by severity (error, warning, info). Within a severity,
  document-level issues come first, then tree order.
- In FTA mode the cut sets are expanded (outside the lock) with the
  document's `analysis.cutsets` limits and a 2 s budget
  (`cutsets.truncation_signal`), so `CUTSETS_TRUNCATED` (`params: {reason,
  count}`, reason such as `"count"` or `"cutoff, order"`) appears when they
  truncate. If the expansion fails or runs out of time, nothing is reported
  about truncation.
- `RATE_IMPLAUSIBLE` (warning, FTA) flags an event whose rate, standby or
  repairable model has λ > 1e-2 /h, or whose rate model gives q ≥ 0.999
  (`params: {lambda, unit: "h", q, model}`): usually FIT or per-year values
  entered as per hour.
- `PROBABILITY_OUT_OF_RANGE` (error, FTA and ETA) flags a probability the
  engine uses that is not a finite number in [0, 1] (`params: {probability}`,
  the stored value): an FTA leaf's own value (not a house event's or a
  rate/standby/repairable model's), every ETA node's. The tree API refuses
  such a value; a loaded file can still hold one.
- `message` is English. The UI localises it with `val.code.<CODE>` and
  `params`.
- The codes and their severities are listed in the
  [User Guide](USER_GUIDE.md#validation) and in `fta_web/lint.py`.

### CCF groups API (1.9)

Common-cause failure groups with the beta-factor model and, for groups of 2 to
4 members, the alpha-factor model. What a group means, the formulas and their
sources are in [CCF.md](CCF.md); the screens are in the
[User Guide](USER_GUIDE.md#ccf-groups-beta-factor-and-alpha-factor).

Groups are stored in the document, as `analysis.ccfGroups` (a list), so the
standard `POST /api/undo` and `POST /api/redo` restore them, and they are saved
and loaded with the file. `POST /api/analysis/settings` does not accept
`ccfGroups`; groups change only through the endpoints below. They work in both
modes (in ETA mode the groups are data and are not applied).

A stored group has exactly these keys:

```json
{"id": "g1", "name": "Feed pumps", "model": "beta", "beta": 0.1,
 "alpha": null, "testing": null, "members": ["n12", "n13"], "source": "data handbook, p. 42"}
```

A beta group has a `beta` (a dimensionless number from 0 to 1) and `alpha` and
`testing` of `null`. An alpha group has `"model": "alpha"`, `beta` of `null`,
`alpha` (a list of numbers, one per member, `alpha[k-1]` being α_k, the fraction
of failure events in which exactly k members fail) and `testing`
(`"staggered"`, `"nonStaggered"` or `null` when no scheme is chosen):

```json
{"id": "g2", "name": "Relief valves", "model": "alpha", "beta": null,
 "alpha": [0.955, 0.034, 0.011], "testing": "staggered",
 "members": ["n20", "n21", "n22"], "source": ""}
```

Every body is read strictly: a body that is not a JSON object, or that holds
the tokens `NaN`, `Infinity` or `-Infinity`, is `400 INVALID_JSON`. A number is
a JSON number: `"0.1"` (a string), `true` and `null` are refused.

**The status of a group.** Every group in every response carries `status`:

```json
{"applied": false, "code": "CCF_MEMBERS_DIFFER", "severity": "error",
 "reason": {"en": "\"Pump B\" differs from \"Pump A\"", "ja": "..."},
 "message": {"en": "CCF group \"Feed pumps\": ...", "ja": "..."},
 "errors": [{"code": "CCF_MEMBERS_DIFFER", "severity": "error", "member": "Pump B", "memberId": "n13",
             "reason": {"en": "...", "ja": "..."}, "message": {"en": "...", "ja": "..."}}],
 "warnings": []}
```

For an applied group `code`, `severity`, `reason` and `message` are `null`,
`errors` is empty and `warnings` lists the group's warnings (same item shape).
`code` is the first error found, or `CCF_ETA_MODE` (severity `status`) in ETA
mode; `errors` lists every error. The codes are listed in
[CCF.md](CCF.md#applied-and-not-applied). The server sends both languages; the
client picks one.

#### `GET /api/ccf/groups`

```json
{"ok": true, "mode": "FTA", "revision": 4, "documentSerial": 1,
 "groups": [{"id": "g1", "name": "Feed pumps", "model": "beta", "beta": 0.1,
             "alpha": null, "testing": null, "members": ["n12", "n13"],
             "memberNames": ["Pump A", "Pump B"], "source": "", "status": {"applied": true}}],
 "ccf": {"applied": [{"id": "g1", "name": "Feed pumps", "model": "beta", "beta": 0.1,
                      "members": ["n12", "n13"], "warnings": []}],
         "notApplied": [],
         "note": "Check CCF results with a qualified engineer before use."}}
```

- `memberNames` has one entry per member: the node's name, or `null` when the
  id is not in the tree. (`status` is abbreviated above.)
- A group with invalid stored values is returned as stored, with its status.
- `ccf` is the block that analysis results carry (below).

An alpha group in the list (the status is abbreviated: this one has a
normalisation warning, so it is applied):

```json
{"id": "g2", "name": "Relief valves", "model": "alpha", "beta": null,
 "alpha": [0.955, 0.034, 0.0115], "testing": "staggered",
 "members": ["n20", "n21", "n22"], "source": "", "memberNames": ["V1", "V2", "V3"],
 "status": {"applied": true, "code": null, "severity": null, "reason": null, "message": null,
            "errors": [],
            "warnings": [{"code": "CCF_ALPHA_NORMALISED", "severity": "warning",
                          "member": "V1, V2, V3", "memberId": null,
                          "reason": {"en": "...", "ja": "..."},
                          "message": {"en": "...", "ja": "..."}}]}}
```

The item of an **applied** alpha group also has `alphaParts`, the probabilities of
the group as the analysis uses them (the same numbers
the expansion and the diagram use; the Details panel shows them):

```json
"alphaParts": {"independent": [0.000955, 0.000955, 0.000955],
               "events": [{"members": ["n20", "n21"], "memberNames": ["V1", "V2"], "q": 1.7e-05},
                          {"members": ["n20", "n22"], "memberNames": ["V1", "V3"], "q": 1.7e-05},
                          {"members": ["n21", "n22"], "memberNames": ["V2", "V3"], "q": 1.7e-05},
                          {"members": ["n20", "n21", "n22"], "memberNames": ["V1", "V2", "V3"], "q": 1.1e-05}]}
```

`independent` holds Q_1 of each member (in the order of `members`); `events` lists
one CCF event per subset of two or more members, size ascending and then in group
order, each with its Q_k. A beta group, and an alpha group that is not applied,
have no `alphaParts` key. The key is in every group item that `GET`, `POST` and
`PATCH /api/ccf/groups` return.

#### `POST /api/ccf/groups`

Body for the beta model: `{name, model: "beta", beta, members, source?}`. Body
for the alpha model: `{name, model: "alpha", alpha, members, source?, testing?}`.
The id (`g1`, `g2`, ... the smallest unused number) is assigned by the server.

```json
{"name": "Relief valves", "model": "alpha", "alpha": [0.955, 0.034, 0.011],
 "testing": "staggered", "members": ["n20", "n21", "n22"], "source": ""}
```

The response is as for a beta group: `ok`, `group` (the new group with its
status), `groups`, `ccf` and the mutation payload. When `testing` is left out the
group is stored with `"testing": null` and its status is
`CCF_NO_TESTING` (`Not applied: testing scheme missing`); it is not a refusal.

| Field | Rule |
|---|---|
| `name` | string, white space normalised, not empty, at most 4,000 characters |
| `model` | `"beta"` or `"alpha"`; any other value is refused |
| `beta` | beta model: a JSON number in [0, 1]; `-0` is stored as `0`. Alpha model: absent or `null` |
| `alpha` | alpha model: a list of JSON numbers, each in [0, 1] (`-0` is stored as `0`; the empty list is accepted). Its length and its sum are **not** refusals: they are lint (`CCF_ALPHA_SUM`, `CCF_ALPHA_NORMALISED`), so a group can be saved and shown with its reason. Beta model: absent or `null` |
| `testing` | alpha model: `"staggered"`, `"nonStaggered"` (no hyphen) or `null`; optional. Beta model: absent or `null` |
| `members` | a list of distinct non-empty node ids, all in the tree |
| `source` | string or `null` (stored as `""`) |

`alpha` checks: a list whose items are all numbers in [0, 1] (`[0.9, 0.1]`) is
accepted; an item that is a string (`["0.1", 0.9]`), `true`, `null`, a list,
`-0.1` or `1.5` gives `400 INVALID_FIELD` with `detail.field` `"alpha"` and
`detail.index`, the 0-based position of the first bad item; a value that is not
a list (`0.5`, `"x"`, `null`) gives `400 INVALID_FIELD` with `detail.field`
`"alpha"` and no index. The tokens `NaN`, `Infinity` and `-Infinity` anywhere in
the body give `400 INVALID_JSON`. A field of the other model that is not `null`
(`alpha` or `testing` with `"model": "beta"`, `beta` with `"model": "alpha"`)
gives `400 INVALID_FIELD` naming it. A `testing` that is not `"staggered"`,
`"nonStaggered"` or `null` gives `400 INVALID_FIELD` with `detail.field`
`"testing"`.

Any other key (`id` included) is refused. A member that is already in another
group, or is not a basic event, is accepted and shown in the group's `status`;
it is not a refusal. The response is the mutation payload (tree, `analysis`,
`dirty`, `canUndo`, `canRedo`, `sessionWarnings`, `revision`,
`documentSerial`) plus `group` (the new group with its status), `groups` and
`ccf`.

#### `PATCH /api/ccf/groups/<id>`

Body: any of `name`, `model`, `beta`, `alpha`, `testing`, `source`, `members`
(the list replaces the old one). The fields are checked as for `POST`; the
effective model is the `model` of the body, else the stored one, and a field of
the other model that is not `null` is refused. Examples:

```json
{"testing": "nonStaggered"}
{"alpha": [0.95, 0.04, 0.01]}
{"model": "beta", "beta": 0.1}
{"model": "alpha"}
{"members": ["n20", "n21"]}
```

- A change of `model` is one request and one undo step: the fields of the old
  model become `null` and those of the new model come from the body, else
  `null`. `{"model": "alpha"}` alone makes a group with `alpha` and `testing` of
  `null`, which is not applied; Undo restores the old model's values.
- `{"alpha": [...]}` on a beta group without `"model": "alpha"` is
  `400 INVALID_FIELD` (`alpha`). `{"alpha": null}` is refused (not a list); to
  clear the values, change the model.
- A change of `members` never edits `alpha`: a list whose length differs from
  the number of members makes the group not applied (`CCF_ALPHA_SUM`, kind
  `length`) until `alpha` is sent again.

An empty body is
`400 INVALID_FIELD` ("No group fields to update."). The response is that of
`POST` plus `changed`: when no field differs from what is stored, `changed` is
`false`, nothing is written, no undo step is made and `revision` does not
change.

#### `DELETE /api/ccf/groups/<id>`

Response: the mutation payload plus `deletedId`, `groups` and `ccf`. When the
last group is deleted the `ccfGroups` key is removed from `analysis`.

**Undo and revision.** Each of `POST`, `PATCH` (with `changed: true`) and
`DELETE` is one undo step and raises `revision` by one, as every other edit.

**Errors.**

| Code | HTTP | When | `detail` |
|---|---|---|---|
| `INVALID_JSON` | 400 | The body is not a JSON object, or holds `NaN`, `Infinity` or `-Infinity` | none |
| `INVALID_FIELD` | 400 | A field is missing, has the wrong type or is out of range (`beta` outside [0, 1], a string, `true`; an item of `alpha` that is not a number in [0, 1], or `alpha` that is not a list; a `testing` other than `"staggered"`, `"nonStaggered"` or `null`; a field of the other model that is not `null`; a member id that is not in the tree; an unknown key; an empty `PATCH`) | `{field}`; for an item of `alpha` also `{index}` (0-based); for members `{field: "members", ids: [...]}`; for unknown keys `{field, fields}` |
| `GROUP_NOT_FOUND` | 404 | `PATCH` or `DELETE` with an id that no stored group has | `{groupId}` |

#### Membership follows the tree

Deleting a node (single or batch), applying an AI update that removes nodes, or
an FMEA re-import that replaces nodes removes the node from its group in the
same undo step. Undo restores both. A file whose duplicate node ids were
repaired on load flags the groups concerned `CCF_MEMBER_RENAMED`; a root id
renamed on load is followed. Making a member a gate keeps it in the group and
flags the group (`CCF_MEMBER_NOT_BASIC`).

#### The `ccf` block and the new result fields

When the document has at least one group, the results of
`GET /api/analysis/summary`, `POST /api/analysis/cutsets`,
`POST /api/analysis/importance` and `POST /api/analysis/uncertainty` carry the
block (and the CLI `--json` output of the same commands carries it too):

```json
"ccf": {"applied": [{"id": "g1", "name": "Feed pumps", "model": "beta", "beta": 0.1,
                     "members": ["n12", "n13"],
                     "warnings": [{"code": "CCF_HIGH_Q", "member": "Pump A", "reason": "..."}]}],
        "notApplied": [{"id": "g2", "name": "Valves", "code": "CCF_MEMBERS_DIFFER",
                        "reason": "\"Valve D\" differs from \"Valve C\""}],
        "note": "Check CCF results with a qualified engineer before use."}
```

The item of an applied alpha group adds four keys; a beta item has none of them:

```json
{"id": "g2", "name": "Relief valves", "model": "alpha", "beta": null,
 "members": ["n20", "n21", "n22"], "warnings": [],
 "alpha": [0.955, 0.034, 0.011], "testing": "staggered",
 "alphaSum": 1.0, "alphaNormalised": false}
```

`alpha` and `testing` are the stored values, `alphaSum` is the sum of the stored
α values (the original sum, before the division) and `alphaNormalised` is `true`
when the group carries `CCF_ALPHA_NORMALISED`. A group without a testing scheme
is in `notApplied` with code `CCF_NO_TESTING` and reason `testing scheme missing`.

`reason` is English in the block. In ETA mode every group is in `notApplied`
with code `CCF_ETA_MODE` and reason `ETA mode`. A document without groups gets
none of the keys below, and its results are those of 1.8.1.

`GET /api/analysis/summary` gains:

| Key | Meaning |
|---|---|
| `ccf` | the block above |
| `ccfIncomplete` | `true` when a group is applied and the cut sets could not be completed |
| `ccfIncompleteReason` | only when `ccfIncomplete`: `"time"`, `"error"` or `"summary cap"` |
| `ccfGates` | only when a group is applied: `{nodeId: {"method": "mcub", "value": v}}` for every gate whose subtree holds a member of an applied group, the root included, or `{"method": "na"}` when the cut sets are incomplete (shown as `n/a (CCF)`) |
| `headlineMethod` | gains the value `incomplete` |

- With a group applied, `headlineMethod` is `mcub` and `headline` includes the
  CCF events, also when the tree has no repeated event. The cut sets are
  always computed for it.
- When the cut sets fail, run out of time, or are cut short by the summary's
  own cap (`capped`), `headlineMethod` is `incomplete` and `headline`, `mcub`
  and `rareEvent` are `null`. `treeWalk` is still sent: it does not include
  CCF, and a client must show it only with that label.
- Groups that are all not applied change no number: `headlineMethod` and
  `headline` are those of the tree without them, and `ccfIncomplete` is
  `false`.
- `repeatedEvents` lists `ccf:<groupId>` with the name `CCF: <group name>`
  (for an alpha group, the events of the group that more than one member
  reaches, with their ids `ccf:<groupId>:<m1>+<m2>…`).

`POST /api/analysis/cutsets` and `/importance`: an event that comes from a
group has a `ccf` marker, and the CCF event has the id `ccf:<groupId>`:

```json
{"id": "ccf:g1", "name": "CCF: Feed pumps", "q": 1e-4,
 "ccf": {"groupId": "g1", "role": "event", "members": ["n12", "n13"], "baseName": "Feed pumps"}}
{"id": "n12", "name": "Pump A (independent part)", "q": 9e-4,
 "ccf": {"groupId": "g1", "role": "independent", "baseName": "Pump A"}}
```

A member's variable keeps the member's id with `q = (1 − β)·Q_t`; the CCF
event has `q = β·Q_t`. Events without a group have no `ccf` key.

An alpha group has one CCF event for each subset of two or more members. The id
is `ccf:<groupId>:<m1>+<m2>…` (member ids in the order of the group), `q` is
`Q_k` for the size k of the subset, and the marker also carries `memberNames`;
the independent part has `q = Q_1`:

```json
{"id": "ccf:g2:n20+n21", "name": "CCF: Relief valves (V1 + V2)", "q": 1.7e-5,
 "ccf": {"groupId": "g2", "role": "event", "members": ["n20", "n21"],
         "memberNames": ["V1", "V2"], "baseName": "Relief valves"}}
```

A group with 2, 3 or 4 members has 1, 4 or 11 such events. An event of a beta
group has no `memberNames`. A group is not applied (`CCF_BAD_PARAMETER`, kind
`event_id`) when two of its events, or an event of another group, would get the
same id, which only ids that contain `+` or `:` can cause. Importance
(FV, Birnbaum, RAW, RRW) is computed on this expanded structure; the CCF event
has its own row and there is no combined row for a component.

`POST /api/analysis/uncertainty` gains `ccf` (the block) and, when a group is
applied, `ccfSampling`:

```json
"ccfSampling": {"groups": [{"id": "g1", "sampled": true}],
                "note": "β and α are not sampled in Monte Carlo."}
```

`sampled` says whether the group's members have an uncertainty that is drawn
(one draw per group per trial); β is never sampled.

`GET /api/analysis/validate`: the lint codes of
[CCF.md](CCF.md#applied-and-not-applied) are issues with `nodeId: null` and
`params: {groupId, group, memberId, member, text}`, where
`text.<lang>.{reason, message, fix}` holds the English and Japanese texts
(they have no `val.code.*` entry). `CCF_ETA_MODE` is a status and is never an
issue, and in ETA mode there is no CCF issue.

`GET /api/dot` gains `ccfGates` (boolean): `true` when the diagram text holds
gate values from the cut sets (MCUB, or `n/a (CCF)`) instead of tree-walk
values, so a client can show the explanation. In ETA mode the diagram has no
CCF badge and no CCF gate value.

**Loading.** Opening a file with `fileFormatVersion` greater than 2 adds the
load warning `{kind: "newer_format", message: "This file was saved by a newer
FTA Editor; saving may lose data"}`. A `ccfGroups` that is not a list is
ignored with the warning kind `ccf_invalid`. An invalid group inside the list
is kept as it is and flagged; it is never an `analysis_invalid` warning.

The CLI (`quantify`, `cutsets`, `importance`, `mc`) adds the same `ccf` block to
`--json` and exits with 1 when a group is not applied or the headline is
`incomplete`, in fault-tree mode only; see the
[User Guide](USER_GUIDE.md#command-line-interface).

### Report and FMEA endpoints

#### `POST /api/report/docx`

Body (every key optional):

```json
{"sections": ["metadata", "headline", "assumptions", "diagram", "events",
              "cutsets", "importance", "uncertainty", "validation", "traceability"],
 "sigFigs": 3, "lang": "en",
 "diagramPng": "<base64 PNG>",
 "topN": {"cutsets": 50, "importance": 30},
 "limits": {"maxOrder": 6, "maxCount": 5000, "cutoff": 1e-15},
 "runUncertainty": false, "uncertaintyN": 5000, "uncertaintyTimeLimit": 30}
```

Only these keys are read; any other top-level key is ignored (never passed to
the report builder). A bad value of a known key is `400 INVALID_FIELD`.

- `sections` defaults to all of them except `uncertainty`. An unknown section
  is `400 INVALID_FIELD`.
- `lang` defaults to the request language.
- `diagramPng`:
  - A `data:image/png;base64,` prefix is accepted.
  - The decoded image can be at most 8 MB and must have a PNG signature.
  - Without it, the diagram is rendered server-side in the compact style when
    a native `dot` exists. Otherwise the report says it is unavailable.
- `topN` values are clamped to 1–10,000.
- `limits` overrides the document's cut-set limits for the report. It is
  validated exactly like `analysis.cutsets`: only `maxOrder`, `maxCount` and
  `cutoff`, each in its range; any other key (including `timeBudgetS`) is a
  400.
- `runUncertainty` runs Monte Carlo for the report. `uncertaintyN` sets the
  samples (an integer 1–5,000, default 5,000) and `uncertaintyTimeLimit` the
  time cap in seconds (a number in (0, 60], default 30). The seed is
  `analysis.mc.seed`.

The response is the `.docx` bytes as an attachment, `<document>_report.docx`,
with MIME type
`application/vnd.openxmlformats-officedocument.wordprocessingml.document`. It
is not a JSON envelope.

- ETA documents are accepted; the fault-tree-only sections carry a note.
- `503 EXPORT_UNAVAILABLE` is returned when python-docx is missing. The detail
  is `{format: "docx", package: "python-docx", install: "uv sync --extra report"}`.

#### `POST /api/fmea/preview`

Body `{path, sheet?, mapping?}`. `path` is a server-side path chosen through
the file dialog. It gets the same root, traversal and symlink checks as
`/api/file/open`. Only `.csv` and `.xlsx` are accepted, at most 10 MB. The
endpoint is read-only.

```json
{"ok": true, "path": "C:/work/pfmea.xlsx", "name": "pfmea.xlsx",
 "sheets": ["PFMEA"], "sheet": "PFMEA",
 "columns": ["ID", "Item", "Failure mode", "Cause", "S", "O", "D", "RPN", "λ (FIT)"],
 "rows": [["P-01", "Pump", "Seal leak", "Wear", 7, 4, 5, 140, 250]],
 "rowNumbers": [2], "rowCount": 120,
 "fields": ["id", "item", "mode", "cause", "severity", "occurrence", "detection", "rpn", "lambda"],
 "suggestedMapping": {"id": "ID", "item": "Item", "mode": "Failure mode", "lambda": "λ (FIT)"},
 "suggestedLambdaUnit": "FIT",
 "occurrenceTable": {"1": 1e-7, "10": 0.1},
 "defaultOccurrenceTable": {"1": 1e-7, "10": 0.1}}
```

`rows` holds at most the first 50 rows, as the import reads them: a blank
item under a row with a failure mode is filled down, for `mapping` when the
body has one, else for `suggestedMapping`. `occurrenceTable` is the
document's table; `defaultOccurrenceTable` is the AIAG default.
`suggestedMapping` never offers an AIAG-VDA "AP" (action priority) column
for `rpn`.

`suggestedLambdaUnit` is the unit the λ header names (`FIT`; `/y`, `per year`,
`年`; `/h`, `per hour`, `時間`). When the header names none, it comes from the
median of the column's non-empty values (all rows, not only the preview):
at least 1 gives `FIT`, 1e-3 up to 1 gives `y`, anything else `h`.

#### `POST /api/fmea/import`

Body `{path, sheet?, mapping: {field: column}, lambdaUnit: "h"|"y"|"FIT",
parentId, update: true, occurrenceTable?: {"1".."10": p}}`.

The `skipped[].reason` values are `noKey`, `duplicate`, `exists`,
`invalidRank`, `invalidRpn` and `invalidLambda`.

- It is one undo step, pushed only when something changes.
- Rows whose key matches a node's `fmea.id` update that node in place; the
  others become new leaf events under `parentId`. An update changes only the
  fields whose columns are mapped (a mapped column left blank empties its
  field).
- Nodes of an earlier import of the same sheet whose key no row holds any
  more are kept and listed in `notInSheet`.
- Text numbers: `1,5` and `1.200,5` (1200.5) are read with a decimal comma;
  in a comma-delimited CSV `1,200` is 1200 (thousands grouping), elsewhere
  1.2.
- An `occurrenceTable` that differs from the document's is saved into
  `analysis.fmeaOccurrenceTable` in the same undo step.

The response is the mutation payload plus:

```json
{"created": ["root_2_0"], "updated": ["root_0_1"], "unchanged": [],
 "skipped": [{"row": 7, "fmeaId": "P-07", "reason": "invalidRank", "field": "occurrence",
              "value": 12, "message": "..."}],
 "notInSheet": [{"id": "root_2_3", "name": "Pump – Bearing seizure", "fmeaId": "P-09"}],
 "changed": true, "source": "pfmea.xlsx [PFMEA]"}
```

Errors:

- `409 MODE_UNSUPPORTED`: ETA mode.
- `503 EXPORT_UNAVAILABLE`: an `.xlsx` without openpyxl. The detail is
  `{format: "xlsx", feature: "fmea", package: "openpyxl"}`.
- `400 INVALID_FIELD`: a bad body, an unknown sheet or column, no key column,
  a bad λ unit, or a transfer gate as the parent. `detail.reason` comes from
  `FmeaImportError`.
- `404 PARENT_NOT_FOUND`: the parent does not exist.
- 4xx `PATH_REJECTED`: the path failed a check. `detail.reason` gives the
  reason (`not_found`, `too_large`, and so on).

### Diagram endpoints: new parameters

`GET /api/dot` (query parameters) and `POST /api/render` (JSON body) accept:

| Parameter | Values | Default |
|---|---|---|
| `style` | `compact` \| `symbols` | `compact` |
| `rankdir` | `LR` \| `TB` | `LR` |
| `sigFigs` | 1–6 (clamped) | 3 |

An invalid `style` or `rankdir` is `400 INVALID_FIELD`. `GET /api/dot` echoes
the three values and adds `idMap` and `rootHeadline`:

```json
{"ok": true, "dot": "digraph G {...}", "renderer": "wasm", "style": "symbols",
 "rankdir": "TB", "sigFigs": 3,
 "idMap": {"root": "root", "root__gate": "root", "root_0_1": "root_0_1", "root_0_1__event": "root_0_1"},
 "rootHeadline": {"method": "mcub", "value": 0.068353515625, "treeWalk": 0.0349375}}
```

- `idMap` maps every DOT node name to its tree node id. That includes the
  synthetic symbol nodes `<sid>__gate` and `<sid>__event`, which get a `_2`
  (`_3` …) suffix if a real id already has that name.
- A plain node keeps its 1.6 name, so older clients that do not read the map
  still work.
- `POST /api/render` draws the Graphviz *approximations* of the symbols. The
  true symbols exist only in the browser renderer.
- **The root's label (1.7.3).** Every node's label shows its
  `calculatedProbability`, the tree-walk value. When the headline is the
  MCUB, the root's label shows the headline instead, marked, with the
  tree-walk value beside it: `P_calc:0.0684 (MCUB) | tree walk 0.0349` in the
  compact style, `Q=0.0684 (MCUB)` over a smaller `tree walk 0.0349` line in
  the symbols style. `rootHeadline` is then `{method: "mcub", value,
  treeWalk}`; otherwise it is `null` and the DOT is what 1.7.2 produced.
  `POST /api/render` draws the same DOT.
  - The rule is `engine.root_headline(summary)`: `headlineMethod` is `mcub`
    and `capped` is false. A headline that is the tree walk (which includes
    cut sets that failed or timed out), ETA mode and a summary cut short by
    its own 2,000-set cap all leave the root's tree-walk label.
  - Only the root. A cut-set value per gate would cost one expansion per
    gate and is a different quantity from the one the tree walk propagates
    along the edges.
  - The tree is copied once under the document lock; the headline and the
    DOT are both computed from that copy, outside the lock. A tree without a
    link, a transfer or an XOR gate is drawn directly, with no cut sets
    computed. The headline is remembered for the last document, so a theme
    or layout change does not recompute it.

### Protecting work: revision, examples, preferences

Added after 1.7.3. Like every `/api` endpoint these need the launch token,
and they are refused for a foreign `Origin` or `Host`.

**`revision` and `documentSerial`.** Two integers, in `/api/state` and in
every answer that carries `tree`.

- `revision` goes up by one whenever the content of the document changes:
  every edit, undo and redo, and New, Open, Import and an example.
- `documentSerial` goes up when another document replaces this one (New,
  Open, Import, an example).
- Saving changes neither. An edit that changes nothing changes neither.
- `POST /api/file/save` and `/save-as` answer without a tree and therefore
  without these two.

A page compares them with the copy it holds to learn that another browser tab
changed the document.

**`GET /api/revision`** returns `{revision, documentSerial, dirty,
currentPath}` and nothing else: no tree. The page asks it when a tab gets the
focus back, and every five seconds while the tab is visible to find out
whether the server is still running.

**`POST /api/prefs`** stores a display preference between launches. Body: any
of `{aiPanelCollapsed: bool}`. It answers `{prefs: {aiPanelCollapsed}}`, which
`/api/state` also carries.

- A key that is not listed here, or a value of another type, is
  `400 INVALID_FIELD` with `detail: {field}`, and nothing is written.
- It is not part of the document: no undo step, no revision.
- The values are kept in `ui_prefs.json` in the per-user folder
  (`~/.fta_editor`), beside the AI credentials. The same file holds
  `lastFolder`, which only a successful `POST /api/file/open` or
  `/api/file/save-as` sets. A request cannot set it.

**`GET /api/fs/home`**: for a document with no path, `cwd` is now the folder
of the last file opened or saved, when that folder still exists inside the
root. The stored folder goes through the same check as a path from the
client, and anything it refuses means `cwd` is the root, as before.

**`GET /api/examples`** lists the analyses that ship with the app
(`config.EXAMPLES_DIR`): `{examples: [{name, title, mode}]}`. `name` is a file
name, never a path. `title` and `mode` come from the file and are `null` for a
file that cannot be read. Only regular `.json` files directly in that folder
are listed; a symbolic link is not.

**`POST /api/examples/open`** replaces the document with a copy of one of
them. Body: `{name}`, one of the names the listing gives.

- The answer is the document payload of `POST /api/file/open`, with
  `example` (the name), `currentPath: null` and `dirty: false`. The next
  `POST /api/file/save` is therefore `409 NO_CURRENT_PATH`: the bundled file
  cannot be written through the API.
- `name` is looked up in the listing and is never joined to a path. Anything
  else (a path, `..`, a name in another case, a file that is not listed) is
  `404 INVALID_FIELD` with `detail: {field: "name"}`; a missing or non-string
  `name` is 400. The value is not echoed back.
- A listed file that is not an analysis is `400 INVALID_JSON`.
- Like `/api/file/open` it does not refuse to discard unsaved changes; the
  page asks first.

**`POST /api/ai/update` with `{"preview": true}`** generates and verifies the
rewrite as before, and does **not** install it. The answer has no tree:

```json
{"ok": true, "preview": true, "updateId": "k3J…", "reply": "…",
 "mergedFields": 0,
 "updateSummary": {"added": [{"id": "root_7", "name": "Common cause"}],
                   "changed": [{"id": "root_0", "name": "Cause A"}],
                   "removed": [{"id": "root_1", "name": "Cause B"}]}}
```

- `updateSummary` and `mergedFields` are what installing it would report.
  They are worked out on a copy; the document, its undo history and its
  revision are untouched.
- One rewrite waits at a time. A newer request to `/api/ai/update`, and
  `DELETE /api/ai/conversation`, drop it.
- Without `preview` (or with `false`) the call installs the rewrite at once,
  as in 1.7. A `preview` that is not a boolean is `400 INVALID_FIELD`.
- The other answers are unchanged: `400 AI_INVALID_JSON`,
  `400 AI_UPDATE_REJECTED`, and `409 AI_DOCUMENT_CHANGED` when the document
  changed while the model was working.

**`POST /api/ai/update/apply`** installs the waiting rewrite. Body: `{id}`,
the `updateId` of the preview.

- The answer is the mutation payload with `mergedFields` and
  `updateSummary`, as from the one-step update. It is one undo step.
- `409 AI_DOCUMENT_CHANGED`: the document was edited, undone, or replaced
  since the preview. Nothing is changed, and the rewrite is dropped.
- `409 AI_UPDATE_EXPIRED`: `id` is not the rewrite that is waiting (it was
  applied, discarded or replaced, or the id is wrong). Nothing is changed.
- `400 AI_NOT_CONFIGURED` without credentials. The provider is not called.

**`POST /api/ai/update/discard`** drops the waiting rewrite. Body: `{id}`, or
nothing for whichever is waiting. It answers `{discarded: bool}` and is never
an error for "nothing was waiting". It needs no credentials.

**`GET /api/ai/conversation`** is what a reloaded page repaints. It is
read-only, needs the session token like every `/api` route, and works with
no provider configured (everything empty; it then does not even create the
per-user folder).

```json
{ "ok": true,
  "messages": [
    {"role": "user", "kind": "chat", "content": "What fails first?"},
    {"role": "assistant", "kind": "chat", "content": "The **valve**."},
    {"role": "user", "kind": "analyze"},
    {"role": "assistant", "kind": "analyze", "content": "..."},
    {"role": "user", "kind": "update"},
    {"role": "assistant", "kind": "update"}
  ],
  "changes": [],
  "pendingUpdate": null }
```

- `messages` are the turns the editor keeps while it runs: what was typed
  and what the model answered. The system prompt and the tree sent with a
  message are not in it. `kind` is `chat`, `analyze` or `update`; the
  built-in request of an Analyze and both turns of an Update FTA (whose
  reply is the whole tree as JSON) carry no `content`.
- `changes` are the proposals still pending **for the open document**, with
  their `index`, as `POST /api/ai/chat` returns them.
- `pendingUpdate` is `{updateId, updateSummary}` for the Update FTA preview
  still waiting, or null.
- No credential is in the answer: there is no field for one, and the text is
  scrubbed of the stored key like every other reply.

### Keeping work, the allowed folder and Stop (after 1.8.0)

Like every `/api` endpoint these need the launch token, and they are refused
for a foreign `Origin` or `Host`.

**Replacing the document needs `force` over unsaved changes.** `POST
/api/file/open`, `POST /api/examples/open` and `POST /api/import/json` now
behave like `POST /api/new`: when the current document has unsaved changes
they answer `409 UNSAVED_CHANGES` and change nothing, unless the request
says to discard them.

- JSON bodies take `force: true`. It must be a boolean: `"true"`, `1` and
  the like are `400 INVALID_FIELD` with `detail: {field: "force"}`.
- The multipart import takes a form field `force` beside the file, with the
  text `true` or `false`. Any other text is `400 INVALID_FIELD`.
- The check comes after every other one. A request that fails anyway (a path
  outside the root, a file that is not an analysis) fails as before, forced
  or not.
- A document without unsaved changes is replaced without the flag, as before.

**`POST /api/ai/cancel`** abandons the provider request in flight. Body:
`{requestId?}`. It answers `{cancelled: bool}`.

- The single AI slot is free at once: the next `chat`, `analyze` or `update`
  is accepted instead of `409 AI_BUSY`.
- The abandoned request is answered `409 AI_CANCELLED`.
- The provider's HTTP call is not interrupted. Its answer is dropped when it
  arrives: it is not added to the conversation (`GET /api/ai/conversation`),
  it proposes no changes, an `update` is not installed and no preview is
  kept.
- `chat`, `analyze` and `update` accept an optional `requestId` (a string of
  1 to 64 characters, chosen by the client). A cancel that names a
  `requestId` only abandons that request; `cancelled` is false when another
  request, or none, is in flight. Without `requestId` whichever request is
  in flight is abandoned.
- A request that timed out (`504 AI_TIMEOUT`) and still holds the slot can
  be abandoned too.
- It needs no provider and works unconfigured. It never changes the
  document.

**`GET /api/recovery`** lists the recovery copies left by a session that did
not end cleanly: `copies: [{id, title, savedAt, originalPath}]`, newest
first. `savedAt` is local time, ISO 8601 to the second. `originalPath` is
the file the document had been opened from or saved to, or null. The copy of
the running session, and of any other editor that is still running, is not
listed. The server's path of a copy is never reported.

**`POST /api/recovery/restore`** `{id, force?}` opens a listed copy.

- `id` is one of the ids `GET /api/recovery` lists. It is looked up in that
  listing and is never used as a path: anything else is `404 INVALID_FIELD`
  with `detail: {field: "id"}`, and the value is not echoed.
- The document is installed with `currentPath: null` and `dirty: true`, so
  `POST /api/file/save` answers `409 NO_CURRENT_PATH` and the client goes to
  Save As. The original file is not written.
- The answer is the usual document payload plus `restoredFrom: {title,
  savedAt, originalPath}` and `warnings`.
- Over unsaved changes it answers `409 UNSAVED_CHANGES` unless `force` is
  true.
- The copy is removed once it has been opened.

**`POST /api/recovery/discard`** `{id}` deletes a listed copy and answers
`{discarded: true}`. An id that is not listed is `404` and deletes nothing.

Recovery copies are written only by an editor started through the launcher
(`fta_web/run.py`, or the packaged app); an app built with `create_app()`
in a test writes none. They are kept in `recovery/` in the per-user folder
(`~/.fta_editor`). The file endpoints never reach into that folder, also
when the sandbox root contains it (the default root is the home folder): a
path into it is `400 PATH_REJECTED` with `detail.reason: "reserved"` for
open, save and listing.

**`POST /api/fs/root/choose`** lets the person at the computer choose
another sandbox root. **It takes no input.** A JSON body other than `{}`, a
form, an uploaded file, or a query parameter other than `lang` is `400
INVALID_FIELD` with `detail: {field: "body"}`, and no dialog is opened. The
server opens the operating system's folder chooser and waits for it:

| Answer | Meaning |
|---|---|
| `200 {changed: true, cancelled: false, root, currentPath, dirty, documentUntitled}` | The folder that was picked is the root now. It went through the same normalisation as `--root`. |
| `200 {changed: false, cancelled: true, root}` | The chooser was closed (or stayed open for 10 minutes). Nothing changed. |
| `501 PICKER_UNAVAILABLE` | No chooser can be opened here. `detail: {reason, relaunch}`; `relaunch` is the command that starts the editor on another folder. `reason` is one of `no_display`, `no_tkinter`, `packaged_without_tkinter`, `no_powershell`, `disabled`, `helper_failed`. |
| `409 PICKER_BUSY` | A chooser is already open. |
| `400 PATH_REJECTED` (`detail.reason: "not_a_directory"`) | What the chooser returned is not a usable folder. Nothing changed. |

- `documentUntitled` is true when the open document's file is outside the
  new root: `currentPath` is then null. The tree, the undo history and
  `dirty` are unchanged.
- The root is changed for the running session only.
- Setting the environment variable `FTA_EDITOR_NO_FOLDER_PICKER` (to any
  value) before the editor starts switches the chooser off (`reason:
  "disabled"`).
- On Windows the chooser is shown by Windows PowerShell; elsewhere, from
  source, by tkinter. The packaged app does not include tkinter, so on Linux
  and macOS it answers 501.

**`GET /api/fs/home`** also returns `canChooseRoot` (whether the endpoint
above can open a chooser on this computer) and `relaunch` (the command for
when it cannot).

### Several nodes in one request

Each of these is **one undo step**, checks every id before it changes
anything (a refusal leaves the document as it was), and answers with the
usual mutation payload. All need the session token.

Both batch requests read the tree once, whatever the number of ids: 4,800
ids on a 4,860-node tree take well under a second (9.4 s and 4.1 s in
1.8.0).

**`POST /api/batch/delete`** `{ids: [...]}` deletes each node with its
subtree. `deletedIds` are the nodes deleted directly (a listed node inside
another listed node goes with it); `removedLinks` as for `DELETE
/api/nodes/<id>`. `400 ROOT_PROTECTED`, `404 NODE_NOT_FOUND`,
`400 INVALID_FIELD` (`ids` not a non-empty list of strings, or more than
5000).

**`POST /api/batch/move`** `{ids: [...], newParentId, index}` moves the
nodes under one parent, side by side, in the order the tree showed them.
`index` is the position among the new parent's children once every moved
node is detached (clamped; null appends). Answers `movedIds` and
`parentId`. A move that leaves everything where it is makes no undo step.
`400 CYCLE_REJECTED`, `400 ROOT_PROTECTED`, `404 NODE_NOT_FOUND`,
`404 PARENT_NOT_FOUND`, `400 INVALID_FIELD` (also for a move that would go
deeper than the tree may be).

**`POST /api/batch/uncertainty`** `{ef}` (optional, default 3) gives every
basic event without an uncertainty distribution `quant.unc = {dist:
"lognormal", ef}`. Events that have one, house, undeveloped and conditioning
events, transfers, gates and the root are left alone. Answers `updatedIds`;
when it is empty nothing changed and no undo step was made.

**ETA mode in `GET /api/dot` and `POST /api/render`.** For a document in ETA
mode the DOT has no gate or event symbol nodes (symbols style: boxes joined
directly, `idMap` one entry per node) and no `Gate: ...` text (compact
style).

**`PATH_REJECTED` with `detail.reason: "outside_root"`** now also carries
`detail.root` (the sandbox root, which `/api/fs/home` gives too) and
`detail.relaunch`, the command that starts the editor on another folder:
`fta_editor.exe --root "<folder>"` in the packaged app,
`uv run python fta_web/run.py --root "<folder>"` from source. The root itself
is set only at launch; no endpoint changes it.

**The page (`GET /`)** fills the command that starts the editor again into its
"not connected" screen: the executable's file name in the packaged app, never
its folder, since this route answers without the token.

### Grid paste

**`POST /api/grid/paste`** applies a block pasted into the Grid tab. Needs the
session token. The browser reads the clipboard text with each field's own
parser and sends numbers; the server reads no text as a number.

```json
{ "revision": 41, "documentSerial": 2,
  "rows": [ { "clipRow": 1, "nodeId": "E00_00",
              "cells": { "lambda": 1e-06, "T": 8760, "source": "vendor data" } } ] }
```

- `revision` and `documentSerial` are the values the grid was drawn from
  (non-negative integers). `rows` holds 0 to 2,000 entries; `clipRow` is the
  1-based row of the clipboard (unique), `nodeId` is unique in the request.
- `cells` has keys from `id, name, model, lambda, T, tau, mu, q, source,
  tags`. An empty cell is left out, never sent as `""` or `null`. Numbers are
  JSON numbers in stored units: `lambda` and `mu` per hour (>= 0), `T` and
  `tau` in hours (> 0), `q` in [0, 1]. A number sent as a string, a bool or
  `null` is refused, never converted. The browser converts the unit of the
  λ header before sending (per year: divided by 8,760; FIT: times 1e-9), so
  `8.76` per year arrives as `0.001`. `model` is `fixed`, `rate`, `standby`
  or `repairable`. `tags` is one string, split on `;`, `；` and `、`. Text cells
  (`id`, `name`, `model`, `source`, `tags`) must be strings.
- Checks run in this order and nothing changes before they pass: a body that
  is not a JSON object, or holds `NaN` or `Infinity`, is `400 INVALID_JSON`; a
  wrong type, an unknown cell key or `model` name, a number out of range, a repeated `nodeId`
  or `clipRow` or more than 2,000 rows is `400 INVALID_FIELD`
  (`detail.field` names the key, `detail.clipRow` the row; for unknown cell
  keys `detail.field` is `cells` and `detail.fields` lists them; for a
  `rows` problem `detail.field` is `rows`); an ETA document is
  `409 MODE_UNSUPPORTED`; a `revision` or `documentSerial` that is not the
  document's is `409 STALE_REVISION` ("The analysis changed; paste again",
  `detail {revision, documentSerial}` with the current values).
- Per row, a refused row changes nothing and the other rows apply. Each
  refused cell is listed as `{clipRow, column, code, message}`: `NOT_BASIC_EVENT`
  (column `""`; not a leaf event, or the root, a house event or a transfer),
  `ID_MISMATCH` (`id` differs from the row's id; an equal `id` is ignored),
  `Q_COMPUTED` (`q` on a model other than `fixed` that differs from the
  computed value; an equal one is ignored), `NOT_USED` (a value for a field the
  row's model does not use: `lambda` on `fixed`, `T` unless `rate`, `tau`
  unless `standby`, `mu` unless `repairable`) and `INVALID_TEXT` (a name,
  source or tags text that cannot be saved, or an empty name). The refusals of
  one row are listed in table order. The `model` cell counts first, so a row
  may change the model and fill the new model's fields together. `message` is
  the server's English text; the browser words the reasons itself in the
  current language.
- Answer: `{ok, applied, refused, ...}` and the usual mutation payload
  (`tree`, `zeroNodes`, `dirty`, `canUndo`, `canRedo`, `analysis`,
  `sessionWarnings`, `revision`, `documentSerial`). `applied` counts rows with
  at least one cell written; a row holding only an equal `id` or an equal `q`
  is neither applied nor refused. Probabilities are recalculated once.
- The whole paste is **one undo step**. A paste that writes values already
  stored (or nothing) makes no undo step, keeps the redo history and does not
  mark the document modified.

### What-if

**`POST /api/whatif`** answers "what would the top event be if these basic
events had a factor on their main parameter?" for the What-if tab. Needs the
session token. It is a calculation on a private copy: it **never changes the
document, its `revision`, the undo or redo history, the modified flag, a file
or any other output** (Save, exports and the assistant's context do not see a
factor), and the server keeps nothing of the factors; the browser sends them
again with every request.

```json
{ "revision": 12, "documentSerial": 3,
  "factors": { "E00_01": 10, "E00_02": 0.5, "E00_03": 1 } }
```

- `revision` is required and `documentSerial` is optional (the browser always
  sends both); each is a non-negative integer, as for `POST /api/grid/paste`.
  `factors` is an object (it may be empty) of at most 1,000 entries,
  `{nodeId: factor}`. A factor is a JSON **number** from 0.01 to 100, both ends
  included; `10` and `10.0` are the same. A string (`"0.1"`), a bool, `null`, a
  list, `-0.1`, `0`, `0.009`, `101` and `1e999` are refused. A factor of 1
  means "no change" and is accepted.
- A factor multiplies the event's **main parameter**: λ for the models `rate`,
  `standby` and `repairable`, q for `fixed` (T, τ and μ are never scaled), the
  way Monte Carlo moves it. q then follows from the model and is **set to 1**
  when it would be higher (`clamped: true`). A rate event with λ = 1e-5 /h and
  T = 1,000 h at factor 10 goes from q = 0.00995017 to q = 0.0951626; a fixed
  event with q = 0.5 at factor 10 gives `param` 5, `q` 1, `clamped: true`.
- A factor on a member of an **applied CCF group** is a factor on the whole
  group: every member is scaled, the independent parts and the shared CCF event
  come from the CCF model's own probability function, and the other members
  come back as rows with `viaGroup: true`. Two members of one group with
  different factors (both not 1) are refused (`group_conflict`); a member with
  factor 1 next to a member with factor 10 means a group factor of 10. A group
  that is not applied (its status in the CCF groups tab) is ignored: its
  members are scaled one by one, and `cautions` says so (`CCF_NOT_APPLIED`).
- The top event uses the **headline's method**: the min-cut upper bound over
  the baseline cut sets with the changed products (always with an applied CCF
  group), the tree walk when the headline is the tree walk, and no number when
  the headline is incomplete. The cut sets are those of the nominal values,
  kept under the headline's own limits (the document's order, count and cutoff
  limits, and the headline's cap of 2,000 sets and 2 s). The top event uses the
  engine's q: the q of every model but `fixed` rounded to 12 significant
  digits, as the engine stores it. So, when the group status and the cut sets
  are the same, the result equals, to rounding, the headline of the same
  document with the scaled parameter typed in (the cut-set sum runs in the
  nominal rank order, so the last bits can differ). They differ when the factor
  changes the group status (a group not applied at baseline stays out of the
  what-if; see `cautions`), when the cutoff, the document's count limit or the 2,000-set cap
  decides which cut sets exist, and when a member is raised to 1; see "Limits
  of the what-if values" in the
  [User Guide](USER_GUIDE.md#the-what-if-tab). With no factor other than 1,
  `whatIf` is the baseline itself (the same number).
- Checks run in this order. Before the baseline is touched: a body that is not
  a JSON object, or holds `NaN`, `Infinity` or `-Infinity`, is
  `400 INVALID_JSON`; then `400 INVALID_FIELD` for `revision`
  (`detail.field: "revision"`), `documentSerial` (`"documentSerial"`),
  `factors` that is not an object or has more than 1,000 entries (`"factors"`)
  and a bad factor value (`detail.field: "factor"`, `detail.id` the node id);
  an ETA document is `409 MODE_UNSUPPORTED` (`detail.mode: "ETA"`); a
  `revision` or `documentSerial` that is not the document's is
  `409 STALE_REVISION` (`detail {revision, documentSerial}` with the current
  values; the browser then starts again from factor 1); then each id must be a
  basic event (`400 INVALID_FIELD`, `detail {field: "factors", id, reason}`
  with `reason` `unknown_event`, or `not_basic_event` for a gate, the root, a
  house event or a transfer). The last two checks run after the baseline has
  been built or found in memory, because they need the CCF groups and the
  models of the events: two members of one applied group with different
  factors are `400 INVALID_FIELD` with `detail {field: "factors", reason:
  "group_conflict", groupId, ids}`; and an event with a factor other than 1
  whose model lacks a parameter (or whose scaled parameter is not a finite
  number) is `422 WHATIF_NOT_EVALUABLE` with `detail {id, missing}`. Even a
  request that ends in one of these two errors has built (or used) the
  baseline.

Answer (200):

```json
{ "ok": true, "revision": 12, "documentSerial": 3,
  "baseline": 0.000100809919, "whatIf": 0.001080919, "ratio": 10.72234766898285,
  "method": "mcub", "note": null, "truncatedBy": [], "cautions": [],
  "cache": "hit", "baselineMs": 0.0,
  "groups": [ { "id": "g1", "name": "Feed pumps", "model": "beta", "members": ["A", "B"] } ],
  "events": [ { "id": "A", "name": "Pump A", "model": "fixed", "paramKey": "q",
                "nominalParam": 0.001, "param": 0.01, "nominalQ": 0.001, "q": 0.01,
                "clamped": false, "factor": 10.0, "groupId": "g1",
                "viaGroup": false, "evaluable": true } ] }
```

The answer above is for the request `{"revision": 12, "documentSerial": 3,
"factors": {"A": 10}}` on a document whose fixed events A and B (q = 0.001
each) sit under an AND gate and form the beta group `g1` (β = 0.1); its
`events` list also holds the row of member B (`viaGroup: true`), which is cut
here.

- `baseline` is the headline of the document with no factor, the number
  `GET /api/analysis/summary` returns. `whatIf` is the top event with the
  factors. `ratio` is `whatIf / baseline`; it is `1.0` when both are 0 and
  `null` when the baseline is 0 and `whatIf` is above 0, when either number is
  `null`, or when the quotient is not finite.
- `method` is the headline's method, verbatim: `mcub`, `treeWalk` or
  `incomplete`. `incomplete` happens only with an applied CCF group whose cut
  sets could not be completed (time, an error, or the headline's own cap of
  2,000 sets); then `baseline`, `whatIf` and `ratio` are `null` and `note` is
  `"incomplete"`, and the event rows are still returned. A cut-set list that
  an order or count limit of the document shortened still gives a number.
- `note` is one machine-readable value or `null`: `"incomplete"` as above, or
  `"cutsets_from_nominal"` when the method is `mcub` and the cutoff left out
  cut sets that have a probability above 0 at nominal values (a set that would
  pass the cutoff only after a factor is not in the what-if number; the tab
  says "cut sets from nominal values"). `truncatedBy` is the baseline's list of
  the **document's** limits that cut the cut sets short (`order`, `count`,
  `cutoff`; `time` or `error` when they could not be completed) and is for
  diagnostics; only the cutoff gives a note. The headline's own cap of 2,000
  sets is **not** listed there, and the response has no `capped` field: without
  an applied group the cap adds nothing to `truncatedBy` or `note`, so read
  `capped` from `GET /api/analysis/summary`. The document's own limits still
  appear: `order`, `count` (only when the document's count limit is 2,000 or
  less; above that the cut is the cap) and `cutoff`, which with an `mcub`
  headline also gives the note `cutsets_from_nominal`. An applied group whose
  cut sets were capped gives the note `incomplete`. With an `mcub` headline, a
  factor on an event only in cut sets that the order limit, the count limit or
  the cap left out changes nothing (`ratio` 1.0); `note` does not say so, but
  `cautions` does (`CUTSETS_TRUNCATED`, below). An order limit or the cutoff
  only drops sets, so the headline reads below
  the full MCUB, though it can still be above the exact value; a count limit or
  the cap usually reads low too but works inside each gate, so on a tree with
  repeated events (a shared CCF event counts as one) it can also read high.
  Treat it as an estimate, not a bound.
- `cautions` is a list (always present, `[]` when nothing applies) of
  machine-coded cautions about the **what-if values**, worked out for each
  request from data the endpoint already holds (nothing is stored, so a cache
  hit and a miss answer the same list). It follows three of the warnings a
  typed document gets (`CCF_Q_ONE`, `CCF_HIGH_Q`, `STANDBY_LARGE_LT`, but not
  `RATE_IMPLAUSIBLE`) and adds two cautions of its own, `CCF_NOT_APPLIED` and
  `CUTSETS_TRUNCATED`; it is independent of `note`. At most one entry per
  code, in this order:
  `{"code": "CCF_NOT_APPLIED", "groupIds": ["g3"]}` (a factor other than 1 sits
  on a member of a CCF group that is not applied at baseline, whatever the
  reason; the what-if scales that member alone, with no CCF event; no
  `limit`),
  `{"code": "CCF_Q_ONE", "groupIds": ["g1"]}` (an applied group that the
  request scales has a member with q of 1 or more; typed into a document, the
  group would not be applied; `>=`),
  `{"code": "CCF_HIGH_Q", "groupIds": ["g2"], "limit": 0.01}` (the same kind of
  group, not listed under `CCF_Q_ONE`, whose largest member `Q_t` is above
  `limit`, the editor's high-q threshold; strict `>`),
  `{"code": "STANDBY_LARGE_LT", "eventIds": ["S1"], "limit": 0.2}` (a
  **scaled** standby row, including the `viaGroup` ones, has λ'·τ above
  `limit`, with λ' the scaled λ before any clamp; strict `>`; it is λτ, not
  λτ/2) and
  `{"code": "CUTSETS_TRUNCATED", "by": ["order", "count"]}` (the method is
  `mcub` and the document's order limit or count limit, or the headline's own
  cap of 2,000 sets, cut the cut sets short; `by` lists `order` and `count`
  in that order, and the cap counts as `count`). `groupIds` follow the order of
  `groups` (for `CCF_NOT_APPLIED`, the order of the groups in the document, and
  `groupIds` may be `[]` when the group's id is missing or empty); `eventIds`
  follow the order of `events`. The cutoff alone gives no
  caution (it is the note `cutsets_from_nominal`), nor does a tree-walk or
  `incomplete` headline give `CUTSETS_TRUNCATED`. **No factor other than 1
  gives `[]`**: a document that already warns at nominal values is silent until
  a factor is set, and a group that is not applied is never listed under
  `CCF_Q_ONE` or `CCF_HIGH_Q`; its members give `CCF_NOT_APPLIED`. An entry
  holds ids and the threshold only, no value of the user's data. Example for
  the document above with `{"A": 20}`:
  `"cautions": [{"code": "CCF_HIGH_Q", "groupIds": ["g1"], "limit": 0.01}]`.
- `groups` lists every applied CCF group (always present, `[]` when none).
- `events` has one row per entry of `factors`, in request order, then, when a
  requested member of an applied group has a factor other than 1, the other
  members of that group in group order with `viaGroup: true`. A row has
  `id`, `name`, `model`, `paramKey` (`"lambda"` per hour, or `"q"`),
  `nominalParam` and `param` (the main parameter before and after the factor,
  before any clamp), `nominalQ` and `q` (the event's total probability; for a
  CCF member its `Q_t`), `clamped` (the unclamped q is above 1; also true at
  factor 1 for a standby event whose λτ/2 is above 1), `factor` (the effective
  factor, 1 when unchanged), `groupId` (the applied group, else `null`),
  `viaGroup` and `evaluable`. An event with factor 1 whose model lacks a
  parameter gets a row with `evaluable: false` and `null` numbers; the same
  event with a factor other than 1 is the 422 above. Numbers are plain JSON
  numbers and are not rounded.
- **Speed.** The baseline (cut sets, the q of every event, the CCF plan) is
  computed once per document version and kept (one entry; a new `revision` or
  `documentSerial`, or any difference in the document, replaces it), except
  that a baseline whose summary ran out of time is not kept, so every call
  then builds it again and answers `"cache": "miss"`. The first call after an
  edit builds it (`"cache": "miss"`); `baselineMs` is the time of the
  headline's summary inside that build, not of the whole call, and `0.0` on a
  hit. Later calls (`"cache": "hit"`) do the work of the factors only: with the
  `mcub` method they recompute the cut sets that hold a changed event, with the
  `treeWalk` method they walk a copy of the whole tree again. On the 301-node
  test file (252 basic events, ten CCF groups, method `mcub`) a call with the
  baseline in memory answers in well under 300 ms (about 1 ms in-process).

### File browser: `ext` filter

`GET /api/fs/list` takes an optional `ext` query parameter: a comma-separated
list of extensions such as `?ext=.csv,.xlsx`. The leading dot is optional and
case is ignored.

- By default only `.json` files are listed, as in 1.6.
- Accepted values are the allow-list `config.LISTABLE_EXTENSIONS`: `.json`,
  `.csv` and `.xlsx`. Anything else is `400 INVALID_FIELD` with
  `detail: {field: "ext", value}`.
- The parameter only changes what is **listed**. The endpoint that reads the
  file (`/api/file/open`, `/api/fmea/*`) still decides what may be opened.
- The FMEA tab's file dialog uses `?ext=.csv,.xlsx`.

### Excel export

`GET /api/export/xlsx[?sigFigs=N]` writes the 1.6 `FTA` sheet, plus
an **Events** sheet (one row per node; the columns are
`excel_events.EVENT_COLUMNS`) and an **Analysis** sheet (settings and, in FTA
mode, the headline figures; for a file with CCF groups also the rows
`CCF groups applied` and `CCF groups not applied`, each with the number of
groups and, in the note column, their names and the reasons). `sigFigs` sets the scientific number format of
the probability cells; it is clamped to 1–6, and a missing or unparseable
value gives 3. The UI sends the top bar's significant-figures setting.
Text stays text in every sheet: a value that starts with `=` (a node named
`=HYPERLINK(…)`, say) is never written as a formula. This export, the XML
export and the DOCX report drop the characters XML cannot hold (C0 control
characters other than tab, line feed and carriage return); the
whitespace-like ones become a space. The document is not changed.

The Events sheet's *Calculated probability* is the tree-walk value of every
node (CCF exception below). When the headline is the MCUB
(`engine.root_headline`), the root's cell in that column carries a comment
with the headline, and the Analysis sheet's *Tree walk* row is noted as the value the Events sheet shows for the top
event (1.7.3). `POST /api/report/docx` draws its own diagram with the root's
headline label and puts a sentence under the picture.

**CCF groups (1.9).** With at least one group applied, a gate above a member
of a group shows its MCUB instead of its tree-walk value: in the `FTA` sheet's
`Calc:` text as `<value> (MCUB, CCF)` and in the Events sheet's *Calculated
probability* as the number. When the cut sets are incomplete, both show
`n/a (CCF)`, and the Events cell has a comment that says why. A member keeps
its `Q_t`. `POST /api/report/docx` writes a CCF section after Assumptions for
a file with groups (also in ETA mode) and a sentence under the diagram about
the gate values.

### New error codes

| Code | HTTP | When | `detail` |
|---|---|---|---|
| `MODE_UNSUPPORTED` | 409 | An analysis or FMEA endpoint, `POST /api/grid/paste` or `POST /api/whatif`, on an ETA document | `{mode: "ETA"}` |
| `BUSY` | 409 | A Monte Carlo run is already in progress | `{}` |
| `ANALYSIS_TOO_LARGE` | 422 | A voting gate over 20,000 combinations, or the cut-set time budget ran out | `{reason: "kofn"\|"time", nodeId?, k?, n?, combinations?, limit?}` |
| `EXPORT_UNAVAILABLE` | 503 | An optional package is missing: `python-docx` for the report, `openpyxl` for xlsx export or FMEA import | `{format, package, install, feature?}` |
| `AI_DOCUMENT_CHANGED` | 409 | `POST /api/ai/update` finished, or `POST /api/ai/update/apply` was called, after the document was edited, undone, replaced by New or opened from another file | none |
| `AI_UPDATE_EXPIRED` | 409 | `POST /api/ai/update/apply` with an `id` that is not the previewed rewrite still waiting | none |
| `AI_CANCELLED` | 409 | The AI request was abandoned by `POST /api/ai/cancel` while it was waiting for the provider | none |
| `UNSAVED_CHANGES` | 409 | New, Open, an example, an import or a recovery restore over unsaved changes without `force` | none |
| `PICKER_UNAVAILABLE` | 501 | `POST /api/fs/root/choose` where no folder chooser can be opened | `{reason, relaunch}` |
| `PICKER_BUSY` | 409 | `POST /api/fs/root/choose` while a chooser is already open | none |
| `STALE_REVISION` | 409 | `POST /api/grid/paste` or `POST /api/whatif` with a `revision` or `documentSerial` other than the document's | `{revision, documentSerial}` (current) |
| `WHATIF_NOT_EVALUABLE` | 422 | `POST /api/whatif` with a factor other than 1 on an event whose model lacks a parameter, or whose scaled parameter is not a finite number | `{id, missing}` |
| `GROUP_NOT_FOUND` | 404 | `PATCH` or `DELETE /api/ccf/groups/<id>` with an id no stored group has | `{groupId}` |

Messages for these codes are localised like every other error. The English
text is the server's own message; `fta_web/i18n.py` supplies the Japanese:

- `BUSY` has a Japanese text.
- `STALE_REVISION` has a Japanese text, the same words as the Grid tab's own
  summary of a stale paste (「解析が変更されました。もう一度貼り付けてください」).
- `ANALYSIS_TOO_LARGE` has one generic text, plus specific texts keyed on
  `detail.reason` (`kofn`, `time`).
- The DOCX `EXPORT_UNAVAILABLE` message gives the install command
  `uv sync --extra report`.
- The FMEA `.xlsx` case (`detail.feature: "fmea"`) has its own message that
  suggests saving the sheet as CSV instead.

**Session warnings from deletes.** Each `DELETE /api/nodes/<id>` returns
`removedLinks` and adds a `LINKS_REMOVED` session warning for every link it
stripped. These appear in `sessionWarnings` and in the Validation issues.
They belong to the delete: `POST /api/undo` (which restores the links)
removes them, and `POST /api/redo` brings them back.

- A `transferTo` that names a deleted node is removed too and reported the
  same way, with `relation: "TRANSFER"` (`{nodeId, targetId, relation}`). The
  node stays a TRANSFER gate without a target (value 0, `TRANSFER_MISSING`).
  Deleted ids can be handed out again, so a kept reference would silently
  point at the next new node.
- The AI paths do the same: a `delete` change applied through
  `POST /api/ai/changes/apply` and a full `POST /api/ai/update` strip links
  and `transferTo` into the ids they removed, with the same `LINKS_REMOVED`
  notices.

### Robustness

- **Strict JSON responses.** Python reads `NaN` and `Infinity` from request
  bodies and document files, but the browser's `JSON.parse` rejects them.
  Every response is strict JSON: a non-finite number (in a loaded tree, or in
  an error's `detail.value`) is sent as `null`.
- **Load errors.** `/api/file/open` reports a file that cannot be read
  (`400 INVALID_JSON`, `detail.reason: "load_failed"`) as *the file is
  empty*, *not valid JSON (line L, column C: …)*, *JSON root must be an
  object*, or *not text in a supported encoding (UTF-8, Shift_JIS, cp1252)*,
  instead of the core's generic encoding error.
- **Windows path hardening** (`fsbrowser.py`, `PATH_REJECTED`):
  - A `:` after the drive is refused (`reason: "stream"`), so
    `notes.txt:x.json` cannot write an NTFS alternate data stream.
  - A path on another drive or share is refused lexically, *before* it is
    resolved (`reason: "outside_root"`). Resolving a UNC path
    (`\\host\share\x.json`) would open an SMB connection to the named
    host. Device-namespace forms (`\\?\`, `\\.\`) and a drive letter that
    `subst` maps onto the root folder are refused the same way.
- **OS refusals** are `PATH_REJECTED` too, not 500s. A save the OS will not
  write (a read-only folder, a file another program holds open) has
  `reason: "unwritable"` and a folder it will not list `reason: "unreadable"`,
  each 403 when permission is denied and 400 otherwise; a path that cannot be
  resolved, such as a symlink loop, is `reason: "unresolvable"` (400). A
  symlink loop inside a folder is left out of its listing.
- **Numerics.** A PAND gate with more than 170 inputs is computed in log
  space (171! does not fit a float), and Monte Carlo samples an extreme error
  factor in log space, clamped below the float ceiling, instead of
  overflowing.
- **Malformed bodies.** An integer beyond the float range is "not finite"
  (`400 INVALID_FIELD` with its field), and a body nested too deeply to parse
  is `400 INVALID_JSON`. `POST /api/new` forces only on a real boolean
  `force: true`; any other non-null value is `400 INVALID_FIELD`.

---

## Python analysis modules (1.7)

These are flat modules in `fta_web/`, and each takes and returns plain dicts.
Import them with `fta_web/` on `sys.path`, or as `fta_web.<module>`. None of
them modifies the tree it is given.

```python
import sys; sys.path.insert(0, "fta_web")
import engine
from engine import WebCore, summary
import cutsets, importance, uncertainty, lint

core = WebCore()                         # FTACore subclass; the core itself is not edited
core.load_from_json("plant.json")        # also reads the `analysis` block
core.set_analysis({"missionTime": 17520})  # validated deep merge; raises engine.AnalysisError
core.recalculate_probabilities()
tree, analysis = core.get_data(), core.get_analysis()

summary(tree, analysis)                  # {treeWalk, mcub, rareEvent, headline, headlineMethod, ...}
engine.root_headline(summary(tree, analysis))  # {method: "mcub", value, treeWalk} or None (1.7.3)
cs = cutsets.compute(tree, analysis, {"maxOrder": 4})   # may raise cutsets.CutsetError
importance.compute(cs)                   # [{id, name, q, fv, birnbaum, raw, rrw, rrwInfinite, cutSetCount}]
uncertainty.run(tree, analysis, n=10000, seed=1, time_limit=30.0)
lint.run(tree, analysis, session_warnings=[], mode="FTA",     # as GET /api/analysis/validate:
         extra={"cutsets": cutsets.truncation_signal(tree, analysis)})  # document's own limits
core.save_to_json("plant.json")          # writes `analysis` beside `tree`
```

- `WebCore` overrides only `_recalculate_fta_probabilities`, `load_from_json`
  and `prepare_export_data`.
- `core.quant_warnings` holds the last recalculation's `{code, nodeId, params}`
  warnings.
- `engine.derive_quant(node, analysis)` evaluates one node's model.
- `engine.summary_with_cut_sets(tree, analysis)` returns `(summary, cut_sets)`:
  the summary and the `cutsets.compute` result it came from (`None` when the
  cut sets failed), from one expansion.
- `diagram_dot.document_dot(core, lock=None, **options)` returns
  `(dot, id_map, root_headline)`; `diagram_dot.build_dot_text2(core, ...,
  root_headline=None)` draws a tree with the headline it is given.
- `engine.kofn_probability(probs, k)` and `engine.xor_probability(probs)` are
  the gate formulas.
- The CLI (`fta_web/cli.py`) is a thin wrapper over these functions. See the
  [User Guide](USER_GUIDE.md#command-line-interface).

## FTACore Class

Main class for fault tree and event tree analysis operations.

The core modules import each other by bare name, so put the web app's copy,
`fta_web/core/` (the one with the documented fixes), on `sys.path`. The
examples below assume this was done.

### Constructor

```python
import sys
sys.path.insert(0, "fta_web/core")   # run from the repository root
from FTA_Editor_core import FTACore

core = FTACore()
```

Initializes with default root node and metadata.

### Metadata Methods

#### `set_metadata(title=None, date=None, mode=None)`

Set analysis metadata.

**Parameters**:
- `title` (str, optional): Analysis title
- `date` (str, optional): Analysis date
- `mode` (str, optional): "FTA" or "ETA"

**Example**:
```python
core.set_metadata(
    title="Server Reliability Analysis",
    date="2025-10-31",
    mode="FTA"
)
```

#### `get_metadata()`

Get current metadata.

**Returns**: dict with keys `title`, `date`, `mode`

**Example**:
```python
metadata = core.get_metadata()
print(f"Mode: {metadata['mode']}")
```

### Data Management Methods

#### `get_data()`

Get the current tree data structure.

**Returns**: dict - Complete tree structure

**Example**:
```python
tree = core.get_data()
print(f"Root: {tree['name']}")
```

#### `set_data(data)`

Set the tree data structure.

**Parameters**:
- `data` (dict): Complete tree structure

**Example**:
```python
tree_data = {
    "id": "root",
    "name": "System Failure",
    "type": "Root",
    "probability": 0.5,
    "logicGate": "OR",
    "children": [],
    "links": []
}
core.set_data(tree_data)
```

### Node Operations

#### `add_node_to_data(parent_id, new_node)`

Append a node as the last child of the specified parent.

**Parameters**:
- `parent_id` (str): ID of parent node
- `new_node` (dict): The node, stored as given. Nothing is validated and no
  ID is generated, so give it a unique `id` and the usual keys. If no node
  has `parent_id`, nothing happens.

**Returns**: None

**Example**:
```python
core.add_node_to_data("root", {
    "id": "root_0",
    "name": "Hardware Failure",
    "type": "Event",
    "probability": 0.1,
    "logicGate": "OR",
    "children": [],
    "links": []
})
core.recalculate_probabilities()
```

#### `update_node(node_id, updates)`

Update an existing node.

**Parameters**:
- `node_id` (str): ID of node to update
- `updates` (dict): Fields to update

**Returns**: bool - True if the node was found and updated

**Example**:
```python
found = core.update_node("root_0", {
    "name": "Updated Name",
    "probability": 0.15
})
```

#### `delete_node_from_data(node_id)`

Delete a node and all its children. Links that point into the deleted
subtree are not removed.

**Parameters**:
- `node_id` (str): ID of node to delete

**Returns**: None

**Example**:
```python
core.delete_node_from_data("root_0_1")
```

#### `find_node_by_id(node_id)`

Find and return a node by its ID.

**Parameters**:
- `node_id` (str): Node ID to find

**Returns**: dict or None - Node data if found

**Example**:
```python
node = core.find_node_by_id("root_0")
if node:
    print(f"Found: {node['name']}")
```

### Probability Calculations

#### `recalculate_probabilities()`

Recalculate all node probabilities based on current mode.

**Note**: Automatically called after loading data. Call manually after modifications.

**Example**:
```python
core.recalculate_probabilities()
```

#### `get_zero_probability_nodes()`

Get list of node IDs with zero probability.

**Returns**: list of str - Node IDs

**Example**:
```python
zero_nodes = core.get_zero_probability_nodes()
print(f"Zero probability nodes: {zero_nodes}")
```

### File I/O Methods

#### `load_from_json(file_path)`

Load tree data from JSON file.

**Parameters**:
- `file_path` (str): Path to JSON file

**Returns**: tuple (success: bool, error: str or None)

**Supports**: Both new format (with metadata) and legacy format

**Example**:
```python
success, error = core.load_from_json("data/analysis.json")
if not success:
    print(f"Error: {error}")
```

#### `save_to_json(file_path=None)`

Save tree data to JSON file with metadata.

**Parameters**:
- `file_path` (str, optional): Path to save. If None, uses last loaded file.

**Returns**: tuple (success: bool, error: str or None)

**Example**:
```python
success, error = core.save_to_json("output.json")
```

#### `export_to_xml(file_path)`

Export tree to XML format.

**Parameters**:
- `file_path` (str): Path for XML file

**Returns**: tuple (success: bool, error: str or None)

**Example**:
```python
success, error = core.export_to_xml("output.xml")
```

#### `export_to_excel(file_path)`

Export tree to hierarchical Excel format.

**Parameters**:
- `file_path` (str): Path for Excel file

**Returns**: tuple (success: bool, error: str or None)

**Features**: Hierarchical columns, color coding, auto-widths

**Example**:
```python
success, error = core.export_to_excel("output.xlsx")
```

## Complete Usage Example

```python
import sys
sys.path.insert(0, "fta_web/core")
from FTA_Editor_core import FTACore

# Initialize
core = FTACore()

# Set metadata
core.set_metadata(
    title="Nuclear Plant Safety Analysis",
    date="2025-10-31",
    mode="ETA"  # Event Tree Analysis
)

# Build tree structure
tree = {
    "id": "root",
    "name": "Loss of Coolant",
    "type": "Root",
    "probability": 0.001,  # Initiating event probability
    "logicGate": "OR",
    "children": [
        {
            "id": "branch1",
            "name": "ECCS Activates",
            "type": "Event",
            "probability": 0.99,
            "logicGate": "OR",
            "children": [
                {
                    "id": "outcome1",
                    "name": "Core Cooled",
                    "type": "Event",
                    "probability": 0.98,
                    "logicGate": "OR",
                    "children": [],
                    "links": []
                },
                {
                    "id": "outcome2",
                    "name": "Partial Cooling",
                    "type": "Event",
                    "probability": 0.02,
                    "logicGate": "OR",
                    "children": [],
                    "links": []
                }
            ],
            "links": []
        },
        {
            "id": "branch2",
            "name": "ECCS Fails",
            "type": "Event",
            "probability": 0.01,
            "logicGate": "OR",
            "children": [
                {
                    "id": "outcome3",
                    "name": "Core Meltdown",
                    "type": "Event",
                    "probability": 1.0,
                    "logicGate": "OR",
                    "children": [],
                    "links": []
                }
            ],
            "links": []
        }
    ],
    "links": []
}

core.set_data(tree)

# Calculate probabilities
core.recalculate_probabilities()

# Access results
root = core.get_data()
print(f"Root calculated probability: {root['calculatedProbability']}")

# Access specific outcome
outcome1 = core.find_node_by_id("outcome1")
print(f"Core Cooled probability: {outcome1['calculatedProbability']}")
# In ETA mode: 0.001 × 0.99 × 0.98 = 0.00097

# Export results
core.save_to_json("analysis.json")
core.export_to_excel("analysis.xlsx")
core.export_to_xml("analysis.xml")

# Check for zero probability nodes
zero_nodes = core.get_zero_probability_nodes()
if zero_nodes:
    print(f"Warning: Zero probability nodes: {zero_nodes}")
```

## Data Structure Reference

### Node Structure

```python
{
    "id": "unique_id",              # Unique identifier
    "name": "Node Name",            # Display name
    "type": "Event",                # Node type
    "probability": 0.5,             # Base probability (0.0-1.0)
    "calculatedProbability": 0.3,   # Calculated (read-only)
    "logicGate": "OR",              # "AND" or "OR"
    "notes": "Description",         # Optional notes
    "children": [],                 # List of child nodes
    "links": [                      # Links to other nodes
        {
            "target_id": "other_node",
            "relation": "AND"       # "AND" or "OR"
        }
    ]
}
```

### Metadata Structure

```python
{
    "title": "Analysis Title",
    "date": "2025-10-31",
    "mode": "ETA"  # "FTA" or "ETA"
}
```

### JSON File Format

```python
{
    "title": "Analysis Title",
    "date": "2025-10-31",
    "mode": "ETA",
    "tree": {
        # Node structure as above
    }
}
```

A file with CCF groups (1.9) also has the top-level key `"fileFormatVersion": 2`
and the groups under `analysis.ccfGroups`; see
[CCF.md](CCF.md#the-file-format). A file without groups has neither.

## Error Handling

The file methods (`load_from_json`, `save_to_json`, `export_to_xml`,
`export_to_excel`) return tuples `(success, error)`:

```python
success, error = core.save_to_json("output.json")
if not success:
    print(f"Error occurred: {error}")
else:
    print("Success!")
```

## Helper Functions

### `sanitize_name(s)`

Remove extra whitespace from strings.

**Parameters**:
- `s` (str): String to sanitize

**Returns**: str - Sanitized string

**Example**:
```python
from FTA_Editor_core import sanitize_name

clean = sanitize_name("  Spaced   Text  ")
# Returns: "Spaced Text"
```

## Constants

`ROOT_ID = "root"`: the id of the top-level node. `load_from_json` renames
any other top-level id to it and records the change in `last_load_warnings`.

## Thread Safety

FTACore is **not** thread-safe. Use separate instances for concurrent operations.

## Performance Notes

- Tree traversal is recursive - very deep trees may hit recursion limits
- Probability recalculation is memoized - efficient for large trees
- Circular reference detection prevents infinite loops

---

## AIAgentHandler Class

New in v1.5.0. Handles AI assistant functionality.

### Constructor

```python
from AI_agent_handler import AIAgentHandler   # fta_web/core on sys.path, as above

handler = AIAgentHandler()
```

### Methods

#### `is_configured()`

Check if AI credentials are set up.

**Returns**: bool

```python
if handler.is_configured():
    print("AI is ready")
```

#### `configure(api_key, api_endpoint, model, provider)`

Configure AI credentials.

**Parameters**:
- `api_key` (str): The provider's API key
- `api_endpoint` (str): API endpoint URL (default: "https://api.openai.com/v1")
- `model` (str): Model name (default: "gpt-4o")
- `provider` (str): "OpenAI" (default), "Anthropic Claude", "Google Gemini"
  or "Microsoft Copilot"

**Returns**: tuple (success, error_message)

```python
success, error = handler.configure(
    api_key="sk-...",
    api_endpoint="https://api.openai.com/v1",
    model="gpt-4o",
    provider="OpenAI"
)
```

#### `set_fta_context(fta_data, mode, title)`

Set the FTA context for AI analysis.

**Parameters**:
- `fta_data` (dict): Current FTA data structure
- `mode` (str): "FTA" or "ETA"
- `title` (str): Analysis title

```python
handler.set_fta_context(
    core.get_data(),
    core.mode,
    core.title
)
```

#### `send_message(user_message, include_fta_context=True)`

Send a message to the AI and get a response.

**Parameters**:
- `user_message` (str): User's message
- `include_fta_context` (bool): Include FTA context in first message

**Returns**: tuple (response_text, list of AIProposedChange)

```python
response, changes = handler.send_message(
    "What root causes might be missing?"
)
print(response)
for change in changes:
    print(f"Proposed: {change.description}")
```

#### `get_quick_analysis(fta_data, mode, title)`

Get a quick AI analysis of the current FTA.

**Returns**: tuple (analysis_text, proposed_changes)

```python
analysis, changes = handler.get_quick_analysis(
    core.get_data(), "FTA", "My Analysis"
)
```

#### `clear_conversation()`

Reset conversation history.

```python
handler.clear_conversation()
```

---

## AICredentialManager Class

Manages API credentials storage.

### Credential Location

Credentials are stored at:
- Windows: `C:\Users\<username>\.fta_editor\ai_credentials.json`
- macOS/Linux: `~/.fta_editor/ai_credentials.json`

### Methods

#### `save_credentials(api_key, api_endpoint, model, provider)`

Save credentials to local storage. One provider's credentials are stored at a
time; saving replaces them.

**Returns**: tuple (success, error_message)

#### `load_credentials()`

Load credentials from local storage.

**Returns**: tuple (credentials_dict or None, error_message or None)

#### `delete_credentials()`

Delete stored credentials.

**Returns**: tuple (success, error_message)

#### `has_credentials()`

Check if credentials file exists.

**Returns**: bool

---

## FTAStructureAnalyzer Class

Utilities for converting FTA data to text format for AI.

### Static Methods

#### `fta_to_text(fta_data, mode, title, indent=0)`

Convert FTA data to human-readable text.

**Parameters**:
- `fta_data` (dict): FTA data structure
- `mode` (str): "FTA" or "ETA"
- `title` (str): Analysis title
- `indent` (int): Current indentation level

**Returns**: str - Formatted text representation

```python
from AI_agent_handler import FTAStructureAnalyzer

text = FTAStructureAnalyzer.fta_to_text(
    core.get_data(), "FTA", "My Analysis"
)
print(text)
```

#### `get_summary(fta_data, mode)`

Get a brief summary of the FTA.

**Returns**: str - Summary text

---

For examples, see `fta_web/tests/`, `fta_web/examples/` and the legacy `desktop/tests/`.
