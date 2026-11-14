"""F0 BRIEF criterion 2: ``make_perf_fixtures.py`` is deterministic.

The generator is run as a script (``--out DIR`` into two fresh folders, and
once with no argument, which writes the files next to itself), and the six
files must be byte-identical between the runs and to the committed ones. The
module must be importable by path without side effects and expose the three
constants of BRIEF criterion 7.
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
FIXTURES = REPO_ROOT / "fta_web" / "tests" / "fixtures"
GENERATOR = FIXTURES / "make_perf_fixtures.py"
NAMES = [
    "perf_ccf_301.json",
    "perf_alpha_301.json",
    "perf_ccf_301_nogroups.json",
    "perf_alpha_301_nogroups.json",
    "perf_grid_500.json",
    "perf_grid_500_paste.tsv",
]


def run_generator(*args, cwd=REPO_ROOT):
    assert GENERATOR.is_file(), "the generator is missing: %s" % GENERATOR
    proc = subprocess.run([sys.executable, str(GENERATOR), *args], cwd=str(cwd),
                          capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0, proc.stderr[-3000:]
    return proc


def committed(name):
    path = FIXTURES / name
    assert path.is_file(), "missing committed fixture: %s" % path
    return path.read_bytes()


def listing(folder):
    return sorted(p.name for p in Path(folder).iterdir())


def test_the_generator_writes_exactly_the_six_files_into_out(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    run_generator("--out", str(out))
    assert listing(out) == sorted(NAMES)
    for name in NAMES:
        assert (out / name).stat().st_size > 0


def test_two_runs_give_byte_identical_files(tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    first.mkdir()
    second.mkdir()
    run_generator("--out", str(first))
    run_generator("--out", str(second))
    assert listing(first) == listing(second) == sorted(NAMES)
    for name in NAMES:
        assert (first / name).read_bytes() == (second / name).read_bytes(), name


def test_a_run_gives_the_bytes_of_the_committed_files(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    run_generator("--out", str(out))
    for name in NAMES:
        assert (out / name).read_bytes() == committed(name), name


def test_without_arguments_the_generator_rewrites_the_committed_files_unchanged():
    before = {name: committed(name) for name in NAMES}
    folder_before = listing(FIXTURES)
    try:
        run_generator()
        for name in NAMES:
            assert (FIXTURES / name).read_bytes() == before[name], name
        assert listing(FIXTURES) == folder_before
    finally:
        for name, data in before.items():  # never leave a changed fixture behind
            if (FIXTURES / name).read_bytes() != data:
                (FIXTURES / name).write_bytes(data)


def load_generator(tmp_path, monkeypatch):
    assert GENERATOR.is_file(), "the generator is missing: %s" % GENERATOR
    monkeypatch.chdir(tmp_path)
    spec = importlib.util.spec_from_file_location("make_perf_fixtures_import_check", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_importing_the_generator_has_no_side_effects(tmp_path, monkeypatch):
    before = {name: committed(name) for name in NAMES}
    folder_before = listing(FIXTURES)
    load_generator(tmp_path, monkeypatch)
    assert listing(tmp_path) == []
    assert listing(FIXTURES) == folder_before
    for name in NAMES:
        assert (FIXTURES / name).read_bytes() == before[name], name


def test_the_generator_exposes_the_expected_constants(tmp_path, monkeypatch):
    module = load_generator(tmp_path, monkeypatch)
    count = module.EXPECTED_CCF_CUTSET_COUNT
    alpha = module.EXPECTED_ALPHA_CUTSET_COUNT
    by = module.EXPECTED_CCF_TRUNCATED_BY
    assert type(count) is int and count > 0
    assert type(alpha) is int and alpha > 0
    assert isinstance(by, list) and all(isinstance(s, str) for s in by)
    assert by == sorted(by)
    assert set(by) <= {"order", "cutoff", "count"}  # 'time' is an error, never a cut
