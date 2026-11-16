"""In-process 1.8.1 baselines (SPEC section 4, "Measurement conditions").

PERF-2   engine.summary on perf_ccf_301_nogroups.json
PERF-5   engine.summary on perf_alpha_301_nogroups.json
PERF-8   (in-process part) engine.summary on perf_ccf_301_nogroups.json

Condition: the Python function called directly, one discarded warm-up call,
then the median of 5 timed calls (``time.perf_counter``). The product code is
the one in ``--repo`` (the detached release worktree), not this branch; the
fixtures are read by path from ``--fixtures`` (this branch).

Run it with the release worktree's own environment, from that worktree::

    cd <release worktree>
    uv run --frozen --extra all --extra test python <this file> \
        --repo . --fixtures <f-0>/fta_web/tests/fixtures --out <result.json>

Nothing here imports the F0 branch's product code, and nothing is asserted:
it only measures and records every run.
"""
import argparse
import json
import os
import statistics
import sys
import time

WARMUPS = 1
RUNS = 5


def load(path):
    """The (tree, analysis) a document file gives, as the app loads it."""
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    return data["tree"], data.get("analysis")


def measure(engine, fixture):
    tree, raw_analysis = load(fixture)
    analysis, _problems = engine.coerce_analysis(raw_analysis)
    for _ in range(WARMUPS):
        engine.summary(tree, analysis)
    runs_ms = []
    result = None
    for _ in range(RUNS):
        started = time.perf_counter()
        result = engine.summary(tree, analysis)
        runs_ms.append((time.perf_counter() - started) * 1000.0)
    return {
        "fixture": os.path.basename(fixture),
        "call": "engine.summary(tree, analysis)",
        "warmups": WARMUPS,
        "runs_ms": runs_ms,
        "median_ms": statistics.median(runs_ms),
        "result": {
            "headline": result.get("headline"),
            "headlineMethod": result.get("headlineMethod"),
            "capped": result.get("capped"),
            "truncated": result.get("truncated"),
            "truncatedBy": result.get("truncatedBy"),
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--repo", required=True, help="the release worktree")
    parser.add_argument("--fixtures", required=True, help="folder with the committed fixtures")
    parser.add_argument("--out", required=True, help="result JSON to write")
    args = parser.parse_args()

    repo = os.path.abspath(args.repo)
    sys.path.insert(0, repo)
    sys.path.insert(0, os.path.join(repo, "fta_web", "core"))  # as fta_web/tests/conftest.py does
    from fta_web import engine  # noqa: E402

    if os.path.dirname(os.path.abspath(engine.__file__)) != os.path.join(repo, "fta_web"):
        raise SystemExit("engine was imported from %s, not from --repo %s" % (engine.__file__, repo))

    fixtures = os.path.abspath(args.fixtures)
    ccf = os.path.join(fixtures, "perf_ccf_301_nogroups.json")
    alpha = os.path.join(fixtures, "perf_alpha_301_nogroups.json")
    out = {
        "PERF-2": measure(engine, ccf),
        "PERF-5": measure(engine, alpha),
        "PERF-8": measure(engine, ccf),
        "python": sys.version.split()[0],
    }
    with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(out, handle, indent=2)
        handle.write("\n")
    for key in ("PERF-2", "PERF-5", "PERF-8"):
        print("%s median %.2f ms  runs %s" % (key, out[key]["median_ms"],
                                              ", ".join("%.2f" % r for r in out[key]["runs_ms"])))


if __name__ == "__main__":
    main()
