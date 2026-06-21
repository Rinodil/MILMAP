# Basemaps

MILMAP's primary basemap is a **self-hosted Protomaps vector basemap** built from
OpenStreetMap data for Florida. It is served by the MILMAP app itself (same
origin), so there are **no third-party tile Terms-of-Service limits** and it
works offline once the archive is built. Online raster providers remain wired as
a fallback.

The map picks a basemap automatically from each scenario's purpose — there is no
manual switcher.

## Basemaps and purposes

Self-hosted Protomaps vector flavors (primary, when `florida.pmtiles` is present):

| Basemap                | Purpose                       | Flavor    |
| ---------------------- | ----------------------------- | --------- |
| `protomaps_light`      | Urban street-level navigation | light     |
| `protomaps_dark`       | Night / low-light operations  | dark      |
| `protomaps_grayscale`  | Terrain / neutral recon base  | grayscale |

Online raster fallbacks (used when the archive is absent, or for areas outside
Florida): `osm`, `cartodb_dark`, `opentopomap`, `esri_street`, `esri_topo`.

`GET /basemaps` returns the full registry, the effective `default`/`order`, and
`pmtiles.available`.

## Auto-selection by purpose

For each scenario the frontend chooses a basemap from `map_context`:

1. An explicit `map_context.basemap` id wins (e.g. `"protomaps_dark"`).
2. Otherwise the first registry keyword found in the joined
   `purpose` / `mode` / `scenario_type` text wins. When the Florida archive is
   present the order is `protomaps_dark` → `protomaps_grayscale` →
   `protomaps_light` → (raster fallbacks).
3. Otherwise the default (`protomaps_light`, or `osm` when the archive is absent).

Examples (archive present):

| `map_context`                        | Basemap               |
| ------------------------------------ | --------------------- |
| `{ "mode": "civil_emergency_demo" }` | `protomaps_light`     |
| `{ "mode": "night_ops" }`            | `protomaps_dark`      |
| `{ "purpose": "terrain analysis" }`  | `protomaps_grayscale` |
| `{ "basemap": "protomaps_dark" }`    | `protomaps_dark`      |

`?basemap=<id>` on the workspace URL forces a basemap for previewing/screenshots
(not a UI control):

```bash
.venv/bin/python -m milmap_engine.notify \
  --scenario orlando_metro_shtf --basemap protomaps_dark --no-send
```

## How it is served

- **Tiles**: the MILMAP FastAPI app reads tiles directly from
  `.milmap/florida.pmtiles` (via the `pmtiles` Python reader) and serves them at
  `GET /basemaps/florida/{z}/{x}/{y}.mvt` (gzip MVT). Same origin as the
  workspace — no separate tile server, no CORS.
- **Style**: `GET /basemaps/protomaps/style/{flavor}.json` returns the vendored
  Protomaps theme (`src/milmap_engine/static/basemaps/protomaps/<flavor>.json`)
  with the vector source rewritten to the local tile route.
- **Glyphs + sprite**: loaded from `protomaps.github.io` (free CC0 assets).
  These are the only remaining network dependency. For a fully air-gapped
  deployment, mirror the fonts and sprites locally and update `PROTOMAPS_GLYPHS`
  / the sprite URLs — see "Full air-gap" below.

`MILMAP_PMTILES` overrides the archive path (default `.milmap/florida.pmtiles`).
Serving tiles requires the `pmtiles` package (in the `[api]` extra); if it is
absent the Protomaps basemaps are simply reported unavailable and the raster
fallbacks are used.

## Building the Florida archive

The archive is gitignored (`.milmap/`). To (re)build it:

```bash
# 1. Get the pmtiles CLI (Linux x86_64) into .milmap/bin/
#    https://github.com/protomaps/go-pmtiles/releases

# 2. Extract Florida from the latest Protomaps daily build (range requests;
#    the CDN keeps ~4 days — check https://maps.protomaps.com/builds/).
.milmap/bin/pmtiles extract https://build.protomaps.com/<YYYYMMDD>.pmtiles \
  .milmap/florida.pmtiles \
  --bbox=-87.634938,24.523096,-80.031362,31.000888 \
  --maxzoom=15

# 3. Verify
.milmap/bin/pmtiles show .milmap/florida.pmtiles
```

Florida @ maxzoom 15 is ~1.1 GB (~210k tiles). Use `--maxzoom=16` for more
detail (larger), or a tighter `--bbox` for a smaller region.

Alternative serving (not used by MILMAP, but supported by the data): the same
file works with `pmtiles serve .milmap` or Martin on a separate port.

## Terms of Service

| Basemap(s)                | Offline posture | Notes                                                            |
| ------------------------- | --------------- | ---------------------------------------------------------------- |
| `protomaps_*` (Florida)   | self-hosted     | Protomaps/OpenStreetMap vector tiles (ODbL). No third-party tile TOS limits. Attribute OpenStreetMap. |
| `opentopomap`             | low             | Online fallback; moderate offline use tolerated.                 |
| `esri_street` / `esri_topo` | medium        | Online fallback; offline via official `.tpk`/`.vtpk` packages.   |
| `cartodb_dark`            | high            | Online fallback; bulk/offline generally violates terms.          |
| `osm`                     | prohibited      | Online fallback only; raw-tile bulk/offline is banned.           |

MILMAP never bulk-downloads third-party tiles. The Protomaps path uses a single
range-extracted archive from the Protomaps build (OSM-derived, freely
self-hostable).

## Full air-gap (follow-up)

Tiles are already fully local. To remove the last online dependency, mirror the
Protomaps fonts and sprites locally:

- Fonts: `https://protomaps.github.io/basemaps-assets/fonts/{fontstack}/{range}.pbf`
- Sprites: `https://protomaps.github.io/basemaps-assets/sprites/v4/{light,dark,grayscale}.{json,png}` (+ `@2x`)

Serve them from the app and point `PROTOMAPS_GLYPHS` and the per-flavor `sprite`
URLs at the local copies.
