#!/usr/bin/env python3
"""
FTA Editor installer.

Dependencies are declared once, in pyproject.toml. This script's only job is
to get them into a venv with the best tool available:

  1. uv, if it is on PATH      -- `uv sync --extra ...` (fast, lockfile-pinned)
  2. plain pip, as a fallback  -- `pip install -r requirements.txt [-r fta_web/requirements.txt]`

Either path leaves you with a normal venv; this script does not do anything
you could not do by hand from the commands it prints.
"""

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

# Maps to pyproject.toml's [project.optional-dependencies] table.
EXTRAS_FOR = {
    "web": ["web", "excel", "ai"],
    "desktop": ["desktop", "excel", "ai"],
    "both": ["web", "desktop", "excel", "ai"],
}


def check_python_version() -> bool:
    if sys.version_info < (3, 10):
        print(f"Error: Python 3.10 or higher required (found {sys.version.split()[0]})")
        return False
    print(f"Python {sys.version.split()[0]}")
    return True


def check_graphviz() -> None:
    """Informational only. Neither app requires it any more.

    The desktop app's live preview does. The web app's diagram renders in the
    browser via a vendored WebAssembly Graphviz with no install step; a native
    `dot` on PATH is used only to sharpen CJK label metrics and native
    high-DPI PNG export, and the app discloses when it is missing rather than
    needing it.
    """
    if shutil.which("dot"):
        print("Graphviz: found (native rendering available)")
    else:
        print(
            "Graphviz: not found. The web app works fully without it "
            "(diagrams render in the browser); the desktop app's preview "
            "needs it. Install from https://graphviz.org/download/ any time."
        )


def choose_target() -> str:
    print()
    print("Which app do you want to set up?")
    print("  1) Web app (recommended) -- runs in your browser, no Graphviz needed")
    print("  2) Desktop app (Tkinter) -- the original UI")
    print("  3) Both")
    choice = input("Choice [1]: ").strip() or "1"
    return {"1": "web", "2": "desktop", "3": "both"}.get(choice, "web")


def install_with_uv(target: str) -> bool:
    extras = EXTRAS_FOR[target]
    cmd = ["uv", "sync"]
    for extra in extras:
        cmd += ["--extra", extra]
    print(f"\nUsing uv: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, cwd=REPO_ROOT, check=True)
    except subprocess.CalledProcessError as exc:
        print(f"uv sync failed: {exc}")
        return False
    print("\nDone. Run commands with `uv run`, e.g.:")
    if target in ("web", "both"):
        print("  uv run python fta_web/run.py")
    if target in ("desktop", "both"):
        print("  uv run python src/FTA_Editor_UI.py")
    return True


def install_with_pip(target: str) -> bool:
    req_files = ["requirements.txt"]
    if target in ("web", "both"):
        req_files.append("fta_web/requirements.txt")
    cmd = [sys.executable, "-m", "pip", "install"]
    for req in req_files:
        cmd += ["-r", req]
    print(f"\nUsing pip: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, cwd=REPO_ROOT, check=True)
    except subprocess.CalledProcessError as exc:
        print(f"pip install failed: {exc}")
        return False
    print("\nDone. Run commands directly, e.g.:")
    if target in ("web", "both"):
        print("  python fta_web/run.py")
    if target in ("desktop", "both"):
        print("  python src/FTA_Editor_UI.py")
    return True


def run_tests(runner_prefix: list) -> None:
    print("\nRunning tests...")
    try:
        result = subprocess.run(
            runner_prefix + ["pytest", "tests/", "-q"], cwd=REPO_ROOT
        )
        print("Tests passed" if result.returncode == 0 else "Some tests failed")
    except FileNotFoundError:
        print("pytest not available, skipping (add the 'test' or 'dev' extra to get it)")


def main() -> None:
    print("FTA Editor installer")
    print("=" * 40)

    if not check_python_version():
        sys.exit(1)
    check_graphviz()

    target = choose_target()

    have_uv = shutil.which("uv") is not None
    if have_uv:
        print("\nuv found -- using it (faster, and pins exact versions via uv.lock).")
        ok = install_with_uv(target)
        runner_prefix = ["uv", "run"]
    else:
        print(
            "\nuv not found -- falling back to pip. "
            "(Install uv from https://docs.astral.sh/uv/ for faster, "
            "reproducible installs.)"
        )
        ok = install_with_pip(target)
        runner_prefix = [sys.executable, "-m"]

    if not ok:
        sys.exit(1)

    choice = input("\nRun the test suite now? (y/N): ").strip().lower()
    if choice == "y":
        run_tests(runner_prefix)

    print("\nSetup complete.")


if __name__ == "__main__":
    main()
