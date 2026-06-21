import unittest

from milmap_engine import ScenarioAgent
from milmap_engine.geojson import GeoJSONError
from milmap_engine.scenario import ScenarioCompiler
from milmap_engine.models import ScenarioPlan


class ScenarioTests(unittest.TestCase):
    def test_scenario_agent_builds_styled_payload(self):
        result = ScenarioAgent().execute(
            {
                "scenario_name": "Training Setup",
                "map_context": {
                    "mode": "simulation",
                    "center": [-82.324, 27.845],
                    "zoom": 11,
                },
                "objects": [
                    {
                        "type": "base",
                        "name": "Base Alpha",
                        "placement": {
                            "mode": "point",
                            "coordinate": [-82.324, 27.845],
                        },
                        "properties": {"role": "logistics"},
                    }
                ],
                "layers": [
                    {
                        "type": "perimeter",
                        "name": "Base Alpha Perimeter",
                        "operation": "buffer",
                        "parameters": {
                            "center": [-82.324, 27.845],
                            "radius_km": 5,
                            "steps": 16,
                        },
                        "style": {"fill_opacity": 0.25},
                    },
                    {
                        "type": "route",
                        "name": "Main Route",
                        "operation": "line",
                        "parameters": {
                            "coordinates": [
                                [-82.35, 27.84],
                                [-82.31, 27.86],
                            ]
                        },
                    },
                ],
            }
        )

        self.assertEqual(result["type"], "Scenario")
        self.assertEqual(result["scenario_id"], "training_setup")
        self.assertEqual(len(result["objects"]), 1)
        self.assertEqual(len(result["layers"]), 2)
        self.assertEqual(len(result["geojson"]["features"]), 3)

        perimeter = result["layers"][0]
        self.assertEqual(perimeter["id"], "base_alpha_perimeter")
        self.assertEqual(perimeter["plan"]["pipeline"], "abstract")
        self.assertEqual(perimeter["plan"]["operation"], "buffer")
        self.assertEqual(perimeter["style"]["fill_opacity"], 0.25)
        self.assertEqual(perimeter["geojson"]["properties"]["layer_type"], "perimeter")
        self.assertEqual(perimeter["geojson"]["properties"]["style"]["line_dasharray"], [4, 2])

        route = result["layers"][1]
        self.assertEqual(route["plan"]["pipeline"], "direct")
        self.assertEqual(route["geojson"]["geometry"]["type"], "LineString")
        self.assertEqual(route["geojson"]["properties"]["style"]["stroke_width"], 4)

        base = result["objects"][0]
        self.assertEqual(base["id"], "base_alpha")
        self.assertEqual(base["geometry"]["type"], "Point")
        self.assertEqual(base["style"]["icon"], "warehouse")

    def test_compiler_rejects_unknown_layer_operation_without_guessing(self):
        plan = ScenarioPlan.from_mapping(
            {
                "scenario_name": "Ambiguous",
                "layers": [
                    {
                        "type": "perimeter",
                        "parameters": {
                            "center": [-82.324, 27.845],
                            "radius_km": 5,
                        },
                    }
                ],
            }
        )
        with self.assertRaises(GeoJSONError):
            ScenarioCompiler().compile_layers(plan)


if __name__ == "__main__":
    unittest.main()
