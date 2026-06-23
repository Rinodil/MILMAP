const DEFAULT_PLAN = {
  scenario_name: "training_setup",
  map_context: {
    mode: "simulation",
    center: [-82.324, 27.845],
    zoom: 11
  },
  objects: [
    {
      type: "base",
      name: "Base Alpha",
      placement: {
        mode: "point",
        coordinate: [-82.324, 27.845]
      },
      properties: {
        role: "logistics",
        status: "active"
      }
    },
    {
      type: "checkpoint",
      name: "Checkpoint North",
      placement: {
        mode: "point",
        coordinate: [-82.342, 27.879]
      },
      properties: {
        status: "planned"
      }
    }
  ],
  layers: [
    {
      type: "perimeter",
      name: "Base Alpha Perimeter",
      operation: "buffer",
      parameters: {
        center: [-82.324, 27.845],
        radius_km: 5,
        steps: 48
      }
    },
    {
      type: "observation_zone",
      name: "Observation Sector East",
      operation: "sector",
      parameters: {
        center: [-82.324, 27.845],
        radius_m: 4200,
        start_bearing: 40,
        end_bearing: 120,
        steps: 24
      }
    },
    {
      type: "corridor",
      name: "Supply Route",
      operation: "corridor",
      parameters: {
        coordinates: [
          [-82.42, 27.91],
          [-82.35, 27.88],
          [-82.3, 27.83]
        ],
        width_m: 750
      }
    },
    {
      type: "hex_grid",
      name: "Search Grid",
      parameters: {
        bounds: [-82.5, 27.7, -82.1, 28.0],
        radius_m: 2000,
        max_features: 500
      }
    }
  ]
};

let map;
let activeScenario = null;
let renderedLayerIds = [];
let renderedSourceIds = [];
let layerRegistry = new Map();

// Render-complete signal for headless screenshot tooling (see milmap_engine.notify).
// Flipped to true once the map goes idle after a scenario is drawn.
window.__milmap = { ready: false, scenarioId: null };

// Basemap config. The server (/basemaps) is the source of truth; this minimal
// fallback keeps the map usable if that request fails.
// Protomaps font glyphs cover the labels used by both the vector basemap and
// the scenario overlays (Noto Sans Regular).
const PROTOMAPS_ASSET_BASE = `${window.location.origin}/static/basemaps/protomaps`;
const GLYPHS_URL = `${PROTOMAPS_ASSET_BASE}/fonts/{fontstack}/{range}.pbf`;
const DEFAULT_SPRITE_URL = `${PROTOMAPS_ASSET_BASE}/sprites/v4/light`;
const LABEL_FONT = ["Noto Sans Regular"];
const FALLBACK_BASEMAPS = {
  osm: {
    id: "osm",
    label: "OpenStreetMap",
    purpose: "Standard street reference",
    tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
    tile_size: 256,
    min_zoom: 0,
    max_zoom: 19,
    attribution: "© OpenStreetMap contributors",
    keywords: ["standard", "reference", "osm", "default"]
  }
};
let basemapState = { default: "osm", order: ["osm"], basemaps: FALLBACK_BASEMAPS };
let activeBasemapId = null;
let activeBasemapDark = false;
let basemapLayerIds = [];
let basemapSourceIds = [];
const vectorStyleCache = {};

const els = {};

document.addEventListener("DOMContentLoaded", () => {
  cacheElements();
  applyUrlModes();
  hydrateIcons();
  els.scenarioInput.value = JSON.stringify(DEFAULT_PLAN, null, 2);
  bindActions();
  loadBasemapConfig();
  initMap();
  loadSavedScenarios();
});

function applyUrlModes() {
  const params = new URLSearchParams(window.location.search);
  if (params.get("presentation") === "1" || params.get("clean") === "1") {
    document.body.classList.add("presentation-mode");
  }
  if (params.get("legend") === "0") {
    document.body.classList.add("hide-map-legend");
  }
}

function cacheElements() {
  for (const id of [
    "scenarioMeta",
    "reloadSaved",
    "newScenario",
    "savedList",
    "scenarioInput",
    "executeScenario",
    "saveScenario",
    "importGeojson",
    "exportGeojson",
    "geojsonFile",
    "statusBar",
    "mapLegend",
    "legendCount",
    "legendItems",
    "layerList",
    "objectList",
    "layerCount",
    "objectCount",
    "qaStatus",
    "qaReport",
    "inspectorOutput",
    "basemapBadge"
  ]) {
    els[id] = document.getElementById(id);
  }
}

function hydrateIcons() {
  if (window.lucide) {
    window.lucide.createIcons();
  }
}

function bindActions() {
  els.executeScenario.addEventListener("click", executeScenario);
  els.saveScenario.addEventListener("click", saveScenario);
  els.reloadSaved.addEventListener("click", loadSavedScenarios);
  els.newScenario.addEventListener("click", () => {
    els.scenarioInput.value = JSON.stringify(DEFAULT_PLAN, null, 2);
    executeScenario();
  });
  els.exportGeojson.addEventListener("click", exportGeojson);
  els.importGeojson.addEventListener("click", () => els.geojsonFile.click());
  els.geojsonFile.addEventListener("change", importGeojson);
}

function initMap() {
  if (!window.maplibregl) {
    setStatus("MapLibre is unavailable");
    return;
  }

  map = new maplibregl.Map({
    container: "map",
    // Start from a bare style; the basemap raster source is chosen per scenario
    // purpose by applyBasemap(). Glyphs are needed for object labels.
    style: {
      version: 8,
      glyphs: GLYPHS_URL,
      // Default sprite (Protomaps light); vector flavors swap it via setSprite.
      sprite: DEFAULT_SPRITE_URL,
      sources: {},
      layers: []
    },
    center: DEFAULT_PLAN.map_context.center,
    zoom: DEFAULT_PLAN.map_context.zoom
  });

  map.addControl(new maplibregl.NavigationControl({ showCompass: true }), "top-right");

  map.on("load", () => {
    const deepLink = new URLSearchParams(window.location.search).get("scenario");
    if (deepLink) {
      loadScenario(deepLink);
    } else {
      executeScenario();
    }
  });

  map.on("click", (event) => {
    const features = renderedLayerIds.length
      ? map.queryRenderedFeatures(event.point, { layers: renderedLayerIds })
      : [];
    if (!features.length) {
      return;
    }
    const feature = features[0];
    inspect(feature.properties || {});
    new maplibregl.Popup({ closeButton: false })
      .setLngLat(event.lngLat)
      .setHTML(popupHtml(feature.properties || {}))
      .addTo(map);
  });
}

async function loadBasemapConfig() {
  try {
    const config = await fetchJson("/basemaps");
    if (config && config.basemaps && Object.keys(config.basemaps).length) {
      basemapState = {
        default: config.default || "osm",
        order: config.order || Object.keys(config.basemaps),
        basemaps: config.basemaps
      };
      if (map && map.loaded() && activeScenario) {
        applyBasemap(selectBasemapId(activeScenario.map_context));
      }
    }
  } catch (_error) {
    // Keep the fallback basemap; the map stays usable.
  }
}

// Auto-pick a basemap from the scenario's map_context: an explicit `basemap`
// id wins, otherwise the first registry keyword found in the purpose/mode text.
function selectBasemapId(mapContext) {
  const ctx = mapContext || {};
  if (ctx.basemap && basemapState.basemaps[ctx.basemap]) {
    return ctx.basemap;
  }
  const haystack = [ctx.purpose, ctx.mode, ctx.basemap_purpose, ctx.scenario_type]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  for (const id of basemapState.order) {
    const cfg = basemapState.basemaps[id];
    if (cfg && (cfg.keywords || []).some((kw) => haystack.includes(String(kw).toLowerCase()))) {
      return id;
    }
  }
  return basemapState.default;
}

function removeBasemap() {
  for (const id of [...basemapLayerIds].reverse()) {
    if (map.getLayer(id)) {
      map.removeLayer(id);
    }
  }
  for (const id of [...basemapSourceIds].reverse()) {
    if (map.getSource(id)) {
      map.removeSource(id);
    }
  }
  basemapLayerIds = [];
  basemapSourceIds = [];
}

// Insert basemap layers beneath the scenario overlays so overlays stay on top.
function firstOverlayLayerId() {
  return renderedLayerIds.length ? renderedLayerIds[0] : undefined;
}

async function applyBasemap(id) {
  if (!map) {
    return;
  }
  const cfg = basemapState.basemaps[id] || basemapState.basemaps[basemapState.default];
  if (!cfg) {
    return;
  }
  removeBasemap();
  const beforeId = firstOverlayLayerId();
  try {
    if (cfg.type === "vector") {
      await addVectorBasemap(cfg, beforeId);
    } else {
      addRasterBasemap(cfg, beforeId);
    }
    activeBasemapId = id;
    activeBasemapDark = Boolean(cfg.dark);
    updateOverlayContrast();
    updateBasemapBadge(cfg);
  } catch (error) {
    console.error("Basemap apply failed", error);
  }
}

// MapLibre resolves tile URLs in a worker with no document base, so root-relative
// URLs must be made absolute against the page origin (keeping {z}/{x}/{y} intact).
function absoluteUrl(url) {
  return typeof url === "string" && url.startsWith("/") ? window.location.origin + url : url;
}

function absoluteTileUrls(tiles) {
  return (tiles || []).map((tile) => absoluteUrl(tile));
}

function addRasterBasemap(cfg, beforeId) {
  // Prefer locally-served offline tiles when available, else the online source.
  const tiles = absoluteTileUrls(cfg.local && cfg.local_tiles ? [cfg.local_tiles] : cfg.tiles);
  if (!tiles || !tiles.length) {
    return;
  }
  map.addSource("basemap", {
    type: "raster",
    tiles,
    tileSize: cfg.tile_size || 256,
    minzoom: cfg.min_zoom || 0,
    maxzoom: cfg.max_zoom || 19,
    attribution: cfg.attribution || ""
  });
  basemapSourceIds.push("basemap");
  map.addLayer({ id: "basemap", type: "raster", source: "basemap" }, beforeId);
  basemapLayerIds.push("basemap");
}

// Self-hosted Protomaps vector basemap: a vector source plus the theme's layer
// stack, fetched once from the server-rewritten flavor style.
async function addVectorBasemap(cfg, beforeId) {
  let style = vectorStyleCache[cfg.id];
  if (!style) {
    style = await fetchJson(cfg.style_url);
    vectorStyleCache[cfg.id] = style;
  }
  const rawSource = style.sources && style.sources.protomaps;
  if (!rawSource) {
    return;
  }
  const source = rawSource.tiles
    ? { ...rawSource, tiles: absoluteTileUrls(rawSource.tiles) }
    : rawSource;
  // Match the sprite to the flavor when MapLibre supports per-style sprites.
  if (cfg.sprite && typeof map.setSprite === "function") {
    try {
      map.setSprite(absoluteUrl(cfg.sprite));
    } catch (_error) {
      // Fall back to the default sprite set on the base style.
    }
  }
  if (!map.getSource("protomaps")) {
    map.addSource("protomaps", source);
  }
  basemapSourceIds.push("protomaps");
  for (const layer of style.layers || []) {
    if (map.getLayer(layer.id)) {
      map.removeLayer(layer.id);
    }
    map.addLayer(layer, beforeId);
    basemapLayerIds.push(layer.id);
  }
}

// Optional `?basemap=<id>` URL override, for previewing/screenshotting a
// scenario under a specific purpose's basemap. Not a UI control.
function urlBasemapOverride() {
  const id = new URLSearchParams(window.location.search).get("basemap");
  return id && basemapState.basemaps[id] ? id : null;
}

function updateBasemapBadge(cfg) {
  if (!els.basemapBadge) {
    return;
  }
  els.basemapBadge.textContent = `${cfg.label} · ${cfg.purpose}${cfg.local ? " (offline)" : ""}`;
  els.basemapBadge.title = cfg.attribution || "";
}

async function executeScenario() {
  try {
    const plan = parseScenarioPlan();
    const buildMode = isBuildPlan(plan);
    setStatus(buildMode ? "Building scenario" : "Executing scenario");
    const result = await postJson(buildMode ? "/scenario/build" : "/scenario/execute", plan);
    const payload = result.payload || result;
    setScenario(payload);
    await loadScenarioQaIfSaved(payload);
    setStatus(`${buildMode ? "Built" : "Executed"} ${payload.scenario_name}`);
  } catch (error) {
    showError(error);
  }
}

async function saveScenario() {
  try {
    const plan = parseScenarioPlan();
    if (isBuildPlan(plan)) {
      setStatus("Building scenario");
      const result = await postJson("/scenario/build", plan);
      setScenario(result.payload);
      await loadSavedScenarios();
      setStatus(`Built ${result.scenario_name}`);
      return;
    }
    setStatus("Saving scenario");
    const record = await postJson("/scenario", plan);
    els.scenarioInput.value = JSON.stringify(record.plan, null, 2);
    setScenario(record.payload);
    await loadScenarioQa(record.id);
    await loadSavedScenarios();
    setStatus(`Saved ${record.scenario_name} v${record.version}`);
  } catch (error) {
    showError(error);
  }
}

async function loadSavedScenarios() {
  try {
    const records = await fetchJson("/scenario");
    renderSavedList(records);
  } catch (error) {
    renderSavedList([]);
    setStatus(error.message);
  }
}

async function loadScenario(id) {
  try {
    setStatus("Loading scenario");
    const record = await fetchJson(`/scenario/${encodeURIComponent(id)}`);
    els.scenarioInput.value = JSON.stringify(record.plan, null, 2);
    setScenario(record.payload);
    await loadScenarioQa(record.id);
    setStatus(`Loaded ${record.scenario_name} v${record.version}`);
  } catch (error) {
    showError(error);
  }
}

function parseScenarioPlan() {
  const value = JSON.parse(els.scenarioInput.value);
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Scenario JSON must be an object");
  }
  return value;
}

function isBuildPlan(value) {
  return Boolean(value && typeof value === "object" && (Array.isArray(value.phases) || value.brief));
}

function setScenario(scenario) {
  activeScenario = scenario;
  els.scenarioMeta.textContent = `${scenario.scenario_name} - ${featureCount(scenario.geojson)} features`;
  renderMapScenario(scenario);
  renderLayerPanel(scenario.layers || []);
  renderObjectPanel(scenario.objects || []);
  renderLegend(scenario.layers || [], scenario.objects || []);
  renderQaPanel(scenario.qa || null);
  inspect({
    scenario_id: scenario.scenario_id,
    scenario_name: scenario.scenario_name,
    map_context: scenario.map_context,
    layers: (scenario.layers || []).length,
    objects: (scenario.objects || []).length,
    features: featureCount(scenario.geojson)
  });
}

async function loadScenarioQaIfSaved(scenario) {
  if (scenario && scenario.qa) {
    return;
  }
  if (scenario && scenario.scenario_id && activeScenario === scenario) {
    await loadScenarioQa(scenario.scenario_id);
  }
}

async function loadScenarioQa(id) {
  try {
    const qa = await fetchJson(`/scenario/${encodeURIComponent(id)}/qa`);
    if (activeScenario && activeScenario.scenario_id === id) {
      activeScenario.qa = qa;
      renderQaPanel(qa);
    }
  } catch (_error) {
    renderQaPanel(activeScenario && activeScenario.qa ? activeScenario.qa : null);
  }
}

async function renderMapScenario(scenario) {
  if (!map || !map.loaded()) {
    return;
  }

  window.__milmap.ready = false;

  removeRenderedLayers();

  const basemapId = urlBasemapOverride() || selectBasemapId(scenario.map_context);
  const basemapCfg = basemapState.basemaps[basemapId] || basemapState.basemaps[basemapState.default];
  activeBasemapDark = Boolean(basemapCfg && basemapCfg.dark);
  const queuedLayers = [];

  for (const layer of scenario.layers || []) {
    queuedLayers.push(
      ...addGeojsonLayer(`scenario-layer-${layer.id}`, layer.name, layer.geojson, layer.style || {}, layer.visible !== false)
    );
  }

  for (const object of scenario.objects || []) {
    const geojson = {
      type: "Feature",
      id: object.id,
      properties: {
        name: object.name,
        object_id: object.id,
        object_type: object.type,
        style: object.style || {}
      },
      geometry: object.geometry
    };
    queuedLayers.push(
      ...addGeojsonLayer(`scenario-object-${object.id}`, object.name, geojson, object.style || {}, object.visible !== false)
    );
  }

  for (const band of ["fill", "casing", "line", "circle", "symbol"]) {
    for (const item of queuedLayers) {
      if (item.band === band) {
        addMapLayer(item.definition, item.rendered, item.type);
      }
    }
  }

  // Basemap is added beneath the overlays, after them, so overlays stay on top.
  await applyBasemap(basemapId);

  fitScenario(scenario);

  map.once("idle", () => {
    window.__milmap.ready = true;
    window.__milmap.scenarioId = scenario.scenario_id || null;
  });
}

function addGeojsonLayer(baseId, name, geojson, style, visible) {
  const sourceId = `${baseId}-source`;
  const visibility = visible ? "visible" : "none";
  const lineColor = style.stroke_color || style.marker_color || "#334155";
  const fillColor = style.fill_color || style.marker_color || "#94a3b8";
  const markerColor = style.marker_color || style.stroke_color || "#2563eb";
  const fillOpacity = numeric(style.fill_opacity, 0.14);
  const lineWidth = numeric(style.stroke_width, 2);
  const markerSize = numeric(style.marker_size, 10);
  const rendered = [];
  const queued = [];

  map.addSource(sourceId, {
    type: "geojson",
    data: geojson
  });
  renderedSourceIds.push(sourceId);

  queueMapLayer(queued, rendered, "fill", "fill", {
    id: `${baseId}-fill`,
    source: sourceId,
    type: "fill",
    filter: ["==", ["geometry-type"], "Polygon"],
    layout: { visibility },
    paint: {
      "fill-color": fillColor,
      "fill-opacity": fillOpacity
    }
  });

  queueMapLayer(queued, rendered, "casing", "line-casing", {
    id: `${baseId}-outline-casing`,
    source: sourceId,
    type: "line",
    filter: ["==", ["geometry-type"], "Polygon"],
    layout: { visibility },
    paint: {
      "line-color": "#f8fafc",
      "line-width": lineWidth + 4,
      "line-opacity": lineCasingOpacity(fillOpacity),
      "line-blur": 0.4
    }
  });

  queueMapLayer(queued, rendered, "line", "line", {
    id: `${baseId}-outline`,
    source: sourceId,
    type: "line",
    filter: ["==", ["geometry-type"], "Polygon"],
    layout: { visibility },
    paint: {
      "line-color": lineColor,
      "line-width": lineWidth,
      "line-opacity": Math.max(fillOpacity, 0.45)
    }
  });

  queueMapLayer(queued, rendered, "casing", "line-casing", {
    id: `${baseId}-line-casing`,
    source: sourceId,
    type: "line",
    filter: ["in", ["geometry-type"], ["literal", ["LineString", "MultiLineString"]]],
    layout: { visibility },
    paint: {
      "line-color": "#f8fafc",
      "line-width": lineWidth + 4,
      "line-opacity": lineCasingOpacity(fillOpacity),
      "line-blur": 0.4
    }
  });

  queueMapLayer(queued, rendered, "line", "line", {
    id: `${baseId}-line`,
    source: sourceId,
    type: "line",
    filter: ["in", ["geometry-type"], ["literal", ["LineString", "MultiLineString"]]],
    layout: { visibility },
    paint: {
      "line-color": lineColor,
      "line-width": lineWidth,
      "line-opacity": Math.max(fillOpacity, 0.72)
    }
  });

  queueMapLayer(queued, rendered, "circle", "circle", {
    id: `${baseId}-point`,
    source: sourceId,
    type: "circle",
    filter: ["in", ["geometry-type"], ["literal", ["Point", "MultiPoint"]]],
    layout: { visibility },
    paint: {
      "circle-color": markerColor,
      "circle-radius": Math.max(5, markerSize / 2),
      "circle-stroke-color": "#ffffff",
      "circle-stroke-width": 2,
      "circle-opacity": visible ? 0.95 : 0
    }
  });

  queueMapLayer(queued, rendered, "symbol", "symbol", {
    id: `${baseId}-label`,
    source: sourceId,
    type: "symbol",
    filter: ["all", ["has", "name"], ["in", ["geometry-type"], ["literal", ["Point", "MultiPoint"]]]],
    layout: {
      visibility,
      "text-field": ["get", "name"],
      "text-font": LABEL_FONT,
      "text-size": 12,
      "text-offset": [0, 1.1],
      "text-anchor": "top"
    },
    paint: {
      "text-color": style.text_color || "#111827",
      "text-halo-color": "#ffffff",
      "text-halo-width": 1.5
    }
  });

  layerRegistry.set(baseId, {
    sourceId,
    name,
    style,
    visible,
    rendered
  });

  return queued;
}

function queueMapLayer(queued, rendered, band, type, definition) {
  queued.push({ band, type, definition, rendered });
}

function addMapLayer(definition, rendered, paintType) {
  map.addLayer(definition);
  rendered.push({ id: definition.id, type: paintType });
  renderedLayerIds.push(definition.id);
}

function lineCasingOpacity(layerOpacity) {
  if (!activeBasemapDark) {
    return 0;
  }
  return Math.min(0.72, Math.max(layerOpacity, 0.52));
}

function updateOverlayContrast() {
  for (const entry of layerRegistry.values()) {
    const baseOpacity = numeric(entry.style.fill_opacity, 0.14);
    for (const layer of entry.rendered) {
      if (layer.type === "line-casing" && map.getLayer(layer.id)) {
        map.setPaintProperty(layer.id, "line-opacity", lineCasingOpacity(baseOpacity));
      }
    }
  }
}

function removeRenderedLayers() {
  for (const id of [...renderedLayerIds].reverse()) {
    if (map.getLayer(id)) {
      map.removeLayer(id);
    }
  }
  for (const id of [...renderedSourceIds].reverse()) {
    if (map.getSource(id)) {
      map.removeSource(id);
    }
  }
  renderedLayerIds = [];
  renderedSourceIds = [];
  layerRegistry = new Map();
}

function renderSavedList(records) {
  els.savedList.innerHTML = "";
  if (!records.length) {
    els.savedList.append(emptyState("No saved scenarios"));
    return;
  }

  for (const record of records) {
    const item = document.createElement("div");
    item.className = "saved-item";
    const body = document.createElement("div");
    const title = document.createElement("div");
    title.className = "saved-title";
    title.textContent = record.scenario_name;
    const meta = document.createElement("div");
    meta.className = "saved-meta";
    meta.textContent = `${record.layer_count} layers, ${record.object_count} objects, v${record.version}`;
    body.append(title, meta);

    const button = document.createElement("button");
    button.className = "load-button";
    button.type = "button";
    button.title = "Load scenario";
    button.innerHTML = '<i data-lucide="folder-open"></i>';
    button.addEventListener("click", () => loadScenario(record.id));
    item.append(body, button);
    els.savedList.append(item);
  }
  hydrateIcons();
}

function renderLayerPanel(layers) {
  els.layerList.innerHTML = "";
  els.layerCount.textContent = String(layers.length);
  if (!layers.length) {
    els.layerList.append(emptyState("No layers"));
    return;
  }

  for (const layer of layers) {
    const baseId = `scenario-layer-${layer.id}`;
    const item = document.createElement("div");
    item.className = "layer-item";
    item.append(layerHeader(layer, baseId, "layer"));
    item.append(opacityControl(baseId, layer.style || {}));
    els.layerList.append(item);
  }
}

function renderObjectPanel(objects) {
  els.objectList.innerHTML = "";
  els.objectCount.textContent = String(objects.length);
  if (!objects.length) {
    els.objectList.append(emptyState("No objects"));
    return;
  }

  for (const object of objects) {
    const baseId = `scenario-object-${object.id}`;
    const item = document.createElement("div");
    item.className = "object-item";
    item.append(layerHeader(object, baseId, "object"));
    els.objectList.append(item);
  }
}

function renderQaPanel(qa) {
  els.qaReport.innerHTML = "";
  const status = qa && qa.status ? String(qa.status) : "n/a";
  els.qaStatus.textContent = status;
  els.qaStatus.className = `count-pill qa-status qa-status-${status}`;

  if (!qa) {
    els.qaReport.append(emptyState("No QA report"));
    return;
  }

  const summary = qa.summary || {};
  const score = qa.score || {};
  const metrics = document.createElement("div");
  metrics.className = "qa-metrics";
  metrics.append(
    qaMetric("Score", score.value != null ? `${score.value} ${score.grade || ""}`.trim() : "n/a"),
    qaMetric("Warnings", summary.warning_count || 0),
    qaMetric("Errors", summary.error_count || 0),
    qaMetric("Features", summary.feature_count || 0),
    qaMetric("Phases", (qa.phases || []).length)
  );
  els.qaReport.append(metrics);

  const issues = qa.issues || [];
  if (!issues.length) {
    els.qaReport.append(emptyState("No QA issues"));
    return;
  }

  const list = document.createElement("div");
  list.className = "qa-issues";
  for (const issue of issues.slice(0, 6)) {
    list.append(qaIssue(issue));
  }
  if (issues.length > 6) {
    const more = document.createElement("div");
    more.className = "qa-more";
    more.textContent = `${issues.length - 6} more`;
    list.append(more);
  }
  els.qaReport.append(list);
}

function qaMetric(label, value) {
  const node = document.createElement("div");
  node.className = "qa-metric";
  const number = document.createElement("strong");
  number.textContent = String(value);
  const text = document.createElement("span");
  text.textContent = label;
  node.append(number, text);
  return node;
}

function qaIssue(issue) {
  const node = document.createElement("button");
  node.type = "button";
  node.className = `qa-issue qa-issue-${issue.severity || "warning"}`;
  node.addEventListener("click", () => inspect(issue));

  const code = document.createElement("span");
  code.className = "qa-code";
  code.textContent = issue.code || issue.severity || "issue";
  const message = document.createElement("span");
  message.className = "qa-message";
  message.textContent = issue.message || "";
  node.append(code, message);
  return node;
}

function renderLegend(layers, objects) {
  const entries = [
    ...layers.map((layer) => ({
      id: `scenario-layer-${layer.id}`,
      name: layer.name || layer.id,
      type: layer.type,
      kind: "layer",
      visible: layer.visible !== false,
      style: layer.style || {},
      geometryType: primaryGeometryType(layer.geojson)
    })),
    ...objects.map((object) => ({
      id: `scenario-object-${object.id}`,
      name: object.name || object.id,
      type: object.type,
      kind: "object",
      visible: object.visible !== false,
      style: object.style || {},
      geometryType: object.geometry && object.geometry.type
    }))
  ];

  els.legendItems.innerHTML = "";
  els.legendCount.textContent = String(entries.length);

  if (!entries.length) {
    els.legendItems.append(emptyState("No visible map items"));
    return;
  }

  for (const entry of entries) {
    els.legendItems.append(legendItem(entry));
  }
}

function legendItem(entry) {
  const item = document.createElement("div");
  item.className = `legend-item${entry.visible ? "" : " is-hidden"}`;
  item.dataset.legendId = entry.id;

  const symbol = document.createElement("span");
  symbol.className = "legend-symbol";
  symbol.append(legendSymbol(entry.geometryType, entry.style));

  const label = document.createElement("div");
  label.className = "legend-label";
  const title = document.createElement("div");
  title.className = "legend-title";
  title.textContent = entry.name;
  const meta = document.createElement("div");
  meta.className = "legend-meta";
  meta.textContent = `${entry.kind} / ${entry.type}`;
  label.append(title, meta);

  item.append(symbol, label);
  return item;
}

function legendSymbol(geometryType, style) {
  const normalized = String(geometryType || "").toLowerCase();
  const symbol = document.createElement("span");

  if (normalized.includes("point")) {
    symbol.className = "legend-point";
    symbol.style.background = style.marker_color || style.stroke_color || "#2563eb";
    return symbol;
  }

  if (normalized.includes("line")) {
    symbol.className = "legend-line";
    symbol.style.borderTopColor = style.stroke_color || style.marker_color || "#334155";
    symbol.style.borderTopWidth = `${Math.max(2, numeric(style.stroke_width, 3))}px`;
    return symbol;
  }

  symbol.className = "legend-fill";
  symbol.style.background = style.fill_color || style.marker_color || "#94a3b8";
  symbol.style.borderColor = style.stroke_color || style.marker_color || "#475569";
  symbol.style.opacity = String(Math.max(0.35, numeric(style.fill_opacity, 0.18)));
  return symbol;
}

function layerHeader(item, baseId, kind) {
  const wrapper = document.createElement("div");
  wrapper.className = "layer-control";
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.checked = item.visible !== false;
  checkbox.title = "Toggle visibility";
  checkbox.addEventListener("change", () => setLayerVisibility(baseId, checkbox.checked));

  const body = document.createElement("button");
  body.type = "button";
  body.className = "item-button";
  body.addEventListener("click", () => inspect(item));
  const title = document.createElement("div");
  title.className = "item-title";
  title.textContent = item.name || item.id;
  const meta = document.createElement("div");
  meta.className = "item-meta";
  meta.textContent = `${kind} / ${item.type}`;
  body.append(title, meta);

  wrapper.append(checkbox, body);
  return wrapper;
}

function opacityControl(baseId, style) {
  const row = document.createElement("div");
  row.className = "opacity-row";
  const swatch = document.createElement("span");
  swatch.className = "swatch";
  swatch.style.background = style.fill_color || style.stroke_color || style.marker_color || "#94a3b8";
  const range = document.createElement("input");
  range.type = "range";
  range.min = "0";
  range.max = "1";
  range.step = "0.01";
  range.value = String(numeric(style.fill_opacity, 0.18));
  const value = document.createElement("span");
  value.className = "item-meta";
  value.textContent = Math.round(Number(range.value) * 100).toString();
  range.addEventListener("input", () => {
    const opacity = Number(range.value);
    value.textContent = Math.round(opacity * 100).toString();
    setLayerOpacity(baseId, opacity);
  });
  row.append(swatch, range, value);
  return row;
}

function setLayerVisibility(baseId, visible) {
  const entry = layerRegistry.get(baseId);
  if (!entry) {
    return;
  }
  for (const layer of entry.rendered) {
    if (map.getLayer(layer.id)) {
      map.setLayoutProperty(layer.id, "visibility", visible ? "visible" : "none");
    }
  }
  const legendItem = els.legendItems.querySelector(`[data-legend-id="${baseId}"]`);
  if (legendItem) {
    legendItem.classList.toggle("is-hidden", !visible);
  }
}

function setLayerOpacity(baseId, opacity) {
  const entry = layerRegistry.get(baseId);
  if (!entry) {
    return;
  }
  for (const layer of entry.rendered) {
    if (!map.getLayer(layer.id)) {
      continue;
    }
    if (layer.type === "fill") {
      map.setPaintProperty(layer.id, "fill-opacity", opacity);
    } else if (layer.type === "line") {
      map.setPaintProperty(layer.id, "line-opacity", Math.max(opacity, 0.2));
    } else if (layer.type === "line-casing") {
      map.setPaintProperty(layer.id, "line-opacity", lineCasingOpacity(opacity));
    } else if (layer.type === "circle") {
      map.setPaintProperty(layer.id, "circle-opacity", Math.max(opacity, 0.2));
    }
  }
}

function fitScenario(scenario) {
  const bounds = geojsonBounds(scenario.geojson);
  if (bounds) {
    map.fitBounds(bounds, { padding: 56, maxZoom: 13, duration: 500 });
    return;
  }
  const context = scenario.map_context || {};
  if (Array.isArray(context.center)) {
    map.easeTo({ center: context.center, zoom: context.zoom || 10 });
  }
}

function geojsonBounds(geojson) {
  const points = [];
  collectPositions(geojson && geojson.coordinates, points);
  if (geojson && geojson.type === "Feature") {
    collectPositions(geojson.geometry && geojson.geometry.coordinates, points);
  }
  if (geojson && geojson.type === "FeatureCollection") {
    for (const feature of geojson.features || []) {
      collectPositions(feature.geometry && feature.geometry.coordinates, points);
    }
  }
  if (!points.length) {
    return null;
  }
  let west = points[0][0];
  let south = points[0][1];
  let east = points[0][0];
  let north = points[0][1];
  for (const point of points) {
    west = Math.min(west, point[0]);
    south = Math.min(south, point[1]);
    east = Math.max(east, point[0]);
    north = Math.max(north, point[1]);
  }
  return [[west, south], [east, north]];
}

function primaryGeometryType(geojson) {
  if (!geojson) {
    return null;
  }
  if (geojson.type === "Feature") {
    return geojson.geometry && geojson.geometry.type;
  }
  if (geojson.type === "FeatureCollection") {
    for (const feature of geojson.features || []) {
      if (feature.geometry && feature.geometry.type) {
        return feature.geometry.type;
      }
    }
    return null;
  }
  return geojson.type;
}

function collectPositions(value, points) {
  if (!Array.isArray(value)) {
    return;
  }
  if (typeof value[0] === "number" && typeof value[1] === "number") {
    points.push(value);
    return;
  }
  for (const item of value) {
    collectPositions(item, points);
  }
}

async function importGeojson(event) {
  const file = event.target.files && event.target.files[0];
  if (!file) {
    return;
  }
  try {
    const raw = await file.text();
    const geojson = JSON.parse(raw);
    const collection = asFeatureCollection(geojson);
    const name = file.name.replace(/\.(geojson|json)$/i, "") || "Imported GeoJSON";
    const scenario = {
      type: "Scenario",
      scenario_id: "imported_geojson",
      scenario_name: name,
      map_context: {},
      metadata: { imported: true },
      objects: [],
      layers: [
        {
          id: "imported_geojson",
          type: "imported_geojson",
          name,
          visible: true,
          style: {
            stroke_color: "#7c3aed",
            stroke_width: 2,
            fill_color: "#a78bfa",
            fill_opacity: 0.18,
            marker_color: "#7c3aed"
          },
          geojson: collection
        }
      ],
      geojson: collection
    };
    setScenario(scenario);
    setStatus(`Imported ${name}`);
  } catch (error) {
    showError(error);
  } finally {
    event.target.value = "";
  }
}

function exportGeojson() {
  if (!activeScenario) {
    setStatus("No scenario loaded");
    return;
  }
  downloadJson(`${activeScenario.scenario_id || "scenario"}.geojson`, activeScenario.geojson);
  setStatus("Exported GeoJSON");
}

function asFeatureCollection(geojson) {
  if (geojson.type === "FeatureCollection") {
    return geojson;
  }
  if (geojson.type === "Feature") {
    return { type: "FeatureCollection", features: [geojson] };
  }
  return {
    type: "FeatureCollection",
    features: [{ type: "Feature", properties: {}, geometry: geojson }]
  };
}

function downloadJson(filename, payload) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { Accept: "application/json", ...(options.headers || {}) },
    ...options
  });
  const text = await response.text();
  const payload = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const detail = payload && payload.detail ? payload.detail : response.statusText;
    throw new Error(detail);
  }
  return payload;
}

function postJson(url, payload) {
  return fetchJson(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
}

function featureCount(geojson) {
  if (!geojson) {
    return 0;
  }
  if (geojson.type === "FeatureCollection") {
    return (geojson.features || []).length;
  }
  return 1;
}

function emptyState(text) {
  const node = document.createElement("div");
  node.className = "empty-state";
  node.textContent = text;
  return node;
}

function inspect(value) {
  els.inspectorOutput.textContent = JSON.stringify(normalizeInspectable(value), null, 2);
}

function normalizeInspectable(value) {
  if (!value || typeof value !== "object") {
    return value;
  }
  const output = {};
  for (const [key, item] of Object.entries(value)) {
    if (typeof item === "string" && looksJson(item)) {
      try {
        output[key] = JSON.parse(item);
      } catch (_error) {
        output[key] = item;
      }
    } else {
      output[key] = item;
    }
  }
  return output;
}

function looksJson(value) {
  return value.startsWith("{") || value.startsWith("[");
}

function popupHtml(properties) {
  const name = properties.name || properties.layer_name || properties.object_id || "Feature";
  const type = properties.layer_type || properties.object_type || properties.operation || "";
  return `<strong>${escapeHtml(String(name))}</strong><br>${escapeHtml(String(type))}`;
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function numeric(value, fallback) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function setStatus(message) {
  els.statusBar.textContent = message;
}

function showError(error) {
  console.error(error);
  setStatus(error.message || "Request failed");
}
