# MILMAP Engine

MILMAP Engine is a deterministic spatial-agent core for creating GeoJSON lines, boundaries, grids, buffers, sectors, and simulated map overlays.

The important design rule is simple: the LLM never guesses coordinate loops. It routes intent into structured plans, and the engine computes or retrieves the geometry.

## Architecture

```text
Natural language or structured request
  -> LLM / heuristic intent router
  -> SpatialPlan JSON
  -> deterministic geometry or registered map-data tool
  -> GeoJSON validation and normalization
  -> map frontend
```

See [Full Agent Build Plan](docs/full_agent_build_plan.md) for the complete roadmap for turning this engine into a full map setup agent.
See [Strategic Scenario Implementation Plan](docs/strategic_scenario_implementation_plan.md) for the staged layer-by-layer upgrade path.
See [Visual Briefings](docs/visual_briefings.md) for the ChatGPT/OpenAI Images
handoff that turns saved scenarios and map screenshots into simulated briefing
graphics.
See [State Of The Art Roadmap](docs/state_of_art_roadmap.md) for the
implemented 1-6 capability focus and deferred 7-10 opportunity notes.

## Pipelines

- `abstract`: deterministic generated geometry, including buffers, sectors, corridors, regular polygons, square grids, and hex grids.
- `direct`: caller-provided coordinates that are normalized, closed, rounded, and validated.
- `real_world`: tool-backed retrieval for public map features such as boundaries or roads. The engine provides the tool interface; production deployments can register Overpass, geocoding, routing, or private GIS adapters.

## Quick Use

```bash
PYTHONPATH=src python3 -m milmap_engine.cli examples/abstract_buffer.json
```

```python
from milmap_engine import SpatialAgent

agent = SpatialAgent()
geojson = agent.execute({
    "pipeline": "abstract",
    "operation": "buffer",
    "parameters": {
        "center": [-82.324, 27.845],
        "radius_miles": 5,
        "steps": 64
    }
})
```

Batch overlays are supported by passing a JSON array of plans:

```bash
PYTHONPATH=src python3 -m milmap_engine.cli examples/scenario_overlay.json
```

Scenario plans sit one level above raw geometry. They compile semantic objects
and layers into executable `SpatialPlan` jobs, then return a styled scenario
payload plus a combined GeoJSON feature collection:

```bash
PYTHONPATH=src python3 -m milmap_engine.cli examples/scenario_plan.json
```

Staged scenario builds sit above `ScenarioPlan`. A caller submits a
`ScenarioBrief` or ordered `LayerBuildPlan`; the builder executes phases in
order, attaches phase/source metadata to layers and objects, saves phase
snapshots when a store is configured, and returns a QA report with the final
scenario payload. QA reports include a 0-100 score, grade, readiness label, and
deduction reasons for briefing and review workflows.

The Orlando real-world demo uses OpenStreetMap data through Overpass for the
Orlando, Florida administrative boundary:

```bash
curl -X POST http://127.0.0.1:8004/scenario \
  -H 'Content-Type: application/json' \
  --data-binary @examples/orlando_real_world_demo.json
```

## API Server

Install optional API dependencies, then run:

```bash
pip install -e ".[api]"
uvicorn milmap_engine.server:app --reload
```

Open `http://127.0.0.1:8000/` for the built-in scenario map workspace.

POST a plan to `/agent/execute`.
POST a list of plans to `/agent/execute_many`.
POST a scenario plan to `/scenario/execute`.
POST a scenario plan to `/scenario` to execute and save it.
POST a staged build plan or brief to `/scenario/build`.
GET saved scenarios from `/scenario`.
GET a saved record from `/scenario/{scenario_id}`.
GET saved GeoJSON from `/scenario/{scenario_id}/geojson`.
GET a saved QA report from `/scenario/{scenario_id}/qa`.
GET a text/structured legend from `/scenario/{scenario_id}/legend`.
POST a visual briefing handoff package to `/scenario/{scenario_id}/visual_briefing`.
GET the basemap registry from `/basemaps`.
GET a self-hosted Florida vector tile from `/basemaps/florida/{z}/{x}/{y}.mvt`.
GET a Protomaps flavor style from `/basemaps/protomaps/style/{flavor}.json`.

Saved scenarios use a local JSON store at `.milmap/scenarios.json` by default.
Set `MILMAP_STORE_PATH` to override the store location.

## Basemaps

MILMAP's primary basemap is a **self-hosted Protomaps vector basemap** built from
OpenStreetMap data for Florida (`.milmap/florida.pmtiles`), served by the app
itself — no third-party tile TOS limits, works offline. It is styled with three
purpose-mapped flavors: `protomaps_light` (urban), `protomaps_dark`
(night/low-light), `protomaps_grayscale` (terrain/neutral). Online raster
providers (`osm`, `cartodb_dark`, `opentopomap`, `esri_street`, `esri_topo`)
remain wired as a fallback.

The map picks a basemap automatically from each scenario's purpose (no manual
switcher): an explicit `map_context.basemap` id, else keywords in
`purpose`/`mode`. A `?basemap=<id>` URL override exists for previews. See
[Basemaps](docs/basemaps.md) for the purpose mapping, how to build the Florida
archive, and the per-provider TOS table.

## Screenshots and Telegram Notifications

Render the running workspace headlessly (deep-linking a saved scenario) and send
the PNG to the project's dedicated Telegram bot:

```bash
.venv/bin/python -m milmap_engine.notify \
  --scenario orlando_metro_shtf \
  --caption "MILMAP - Orlando metro SHTF build, QA pass"
```

The frontend understands a `?scenario=<id>` deep link and exposes a
`window.__milmap.ready` flag so the headless capture waits for the map to finish
rendering. The bot token and chat are hardcoded for this project and can be
overridden with `MILMAP_TG_BOT_TOKEN` / `MILMAP_TG_CHAT_ID`. See
[Screenshots and Telegram Notifications](docs/notifications.md) for full details,
including the token-rotation note.

A more complex civil-emergency stress test ships in
`examples/orlando_metro_shtf_buildplan.json` — a six-phase Orlando-metro
hurricane plus grid-down build (16 layers, 19 objects) used to exercise staged
builds and QA accuracy:

```bash
curl -X POST http://127.0.0.1:8004/scenario/build \
  -H 'Content-Type: application/json' \
  --data-binary @examples/orlando_metro_shtf_buildplan.json
```

## Supported Operations

- Direct geometry: `point`, `line`, `polygon`, `bbox`
- Radial geometry: `buffer`, `range_ring`, `sector`, `regular_polygon`
- Route geometry: `corridor`
- Grids: `square_grid`, `hex_grid`
- Tool-backed geography: `real_world_boundary`, `overpass_query`

Grid operations support `max_features` to cap payload size.

Tool-backed operations require an explicit registry:

```python
from milmap_engine import SpatialAgent, overpass_tool_registry

agent = SpatialAgent(tools=overpass_tool_registry())
```

The FastAPI app registers the Overpass tool registry by default for local demos.

## Scenario Plans

`ScenarioPlan` JSON supports:

- `objects`: semantic map objects such as bases, checkpoints, labels, and objectives.
- `layers`: generated geometry layers with styles, visibility, and layer metadata.
- `map_context`: frontend hints such as center, zoom, and mode.

When a layer type is semantic, such as `perimeter` or `route`, include the
deterministic engine `operation` to run:

```json
{
  "type": "perimeter",
  "operation": "buffer",
  "parameters": {
    "center": [-82.324, 27.845],
    "radius_km": 5
  }
}
```

See `schemas/scenario_plan.schema.json` for the planner contract.

Staged build plans use:

- `ScenarioBrief`: scenario name, location, mode, purpose, center/bounds,
  assumptions, and requested outputs.
- `LayerBuildPlan`: ordered phases, dependencies, validation rules, map
  context, and optional brief.
- `LayerPhase`: phase id/name/order/objective plus the layers and objects to
  build in that phase.

The builder adds standard metadata such as `phase_id`, `phase_name`,
`source_type`, `source_name`, `confidence`, `warnings`, `assumptions`, and
`dependencies` without asking the LLM to invent coordinate loops.

QA reports check empty layers, source metadata for real-world layers,
assumptions for generated layers, feature counts, duplicate names, missing
styles, coordinate validity, and objects outside scenario bounds.

The built-in web workspace supports:

- Interactive MapLibre rendering.
- Scenario JSON execution and save/load.
- Dynamic map legend.
- Layer and object lists.
- Visibility toggles.
- Layer opacity controls.
- Object and feature inspection.
- QA status, summary metrics, and top validation issues.
- GeoJSON import/export.

## Coordinate Rules

- GeoJSON coordinates are always `[longitude, latitude]`.
- Polygon rings are always closed by the engine.
- Coordinates are rounded to 6 decimal places by default.
- Invalid longitude/latitude values are rejected.

## Map Integration

The engine returns map-ready GeoJSON. In MapLibre:

```js
map.addSource("milmap-overlay", {
  type: "geojson",
  data: geojson
});
```

In Leaflet:

```js
L.geoJSON(geojson).addTo(map);
```
