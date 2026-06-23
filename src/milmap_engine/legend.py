from __future__ import annotations

from typing import Any


COLOR_NAMES = {
    "#2563eb": "blue",
    "#1d4ed8": "blue",
    "#7c3aed": "purple",
    "#38bdf8": "light blue",
    "#0284c7": "blue",
    "#f97316": "orange",
    "#c2410c": "orange",
    "#64748b": "slate",
    "#334155": "slate",
    "#0ea5e9": "sky blue",
    "#0369a1": "blue",
    "#22c55e": "green",
    "#15803d": "green",
    "#16a34a": "green",
    "#475569": "slate",
    "#94a3b8": "gray",
}


def scenario_legend_entries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for layer in payload.get("layers", []):
        if isinstance(layer, dict):
            entries.append(_entry(layer, "layer", _geometry_type(layer.get("geojson"))))
    for obj in payload.get("objects", []):
        if isinstance(obj, dict):
            geometry = obj.get("geometry") if isinstance(obj.get("geometry"), dict) else {}
            entries.append(_entry(obj, "object", str(geometry.get("type") or "Point")))
    return entries


def scenario_legend_text(payload: dict[str, Any], *, max_entries: int | None = None) -> str:
    entries = scenario_legend_entries(payload)
    if max_entries is not None:
        entries = entries[:max_entries]
    return "\n".join(_entry_text(entry) for entry in entries)


def _entry(item: dict[str, Any], kind: str, geometry_type: str) -> dict[str, Any]:
    style = item.get("style") if isinstance(item.get("style"), dict) else {}
    swatch = _swatch(style, geometry_type)
    return {
        "id": item.get("id"),
        "name": item.get("name") or item.get("id") or item.get("type"),
        "kind": kind,
        "type": item.get("type"),
        "geometry_type": geometry_type,
        "symbol": swatch["symbol"],
        "color": swatch["color"],
        "color_name": _color_name(swatch["color"]),
    }


def _entry_text(entry: dict[str, Any]) -> str:
    return f"{entry['color_name']} {entry['symbol']}: {entry['name']} ({entry['kind']} / {entry.get('type')})"


def _geometry_type(geojson: Any) -> str:
    if not isinstance(geojson, dict):
        return ""
    if geojson.get("type") == "Feature":
        geometry = geojson.get("geometry")
        return str(geometry.get("type") if isinstance(geometry, dict) else "")
    if geojson.get("type") == "FeatureCollection":
        for feature in geojson.get("features", []):
            if isinstance(feature, dict):
                geometry = feature.get("geometry")
                if isinstance(geometry, dict) and geometry.get("type"):
                    return str(geometry["type"])
    return str(geojson.get("type") or "")


def _swatch(style: dict[str, Any], geometry_type: str) -> dict[str, str]:
    normalized = geometry_type.lower()
    if "point" in normalized:
        return {"symbol": "point", "color": _clean_color(style.get("marker_color") or style.get("stroke_color") or "#2563eb")}
    if "line" in normalized:
        return {"symbol": "line", "color": _clean_color(style.get("stroke_color") or style.get("marker_color") or "#334155")}
    return {"symbol": "area", "color": _clean_color(style.get("fill_color") or style.get("marker_color") or style.get("stroke_color") or "#94a3b8")}


def _clean_color(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text.startswith("#") and len(text) in {4, 7}:
        return text
    return "#94a3b8"


def _color_name(color: str) -> str:
    if color in COLOR_NAMES:
        return COLOR_NAMES[color]
    return color
