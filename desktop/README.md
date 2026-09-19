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

- `NOT` logic gates are silently calculated as `OR` (D1).
- The move guard permits exactly the reparenting moves that corrupt the tree (D5).
- Minified (single-line) JSON files fail to open with a misleading encoding error (D7).
- The Gemini provider uses the end-of-life `google-generativeai` SDK (D11).

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
