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
        self.assertEqual(metadata["selected_candidate"]["name"], "Central Transit")
        self.assertGreaterEqual(len(metadata["ranked_candidates"]), 2)

    def test_prefer_tags_boosts_matching_candidate(self):
        context = MapContext.from_geojson(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"name": "Close Mall", "shop": "mall", "access": "private"},
                        "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
                    },
                    {
                        "type": "Feature",
                        "properties": {"name": "Public Mall", "shop": "mall", "access": "public"},
                        "geometry": {"type": "Point", "coordinates": [0.001, 0.0]},
                    },
                ],
            }
        )

        selection = context.select_candidate(
            "pickup_hub",
            near=[0.0, 0.0],
            preferred_max_distance_m=10_000,
            prefer_tags={"access": ["public", "yes"]},
        )

        self.assertEqual(selection.selected.feature.name, "Public Mall")
        self.assertIn("prefer_tag:access", selection.selected.constraints_checked)

    def test_exclude_tags_rejects_matching_candidate(self):
        context = MapContext.from_geojson(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"name": "Private Supermarket", "shop": "supermarket", "access": "private"},
                        "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
                    },
                    {
                        "type": "Feature",
                        "properties": {"name": "Public Mall", "shop": "mall", "access": "public"},
                        "geometry": {"type": "Point", "coordinates": [0.01, 0.0]},
                    },
                ],
            }
        )

        selection = context.select_candidate(
            "pickup_hub",
            near=[0.0, 0.0],
            preferred_max_distance_m=10_000,
            exclude_tags={"access": "private"},
        )

        self.assertEqual(selection.selected.feature.name, "Public Mall")
        rejected = {item.feature.name: item for item in selection.rejected_alternatives}
        self.assertFalse(rejected["Private Supermarket"].eligible)
        self.assertIn("excluded tag access=private", rejected["Private Supermarket"].rejection_reason)

    def test_polygon_avoidance_rejects_candidate_inside_avoidance_zone(self):
        context = MapContext.from_geojson(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"name": "Flooded Mall", "shop": "mall"},
                        "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
                    },
                    {
                        "type": "Feature",
                        "properties": {"name": "Dry Mall", "shop": "mall"},
                        "geometry": {"type": "Point", "coordinates": [0.02, 0.0]},
                    },
                    {
                        "type": "Feature",
                        "properties": {"name": "Flood Zone", "natural": "water", "water": "lake"},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [[[-0.01, -0.01], [0.01, -0.01], [0.01, 0.01], [-0.01, 0.01], [-0.01, -0.01]]],
                        },
                    },
                ],
            }
        )

        selection = context.select_candidate(
            "pickup_hub",
            near=[0.0, 0.0],
            preferred_max_distance_m=10_000,
            avoid_roles=["avoidance_zone"],
            avoid_within_m=500,
        )

        self.assertEqual(selection.selected.feature.name, "Dry Mall")
        rejected = {item.feature.name: item for item in selection.rejected_alternatives}
        self.assertFalse(rejected["Flooded Mall"].eligible)
        self.assertIn("inside avoided avoidance_zone feature Flood Zone", rejected["Flooded Mall"].rejection_reason)

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

    def test_strict_placement_qa_can_require_new_selection_metadata(self):
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
                    "metadata": {
                        "placement_rationale": "Looks useful.",
                        "candidate_score": 60,
                        "confidence": "low",
                        "rejected_alternatives": [],
                    },
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
                    "require_constraints_checked": True,
                    "require_selected_role": True,
                    "require_source_url_or_osm_id": True,
                    "min_rejected_alternatives": 1,
                    "reject_low_confidence": True,
                }
            },
        )
        codes = {issue["code"] for issue in qa["issues"]}
        self.assertIn("missing_constraints_checked", codes)
        self.assertIn("missing_selected_role", codes)
        self.assertIn("missing_placement_source_identifier", codes)
        self.assertIn("rejected_alternatives_low", codes)
        self.assertIn("placement_confidence_low", codes)


if __name__ == "__main__":
    unittest.main()
