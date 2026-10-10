"""Regression tests for the 2026-10 review of import/export, the CLI, the
DOCX report, the Excel export and the FMEA import (finding prefix IO-).

Each test failed before its fix.
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


def write_doc(path, tree=None, title="Doc", mode="FTA", **extra):
    doc = {"title": title, "date": "2026-01-01", "mode": mode, "tree": tree or {
        "id": "root", "name": "Top", "type": "Root", "logicGate": "OR", "children": [
            {"id": "a", "name": "Pump ü", "probability": 0.01, "children": []},
            {"id": "b", "name": "Valve", "probability": 0.02, "children": []},
        ]}}
    doc.update(extra)
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def run_cli(*args, encoding):
    """The real entry point with stdout in ``encoding`` (not UTF-8 mode)."""
    env = dict(os.environ, PYTHONIOENCODING=encoding)
    env.pop("PYTHONUTF8", None)
    proc = subprocess.run([sys.executable, str(RUN)] + [str(a) for a in args],
                          capture_output=True, cwd=str(REPO), env=env, timeout=120)
    return proc.returncode, proc.stdout, proc.stderr.decode("utf-8", "replace")


# ---- IO-1: a console that cannot encode a character ----------------------------------


@pytest.mark.parametrize("encoding", ["ascii", "cp932"])
def test_cli_survives_a_console_that_cannot_encode_the_output(tmp_path, encoding):
    """'ü' (not in cp932) or the '—' of an empty cell crashed the write with
    UnicodeEncodeError: a traceback and exit 1 for a run that succeeded."""
    doc = write_doc(tmp_path / "t.json")
    code, out, err = run_cli("quantify", doc, encoding=encoding)
    assert code == 0, err
    assert "Traceback" not in err and b"Pump" in out

    code, out, err = run_cli("quantify", doc, "--json", encoding=encoding)
    assert code == 0, err
    # Still valid JSON, and lossless: non-ASCII is escaped, not replaced.
    payload = json.loads(out.decode("ascii"))
    assert payload["results"]["events"][0]["name"] == "Pump ü"


def test_cli_exit_code_3_survives_a_non_ascii_file_name(tmp_path):
    """The documented 'unreadable file' code was lost to the crash (exit 1)."""
    code, _out, err = run_cli("validate", tmp_path / "nö.json", encoding="ascii")
    assert code == 3, err
    assert "Traceback" not in err


# ---- IO-2: --json is strict JSON ------------------------------------------------------


def _strict_json(text):
    def refuse(token):
        raise ValueError("non-standard JSON token %s" % token)

    return json.loads(text, parse_constant=refuse)


def test_cli_json_has_no_nan_tokens(tmp_path, capsys):
    """A probability of NaN (Python's json reads the bare literal) reached the
    summary and was printed as ``NaN``, which JSON.parse, jq and every strict
    parser reject. It is null now, as in the API's responses."""
    tree = {"id": "root", "name": "Top", "type": "Root", "logicGate": "OR", "children": [
        {"id": "a", "name": "A", "probability": float("nan"), "children": []},
        {"id": "b", "name": "B", "probability": 0.1, "children": []}]}
    doc = write_doc(tmp_path / "nan.json", tree)
    assert cli.main(["quantify", str(doc), "--json"]) == 0
    payload = _strict_json(capsys.readouterr().out)
    assert payload["results"]["summary"]["treeWalk"] is None

    out = tmp_path / "res.json"
    assert cli.main(["quantify", str(doc), "--json", "--out", str(out)]) == 0
    _strict_json(out.read_text(encoding="utf-8"))


# ---- IO-3: --top applies to --json --------------------------------------------------------


def test_cutsets_top_applies_to_json(tmp_path, capsys):
    """``--top N`` cut the text and CSV tables (and importance's JSON) but
    ``cutsets --json`` still listed every cut set."""
    tree = {"id": "root", "name": "Top", "type": "Root", "logicGate": "OR", "children": [
        {"id": "e%d" % i, "name": "E%d" % i, "probability": 0.001 * (i + 1), "children": []}
        for i in range(5)]}
    doc = write_doc(tmp_path / "five.json", tree)
    assert cli.main(["cutsets", str(doc), "--top", "2", "--json"]) == 0
    results = json.loads(capsys.readouterr().out)["results"]
    assert [c["rank"] for c in results["cutSets"]] == [1, 2]
    assert results["cutSets"][0]["events"][0]["id"] == "e4"  # the most probable
    assert results["total"] == 5  # the totals still describe the whole list
    assert cli.main(["cutsets", str(doc), "--top", "2", "--csv"]) == 0
    assert len(list(csv.DictReader(io.StringIO(capsys.readouterr().out)))) == 2


# ---- IO-4: an output that cannot be written -------------------------------------------


def test_unwritable_out_is_an_error_message_not_a_traceback(tmp_path, capsys):
    """``--out`` under a regular file (or any OSError while writing) escaped
    main() as FileExistsError / NotADirectoryError with a traceback."""
    doc = write_doc(tmp_path / "t.json")
    blocker = tmp_path / "taken.txt"
    blocker.write_text("not a folder", encoding="utf-8")
    assert cli.main(["quantify", str(doc), "--json", "--out", str(blocker / "r.json")]) == 1
    err = capsys.readouterr().err
    assert "cannot write" in err and "r.json" in err


def test_report_that_cannot_be_written_fails_that_file_only(tmp_path, capsys):
    pytest.importorskip("docx")
    good = write_doc(tmp_path / "good.json")
    blocker = tmp_path / "taken.txt"
    blocker.write_text("not a folder", encoding="utf-8")
    # A non-.docx --out is a folder; here it names an existing file.
    code = cli.main(["report", str(good), "--out", str(blocker), "--sections", "metadata",
                     "--json"])
    assert code == 1
    captured = capsys.readouterr()
    assert "cannot write" in captured.err
    assert "cannot write" in json.loads(captured.out)["error"]
