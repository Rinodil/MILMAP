# Screenshots and Telegram Notifications

MILMAP can render the running web workspace headlessly and deliver the PNG to a
dedicated Telegram bot. This is the standard way to capture a build/QA result
and push it somewhere reviewable.

The implementation lives in `src/milmap_engine/notify.py` and has **no
third-party requirements** for delivery: screenshots use the Chromium that ships
with Playwright (preferred) or any system Chrome, and the upload is a hand-rolled
multipart request over `urllib`.

## Pipeline

```text
saved scenario  ->  GET /scenario/{id}            (server already running)
workspace URL   ->  http://127.0.0.1:8004/?scenario=<id>
headless render ->  Playwright Chromium (software WebGL) waits for map idle
PNG             ->  Telegram Bot API sendPhoto  ->  @milmapbot chat
```

The frontend supports a `?scenario=<id>` deep link: on map load it calls
`loadScenario(<id>)` instead of executing the default plan, and it sets
`window.__milmap.ready = true` once the map goes idle after drawing. The
screenshot tool waits on that flag, so the capture always reflects a fully
rendered scenario rather than a half-painted map.

## Dedicated Telegram bot (hardcoded)

This project owns a dedicated bot, so the credentials are hardcoded in
`notify.py` rather than passed in every run:

| Setting   | Value                                   | Env override            |
| --------- | --------------------------------------- | ----------------------- |
| Bot       | `@milmapbot`                            | `MILMAP_TG_BOT_TOKEN`   |
| Chat      | private chat `7972353156` (`@Xvernici`) | `MILMAP_TG_CHAT_ID`     |
| Server    | `http://127.0.0.1:8004`                 | `MILMAP_SERVER`         |
| Chrome    | Playwright cache / system Chrome        | `MILMAP_CHROME`         |

> **Security note.** The bot token is a live credential. If this tree is ever
> shared or published, rotate it through `@BotFather` (`/revoke`) and set
> `MILMAP_TG_BOT_TOKEN` to the new value instead of editing the default. The
> chat id is discovered once from `getUpdates` after sending `/start` to the
> bot.

## Usage

Screenshot a saved scenario and send it:

```bash
.venv/bin/python -m milmap_engine.notify \
  --scenario orlando_metro_shtf \
  --caption "MILMAP - Orlando metro SHTF build, QA pass"
```

Capture only (no Telegram delivery), e.g. for a local review:

```bash
.venv/bin/python -m milmap_engine.notify \
  --scenario orlando_metro_shtf --out /tmp/milmap.png --no-send
```

Screenshot an arbitrary URL or the default workspace:

```bash
.venv/bin/python -m milmap_engine.notify --url http://127.0.0.1:8004/
```

### Options

| Flag         | Default                  | Purpose                                          |
| ------------ | ------------------------ | ------------------------------------------------ |
| `--scenario` | —                        | Saved scenario id to deep-link.                  |
| `--basemap`  | —                        | Force a basemap id (`?basemap=<id>`), e.g. `cartodb_dark`. |
| `--server`   | `http://127.0.0.1:8004`  | Base URL of the running workspace.               |
| `--url`      | —                        | Explicit URL (overrides `--server`/`--scenario`).|
| `--caption`  | auto                     | Telegram caption text.                           |
| `--out`      | temp dir                 | Where to write the PNG.                           |
| `--width`    | `1366`                   | Viewport width.                                  |
| `--height`   | `900`                    | Viewport height.                                 |
| `--wait`     | `12000`                  | Max ms to wait for the render to settle.         |
| `--no-send`  | off                      | Capture only; skip Telegram delivery.            |

## Programmatic use

```python
from milmap_engine.notify import notify_screenshot

notify_screenshot(
    scenario="orlando_metro_shtf",
    caption="MILMAP - Orlando metro SHTF build, QA pass",
)
```

Lower-level helpers are also exported: `capture_screenshot(url, out_path)` and
`send_photo(path, caption)`.

## How the render works headlessly

MapLibre GL needs a WebGL context. Headless Chromium disables GPU WebGL by
default, so the tool launches with software WebGL enabled:

```text
--enable-unsafe-swiftshader --use-gl=angle --use-angle=swiftshader
--ignore-gpu-blocklist
```

If Playwright is not installed, the tool falls back to a one-shot
`chrome-headless-shell --screenshot`. That fallback cannot wait for the map to
settle, so it is best-effort only — install Playwright for reliable scenario
screenshots.
