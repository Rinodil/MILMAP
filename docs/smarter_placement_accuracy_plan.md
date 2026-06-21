# Smarter Placement Accuracy Plan

## Goal

Improve MILMAP placement accuracy by making map placement an evidence-backed,
adaptable selection process instead of relying on model-guessed coordinates.
The LLM or caller should describe intent, role, constraints, and required
evidence. The engine should select, score, explain, validate, and expose the
placement.

## Current Foundation

MILMAP already has the correct base architecture:

- `MapContext` normalizes OSM/GeoJSON features into semantic candidates.
- `classify_feature` assigns roles such as `pickup_hub`, `shelter_candidate`,
  `supply_node`, `avoidance_zone`, `route_anchor`, and
  `comms_relay_candidate`.
- `ScenarioBuilder` resolves elements with `metadata.map_context_role` before
  geometry compilation.
- Placement metadata includes `candidate_score`, `evidence`,
  `constraints_checked`, `rejected_alternatives`, `selected_role`, and
  `placement_rationale`.
- QA can require placement rationale, evidence, rejected alternatives, and a
  minimum candidate score through `validation_rules.placement_reasoning`.

The next step is to make the selection contract stricter and the scoring model
more expressive.

## Adaptable Placement Format

Use this format for layers and objects that need smart placement:

```json
{
  "placement": { "mode": "point" },
  "metadata": {
    "map_context_role": "pickup_hub",
    "map_context_constraints": {
      "near": [-81.3797, 28.5377],
      "preferred_max_distance_m": 12000,
      "avoid_roles": ["avoidance_zone"],
      "avoid_within_m": 500,
      "required_tags": {
        "shop": ["mall", "supermarket"]
      }
    },
    "placement_rationale": "Select a mapped pickup hub near the civic center, outside avoidance zones."
  }
}
```

The builder resolves this into a concrete coordinate and attaches evidence:

```json
{
  "source_type": "map_context",
  "source_name": "OpenStreetMap via Overpass",
  "confidence": "high",
  "selected_role": "pickup_hub",
  "candidate_score": 72.5,
  "constraints_checked": ["role:pickup_hub", "near", "avoid_roles"],
  "evidence": [],
  "rejected_alternatives": [],
  "placement_rationale": "Select a mapped pickup hub near the civic center, outside avoidance zones."
}
```

This keeps input semantic and output auditable.

## Implementation Plan

### 1. Add Placement Profiles

Introduce placement profiles keyed by scenario purpose or mode:

- `civil_emergency`
- `evacuation`
- `logistics`
- `training`
- `infrastructure`
- `default`

Each profile should define scoring weights:

```json
{
  "placement_profile": "civil_emergency",
  "weights": {
    "role": 50,
    "distance": 30,
    "named_feature": 5,
    "footprint": 10,
    "source_confidence": 15,
    "avoidance_clearance": 20,
    "required_tag": 12,
    "preferred_tag": 6
  }
}
```

Default behavior should remain backward compatible when no profile is supplied.

### 2. Extend Constraint Syntax

Add support for:

- `prefer_tags`: soft boosts for useful tags.
- `exclude_tags`: hard rejection for disallowed tags.
- `min_distance_from_existing_m`: deconflict new placements from existing
  scenario objects.
- `unique_feature_required`: prevent multiple planned elements from selecting
  the same map feature.
- `within_bounds`: require the candidate geometry or coordinate to fall inside
  scenario bounds.
- `max_candidates`: control how many alternatives are returned.

Example:

```json
{
  "map_context_constraints": {
    "near": [-81.3797, 28.5377],
    "preferred_max_distance_m": 12000,
    "required_tags": { "amenity": ["school", "community_centre"] },
    "prefer_tags": { "access": ["yes", "public"], "parking": ["yes"] },
    "exclude_tags": { "access": ["private", "no"] },
    "avoid_roles": ["avoidance_zone"],
    "avoid_within_m": 500,
    "unique_feature_required": true
  }
}
```

### 3. Use Geometry-Aware Avoidance

Current candidate checks mainly compare center-point distance. Improve this by
using feature geometry when available:

- Reject candidate points inside avoidance polygons.
- Penalize candidates near avoidance polygon edges.
- Prefer area features with usable mapped footprints for hubs and shelters.
- Use polygon bounds as a cheap first pass before exact geometry checks.

This matters for water, wetlands, industrial landuse, campuses, parks,
shopping centers, and large civic sites.

### 4. Return Ranked Candidates

Expose the top ranked candidates in metadata and optionally through an API route:

```json
{
  "selected_candidate": {},
  "ranked_candidates": [],
  "rejected_alternatives": []
}
```

This allows the UI, tests, and operators to inspect why one feature won.

### 5. Add Source Confidence

Increase confidence when a feature has:

- Stable `osm_type` and `osm_id`.
- A `name`.
- Relevant role tags.
- Polygon or line geometry rather than only a sparse point.
- A `source_url`.

Lower confidence for sparse or generated features.

### 6. Enable Strict Placement QA

Use strict placement rules for smart-placement scenarios:

```json
{
  "placement_reasoning": {
    "enabled": true,
    "require_evidence": true,
    "require_rejected_alternatives": true,
    "min_candidate_score": 40
  }
}
```

Add optional stricter checks:

- `require_constraints_checked`
- `require_selected_role`
- `require_source_url_or_osm_id`
- `min_rejected_alternatives`
- `reject_low_confidence`

### 7. Add Tests

Add focused tests for:

- `prefer_tags` boosts but does not override hard constraints.
- `exclude_tags` rejects otherwise strong candidates.
- Polygon avoidance rejects points inside water or industrial zones.
- Ranked alternatives are returned in deterministic order.
- Deconfliction prevents duplicate feature use when requested.
- Strict QA flags missing source, role, evidence, alternatives, or low score.

### 8. Surface Placement Quality In The UI

Enhance the inspector to show:

- Candidate score.
- Confidence.
- Selected role.
- Evidence tags.
- Rejected alternatives.
- Constraints checked.
- Warnings for low-confidence or weakly sourced placements.

This makes smarter placement reviewable instead of hidden inside the backend.

## Recommended Order

1. Add `prefer_tags`, `exclude_tags`, and ranked candidate output.
2. Add placement profile weights with backward-compatible defaults.
3. Add geometry-aware avoidance.
4. Add deconfliction across scenario objects/layers.
5. Tighten QA rules and tests.
6. Expose placement quality in the UI inspector.

## Design Rule

The LLM should never invent final coordinates when map data is available. It
should emit role, constraints, and rationale. MILMAP should resolve the exact
placement through map context, deterministic scoring, source metadata, and QA.
