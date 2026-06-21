# LLM Contract

The LLM is an intent router. It should emit a `SpatialPlan`, not raw coordinate loops.

## System Prompt

```text
You are a spatial intent router.
Output only JSON matching the provided schema.
Never invent coordinate loops.
Use [longitude, latitude] order for every coordinate.
Route abstract shapes to pipeline=abstract.
Route caller-provided raw coordinates to pipeline=direct.
Route public map-feature retrieval to pipeline=real_world.
Use operation=osrm_route for road-following routes when caller provides waypoints.
When coordinates, bounds, radius, width, bearings, or names are missing, ask for the missing field instead of guessing.
```

## Examples

Buffer:

```json
{
  "pipeline": "abstract",
  "operation": "buffer",
  "parameters": {
    "center": [-82.324, 27.845],
    "radius_miles": 5,
    "steps": 64
  }
}
```

Route corridor:

```json
{
  "pipeline": "abstract",
  "operation": "corridor",
  "parameters": {
    "coordinates": [[-82.42, 27.91], [-82.35, 27.88], [-82.30, 27.83]],
    "width_m": 750
  }
}
```

Real-world boundary tool call:

```json
{
  "pipeline": "real_world",
  "operation": "real_world_boundary",
  "parameters": {
    "name": "Hillsborough County",
    "admin_level": "6"
  }
}
```

Road-following route tool call:

```json
{
  "pipeline": "real_world",
  "operation": "osrm_route",
  "parameters": {
    "waypoints": [[-81.3792, 28.5383], [-81.423, 28.541], [-81.758, 28.549]],
    "profile": "driving"
  }
}
```

## Runtime Rule

If the plan is missing required fields, reject it or ask a follow-up question. Do not repair missing spatial facts by guessing.

## Scenario Planner Contract

A scenario planner can emit `ScenarioPlan` JSON when the request asks for a
complete map setup rather than a single geometry operation.

Use `objects` for semantic markers and annotations. Use `layers` for generated
geometry. If a layer `type` is semantic, include the deterministic geometry
`operation` that the engine should execute.

Example:

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
      "type": "perimeter",
      "operation": "buffer",
      "parameters": {
        "center": [-82.324, 27.845],
        "radius_km": 5
      }
    }
  ]
}
```

The schema is in `schemas/scenario_plan.schema.json`.

## Element Refinement Contract

For revisions, the LLM should not return a full scenario unless the caller asks for
a rebuild. It should return one replacement element for the requested target. The
backend applies that element, recompiles the scenario, runs QA, and saves a new
version.

Rules:

- Return exactly one `layer` or `object` replacement.
- Preserve the target `id` unless the caller explicitly asks for a new element.
- For routes, prefer `type: route` + `operation: line` centerlines. Use
  `type: corridor` only when an explicit corridor width is needed.
- For detailed streets, coordinates must come from caller-provided route data, a
  routing engine, or a map extraction step. Synthetic routes must be marked with
  `metadata.source_type: generated`, a confidence value, and assumptions.
- If water avoidance or turn-by-turn road accuracy is required, mark the element
  as routing/user verified only when that external check actually happened.

Shape:

```json
{
  "target": {"kind": "layer", "id": "primary_route"},
  "action": "replace",
  "element": {
    "id": "primary_route",
    "type": "route",
    "name": "Primary Route Centerline",
    "pipeline": "direct",
    "operation": "line",
    "parameters": {
      "coordinates": [[-81.3792, 28.5383], [-81.3860, 28.5388]]
    },
    "metadata": {
      "source_type": "routing",
      "source_name": "street-routing pass",
      "confidence": "high",
      "assumptions": ["Route geometry was checked against the road network."]
    }
  },
  "note": "Replace broad corridor with street-following centerline."
}
```

The schema is exposed in `milmap_engine.llm.ELEMENT_REFINEMENT_SCHEMA`, and
`ScenarioRefiner` applies the proposal via `POST /scenario/{id}/refine`.
