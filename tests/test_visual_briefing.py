import json
import tempfile
import unittest
from pathlib import Path

from milmap_engine import ScenarioAgent, ScenarioStore
from milmap_engine.visual_briefing import (
    build_visual_briefing_package,
    create_visual_briefing_for_scenario,
    save_visual_briefing_package,
)


def scenario_payload():
    return ScenarioAgent().execute(
        {
            "scenario_name": "Visual Briefing Test",
            "map_context": {
                "mode": "civil_emergency",
                "center": [-82.4572, 27.9506],
                "bounds": [-82.62, 27.82, -82.30, 28.08],
            },
            "layers": [
                {
                    "id": "service_area",
                    "type": "perimeter",
                    "name": "Service Area",
                    "operation": "buffer",
                    "parameters": {
                        "center": [-82.4572, 27.9506],
                        "radius_km": 3,
                        "steps": 16,
                    },
                }
            ],
            "objects": [
                {
                    "id": "command_node",
                    "type": "base",
                    "name": "Command Node",
                    "placement": {
                        "mode": "point",
                        "coordinate": [-82.4572, 27.9506],
                    },
                }
            ],
        }
    )


class VisualBriefingTests(unittest.TestCase):
    def test_build_package_includes_safe_prompt_and_openai_handoff(self):
        package = build_visual_briefing_package(scenario_payload())

        self.assertEqual(package["type"], "VisualBriefingPackage")
        self.assertEqual(package["source_scenario_id"], "visual_briefing_test")
        self.assertEqual(package["openai"]["model"], "gpt-image-2")
        self.assertEqual(package["openai"]["api_mode"], "image_generation")
        self.assertIn("not a targeting product", package["disclaimer"])
        self.assertIn("Do not depict weapon targeting", package["prompt"])
        self.assertIn("QA score:", package["prompt"])
        self.assertIn("Service Area", package["prompt"])
        self.assertIn("Command Node", package["prompt"])

    def test_save_package_copies_reference_images_and_writes_handoff_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            image = tmp_path / "map.png"
            image.write_bytes(b"fake-png-reference")
            package = build_visual_briefing_package(scenario_payload(), screenshot_path=image)
            result = save_visual_briefing_package(package, tmp_path / "briefing")

            manifest = Path(result["manifest"])
            summary = Path(result["summary"])
            prompt = Path(result["prompt"])
            handoff = Path(result["chatgpt_handoff"])
            packaged_image = Path(result["package"]["image_inputs"][0]["packaged_path"])

            self.assertTrue(manifest.is_file())
            self.assertTrue(summary.is_file())
            self.assertTrue(prompt.is_file())
            self.assertTrue(handoff.is_file())
            self.assertTrue(packaged_image.is_file())
            self.assertEqual(result["reference_count"], 1)
            manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(manifest_data["openai"]["api_mode"], "image_edit_with_references")
            summary_data = json.loads(summary.read_text(encoding="utf-8"))
            self.assertEqual(summary_data["type"], "BriefingSummary")
            self.assertIn("legend_text", summary_data)

    def test_create_visual_briefing_for_saved_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            store = ScenarioStore(tmp_path / "scenarios.json")
            payload = scenario_payload()
            store.save({"scenario_name": "Visual Briefing Test"}, payload)

            result = create_visual_briefing_for_scenario(
                "visual_briefing_test",
                store=store,
                out_dir=tmp_path / "visual",
            )

            self.assertEqual(result["type"], "VisualBriefing")
            self.assertEqual(result["scenario_id"], "visual_briefing_test")
            self.assertTrue(Path(result["package"]["manifest"]).is_file())


if __name__ == "__main__":
    unittest.main()
