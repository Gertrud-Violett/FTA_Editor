# Environment: fta-editor

Read by every loop iteration and by the owner. Keep it current. If you (the
agent) change how the project is built or tested, update this file in the
same commit.

## Where it runs
- Host: lightsail (pure Python; the Flask web app and the whole test suite run headless on Linux. No Tk display, GPU or Windows needed. Windows coverage stays with the GitHub Actions `windows` job.)
- Repo path on host: `~/repos/FTA_Editor` (clone of `Gertrud-Violett/FTA_Editor`)
- Loop branch: `loop/fta-editor` → PRs into `main`

## Toolchain
| Tool | Version | Check |
|---|---|---|
| python3 | 3.10 or newer (CI tests 3.10 and 3.13; verified here with 3.11) | `python3 --version` |
| uv (preferred, optional) | any recent; installs exactly from `uv.lock` | `uv --version` |
| python3-venv (needed only when uv is absent) | matches python3 | `python3 -m venv --help` |
| git | any | `git --version` |
| graphviz `dot` (optional) | any | `dot -V` |

## Setup
`bash .loop/init.sh`: idempotent. What it does:
- Checks git and python3 >= 3.10 (exit 10 if missing).
- Notes (does not fail) when Graphviz `dot` is absent: 4 native-render tests then skip.
- If uv is on PATH: `uv sync --locked --extra all --extra test` into `.venv` (same as CI; fails if `uv.lock` is out of sync with `pyproject.toml`).
- Otherwise: `python3 -m venv .venv` and `pip install -r requirements.txt -r fta_web/requirements.txt` (unlocked fallback).
- Reinstalls only when `pyproject.toml`, `uv.lock` or either requirements file is newer than `.venv/.installed`. Second run: under 1 s.
- Smoke check: `pytest --version` and `import flask, openpyxl` in `.venv`.
- Warns if `fta_web/static/vendor/viz-js/viz.js` (tracked, about 1.2 MB) is missing from the checkout.
- First run: about 5 s with uv, about 90 s with pip.

## Verify (what "working" means mechanically)
Same as `prd.json → verify.commands`:
- `.venv/bin/python -m pytest -q -p no:cacheprovider`: the full suite (fta_web/tests + desktop/tests, from pytest.ini), including the hash-pin guards in `fta_web/tests/test_vendor_integrity.py`. Baseline on origin/main (2026-09-23): 630 passed, 4 skipped (no `dot`), exit 0, about 12 s (uv) / 29 s (pip). Confirmed non-zero exit when a pinned file is modified.

## Secrets and accounts
Names only, never values. Values go in
`~/.config/loop-engineering/projects/fta-editor.env` on the host (chmod 600).
| Name | Used for | Who provides |
|---|---|---|
| none | AI provider keys (OpenAI, Anthropic, Gemini, Copilot) are only for interactive use of the app; the tests mock every provider, so the loop needs no keys | nobody |

## Owner-only steps (the agent can't do these)
- [ ] On the host: `apt install python3 python3-venv git` if not already present (or install uv, which is preferred: `curl -LsSf https://astral.sh/uv/install.sh | sh`).
- [ ] Optional: `apt install graphviz` so the 4 native-`dot` render tests run instead of skipping.
- [ ] `gh auth login` on the host so the loop can open draft PRs.

## Off-limits for the loop
- `desktop/**` (frozen legacy app, source, tests and data are SHA-256 pinned in `fta_web/core/BASELINE.json`).
- `fta_web/core/BASELINE.json` pins and `fta_web/core/DIVERGENCE.md` entries: only change together with a deliberate, documented divergence; never to make a test pass.
- `fta_web/static/vendor/**` (vendored viz.js with a pinned sha256 in PROVENANCE.json).
- `uv.lock`: only regenerate with `uv lock` when a task explicitly changes dependencies.
- Releases, PyInstaller builds (`build/`), tags and version bumps: escalate tier.

## Known quirks
- `--import-mode=importlib` in pytest.ini is required: `fta_web/tests/core/` holds vendored copies of `desktop/tests/` with identical basenames.
- `fta_web/core/*.py` is imported by bare module name via `sys.path` (see `fta_web/tests/conftest.py`); do not turn it into a package.
- The desktop tests emit 4 `PytestReturnNotNoneWarning`s; they are frozen files, so leave them.
- The web app refuses to run under multi-worker servers (gunicorn/uwsgi) by design; run it only via `fta_web/run.py`.
- Line endings matter: pinned files are hashed byte-for-byte (LF); `.gitattributes` enforces this.
