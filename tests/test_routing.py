import json
import unittest

from milmap_engine import OSRMRoutingClient, SpatialAgent, ToolRegistry
from milmap_engine.routing import RoutingError


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class OSRMRoutingClientTests(unittest.TestCase):
    def test_route_returns_detailed_geometry_and_source_url(self):
        calls = []

        def fake_urlopen(request, timeout):
            calls.append((request, timeout))
            return FakeResponse(
                {
                    "code": "Ok",
                    "routes": [
                        {
                            "distance": 1234.5,
                            "duration": 321.0,
                            "geometry": {
                                "type": "LineString",
                                "coordinates": [
                                    [-81.3792, 28.5383],
                                    [-81.38, 28.539],
                                    [-81.423, 28.541],
                                ],
                            },
                        }
                    ],
                    "waypoints": [{"location": [-81.3791, 28.5382]}, {"location": [-81.4231, 28.5411]}],
                }
            )

        client = OSRMRoutingClient(endpoint="https://example.test", timeout_s=7, urlopen=fake_urlopen)
        result = client.route([[-81.3792, 28.5383], [-81.423, 28.541]])

        self.assertEqual(result["distance_m"], 1234.5)
        self.assertEqual(len(result["coordinates"]), 3)
        self.assertIn("/route/v1/driving/", result["source_url"])
        self.assertIn("geometries=geojson", result["source_url"])
        self.assertEqual(calls[0][1], 7)

    def test_route_geojson_can_back_spatial_agent_tool_operation(self):
        client = OSRMRoutingClient(
            urlopen=lambda _request, timeout: FakeResponse(
                {
                    "code": "Ok",
                    "routes": [
                        {
                            "distance": 10.0,
                            "duration": 2.0,
                            "geometry": {
                                "type": "LineString",
                                "coordinates": [[0.0, 0.0], [0.001, 0.001]],
                            },
                        }
                    ],
                }
            )
        )
        registry = ToolRegistry()
        registry.register("osrm_route", client.route_geojson)
        geojson = SpatialAgent(tools=registry).execute(
            {
                "pipeline": "real_world",
                "operation": "osrm_route",
                "parameters": {"waypoints": [[0.0, 0.0], [0.001, 0.001]]},
            }
        )

        self.assertEqual(geojson["geometry"]["type"], "LineString")
        self.assertEqual(geojson["properties"]["source"], "osrm")

    def test_route_rejects_single_waypoint(self):
        client = OSRMRoutingClient(urlopen=lambda *_args, **_kwargs: None)
        with self.assertRaises(RoutingError):
            client.route([[0.0, 0.0]])


if __name__ == "__main__":
    unittest.main()
