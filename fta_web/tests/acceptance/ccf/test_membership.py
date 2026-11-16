"""F2 BRIEF criterion 4 (FN-38): membership follows the tree.

One test per operation, each checking the group's member list before, after
the operation, after one undo and after a redo:

(a) an operation that removes a member node removes it from its group in the
    same undo step: tree delete, batch delete, AI apply-changes, AI update
    (one step, and preview then apply), undo of the node's creation; an FMEA
    import never removes a node, so it must leave the members alone;
(b) an operation that gives existing nodes new ids remaps the members when the
    mapping is one to one (the top-level id), and otherwise flags the group
    ``CCF_MEMBER_RENAMED`` and leaves the members as they are (duplicate-id
    repair on open and on import);
(c) an operation that makes a member non-basic (adding a child, setting a gate
    through ``PATCH /api/nodes``) keeps the membership; lint flags the group
    ``CCF_MEMBER_NOT_BASIC``.

The member list is read through ``GET /api/ccf/groups``.
"""
import copy
import io
import json

import pytest

import _ccf_models as M

THREE = ["A", "B", "X"]


def membership_doc():
    tree = M.top([
        M.gate("G1", "AND", [M.pump("A"), M.pump("B"), M.pump("X")], name="Pumps fail"),
        M.pump("D"),
    ])
    return M.document(tree, [M.group(members=THREE)])


@pytest.fixture
def opened(api):
    api.open_doc(membership_doc())
    return api


def members(api, gid="g1"):
    for group in api.groups()["groups"]:
        if group["id"] == gid:
            return group["members"]
    raise AssertionError("group %s not listed" % gid)


def status_of(api, gid="g1"):
    for group in api.groups()["groups"]:
        if group["id"] == gid:
            return group["status"]
    raise AssertionError("group %s not listed" % gid)


def has_node(api, node_id):
    status, _ = api.get("/api/nodes/%s" % node_id)
    return status == 200


def check_cycle(api, operation, after, node_checks=None):
    """before -> operation -> after -> undo (one step) -> before -> redo -> after."""
    before = members(api)
    operation()
    assert members(api) == after
    status, undone = api.post("/api/undo")
    assert status == 200, undone
    assert members(api) == before  # one undo restores the node and the membership
    assert undone["analysis"]["ccfGroups"][0]["members"] == before
    status, redone = api.post("/api/redo")
    assert status == 200, redone
    assert members(api) == after
    assert redone["analysis"]["ccfGroups"][0]["members"] == after


# ------------------------------------------------------------------ (a) removal


def test_a_tree_delete_removes_the_member_in_the_same_undo_step(opened):
    def operation():
        status, body = opened.delete("/api/nodes/A")
        assert status == 200, body

    check_cycle(opened, operation, ["B", "X"])
    assert not has_node(opened, "A")  # after the redo
    opened.post("/api/undo")
    assert has_node(opened, "A")


def test_deleting_a_gate_removes_every_member_below_it_and_keeps_the_group(opened):
    def operation():
        assert opened.delete("/api/nodes/G1")[0] == 200

    check_cycle(opened, operation, [])
    groups = opened.groups()["groups"]
    assert [g["id"] for g in groups] == ["g1"]  # a group is never deleted by the tree
    assert groups[0]["status"]["code"] == "CCF_TOO_FEW_MEMBERS"
    assert groups[0]["status"]["applied"] is False


def test_a_batch_delete_removes_the_members_in_the_same_undo_step(opened):
    def operation():
        status, body = opened.post("/api/batch/delete", {"ids": ["A", "B"]})
        assert status == 200, body

    check_cycle(opened, operation, ["X"])
    assert status_of(opened)["code"] == "CCF_TOO_FEW_MEMBERS"


def test_a_batch_delete_of_a_non_member_leaves_the_members_alone(opened):
    def operation():
        assert opened.post("/api/batch/delete", {"ids": ["D"]})[0] == 200

    check_cycle(opened, operation, THREE)


# The AI is never called: the provider's send_message is replaced (as in test_api_ai.py).

API_KEY = "sk-testkeyDONOTLEAK0123456789abcdefAB12"
DELETE_A_REPLY = """Pump A is redundant.

SUGGESTION: Remove pump A
DESCRIPTION: The pump is not needed.
ACTION: delete
TARGET: A
DATA: {"id": "A"}
"""


@pytest.fixture
def ai(opened, tmp_path, monkeypatch):
    from AI_agent_handler import AICredentialManager
    from ai_providers import AIProviderFactory

    from fta_web import ai_bridge

    directory = tmp_path / "fta_editor_home"
    monkeypatch.setattr(AICredentialManager, "CREDENTIALS_DIR", directory)
    monkeypatch.setattr(AICredentialManager, "CREDENTIALS_FILE", directory / "ai_credentials.json")
    ai_bridge.reset_handler()
    provider = AIProviderFactory.get_provider("OpenAI")
    monkeypatch.setattr(provider, "test_connection", lambda *a, **k: (True, "connection successful"))
    status, body = opened.post("/api/ai/credentials", {
        "provider": "OpenAI", "apiKey": API_KEY,
        "endpoint": "https://api.openai.com/v1", "model": "gpt-4o"})
    assert status == 200, body

    def reply_with(text):
        def send_message(api_key, endpoint, model, messages, max_tokens=2000):
            return text, None

        monkeypatch.setattr(provider, "send_message", send_message)

    opened.reply_with = reply_with
    yield opened
    ai_bridge.reset_handler()


def test_ai_apply_changes_removes_the_member_in_the_same_undo_step(ai):
    ai.reply_with(DELETE_A_REPLY)
    assert ai.post("/api/ai/chat", {"message": "suggest"})[0] == 200

    def operation():
        status, body = ai.post("/api/ai/changes/apply", {"indices": [0]})
        assert status == 200, body

    check_cycle(ai, operation, ["B", "X"])


def updated_tree_without(api, node_id):
    """The current tree with ``node_id`` cut out of its parent, as the AI would return it."""
    status, state = api.get("/api/state")
    assert status == 200
    tree = copy.deepcopy(state["tree"])

    def cut(node):
        node["children"] = [c for c in node.get("children", []) if c["id"] != node_id]
        for child in node["children"]:
            cut(child)

    cut(tree)
    return tree


def test_ai_update_removes_the_member_in_the_same_undo_step(ai):
    ai.reply_with(json.dumps(updated_tree_without(ai, "A")))

    def operation():
        status, body = ai.post("/api/ai/update", {})
        assert status == 200, body

    check_cycle(ai, operation, ["B", "X"])


def test_ai_update_preview_changes_nothing_and_apply_removes_the_member(ai):
    ai.reply_with(json.dumps(updated_tree_without(ai, "A")))
    status, preview = ai.post("/api/ai/update", {"preview": True})
    assert status == 200, preview
    assert members(ai) == THREE  # a preview works on a copy of the document

    def operation():
        status, body = ai.post("/api/ai/update/apply", {"id": preview["updateId"]})
        assert status == 200, body

    check_cycle(ai, operation, ["B", "X"])


def test_an_fmea_import_removes_no_member_and_is_one_undo_step(opened, tmp_path):
    csv_path = tmp_path / "fmea.csv"
    csv_path.write_text("FMEA ID,Item,Failure Mode,Failure rate\nF-1,Relief,Leaks,1e-6\n",
                        encoding="utf-8")
    body = {"path": str(csv_path), "parentId": "root", "update": True, "lambdaUnit": "h",
            "mapping": {"id": "FMEA ID", "item": "Item", "mode": "Failure Mode",
                        "lambda": "Failure rate"}}

    def operation():
        status, payload = opened.post("/api/fmea/import", body)
        assert status == 200, payload
        assert payload["created"], payload

    check_cycle(opened, operation, THREE)  # nothing was removed, so nothing changes


def test_undoing_the_creation_of_a_member_removes_it_from_the_group(opened):
    assert members(opened) == THREE
    status, created = opened.post("/api/nodes", {"parentId": "G1", "name": "Pump N",
                                                 "probability": 1e-3})
    assert status == 200, created
    new_id = created["nodeId"]
    status, body = opened.patch("/api/ccf/groups/g1", {"members": THREE + [new_id]})
    assert status == 200, body
    assert members(opened) == THREE + [new_id]

    assert opened.post("/api/undo")[0] == 200  # the group edit
    assert members(opened) == THREE
    assert opened.post("/api/undo")[0] == 200  # the creation of the node
    assert members(opened) == THREE
    assert not has_node(opened, new_id)

    assert opened.post("/api/redo")[0] == 200
    assert has_node(opened, new_id) and members(opened) == THREE
    assert opened.post("/api/redo")[0] == 200
    assert members(opened) == THREE + [new_id]


def test_deleting_a_member_added_in_the_same_session_removes_it_and_undo_restores_it(opened):
    assert members(opened) == THREE
    status, created = opened.post("/api/nodes", {"parentId": "G1", "name": "Pump N",
                                                 "probability": 1e-3})
    new_id = created["nodeId"]
    assert opened.patch("/api/ccf/groups/g1", {"members": THREE + [new_id]})[0] == 200

    def operation():
        assert opened.delete("/api/nodes/%s" % new_id)[0] == 200

    check_cycle(opened, operation, THREE)


# ------------------------------------------------------------------ (b) new ids


def top_id_doc():
    """The top-level node carries the id TOP; the loader turns it into ``root``."""
    tree = M.gate("TOP", "OR", [M.gate("G1", "AND", [M.pump("A"), M.pump("B")],
                                       name="Pumps fail")], name="Top event", type_="Root")
    return M.document(tree, [M.group(members=["TOP", "A"])])


def test_a_member_equal_to_the_renamed_top_id_is_remapped_one_to_one(api):
    body = api.open_doc(top_id_doc())
    assert any(w.get("kind") == "root_id" and w.get("old_id") == "TOP" for w in body["warnings"])
    assert members(api) == ["root", "A"]
    status = status_of(api)
    # Remapped, so it is found as the (gate) top event, not reported as missing.
    assert status["code"] == "CCF_MEMBER_NOT_BASIC"
    assert status["reason"]["en"] == '"Top event" is not a basic event'
    # And a stored file keeps the new id.
    out = api.root / "saved_top.json"
    assert api.post("/api/file/save-as", {"path": str(out)})[0] == 200
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["analysis"]["ccfGroups"][0]["members"] == ["root", "A"]


def duplicate_id_doc():
    tree = M.top([
        M.gate("G1", "AND", [M.pump("A"), M.pump("B")], name="Pumps fail"),
        M.gate("G2", "AND", [M.leaf("A", 1e-3, name="Pump A twin"), M.pump("D")], name="Other"),
    ])
    return M.document(tree, [M.group()])


def check_renamed_group(api):
    assert members(api) == ["A", "B"]  # not changed: the old id names several nodes
    status = status_of(api)
    assert status["applied"] is False
    assert status["code"] == "CCF_MEMBER_RENAMED"
    assert status["severity"] == "error"


def test_a_duplicate_id_repair_flags_the_group_and_keeps_the_members(api):
    body = api.open_doc(duplicate_id_doc())
    assert any(w.get("kind") == "duplicate_id" and w.get("old_id") == "A" for w in body["warnings"])
    check_renamed_group(api)
    status, validate = api.get("/api/analysis/validate")
    codes = [i["code"] for i in validate["issues"]]
    assert "CCF_MEMBER_RENAMED" in codes


def test_choosing_the_members_again_clears_the_flag_and_undo_brings_it_back(api):
    api.open_doc(duplicate_id_doc())
    status, body = api.patch("/api/ccf/groups/g1", {"members": ["A_dup2", "B"]})
    assert status == 200, body
    assert members(api) == ["A_dup2", "B"]
    assert status_of(api)["applied"] is True
    assert api.post("/api/undo")[0] == 200
    check_renamed_group(api)
    assert api.post("/api/redo")[0] == 200
    assert status_of(api)["applied"] is True


def test_the_rename_flag_is_never_saved(api):
    api.open_doc(duplicate_id_doc())
    out = api.root / "saved_dup.json"
    assert api.post("/api/file/save-as", {"path": str(out)})[0] == 200
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["analysis"]["ccfGroups"][0]["members"] == ["A", "B"]
    assert not [key for key in saved["analysis"] if key.startswith("_ccf")]
    ids = []

    def collect(node):
        ids.append(node["id"])
        for child in node["children"]:
            collect(child)

    collect(saved["tree"])
    assert len(ids) == len(set(ids))  # the saved file has unique ids
    # Opened again, the file has nothing left to repair: the group is applied.
    api.open_doc(saved, "reopened.json")
    assert status_of(api)["applied"] is True


def test_an_import_with_duplicate_ids_flags_the_group_like_an_open(api):
    payload = json.dumps(duplicate_id_doc(), ensure_ascii=False).encode("utf-8")
    response = api.client.post(
        "/api/import/json", data={"file": (io.BytesIO(payload), "dup.json")},
        content_type="multipart/form-data")
    assert response.status_code == 200, response.get_data(as_text=True)
    check_renamed_group(api)


def test_an_import_with_a_renamed_top_id_remaps_the_members(api):
    payload = json.dumps(top_id_doc(), ensure_ascii=False).encode("utf-8")
    response = api.client.post(
        "/api/import/json", data={"file": (io.BytesIO(payload), "top.json")},
        content_type="multipart/form-data")
    assert response.status_code == 200, response.get_data(as_text=True)
    assert members(api) == ["root", "A"]


# ------------------------------------------------------------ (c) member made non-basic


def test_a_member_that_gets_a_child_keeps_its_membership_and_the_group_is_flagged(opened):
    assert members(opened) == THREE
    assert status_of(opened)["applied"] is True

    def operation():
        status, body = opened.post("/api/nodes", {"parentId": "A", "name": "Seal", "probability": 1e-3})
        assert status == 200, body

    check_cycle(opened, operation, THREE)  # the membership is kept in all four states
    status = status_of(opened)  # after the redo
    assert status["applied"] is False
    assert status["code"] == "CCF_MEMBER_NOT_BASIC"
    assert status["reason"]["en"] == '"Pump A" is not a basic event'
    assert "has child events" in status["message"]["en"]
    opened.post("/api/undo")
    assert status_of(opened)["applied"] is True  # the child is gone: A is a basic event again


def test_a_member_turned_into_a_transfer_gate_keeps_its_membership_and_the_group_is_flagged(api):
    # FN-38 (c), the second listed operation, "setting a gate": PATCH /api/nodes/A with
    # gateType TRANSFER and a transferTo (an existing sub tree, so the document stays sound).
    tree = M.top([
        M.gate("G1", "AND", [M.pump("A"), M.pump("B"), M.pump("X")], name="Pumps fail"),
        M.gate("SUB", "AND", [M.leaf("C"), M.leaf("E")], name="Sub tree"),
    ])
    api.open_doc(M.document(tree, [M.group(members=THREE)]))
    assert members(api) == THREE
    assert status_of(api)["applied"] is True

    def operation():
        status, body = api.patch("/api/nodes/A", {"gateType": "TRANSFER", "transferTo": "SUB"})
        assert status == 200, body

    check_cycle(api, operation, THREE)  # the membership is kept in all four states
    status = status_of(api)  # after the redo
    assert status["applied"] is False
    assert status["code"] == "CCF_MEMBER_NOT_BASIC"
    assert status["reason"]["en"] == '"Pump A" is not a basic event'
    assert "transfer gate" in status["message"]["en"]
    assert [g["id"] for g in api.groups()["groups"]] == ["g1"]  # the group itself stays
    api.post("/api/undo")
    assert status_of(api)["applied"] is True  # A is a basic event again
    assert members(api) == THREE
    api.post("/api/redo")
    assert status_of(api)["code"] == "CCF_MEMBER_NOT_BASIC"  # and the redo flags it again
