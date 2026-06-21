# Current State

Last updated: 2026-06-19

## Working System

MILMAP currently has a deterministic Python geometry engine, a scenario compiler,
a JSON-backed scenario store, and a built-in MapLibre web workspace.

The core rule remains unchanged: the LLM or caller plans the map, but the engine
computes geometry. Coordinate loops are not guessed by the model.

The backend now also supports staged scenario builds. A caller can submit a
`ScenarioBrief` or ordered `LayerBuildPlan`; the builder attaches phase/source
metadata, executes deterministic scenario phases, saves phase snapshots, and
returns a QA report with the final scenario payload.

## Backend

- `SpatialAgent` executes low-level `SpatialPlan` jobs.
- `ScenarioAgent` executes higher-level `ScenarioPlan` payloads.
- `ScenarioCompiler` converts semantic scenario layers into deterministic
  `SpatialPlan` jobs.
- `StyleEngine` assigns default styles for bases, checkpoints, perimeters,
  corridors, grids, sectors, boundaries, and other map objects.
- `ScenarioStore` persists executed scenarios in `.milmap/scenarios.json` by
  default.
- The FastAPI app registers the Overpass-backed tool registry by default for
  `real_world_boundary` and `overpass_query`.
- `ScenarioBuilder` builds staged scenario phases into a normal executable
  `ScenarioPlan`; opt-in `metadata.map_context_role` entries are resolved into
  scored map-context coordinates before geometry compilation.
- `MapContextBuilder` builds semantic map context from OSM/GeoJSON features;
  `MapContext` classifies features into roles and scores placement candidates
  with evidence and rejected alternatives.
- `validate_scenario_payload` produces QA reports for saved or newly built
  scenarios, including opt-in semantic placement checks for rationale,
  evidence, candidate score, and rejected alternatives.

## API

The FastAPI app exposes:

- `GET /health`
- `POST /agent/execute`
- `POST /agent/execute_many`
- `POST /scenario/execute`
- `GET /scenario`
- `POST /scenario`
- `POST /scenario/build`
- `GET /scenario/{scenario_id}`
- `PUT /scenario/{scenario_id}`
- `DELETE /scenario/{scenario_id}`
- `GET /scenario/{scenario_id}/geojson`
- `GET /scenario/{scenario_id}/qa`
- `GET /basemaps`
- `GET /basemaps/florida/{z}/{x}/{y}.mvt`
- `GET /basemaps/protomaps/style/{flavor}.json`
- `GET /basemaps/{basemap}/{z}/{x}/{y}.png`

## Web Workspace

The built-in web UI is served from `/`.

Current capabilities:

- Execute scenario JSON.
- Save and reload scenarios.
- Render layers and objects on a MapLibre map.
- Show a map legend derived from active layer and object styles.
- Toggle layer and object visibility.
- Adjust layer opacity.
- Inspect rendered scenario metadata.
- Show QA status, summary metrics, and top validation issues in the inspector.
- Import GeoJSON.
- Export combined scenario GeoJSON.
- Deep-link a saved scenario for headless capture via `?scenario=<id>`.
- Build staged scenarios with phase metadata on layers, objects, and GeoJSON
  feature properties.
- Resolve map-aware layer/object placements from cached GeoJSON or Overpass
  context, including candidate evidence, scores, constraints, and rejected
  alternatives.
- Run QA checks for empty layers, source metadata, generated-layer assumptions,
  feature counts, duplicate names, missing styles, coordinate validity, and
  out-of-bounds objects. Route-quality and map-aware placement-reasoning checks
  are opt-in via `validation_rules`.

The demo store currently includes:

- `training_setup`: 4 layers, 2 objects, 152 GeoJSON features.
- `orlando_real_world_demo`: 4 layers, 2 objects, 6 GeoJSON features.
- `orlando_shtf_civil_emergency`: 12 layers, 12 objects, 79 GeoJSON
  features.
- `orlando_metro_shtf`: 16 layers, 19 objects, 97 GeoJSON features. A
  six-phase civil-emergency stress test (hurricane landfall plus grid-down)
  built from `examples/orlando_metro_shtf_buildplan.json` via `/scenario/build`;
  QA status is `pass` with zero warnings and zero errors.
- `orlando_shtf_evacuation_route`: road-routed Orlando evacuation scenario with
  evidence-backed support elements and placement rationale metadata.
- `fictional_civil_conflict_base_vs_base` and
  `orlando_fictional_civil_conflict_base_vs_base`: fictional, non-operational
  tabletop overlays for deconfliction, humanitarian evacuation, supply
  resilience, and communications coverage.

## Basemaps

The primary basemap is a self-hosted Protomaps vector basemap built from
OpenStreetMap data for Florida (`.milmap/florida.pmtiles`, ~1.1 GB, MVT z0–15).
The MILMAP app serves the tiles directly via the `pmtiles` reader at
`GET /basemaps/florida/{z}/{x}/{y}.mvt` (gzip MVT, same origin), styled with
vendored Protomaps flavors (`protomaps_light`, `protomaps_dark`,
`protomaps_grayscale`) returned by `GET /basemaps/protomaps/style/{flavor}.json`
with the vector source rewritten to the local tile route. Glyphs and sprites load
from `protomaps.github.io` (the only remaining network dependency; mirror locally
for full air-gap).

The workspace auto-selects a basemap per scenario purpose (no manual switcher):
an explicit `map_context.basemap` id, else keywords in `purpose`/`mode`. When the
archive is present the default is `protomaps_light` and Protomaps flavors lead
the selection order; the online raster providers (`osm`, `cartodb_dark`,
`opentopomap`, `esri_street`, `esri_topo`) remain as fallback. A `?basemap=<id>`
URL override exists for previews. `MILMAP_PMTILES` overrides the archive path;
`pmtiles` is required (in the `[api]` extra) to serve tiles. See
[Basemaps](basemaps.md).

## Screenshots and Notifications

`src/milmap_engine/notify.py` renders the running workspace headlessly and
delivers the PNG to a dedicated Telegram bot (`@milmapbot`). The frontend
understands a `?scenario=<id>` deep link and exposes a `window.__milmap.ready`
flag so the capture waits for the MapLibre render to settle. Screenshots prefer
Playwright Chromium with software WebGL, falling back to `chrome-headless-shell`.
The bot token and chat are hardcoded for this project and overridable via
`MILMAP_TG_BOT_TOKEN` / `MILMAP_TG_CHAT_ID`. See
[Screenshots and Telegram Notifications](notifications.md).

## Local Run

The current demo server is running at:

```text
http://127.0.0.1:8004/
```

Ports `8000` through `8003` were occupied on the host during the last run, so
the demo used port `8004`.

To run from a fresh checkout:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[api]"
.venv/bin/uvicorn milmap_engine.server:app --host 127.0.0.1 --port 8004
```

## Verification

Current passing check:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -q
```

Latest local result: 46 tests passed, with 1 optional FastAPI test-client test
skipped because the local Starlette test client requires the extra `httpx2`
package. The added tests build `examples/orlando_metro_shtf_buildplan.json`
offline (stubbing the Overpass call) and assert a clean QA pass, in-order phase
execution, and attached dependency metadata, plus structural checks on the raster
basemap registry and the Protomaps flavor registry (expected flavors, vendored
style files, source-rewrite target, and `MILMAP_PMTILES` override). Map-context
tests cover semantic role classification, candidate selection metadata,
builder-level placement resolution, Overpass bbox query generation, and strict
placement-reasoning QA.

The browser demo has also been exercised with Playwright and Chromium.

## Known Gaps

- Scenario persistence is file-backed, not PostGIS-backed.
- The UI has no draw/edit geometry mode yet.
- Follow-up natural-language refinement is not wired into the frontend.
- The frontend does not yet show phase-oriented controls.
- OSM administrative relations are currently preserved as member linework; the
  engine does not yet assemble complex boundary relations into filled polygons.
- Map context classification is rule-based and should be backed by cached local
  feature indexes or PostGIS for production-scale use.
- There is no authentication or multi-user separation.
