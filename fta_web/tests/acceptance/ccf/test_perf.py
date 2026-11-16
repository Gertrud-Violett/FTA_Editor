"""F2 BRIEF criteria 28 and 30 (PERF-2, PERF-4) on F0's ``perf_ccf_301.json``.

The fixture (SPEC 7.6): 301 nodes, ten beta groups G1..G10 with beta 0.1, the
settings ``maxOrder 6, maxCount 5000, cutoff 1e-30``. Its derived cut-set
count (92) and ``truncatedBy`` (``["order"]``) are the constants recorded in
``make_perf_fixtures.py`` (F0 derived them from a hand-expanded tree).

PERF-2: in-process ``engine.summary`` takes at most 1.0 s (median of 5 runs
after a warm-up run) and returns ``capped`` false, ``headlineMethod`` ``mcub``
and no ``time``, ``count``, ``cutoff`` or ``error`` in ``truncatedBy``; the cut
sets it used (``engine.summary_with_cut_sets``) contain each of the ten CCF
events, and their number and ``truncatedBy`` equal F0's derived values. The
timings go to ``<repo>/.division/artifacts/perf/PERF-2.json``.

PERF-4: Monte Carlo with n = 10,000 completes within the default 30 s limit
(``truncatedByTime`` false); the time goes to ``PERF-4.json``.

The artifacts hold no absolute path. They are written only for a run on which
the ten groups were applied (a run of the unchanged tree would time nothing
useful).
"""
import importlib.util
import json
import platform
import re
import statistics
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
FIXTURES = REPO_ROOT / "fta_web" / "tests" / "fixtures"
FIXTURE = FIXTURES / "perf_ccf_301.json"
GENERATOR = FIXTURES / "make_perf_fixtures.py"
ARTIFACTS = REPO_ROOT / ".division" / "artifacts" / "perf"

BUDGET_S = 1.0
RUNS = 5
MC_N = 10000
MC_LIMIT_S = 30.0
CCF_IDS = ["ccf:G%d" % k for k in range(1, 11)]
ABSOLUTE_PATH = re.compile(r"[A-Za-z]:[\\/]|\\\\|/Users/|/home/|/tmp/|/var/")


def load_fixture():
    doc = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return doc["tree"], doc["analysis"]


def load_generator():
    assert GENERATOR.is_file(), "the generator is missing"
    spec = importlib.util.spec_from_file_location("make_perf_fixtures_for_perf", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_artifact(name, payload):
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    path = ARTIFACTS / name
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    assert not ABSOLUTE_PATH.search(text), "an artifact must not hold an absolute path"
    path.write_text(text, encoding="utf-8", newline="\n")


def applied_ids(block):
    assert block is not None and block.get("applied"), "the ten CCF groups were not applied"
    return [g["id"] for g in block["applied"]]


def test_perf_2_summary_of_the_301_node_fixture_with_ten_groups():
    from fta_web import engine

    generator = load_generator()
    tree, analysis = load_fixture()

    warm = engine.summary(tree, analysis)  # warm-up (imports, caches)
    assert applied_ids(warm.get("ccf")) == ["G%d" % k for k in range(1, 11)]

    timings = []
    last = None
    for _ in range(RUNS):
        started = time.perf_counter()
        last = engine.summary(tree, analysis)
        timings.append(time.perf_counter() - started)
        assert last["capped"] is False
        assert last["headlineMethod"] == "mcub"
        assert not {"time", "count", "cutoff", "error"} & set(last["truncatedBy"]), last["truncatedBy"]
    median = statistics.median(timings)

    summary, result = engine.summary_with_cut_sets(tree, analysis)
    assert result is not None
    found = {e["id"] for cs in result["cutSets"] for e in cs["events"]}
    assert set(CCF_IDS) <= found, sorted(set(CCF_IDS) - found)  # all ten CCF events used
    assert result["total"] == generator.EXPECTED_CCF_CUTSET_COUNT
    assert result["truncatedBy"] == generator.EXPECTED_CCF_TRUNCATED_BY
    assert summary["truncatedBy"] == generator.EXPECTED_CCF_TRUNCATED_BY
    assert summary["capped"] is False and summary["headlineMethod"] == "mcub"

    write_artifact("PERF-2.json", {
        "id": "PERF-2",
        "what": "in-process engine.summary on the 301-node fixture with ten beta groups",
        "fixture": "fta_web/tests/fixtures/perf_ccf_301.json",
        "protocol": "median of %d runs after one warm-up run" % RUNS,
        "budgetS": BUDGET_S,
        "medianS": median,
        "runsS": timings,
        "cutSetTotal": result["total"],
        "truncatedBy": result["truncatedBy"],
        "headlineMethod": summary["headlineMethod"],
        "capped": summary["capped"],
        "python": platform.python_version(),
        "platform": sys.platform,
    })
    assert median <= BUDGET_S, "PERF-2: median %.3f s over %.1f s (all: %s)" % (
        median, BUDGET_S, ["%.3f" % t for t in timings])


def test_perf_4_monte_carlo_of_10000_trials_on_the_301_node_fixture():
    from fta_web import uncertainty

    tree, analysis = load_fixture()
    started = time.perf_counter()
    result = uncertainty.run(tree, analysis, n=MC_N, seed=1, time_limit=MC_LIMIT_S)
    wall = time.perf_counter() - started
    assert len(applied_ids(result.get("ccf"))) == 10
    assert result["method"] == "cutsets"

    write_artifact("PERF-4.json", {
        "id": "PERF-4",
        "what": "in-process Monte Carlo on the 301-node fixture with ten beta groups",
        "fixture": "fta_web/tests/fixtures/perf_ccf_301.json",
        "n": MC_N,
        "seed": 1,
        "limitS": MC_LIMIT_S,
        "completed": result["completed"],
        "truncatedByTime": result["truncatedByTime"],
        "wallS": wall,
        "elapsedMs": result["elapsedMs"],
        "python": platform.python_version(),
        "platform": sys.platform,
    })
    assert result["truncatedByTime"] is False
    assert result["completed"] == MC_N
    assert wall <= MC_LIMIT_S, "PERF-4: %.1f s over the %.0f s limit" % (wall, MC_LIMIT_S)
