"""
Tests for the full-JSON Update FTA flow using a mocked AI response.
"""
import unittest
import json
import sys
from pathlib import Path

# Ensure repository root is on sys.path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "src"))

from src.AI_agent_handler import AIAgentHandler


def base_tree():
    return {
        "id": "root",
        "name": "Root",
        "type": "Event",
        "probability": 0.7,
        "logicGate": "OR",
        "notes": "",
        "children": [
            {
                "id": "A",
                "name": "A",
                "type": "Event",
                "probability": 0.2,
                "logicGate": "OR",
                "notes": "",
                "children": [],
                "links": []
            }
        ],
        "links": []
    }


class TestUpdateFlowWithMock(unittest.TestCase):
    def setUp(self):
        self.handler = AIAgentHandler()

    def test_generate_full_update_parses_json(self):
        current = base_tree()

        # Mock send_message to return plain JSON
        updated = base_tree()
        # Add a new child under root
        updated["children"].append({
            "id": "B",
            "name": "B",
            "type": "Event",
            "probability": 0.3,
            "logicGate": "OR",
            "notes": "",
            "children": [],
            "links": []
        })

        def fake_send_message(msg, include_fta_context=True):
            return (json.dumps(updated), [])

        self.handler.send_message = fake_send_message  # monkeypatch
        text, parsed = self.handler.generate_full_fta_update(current, mode="FTA", title="Mock Test")
        self.assertIsNotNone(parsed, "Expected JSON to be parsed from assistant text")
        ok, err = self.handler.verify_updated_fta_json(parsed)
        self.assertTrue(ok, f"Parsed JSON failed validation: {err}")

    def test_generate_full_update_parses_code_fenced_json(self):
        current = base_tree()

        fenced_json = """```json
{"id":"root","name":"Root","type":"Event","probability":0.7,"logicGate":"OR","notes":"","children":[{"id":"A","name":"A","type":"Event","probability":0.2,"logicGate":"OR","notes":"","children":[],"links":[]},{"id":"Gate1","name":"Gate1","type":"Gate","probability":0.5,"logicGate":"AND","notes":"","children":[{"id":"C","name":"C","type":"Event","probability":0.4,"logicGate":"OR","notes":"","children":[],"links":[]}],"links":[]}],"links":[]}
```"""

        def fake_send_message(msg, include_fta_context=True):
            return (fenced_json, [])

        self.handler.send_message = fake_send_message  # monkeypatch
        text, parsed = self.handler.generate_full_fta_update(current, mode="FTA", title="Fenced JSON")
        self.assertIsNotNone(parsed, "Expected code-fenced JSON to be parsed")
        ok, err = self.handler.verify_updated_fta_json(parsed)
        self.assertTrue(ok, f"Fenced JSON failed validation: {err}")

    def test_generate_full_update_invalid_json_returns_none(self):
        current = base_tree()

        def fake_send_message(msg, include_fta_context=True):
            return ("not-a-json", [])

        self.handler.send_message = fake_send_message  # monkeypatch
        text, parsed = self.handler.generate_full_fta_update(current, mode="FTA", title="Invalid JSON")
        self.assertIsNone(parsed, "Expected parsed to be None for invalid JSON")


def run_tests():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestUpdateFlowWithMock))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    print("\n" + "=" * 70)
    print("FULL-JSON UPDATE FLOW (MOCK) TEST SUMMARY")
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
