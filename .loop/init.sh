#!/usr/bin/env bash
# .loop/init.sh: make this repo ready for a loop run. ralph.sh runs it once
# before the first iteration; you can run it by hand at any time.
#
# Contract (the loop relies on this):
#   - Idempotent: safe to run on every loop start; second run should be fast.
#   - Non-interactive: no prompts, no GUI, no sudo.
#   - Exit 0  = ready.
#   - Exit 10 = needs the owner (missing tool). Prints WHAT and HOW.
#   - Any other non-zero = setup is broken.
#
# Stack: Python 3.10+ (Flask web app fta_web/ + frozen Tkinter desktop app).
# Mirrors CI (.github/workflows/tests.yml): `uv sync --locked --extra all
# --extra test` into .venv. Falls back to pip + requirements files when uv is
# not installed (unlocked versions; CI remains the locked reference).
set -euo pipefail
cd "$(dirname "$0")/.."

need() {  # need <command> "<how to install>"
  command -v "$1" >/dev/null 2>&1 || { echo "MISSING TOOL: $1. $2"; exit 10; }
}

# ---- 1. tools -------------------------------------------------------------
need git "apt install git (owner)"
need python3 "apt install python3 python3-venv (owner)"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
  || { echo "MISSING TOOL: python3 >= 3.10 (found $(python3 --version 2>&1)). Install Python 3.10+ (owner)"; exit 10; }
if ! command -v dot >/dev/null 2>&1; then
  echo "note: Graphviz 'dot' not found; native-render tests in fta_web/tests/test_api_render.py will skip (optional: apt install graphviz)"
fi

# ---- 2. secrets: none. AI provider keys are NOT needed; AI tests use mocks.

# ---- 3. dependencies (idempotent) ------------------------------------------
stamp=.venv/.installed
if [[ ! -f $stamp || pyproject.toml -nt $stamp || uv.lock -nt $stamp \
      || requirements.txt -nt $stamp || fta_web/requirements.txt -nt $stamp ]]; then
  if command -v uv >/dev/null 2>&1; then
    echo "installing deps with uv (locked, extras all+test) ..."
    UV_PROJECT_ENVIRONMENT=.venv uv sync --locked --extra all --extra test --quiet
  else
    echo "uv not found; installing deps with pip (unlocked fallback) ..."
    if [[ ! -x .venv/bin/python ]]; then
      python3 -m venv .venv \
        || { echo "MISSING TOOL: python3-venv. apt install python3-venv (owner)"; exit 10; }
    fi
    .venv/bin/python -m pip install -q -U pip
    .venv/bin/python -m pip install -q -r requirements.txt -r fta_web/requirements.txt
  fi
  touch "$stamp"
fi

# ---- 4. smoke check: the verify tooling runs ------------------------------
.venv/bin/python -m pytest --version >/dev/null
.venv/bin/python -c 'import flask, openpyxl' >/dev/null

# Snapshot/partial-clone guard: the vendored WebAssembly Graphviz is a
# committed file the tests (and the app) rely on.
if [[ ! -f fta_web/static/vendor/viz-js/viz.js ]]; then
  echo "warning: fta_web/static/vendor/viz-js/viz.js is missing (it is tracked in git); run 'git checkout -- fta_web/static/vendor' or re-clone"
fi

echo "init ok"
