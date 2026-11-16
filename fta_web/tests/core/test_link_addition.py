#!/usr/bin/env python3
"""
Test script to verify link addition functionality
"""
import sys
from pathlib import Path

# Add the vendored core directory to path (fta_web/core).
# tests/core/<file>.py -> parents[0]=core, [1]=tests, [2]=fta_web
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "core"))

from FTA_Editor_core import FTACore

def test_link_addition():
    """Test that links can be added to existing nodes"""
    print("Testing Link Addition to Existing Nodes")
    print("=" * 70)
    
    # Create core and set up test data
    core = FTACore()
    core.set_data({
        "id": "root",
        "name": "Root",
        "type": "Root",
        "probability": 1.0,
        "logicGate": "OR",
        "children": [
            {
                "id": "node1",
                "name": "Node 1",
                "type": "Event",
                "probability": 0.5,
                "logicGate": "OR",
                "children": [],
                "links": []
            },
            {
                "id": "node2",
                "name": "Node 2",
                "type": "Event",
                "probability": 0.6,
                "logicGate": "OR",
                "children": [],
                "links": []
            }
        ],
        "links": []
    })
    
    print("✓ Initial tree created with 2 child nodes (node1, node2)")
    
    # Find node1 and add a link to node2
    node1 = core.find_node_by_id("node1")
    print(f"\nBefore adding link:")
    print(f"  Node 1 links: {node1.get('links', [])}")
    
    # Add AND link from node1 to node2
    node1["links"] = [
        {
            "target_id": "node2",
            "relation": "AND"
        }
    ]
    print(f"\nAfter adding link:")
    print(f"  Node 1 links: {node1.get('links', [])}")
    
    # Verify the link was added
    assert node1["links"], (
        "Link was not added to node1: node1['links'] is empty after direct assignment"
    )
    link = node1["links"][0]
    assert link["target_id"] == "node2", (
        f"Link target_id mismatch: expected 'node2', got {link['target_id']!r}"
    )
    assert link["relation"] == "AND", (
        f"Link relation mismatch: expected 'AND', got {link['relation']!r}"
    )
    print("✓ Link successfully added to node1")

    # Test updating node with new links
    print("\nTesting update_node with links:")
    result = core.update_node("node1", {
        "links": [
            {"target_id": "node2", "relation": "OR"}
        ]
    })

    assert result, (
        "core.update_node('node1', {...}) returned a falsy value; "
        "expected the update to succeed"
    )

    node1_updated = core.find_node_by_id("node1")
    print(f"✓ update_node returned True")
    print(f"  Node 1 links after update: {node1_updated.get('links', [])}")

    assert node1_updated["links"], (
        "node1 has no links after update_node(); expected one OR link to node2"
    )
    assert node1_updated["links"][0]["relation"] == "OR", (
        "Link relation not updated correctly: expected 'OR' after update_node(), "
        f"got {node1_updated['links'][0]['relation']!r}"
    )
    print("✓ Link relation successfully changed from AND to OR")
    
    # Test adding multiple links
    print("\nTesting multiple link addition:")
    core.update_node("node1", {
        "links": [
            {"target_id": "node2", "relation": "AND"},
            {"target_id": "root", "relation": "OR"}
        ]
    })
    
    node1_multi = core.find_node_by_id("node1")
    link_count = len(node1_multi.get('links', []))
    print(f"✓ Node 1 now has {link_count} links:")
    for link in node1_multi.get('links', []):
        print(f"  - {link['relation']} → {link['target_id']}")
    
    assert link_count == 2, (
        f"Expected 2 links on node1 after adding an AND link to node2 and an "
        f"OR link to root, got {link_count}: {node1_multi.get('links', [])}"
    )
    print("✓ Multiple links added successfully")

    print("\n" + "=" * 70)
    print("✅ ALL LINK ADDITION TESTS PASSED")
    print("=" * 70)


if __name__ == "__main__":
    # An assertion failure propagates and exits non-zero via the traceback.
    test_link_addition()
    sys.exit(0)
