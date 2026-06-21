from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .geojson import GeoJSONError, geometry_bounds
from .geometry import haversine_m
from .tools import OverpassClient


ROLE_LABELS: dict[str, str] = {
    "aid_hub": "Aid hub",
    "avoidance_zone": "Avoidance zone",
    "chokepoint": "Chokepoint",
    "civic_anchor": "Civic anchor",
    "comms_relay_candidate": "Comms relay candidate",
    "flow_gate": "Flow gate",
    "pickup_hub": "Pickup hub",
    "reception_site": "Reception site",
    "route_anchor": "Route anchor",
    "shelter_candidate": "Shelter candidate",
    "supply_node": "Supply node",
}


DEFAULT_CONTEXT_SELECTORS = [
    'nwr["amenity"~"hospital|clinic|school|college|university|bus_station|parking|fuel|townhall|courthouse|police|fire_station|community_centre|place_of_worship|marketplace|social_facility"]',
    'nwr["shop"~"mall|supermarket|department_store|wholesale"]',
    'nwr["leisure"~"stadium|park|sports_centre"]',
    'nwr["railway"~"station|halt"]',
    'nwr["public_transport"~"station|platform|stop_position"]',
    'nwr["highway"~"motorway_junction|motorway|trunk|primary|secondary"]',
    'nwr["bridge"]',
    'nwr["natural"~"water|wetland"]',
    'nwr["water"]',
    'nwr["landuse"~"retail|industrial|commercial"]',
    'nwr["man_made"~"tower|communications_tower|water_tower"]',
    'nwr["emergency"~"assembly_point|siren"]',
]


@dataclass(frozen=True)
class MapFeature:
    id: str
    coordinate: list[float]
    tags: dict[str, Any] = field(default_factory=dict)
    geometry: dict[str, Any] | None = None
    roles: dict[str, float] = field(default_factory=dict)
    source_name: str = "map_context"
    source_url: str | None = None

    @property
    def name(self) -> str:
        return str(self.tags.get("name") or self.id)

    def role_score(self, role: str) -> float:
        return float(self.roles.get(role, 0.0))


@dataclass(frozen=True)
class MapCandidate:
    feature: MapFeature
    role: str
    score: float
    reasons: list[str]
    constraints_checked: list[str]
    eligible: bool = True
    rejection_reason: str | None = None
    distance_m: float | None = None

    def summary(self) -> dict[str, Any]:
        data = {
            "id": self.feature.id,
            "name": self.feature.name,
            "role": self.role,
            "score": round(self.score, 3),
            "coordinate": list(self.feature.coordinate),
            "source_url": self.feature.source_url,
            "eligible": self.eligible,
        }
        if self.distance_m is not None:
            data["distance_m"] = round(self.distance_m, 3)
        if self.rejection_reason:
            data["rejection_reason"] = self.rejection_reason
        return data


@dataclass(frozen=True)
class MapSelection:
    selected: MapCandidate
    rejected_alternatives: list[MapCandidate] = field(default_factory=list)

    def metadata(self, rationale: str | None = None) -> dict[str, Any]:
        feature = self.selected.feature
        metadata: dict[str, Any] = {
            "source_type": "map_context",
            "source_name": feature.source_name,
            "source_url": feature.source_url,
            "confidence": _confidence_for_score(self.selected.score),
            "selected_role": self.selected.role,
            "candidate_score": round(self.selected.score, 3),
            "constraints_checked": list(self.selected.constraints_checked),
            "evidence": [
                {
                    "id": feature.id,
                    "name": feature.name,
                    "coordinate": list(feature.coordinate),
                    "roles": dict(feature.roles),
                    "tags": _evidence_tags(feature.tags),
                    "source_url": feature.source_url,
                }
            ],
            "rejected_alternatives": [item.summary() for item in self.rejected_alternatives],
        }
        if rationale:
            metadata["placement_rationale"] = rationale
        return metadata


class MapContext:
    def __init__(self, features: list[MapFeature], *, bounds: list[float] | None = None) -> None:
        self.features = list(features)
        self.bounds = list(bounds) if bounds is not None else _bounds_for_features(features)

    @classmethod
    def from_geojson(
        cls,
        geojson: dict[str, Any],
        *,
        source_name: str = "GeoJSON",
        bounds: list[float] | None = None,
    ) -> "MapContext":
        return cls(_features_from_geojson(geojson, source_name=source_name), bounds=bounds)

    @classmethod
    def from_overpass_json(
        cls,
        raw: dict[str, Any],
        *,
        source_name: str = "OpenStreetMap via Overpass",
        bounds: list[float] | None = None,
    ) -> "MapContext":
        return cls(_features_from_overpass_json(raw, source_name=source_name), bounds=bounds)

    def roles(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for feature in self.features:
            for role in feature.roles:
                counts[role] = counts.get(role, 0) + 1
        return counts

    def candidates(
        self,
        role: str,
        *,
        near: list[float] | None = None,
        preferred_max_distance_m: float = 25_000,
        far_from: list[dict[str, Any]] | None = None,
        avoid_roles: list[str] | None = None,
        avoid_within_m: float = 500,
        required_tags: dict[str, Any] | None = None,
        limit: int | None = 10,
    ) -> list[MapCandidate]:
        candidates = [
            self._candidate(
                feature,
                role,
                near=near,
                preferred_max_distance_m=preferred_max_distance_m,
                far_from=far_from or [],
                avoid_roles=avoid_roles or [],
                avoid_within_m=avoid_within_m,
                required_tags=required_tags or {},
            )
            for feature in self.features
            if feature.role_score(role) > 0
        ]
        candidates.sort(key=lambda item: (item.eligible, item.score), reverse=True)
        return candidates[:limit] if limit is not None else candidates

    def select_candidate(self, role: str, **kwargs: Any) -> MapSelection:
        candidates = self.candidates(role, limit=None, **kwargs)
        for index, candidate in enumerate(candidates):
            if candidate.eligible:
                rejected = [
                    item
                    for item in candidates[: max(8, index + 4)]
                    if item.feature.id != candidate.feature.id
                ][:5]
                return MapSelection(selected=candidate, rejected_alternatives=rejected)
        raise GeoJSONError(f"No eligible map-context candidate found for role {role!r}.")

    def _candidate(
        self,
        feature: MapFeature,
        role: str,
        *,
        near: list[float] | None,
        preferred_max_distance_m: float,
        far_from: list[dict[str, Any]],
        avoid_roles: list[str],
        avoid_within_m: float,
        required_tags: dict[str, Any],
    ) -> MapCandidate:
        score = feature.role_score(role) * 12.0
        reasons = [f"{ROLE_LABELS.get(role, role)} role score {feature.role_score(role):.1f}."]
        checked = [f"role:{role}"]
        eligible = True
        rejection_reason = None
        distance_m = None

        if feature.tags.get("name"):
            score += 4.0
            reasons.append("Named map feature.")
        if feature.geometry and feature.geometry.get("type") in {"Polygon", "MultiPolygon"}:
            score += 2.0
            reasons.append("Area feature with mapped footprint.")

        for key, expected in required_tags.items():
            checked.append(f"required_tag:{key}")
            if not _tag_matches(feature.tags.get(key), expected):
                eligible = False
                rejection_reason = f"missing required tag {key}={expected}"
                score -= 100.0
            else:
                score += 8.0
                reasons.append(f"Matches required tag {key}.")

        if near is not None:
            checked.append("near")
            distance_m = haversine_m(feature.coordinate, near)
            distance_score = max(0.0, 1.0 - (distance_m / float(preferred_max_distance_m))) * 30.0
            score += distance_score
            reasons.append(f"{distance_m:.0f} m from preferred anchor.")

        for item in far_from:
            label = str(item.get("label") or "avoidance anchor")
            min_distance = float(item.get("min_distance_m", 0))
            coordinate = item.get("coordinate")
            if not _is_coord(coordinate):
                continue
            checked.append(f"far_from:{label}")
            actual = haversine_m(feature.coordinate, coordinate)
            if actual < min_distance:
                eligible = False
                rejection_reason = f"{actual:.0f} m from {label}, below {min_distance:.0f} m minimum"
                score -= 60.0
            else:
                score += min(12.0, (actual - min_distance) / max(min_distance, 1.0) * 8.0)
                reasons.append(f"{actual:.0f} m from {label}.")

        if avoid_roles:
            checked.append("avoid_roles")
            nearest = self._nearest_role_feature(feature.coordinate, avoid_roles)
            if nearest is not None:
                avoid_feature, actual = nearest
                if actual < avoid_within_m:
                    eligible = False
                    rejection_reason = (
                        f"{actual:.0f} m from avoided {','.join(avoid_roles)} feature {avoid_feature.name}"
                    )
                    score -= 60.0
                else:
                    score += min(10.0, actual / max(avoid_within_m, 1.0))
                    reasons.append(f"{actual:.0f} m from nearest avoided role.")

        return MapCandidate(
            feature=feature,
            role=role,
            score=max(0.0, score),
            reasons=reasons,
            constraints_checked=checked,
            eligible=eligible,
            rejection_reason=rejection_reason,
            distance_m=distance_m,
        )

    def _nearest_role_feature(
        self,
        coordinate: list[float],
        roles: list[str],
    ) -> tuple[MapFeature, float] | None:
        matches = [
            (feature, haversine_m(coordinate, feature.coordinate))
            for feature in self.features
            if any(feature.role_score(role) > 0 for role in roles)
        ]
        if not matches:
            return None
        matches.sort(key=lambda item: item[1])
        return matches[0]


class MapContextBuilder:
    def __init__(self, client: OverpassClient | None = None) -> None:
        self.client = client or OverpassClient()

    def build_query(self, bounds: list[float], *, selectors: list[str] | None = None) -> str:
        west, south, east, north = _bounds(bounds)
        bbox = f"({south},{west},{north},{east})"
        clauses = [f"{selector}{bbox};" for selector in (selectors or DEFAULT_CONTEXT_SELECTORS)]
        return "[out:json][timeout:45];\n(\n  " + "\n  ".join(clauses) + "\n);\nout center geom 5000;"

    def build_from_overpass(self, bounds: list[float], *, selectors: list[str] | None = None) -> MapContext:
        raw = self.client.execute_query(self.build_query(bounds, selectors=selectors))
        return MapContext.from_overpass_json(raw, bounds=bounds)

    def build_from_geojson(self, geojson: dict[str, Any], *, source_name: str = "GeoJSON") -> MapContext:
        return MapContext.from_geojson(geojson, source_name=source_name)


def classify_feature(tags: dict[str, Any]) -> dict[str, float]:
    tags = {str(key): str(value) for key, value in tags.items() if value is not None}
    roles: dict[str, float] = {}

    amenity = tags.get("amenity", "")
    shop = tags.get("shop", "")
    leisure = tags.get("leisure", "")
    railway = tags.get("railway", "")
    public_transport = tags.get("public_transport", "")
    highway = tags.get("highway", "")
    natural = tags.get("natural", "")
    landuse = tags.get("landuse", "")
    man_made = tags.get("man_made", "")
    emergency = tags.get("emergency", "")

    if amenity in {"hospital", "clinic"}:
        _add_role(roles, "reception_site", 5)
        _add_role(roles, "aid_hub", 4)
    if amenity in {"school", "college", "university", "community_centre", "place_of_worship"}:
        _add_role(roles, "reception_site", 3)
        _add_role(roles, "shelter_candidate", 4)
        _add_role(roles, "aid_hub", 3)
    if shop in {"mall", "department_store", "supermarket", "wholesale"} or landuse == "retail":
        _add_role(roles, "pickup_hub", 4)
        _add_role(roles, "supply_node", 3)
        _add_role(roles, "aid_hub", 3)
    if amenity == "parking":
        _add_role(roles, "pickup_hub", 4)
        _add_role(roles, "aid_hub", 3)
        _add_role(roles, "supply_node", 2)
    if leisure in {"stadium", "sports_centre"}:
        _add_role(roles, "pickup_hub", 4)
        _add_role(roles, "aid_hub", 3)
    if amenity in {"bus_station"} or railway in {"station", "halt"} or public_transport in {"station", "platform"}:
        _add_role(roles, "pickup_hub", 5)
        _add_role(roles, "route_anchor", 3)
    if amenity in {"townhall", "courthouse"} or tags.get("office") == "government":
        _add_role(roles, "civic_anchor", 5)
        _add_role(roles, "aid_hub", 2)
    if amenity in {"fuel", "marketplace"} or landuse in {"industrial", "commercial"}:
        _add_role(roles, "supply_node", 3)
    if highway in {"motorway_junction", "motorway", "trunk", "primary", "secondary"}:
        _add_role(roles, "flow_gate", 3 if highway != "motorway_junction" else 5)
        _add_role(roles, "route_anchor", 3)
    if tags.get("bridge") and tags.get("bridge") != "no":
        _add_role(roles, "chokepoint", 5)
        _add_role(roles, "flow_gate", 2)
    if natural in {"water", "wetland"} or tags.get("water"):
        _add_role(roles, "avoidance_zone", 5)
    if landuse == "industrial":
        _add_role(roles, "avoidance_zone", 2)
    if man_made in {"tower", "communications_tower", "water_tower"} or tags.get("tower:type") in {"communication", "communications"}:
        _add_role(roles, "comms_relay_candidate", 5)
    if amenity in {"fire_station", "police"}:
        _add_role(roles, "comms_relay_candidate", 2)
        _add_role(roles, "civic_anchor", 2)
    if emergency == "assembly_point":
        _add_role(roles, "shelter_candidate", 5)
        _add_role(roles, "reception_site", 3)

    return roles


def _features_from_geojson(geojson: dict[str, Any], *, source_name: str) -> list[MapFeature]:
    items = geojson.get("features", []) if geojson.get("type") == "FeatureCollection" else [geojson]
    features = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        geometry = item.get("geometry") if item.get("type") == "Feature" else item
        if not isinstance(geometry, dict):
            continue
        properties = item.get("properties", {}) if isinstance(item.get("properties"), dict) else {}
        coordinate = _geometry_center(geometry)
        roles = classify_feature(properties)
        feature_id = _feature_id(properties, fallback=f"feature_{index + 1}")
        features.append(
            MapFeature(
                id=feature_id,
                coordinate=coordinate,
                tags=dict(properties),
                geometry=geometry,
                roles=roles,
                source_name=source_name,
                source_url=_source_url(properties),
            )
        )
    return features


def _features_from_overpass_json(raw: dict[str, Any], *, source_name: str) -> list[MapFeature]:
    features = []
    for index, element in enumerate(raw.get("elements", [])):
        if not isinstance(element, dict):
            continue
        geometry = _overpass_geometry(element)
        if geometry is None:
            continue
        tags = dict(element.get("tags") or {})
        osm_type = str(element.get("type") or "element")
        osm_id = element.get("id")
        tags.setdefault("osm_type", osm_type)
        if osm_id is not None:
            tags.setdefault("osm_id", osm_id)
        roles = classify_feature(tags)
        feature_id = _feature_id(tags, fallback=f"{osm_type}_{osm_id or index + 1}")
        features.append(
            MapFeature(
                id=feature_id,
                coordinate=_geometry_center(geometry),
                tags=tags,
                geometry=geometry,
                roles=roles,
                source_name=source_name,
                source_url=_osm_url(osm_type, osm_id),
            )
        )
    return features


def _overpass_geometry(element: dict[str, Any]) -> dict[str, Any] | None:
    element_type = element.get("type")
    if element_type == "node" and "lon" in element and "lat" in element:
        return {"type": "Point", "coordinates": [float(element["lon"]), float(element["lat"])]}
    if isinstance(element.get("center"), dict):
        center = element["center"]
        if "lon" in center and "lat" in center:
            return {"type": "Point", "coordinates": [float(center["lon"]), float(center["lat"])]}
    if isinstance(element.get("geometry"), list):
        coords = [[float(point["lon"]), float(point["lat"])] for point in element["geometry"]]
        if len(coords) >= 2:
            if coords[0] == coords[-1] and len(coords) >= 4:
                return {"type": "Polygon", "coordinates": [coords]}
            return {"type": "LineString", "coordinates": coords}
    return None


def _geometry_center(geometry: dict[str, Any]) -> list[float]:
    if geometry.get("type") == "Point":
        coordinates = geometry.get("coordinates")
        if _is_coord(coordinates):
            return [float(coordinates[0]), float(coordinates[1])]
    west, south, east, north = geometry_bounds(geometry)
    return [(west + east) / 2.0, (south + north) / 2.0]


def _feature_id(properties: dict[str, Any], *, fallback: str) -> str:
    osm_type = properties.get("osm_type")
    osm_id = properties.get("osm_id")
    if osm_type and osm_id:
        return f"osm:{osm_type}:{osm_id}"
    if properties.get("id"):
        return str(properties["id"])
    if properties.get("name"):
        return "name:" + str(properties["name"]).strip().lower().replace(" ", "_")
    return fallback


def _source_url(properties: dict[str, Any]) -> str | None:
    if properties.get("source_url"):
        return str(properties["source_url"])
    return _osm_url(properties.get("osm_type"), properties.get("osm_id"))


def _osm_url(osm_type: Any, osm_id: Any) -> str | None:
    if osm_type and osm_id:
        return f"https://www.openstreetmap.org/{osm_type}/{osm_id}"
    return None


def _evidence_tags(tags: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "name",
        "amenity",
        "shop",
        "leisure",
        "railway",
        "public_transport",
        "highway",
        "bridge",
        "natural",
        "water",
        "landuse",
        "man_made",
        "emergency",
        "osm_type",
        "osm_id",
    ]
    return {key: tags[key] for key in keys if key in tags}


def _confidence_for_score(score: float) -> str:
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def _tag_matches(actual: Any, expected: Any) -> bool:
    if isinstance(expected, list | tuple | set):
        return str(actual) in {str(item) for item in expected}
    return str(actual) == str(expected)


def _add_role(roles: dict[str, float], role: str, score: float) -> None:
    roles[role] = max(float(score), roles.get(role, 0.0))


def _bounds(bounds: list[float]) -> tuple[float, float, float, float]:
    if not isinstance(bounds, list) or len(bounds) != 4:
        raise GeoJSONError("Map context bounds must be [west, south, east, north].")
    west, south, east, north = [float(item) for item in bounds]
    if west >= east or south >= north:
        raise GeoJSONError("Map context bounds are invalid.")
    return west, south, east, north


def _bounds_for_features(features: list[MapFeature]) -> list[float] | None:
    if not features:
        return None
    lons = [feature.coordinate[0] for feature in features]
    lats = [feature.coordinate[1] for feature in features]
    return [min(lons), min(lats), max(lons), max(lats)]


def _is_coord(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) >= 2
        and isinstance(value[0], (int, float))
        and isinstance(value[1], (int, float))
    )
