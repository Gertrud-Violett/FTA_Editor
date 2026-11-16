"""
The example analyses in ``fta_web/examples/``, which the packaged build ships
as ``_internal/examples/``.

``sampleFTA.json`` is the pinned legacy sample (``test_vendor_integrity.py``).
The others are worked examples of well-documented accidents, a starting point
for a user's own analysis, each in English and in Japanese:

  challenger_fta_en.json, _ja.json      a fault tree of the loss of the Space
                                        Shuttle Challenger (STS 51-L, 1986)
  tmi2_eta_en.json, tmi2_eta_ja.json    an event tree of the accident at
                                        Three Mile Island Unit 2 (1979)

What is pinned here, so that an edit of one file cannot quietly break it:

* each file opens without a repair and validates without an error or warning;
* it is in the format Save writes, so opening and saving it changes nothing;
* the two languages are one analysis: only names, notes and the title differ;
* every node is explained, and the document says its probabilities are
  illustrative;
* the numbers are the ones worked out by hand below, from the probabilities
  in the file and nothing else;
* the documentation names every file.
"""
import itertools
import json
import math
import re
from fractions import Fraction
from pathlib import Path

import pytest

from fta_web import cutsets, engine, lint
from fta_web.numfmt import format_prob

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = REPO_ROOT / "fta_web" / "examples"

#: stem -> (mode, a word the title must carry to say the numbers are examples)
PAIRS = {
    "challenger_fta": "FTA",
    "tmi2_eta": "ETA",
}
LANGUAGES = {"en": "illustrative", "ja": "例示"}
FILES = ["%s_%s.json" % (stem, lang) for stem in PAIRS for lang in LANGUAGES]

#: What a translation may change. Everything else is the analysis itself.
TEXT_KEYS = ("name", "notes")
CJK = re.compile(r"[぀-ヿ一-鿿]")


def read(name):
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def load(name):
    core = engine.WebCore()
    ok, error = core.load_from_json(str(EXAMPLES / name))
    assert ok, error
    return core


def walk(node, path=()):
    """Every node with the names of the nodes above it, pre-order."""
    yield node, path
    for child in node.get("children") or []:
        yield from walk(child, path + (node,))


def without_text(node):
    return {
        key: [without_text(child) for child in value] if key == "children" else value
        for key, value in node.items()
        if key not in TEXT_KEYS
    }


def exact(value):
    """A probability as the fraction its decimal text says (0.02 -> 1/50)."""
    return Fraction(repr(value))


# --------------------------------------------------------------------------
# the folder
# --------------------------------------------------------------------------


def test_the_examples_folder_holds_exactly_these_files():
    """The build copies the whole folder into the bundle, so nothing else may
    be left in it."""
    assert sorted(p.name for p in EXAMPLES.iterdir()) == sorted(["sampleFTA.json"] + FILES)


@pytest.mark.parametrize("name", FILES)
def test_an_example_is_stored_with_unix_line_endings_as_utf8(name):
    """``fta_web/examples/**`` is ``-text`` in .gitattributes: what is committed
    is what ships, byte for byte."""
    raw = (EXAMPLES / name).read_bytes()

    assert b"\r" not in raw
    assert not raw.startswith(b"\xef\xbb\xbf")
    raw.decode("utf-8")


# --------------------------------------------------------------------------
# every example
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", FILES)
def test_an_example_opens_without_a_repair(name):
    core = load(name)

    assert core.last_load_warnings == []
    assert core.mode == PAIRS[name.rsplit("_", 1)[0]]
    assert core.get_data()["id"] == "root"


@pytest.mark.parametrize("name", FILES)
def test_validation_finds_nothing_to_fix_in_an_example(name):
    core = load(name)

    issues = lint.run(core.get_data(), core.analysis, mode=core.mode)

    assert [(i["severity"], i["code"], i["nodeId"]) for i in issues
            if i["severity"] != "info"] == []


@pytest.mark.parametrize("name", FILES)
def test_saving_an_example_changes_nothing(name, tmp_path):
    """The file is what Save writes: nothing is recalculated to another value,
    reordered, added or dropped when a user opens it and saves it."""
    core = load(name)
    saved = tmp_path / name

    ok, error = core.save_to_json(str(saved))

    assert ok, error
    assert saved.read_text(encoding="utf-8") == (EXAMPLES / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("name", FILES)
def test_every_node_of_an_example_is_explained(name):
    document = read(name)
    lang = name.rsplit("_", 1)[1].split(".")[0]

    unexplained = [node["id"] for node, _ in walk(document["tree"])
                   if len((node.get("notes") or "").strip()) < 40]
    ids = [node["id"] for node, _ in walk(document["tree"])]

    assert unexplained == []
    assert len(ids) == len(set(ids))
    # The numbers are for learning the tool. The title says so, because the
    # title is what an export, a report and a screenshot carry.
    assert LANGUAGES[lang] in document["title"]
    assert LANGUAGES[lang] in document["tree"]["notes"]


@pytest.mark.parametrize("stem", PAIRS)
def test_the_two_languages_of_an_example_are_one_analysis(stem):
    english, japanese = read(stem + "_en.json"), read(stem + "_ja.json")

    assert without_text(english["tree"]) == without_text(japanese["tree"])
    assert {k: v for k, v in english.items() if k not in ("title", "tree")} == {
        k: v for k, v in japanese.items() if k not in ("title", "tree")}
    # ... and each is written in its language.
    for node, _ in walk(english["tree"]):
        assert not CJK.search(node["name"] + node["notes"]), node["id"]
    for node, _ in walk(japanese["tree"]):
        assert CJK.search(node["name"]) and CJK.search(node["notes"]), node["id"]


@pytest.mark.parametrize("name", FILES)
@pytest.mark.parametrize("document", ["README.md", "QUICKSTART.md", "docs/USER_GUIDE.md",
                                      "build/README.md"])
def test_the_documentation_names_every_example(document, name):
    assert name in (REPO_ROOT / document).read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# Three Mile Island Unit 2: the event tree
#
#   feedwater lost, relief valve opens, reactor scrams          1
#   |- the relief valve closes again                            49/50
#   `- the relief valve sticks open                             1/50
#      |- the operators close the block valve in time           1/2
#      `- the open valve is not recognised                      1/2
#         |- high pressure injection is left running            1/2
#         `- high pressure injection is throttled               1/2
#            |- the containment holds                           99/100
#            `- the containment fails                           1/100
#
# In an event tree a node's value is the product of the probabilities on the
# way down to it, so the five ends are, by hand:
#
#   49/50 = 0.98      1/50 * 1/2 = 0.01      1/50 * 1/2 * 1/2 = 0.005
#   1/50 * 1/2 * 1/2 * 99/100 = 0.00495      1/50 * 1/2 * 1/2 * 1/100 = 0.00005
#
# and they add up to 1: the tree loses nothing on the way.
# --------------------------------------------------------------------------

TMI_ENDS = {
    "root_0": Fraction(49, 50),
    "root_1_0": Fraction(1, 100),
    "root_1_1_0": Fraction(1, 200),
    "root_1_1_1_0": Fraction(99, 20000),
    "root_1_1_1_1": Fraction(1, 20000),
}
#: What happened on 28 March 1979, branch by branch.
TMI_AS_IT_HAPPENED = ["root", "root_1", "root_1_1", "root_1_1_1", "root_1_1_1_0"]


@pytest.mark.parametrize("name", ["tmi2_eta_en.json", "tmi2_eta_ja.json"])
def test_tmi2_end_states_are_the_products_worked_out_by_hand(name):
    tree = load(name).get_data()

    ends = {node["id"]: node for node, _ in walk(tree) if not node["children"]}

    assert set(ends) == set(TMI_ENDS)
    for node_id, expected in TMI_ENDS.items():
        assert ends[node_id]["calculatedProbability"] == pytest.approx(float(expected), rel=1e-12)
    assert sum(TMI_ENDS.values()) == 1
    assert math.fsum(n["calculatedProbability"] for n in ends.values()) == pytest.approx(1.0, abs=1e-12)


@pytest.mark.parametrize("name", ["tmi2_eta_en.json", "tmi2_eta_ja.json"])
def test_tmi2_values_follow_from_the_branch_probabilities_alone(name):
    """An independent walk in exact fractions: nothing but the file's own
    branch probabilities goes in."""
    tree = load(name).get_data()

    for node, above in walk(tree):
        expected = exact(node["probability"])
        for parent in above:
            expected *= exact(parent["probability"])
        assert node["calculatedProbability"] == pytest.approx(float(expected), rel=1e-12), node["id"]
        if node["children"]:
            assert sum(exact(c["probability"]) for c in node["children"]) == 1, node["id"]


@pytest.mark.parametrize("name,marker", [("tmi2_eta_en.json", "(actual)"),
                                         ("tmi2_eta_ja.json", "（実際）")])
def test_tmi2_marks_the_path_the_accident_took(name, marker):
    tree = read(name)["tree"]

    marked = [node["id"] for node, _ in walk(tree) if marker in node["name"]]

    assert marked == TMI_AS_IT_HAPPENED


# --------------------------------------------------------------------------
# Challenger (STS 51-L): the fault tree
#
#   loss of Challenger                                         AND
#   |- aft field joint does not seal                           AND
#   |  |- primary O-ring does not seal                         OR
#   |  |  |- X  O-rings stay compressed in their grooves       AND
#   |  |  |     |- C  cold makes the O-rings slow to recover       1/2
#   |  |  |     `- S  narrow gap squeezes the O-rings tight        1/2
#   |  |  `- U  putty delays the gas pressure too long             1/10
#   |  `- secondary O-ring does not seal                       OR, then OR with X (a link)
#   |     |- R  joint rotation unseats the secondary O-ring        1/5
#   |     `- I  ice blocks the secondary O-ring                    1/20
#   `- launch is not stopped                                   AND
#      |- V  contractor reverses its no-launch advice              1/2
#      `- N  doubts do not reach the decision-makers               1/2
#
# X (the cold and the squeeze together) is one thing, and it defeats both
# O-rings. By hand:
#
#   joint = X or (U and (R or I)),   X = C and S = 1/4
#         = 1/4 + 3/4 * 1/10 * (1 - 4/5 * 19/20) = 1/4 + 3/4 * 1/10 * 6/25 = 67/250
#   top   = joint * V * N = 67/250 * 1/4 = 67/1000 = 0.067               exact
#
# Counting X once per O-ring, as if each had its own (the tree walk):
#
#   (1 - 3/4 * 9/10) * (1 - 3/4 * 4/5 * 19/20) * 1/4
#         = 13/40 * 43/100 * 1/4 = 559/16000 = 0.0349375                 too low
#
# The minimal cut sets, and the upper bound the headline shows (MCUB):
#
#   {C S V N} 1/16      {U R V N} 1/200      {U I V N} 1/800
#   1 - 15/16 * 199/200 * 799/800 = 0.068353515625                       a little high
# --------------------------------------------------------------------------

CHALLENGER = ["challenger_fta_en.json", "challenger_fta_ja.json"]
X = "root_0_0_0"
C, S, U, R, I, V, N = ("root_0_0_0_0", "root_0_0_0_1", "root_0_0_1", "root_0_1_0", "root_0_1_1",
                       "root_1_0", "root_1_1")
CHALLENGER_EVENTS = {C: Fraction(1, 2), S: Fraction(1, 2), U: Fraction(1, 10), R: Fraction(1, 5),
                     I: Fraction(1, 20), V: Fraction(1, 2), N: Fraction(1, 2)}
CHALLENGER_CUT_SETS = {
    frozenset({C, S, V, N}): Fraction(1, 16),
    frozenset({U, R, V, N}): Fraction(1, 200),
    frozenset({U, I, V, N}): Fraction(1, 800),
}
CHALLENGER_EXACT = Fraction(67, 1000)
CHALLENGER_TREE_WALK = Fraction(559, 16000)
CHALLENGER_MCUB = 1 - Fraction(15, 16) * Fraction(199, 200) * Fraction(799, 800)
#: As the tool prints them at its default three significant figures.
CHALLENGER_SHOWN = {"headline": "0.0684", "exact": "0.0670", "tree walk": "0.0349"}


def occurs(node, state, index):
    """Whether ``node`` occurs when exactly the basic events in ``state`` do.
    This file's own reading of a tree: a gate combines its children, then each
    link is combined with the result (AND links, then OR links)."""
    children = node.get("children") or []
    if not children:
        value = node["id"] in state
    elif node["logicGate"] == "AND":
        value = all(occurs(child, state, index) for child in children)
    else:
        value = any(occurs(child, state, index) for child in children)
    links = node.get("links") or []
    for link in links:
        if link["relation"] == "AND":
            value = value and occurs(index[link["target_id"]], state, index)
    for link in links:
        if link["relation"] == "OR":
            value = value or occurs(index[link["target_id"]], state, index)
    return value


def enumerate_top(tree, events):
    """The exact top-event probability: every one of the 2^n states, in fractions."""
    index = {node["id"]: node for node, _ in walk(tree)}
    ids = sorted(events)
    total = Fraction(0)
    for bits in itertools.product((False, True), repeat=len(ids)):
        weight = Fraction(1)
        for node_id, on in zip(ids, bits):
            weight *= events[node_id] if on else 1 - events[node_id]
        if occurs(tree, {node_id for node_id, on in zip(ids, bits) if on}, index):
            total += weight
    return total


@pytest.mark.parametrize("name", CHALLENGER)
def test_challenger_events_and_gates_are_the_ones_worked_out_above(name):
    tree = read(name)["tree"]
    index = {node["id"]: node for node, _ in walk(tree)}

    events = {node_id: exact(node["probability"]) for node_id, node in index.items()
              if not node["children"]}
    gates = {node_id: node["logicGate"] for node_id, node in index.items() if node["children"]}

    assert events == CHALLENGER_EVENTS
    assert gates == {"root": "AND", "root_0": "AND", "root_0_0": "OR", X: "AND",
                     "root_0_1": "OR", "root_1": "AND"}
    assert {node_id: node["links"] for node_id, node in index.items() if node["links"]} == {
        "root_0_1": [{"target_id": X, "relation": "OR"}]}


@pytest.mark.parametrize("name", CHALLENGER)
def test_challenger_exact_top_event_by_enumerating_every_state(name):
    """2^7 states in exact fractions, from the file's structure and nothing
    of the engine's."""
    assert enumerate_top(read(name)["tree"], CHALLENGER_EVENTS) == CHALLENGER_EXACT
    assert CHALLENGER_TREE_WALK < CHALLENGER_EXACT < CHALLENGER_MCUB


@pytest.mark.parametrize("name", CHALLENGER)
def test_challenger_cut_sets_and_headline_are_the_ones_worked_out_by_hand(name):
    core = load(name)

    result = cutsets.compute(core.get_data(), core.analysis)
    summary = engine.summary(core.get_data(), core.analysis)

    found = {frozenset(e["id"] for e in row["events"]): row["probability"]
             for row in result["cutSets"]}
    assert set(found) == set(CHALLENGER_CUT_SETS)
    for members, expected in CHALLENGER_CUT_SETS.items():
        assert found[members] == pytest.approx(float(expected), rel=1e-12)
    assert not result["truncated"]
    # The cold and the squeeze are under both O-rings: each is one event, counted once.
    assert sorted(e["id"] for e in result["repeatedEvents"]) == [C, S]
    assert summary["headlineMethod"] == "mcub"
    assert summary["headline"] == pytest.approx(float(CHALLENGER_MCUB), rel=1e-12)
    assert summary["treeWalk"] == pytest.approx(float(CHALLENGER_TREE_WALK), rel=1e-12)
    assert core.get_data()["calculatedProbability"] == pytest.approx(
        float(CHALLENGER_TREE_WALK), rel=1e-12)


@pytest.mark.parametrize("name", CHALLENGER)
def test_challenger_notes_quote_the_numbers_the_tool_shows(name):
    """The top node's notes explain why the headline and its own value
    differ, and name both and the exact value: they must be the numbers on
    screen, and the exact one must be what the enumeration above gives."""
    core = load(name)
    notes = core.get_data()["notes"]

    shown = {
        "headline": format_prob(engine.summary(core.get_data(), core.analysis)["headline"], 3),
        "exact": format_prob(float(enumerate_top(read(name)["tree"], CHALLENGER_EVENTS)), 3),
        "tree walk": format_prob(core.get_data()["calculatedProbability"], 3),
    }

    assert shown == CHALLENGER_SHOWN
    for number in shown.values():
        assert notes.count(number) == 1, number
    assert "MCUB" in notes


@pytest.mark.parametrize("name", CHALLENGER)
def test_challenger_joint_note_gives_its_own_two_values(name):
    """The joint node's value is a tree-walk value as well (13/40 * 43/100 =
    559/4000); its note says so and gives the value with the common cause
    counted once (67/250, worked out above)."""
    core = load(name)
    joint = {node["id"]: node for node, _ in walk(core.get_data())}["root_0"]
    in_the_joint = {node_id: p for node_id, p in CHALLENGER_EVENTS.items() if node_id not in (V, N)}

    exact_value = enumerate_top(joint, in_the_joint)
    shown = (format_prob(joint["calculatedProbability"], 3), format_prob(float(exact_value), 3))

    assert exact_value == Fraction(67, 250)
    assert joint["calculatedProbability"] == pytest.approx(float(Fraction(559, 4000)), rel=1e-12)
    assert shown == ("0.140", "0.268")
    for number in shown:
        assert joint["notes"].count(number) == 1, number


@pytest.mark.parametrize("name", CHALLENGER)
def test_challenger_note_names_the_node_the_link_points_at(name):
    """The secondary O-ring's note refers to the common-cause node by name."""
    index = {node["id"]: node for node, _ in walk(read(name)["tree"])}

    assert index[X]["name"] in index["root_0_1"]["notes"]


@pytest.mark.parametrize("document", ["README.md", "docs/USER_GUIDE.md", "build/README.md",
                                      "CHANGELOG.md"])
def test_the_documentation_quotes_the_challenger_numbers_the_tool_shows(document):
    text = (REPO_ROOT / document).read_text(encoding="utf-8")

    assert CHALLENGER_SHOWN["headline"] in text and CHALLENGER_SHOWN["tree walk"] in text
    # ... and not the numbers of an earlier draft of the tree.
    assert "0.136" not in text and "0.0922" not in text
