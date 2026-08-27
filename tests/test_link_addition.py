#!/usr/bin/env python3
"""
Test script to verify link addition functionality
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.FTA_Editor_core import FTACore

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
    if node1["links"]:
        link = node1["links"][0]
        assert link["target_id"] == "node2", "Link target_id mismatch"
        assert link["relation"] == "AND", "Link relation mismatch"
        print("✓ Link successfully added to node1")
    else:
        print("✗ Link was not added to node1")
        return False
    
    # Test updating node with new links
    print("\nTesting update_node with links:")
    result = core.update_node("node1", {
        "links": [
            {"target_id": "node2", "relation": "OR"}
        ]
    })
    
    if result:
        node1_updated = core.find_node_by_id("node1")
        print(f"✓ update_node returned True")
        print(f"  Node 1 links after update: {node1_updated.get('links', [])}")
        
        if node1_updated["links"] and node1_updated["links"][0]["relation"] == "OR":
            print("✓ Link relation successfully changed from AND to OR")
        else:
            print("✗ Link relation not updated correctly")
            return False
    else:
        print("✗ update_node returned False")
        return False
    
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
    
    if link_count == 2:
        print("✓ Multiple links added successfully")
    else:
        print(f"✗ Expected 2 links, got {link_count}")
        return False
    
    print("\n" + "=" * 70)
    print("✅ ALL LINK ADDITION TESTS PASSED")
    print("=" * 70)
    return True

if __name__ == "__main__":
    success = test_link_addition()
    sys.exit(0 if success else 1)
