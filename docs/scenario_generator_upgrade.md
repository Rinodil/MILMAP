# Scenario Generator Upgrade

Date: 2026-06-24

## Purpose

This upgrade adds a simple public entry point for generating a complete MILMAP
scenario from a built-in template, validating the compiled payload, and
exporting it as JSON. It is intended to give new users a one-command path from
repository checkout to a working spatial scenario.

## Files Changed

- `generate_scenario.py`
  - Adds a root-level scenario generator CLI.
  - Includes the built-in `regional_coordination` and
    `advanced_regional_scenario` templates.
  - Compiles the template through `ScenarioAgent`.
  - Runs QA with `validate_scenario_payload`.
  - Writes the generated scenario payload to JSON.
  - Optionally saves the scenario and sends a Telegram screenshot through the
    existing `milmap_engine.notify` workflow.
- `examples/regional_coordination_scenario.json`
  - Adds a ready-to-run neutral example scenario using the same template shape.
- `examples/advanced_regional_scenario.json`
  - Adds a ready-to-run advanced planning example with a coverage sector,
    approach corridor, search grid, hub, and priority node.
- `README.md`
  - Adds usage instructions for the one-command generator, direct CLI execution
    of the example, and optional screenshot notification.

## Compatibility Notes

The original handoff used APIs and field names that did not match the current
repository implementation. The generator was adapted to the live engine:

- `ScenarioPlan.from_mapping(...)` is used instead of Pydantic
  `ScenarioPlan.model_validate(...)`.
- `validate_scenario_payload(result.payload)` is used instead of the missing
  `validate_scenario(...)`.
- Existing notification support is `notify_screenshot(...)`; there is no
  `notify_scenario_result(...)`.
- Scenario object placement uses:

```json
{"mode": "point", "coordinate": [35.5, 33.8]}
```

instead of:

```json
{"type": "point", "coordinates": [35.5, 33.8]}
```

- Corridor parameters use `coordinates`.
- Grid parameters use `bounds`.
- `max_features` was raised from `30` to `300` because the requested 10 km
  grid over the provided bounds generates more than 30 cells.
- Public examples use neutral layer/object types such as `coverage_zone`,
  `approach_corridor`, `hub`, and `priority_node` while still exercising the
  requested spatial mechanics.

## Runtime Behavior

Run the built-in generator:

```bash
python3 generate_scenario.py --template regional_coordination
python3 generate_scenario.py --template advanced_regional_scenario
```

Expected result:

- Writes `generated_regional_coordination.json` or
  `generated_advanced_regional_scenario.json`.
- Prints scenario name, QA score, layer count, object count, and output path.
- Current verified QA result: `92/100`, grade `A`, status `pass`.

Run the example through the existing package CLI:

```bash
PYTHONPATH=src python3 -m milmap_engine.cli examples/regional_coordination_scenario.json
PYTHONPATH=src python3 -m milmap_engine.cli examples/advanced_regional_scenario.json
```

Optional screenshot notification:

```bash
python3 generate_scenario.py --template regional_coordination --notify
python3 generate_scenario.py --template advanced_regional_scenario --notify
```

`--notify` requires the MILMAP web workspace to be running. It saves the
generated payload through `ScenarioStore`, then asks the existing notifier to
capture the scenario deep link and send it to Telegram.

## Verification Performed

The following commands completed successfully:

```bash
python3 generate_scenario.py --template regional_coordination --output /tmp/milmap_generated_regional_coordination.json
python3 generate_scenario.py --template advanced_regional_scenario --output /tmp/milmap_generated_advanced_regional_scenario.json
PYTHONPATH=src python3 -m milmap_engine.cli examples/regional_coordination_scenario.json
PYTHONPATH=src python3 -m milmap_engine.cli examples/advanced_regional_scenario.json
python3 -m json.tool examples/regional_coordination_scenario.json
python3 -m json.tool examples/advanced_regional_scenario.json
```

Observed generator output:

```text
Generating scenario: Regional Coordination Scenario
QA Score: 92/100 | Grade: A | Status: pass
Layers processed: 3
Objects processed: 2
Result saved to: /tmp/milmap_generated_regional_coordination.json
```

The advanced template currently verifies with the same QA result shape:

```text
Generating scenario: Advanced Regional Planning Scenario
QA Score: 92/100 | Grade: A | Status: pass
Layers processed: 3
Objects processed: 2
Result saved to: /tmp/milmap_generated_advanced_regional_scenario.json
```

## Review Checklist

- Confirm the neutral template language is appropriate for public repository
  use.
- Confirm `--notify` should remain screenshot-based rather than adding a new
  payload-only notification helper.
- Decide whether the root generator should eventually support loading templates
  from `examples/*.json`.
- Decide whether `generate_scenario.py` should be promoted into an installed
  console script in `pyproject.toml`.
- Consider adding a focused automated test that executes the built-in template
  and asserts QA status, layer count, object count, and GeoJSON feature count.
