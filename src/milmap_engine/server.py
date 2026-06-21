from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .agent import SpatialAgent
from .builder import ScenarioBuilder
from .geojson import GeoJSONError
from .models import ScenarioPlan
from .refinement import ScenarioRefiner
from .scenario import ScenarioAgent
from .store import ScenarioStore
from .tools import default_tool_registry
from .validation import validate_scenario_payload

try:
    from fastapi import FastAPI, HTTPException, Response
    from fastapi.responses import FileResponse
except ModuleNotFoundError:  # pragma: no cover
    FastAPI = None
    HTTPException = None
    Response = None
    FileResponse = None


STATIC_DIR = Path(__file__).resolve().parent / "static"


def _basemap_dir() -> Path:
    """Directory of optional offline tiles (XYZ: ``<type>/<z>/<x>/<y>.png``).

    MILMAP never downloads tiles itself; this only serves tiles already placed
    here legitimately. Override with ``MILMAP_BASEMAP_DIR``.
    """
    return Path(os.environ.get("MILMAP_BASEMAP_DIR", Path.cwd() / ".milmap" / "basemaps"))


# Canonical basemap registry. The online tile URLs are used for interactive
# display, which is the intended, lowest-TOS-risk use of these providers.
# ``offline_tos`` documents the risk of *bulk downloading* each provider for the
# offline path. See docs/basemaps.md. Each basemap maps to an operational
# purpose, and ``keywords`` drive auto-selection from a scenario's map_context.
BASEMAP_REGISTRY: dict[str, dict[str, Any]] = {
    "osm": {
        "label": "OpenStreetMap",
        "purpose": "Standard street reference",
        "tiles": ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
        "tile_size": 256,
        "min_zoom": 0,
        "max_zoom": 19,
        "attribution": "© OpenStreetMap contributors",
        "keywords": ["standard", "reference", "osm", "default"],
        "offline_tos": "prohibited",
        "offline_note": "OSMF tile policy bans bulk download/prefetch/offline use; can get the IP blocked. Self-host instead.",
    },
    "cartodb_dark": {
        "label": "CartoDB Dark",
        "purpose": "Night / low-light operations",
        "tiles": [
            "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
            "https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
            "https://c.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
        ],
        "tile_size": 256,
        "min_zoom": 0,
        "max_zoom": 20,
        "attribution": "© OpenStreetMap contributors, © CARTO",
        "keywords": ["night", "dark", "low-light", "low_light", "lowlight", "blackout", "nocturnal", "nvg"],
        "dark": True,
        "offline_tos": "high",
        "offline_note": "CARTO basemaps are for interactive use; bulk/offline prefetch generally violates terms.",
    },
    "opentopomap": {
        "label": "OpenTopoMap",
        "purpose": "Terrain / off-road navigation",
        "tiles": [
            "https://a.tile.opentopomap.org/{z}/{x}/{y}.png",
            "https://b.tile.opentopomap.org/{z}/{x}/{y}.png",
            "https://c.tile.opentopomap.org/{z}/{x}/{y}.png",
        ],
        "tile_size": 256,
        "min_zoom": 0,
        "max_zoom": 17,
        "attribution": "© OpenTopoMap (CC-BY-SA), © OpenStreetMap contributors",
        "keywords": ["terrain", "topo", "topographic", "elevation", "off-road", "offroad", "mountain", "wilderness", "hike", "tactical"],
        "offline_tos": "low",
        "offline_note": "Most tolerant for moderate offline use; respect rate limits (~2 parallel) and identify your agent.",
    },
    "esri_street": {
        "label": "Esri World Street",
        "purpose": "Urban street-level navigation",
        "tiles": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}"],
        "tile_size": 256,
        "min_zoom": 0,
        "max_zoom": 19,
        "attribution": "© Esri, HERE, Garmin, FAO, NOAA, USGS",
        "keywords": ["street", "urban", "city", "traffic", "emergency", "evac", "evacuation", "disaster", "shtf", "civil", "relief"],
        "offline_tos": "medium",
        "offline_note": "Use official Esri offline packages (.tpk/.vtpk via ArcGIS), not raw tile scraping.",
    },
    "esri_topo": {
        "label": "Esri World Topo",
        "purpose": "Terrain features / elevation",
        "tiles": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}"],
        "tile_size": 256,
        "min_zoom": 0,
        "max_zoom": 19,
        "attribution": "© Esri, HERE, Garmin, FAO, NOAA, USGS",
        "keywords": ["contour", "relief", "topographic-detail", "elevation-detail"],
        "offline_tos": "medium",
        "offline_note": "Use official Esri offline packages (.tpk/.vtpk via ArcGIS), not raw tile scraping.",
    },
}

DEFAULT_BASEMAP = "osm"
# Auto-selection order: the first basemap whose keyword appears in the
# scenario's purpose/mode text wins.
BASEMAP_PURPOSE_ORDER = ["cartodb_dark", "opentopomap", "esri_street", "esri_topo", "osm"]


# --- Self-hosted Protomaps (Florida) vector basemaps --------------------------
# A single Florida PMTiles archive (self-hosted OpenStreetMap-derived vector
# tiles, ODbL) is served locally and styled with Protomaps theme flavors. This
# is the primary, fully self-hosted basemap path: no third-party tile TOS limits.
PROTOMAPS_ASSET_BASE = "/static/basemaps/protomaps"
PROTOMAPS_GLYPHS = f"{PROTOMAPS_ASSET_BASE}/fonts/{{fontstack}}/{{range}}.pbf"
PROTOMAPS_SPRITE_BASE = f"{PROTOMAPS_ASSET_BASE}/sprites/v4"

PROTOMAPS_FLAVORS: dict[str, dict[str, Any]] = {
    "protomaps_light": {
        "label": "Protomaps Light (FL)",
        "purpose": "Urban street-level navigation",
        "flavor": "light",
        "keywords": ["street", "urban", "city", "standard", "reference", "civil", "emergency", "evac", "evacuation", "disaster", "shtf", "relief", "traffic", "day"],
    },
    "protomaps_dark": {
        "label": "Protomaps Dark (FL)",
        "purpose": "Night / low-light operations",
        "flavor": "dark",
        "dark": True,
        "keywords": ["night", "dark", "low-light", "low_light", "lowlight", "blackout", "nocturnal", "nvg", "tactical"],
    },
    "protomaps_grayscale": {
        "label": "Protomaps Grayscale (FL)",
        "purpose": "Terrain / neutral recon base",
        "flavor": "grayscale",
        "keywords": ["terrain", "topo", "topographic", "off-road", "offroad", "mountain", "wilderness", "recon", "neutral", "contour", "relief", "elevation"],
    },
}
DEFAULT_PROTOMAPS = "protomaps_light"
PROTOMAPS_ORDER = ["protomaps_dark", "protomaps_grayscale", "protomaps_light"]

_FLORIDA_STATE: dict[str, Any] = {"reader": None, "file": None}


def _florida_pmtiles_path() -> Path:
    return Path(os.environ.get("MILMAP_PMTILES", Path.cwd() / ".milmap" / "florida.pmtiles"))


def _florida_reader() -> Any:
    """Return a cached PMTiles reader for the Florida archive, or None."""
    if _FLORIDA_STATE["reader"] is not None:
        return _FLORIDA_STATE["reader"]
    path = _florida_pmtiles_path()
    if not path.is_file():
        return None
    try:
        from pmtiles.reader import MmapSource, Reader
    except ModuleNotFoundError:  # pragma: no cover
        return None
    handle = open(path, "rb")
    _FLORIDA_STATE["file"] = handle
    _FLORIDA_STATE["reader"] = Reader(MmapSource(handle))
    return _FLORIDA_STATE["reader"]


def create_app(store: ScenarioStore | None = None) -> Any:
    if FastAPI is None:
        raise RuntimeError('FastAPI is not installed. Install with: pip install -e ".[api]"')

    app = FastAPI(title="MILMAP Engine", version="0.1.0")
    agent = SpatialAgent(tools=default_tool_registry())
    scenario_agent = ScenarioAgent(spatial_agent=agent)
    scenario_store = store or ScenarioStore()
    scenario_builder = ScenarioBuilder(agent=scenario_agent, store=scenario_store)
    scenario_refiner = ScenarioRefiner(agent=scenario_agent, store=scenario_store)

    @app.get("/")
    def index() -> Any:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/static/{path:path}")
    def static_asset(path: str) -> Any:
        asset = (STATIC_DIR / path).resolve()
        if STATIC_DIR.resolve() not in asset.parents:
            raise HTTPException(status_code=404, detail="Asset not found.")
        if not asset.is_file():
            raise HTTPException(status_code=404, detail="Asset not found.")
        return FileResponse(asset)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/agent/execute")
    def execute_plan(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return agent.execute(payload)
        except (GeoJSONError, KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/agent/execute_many")
    def execute_many(payload: list[dict[str, Any]]) -> dict[str, Any]:
        try:
            return agent.execute_many(payload)
        except (GeoJSONError, KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/scenario/execute")
    def execute_scenario(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return scenario_agent.execute(payload)
        except (GeoJSONError, KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/scenario/build")
    def build_scenario(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return scenario_builder.build(payload)
        except (GeoJSONError, KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/scenario")
    def list_scenarios() -> list[dict[str, Any]]:
        try:
            return scenario_store.list()
        except (GeoJSONError, KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/scenario")
    def save_scenario(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            plan = ScenarioPlan.from_mapping(payload)
            result = scenario_agent.execute_plan(plan).payload
            return scenario_store.save(plan, result)
        except (GeoJSONError, KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/scenario/{scenario_id}/refine")
    def refine_scenario(scenario_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return scenario_refiner.refine(scenario_id, payload)
        except (GeoJSONError, KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/scenario/{scenario_id}")
    def get_scenario(scenario_id: str) -> dict[str, Any]:
        try:
            return scenario_store.get(scenario_id)
        except (GeoJSONError, KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.put("/scenario/{scenario_id}")
    def update_scenario(scenario_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            plan = ScenarioPlan.from_mapping(payload)
            result = scenario_agent.execute_plan(plan).payload
            return scenario_store.save(plan, result, scenario_id=scenario_id)
        except (GeoJSONError, KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.delete("/scenario/{scenario_id}")
    def delete_scenario(scenario_id: str) -> dict[str, Any]:
        try:
            deleted = scenario_store.delete(scenario_id)
            return {"deleted": deleted["id"]}
        except (GeoJSONError, KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/scenario/{scenario_id}/qa")
    def get_scenario_qa(scenario_id: str) -> dict[str, Any]:
        try:
            record = scenario_store.get(scenario_id)
            payload = record["payload"]
            return payload.get("qa") or validate_scenario_payload(payload)
        except (GeoJSONError, KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/scenario/{scenario_id}/geojson")
    def get_scenario_geojson(scenario_id: str) -> dict[str, Any]:
        try:
            record = scenario_store.get(scenario_id)
            return record["payload"]["geojson"]
        except (GeoJSONError, KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/basemaps")
    def list_basemaps() -> dict[str, Any]:
        root = _basemap_dir()
        florida = _florida_pmtiles_path()
        florida_ok = florida.is_file()
        basemaps: dict[str, Any] = {}

        # Self-hosted Protomaps vector flavors (primary when the archive exists).
        for basemap_id, cfg in PROTOMAPS_FLAVORS.items():
            basemaps[basemap_id] = {
                "id": basemap_id,
                "type": "vector",
                "label": cfg["label"],
                "purpose": cfg["purpose"],
                "style_url": f"/basemaps/protomaps/style/{cfg['flavor']}.json",
                "tiles_url": "/basemaps/florida/{z}/{x}/{y}.mvt",
                "sprite": f"{PROTOMAPS_SPRITE_BASE}/{cfg['flavor']}",
                "dark": cfg.get("dark", False),
                "keywords": list(cfg["keywords"]),
                "attribution": "Protomaps © OpenStreetMap",
                "offline_tos": "self-hosted",
                "offline_note": "Self-hosted Protomaps/OpenStreetMap vector tiles (ODbL); no third-party tile TOS limits.",
                "available": florida_ok,
                "local": florida_ok,
            }

        # Online raster providers (fallback / out-of-Florida).
        for basemap_id, cfg in BASEMAP_REGISTRY.items():
            local = (root / basemap_id).is_dir()
            basemaps[basemap_id] = {
                "id": basemap_id,
                "type": "raster",
                "label": cfg["label"],
                "purpose": cfg["purpose"],
                "tiles": list(cfg["tiles"]),
                "tile_size": cfg["tile_size"],
                "min_zoom": cfg["min_zoom"],
                "max_zoom": cfg["max_zoom"],
                "attribution": cfg["attribution"],
                "keywords": list(cfg["keywords"]),
                "dark": cfg.get("dark", False),
                "offline_tos": cfg["offline_tos"],
                "offline_note": cfg["offline_note"],
                "available": True,
                "local": local,
                "local_tiles": f"/basemaps/{basemap_id}/{{z}}/{{x}}/{{y}}.png" if local else None,
            }

        if florida_ok:
            default = DEFAULT_PROTOMAPS
            order = PROTOMAPS_ORDER + BASEMAP_PURPOSE_ORDER
        else:
            default = DEFAULT_BASEMAP
            order = BASEMAP_PURPOSE_ORDER

        return {
            "default": default,
            "order": order,
            "basemap_dir": str(root),
            "pmtiles": {"path": str(florida), "available": florida_ok},
            "basemaps": basemaps,
        }

    @app.get("/basemaps/florida/{z}/{x}/{y}.mvt")
    def florida_tile(z: int, x: int, y: int) -> Any:
        reader = _florida_reader()
        if reader is None:
            raise HTTPException(status_code=404, detail="Florida PMTiles archive is not available.")
        try:
            data = reader.get(z, x, y)
        except Exception:  # pragma: no cover - defensive
            data = None
        if not data:
            return Response(status_code=204)
        headers = {"Cache-Control": "public, max-age=86400"}
        if bytes(data[:2]) == b"\x1f\x8b":
            headers["Content-Encoding"] = "gzip"
        return Response(content=bytes(data), media_type="application/vnd.mapbox-vector-tile", headers=headers)

    @app.get("/basemaps/protomaps/style/{flavor}.json")
    def protomaps_style(flavor: str) -> Any:
        import json as _json

        valid = {cfg["flavor"] for cfg in PROTOMAPS_FLAVORS.values()}
        if flavor not in valid:
            raise HTTPException(status_code=404, detail="Unknown Protomaps flavor.")
        style_path = (STATIC_DIR / "basemaps" / "protomaps" / f"{flavor}.json").resolve()
        if not style_path.is_file():
            raise HTTPException(status_code=404, detail="Flavor style not found.")
        style = _json.loads(style_path.read_text())
        source = dict(style.get("sources", {}).get("protomaps", {}))
        source.pop("url", None)
        source["type"] = "vector"
        source["tiles"] = ["/basemaps/florida/{z}/{x}/{y}.mvt"]
        source["minzoom"] = 0
        source["maxzoom"] = 15
        source["attribution"] = "Protomaps © OpenStreetMap"
        style["sources"]["protomaps"] = source
        style["glyphs"] = PROTOMAPS_GLYPHS
        style["sprite"] = f"{PROTOMAPS_SPRITE_BASE}/{flavor}"
        return style

    @app.get("/basemaps/{basemap}/{z}/{x}/{y}.png")
    def basemap_tile(basemap: str, z: int, x: int, y: int) -> Any:
        if basemap not in BASEMAP_REGISTRY:
            raise HTTPException(status_code=404, detail="Unknown basemap.")
        root = _basemap_dir().resolve()
        tile = (root / basemap / str(z) / str(x) / f"{y}.png").resolve()
        if root not in tile.parents or not tile.is_file():
            raise HTTPException(status_code=404, detail="Basemap tile not found.")
        return FileResponse(tile)

    return app


app = create_app() if FastAPI is not None else None
