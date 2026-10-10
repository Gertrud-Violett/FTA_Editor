"""The pip requirements files stay in step with pyproject.toml.

pyproject.toml is the source of truth; requirements.txt and
fta_web/requirements.txt are the hand-maintained pip fallback, and their
headers say "there is no tool wiring the two together". This test is that
wiring: every package of the `all` extra (plus pytest from `test`) is in one of
the two files with the same minimum version, and neither file lists anything
pyproject.toml does not declare.

Runs on Python 3.10 too, where tomllib does not exist, through a minimal
parser of the [project.optional-dependencies] table.
"""

import re
from pathlib import Path

import pytest

try:
    import tomllib
except ImportError:  # Python 3.10
    tomllib = None

REPO = Path(__file__).resolve().parents[2]
REQUIREMENT_FILES = (REPO / "requirements.txt", REPO / "fta_web" / "requirements.txt")
_REQUIREMENT = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*>=\s*([^\s;,#]+)$")


def _normalise(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def _parse_extras_minimal(text):
    """{extra: [requirement, ...]} from [project.optional-dependencies]."""
    match = re.search(r"(?ms)^\[project\.optional-dependencies\]\s*$(.*?)(?=^\[)", text)
    table = re.sub(r"(?m)#.*$", "", match.group(1))
    return {
        name: re.findall(r'"([^"]+)"', body)
        for name, body in re.findall(r"(?ms)^([A-Za-z0-9_-]+)\s*=\s*\[(.*?)\]", table)
    }


def _declared_extras():
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    if tomllib is not None:
        return tomllib.loads(text)["project"]["optional-dependencies"]
    return _parse_extras_minimal(text)


def _pins(requirements):
    pins = {}
    for requirement in requirements:
        match = _REQUIREMENT.match(requirement.strip())
        assert match, "not a plain `name>=version` requirement: %r" % requirement
        pins[_normalise(match.group(1))] = match.group(2)
    return pins


def _requirement_file_pins():
    pins = {}
    for path in REQUIREMENT_FILES:
        lines = path.read_text(encoding="utf-8").splitlines()
        for name, version in _pins(
            line.split("#", 1)[0] for line in lines if line.split("#", 1)[0].strip()
        ).items():
            assert name not in pins, "%s is listed in both requirements files" % name
            pins[name] = version
    return pins


def test_requirement_files_cover_every_declared_package():
    extras = _declared_extras()
    expected = _pins(extras["all"] + extras["test"])
    assert _requirement_file_pins() == expected


@pytest.mark.skipif(tomllib is None, reason="tomllib is Python 3.11+")
def test_minimal_parser_agrees_with_tomllib():
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert _parse_extras_minimal(text) == tomllib.loads(text)["project"]["optional-dependencies"]
