# Spatial Agent Architecture

## Goal

Create map-ready GeoJSON without asking an LLM to invent coordinates.

## Components

1. Intent router
   - Accepts natural language or structured JSON.
   - Emits a `SpatialPlan`.
   - Can be backed by an LLM, a rules engine, or direct API callers.

2. Geometry engine
   - Generates abstract shapes deterministically.
   - Uses geodesic destination math for radial shapes.
   - Uses a local tangent-plane projection for grid and corridor construction.

3. Tool registry
   - Holds adapters for real-world geographic data.
   - Examples: Overpass, geocoder, routing engine, PostGIS, private GIS service.

4. Map context
   - Normalizes map features into semantic `MapFeature` records.
   - Classifies features into roles such as pickup hub, reception site,
     flow gate, chokepoint, aid hub, avoidance zone, and comms relay candidate.
   - Scores candidate placements against constraints and returns evidence,
     rejected alternatives, and placement rationale metadata.

5. GeoJSON normalizer
   - Enforces `[lon, lat]`.
   - Closes polygon rings.
   - Trims precision.
   - Validates coordinate ranges.

6. Frontend map
   - Consumes normalized GeoJSON directly.
   - MapLibre, Leaflet, OpenLayers, or Google Maps can all consume the output.

## Map-Aware Scenario Flow

```text
Scenario request
  -> scenario type/template
  -> MapContextBuilder gathers or loads features for bounds
  -> MapContext selects role candidates with constraints
  -> ScenarioPlan uses selected coordinates and metadata
  -> semantic QA checks evidence, scores, rejected alternatives, and geometry
```

## Recommended LLM Contract

The LLM should output only strict plan JSON:

```json
{
  "pipeline": "abstract",
  "operation": "hex_grid",
  "parameters": {
    "bounds": [-82.5, 27.7, -82.1, 28.0],
    "radius_m": 1000
  }
}
```

The engine executes the plan and returns GeoJSON.
