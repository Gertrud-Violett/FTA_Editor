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
