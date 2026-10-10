"""
Release 1.7.3, fix 2: the AI was not given the headline top-event value.

Confirmed in 1.7.2: the context sent to the model called the root's tree-walk
``calculatedProbability`` the "Top-level Probability". For a tree with
repeated events the editor's headline is the MCUB, so the model "found" the
double counting the tool already corrects.

``ai_bridge.analysis_section`` is appended to the context in FTA mode, on the
chat, analyze and update paths. Fixtures and helpers: ``support_1_7_3.py``.
"""
import copy
import re
import threading
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fta_web import ai_bridge, engine  # noqa: E402
from fta_web.numfmt import format_prob  # noqa: E402
from fta_web.state import get_state  # noqa: E402
from fta_web.tests.support_1_7_3 import *  # noqa: E402,F401,F403


def captured(provider, monkeypatch, reply="Noted."):
    """Mock the provider; returns the list its message arrays land in."""
    seen = []

    def send_message(api_key, endpoint, model, messages, max_tokens=2000):
        seen.append(copy.deepcopy(messages))
        return reply, None

    monkeypatch.setattr(provider, "send_message", send_message)
    return seen


def context_sent(seen):
    return seen[-1][-1]["content"]


class TestAnalysisSection:
    def test_challenger_the_headline_is_the_mcub_and_says_so(self):
        core = core_of(CHALLENGER)
        summary = engine.summary(core.get_data(), core.analysis)

        text = ai_bridge.analysis_section(core.get_data(), core.mode, core.analysis)
        lines = text.split("\n")

        assert lines[0] == ai_bridge.ANALYSIS_HEADER and lines[-1] == ai_bridge.ANALYSIS_FOOTER
        assert summary["headlineMethod"] == "mcub"
        assert format_prob(summary["headline"], 3) == "0.0684"
        assert lines[1] == ("Top event probability (headline): 0.0683535 by MCUB (min-cut upper "
                            "bound over the minimal cut sets).")
        assert lines[2] == ("The headline already counts each repeated event once, so the double "
                            "counting in the tree-walk value is corrected in it.")
        assert lines[3].startswith("Tree walk: 0.0349375 (every branch taken as independent;")
        assert lines[4] == "Rare-event approximation (sum of the cut sets): 0.06875."

    def test_challenger_repeated_events_by_id_and_name(self):
        core = core_of(CHALLENGER)
        summary = engine.summary(core.get_data(), core.analysis)

        text = ai_bridge.analysis_section(core.get_data(), core.mode, core.analysis)

        (line,) = [l for l in text.split("\n") if l.startswith("Repeated events")]
        assert line.startswith("Repeated events (2), each reached by more than one branch: ")
        assert len(summary["repeatedEvents"]) == 2
        for event in summary["repeatedEvents"]:
            assert '%s "%s"' % (event["id"], event["name"]) in line

    def test_challenger_cut_sets_with_probability_and_share(self):
        core = core_of(CHALLENGER)
        from fta_web import cutsets

        full = cutsets.compute(core.get_data(), core.analysis)

        lines = ai_bridge.analysis_section(core.get_data(), core.mode, core.analysis).split("\n")

        start = lines.index("Minimal cut sets: 3; the top 3 by probability, as probability "
                            "(share of the rare-event sum): events")
        rows = lines[start + 1:start + 4]
        assert [row.split(": ")[0] for row in rows] == [
            "1. 0.0625 (90.9%)", "2. 0.005 (7.27%)", "3. 0.00125 (1.82%)"]
        for row, cut_set in zip(rows, full["cutSets"]):
            assert row.count(" AND ") == cut_set["order"] - 1
            for event in cut_set["events"]:
                assert '%s "%s"' % (event["id"], event["name"]) in row

    def test_challenger_approximations_and_mission_time(self):
        core = core_of(CHALLENGER)

        lines = ai_bridge.analysis_section(core.get_data(), core.mode, core.analysis).split("\n")

        assert "Approximations: none." in lines
        assert lines[-2] == "Mission time: 8760 h (shown to the user in h)."
        assert not any("truncated" in l or "first" in l for l in lines)

    def test_a_tree_without_repeats_says_tree_walk(self):
        tree = node("root", type="Root", logicGate="OR", probability=1.0, children=[
            node("a", probability=0.1), node("b", probability=0.2)])
        core = simple_core(tree)

        lines = ai_bridge.analysis_section(core.get_data(), "FTA", core.analysis).split("\n")

        assert lines[1] == ("Top event probability (headline): 0.28 by tree walk (no event is "
                            "repeated, so no branch is counted twice).")
        assert lines[2] == "MCUB (min-cut upper bound) for comparison: 0.28."
        assert "Repeated events: none." in lines
        assert not any("already counts" in l for l in lines)
        assert "1. 0.2 (66.7%): b \"B\"" in lines and "2. 0.1 (33.3%): a \"A\"" in lines

    def test_at_most_ten_cut_sets_and_the_total(self):
        tree = node("root", type="Root", logicGate="OR", probability=1.0, children=[
            node("e%02d" % i, probability=0.001 * (i + 1)) for i in range(14)])
        core = simple_core(tree)

        lines = ai_bridge.analysis_section(core.get_data(), "FTA", core.analysis).split("\n")

        assert any(l.startswith("Minimal cut sets: 14; the top 10 by probability") for l in lines)
        numbered = [l for l in lines if re.match(r"\d+\. ", l)]
        assert len(numbered) == ai_bridge.ANALYSIS_TOP_CUT_SETS == 10
        assert numbered[0].startswith("1. 0.014 (")

    def test_approximations_and_truncation_are_flagged(self):
        tree = node("root", type="Root", logicGate="OR", probability=1.0, children=[
            node("p", type="Gate", logicGate="AND", gateType="PAND", probability=1.0, children=[
                node("a", probability=0.1), node("b", probability=0.2)]),
            node("x", type="Gate", logicGate="OR", gateType="XOR", probability=1.0, children=[
                node("c", probability=0.1), node("d", probability=0.2), node("e", probability=0.3)]),
        ])
        core = simple_core(tree)
        core.analysis["cutsets"]["maxOrder"] = 1
        core.analysis["missionTime"] = 100.0
        core.analysis["timeUnit"] = "y"

        text = ai_bridge.analysis_section(core.get_data(), "FTA", core.analysis)

        (approx,) = [l for l in text.split("\n") if l.startswith("Approximations: ")]
        assert "priority-AND gate p is computed as product/n!" in approx
        assert "XOR gate x has other than two inputs" in approx
        assert "non-coherent (the cut sets treat XOR as OR)" in approx
        assert "Cut sets truncated by the document's limits (order): the MCUB is from the sets kept." in text
        assert "Mission time: 100 h (shown to the user in y)." in text
        assert "by MCUB" in text

    def test_a_capped_headline_says_so(self, monkeypatch):
        tree = node("root", type="Root", logicGate="OR", probability=1.0, children=[
            node("e%d" % i, probability=0.01, links=[link("e0")] if i else []) for i in range(6)])
        core = simple_core(tree)
        core.analysis["cutsets"]["maxCount"] = 5000
        monkeypatch.setitem(engine.SUMMARY_LIMITS, "maxCount", 2)

        text = ai_bridge.analysis_section(core.get_data(), "FTA", core.analysis)

        assert "The headline is computed from the first 2 cut sets only" in text

    def test_it_is_deterministic_and_does_not_touch_the_tree(self):
        core = core_of(CHALLENGER)
        before = copy.deepcopy(core.get_data())

        first = ai_bridge.analysis_section(core.get_data(), core.mode, core.analysis)
        second = ai_bridge.analysis_section(copy.deepcopy(core.get_data()), core.mode,
                                            copy.deepcopy(core.analysis))

        assert first == second and core.get_data() == before
        assert len(first) < 2500, "the section is sent with every message"

    def test_japanese_names_are_kept_and_long_ones_cut(self):
        core = core_of(CHALLENGER_JA)
        name = engine.summary(core.get_data(), core.analysis)["repeatedEvents"][0]["name"]
        text = ai_bridge.analysis_section(core.get_data(), core.mode, core.analysis)
        assert not name.isascii()
        assert name in text and "by MCUB" in text

        long_tree = node("root", type="Root", logicGate="OR", probability=1.0, children=[
            node("a", name="x" * 200 + "\nsecond line", probability=0.1)])
        long_text = ai_bridge.analysis_section(simple_core(long_tree).get_data(), "FTA", None)
        assert 'a "%s…"' % ("x" * (ai_bridge.ANALYSIS_NAME_CHARS - 1)) in long_text
        assert "second line" not in long_text

    @pytest.mark.parametrize("mode", ["ETA", "eta", " Eta "])
    def test_nothing_in_eta_mode(self, mode):
        core = core_of(TMI)

        assert ai_bridge.analysis_section(core.get_data(), mode, core.analysis) == ""

    def test_nothing_when_the_cut_sets_fail(self, monkeypatch):
        core = core_of(CHALLENGER)
        from fta_web import cutsets

        def boom(*args, **kwargs):
            raise cutsets.CutsetError("too large")

        monkeypatch.setattr(cutsets, "compute", boom)
        assert ai_bridge.analysis_section(core.get_data(), core.mode, core.analysis) == ""

        monkeypatch.setattr(ai_bridge, "summary_with_cut_sets", boom)
        assert ai_bridge.analysis_section(core.get_data(), core.mode, core.analysis) == ""

    def test_one_expansion_within_the_summarys_budget(self, monkeypatch):
        """The section reuses the summary's caps and 2 s budget, once."""
        core = core_of(CHALLENGER)
        from fta_web import cutsets

        calls = []
        real = cutsets.compute

        def counting(tree, analysis=None, limits=None, structure=None):
            calls.append(dict(limits or {}))
            return real(tree, analysis, limits, structure)

        monkeypatch.setattr(cutsets, "compute", counting)
        ai_bridge.analysis_section(core.get_data(), core.mode, core.analysis)

        assert calls == [{"maxCount": 2000, "timeBudgetS": 2.0}]


class TestTheContextTheModelIsSent:
    @pytest.mark.parametrize("path,payload", [
        ("/api/ai/chat", {"message": "What is the top event probability?"}),
        ("/api/ai/analyze", {}),
        ("/api/ai/update", {}),
    ])
    def test_every_path_carries_the_results(self, configured, provider, monkeypatch, path, payload):
        state = open_file(CHALLENGER)
        expected = ai_bridge.analysis_section(
            state.core.get_data(), state.core.mode, state.core.analysis)
        seen = captured(provider, monkeypatch)

        configured.post(path, json=payload)

        context = context_sent(seen)
        assert expected in context
        assert "by MCUB" in expected
        # Inside the structure block, after the tree, before the reminders.
        assert context.index("--- Current FTA Structure ---") < context.index(
            ai_bridge.ANALYSIS_HEADER) < context.index("--- End FTA Structure ---")
        # The handler's own first line no longer passes the tree walk off as
        # the top-level probability.
        assert "- Top-level Probability (tree walk): 0.0349375" in context
        assert "- Top-level Probability: " not in context

    def test_a_plain_tree_is_told_tree_walk(self, configured, provider, monkeypatch):
        install(node("root", type="Root", logicGate="OR", probability=1.0, children=[
            node("a", probability=0.1), node("b", probability=0.2)]))
        seen = captured(provider, monkeypatch)

        configured.post("/api/ai/chat", json={"message": "hello"})

        assert "by tree walk (no event is repeated" in context_sent(seen)
        assert "by MCUB" not in context_sent(seen)

    @pytest.mark.parametrize("path,payload", [
        ("/api/ai/chat", {"message": "hello"}),
        ("/api/ai/analyze", {}),
        ("/api/ai/update", {}),
    ])
    def test_eta_mode_is_unchanged(self, configured, provider, monkeypatch, path, payload):
        """Byte for byte what the vendored handler alone would send."""
        state = open_file(TMI)
        assert state.core.mode == "ETA"
        from AI_agent_handler import AIAgentHandler

        plain = AIAgentHandler()
        plain.set_fta_context(copy.deepcopy(state.core.get_data()), state.core.mode,
                              state.core.title)
        seen = captured(provider, monkeypatch)

        configured.post(path, json=payload)

        context = context_sent(seen)
        assert "Analysis results" not in context
        assert ("--- Current FTA Structure ---\n%s\n--- End FTA Structure ---"
                % plain.current_fta_context) in context

    def test_the_section_is_for_one_call_only(self, configured, provider, monkeypatch):
        open_file(CHALLENGER)
        seen = captured(provider, monkeypatch)
        configured.post("/api/ai/chat", json={"message": "one"})
        assert ai_bridge.get_handler().analysis_section == ""

        open_file(TMI)
        configured.post("/api/ai/chat", json={"message": "two"})

        assert "Analysis results" in context_sent(seen[:1])
        assert "Analysis results" not in context_sent(seen)

    def test_it_is_not_kept_in_the_conversation_history(self, configured, provider, monkeypatch):
        open_file(CHALLENGER)
        captured(provider, monkeypatch)

        configured.post("/api/ai/chat", json={"message": "remember this"})

        history = ai_bridge.get_handler().conversation_history
        assert [m["content"] for m in history] == ["remember this", "Noted."]

    def test_a_failing_section_does_not_cost_the_call(self, configured, provider, monkeypatch):
        open_file(CHALLENGER)
        seen = captured(provider, monkeypatch)
        monkeypatch.setattr(ai_bridge, "summary_with_cut_sets",
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no")))

        response = configured.post("/api/ai/chat", json={"message": "hello"})

        assert response.status_code == 200 and body(response)["reply"] == "Noted."
        assert "Analysis results" not in context_sent(seen)
        assert "- Top-level Probability: 0.0349375" in context_sent(seen)

    def test_the_document_lock_is_free_while_the_results_are_computed(self, configured, provider,
                                                                     monkeypatch):
        open_file(CHALLENGER)
        captured(provider, monkeypatch)
        state = get_state()
        held = []
        real = ai_bridge.summary_with_cut_sets

        def probing(tree, analysis=None):
            grabbed = []
            thread = threading.Thread(
                target=lambda: grabbed.append(state.lock.acquire(timeout=2)) or state.lock.release())
            thread.start()
            thread.join(5)
            held.append(grabbed == [True])
            return real(tree, analysis)

        monkeypatch.setattr(ai_bridge, "summary_with_cut_sets", probing)

        configured.post("/api/ai/chat", json={"message": "hello"})

        assert held == [True], "another thread must be able to take state.lock meanwhile"
