# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for the FTA Editor web app -- ONEDIR, deliberately not onefile.

Build it from the repo root:

    python3 -m PyInstaller --clean --noconfirm \
        --distpath build/dist --workpath build/build build/fta_editor.spec

Output: ``build/dist/fta_editor/`` (executable + ``_internal/``). See
build/README.md for the rationale, per-OS notes and the verification steps.

Two things about this app make its spec less boring than most:

1. The vendored core in ``fta_web/core/`` is imported by BARE module name --
   ``from ai_providers import AIProviderFactory`` runs at import time inside
   ``AI_agent_handler``. PyInstaller reaches those files only if the core
   directory is on ``pathex`` AND the four module names are named as hidden
   imports; nothing in the analysed source references them with a name a static
   scan can follow.
2. ``app._register_blueprints`` loads the API blueprints with
   ``importlib.import_module("routes.<name>")`` from a table of strings. A
   static scan sees no import at all, and the failure is quiet by design: the
   app starts and logs "routes.tree not found", so a bundle missing them would
   serve the page and 404 every API call.
"""
import importlib.util
from pathlib import Path

# SPECPATH is injected by PyInstaller and is the directory holding this file.
SPEC_DIR = Path(SPECPATH).resolve()  # noqa: F821  (PyInstaller global)
REPO_ROOT = SPEC_DIR.parent
FTA_WEB = REPO_ROOT / "fta_web"
CORE = FTA_WEB / "core"

APP_NAME = "fta_editor"
ENTRY_SCRIPT = str(FTA_WEB / "run.py")


def _tree(source: Path, destination: str):
    """``datas`` entries for every file under ``source``, minus build droppings.

    PyInstaller's ``(dir, dest)`` shorthand copies the directory verbatim,
    ``__pycache__/`` included. That matters for ``core/``: the shipped copy is
    what an auditor hashes against ``core/BASELINE.json``, and a directory
    salted with stale ``.pyc`` files from whichever interpreter last imported
    the checkout is a worse artifact than the source tree it is meant to
    mirror. Nothing in the bundle imports from these files anyway -- the
    modules themselves are compiled into the archive.
    """
    entries = []
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or path.suffix in (".pyc", ".pyo"):
            continue
        relative = path.parent.relative_to(source)
        # as_posix() so a Windows build emits "static/js", not "static\\js":
        # PyInstaller accepts either, but forward slashes keep the TOC readable
        # and identical across the three platforms this is built on.
        entries.append((str(path), (Path(destination) / relative).as_posix()))
    return entries


def _require(path: Path) -> Path:
    """Fail the build now rather than ship a bundle with a hole in it.

    A missing data directory is not an error PyInstaller raises on its own --
    it warns and carries on -- and the result runs far enough to look fine:
    the page loads from the "frontend not installed" fallback in app.py, or
    every /static/ URL 404s. Both are much harder to diagnose from the bundle
    than from here.
    """
    if not path.exists():
        raise SystemExit(
            "fta_editor.spec: required path is missing: %s\n"
            "Build from a complete checkout, with the repo root as the working "
            "directory." % path
        )
    return path


# ---------------------------------------------------------------------------
# Data files.
#
# The destination names are a contract with fta_web/runtime_paths.py: it
# resolves every data path as ``resource_root() / "<name>"``, where
# resource_root() is sys._MEIPASS when frozen and fta_web/ from source. The two
# layouts are identical below the root precisely so no caller has to care which
# one it is in. Renaming a destination here breaks the app at runtime, not at
# build time.
# ---------------------------------------------------------------------------
datas = (
    # Jinja templates -- app.py passes config.TEMPLATES_DIR to Flask.
    _tree(_require(FTA_WEB / "templates"), "templates")
    # The whole frontend, including static/vendor/viz-js/viz.js (~1.1 MB): the
    # WebAssembly Graphviz build that makes the diagram render with no native
    # Graphviz installed. It is the reason this executable has no native
    # prerequisite, so it is not optional and must never be pruned for size.
    + _tree(_require(FTA_WEB / "static"), "static")
    # The vendored core, shipped as source as well as compiled into the archive
    # (see hiddenimports). Both copies matter: the archive is what imports, the
    # directory is what an auditor hashes against core/BASELINE.json.
    + _tree(_require(CORE), "core")
    # Sample tree offered by the file dialog.
    + _tree(_require(FTA_WEB / "examples"), "examples")
)

_require(FTA_WEB / "static" / "vendor" / "viz-js" / "viz.js")
_require(Path(ENTRY_SCRIPT))


# ---------------------------------------------------------------------------
# Hidden imports.
# ---------------------------------------------------------------------------
hiddenimports = [
    # -- Vendored core, imported by bare name (reason 1 in the module docstring).
    #    pathex below puts CORE on the analysis path so these resolve.
    "FTA_Editor_core",
    "AI_agent_handler",
    "ai_providers",
    "json_viewer",
    # -- API blueprints, loaded via importlib.import_module (reason 2).
    "routes",
    "routes.tree",
    "routes.render",
    "routes.files",
    "routes.ai",
    # -- fta_web's own modules. Most are reachable statically through run.py,
    #    but every cross-module import in this package is written as
    #    ``try: from ..x import y / except ImportError: from x import y``, and
    #    which branch a static scan believes is not something to leave to
    #    chance for the modules the whole app depends on.
    "runtime_paths",
    "config",
    "errors",
    "security",
    "state",
    "rendering",
    "tree_ops",
    "fsbrowser",
    "ai_bridge",
    "app",
]

# ---------------------------------------------------------------------------
# Optional third-party packages.
#
# Every one of these is optional at runtime *by design*: the app probes for
# them and disables the corresponding feature with an explanation rather than
# failing (state._probe_excel_export, routes/files.py's export capability list,
# and the "package not installed" branches in core/ai_providers.py). So they
# are bundled when the build machine has them and skipped when it does not --
# listing an absent package unconditionally would bury a real "module not
# found" warning under expected ones on every build.
#
# The consequence is that the bundle's feature set is decided by the build
# environment. Install the full set before building a release:
#
#     pip install -r requirements.txt -r fta_web/requirements.txt
#
# openpyxl is reached through a function-level ``from openpyxl import Workbook``
# in the vendored FTA_Editor_core, which the analysis does follow -- it is named
# here anyway so that a build without .xlsx export is visible in the log rather
# than silent.
#
# Pillow/PIL is deliberately NOT here: it is imported only by
# src/FTA_Editor_UI.py, the Tk desktop app, which this bundle does not contain.
# Adding it would cost megabytes for code no web request can reach.
# ---------------------------------------------------------------------------
OPTIONAL_IMPORTS = (
    "openai",              # OpenAI + Azure OpenAI providers
    "anthropic",           # Anthropic provider
    "google.generativeai",  # Gemini provider
    "openpyxl",            # .xlsx export
)


def _installed(module_name: str) -> bool:
    """Whether ``module_name`` can be found on the build machine."""
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ValueError):
        # A namespace-package parent that cannot be imported, or a broken
        # install. Either way it is not safe to bundle.
        return False


_present = [name for name in OPTIONAL_IMPORTS if _installed(name)]
_absent = [name for name in OPTIONAL_IMPORTS if name not in _present]
hiddenimports.extend(_present)

# ---------------------------------------------------------------------------
# Namespace packages need collect_all, not hiddenimports.
#
# ``google`` is a PEP 420 namespace package: there is no google/__init__.py, and
# the subpackages live in separate distributions. A plain hiddenimports entry
# for "google.generativeai" is accepted without complaint and then collects
# NOTHING -- the build reports it as bundled, the bundle ships without
# google/generativeai at all, and at runtime the provider's
# ``except ImportError`` reports "package not installed". That is a silent,
# build-time-invisible loss of one of the three AI providers; it was caught only
# by exercising each provider against the frozen binary.
#
# collect_all() walks the real package directory, so it picks up the submodules,
# their data files, and the compiled grpc/protobuf extensions underneath.
_GOOGLE_NAMESPACE_PACKAGES = (
    "google.generativeai",
    "google.ai.generativelanguage",
)
extra_datas = []      # collect_all results, merged into Analysis(datas=...)
extra_binaries = []   # collect_all results, merged into Analysis(binaries=...)
if "google.generativeai" in _present:
    from PyInstaller.utils.hooks import collect_all  # noqa: F821

    for _pkg in _GOOGLE_NAMESPACE_PACKAGES:
        try:
            _datas, _binaries, _hidden = collect_all(_pkg)
        except Exception as exc:  # a partial install: better loud than silent
            print("fta_editor.spec: WARNING: could not collect %s (%s); the "
                  "Gemini provider will be missing from this build." % (_pkg, exc))
            continue
        extra_datas.extend(_datas)
        extra_binaries.extend(_binaries)
        hiddenimports.extend(_hidden)
    print("fta_editor.spec: collected the google.* namespace packages for Gemini")

print("fta_editor.spec: optional packages bundled: %s"
      % (", ".join(_present) or "(none)"))
if _absent:
    print("fta_editor.spec: optional packages NOT installed, so NOT bundled: %s"
          % ", ".join(_absent))
    print("fta_editor.spec: the matching features will report themselves as "
          "unavailable in the built app. Install them and rebuild if that is "
          "not what you want.")


# ---------------------------------------------------------------------------
# Exclusions.
#
# Each entry below is something the analysis pulled in through an import that
# no reachable code path executes. Every one was checked to be a *guarded*
# import at its use site -- a try/except ImportError, or a function-level
# import behind a feature this app never turns on -- so excluding it removes
# weight without removing behaviour. Do not add to this list on the strength of
# a package name looking irrelevant; check the import site first.
# ---------------------------------------------------------------------------
excludes = [
    # The desktop app (src/) is a Tk program; the web app never touches it, and
    # Tcl/Tk costs tens of megabytes of runtime libraries and .tcl script trees.
    "tkinter",
    "_tkinter",
    "tkinter.filedialog",
    "tkinter.messagebox",
    "tkinter.ttk",
    # Pillow arrives only through openpyxl.drawing.image, whose import is
    # ``try: from PIL import Image / except ImportError: PILImage = False`` and
    # which is used for embedding pictures in a workbook. The Excel export in
    # core/FTA_Editor_core.py writes cells, fonts, fills and alignment and no
    # images at all. ~14 MB of imaging codecs for a code path with no caller.
    # (Pillow is a genuine dependency of the *desktop* app -- src/FTA_Editor_UI.py
    #  displays PNG previews with it -- which is why it is in requirements.txt.)
    "PIL",
    # cryptography (and bcrypt behind it) arrive only through
    # werkzeug.serving.generate_adhoc_ssl_pair, the dev server's
    # ``ssl_context="adhoc"`` support. run.py serves plain HTTP on loopback and
    # never passes ssl_context; the import is inside that function.
    "cryptography",
    "bcrypt",
    # Test-only, never imported by the app.
    "pytest",
    "_pytest",
    # Occasionally pulled in transitively by an SDK's optional extras; the app
    # has no plotting or notebook code.
    "matplotlib",
    "IPython",
    # Test-only, and genuinely observed in a build: hypothesis is a dependency
    # of the dev environment, not of the app. A property-based testing library
    # has no business in a shipped bundle.
    "hypothesis",
    # An alternative asyncio event loop pulled in transitively by an SDK's
    # extras. This app is a synchronous Flask server on loopback and never
    # installs a custom loop policy -- 13 MB of compiled C for no caller.
    "uvloop",
    # A Google discovery-client dependency chain the Gemini provider does not
    # use. ai_providers.GeminiProvider calls google.generativeai directly; the
    # REST discovery client is only needed for the wider Google API surface.
    # See build/README.md "Bundle size" for the measurement and the caveat.
    "googleapiclient.discovery_cache",
]


a = Analysis(  # noqa: F821  (PyInstaller global)
    [ENTRY_SCRIPT],
    # fta_web/ first so ``import config`` etc. resolve; CORE so the four
    # bare-named vendored modules do. This mirrors, at build time, the
    # sys.path that config.py and run.py construct at run time.
    pathex=[str(FTA_WEB), str(CORE)],
    binaries=extra_binaries,
    datas=list(datas) + extra_datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

# ---------------------------------------------------------------------------
# Drop the Google API discovery documents.
#
# google-api-python-client ships ~600 JSON descriptors -- one per Google API
# (BigQuery, Compute, YouTube, ...) -- totalling ~102 MB, and PyInstaller's hook
# bundles all of them. They are *data*, not modules, so an `excludes` entry does
# not touch them; they have to be filtered off a.datas here.
#
# The Gemini provider (core/ai_providers.py GeminiProvider) talks to
# generativelanguage directly through google.generativeai. It never calls
# googleapiclient.discovery.build(), which is the only thing that reads these
# documents. Removing them takes the bundle from ~179 MB to ~77 MB.
#
# If a future provider ever does call discovery.build(), it will raise
# UnknownApiNameOrVersion at that call -- loudly, not silently -- and this
# filter is where to look.
_before = len(a.datas)  # noqa: F821  (PyInstaller global)
a.datas = [  # noqa: F821  (PyInstaller global)
    entry for entry in a.datas  # noqa: F821
    if "googleapiclient/discovery_cache/documents" not in entry[0].replace("\\", "/")
]
print("fta_editor.spec: dropped %d Google API discovery documents"
      % (_before - len(a.datas)))  # noqa: F821

pyz = PYZ(a.pure)  # noqa: F821  (PyInstaller global)

exe = EXE(  # noqa: F821  (PyInstaller global)
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # onedir: the libraries stay outside the executable
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX-packed executables are a well-known antivirus trigger and
                # save nothing that matters for a locally-copied tool.
    # A console is required, not cosmetic: run.py prints the URL *including the
    # per-launch session token*, and that terminal line is the only copy the
    # user can reach when the browser does not open by itself (headless box,
    # SSH, WSL, a locked-down default browser). Ctrl-C there is also how the
    # server is stopped. Do not set console=False.
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon="build/icon.ico",  # add when an icon exists; .ico on Windows,
    #                           .icns on macOS.
)

coll = COLLECT(  # noqa: F821  (PyInstaller global)
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)
