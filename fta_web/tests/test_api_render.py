"""
Tests for the rendering backend: fta_web/rendering.py and the /api render
blueprint.

Two things make this suite unusual, and both are deliberate.

**The DOT is checked against the vendored renderer, not against a golden
string.** ``build_dot_text`` exists to reuse ``json_viewer.gather_nodes`` and
``json_viewer.build_dot`` and to add the header that ``json_viewer.main()``
adds (json_viewer.py:302-307). A frozen expected-output blob would pass just
as happily against a re-implementation that had drifted from the CLI, which is
the one failure this phase has to rule out. So the body is compared to what
the vendored functions produce for the same tree, and only the four header
lines are asserted literally.

**Graphviz is treated as absent by default.** It genuinely is absent on the
development machine, which is also the configuration most users are in, so the
native paths are driven through ``monkeypatch`` -- both present and absent --
and only the one test that needs a real binary is marked
``skipif(shutil.which("dot") is None)``. Nothing here silently passes because
Graphviz happens to be installed, and nothing here fails because it is not.
"""
import base64
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# conftest.py put fta_web/core on sys.path, so the vendored renderer imports
# under its bare name -- exactly as fta_web/rendering.py imports it.
from FTA_Editor_core import FTACore  # noqa: E402
from json_viewer import build_dot, gather_nodes, sanitize_id  # noqa: E402

from fta_web import rendering  # noqa: E402
from fta_web.rendering import (  # noqa: E402
    RenderError,
    RendererUnavailable,
    build_dot_text,
    probe_native_dot,
    render_native,
)
from fta_web.state import get_state, reset_state  # noqa: E402

HAS_NATIVE_DOT = shutil.which("dot") is not None
needs_graphviz = pytest.mark.skipif(
    not HAS_NATIVE_DOT, reason="requires a native Graphviz 'dot' on PATH"
)

#: The four lines json_viewer.main() inserts, for a document titled "T" dated
#: "D". Pinned literally: this is the parity contract with the CLI.
HEADER_TEMPLATE = [
    '  labelloc="t";',
    '  label="{title}\\nDate: {date}";',
    "  fontsize=14;",
    '  fontname="Noto Sans CJK JP";',
]


# --------------------------------------------------------------------------
# fixtures and helpers
# --------------------------------------------------------------------------


@pytest.fixture
def core():
    """A small tree with one live branch and one zero-probability leaf."""
    built = FTACore()
    built.set_metadata(title="Pump Failure", date="2026-01-31")
    built.add_node_to_data(
        "root",
        {
            "id": "root_0",
            "name": "Seal leak",
            "type": "Event",
            "probability": 0.5,
            "logicGate": "OR",
            "notes": "",
            "links": [],
            "children": [],
        },
    )
    built.add_node_to_data(
        "root",
        {
            "id": "root_1",
            "name": "Impossible cause",
            "type": "Event",
            "probability": 0.0,
            "logicGate": "OR",
            "notes": "",
            "links": [],
            "children": [],
        },
    )
    built.recalculate_probabilities()
    return built


@pytest.fixture
def client(core):
    """A bare Flask app with the tree and render blueprints, no security layer."""
    flask = pytest.importorskip("flask")
    from fta_web.routes.render import render_bp
    from fta_web.routes.tree import tree_bp

    state = reset_state()
    state.core = core
    app = flask.Flask(__name__)
    app.register_blueprint(tree_bp)
    app.register_blueprint(render_bp)
    app.config.update(TESTING=True)
    with app.test_client() as test_client:
        yield test_client


def header_for(title, date):
    return [line.format(title=title, date=date) for line in HEADER_TEMPLATE]


def strip_header(dot_text):
    """The DOT minus the four inserted header lines."""
    lines = dot_text.split("\n")
    return "\n".join(lines[:1] + lines[5:])


def fake_which(result):
    """A shutil.which replacement answering `result` for 'dot' only."""

    def _which(name, *args, **kwargs):
        return result if name == "dot" else None

    return _which


# --------------------------------------------------------------------------
# build_dot_text: parity with the vendored pipeline
# --------------------------------------------------------------------------


class TestBuildDotText:
    def test_body_is_exactly_what_the_vendored_pipeline_produces(self, core):
        nodes, edges = gather_nodes(core.get_data(), hide_zero=False)
        expected = build_dot(nodes, edges)

        produced = build_dot_text(core)

        assert strip_header(produced) == expected

    def test_body_matches_the_vendored_pipeline_with_hide_zero_too(self, core):
        nodes, edges = gather_nodes(core.get_data(), hide_zero=True)
        expected = build_dot(nodes, edges)

        assert strip_header(build_dot_text(core, hide_zero=True)) == expected

    def test_header_lines_are_present_and_correctly_placed(self, core):
        lines = build_dot_text(core).split("\n")

        assert lines[0] == "digraph G {"
        assert lines[1:5] == header_for("Pump Failure", "2026-01-31")
        # The vendored body starts immediately after the header, unshifted.
        assert lines[5] == "  rankdir=LR;"
        assert lines[-1] == "}"

    def test_header_carries_the_live_metadata(self, core):
        core.set_metadata(title="Renamed", date="2020-02-29")

        assert build_dot_text(core).split("\n")[1:5] == header_for(
            "Renamed", "2020-02-29"
        )

    def test_header_appears_exactly_once(self, core):
        assert build_dot_text(core).count('labelloc="t"') == 1

    def test_a_quote_in_the_title_cannot_break_the_dot_string(self, core):
        # json_viewer.main() interpolates the title raw, so this would emit
        # label="A "B"" -- unparseable by any Graphviz. rendering.py escapes.
        core.set_metadata(title='A "B" pump', date="2026-01-31")

        label = build_dot_text(core).split("\n")[2]

        assert label == '  label="A \\"B\\" pump\\nDate: 2026-01-31";'

    def test_an_empty_tree_still_produces_a_valid_graph(self):
        empty = FTACore()
        empty.set_data({})

        dot_text = build_dot_text(empty)

        assert dot_text.startswith("digraph G {")
        assert dot_text.endswith("}")
        # No stray node named "None" from gather_nodes walking an empty dict.
        assert "None" not in dot_text


class TestHideZero:
    def test_hide_zero_drops_zero_probability_nodes(self, core):
        assert core.find_node_by_id("root_1")["calculatedProbability"] == 0.0

        full = build_dot_text(core, hide_zero=False)
        hidden = build_dot_text(core, hide_zero=True)

        assert sanitize_id("root_1") in full
        assert "Impossible cause" in full
        assert sanitize_id("root_1") not in hidden
        assert "Impossible cause" not in hidden

    def test_hide_zero_keeps_the_non_zero_nodes_and_their_edge(self, core):
        hidden = build_dot_text(core, hide_zero=True)

        assert "Seal leak" in hidden
        assert "root:e -> root_0:w" in hidden
        # ...and the edge to the dropped node went with it.
        assert "root_1" not in hidden


# --------------------------------------------------------------------------
# probe_native_dot / render_native
# --------------------------------------------------------------------------


class TestProbe:
    def test_probe_reports_a_present_binary(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", fake_which("/opt/bin/dot"))
        assert probe_native_dot() == "/opt/bin/dot"

    def test_probe_reports_an_absent_binary(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", fake_which(None))
        assert probe_native_dot() is None

    def test_probe_is_not_cached_so_it_can_change_mid_session(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", fake_which(None))
        assert probe_native_dot() is None
        monkeypatch.setattr(shutil, "which", fake_which("/opt/bin/dot"))
        assert probe_native_dot() == "/opt/bin/dot"


class TestRenderNative:
    def test_missing_dot_raises_renderer_unavailable_naming_graphviz(
        self, monkeypatch, core
    ):
        monkeypatch.setattr(shutil, "which", fake_which(None))

        with pytest.raises(RendererUnavailable) as caught:
            render_native(build_dot_text(core), "svg")

        message = str(caught.value)
        assert "Graphviz" in message
        assert rendering.GRAPHVIZ_DOWNLOAD_URL in message
        assert caught.value.reason == "not_installed"

    def test_an_unsupported_format_never_reaches_the_command_line(self, monkeypatch):
        def explode(*args, **kwargs):  # pragma: no cover - must not run
            raise AssertionError("subprocess was invoked for an invalid format")

        monkeypatch.setattr(shutil, "which", fake_which("/opt/bin/dot"))
        monkeypatch.setattr(subprocess, "run", explode)

        with pytest.raises(ValueError):
            render_native("digraph G {}", "pdf; rm -rf /")

    def test_high_quality_adds_the_cli_flags(self, monkeypatch):
        seen = {}

        def fake_run(command, **kwargs):
            seen["command"] = command
            Path(command[command.index("-o") + 1]).write_bytes(b"<svg/>")
            return subprocess.CompletedProcess(command, 0, b"", b"")

        monkeypatch.setattr(shutil, "which", fake_which("/opt/bin/dot"))
        monkeypatch.setattr(subprocess, "run", fake_run)

        render_native("digraph G {}", "svg", high_quality=True)
        assert seen["command"][:2] == ["/opt/bin/dot", "-Tsvg"]
        for flag in rendering.HIGH_QUALITY_FLAGS:
            assert flag in seen["command"]

        render_native("digraph G {}", "png", high_quality=False)
        assert seen["command"][:2] == ["/opt/bin/dot", "-Tpng"]
        for flag in rendering.HIGH_QUALITY_FLAGS:
            assert flag not in seen["command"]

    def test_a_failing_dot_reports_graphviz_stderr(self, monkeypatch):
        def fake_run(command, **kwargs):
            return subprocess.CompletedProcess(command, 1, b"", b"syntax error near line 3")

        monkeypatch.setattr(shutil, "which", fake_which("/opt/bin/dot"))
        monkeypatch.setattr(subprocess, "run", fake_run)

        with pytest.raises(RenderError) as caught:
            render_native("digraph G {", "svg")

        assert caught.value.reason == "render_failed"
        assert "syntax error near line 3" in caught.value.stderr

    def test_a_timeout_is_reported_as_such(self, monkeypatch):
        def fake_run(command, **kwargs):
            raise subprocess.TimeoutExpired(command, rendering.RENDER_TIMEOUT_SECONDS)

        monkeypatch.setattr(shutil, "which", fake_which("/opt/bin/dot"))
        monkeypatch.setattr(subprocess, "run", fake_run)

        with pytest.raises(RenderError) as caught:
            render_native("digraph G {}", "png")

        assert caught.value.reason == "timeout"

    @pytest.mark.parametrize(
        "failure",
        [
            "nonzero",
            "timeout",
            "oserror",
            "empty",
        ],
    )
    def test_temp_files_are_cleaned_up_on_every_failure_path(
        self, monkeypatch, tmp_path, failure
    ):
        def fake_run(command, **kwargs):
            if failure == "timeout":
                raise subprocess.TimeoutExpired(command, 1)
            if failure == "oserror":
                raise OSError("Text file busy")
            if failure == "nonzero":
                return subprocess.CompletedProcess(command, 1, b"", b"boom")
            return subprocess.CompletedProcess(command, 0, b"", b"")  # "empty"

        monkeypatch.setattr(shutil, "which", fake_which("/opt/bin/dot"))
        monkeypatch.setattr(subprocess, "run", fake_run)
        # tempfile.gettempdir() honours this module attribute, so every temp
        # file this render creates lands where the assertion can see it.
        monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))

        with pytest.raises(RenderError):
            render_native("digraph G {}", "svg")

        assert list(tmp_path.iterdir()) == []

    def test_temp_files_are_cleaned_up_on_success_too(self, monkeypatch, tmp_path):
        def fake_run(command, **kwargs):
            Path(command[command.index("-o") + 1]).write_bytes(b"<svg/>")
            return subprocess.CompletedProcess(command, 0, b"", b"")

        monkeypatch.setattr(shutil, "which", fake_which("/opt/bin/dot"))
        monkeypatch.setattr(subprocess, "run", fake_run)
        monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))

        assert render_native("digraph G {}", "svg") == b"<svg/>"
        assert list(tmp_path.iterdir()) == []

    @needs_graphviz
    def test_real_graphviz_renders_svg(self, core):
        data = render_native(build_dot_text(core), "svg")

        head = data[:512].lstrip()
        assert head.startswith(b"<?xml") or head.startswith(b"<svg")
        assert b"<svg" in data
        assert b"Seal leak" in data

    @needs_graphviz
    def test_real_graphviz_renders_png(self, core):
        data = render_native(build_dot_text(core), "png")

        assert data.startswith(b"\x89PNG\r\n\x1a\n")


# --------------------------------------------------------------------------
# GET /api/dot
# --------------------------------------------------------------------------


def assert_parseable_dot(dot_text):
    """Structural checks that hold for any DOT this backend emits.

    Not a Graphviz parser: on a machine without Graphviz there is nothing to
    parse with, and the point of these endpoints is that such a machine is
    fully supported. ``dot`` itself parses the output in the tests marked
    ``needs_graphviz``.
    """
    assert dot_text.startswith("digraph G {")
    assert dot_text.rstrip().endswith("}")
    assert dot_text.count("{") == dot_text.count("}")
    # node_label() emits multi-line HTML-like labels; they must be closed.
    assert dot_text.count("<<TABLE") == dot_text.count("</TABLE>>")
    # Every attribute list is closed on the line it opened on.
    for line in dot_text.split("\n"):
        if "[label=" in line and "<<TABLE" not in line:
            assert line.rstrip().endswith("];"), "unterminated line: %r" % line


class TestDotEndpoint:
    def test_returns_parseable_dot_and_a_renderer(self, client):
        response = client.get("/api/dot")

        assert response.status_code == 200
        body = response.get_json()
        assert body["ok"] is True
        assert body["renderer"] in ("wasm", "native")
        assert_parseable_dot(body["dot"])
        assert "Seal leak" in body["dot"]

    def test_dot_matches_the_library_function(self, client, core):
        assert client.get("/api/dot").get_json()["dot"] == build_dot_text(core)

    def test_hide_zero_query_parameter_drops_zero_nodes(self, client):
        shown = client.get("/api/dot").get_json()
        hidden = client.get("/api/dot?hideZero=true").get_json()

        assert shown["hideZero"] is False
        assert hidden["hideZero"] is True
        assert "Impossible cause" in shown["dot"]
        assert "Impossible cause" not in hidden["dot"]
        assert_parseable_dot(hidden["dot"])

    @pytest.mark.parametrize("raw", ["true", "1", "yes", "on", "TRUE"])
    def test_truthy_spellings(self, client, raw):
        assert client.get("/api/dot?hideZero=%s" % raw).get_json()["hideZero"] is True

    @pytest.mark.parametrize("raw", ["false", "0", "no", "off", ""])
    def test_falsy_spellings(self, client, raw):
        assert client.get("/api/dot?hideZero=%s" % raw).get_json()["hideZero"] is False

    def test_an_unparseable_flag_is_refused_rather_than_assumed_false(self, client):
        response = client.get("/api/dot?hideZero=treu")

        assert response.status_code == 400
        body = response.get_json()
        assert body["ok"] is False
        assert body["error"]["code"] == "INVALID_FIELD"

    def test_renderer_field_follows_the_live_probe(self, client, monkeypatch):
        monkeypatch.setattr(shutil, "which", fake_which(None))
        assert client.get("/api/dot").get_json()["renderer"] == "wasm"

        monkeypatch.setattr(shutil, "which", fake_which("/opt/bin/dot"))
        assert client.get("/api/dot").get_json()["renderer"] == "native"


# --------------------------------------------------------------------------
# POST /api/render
# --------------------------------------------------------------------------


class TestRenderEndpoint:
    def test_503_when_there_is_no_native_dot(self, client, monkeypatch):
        monkeypatch.setattr(shutil, "which", fake_which(None))

        response = client.post("/api/render", json={"format": "png"})

        assert response.status_code == 503
        body = response.get_json()
        assert body["ok"] is False
        error = body["error"]
        assert error["code"] == "RENDERER_UNAVAILABLE"
        # The remedy has to travel with the error, not live only in the docs.
        assert "Graphviz" in error["message"]
        assert rendering.GRAPHVIZ_DOWNLOAD_URL in error["message"]
        assert error["detail"]["reason"] == "not_installed"
        assert error["detail"]["format"] == "png"

    def test_503_names_the_browser_renderer_as_the_fallback(self, client, monkeypatch):
        monkeypatch.setattr(shutil, "which", fake_which(None))

        error = client.post("/api/render", json={}).get_json()["error"]

        assert error["detail"]["renderer"] == "wasm"

    def test_success_when_a_native_dot_is_present(self, client, monkeypatch):
        captured = {}

        def fake_render(dot_text, fmt, high_quality=False):
            captured.update(dot=dot_text, fmt=fmt, high_quality=high_quality)
            return b"<svg>rendered</svg>"

        monkeypatch.setattr(shutil, "which", fake_which("/opt/bin/dot"))
        monkeypatch.setattr("fta_web.routes.render.render_native", fake_render)

        response = client.post(
            "/api/render", json={"format": "svg", "highQuality": True}
        )

        assert response.status_code == 200
        body = response.get_json()
        assert body["ok"] is True
        assert body["renderer"] == "native"
        assert body["format"] == "svg"
        assert body["contentType"] == "image/svg+xml"
        assert body["encoding"] == "base64"
        assert base64.b64decode(body["data"]) == b"<svg>rendered</svg>"
        assert body["bytes"] == len(b"<svg>rendered</svg>")
        assert captured["fmt"] == "svg"
        assert captured["high_quality"] is True
        assert captured["dot"].startswith("digraph G {")

    def test_hide_zero_reaches_the_renderer(self, client, monkeypatch):
        captured = {}

        def fake_render(dot_text, fmt, high_quality=False):
            captured["dot"] = dot_text
            return b"\x89PNG\r\n\x1a\n"

        monkeypatch.setattr(shutil, "which", fake_which("/opt/bin/dot"))
        monkeypatch.setattr("fta_web.routes.render.render_native", fake_render)

        body = client.post(
            "/api/render", json={"format": "png", "hideZero": True}
        ).get_json()

        assert body["hideZero"] is True
        assert body["contentType"] == "image/png"
        assert "Impossible cause" not in captured["dot"]

    def test_defaults_are_svg_full_tree_normal_quality(self, client, monkeypatch):
        monkeypatch.setattr(shutil, "which", fake_which("/opt/bin/dot"))
        monkeypatch.setattr(
            "fta_web.routes.render.render_native",
            lambda dot_text, fmt, high_quality=False: b"<svg/>",
        )

        body = client.post("/api/render", json={}).get_json()

        assert (body["format"], body["hideZero"], body["highQuality"]) == (
            "svg",
            False,
            False,
        )

    def test_a_dot_that_runs_and_fails_is_a_503_with_the_reason(
        self, client, monkeypatch
    ):
        def fake_render(dot_text, fmt, high_quality=False):
            raise RenderError("dot fell over", stderr="syntax error in line 3")

        monkeypatch.setattr(shutil, "which", fake_which("/opt/bin/dot"))
        monkeypatch.setattr("fta_web.routes.render.render_native", fake_render)

        response = client.post("/api/render", json={"format": "svg"})

        assert response.status_code == 503
        error = response.get_json()["error"]
        assert error["code"] == "RENDERER_UNAVAILABLE"
        assert error["detail"]["reason"] == "render_failed"
        assert "syntax error in line 3" in error["detail"]["stderr"]

    @pytest.mark.parametrize("bad", ["pdf", "", "svg;rm -rf /", 7, ["svg"]])
    def test_only_svg_and_png_are_accepted(self, client, bad):
        response = client.post("/api/render", json={"format": bad})

        assert response.status_code == 400
        assert response.get_json()["error"]["code"] == "INVALID_FIELD"

    @pytest.mark.parametrize("spelling", ["SVG", " svg ", "Svg"])
    def test_case_and_whitespace_are_normalised_not_rejected(
        self, client, monkeypatch, spelling
    ):
        monkeypatch.setattr(shutil, "which", fake_which("/opt/bin/dot"))
        monkeypatch.setattr(
            "fta_web.routes.render.render_native",
            lambda dot_text, fmt, high_quality=False: b"<svg/>",
        )

        assert (
            client.post("/api/render", json={"format": spelling}).get_json()["format"]
            == "svg"
        )

    @pytest.mark.parametrize("field", ["hideZero", "highQuality"])
    def test_a_non_boolean_flag_is_refused(self, client, field):
        response = client.post("/api/render", json={field: "sometimes"})

        assert response.status_code == 400
        error = response.get_json()["error"]
        assert error["code"] == "INVALID_FIELD"
        assert error["detail"]["field"] == field

    def test_a_non_object_body_is_refused(self, client):
        response = client.post(
            "/api/render", data="[1,2]", content_type="application/json"
        )

        assert response.status_code == 400
        assert response.get_json()["error"]["code"] == "INVALID_JSON"

    @needs_graphviz
    def test_real_native_render_round_trip(self, client):
        body = client.post("/api/render", json={"format": "svg"}).get_json()

        assert body["ok"] is True
        assert body["renderer"] == "native"
        assert base64.b64decode(body["data"]).lstrip()[:5] in (b"<?xml", b"<svg ")


# --------------------------------------------------------------------------
# capability reporting
# --------------------------------------------------------------------------


class TestCapabilities:
    def test_state_reports_all_three_capabilities_as_booleans(self, client):
        body = client.get("/api/state").get_json()

        capabilities = body["capabilities"]
        assert set(capabilities) == {"nativeDot", "excelExport", "aiConfigured"}
        for name, value in capabilities.items():
            assert isinstance(value, bool), "%s is %r" % (name, value)

    def test_the_legacy_top_level_keys_are_unchanged(self, client):
        body = client.get("/api/state").get_json()

        assert isinstance(body["nativeDot"], bool)
        assert isinstance(body["aiConfigured"], bool)
        assert body["nativeDot"] == body["capabilities"]["nativeDot"]
        assert body["aiConfigured"] == body["capabilities"]["aiConfigured"]

    def test_native_dot_capability_matches_this_machine(self, client):
        assert client.get("/api/state").get_json()["capabilities"][
            "nativeDot"
        ] is HAS_NATIVE_DOT

    def test_excel_capability_matches_whether_openpyxl_imports(self, client):
        import importlib.util

        expected = importlib.util.find_spec("openpyxl") is not None

        assert (
            client.get("/api/state").get_json()["capabilities"]["excelExport"]
            is expected
        )

    def test_openpyxl_is_probed_once_per_process_not_per_request(self, monkeypatch):
        """A /api/state call must not import-scan openpyxl every time."""
        import importlib.util

        from fta_web import state as state_module

        state_module._probe_excel_export()  # warm the cache, whatever it holds

        calls = []
        real_find_spec = importlib.util.find_spec

        def counting_find_spec(name, *args, **kwargs):
            if name == "openpyxl":
                calls.append(name)
            return real_find_spec(name, *args, **kwargs)

        monkeypatch.setattr(importlib.util, "find_spec", counting_find_spec)

        reset_state().to_dict()
        get_state().to_dict()
        get_state().to_dict()

        assert calls == []
