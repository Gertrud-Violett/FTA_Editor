"""
The move/rename/delete contract the tree panel's editing surface is built on.

``fta_web/static/js/tree.js`` computes drop positions, refuses illegal drags
before they are released, and refuses an empty rename outright. Every one of
those decisions is an assumption about this API, and an assumption that is only
written down in JavaScript is one nobody will notice breaking. So each is
pinned here:

* ``index`` counts positions in the new parent's child list **after** the node
  has been detached. That single sentence is what the client's
  ``if (from < insertAt) insertAt -= 1`` exists for, and it is the difference
  between "drop below the last sibling" landing last or second-to-last.
* a cycle, a root move and a root delete are refused with their own codes, so
  the client can mirror the check locally and still surface the server's
  message verbatim when the two disagree.
* one mutation is one undo step -- which is also why the two gaps below matter.

TWO GAPS THIS FILE DELIBERATELY RECORDS RATHER THAN FIXES
=========================================================
1. ``PATCH /api/nodes/<id>`` accepts an empty name. ``sanitize_name`` turns
   ``"   "`` into ``""`` and the update is stored, leaving a row that cannot be
   read in the tree, picked in a link dropdown, or found by search. The web
   client therefore refuses an empty name before it sends anything; that
   client-side guard is the only thing standing between a user and an unusable
   row, so ``test_empty_name_is_accepted_by_the_server`` pins the behaviour it
   is compensating for. If the server ever starts refusing it, this test fails
   and the guard can become a belt to the server's braces rather than the only
   defence.

2. There is no batch delete. Removing N nodes is N requests and therefore N
   undo steps: Ctrl+Z walks back one node at a time. The tree panel says so in
   its confirmation message instead of implying a single reversible action.
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fta_web.state import reset_state  # noqa: E402


@pytest.fixture
def client():
    """A bare Flask app with only the tree blueprint -- no security layer."""
    flask = pytest.importorskip("flask")
    from fta_web.routes.tree import tree_bp

    reset_state()
    app = flask.Flask(__name__)
    app.register_blueprint(tree_bp)
    app.config.update(TESTING=True)
    with app.test_client() as test_client:
        yield test_client


def add(client, parent_id="root", name="Child", **kwargs):
    payload = {"parentId": parent_id, "name": name}
    payload.update(kwargs)
    response = client.post("/api/nodes", json=payload)
    assert response.status_code == 200, response.get_json()
    return response.get_json()["nodeId"]


def child_ids(client, parent_id):
    """The ids of ``parent_id``'s direct children, in order."""
    node = client.get(f"/api/nodes/{parent_id}").get_json()["node"]
    return node["childIds"]


def move(client, node_id, new_parent_id, index="omit"):
    payload = {"newParentId": new_parent_id}
    if index != "omit":
        payload["index"] = index
    return client.post(f"/api/nodes/{node_id}/move", json=payload)


@pytest.fixture
def sample(client):
    """
        root
        |- root_0  "Alpha"   |- root_0_0 "Alpha One"
        |                    '- root_0_1 "Alpha Two"
        '- root_1  "Beta"    '- root_1_0 "Beta One"
    """
    add(client, name="Alpha")
    add(client, "root_0", name="Alpha One")
    add(client, "root_0", name="Alpha Two")
    add(client, name="Beta")
    add(client, "root_1", name="Beta One")
    return client


class TestIndexIsPostDetach:
    """The arithmetic every drop position in the client is computed with."""

    def test_same_parent_move_to_the_end(self, sample):
        # Drag root_0_0 below root_0_1. Visually that is slot 2; because the
        # node is detached first, the client sends 1 -- and 1 is what lands it
        # last. Sending the visual 2 would clamp to the same place here, so the
        # asymmetric case below is the one that actually proves the rule.
        assert child_ids(sample, "root_0") == ["root_0_0", "root_0_1"]
        assert move(sample, "root_0_0", "root_0", 1).status_code == 200
        assert child_ids(sample, "root_0") == ["root_0_1", "root_0_0"]

    def test_same_parent_move_of_a_middle_child(self, sample):
        add(sample, "root_0", name="Alpha Three")  # root_0_2
        assert child_ids(sample, "root_0") == ["root_0_0", "root_0_1", "root_0_2"]
        # Drop root_0_0 between root_0_1 and root_0_2. Visual slot 2; after the
        # detach the list is [root_0_1, root_0_2], so the client subtracts one
        # and sends 1.
        assert move(sample, "root_0_0", "root_0", 1).status_code == 200
        assert child_ids(sample, "root_0") == ["root_0_1", "root_0_0", "root_0_2"]
        # Sending the un-subtracted 2 would have put it last, which is a
        # different node order and the bug this rule prevents.

    def test_foreign_parent_uses_the_visual_index_unchanged(self, sample):
        # The dragged node is not among the target's children, so nothing
        # shifts and the client sends the visual slot as-is.
        assert move(sample, "root_1_0", "root_0", 1).status_code == 200
        assert child_ids(sample, "root_0") == ["root_0_0", "root_1_0", "root_0_1"]

    def test_index_zero_puts_it_first(self, sample):
        assert move(sample, "root_1", "root_0", 0).status_code == 200
        assert child_ids(sample, "root_0") == ["root_1", "root_0_0", "root_0_1"]

    def test_omitted_index_appends(self, sample):
        assert move(sample, "root_1_0", "root_0").status_code == 200
        assert child_ids(sample, "root_0") == ["root_0_0", "root_0_1", "root_1_0"]

    def test_null_index_appends_too(self, sample):
        """The client sends an explicit null for an onto-the-node drop."""
        assert move(sample, "root_1_0", "root_0", None).status_code == 200
        assert child_ids(sample, "root_0") == ["root_0_0", "root_0_1", "root_1_0"]

    def test_out_of_range_index_is_clamped(self, sample):
        assert move(sample, "root_1_0", "root_0", 99).status_code == 200
        assert child_ids(sample, "root_0")[-1] == "root_1_0"

    def test_non_integer_index_is_refused(self, sample):
        response = move(sample, "root_1_0", "root_0", "1")
        assert response.status_code == 400
        assert response.get_json()["error"]["code"] == "INVALID_FIELD"

    def test_the_subtree_travels_with_the_node(self, sample):
        assert move(sample, "root_0", "root_1", 0).status_code == 200
        assert child_ids(sample, "root_1") == ["root_0", "root_1_0"]
        assert child_ids(sample, "root_0") == ["root_0_0", "root_0_1"]


class TestRefusals:
    """Each refusal the client mirrors locally, so a drag can read as illegal
    while it is still in flight rather than as an error after the drop."""

    def test_into_own_child(self, sample):
        response = move(sample, "root_0", "root_0_0")
        assert response.status_code == 400
        assert response.get_json()["error"]["code"] == "CYCLE_REJECTED"

    def test_into_a_deeper_descendant(self, sample):
        add(sample, "root_0_1", name="Deep")  # root_0_1_0
        response = move(sample, "root_0", "root_0_1_0")
        assert response.status_code == 400
        assert response.get_json()["error"]["code"] == "CYCLE_REJECTED"

    def test_onto_itself(self, sample):
        response = move(sample, "root_0", "root_0")
        assert response.status_code == 400
        assert response.get_json()["error"]["code"] == "CYCLE_REJECTED"

    def test_the_root_cannot_be_moved(self, sample):
        response = move(sample, "root", "root_0")
        assert response.status_code == 400
        assert response.get_json()["error"]["code"] == "ROOT_PROTECTED"

    def test_the_root_cannot_be_deleted(self, sample):
        response = sample.delete("/api/nodes/root")
        assert response.status_code == 400
        assert response.get_json()["error"]["code"] == "ROOT_PROTECTED"

    def test_an_unknown_parent_is_a_404(self, sample):
        response = move(sample, "root_0", "ghost")
        assert response.status_code == 404
        assert response.get_json()["error"]["code"] == "PARENT_NOT_FOUND"

    def test_a_promotion_is_not_a_cycle(self, sample):
        """The check is "is the target inside the moved subtree", not the
        reverse. Moving a grandchild up under the root is legal and stays so."""
        assert move(sample, "root_0_1", "root").status_code == 200
        assert "root_0_1" in child_ids(sample, "root")

    def test_a_refused_move_changes_nothing(self, sample):
        before = client_tree(sample)
        move(sample, "root_0", "root_0_0")
        assert client_tree(sample) == before


def client_tree(client):
    return client.get("/api/state").get_json()["tree"]


class TestUndoAccounting:
    """One mutation is one undo step -- which is exactly why an N-node delete
    costs N of them."""

    def test_a_move_is_one_undo_step(self, sample):
        before = child_ids(sample, "root_0")
        response = move(sample, "root_1_0", "root_0", 0)
        assert response.get_json()["canUndo"] is True
        assert sample.post("/api/undo", json={}).status_code == 200
        assert child_ids(sample, "root_0") == before
        assert child_ids(sample, "root_1") == ["root_1_0"]

    def test_a_rename_is_one_undo_step(self, sample):
        sample.patch("/api/nodes/root_0", json={"name": "Renamed"})
        assert sample.post("/api/undo", json={}).status_code == 200
        assert client_node(sample, "root_0")["name"] == "Alpha"

    def test_deleting_three_nodes_takes_three_undos(self, sample):
        """The gap behind the tree panel's multi-delete message.

        There is no batch endpoint, so a multi-node delete is a loop of
        requests and Ctrl+Z walks back one node at a time. The panel says so
        rather than implying the whole selection comes back at once.
        """
        add(sample, name="Gamma")  # root_2
        for node_id in ("root_0_0", "root_0_1", "root_2"):
            assert sample.delete(f"/api/nodes/{node_id}").status_code == 200
        assert child_ids(sample, "root_0") == []

        sample.post("/api/undo", json={})
        assert child_ids(sample, "root_0") == []  # only root_2 is back so far
        assert "root_2" in child_ids(sample, "root")

        sample.post("/api/undo", json={})
        sample.post("/api/undo", json={})
        assert child_ids(sample, "root_0") == ["root_0_0", "root_0_1"]

    def test_deleting_a_parent_takes_its_children_with_it(self, sample):
        """Why the panel prunes a selection down to its top-most nodes: the
        second request would be a 404 on an id that no longer exists."""
        assert sample.delete("/api/nodes/root_0").status_code == 200
        assert sample.delete("/api/nodes/root_0_0").status_code == 404


def client_node(client, node_id):
    return client.get(f"/api/nodes/{node_id}").get_json()["node"]


class TestRenameGap:
    def test_empty_name_is_accepted_by_the_server(self, sample):
        """GAP: the server stores an empty name, so the client must refuse it.

        This is not asserting desirable behaviour -- it is pinning the
        behaviour ``tree.js``'s client-side guard exists to compensate for. If
        this ever starts returning 400, the guard becomes redundant rather than
        load-bearing, and this test is where that shows up.
        """
        response = sample.patch("/api/nodes/root_0", json={"name": "   "})
        assert response.status_code == 200
        assert client_node(sample, "root_0")["name"] == ""

    def test_a_name_is_whitespace_collapsed_the_way_the_client_previews_it(self, sample):
        """dialogs.sanitizeName mirrors core.sanitize_name, so the row shows
        what will actually be stored rather than what was typed."""
        sample.patch("/api/nodes/root_0", json={"name": "  Two   words  "})
        assert client_node(sample, "root_0")["name"] == "Two words"


class TestMovePayload:
    def test_move_returns_the_whole_post_mutation_view(self, sample):
        """The client applies this response instead of re-fetching /state."""
        body = move(sample, "root_1_0", "root_0", 0).get_json()
        assert body["ok"] is True
        assert body["nodeId"] == "root_1_0"
        assert body["parentId"] == "root_0"
        for key in ("tree", "zeroNodes", "dirty", "canUndo", "canRedo"):
            assert key in body, f"missing {key}: the client would render stale state"

    def test_zero_marks_are_recomputed_after_a_move(self, sample):
        """A move changes which nodes score zero, so the ✖ column has to come
        back with the response rather than on a later refresh."""
        for parent in ("root_0", "root_1"):
            sample.patch(f"/api/nodes/{parent}", json={"logicGate": "AND"})
        add(sample, "root_1", name="Impossible", probability=0.0)  # root_1_1
        assert "root_1" in sample.get("/api/state").get_json()["zeroNodes"]
        assert "root_0" not in sample.get("/api/state").get_json()["zeroNodes"]

        # Carry the impossible event across to the other AND branch: the mark
        # has to move with it, in the very payload that reports the move.
        body = move(sample, "root_1_1", "root_0", 0).get_json()
        assert "root_1" not in body["zeroNodes"]
        assert "root_0" in body["zeroNodes"]
