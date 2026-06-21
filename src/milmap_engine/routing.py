from __future__ import annotations

import json
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from . import geometry
from .geojson import GeoJSONError, feature


class RoutingError(GeoJSONError):
    """Raised when a routing backend cannot return usable route geometry."""


class OSRMRoutingClient:
    def __init__(
        self,
        endpoint: str = "https://router.project-osrm.org",
        *,
        profile: str = "driving",
        timeout_s: int = 30,
        user_agent: str = "MILMAP Engine/0.1",
        urlopen: Callable[..., Any] | None = None,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.profile = profile
        self.timeout_s = timeout_s
        self.user_agent = user_agent
        self._urlopen = urlopen or urllib.request.urlopen

    def route(self, waypoints: list[Any], *, profile: str | None = None) -> dict[str, Any]:
        coordinates = _coordinates(waypoints)
        route_profile = str(profile or self.profile)
        url = self._route_url(coordinates, route_profile)
        request = urllib.request.Request(
            url,
            headers={"User-Agent": self.user_agent},
            method="GET",
        )
        try:
            with self._urlopen(request, timeout=self.timeout_s) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # pragma: no cover - exercised via failure path
            raise RoutingError(f"OSRM route request failed: {exc}") from exc

        if raw.get("code") != "Ok":
            message = raw.get("message") or raw.get("code") or "unknown OSRM error"
            raise RoutingError(f"OSRM route request failed: {message}")
        routes = raw.get("routes")
        if not isinstance(routes, list) or not routes:
            raise RoutingError("OSRM route response did not include a route.")
        route = routes[0]
        if not isinstance(route, dict):
            raise RoutingError("OSRM route response did not include a route object.")
        geometry_obj = route.get("geometry")
        route_coordinates = geometry_obj.get("coordinates") if isinstance(geometry_obj, dict) else None
        if not isinstance(geometry_obj, dict) or geometry_obj.get("type") != "LineString" or not isinstance(route_coordinates, list):
            raise RoutingError("OSRM route response did not include LineString geometry.")

        snapped = []
        for item in raw.get("waypoints", []):
            if isinstance(item, dict) and isinstance(item.get("location"), list):
                snapped.append([float(item["location"][0]), float(item["location"][1])])

        return {
            "coordinates": _coordinates(route_coordinates),
            "distance_m": float(route.get("distance", 0.0)),
            "duration_s": float(route.get("duration", 0.0)),
            "profile": route_profile,
            "source_name": "OSRM public demo server",
            "source_url": url,
            "snapped_waypoints": snapped,
        }

    def route_geojson(self, arguments: dict[str, Any]) -> dict[str, Any]:
        waypoints = arguments.get("waypoints", arguments.get("coordinates"))
        if not isinstance(waypoints, list):
            raise RoutingError("OSRM route requires waypoints or coordinates.")
        result = self.route(waypoints, profile=_optional_str(arguments.get("profile")))
        return feature(
            geometry.line_string(result["coordinates"]),
            {
                "source": "osrm",
                "source_name": result["source_name"],
                "source_url": result["source_url"],
                "profile": result["profile"],
                "distance_m": round(float(result["distance_m"]), 3),
                "duration_s": round(float(result["duration_s"]), 3),
            },
        )

    def _route_url(self, coordinates: list[list[float]], profile: str) -> str:
        coord_path = ";".join(f"{coord[0]:.6f},{coord[1]:.6f}" for coord in coordinates)
        query = urllib.parse.urlencode(
            {
                "overview": "full",
                "geometries": "geojson",
                "steps": "false",
                "alternatives": "false",
            }
        )
        quoted_profile = urllib.parse.quote(profile, safe="")
        return f"{self.endpoint}/route/v1/{quoted_profile}/{coord_path}?{query}"


def _coordinates(raw: list[Any]) -> list[list[float]]:
    coordinates = []
    for item in raw:
        if not isinstance(item, list | tuple) or len(item) < 2:
            raise RoutingError("Route waypoints must be [longitude, latitude] pairs.")
        lon = float(item[0])
        lat = float(item[1])
        if not -180.0 <= lon <= 180.0 or not -90.0 <= lat <= 90.0:
            raise RoutingError("Route waypoint is outside longitude/latitude bounds.")
        coordinates.append([lon, lat])
    if len(coordinates) < 2:
        raise RoutingError("A route needs at least two waypoints.")
    return coordinates


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
