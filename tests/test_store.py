import tempfile
import unittest
from pathlib import Path

from milmap_engine import ScenarioAgent, ScenarioStore


class ScenarioStoreTests(unittest.TestCase):
    def test_store_saves_lists_gets_versions_and_deletes(self):
        plan = {
            "scenario_name": "Store Test",
            "objects": [
                {
                    "type": "base",
                    "name": "Base Alpha",
                    "placement": {
                        "mode": "point",
                        "coordinate": [-82.324, 27.845],
                    },
                }
            ],
            "layers": [
                {
                    "type": "perimeter",
                    "operation": "buffer",
                    "parameters": {
                        "center": [-82.324, 27.845],
                        "radius_m": 1000,
                        "steps": 16,
                    },
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmp:
            store = ScenarioStore(Path(tmp) / "scenarios.json")
            payload = ScenarioAgent().execute(plan)

            first = store.save(plan, payload)
            second = store.save(plan, payload)
            summaries = store.list()
            loaded = store.get("store_test")

            self.assertEqual(first["version"], 1)
            self.assertEqual(second["version"], 2)
            self.assertEqual(len(summaries), 1)
            self.assertEqual(summaries[0]["id"], "store_test")
            self.assertEqual(summaries[0]["layer_count"], 1)
            self.assertEqual(summaries[0]["object_count"], 1)
            self.assertEqual(loaded["version"], 2)
            self.assertEqual(len(loaded["versions"]), 1)

            deleted = store.delete("store_test")
            self.assertEqual(deleted["id"], "store_test")
            self.assertEqual(store.list(), [])


if __name__ == "__main__":
    unittest.main()
