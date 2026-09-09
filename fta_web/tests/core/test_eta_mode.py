#!/usr/bin/env python3
"""
Test script for ETA (Event Tree Analysis) functionality
"""
import sys
from pathlib import Path

# Add the vendored core directory to path (fta_web/core).
# tests/core/<file>.py -> parents[0]=core, [1]=tests, [2]=fta_web
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "core"))

from FTA_Editor_core import FTACore

def test_eta_mode():
    """Test ETA probability calculation"""
    print("Testing ETA (Event Tree Analysis) Mode")
    print("=" * 70)
    
    # Create a simple test tree
    core = FTACore()
    core.set_metadata(title="ETA Test", date="2025-10-31", mode="ETA")
    
    # Build test tree
    test_data = {
        "id": "root",
        "name": "Initiating Event",
        "type": "Root",
        "probability": 0.5,
        "logicGate": "OR",
        "children": [
            {
                "id": "branch1",
                "name": "Branch 1",
                "type": "Event",
                "probability": 0.8,
                "logicGate": "OR",
                "children": [
                    {
                        "id": "outcome1",
                        "name": "Outcome 1",
                        "type": "Event",
                        "probability": 0.9,
                        "logicGate": "OR",
                        "children": [],
                        "links": []
                    },
                    {
                        "id": "outcome2",
                        "name": "Outcome 2",
                        "type": "Event",
                        "probability": 0.7,
                        "logicGate": "OR",
                        "children": [],
                        "links": []
                    }
                ],
                "links": []
            },
            {
                "id": "branch2",
                "name": "Branch 2",
                "type": "Event",
                "probability": 0.6,
                "logicGate": "OR",
                "children": [],
                "links": []
            }
        ],
        "links": []
    }
    
    core.set_data(test_data)
    
    # Calculate in ETA mode
    print("\nETA Mode Calculation:")
    print("-" * 70)
    core.recalculate_probabilities()
    
    # Check results
    root = core.get_data()
    print(f"Root (Initiating Event):")
    print(f"  Base Probability: {root['probability']}")
    print(f"  Calculated Probability: {root['calculatedProbability']}")
    print(f"  Expected: {root['probability']} (root uses base prob)")
    
    branch1 = root['children'][0]
    print(f"\nBranch 1:")
    print(f"  Base Probability: {branch1['probability']}")
    print(f"  Calculated Probability: {branch1['calculatedProbability']}")
    print(f"  Expected: {0.5 * 0.8} (root calc * branch1 base)")
    
    outcome1 = branch1['children'][0]
    print(f"\nOutcome 1:")
    print(f"  Base Probability: {outcome1['probability']}")
    print(f"  Calculated Probability: {outcome1['calculatedProbability']}")
    print(f"  Expected: {0.5 * 0.8 * 0.9} (branch1 calc * outcome1 base)")
    
    outcome2 = branch1['children'][1]
    print(f"\nOutcome 2:")
    print(f"  Base Probability: {outcome2['probability']}")
    print(f"  Calculated Probability: {outcome2['calculatedProbability']}")
    print(f"  Expected: {0.5 * 0.8 * 0.7} (branch1 calc * outcome2 base)")
    
    branch2 = root['children'][1]
    print(f"\nBranch 2:")
    print(f"  Base Probability: {branch2['probability']}")
    print(f"  Calculated Probability: {branch2['calculatedProbability']}")
    print(f"  Expected: {0.5 * 0.6} (root calc * branch2 base)")
    
    # Verify calculations
    print("\n" + "=" * 70)
    print("VERIFICATION:")
    print("=" * 70)
    
    checks = [
        (root['calculatedProbability'], 0.5, "Root"),
        (branch1['calculatedProbability'], 0.4, "Branch 1"),
        (outcome1['calculatedProbability'], 0.36, "Outcome 1"),
        (outcome2['calculatedProbability'], 0.28, "Outcome 2"),
        (branch2['calculatedProbability'], 0.3, "Branch 2"),
    ]
    
    # Collect every mismatch before failing, so the message reports all of them
    # rather than only the first.
    mismatches = []
    for actual, expected, name in checks:
        ok = abs(actual - expected) < 0.0001
        print(f"{'✓' if ok else '✗'} {name}: {actual} (expected {expected})")
        if not ok:
            mismatches.append(f"{name}: got {actual}, expected {expected}")

    print("=" * 70)

    assert not mismatches, (
        "ETA mode probability calculation is wrong for "
        f"{len(mismatches)} of {len(checks)} nodes: " + "; ".join(mismatches)
    )
    print("✅ All ETA calculations correct!")


def test_fta_vs_eta():
    """Compare FTA and ETA modes"""
    print("\n\n")
    print("Comparing FTA vs ETA Modes")
    print("=" * 70)
    
    # Create test tree
    test_data = {
        "id": "root",
        "name": "Root",
        "type": "Root",
        "probability": 0.5,
        "logicGate": "AND",
        "children": [
            {
                "id": "child1",
                "name": "Child 1",
                "type": "Event",
                "probability": 0.8,
                "logicGate": "OR",
                "children": [],
                "links": []
            },
            {
                "id": "child2",
                "name": "Child 2",
                "type": "Event",
                "probability": 0.6,
                "logicGate": "OR",
                "children": [],
                "links": []
            }
        ],
        "links": []
    }
    
    # Test FTA mode
    core_fta = FTACore()
    core_fta.set_metadata(mode="FTA")
    core_fta.set_data(test_data.copy())
    core_fta.recalculate_probabilities()
    
    # Test ETA mode
    core_eta = FTACore()
    core_eta.set_metadata(mode="ETA")
    import copy
    core_eta.set_data(copy.deepcopy(test_data))
    core_eta.recalculate_probabilities()
    
    print("\nFTA Mode (bottom-up, children affect parent):")
    fta_data = core_fta.get_data()
    print(f"  Root: {fta_data['calculatedProbability']}")
    print(f"  Child1: {fta_data['children'][0]['calculatedProbability']}")
    print(f"  Child2: {fta_data['children'][1]['calculatedProbability']}")
    
    print("\nETA Mode (top-down, parent affects children):")
    eta_data = core_eta.get_data()
    print(f"  Root: {eta_data['calculatedProbability']}")
    print(f"  Child1: {eta_data['children'][0]['calculatedProbability']}")
    print(f"  Child2: {eta_data['children'][1]['calculatedProbability']}")
    
    print("\n" + "=" * 70)


def test_json_save_load():
    """Test saving and loading with metadata"""
    import tempfile
    import os
    
    print("\n\n")
    print("Testing JSON Save/Load with Metadata")
    print("=" * 70)
    
    # Create core with metadata
    core1 = FTACore()
    core1.set_metadata(title="Test Analysis", date="2025-10-31", mode="ETA")
    
    test_data = {
        "id": "root",
        "name": "Root",
        "type": "Root",
        "probability": 0.7,
        "logicGate": "OR",
        "children": [],
        "links": []
    }
    core1.set_data(test_data)
    
    # Save to temp file
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
        test_file = f.name
    
    try:
        success, error = core1.save_to_json(test_file)
        assert success, f"core1.save_to_json({test_file}) failed: {error}"
        print(f"✓ Saved to {test_file}")

        # Load into new core
        core2 = FTACore()
        success, error = core2.load_from_json(test_file)
        assert success, f"core2.load_from_json({test_file}) failed: {error}"

        print(f"✓ Loaded from {test_file}")
        
        # Verify metadata
        print("\nMetadata verification:")
        print(f"  Title: {core2.title} (expected: 'Test Analysis')")
        print(f"  Date: {core2.date} (expected: '2025-10-31')")
        print(f"  Mode: {core2.mode} (expected: 'ETA')")
        
        checks = [
            ("Title", core2.title, "Test Analysis"),
            ("Date", core2.date, "2025-10-31"),
            ("Mode", core2.mode, "ETA"),
        ]

        # Collect every mismatch before failing, so the message reports all of
        # them rather than only the first.
        mismatches = []
        for name, actual, expected in checks:
            ok = actual == expected
            print(f"{'✓' if ok else '✗'} {name} correct")
            if not ok:
                mismatches.append(f"{name}: got {actual!r}, expected {expected!r}")

        print("=" * 70)

        assert not mismatches, (
            "Metadata did not survive the JSON save/load round-trip: "
            + "; ".join(mismatches)
        )
    finally:
        if os.path.exists(test_file):
            os.unlink(test_file)


if __name__ == "__main__":
    # An assertion failure propagates and exits non-zero via the traceback.
    test_eta_mode()
    test_fta_vs_eta()
    test_json_save_load()

    print("\n" + "=" * 70)
    print("OVERALL RESULT")
    print("=" * 70)
    print("✅ All tests passed!")
    sys.exit(0)
