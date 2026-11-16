"""F2 BRIEF criterion 16 (FN-28): files without CCF groups give the 1.8.1 results.

For every file of ``fta_web/examples/*.json`` and ``fta_web/tests/b2b/*.json``
(except ``expected.json``) the five CLI commands of the manifest in
``fta_web/tests/golden_1_8_1/`` are run -- ``quantify``, ``cutsets``,
``importance``, ``validate`` with ``--json`` and ``mc --json --n 2000 --seed 1
--time-limit 3600``; the two large b2b files run ``quantify`` and ``validate``
through the manifest's budget driver ``cli_with_budgets.py`` -- and compared with
the goldens made on the 1.8.1 release commit:

1. the exit code equals the stored one;
2. the parsed JSON equals the stored one after removing ``elapsedMs`` at any
   depth from the fresh output (the stored goldens have it removed already);
   floats within relative 1e-13, everything else exact (CR-20261102-fn28-tolerance:
   ``math.expm1`` differs in the last bits between interpreters and platforms);
3. neither side is cut short by time (no ``truncatedByTime`` true, no ``"time"``
   in a ``truncatedBy``).

Also: ``git diff <release commit> -- fta_web/core desktop`` is empty. The b2b
suite (``test_b2b.py``) and ``test_vendor_integrity.py`` are existing tests that
the verify step runs.
"""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
GOLDEN_DIR = REPO_ROOT / "fta_web" / "tests" / "golden_1_8_1"
MANIFEST_PATH = GOLDEN_DIR / "manifest.json"
RELEASE_COMMIT = "c6d09f5b0d5363fc037f63d3ec7cf1c91186a798"
VOLATILE = ("elapsedMs",)
FLOAT_REL = 1e-13
MISSING = "__manifest_missing__"


def read_manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


try:
    FILES = sorted(read_manifest()["files"])
except (OSError, ValueError, KeyError):
    FILES = [MISSING]


def short_id(rel):
    return rel.replace("fta_web/tests/", "").replace("fta_web/", "")


def strip_volatile(value):
    if isinstance(value, dict):
        return {k: strip_volatile(v) for k, v in value.items() if k not in VOLATILE}
    if isinstance(value, list):
        return [strip_volatile(v) for v in value]
    return value


def time_truncated(value, trail="$"):
    """Paths in ``value`` that show a time cut-off."""
    found = []
    if isinstance(value, dict):
        for key, item in value.items():
            here = "%s.%s" % (trail, key)
            if key == "truncatedByTime" and item:
                found.append(here)
            if key == "truncatedBy" and isinstance(item, list) and any(
                    "time" in str(x).lower() for x in item):
                found.append(here)
            found.extend(time_truncated(item, here))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(time_truncated(item, "%s[%d]" % (trail, index)))
    return found


def first_difference(fresh, stored, trail="$"):
    """A short description of where two parsed values first differ."""
    if type(fresh) is not type(stored):
        return "%s: %r != %r" % (trail, fresh, stored)
    if isinstance(fresh, dict):
        for key in sorted(set(fresh) | set(stored)):
            if key not in fresh:
                return "%s.%s: missing in the fresh output" % (trail, key)
            if key not in stored:
                return "%s.%s: new in the fresh output (%r)" % (trail, key, fresh[key])
            found = first_difference(fresh[key], stored[key], "%s.%s" % (trail, key))
            if found:
                return found
        return None
    if isinstance(fresh, list):
        if len(fresh) != len(stored):
            return "%s: %d items != %d stored" % (trail, len(fresh), len(stored))
        for index, (a, b) in enumerate(zip(fresh, stored)):
            found = first_difference(a, b, "%s[%d]" % (trail, index))
            if found:
                return found
        return None
    if isinstance(fresh, float):
        same = abs(fresh - stored) <= FLOAT_REL * max(abs(fresh), abs(stored))
    else:
        same = fresh == stored
    return None if same else "%s: %r != %r" % (trail, fresh, stored)


@pytest.mark.parametrize("fresh, stored, same", [
    (0.908655027573792, 0.9086550275737919, True),
    (1.0, 1.0 + 0.9e-13, True),
    (1.0, 1.0 + 1.1e-13, False),
    (1e-20, 1.0000000000002e-20, False),
    (0.0, 0.0, True),
    (0.0, 1e-300, False),
    (1, 1.0, False),
    ("0.5", "0.50", False),
    (True, False, False),
    (2000, 2001, False),
    (10 ** 14, 10 ** 14 + 1, False),
])
def test_floats_compare_within_the_stated_tolerance_and_the_rest_exactly(fresh, stored, same):
    assert (first_difference([{"x": fresh}], [{"x": stored}]) is None) is same


def run_cli(argv):
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    proc = subprocess.run([sys.executable] + list(argv), cwd=str(REPO_ROOT), env=env,
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=1800)
    return proc


def parse_output(text):
    try:
        return json.loads(text)
    except ValueError:
        return text


@pytest.mark.parametrize("rel", FILES, ids=[short_id(f) for f in FILES])
def test_the_five_commands_equal_the_1_8_1_goldens(rel):
    assert rel != MISSING, "fta_web/tests/golden_1_8_1/manifest.json is missing or unreadable"
    manifest = read_manifest()
    entry = manifest["files"][rel]
    golden = json.loads((GOLDEN_DIR / entry["golden"]).read_text(encoding="utf-8"))
    assert golden["file"] == rel
    source = REPO_ROOT / rel
    assert hashlib.sha256(source.read_bytes()).hexdigest() == entry["inputSha256"], (
        "the corpus file changed since the goldens were made")
    assert set(entry["commands"]) == set(golden["commands"]) == {
        "quantify", "cutsets", "importance", "validate", "mc"}

    problems = []
    for name in sorted(entry["commands"]):
        stored = golden["commands"][name]
        proc = run_cli(entry["commands"][name])  # the manifest's command line, driver included
        if proc.returncode != stored["exitCode"]:
            problems.append("%s: exit code %s, stored %s (%s)" % (
                name, proc.returncode, stored["exitCode"], proc.stderr.strip()[:200]))
            continue
        fresh = strip_volatile(parse_output(proc.stdout))
        for label, value in (("fresh", fresh), ("stored", stored["stdout"])):
            cut = time_truncated(value)
            if cut:
                problems.append("%s: the %s result is cut short by time at %s" % (name, label, cut))
        difference = first_difference(fresh, stored["stdout"])
        if difference:
            problems.append("%s: %s" % (name, difference))
    assert not problems, "\n".join(problems)


def test_the_goldens_cover_the_whole_corpus():
    manifest = read_manifest()
    corpus = set()
    for folder in ("fta_web/examples", "fta_web/tests/b2b"):
        for path in (REPO_ROOT / folder).glob("*.json"):
            if path.name != "expected.json":
                corpus.add("%s/%s" % (folder, path.name))
    assert corpus == set(manifest["files"])
    assert manifest["releaseCommit"] == RELEASE_COMMIT
    for rel, entry in manifest["files"].items():
        assert (GOLDEN_DIR / entry["golden"]).is_file(), rel
    # the two large files use the budget driver for the two internal budgets
    for rel in manifest["largerLimits"]:
        commands = manifest["files"][rel]["commands"]
        assert commands["quantify"][0].endswith("cli_with_budgets.py")
        assert commands["validate"][0].endswith("cli_with_budgets.py")


def test_core_and_desktop_are_unchanged_since_the_1_8_1_release():
    probe = subprocess.run(["git", "cat-file", "-e", RELEASE_COMMIT + "^{commit}"],
                           cwd=str(REPO_ROOT), capture_output=True, text=True)
    if probe.returncode != 0:
        pytest.skip("the 1.8.1 release commit %s is not in this checkout" % RELEASE_COMMIT)
    diff = subprocess.run(["git", "diff", "--quiet", RELEASE_COMMIT, "--", "fta_web/core",
                           "desktop"], cwd=str(REPO_ROOT), capture_output=True, text=True)
    assert diff.returncode == 0, "fta_web/core or desktop differs from the 1.8.1 release commit"
