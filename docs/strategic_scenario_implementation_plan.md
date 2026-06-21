# Strategic Scenario Implementation Plan

Last updated: 2026-06-19

## Objective

Upgrade MILMAP from a one-shot scenario executor into a staged strategic
scenario builder for complex civil-emergency and SHTF planning workflows.

The user experience can still start from one request, but internally the system
should build, validate, render, and revise scenarios layer by layer.

## Current Method

The current system accepts a `ScenarioPlan` containing `objects` and `layers`.
The backend compiles each scenario layer into a deterministic `SpatialPlan`,
executes it, applies styles, combines the result into GeoJSON, saves the
scenario, and renders it in the web workspace.

Current flow:

```text
ScenarioPlan
  -> compile each layer
  -> execute each SpatialPlan
  -> style objects and layers
  -> combine GeoJSON
  -> save JSON scenario record
  -> render in MapLibre
```

This already prevents the LLM from inventing coordinate loops. The model or
caller describes intent; the engine computes geometry or retrieves real-world
data.

## Target Method

Strategic scenarios should be built in explicit phases:

```text
User request
  -> ScenarioBrief
  -> LayerBuildPlan
  -> Phase 1: real-world context
  -> Phase 2: critical infrastructure
  -> Phase 3: risk and disruption overlays
  -> Phase 4: response network
  -> Phase 5: movement and logistics
  -> Phase 6: coverage, gaps, and QA
  -> final rendered scenario
```

Each phase should produce a versioned layer group with source metadata,
confidence, warnings, and validation results.

## Core Design Rules

- Never ask the LLM to invent coordinate loops.
- Treat real-world data and simulated overlays as different layer classes.
- Build strategic scenarios layer by layer, even when the user makes one broad
  request.
- Preserve enough metadata to explain where every layer came from.
- Allow one layer group to be regenerated without rebuilding the whole
  scenario.
- Keep map rendering independent from the selected basemap style.

## Phase Model

### Phase 1: Base Context

Purpose: establish the operating geography.

Layer types:

- Administrative boundary.
- Map center and extent.
- Named districts or neighborhoods.
- Major landmarks.
- Optional terrain or water context.

Implementation:

- Add `ScenarioBrief` model with location, purpose, assumptions, and requested
  scope.
- Add `LayerBuildPlan` model with ordered phase definitions.
- Add `phase`, `source`, `confidence`, and `warnings` metadata to scenario
  layers.
- Keep Orlando OSM boundary demo as the first regression fixture.

### Phase 2: Critical Infrastructure

Purpose: map strategic assets and dependencies.

Layer types:

- Hospitals and urgent care.
- Shelters and public facilities.
- Airports, rail, ports, and logistics hubs.
- Major highways and evacuation routes.
- Water, fuel, power, and communications assets where data is available.

Implementation:

- Add Overpass query templates for common infrastructure classes.
- Add geocoder interface for named places.
- Add typed real-world tool outputs with source attribution.
- Add `infrastructure_category` and `operational_role` properties.

### Phase 3: Risk And Disruption

Purpose: model where normal operations are degraded.

Layer types:

- Flood pockets.
- Power outage zones.
- Road closure zones.
- Low mobility areas.
- Communications degradation zones.
- Public safety exclusion or caution zones.

Implementation:

- Support deterministic simulated risk zones with explicit assumptions.
- Add import hooks for external GeoJSON risk datasets.
- Add future adapters for FEMA, NWS, local GIS, traffic feeds, and utility data.
- Add `simulation_assumption` metadata for generated disruption layers.

### Phase 4: Response Network

Purpose: place response assets and civilian support nodes.

Object types:

- Emergency operations center.
- Medical triage point.
- Shelter.
- Supply distribution point.
- Staging area.
- Communications relay.
- Checkpoint or traffic control point.

Implementation:

- Expand default styles for civilian emergency object types.
- Add object grouping by function.
- Add object status values: `planned`, `active`, `degraded`, `closed`.
- Add object inspector fields for capacity, resource type, and contact/source
  metadata.

### Phase 5: Movement And Logistics

Purpose: model how people, supplies, and responders move.

Layer types:

- Evacuation corridor.
- Supply corridor.
- Medical transfer corridor.
- Alternate route.
- Chokepoint.
- Access-control area.

Implementation:

- Replace hand-defined corridors with routing-tool-backed corridors when
  routing data is available.
- Add corridor width, priority, status, and purpose.
- Add dependency links from corridors to endpoints.
- Add route validation: endpoint exists, minimum two waypoints, width positive,
  and route geometry inside scenario extent where appropriate.

### Phase 6: Coverage, Gaps, And QA

Purpose: evaluate whether the scenario is useful and internally coherent.

Layer types:

- Service areas.
- Range rings.
- Search grids.
- Gap polygons.
- Layer confidence overlay.

Implementation:

- Add scenario QA report.
- Add checks for empty real-world layers.
- Add checks for out-of-bounds objects.
- Add checks for duplicated names and missing styles.
- Add checks for overloaded maps with excessive feature counts.
- Add summary statistics by layer group.

## Data Model Changes

Add these models in `src/milmap_engine/models.py` or a dedicated scenario
planning module.

### ScenarioBrief

Fields:

- `scenario_name`
- `location_name`
- `mode`
- `purpose`
- `center`
- `bounds`
- `time_horizon`
- `assumptions`
- `requested_outputs`

### LayerBuildPlan

Fields:

- `scenario_name`
- `phases`
- `dependencies`
- `validation_rules`

### LayerPhase

Fields:

- `id`
- `name`
- `order`
- `objective`
- `layers`
- `objects`
- `required`

### Layer Metadata

Add standard metadata keys:

- `phase_id`
- `phase_name`
- `source_type`
- `source_name`
- `source_url`
- `retrieved_at`
- `confidence`
- `warnings`
- `assumptions`
- `dependencies`

## Backend Implementation Plan

### 1. Scenario Build Service

Create `src/milmap_engine/builder.py`.

Responsibilities:

- Accept `ScenarioBrief` or full `LayerBuildPlan`.
- Build scenario phases in order.
- Execute each phase with `ScenarioAgent`.
- Save intermediate versions.
- Return final scenario payload plus QA report.

Proposed API:

```python
builder = ScenarioBuilder(agent=scenario_agent, store=scenario_store)
result = builder.build(brief_or_plan)
```

### 2. Layer Group Execution

Add support for executing only a subset of scenario layers.

Needed methods:

- `ScenarioAgent.execute_layers(...)`
- `ScenarioAgent.execute_objects(...)`
- `ScenarioStore.save_phase(...)`
- `ScenarioStore.get_versions(...)`

### 3. Validation And QA

Create `src/milmap_engine/validation.py`.

Initial checks:

- Required fields present.
- Coordinates valid.
- Layer output is non-empty.
- Feature count below threshold.
- Objects fall inside scenario bounds when bounds exist.
- Real-world layer has source metadata.
- Generated layer has assumptions metadata.

### 4. OSM Relation Assembly

Current limitation: complex OSM administrative relations render as
`MultiLineString` member linework.

Improve `overpass_json_to_geojson`:

- Detect relation members with `role=outer` and `role=inner`.
- Stitch connected ways into closed rings.
- Emit `Polygon` or `MultiPolygon` when possible.
- Preserve fallback `MultiLineString` when rings cannot be assembled.
- Add tests using a compact fixture before running broad live Overpass tests.

### 5. Real-World Tool Templates

Create `src/milmap_engine/overpass_templates.py`.

Templates:

- Administrative boundary by Wikidata ID.
- Hospitals and clinics.
- Shelters and public buildings.
- Airports and helipads.
- Major roads.
- Water bodies.
- Fuel stations.
- Police, fire, and EMS stations.

Each template should return:

- Query string.
- Expected geometry types.
- Source description.
- Recommended style type.

### 6. Map Style Modes

Add style modes to the frontend.

Initial modes:

- `Light Operations`
- `Dark Operations`
- `Satellite Hybrid`
- `OSM Detail`
- `Minimal Tactical`

Implementation:

- Add basemap selector in the map toolbar.
- Keep overlay sources/layers stable when switching basemaps.
- Store selected basemap in scenario UI state, not in GeoJSON.
- Add style config in `static/app.js` or a separate `static/map-styles.js`.

### 7. Layer Dependency Metadata

Add optional dependency declarations:

```json
{
  "id": "airport_logistics_corridor",
  "depends_on": ["downtown_eoc", "airport_air_bridge"]
}
```

Use dependencies for:

- Regenerating affected layers.
- QA warnings.
- Explaining why a layer exists.

### 8. Scenario Version Diffs

Current store tracks versions, but does not expose useful diffs.

Add:

- `GET /scenario/{scenario_id}/versions`
- `GET /scenario/{scenario_id}/versions/{version}`
- `GET /scenario/{scenario_id}/diff?from=1&to=2`

Diff should include:

- Added/removed layers.
- Added/removed objects.
- Changed properties.
- Changed feature counts.

## Frontend Implementation Plan

### 1. Build Phase Panel

Add a phase-oriented panel above or beside the layer list.

Panel should show:

- Phase name.
- Completion status.
- Layer count.
- Warning count.
- Rebuild button.

### 2. Basemap Selector

Add a compact control to the map viewport.

Requirements:

- Use an icon button or segmented menu.
- Preserve current overlays.
- Avoid covering the legend or attribution.

### 3. QA Report View

Add an inspector tab for QA.

Contents:

- Scenario summary.
- Layer warnings.
- Empty layers.
- Source age.
- Confidence by layer.
- Feature counts.

### 4. Layer Filtering

Add filters:

- By phase.
- By source type.
- By object/layer role.
- By status.

### 5. Legend Improvements

Current legend lists every layer and object. For dense scenarios, add:

- Collapse by phase.
- Hide object labels below a zoom threshold.
- Show warning indicators for low-confidence layers.

## API Implementation Plan

Add endpoints:

- `POST /scenario/build`
- `POST /scenario/build/phase`
- `GET /scenario/{scenario_id}/qa`
- `GET /scenario/{scenario_id}/versions`
- `GET /scenario/{scenario_id}/diff`
- `GET /map/styles`

Keep existing endpoints stable.

## Testing Plan

### Unit Tests

- OSM relation stitching.
- Layer phase compilation.
- QA validation checks.
- Style mode config.
- Scenario version diffing.

### Integration Tests

- Build Orlando real-world scenario from a staged plan.
- Rebuild only the movement/logistics phase.
- Save and reload a multi-phase scenario.
- Export final combined GeoJSON.

### Browser Tests

- Load staged scenario.
- Switch basemap styles.
- Toggle phase visibility.
- Verify legend updates.
- Verify QA warnings appear.

## Implementation Milestones

### Milestone 1: Staged Scenario Core

- Add `ScenarioBrief`, `LayerBuildPlan`, and `LayerPhase`.
- Add `ScenarioBuilder`.
- Add phase metadata to layer outputs.
- Add unit tests.

### Milestone 2: QA And Validation

- Add validation module.
- Add QA report payload.
- Add `/scenario/{id}/qa`.
- Show QA in frontend inspector.

### Milestone 3: Better Real-World Geometry

- Add OSM relation assembly.
- Add fixtures and tests.
- Update Orlando boundary demo to render filled polygons when possible.

### Milestone 4: Strategic Frontend Controls

- Add basemap selector.
- Add phase panel.
- Add layer filtering.
- Improve legend for dense scenarios.

### Milestone 5: Strategic Data Connectors

- Add Overpass templates.
- Add geocoder interface.
- Add routing interface.
- Add external GeoJSON import metadata.

## Recommended Next Task

Start with Milestone 1 and Milestone 2:

1. Add staged scenario models.
2. Add `ScenarioBuilder`.
3. Add phase metadata.
4. Add QA checks for empty layers, source metadata, and feature counts.
5. Expose `/scenario/build` and `/scenario/{id}/qa`.

This gives the system the right architecture before adding more data sources or
more complex frontend controls.
