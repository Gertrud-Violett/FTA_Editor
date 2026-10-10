# Legacy desktop app (backup / fallback)

This folder holds the original **Tkinter desktop version** of the FTA/ETA
Editor (v1.5.1 behaviour), kept as a backup and fallback for the web app in
[`../fta_web/`](../fta_web/), which is the primary, actively developed version
of the editor.

```
desktop/
├── src/                    # the Tk application and its copy of the core
│   ├── FTA_Editor_UI.py    # GUI (entry point)
│   ├── FTA_Editor_core.py  # tree model, probability engine, JSON/XML/Excel export
│   ├── json_viewer.py      # Graphviz DOT/PNG rendering (also a CLI)
│   ├── AI_agent_handler.py # AI assistant
│   └── ai_providers.py     # OpenAI / Azure / Anthropic / Gemini clients
├── tests/                  # the frozen upstream test suite
└── data/examples/          # sampleFTA.json
```

## Status: frozen

`desktop/src/` is **hash-pinned** by `fta_web/tests/test_vendor_integrity.py`
against `fta_web/core/BASELINE.json` and must not be edited. The web app's
`fta_web/core/` is a vendored fork of four of these modules; every fix made
there is recorded in [`fta_web/core/DIVERGENCE.md`](../fta_web/core/DIVERGENCE.md)
and is, by definition, **not** applied here. Known defects that remain in this
desktop version include:

- `NOT` logic gates are silently calculated as `OR` (D5).
- The move guard permits exactly the reparenting moves that corrupt the tree (D7).
- Minified (single-line) JSON files fail to open with a misleading encoding error (D8).
- The Gemini provider uses the end-of-life `google-generativeai` SDK (D11).
- AI providers: the Anthropic model list is the built-in Claude 3 one, never
  fetched (D9, D22); replies from Claude models that think, which all current
  ones do, fail (D21); the documented Azure endpoint
  `…/openai/deployments/<name>` gets a 404, so enter the bare resource URL and
  put the deployment in Model (D23); no request has a deadline, so a provider
  that stops answering is waited on for many minutes (D24); an empty reply
  breaks the conversation (D25); OpenAI reasoning models (o-series, GPT-5) are
  refused (D26).

### Known defects (not fixed in the frozen app)

The September 2026 code review found these in the desktop app; they are
described in [`docs/CODE_REVIEW_2026-09.md`](../docs/CODE_REVIEW_2026-09.md).

- **D-C1** Every gate result is rounded to 6 decimals: a probability below
  5e-7 becomes exactly 0, is flagged as zero and turns AND gates above it to 0.
- **D-C2** After opening a file whose top node id is not `root`, every node
  added is silently dropped and not saved.
- **D-C3** Ctrl+D (like Ctrl+A/E/N) is bound application-wide: pressed while
  typing in the chat or a Notes box, it deletes the selected subtree without
  asking. There is no undo.
- **D-C4** Closing the main window never asks about unsaved changes.
- **D-C5** A file with duplicate node ids crashes the load half-way, leaving a
  partial tree over the replaced data.
- **D-C6** The AI settings dialog makes its network calls on the UI thread with
  no timeouts, so the window can freeze for minutes (behind a proxy, say).
- **D-H1** Changing the title or mode resets the analysis date to today.
- **D-H2** A node name containing `<`, `>` or `&` makes the whole diagram
  disappear.
- **D-H3** Distinct ids made of non-ASCII characters (`節点1`, `節点2`), or
  `a-b` and `a_b`, merge into one diagram node.
- **D-H4** Update FTA installs AI output that is only shape-checked; removed
  nodes are not reported and there is no undo.
- **D-H5** Graphviz `dot` runs without a timeout, and the one timeout kills
  only the Python child, leaving `dot.exe` running on Windows.
- **D-M1…M7** Tabbing through a field marks the file as changed; the
  `json_viewer.py` command line crashes on a string or `null` probability;
  links to missing nodes are exported as they are; saving is not atomic, so a
  failure mid-write truncates the previous file; the Anthropic and Gemini
  providers ignore the endpoint; the chat history grows without limit; worker
  threads call `root.after()` (plausible, not confirmed); an `add_node` id
  clash raises `TclError`; the AI credentials file is written with default
  permissions.

If any of these matter to you, use the web app.

## Running it

Prerequisites beyond Python 3.10+: **Tk** (your OS's `python3-tk` package),
**Graphviz** on `PATH` (the live preview needs the native `dot`), and Pillow.

```bash
# from the repo root
uv sync --extra desktop --extra excel --extra ai     # or: pip install -r requirements.txt
uv run python desktop/src/FTA_Editor_UI.py          # or: python desktop/src/FTA_Editor_UI.py
```

Files, AI credentials (`~/.fta_editor/ai_credentials.json`) and diagrams are
interchangeable with the web app.

## Tests

```bash
python -m pytest desktop/tests/            # via pytest (pytest.ini already lists it)
python desktop/tests/run_all_tests.py      # the original runner
```

The original runner prints `✓`/`❌` and will crash with `UnicodeEncodeError`
on a Windows console whose code page is not UTF-8 (e.g. cp932). Set
`PYTHONIOENCODING=utf-8` first, or use pytest.

## Why is it in a subfolder?

The tests and the source resolve each other relative to this folder
(`Path(__file__).parent.parent`), so moving `src/`, `tests/` and `data/`
together into `desktop/` kept the frozen suite byte-for-byte unchanged and
still passing. Only the paths recorded in `BASELINE.json` changed; the
hashes did not.
