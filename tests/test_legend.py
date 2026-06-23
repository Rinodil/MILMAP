import unittest

from milmap_engine.legend import scenario_legend_entries, scenario_legend_text
from milmap_engine.notify import build_url


class LegendTests(unittest.TestCase):
    def test_scenario_legend_text_describes_color_symbol_and_name(self):
        payload = {
            "layers": [
                {
                    "id": "friendly_comms",
                    "name": "Friendly Comms",
                    "type": "range_ring",
                    "style": {"stroke_color": "#2563eb", "stroke_width": 2},
                    "geojson": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
                },
                {
                    "id": "flood_area",
                    "name": "Flood Area",
                    "type": "restricted_zone",
                    "style": {"fill_color": "#38bdf8", "stroke_color": "#0284c7"},
                    "geojson": {
                        "type": "Polygon",
                        "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]],
                    },
                },
            ],
            "objects": [
                {
                    "id": "aid_node",
                    "name": "Aid Node",
                    "type": "aid_station",
                    "style": {"marker_color": "#22c55e"},
                    "geometry": {"type": "Point", "coordinates": [0, 0]},
                }
            ],
        }

        entries = scenario_legend_entries(payload)
        text = scenario_legend_text(payload)

        self.assertEqual(len(entries), 3)
        self.assertIn("blue line: Friendly Comms", text)
        self.assertIn("light blue area: Flood Area", text)
        self.assertIn("green point: Aid Node", text)

    def test_build_url_supports_presentation_and_legend_modes(self):
        url = build_url(
            "http://127.0.0.1:8004",
            "lebanon_map_test",
            "osm",
            presentation=True,
            show_legend=False,
        )

        self.assertEqual(
            url,
            "http://127.0.0.1:8004/?scenario=lebanon_map_test&basemap=osm&presentation=1&legend=0",
        )


if __name__ == "__main__":
    unittest.main()
