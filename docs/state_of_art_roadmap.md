# State Of The Art Roadmap

MILMAP's near-term differentiator is an auditable geospatial scenario factory:
one scenario source produces the map, clean presentation view, plain-text legend,
QA score, and image-generation handoff package.

## Implemented Focus: 1-6

1. Scenario-to-briefing pipeline: saved scenarios can produce visual briefing
   handoff packages with manifests, prompts, reference images, and summaries.
2. Auditable placement intelligence: map-context selection records candidate
   scores, selected roles, evidence, constraints checked, and rejected
   alternatives.
3. Map QA score: validation reports now include a 0-100 score, grade,
   readiness label, deduction reasons, and scoring signals.
4. Clean presentation modes: screenshots can hide side panels and optionally
   hide the on-map legend.
5. Text legend as data: scenarios expose structured legend entries and
   caption-ready text such as `blue line: Friendly Comms`.
6. Reference-accurate image generation handoff: the visual briefing package
   uses MILMAP screenshots/reference images as ground truth for ChatGPT/OpenAI
   Images, with non-kinetic safety constraints and required disclaimer text.

## Deferred Notes: 7-10

7. Contract opportunity targeting: add a separate capture module for matching
   MILMAP capabilities to public solicitations, NAICS/PSC codes, and agency
   mission needs. Keep this separate from scenario execution.
8. Exercise generator: generate non-kinetic training injects, phase cards,
   observer notes, and evaluation rubrics from a scenario.
9. After-action review mode: capture decisions, map snapshots, timeline
   events, participant notes, and lessons learned against the scenario source.
10. Interoperability layer: export/import common geospatial formats and
    operational graphics packages where permitted, including GeoJSON, KML, GPX,
    PMTiles references, and future TAK/CoT-style adapters.

All deferred items should stay civil-emergency, resilience, logistics, training,
or assessment focused. Do not implement weapon targeting, strike planning,
enemy target generation, or harm-enabling workflows.
