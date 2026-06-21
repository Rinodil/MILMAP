from __future__ import annotations

import math
from dataclasses import dataclass

Coordinate = list[float] | tuple[float, float]
Point2D = tuple[float, float]


@dataclass(frozen=True)
class LocalProjector:
    """Small-area lon/lat <-> meter projection around an origin."""

    origin: Coordinate

    def __post_init__(self) -> None:
        lon, lat = self.origin
        lat_rad = math.radians(lat)
        meters_per_deg_lat = (
            111132.92
            - 559.82 * math.cos(2 * lat_rad)
            + 1.175 * math.cos(4 * lat_rad)
            - 0.0023 * math.cos(6 * lat_rad)
        )
        meters_per_deg_lon = (
            111412.84 * math.cos(lat_rad)
            - 93.5 * math.cos(3 * lat_rad)
            + 0.118 * math.cos(5 * lat_rad)
        )
        object.__setattr__(self, "_lon0", float(lon))
        object.__setattr__(self, "_lat0", float(lat))
        object.__setattr__(self, "_meters_per_deg_lon", meters_per_deg_lon)
        object.__setattr__(self, "_meters_per_deg_lat", meters_per_deg_lat)

    def project(self, coord: Coordinate) -> Point2D:
        lon, lat = coord
        x = (float(lon) - self._lon0) * self._meters_per_deg_lon
        y = (float(lat) - self._lat0) * self._meters_per_deg_lat
        return x, y

    def unproject(self, point: Point2D) -> list[float]:
        x, y = point
        lon = self._lon0 + x / self._meters_per_deg_lon
        lat = self._lat0 + y / self._meters_per_deg_lat
        return [lon, lat]


def projector_for_bounds(bounds: list[float] | tuple[float, float, float, float]) -> LocalProjector:
    west, south, east, north = bounds
    return LocalProjector([(west + east) / 2.0, (south + north) / 2.0])


def projector_for_coordinates(coords: list[Coordinate]) -> LocalProjector:
    lon = sum(float(coord[0]) for coord in coords) / len(coords)
    lat = sum(float(coord[1]) for coord in coords) / len(coords)
    return LocalProjector([lon, lat])

