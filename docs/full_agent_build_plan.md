# Full Agent Build Plan

## Objective

Build an LLM-powered map setup agent that can take a user request and produce a complete interactive map scenario with generated shapes, boundaries, lines, bases, zones, routes, labels, styles, and editable layers.

The LLM should act as the planner and translator. The geometry engine should generate every coordinate deterministically.

## Core Principle

Do not ask the LLM to invent coordinate loops.

The agent should compile natural language into structured plans, then use deterministic tools to create valid GeoJSON.

```text
User request
  -> LLM scenario planner
  -> structured ScenarioPlan
  -> SpatialPlan jobs
  -> deterministic geometry and map-data tools
  -> GeoJSON validation
  -> styled scenario objects
  -> frontend map renderer
```

## Recommended Stack

Backend:

- Python
- FastAPI
- MILMAP Engine
- PostgreSQL + PostGIS
- Redis and Celery/RQ for large jobs later
- Overpass API for OpenStreetMap-backed public map data

Frontend:

- React or Next.js
- MapLibre GL JS
- Turf.js for client-side measuring and editing
- Zustand or Redux for scenario state

Storage:

- Scenario records
- Scenario object records
- GeoJSON layer payloads
- Style definitions
- Agent run logs
- Scenario versions

## System Architecture

```text
Natural language request
  |
  v
LLM Scenario Planner
  |
  v
ScenarioPlan JSON
  |
  +--> Abstract geometry pipeline
  |      buffers, rings, grids, sectors, corridors, polygons
  |
  +--> Real-world map data pipeline
  |      boundaries, roads, rivers, routes, terrain references
  |
  +--> Scenario object builder
  |      bases, outposts, control areas, labels, markers
  |
  +--> Style engine
  |      colors, icons, layer order, opacity
  |
  v
GeoJSON normalizer and validator
  |
  v
Scenario store
  |
  v
Map frontend
```

## Agent Responsibilities

The agent should be able to:

- Interpret natural-language map setup requests.
- Ask for missing spatial anchors when needed.
- Create structured scenario plans.
- Generate buffers, sectors, range rings, grids, corridors, lines, points, and polygons.
- Retrieve named public map features through registered tools.
- Build simulated bases, outposts, zones, routes, and labels.
- Style generated layers automatically.
- Save and reload complete map setups.
- Refine existing setups through follow-up instructions.
- Export map layers as GeoJSON.

## ScenarioPlan Model

The LLM should produce a high-level scenario plan before geometry execution.

```json
{
  "scenario_name": "training_setup",
  "map_context": {
    "mode": "simulation",
    "center": [-82.324, 27.845],
    "zoom": 11
  },
  "objects": [
    {
      "type": "base",
      "name": "Base Alpha",
      "placement": {
        "mode": "point",
        "coordinate": [-82.324, 27.845]
      }
    }
  ],
  "layers": [
    {
      "type": "buffer",
      "name": "Base Alpha Perimeter",
      "parameters": {
        "center": [-82.324, 27.845],
        "radius_km": 5
      }
    }
  ]
}
```

## SpatialPlan Compilation

The scenario planner should compile scenario layers into executable `SpatialPlan` jobs.

```json
{
  "pipeline": "abstract",
  "operation": "buffer",
  "parameters": {
    "center": [-82.324, 27.845],
    "radius_km": 5,
    "steps": 64
  },
  "properties": {
    "name": "Base Alpha Perimeter",
    "layer_type": "zone"
  }
}
```

The current engine already supports these operations:

- `point`
- `line`
- `polygon`
- `bbox`
- `buffer`
- `range_ring`
- `sector`
- `regular_polygon`
- `corridor`
- `square_grid`
- `hex_grid`
- `real_world_boundary`
- `overpass_query`

## Scenario Objects

Scenario objects sit above raw geometry and provide semantic meaning.

Supported object types should include:

- `base`
- `outpost`
- `checkpoint`
- `route`
- `corridor`
- `search_area`
- `perimeter`
- `observation_zone`
- `restricted_zone`
- `supply_node`
- `objective_marker`
- `label`
- `annotation`
- `grid_cell`
- `region_boundary`

Example:

```json
{
  "id": "base_alpha",
  "type": "base",
  "name": "Base Alpha",
  "geometry": {
    "type": "Point",
    "coordinates": [-82.324, 27.845]
  },
  "properties": {
    "role": "logistics",
    "status": "active",
    "icon": "warehouse",
    "color": "#2563eb"
  }
}
```

## Style Engine

The style engine should assign default styles by object and layer type.

Suggested defaults:

- Bases: icon markers with labels.
- Outposts: smaller icon markers.
- Buffers: translucent fills with solid outlines.
- Corridors: semi-transparent polygon fills.
- Routes: solid line layers.
- Search grids: thin outlined cells.
- Boundaries: high-contrast outlines.
- Restricted zones: red/orange translucent fills.
- Objectives: flag or target-style markers.

Example style:

```json
{
  "layer_id": "perimeter_alpha",
  "style": {
    "fill_color": "#2563eb",
    "fill_opacity": 0.18,
    "stroke_color": "#1d4ed8",
    "stroke_width": 2,
    "line_dasharray": [4, 2]
  }
}
```

## Frontend Requirements

The frontend should provide:

- Interactive MapLibre map.
- Layer panel.
- Object list.
- Object inspector.
- Toggle visibility.
- Opacity controls.
- Draw/edit mode.
- Move, resize, duplicate, and delete tools.
- GeoJSON import/export.
- Scenario save/load.
- Follow-up command input.

MapLibre source example:

```js
map.addSource("scenario", {
  type: "geojson",
  data: scenarioGeojson
});
```

MapLibre style example:

```js
map.addLayer({
  id: "scenario-fill",
  type: "fill",
  source: "scenario",
  paint: {
    "fill-color": ["get", "fill_color"],
    "fill-opacity": ["coalesce", ["get", "fill_opacity"], 0.2]
  }
});
```

## Backend API

Recommended API endpoints:

```text
POST /agent/build
POST /agent/refine
POST /agent/execute
POST /agent/execute_many
GET  /scenarios/{id}
POST /scenarios
PUT  /scenarios/{id}
POST /scenarios/{id}/export
```

Example `/agent/build` request:

```json
{
  "request": "Create a setup with one main base, three outposts, a 5 km perimeter, and a hex search grid.",
  "context": {
    "center": [-82.324, 27.845],
    "mode": "simulation"
  }
}
```

## Database Model

Recommended tables:

```text
scenarios
scenario_objects
scenario_layers
scenario_versions
map_assets
agent_runs
```

Recommended spatial columns:

```text
geometry geometry(Geometry, 4326)
bbox geometry(Polygon, 4326)
```

## Refinement Workflow

The agent should support follow-up commands against the current scenario.

Examples:

```text
Move Base Alpha 2 km north.
Add a 3 km buffer around Outpost Bravo.
Split the search area into 500 meter hex cells.
Make the route corridor wider.
Hide all grid labels.
Export this setup as GeoJSON.
```

Refinement flow:

```text
Existing scenario
  -> user follow-up
  -> LLM identifies target objects
  -> patch ScenarioPlan
  -> re-run affected SpatialPlan jobs
  -> update layers and styles
  -> save new scenario version
```

## Validation Rules

Every output must pass validation before rendering:

- GeoJSON type is valid.
- Coordinates are `[longitude, latitude]`.
- Longitude is between `-180` and `180`.
- Latitude is between `-90` and `90`.
- Polygon rings are closed.
- Precision is trimmed.
- Grid feature count is capped.
- Empty geometries are rejected.
- Tool output is normalized before storage.

## LLM Contract

The LLM should be prompted as a planner:

```text
You are a map setup planner.
Return only structured JSON.
Do not invent coordinate loops.
Use [longitude, latitude] order.
Convert user requests into scenario objects and geometry jobs.
If a required coordinate, boundary, radius, width, or named place is missing, ask for the missing field.
```

The LLM should output:

- scenario intent
- required objects
- required layers
- geometry parameters
- style hints
- missing-field questions when needed

The LLM should not output:

- hand-written circle coordinates
- guessed city boundaries
- guessed road paths
- invalid GeoJSON

## Implementation Phases

### Phase 1: Core Engine

Status: done.

- Deterministic GeoJSON engine.
- Batch execution.
- GeoJSON normalization.
- Polygon closure.
- Precision trimming.
- Buffers, sectors, corridors, square grids, and hex grids.

### Phase 2: Scenario Planner

- Add `ScenarioPlan` model.
- Add scenario object schema.
- Add scenario layer schema.
- Compile scenario plans into `SpatialPlan` jobs.
- Generate object IDs and metadata.
- Add scenario-level validation.

### Phase 3: LLM Integration

- Add structured-output API call.
- Add schema validation.
- Add retry/repair for malformed model output.
- Add missing-field clarification flow.
- Add prompt templates for build and refine workflows.

### Phase 4: Frontend Map

- Build MapLibre interface.
- Add layer panel.
- Add object inspector.
- Add drawing/editing tools.
- Add command input for follow-up instructions.
- Add GeoJSON import/export.

### Phase 5: Real-World Data Tools

- Register Overpass adapter.
- Add geocoder adapter.
- Add routing adapter.
- Add boundary retrieval.
- Add road and river retrieval.
- Normalize all returned data into GeoJSON.

### Phase 6: Persistence

- Add PostgreSQL/PostGIS.
- Save scenarios.
- Save generated objects and layers.
- Add version history.
- Add agent run logs.
- Add export endpoint.

### Phase 7: Advanced Generation

- Scenario templates.
- Placement constraints.
- Synthetic terrain modes.
- Automatic label placement.
- Layer grouping.
- Timeline playback.
- Scenario comparison.
- Reusable setup presets.

## Final Target

The finished system should behave like a map setup compiler:

```text
Natural language
  -> ScenarioPlan
  -> SpatialPlan jobs
  -> GeoJSON layers
  -> styled scenario objects
  -> interactive editable map
```

The LLM decides what should be built. The engine determines the actual geometry.

