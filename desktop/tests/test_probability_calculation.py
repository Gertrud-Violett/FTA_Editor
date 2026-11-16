"""
Test suite for FTA Editor probability calculation validation
Tests AND/OR gate logic and link handling
"""
import unittest
import sys
from pathlib import Path

# Add parent directory to path to import FTA_Editor
sys.path.insert(0, str(Path(__file__).parent))

# Import just the calculation logic by creating a minimal mock
class ProbabilityCalculator:
    """Extracted probability calculation logic for testing"""
    
    def __init__(self):
        self.fta_data = None
    
    def _product(self, nums):
        """Calculate product of numbers"""
        result = 1
        for n in nums:
            result *= n
        return result
    
    def _find_node_by_id(self, current_node, node_id):
        """Find a node by ID in the tree"""
        if str(current_node.get("id")) == str(node_id):
            return current_node
        for child in current_node.get("children", []):
            result = self._find_node_by_id(child, node_id)
            if result:
                return result
        return None
    
    def recalculate_probabilities(self, data):
        """Calculate probabilities for all nodes in the tree"""
        self.fta_data = data
        memo = {}
        visiting = set()

        def get_prob(node):
            nid = node.get("id")
            if nid in memo:
                return memo[nid]
            if nid in visiting:
                val = float(node.get("probability", 1.0))
                memo[nid] = val
                return val

            visiting.add(nid)
            children = node.get("children", []) or []
            
            if not children:
                base = float(node.get("probability", 0.0))
            else:
                child_probs = [get_prob(c) for c in children]
                gate = (node.get("logicGate") or "OR").upper()
                
                if gate == "AND":
                    # AND gate: product of children probabilities
                    base = round(self._product(child_probs), 6)
                else:
                    # OR gate: union formula
                    base = round(1 - self._product([1 - p for p in child_probs]), 6)

            # Process links
            links = node.get("links", []) or []
            and_probs = []
            or_probs = []
            
            for l in links:
                tid = l.get("target_id")
                rel = (l.get("relation") or "OR").upper()
                if not tid:
                    continue
                target = self._find_node_by_id(self.fta_data, tid)
                if not target:
                    continue
                tp = get_prob(target)
                (and_probs if rel == "AND" else or_probs).append(tp)

            if and_probs:
                base = round(base * self._product(and_probs), 6)
            if or_probs:
                vals = [base] + or_probs
                base = round(1 - self._product([1 - p for p in vals]), 6)

            memo[nid] = base
            visiting.remove(nid)
            node["calculatedProbability"] = base
            return base

        if isinstance(data, dict):
            get_prob(data)
        
        return data


class TestProbabilityCalculation(unittest.TestCase):
    """Test cases for probability calculation logic"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.calc = ProbabilityCalculator()
    
    def test_leaf_node_probability(self):
        """Test that leaf nodes use their base probability"""
        data = {
            "id": "root",
            "name": "Root",
            "type": "Event",
            "probability": 0.5,
            "logicGate": "OR",
            "children": [],
            "links": []
        }
        result = self.calc.recalculate_probabilities(data)
        self.assertEqual(result["calculatedProbability"], 0.5)
    
    def test_and_gate_with_two_children(self):
        """Test AND gate: should calculate product(child_probs)"""
        data = {
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
        }
        result = self.calc.recalculate_probabilities(data)
        # AND: product(children) = 0.5 * 0.4 = 0.2
        # Parent's base probability is ignored when children exist
        self.assertEqual(result["calculatedProbability"], 0.2)
        self.assertEqual(result["children"][0]["calculatedProbability"], 0.5)
        self.assertEqual(result["children"][1]["calculatedProbability"], 0.4)
    
    def test_or_gate_with_two_children(self):
        """Test OR gate: should use 1 - product(1 - child_prob)"""
        data = {
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
        }
        result = self.calc.recalculate_probabilities(data)
        # OR: 1 - product(1 - child_prob) = 1 - (1-0.5)*(1-0.4) = 1 - 0.5*0.6 = 1 - 0.3 = 0.7
        self.assertEqual(result["calculatedProbability"], 0.7)
    
    def test_and_gate_with_three_children(self):
        """Test AND gate with three children"""
        data = {
            "id": "root",
            "name": "Root",
            "type": "Event",
            "probability": 1.0,
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
                    "probability": 0.6,
                    "logicGate": "OR",
                    "children": [],
                    "links": []
                },
                {
                    "id": "child3",
                    "name": "Child3",
                    "type": "Event",
                    "probability": 0.8,
                    "logicGate": "OR",
                    "children": [],
                    "links": []
                }
            ],
            "links": []
        }
        result = self.calc.recalculate_probabilities(data)
        # AND: product(children) = 0.5 * 0.6 * 0.8 = 0.24
        self.assertEqual(result["calculatedProbability"], 0.24)
    
    def test_or_gate_with_three_children(self):
        """Test OR gate with three children"""
        data = {
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
                    "probability": 0.6,
                    "logicGate": "OR",
                    "children": [],
                    "links": []
                },
                {
                    "id": "child3",
                    "name": "Child3",
                    "type": "Event",
                    "probability": 0.8,
                    "logicGate": "OR",
                    "children": [],
                    "links": []
                }
            ],
            "links": []
        }
        result = self.calc.recalculate_probabilities(data)
        # OR: 1 - (1-0.5)*(1-0.6)*(1-0.8) = 1 - 0.5*0.4*0.2 = 1 - 0.04 = 0.96
        self.assertEqual(result["calculatedProbability"], 0.96)
    
    def test_and_link_simple(self):
        """Test AND link between nodes"""
        data = {
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
        }
        result = self.calc.recalculate_probabilities(data)
        # child2 has no links: 0.6
        self.assertEqual(result["children"][1]["calculatedProbability"], 0.6)
        # child1 AND-linked to child2: 0.8 * 0.6 = 0.48
        self.assertEqual(result["children"][0]["calculatedProbability"], 0.48)
    
    def test_or_link_simple(self):
        """Test OR link between nodes"""
        data = {
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
                    "probability": 0.5,
                    "logicGate": "OR",
                    "children": [],
                    "links": [
                        {
                            "target_id": "child2",
                            "relation": "OR"
                        }
                    ]
                },
                {
                    "id": "child2",
                    "name": "Child2",
                    "type": "Event",
                    "probability": 0.3,
                    "logicGate": "OR",
                    "children": [],
                    "links": []
                }
            ],
            "links": []
        }
        result = self.calc.recalculate_probabilities(data)
        # child2: 0.3
        self.assertEqual(result["children"][1]["calculatedProbability"], 0.3)
        # child1 OR-linked to child2: 1 - (1-0.5)*(1-0.3) = 1 - 0.5*0.7 = 1 - 0.35 = 0.65
        self.assertEqual(result["children"][0]["calculatedProbability"], 0.65)
    
    def test_mixed_and_or_links(self):
        """Test node with both AND and OR links"""
        data = {
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
                    "links": [
                        {
                            "target_id": "child2",
                            "relation": "AND"
                        },
                        {
                            "target_id": "child3",
                            "relation": "OR"
                        }
                    ]
                },
                {
                    "id": "child2",
                    "name": "Child2",
                    "type": "Event",
                    "probability": 0.8,
                    "logicGate": "OR",
                    "children": [],
                    "links": []
                },
                {
                    "id": "child3",
                    "name": "Child3",
                    "type": "Event",
                    "probability": 0.4,
                    "logicGate": "OR",
                    "children": [],
                    "links": []
                }
            ],
            "links": []
        }
        result = self.calc.recalculate_probabilities(data)
        # child2: 0.8, child3: 0.4
        self.assertEqual(result["children"][1]["calculatedProbability"], 0.8)
        self.assertEqual(result["children"][2]["calculatedProbability"], 0.4)
        # child1: first apply AND link: 0.5 * 0.8 = 0.4
        # then apply OR link: 1 - (1-0.4)*(1-0.4) = 1 - 0.6*0.6 = 1 - 0.36 = 0.64
        self.assertEqual(result["children"][0]["calculatedProbability"], 0.64)
    
    def test_zero_probability_leaf(self):
        """Test that zero probability propagates correctly"""
        data = {
            "id": "root",
            "name": "Root",
            "type": "Event",
            "probability": 1.0,
            "logicGate": "AND",
            "children": [
                {
                    "id": "child1",
                    "name": "Child1",
                    "type": "Event",
                    "probability": 0.0,
                    "logicGate": "OR",
                    "children": [],
                    "links": []
                },
                {
                    "id": "child2",
                    "name": "Child2",
                    "type": "Event",
                    "probability": 1.0,
                    "logicGate": "OR",
                    "children": [],
                    "links": []
                }
            ],
            "links": []
        }
        result = self.calc.recalculate_probabilities(data)
        # AND gate with one zero child: 1.0 * (0.0 * 1.0) = 0.0
        self.assertEqual(result["calculatedProbability"], 0.0)
    
    def test_nested_and_gates(self):
        """Test nested AND gates"""
        data = {
            "id": "root",
            "name": "Root",
            "type": "Event",
            "probability": 1.0,
            "logicGate": "AND",
            "children": [
                {
                    "id": "child1",
                    "name": "Child1",
                    "type": "Event",
                    "probability": 0.9,
                    "logicGate": "AND",
                    "children": [
                        {
                            "id": "grandchild1",
                            "name": "GrandChild1",
                            "type": "Event",
                            "probability": 0.5,
                            "logicGate": "OR",
                            "children": [],
                            "links": []
                        },
                        {
                            "id": "grandchild2",
                            "name": "GrandChild2",
                            "type": "Event",
                            "probability": 0.6,
                            "logicGate": "OR",
                            "children": [],
                            "links": []
                        }
                    ],
                    "links": []
                }
            ],
            "links": []
        }
        result = self.calc.recalculate_probabilities(data)
        # grandchild1: 0.5, grandchild2: 0.6
        self.assertEqual(result["children"][0]["children"][0]["calculatedProbability"], 0.5)
        self.assertEqual(result["children"][0]["children"][1]["calculatedProbability"], 0.6)
        # child1 (AND gate): product(children) = 0.5 * 0.6 = 0.3
        self.assertEqual(result["children"][0]["calculatedProbability"], 0.3)
        # root (AND gate): product(children) = 0.3
        self.assertEqual(result["calculatedProbability"], 0.3)
    
    def test_nested_or_gates(self):
        """Test nested OR gates"""
        data = {
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
                    "probability": 1.0,
                    "logicGate": "OR",
                    "children": [
                        {
                            "id": "grandchild1",
                            "name": "GrandChild1",
                            "type": "Event",
                            "probability": 0.5,
                            "logicGate": "OR",
                            "children": [],
                            "links": []
                        },
                        {
                            "id": "grandchild2",
                            "name": "GrandChild2",
                            "type": "Event",
                            "probability": 0.2,
                            "logicGate": "OR",
                            "children": [],
                            "links": []
                        }
                    ],
                    "links": []
                }
            ],
            "links": []
        }
        result = self.calc.recalculate_probabilities(data)
        # grandchild1: 0.5, grandchild2: 0.2
        self.assertEqual(result["children"][0]["children"][0]["calculatedProbability"], 0.5)
        self.assertEqual(result["children"][0]["children"][1]["calculatedProbability"], 0.2)
        # child1 (OR gate): 1 - (1-0.5)*(1-0.2) = 1 - 0.5*0.8 = 1 - 0.4 = 0.6
        self.assertEqual(result["children"][0]["calculatedProbability"], 0.6)
        # root (OR gate): 1 - (1-0.6) = 1 - 0.4 = 0.6
        self.assertEqual(result["calculatedProbability"], 0.6)
    
    def test_circular_reference_protection(self):
        """Test that circular references are handled (uses base probability)"""
        # This is a tricky case - we set up a potential circular reference
        # The algorithm should handle this with the visiting set
        data = {
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
                    "links": [
                        {
                            "target_id": "child1",  # Self-reference
                            "relation": "OR"
                        }
                    ]
                }
            ],
            "links": []
        }
        result = self.calc.recalculate_probabilities(data)
        # Should complete without infinite loop
        # When circular reference detected, uses base probability
        self.assertIsNotNone(result["children"][0]["calculatedProbability"])


class TestSampleDataValidation(unittest.TestCase):
    """Validate calculations against the sample FTA data"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.calc = ProbabilityCalculator()
    
    def test_sample_event_1_1_1(self):
        """Test Event1.1.1 from sampleFTA.json
        - Base probability: 0.5
        - Has OR link to root_1_1 (prob 0.0)
        - Has AND link to root_0_2 (prob 0.8)
        - Expected: 0.5 * 0.8 (AND) = 0.4, then OR with 0.0 = 0.4
        """
        data = {
            "id": "root",
            "name": "Root",
            "type": "Event",
            "probability": 1.0,
            "logicGate": "OR",
            "children": [
                {
                    "id": "root_0_0_0",
                    "name": "Ev1.1.1",
                    "type": "Event",
                    "probability": 0.5,
                    "logicGate": "OR",
                    "children": [],
                    "links": [
                        {
                            "target_id": "root_1_1",
                            "relation": "OR"
                        },
                        {
                            "target_id": "root_0_2",
                            "relation": "AND"
                        }
                    ]
                },
                {
                    "id": "root_1_1",
                    "name": "Ev2.2",
                    "type": "Event",
                    "probability": 0.0,
                    "logicGate": "OR",
                    "children": [],
                    "links": []
                },
                {
                    "id": "root_0_2",
                    "name": "Ev1.3",
                    "type": "Event",
                    "probability": 0.8,
                    "logicGate": "OR",
                    "children": [],
                    "links": []
                }
            ],
            "links": []
        }
        result = self.calc.recalculate_probabilities(data)
        # First AND link: 0.5 * 0.8 = 0.4
        # Then OR link: 1 - (1-0.4)*(1-0.0) = 1 - 0.6*1.0 = 0.4
        self.assertEqual(result["children"][0]["calculatedProbability"], 0.4)


def run_tests():
    """Run all tests and print results"""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test cases
    suite.addTests(loader.loadTestsFromTestCase(TestProbabilityCalculation))
    suite.addTests(loader.loadTestsFromTestCase(TestSampleDataValidation))
    
    # Run tests with verbose output
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "="*70)
    print("PROBABILITY CALCULATION VALIDATION SUMMARY")
    print("="*70)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print("="*70)
    
    if result.wasSuccessful():
        print("\n✓ All probability calculation tests passed!")
        print("\nValidated behaviors:")
        print("  • AND gate: calculates product of child probabilities")
        print("  • OR gate: uses union formula 1 - product(1 - p for each child)")
        print("  • AND links: multiply current probability with linked probabilities")
        print("  • OR links: apply union formula with linked probabilities")
        print("  • Mixed links: AND links applied first, then OR links")
        print("  • Circular references: handled via visiting set (uses base probability)")
    else:
        print("\n✗ Some tests failed. See details above.")
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
