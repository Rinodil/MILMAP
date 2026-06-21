import unittest

from milmap_engine import MapContext, MapContextBuilder
from milmap_engine.map_context import classify_feature
from milmap_engine.validation import validate_scenario_payload


def fixture_geojson():
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "osm_type": "way",
                    "osm_id": 10,
                    "name": "Central Hospital",
                    "amenity": "hospital",
                },
                "geometry": {"type": "Point", "coordinates": [0.020, 0.000]},
            },
            {
                "type": "Feature",
                "properties": {
                    "osm_type": "relation",
                    "osm_id": 20,
                    "name": "Central Transit",
                    "railway": "station",
                    "public_transport": "station",
                },
                "geometry": {"type": "Point", "coordinates": [0.000, 0.000]},
            },
            {
                "type": "Feature",
                "properties": {
                    "osm_type": "way",
                    "osm_id": 30,
                    "name": "Retail Mall",
                    "shop": "mall",
                    "landuse": "retail",
                },
                "geometry": {"type": "Point", "coordinates": [0.045, 0.010]},
            },
            {
                "type": "Feature",
                "properties": {
                    "osm_type": "way",
                    "osm_id": 40,
                    "name": "Training Lake",
                    "natural": "water",
                    "water": "lake",
                },
                "geometry": {"type": "Polygon", "coordinates": [[[0.018, -0.002], [0.024, -0.002], [0.024, 0.004], [0.018, -0.002]]]},
            },
            {
                "type": "Feature",
                "properties": {
                    "osm_type": "node",
                    "osm_id": 50,
                    "name": "City Hall",
                    "amenity": "townhall",
                },
                "geometry": {"type": "Point", "coordinates": [-0.015, 0.003]},
            },
        ],
    }


class MapContextTests(unittest.TestCase):
    def test_classify_feature_assigns_semantic_roles(self):
        roles = classify_feature({"amenity": "hospital", "name": "Hospital"})
        self.assertGreaterEqual(roles["reception_site"], 5)
        self.assertIn("aid_hub", roles)

        roles = classify_feature({"railway": "station", "public_transport": "station"})
        self.assertGreaterEqual(roles["pickup_hub"], 5)

    def test_select_candidate_returns_evidence_and_rejected_alternatives(self):
        context = MapContext.from_geojson(fixture_geojson(), source_name="fixture")
        selection = context.select_candidate(
            "pickup_hub",
            near=[0.0, 0.0],
            preferred_max_distance_m=10_000,
            avoid_roles=["avoidance_zone"],
            avoid_within_m=500,
        )

        self.assertEqual(selection.selected.feature.name, "Central Transit")
        metadata = selection.metadata("Use nearest transit pickup outside avoidance zones.")
        self.assertEqual(metadata["source_type"], "map_context")
        self.assertGreater(metadata["candidate_score"], 40)
        self.assertTrue(metadata["evidence"])
        self.assertIsInstance(metadata["rejected_alternatives"], list)
        self.assertIn("placement_rationale", metadata)

    def test_overpass_query_builder_uses_bbox_order(self):
        query = MapContextBuilder().build_query([-1.0, -2.0, 3.0, 4.0], selectors=['nwr["amenity"="hospital"]'])
        self.assertIn('nwr["amenity"="hospital"](-2.0,-1.0,4.0,3.0);', query)
        self.assertIn("out center geom", query)

    def test_strict_placement_qa_requires_candidate_metadata(self):
        payload = {
            "type": "Scenario",
            "scenario_id": "fixture",
            "scenario_name": "fixture",
            "map_context": {},
            "layers": [],
            "objects": [
                {
                    "id": "node",
                    "type": "supply_node",
                    "name": "Node",
                    "style": {"marker_color": "#2563eb"},
                    "properties": {},
                    "metadata": {"placement_rationale": "Looks useful."},
                    "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
                }
            ],
            "geojson": {"type": "FeatureCollection", "features": []},
        }
        qa = validate_scenario_payload(
            payload,
            validation_rules={
                "placement_reasoning": {
                    "enabled": True,
                    "require_evidence": True,
                    "require_rejected_alternatives": True,
                    "min_candidate_score": 50,
                }
            },
        )
        codes = {issue["code"] for issue in qa["issues"]}
        self.assertIn("missing_placement_evidence", codes)
        self.assertIn("missing_rejected_alternatives", codes)
        self.assertIn("missing_candidate_score", codes)


if __name__ == "__main__":
    unittest.main()
