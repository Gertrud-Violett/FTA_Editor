"""F3 acceptance tests (T0): what the grid's source must and must not contain.

FN-46: "the grid module imports these functions and defines no number parser of its
own". The reviewer confirms it by reading; these checks catch the usual ways of getting
it wrong (a second reader of cell text, a copy of the parsers) and fail until
``tabs/grid.js`` exists. The last test keeps personal names out of the public repository.
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
TABS = REPO / "fta_web" / "static" / "js" / "tabs"
GRID = TABS / "grid.js"
GRID_PASTE = TABS / "grid_paste.js"


def strip_comments(source):
    """The source without ``//`` and ``/* */`` comments (string-aware enough for these checks)."""
    out, i, n = [], 0, len(source)
    quote = None
    while i < n:
        c = source[i]
        if quote:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(source[i + 1])
                i += 1
            elif c == quote:
                quote = None
        elif c in "'\"`":
            quote = c
            out.append(c)
        elif source.startswith("//", i):
            while i < n and source[i] != "\n":
                i += 1
            continue
        elif source.startswith("/*", i):
            end = source.find("*/", i + 2)
            i = n if end < 0 else end + 1
        else:
            out.append(c)
        i += 1
    return "".join(out)


def grid_source():
    assert GRID.is_file(), "missing %s (F3 T2)" % GRID
    return strip_comments(GRID.read_text(encoding="utf-8"))


def imported_names(source):
    """``{name: module path}`` for every named import of a JS module."""
    found = {}
    for names, path in re.findall(r"import\s*\{([^}]*)\}\s*from\s*['\"]([^'\"]+)['\"]", source):
        for part in names.split(","):
            part = part.strip()
            if part:
                found[part.split(" as ")[-1].strip()] = path
    return found


def test_grid_js_exists_and_is_a_tab_module():
    source = grid_source()
    assert re.search(r"export\s+const\s+id\s*=\s*'grid'", source)
    assert re.search(r"export\s+const\s+advanced\s*=\s*true", source)
    assert re.search(r"export\s+(async\s+)?function\s+mount\b", source)


def test_grid_js_imports_the_existing_parsers():
    names = imported_names(grid_source())
    assert names.get("parseProbability", "").endswith("dialogs.js"), names
    assert names.get("numberParser", "").endswith("analysis_common.js"), names


def test_grid_js_calls_the_parser_of_each_numeric_column():
    source = grid_source()
    assert len(re.findall(r"\bparseProbability\s*\(", source)) >= 1
    # lambda and mu: numberParser(0); T and tau: numberParser(0, { exclusive: true })
    assert len(re.findall(r"\bnumberParser\s*\(\s*0\s*\)", source)) >= 1
    assert len(re.findall(r"\bnumberParser\s*\(\s*0\s*,\s*\{\s*exclusive\s*:\s*true", source)) >= 1


def test_number_parser_is_exported_by_analysis_common_and_still_used_by_quant():
    common = (TABS / "analysis_common.js").read_text(encoding="utf-8")
    assert re.search(r"export\s+function\s+numberParser\s*\(", common), "numberParser must move to analysis_common.js"
    quant = strip_comments((TABS / "quant.js").read_text(encoding="utf-8"))
    assert re.search(r"\bnumberParser\s*\(\s*0\s*,\s*\{\s*exclusive\s*:\s*true", quant)
    assert "parseNumber" in common


@pytest.mark.parametrize("path", [GRID, GRID_PASTE], ids=["grid.js", "grid_paste.js"])
def test_the_grid_modules_define_no_number_parser(path):
    assert path.is_file(), "missing %s (F3)" % path
    source = strip_comments(path.read_text(encoding="utf-8"))
    # no direct reading of text as a number
    assert not re.search(r"\bparseFloat\b|\bparseInt\b|Number\.parse(Float|Int)", source)
    # no pattern that recognises a number: \d, [0-9], a decimal-comma or exponent shape
    assert not re.search(r"\\d|\[0-9\]|\[\+-\]|\[-\+\]|e\[\+-\]", source), "a number pattern in " + path.name
    # no Number(...) / unary plus of something that is cell text
    for call in re.finditer(r"\bNumber\(", source):
        depth, j = 1, call.end()
        while j < len(source) and depth:
            depth += source[j] == "("
            depth -= source[j] == ")"
            j += 1
        argument = source[call.end():j - 1]
        assert not re.fullmatch(r"\s*(?:\w*(?:text|raw|typed|cell|clip)\w*|[\w.]*\.value|str)\s*", argument, re.I), \
            "Number(%s) reads cell text" % argument
    # no function named like a number reader
    names = re.findall(r"function\s+([A-Za-z_$][\w$]*)", source)
    assert not [n for n in names if re.match(r"(parse|read|to)(Number|Num|Float|Prob|Probability|Decimal|Value|Rate)", n, re.I)
                and n != "parseProbability"], names
    assert "function parseProbability" not in source and "function parseNumber" not in source
    assert "function numberParser" not in source


def test_grid_paste_is_pure():
    assert GRID_PASTE.is_file(), "missing %s (F3)" % GRID_PASTE
    source = strip_comments(GRID_PASTE.read_text(encoding="utf-8"))
    assert not re.search(r"\bdocument\b|\bwindow\b|\blocalStorage\b|\bfetch\s*\(", source), "grid_paste.js must have no DOM"
    assert not re.search(r"import[^;]*dialogs\.js|import[^;]*numfmt\.js|import[^;]*analysis_common\.js", source)
    assert re.search(r"export\s+function\s+parseClipboard\b", source)
    assert re.search(r"export\s+function\s+planPaste\b", source)


def test_every_keydown_handler_of_grid_js_starts_with_the_ime_guard():
    source = grid_source()
    handlers = [m.start() for m in re.finditer(r"addEventListener\(\s*'keydown'", source)]
    assert handlers, "the grid has keyboard handling"
    assert source.count("isComposing") >= len(handlers) and "229" in source


# ---------------------------------------------------------------------------
# privacy: the repository is public
# ---------------------------------------------------------------------------


def test_no_personal_name_or_user_path_in_the_tracked_files():
    git = shutil.which("git")
    if not git or not (REPO / ".git").exists():
        pytest.skip("not a git checkout")
    # The pattern is assembled so that this file does not contain what it searches for.
    pattern = "|".join(["ner" + "ga", "kat" + "ey", "ner" + "galheavy"])
    proc = subprocess.run(
        [git, "grep", "--untracked", "-i", "-n", "-E", pattern, "--", ".", ":!.division"],
        cwd=str(REPO), capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert proc.returncode in (0, 1), proc.stderr
    assert proc.stdout.strip() == "", "personal names in tracked files:\n" + proc.stdout[:800]
