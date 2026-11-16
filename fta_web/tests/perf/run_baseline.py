"""Measure the 1.8.1 baselines of SPEC section 4 and write baseline-1.8.1.json.

Runs ``baseline_inprocess.py`` (PERF-2, PERF-5, PERF-8 in-process) and
``baseline_browser.js`` (PERF-6, PERF-7, PERF-8 browser) against a detached
worktree at the final release commit, with the fixtures of this branch passed by
path, then merges both results (all runs, medians, conditions, machine, commit)::

    git worktree add --detach .worktrees/rel-181 <release commit>      # main folder
    (cd .worktrees/rel-181 && uv sync --frozen --extra all --extra test)
    cd <f-0 worktree>
    uv run --frozen python fta_web/tests/perf/run_baseline.py \
        --release .worktrees/rel-181 --commit <release commit> \
        --out <main folder>/.division/artifacts/perf/baseline-1.8.1.json

Nothing else CPU-heavy should run on the PC during the measurement. The browser
part needs ``npm ci`` in ``fta_web/tests/gui`` (Playwright) and port 8780 free.
Nothing is asserted: the Director sets the bounds from these numbers (SPEC 4).
"""
import argparse
import datetime
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(os.path.dirname(HERE), "fixtures")
FIXTURE_FILES = [
    "perf_ccf_301.json", "perf_alpha_301.json", "perf_ccf_301_nogroups.json",
    "perf_alpha_301_nogroups.json", "perf_grid_500.json", "perf_grid_500_paste.tsv",
]


def git(release, *args):
    return subprocess.run(["git", "-C", release] + list(args), check=True,
                          capture_output=True, text=True).stdout.strip()


def sha256(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--release", required=True, help="detached worktree at the release commit")
    parser.add_argument("--commit", required=True, help="the final release commit (full hash)")
    parser.add_argument("--out", required=True, help="baseline-1.8.1.json to write")
    parser.add_argument("--port", default="8780")
    args = parser.parse_args()

    release = os.path.abspath(args.release)
    head = git(release, "rev-parse", "HEAD")
    if head != args.commit:
        raise SystemExit("release worktree is at %s, not %s" % (head, args.commit))
    if git(release, "status", "--porcelain"):
        raise SystemExit("release worktree is not clean")

    scratch = tempfile.mkdtemp(prefix="fta_perf_run_")
    inproc_json = os.path.join(scratch, "inprocess.json")
    browser_json = os.path.join(scratch, "browser.json")

    subprocess.run(
        ["uv", "run", "--frozen", "--extra", "all", "--extra", "test", "python",
         os.path.join(HERE, "baseline_inprocess.py"), "--repo", ".",
         "--fixtures", FIXTURES, "--out", inproc_json],
        cwd=release, check=True)
    subprocess.run(
        ["node", os.path.join(HERE, "baseline_browser.js"), "--repo", release,
         "--fixtures", FIXTURES, "--out", browser_json, "--port", args.port],
        check=True)

    with open(inproc_json, encoding="utf-8") as handle:
        inproc = json.load(handle)
    with open(browser_json, encoding="utf-8") as handle:
        browser = json.load(handle)

    def stamp(item):
        item["releaseCommit"] = args.commit
        return item

    items = {
        "PERF-2": stamp(dict(inproc["PERF-2"], condition="in-process")),
        "PERF-5": stamp(dict(inproc["PERF-5"], condition="in-process")),
        "PERF-6": stamp(browser["PERF_6"]),
        "PERF-7": stamp(browser["PERF_7"]),
        "PERF-8": stamp({
            "condition": "in-process (engine.summary) and browser (one q edit in Details)",
            "parts": {
                "in_process": dict(inproc["PERF-8"], condition="in-process"),
                "browser": browser["PERF_8_browser"],
            },
        }),
    }
    machine = dict(browser["machine"])
    machine.update({"python": inproc["python"], "pythonPlatform": platform.platform(),
                    "note": "measurement PC (Windows 11); the release worktree and the fixtures sit under a Dropbox folder"})
    result = {
        "schema": 1,
        "purpose": "1.8.1 baselines for the Director's one-time PERF adjustment (SPEC section 4, OQ-17); no bound asserted",
        "release": {"commit": args.commit, "describe": git(release, "describe", "--tags", "--always")},
        "measuredAt": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "conditions": {
            "in-process": "Python function called directly, one discarded warm-up, median of 5 (time.perf_counter)",
            "browser": "fta_web/tests/gui/lib.js harness, Chromium, dev server by `uv run --frozen` on port %s, "
                       "app loaded and fixture opened before timing, one discarded warm-up, median of 5, "
                       "times taken in the page with performance.now()" % args.port,
        },
        "machine": machine,
        "fixtureSha256": {name: sha256(os.path.join(FIXTURES, name)) for name in FIXTURE_FILES},
        "items": items,
        "pageErrors": browser["pageErrors"],
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, indent=2)
        handle.write("\n")
    print("written", args.out)
    print("medians (ms): PERF-2 %.2f, PERF-5 %.2f, PERF-6 %.1f, PERF-7 %.1f, PERF-8 in-process %.2f / browser %.1f" % (
        items["PERF-2"]["median_ms"], items["PERF-5"]["median_ms"], items["PERF-6"]["median_ms"],
        items["PERF-7"]["median_ms"], items["PERF-8"]["parts"]["in_process"]["median_ms"],
        items["PERF-8"]["parts"]["browser"]["median_ms"]))


if __name__ == "__main__":
    sys.exit(main())
