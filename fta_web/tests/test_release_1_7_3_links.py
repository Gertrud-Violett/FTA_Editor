"""
Release 1.7.3, fix 1: applying an AI suggestion dropped its link changes and
still said "applied".

Confirmed in 1.7.2: the vendored handler's add/edit write name, type,
probability, gate and notes; ``links`` in a suggestion's data was ignored. A
suggestion with name and links was reported applied with the links lost, a
links-only edit was refused with "No valid fields to update" -- and a
suggestion with a link in it did not even survive the parser (divergence D29,
tested in ``test_divergence_fixes.py``).

``ai_bridge.apply_change`` now applies them: a suggestion as a whole or not
at all. Fixtures and helpers: ``support_1_7_3.py``.
"""
import copy
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from AI_agent_handler import AIProposedChange  # noqa: E402

from fta_web import ai_bridge  # noqa: E402
from fta_web.tests.support_1_7_3 import *  # noqa: E402,F401,F403


class TestApplyingLinks:
    def test_a_link_is_added_and_the_rest_of_the_list_kept(self, configured):
        install(small_tree())
        indices = propose(edit("a", id="a", name="A", links=[link("c"), link("d", "AND")]))

        response = apply(configured, indices)

        assert response.status_code == 200, body(response)
        assert links_of(configured, "a") == [link("c"), link("d", "AND")]
        (record,) = body(response)["applied"]
        assert record["message"].endswith("links") and record["ignored"] == []

    def test_a_link_is_removed_by_leaving_it_out(self, configured):
        install(small_tree())

        response = apply(configured, propose(edit("a", id="a", name="A", links=[])))

        assert response.status_code == 200, body(response)
        assert links_of(configured, "a") == []

    def test_the_list_replaces_the_one_the_node_had(self, configured):
        install(small_tree())

        apply(configured, propose(edit("a", id="a", name="A", links=[link("b", "and")])))

        # Normalised as PATCH /api/nodes stores a link.
        assert links_of(configured, "a") == [link("b", "AND")]

    def test_an_edit_without_links_leaves_them_alone(self, configured):
        install(small_tree())

        response = apply(configured, propose(edit("a", id="a", name="Renamed")))

        assert response.status_code == 200
        assert links_of(configured, "a") == [link("c")]
        assert find(body(response)["tree"], "a")["name"] == "Renamed"

    def test_null_links_mean_no_change_to_them(self, configured):
        install(small_tree())

        apply(configured, propose(edit("a", id="a", name="A2", links=None)))

        assert links_of(configured, "a") == [link("c")]

    def test_an_edit_of_the_links_alone_is_applied(self, configured):
        """1.7.2 answered "No valid fields to update"."""
        install(small_tree())

        response = apply(configured, propose(edit("b", links=[link("c")])))

        assert response.status_code == 200, body(response)
        assert links_of(configured, "b") == [link("c")]
        assert body(response)["applied"][0]["message"] == "✓ Updated 'B': links"

    def test_the_handlers_refusal_is_the_one_this_relies_on(self):
        """``apply_change`` recognises a links-only edit by this message."""
        handler = ai_bridge.get_handler()
        core = simple_core(small_tree())

        assert handler.apply_change_to_fta(core, edit("b", links=[link("c")])) == (
            False, ai_bridge.NO_FIELDS_MESSAGE)

    def test_name_and_links_are_applied_together(self, configured):
        install(small_tree())

        response = apply(configured, propose(
            edit("b", id="b", name="Both", probability=0.25, links=[link("d")])))

        changed = find(body(response)["tree"], "b")
        assert (changed["name"], changed["probability"], changed["links"]) == (
            "Both", 0.25, [link("d")])
        assert body(response)["applied"][0]["message"] == "✓ Updated 'Both': name, probability, links"

    def test_a_new_node_gets_its_links(self, configured):
        install(small_tree())

        response = apply(configured, propose(add(
            "root", id="ice", name="Ice", type="Event", probability=0.05, logicGate="",
            notes="", links=[link("c", "AND"), link("d")])))

        assert response.status_code == 200, body(response)
        assert links_of(configured, "ice") == [link("c", "AND"), link("d")]
        assert body(response)["applied"][0]["message"] == "✓ Added node 'Ice' to parent, with 2 links"

    def test_a_link_may_point_at_a_node_added_earlier_in_the_batch(self, configured):
        install(small_tree())
        indices = propose(
            add("root", id="cold", name="Cold", probability=0.5),
            edit("b", id="b", name="B", links=[link("cold")]),
        )

        response = apply(configured, indices)

        assert [r["index"] for r in body(response)["applied"]] == indices
        assert links_of(configured, "b") == [link("cold")]

    def test_the_numbers_follow_the_new_link(self, configured):
        """Recalculated, and the headline becomes the MCUB: b now shares c."""
        install(small_tree())
        before = body(configured.get("/api/analysis/summary"))

        response = apply(configured, propose(edit("b", id="b", name="B", links=[link("c", "AND")])))

        tree = body(response)["tree"]
        assert find(tree, "b")["calculatedProbability"] == pytest.approx(0.2 * 0.3)
        after = body(configured.get("/api/analysis/summary"))
        assert before["headline"] != after["headline"]
        assert "c" in [e["id"] for e in after["repeatedEvents"]]

    def test_it_is_one_undo_step_with_the_rest_of_the_batch(self, configured):
        state = install(small_tree())
        original = copy.deepcopy(state.core.get_data())
        indices = propose(
            edit("a", id="a", name="A1", links=[link("d")]),
            add("root", id="ice", name="Ice", probability=0.05, links=[link("c")]),
            edit("b", links=[link("c"), link("d", "AND")]),
        )

        response = apply(configured, indices)

        assert len(body(response)["applied"]) == 3
        assert body(response)["dirty"] is True and body(response)["canUndo"] is True
        undone = body(configured.post("/api/undo"))
        assert undone["tree"] == original
        assert undone["canUndo"] is False
        redone = body(configured.post("/api/redo"))["tree"]
        assert find(redone, "a")["links"] == [link("d")]
        assert find(redone, "ice")["links"] == [link("c")]
        assert find(redone, "b")["links"] == [link("c"), link("d", "AND")]


class TestASuggestionIsAppliedWholeOrNotAtAll:
    """The policy (``ai_bridge`` module docstring): an invalid link rejects
    that suggestion -- its other fields too -- with the reason; the rest of
    the batch is applied."""

    def refused(self, client, change):
        install(small_tree())
        before = body(client.get("/api/state"))["tree"]
        response = apply(client, propose(change))
        assert response.status_code == 400, body(response)
        error = body(response)["error"]
        assert error["code"] == "AI_CHANGE_REJECTED"
        state = body(client.get("/api/state"))
        assert state["tree"] == before, "a rejected suggestion must change nothing"
        assert state["dirty"] is False and state["canUndo"] is False
        (record,) = error["detail"]["rejected"]
        return record["message"]

    def test_an_unknown_target(self, configured):
        message = self.refused(configured, edit("b", id="b", name="Renamed", links=[link("ghost")]))

        assert message == ("Not applied: the suggested link target 'ghost' does not exist "
                           "in this analysis.")

    def test_a_link_to_itself(self, configured):
        message = self.refused(configured, edit("b", id="b", name="B", links=[link("b")]))

        assert message == "Not applied: the suggested link points from 'b' to itself."

    def test_a_new_node_linked_to_itself(self, configured):
        message = self.refused(configured, add("root", id="ice", name="Ice", links=[link("ice")]))

        assert "to itself" in message

    def test_the_same_link_twice(self, configured):
        message = self.refused(configured, edit(
            "b", id="b", name="B", links=[link("c"), link("c", "or")]))

        assert message.startswith("Not applied: the suggested links are not valid.")
        assert "may appear only once" in message

    def test_a_relation_that_is_not_and_or_or(self, configured):
        message = self.refused(configured, edit("b", id="b", name="B", links=[link("c", "XOR")]))

        assert "'relation' must be 'AND' or 'OR'" in message

    @pytest.mark.parametrize("links", ["c", [["c", "OR"]], [{"relation": "OR"}], {"target_id": "c"}])
    def test_links_that_are_not_a_list_of_links(self, configured, links):
        message = self.refused(configured, edit("b", id="b", name="B", links=links))

        assert message.startswith("Not applied: the suggested links are not valid.")

    @pytest.mark.parametrize("data,needle", [
        ({"type": "Condition"}, "the suggested type 'Condition' is not Event, Gate or Intermediate"),
        ({"logicGate": "XOR"}, "the suggested gate 'XOR' is not AND or OR"),
    ])
    def test_a_field_the_handler_would_have_skipped(self, configured, data, needle):
        """The vendored edit skips such a field and reports the others as
        updated; the suggestion is refused instead."""
        message = self.refused(configured, edit("b", id="b", name="Renamed", **data))

        assert needle in message

    def test_a_new_node_with_a_bad_link_is_not_added(self, configured):
        message = self.refused(configured, add("root", id="ice", name="Ice", links=[link("ghost")]))

        assert "'ghost' does not exist" in message
        assert find(body(configured.get("/api/state"))["tree"], "ice") is None

    def test_the_rest_of_the_batch_is_still_applied(self, configured):
        install(small_tree())
        indices = propose(
            edit("a", id="a", name="Kept change", links=[link("d")]),
            edit("b", id="b", name="Lost change", links=[link("ghost")]),
        )

        response = apply(configured, indices)

        assert response.status_code == 200, body(response)
        result = body(response)
        assert [r["index"] for r in result["applied"]] == [indices[0]]
        assert [r["index"] for r in result["rejected"]] == [indices[1]]
        assert "'ghost' does not exist" in result["rejected"][0]["message"]
        assert find(result["tree"], "a")["name"] == "Kept change"
        # Not its name either: nothing of a rejected suggestion is written.
        assert find(result["tree"], "b")["name"] == "B"
        assert find(result["tree"], "b")["links"] == []

    def test_what_a_suggestion_never_changes_is_named_not_claimed(self, configured):
        install(small_tree())
        change = add("root", id="sub", name="Sub", type="Gate", logicGate="AND",
                     calculatedProbability=0.5, gateType="KOFN",
                     children=[{"id": "leaf", "name": "Leaf"}], links=[])

        response = apply(configured, propose(change))

        (record,) = body(response)["applied"]
        assert record["ignored"] == ["children", "gateType"]
        assert record["message"].endswith("Not changed by a suggestion: children, gateType")
        added = find(body(response)["tree"], "sub")
        assert added["children"] == [] and "gateType" not in added

    def test_an_ordinary_suggestion_ignores_nothing(self, configured):
        install(small_tree())
        change = add("root", id="plain", name="Plain", type="Event", probability=0.1,
                     logicGate="", notes="", children=[], calculatedProbability=0.1)

        (record,) = body(apply(configured, propose(change)))["applied"]

        assert record["ignored"] == []
        assert record["message"] == "✓ Added node 'Plain' to parent"


class TestTheOtherAiPathsAreAsTheyWere:
    def test_a_deleted_node_takes_the_links_into_it_with_it(self, configured):
        """Unchanged from 1.7.2: the AI's delete strips links to what it removed."""
        install(small_tree())
        indices = propose(
            edit("b", links=[link("c")]),
            AIProposedChange("delete", "c", "delete c", {"id": "c"}),
        )

        response = apply(configured, indices)

        result = body(response)
        assert len(result["applied"]) == 2
        assert find(result["tree"], "c") is None
        assert find(result["tree"], "a")["links"] == []
        assert find(result["tree"], "b")["links"] == []
        removed = [w for w in result["sessionWarnings"] if w.get("code") == "LINKS_REMOVED"]
        assert len(removed) == 2

    def test_a_reply_with_a_link_is_parsed_previewed_and_applied(self, configured, provider,
                                                                 monkeypatch):
        """End to end, through the vendored parser (D29) and the real apply."""
        install(small_tree())
        reply = (
            "B shares the cause of C.\n\n"
            "SUGGESTION: Link B to C\n"
            "DESCRIPTION: One cause acts on both\n"
            "ACTION: edit\n"
            "TARGET: b\n"
            'DATA: {"id": "b", "name": "B", "links": [{"target_id": "c", "relation": "OR"}]}\n'
        )
        monkeypatch.setattr(provider, "send_message", lambda *a, **k: (reply, None))

        chat = body(configured.post("/api/ai/chat", json={"message": "anything shared?"}))

        (change,) = chat["changes"]
        assert change["data"]["links"] == [link("c")]
        assert change["linkChanges"] == {
            "added": [{"targetId": "c", "targetName": "C", "relation": "OR"}],
            "removed": [],
            "problem": None,
        }
        applied = body(apply(configured, [change["index"]]))
        assert find(applied["tree"], "b")["links"] == [link("c")]

    def test_update_fta_still_installs_links_as_it_did(self, configured, provider, monkeypatch):
        """``/api/ai/update`` replaces the whole tree; its links were never lost."""
        install(small_tree())
        updated = small_tree()
        updated["children"][1]["links"] = [link("d", "AND")]
        monkeypatch.setattr(provider, "send_message", lambda *a, **k: (json.dumps(updated), None))

        response = configured.post("/api/ai/update", json={})

        assert response.status_code == 200, body(response)
        result = body(response)
        assert find(result["tree"], "b")["links"] == [link("d", "AND")]
        assert find(result["tree"], "a")["links"] == [link("c")]
        assert "ignored" not in result and result["canUndo"] is True

    def test_update_fta_still_refuses_a_duplicate_link(self, configured, provider, monkeypatch):
        install(small_tree())
        updated = small_tree()
        updated["children"][1]["links"] = [link("d"), link("d")]
        monkeypatch.setattr(provider, "send_message", lambda *a, **k: (json.dumps(updated), None))

        response = configured.post("/api/ai/update", json={})

        assert response.status_code == 400
        assert body(response)["error"]["code"] == "AI_UPDATE_REJECTED"

    def test_patch_nodes_validates_links_exactly_as_before(self, client):
        """The validator moved to node_schema; PATCH still allows a dangling
        link and a self-link (the AI's suggestions are held to more)."""
        install(small_tree())

        ok = client.patch("/api/nodes/b", json={"links": [
            {"targetId": "nowhere", "relation": "and"}, {"target_id": "b"}]})
        twice = client.patch("/api/nodes/b", json={"links": [link("c"), link("c")]})

        assert ok.status_code == 200
        assert find(body(ok)["tree"], "b")["links"] == [link("nowhere", "AND"), link("b")]
        assert twice.status_code == 400
        assert body(twice)["error"]["detail"] == {"field": "links", "index": 1}


class TestTheCardShowsWhatWouldChange:
    def test_additions_and_removals_against_the_tree_shown(self):
        tree = simple_core(small_tree()).get_data()
        change = edit("a", id="a", name="A", links=[link("d", "AND"), link("b")])

        assert ai_bridge.link_changes(change, tree) == {
            "added": [{"targetId": "d", "targetName": "D", "relation": "AND"},
                      {"targetId": "b", "targetName": "B", "relation": "OR"}],
            "removed": [{"targetId": "c", "targetName": "C", "relation": "OR"}],
            "problem": None,
        }

    def test_the_same_list_is_no_change(self):
        tree = simple_core(small_tree()).get_data()

        assert ai_bridge.link_changes(edit("a", links=[link("c", "or")]), tree) == {
            "added": [], "removed": [], "problem": None}

    def test_a_change_that_does_not_set_links_has_no_preview(self):
        tree = simple_core(small_tree()).get_data()

        assert ai_bridge.link_changes(edit("a", id="a", name="X"), tree) is None
        assert ai_bridge.link_changes(AIProposedChange("delete", "a", "", {"id": "a"}), tree) is None
        assert "linkChanges" not in ai_bridge.change_view(edit("a", id="a", name="X"), 0, tree)

    def test_a_target_nobody_creates_is_a_problem_before_apply(self):
        tree = simple_core(small_tree()).get_data()

        preview = ai_bridge.link_changes(edit("b", links=[link("ghost")]), tree)

        assert preview["added"] == [{"targetId": "ghost", "targetName": None, "relation": "OR"}]
        assert "'ghost' does not exist" in preview["problem"]

    def test_a_target_an_earlier_suggestion_adds_is_known(self):
        tree = simple_core(small_tree()).get_data()
        earlier = add("root", id="cold", name="Cold")

        preview = ai_bridge.link_changes(edit("b", links=[link("cold")]), tree, [earlier])

        assert preview == {
            "added": [{"targetId": "cold", "targetName": "Cold", "relation": "OR"}],
            "removed": [], "problem": None}

    def test_chat_js_renders_the_link_lines(self):
        source = (STATIC / "chat.js").read_text(encoding="utf-8")

        assert "const links = linkLines(change);" in source
        for key in ("ai.changes.linkAdd", "ai.changes.linkRemove", "ai.changes.linkNone",
                    "ai.changes.linkProblem", "ai.changes.rejectedOne", "ai.changes.ignoredOne"):
            assert "'%s'" % key in source, key
        apply_src = re.search(r"async function applyChanges\(handle, total\) \{(.*?)\n  \}\n",
                              source, re.S).group(1)
        assert "showRejected(result.rejected)" in apply_src
        assert "record.ignored" in apply_src


needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


@needs_node
def test_link_lines_in_the_card_say_what_is_added_and_removed():
    """chat.js ``linkLines`` and ``linkTarget``, run in node."""
    source = (STATIC / "chat.js").read_text(encoding="utf-8")
    functions = "\n".join(
        re.search(r"^  function %s\(.*?\n  \}\n" % name, source, re.S | re.M).group(0)
        for name in ("linkTarget", "linkLines"))
    first = re.search(r"^function firstString\(.*?\n\}\n", source, re.S | re.M).group(0)
    cases = [
        {"linkChanges": {"added": [{"targetId": "c", "targetName": "Cold", "relation": "OR"}],
                         "removed": [{"targetId": "d", "targetName": None, "relation": "AND"}],
                         "problem": None}},
        {"linkChanges": {"added": [], "removed": [], "problem": None}},
        {"linkChanges": {"added": [{"targetId": "g", "targetName": None, "relation": "OR"}],
                         "removed": [], "problem": "no such node"}},
        {"data": {"name": "x"}},
    ]
    script = (
        "const t = (key, vars) => key + ' ' + JSON.stringify(vars || {});\n"
        + first + functions
        + "\nconsole.log(JSON.stringify(%s.map((c) => linkLines(c))));" % json.dumps(cases)
    )
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True,
                         encoding="utf-8", check=True).stdout
    lines = json.loads(out)

    assert [[line["kind"] for line in case] for case in lines] == [
        ["add", "remove"], ["none"], ["add", "problem"], []]
    assert lines[0][0]["text"] == 'ai.changes.linkAdd {"relation":"OR","name":"Cold (c)"}'
    assert lines[0][1]["text"] == 'ai.changes.linkRemove {"relation":"AND","name":"d"}'
    assert lines[2][1]["text"] == 'ai.changes.linkProblem {"reason":"no such node"}'
