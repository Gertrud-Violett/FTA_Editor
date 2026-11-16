"""The version a user sees (CLI --version, the DOCX report) is the version
the project declares. They are two constants; this keeps them in step so a
release bump cannot update one and forget the other."""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


def test_tool_version_matches_pyproject():
    from fta_web import report_docx

    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    declared = re.search(r'(?m)^version = "([^"]+)"$', text).group(1)
    assert report_docx.TOOL_VERSION == declared


def test_changelog_has_an_entry_for_the_version():
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    declared = re.search(r'(?m)^version = "([^"]+)"$', text).group(1)
    changelog = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## [%s] - " % declared in changelog
