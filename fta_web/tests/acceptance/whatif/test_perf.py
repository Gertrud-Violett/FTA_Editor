"""F4 BRIEF criterion 8 (PERF-8), in-process half: ``POST /api/whatif`` on ``perf_ccf_301.json``.

With the baseline cut sets already computed (the first call builds them), 20 calls with
factor 10 on a member of CCF group G1 each answer within 300 ms (provisional) through the
test client. min / median / max go to ``.division/artifacts/perf/PERF-8.json`` under the key
``"inProcess"`` (the file is merged, never replaced: the GUI section adds the key ``"browser"``
to the same file; there is no separate ``PERF-8-browser.json``).

The first what-if after an edit builds the baseline again; SPEC allows it up to the PERF-2
bound (1.0 s). The whole request, baseline build included, is held to that bound, and the
number is recorded.

The artifact holds no absolute path and is written only for a run whose answers were
cache hits of an MCUB headline with the ten groups applied.
"""
import json
import platform
import re
import statistics
import sys
import time

import pytest

import whatif_support as W

BOUND_MS = 300.0
CALLS = 20
FACTOR = 10
EVENT = "C0_1_0"          # a member of group G1 (perf_ccf_301.json)
FIRST_CALL_BOUND_S = 1.0  # the PERF-2 bound (SPEC PERF-8)
ARTIFACT = W.ARTIFACTS / "PERF-8.json"
ABSOLUTE_PATH = re.compile(r"[A-Za-z]:[\\/]|\\\\|/Users/|/home/|/tmp/|/var/")


def merge_in_process(**fields):
    """Read PERF-8.json (if any), update ``inProcess`` and write it back; keep other keys."""
    W.ARTIFACTS.mkdir(parents=True, exist_ok=True)
    data = {}
    if ARTIFACT.is_file():
        try:
            data = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        except ValueError:
            data = {}
    block = data.get("inProcess")
    block = block if isinstance(block, dict) else {}
    block.update(fields)
    data.update({
        "id": "PERF-8",
        "what": "POST /api/whatif on the 301-node fixture with ten beta groups",
        "inProcess": block,
    })
    text = json.dumps(data, indent=2, sort_keys=True) + "\n"
    assert not ABSOLUTE_PATH.search(text), "an artifact must not hold an absolute path"
    ARTIFACT.write_text(text, encoding="utf-8", newline="\n")


def timed_post(api, factors):
    payload = api.payload(factors)           # the revision lookup is not part of the timing
    started = time.perf_counter()
    status, body = api.post(W.URL, payload)
    elapsed = time.perf_counter() - started
    assert status == 200, (status, body)
    return elapsed, body


@pytest.fixture
def perf(api):
    api.open_doc(W.load_perf_fixture())
    return api


def test_perf_8_twenty_hits_with_factor_10_on_a_group_member(perf):
    first_s, first = timed_post(perf, {EVENT: FACTOR})        # builds the baseline
    assert first["cache"] == "miss"
    assert first["method"] == "mcub"
    assert len(first["groups"]) == 10                         # the ten groups are applied
    group = next(g for g in first["groups"] if g["id"] == "G1")
    assert EVENT in group["members"]
    assert [r["id"] for r in first["events"]] == [EVENT] + [
        m for m in group["members"] if m != EVENT]

    timings = []
    for _ in range(CALLS):
        elapsed, body = timed_post(perf, {EVENT: FACTOR})
        assert body["cache"] == "hit" and body["baselineMs"] == 0.0
        assert body["whatIf"] == first["whatIf"]
        timings.append(elapsed * 1000.0)
    assert first["baseline"] == perf.headline()
    assert first["whatIf"] > first["baseline"] > 0
    # The factor moves this top event by only a few parts in 1e10, so "bigger than the baseline"
    # proves little: the number must be the headline of the same file with the members' q typed
    # in by hand (10 * 1e-3 for every member of G1), through the existing engine.
    hand = W.hand_headline(W.load_perf_fixture(), set(group["members"]), FACTOR * 1e-3)
    assert hand["headlineMethod"] == "mcub"
    assert first["whatIf"] == W.rel(hand["headline"], 1e-12)
    assert first["ratio"] == W.rel(first["whatIf"] / first["baseline"], 1e-12)

    merge_in_process(
        fixture="fta_web/tests/fixtures/perf_ccf_301.json",
        protocol="first call builds the baseline; then %d calls with factor %d on %s" % (
            CALLS, FACTOR, EVENT),
        boundMs=BOUND_MS, calls=CALLS, factor=FACTOR, event=EVENT,
        minMs=min(timings), medianMs=statistics.median(timings), maxMs=max(timings),
        runsMs=timings, firstCallMs=first_s * 1000.0,
        cutSetsMethod=first["method"], groupsApplied=len(first["groups"]),
        python=platform.python_version(), platform=sys.platform)
    assert max(timings) <= BOUND_MS, "PERF-8: slowest %.1f ms over %.0f ms (all: %s)" % (
        max(timings), BOUND_MS, ["%.1f" % t for t in timings])


def test_perf_8_the_first_call_after_an_edit_rebuilds_within_the_perf_2_bound(perf):
    timed_post(perf, {EVENT: FACTOR})                           # warm
    hit_s, hit = timed_post(perf, {EVENT: FACTOR})
    assert hit["cache"] == "hit"

    perf.edit("C0_1_0", name="Feed pump edited")                # a Details edit
    rebuilt_s, rebuilt = timed_post(perf, {EVENT: FACTOR})
    assert rebuilt["cache"] == "miss"
    assert rebuilt["baselineMs"] > 0
    # a rename: the same numbers (the cut sets may rank differently after a rename, and
    # mcub_of depends on the order in the last bits, so equal to 1e-12 and not bit for bit)
    assert rebuilt["method"] == "mcub"
    assert rebuilt["whatIf"] == W.rel(hit["whatIf"], 1e-12)
    assert rebuilt["baseline"] == W.rel(hit["baseline"], 1e-12)
    after_s, after = timed_post(perf, {EVENT: FACTOR})
    assert after["cache"] == "hit"

    merge_in_process(
        firstCallAfterEditMs=rebuilt_s * 1000.0, firstCallAfterEditBoundMs=FIRST_CALL_BOUND_S * 1000.0,
        hitBeforeEditMs=hit_s * 1000.0, hitAfterEditMs=after_s * 1000.0)
    assert rebuilt_s <= FIRST_CALL_BOUND_S, "first call after an edit took %.2f s (bound %.1f s)" % (
        rebuilt_s, FIRST_CALL_BOUND_S)
    assert after_s * 1000.0 <= BOUND_MS


def test_the_artifact_has_the_documented_shape_and_no_absolute_path(perf):
    test_perf_8_twenty_hits_with_factor_10_on_a_group_member(perf)
    data = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    block = data["inProcess"]
    assert {"minMs", "medianMs", "maxMs", "boundMs", "calls"} <= set(block)
    assert block["minMs"] <= block["medianMs"] <= block["maxMs"]
    assert not ABSOLUTE_PATH.search(ARTIFACT.read_text(encoding="utf-8"))
