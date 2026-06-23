# End-To-End Capability Workflow

This document describes how MILMAP turns a structured scenario request into an
auditable map, QA report, clean screenshot, legend, visual briefing package, and
Telegram delivery.

## Safety Boundary

MILMAP scenarios in this repo are non-operational planning, training,
resilience, logistics, and humanitarian-support artifacts. They must not encode
weapon targeting, strike planning, enemy unit locations, attack routes, weapon
effects, or instructions for harming people.

Conflict-adjacent tests should be framed as simulated civilian impact,
resilience, evacuation, support, medical reception, logistics, communications,
and briefing workflows. Generated imagery must carry the standard disclaimer:

```text
Generated illustration based on MILMAP scenario data; not operational imagery,
not intelligence, and not a targeting product.
```

## 1. Build Plan

The source input is a staged JSON build plan such as:

```text
examples/israel_iran_lebanon_crisis_buildplan.json
```

A build plan defines:

- `scenario_name`: saved scenario id/name.
- `map_context`: map center, bounds, basemap, and optional offline feature
  collection for deterministic smart placement.
- `metadata`: scenario-level safety notes and assumptions.
- `validation_rules`: QA limits for feature counts and route geometry.
- `phases`: ordered layer/object groups with objectives, source metadata,
  geometry operations, styles, and smart-placement requests.

## 2. Smart Placement

`ScenarioBuilder` resolves elements that include `metadata.map_context_role`.
The builder uses `MapContext` to score candidate features from the provided
fixture or a registered map source.

Placement roles include:

- `civic_anchor`
- `reception_site`
- `pickup_hub`
- `supply_node`
- `shelter_candidate`
- `comms_relay_candidate`
- `avoidance_zone`

Scoring considers role match, distance from a preferred anchor, required tags,
preferred tags, excluded tags, bounds, avoidance roles, source confidence, and
the placement profile. Selected elements receive metadata:

- `candidate_score`
- `confidence`
- `selected_role`
- `constraints_checked`
- `evidence`
- `selected_candidate`
- `ranked_candidates`
- `rejected_alternatives`
- `placement_rationale`

## 3. Geometry Compilation

After placement resolution, `ScenarioAgent` compiles the plan into deterministic
GeoJSON. Common operations include:

- `bbox` for operating extents.
- `buffer` and `range_ring` for service/communications areas.
- `polygon` and `sector` for advisory zones.
- `square_grid` for public support grids.
- `corridor` for broad, non-turn-by-turn support corridors.

The output scenario contains styled `layers`, semantic `objects`, and a
combined `geojson` feature collection.

## 4. QA And Score

`validate_scenario_payload` checks the compiled scenario and adds:

- `status`: `pass`, `warning`, or `error`.
- `summary`: layer/object/feature counts and issue counts.
- `score`: 0-100 value, grade, readiness label, deductions, and scoring
  signals.
- `issues`: structured warning/error records.
- `layers`, `objects`, `phases`: per-element QA summaries.

The score rewards evidence-backed, scored, reasoned placements and penalizes
warnings, errors, empty maps, missing placement rationale, low evidence
coverage, low candidate-score coverage, and low-confidence placements.

## 5. Scenario Store

When `ScenarioBuilder(store=ScenarioStore())` is used, the final scenario is
saved to:

```text
.milmap/scenarios.json
```

The API can then load it by scenario id:

```text
GET /scenario/{scenario_id}
GET /scenario/{scenario_id}/qa
GET /scenario/{scenario_id}/legend
```

## 6. Web Rendering

The FastAPI server serves the MapLibre workspace. A saved scenario can be opened
with:

```text
http://127.0.0.1:8004/?scenario=<scenario_id>&basemap=osm
```

Presentation mode hides side panels for clean export:

```text
http://127.0.0.1:8004/?scenario=<scenario_id>&basemap=osm&presentation=1
```

Add `legend=0` to hide the on-map legend when the caption or report carries the
legend as text.

## 7. Legend Export

`GET /scenario/{scenario_id}/legend` returns structured entries and caption
text. Example format:

```text
blue area: Jerusalem Coordination Area
purple line: Mount Lebanon Communications Ring
green area: Jordan Valley Support Corridor
```

The Telegram sender can append this text with `--legend-text`.

## 8. Visual Briefing Package

`milmap-visual-briefing` packages the stored scenario and optional screenshot
for ChatGPT/OpenAI Images. It writes:

- `visual_briefing_manifest.json`
- `briefing_summary.json`
- `briefing_report.md`
- `prompt.txt`
- `chatgpt_handoff.md`
- copied reference images under `references/`

The prompt includes scenario name, QA score, map context, layer/object names,
legend text, safety constraints, and disclaimer. If a screenshot is supplied,
the package targets image editing with references; otherwise it targets
text-to-image generation.

## 9. Telegram Delivery

`milmap_engine.notify` captures a headless browser screenshot and sends it to
the configured Telegram bot. For clean map delivery:

```bash
.venv/bin/python -m milmap_engine.notify \
  --scenario israel_iran_lebanon_crisis_test \
  --basemap osm \
  --presentation \
  --hide-legend \
  --legend-text \
  --caption "MILMAP - Israel/Iran/Lebanon regional crisis capability test"
```

For this conflict-adjacent test, the caption should state that the image is
simulated, non-operational, and not intelligence or targeting.

## 10. Reproducible Test Sequence

Build and save:

```bash
.venv/bin/python - <<'PY'
import json
from pathlib import Path
from milmap_engine import ScenarioBuilder, ScenarioStore

plan = json.loads(Path("examples/israel_iran_lebanon_crisis_buildplan.json").read_text())
result = ScenarioBuilder(store=ScenarioStore()).build(plan)
print(result["scenario_id"], result["qa"]["status"], result["qa"]["score"])
PY
```

Start or restart the server:

```bash
.venv/bin/uvicorn milmap_engine.server:app --host 127.0.0.1 --port 8004
```

Capture and send:

```bash
.venv/bin/python -m milmap_engine.notify \
  --scenario israel_iran_lebanon_crisis_test \
  --basemap osm \
  --presentation \
  --hide-legend \
  --legend-text
```

Create the image-generation handoff:

```bash
milmap-visual-briefing \
  --scenario israel_iran_lebanon_crisis_test \
  --screenshot /tmp/milmap-israel-iran-lebanon-crisis-test-clean.png \
  --out-dir .milmap/visual_briefings/israel_iran_lebanon_crisis_test
```

Use `prompt.txt` plus the packaged reference screenshot in ChatGPT/OpenAI
Images. The scenario JSON, QA report, legend, and screenshot remain the
authoritative record.
