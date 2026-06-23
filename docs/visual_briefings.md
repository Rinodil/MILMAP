# Visual Briefings

MILMAP can package a saved scenario and map screenshot for high-fidelity visual
briefing generation. The geospatial scenario remains the source of truth; image
generation is used only for simulated training, proposal, resilience, and
planning visuals.

## Flow

```text
saved scenario
-> rendered map screenshot
-> scenario/layer/object summary, legend text, and QA score
-> reference-image package
-> ChatGPT Images or OpenAI Images API
-> generated briefing graphic
```

The package includes:

- `visual_briefing_manifest.json`
- `briefing_summary.json`
- `briefing_report.md`
- `prompt.txt`
- `chatgpt_handoff.md`
- copied reference images under `references/`

The summary and prompt include the scenario QA status, 0-100 QA score, grade,
readiness label, map context, and text legend so briefing graphics stay tied to
the same auditable scenario source as the map.

`briefing_report.md` is the human-readable packet for proposal, review, or
handoff use. It includes QA readiness, map context, layer/object names, the
plain-text legend, image-generation settings, references, and the required
disclaimer.

Every prompt includes the required disclaimer:

```text
Generated illustration based on MILMAP scenario data; not operational imagery,
not intelligence, and not a targeting product.
```

The prompt also instructs the image model to avoid weapon targeting, reticles,
strike planning, weapon effects, or harm instructions.

## CLI

Create a handoff package from a saved scenario and existing screenshot:

```bash
milmap-visual-briefing \
  --scenario tampa_map_test \
  --screenshot /tmp/milmap-tampa-map-test.png \
  --out-dir .milmap/visual_briefings/tampa_map_test
```

Generate through the OpenAI Images API when `OPENAI_API_KEY` is set:

```bash
milmap-visual-briefing \
  --scenario tampa_map_test \
  --screenshot /tmp/milmap-tampa-map-test.png \
  --out-dir .milmap/visual_briefings/tampa_map_test \
  --generate
```

The default model target is `gpt-image-2`. If reference images are supplied,
MILMAP prepares an image-edit request. Without references, it prepares a
text-to-image request.

## API

```bash
curl -X POST http://127.0.0.1:8004/scenario/tampa_map_test/visual_briefing \
  -H 'Content-Type: application/json' \
  -d '{
    "screenshot_path": "/tmp/milmap-tampa-map-test.png",
    "out_dir": ".milmap/visual_briefings/tampa_map_test"
  }'
```

Set `"generate": true` to call the OpenAI Images API from the server process.
That requires `OPENAI_API_KEY` in the server environment.

## Use Cases

- Government capability statements and proposal graphics.
- Emergency-management training visuals.
- Installation resilience exercises.
- Non-kinetic logistics and support storyboards.
- Telegram/PDF briefing image production.

Generated images are illustrative only. MILMAP GeoJSON, source metadata, QA
reports, and screenshots remain the authoritative record.
