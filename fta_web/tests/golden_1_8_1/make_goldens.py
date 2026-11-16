"""Regenerate the FN-28 golden outputs from the 1.8.1 release commit.

    uv run --frozen python fta_web/tests/golden_1_8_1/make_goldens.py <release-worktree>

``<release-worktree>`` is a checkout (for example ``git worktree add --detach
<dir> <commit>``) of the pinned release commit below, with its environment set
up (``uv sync --frozen --extra all --extra test``). The script refuses any
other commit. For every corpus file (``fta_web/examples/*.json`` and
``fta_web/tests/b2b/*.json`` except ``expected.json``) it runs the release
checkout's CLI (``uv run --frozen python fta_web/run.py ...`` with the checkout
as working directory and the file given as a repo-relative path) for

    quantify, cutsets, importance, validate   (each with --json)
    mc --json --n 2000 --seed 1 --time-limit 3600

and writes one JSON file per corpus file next to this script, plus
``manifest.json``. Every command is run twice; the two results must be equal
once ``elapsedMs`` (the only volatile key) is removed at any depth, and no
result may be cut short by time. ``elapsedMs`` is removed from the stored
goldens, so a comparison removes it from the fresh output too.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

GENERATOR_VERSION = 1
RELEASE_COMMIT = "c6d09f5b0d5363fc037f63d3ec7cf1c91186a798"
VOLATILE_KEYS = ("elapsedMs",)
HERE = Path(__file__).resolve().parent

CORPUS_DIRS = ("fta_web/examples", "fta_web/tests/b2b")
CORPUS_SKIP = ("expected.json",)

#: Per-file larger limits, keyed by repo-relative corpus path.
#: ``summaryTimeBudgetS`` (quantify's headline cut sets, 2 s in the product) and
#: ``validateTimeBudgetS`` (validate's truncation check, 2 s) are internal budgets
#: the CLI cannot change; a file given them runs its ``quantify`` and ``validate``
#: through ``cli_with_budgets.py``. ``mcTimeLimit`` (seconds) replaces --time-limit.
#: R00 and R03 need about 9 s for their cut sets, so at 2 s they are cut short by
#: time and the result would depend on the machine.
_SLOW = {"summaryTimeBudgetS": 300, "validateTimeBudgetS": 300}
LARGER_LIMITS: Dict[str, Dict[str, float]] = {
    "fta_web/tests/b2b/R00_random_legacy_400.json": dict(_SLOW),
    "fta_web/tests/b2b/R03_random_2000.json": dict(_SLOW),
}

DRIVER = "fta_web/tests/golden_1_8_1/cli_with_budgets.py"

MC_N = 2000
MC_SEED = 1
MC_TIME_LIMIT = 3600


def command_lines(rel: str) -> Dict[str, List[str]]:
    """CLI argument lists (after ``fta_web/run.py``) for one corpus file."""
    mc_time = LARGER_LIMITS.get(rel, {}).get("mcTimeLimit", MC_TIME_LIMIT)
    return {
        "quantify": ["quantify", rel, "--json"],
        "cutsets": ["cutsets", rel, "--json"],
        "importance": ["importance", rel, "--json"],
        "validate": ["validate", rel, "--json"],
        "mc": ["mc", rel, "--json", "--n", str(MC_N), "--seed", str(MC_SEED),
               "--time-limit", ("%g" % mc_time)],
    }


def entry_for(rel: str, name: str, args: List[str], driver_path: str = DRIVER) -> List[str]:
    """What follows ``python`` on the command line: ``fta_web/run.py <args>``, or
    the budget driver for quantify / validate of a file with larger budgets."""
    lim = LARGER_LIMITS.get(rel, {})
    if (name == "quantify" and "summaryTimeBudgetS" in lim) or             (name == "validate" and "validateTimeBudgetS" in lim):
        return [driver_path, "%g" % lim.get("summaryTimeBudgetS", 2.0),
                "%g" % lim.get("validateTimeBudgetS", 2.0)] + args
    return ["fta_web/run.py"] + args


def corpus(root: Path) -> List[str]:
    out: List[str] = []
    for d in CORPUS_DIRS:
        for p in sorted((root / d).glob("*.json")):
            if p.name not in CORPUS_SKIP:
                out.append("%s/%s" % (d, p.name))
    return out


def strip_volatile(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: strip_volatile(v) for k, v in value.items() if k not in VOLATILE_KEYS}
    if isinstance(value, list):
        return [strip_volatile(v) for v in value]
    return value


def time_truncated(value: Any, trail: str = "$") -> List[str]:
    """Paths in ``value`` that show a time cut-off."""
    found: List[str] = []
    if isinstance(value, dict):
        for k, v in value.items():
            here = "%s.%s" % (trail, k)
            if k == "truncatedByTime" and v:
                found.append(here)
            if k == "truncatedBy" and isinstance(v, list) and any("time" in str(x).lower() for x in v):
                found.append(here)
            found.extend(time_truncated(v, here))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            found.extend(time_truncated(v, "%s[%d]" % (trail, i)))
    return found


def run_cli(root: Path, argv: List[str]) -> Tuple[int, str]:
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    env.pop("VIRTUAL_ENV", None)
    proc = subprocess.run(
        ["uv", "run", "--frozen", "python"] + argv,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(root), env=env, timeout=900)
    return proc.returncode, proc.stdout


def parse_stdout(text: str) -> Any:
    try:
        return json.loads(text)
    except ValueError:
        return text


def check_no_absolute_path(root: Path, text: str, what: str) -> None:
    for form in {str(root), str(root).replace("\\", "/"), str(root.resolve()),
                 str(root.resolve()).replace("\\", "/")}:
        if form in text:
            raise SystemExit("%s: output contains the absolute path %s" % (what, form))


def run_one(root: Path, rel: str, name: str, args: List[str]) -> Dict[str, Any]:
    results = []
    driver = str(HERE / "cli_with_budgets.py")
    for _ in range(2):
        code, out = run_cli(root, entry_for(rel, name, args, driver))
        check_no_absolute_path(root, out, "%s %s" % (rel, name))
        results.append({"exitCode": code, "stdout": strip_volatile(parse_stdout(out))})
    if results[0] != results[1]:
        raise SystemExit("%s %s: not deterministic (two runs differ beyond elapsedMs)" % (rel, name))
    cut = time_truncated(results[0]["stdout"])
    if cut:
        raise SystemExit("%s %s: cut short by time at %s; add a larger limit for this file in "
                         "LARGER_LIMITS" % (rel, name, ", ".join(cut)))
    return results[0]


def dumps(obj: Any) -> str:
    return json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def golden_name(rel: str) -> str:
    parts = rel.split("/")
    group = "examples" if parts[1] == "examples" else "b2b"
    return "%s__%s" % (group, parts[-1])


def head_of(root: Path) -> str:
    proc = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                          capture_output=True, text=True)
    return proc.stdout.strip()


def main(argv: List[str]) -> int:
    resume = "--resume" in argv
    argv = [a for a in argv if a != "--resume"]
    if len(argv) != 2:
        print(__doc__)
        return 2
    root = Path(argv[1]).resolve()
    head = head_of(root)
    if head != RELEASE_COMMIT:
        print("refusing: %s is at %s, not the pinned release commit %s" % (root, head or "?", RELEASE_COMMIT))
        return 2
    files = corpus(root)
    manifest: Dict[str, Any] = {
        "generatorVersion": GENERATOR_VERSION,
        "releaseCommit": RELEASE_COMMIT,
        "volatileKeys": list(VOLATILE_KEYS),
        "volatileKeysStoredInGoldens": False,
        "pathHandling": ("Each corpus file is passed to the CLI as a repo-relative path with forward "
                         "slashes and the working directory is the repo root, so the CLI's own 'file' "
                         "field is that relative path; the generator fails if any output holds an "
                         "absolute path. Nothing needed rewriting."),
        "commandTemplates": {k: ["fta_web/run.py"] + v for k, v in command_lines("<corpus file>").items()},
        "entry": ("uv run --frozen python <first word of the command line>, working directory = "
                  "repo root; the driver cli_with_budgets.py only raises the two internal 2 s "
                  "budgets named in largerLimits (see its docstring)"),
        "largerLimits": LARGER_LIMITS,
        "determinism": "every command run twice; equal after removing elapsedMs",
        "files": {},
    }
    nonzero: List[str] = []
    for rel in files:
        data = (root / rel).read_bytes()
        out_name = golden_name(rel)
        if resume and (HERE / out_name).is_file():  # development shortcut after an interrupted run
            cmds = json.loads((HERE / out_name).read_text(encoding="utf-8"))["commands"]
        else:
            cmds = {name: run_one(root, rel, name, args) for name, args in command_lines(rel).items()}
        for name, res in cmds.items():
            if res["exitCode"] != 0:
                nonzero.append("%s %s=%d" % (rel, name, res["exitCode"]))
        (HERE / out_name).write_text(dumps({"file": rel, "commands": cmds}), encoding="utf-8", newline="\n")
        manifest["files"][rel] = {
            "golden": out_name,
            "inputSha256": hashlib.sha256(data).hexdigest(),
            "commands": {n: entry_for(rel, n, a) for n, a in command_lines(rel).items()},
            "exitCodes": {n: r["exitCode"] for n, r in cmds.items()},
        }
        print("ok %s" % rel, flush=True)
    (HERE / "manifest.json").write_text(dumps(manifest), encoding="utf-8", newline="\n")
    print("%d corpus files, %d goldens; non-zero exit codes: %s"
          % (len(files), len(files), nonzero or "none"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
