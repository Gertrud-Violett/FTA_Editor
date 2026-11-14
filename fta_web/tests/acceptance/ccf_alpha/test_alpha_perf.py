"""F2A BRIEF criterion 7 (PERF-5) on F0's ``perf_alpha_301.json``.

The fixture (SPEC 7.6): the 301-node tree of ``perf_ccf_301.json`` with five staggered alpha
groups A1..A5 of four members, alpha (0.95, 0.03, 0.01, 0.01), settings ``maxOrder 6, maxCount
5000, cutoff 1e-30``. Each group has 11 CCF events, 55 in all.

PERF-5: in-process ``engine.summary`` takes at most 1.5 s (provisional; median of 5 runs after a
warm-up run, as PERF-2 of F2) and returns ``capped`` false and no ``time``, ``count``,
``cutoff`` or ``error`` in ``truncatedBy``; the cut sets it used
(``engine.summary_with_cut_sets``) contain each of the 55 CCF events, and their number equals
F0's derived value (``EXPECTED_ALPHA_CUTSET_COUNT``, 321, recorded in ``make_perf_fixtures.py``).
Timings go to ``<repo>/.division/artifacts/perf/PERF-5.json`` (no absolute path in it).
"""
import importlib.util
import json
import platform
import re
import statistics
import sys
import time
from itertools import combinations
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
FIXTURES = REPO_ROOT / "fta_web" / "tests" / "fixtures"
FIXTURE = FIXTURES / "perf_alpha_301.json"
GENERATOR = FIXTURES / "make_perf_fixtures.py"
ARTIFACTS = REPO_ROOT / ".division" / "artifacts" / "perf"

BUDGET_S = 1.5
RUNS = 5
ABSOLUTE_PATH = re.compile(r"[A-Za-z]:[\\/]|\\\\|/Users/|/home/|/tmp/|/var/")
FORBIDDEN_TRUNCATION = {"time", "count", "cutoff", "error"}


def load_fixture():
    doc = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return doc["tree"], doc["analysis"]


def load_generator():
    assert GENERATOR.is_file(), "the generator is missing"
    spec = importlib.util.spec_from_file_location("make_perf_fixtures_for_alpha_perf", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def expected_ccf_ids(analysis):
    """The 55 event ids from the stored groups: every subset of size 2..4, members in group order."""
    ids = []
    for group in analysis["ccfGroups"]:
        members = group["members"]
        for k in range(2, len(members) + 1):
            for idxs in combinations(range(len(members)), k):
                ids.append("ccf:%s:%s" % (group["id"], "+".join(members[i] for i in idxs)))
    return ids


def write_artifact(name, payload):
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    assert not ABSOLUTE_PATH.search(text), "an artifact must not hold an absolute path"
    (ARTIFACTS / name).write_text(text, encoding="utf-8", newline="\n")


def test_the_fixture_has_five_groups_and_fifty_five_events():
    _tree, analysis = load_fixture()
    assert [g["id"] for g in analysis["ccfGroups"]] == ["A1", "A2", "A3", "A4", "A5"]
    ids = expected_ccf_ids(analysis)
    assert len(ids) == 55 == len(set(ids))


def test_perf_5_summary_of_the_301_node_fixture_with_five_alpha_groups():
    from fta_web import engine

    generator = load_generator()
    tree, analysis = load_fixture()
    wanted = expected_ccf_ids(analysis)

    warm = engine.summary(tree, analysis)  # warm-up (imports, caches)
    block = warm.get("ccf")
    assert block is not None and block.get("applied"), "the five alpha groups were not applied"
    assert [g["id"] for g in block["applied"]] == ["A1", "A2", "A3", "A4", "A5"]
    assert block["notApplied"] == []

    timings = []
    last = None
    for _ in range(RUNS):
        started = time.perf_counter()
        last = engine.summary(tree, analysis)
        timings.append(time.perf_counter() - started)
        assert last["capped"] is False
        assert last["headlineMethod"] == "mcub"
        assert not FORBIDDEN_TRUNCATION & set(last["truncatedBy"]), last["truncatedBy"]
    median = statistics.median(timings)

    summary, result = engine.summary_with_cut_sets(tree, analysis)
    assert result is not None
    found = {e["id"] for cs in result["cutSets"] for e in cs["events"]}
    missing = sorted(set(wanted) - found)
    assert not missing, "CCF events missing from the cut sets: %s" % missing   # all 55 used
    assert result["total"] == generator.EXPECTED_ALPHA_CUTSET_COUNT == 321
    assert not FORBIDDEN_TRUNCATION & set(result["truncatedBy"]), result["truncatedBy"]
    assert summary["capped"] is False and summary["headlineMethod"] == "mcub"

    write_artifact("PERF-5.json", {
        "id": "PERF-5",
        "what": "in-process engine.summary on the 301-node fixture with five staggered alpha groups",
        "fixture": "fta_web/tests/fixtures/perf_alpha_301.json",
        "protocol": "median of %d runs after one warm-up run" % RUNS,
        "budgetS": BUDGET_S,
        "seconds": median,
        "runsS": timings,
        "cutSets": result["total"],
        "ccfEvents": len(wanted),
        "capped": summary["capped"],
        "truncatedBy": result["truncatedBy"],
        "headlineMethod": summary["headlineMethod"],
        "python": platform.python_version(),
        "platform": sys.platform,
    })
    assert median <= BUDGET_S, "PERF-5: median %.3f s over %.1f s (all: %s)" % (
        median, BUDGET_S, ["%.3f" % t for t in timings])
