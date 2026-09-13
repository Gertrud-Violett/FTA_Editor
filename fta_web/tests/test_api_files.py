"""
Tests for the file and export backend: fta_web/fsbrowser.py and the
``/api/fs``, ``/api/file``, ``/api/export`` and ``/api/import`` endpoints.

Three things shape this suite.

**The sandbox root is always a fresh ``tmp_path``.** Never the real home
directory, which is what ``config.DEFAULT_FS_ROOT`` points at: a bug in these
endpoints -- or in a test -- would otherwise be exercised against the
developer's actual files. The root is a *subdirectory* of ``tmp_path`` so that
``tmp_path`` itself is a legitimate "outside the sandbox" location to point
attacks at.

**The security tests assert on the error code, not on the message.**
``PATH_REJECTED`` is the contract; the wording is not. What the messages are
checked for is the opposite property -- that they do *not* contain anything
about the filesystem outside the root, because a rejection that says where a
symlink pointed is an oracle for probing the host.

**Excel absence is simulated two different ways.** ``openpyxl`` is installed
here, so the interesting path -- a user who never ran ``pip install
openpyxl`` -- only exists under monkeypatch: once by making the capability
probe fail, and once by making the import itself fail underneath the vendored
exporter, which is the case that would otherwise surface as a raw traceback
string.
"""
import io
import json
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# conftest.py put fta_web/core on sys.path, so the vendored core imports under
# its bare name -- exactly as fta_web/routes/files.py imports it.
from FTA_Editor_core import FTACore  # noqa: E402

from fta_web import fsbrowser  # noqa: E402
from fta_web.routes.files import EXCEL_MISSING_MESSAGE, files_bp  # noqa: E402
from fta_web.routes.tree import tree_bp  # noqa: E402
from fta_web.state import get_state, reset_state  # noqa: E402

TREE = {
    "id": "root",
    "name": "Top event",
    "type": "Root",
    "probability": 1.0,
    "logicGate": "OR",
    "notes": "",
    "links": [],
    "children": [
        {
            "id": "root_0",
            "name": "Seal leak",
            "type": "Event",
            "probability": 0.5,
            "logicGate": "OR",
            "notes": "check quarterly",
            "links": [],
            "children": [],
        },
        {
            "id": "root_1",
            "name": "Bearing seizure",
            "type": "Event",
            "probability": 0.0,
            "logicGate": "OR",
            "notes": "",
            "links": [],
            "children": [],
        },
    ],
}

DOCUMENT = {"title": "Pump failure", "date": "2026-01-31", "mode": "FTA", "tree": TREE}


# --------------------------------------------------------------------------
# fixtures and helpers
# --------------------------------------------------------------------------


@pytest.fixture
def sandbox(tmp_path):
    """The sandbox root, with somewhere outside it to point attacks at."""
    root = tmp_path / "sandbox"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.json").write_text(
        dumps({"title": "not yours", "tree": TREE}), encoding="utf-8"
    )
    return root


@pytest.fixture
def client(sandbox):
    """A bare Flask app with the file and tree blueprints, no security layer.

    The blueprints are registered *before* ``fs_root`` is set: registering
    ``files_bp`` copies ``app.config["FTA_FS_ROOT"]`` onto the state when the
    app has one, which would otherwise stamp the real home directory back over
    the sandbox.
    """
    flask = pytest.importorskip("flask")

    reset_state()
    app = flask.Flask(__name__)
    app.register_blueprint(files_bp)
    app.register_blueprint(tree_bp)
    app.config.update(TESTING=True)

    get_state().fs_root = sandbox
    with app.test_client() as test_client:
        yield test_client


def body(response):
    return json.loads(response.get_data(as_text=True))


def post(client, path, payload=None):
    return client.post(path, json={} if payload is None else payload)


def dumps(document):
    """Serialize a test document the way the editor itself writes one.

    ``indent=2`` matches what ``save_to_json`` writes, so fixtures look like
    real editor files. It used to matter for a second reason: at baseline the
    loader stripped a brace from anything ending ``}}``, which mangled every
    minified document. Divergence D8 fixed that -- see
    ``test_minified_json_opens`` below.
    """
    return json.dumps(document, ensure_ascii=False, indent=2)


def write_document(directory, name="analysis.json", document=None):
    path = Path(directory) / name
    path.write_text(dumps(DOCUMENT if document is None else document), encoding="utf-8")
    return path


def assert_rejected(response, reason=None, status=None):
    """The response is the documented PATH_REJECTED envelope."""
    payload = body(response)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "PATH_REJECTED", payload
    if reason is not None:
        assert payload["error"]["detail"]["reason"] == reason, payload
    if status is not None:
        assert response.status_code == status
    return payload


def temp_files(prefix):
    return set(Path(tempfile.gettempdir()).glob(prefix + "*"))


# --------------------------------------------------------------------------
# fs browsing
# --------------------------------------------------------------------------


def test_home_reports_the_sandbox_root(client, sandbox):
    payload = body(client.get("/api/fs/home"))
    assert payload["ok"] is True
    assert payload["root"] == str(sandbox)
    assert payload["cwd"] == str(sandbox)


def test_home_follows_the_open_document(client, sandbox):
    nested = sandbox / "project"
    nested.mkdir()
    target = write_document(nested)

    assert post(client, "/api/file/open", {"path": str(target)}).status_code == 200
    payload = body(client.get("/api/fs/home"))
    assert payload["cwd"] == str(nested)
    assert payload["root"] == str(sandbox)


def test_list_root_has_no_parent(client, sandbox):
    (sandbox / "sub").mkdir()
    write_document(sandbox)

    payload = body(client.get("/api/fs/list"))
    assert payload["ok"] is True
    assert payload["path"] == str(sandbox)
    # None at the root: the picker gets no way to climb out of the sandbox.
    assert payload["parent"] is None
    assert [d["name"] for d in payload["dirs"]] == ["sub"]
    assert [f["name"] for f in payload["files"]] == ["analysis.json"]
    assert payload["truncated"] is False


def test_list_subdirectory_reports_its_parent(client, sandbox):
    nested = sandbox / "sub"
    nested.mkdir()

    payload = body(client.get("/api/fs/list", query_string={"path": str(nested)}))
    assert payload["path"] == str(nested)
    assert payload["parent"] == str(sandbox)


def test_list_returns_size_and_modified_for_files(client, sandbox):
    target = write_document(sandbox)

    entry = body(client.get("/api/fs/list"))["files"][0]
    assert entry["path"] == str(target)
    assert entry["size"] == target.stat().st_size
    # A string the frontend can print, and a machine can parse back.
    assert datetime.fromisoformat(entry["modified"])


def test_list_hides_unopenable_files_and_dotfiles(client, sandbox):
    write_document(sandbox)
    (sandbox / "notes.txt").write_text("x", encoding="utf-8")
    (sandbox / "sheet.xlsx").write_bytes(b"x")
    (sandbox / ".hidden.json").write_text("{}", encoding="utf-8")
    (sandbox / ".config").mkdir()

    payload = body(client.get("/api/fs/list"))
    assert [f["name"] for f in payload["files"]] == ["analysis.json"]
    assert payload["dirs"] == []


def test_list_of_a_missing_directory_is_rejected(client, sandbox):
    response = client.get(
        "/api/fs/list", query_string={"path": str(sandbox / "nope")}
    )
    assert_rejected(response, reason="not_a_directory", status=404)


# --------------------------------------------------------------------------
# security
# --------------------------------------------------------------------------


def test_traversal_out_of_the_root_is_rejected(client, sandbox):
    response = post(
        client, "/api/file/open", {"path": str(sandbox / ".." / "outside" / "secret.json")}
    )
    assert_rejected(response, reason="traversal", status=400)


def test_relative_traversal_is_rejected(client):
    assert_rejected(
        post(client, "/api/file/open", {"path": "../outside/secret.json"}),
        reason="traversal",
    )


def test_absolute_path_outside_the_root_is_rejected(client, sandbox):
    outside = sandbox.parent / "outside" / "secret.json"
    assert outside.is_file()  # the file really is there; the sandbox is why it fails

    response = post(client, "/api/file/open", {"path": str(outside)})
    assert_rejected(response, reason="outside_root", status=400)


def test_symlink_pointing_out_of_the_root_is_rejected(client, sandbox):
    """Resolve first, then confine: the target is what has to be inside."""
    secret = sandbox.parent / "outside" / "secret.json"
    link = sandbox / "innocent.json"
    link.symlink_to(secret)
    assert link.is_file()  # it opens fine as far as the OS is concerned

    response = post(client, "/api/file/open", {"path": str(link)})
    payload = assert_rejected(response, reason="outside_root", status=400)

    # The rejection must not disclose where the link pointed, or the sandbox
    # becomes an oracle for probing the rest of the filesystem.
    text = json.dumps(payload)
    assert str(secret) not in text
    assert "secret" not in text
    assert "not yours" not in text


def test_symlinked_directory_out_of_the_root_is_rejected(client, sandbox):
    link = sandbox / "elsewhere"
    link.symlink_to(sandbox.parent / "outside", target_is_directory=True)

    response = client.get("/api/fs/list", query_string={"path": str(link)})
    assert_rejected(response, reason="outside_root")


def test_escaping_symlinks_are_not_even_listed(client, sandbox):
    (sandbox / "innocent.json").symlink_to(sandbox.parent / "outside" / "secret.json")
    (sandbox / "elsewhere").symlink_to(
        sandbox.parent / "outside", target_is_directory=True
    )
    write_document(sandbox)

    payload = body(client.get("/api/fs/list"))
    assert [f["name"] for f in payload["files"]] == ["analysis.json"]
    assert payload["dirs"] == []


def test_symlink_staying_inside_the_root_is_allowed(client, sandbox):
    """The rule is containment, not "no symlinks"."""
    real = write_document(sandbox, "real.json")
    (sandbox / "alias.json").symlink_to(real)

    response = post(client, "/api/file/open", {"path": str(sandbox / "alias.json")})
    assert response.status_code == 200
    assert body(response)["metadata"]["title"] == "Pump failure"


def test_nul_byte_in_a_path_is_rejected(client, sandbox):
    response = post(
        client, "/api/file/open", {"path": str(sandbox / "analysis.json") + "\x00.png"}
    )
    assert_rejected(response, reason="nul_byte", status=400)


def test_nul_byte_is_rejected_on_write_too(client, sandbox):
    response = post(
        client, "/api/file/save-as", {"path": str(sandbox / "out.json\x00.exe")}
    )
    assert_rejected(response, reason="nul_byte")


def test_disallowed_write_extension_is_rejected(client, sandbox):
    response = post(client, "/api/file/save-as", {"path": str(sandbox / "payload.exe")})
    assert_rejected(response, reason="extension", status=400)
    assert not (sandbox / "payload.exe").exists()


def test_save_as_refuses_a_writable_but_wrong_extension(client, sandbox):
    """.xml is in ALLOWED_WRITE_EXTENSIONS, but Save As writes JSON."""
    response = post(client, "/api/file/save-as", {"path": str(sandbox / "tree.xml")})
    assert_rejected(response, reason="extension")
    assert not (sandbox / "tree.xml").exists()


def test_disallowed_open_extension_is_rejected(client, sandbox):
    (sandbox / "notes.txt").write_text("{}", encoding="utf-8")
    response = post(client, "/api/file/open", {"path": str(sandbox / "notes.txt")})
    assert_rejected(response, reason="extension")


def test_save_as_into_a_missing_directory_is_rejected(client, sandbox):
    response = post(
        client, "/api/file/save-as", {"path": str(sandbox / "nope" / "a.json")}
    )
    assert_rejected(response, reason="parent_missing", status=404)


def test_opening_a_directory_is_rejected(client, sandbox):
    directory = sandbox / "folder.json"
    directory.mkdir()
    response = post(client, "/api/file/open", {"path": str(directory)})
    assert_rejected(response, reason="not_a_file")


def test_missing_file_is_reported_as_not_found(client, sandbox):
    response = post(client, "/api/file/open", {"path": str(sandbox / "gone.json")})
    assert_rejected(response, reason="not_found", status=404)


def test_path_must_be_a_string(client):
    assert_rejected(post(client, "/api/file/open", {"path": 17}), reason="not_a_string")
    assert_rejected(post(client, "/api/file/open", {"path": "   "}), reason="empty")


def test_path_is_required(client):
    payload = body(post(client, "/api/file/open", {}))
    assert payload["error"]["code"] == "INVALID_FIELD"


def test_oversized_file_is_refused_before_it_is_read(client, sandbox, monkeypatch):
    monkeypatch.setattr(fsbrowser, "MAX_OPEN_BYTES", 10)
    write_document(sandbox)
    response = post(client, "/api/file/open", {"path": str(sandbox / "analysis.json")})
    assert_rejected(response, reason="too_large", status=413)


# --------------------------------------------------------------------------
# open / save round trip
# --------------------------------------------------------------------------


def test_open_returns_the_whole_document(client, sandbox):
    target = write_document(sandbox)

    payload = body(post(client, "/api/file/open", {"path": str(target)}))
    assert payload["ok"] is True
    assert payload["currentPath"] == str(target)
    assert payload["dirty"] is False
    assert payload["canUndo"] is False
    assert payload["canRedo"] is False
    assert payload["metadata"] == {
        "title": "Pump failure",
        "date": "2026-01-31",
        "mode": "FTA",
    }
    assert payload["tree"]["name"] == "Top event"
    assert [c["name"] for c in payload["tree"]["children"]] == [
        "Seal leak",
        "Bearing seizure",
    ]
    # Probabilities are recalculated on load, so the client never renders a
    # stale calculatedProbability that came off disk.
    assert payload["tree"]["calculatedProbability"] == pytest.approx(0.5)
    assert "root_1" in payload["zeroNodes"]


def test_open_clears_the_undo_stack(client, sandbox):
    target = write_document(sandbox)

    created = post(client, "/api/nodes", {"parentId": "root", "name": "Scratch"})
    assert body(created)["canUndo"] is True

    payload = body(post(client, "/api/file/open", {"path": str(target)}))
    assert payload["canUndo"] is False
    assert body(post(client, "/api/undo")) ["error"]["code"] == "NOTHING_TO_UNDO"


def test_open_leaves_the_document_untouched_when_the_file_is_bad(client, sandbox):
    good = write_document(sandbox)
    assert post(client, "/api/file/open", {"path": str(good)}).status_code == 200

    bad = sandbox / "broken.json"
    bad.write_text("this is not JSON", encoding="utf-8")
    response = post(client, "/api/file/open", {"path": str(bad)})
    assert response.status_code == 400
    assert body(response)["error"]["code"] == "INVALID_JSON"

    # Still the previously opened analysis, not a half-loaded one.
    state = body(client.get("/api/state"))
    assert state["metadata"]["title"] == "Pump failure"
    assert state["currentPath"] == str(good)


def test_save_without_a_path_is_a_conflict(client):
    response = post(client, "/api/file/save")
    assert response.status_code == 409
    assert body(response)["error"]["code"] == "NO_CURRENT_PATH"


def test_save_as_then_save_round_trips(client, sandbox):
    target = sandbox / "saved.json"

    saved = body(post(client, "/api/file/save-as", {"path": str(target)}))
    assert saved == {"ok": True, "currentPath": str(target), "dirty": False}
    on_disk = json.loads(target.read_text(encoding="utf-8"))
    assert set(on_disk) == {"title", "date", "mode", "tree"}

    # Edit, save to the same path, reopen: the edit is on disk.
    post(client, "/api/metadata", {"title": "Renamed"})
    post(client, "/api/nodes", {"parentId": "root", "name": "Added event",
                                "probability": 0.25})
    assert body(client.get("/api/state"))["dirty"] is True

    saved_again = body(post(client, "/api/file/save"))
    assert saved_again == {"ok": True, "currentPath": str(target), "dirty": False}

    reopened = body(post(client, "/api/file/open", {"path": str(target)}))
    assert reopened["metadata"]["title"] == "Renamed"
    assert [c["name"] for c in reopened["tree"]["children"]] == ["Added event"]
    assert reopened["dirty"] is False


def test_save_overwrites_atomically_and_leaves_no_temp_files(client, sandbox):
    target = write_document(sandbox)
    post(client, "/api/file/open", {"path": str(target)})
    post(client, "/api/metadata", {"title": "Second version"})
    post(client, "/api/file/save")

    assert json.loads(target.read_text(encoding="utf-8"))["title"] == "Second version"
    # The temp file the atomic write used is gone, and nothing else appeared.
    assert sorted(p.name for p in sandbox.iterdir()) == ["analysis.json"]


def test_save_keeps_the_permissions_of_the_file_it_replaces(client, sandbox):
    target = write_document(sandbox)
    target.chmod(0o640)
    post(client, "/api/file/open", {"path": str(target)})
    post(client, "/api/file/save")

    assert target.stat().st_mode & 0o777 == 0o640


def test_saved_file_reloads_in_the_vendored_core(client, sandbox):
    """What we write is what the desktop editor reads."""
    target = sandbox / "interop.json"
    post(client, "/api/metadata", {"title": "Interop", "mode": "ETA"})
    post(client, "/api/file/save-as", {"path": str(target)})

    core = FTACore()
    ok, error = core.load_from_json(str(target))
    assert (ok, error) == (True, None)
    assert core.title == "Interop"
    assert core.mode == "ETA"


# --------------------------------------------------------------------------
# legacy input formats (all handled by the vendored loader)
# --------------------------------------------------------------------------


def test_open_accepts_a_legacy_bare_tree(client, sandbox):
    target = sandbox / "legacy.json"
    target.write_text(dumps(TREE), encoding="utf-8")

    payload = body(post(client, "/api/file/open", {"path": str(target)}))
    assert payload["tree"]["name"] == "Top event"
    # No metadata in the file, so the loader supplies its defaults.
    assert payload["metadata"]["title"] == "Untitled Analysis"
    assert payload["metadata"]["mode"] == "FTA"


def test_open_accepts_the_fta_wrapper(client, sandbox):
    target = sandbox / "wrapped.json"
    target.write_text(dumps({"FTA": TREE}), encoding="utf-8")

    payload = body(post(client, "/api/file/open", {"path": str(target)}))
    assert payload["tree"]["name"] == "Top event"


def test_open_accepts_double_brace_wrapped_json(client, sandbox):
    target = sandbox / "doubled.json"
    inner = dumps(DOCUMENT)
    target.write_text("{" + inner + "}", encoding="utf-8")

    payload = body(post(client, "/api/file/open", {"path": str(target)}))
    assert payload["metadata"]["title"] == "Pump failure"


def test_minified_json_opens(client, sandbox):
    """Divergence D8: minified documents load.

    At baseline ``load_from_json`` applied its double-brace repair before
    attempting a parse, and ``content.endswith("}}")`` matches every minified
    analysis -- the tree's closing brace followed by the document's. Stripping a
    brace produced invalid JSON, and the encoding-retry loop then reported
    "Failed to read file with common encodings", naming the wrong cause.

    D8 parses the document as written first and falls back to the repair only on
    failure, so this interchange case works while the legacy path survives.
    """
    target = sandbox / "minified.json"
    minified = json.dumps(DOCUMENT)
    assert minified.endswith("}}"), "fixture must reproduce the shape that used to fail"
    target.write_text(minified, encoding="utf-8")

    payload = body(post(client, "/api/file/open", {"path": str(target)}))
    assert payload["metadata"]["title"] == "Pump failure"

    # Indented is unchanged, and the two agree.
    target.write_text(dumps(DOCUMENT), encoding="utf-8")
    indented = body(post(client, "/api/file/open", {"path": str(target)}))
    assert indented["tree"] == payload["tree"]


def test_double_wrapped_json_still_opens(client, sandbox):
    """D8 kept the legacy repair reachable for the files it was added for."""
    target = sandbox / "wrapped.json"
    target.write_text("{" + dumps(DOCUMENT) + "}", encoding="utf-8")

    payload = body(post(client, "/api/file/open", {"path": str(target)}))
    assert payload["metadata"]["title"] == "Pump failure"


def test_malformed_json_is_still_rejected(client, sandbox):
    """D8 must not turn the repair into a way to accept broken files."""
    target = sandbox / "broken.json"
    target.write_text('{"title": "x", ', encoding="utf-8")

    response = post(client, "/api/file/open", {"path": str(target)})
    assert response.status_code == 400


def test_open_accepts_a_utf8_bom(client, sandbox):
    target = sandbox / "bom.json"
    target.write_text(dumps(DOCUMENT), encoding="utf-8-sig")

    payload = body(post(client, "/api/file/open", {"path": str(target)}))
    assert payload["metadata"]["title"] == "Pump failure"


@pytest.mark.parametrize("encoding", ["cp932", "shift_jis"])
def test_open_accepts_japanese_legacy_encodings(client, sandbox, encoding):
    document = json.loads(json.dumps(DOCUMENT))
    document["title"] = "ポンプ故障"
    document["tree"]["name"] = "頂上事象"
    target = sandbox / ("japanese_%s.json" % encoding)
    target.write_bytes(dumps(document).encode(encoding))

    payload = body(post(client, "/api/file/open", {"path": str(target)}))
    assert payload["metadata"]["title"] == "ポンプ故障"
    assert payload["tree"]["name"] == "頂上事象"


def test_open_accepts_the_vendored_sample(client, sandbox, sample_fta_path):
    target = sandbox / "sampleFTA.json"
    target.write_bytes(sample_fta_path.read_bytes())

    payload = body(post(client, "/api/file/open", {"path": str(target)}))
    assert payload["ok"] is True
    assert payload["metadata"]["title"] == "sampleFTA"


# --------------------------------------------------------------------------
# exports
# --------------------------------------------------------------------------


@pytest.fixture
def opened(client, sandbox):
    """A client with the sample document open, for the export tests."""
    target = write_document(sandbox)
    assert post(client, "/api/file/open", {"path": str(target)}).status_code == 200
    return client


def test_export_json_downloads_a_parseable_document(opened):
    response = opened.get("/api/export/json")
    assert response.status_code == 200
    assert response.mimetype == "application/json"
    assert "attachment" in response.headers["Content-Disposition"]
    assert "analysis.json" in response.headers["Content-Disposition"]

    payload = json.loads(response.get_data(as_text=True))
    assert payload["title"] == "Pump failure"
    assert payload["tree"]["name"] == "Top event"


def test_export_xml_downloads_parseable_xml(opened):
    response = opened.get("/api/export/xml")
    assert response.status_code == 200
    assert response.mimetype == "application/xml"
    assert "attachment" in response.headers["Content-Disposition"]
    assert "analysis.xml" in response.headers["Content-Disposition"]

    root = ET.fromstring(response.get_data())
    assert root.tag == "FaultTree"
    top = root.find("Node")
    assert top.get("name") == "Top event"
    assert [n.get("name") for n in top.findall("Node")] == [
        "Seal leak",
        "Bearing seizure",
    ]


def test_export_xlsx_downloads_a_readable_workbook(opened):
    openpyxl = pytest.importorskip("openpyxl")

    response = opened.get("/api/export/xlsx")
    assert response.status_code == 200
    assert response.mimetype == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert "analysis.xlsx" in response.headers["Content-Disposition"]

    workbook = openpyxl.load_workbook(io.BytesIO(response.get_data()))
    sheet = workbook["FTA"]
    assert "Top event" in sheet["A1"].value
    assert "Seal leak" in sheet["B1"].value


def test_export_names_the_download_after_the_title_when_unsaved(client):
    post(client, "/api/metadata", {"title": "Untitled Analysis"})
    disposition = client.get("/api/export/json").headers["Content-Disposition"]
    assert "Untitled Analysis.json" in disposition


def test_export_leaves_no_temp_files_behind(opened):
    before = temp_files("fta_export_")
    for fmt in ("json", "xml", "xlsx"):
        assert opened.get("/api/export/%s" % fmt).status_code == 200
    assert temp_files("fta_export_") == before


def test_failed_export_leaves_no_temp_files_behind(opened, monkeypatch):
    monkeypatch.setattr(
        FTACore, "export_to_xml", lambda self, path: (False, "disk on fire")
    )
    before = temp_files("fta_export_")
    response = opened.get("/api/export/xml")

    assert response.status_code == 500
    assert body(response)["error"]["code"] == "EXPORT_UNAVAILABLE"
    assert temp_files("fta_export_") == before


def test_unknown_export_format_is_a_404(opened):
    response = opened.get("/api/export/pdf")
    assert response.status_code == 404
    assert body(response)["error"]["code"] == "INVALID_FIELD"


def test_export_does_not_adopt_the_temp_file_as_the_current_path(opened, sandbox):
    """save_to_json() records the file it wrote; an export must not keep that."""
    assert opened.get("/api/export/json").status_code == 200

    state = get_state()
    assert state.core.last_saved_file == str(sandbox / "analysis.json")
    assert body(opened.get("/api/state"))["currentPath"] == str(sandbox / "analysis.json")


# --------------------------------------------------------------------------
# Excel export without openpyxl
# --------------------------------------------------------------------------


def assert_excel_missing(response):
    payload = body(response)
    assert response.status_code == 503
    assert payload["error"]["code"] == "EXPORT_UNAVAILABLE"
    message = payload["error"]["message"]
    assert message == EXCEL_MISSING_MESSAGE
    # The whole point: a remedy, not a traceback.
    assert "pip install openpyxl" in message
    assert "Traceback" not in message
    assert payload["error"]["detail"]["install"] == "pip install openpyxl"
    return payload


def test_xlsx_export_without_openpyxl_explains_how_to_install_it(opened, monkeypatch):
    """The capability probe cannot find openpyxl at all."""
    import importlib.util as importlib_util

    real_find_spec = importlib_util.find_spec

    def missing(name, *args, **kwargs):
        if name == "openpyxl":
            return None
        return real_find_spec(name, *args, **kwargs)

    monkeypatch.setattr(importlib_util, "find_spec", missing)
    assert_excel_missing(opened.get("/api/export/xlsx"))


def test_xlsx_export_with_an_unimportable_openpyxl(opened, monkeypatch):
    """openpyxl is on the path but importing it fails.

    ``sys.modules["openpyxl"] = None`` is how the import system spells "this
    module is not available": every ``import openpyxl`` below raises. Without
    the request-time probe the vendored exporter would swallow that into
    ``"Failed to export Excel: import of openpyxl halted..."`` and the user
    would be told nothing they could act on.
    """
    monkeypatch.setitem(sys.modules, "openpyxl", None)
    assert_excel_missing(opened.get("/api/export/xlsx"))


def test_xlsx_export_when_openpyxl_breaks_on_use(opened, monkeypatch):
    """Importable, but broken -- the exporter's own error still gets mapped."""
    monkeypatch.setattr(
        FTACore,
        "export_to_excel",
        lambda self, path: (False, "Failed to export Excel: No module named 'openpyxl.styles'"),
    )
    assert_excel_missing(opened.get("/api/export/xlsx"))


def test_json_and_xml_still_work_without_openpyxl(opened, monkeypatch):
    monkeypatch.setitem(sys.modules, "openpyxl", None)
    assert opened.get("/api/export/json").status_code == 200
    assert opened.get("/api/export/xml").status_code == 200


def test_capability_flag_and_endpoint_agree(opened):
    """/api/state's excelExport is a promise this endpoint has to keep."""
    capable = body(opened.get("/api/state"))["capabilities"]["excelExport"]
    status = opened.get("/api/export/xlsx").status_code
    assert capable == (status == 200)


# --------------------------------------------------------------------------
# import
# --------------------------------------------------------------------------


def upload(client, content, filename="uploaded.json", field="file"):
    if isinstance(content, str):
        content = content.encode("utf-8")
    return client.post(
        "/api/import/json",
        data={field: (io.BytesIO(content), filename)},
        content_type="multipart/form-data",
    )


def test_import_replaces_the_document(client):
    document = json.loads(json.dumps(DOCUMENT))
    document["title"] = "Imported"

    payload = body(upload(client, dumps(document)))
    assert payload["ok"] is True
    assert payload["metadata"]["title"] == "Imported"
    assert payload["tree"]["name"] == "Top event"
    assert payload["canUndo"] is False
    # Nowhere on disk to save it back to, so: no path, and dirty until the
    # user picks one.
    assert payload["currentPath"] is None
    assert payload["dirty"] is True


def test_import_then_save_asks_for_a_location(client):
    upload(client, dumps(DOCUMENT))
    response = post(client, "/api/file/save")
    assert response.status_code == 409
    assert body(response)["error"]["code"] == "NO_CURRENT_PATH"


def test_import_then_save_as_writes_the_uploaded_tree(client, sandbox):
    upload(client, dumps(DOCUMENT))
    target = sandbox / "from_upload.json"
    assert post(client, "/api/file/save-as", {"path": str(target)}).status_code == 200
    assert json.loads(target.read_text(encoding="utf-8"))["title"] == "Pump failure"


def test_import_accepts_legacy_and_encoded_uploads(client):
    payload = body(upload(client, dumps({"FTA": TREE})))
    assert payload["tree"]["name"] == "Top event"

    document = json.loads(json.dumps(DOCUMENT))
    document["title"] = "ポンプ故障"
    payload = body(
        upload(client, dumps(document).encode("cp932"))
    )
    assert payload["metadata"]["title"] == "ポンプ故障"


def test_import_accepts_a_nameless_blob(client):
    """A browser FormData blob arrives as 'blob' with no extension."""
    payload = body(upload(client, dumps(DOCUMENT), filename="blob"))
    assert payload["ok"] is True


def test_import_rejects_a_non_json_extension(client):
    response = upload(client, dumps(DOCUMENT), filename="payload.exe")
    assert_rejected(response, reason="extension")


def test_import_rejects_junk(client):
    response = upload(client, "not json at all")
    assert response.status_code == 400
    assert body(response)["error"]["code"] == "INVALID_JSON"


def test_import_without_a_file_is_a_bad_request(client):
    response = client.post("/api/import/json", data={}, content_type="multipart/form-data")
    assert response.status_code == 400
    assert body(response)["error"]["code"] == "INVALID_FIELD"


def test_import_leaves_no_temp_files_and_no_temp_path_behind(client):
    before = temp_files("fta_import_")
    assert upload(client, dumps(DOCUMENT)).status_code == 200
    assert temp_files("fta_import_") == before
    # The loader points last_saved_file at the file it read -- here a temp
    # file that no longer exists. A later save must never land there.
    assert get_state().core.last_saved_file is None


def test_oversized_import_is_refused(client, monkeypatch):
    import fta_web.routes.files as files_module

    monkeypatch.setattr(files_module, "MAX_UPLOAD_BYTES", 16)
    response = upload(client, dumps(DOCUMENT))
    assert response.status_code == 413
    assert body(response)["error"]["code"] == "PAYLOAD_TOO_LARGE"


# --------------------------------------------------------------------------
# the sandbox root comes from the app configuration
# --------------------------------------------------------------------------


def test_blueprint_adopts_the_apps_configured_root(tmp_path):
    """``run.py --root`` must actually confine the endpoints.

    create_app() stores the root in app.config; everything at runtime reads
    AppState.fs_root. Registering the blueprint is what bridges the two, so
    this asserts the bridge rather than the default.
    """
    flask = pytest.importorskip("flask")

    configured = tmp_path / "configured"
    configured.mkdir()
    reset_state()
    app = flask.Flask(__name__)
    app.config["FTA_FS_ROOT"] = configured
    app.register_blueprint(files_bp)

    assert get_state().fs_root == configured
    with app.test_client() as test_client:
        assert body(test_client.get("/api/fs/home"))["root"] == str(configured)


def test_fsbrowser_resolves_a_symlinked_root(tmp_path):
    """A root reached through a symlink must not reject its own contents."""
    real = tmp_path / "real"
    real.mkdir()
    (real / "a.json").write_text("{}", encoding="utf-8")
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)

    root = fsbrowser.resolve_root(link)
    assert root == real.resolve()
    assert fsbrowser.resolve_for_open(str(link / "a.json"), root) == real / "a.json"
