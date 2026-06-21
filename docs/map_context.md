# Map Context

`MapContext` is the semantic map-understanding layer between raw map data and
scenario placement. It keeps the agent from picking points by label alone.

## Flow

```text
OSM / GeoJSON features
-> MapFeature normalization
-> semantic role classification
-> candidate scoring with constraints
-> selected placement metadata
-> scenario layer/object
-> semantic QA
```

## Roles

The classifier assigns one or more roles to each feature:

- `aid_hub`
- `avoidance_zone`
- `chokepoint`
- `civic_anchor`
- `comms_relay_candidate`
- `flow_gate`
- `pickup_hub`
- `reception_site`
- `route_anchor`
- `shelter_candidate`
- `supply_node`

Roles are evidence hints, not final decisions. Scenario builders should request
candidates by role and pass constraints such as `near`, `far_from`,
`avoid_roles`, and `required_tags`.

## Example

```python
from milmap_engine import MapContext

context = MapContext.from_geojson(feature_collection, source_name="fixture")
selection = context.select_candidate(
    "pickup_hub",
    near=[-81.3797, 28.5377],
    preferred_max_distance_m=12000,
    avoid_roles=["avoidance_zone"],
    avoid_within_m=500,
)

metadata = selection.metadata(
    "Selected because it is the highest-scored pickup hub near the civic origin "
    "and outside mapped avoidance zones."
)
```

## Builder Integration

`ScenarioBuilder` can resolve map-aware placements before it compiles geometry.
Supply cached context in `map_context.feature_collection`,
`map_context.features_geojson`, or `map_context.overpass_json`. If live network
lookup is acceptable, set `map_context.fetch_overpass` with `map_context.bounds`.

Then annotate any layer or object metadata:

```json
{
  "type": "supply_node",
  "name": "Pickup Node",
  "placement": { "mode": "point" },
  "metadata": {
    "map_context_role": "pickup_hub",
    "map_context_constraints": {
      "near": [-81.3797, 28.5377],
      "preferred_max_distance_m": 12000,
      "avoid_roles": ["avoidance_zone"],
      "avoid_within_m": 500
    },
    "placement_rationale": "Select the best mapped pickup hub near the origin and outside mapped avoidance zones."
  }
}
```

For point objects, the selected coordinate is written to `placement.coordinate`.
For centered layers such as `buffer`, `range_ring`, `sector`, and
`regular_polygon`, the selected coordinate is written to `parameters.center`.
Use `map_context_constraints.target_parameter` to select a different layer
parameter.

The returned metadata includes:

- `selected_role`
- `candidate_score`
- `constraints_checked`
- `evidence`
- `rejected_alternatives`
- `placement_rationale`

Copy that metadata into the scenario element. Then run:

```python
validate_scenario_payload(
    payload,
    validation_rules={
        "placement_reasoning": {
            "enabled": True,
            "require_evidence": True,
            "require_rejected_alternatives": True,
            "min_candidate_score": 40,
        }
    },
)
```

## Overpass

`MapContextBuilder.build_query(bounds)` emits an Overpass query for common
candidate classes: hospitals, schools, transit, parking, malls, civic buildings,
fuel/logistics points, roads, bridges, water, industrial areas, and towers.

Use `build_from_overpass(bounds)` when network access is acceptable. For tests
and deterministic scenario builds, prefer cached GeoJSON/Overpass fixtures.
