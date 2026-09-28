"""The batch CLI: ``python fta_web/run.py <command> ...`` (workstream D).

Subprocess tests cover the real entry point (dispatch before Flask, exit
codes, output formats). In-process tests call ``cli.main`` with fake
cut-set / importance / Monte Carlo / lint functions for determinism.
"""
import csv
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from fta_web import cli

REPO = Path(__file__).resolve().parents[2]
RUN = REPO / "fta_web" / "run.py"
SAMPLE = REPO / "fta_web" / "examples" / "sampleFTA.json"


def run_cli(*args, cwd=None):
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    proc = subprocess.run(
        [sys.executable, str(RUN)] + [str(a) for a in args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(cwd or REPO), env=env, timeout=120,
    )
    return proc.returncode, proc.stdout, proc.stderr


def small_tree(**extra):
    tree = {
        "id": "root", "name": "Top", "type": "Root", "logicGate": "OR",
        "children": [
            {"id": "a", "name": "Pump", "probability": 0.01, "children": [],
             "quant": {"model": "rate", "lambda": 1e-5}},
            {"id": "b", "name": "Valve ü", "probability": 0.02, "children": []},
        ],
    }
    tree.update(extra)
    return tree


def write_doc(path, tree=None, mode="FTA", title="Small"):
    path.write_text(json.dumps({"title": title, "date": "2026-01-01", "mode": mode,
                                "tree": tree or small_tree()}, indent=2), encoding="utf-8")
    return path


# ---- subprocess: the real entry point --------------------------------------------------------


def test_help_lists_the_commands():
    code, out, _err = run_cli("help")
    assert code == 0
    for command in cli.COMMANDS:
        assert command in out


def test_version():
    code, out, _err = run_cli("--version")
    assert code == 0 and cli.VERSION in out


def test_validate_the_sample_exits_0():
    code, out, err = run_cli("validate", SAMPLE)
    assert code == 0, err
    assert "sampleFTA" in out
    assert "FTA Editor" not in out and "URL" not in out  # no server banner


def test_quantify_json_schema(tmp_path):
    doc = write_doc(tmp_path / "t.json")
    code, out, err = run_cli("quantify", doc, "--json")
    assert code == 0, err
    payload = json.loads(out)
    assert set(payload) >= {"file", "title", "mode", "results"}
    assert payload["title"] == "Small" and payload["mode"] == "FTA"
    results = payload["results"]
    assert results["summary"]["headline"] == pytest.approx(1 - (1 - 0.0839) * 0.98, rel=1e-2)
    ids = [e["id"] for e in results["events"]]
    assert ids == ["a", "b"]
    assert results["events"][0]["model"] == "rate"


def test_mission_time_override(tmp_path):
    doc = write_doc(tmp_path / "t.json")
    code, out, _ = run_cli("quantify", doc, "--json", "--mission-time", "100")
    assert code == 0
    event = json.loads(out)["results"]["events"][0]
    assert event["calculated"] == pytest.approx(1 - 2.718281828459045 ** -1e-3, rel=1e-6)


def test_quantify_csv_and_human(tmp_path):
    doc = write_doc(tmp_path / "t.json")
    code, out, _ = run_cli("quantify", doc, "--csv")
    assert code == 0
    rows = list(csv.DictReader(io.StringIO(out)))
    assert [r["id"] for r in rows] == ["a", "b"]
    assert rows[0]["file"].endswith("t.json")
    code, out, _ = run_cli("quantify", doc, "--sig-figs", "2")
    assert code == 0
    assert "Top event:" in out and "Valve ü" in out and "0.020" in out


def test_multiple_files_give_a_json_list(tmp_path):
    a = write_doc(tmp_path / "a.json", title="A")
    b = write_doc(tmp_path / "b.json", title="B")
    code, out, _ = run_cli("quantify", a, b, "--json")
    assert code == 0
    payload = json.loads(out)
    assert isinstance(payload, list) and [p["title"] for p in payload] == ["A", "B"]


def test_glob_expansion_and_output_dir(tmp_path):
    write_doc(tmp_path / "a.json")
    write_doc(tmp_path / "b.json")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    code, out, _ = run_cli("quantify", str(tmp_path / "*.json"), "--json", "--out", out_dir)
    assert code == 0 and out == ""
    names = sorted(p.name for p in out_dir.iterdir())
    assert names == ["a.quantify.json", "b.quantify.json"]
    assert json.loads((out_dir / "a.quantify.json").read_text(encoding="utf-8"))["file"].endswith("a.json")


def test_out_file(tmp_path):
    doc = write_doc(tmp_path / "t.json")
    target = tmp_path / "res.csv"
    code, _out, _ = run_cli("quantify", doc, "--csv", "--out", target)
    assert code == 0 and target.read_text(encoding="utf-8").startswith("file,")


def test_unreadable_file_exits_3(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("this is not json", encoding="utf-8")
    code, _out, err = run_cli("validate", bad)
    assert code == 3 and "bad.json" in err
    code, _out, _ = run_cli("validate", tmp_path / "missing.json")
    assert code == 3
    good = write_doc(tmp_path / "good.json")
    code, out, _ = run_cli("quantify", good, bad, "--json")
    assert code == 3
    payload = json.loads(out)
    assert "results" in payload[0] and "error" in payload[1]


@pytest.mark.parametrize("args", [
    ("validate",),                                  # no files
    ("validate", "x.json", "--json", "--csv"),      # exclusive formats
    ("quantify", "x.json", "--sig-figs", "many"),   # bad number
    ("cutsets", "x.json", "--bogus"),
])
def test_usage_errors_exit_2(args):
    code, _out, _err = run_cli(*args)
    assert code == 2


def test_bad_override_value_exits_2(tmp_path):
    doc = write_doc(tmp_path / "t.json")
    code, _out, err = run_cli("quantify", doc, "--mission-time", "-5")
    assert code == 2 and "missionTime" in err


def test_report_writes_a_docx(tmp_path):
    docx = pytest.importorskip("docx")
    doc = write_doc(tmp_path / "t.json")
    code, out, err = run_cli("report", doc, "--sections", "metadata,headline,events", "--lang", "ja")
    assert code == 0, err
    target = tmp_path / "t_report.docx"
    assert target.is_file() and "t_report.docx" in out
    text = "\n".join(p.text for p in docx.Document(str(target)).paragraphs)
    assert "故障の木解析レポート" in text


def test_report_with_multiple_files_needs_a_directory(tmp_path):
    a = write_doc(tmp_path / "a.json")
    b = write_doc(tmp_path / "b.json")
    code, _out, _err = run_cli("report", a, b, "--out", tmp_path / "one.docx")
    assert code == 2


def test_report_unknown_section_exits_2(tmp_path):
    pytest.importorskip("docx")
    code, _out, _err = run_cli("report", write_doc(tmp_path / "t.json"), "--sections", "nope")
    assert code == 2


def test_run_main_dispatches_before_flask(tmp_path, monkeypatch, capsys):
    """run.main must hand a command to the CLI without building the app."""
    fta_web_dir = str(REPO / "fta_web")
    if fta_web_dir not in sys.path:
        monkeypatch.syspath_prepend(fta_web_dir)
    import run

    def no_app(**_kw):
        raise AssertionError("create_app must not be called for a CLI command")

    monkeypatch.setattr(run, "create_app", no_app)
    monkeypatch.setattr(run.webbrowser, "open", no_app)
    assert run.main(["validate", str(write_doc(tmp_path / "t.json"))]) == 0
    assert "Small" in capsys.readouterr().out


# ---- in process, with fakes -------------------------------------------------------------------


def fake_cutsets(tree, analysis, limits=None):
    fake_cutsets.limits = limits
    return {"cutSets": [
        {"rank": 1, "events": [{"id": "b", "name": "Valve ü", "q": 0.02}], "order": 1,
         "probability": 0.02, "share": 0.7},
        {"rank": 2, "events": [{"id": "a", "name": "Pump", "q": 0.01}], "order": 1,
         "probability": 0.01, "share": 0.3},
    ], "total": 2, "truncated": False, "truncatedBy": None, "mcub": 0.0298,
        "rareEvent": 0.03, "treeWalk": 0.0298, "repeatedEvents": [], "nonCoherent": False,
        "approximations": [], "warnings": [], "elapsedMs": 0}


def fake_importance(result):
    return [{"id": "a", "name": "Pump", "q": 0.01, "fv": 0.3, "birnbaum": 0.98, "raw": 30,
             "rrw": 1.4, "cutSetCount": 1},
            {"id": "b", "name": "Valve ü", "q": 0.02, "fv": 0.7, "birnbaum": 0.99, "raw": 34,
             "rrw": 3.3, "cutSetCount": 1}]


def fake_mc(tree, analysis, n=None, seed=None, time_limit=30, bins=40):
    return {"mean": 0.03, "median": 0.029, "p05": 0.02, "p95": 0.04, "std": 0.005,
            "pointEstimate": 0.0298, "histogram": {"edges": [0, 1], "counts": [n or 0]},
            "completed": True, "seed": seed, "method": "engine", "n": n}


LINT_RESULT = []


def fake_lint(tree, analysis, session_warnings=(), mode="FTA", extra=None):
    fake_lint.calls.append({"mode": mode, "extra": extra})
    return list(LINT_RESULT) + list(session_warnings)


fake_lint.calls = []


@pytest.fixture
def fakes(monkeypatch):
    import fta_web.cutsets
    import fta_web.importance
    import fta_web.lint
    import fta_web.uncertainty

    monkeypatch.setattr(fta_web.cutsets, "compute", fake_cutsets, raising=False)
    monkeypatch.setattr(fta_web.importance, "compute", fake_importance, raising=False)
    monkeypatch.setattr(fta_web.uncertainty, "run", fake_mc, raising=False)
    monkeypatch.setattr(fta_web.lint, "run", fake_lint, raising=False)
    LINT_RESULT[:] = []


def main_json(capsys, *args):
    code = cli.main([str(a) for a in args] + ["--json"])
    return code, json.loads(capsys.readouterr().out)


def test_cutsets_json(fakes, tmp_path, capsys):
    doc = write_doc(tmp_path / "t.json")
    code, payload = main_json(capsys, "cutsets", doc, "--max-order", "3", "--cutoff", "1e-9")
    assert code == 0
    assert payload["results"]["cutSets"][0]["rank"] == 1
    assert payload["results"]["mcub"] == 0.0298
    assert fake_cutsets.limits["maxOrder"] == 3 and fake_cutsets.limits["cutoff"] == 1e-9


def test_cutsets_csv_rows(fakes, tmp_path, capsys):
    doc = write_doc(tmp_path / "t.json")
    assert cli.main(["cutsets", str(doc), "--csv", "--top", "1"]) == 0
    rows = list(csv.DictReader(io.StringIO(capsys.readouterr().out)))
    assert len(rows) == 1 and rows[0]["events"] == "b" and rows[0]["names"] == "Valve ü"


def test_importance_sorted_by_fv(fakes, tmp_path, capsys):
    code, payload = main_json(capsys, "importance", write_doc(tmp_path / "t.json"))
    assert code == 0
    assert [m["id"] for m in payload["results"]["measures"]] == ["b", "a"]


def test_importance_human(fakes, tmp_path, capsys):
    assert cli.main(["importance", str(write_doc(tmp_path / "t.json"))]) == 0
    out = capsys.readouterr().out
    assert "fv" in out and "0.700" in out


def test_mc_uses_n_and_seed(fakes, tmp_path, capsys):
    code, payload = main_json(capsys, "mc", write_doc(tmp_path / "t.json"), "--n", "123",
                              "--seed", "7")
    assert code == 0
    assert payload["results"]["n"] == 123 and payload["results"]["seed"] == 7


def test_validate_exit_codes(fakes, tmp_path, capsys):
    doc = write_doc(tmp_path / "t.json")
    assert cli.main(["validate", str(doc)]) == 0
    LINT_RESULT[:] = [{"severity": "warning", "code": "DEFAULT_PROBABILITY", "nodeId": "a",
                       "message": "m", "params": {}}]
    assert cli.main(["validate", str(doc)]) == 0
    assert cli.main(["validate", str(doc), "--strict"]) == 1
    LINT_RESULT[:] = [{"severity": "error", "code": "CYCLIC_LINK", "nodeId": "a",
                       "message": "cycle", "params": {}}]
    capsys.readouterr()
    code, payload = main_json(capsys, "validate", doc)
    assert code == 1
    assert payload["results"]["counts"]["error"] == 1
    assert payload["results"]["issues"][0]["code"] == "CYCLIC_LINK"
    assert fake_lint.calls[-1]["mode"] == "FTA"


def test_validate_passes_the_eta_mode(fakes, tmp_path, capsys):
    fake_lint.calls.clear()
    assert cli.main(["validate", str(write_doc(tmp_path / "e.json", mode="ETA"))]) == 0
    assert fake_lint.calls[-1]["mode"] == "ETA"


def test_analysis_commands_refuse_eta(fakes, tmp_path, capsys):
    doc = write_doc(tmp_path / "e.json", mode="ETA")
    code, payload = main_json(capsys, "cutsets", doc)
    assert code == 1 and "ETA" in payload["error"]


def test_unavailable_analysis_exits_1(tmp_path, capsys, monkeypatch):
    import fta_web.cutsets

    monkeypatch.delattr(fta_web.cutsets, "compute", raising=False)
    code, payload = main_json(capsys, "cutsets", write_doc(tmp_path / "t.json"))
    assert code == 1 and "not available" in payload["error"]


def test_report_in_process_with_fakes(fakes, tmp_path, capsys):
    docx = pytest.importorskip("docx")
    doc = write_doc(tmp_path / "t.json")
    out_dir = tmp_path / "reports"
    out_dir.mkdir()
    code, payload = main_json(capsys, "report", doc, "--out", out_dir, "--uncertainty")
    assert code == 0
    target = out_dir / "t_report.docx"
    assert payload["results"]["out"] == str(target)
    text = "\n".join(p.text for p in docx.Document(str(target)).paragraphs)
    assert "Minimal cut sets" in text and "Uncertainty (Monte Carlo)" in text
