"""
Regression tests for the documented divergences of the vendored core.

Each divergence recorded in fta_web/core/DIVERGENCE.md gets coverage here:

  D1 - AIAgentHandler._get_client() (dead code, always raised AttributeError)
       was deleted.
  D3 - Excel export sibling row layout. Reported as a row-overwrite defect but
       NOT reproducible; no patch was applied. These tests pin the layout so a
       future refactor of write_node() cannot introduce the reported bug.
  D5 - logicGate "NOT" is rejected at validation instead of silently computing
       as OR.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))

from FTA_Editor_core import FTACore  # noqa: E402
from AI_agent_handler import AIAgentHandler  # noqa: E402


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def node(node_id, children=None, **kwargs):
    """Build a well-formed FTA node."""
    return {
        "id": node_id,
        "name": kwargs.get("name", node_id),
        "type": kwargs.get("type", "Event"),
        "logicGate": kwargs.get("logicGate", ""),
        "probability": kwargs.get("probability", 0.1),
        "children": children or [],
        "links": [],
        "notes": kwargs.get("notes", ""),
    }


def walk(n):
    """Yield every node in the tree, depth-first."""
    yield n
    for child in n.get("children", []):
        yield from walk(child)


def export_grid(tree, path):
    """Export `tree` to Excel and return {(row, col): first_line_of_cell}."""
    core = FTACore()
    core.set_data(tree)
    ok, err = core.export_to_excel(str(path))
    assert ok, f"export failed: {err}"

    from openpyxl import load_workbook

    ws = load_workbook(str(path)).active
    return {
        (cell.row, cell.column): str(cell.value).split("\n")[0]
        for row in ws.iter_rows()
        for cell in row
        if cell.value
    }


# --------------------------------------------------------------------------
# D1 - dead _get_client() removed
# --------------------------------------------------------------------------

def test_d1_get_client_attribute_is_gone():
    """The dead _get_client method must not exist on the class or instances."""
    assert not hasattr(AIAgentHandler, "_get_client")

    handler = AIAgentHandler()
    assert not hasattr(handler, "_get_client")


def test_d1_live_provider_path_survived():
    """Deleting _get_client must not have touched the live _get_provider path."""
    handler = AIAgentHandler()
    assert hasattr(handler, "_get_provider")
    assert callable(handler._get_provider)
    # _get_provider caches on `provider`, which __init__ *does* initialise --
    # this is exactly what _get_client's `self._client` was missing.
    assert hasattr(handler, "provider")


# --------------------------------------------------------------------------
# D3 - Excel export sibling row layout
# --------------------------------------------------------------------------

def test_d3_deep_sibling_tree_loses_no_nodes(tmp_path):
    """A tree whose first sibling branch has grandchildren must export intact."""
    tree = node(
        "ROOT",
        [
            node(
                "S1",
                [
                    node("S1a", [node("S1a1"), node("S1a2")]),
                    node("S1b", [node("S1b1")]),
                ],
            ),
            node("S2", [node("S2a")]),
            node("S3"),
        ],
        type="Root",
    )

    grid = export_grid(tree, tmp_path / "deep.xlsx")

    expected_names = {n["name"] for n in walk(tree)}
    written_names = set(grid.values())

    missing = expected_names - written_names
    assert not missing, f"nodes lost from the sheet: {sorted(missing)}"

    # No node may be dropped by a same-cell overwrite either.
    assert len(grid) == len(list(walk(tree)))


def test_d3_deep_sibling_tree_exact_layout(tmp_path):
    """Pin the hierarchical layout: depth -> column, subtrees never collide.

    S2 must start on row 4, *below* S1's three-row subtree -- this is the exact
    scenario the reported defect claimed would overwrite rows.
    """
    tree = node(
        "ROOT",
        [
            node(
                "S1",
                [
                    node("S1a", [node("S1a1"), node("S1a2")]),
                    node("S1b", [node("S1b1")]),
                ],
            ),
            node("S2", [node("S2a")]),
        ],
        type="Root",
    )

    grid = export_grid(tree, tmp_path / "layout.xlsx")

    assert grid == {
        (1, 1): "ROOT",
        (1, 2): "S1",
        (1, 3): "S1a",
        (1, 4): "S1a1",
        (2, 4): "S1a2",
        (3, 3): "S1b",
        (3, 4): "S1b1",
        (4, 2): "S2",
        (4, 3): "S2a",
    }


def test_d3_shallow_tree_output_unchanged(tmp_path):
    """A tree with no multi-level sibling descendants keeps its original layout."""
    tree = node("ROOT", [node("X"), node("Y"), node("Z")], type="Root")

    grid = export_grid(tree, tmp_path / "shallow.xlsx")

    assert grid == {
        (1, 1): "ROOT",
        (1, 2): "X",
        (2, 2): "Y",
        (3, 2): "Z",
    }


def test_d3_cell_content_and_styling_preserved(tmp_path):
    """Content format, per-depth fills, bold root, wrap/top align, widths, heights."""
    tree = node(
        "ROOT",
        [node("child", probability=0.25, type="Gate", logicGate="AND", notes="a note")],
        type="Root",
    )
    core = FTACore()
    core.set_data(tree)
    core.recalculate_probabilities()

    path = tmp_path / "style.xlsx"
    ok, err = core.export_to_excel(str(path))
    assert ok, err

    from openpyxl import load_workbook

    ws = load_workbook(str(path)).active

    root_cell = ws.cell(row=1, column=1)
    child_cell = ws.cell(row=1, column=2)

    # Content format: name, then "(Type: ..., P: ..., Calc: ..., Gate: ...)",
    # then "Notes: ...".
    lines = child_cell.value.split("\n")
    assert lines[0] == "child"
    assert lines[1].startswith("(Type: Gate") and lines[1].endswith(")")
    assert "P: 0.25" in lines[1]
    assert "Gate: AND" in lines[1]
    assert lines[2] == "Notes: a note"

    # Bold root font, plain child.
    assert root_cell.font.bold is True
    assert not child_cell.font.bold

    # wrap_text / vertical top on both.
    for cell in (root_cell, child_cell):
        assert cell.alignment.wrap_text is True
        assert cell.alignment.vertical == "top"

    # Per-depth fill colours.
    assert root_cell.fill.start_color.rgb.endswith("E6F3FF")
    assert child_cell.fill.start_color.rgb.endswith("FFF4E6")

    # Auto column widths capped at 50, row heights 45.
    for dim in ws.column_dimensions.values():
        assert dim.width <= 50
    assert ws.row_dimensions[1].height == 45


def test_d3_links_rendered_in_cell(tmp_path):
    """The 'Links: ...' line of the cell format is preserved."""
    target = node("tgt", name="Target Node")
    source = node("src", name="Source Node")
    source["links"] = [{"target_id": "tgt", "relation": "AND"}]
    tree = node("ROOT", [source, target], type="Root")

    core = FTACore()
    core.set_data(tree)
    path = tmp_path / "links.xlsx"
    ok, err = core.export_to_excel(str(path))
    assert ok, err

    from openpyxl import load_workbook

    ws = load_workbook(str(path)).active
    assert "Links: AND→Target Node" in ws.cell(row=1, column=2).value


# --------------------------------------------------------------------------
# D5 - NOT gates are rejected
# --------------------------------------------------------------------------

def _tree_with_gate(gate):
    return node(
        "root",
        [node("child_a", probability=0.2), node("child_b", probability=0.3)],
        type="Root",
        logicGate=gate,
        probability=1.0,
    )


def test_d5_not_gate_rejected_by_verify_updated_fta_json():
    handler = AIAgentHandler()
    ok, err = handler.verify_updated_fta_json(_tree_with_gate("NOT"))

    assert ok is False
    assert err is not None
    # The message must name the offending node.
    assert "root" in err
    assert "NOT" in err


def test_d5_not_gate_rejected_on_a_nested_node_names_that_node():
    handler = AIAgentHandler()
    tree = node(
        "root",
        [node("branch", [node("leaf", probability=0.4)], logicGate="NOT", type="Gate")],
        type="Root",
        probability=1.0,
    )

    ok, err = handler.verify_updated_fta_json(tree)

    assert ok is False
    assert "branch" in err, f"error must name the offending node, got: {err!r}"


@pytest.mark.parametrize("gate", ["AND", "OR", ""])
def test_d5_valid_gates_still_accepted(gate):
    handler = AIAgentHandler()
    ok, err = handler.verify_updated_fta_json(_tree_with_gate(gate))

    assert ok is True, f"gate {gate!r} should validate, got error: {err!r}"
    assert err is None


def test_d5_not_gate_rejected_by_validate_node_data():
    handler = AIAgentHandler()
    ok, err = handler._validate_node_data(
        {"id": "gate_3", "name": "Some Gate", "type": "Gate", "logicGate": "NOT"}
    )

    assert ok is False
    assert "gate_3" in err
    assert "NOT" in err


@pytest.mark.parametrize("gate", ["AND", "OR"])
def test_d5_validate_node_data_still_accepts_and_or(gate):
    handler = AIAgentHandler()
    ok, err = handler._validate_node_data(
        {"id": "gate_3", "name": "Some Gate", "type": "Gate", "logicGate": gate}
    )

    assert ok is True, f"gate {gate!r} should validate, got: {err!r}"


def test_d5_prompts_never_advertise_not_as_valid():
    """The AI must not be told NOT is an accepted logicGate value."""
    assert "AND|OR|NOT" not in AIAgentHandler.FTA_JSON_SCHEMA
    assert "AND|OR" in AIAgentHandler.FTA_JSON_SCHEMA
    assert "AND|OR|NOT" not in AIAgentHandler.SYSTEM_PROMPT


def test_d5_probability_engine_unchanged_for_and_or():
    """D5 was fixed at validation only; the engine must be untouched."""
    core = FTACore()
    core.set_data(_tree_with_gate("AND"))
    core.recalculate_probabilities()
    assert core.get_data()["calculatedProbability"] == pytest.approx(0.2 * 0.3)

    core = FTACore()
    core.set_data(_tree_with_gate("OR"))
    core.recalculate_probabilities()
    assert core.get_data()["calculatedProbability"] == pytest.approx(
        1 - (1 - 0.2) * (1 - 0.3)
    )
