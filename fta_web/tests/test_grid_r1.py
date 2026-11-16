"""F3 polish round R1: the Japanese text of STALE_REVISION and the failed-paste sentence.

* STALE_REVISION (a stale ``POST /api/grid/paste``) has a Japanese message from the server, the
  same words as ``grid.summary.stale`` in the Grid tab's own catalog (static/js/i18n/grid.js).
* ``endSentence`` (static/js/tabs/grid_paste.js) closes the error that is joined into
  "The paste failed: {error} Nothing was applied." (run under Node, like the other JS tests).
* The browser checks of the cell-error box, the ETA text and the hint are in
  tests/gui/s_gridr1.js (``node tests/gui/run.mjs gridr1``).
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from fta_web import i18n  # noqa: E402

GRID_CATALOG = REPO / "fta_web" / "static" / "js" / "i18n" / "grid.js"
GRID_PASTE = REPO / "fta_web" / "static" / "js" / "tabs" / "grid_paste.js"

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def catalog_text(lang, key):
    """The text of ``key`` in the ``lang`` block of the Grid catalog (a flat, single-quoted file)."""
    source = GRID_CATALOG.read_text(encoding="utf-8")
    block = source.split("  %s: {" % lang, 1)[1]
    if lang == "en":
        block = block.split("  ja: {", 1)[0]
    match = re.search(r"^\s*'%s': '((?:[^'\\]|\\.)*)',\s*$" % re.escape(key), block, re.M)
    assert match, "%s (%s) is not in the Grid catalog" % (key, lang)
    return match.group(1).replace("\\'", "'")


def test_the_catalog_reader_finds_both_languages():
    assert catalog_text("en", "grid.summary.stale") == "The analysis changed; paste again"
    assert catalog_text("ja", "grid.summary.stale").startswith("解析が変更されました")


def test_stale_revision_has_a_japanese_message():
    ja = catalog_text("ja", "grid.summary.stale")
    err = {"ok": False, "error": {"code": "STALE_REVISION", "message": "The analysis changed; paste again",
                                  "detail": {"revision": 3, "documentSerial": 1}}}
    out = i18n.localize_error(err, "ja")
    assert out["error"]["message"] == ja
    assert out["error"]["code"] == "STALE_REVISION"
    assert out["error"]["detail"] == {"revision": 3, "documentSerial": 1}  # never touched
    assert i18n.localize_error(err, "en")["error"]["message"] == "The analysis changed; paste again"


def test_the_server_answers_a_stale_paste_in_japanese_with_lang_ja():
    pytest.importorskip("flask")
    from fta_web.app import create_app
    from fta_web.state import reset_state

    reset_state()
    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as client:
        now = client.get("/api/revision").get_json()
        body = {"revision": now["revision"] + 1, "documentSerial": now["documentSerial"], "rows": []}
        en = client.post("/api/grid/paste", json=body)
        ja = client.post("/api/grid/paste?lang=ja", json=body)
        ja_header = client.post("/api/grid/paste", json=body, headers={"Accept-Language": "ja"})
    assert en.status_code == ja.status_code == ja_header.status_code == 409
    en_error = en.get_json()["error"]
    assert en_error["code"] == "STALE_REVISION"
    assert en_error["message"] == catalog_text("en", "grid.summary.stale")
    for response in (ja, ja_header):
        error = response.get_json()["error"]
        assert error["code"] == "STALE_REVISION"
        assert error["message"] == catalog_text("ja", "grid.summary.stale")
        assert error["detail"] == en_error["detail"]


def _end_sentence(cases):
    script = (
        "import { endSentence } from %s;\n" % json.dumps(GRID_PASTE.as_uri())
        + "const input = %s;\n" % json.dumps(cases)
        + "console.log(JSON.stringify(input.map(([text, lang]) => endSentence(text, lang))));\n"
    )
    out = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True,
                         text=True, encoding="utf-8", check=True, timeout=60).stdout
    return json.loads(out)


@needs_node
def test_end_sentence_keeps_ending_punctuation_and_adds_a_full_stop_otherwise():
    cases = [
        ("Disk is full", "en"), ("Disk is full.", "en"), ("Disk is full!", "en"), ("Disk is full?", "en"),
        ("Disk is full...", "en"), ("Disk is full…", "en"), ("Could not save (see log.)", "en"), ("  padded  ", "en"),
        ("ディスクがいっぱいです", "ja"), ("ディスクがいっぱいです。", "ja"), ("ディスクがいっぱいです！", "ja"),
        ("ディスクがいっぱいです？", "ja"), ("「失敗」", "ja"), ("Disk is full", "ja"),
        ("", "en"), (None, "ja"),
    ]
    assert _end_sentence(cases) == [
        "Disk is full.", "Disk is full.", "Disk is full!", "Disk is full?",
        "Disk is full...", "Disk is full…", "Could not save (see log.)", "padded.",
        "ディスクがいっぱいです。", "ディスクがいっぱいです。", "ディスクがいっぱいです！",
        "ディスクがいっぱいです？", "「失敗」。", "Disk is full。",
        "", "",
    ]


@needs_node
def test_the_joined_failed_sentence_reads_correctly_in_both_languages():
    """The catalog templates are unchanged; the code closes {error} before it is joined in."""
    en = catalog_text("en", "grid.summary.failed")
    ja = catalog_text("ja", "grid.summary.failed")
    assert en == "The paste failed: {error} Nothing was applied."
    assert ja == "貼り付けに失敗しました: {error} 何も適用されていません。"
    closed = _end_sentence([("Network error", "en"), ("Network error", "ja")])
    assert en.replace("{error}", closed[0]) == "The paste failed: Network error. Nothing was applied."
    assert ja.replace("{error}", closed[1]) == "貼り付けに失敗しました: Network error。 何も適用されていません。"
