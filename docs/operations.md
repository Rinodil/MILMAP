# Operations

All coordinates use GeoJSON `[longitude, latitude]` order.

## Direct

- `point`: `{ "coordinate": [lon, lat] }`
- `line`: `{ "coordinates": [[lon, lat], ...] }`
- `polygon`: `{ "rings": [[[lon, lat], ...]] }`
- `bbox`: `{ "bounds": [west, south, east, north] }`

## Abstract

- `buffer`: `center`, one radius field, optional `steps`
- `range_ring`: `center`, one radius field, optional `steps`
- `sector`: `center`, one radius field, `start_bearing`, `end_bearing`, optional `steps`
- `regular_polygon`: `center`, one radius field, `sides`, optional `rotation_deg`
- `corridor`: `coordinates`, one width field
- `square_grid`: `bounds`, one cell-size field, optional `max_features`
- `hex_grid`: `bounds`, one radius field, optional `max_features`

Distance fields can use these suffixes:

- `_m`
- `_meters`
- `_km`
- `_kilometers`
- `_miles`

Examples: `radius_m`, `radius_km`, `width_m`, `cell_size_m`.

## Tool-Backed

- `real_world_boundary`: calls a registered `real_world_boundary` tool.
- `overpass_query`: calls a registered `overpass_query` tool.
- `osrm_route`: calls a registered OSRM-compatible routing tool with
  `{ "waypoints": [[lon, lat], ...], "profile": "driving" }` and returns a
  road-following LineString.

Use `default_tool_registry()` to register the default OpenStreetMap Overpass and
OSRM adapters.

## Basemaps

MILMAP's primary basemap is a self-hosted Protomaps vector basemap built from a
Florida PMTiles archive (`.milmap/florida.pmtiles`), served by the app at
`GET /basemaps/florida/{z}/{x}/{y}.mvt` and styled with purpose-mapped flavors
(`protomaps_light` / `protomaps_dark` / `protomaps_grayscale`). No third-party
tile TOS limits; works offline. Online raster providers remain as a fallback. The
basemap is auto-selected per scenario purpose (no manual switcher). See
[Basemaps](basemaps.md) for the purpose mapping, archive build steps, and the TOS
table.

## Screenshots and Notifications

Render the running workspace headlessly and deliver the PNG to the dedicated
Telegram bot:

```bash
.venv/bin/python -m milmap_engine.notify --scenario orlando_metro_shtf
```

See [Screenshots and Telegram Notifications](notifications.md) for deep-linking,
options, env overrides, and the bot-token rotation note.
