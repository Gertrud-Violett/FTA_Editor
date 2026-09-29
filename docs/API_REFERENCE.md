# API Reference

**Version**: 1.7.0 | **Updated**: September 28, 2026

Complete API documentation for programmatic use of FTA/ETA Editor.

## Overview

This document covers:
- **The web app's HTTP API, 1.7 additions**: [below](#http-api-17-additions).
  The 1.6 endpoints are specified in [V1.6_WEB_SPEC.md §5](V1.6_WEB_SPEC.md#5-http-api).
- **The 1.7 Python analysis modules** (`WebCore`, cut sets, importance,
  uncertainty, lint): [below](#python-analysis-modules-17).
- **FTACore**: Core business logic for FTA/ETA operations
- **AIAgentHandler**: AI assistant integration (new in v1.5)
- **FTAStructureAnalyzer**: FTA data conversion utilities

---

## HTTP API (1.7 additions)

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
- Unknown sub-keys are a 400 whose `detail.fields` lists them.

`logicGate` stays AND/OR, and it is always the projection of `gateType`:

- INHIBIT and PAND project to AND.
- KOFN, XOR and TRANSFER project to OR.

When a loaded file (or an AI update) has a `gateType` that does not project
to its `logicGate` (the 1.6 desktop app edits only `logicGate`), `logicGate`
wins: `gateType`, `k` and `transferTo` are removed from that node and a
`LOAD_REPAIR` session warning is recorded with `kind: "gate_type_reset"` and
`params` `{old_id, new_id, name, gateType, logicGate, dropped, cause, message}`.
`cause` is `"desktop"` for a loaded file and `"ai"` for an AI edit
(`POST /api/ai/update`, `POST /api/ai/changes/apply`), and the message says
which. A notice with `cause: "ai"` belongs to that edit: undoing the AI update
removes it and redo brings it back.

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
  `gate_type_reset` notices of an AI edit (`params.cause: "ai"`) -- are undone
  and redone with that edit. At most 500 are kept.
- `capabilities.reportExport`: whether `python-docx` is installed.
- `capabilities.fmeaXlsx`: whether `openpyxl` is installed, which `.xlsx`
  FMEA import needs.

**Mutation payload.** Every endpoint that changes the document returns
`tree, zeroNodes, dirty, canUndo, canRedo`, and now also `analysis` and
`sessionWarnings`.

### Nodes: new fields and PATCH semantics

`GET /api/nodes/<id>`, and the `node` returned by create and PATCH, carry:

- every key of the table above: the raw value, or `null` when absent;
- `quantDerived: {q, model, formula, formulaKey, params, warnings}`.
  - `q` is the derived probability, or `null` when the model cannot be
    evaluated.
  - `params` holds the resolved inputs. A `T` taken from the mission time
    is marked `TFromMission: true`.
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

```http
PATCH /api/nodes/root_0_1
{"quant": {"model": "rate", "lambda": 2.5e-6}, "trace": {"tags": ["pump"]}}
```

**AI update** (`POST /api/ai/update`): a full-tree AI rewrite usually drops
the 1.7 keys. They are restored by node id wherever the new tree lacks them,
and the response includes `mergedFields`, the number of fields restored.
`gateType` and `k` are restored only while they still project to the node's
new `logicGate`.

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
- `message` is English. The UI localises it with `val.code.<CODE>` and
  `params`.
- The codes and their severities are listed in the
  [User Guide](USER_GUIDE.md#validation) and in `fta_web/lint.py`.

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

Body `{path, sheet?}`. `path` is a server-side path chosen through the file
dialog. It gets the same root, traversal and symlink checks as
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

`rows` holds at most the first 50 rows. `occurrenceTable` is the document's
table; `defaultOccurrenceTable` is the AIAG default.

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
  others become new leaf events under `parentId`.
- An `occurrenceTable` that differs from the document's is saved into
  `analysis.fmeaOccurrenceTable` in the same undo step.

The response is the mutation payload plus:

```json
{"created": ["root_2_0"], "updated": ["root_0_1"], "unchanged": [],
 "skipped": [{"row": 7, "fmeaId": "P-07", "reason": "invalidRank", "field": "occurrence",
              "value": 12, "message": "..."}],
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
the three values and adds `idMap`:

```json
{"ok": true, "dot": "digraph G {...}", "renderer": "wasm", "style": "symbols",
 "rankdir": "TB", "sigFigs": 3,
 "idMap": {"root": "root", "root__gate": "root", "root_0_1": "root_0_1", "root_0_1__event": "root_0_1"}}
```

- `idMap` maps every DOT node name to its tree node id. That includes the
  synthetic symbol nodes `<sid>__gate` and `<sid>__event`, which get a `_2`
  (`_3` …) suffix if a real id already has that name.
- A plain node keeps its 1.6 name, so older clients that do not read the map
  still work.
- `POST /api/render` draws the Graphviz *approximations* of the symbols. The
  true symbols exist only in the browser renderer.

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

`GET /api/export/xlsx[?sigFigs=N]` writes the 1.6 `FTA` sheet unchanged, plus
an **Events** sheet (one row per node; the columns are
`excel_events.EVENT_COLUMNS`) and an **Analysis** sheet (settings and, in FTA
mode, the headline figures). `sigFigs` sets the scientific number format of
the probability cells; it is clamped to 1–6, and a missing or unparseable
value gives 3. The UI sends the top bar's significant-figures setting.

### New error codes

| Code | HTTP | When | `detail` |
|---|---|---|---|
| `MODE_UNSUPPORTED` | 409 | An analysis or FMEA endpoint on an ETA document | `{mode: "ETA"}` |
| `BUSY` | 409 | A Monte Carlo run is already in progress | `{}` |
| `ANALYSIS_TOO_LARGE` | 422 | A voting gate over 20,000 combinations, or the cut-set time budget ran out | `{reason: "kofn"\|"time", nodeId?, k?, n?, combinations?, limit?}` |
| `EXPORT_UNAVAILABLE` | 503 | An optional package is missing: `python-docx` for the report, `openpyxl` for xlsx export or FMEA import | `{format, package, install, feature?}` |

Messages for these codes are localised like every other error. The English
text is the server's own message; `fta_web/i18n.py` supplies the Japanese:

- `BUSY` has a Japanese text.
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
- **Numerics.** A PAND gate with more than 170 inputs is computed in log
  space (171! does not fit a float), and Monte Carlo samples an extreme error
  factor in log space, clamped below the float ceiling, instead of
  overflowing.

---

## Python analysis modules (1.7)

These are flat modules in `fta_web/`, and each takes and returns plain dicts.
Import them with `fta_web/` on `sys.path`, or as `fta_web.<module>`. None of
them modifies the tree it is given.

```python
import sys; sys.path.insert(0, "fta_web")
from engine import WebCore, summary
import cutsets, importance, uncertainty, lint

core = WebCore()                         # FTACore subclass; the core itself is not edited
core.load_from_json("plant.json")        # also reads the `analysis` block
core.set_analysis({"missionTime": 17520})  # validated deep merge; raises engine.AnalysisError
core.recalculate_probabilities()
tree, analysis = core.get_data(), core.get_analysis()

summary(tree, analysis)                  # {treeWalk, mcub, rareEvent, headline, headlineMethod, ...}
cs = cutsets.compute(tree, analysis, {"maxOrder": 4})   # may raise cutsets.CutsetError
importance.compute(cs)                   # [{id, name, q, fv, birnbaum, raw, rrw, rrwInfinite, cutSetCount}]
uncertainty.run(tree, analysis, n=10000, seed=1, time_limit=30.0)
lint.run(tree, analysis, session_warnings=[], mode="FTA", extra={"cutsets": cs})
core.save_to_json("plant.json")          # writes `analysis` beside `tree`
```

- `WebCore` overrides only `_recalculate_fta_probabilities`, `load_from_json`
  and `prepare_export_data`.
- `core.quant_warnings` holds the last recalculation's `{code, nodeId, params}`
  warnings.
- `engine.derive_quant(node, analysis)` evaluates one node's model.
- `engine.kofn_probability(probs, k)` and `engine.xor_probability(probs)` are
  the gate formulas.
- The CLI (`fta_web/cli.py`) is a thin wrapper over these functions. See the
  [User Guide](USER_GUIDE.md#command-line-interface).

## FTACore Class

Main class for fault tree and event tree analysis operations.

### Constructor

```python
from src.FTA_Editor_core import FTACore

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

#### `add_node(parent_id, node_data)`

Add a new node as child of specified parent.

**Parameters**:
- `parent_id` (str): ID of parent node
- `node_data` (dict): Node data (name, type, probability, etc.)

**Returns**: tuple (success: bool, error: str or None)

**Example**:
```python
success, error = core.add_node("root", {
    "name": "Hardware Failure",
    "type": "Event",
    "probability": 0.1,
    "logicGate": "OR"
})
```

#### `update_node(node_id, updates)`

Update an existing node.

**Parameters**:
- `node_id` (str): ID of node to update
- `updates` (dict): Fields to update

**Returns**: tuple (success: bool, error: str or None)

**Example**:
```python
success, error = core.update_node("root_0", {
    "name": "Updated Name",
    "probability": 0.15
})
```

#### `delete_node(node_id)`

Delete a node and all its children.

**Parameters**:
- `node_id` (str): ID of node to delete

**Returns**: tuple (success: bool, error: str or None)

**Example**:
```python
success, error = core.delete_node("root_0_1")
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
from src.FTA_Editor_core import FTACore

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

## Error Handling

All methods return tuples `(success, error)`:

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
from src.FTA_Editor_core import sanitize_name

clean = sanitize_name("  Spaced   Text  ")
# Returns: "Spaced Text"
```

## Constants

None - all configuration is data-driven.

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
from src.AI_agent_handler import AIAgentHandler

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

#### `configure(api_key, api_endpoint, model)`

Configure AI credentials.

**Parameters**:
- `api_key` (str): OpenAI API key
- `api_endpoint` (str): API endpoint URL (default: "https://api.openai.com/v1")
- `model` (str): Model name (default: "gpt-4o")

**Returns**: tuple (success, error_message)

```python
success, error = handler.configure(
    api_key="sk-...",
    api_endpoint="https://api.openai.com/v1",
    model="gpt-4o"
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

#### `save_credentials(api_key, api_endpoint, model)`

Save credentials to local storage.

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
from src.AI_agent_handler import FTAStructureAnalyzer

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
