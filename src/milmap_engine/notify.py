"""Screenshot capture and Telegram delivery for the MILMAP demo workspace.

This module is dedicated to the MILMAP project. The Telegram bot
(``@milmapbot``) and the default chat are hardcoded below on purpose: that
bot exists only to deliver MILMAP build/QA screenshots, so the project owns
the credential rather than threading it through config every run. Override
with environment variables when forking or rotating.

Pipeline
--------
1. Render the running web workspace with headless Chromium. Pass a saved
   ``scenario_id`` to deep-link the map straight to that scenario via the
   ``?scenario=<id>`` URL parameter the frontend understands.
2. POST the resulting PNG to the Telegram Bot API ``sendPhoto`` endpoint.

No third-party dependencies are required: screenshots reuse the Chromium
binary that ships with the Playwright browser cache (or any system Chrome),
and the upload is a hand-rolled multipart request over ``urllib``.

CLI
---
    python -m milmap_engine.notify --scenario orlando_metro_shtf \\
        --caption "MILMAP - Orlando metro SHTF build, QA pass"

Security note: the bot token below is a live credential. If this tree is
shared, rotate it through @BotFather (``/revoke``) and set
``MILMAP_TG_BOT_TOKEN`` instead of editing the default.
"""

from __future__ import annotations

import argparse
import glob
import json
import mimetypes
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from .legend import scenario_legend_text
from .store import ScenarioStore

# --- Hardcoded, project-dedicated Telegram configuration ---------------------
# Override any of these via environment variables without touching the code.
TELEGRAM_BOT_TOKEN = os.environ.get(
    "MILMAP_TG_BOT_TOKEN", "8809583793:AAEYlrIniPjVGjG4G06xVWER8ifQdbgZDr4"
)
TELEGRAM_CHAT_ID = os.environ.get("MILMAP_TG_CHAT_ID", "7972353156")

# Where the demo workspace is served. The current demo runs on :8004.
DEFAULT_SERVER = os.environ.get("MILMAP_SERVER", "http://127.0.0.1:8004")

# Headless Chromium flags that make MapLibre's WebGL canvas render without a
# GPU. SwiftShader is gated behind --enable-unsafe-swiftshader in recent
# Chromium builds, so it must be passed explicitly.
_CHROME_FLAGS = [
    "--headless",
    "--no-sandbox",
    "--hide-scrollbars",
    "--enable-unsafe-swiftshader",
    "--use-gl=angle",
    "--use-angle=swiftshader",
    "--ignore-gpu-blocklist",
    "--force-color-profile=srgb",
]


class NotifyError(RuntimeError):
    """Raised when screenshot capture or Telegram delivery fails."""


def find_chrome() -> str:
    """Locate a Chromium/Chrome binary for headless screenshots.

    Resolution order: ``MILMAP_CHROME`` env override, the Playwright browser
    cache (headless shell preferred, then full Chrome), then common system
    binaries.
    """
    override = os.environ.get("MILMAP_CHROME")
    if override:
        if Path(override).is_file():
            return override
        raise NotifyError(f"MILMAP_CHROME points to a missing binary: {override}")

    cache = Path.home() / ".cache" / "ms-playwright"
    patterns = [
        str(cache / "chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell"),
        str(cache / "chromium-*/chrome-linux64/chrome"),
    ]
    for pattern in patterns:
        matches = sorted(glob.glob(pattern))
        if matches:
            return matches[-1]  # newest revision

    for name in ("chromium", "chromium-browser", "google-chrome", "chrome"):
        from shutil import which

        found = which(name)
        if found:
            return found

    raise NotifyError(
        "No Chromium/Chrome binary found. Set MILMAP_CHROME to a Chrome "
        "executable, or install Playwright browsers."
    )


def build_url(
    server: str = DEFAULT_SERVER,
    scenario: str | None = None,
    basemap: str | None = None,
    presentation: bool = False,
    show_legend: bool = True,
) -> str:
    """Build the workspace URL, optionally deep-linking a scenario/basemap."""
    base = server.rstrip("/") + "/"
    params = {}
    if scenario:
        params["scenario"] = scenario
    if basemap:
        params["basemap"] = basemap
    if presentation:
        params["presentation"] = "1"
    if not show_legend:
        params["legend"] = "0"
    if params:
        return base + "?" + urllib.parse.urlencode(params)
    return base


# Marker class so the dispatcher can fall back when Playwright is missing.
class _PlaywrightUnavailable(Exception):
    pass


# Chromium launch args that enable software WebGL so MapLibre's canvas renders.
_WEBGL_ARGS = [
    "--no-sandbox",
    "--enable-unsafe-swiftshader",
    "--use-gl=angle",
    "--use-angle=swiftshader",
    "--ignore-gpu-blocklist",
    "--force-color-profile=srgb",
]

# Condition the frontend exposes once a scenario has been drawn and the map is idle.
_READY_FN = "() => window.__milmap && window.__milmap.ready === true"


def capture_screenshot(
    url: str,
    out_path: str | os.PathLike[str],
    *,
    width: int = 1366,
    height: int = 900,
    wait_ms: int = 12000,
    timeout_s: int = 90,
) -> Path:
    """Render ``url`` to a PNG and return its path.

    Prefers Playwright (it can wait for the MapLibre render to settle before
    snapping). Falls back to a one-shot headless-Chromium screenshot when
    Playwright is not installed.
    """
    out = Path(out_path)
    if out.exists():
        out.unlink()
    try:
        return _capture_playwright(url, out, width=width, height=height, wait_ms=wait_ms)
    except _PlaywrightUnavailable:
        return _capture_cli(url, out, width=width, height=height, wait_ms=wait_ms, timeout_s=timeout_s)


def _capture_playwright(url: str, out: Path, *, width: int, height: int, wait_ms: int) -> Path:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # ImportError or driver issues
        raise _PlaywrightUnavailable(str(exc))

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, chromium_sandbox=False, args=_WEBGL_ARGS)
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(url, wait_until="load", timeout=max(wait_ms * 2, 30000))
            try:
                page.wait_for_function(_READY_FN, timeout=wait_ms)
            except Exception:
                # Render did not signal readiness (e.g. empty page); snap anyway.
                page.wait_for_timeout(2000)
            page.wait_for_timeout(600)  # let the final frame paint
            page.screenshot(path=str(out), type="png")
        finally:
            browser.close()

    if not out.is_file() or out.stat().st_size < 1024:
        raise NotifyError(f"Playwright did not produce a usable screenshot for {url}.")
    return out


def _capture_cli(
    url: str,
    out: Path,
    *,
    width: int,
    height: int,
    wait_ms: int,
    timeout_s: int,
) -> Path:
    """One-shot headless-Chromium screenshot (no render-settle wait)."""
    chrome = find_chrome()

    cmd = [
        chrome,
        *_CHROME_FLAGS,
        f"--window-size={width},{height}",
        f"--virtual-time-budget={wait_ms}",
        "--run-all-compositor-stages-before-draw",
        f"--screenshot={out}",
        url,
    ]
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout_s,
            text=True,
        )
    except subprocess.TimeoutExpired as exc:
        raise NotifyError(f"Screenshot timed out after {timeout_s}s for {url}") from exc

    if not out.is_file() or out.stat().st_size < 1024:
        tail = (proc.stdout or "").strip().splitlines()[-5:]
        raise NotifyError(
            "Headless Chromium did not produce a usable screenshot for "
            f"{url}.\n" + "\n".join(tail)
        )
    return out


def _encode_multipart(
    fields: dict[str, str],
    file_field: str,
    file_path: Path,
) -> tuple[bytes, str]:
    boundary = "----MILMAP" + uuid.uuid4().hex
    crlf = b"\r\n"
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(f"--{boundary}".encode())
        parts.append(f'Content-Disposition: form-data; name="{name}"'.encode())
        parts.append(b"")
        parts.append(str(value).encode())
    content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    parts.append(f"--{boundary}".encode())
    parts.append(
        f'Content-Disposition: form-data; name="{file_field}"; '
        f'filename="{file_path.name}"'.encode()
    )
    parts.append(f"Content-Type: {content_type}".encode())
    parts.append(b"")
    parts.append(file_path.read_bytes())
    body = crlf.join(parts) + crlf + f"--{boundary}--".encode() + crlf
    return body, boundary


def send_photo(
    photo_path: str | os.PathLike[str],
    caption: str | None = None,
    *,
    chat_id: str = TELEGRAM_CHAT_ID,
    bot_token: str = TELEGRAM_BOT_TOKEN,
    timeout_s: int = 60,
) -> dict:
    """Upload ``photo_path`` to the Telegram chat and return the API result."""
    path = Path(photo_path)
    if not path.is_file():
        raise NotifyError(f"Photo not found: {path}")

    fields = {"chat_id": str(chat_id)}
    if caption:
        fields["caption"] = caption
    body, boundary = _encode_multipart(fields, "photo", path)

    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    request = urllib.request.Request(url, data=body, method="POST")
    request.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            payload = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise NotifyError(f"Telegram sendPhoto failed ({exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise NotifyError(f"Telegram sendPhoto request failed: {exc.reason}") from exc

    if not payload.get("ok"):
        raise NotifyError(f"Telegram rejected the photo: {payload}")
    return payload["result"]


def notify_screenshot(
    *,
    server: str = DEFAULT_SERVER,
    scenario: str | None = None,
    basemap: str | None = None,
    presentation: bool = False,
    show_legend: bool = True,
    caption: str | None = None,
    out_path: str | os.PathLike[str] | None = None,
    width: int = 1366,
    height: int = 900,
    wait_ms: int = 12000,
) -> dict:
    """Capture the workspace (optionally a scenario) and send it to Telegram."""
    url = build_url(server, scenario, basemap, presentation=presentation, show_legend=show_legend)
    if out_path is None:
        suffix = f"-{scenario}" if scenario else ""
        out_path = Path(tempfile.gettempdir()) / f"milmap{suffix}.png"
    shot = capture_screenshot(url, out_path, width=width, height=height, wait_ms=wait_ms)
    result = send_photo(shot, caption)
    return {"url": url, "screenshot": str(shot), "telegram": result}


def _build_caption(args: argparse.Namespace) -> str | None:
    caption = args.caption
    if not caption and args.scenario:
        caption = f"MILMAP screenshot - {args.scenario} ({time.strftime('%Y-%m-%d %H:%M')})"
    if args.legend_text and args.scenario:
        legend = _legend_text_for_caption(args.scenario, max_entries=args.legend_max)
        if legend:
            caption = (caption or "") + "\n\nLegend:\n" + legend
    return caption or None


def _legend_text_for_caption(scenario_id: str, *, max_entries: int) -> str:
    try:
        record = ScenarioStore().get(scenario_id)
    except Exception:
        return ""
    payload = record.get("payload", {})
    return scenario_legend_text(payload, max_entries=max_entries)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Screenshot the MILMAP workspace and send it to Telegram.")
    parser.add_argument("--server", default=DEFAULT_SERVER, help="Base URL of the running workspace.")
    parser.add_argument("--scenario", help="Saved scenario id to deep-link (?scenario=<id>).")
    parser.add_argument("--basemap", help="Force a basemap id (?basemap=<id>), e.g. cartodb_dark.")
    parser.add_argument("--presentation", action="store_true", help="Hide side panels for a clean map screenshot.")
    parser.add_argument("--hide-legend", action="store_true", help="Hide the on-map legend in screenshots.")
    parser.add_argument("--legend-text", action="store_true", help="Append a text legend to the Telegram caption.")
    parser.add_argument("--legend-max", type=int, default=12, help="Maximum legend entries to append to caption.")
    parser.add_argument("--url", help="Explicit URL to screenshot (overrides --server/--scenario).")
    parser.add_argument("--caption", help="Telegram caption text.")
    parser.add_argument("--out", help="Where to write the PNG (default: temp dir).")
    parser.add_argument("--width", type=int, default=1366)
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument("--wait", type=int, default=12000, help="Virtual-time budget in ms for render.")
    parser.add_argument("--no-send", action="store_true", help="Capture only; skip Telegram delivery.")
    args = parser.parse_args(argv)

    url = args.url or build_url(
        args.server,
        args.scenario,
        args.basemap,
        presentation=args.presentation,
        show_legend=not args.hide_legend,
    )
    out = args.out or (
        Path(tempfile.gettempdir()) / f"milmap{('-' + args.scenario) if args.scenario else ''}.png"
    )
    try:
        shot = capture_screenshot(url, out, width=args.width, height=args.height, wait_ms=args.wait)
        print(f"captured {shot} ({shot.stat().st_size} bytes) from {url}")
        if args.no_send:
            return 0
        result = send_photo(shot, _build_caption(args))
        print(f"sent to Telegram chat {TELEGRAM_CHAT_ID} (message_id={result.get('message_id')})")
    except NotifyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
