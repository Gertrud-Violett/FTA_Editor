"""
Run every back-to-back path over the corpus and print the comparison matrix.

    uv run --frozen --extra all python fta_web/tests/b2b/run_b2b.py
    FTA_B2B_FULL=1 uv run --frozen --extra all python fta_web/tests/b2b/run_b2b.py

Without ``FTA_B2B_FULL=1`` the large random trees (``R*.json``) are left
out; everything else always runs: the engine checks (hand-computed values,
truth-table oracle, Monte Carlo properties), the create_app() test client, a
real ``run.py`` server, the CLI (JSON and CSV), the vendored 1.6 core, the
frozen desktop core, 1.7 files in the desktop core, engine round trips, the
browser's number formatter (node), and -- when present -- the packaged
``fta_editor.exe`` (CLI and server) and the source CLI under a second Python
build (``.venv314``, see README.md).

Only processes this script starts are stopped. Exit code 1 when any row is a
mismatch (documented divergences do not count).

Options: ``--only PATTERN`` (fnmatch on tree names), ``--json PATH`` (write
every row), ``--no-exe``, ``--no-server``, ``--details N`` (mismatch rows to
print, default 40).
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
import tempfile
import time
from collections import OrderedDict, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))

from fta_web.tests.b2b import b2b_lib as B  # noqa: E402

STATUS_CHAR = {"match": ".", "divergence": "d", "mismatch": "X", "error": "E", "skip": "s"}


def second_python() -> Path | None:
    """A second Python build for the cross-build check (``.venv314``)."""
    raw = os.environ.get("FTA_B2B_PY2")
    if raw:
        path = Path(raw)
        return path if path.is_file() else None
    for name in (".venv314", ".venv313", ".venv312"):
        path = B.REPO / name / "Scripts" / "python.exe"
        if not path.is_file():
            path = B.REPO / name / "bin" / "python"
        if path.is_file():
            return path
    return None


def python_version(python: Path | str) -> str:
    out = subprocess.run([str(python), "-c", "import sys; print(sys.version.split()[0])"],
                         capture_output=True, text=True, timeout=60)
    return out.stdout.strip()


def cli_batch_results(names, exe=None, python=None, run_py=None):
    files = [B.corpus_path(n) for n in names]
    outputs = {}
    for command in B.CLI_COMMANDS:
        code, payload, err = B.run_cli_batch(command, files, exe=exe, python=python,
                                             run_py=run_py)
        if code not in (0, 1) or payload is None:
            raise RuntimeError("%s %s exited %s: %s" % (exe or python or "cli", command, code,
                                                        err[-800:]))
        outputs[command] = payload
    return B.cli_results(outputs)


def same(tree, path, a, b):
    """Two Results of the same kind, metric by metric, bit for bit."""
    return [B.compare(tree, path, m, a[m], b[m], keys="both")
            for m in sorted(set(a) & set(b)) if not m.startswith("_") and isinstance(a[m], dict)]


def api_run(transport, root, names, refs, large):
    return {n: B.run_api(transport, root, n, refs[n], per_node_limit=300 if n in large else None)
            for n in names}


def cross(name, ref, got, maker):
    exact = maker(0.0)
    loose = maker(B.LIBM_REL)
    return B.relabel_timing(B.cross_build(exact, loose), ref, got)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--only", help="fnmatch pattern on tree names")
    parser.add_argument("--json", help="write every row to this file")
    parser.add_argument("--no-exe", action="store_true")
    parser.add_argument("--no-server", action="store_true")
    parser.add_argument("--details", type=int, default=40)
    args = parser.parse_args(argv)

    full = os.environ.get("FTA_B2B_FULL") == "1"
    names = B.corpus_names(large=full)
    if args.only:
        names = [n for n in names if fnmatch.fnmatch(n, args.only)]
    large = [n for n in names if n.startswith(B.LARGE_PREFIX)]
    exe = None if args.no_exe else B.exe_path()
    py2 = second_python()
    expected = B.load_expected()
    started = time.perf_counter()
    rows = []
    timings = OrderedDict()

    def phase(label):
        timings[label] = time.perf_counter()
        print("[%6.1fs] %s" % (time.perf_counter() - started, label), flush=True)

    print("FTA Editor back-to-back run: %d trees (%s), Python %s, exe %s, 2nd Python %s"
          % (len(names), "full" if full else "fast; FTA_B2B_FULL=1 adds the large trees",
             sys.version.split()[0], exe or "not found",
             ("%s (%s)" % (py2, python_version(py2))) if py2 else "not found"))

    phase("engine reference")
    refs = {n: B.run_engine(B.corpus_path(n)) for n in names}

    phase("engine checks: expected / oracle / Monte Carlo / internal")
    for n in names:
        ref = refs[n]
        rows += B.check_expected(n, ref, expected.get(n, {})) if n in expected else []
        rows += B.check_oracle(n, ref)
        rows += B.check_mc(n, ref, expected.get(n))
        rows += B.check_engine_internal(n, ref)

    tmp = Path(tempfile.mkdtemp(prefix="fta_b2b_"))
    root = B.copy_corpus(tmp / "root", B.corpus_names())

    phase("api:client (create_app test client)")
    client = B.ClientTransport(root)
    for n in names:
        got = B.run_api(client, root, n, refs[n], per_node_limit=300 if n in large else None)
        rows += B.relabel_timing(B.api_rows(n, refs[n], got, "api:client"), refs[n], got)

    if not args.no_server:
        phase("api:server (run.py over HTTP)")
        server = B.ServerTransport(B.source_server_command(), root)
        try:
            for n in names:
                got = B.run_api(server, root, n, refs[n],
                                per_node_limit=300 if n in large else None)
                rows += B.relabel_timing(B.api_rows(n, refs[n], got, "api:server"), refs[n], got)
        finally:
            server.close()

    phase("cli (--json, one batch per command)")
    cli = cli_batch_results(names)
    for n in names:
        rows += B.relabel_timing(B.cli_rows(n, refs[n], cli.get(n, {}), "cli"), refs[n],
                                 cli.get(n, {}))

    phase("cli:csv spot checks")
    for n in [x for x in ("F14_mixed_plant.json", "T02_2oo3_expanded.json", "L16_tiny_or.json",
                          "O04_random_oracle.json") if x in names]:
        rows += B.cli_csv_rows(n, refs[n])

    phase("legacy_core (vendored 1.6 FTACore) and desktop (frozen FTACore)")
    for n in names:
        if not B.is_legacy(n):
            continue
        for label, attribution in (("legacy_core", B.vendored_attribution(n)),
                                   ("desktop", B.desktop_attribution(n))):
            status = "match" if attribution.ok and not attribution.divergences else (
                "divergence" if attribution.ok else "mismatch")
            rows.append(B.Row(n, label, "calculatedProbability", status, 1,
                              note=" / ".join(attribution.divergences + attribution.detail)))

    phase("desktop_compat (1.7 files in the desktop core)")
    for n in names:
        if B.is_legacy(n) or n in large:
            continue
        ok, findings = B.desktop_compat(n, tmp)
        rows.append(B.Row(n, "desktop_compat", "documented claims", "match" if ok else "mismatch",
                          len(findings), note="; ".join(f for f in findings if f.startswith("FAIL"))
                          or findings[-1] if findings else ""))

    phase("roundtrip:engine (load -> save -> load)")
    for n in names:
        core = B.load_web(B.corpus_path(n))
        path = tmp / ("rt_" + n)
        core.save_to_json(str(path))
        again = B.reload_json_bytes(path.read_bytes())
        for m in ("calc", "prob", "keys", "analysis"):
            rows.append(B.compare(n, "roundtrip:engine", m, refs[n][m], again[m], keys="both"))

    phase("numfmt:js (browser formatter via node)")
    rows += B.numfmt_rows(list(refs.values()))

    if py2 is not None:
        phase("cli:py2 (this branch's CLI under Python %s)" % python_version(py2))
        py2_cli = cli_batch_results(names, python=py2)
        for n in names:
            got = py2_cli.get(n, {})
            rows += cross(n, refs[n], got,
                          lambda rel, n=n, got=got: B.cli_rows(n, refs[n], got, "cli:py2", rel=rel))

    # The packaged exe is the release: it must compute exactly what its own
    # source (RELEASE_COMMIT) computes under the same Python version; and the
    # release's source must differ from this branch only by the branch's fixes.
    src_run_py = B.export_commit(B.RELEASE_COMMIT, tmp / "release_src")
    phase("release: %s source CLI under this Python" % B.RELEASE_COMMIT)
    or_trees = B.or_affected(names)
    rel_cli = cli_batch_results(names, run_py=src_run_py)
    for n in names:
        got = rel_cli.get(n, {})
        rows += B.classify_release(B.relabel_timing(
            B.cli_rows(n, refs[n], got, "release->branch"), refs[n], got), or_trees)
    if exe is not None:
        phase("exe:cli (%s)" % exe)
        exe_cli = cli_batch_results(names, exe=exe)
        if py2 is not None:
            rel_py2 = cli_batch_results(names, python=py2, run_py=src_run_py)
            for n in names:
                rows += B.relabel_timing(same(n, "exe:cli==src", rel_py2.get(n, {}),
                                              exe_cli.get(n, {})), rel_py2.get(n, {}),
                                         exe_cli.get(n, {}))
        for n in names:  # and, loosely, against this branch
            got = exe_cli.get(n, {})
            rows += B.classify_release(cross(n, refs[n], got, lambda rel, n=n, got=got: B.cli_rows(
                n, refs[n], got, "exe:cli", rel=rel)), or_trees)
        if not args.no_server:
            phase("exe:server (and the release source's server under Python %s)"
                  % (python_version(py2) if py2 else "-"))
            server = B.ServerTransport([str(exe)], root)
            try:
                exe_api = api_run(server, root, names, refs, large)
            finally:
                server.close()
            if py2 is not None:
                server = B.ServerTransport(B.source_server_command(py2, src_run_py), root)
                try:
                    src_api = api_run(server, root, names, refs, large)
                finally:
                    server.close()
                for n in names:
                    rows += B.relabel_timing(same(n, "exe:server==src", src_api[n], exe_api[n]),
                                             src_api[n], exe_api[n])
            for n in names:
                got = exe_api[n]
                rows += B.classify_release(cross(n, refs[n], got, lambda rel, n=n, got=got:
                                                 B.api_rows(n, refs[n], got, "exe:server",
                                                            rel=rel)), or_trees)
    phase("done")
    elapsed = time.perf_counter() - started

    report(rows, names, elapsed, args.details)
    if args.json:
        Path(args.json).write_text(json.dumps([row_dict(r) for r in rows], indent=1,
                                              ensure_ascii=False, default=str), encoding="utf-8")
        print("rows written to %s" % args.json)
    return 1 if any(r.status in ("mismatch", "error") for r in rows) else 0


def row_dict(r):
    return {"tree": r.tree, "path": r.path, "metric": r.metric, "status": r.status, "n": r.n,
            "maxAbs": r.max_abs, "maxRel": r.max_rel, "note": r.note,
            "diffs": [list(map(str, d)) for d in r.diffs]}


def report(rows, names, elapsed, details):
    paths = list(OrderedDict.fromkeys(r.path for r in rows))
    print()
    print("=" * 100)
    print("MATRIX SUMMARY  (%d rows, %d trees, %.0f s)" % (len(rows), len(names), elapsed))
    print("=" * 100)
    head = "%-18s %6s %6s %8s %6s %11s %9s %6s %11s %11s" % (
        "path", "trees", "rows", "compared", "match", "divergence", "mismatch", "skip",
        "max abs", "max rel")
    print(head)
    print("-" * len(head))
    totals = defaultdict(int)
    for p in paths:
        sub = [r for r in rows if r.path == p]
        counts = defaultdict(int)
        for r in sub:
            counts[r.status] += 1
        max_abs = max((r.max_abs for r in sub), default=0.0)
        max_rel = max((r.max_rel for r in sub), default=0.0)
        print("%-18s %6d %6d %8d %6d %11d %9d %6d %11.3g %11.3g" % (
            p, len({r.tree for r in sub}), len(sub), sum(r.n for r in sub), counts["match"],
            counts["divergence"], counts["mismatch"] + counts["error"], counts["skip"],
            max_abs, max_rel))
        for key in ("match", "divergence", "mismatch", "skip"):
            totals[key] += counts[key]
        totals["error"] += counts["error"]
    print("-" * len(head))
    print("%-18s %6s %6d %8d %6d %11d %9d %6d" % (
        "TOTAL", "", len(rows), sum(r.n for r in rows), totals["match"], totals["divergence"],
        totals["mismatch"] + totals["error"], totals["skip"]))

    print()
    print("TREE x PATH  (. match   d documented divergence   X mismatch   s skip   blank n/a)")
    width = max(len(p) for p in paths)
    for i in range(width):
        print(" " * 29 + " ".join(p[i] if i < len(p) else " " for p in paths))
    trees = list(OrderedDict.fromkeys([n for n in names] + [r.tree for r in rows]))
    for t in trees:
        cells = []
        for p in paths:
            sub = [r for r in rows if r.tree == t and r.path == p]
            if not sub:
                cells.append(" ")
            elif any(r.status in ("mismatch", "error") for r in sub):
                cells.append("X")
            elif any(r.status == "divergence" for r in sub):
                cells.append("d")
            elif all(r.status == "skip" for r in sub):
                cells.append("s")
            else:
                cells.append(".")
        print("%-28s %s" % (t[:28], " ".join(cells)))

    div = defaultdict(list)
    fixed_tags = (B.FIX_MC, B.FIX_OR, B.FIX_FMT)
    plain_tags = ("LIBM", "TIME", "FRONTEND BUG", "OR-LOG", "D8", "D14", "D15", "D16", "D17")
    for r in rows:
        if r.status != "divergence":
            continue
        tags = [t for t in fixed_tags if t in r.note][:1]
        if not tags:  # a row can carry several (desktop: D14 and OR-LOG)
            tags = [t for t in plain_tags if t in r.note]
        for tag in tags or [r.note.split(":")[0] if r.note else r.metric]:
            div[tag].append(r)
    if div:
        print()
        print("DOCUMENTED DIVERGENCES (a row can count under several)")
        for key, items in sorted(div.items()):
            worst = max(items, key=lambda r: r.max_rel)
            print("  %-21s %4d row(s) on %2d tree(s), max rel %-9.3g paths %s" % (
                key, len(items), len({r.tree for r in items}), worst.max_rel,
                ",".join(sorted({r.path for r in items}))))
    bad = [r for r in rows if r.status in ("mismatch", "error")]
    print()
    if not bad:
        print("NO MISMATCHES.")
    else:
        print("MISMATCHES (%d, first %d):" % (len(bad), details))
        for r in bad[:details]:
            print("  %s | %s | %s | n=%d abs=%.3g rel=%.3g %s %s" % (
                r.tree, r.path, r.metric, r.n, r.max_abs, r.max_rel, r.note, r.diffs[:3]))


if __name__ == "__main__":
    raise SystemExit(main())
