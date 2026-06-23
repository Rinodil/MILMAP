from __future__ import annotations

import argparse
import base64
import hashlib
import json
import mimetypes
import os
import shutil
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from .legend import scenario_legend_text
from .store import ScenarioStore


DEFAULT_IMAGE_MODEL = "gpt-image-2"
DEFAULT_SIZE = "1536x1024"
DEFAULT_OUTPUT_FORMAT = "png"
DEFAULT_VISUAL_STYLE = "polished emergency-management briefing graphic"
DEFAULT_AUDIENCE = "government resilience, emergency management, and defense logistics stakeholders"
DEFAULT_DISCLAIMER = (
    "Generated illustration based on MILMAP scenario data; not operational imagery, "
    "not intelligence, and not a targeting product."
)
SAFETY_INSTRUCTION = (
    "Keep the image non-kinetic and planning-focused. Do not depict weapon targeting, "
    "target reticles, enemy locations, strike planning, weapon effects, or instructions "
    "for harming people. Treat all overlays as training and resilience visualization."
)


class VisualBriefingError(RuntimeError):
    """Raised when visual briefing packaging or image generation fails."""


def build_visual_briefing_package(
    record_or_payload: dict[str, Any],
    *,
    screenshot_path: str | os.PathLike[str] | None = None,
    reference_images: list[str | os.PathLike[str]] | None = None,
    brief_type: str = "scenario_overview",
    audience: str = DEFAULT_AUDIENCE,
    visual_style: str = DEFAULT_VISUAL_STYLE,
    model: str = DEFAULT_IMAGE_MODEL,
    size: str = DEFAULT_SIZE,
    quality: str = "high",
    output_format: str = DEFAULT_OUTPUT_FORMAT,
    disclaimer: str = DEFAULT_DISCLAIMER,
) -> dict[str, Any]:
    """Build an auditable OpenAI image-generation handoff package.

    The returned package is pure JSON-serializable metadata plus local reference
    image paths. It can be saved for manual ChatGPT upload or sent to the OpenAI
    Images API when an API key is available.
    """
    payload = _payload_from_record(record_or_payload)
    scenario_id = str(payload.get("scenario_id") or payload.get("scenario_name") or "scenario")
    scenario_name = str(payload.get("scenario_name") or scenario_id)
    image_inputs = _image_inputs(screenshot_path, reference_images or [])
    summary = _scenario_summary(payload)
    prompt = build_visual_prompt(
        payload,
        summary=summary,
        brief_type=brief_type,
        audience=audience,
        visual_style=visual_style,
        disclaimer=disclaimer,
    )
    api_mode = "image_edit_with_references" if image_inputs else "image_generation"
    package_id = f"{_slug(scenario_id)}-{int(time.time())}"
    return {
        "type": "VisualBriefingPackage",
        "package_id": package_id,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_scenario_id": scenario_id,
        "source_scenario_name": scenario_name,
        "classification": "simulated_training_visual",
        "disclaimer": disclaimer,
        "safety_instruction": SAFETY_INSTRUCTION,
        "brief_type": brief_type,
        "audience": audience,
        "visual_style": visual_style,
        "scenario_summary": summary,
        "image_inputs": image_inputs,
        "prompt": prompt,
        "openai": {
            "model": model,
            "api_mode": api_mode,
            "endpoint": "/v1/images/edits" if image_inputs else "/v1/images/generations",
            "size": size,
            "quality": quality,
            "output_format": output_format,
        },
        "chatgpt_handoff": {
            "instructions": [
                "Upload the listed reference image(s) to ChatGPT Images.",
                "Paste the prompt exactly as written.",
                "Keep generated output labeled as simulated training visualization.",
                "Use MILMAP scenario geometry and source metadata as the ground truth.",
            ],
        },
    }


def build_visual_prompt(
    payload: dict[str, Any],
    *,
    summary: dict[str, Any] | None = None,
    brief_type: str = "scenario_overview",
    audience: str = DEFAULT_AUDIENCE,
    visual_style: str = DEFAULT_VISUAL_STYLE,
    disclaimer: str = DEFAULT_DISCLAIMER,
) -> str:
    summary = summary or _scenario_summary(payload)
    layers = ", ".join(summary.get("layer_names", [])[:10]) or "none"
    objects = ", ".join(summary.get("object_names", [])[:10]) or "none"
    legend = summary.get("legend_text") or "none"
    qa = summary.get("qa_status") or "unknown"
    context = summary.get("map_context", {})
    center = context.get("center")
    bounds = context.get("bounds")
    return "\n".join(
        [
            f"Create a {visual_style} for {audience}.",
            "",
            f"Briefing type: {brief_type}.",
            f"Scenario: {summary.get('scenario_name')} ({summary.get('scenario_id')}).",
            f"QA status: {qa}; warnings: {summary.get('warning_count')}; errors: {summary.get('error_count')}.",
            f"Map center: {center}; bounds: {bounds}.",
            f"Layers to preserve visually: {layers}.",
            f"Objects to preserve visually: {objects}.",
            f"Text legend to preserve: {legend}",
            "",
            "Use the provided MILMAP screenshot/reference images as the geographic and visual source of truth.",
            "Preserve relative placement, map orientation, labels, and the distinction between hazards, corridors, service areas, and support nodes.",
            "Improve readability for a briefing audience with clean callouts, a concise title, and restrained professional styling.",
            "Do not invent new geographic facts, coordinates, units, agency names, or operational claims.",
            SAFETY_INSTRUCTION,
            f"Required disclaimer text: {disclaimer}",
        ]
    )


def save_visual_briefing_package(
    package: dict[str, Any],
    out_dir: str | os.PathLike[str],
    *,
    copy_images: bool = True,
) -> dict[str, Any]:
    """Write manifest, prompt, handoff notes, and optional reference copies."""
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    package = json.loads(json.dumps(package))

    if copy_images:
        ref_dir = root / "references"
        ref_dir.mkdir(exist_ok=True)
        copied_inputs = []
        for index, item in enumerate(package.get("image_inputs", []), start=1):
            source = Path(item["path"])
            suffix = source.suffix or ".png"
            dest = ref_dir / f"reference_{index}{suffix}"
            shutil.copy2(source, dest)
            copied = dict(item)
            copied["packaged_path"] = str(dest)
            copied_inputs.append(copied)
        package["image_inputs"] = copied_inputs

    manifest = root / "visual_briefing_manifest.json"
    prompt_file = root / "prompt.txt"
    handoff_file = root / "chatgpt_handoff.md"
    manifest.write_text(json.dumps(package, indent=2, sort_keys=True), encoding="utf-8")
    prompt_file.write_text(package["prompt"] + "\n", encoding="utf-8")
    handoff_file.write_text(_handoff_markdown(package), encoding="utf-8")

    return {
        "type": "VisualBriefingPackageFiles",
        "package_id": package["package_id"],
        "directory": str(root),
        "manifest": str(manifest),
        "prompt": str(prompt_file),
        "chatgpt_handoff": str(handoff_file),
        "reference_count": len(package.get("image_inputs", [])),
        "package": package,
    }


def generate_visual_briefing_image(
    package: dict[str, Any],
    *,
    out_path: str | os.PathLike[str],
    api_key: str | None = None,
    timeout_s: int = 180,
) -> dict[str, Any]:
    """Generate an image through the OpenAI Images API and write it to disk."""
    key = api_key or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise VisualBriefingError("OPENAI_API_KEY is required to generate a visual briefing image.")
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    config = package.get("openai", {})
    images = [Path(item.get("packaged_path") or item.get("path")) for item in package.get("image_inputs", [])]
    if images:
        response = _post_image_edit(package, images=images, api_key=key, timeout_s=timeout_s)
    else:
        response = _post_image_generation(package, api_key=key, timeout_s=timeout_s)
    image_data = _first_image_b64(response)
    out.write_bytes(base64.b64decode(image_data))
    return {
        "type": "VisualBriefingImage",
        "model": config.get("model", DEFAULT_IMAGE_MODEL),
        "path": str(out),
        "bytes": out.stat().st_size,
        "source_scenario_id": package.get("source_scenario_id"),
        "disclaimer": package.get("disclaimer"),
    }


def create_visual_briefing_for_scenario(
    scenario_id: str,
    *,
    store: ScenarioStore | None = None,
    screenshot_path: str | os.PathLike[str] | None = None,
    reference_images: list[str | os.PathLike[str]] | None = None,
    out_dir: str | os.PathLike[str] | None = None,
    generate: bool = False,
    generated_image_path: str | os.PathLike[str] | None = None,
    **options: Any,
) -> dict[str, Any]:
    store = store or ScenarioStore()
    record = store.get(scenario_id)
    package = build_visual_briefing_package(
        record,
        screenshot_path=screenshot_path,
        reference_images=reference_images,
        **options,
    )
    if out_dir is None:
        out_dir = Path.cwd() / ".milmap" / "visual_briefings" / package["package_id"]
    files = save_visual_briefing_package(package, out_dir)
    result: dict[str, Any] = {
        "type": "VisualBriefing",
        "scenario_id": scenario_id,
        "package": files,
    }
    if generate:
        generated = generate_visual_briefing_image(
            files["package"],
            out_path=generated_image_path or (Path(files["directory"]) / "generated_briefing.png"),
        )
        result["generated_image"] = generated
    return result


def _payload_from_record(value: dict[str, Any]) -> dict[str, Any]:
    if isinstance(value.get("payload"), dict):
        return value["payload"]
    return value


def _scenario_summary(payload: dict[str, Any]) -> dict[str, Any]:
    layers = [item for item in payload.get("layers", []) if isinstance(item, dict)]
    objects = [item for item in payload.get("objects", []) if isinstance(item, dict)]
    qa = payload.get("qa") if isinstance(payload.get("qa"), dict) else {}
    qa_summary = qa.get("summary", {}) if isinstance(qa.get("summary"), dict) else {}
    map_context = payload.get("map_context") if isinstance(payload.get("map_context"), dict) else {}
    return {
        "scenario_id": payload.get("scenario_id"),
        "scenario_name": payload.get("scenario_name"),
        "layer_count": len(layers),
        "object_count": len(objects),
        "feature_count": qa_summary.get("feature_count", _feature_count(payload.get("geojson"))),
        "qa_status": qa.get("status"),
        "warning_count": qa_summary.get("warning_count", 0),
        "error_count": qa_summary.get("error_count", 0),
        "layer_names": [str(item.get("name") or item.get("id") or item.get("type")) for item in layers],
        "object_names": [str(item.get("name") or item.get("id") or item.get("type")) for item in objects],
        "legend_text": scenario_legend_text(payload),
        "map_context": {
            "mode": map_context.get("mode"),
            "purpose": map_context.get("purpose"),
            "center": map_context.get("center"),
            "bounds": map_context.get("bounds"),
            "basemap": map_context.get("basemap"),
        },
    }


def _feature_count(geojson: Any) -> int:
    if not isinstance(geojson, dict):
        return 0
    if geojson.get("type") == "FeatureCollection" and isinstance(geojson.get("features"), list):
        return len(geojson["features"])
    if geojson.get("type") == "Feature":
        return 1
    return 0


def _image_inputs(
    screenshot_path: str | os.PathLike[str] | None,
    reference_images: list[str | os.PathLike[str]],
) -> list[dict[str, Any]]:
    paths: list[tuple[str, str | os.PathLike[str]]] = []
    if screenshot_path:
        paths.append(("milmap_screenshot", screenshot_path))
    paths.extend((f"reference_image_{index}", path) for index, path in enumerate(reference_images, start=1))
    inputs = []
    for role, raw_path in paths:
        path = Path(raw_path)
        if not path.is_file():
            raise VisualBriefingError(f"Reference image not found: {path}")
        inputs.append(
            {
                "role": role,
                "path": str(path),
                "filename": path.name,
                "mime_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                "sha256": _sha256(path),
                "bytes": path.stat().st_size,
            }
        )
    return inputs


def _post_image_generation(package: dict[str, Any], *, api_key: str, timeout_s: int) -> dict[str, Any]:
    config = package.get("openai", {})
    payload = {
        "model": config.get("model", DEFAULT_IMAGE_MODEL),
        "prompt": package["prompt"],
        "size": config.get("size", DEFAULT_SIZE),
        "quality": config.get("quality", "high"),
        "output_format": config.get("output_format", DEFAULT_OUTPUT_FORMAT),
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/images/generations",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
    )
    request.add_header("Authorization", f"Bearer {api_key}")
    request.add_header("Content-Type", "application/json")
    return _openai_json(request, timeout_s=timeout_s)


def _post_image_edit(
    package: dict[str, Any],
    *,
    images: list[Path],
    api_key: str,
    timeout_s: int,
) -> dict[str, Any]:
    config = package.get("openai", {})
    fields = {
        "model": str(config.get("model", DEFAULT_IMAGE_MODEL)),
        "prompt": package["prompt"],
        "size": str(config.get("size", DEFAULT_SIZE)),
        "quality": str(config.get("quality", "high")),
        "output_format": str(config.get("output_format", DEFAULT_OUTPUT_FORMAT)),
    }
    body, boundary = _encode_multipart(fields, images)
    request = urllib.request.Request("https://api.openai.com/v1/images/edits", data=body, method="POST")
    request.add_header("Authorization", f"Bearer {api_key}")
    request.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    return _openai_json(request, timeout_s=timeout_s)


def _openai_json(request: urllib.request.Request, *, timeout_s: int) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise VisualBriefingError(f"OpenAI image request failed ({exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise VisualBriefingError(f"OpenAI image request failed: {exc.reason}") from exc


def _first_image_b64(response: dict[str, Any]) -> str:
    data = response.get("data")
    if not isinstance(data, list) or not data:
        raise VisualBriefingError("OpenAI image response did not include image data.")
    item = data[0]
    if not isinstance(item, dict) or not item.get("b64_json"):
        raise VisualBriefingError("OpenAI image response did not include b64_json output.")
    return str(item["b64_json"])


def _encode_multipart(fields: dict[str, str], images: list[Path]) -> tuple[bytes, str]:
    boundary = "----MILMAPVisual" + uuid.uuid4().hex
    crlf = b"\r\n"
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(f"--{boundary}".encode())
        parts.append(f'Content-Disposition: form-data; name="{name}"'.encode())
        parts.append(b"")
        parts.append(str(value).encode())
    for image in images:
        if not image.is_file():
            raise VisualBriefingError(f"Reference image not found: {image}")
        content_type = mimetypes.guess_type(image.name)[0] or "application/octet-stream"
        parts.append(f"--{boundary}".encode())
        parts.append(f'Content-Disposition: form-data; name="image[]"; filename="{image.name}"'.encode())
        parts.append(f"Content-Type: {content_type}".encode())
        parts.append(b"")
        parts.append(image.read_bytes())
    body = crlf.join(parts) + crlf + f"--{boundary}--".encode() + crlf
    return body, boundary


def _handoff_markdown(package: dict[str, Any]) -> str:
    references = "\n".join(
        f"- `{item.get('packaged_path') or item.get('path')}` ({item.get('role')}, {item.get('bytes')} bytes)"
        for item in package.get("image_inputs", [])
    )
    if not references:
        references = "- No image references packaged; use the prompt as a text-to-image request."
    return f"""# MILMAP Visual Briefing Handoff

Scenario: `{package.get('source_scenario_id')}`
Model target: `{package.get('openai', {}).get('model')}`
Classification: `{package.get('classification')}`

## References

{references}

## Prompt

```text
{package.get('prompt')}
```

## Required Disclaimer

{package.get('disclaimer')}
"""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _slug(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_") or "scenario"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a MILMAP visual briefing package for ChatGPT/OpenAI Images.")
    parser.add_argument("--scenario", required=True, help="Saved scenario id.")
    parser.add_argument("--store", help="Path to scenario store JSON.")
    parser.add_argument("--screenshot", help="MILMAP screenshot/reference image path.")
    parser.add_argument("--reference", action="append", default=[], help="Additional reference image path. Repeatable.")
    parser.add_argument("--out-dir", help="Output directory for package files.")
    parser.add_argument("--brief-type", default="scenario_overview")
    parser.add_argument("--audience", default=DEFAULT_AUDIENCE)
    parser.add_argument("--visual-style", default=DEFAULT_VISUAL_STYLE)
    parser.add_argument("--model", default=DEFAULT_IMAGE_MODEL)
    parser.add_argument("--size", default=DEFAULT_SIZE)
    parser.add_argument("--quality", default="high")
    parser.add_argument("--output-format", default=DEFAULT_OUTPUT_FORMAT)
    parser.add_argument("--generate", action="store_true", help="Call OpenAI Images API and write generated_briefing.png.")
    args = parser.parse_args(argv)

    store = ScenarioStore(Path(args.store)) if args.store else ScenarioStore()
    result = create_visual_briefing_for_scenario(
        args.scenario,
        store=store,
        screenshot_path=args.screenshot,
        reference_images=args.reference,
        out_dir=args.out_dir,
        brief_type=args.brief_type,
        audience=args.audience,
        visual_style=args.visual_style,
        model=args.model,
        size=args.size,
        quality=args.quality,
        output_format=args.output_format,
        generate=args.generate,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
