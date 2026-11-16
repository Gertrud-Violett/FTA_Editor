"""R191, BRIEF criterion 1: the editor version in the page and in the API (CR-20261115-version-in-ui).

The page's ``<title>`` is exactly ``FTA Editor <version>``; the top bar holds exactly one
``<span id="app-version">`` whose text is ``v<version>``; ``GET /api/state`` has a top-level string
field ``version``; all three come from ``report_docx.TOOL_VERSION`` at request time (``cli.VERSION``
is the same object and is not patched separately), and no static file carries a second copy of it.

The version is always read from ``report_docx`` while the test runs: this file never names it.

Two copies of ``report_docx`` can be loaded (``fta_web.report_docx`` and the bare ``report_docx`` that
``create_app()`` and the blueprints import by bare name).  The monkeypatch below patches every loaded
copy, so the tests do not depend on which of the two the page or the API reads.

Runs in the default collection; ``verify`` of R191 ignores this folder until the feature is built (T1).
"""
import html.parser
import importlib
import re
import sys
from pathlib import Path

import pytest

# fta_web/tests/acceptance/version_ui/test_version_ui.py -> parents[4] is the repo root
REPO_ROOT = Path(__file__).resolve().parents[4]
FTA_WEB_DIR = REPO_ROOT / "fta_web"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

#: a value no real release has; HTML-safe
TEST_VERSION = "0.0.1-r191test"

VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


def tool_version() -> str:
    """The version of the tree under test, read from report_docx now."""
    report_docx = importlib.import_module("fta_web.report_docx")
    value = report_docx.TOOL_VERSION
    assert isinstance(value, str) and re.match(r"^\d+\.\d+\.\d+", value), value
    return value


def _report_docx_modules():
    """Every loaded copy of report_docx (package and bare name), after making sure both are loaded."""
    importlib.import_module("fta_web.report_docx")
    importlib.import_module("fta_web.app")  # puts fta_web/ on sys.path, as create_app() relies on
    try:
        importlib.import_module("report_docx")
    except ImportError:
        pass
    modules = [sys.modules[name] for name in ("fta_web.report_docx", "report_docx")
               if name in sys.modules and hasattr(sys.modules[name], "TOOL_VERSION")]
    assert modules, "no loaded report_docx module"
    return modules


@pytest.fixture
def client(tmp_path):
    """The full app from ``create_app()`` (page and API), no token (test-only, as the other web tests)."""
    from fta_web.app import create_app

    flask_app = create_app(fs_root=tmp_path)
    flask_app.config.update(TESTING=True)
    try:  # the blueprints import ``state`` by bare name: start from a fresh document
        importlib.import_module("state").reset_state()
    except ImportError:
        pass
    with flask_app.test_client() as test_client:
        yield test_client


@pytest.fixture
def patch_version(monkeypatch):
    """Set ``report_docx.TOOL_VERSION`` in every loaded copy.  ``cli.VERSION`` is NOT touched."""
    def apply(value):
        for module in _report_docx_modules():
            monkeypatch.setattr(module, "TOOL_VERSION", value)
    return apply


# ---- reading the page -----------------------------------------------------------------------


class Page(html.parser.HTMLParser):
    """Titles, elements with an id and the tag stack above each of them."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.titles = []
        self._in_title = False
        self.by_id = {}  # id -> list of {"tag", "text", "ancestors"}
        self._open = []  # elements whose text is being collected

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "title":
            self._in_title = True
            self.titles.append("")
        element = {"tag": tag, "attrs": attrs, "text": "", "ancestors": [(t, a) for t, a in self.stack]}
        if attrs.get("id"):
            self.by_id.setdefault(attrs["id"], []).append(element)
        self._open.append(element)
        if tag not in VOID_TAGS:
            self.stack.append((tag, attrs))
        else:
            self._open.pop()

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag in VOID_TAGS:
            return
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break
        for index in range(len(self._open) - 1, -1, -1):
            if self._open[index]["tag"] == tag:
                del self._open[index:]
                break

    def handle_data(self, data):
        if self._in_title:
            self.titles[-1] += data
        for element in self._open:
            element["text"] += data


def read_page(client):
    response = client.get("/")
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    page = Page()
    page.feed(text)
    return page, text


def api_state(client):
    response = client.get("/api/state")
    assert response.status_code == 200, response.get_data(as_text=True)[:300]
    body = response.get_json()
    assert isinstance(body, dict)
    return body


# ---- the version in the page ----------------------------------------------------------------


def test_title_is_the_app_name_and_the_version(client):
    page, _text = read_page(client)
    assert page.titles == ["FTA Editor " + tool_version()], page.titles


def test_exactly_one_app_version_span_with_the_version_text(client):
    page, text = read_page(client)
    found = page.by_id.get("app-version", [])
    assert len(found) == 1, "expected exactly one #app-version, found %d" % len(found)
    assert text.count('id="app-version"') + text.count("id='app-version'") == 1
    element = found[0]
    assert element["tag"] == "span", element["tag"]
    assert element["text"].strip() == "v" + tool_version(), repr(element["text"])


def test_the_span_is_inside_the_top_bar(client):
    page, _text = read_page(client)
    found = page.by_id.get("app-version", [])
    assert len(found) == 1, "expected exactly one #app-version, found %d" % len(found)
    classes = [(tag, (attrs.get("class") or "").split()) for tag, attrs in found[0]["ancestors"]]
    assert any(tag == "header" and "topbar" in cls for tag, cls in classes), classes


def test_the_span_is_not_a_control(client):
    """Not focusable, not a button (BRIEF criterion 3, source part)."""
    page, _text = read_page(client)
    found = page.by_id.get("app-version", [])
    assert len(found) == 1, "expected exactly one #app-version, found %d" % len(found)
    element = found[0]
    assert element["tag"] == "span"
    assert "tabindex" not in element["attrs"] and "role" not in element["attrs"], element["attrs"]
    inside = [tag for tag, _attrs in element["ancestors"] if tag in ("button", "a", "label", "summary")]
    assert inside == [], inside


# ---- the version in the API -----------------------------------------------------------------


def test_api_state_has_a_top_level_version_string(client):
    body = api_state(client)
    assert "version" in body, sorted(body)[:20]
    assert isinstance(body["version"], str)
    assert body["version"] == tool_version()


def test_the_existing_api_state_fields_are_still_there(client):
    """The new field is additive: the document fields the page renders from stay."""
    body = api_state(client)
    assert {"tree", "dirty"} <= set(body), sorted(body)[:30]


# ---- one source, read at request time -------------------------------------------------------


def test_a_patched_tool_version_shows_in_the_page_and_in_the_api(client, patch_version):
    patch_version(TEST_VERSION)
    page, _text = read_page(client)
    assert page.titles == ["FTA Editor " + TEST_VERSION], page.titles
    found = page.by_id.get("app-version", [])
    assert len(found) == 1 and found[0]["text"].strip() == "v" + TEST_VERSION, [e["text"] for e in found]
    assert api_state(client).get("version") == TEST_VERSION


def test_the_version_is_read_per_request_not_cached(client, patch_version, monkeypatch):
    real = tool_version()
    before, _ = read_page(client)
    assert before.titles == ["FTA Editor " + real], before.titles
    assert api_state(client).get("version") == real
    patch_version(TEST_VERSION)
    during, _ = read_page(client)
    assert during.titles == ["FTA Editor " + TEST_VERSION], during.titles
    assert api_state(client).get("version") == TEST_VERSION
    monkeypatch.undo()
    after, _ = read_page(client)
    assert after.titles == ["FTA Editor " + real], after.titles
    assert api_state(client).get("version") == real


def test_cli_version_is_not_where_the_value_comes_from(client, patch_version):
    """``cli.VERSION`` is a copy taken at import.  The page and the API read report_docx, so patching only
    report_docx moves them and leaves ``cli.VERSION`` as it was."""
    cli = importlib.import_module("fta_web.cli")
    real = cli.VERSION
    patch_version(TEST_VERSION)
    assert cli.VERSION == real != TEST_VERSION
    assert api_state(client).get("version") == TEST_VERSION


# ---- no second copy in the front end --------------------------------------------------------

SCANNED = [FTA_WEB_DIR / "static" / "js", FTA_WEB_DIR / "static" / "css", FTA_WEB_DIR / "templates"]
SUFFIXES = {".js", ".mjs", ".css", ".html", ".htm", ".json", ".svg", ".txt"}

#: shapes of a hard-coded displayed version, besides the current number itself:
#:  v1.2.3 | FTA Editor 1.2 / FTA Editor v1.2 | version: '1.2.3' / VERSION = "1.2.3"
COPY_PATTERNS = [
    re.compile(r"(?<![A-Za-z0-9_.])v\d+\.\d+\.\d+"),
    re.compile(r"FTA Editor\s+v?\d+\.\d+"),
    re.compile(r"version\W{1,6}\d+\.\d+\.\d+", re.I),
]


def scan_text(text: str, version: str):
    """Reasons why a text carries a hard-coded version: the current number, or a copy-shaped string."""
    hits = []
    if re.search(r"(?<![0-9.])%s(?![0-9])" % re.escape(version), text):
        hits.append("the current version %s" % version)
    for pattern in COPY_PATTERNS:
        match = pattern.search(text)
        if match:
            hits.append("%r" % match.group(0))
    return hits


def front_end_files():
    files = []
    for root in SCANNED:
        assert root.is_dir(), root
        files += [p for p in sorted(root.rglob("*")) if p.is_file() and p.suffix.lower() in SUFFIXES]
    return files


def test_the_scan_sees_the_front_end():
    names = {p.name for p in front_end_files()}
    assert {"main.js", "app.css", "theme.css", "index.html"} <= names, sorted(names)[:20]
    assert len(names) >= 20


def test_no_front_end_file_carries_the_version_or_a_copy_of_it():
    version = tool_version()
    found = {}
    for path in front_end_files():
        hits = scan_text(path.read_text(encoding="utf-8", errors="replace"), version)
        if hits:
            found[str(path.relative_to(REPO_ROOT)).replace("\\", "/")] = hits
    assert found == {}, "hard-coded version in the front end: %s" % found


@pytest.mark.parametrize("text, expected", [
    ("const APP_NAME = 'FTA Editor 9.9.9';", True),
    ("<title>FTA Editor 9.9</title>", True),
    ("el.textContent = 'v9.9.9';", True),
    ("const version = '9.9.9';", True),
    ("VERSION = \"9.9.9\"", True),
    ("// 1.7.0 said Rendering", False),
    ("const APP_NAME = 'FTA Editor ' + version;", False),
    ("<title>FTA Editor {{ version }}</title>", False),
    ("a node. Without this \"0.5.1\" typed for", False),
    ("rgba(0, 0, 0, .55)", False),
])
def test_selftest_the_copy_patterns(text, expected):
    """The scan above would pass on any front end if its patterns matched nothing: they match these."""
    hits = scan_text(text, "9.9.9")
    assert bool(hits) is expected, hits
