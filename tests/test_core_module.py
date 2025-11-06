"""
Test suite for FTA Editor probability calculation validation
Tests AND/OR gate logic and link handling using the refactored core module
"""
import unittest
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import the core module
from src.FTA_Editor_core import FTACore


class TestProbabilityCalculationWithCore(unittest.TestCase):
    """Test cases for probability calculation using FTACore"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.core = FTACore()
    
    def test_leaf_node_probability(self):
        """Test that leaf nodes use their base probability"""
        self.core.set_data({
            "id": "root",
            "name": "Root",
            "type": "Event",
            "probability": 0.5,
            "logicGate": "OR",
            "children": [],
            "links": []
        })
        self.core.recalculate_probabilities()
        data = self.core.get_data()
        self.assertEqual(data["calculatedProbability"], 0.5)
    
    def test_and_gate_with_two_children(self):
        """Test AND gate: should calculate product(child_probs) only"""
        self.core.set_data({
            "id": "root",
            "name": "Root",
            "type": "Event",
            "probability": 0.8,
            "logicGate": "AND",
            "children": [
                {
                    "id": "child1",
                    "name": "Child1",
                    "type": "Event",
                    "probability": 0.5,
                    "logicGate": "OR",
                    "children": [],
                    "links": []
                },
                {
                    "id": "child2",
                    "name": "Child2",
                    "type": "Event",
                    "probability": 0.4,
                    "logicGate": "OR",
                    "children": [],
                    "links": []
                }
            ],
            "links": []
        })
        self.core.recalculate_probabilities()
        data = self.core.get_data()
        # AND: product(children) = 0.5 * 0.4 = 0.2 (parent base probability is ignored when children exist)
        self.assertEqual(data["calculatedProbability"], 0.2)
    
    def test_or_gate_with_two_children(self):
        """Test OR gate: should use 1 - product(1 - child_prob)"""
        self.core.set_data({
            "id": "root",
            "name": "Root",
            "type": "Event",
            "probability": 1.0,
            "logicGate": "OR",
            "children": [
                {
                    "id": "child1",
                    "name": "Child1",
                    "type": "Event",
                    "probability": 0.5,
                    "logicGate": "OR",
                    "children": [],
                    "links": []
                },
                {
                    "id": "child2",
                    "name": "Child2",
                    "type": "Event",
                    "probability": 0.4,
                    "logicGate": "OR",
                    "children": [],
                    "links": []
                }
            ],
            "links": []
        })
        self.core.recalculate_probabilities()
        data = self.core.get_data()
        # OR: 1 - product(1 - child_prob) = 1 - (1-0.5)*(1-0.4) = 1 - 0.5*0.6 = 1 - 0.3 = 0.7
        self.assertEqual(data["calculatedProbability"], 0.7)
    
    def test_and_link_simple(self):
        """Test AND link between nodes"""
        self.core.set_data({
            "id": "root",
            "name": "Root",
            "type": "Event",
            "probability": 0.5,
            "logicGate": "OR",
            "children": [
                {
                    "id": "child1",
                    "name": "Child1",
                    "type": "Event",
                    "probability": 0.8,
                    "logicGate": "OR",
                    "children": [],
                    "links": [
                        {
                            "target_id": "child2",
                            "relation": "AND"
                        }
                    ]
                },
                {
                    "id": "child2",
                    "name": "Child2",
                    "type": "Event",
                    "probability": 0.6,
                    "logicGate": "OR",
                    "children": [],
                    "links": []
                }
            ],
            "links": []
        })
        self.core.recalculate_probabilities()
        child1 = self.core.find_node_by_id("child1")
        child2 = self.core.find_node_by_id("child2")
        # child2 has no links: 0.6
        self.assertEqual(child2["calculatedProbability"], 0.6)
        # child1 AND-linked to child2: 0.8 * 0.6 = 0.48
        self.assertEqual(child1["calculatedProbability"], 0.48)
    
    def test_file_io_json(self):
        """Test JSON save and load functionality"""
        import tempfile
        import os
        
        # Set up test data
        self.core.set_data({
            "id": "root",
            "name": "TestRoot",
            "type": "Root",
            "probability": 1.0,
            "logicGate": "AND",
            "children": [
                {
                    "id": "child1",
                    "name": "TestChild",
                    "type": "Event",
                    "probability": 0.5,
                    "logicGate": "OR",
                    "children": [],
                    "links": []
                }
            ],
            "links": []
        })
        self.core.recalculate_probabilities()
        
        # Save to temp file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            temp_path = f.name
        
        try:
            success, error = self.core.save_to_json(temp_path)
            self.assertTrue(success, f"Save failed: {error}")
            
            # Load into new core instance
            new_core = FTACore()
            success, error = new_core.load_from_json(temp_path)
            self.assertTrue(success, f"Load failed: {error}")
            
            # Verify data
            loaded_data = new_core.get_data()
            self.assertEqual(loaded_data["name"], "TestRoot")
            self.assertEqual(loaded_data["children"][0]["name"], "TestChild")
            
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    def test_node_operations(self):
        """Test node add, update, delete operations"""
        # Start with root
        self.assertEqual(self.core.get_data()["id"], "root")
        
        # Add a child node
        new_node = {
            "id": "root_0",
            "name": "NewChild",
            "type": "Event",
            "probability": 0.7,
            "logicGate": "OR",
            "children": [],
            "links": []
        }
        self.core.add_node_to_data("root", new_node)
        
        # Verify it was added
        found = self.core.find_node_by_id("root_0")
        self.assertIsNotNone(found)
        self.assertEqual(found["name"], "NewChild")
        
        # Update the node
        self.core.update_node("root_0", {"name": "UpdatedChild", "probability": 0.9})
        found = self.core.find_node_by_id("root_0")
        self.assertEqual(found["name"], "UpdatedChild")
        self.assertEqual(found["probability"], 0.9)
        
        # Delete the node
        self.core.delete_node_from_data("root_0")
        found = self.core.find_node_by_id("root_0")
        self.assertIsNone(found)


def run_tests():
    """Run all tests and print results"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    suite.addTests(loader.loadTestsFromTestCase(TestProbabilityCalculationWithCore))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print("\n" + "="*70)
    print("FTA CORE MODULE TEST SUMMARY")
    print("="*70)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print("="*70)
    
    if result.wasSuccessful():
        print("\n✓ All FTA Core tests passed!")
        print("\nValidated:")
        print("  • Core module functionality")
        print("  • Probability calculations")
        print("  • File I/O (JSON)")
        print("  • Node operations (add, update, delete)")
    else:
        print("\n✗ Some tests failed. See details above.")
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
