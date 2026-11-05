"""F4 BRIEF criteria 6 and 8 (DESIGN 2.2): the baseline is cached once per document version.

``fta_web.whatif`` keeps one entry, keyed ``(id(state), documentSerial, revision)`` and
guarded by equality of the cached tree and analysis with the live ones. Every response
says ``cache: "miss"`` or ``"hit"`` and ``baselineMs`` (0.0 on a hit). ``cache_info()``
returns ``{"hits", "misses", "size", "key"}``, ``clear_cache()`` empties the entry and the
counters. A summary cut short by time (``"time"`` in ``truncatedBy``) is never cached.

``fta_web.whatif`` is imported inside each test: until F4 exists a test fails on that
import (or on the 404 of the route) and on nothing else.
"""
import pytest

import whatif_support as W


def counters(module):
    info = module.cache_info()
    return info["hits"], info["misses"], info["size"]


def test_an_empty_cache_and_clear_cache_reset_everything(r1):
    whatif = W.whatif_module()
    assert whatif.cache_info() == {"hits": 0, "misses": 0, "size": 0, "key": None}
    r1.whatif_ok({"A": 10})
    r1.whatif_ok({"A": 10})
    assert counters(whatif) == (1, 1, 1)
    whatif.clear_cache()
    assert whatif.cache_info() == {"hits": 0, "misses": 0, "size": 0, "key": None}
    assert r1.whatif_ok({"A": 10})["cache"] == "miss"


def test_first_call_is_a_miss_the_next_ones_are_hits(r1):
    whatif = W.whatif_module()
    first = r1.whatif_ok({"A": 10})
    assert first["cache"] == "miss"
    assert isinstance(first["baselineMs"], (int, float)) and first["baselineMs"] >= 0
    assert counters(whatif) == (0, 1, 1)

    second = r1.whatif_ok({"A": 5})            # other factors, same version
    third = r1.whatif_ok({})
    assert second["cache"] == "hit" and third["cache"] == "hit"
    assert second["baselineMs"] == 0.0 and third["baselineMs"] == 0.0
    assert counters(whatif) == (2, 1, 1)

    again = r1.whatif_ok({"A": 10})            # same request: same answer, to the float
    assert again["cache"] == "hit"
    assert again["whatIf"] == first["whatIf"] and again["baseline"] == first["baseline"]
    assert again["events"] == first["events"]


def test_the_key_names_the_document_version(r1):
    whatif = W.whatif_module()
    r1.whatif_ok({"A": 10})
    fields = r1.fields()
    key = list(whatif.cache_info()["key"])
    assert len(key) == 3
    assert key[1:] == [fields["documentSerial"], fields["revision"]]


def test_an_edit_makes_the_next_call_a_miss_and_the_one_after_a_hit(r1):
    whatif = W.whatif_module()
    r1.whatif_ok({"A": 10})
    assert r1.whatif_ok({"A": 10})["cache"] == "hit"
    r1.edit("C", name="Sensor C edited")
    fields = r1.fields()
    after = r1.whatif_ok({"A": 10})
    assert after["cache"] == "miss"
    assert counters(whatif) == (1, 2, 1)           # one entry: the new version replaced the old
    assert list(whatif.cache_info()["key"])[1:] == [fields["documentSerial"], fields["revision"]]
    assert r1.whatif_ok({"A": 10})["cache"] == "hit"
    assert counters(whatif) == (2, 2, 1)


def test_a_probability_edit_is_seen_in_the_new_baseline(r1):
    """C 0 -> 0.5 adds the cut set {C}: the baseline moves, and the cached one is not served."""
    old = r1.whatif_ok({})
    r1.edit("C", probability=0.5)
    new = r1.whatif_ok({})
    assert new["cache"] == "miss"
    assert new["baseline"] != old["baseline"]
    assert new["baseline"] == r1.headline()
    assert new["baseline"] > 0.5


@pytest.mark.parametrize("step", ["undo", "redo"])
def test_undo_and_redo_are_misses(r1, step):
    r1.edit("C", name="Sensor C edited")
    if step == "redo":
        assert r1.post("/api/undo")[0] == 200
    r1.whatif_ok({"A": 10})
    assert r1.post("/api/" + step)[0] == 200
    assert r1.whatif_ok({"A": 10})["cache"] == "miss"


def test_a_new_document_and_an_open_of_the_same_file_are_misses(r1):
    r1.whatif_ok({})
    assert r1.whatif_ok({})["cache"] == "hit"
    r1.open_doc(W.r1_doc())                       # same content, new documentSerial
    assert r1.whatif_ok({})["cache"] == "miss"
    assert r1.post("/api/new", {"force": True})[0] == 200
    assert r1.whatif_ok({})["cache"] == "miss"


def test_a_change_of_the_live_tree_without_a_revision_bump_is_not_served_from_the_cache(r1):
    """DESIGN D2: the equality guard. The live tree is changed behind the revision's back
    (as code that mutates ``state.core`` without ``mark_dirty`` would); same key, other tree."""
    from fta_web.state import get_state

    r1.whatif_ok({})
    before = r1.fields()
    state = get_state()
    with state.lock:
        state.core.find_node_by_id("C")["probability"] = 0.25
    assert r1.fields() == before                    # the premise: no bump
    body = r1.whatif_ok({})
    assert body["cache"] == "miss"
    assert body["baseline"] == r1.headline()
    assert body["baseline"] > 0.25


def test_a_change_of_the_live_analysis_without_a_revision_bump_is_not_served_from_the_cache(r1):
    from fta_web.state import get_state

    first = r1.whatif_ok({})
    assert first["baseline"] == W.rel(W.R1_BASELINE, 1e-9)
    state = get_state()
    with state.lock:
        state.core.analysis.setdefault("cutsets", {})["cutoff"] = 1e-6
    body = r1.whatif_ok({})
    assert body["cache"] == "miss"
    assert body["baseline"] == W.rel(1e-4, 1e-9)
    assert body["note"] == "cutsets_from_nominal"


def test_a_hit_does_not_expand_the_tree_again(r1, monkeypatch):
    """The point of the cache (PERF-8): cut sets are computed once per version."""
    from fta_web import cutsets

    calls = []
    real = cutsets.compute

    def counting(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(cutsets, "compute", counting)
    r1.whatif_ok({"A": 10})
    built = len(calls)
    assert built >= 1
    for factors in ({"A": 5}, {"B": 0.5}, {}, {"A": 100}, {"C": 3}):
        assert r1.whatif_ok(factors)["cache"] == "hit"
    assert len(calls) == built
    r1.edit("C", name="Sensor C edited")
    r1.whatif_ok({"A": 10})
    assert len(calls) > built


def test_requests_refused_before_the_computation_do_not_touch_the_cache(r1):
    whatif = W.whatif_module()
    r1.whatif_ok({})
    before = whatif.cache_info()
    W.assert_error(r1.whatif({"A": "x"}), 400, "INVALID_FIELD", field="factor")
    W.assert_error(r1.whatif({"A": 10}, revision=10 ** 6), 409, "STALE_REVISION")
    W.assert_error(r1.whatif({"A": 10}, revision="x"), 400, "INVALID_FIELD", field="revision")
    assert whatif.cache_info() == before
    r1.post("/api/metadata", {"mode": "ETA"})
    W.assert_error(r1.whatif({"A": 10}), 409, "MODE_UNSUPPORTED")
    assert whatif.cache_info() == before


# ------------------------------------------------- a timed-out baseline is not cached


def _times_out(monkeypatch):
    from fta_web import cutsets

    def fail(*args, **kwargs):
        raise cutsets.CutsetError("time", "The cut-set time budget ran out.")

    monkeypatch.setattr(cutsets, "compute", fail)


def test_a_timed_out_baseline_is_not_cached_with_an_applied_group(r1):
    """R1 has an applied group: when the cut sets run out of time the headline is incomplete
    (FN-21). The answer is given (200) but nothing is stored: the next call builds again, and
    once the cut sets work again the baseline is built, stored and then served."""
    from fta_web import cutsets

    whatif = W.whatif_module()
    real = cutsets.compute
    patch = pytest.MonkeyPatch()
    try:
        _times_out(patch)
        first = r1.whatif_ok({"A": 10})
        assert first["cache"] == "miss"
        assert "time" in first["truncatedBy"]
        assert first["method"] == "incomplete" and first["whatIf"] is None
        assert counters(whatif) == (0, 1, 0)
        second = r1.whatif_ok({"A": 10})
        assert second["cache"] == "miss"             # not served from a stored timed-out entry
        assert counters(whatif) == (0, 2, 0)
    finally:
        patch.undo()
    assert cutsets.compute is real

    healed = r1.whatif_ok({"A": 10})
    assert healed["cache"] == "miss" and healed["method"] == "mcub"
    assert healed["whatIf"] == W.rel(W.R1_F10, 1e-9)
    assert counters(whatif) == (0, 3, 1)
    assert r1.whatif_ok({"A": 10})["cache"] == "hit"


def test_a_timed_out_baseline_is_not_cached_for_a_tree_walk_document(models, monkeypatch):
    whatif = W.whatif_module()
    _times_out(monkeypatch)
    first = models.whatif_ok({"RATE": 10})
    second = models.whatif_ok({"RATE": 10})
    assert first["cache"] == "miss" and second["cache"] == "miss"
    assert "time" in first["truncatedBy"]
    assert first["method"] == "treeWalk"             # the summary's own fallback
    # a what-if made from an empty cut-set list would be 0: the number must be the real one
    assert first["whatIf"] == W.rel(W.MODELS_RATE_10, 1e-9)
    assert second["whatIf"] == first["whatIf"]
    assert first["baseline"] == W.rel(W.MODELS_BASELINE, 1e-9)
    assert counters(whatif) == (0, 2, 0)
