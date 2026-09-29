"""
Back-to-back (B2B) numeric comparison: the corpus in ``fta_web/tests/b2b/``
through every independent path, compared key by key.

Fast by default (the engine, the create_app() test client, the CLI as a
subprocess, the truth-table oracle, the vendored and the frozen desktop
cores). The large random trees, the real server, the packaged exe and a
second Python build run only with ``FTA_B2B_FULL=1`` (exe checks also need
the exe; see ``b2b_lib.exe_path``). ``fta_web/tests/b2b/run_b2b.py`` runs
everything and prints the comparison matrix.

What each path is compared on, and every intended divergence, is listed in
``fta_web/tests/b2b/README.md``.
"""
import copy
import json
import os
import sys
from pathlib import Path

import pytest

from fta_web.tests.b2b import b2b_lib as B

pytest.importorskip("flask")

FULL = os.environ.get("FTA_B2B_FULL") == "1"
full_only = pytest.mark.skipif(not FULL, reason="set FTA_B2B_FULL=1 (large trees, servers, exe)")
EXE = B.exe_path()
needs_exe = pytest.mark.skipif(EXE is None, reason="packaged fta_editor.exe not found")

FAST = B.corpus_names(large=False)
LARGE = [n for n in B.corpus_names() if n not in FAST]
NAMES = FAST + (LARGE if FULL else [])
EXPECTED = B.load_expected()
LEGACY = [n for n in NAMES if B.is_legacy(n)]
V17 = [n for n in NAMES if not B.is_legacy(n)]

#: What the frozen desktop core may differ by (fta_web/core/DIVERGENCE.md,
#: plus the 1.7.1 OR-UNION change), and what some trees must show.
DESKTOP_ALLOWED = {"D8", "D14", "D15", "D16", "D17", B.OR_LOG}
DESKTOP_MUST = {"L05_link_cycle.json": {"D17"}, "L07_eta_mode.json": {"D14"},
                "L08_prob_span.json": {"D14"}, "L10_duplicate_ids.json": {"D15"},
                "L12_top_not_root.json": {"D16"}, "L13_minified.json": {"D8"},
                "L16_tiny_or.json": {"D14", B.OR_LOG}}


def assert_rows(rows):
    """Mismatches fail; a documented divergence (``divergence``) does not."""
    bad = [r for r in rows if r.status in ("mismatch", "error")]
    assert not bad, "\n".join(
        "%s %s %s: %s (n=%d, max abs %.3g, max rel %.3g) %s %s" % (
            r.tree, r.path, r.metric, r.status, r.n, r.max_abs, r.max_rel, r.note, r.diffs[:4])
        for r in bad)


@pytest.fixture(scope="module")
def refs():
    return {name: B.run_engine(B.corpus_path(name)) for name in NAMES}


@pytest.fixture(scope="module")
def root(tmp_path_factory):
    """A writable copy of the corpus (open/save-as run against it)."""
    return B.copy_corpus(tmp_path_factory.mktemp("b2b") / "root", B.corpus_names())


# ---- the engine against hand-computed values and a truth-table oracle -----------------------


def test_corpus_is_what_make_corpus_writes(tmp_path):
    """The committed JSON files are exactly the generator's output."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("b2b_make_corpus", B.HERE / "make_corpus.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.HERE = tmp_path
    module.FILES.clear()
    module.EXPECTED.clear()
    module.main()
    for path in sorted(tmp_path.glob("*.json")):
        assert path.read_bytes() == (B.HERE / path.name).read_bytes(), path.name
    assert len(list(tmp_path.glob("*.json"))) == len(B.corpus_names()) + 1


def test_corpus_size_and_coverage():
    assert len(B.corpus_names()) >= 25
    assert len(LEGACY) >= 10 and len(V17) >= 15
    assert len([n for n in B.corpus_names() if n.startswith("R")]) >= 3


@pytest.mark.parametrize("name", sorted(n for n in EXPECTED if n in NAMES))
def test_hand_computed_values(refs, name):
    rows = B.check_expected(name, refs[name], EXPECTED[name])
    if "mc_means" in EXPECTED[name]:  # analytical lognormal means (F12)
        rows += [r for r in B.check_mc(name, refs[name], EXPECTED[name])
                 if r.metric.startswith("mean~analytical")]
    assert rows
    assert_rows(rows)


@pytest.mark.parametrize("name", NAMES)
def test_oracle_and_engine_invariants(refs, name):
    """Exact probability and minimal cut sets by truth table (<= 16 events,
    no PAND, no cycles); Monte Carlo = point estimate without uncertainty;
    lognormal means vs the analytical ones; summary = cut sets."""
    ref = refs[name]
    rows = (B.check_oracle(name, ref) + B.check_mc(name, ref, EXPECTED.get(name))
            + B.check_engine_internal(name, ref))
    assert_rows(rows)


def test_the_oracle_covers_enough_trees(refs):
    covered = [n for n in FAST if B.check_oracle(n, refs[n])]
    assert len(covered) >= 25, covered


# ---- the HTTP API (create_app() test client) -------------------------------------------------


@pytest.fixture(scope="module")
def api(refs, root):
    transport = B.ClientTransport(root)
    return {name: B.run_api(transport, root, name, refs[name],
                            per_node_limit=300 if name in LARGE else None)
            for name in NAMES}


@pytest.mark.parametrize("name", NAMES)
def test_api_matches_engine(refs, api, name):
    """Open, /state, /nodes/<id>, summary, cutsets, importance, uncertainty
    (seeded), validate, DOT labels at 6 s.f., XLSX, XML, JSON export,
    DOCX report at 6 s.f., save-as and reopen."""
    rows = B.api_rows(name, refs[name], api[name], "api:client")
    assert len(rows) >= 20 or refs[name]["meta"]["mode"] == "ETA"
    assert_rows(B.relabel_timing(rows, refs[name], api[name]))


def test_overrides_agree_across_engine_api_and_cli(root):
    """A changed mission time (settings / --mission-time) and one-run cut-set
    limits (the Cut Sets tab's body / --max-order --max-count --cutoff)."""
    transport = B.ClientTransport(root)
    rows = B.override_rows(list(B.OVERRIDE_TREES), transport, root, "overrides")
    assert len(rows) == 6 * len(B.OVERRIDE_TREES)
    assert_rows(rows)


# ---- the CLI (subprocess) ----------------------------------------------------------------------


@pytest.fixture(scope="module")
def cli():
    files = [B.corpus_path(n) for n in NAMES]
    outputs = {}
    for command in B.CLI_COMMANDS:
        code, payload, err = B.run_cli_batch(command, files)
        # ETA files make the FTA-only commands exit 1; validation errors too.
        assert code in (0, 1), (command, code, err)
        outputs[command] = payload
    return B.cli_results(outputs)


@pytest.mark.parametrize("name", NAMES)
def test_cli_matches_engine(refs, cli, name):
    rows = B.cli_rows(name, refs[name], cli.get(name, {}), "cli")
    assert rows
    assert_rows(B.relabel_timing(rows, refs[name], cli.get(name, {})))


@pytest.mark.parametrize("name", ["F14_mixed_plant.json", "T02_2oo3_expanded.json",
                                  "L16_tiny_or.json"])
def test_cli_csv_spot_check(refs, name):
    """--csv carries full precision (str(float)): parse it back exactly."""
    assert_rows(B.cli_csv_rows(name, refs[name]))


# ---- the 1.6 engines ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", LEGACY)
def test_vendored_16_core_matches_except_or_log(name):
    a = B.vendored_attribution(name)
    assert a.ok, a.detail
    assert set(a.divergences) <= {B.OR_LOG}, a.detail


@pytest.mark.parametrize("name", LEGACY)
def test_desktop_core_differences_are_all_documented(name):
    a = B.desktop_attribution(name)
    assert a.ok, a.detail
    assert set(a.divergences) <= DESKTOP_ALLOWED, a.divergences
    assert DESKTOP_MUST.get(name, set()) <= set(a.divergences), (a.divergences, a.detail)


@pytest.mark.parametrize("name", [n for n in V17 if n in FAST])
def test_17_files_in_the_desktop_core_behave_as_documented(name, tmp_path):
    ok, findings = B.desktop_compat(name, tmp_path)
    assert ok, findings


# ---- round trips ---------------------------------------------------------------------------------


@pytest.mark.parametrize("name", NAMES)
def test_engine_save_reopen_is_stable(refs, name, tmp_path):
    core = B.load_web(B.corpus_path(name))
    path = tmp_path / name
    ok, err = core.save_to_json(str(path))
    assert ok, err
    again = B.reload_json_bytes(path.read_bytes())
    ref = refs[name]
    rows = [B.compare(name, "roundtrip", m, ref[m], again[m], keys="both")
            for m in ("calc", "prob", "keys", "analysis")]
    assert_rows(rows)
    assert again["loadWarnings"]["kinds"] == ()  # the saved file needs no repair


# ---- determinism -------------------------------------------------------------------------------------

_HASHSEED_CHILD = r'''
import copy, json, sys
sys.path[:0] = [%(repo)r, %(core)r]
from fta_web import engine, cutsets, importance, uncertainty, lint
out = {}
for path in %(files)r:
    core = engine.WebCore(); core.load_from_json(path)
    tree, analysis = core.get_data(), core.analysis
    r = {"calc": [n.get("calculatedProbability") for n in core._walk(tree)],
         "lint": lint.run(tree, analysis)}
    if core.mode != "ETA":
        r["summary"] = engine.summary(copy.deepcopy(tree), analysis)
        r["cutsets"] = cutsets.compute(copy.deepcopy(tree), analysis)
        r["importance"] = importance.compute(r["cutsets"])
        r["mc"] = uncertainty.run(copy.deepcopy(tree), analysis, n=300, seed=7)
    out[path] = r
def strip(v):
    if isinstance(v, dict):
        return {k: strip(x) for k, x in v.items() if k != "elapsedMs"}
    if isinstance(v, list):
        return [strip(x) for x in v]
    return v
sys.stdout.write(json.dumps(strip(out), sort_keys=True))
'''


def test_results_do_not_depend_on_the_hash_seed():
    """Two processes with different PYTHONHASHSEED (string hashing, hence
    set/dict-of-str iteration order) must give bit-identical results."""
    import subprocess

    files = [str(B.corpus_path(n)) for n in FAST
             if n.startswith(("F14", "L04", "L05", "L10", "O04", "T02", "F12", "F16"))]
    code = _HASHSEED_CHILD % {"repo": str(B.REPO), "core": str(B.CORE_DIR), "files": files}
    outputs = []
    for seed in ("0", "4242"):
        env = dict(os.environ, PYTHONHASHSEED=seed, PYTHONUTF8="1")
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, env=env,
                              timeout=600)
        assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")[-2000:]
        outputs.append(proc.stdout)
    assert outputs[0] == outputs[1]
    assert len(json.loads(outputs[0])) == len(files) == 8


# ---- formatted output parity with the browser ------------------------------------------------------


def test_python_and_browser_formatters_agree_on_every_corpus_number(refs):
    if not B.node_available():
        pytest.skip("node is not installed")
    rows = B.numfmt_rows(list(refs.values()))
    assert_rows(rows)


# ---- the full run: real servers, the packaged exe, a second Python build ----------------------------


@full_only
def test_real_server_matches_engine(refs, root):
    server = B.ServerTransport(B.source_server_command(), root)
    try:
        rows = []
        for name in NAMES:
            got = B.run_api(server, root, name, refs[name],
                            per_node_limit=300 if name in LARGE else None)
            rows += B.relabel_timing(B.api_rows(name, refs[name], got, "api:server"),
                                     refs[name], got)
    finally:
        server.close()
    assert_rows(rows)


@pytest.fixture(scope="module")
def or_trees():
    """Trees whose numbers this branch's OR fix changed relative to the
    release the exe was built from."""
    return B.or_affected(NAMES)


@full_only
@needs_exe
def test_exe_cli_matches_engine(refs, or_trees):
    """The exe is the 1.7.0 release under CPython 3.14: it may differ from
    this branch by LIBM (last ulp) and the branch's fixes (FIXED:*) only.
    run_b2b.py also proves it bit-identical to its own source."""
    files = [B.corpus_path(n) for n in NAMES]
    outputs = {}
    for command in B.CLI_COMMANDS:
        code, payload, err = B.run_cli_batch(command, files, exe=EXE)
        assert code in (0, 1), (command, code, err)
        outputs[command] = payload
    got = B.cli_results(outputs)
    rows = []
    for name in NAMES:
        mine = got.get(name, {})
        exact = B.cli_rows(name, refs[name], mine, "exe:cli")
        loose = B.cli_rows(name, refs[name], mine, "exe:cli", rel=B.LIBM_REL)
        rows += B.classify_release(
            B.relabel_timing(B.cross_build(exact, loose), refs[name], mine), or_trees)
    assert_rows(rows)


@full_only
@needs_exe
def test_exe_server_matches_engine(refs, root, or_trees):
    subset = [n for n in NAMES if n[0] in "FTL"][:20]
    server = B.ServerTransport([str(EXE)], root)
    try:
        rows = []
        for name in subset:
            got = B.run_api(server, root, name, refs[name])
            exact = B.api_rows(name, refs[name], got, "exe:server")
            loose = B.api_rows(name, refs[name], got, "exe:server", rel=B.LIBM_REL)
            rows += B.classify_release(
                B.relabel_timing(B.cross_build(exact, loose), refs[name], got), or_trees)
    finally:
        server.close()
    assert_rows(rows)
