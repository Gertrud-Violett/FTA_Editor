"""
Release 1.7.3, fix 3: the diagram's top box disagreed with the headline on a
tree with repeated events.

Confirmed in 1.7.2: every diagram label printed the node's tree-walk
``calculatedProbability``, the root's included, so the Challenger example
showed 0.0349 in the top box and 0.0684 in the top bar.

When the headline is the MCUB the root shows it, marked, with the tree-walk
value beside it (``engine.root_headline``, ``diagram_dot.document_dot``) --
in the diagram, Node Details, the report's diagram, the workbook and the
native render. Every other node, and every tree without such a headline, is
as before. Fixtures and helpers: ``support_1_7_3.py``.
"""
import copy
import html
import io
import re
import threading
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fta_web import diagram_dot, engine, excel_events, report_docx  # noqa: E402
from fta_web.diagram_dot import build_dot_text2, document_dot  # noqa: E402
from fta_web.engine import WebCore  # noqa: E402
from fta_web.numfmt import format_prob  # noqa: E402
from fta_web.tests.support_1_7_3 import *  # noqa: E402,F401,F403


def root_block(dot, name="root"):
    """The DOT statement of node ``name``, as text."""
    match = re.search(r"(?ms)^  %s \[.*?\];\n" % re.escape(name), dot)
    assert match, "no node %r in the DOT" % name
    return match.group(0)


def label_rows(block):
    """The text rows of a label, padding trimmed."""
    return [html_unescape(text).strip()
            for text in re.findall(r'<FONT POINT-SIZE="\d+">(.*?)</FONT>', block, re.S)]


def html_unescape(text):
    return html.unescape(text)


class TestRootHeadlineRule:
    def test_mcub_headline(self):
        assert engine.root_headline({"headlineMethod": "mcub", "headline": 0.07, "treeWalk": 0.03,
                                     "capped": False}) == {
            "method": "mcub", "value": 0.07, "treeWalk": 0.03}

    @pytest.mark.parametrize("summary", [
        None, {}, "x",
        {"headlineMethod": "treeWalk", "headline": 0.07},
        {"headlineMethod": "mcub", "headline": 0.07, "capped": True},
        {"headlineMethod": "mcub", "headline": None},
        {"headlineMethod": "mcub", "headline": float("nan")},
        {"headlineMethod": "mcub", "headline": True},
    ])
    def test_everything_else_keeps_the_tree_walk_label(self, summary):
        assert engine.root_headline(summary) is None

    def test_failed_cut_sets_are_a_tree_walk_headline(self, monkeypatch):
        from fta_web import cutsets

        core = core_of(CHALLENGER)
        monkeypatch.setattr(cutsets, "compute", lambda *a, **k: (_ for _ in ()).throw(
            cutsets.CutsetError("out of time")))

        assert engine.diagram_headline(core.get_data(), core.analysis, core.mode) is None

    def test_the_cheap_check_never_misses_an_mcub_headline(self):
        """``may_need_cut_sets`` False must imply a tree-walk headline -- on
        every tree of the back-to-back corpus and every example."""
        files = sorted((REPO_ROOT / "fta_web" / "tests" / "b2b").glob("*.json")) + sorted(
            EXAMPLES.glob("*.json"))
        files = [f for f in files if f.name != "expected.json"]
        checked = skipped = 0
        for path in files:
            core = WebCore()
            ok, _error = core.load_from_json(str(path))
            if not ok or core.mode == "ETA":
                continue
            core.recalculate_probabilities()
            tree = core.get_data()
            if engine.may_need_cut_sets(tree):
                skipped += 1
                continue
            checked += 1
            assert engine.summary(tree, core.analysis)["headlineMethod"] == "treeWalk", path.name
        assert checked >= 15 and skipped >= 5

    @pytest.mark.parametrize("change,expected", [
        (lambda t: None, False),
        (lambda t: t["children"][0].__setitem__("links", [link("b")]), True),
        (lambda t: t["children"][2].__setitem__("gateType", "XOR"), True),
        (lambda t: t["children"][2].__setitem__("gateType", "TRANSFER"), True),
        (lambda t: t["children"][2].__setitem__("transferTo", "a"), True),
        (lambda t: t["children"][1].__setitem__("id", "a"), True),
        (lambda t: t["children"][2].__setitem__("gateType", "KOFN"), False),
    ])
    def test_the_cheap_check(self, change, expected):
        tree = small_tree()
        tree["children"][0]["links"] = []
        change(tree)

        assert engine.may_need_cut_sets(tree) is expected

    def test_the_headline_is_remembered_per_document(self, monkeypatch):
        core = core_of(CHALLENGER)
        calls = []
        real = engine.summary_with_cut_sets
        monkeypatch.setattr(engine, "summary_with_cut_sets",
                            lambda *a, **k: calls.append(1) or real(*a, **k))

        first = engine.diagram_headline(core.get_data(), core.analysis, core.mode)
        again = engine.diagram_headline(copy.deepcopy(core.get_data()), core.analysis, core.mode)
        core.get_data()["children"][1]["children"][0]["probability"] = 0.9
        core.recalculate_probabilities()
        edited = engine.diagram_headline(core.get_data(), core.analysis, core.mode)

        assert first == again and len(calls) == 2
        assert edited["value"] != first["value"]

    def test_eta_mode_has_no_headline_and_costs_nothing(self, monkeypatch):
        core = core_of(CHALLENGER)
        monkeypatch.setattr(engine, "summary_with_cut_sets",
                            lambda *a, **k: pytest.fail("must not be computed"))

        assert engine.diagram_headline(core.get_data(), core.analysis, "eta") is None
        assert engine.diagram_headline(simple_core(node("root")).get_data(), None, "FTA") is None


STYLE_MATRIX = [(style, rankdir, dark) for style in ("compact", "symbols")
                for rankdir in ("LR", "TB") for dark in (False, True)]


class TestTheDiagramsTopBox:
    @pytest.mark.parametrize("style,rankdir,dark", STYLE_MATRIX)
    def test_challenger_root_shows_the_headline_and_the_tree_walk(self, style, rankdir, dark):
        core = core_of(CHALLENGER)
        summary = engine.summary(core.get_data(), core.analysis)

        dot, id_map, headline = document_dot(core, style=style, rankdir=rankdir, dark=dark)

        assert headline == {"method": "mcub", "value": summary["headline"],
                            "treeWalk": summary["treeWalk"]}
        rows = label_rows(root_block(dot))
        if style == "compact":
            assert rows == ["Loss of Challenger (STS 51-L)",
                            "Gate: AND | P:1.00 | P_calc:0.0684 (MCUB) | tree walk 0.0349"]
        else:
            assert rows == ["Loss of Challenger (STS 51-L)", "Q=0.0684 (MCUB)",
                            "tree walk 0.0349"]
        assert dot.count("MCUB") == 1 and dot.count("tree walk") == 1

    @pytest.mark.parametrize("style,rankdir,dark", STYLE_MATRIX)
    def test_every_other_node_and_the_graph_are_untouched(self, style, rankdir, dark):
        """Only the root's label differs from the diagram without a headline."""
        core = core_of(CHALLENGER)
        options = dict(style=style, rankdir=rankdir, dark=dark, sig_figs=4)

        plain, plain_map = build_dot_text2(core, **options)
        marked, marked_map, _headline = document_dot(core, **options)

        assert marked_map == plain_map
        differing = [(a, b) for a, b in zip(plain.split("\n"), marked.split("\n")) if a != b]
        if style == "compact":
            assert len(plain.split("\n")) == len(marked.split("\n")) and len(differing) == 1
        else:
            assert len(differing) == 1 and len(plain.split("\n")) == len(marked.split("\n"))
        assert "MCUB" in differing[0][1] and "MCUB" not in differing[0][0]
        assert root_block(marked).replace(differing[0][1], differing[0][0]) == root_block(plain)

    def test_the_label_follows_the_significant_figures(self):
        core = core_of(CHALLENGER)

        rows = label_rows(root_block(document_dot(core, sig_figs=6)[0]))

        assert rows[1].endswith("P_calc:0.0683535 (MCUB) | tree walk 0.0349375")

    def test_the_longer_row_is_padded_like_any_other(self):
        """One space per two characters plus the box scale, split evenly."""
        core = core_of(CHALLENGER)

        for style in ("compact", "symbols"):
            block = root_block(document_dot(core, style=style, scale=4)[0])
            for lead, text, trail in re.findall(
                    r'<FONT POINT-SIZE="\d+">( *)([^<]*?)( *)</FONT>', block):
                if "MCUB" not in text and "tree walk" not in text:
                    continue
                total = 4 + (len(html_unescape(text)) + 1) // 2
                assert (len(lead), len(trail)) == (total // 2, total - total // 2), text

    @pytest.mark.parametrize("path", [PLAIN, TMI])
    @pytest.mark.parametrize("style", ["compact", "symbols"])
    def test_a_tree_without_an_mcub_headline_is_byte_for_byte_as_before(self, path, style,
                                                                       monkeypatch):
        """No link, transfer or XOR (a legacy tree), or ETA mode: nothing is
        computed and nothing changes."""
        core = core_of(path)
        monkeypatch.setattr(engine, "summary_with_cut_sets",
                            lambda *a, **k: pytest.fail("must not be computed"))

        dot, id_map, headline = document_dot(core, style=style, sig_figs=3)

        assert headline is None
        assert (dot, id_map) == build_dot_text2(core, style=style, sig_figs=3)
        assert "MCUB" not in dot and "tree walk" not in dot

    def test_links_without_an_mcub_headline_change_nothing(self):
        """A link that repeats no event: the headline stays the tree walk."""
        tree = small_tree()
        tree["children"][0]["links"] = []
        tree["children"][2]["links"] = [link("zzz")]  # dangling: repeats nothing
        core = simple_core(tree)
        assert engine.summary(core.get_data(), core.analysis)["headlineMethod"] == "treeWalk"

        dot, id_map, headline = document_dot(core)

        assert headline is None and (dot, id_map) == build_dot_text2(core)

    def test_a_capped_summary_falls_back_to_the_tree_walk_label(self, monkeypatch):
        tree = node("root", type="Root", logicGate="OR", probability=1.0, children=[
            node("e%d" % i, probability=0.01, links=[link("e0")] if i else []) for i in range(6)])
        core = simple_core(tree)
        core.analysis["cutsets"]["maxCount"] = 5000
        monkeypatch.setitem(engine.SUMMARY_LIMITS, "maxCount", 2)
        assert engine.summary(core.get_data(), core.analysis)["capped"] is True

        dot, id_map, headline = document_dot(core)

        assert headline is None and (dot, id_map) == build_dot_text2(core)

    def test_a_second_node_with_the_roots_id_is_not_the_top_event(self):
        core = core_of(CHALLENGER)
        tree = copy.deepcopy(core.get_data())
        headline = {"method": "mcub", "value": 0.5, "treeWalk": 0.25}

        dot, _ = build_dot_text2(diagram_dot.DocView(tree, core.get_metadata()),
                                 root_headline=headline)

        assert dot.count("0.500 (MCUB)") == 1

    def test_an_empty_document_ignores_a_headline(self):
        dot, id_map = build_dot_text2(diagram_dot.DocView({}, {"title": "t", "date": "d"}),
                                      root_headline={"method": "mcub", "value": 0.5})

        assert "MCUB" not in dot and id_map == {}


class TestTheRenderRoutes:
    def test_api_dot_labels_the_root_and_says_so(self, client):
        open_file(CHALLENGER)
        summary = body(client.get("/api/analysis/summary"))

        payload = body(client.get("/api/dot?sigFigs=3"))

        assert payload["rootHeadline"] == {"method": "mcub", "value": summary["headline"],
                                           "treeWalk": summary["treeWalk"]}
        assert format_prob(summary["headline"], 3) == "0.0684"
        assert label_rows(root_block(payload["dot"]))[1] == (
            "Gate: AND | P:1.00 | P_calc:0.0684 (MCUB) | tree walk 0.0349")
        assert payload["idMap"]["root"] == "root"

    def test_every_other_box_is_its_calculated_probability(self, client):
        open_file(CHALLENGER)
        tree = body(client.get("/api/state"))["tree"]
        payload = body(client.get("/api/dot?sigFigs=5"))

        stack, checked = list(tree["children"]), 0
        while stack:
            current = stack.pop()
            stack.extend(current.get("children") or [])
            (name,) = [k for k, v in payload["idMap"].items() if v == current["id"]]
            meta = label_rows(root_block(payload["dot"], name))[1]
            assert meta.endswith("P_calc:%s" % format_prob(current["calculatedProbability"], 5))
            checked += 1
        assert checked == 12

    def test_a_tree_without_repeats_has_no_root_headline(self, client):
        open_file(PLAIN)

        payload = body(client.get("/api/dot"))

        assert payload["rootHeadline"] is None and "MCUB" not in payload["dot"]

    def test_the_bundled_sample_has_repeated_events_so_it_is_marked_too(self, client):
        """sampleFTA.json links its branches: its headline is the MCUB (1.00,
        as its tree walk), and the box says which of the two it shows."""
        open_file(SAMPLE)

        payload = body(client.get("/api/dot"))

        assert payload["rootHeadline"]["method"] == "mcub"
        assert label_rows(root_block(payload["dot"]))[1].endswith(
            "P_calc:1.00 (MCUB) | tree walk 1.00")

    def test_eta_mode_has_no_root_headline(self, client):
        open_file(TMI)

        payload = body(client.get("/api/dot?style=symbols"))

        assert payload["rootHeadline"] is None and "MCUB" not in payload["dot"]

    def test_the_lock_is_not_held_while_the_headline_is_computed(self, client, monkeypatch):
        """One lock window (the copy), released before the cut sets run."""
        state = open_file(CHALLENGER)
        free = []
        real = engine.summary_with_cut_sets

        def probing(tree, analysis=None):
            grabbed = []
            thread = threading.Thread(
                target=lambda: grabbed.append(state.lock.acquire(timeout=2)) or state.lock.release())
            thread.start()
            thread.join(5)
            free.append(grabbed == [True])
            return real(tree, analysis)

        monkeypatch.setattr(engine, "summary_with_cut_sets", probing)

        payload = body(client.get("/api/dot"))

        assert free == [True] and payload["rootHeadline"]["method"] == "mcub"

    def test_the_label_and_the_tree_are_one_snapshot(self, client, monkeypatch):
        """An edit landing while the headline is computed is in neither the
        label nor the boxes: both come from the copy taken under the lock."""
        state = open_file(CHALLENGER)
        before = body(client.get("/api/dot?sigFigs=6"))
        engine._headline_cache[:] = []
        real = engine.summary_with_cut_sets

        def editing(tree, analysis=None):
            with state.lock:
                leaf = state.core.get_data()["children"][1]["children"][0]
                leaf["probability"] = 0.99
                state.core.recalculate_probabilities()
            return real(tree, analysis)

        monkeypatch.setattr(engine, "summary_with_cut_sets", editing)

        during = body(client.get("/api/dot?sigFigs=6"))
        monkeypatch.setattr(engine, "summary_with_cut_sets", real)
        after = body(client.get("/api/dot?sigFigs=6"))

        assert during["dot"] == before["dot"] and during["rootHeadline"] == before["rootHeadline"]
        assert after["dot"] != before["dot"]
        assert after["rootHeadline"]["value"] > before["rootHeadline"]["value"]

    def test_native_render_gets_the_same_dot(self, client, monkeypatch):
        from fta_web.routes import render as render_route

        open_file(CHALLENGER)
        seen = []
        monkeypatch.setattr(render_route, "render_native",
                            lambda dot, fmt, high_quality=False: seen.append(dot) or b"<svg/>")

        response = client.post("/api/render", json={"format": "svg", "style": "symbols",
                                                    "rankdir": "TB", "dark": True})

        assert response.status_code == 200, body(response)
        expected = body(client.get("/api/dot?style=symbols&rankdir=TB&dark=true"))["dot"]
        assert seen == [expected]
        assert label_rows(root_block(seen[0]))[1:] == ["Q=0.0684 (MCUB)", "tree walk 0.0349"]


class TestTheReportAndTheWorkbook:
    def test_the_reports_own_diagram_has_the_headline(self):
        core = core_of(CHALLENGER)

        dot = report_docx.diagram_dot_text(core, 3)

        assert "P_calc:0.0684 (MCUB) | tree walk 0.0349" in dot
        snapshot = report_docx.DocSnapshot.of(core)
        assert report_docx.diagram_dot_text(snapshot, 3) == dot

    def test_the_report_data_carries_the_root_headline(self):
        core = core_of(CHALLENGER)

        data = report_docx.collect_report_data(core, [], {"sections": ["diagram"]})
        plain = report_docx.collect_report_data(core_of(PLAIN), [], {"sections": ["diagram"]})
        eta = report_docx.collect_report_data(core_of(TMI), [], {"sections": ["diagram"]})

        assert data["rootHeadline"]["method"] == "mcub"
        assert format_prob(data["rootHeadline"]["value"], 3) == "0.0684"
        assert plain["rootHeadline"] is None and eta["rootHeadline"] is None

    @pytest.mark.parametrize("lang,needle", [
        ("en", "The top box shows the top-event probability by MCUB (0.0684)"),
        ("ja", "MCUB による頂上事象の発生確率 (0.0684)"),
    ])
    def test_the_diagram_caption_in_the_report(self, lang, needle):
        docx = pytest.importorskip("docx")
        core = core_of(CHALLENGER)
        png = io.BytesIO()
        pytest.importorskip("PIL.Image").new("RGB", (8, 8), "white").save(png, "PNG")
        options = {"sections": ["diagram"], "lang": lang, "diagramPng": png.getvalue()}

        data = report_docx.collect_report_data(core, [], options)
        document = docx.Document(io.BytesIO(report_docx.build_report(data, options)))
        text = "\n".join(p.text for p in document.paragraphs)

        assert needle in text and "0.0349" in text

    def test_no_caption_without_an_mcub_headline_or_without_a_picture(self):
        docx = pytest.importorskip("docx")
        png = io.BytesIO()
        pytest.importorskip("PIL.Image").new("RGB", (8, 8), "white").save(png, "PNG")

        def text_of(core, picture):
            options = {"sections": ["diagram"], "lang": "en", "diagramPng": picture}
            data = report_docx.collect_report_data(core, [], options)
            document = docx.Document(io.BytesIO(report_docx.build_report(data, options)))
            return "\n".join(p.text for p in document.paragraphs)

        assert "MCUB" not in text_of(core_of(PLAIN), png.getvalue())
        assert "MCUB" not in text_of(core_of(CHALLENGER), None)

    def test_the_event_table_has_no_root_row_to_relabel(self):
        """The report's event table lists basic events; the root of a tree
        with an MCUB headline is a gate and is not in it."""
        core = core_of(CHALLENGER)

        data = report_docx.collect_report_data(core, [], {"sections": ["events"]})

        assert "root" not in [row["Id"] for row in data["events"]]

    def test_the_workbook_points_from_the_root_row_to_the_headline(self, tmp_path):
        openpyxl = pytest.importorskip("openpyxl")
        core = core_of(CHALLENGER)
        summary = engine.summary(core.get_data(), core.analysis)
        path = tmp_path / "challenger.xlsx"

        assert excel_events.export_xlsx(core, str(path), 3) == (True, None)
        book = openpyxl.load_workbook(path)

        events = book["Events"]
        headers = [c.value for c in events[1]]
        cell = events.cell(row=2, column=headers.index("Calculated probability") + 1)
        assert events.cell(row=2, column=1).value == "root"
        # The column stays one quantity: the root's number is its tree walk.
        assert cell.value == pytest.approx(summary["treeWalk"])
        assert cell.comment is not None
        assert cell.comment.text == excel_events.root_comment(engine.root_headline(summary))
        assert repr(summary["headline"]) in cell.comment.text and "MCUB" in cell.comment.text
        assert [c.comment for row in events.iter_rows(min_row=3) for c in row
                if c.comment is not None] == []
        rows = {row[0].value: row for row in book["Analysis"].iter_rows()}
        assert rows["Top event (headline)"][1].value == pytest.approx(summary["headline"])
        assert rows["Top event (headline)"][2].value == "method: mcub"
        assert rows["Tree walk"][1].value == pytest.approx(summary["treeWalk"])
        assert rows["Tree walk"][2].value == excel_events.TREE_WALK_NOTE

    def test_a_workbook_without_an_mcub_headline_is_as_before(self, tmp_path):
        openpyxl = pytest.importorskip("openpyxl")
        path = tmp_path / "plain.xlsx"

        assert excel_events.export_xlsx(core_of(PLAIN), str(path), 3) == (True, None)
        book = openpyxl.load_workbook(path)

        assert [c for row in book["Events"].iter_rows() for c in row if c.comment] == []
        rows = {row[0].value: row for row in book["Analysis"].iter_rows()}
        assert rows["Tree walk"][2].value in (None, "")
        assert rows["Top event (headline)"][2].value == "method: treeWalk"

    def test_the_summary_is_computed_once_per_workbook(self, tmp_path, monkeypatch):
        pytest.importorskip("openpyxl")
        calls = []
        real = engine.summary
        monkeypatch.setattr(engine, "summary", lambda *a, **k: calls.append(1) or real(*a, **k))

        assert excel_events.export_xlsx(core_of(CHALLENGER), str(tmp_path / "c.xlsx"), 3)[0]

        assert len(calls) == 1


class TestTheFrontendFollowsTheSameRule:
    def test_details_shows_both_on_the_root(self):
        source = (STATIC / "details.js").read_text(encoding="utf-8")

        assert "shell.rootHeadline()" in source
        assert "t('details.calcMcub', { walk: formatProbability(calculated) })" in source
        assert "window.addEventListener('fta:headline', onHeadline);" in source
        assert "window.removeEventListener('fta:headline', onHeadline);" in source

    def test_the_shell_rule_is_the_servers(self):
        """main.js rootHeadline(): MCUB, not capped, a finite number, and
        computed for the tree on screen."""
        source = (STATIC / "main.js").read_text(encoding="utf-8")
        fn = re.search(r"^function rootHeadline\(\) \{(.*?)\n\}", source, re.S | re.M).group(1)

        assert "headline.method !== 'mcub' || headline.capped" in fn
        assert "Number.isFinite(headline.value)" in fn
        assert "headline.tree !== store.state.tree" in fn
        assert "tree: forTree," in source
        assert "window.dispatchEvent(new CustomEvent('fta:headline'));" in source

    def test_the_diagram_panel_explains_the_top_box(self):
        source = (STATIC / "diagram.js").read_text(encoding="utf-8")
        catalog = (STATIC / "i18n" / "diagram.js").read_text(encoding="utf-8")

        assert "payload.rootHeadline && payload.rootHeadline.method === 'mcub'" in source
        assert source.count("'diagram17.rootMcub'") == 1
        assert catalog.count("'diagram17.rootMcub'") == 2  # en and ja
