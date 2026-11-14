"""F4 BRIEF criterion 3 (FN-53, G5): what-if never changes the file or any output.

The factors live in the browser and ``POST /api/whatif`` is the only request that carries
one (DESIGN D1). So the server-side proof of FN-53 is: with the endpoint called with factor
10 (the cache then holds the baseline), every output path of the app gives exactly what it
gave before the first call --

* Save: the bytes of the saved file;            * the recovery copy: its bytes;
* the JSON and XML exports: bytes; Excel export: every cell value (the file itself holds
  zip timestamps); the DOCX report: its text; the diagram: DOT text and the SVG;
* the AI context: the messages sent to the provider (mocked, no network);
* CSV and events CSV: the CLI's ``cutsets --csv``, ``quantify --csv`` and ``importance --csv``
  on the saved file (the browser's own CSV / Copy CSV are checked by the GUI section);
* the analysis results the tabs build their CSV from (summary, cut sets, importance);
* ``revision``, ``documentSerial``, ``canUndo``, ``dirty``, ``state.snapshot()``.

Creation timestamps (``Generated: YYYY-MM-DD HH:MM``) are masked. The comparison itself is
guarded: a repeat capture is identical, and a real edit changes the capture.
Until the route exists each test fails on the 404 of ``POST /api/whatif``.
"""
import base64
import copy
import json
import re

import pytest

import whatif_support as W

API_KEY = "sk-testkeyNOTREAL0123456789abcdefAB12"
TIMESTAMP = re.compile(r"\d{4}-\d\d-\d\d[ T]\d\d:\d\d(:\d\d)?")


def mask(text):
    return TIMESTAMP.sub("<time>", text)


class Outputs:
    """Reads every output path of the app for the open document."""

    def __init__(self, api, tmp_path, capsys, monkeypatch):
        self.api = api
        self.tmp = tmp_path
        self.capsys = capsys
        self.monkeypatch = monkeypatch
        self.messages = []
        self._ai_ready = False

    # -- AI (mocked provider) --------------------------------------------

    def _prepare_ai(self):
        if self._ai_ready:
            return
        from ai_providers import AIProviderFactory

        from fta_web import ai_bridge

        ai_bridge.reset_handler()
        provider = AIProviderFactory.get_provider("OpenAI")
        assert provider is not None
        self.monkeypatch.setattr(provider, "test_connection", lambda *a, **k: (True, "ok"))

        def send_message(api_key, endpoint, model, messages, max_tokens=2000):
            self.messages.append(copy.deepcopy(messages))
            return "Noted.", None

        self.monkeypatch.setattr(provider, "send_message", send_message)
        status, body = self.api.post("/api/ai/credentials", {
            "provider": "OpenAI", "apiKey": API_KEY,
            "endpoint": "https://api.openai.com/v1", "model": "gpt-4o"})
        assert status == 200, body
        self._ai_ready = True

    def ai_context(self):
        self._prepare_ai()
        self.messages.clear()
        status, body = self.api.post("/api/ai/chat", {"message": "What is the top event probability?"})
        assert status == 200, body
        assert self.messages, "the provider was not called"
        sent = json.dumps(self.messages[-1], sort_keys=True, ensure_ascii=False)
        assert self.api.call("DELETE", "/api/ai/conversation")[0] == 200  # next capture starts clean
        return sent

    # -- single outputs ----------------------------------------------------

    def save_bytes(self):
        status, body = self.api.post("/api/file/save")
        assert status == 200, body
        return (self.api.root / "doc.json").read_bytes()

    def export(self, fmt):
        status, blob = self.api.binary("GET", "/api/export/" + fmt)
        assert status == 200, (fmt, status)
        return blob

    def xlsx_cells(self):
        cells = []
        for sheet, row, column, value in W.M.xlsx_cells(self.export("xlsx")):
            cells.append((sheet, row, column, mask(value) if isinstance(value, str) else value))
        return cells

    def docx_text(self):
        status, blob = self.api.binary("POST", "/api/report/docx", json={
            "sections": ["metadata", "headline", "assumptions", "events", "cutsets",
                         "importance", "validation", "traceability"], "lang": "en"})
        assert status == 200, status
        return mask(W.M.docx_text(blob)[0])

    def diagram(self):
        status, dot = self.api.get("/api/dot")
        assert status == 200, dot
        status, rendered = self.api.post("/api/render", {"format": "svg"})
        svg = None
        if status == 503:
            # the only tolerated failure: no diagram renderer on this machine (the dedicated
            # diagram test skips visibly; ``everything`` then compares the DOT text only)
            assert rendered["error"]["code"] == "RENDERER_UNAVAILABLE", rendered
        else:
            assert status == 200, (status, rendered)
            svg = mask(base64.b64decode(rendered["data"]).decode("utf-8"))
            assert "<svg" in svg and len(svg) > 200, "the rendered diagram is not an SVG"
        return {"dot": dot, "renderStatus": status, "svg": svg}

    def analysis(self):
        out = {}
        for name, method, url, payload in (("summary", "GET", "/api/analysis/summary", None),
                                           ("cutsets", "POST", "/api/analysis/cutsets", {}),
                                           ("importance", "POST", "/api/analysis/importance", {})):
            status, body = self.api.call(method, url, **({"json": payload} if payload is not None else {}))
            assert status == 200, (url, body)
            out[name] = W.M.strip_keys(body)
        return out

    def csv(self, path):
        from fta_web import cli

        out = {}
        for command in ("quantify", "cutsets", "importance"):
            code = cli.main([command, str(path), "--csv"])
            captured = self.capsys.readouterr()
            assert code == 0, (command, captured.err)
            out[command] = captured.out.encode("utf-8")
        return out

    def everything(self):
        saved = self.save_bytes()
        return {
            "save": saved,
            "exportJson": self.export("json"),
            "exportXml": self.export("xml"),
            "exportXlsxCells": self.xlsx_cells(),
            "docxText": self.docx_text(),
            "diagram": self.diagram(),
            "analysis": self.analysis(),
            "aiContext": self.ai_context(),
            "csv": self.csv(self.api.root / "doc.json"),
        }


@pytest.fixture
def outputs(api, tmp_path, capsys, monkeypatch):
    api.open_doc(W.r1_doc())
    api.edit("C", name="Sensor C, checked")  # a modified document (can undo, dirty), as a user's is
    return Outputs(api, tmp_path, capsys, monkeypatch)


def factor_is_active(api, factors=None):
    """Call the endpoint with a factor 10 and prove the factor did something."""
    body = api.whatif_ok(factors or {"A": 10})
    assert body["whatIf"] != body["baseline"]
    return body


def assert_same(before, after):
    assert set(before) == set(after)
    for key in before:
        assert after[key] == before[key], "%s changed while a factor was active" % key


# ------------------------------------------------------------- the guards


def test_the_capture_is_repeatable_without_any_what_if_call(outputs):
    first = outputs.everything()
    second = outputs.everything()
    assert_same(first, second)


def test_the_capture_notices_a_real_edit(outputs):
    """If this fails the comparison in the other tests proves nothing."""
    first = outputs.everything()
    outputs.api.edit("C", probability=0.5)
    second = outputs.everything()
    for key in ("save", "exportJson", "exportXml", "exportXlsxCells", "docxText", "diagram",
                "analysis", "aiContext", "csv"):
        assert second[key] != first[key], "an edit left %s unchanged" % key


# ------------------------------------------------------------- FN-53 proper


def test_every_output_is_the_same_with_factor_10_active(outputs):
    before = outputs.everything()
    body = factor_is_active(outputs.api)
    assert body["whatIf"] == W.rel(W.R1_F10, 1e-9)
    after = outputs.everything()
    assert_same(before, after)
    factor_is_active(outputs.api, {"A": 100})  # a second call (a cache hit), still nothing leaks
    assert_same(before, outputs.everything())


def test_save_is_byte_identical_and_holds_no_what_if_value(outputs):
    before = outputs.save_bytes()
    factor_is_active(outputs.api)
    after = outputs.save_bytes()
    assert after == before
    text = after.decode("utf-8")
    assert "whatif" not in text.lower() and "factor" not in text.lower()
    saved = json.loads(text)
    node_a = next(n for n in _walk(saved["tree"]) if n["id"] == "A")
    assert node_a["probability"] == W.rel(1e-3, 1e-12)


def test_save_as_another_file_is_the_same_bytes_too(outputs):
    before = outputs.save_bytes()
    factor_is_active(outputs.api)
    target = outputs.api.root / "copy.json"
    status, body = outputs.api.post("/api/file/save-as", {"path": str(target)})
    assert status == 200, body
    assert target.read_bytes() == before


def test_recovery_copy_is_byte_identical(outputs):
    from fta_web import recovery

    session = recovery.start(background=False)
    assert session
    copy_file = recovery.directory() / (session + ".json")
    assert recovery.flush() is True           # the document is modified: a copy exists
    before = copy_file.read_bytes()
    factor_is_active(outputs.api)
    assert recovery.flush() is True           # written again, after the call
    after = copy_file.read_bytes()
    assert after == before
    assert b"whatif" not in after.lower()


def test_json_and_xml_exports_are_byte_identical(outputs):
    before = (outputs.export("json"), outputs.export("xml"))
    factor_is_active(outputs.api)
    assert (outputs.export("json"), outputs.export("xml")) == before


def test_excel_cell_values_are_equal(outputs):
    before = outputs.xlsx_cells()
    assert before, "the workbook is empty"
    factor_is_active(outputs.api)
    assert outputs.xlsx_cells() == before


def test_docx_text_is_equal(outputs):
    before = outputs.docx_text()
    assert "Top-event probability" in before
    factor_is_active(outputs.api)
    assert outputs.docx_text() == before


def test_the_diagram_dot_and_svg_are_equal(outputs):
    before = outputs.diagram()
    if before["renderStatus"] == 503:
        pytest.skip("RENDERER_UNAVAILABLE: no diagram renderer on this machine, the SVG of the "
                    "diagram is not compared (the DOT text is, in the capture of the other tests)")
    assert before["renderStatus"] == 200 and before["svg"].lstrip().startswith(("<?xml", "<svg"))
    factor_is_active(outputs.api)
    after = outputs.diagram()
    assert after["dot"] == before["dot"]
    assert after["renderStatus"] == before["renderStatus"] == 200
    assert after["svg"] and after["svg"] == before["svg"]
    assert "1.080919e-03" not in json.dumps(after["dot"]) and "1.08e-3" not in json.dumps(after["dot"])


def test_the_ai_context_text_is_equal(outputs):
    before = outputs.ai_context()
    factor_is_active(outputs.api)
    after = outputs.ai_context()
    assert after == before
    assert "1.08" not in after.replace("1.08.", "")  # the what-if top event 1.08e-3 is not in it


def test_csv_and_events_csv_are_byte_identical(outputs):
    outputs.save_bytes()
    path = outputs.api.root / "doc.json"
    before = outputs.csv(path)
    assert all(before.values()), "an empty CSV proves nothing"
    factor_is_active(outputs.api)
    outputs.save_bytes()
    assert outputs.csv(path) == before


def test_the_results_the_tabs_build_their_csv_from_are_equal(outputs):
    before = outputs.analysis()
    factor_is_active(outputs.api)
    assert outputs.analysis() == before


def test_can_undo_dirty_revision_and_snapshot_are_unchanged(outputs):
    before = W.fingerprint()
    assert before["canUndo"] is True and before["dirty"] is True
    factor_is_active(outputs.api)
    after = W.fingerprint()
    assert after == before
    fields = outputs.api.fields()
    assert fields["revision"] == before["revision"] and fields["documentSerial"] == before["documentSerial"]


def test_a_saved_document_stays_saved(outputs):
    outputs.save_bytes()
    before = W.fingerprint()
    assert before["dirty"] is False
    factor_is_active(outputs.api)
    assert W.fingerprint() == before


def _walk(node):
    yield node
    for child in node.get("children") or []:
        yield from _walk(child)
