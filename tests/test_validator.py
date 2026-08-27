"""
Tests for the AI agent full-JSON validator.
Covers valid structure and common failure modes.
"""
import unittest
import sys
from pathlib import Path

# Ensure repository root is on sys.path
# Add both repo root and src to sys.path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "src"))

from src.AI_agent_handler import AIAgentHandler


def make_min_valid_tree():
    return {
        "id": "root",
        "name": "Root Event",
        "type": "Event",
        "probability": 0.5,
        "logicGate": "OR",
        "notes": "",
        "children": [
            {
                "id": "A",
                "name": "Basic A",
                "type": "Event",
                "probability": 0.2,
                "logicGate": "OR",
                "notes": "",
                "children": [],
                "links": []
            },
            {
                "id": "Gate1",
                "name": "Intermediate Gate",
                "type": "Gate",
                "probability": 0.3,
                "logicGate": "AND",
                "notes": "",
                "children": [
                    {
                        "id": "B",
                        "name": "Basic B",
                        "type": "Event",
                        "probability": 0.4,
                        "logicGate": "OR",
                        "notes": "",
                        "children": [],
                        "links": []
                    }
                ],
                "links": [
                    {"target_id": "A", "relation": "OR"}
                ]
            }
        ],
        "links": []
    }


class TestUpdatedFTAValidator(unittest.TestCase):
    def setUp(self):
        self.handler = AIAgentHandler()

    def test_valid_tree_passes(self):
        data = make_min_valid_tree()
        ok, err = self.handler.verify_updated_fta_json(data)
        self.assertTrue(ok, f"Expected valid tree, got error: {err}")

    def test_missing_root_field_fails(self):
        data = make_min_valid_tree()
        del data["name"]
        ok, err = self.handler.verify_updated_fta_json(data)
        self.assertFalse(ok)
        self.assertIn("Missing root field", err)

    def test_duplicate_id_fails(self):
        data = make_min_valid_tree()
        dup_node = {
            "id": "A",  # duplicate of existing 'A'
            "name": "Duplicate A",
            "type": "Event",
            "probability": 0.1,
            "logicGate": "OR",
            "notes": "",
            "children": [],
            "links": []
        }
        data["children"].append(dup_node)
        ok, err = self.handler.verify_updated_fta_json(data)
        self.assertFalse(ok)
        self.assertIn("Duplicate node ID", err)

    def test_probability_out_of_range_fails(self):
        data = make_min_valid_tree()
        data["children"][0]["probability"] = 1.5
        ok, err = self.handler.verify_updated_fta_json(data)
        self.assertFalse(ok)
        self.assertIn("Probability out of range", err)

    def test_invalid_logic_gate_fails(self):
        data = make_min_valid_tree()
        data["children"][1]["logicGate"] = "XOR"
        ok, err = self.handler.verify_updated_fta_json(data)
        self.assertFalse(ok)
        self.assertIn("Invalid logicGate", err)

    def test_invalid_id_format_fails(self):
        data = make_min_valid_tree()
        data["children"][0]["id"] = "bad-id"
        ok, err = self.handler.verify_updated_fta_json(data)
        self.assertFalse(ok)
        self.assertIn("Invalid node ID", err)

    def test_invalid_links_array_fails(self):
        data = make_min_valid_tree()
        data["children"][0]["links"] = "not-a-list"
        ok, err = self.handler.verify_updated_fta_json(data)
        self.assertFalse(ok)
        self.assertIn("Links must be a list", err)

    def test_invalid_link_relation_fails(self):
        data = make_min_valid_tree()
        data["children"][1]["links"][0]["relation"] = "XAND"
        ok, err = self.handler.verify_updated_fta_json(data)
        self.assertFalse(ok)
        self.assertIn("Invalid link relation", err)


def run_tests():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestUpdatedFTAValidator))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 70)
    print("UPDATED FTA VALIDATOR TEST SUMMARY")
    print("=" * 70)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print("=" * 70)
    return result.wasSuccessful()


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
