"""
Tests for the fta_web domain layer: tree_ops, AppState and the /api tree
blueprint.

The rules under test are parity rules -- a file edited in the web app has to
round-trip through the desktop editor unchanged -- so several tests pin
behaviour against the desktop source (``src/FTA_Editor_UI.py``) and against the
vendored core rather than against a hand-written expectation.

``conftest.py`` puts ``fta_web/core`` on sys.path for the vendored modules; the
repo root goes on below so ``fta_web.*`` imports as a package.
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from FTA_Editor_core import FTACore  # noqa: E402

from fta_web.state import AppState, get_state, reset_state  # noqa: E402
from fta_web.tree_ops import (  # noqa: E402
    collect_flat,
    depth_of,
    find_parent_id,
    move_node,
    next_child_id,
    would_create_cycle,
)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def node(node_id, children=None, **kwargs):
    """A well-formed node in the shape FTACore._normalize_node produces."""
    return {
        "id": node_id,
        "name": kwargs.get("name", node_id.upper()),
        "type": kwargs.get("type", "Event"),
        "logicGate": kwargs.get("logicGate", "OR"),
        "probability": kwargs.get("probability", 0.1),
        "children": children or [],
        "links": kwargs.get("links", []),
        "notes": kwargs.get("notes", ""),
    }


def core_with(tree):
    core = FTACore()
    core.set_data(tree)
    return core


@pytest.fixture
def sample_core():
    """
        root
        |- root_0            (a branch with two children)
        |  |- root_0_0
        |  '- root_0_1
        |     '- root_0_1_0  (three levels below the root)
        '- root_1            (a leaf)
    """
    return core_with(
        node(
            "root",
            [
                node(
                    "root_0",
                    [
                        node("root_0_0"),
                        node("root_0_1", [node("root_0_1_0")]),
                    ],
                ),
                node("root_1"),
            ],
        )
    )


def all_ids(core):
    """Every id in the tree, pre-order -- used to assert nothing was lost."""
    return [entry["id"] for entry in collect_flat(core)]


def desktop_next_child_id(existing_child_ids, parent_id):
    """The desktop editor's id generator, transcribed verbatim.

    ``src/FTA_Editor_UI.py`` lines 1414-1424, with the Tkinter call
    ``self.fta_tree.get_children(parent_id)`` replaced by its result. Kept
    byte-for-byte so the parity assertions below compare against the real
    algorithm and not a paraphrase of it.
    """
    existing_children = existing_child_ids
    max_index = -1
    for child_id in existing_children:
        if child_id.startswith(f"{parent_id}_"):
            try:
                index = int(child_id.split("_")[-1])
                max_index = max(max_index, index)
            except ValueError:
                continue
    return f"{parent_id}_{max_index + 1}"


# --------------------------------------------------------------------------
# next_child_id
# --------------------------------------------------------------------------


class TestNextChildId:
    def test_first_child_of_root_is_root_0(self):
        assert next_child_id(FTACore(), "root") == "root_0"

    def test_increments_past_the_highest_existing_index(self, sample_core):
        assert next_child_id(sample_core, "root") == "root_2"
        assert next_child_id(sample_core, "root_0") == "root_0_2"

    def test_first_child_of_a_leaf(self, sample_core):
        assert next_child_id(sample_core, "root_1") == "root_1_0"
        assert next_child_id(sample_core, "root_0_1_0") == "root_0_1_0_0"

    def test_gaps_are_never_reused(self):
        """A deleted middle child does not free up its index."""
        core = core_with(node("root", [node("root_0"), node("root_5")]))
        assert next_child_id(core, "root") == "root_6"

    def test_gap_after_deletion_of_the_last_child(self):
        core = core_with(node("root", [node("root_0"), node("root_1")]))
        core.delete_node_from_data("root_1")
        # root_1 is gone, so the max index is 0 again and the id is recycled.
        assert next_child_id(core, "root") == "root_1"

    def test_ids_that_do_not_match_the_prefix_are_ignored(self):
        core = core_with(node("root", [node("custom-id"), node("other_9")]))
        assert next_child_id(core, "root") == "root_0"

    def test_non_integer_suffixes_are_skipped(self):
        core = core_with(node("root", [node("root_x"), node("root_3")]))
        assert next_child_id(core, "root") == "root_4"

    def test_only_the_trailing_segment_is_read(self):
        """'root_2_7' under root reads as index 7 -- the desktop's split()[-1]."""
        core = core_with(node("root", [node("root_2_7")]))
        assert next_child_id(core, "root") == "root_8"
        assert next_child_id(core, "root") == desktop_next_child_id(["root_2_7"], "root")

    def test_unknown_parent_yields_a_first_child_id(self, sample_core):
        # Callers validate the parent; the format stays predictable regardless.
        assert next_child_id(sample_core, "nope") == "nope_0"

    @pytest.mark.parametrize(
        "child_ids",
        [
            [],
            ["root_0"],
            ["root_0", "root_1", "root_2"],
            ["root_0", "root_5"],
            ["root_x", "root_3"],
            ["custom", "root_0"],
            ["root_10", "root_9"],
            ["root_2_7"],
        ],
    )
    def test_matches_the_desktop_algorithm_exactly(self, child_ids):
        core = core_with(node("root", [node(cid) for cid in child_ids]))
        assert next_child_id(core, "root") == desktop_next_child_id(child_ids, "root")

    def test_agrees_with_core_normalize_node(self):
        """_normalize_node invents f"{parent_id}_{idx}" for an id-less child.

        Generated ids must therefore survive a save/load round-trip through
        either tool without being renumbered.
        """
        core = FTACore()
        raw = {
            "id": "root",
            "name": "Root",
            "children": [{"name": "first"}, {"name": "second"}],
        }
        normalized = core._normalize_node(raw)
        assert [c["id"] for c in normalized["children"]] == ["root_0", "root_1"]

        core.set_data(normalized)
        assert next_child_id(core, "root") == "root_2"

        # And an already-numbered tree is left alone by normalization.
        before = all_ids(core)
        core.set_data(core._normalize_node(core.get_data()))
        assert all_ids(core) == before


# --------------------------------------------------------------------------
# depth_of
# --------------------------------------------------------------------------


class TestDepthOf:
    def test_root_is_zero(self, sample_core):
        assert depth_of(sample_core, "root") == 0

    def test_direct_children_are_one(self, sample_core):
        assert depth_of(sample_core, "root_0") == 1
        assert depth_of(sample_core, "root_1") == 1

    def test_nested_depths(self, sample_core):
        assert depth_of(sample_core, "root_0_0") == 2
        assert depth_of(sample_core, "root_0_1") == 2
        assert depth_of(sample_core, "root_0_1_0") == 3

    def test_missing_node_is_minus_one(self, sample_core):
        assert depth_of(sample_core, "does_not_exist") == -1

    def test_depth_is_uncapped(self):
        """The desktop caps two of its four call sites at min(depth, 3); the
        data-level answer is deliberately uncapped."""
        deepest = node("n7")
        tree = deepest
        for level in range(6, -1, -1):
            tree = node(f"n{level}", [tree])
        tree["id"] = "root"
        core = core_with(tree)
        assert depth_of(core, "n7") == 7
        assert depth_of(core, "n4") == 4


# --------------------------------------------------------------------------
# find_parent_id
# --------------------------------------------------------------------------


class TestFindParentId:
    def test_direct_child(self, sample_core):
        assert find_parent_id(sample_core, "root_0") == "root"

    def test_nested_child(self, sample_core):
        assert find_parent_id(sample_core, "root_0_1") == "root_0"
        assert find_parent_id(sample_core, "root_0_1_0") == "root_0_1"

    def test_root_has_no_parent(self, sample_core):
        assert find_parent_id(sample_core, "root") is None

    def test_unknown_node_has_no_parent(self, sample_core):
        assert find_parent_id(sample_core, "ghost") is None


# --------------------------------------------------------------------------
# would_create_cycle
# --------------------------------------------------------------------------


class TestWouldCreateCycle:
    def test_moving_a_node_into_itself(self, sample_core):
        assert would_create_cycle(sample_core, "root_0", "root_0") is True

    def test_moving_a_node_into_its_own_child(self, sample_core):
        assert would_create_cycle(sample_core, "root_0", "root_0_1") is True

    def test_moving_a_node_into_a_deep_descendant(self, sample_core):
        assert would_create_cycle(sample_core, "root_0", "root_0_1_0") is True

    def test_moving_to_a_sibling_is_fine(self, sample_core):
        assert would_create_cycle(sample_core, "root_0_0", "root_1") is False

    def test_moving_to_the_current_parent_is_fine(self, sample_core):
        """A re-order, not a cycle.

        The vendored AIAgentHandler._would_create_circular_reference asks the
        descendant question with its arguments the other way round and would
        reject this. tree_ops corrects the direction; see its docstring.
        """
        assert would_create_cycle(sample_core, "root_0_0", "root_0") is False

    def test_promoting_a_grandchild_is_fine(self, sample_core):
        """Same regression, one level up: moving a node to its grandparent."""
        assert would_create_cycle(sample_core, "root_0_1_0", "root") is False

    def test_unknown_node_is_not_a_cycle(self, sample_core):
        assert would_create_cycle(sample_core, "ghost", "root_0") is False


# --------------------------------------------------------------------------
# move_node
# --------------------------------------------------------------------------


class TestMoveNodeSuccess:
    def test_appends_to_the_new_parent(self, sample_core):
        ok, err = move_node(sample_core, "root_1", "root_0")
        assert (ok, err) == (True, None)
        assert [c["id"] for c in sample_core.find_node_by_id("root_0")["children"]] == [
            "root_0_0",
            "root_0_1",
            "root_1",
        ]
        assert [c["id"] for c in sample_core.get_data()["children"]] == ["root_0"]

    def test_the_node_is_not_duplicated(self, sample_core):
        before = sorted(all_ids(sample_core))
        assert move_node(sample_core, "root_1", "root_0_1")[0] is True
        assert sorted(all_ids(sample_core)) == before

    def test_subtree_travels_with_the_node(self, sample_core):
        assert move_node(sample_core, "root_0_1", "root_1")[0] is True
        moved = sample_core.find_node_by_id("root_1")["children"][0]
        assert moved["id"] == "root_0_1"
        assert [c["id"] for c in moved["children"]] == ["root_0_1_0"]
        assert depth_of(sample_core, "root_0_1_0") == 3

    def test_index_inserts_at_a_position(self, sample_core):
        assert move_node(sample_core, "root_1", "root_0", index=0)[0] is True
        assert [c["id"] for c in sample_core.find_node_by_id("root_0")["children"]] == [
            "root_1",
            "root_0_0",
            "root_0_1",
        ]

    def test_index_is_clamped(self, sample_core):
        assert move_node(sample_core, "root_1", "root_0", index=99)[0] is True
        assert sample_core.find_node_by_id("root_0")["children"][-1]["id"] == "root_1"

        assert move_node(sample_core, "root_1", "root_0", index=-5)[0] is True
        assert sample_core.find_node_by_id("root_0")["children"][0]["id"] == "root_1"

    def test_same_parent_move_reorders(self, sample_core):
        """Index is applied after the node is detached, so this is a re-order."""
        ok, err = move_node(sample_core, "root_0_1", "root_0", index=0)
        assert (ok, err) == (True, None)
        assert [c["id"] for c in sample_core.find_node_by_id("root_0")["children"]] == [
            "root_0_1",
            "root_0_0",
        ]

    def test_promotion_to_grandparent(self, sample_core):
        ok, err = move_node(sample_core, "root_0_1_0", "root")
        assert (ok, err) == (True, None)
        assert find_parent_id(sample_core, "root_0_1_0") == "root"
        assert depth_of(sample_core, "root_0_1_0") == 1
        assert sample_core.find_node_by_id("root_0_1")["children"] == []

    def test_moved_node_keeps_its_id(self, sample_core):
        """Ids are stable across a move; only next_child_id ever mints one."""
        move_node(sample_core, "root_0_0", "root_1")
        assert sample_core.find_node_by_id("root_0_0") is not None
        assert next_child_id(sample_core, "root_1") == "root_1_0"


class TestMoveNodeRejection:
    def _unchanged(self, core, snapshot_ids):
        assert all_ids(core) == snapshot_ids

    def test_rejects_moving_the_root(self, sample_core):
        before = all_ids(sample_core)
        ok, err = move_node(sample_core, "root", "root_0")
        assert ok is False
        assert "root" in err
        self._unchanged(sample_core, before)

    def test_rejects_an_unknown_node(self, sample_core):
        before = all_ids(sample_core)
        ok, err = move_node(sample_core, "ghost", "root_0")
        assert ok is False
        assert "ghost" in err
        self._unchanged(sample_core, before)

    def test_rejects_an_unknown_parent(self, sample_core):
        before = all_ids(sample_core)
        ok, err = move_node(sample_core, "root_1", "ghost_parent")
        assert ok is False
        assert "ghost_parent" in err
        self._unchanged(sample_core, before)

    def test_rejects_moving_into_itself(self, sample_core):
        before = all_ids(sample_core)
        ok, err = move_node(sample_core, "root_0", "root_0")
        assert ok is False
        assert "descendant" in err
        self._unchanged(sample_core, before)

    def test_rejects_moving_into_a_child(self, sample_core):
        before = all_ids(sample_core)
        ok, err = move_node(sample_core, "root_0", "root_0_0")
        assert ok is False
        assert "descendant" in err
        self._unchanged(sample_core, before)

    def test_rejects_moving_into_a_deep_descendant(self, sample_core):
        before = all_ids(sample_core)
        ok, err = move_node(sample_core, "root_0", "root_0_1_0")
        assert ok is False
        self._unchanged(sample_core, before)


# --------------------------------------------------------------------------
# collect_flat
# --------------------------------------------------------------------------


class TestCollectFlat:
    def test_pre_order_with_depths(self, sample_core):
        assert collect_flat(sample_core) == [
            {"id": "root", "name": "ROOT", "depth": 0},
            {"id": "root_0", "name": "ROOT_0", "depth": 1},
            {"id": "root_0_0", "name": "ROOT_0_0", "depth": 2},
            {"id": "root_0_1", "name": "ROOT_0_1", "depth": 2},
            {"id": "root_0_1_0", "name": "ROOT_0_1_0", "depth": 3},
            {"id": "root_1", "name": "ROOT_1", "depth": 1},
        ]

    def test_sibling_order_is_preserved(self, sample_core):
        move_node(sample_core, "root_1", "root", index=0)
        assert [e["id"] for e in collect_flat(sample_core)][:2] == ["root", "root_1"]

    def test_lone_root(self):
        flat = collect_flat(FTACore())
        assert flat == [{"id": "root", "name": "RootEvent", "depth": 0}]

    def test_depth_matches_depth_of(self, sample_core):
        for entry in collect_flat(sample_core):
            assert entry["depth"] == depth_of(sample_core, entry["id"])


# --------------------------------------------------------------------------
# link cycles stay tolerated
# --------------------------------------------------------------------------


def test_link_cycles_are_not_rejected():
    """Invariant 5: links may point anywhere, including backwards.

    The engine's `visiting` set handles the loop. tree_ops must not treat a
    link as structure -- a link cycle is neither a move cycle nor a depth.
    """
    core = core_with(
        node(
            "root",
            [node("root_0", links=[{"target_id": "root", "relation": "OR"}])],
            links=[{"target_id": "root_0", "relation": "AND"}],
        )
    )
    core.recalculate_probabilities()  # must terminate

    assert depth_of(core, "root_0") == 1
    assert would_create_cycle(core, "root_0", "root") is False
    assert move_node(core, "root_0", "root")[0] is True
    assert len(collect_flat(core)) == 2


# --------------------------------------------------------------------------
# AppState
# --------------------------------------------------------------------------


class TestAppState:
    def test_fresh_state_defaults(self):
        state = AppState()
        assert state.core.get_data()["id"] == "root"
        assert state.core.get_data()["probability"] == 1.0  # not 0.0
        assert state.dirty is False
        assert state.current_path is None
        assert (state.can_undo, state.can_redo) == (False, False)

    def test_undo_and_redo_round_trip(self):
        state = AppState()
        state.push_undo()
        state.core.add_node_to_data("root", node("root_0"))
        state.mark_dirty()

        assert state.can_undo is True
        assert state.can_redo is False

        assert state.undo() is True
        assert state.core.find_node_by_id("root_0") is None
        assert state.can_redo is True

        assert state.redo() is True
        assert state.core.find_node_by_id("root_0") is not None

    def test_undo_on_empty_history_returns_false(self):
        state = AppState()
        assert state.undo() is False
        assert state.redo() is False

    def test_push_undo_clears_the_redo_stack(self):
        state = AppState()
        state.push_undo()
        state.core.add_node_to_data("root", node("root_0"))
        state.undo()
        assert state.can_redo is True

        state.push_undo()
        assert state.can_redo is False

    def test_snapshots_are_detached_copies(self):
        state = AppState()
        state.push_undo()
        state.core.add_node_to_data("root", node("root_0", name="original"))
        state.push_undo()
        state.core.find_node_by_id("root_0")["name"] = "renamed"

        state.undo()
        assert state.core.find_node_by_id("root_0")["name"] == "original"
        # Mutating the restored tree must not corrupt the redo entry.
        state.core.find_node_by_id("root_0")["name"] = "scribble"
        state.redo()
        assert state.core.find_node_by_id("root_0")["name"] == "renamed"

    def test_history_is_bounded(self):
        try:
            from fta_web import config
        except ImportError:  # pragma: no cover
            import config
        state = AppState()
        for index in range(config.UNDO_DEPTH + 10):
            state.push_undo()
            state.core.add_node_to_data("root", node(f"root_{index}"))
        assert len(state._undo) == config.UNDO_DEPTH

    def test_metadata_is_part_of_the_snapshot(self):
        state = AppState()
        state.push_undo()
        state.core.set_metadata(title="After", date="2026-01-01", mode="ETA")
        assert state.undo() is True
        assert state.core.title == "Untitled Analysis"
        assert state.core.mode == "FTA"

    def test_reset_clears_everything(self):
        state = AppState()
        state.push_undo()
        state.core.add_node_to_data("root", node("root_0"))
        state.mark_dirty()
        state.current_path = Path("/tmp/whatever.json")

        state.reset()
        assert state.core.find_node_by_id("root_0") is None
        assert state.dirty is False
        assert state.current_path is None
        assert (state.can_undo, state.can_redo) == (False, False)

    def test_mark_dirty_and_saved(self):
        state = AppState()
        state.mark_dirty()
        assert state.dirty is True
        state.mark_saved()
        assert state.dirty is False

    def test_to_dict_shape(self):
        payload = AppState().to_dict()
        assert set(payload) == {
            "tree",
            "metadata",
            "dirty",
            "currentPath",
            "nativeDot",
            "aiConfigured",
            # Additive in P2: the same facts, grouped, plus excelExport. The
            # two flat keys above stay for the frontend that shipped against
            # them. Contents are asserted in test_api_render.py.
            "capabilities",
            "canUndo",
            "canRedo",
            "language",
            "zeroNodes",
        }
        assert set(payload["metadata"]) == {"title", "date", "mode"}
        assert payload["metadata"]["mode"] == "FTA"
        assert isinstance(payload["nativeDot"], bool)
        assert isinstance(payload["aiConfigured"], bool)
        assert payload["zeroNodes"] == []

    def test_to_dict_tree_is_a_copy(self):
        state = AppState()
        payload = state.to_dict()
        payload["tree"]["name"] = "mutated"
        assert state.core.get_data()["name"] == "RootEvent"

    def test_get_state_is_a_singleton_and_reset_replaces_it(self):
        first = get_state()
        assert get_state() is first
        replacement = reset_state()
        assert replacement is not first
        assert get_state() is replacement


# --------------------------------------------------------------------------
# /api blueprint
# --------------------------------------------------------------------------


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


def add_node(client, parent_id="root", name="Child", **kwargs):
    payload = {"parentId": parent_id, "name": name}
    payload.update(kwargs)
    return client.post("/api/nodes", json=payload)


class TestBlueprint:
    def test_state_endpoint(self, client):
        body = client.get("/api/state").get_json()
        assert body["ok"] is True
        assert body["tree"]["id"] == "root"
        assert body["dirty"] is False

    def test_create_assigns_the_id_and_ignores_a_client_supplied_one(self, client):
        response = add_node(client, name="  spaced   name  ", id="hacker")
        assert response.status_code == 200
        body = response.get_json()
        assert body["nodeId"] == "root_0"
        # sanitize_name collapses the whitespace, as in the desktop editor.
        assert body["node"]["name"] == "spaced name"
        assert body["dirty"] is True
        assert body["canUndo"] is True
        # The unexpected "id" key was simply not used; the tree has no such node.
        assert client.get("/api/nodes/hacker").status_code == 404

    def test_created_ids_follow_the_desktop_sequence(self, client):
        assert add_node(client).get_json()["nodeId"] == "root_0"
        assert add_node(client).get_json()["nodeId"] == "root_1"
        assert add_node(client, "root_0").get_json()["nodeId"] == "root_0_0"

    def test_mutation_response_carries_the_whole_view(self, client):
        body = add_node(client).get_json()
        assert set(body) >= {
            "ok",
            "tree",
            "zeroNodes",
            "dirty",
            "canUndo",
            "canRedo",
            "nodeId",
            "node",
        }

    def test_and_gate_is_calculated(self, client):
        add_node(client, name="A", probability=0.5)
        add_node(client, name="B", probability=0.5)
        client.patch("/api/nodes/root", json={"logicGate": "AND"})
        body = client.get("/api/nodes/root").get_json()
        assert body["node"]["calculatedProbability"] == 0.25

    def test_or_gate_is_the_default_for_an_empty_gate(self, client):
        add_node(client, name="A", probability=0.5)
        add_node(client, name="B", probability=0.5)
        # The core's fresh root has logicGate "" -- invariant 3 says that is OR.
        body = client.get("/api/nodes/root").get_json()
        assert body["node"]["calculatedProbability"] == 0.75

    def test_not_gate_is_rejected(self, client):
        response = add_node(client, logicGate="NOT")
        assert response.status_code == 400
        body = response.get_json()
        assert body["ok"] is False
        assert body["error"]["code"] == "INVALID_FIELD"
        assert "NOT" in body["error"]["message"]

    @pytest.mark.parametrize("bad", [-0.1, 1.5, "abc", None, True])
    def test_probability_is_range_checked(self, client, bad):
        response = add_node(client, probability=bad)
        assert response.status_code == 400
        assert response.get_json()["error"]["code"] == "INVALID_FIELD"

    def test_probability_bounds_are_inclusive(self, client):
        assert add_node(client, probability=0.0).status_code == 200
        assert add_node(client, probability=1.0).status_code == 200

    def test_unknown_parent_is_404(self, client):
        response = add_node(client, parent_id="ghost")
        assert response.status_code == 404
        assert response.get_json()["error"]["code"] == "PARENT_NOT_FOUND"

    def test_patch_rejects_unknown_fields(self, client):
        add_node(client)
        response = client.patch("/api/nodes/root_0", json={"id": "new", "children": []})
        assert response.status_code == 400
        assert response.get_json()["error"]["code"] == "INVALID_FIELD"

    def test_patch_is_partial(self, client):
        add_node(client, name="Original", probability=0.4, notes="keep me")
        client.patch("/api/nodes/root_0", json={"probability": 0.9})
        node_body = client.get("/api/nodes/root_0").get_json()["node"]
        assert node_body["name"] == "Original"
        assert node_body["notes"] == "keep me"
        assert node_body["probability"] == 0.9

    def test_delete_root_is_refused(self, client):
        response = client.delete("/api/nodes/root")
        assert response.status_code == 400
        assert response.get_json()["error"]["code"] == "ROOT_PROTECTED"

    def test_delete_removes_the_subtree(self, client):
        add_node(client)
        add_node(client, "root_0")
        client.delete("/api/nodes/root_0")
        assert client.get("/api/nodes/root_0_0").status_code == 404
        assert [n["id"] for n in client.get("/api/nodes").get_json()["nodes"]] == ["root"]

    def test_move_endpoint(self, client):
        add_node(client, name="A")
        add_node(client, name="B")
        response = client.post("/api/nodes/root_1/move", json={"newParentId": "root_0"})
        assert response.status_code == 200
        assert response.get_json()["parentId"] == "root_0"

    def test_move_into_own_descendant_is_rejected(self, client):
        add_node(client)
        add_node(client, "root_0")
        response = client.post("/api/nodes/root_0/move", json={"newParentId": "root_0_0"})
        assert response.status_code == 400
        assert response.get_json()["error"]["code"] == "CYCLE_REJECTED"

    def test_move_root_is_refused(self, client):
        add_node(client)
        response = client.post("/api/nodes/root/move", json={"newParentId": "root_0"})
        assert response.status_code == 400
        assert response.get_json()["error"]["code"] == "ROOT_PROTECTED"

    def test_nodes_listing_is_flat_and_ordered(self, client):
        add_node(client, name="A")
        add_node(client, "root_0", name="A1")
        add_node(client, name="B")
        nodes = client.get("/api/nodes").get_json()["nodes"]
        assert [(n["id"], n["depth"]) for n in nodes] == [
            ("root", 0),
            ("root_0", 1),
            ("root_0_0", 2),
            ("root_1", 1),
        ]

    def test_node_detail_resolves_link_names(self, client):
        add_node(client, name="Target")
        add_node(client, name="Source", links=[{"target_id": "root_0"}])
        node_body = client.get("/api/nodes/root_1").get_json()["node"]
        assert node_body["links"] == [
            {"target_id": "root_0", "relation": "OR", "targetName": "Target"}
        ]

    def test_dangling_links_are_accepted(self, client):
        """Invariant 5: the engine skips unresolvable targets, so we allow them."""
        response = add_node(client, links=[{"target_id": "not_a_node"}])
        assert response.status_code == 200
        node_body = client.get("/api/nodes/root_0").get_json()["node"]
        assert node_body["links"][0]["targetName"] is None

    def test_undo_redo_endpoints(self, client):
        add_node(client, name="Doomed")
        assert client.post("/api/undo").get_json()["canRedo"] is True
        assert client.get("/api/nodes/root_0").status_code == 404
        assert client.post("/api/redo").status_code == 200
        assert client.get("/api/nodes/root_0").status_code == 200

    def test_undo_with_empty_history(self, client):
        response = client.post("/api/undo")
        assert response.status_code == 400
        assert response.get_json()["error"]["code"] == "NOTHING_TO_UNDO"

    def test_redo_with_empty_history(self, client):
        response = client.post("/api/redo")
        assert response.status_code == 400
        assert response.get_json()["error"]["code"] == "NOTHING_TO_REDO"

    def test_metadata_mode_change_recalculates(self, client):
        add_node(client, name="A", probability=0.5)
        add_node(client, "root_0", name="A1", probability=0.5)
        response = client.post("/api/metadata", json={"mode": "ETA"})
        assert response.status_code == 200
        assert response.get_json()["metadata"]["mode"] == "ETA"
        # ETA: running product down from the root (1.0 * 0.5 * 0.5).
        assert client.get("/api/nodes/root_0_0").get_json()["node"][
            "calculatedProbability"
        ] == 0.25

    def test_metadata_rejects_a_bad_mode(self, client):
        response = client.post("/api/metadata", json={"mode": "PHA"})
        assert response.status_code == 400
        assert response.get_json()["error"]["code"] == "INVALID_FIELD"

    def test_new_refuses_to_discard_unsaved_changes(self, client):
        add_node(client)
        response = client.post("/api/new")
        assert response.status_code == 409
        assert response.get_json()["error"]["code"] == "UNSAVED_CHANGES"

    def test_new_with_force(self, client):
        add_node(client)
        body = client.post("/api/new", json={"force": True}).get_json()
        assert body["dirty"] is False
        assert body["canUndo"] is False
        assert body["tree"]["children"] == []

    def test_new_on_a_clean_document(self, client):
        assert client.post("/api/new").status_code == 200

    def test_malformed_json_body(self, client):
        response = client.post(
            "/api/nodes", data="not json", content_type="application/json"
        )
        assert response.status_code == 400
        assert response.get_json()["error"]["code"] == "INVALID_JSON"

    def test_zero_nodes_are_reported(self, client):
        body = add_node(client, name="Impossible", probability=0.0).get_json()
        assert "root_0" in body["zeroNodes"]
