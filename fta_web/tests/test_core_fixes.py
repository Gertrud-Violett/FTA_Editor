"""
Regression tests for the fixes recorded as D13-D20 in fta_web/core/DIVERGENCE.md.

Each test pins one defect from docs/CODE_REVIEW_2026-09.md:

* B-1  node names are XML-escaped in the Graphviz HTML-like label
* B-2  the engine never rounds a probability to zero
* B-4  duplicate node ids are renamed on load and cannot alias each other
* B-5  a link cycle does not saturate the tree to 1.0
* B-8  the top-level node is always ``root``
* D-H1 set_metadata() leaves the date alone unless told otherwise
* D-H3 sanitize_id() gives distinct DOT names to distinct ids
* B-10 the credentials file is created owner-only
"""
import json
import os
import shutil
import stat
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from FTA_Editor_core import FTACore, ROOT_ID  # noqa: E402
from json_viewer import build_dot, gather_nodes, node_label, sanitize_id  # noqa: E402

from fta_web import rendering  # noqa: E402

HAS_NATIVE_DOT = shutil.which("dot") is not None


def leaf(nid, p, name=None, links=None):
    return {
        "id": nid,
        "name": name or nid,
        "type": "Event",
        "probability": p,
        "logicGate": "OR",
        "children": [],
        "links": links or [],
    }


def gate(nid, logic, children, p=1.0, links=None):
    node = leaf(nid, p, links=links)
    node["logicGate"] = logic
    node["children"] = children
    return node


def write_doc(tmp_path, tree, mode="FTA"):
    path = tmp_path / "doc.json"
    path.write_text(
        json.dumps({"title": "T", "date": "2026-01-01", "mode": mode, "tree": tree}),
        encoding="utf-8",
    )
    return path


# --------------------------------------------------------------------------
# B-1: node names are escaped in the HTML-like label
# --------------------------------------------------------------------------


class TestNodeLabelEscaping:
    NAME = "Pressure > 5 bar & T < 50"

    def test_label_escapes_markup_characters(self):
        label = node_label(leaf("n", 0.5, name=self.NAME))
        assert "Pressure &gt; 5 bar &amp; T &lt; 50" in label
        assert self.NAME not in label

    def test_gate_text_is_escaped(self):
        node = leaf("n", 0.5)
        node["logicGate"] = "<b>OR</b>"
        label = node_label(node)
        assert "<b>" not in label
        assert "&lt;b&gt;OR&lt;/b&gt;" in label

    def test_none_and_non_string_names_render(self):
        node = leaf("n", 0.5)
        node["name"] = None
        assert ">n" in node_label(node)  # falls back to the id
        node["name"] = 42
        assert ">42" in node_label(node)

    def test_build_dot_text_carries_escaped_name(self):
        core = FTACore()
        core.set_data(gate(ROOT_ID, "OR", [leaf("root_1", 0.5, name=self.NAME)]))
        core.recalculate_probabilities()
        dot = rendering.build_dot_text(core)
        assert "&gt; 5 bar &amp; T &lt;" in dot

    @pytest.mark.skipif(not HAS_NATIVE_DOT, reason="requires a native Graphviz 'dot'")
    def test_native_dot_accepts_the_escaped_label(self):
        core = FTACore()
        core.set_data(gate(ROOT_ID, "OR", [leaf("root_1", 0.5, name=self.NAME)]))
        core.recalculate_probabilities()
        svg = rendering.render_native(rendering.build_dot_text(core), "svg")
        assert b"<svg" in svg
        assert b"Pressure &gt; 5 bar &amp; T &lt; 50" in svg


# --------------------------------------------------------------------------
# B-2: no rounding in the engine
# --------------------------------------------------------------------------


class TestNoEngineRounding:
    def test_and_gate_keeps_tiny_product(self):
        core = FTACore()
        core.set_data(gate(ROOT_ID, "AND", [leaf("a", 1e-3), leaf("b", 1e-4)]))
        core.recalculate_probabilities()
        assert core.get_data()["calculatedProbability"] == pytest.approx(1e-7)
        assert ROOT_ID not in core.get_zero_probability_nodes()

    def test_or_gate_keeps_tiny_union(self):
        core = FTACore()
        core.set_data(gate(ROOT_ID, "OR", [leaf("a", 3e-7), leaf("b", 4e-7)]))
        core.recalculate_probabilities()
        assert core.get_data()["calculatedProbability"] == pytest.approx(7e-7 - 1.2e-13)
        assert ROOT_ID not in core.get_zero_probability_nodes()

    def test_links_keep_tiny_values(self):
        core = FTACore()
        core.set_data(
            gate(
                ROOT_ID,
                "OR",
                [
                    leaf("a", 1e-3, links=[{"target_id": "b", "relation": "AND"}]),
                    leaf("b", 1e-4),
                ],
            )
        )
        core.recalculate_probabilities()
        assert core.find_node_by_id("a")["calculatedProbability"] == pytest.approx(1e-7)
        assert "a" not in core.get_zero_probability_nodes()

    def test_eta_keeps_tiny_product(self):
        core = FTACore()
        core.set_metadata(mode="ETA")
        core.set_data(gate(ROOT_ID, "OR", [leaf("a", 1e-4)], p=1e-3))
        core.recalculate_probabilities()
        assert core.find_node_by_id("a")["calculatedProbability"] == pytest.approx(1e-7)
        assert "a" not in core.get_zero_probability_nodes()

    def test_float_noise_is_still_trimmed(self):
        core = FTACore()
        core.set_data(gate(ROOT_ID, "OR", [leaf("a", 0.1), leaf("b", 0.2)]))
        core.recalculate_probabilities()
        # 1 - 0.9*0.8 is 0.28000000000000003 in binary; the engine reports 0.28.
        assert core.get_data()["calculatedProbability"] == 0.28

    def test_true_zero_is_still_reported(self):
        core = FTACore()
        core.set_data(gate(ROOT_ID, "AND", [leaf("a", 0.0), leaf("b", 0.5)]))
        core.recalculate_probabilities()
        assert core.get_data()["calculatedProbability"] == 0.0
        assert ROOT_ID in core.get_zero_probability_nodes()


# --------------------------------------------------------------------------
# B-4: duplicate ids
# --------------------------------------------------------------------------


class TestDuplicateIds:
    def test_load_renames_later_duplicates_and_reports(self, tmp_path):
        tree = gate(ROOT_ID, "OR", [leaf("e1", 0.1, name="first"), leaf("e1", 0.9, name="second")])
        core = FTACore()
        ok, err = core.load_from_json(str(write_doc(tmp_path, tree)))
        assert ok, err
        ids = [c["id"] for c in core.get_data()["children"]]
        assert ids == ["e1", "e1_dup2"]
        assert core.get_data()["calculatedProbability"] == pytest.approx(0.91)
        assert [w["kind"] for w in core.last_load_warnings] == ["duplicate_id"]
        assert core.last_load_warnings[0]["old_id"] == "e1"
        assert core.last_load_warnings[0]["new_id"] == "e1_dup2"
        assert core.last_load_warnings[0]["name"] == "second"

    def test_generated_id_never_collides_with_an_existing_one(self, tmp_path):
        tree = gate(ROOT_ID, "OR", [leaf("e1", 0.1), leaf("e1", 0.2), leaf("e1_dup2", 0.3), leaf("e1", 0.4)])
        core = FTACore()
        ok, err = core.load_from_json(str(write_doc(tmp_path, tree)))
        assert ok, err
        ids = [c["id"] for c in core.get_data()["children"]]
        assert ids == ["e1", "e1_dup3", "e1_dup2", "e1_dup4"]
        assert len(set(ids)) == 4

    def test_clean_file_produces_no_warnings(self, tmp_path):
        tree = gate(ROOT_ID, "OR", [leaf("a", 0.1), leaf("b", 0.2)])
        core = FTACore()
        ok, err = core.load_from_json(str(write_doc(tmp_path, tree)))
        assert ok, err
        assert core.last_load_warnings == []

    def test_memo_is_keyed_by_identity_not_id(self):
        # set_data() bypasses the load-time rename, so the engine itself has
        # to cope with two nodes that share an id.
        core = FTACore()
        core.set_data(gate(ROOT_ID, "OR", [leaf("e1", 0.1), leaf("e1", 0.9)]))
        core.recalculate_probabilities()
        first, second = core.get_data()["children"]
        assert first["calculatedProbability"] == pytest.approx(0.1)
        assert second["calculatedProbability"] == pytest.approx(0.9)
        assert core.get_data()["calculatedProbability"] == pytest.approx(0.91)


# --------------------------------------------------------------------------
# B-8: canonical root id
# --------------------------------------------------------------------------


class TestRootId:
    @pytest.mark.parametrize("old_id", ["TOP", "1", 1])
    def test_top_level_id_is_forced_to_root_and_links_follow(self, tmp_path, old_id):
        tree = gate(
            old_id,
            "OR",
            [leaf("a", 0.5, links=[{"target_id": old_id, "relation": "AND"}]), leaf("b", 0.2)],
        )
        core = FTACore()
        ok, err = core.load_from_json(str(write_doc(tmp_path, tree)))
        assert ok, err
        assert core.get_data()["id"] == ROOT_ID
        assert core.find_node_by_id("a")["links"][0]["target_id"] == ROOT_ID
        assert core.find_node_by_id(ROOT_ID) is core.get_data()
        kinds = [w["kind"] for w in core.last_load_warnings]
        assert kinds == ["root_id"]
        assert core.last_load_warnings[0]["old_id"] == str(old_id)

    def test_missing_top_level_id_becomes_root(self, tmp_path):
        tree = gate("x", "OR", [leaf("a", 0.5)])
        del tree["id"]
        core = FTACore()
        ok, err = core.load_from_json(str(write_doc(tmp_path, tree)))
        assert ok, err
        assert core.get_data()["id"] == ROOT_ID
        assert core.get_data()["children"][0]["id"] == "a"

    def test_child_already_named_root_is_renamed_not_the_top(self, tmp_path):
        tree = gate("TOP", "OR", [leaf("root", 0.5)])
        core = FTACore()
        ok, err = core.load_from_json(str(write_doc(tmp_path, tree)))
        assert ok, err
        assert core.get_data()["id"] == ROOT_ID
        assert core.get_data()["children"][0]["id"] == "root_dup2"
        assert [w["kind"] for w in core.last_load_warnings] == ["root_id", "duplicate_id"]


# --------------------------------------------------------------------------
# B-5: link cycles
# --------------------------------------------------------------------------


class TestLinkCycles:
    def test_gate_and_leaf_linked_both_ways_do_not_saturate(self):
        g = gate("G", "OR", [leaf("C", 0.01)], links=[{"target_id": "B", "relation": "OR"}])
        b = leaf("B", 0.02, links=[{"target_id": "G", "relation": "OR"}])
        core = FTACore()
        core.set_data(gate(ROOT_ID, "OR", [g, b]))
        core.recalculate_probabilities()
        vals = {nid: core.find_node_by_id(nid)["calculatedProbability"] for nid in (ROOT_ID, "G", "B", "C")}
        assert all(v < 1.0 for v in vals.values()), vals
        # B is evaluated while G is on the stack, so B sees G's children-only
        # value (0.01); G then ORs its children with the finished B.
        assert vals["B"] == pytest.approx(1 - 0.98 * 0.99)
        assert vals["G"] == pytest.approx(1 - 0.99 * (1 - vals["B"]))
        assert vals[ROOT_ID] == pytest.approx(1 - (1 - vals["G"]) * (1 - vals["B"]))

    def test_leaf_self_link_still_uses_its_own_probability(self):
        core = FTACore()
        core.set_data(gate(ROOT_ID, "OR", [leaf("a", 0.5, links=[{"target_id": "a", "relation": "OR"}])]))
        core.recalculate_probabilities()
        assert core.find_node_by_id("a")["calculatedProbability"] == pytest.approx(0.75)

    def test_descendant_linking_to_ancestor_skips_the_unresolvable_link(self):
        # `a` links to root while root's children are still being evaluated:
        # no children-only value exists yet, so the link is ignored rather
        # than answered with root's ignored base probability of 1.0.
        core = FTACore()
        core.set_data(
            gate(ROOT_ID, "OR", [leaf("a", 0.1, links=[{"target_id": ROOT_ID, "relation": "AND"}]), leaf("b", 0.2)])
        )
        core.recalculate_probabilities()
        assert core.find_node_by_id("a")["calculatedProbability"] == pytest.approx(0.1)
        assert core.get_data()["calculatedProbability"] == pytest.approx(0.28)


# --------------------------------------------------------------------------
# D-H1: set_metadata leaves the date alone
# --------------------------------------------------------------------------


class TestSetMetadata:
    def test_title_only_keeps_date(self):
        core = FTACore()
        core.set_metadata(date="2020-02-29")
        core.set_metadata(title="Renamed")
        assert core.get_metadata() == {"title": "Renamed", "date": "2020-02-29", "mode": "FTA"}

    def test_mode_only_keeps_date(self):
        core = FTACore()
        core.set_metadata(date="2020-02-29")
        core.set_metadata(mode="ETA")
        assert core.get_metadata()["date"] == "2020-02-29"
        assert core.get_metadata()["mode"] == "ETA"

    def test_all_three_are_applied(self):
        core = FTACore()
        core.set_metadata(title="A", date="2021-01-01", mode="ETA")
        assert core.get_metadata() == {"title": "A", "date": "2021-01-01", "mode": "ETA"}


# --------------------------------------------------------------------------
# D-H3: sanitize_id is injective
# --------------------------------------------------------------------------


class TestSanitizeId:
    def test_plain_ids_are_unchanged(self):
        for nid in ("root", "root_1", "a", "Z9_"):
            assert sanitize_id(nid) == nid

    def test_distinct_ids_get_distinct_names(self):
        ids = ["a.b", "a b", "a-b", "a_b", "日本", "日本語", "x/y", "x\\y"]
        out = [sanitize_id(i) for i in ids]
        assert len(set(out)) == len(ids)
        assert all(sanitize_id.__globals__["_ID_UNSAFE"].search(o) is None for o in out)

    def test_hash_suffix_is_stable_and_eight_hex_chars(self):
        out = sanitize_id("a.b")
        assert out == sanitize_id("a.b")
        assert out.startswith("a_b_")
        suffix = out[len("a_b_"):]
        assert len(suffix) == 8
        int(suffix, 16)

    def test_dot_output_keeps_punctuated_ids_apart(self):
        tree = gate(ROOT_ID, "OR", [leaf("a.b", 0.1), leaf("a b", 0.2)])
        nodes, edges = gather_nodes(tree)
        dot = build_dot(nodes, edges)
        assert dot.count("[label=") == 3


# --------------------------------------------------------------------------
# B-10: credentials file permissions
# --------------------------------------------------------------------------


class TestCredentialPermissions:
    def test_file_and_dir_are_owner_only(self, tmp_path, monkeypatch):
        from AI_agent_handler import AICredentialManager

        cred_dir = tmp_path / "home" / ".fta_editor"
        cred_file = cred_dir / "ai_credentials.json"
        monkeypatch.setattr(AICredentialManager, "CREDENTIALS_DIR", cred_dir)
        monkeypatch.setattr(AICredentialManager, "CREDENTIALS_FILE", cred_file)

        manager = AICredentialManager()
        ok, err = manager.save_credentials("sk-test", model="m", provider="OpenAI")
        assert ok, err
        assert json.loads(cred_file.read_text(encoding="utf-8"))["api_key"] == "sk-test"

        if os.name != "nt":
            assert stat.S_IMODE(cred_dir.stat().st_mode) == 0o700
            assert stat.S_IMODE(cred_file.stat().st_mode) == 0o600

        # A second save must overwrite, not append, and stay readable.
        ok, err = manager.save_credentials("sk-other")
        assert ok, err
        loaded, err = manager.load_credentials()
        assert err is None
        assert loaded["api_key"] == "sk-other"

    def test_existing_world_readable_file_is_tightened(self, tmp_path, monkeypatch):
        from AI_agent_handler import AICredentialManager

        cred_dir = tmp_path / ".fta_editor"
        cred_file = cred_dir / "ai_credentials.json"
        cred_dir.mkdir()
        cred_file.write_text("{}", encoding="utf-8")
        os.chmod(cred_file, 0o644)
        monkeypatch.setattr(AICredentialManager, "CREDENTIALS_DIR", cred_dir)
        monkeypatch.setattr(AICredentialManager, "CREDENTIALS_FILE", cred_file)

        ok, err = AICredentialManager().save_credentials("k")
        assert ok, err
        if os.name != "nt":
            assert stat.S_IMODE(cred_file.stat().st_mode) == 0o600
