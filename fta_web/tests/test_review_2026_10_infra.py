"""install.py: the uv path must install what the documented commands install.

The installer offers uv first and pip as the fallback. Both paths are meant to
leave the same working app (README.md → Quick Start), and its "Run the test
suite now?" step must run the suite in the environment it just built.
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _load_installer():
    spec = importlib.util.spec_from_file_location("fta_install", REPO / "install.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_installer(monkeypatch, answers):
    """Run install.main() with uv on PATH; return every command it ran."""
    installer = _load_installer()
    commands = []

    def fake_run(cmd, *args, **kwargs):
        commands.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0)

    replies = iter(answers)
    monkeypatch.setattr(installer.subprocess, "run", fake_run)
    monkeypatch.setattr(installer.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(replies))
    installer.main()
    return commands


def _extras(cmd):
    return {cmd[i + 1] for i, arg in enumerate(cmd[:-1]) if arg == "--extra"}


def test_uv_web_install_includes_the_report_extra(monkeypatch):
    # README's uv command for the web app is
    # `uv sync --extra web --extra excel --extra ai --extra report`, and the pip
    # fallback installs python-docx from fta_web/requirements.txt. The uv path
    # used to leave the DOCX report disabled.
    sync = _run_installer(monkeypatch, ["1", "n"])[0]
    assert sync[:2] == ["uv", "sync"]
    assert _extras(sync) >= {"web", "excel", "ai", "report"}


def test_uv_both_install_includes_the_report_extra(monkeypatch):
    sync = _run_installer(monkeypatch, ["3", "n"])[0]
    assert _extras(sync) >= {"web", "desktop", "excel", "ai", "report"}


def test_uv_test_run_asks_uv_for_pytest(monkeypatch):
    # `uv sync` is exact, so the extras above leave no pytest in the venv, and
    # a bare `uv run pytest` fell through to whatever pytest was on PATH (a
    # different interpreter without Flask) or failed to spawn.
    commands = _run_installer(monkeypatch, ["1", "y"])
    test_cmd = commands[-1]
    assert test_cmd[:2] == ["uv", "run"]
    assert "test" in _extras(test_cmd)
    assert "pytest" in test_cmd


def test_pip_test_run_uses_this_interpreter(monkeypatch):
    installer = _load_installer()
    commands = []

    def fake_run(cmd, *args, **kwargs):
        commands.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0)

    replies = iter(["1", "y"])
    monkeypatch.setattr(installer.subprocess, "run", fake_run)
    monkeypatch.setattr(installer.shutil, "which", lambda name: None)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(replies))
    installer.main()
    assert commands[-1][:3] == [sys.executable, "-m", "pytest"]


# ---- fta_web/tests/b2b/run_b2b.py: the printed divergence summary ----------------------

def _runner():
    from fta_web.tests.b2b import run_b2b

    return run_b2b


def test_b2b_summary_counts_mcub_rows_under_their_own_tag():
    # "FIXED:MC" is a substring of "FIXED:MCUB", and the first matching tag
    # won, so the summary printed "FIXED:MC 42 rows" for 10 MC + 32 MCUB rows.
    runner = _runner()
    B = runner.B
    assert runner.divergence_tags(B.Row("t", "release->branch", "mcub", "divergence", 1,
                                        note=B.FIX_MCUB)) == [B.FIX_MCUB]
    assert runner.divergence_tags(B.Row("t", "release->branch", "mc", "divergence", 1,
                                        note=B.FIX_MC)) == [B.FIX_MC]
    # "FIXED:MC" is a substring of "FIXED:MC-EVENT-NOT-SAMPLED" too.
    assert runner.divergence_tags(B.Row("t", "release->branch", "mc", "divergence", 1,
                                        note="%s %s" % (B.FIX_MC_EVENT, B.FIX_MC))) == [
        B.FIX_MC_EVENT]


def test_b2b_summary_keeps_every_plain_tag_of_a_desktop_row():
    runner = _runner()
    B = runner.B
    row = B.Row("t", "desktop", "calculatedProbability", "divergence", 1,
                note="D14 / %s: ..." % B.OR_LOG)
    assert runner.divergence_tags(row) == [B.OR_LOG, "D14"]
