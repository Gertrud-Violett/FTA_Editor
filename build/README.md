# Building the FTA Editor web app as a standalone executable

`fta_editor.spec` freezes the web app (`fta_web/`) into a self-contained folder
that runs on a machine with **no Python and no Graphviz installed**. The user
double-clicks one executable; a local server starts and a browser opens on it.

This directory is source, not output. `dist/` and `build/` are produced here and
are git-ignored; `fta_editor.spec` and this file are tracked.

---

## Prerequisites

On the machine doing the build — and it must be the **same OS and CPU
architecture as the target**, see [Per-OS notes](#per-os-notes):

```
python3 -m pip install -r requirements.txt -r fta_web/requirements.txt
python3 -m pip install pyinstaller
```

Verified with PyInstaller 6.22.2 on CPython 3.10.

The first command matters more than it looks. **The build machine's installed
packages decide the built app's feature set**, because the optional ones are
optional at runtime by design:

| Package | Feature | Absent from the build ⇒ |
|---|---|---|
| `openpyxl` | `.xlsx` export | `capabilities.excelExport: false`; the export offers JSON/XML/SVG/PNG only |
| `openai` | OpenAI + Azure/Copilot providers | provider present in the list, "package not installed" on connect |
| `anthropic` | Anthropic Claude provider | as above |
| `google-generativeai` | Google Gemini provider | as above |

The spec prints which of these it bundled and which it skipped. Read that line;
it is the only warning you get that you have built a crippled release:

```
fta_editor.spec: optional packages bundled: openpyxl
fta_editor.spec: optional packages NOT installed, so NOT bundled: openai, anthropic, google.generativeai
```

Graphviz is **not** a build prerequisite and not a runtime one — see
[No native prerequisite](#no-native-prerequisite).

## Build

From the **repo root** (not from this directory — the spec resolves everything
relative to itself, but PyInstaller resolves `--distpath`/`--workpath` relative
to the working directory):

```
python3 -m PyInstaller --clean --noconfirm \
    --distpath build/dist --workpath build/build \
    build/fta_editor.spec
```

Output: `build/dist/fta_editor/` — around **20 MB, 97 files** on Linux, of which
the executable itself is ~3.2 MB and the rest is `_internal/`.

Ship the whole `fta_editor/` folder. The executable will not run without its
`_internal/` sibling.

## What ships

Compiled into the archive: the `fta_web` Python modules, the four vendored core
modules, Flask/Werkzeug/Jinja/click/itsdangerous/MarkupSafe, `openpyxl` when
present, and a private CPython runtime.

Unpacked as data, under the root the app knows as
[`runtime_paths.resource_root()`](../fta_web/runtime_paths.py):

| In the bundle | From | Why |
|---|---|---|
| `templates/` | `fta_web/templates/` | `index.html`, rendered by Flask |
| `static/` | `fta_web/static/` | the whole frontend: JS, CSS, and `vendor/viz-js/viz.js` (~1.1 MB) |
| `core/` | `fta_web/core/` | the vendored core **as source**, so it can be hashed against `core/BASELINE.json` |
| `examples/` | `fta_web/examples/` | `sampleFTA.json` |

`core/` is shipped twice on purpose: the compiled copy in the archive is what
actually imports, the source copy is the audit trail. `__pycache__` and `.pyc`
files are filtered out so the shipped directory is a faithful mirror of the
checkout — a build machine's stale bytecode must not end up in a hash an
auditor is checking.

Deliberately **not** bundled:

- **Tcl/Tk** — the desktop app (`src/`) is a Tk program; this bundle is the web
  app and contains none of it.
- **Pillow** — reached only through `openpyxl.drawing.image`, behind a
  `try: from PIL import Image / except ImportError`, for embedding pictures in a
  workbook. The Excel export writes cells, fonts, fills and alignment, and no
  images. (Pillow *is* a real dependency of the desktop app, which is why it
  stays in `requirements.txt`.)
- **cryptography / bcrypt** — reached only through
  `werkzeug.serving.generate_adhoc_ssl_pair`, i.e. the dev server's
  `ssl_context="adhoc"`. This app serves plain HTTP on loopback and never
  passes `ssl_context`.

Together those three are ~31 MB: the bundle is 51 MB without the exclusions and
20 MB with them. Each was checked at its import site before being excluded. If
you add one back, say why in the spec.

## Why onedir, and not onefile

**Do not "optimise" this into `--onefile`.** It is a single artifact and it
looks tidier, and both of the reasons against it are worse than that is good:

1. **It re-extracts the entire bundle to a temp directory on every launch.**
   Onefile is a self-extracting archive: each start unpacks ~20 MB — including
   the 1.1 MB `viz.js` and the whole CPython runtime — writes it under `%TEMP%`
   or `/tmp`, runs from there, and deletes it on exit. That is seconds of
   startup for a tool people open and close all day, repeated in full every
   time, and it leaves the extracted tree behind whenever the process is killed
   rather than exited.
2. **It reliably trips antivirus heuristics.** "Executable writes an executable
   and a batch of DLLs to a temp directory, then runs them" is a textbook
   dropper signature. Onefile PyInstaller builds are a standing entry in
   false-positive trackers for most major engines. Onedir keeps the libraries
   on disk where a scanner can look at them once, at install time, which is
   what scanners are built to expect.

The cost of onedir is that users must keep the folder together and launch the
executable inside it. That is a one-line instruction. The cost of onefile is
paid on every single launch, by every user, forever.

Related, in the spec and for the same reason: `upx=False`. UPX compression is
itself a strong antivirus heuristic and saves nothing worth having for a tool
that is copied once.

## No native prerequisite

The built app renders diagrams with **no Graphviz installed**. The browser draws
them from `GET /api/dot` using the vendored WebAssembly Graphviz in
`static/vendor/viz-js/viz.js`, which is why that file is a hard requirement of
the bundle and must never be pruned for size.

A native `dot` binary, when present, is used only by `POST /api/render` to
produce a file to save. When it is absent the app says so rather than
pretending: `/api/state` reports `capabilities.nativeDot: false`, the UI
disables native export, and `/api/render` returns `503 RENDERER_UNAVAILABLE`
with install instructions. Verified on the frozen build on a machine with no
`dot` on `PATH` — see the verification steps below.

## Per-OS notes

PyInstaller does **not cross-compile.** There is no flag, no toolchain and no
supported trick: a Windows `.exe` is produced by running PyInstaller on Windows,
a macOS bundle on macOS. Three build machines (or three CI runners) are needed
for three platforms. The spec itself is platform-neutral and takes no changes.

### Linux

The command above. The bundle links against the glibc of the build machine, so
build on the **oldest** distribution you intend to support — a bundle built on
a current Ubuntu will not start on an older one (`GLIBC_2.xx not found`).

### Windows

Out of scope for the current build; the command is identical apart from the
interpreter:

```
py -m PyInstaller --clean --noconfirm ^
    --distpath build\dist --workpath build\build ^
    build\fta_editor.spec
```

Known differences to expect when someone does it:

- **Unsigned executables get SmartScreen.** A fresh download shows "Windows
  protected your PC" until enough people run it. An Authenticode certificate and
  `signtool sign` on `dist\fta_editor\fta_editor.exe` is the only real fix; the
  spec has a commented-out `icon=` line, and an icon plus a signature is what
  makes a download look like software rather than like a payload.
- **`console=True` is required, not a default we forgot to change.** `run.py`
  prints the URL *including the per-launch session token*, and that console line
  is the only copy the user can reach if the browser does not open. Setting
  `console=False` also makes every `print()` raise on a process with no stdout.
  The visible console window is the price of the token being recoverable.
- **Users will copy the `.exe` on its own** — it is the only file in the folder
  that looks like the program — and it will fail. Ship a zip of the whole
  `fta_editor\` folder, or wrap it in an installer.
- **`%TEMP%` still matters** even under onedir: `POST /api/render` writes its
  `.dot` and output files there via `tempfile`. They are cleaned up on every
  exit path.
- The `.gitignore` at the repo root ignores `*.png`, `*.xlsx` and `*.xml`; that
  is irrelevant to the build but bites anyone trying to commit a test artifact.

### macOS

Same command as Linux. Additionally: builds are per-architecture unless
`target_arch="universal2"` is set in the spec *and* every bundled wheel is
universal, and Gatekeeper will quarantine an unsigned, unnotarized bundle
downloaded from the internet. Codesigning hooks are present but unset
(`codesign_identity`, `entitlements_file`).

## How to verify a build

The bundle can fail in ways that still look like a working app — the page
renders from the fallback HTML in `app.py`, or every `/static/` URL 404s, or the
API blueprints are quietly absent because `importlib.import_module("routes.…")`
found nothing. Check all four.

Start it on a spare port without opening a browser:

```
./build/dist/fta_editor/fta_editor --port 8791 --no-browser
```

It prints the URL with the session token. Copy the token out of it, then, in
another terminal:

```
TOKEN=<the value after ?t=>

# 1. The real page, not the "frontend has not been installed" fallback.
curl -s http://127.0.0.1:8791/ | grep -c 'frontend has not been installed'   # 0
curl -s http://127.0.0.1:8791/ | grep -o '/static/js/main.js'                # found

# 2. Static assets, including the WASM Graphviz.
for u in /static/js/main.js /static/css/app.css /static/vendor/viz-js/viz.js; do
  curl -s -o /dev/null -w "$u %{http_code}\n" "http://127.0.0.1:8791$u"      # 200 x3
done

# 3. The API is mounted, and the token is enforced.
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8791/api/state                        # 403
curl -s -H "X-FTA-Token: $TOKEN" http://127.0.0.1:8791/api/state | head -c 200                  # 200 + JSON

# 4. DOT generation, i.e. the vendored core imported under its bare name.
curl -s -H "X-FTA-Token: $TOKEN" http://127.0.0.1:8791/api/dot | head -c 80   # {"ok":true,"dot":"digraph G {...
```

A 404 on `/api/state` rather than a 403 means the blueprints did not make it
into the bundle: check the `routes.*` hidden imports.

Worth also checking, because they exercise the parts a naive freeze breaks:

```
# capabilities disclosure, on a machine with no Graphviz
curl -s -H "X-FTA-Token: $TOKEN" http://127.0.0.1:8791/api/state | python3 -m json.tool | grep -A3 capabilities
#   "nativeDot": false, "excelExport": true, "aiConfigured": false

# openpyxl inside the bundle
curl -s -o /tmp/t.xlsx -w "%{http_code}\n" -H "X-FTA-Token: $TOKEN" \
     http://127.0.0.1:8791/api/export/xlsx && file /tmp/t.xlsx   # Microsoft Excel 2007+

# the vendored ai_providers module, reached as a bare-name import
curl -s -H "X-FTA-Token: $TOKEN" http://127.0.0.1:8791/api/ai/providers | head -c 120
```

And confirm the shipped core still matches the checkout it was built from:

```
for f in AI_agent_handler.py FTA_Editor_core.py ai_providers.py json_viewer.py; do
  diff -q "fta_web/core/$f" "build/dist/fta_editor/_internal/core/$f"
done
```

Finally, prove the "no prerequisites" claim on a scrubbed environment rather
than trusting it:

```
env -i HOME=/tmp/fakehome PATH=/nonexistent \
  ./build/dist/fta_editor/fta_editor --port 8792 --no-browser
```

It should start and serve normally with no Python and nothing else on `PATH`.

## Known limitation: Gemini in a frozen build

**Verified against the built binary: OpenAI and Anthropic work; Google Gemini does
not.** With a deliberately invalid key, OpenAI and Anthropic both reach their APIs and
return `401`, which proves their client libraries loaded. Gemini returns *"Google
Generative AI package not installed"* — the provider's `except ImportError` branch.

The cause is that `google.generativeai` lives under `google`, a **PEP 420 namespace
package**. A plain `hiddenimports` entry for it is accepted without complaint and
collects nothing: the build prints "bundled", the bundle ships without
`google/generativeai`, and the failure only appears at runtime. `collect_all()` (now in
the spec) does place the files in the bundle, but the import still fails inside the
frozen app — PyInstaller's importer and namespace packages remain an unsolved
combination here.

**This is disclosed, not hidden.** `AppState._probe_provider_sdks` really imports each
SDK rather than calling `find_spec`, precisely because `find_spec` reported Gemini
present in the frozen build while the import raised. The capability indicator therefore
shows Gemini as unavailable in a frozen build, and the AI settings dialog can say so
before the user pastes a key.

**Workarounds, in order of preference:**

1. Run from source (`python fta_web/run.py`), where all three providers work.
2. Use OpenAI or Anthropic in the packaged build.
3. Migrate `GeminiProvider` to the `google.genai` package — see below.

`google.generativeai` is **end-of-life** ("All support for the `google.generativeai`
package has ended... switch to the `google.genai` package"). Its replacement is far
lighter and avoids the `google-api-python-client` dependency entirely, so migrating
would very likely fix the freeze problem *and* shrink the bundle further. That is a
change to `fta_web/core/ai_providers.py` and needs a real Gemini key to verify, so it is
recorded as the top v1.7 item rather than done blind.

## Bundle size

Measured on Linux, all optional packages installed:

| Configuration | Size |
|---|---|
| No AI SDKs | 20 MB |
| All three AI SDKs, naive | 194 MB |
| After exclusions and the discovery-document filter | **79 MB** |

Two things account for the difference:

- **`googleapiclient/discovery_cache/documents`** — ~600 JSON descriptors, one per
  Google API (BigQuery, Compute, YouTube…), **102 MB**. They are *data*, not modules, so
  an `excludes` entry does not touch them; the spec filters them off `a.datas` after
  Analysis. The Gemini provider never calls `discovery.build()`, the only thing that
  reads them. If a future provider does, it will raise `UnknownApiNameOrVersion` at that
  call — loudly — and the filter is where to look.
- **`hypothesis` (2 MB) and `uvloop` (13 MB)** were being bundled: a property-based
  testing library and an unused async event loop, both pulled in transitively from the
  dev environment. Neither has a caller in this app.

