"use strict";
/*
 * Local China map dock for the carrot 7000 drive page.
 *
 * Speaks the SAME postMessage contract as CarrotPilot's kmap iframe, so the
 * parent (web/js/realtime/carrot_map.js) works unchanged. Tiles are Tianditu
 * (国家天地图, CGCS2000 ~= WGS-84, so vehicle/route points need NO datum
 * transform); the browser token is fetched same-origin from /api/web_settings.
 * Without a token we fall back to OpenStreetMap raster tiles.
 *
 * inbound (window "message", parent -> here):
 *   vehicle {lat, lon, heading, speed, ...}
 *   nav     {active, turn{info,dist,text}, sdi{limit,dist}, goal{dist}, road}
 *   route   {active, coordinates:[{lat,lon}]}
 *   expanded bool | zoom-bias int(-3..3) | debug-request
 * outbound (here -> parent): MUST include source:"carrot-kmap"
 *   ready {provider, sdkLoadedAt} on first usable state
 */
(function () {
  const root = document.getElementById("mapRoot");
  const mapEl = document.getElementById("leafletMap");
  const vehicleEl = document.getElementById("vehicleMarker");
  const arrowEl = vehicleEl.querySelector(".map-vehicle__arrow");
  const navCard = document.getElementById("navCard");
  const navTurn = document.getElementById("navTurn");
  const navTurnText = document.getElementById("navText");
  const navRoad = document.getElementById("navRoad");
  const navTurnDist = document.getElementById("navTurnDist");
  const navGoal = document.getElementById("navGoal");
  const sdiBadge = document.getElementById("sdiBadge");
  const sdiLimit = document.getElementById("sdiLimit");
  const sdiDist = document.getElementById("sdiDist");
  const statusEl = document.getElementById("statusText");

  const params = new URLSearchParams(window.location.search);
  const MAP_TYPE = String(params.get("map_type") || "roadmap").toLowerCase();
  const HEADING_UP = params.get("heading_up") === "1";

  const DEFAULT_CENTER = [39.9087, 116.3975]; // Beijing, only before first fix
  const FOLLOW_ZOOM = 16;
  const ROUTE_MAX_POINTS = 1200;
  const TDT_SUBS = "01234567".split("");

  let map = null;
  let baseLayer = null;
  let labelLayer = null;
  let routeLayer = null;
  let provider = "loading";
  let sdkLoadedAt = 0;
  let readyPosted = false;
  let lastCenter = null;
  let lastHeading = 0;
  let following = true;
  let zoomBias = 0;
  const state = { lat: NaN, lon: NaN, heading: 0, speed: 0 };

  const routeState = { active: false, coordinates: [] };

  function finite(value) {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }
  function validLatLon(lat, lon) {
    return lat !== null && lon !== null && Math.abs(lat) <= 90 && Math.abs(lon) <= 180 && !(lat === 0 && lon === 0);
  }
  function setStatus(text) {
    statusEl.textContent = text;
    root.dataset.status = text ? "active" : "idle";
  }

  function tdtUrl(layer) {
    const sub = TDT_SUBS[Math.floor(Math.random() * TDT_SUBS.length)];
    return `https://t${sub}.tianditu.gov.cn/${layer}/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0`
      + `&LAYER=${layer.split("_")[0]}&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles`
      + `&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&tk=${encodeURIComponent(state.tk || "")}`;
  }

  function removeLayerSafe(layer) {
    if (layer) {
      try { map.removeLayer(layer); } catch { /* noop */ }
    }
    return null;
  }

  function applyLayers() {
    if (!map) return;
    baseLayer = removeLayerSafe(baseLayer);
    labelLayer = removeLayerSafe(labelLayer);

    if (state.tk) {
      const isSat = MAP_TYPE === "satellite" || (MAP_TYPE === "hybrid");
      const baseName = isSat ? "img_w" : "vec_w";
      const labelName = isSat ? "cia_w" : "cva_w";
      baseLayer = L.tileLayer(tdtUrl(baseName), {
        maxZoom: 18,
        minZoom: 2,
        subdomains: TDT_SUBS,
        attribution: "© 天地图",
      });
      // hybrid keeps labels; pure satellite hides them.
      if (MAP_TYPE !== "satellite") {
        labelLayer = L.tileLayer(tdtUrl(labelName), {
          maxZoom: 18,
          minZoom: 2,
          subdomains: TDT_SUBS,
        });
      }
      provider = isSat ? "tianditu-img" : "tianditu-vec";
    } else {
      baseLayer = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: "© OpenStreetMap",
      });
      provider = "osm";
    }
    baseLayer.addTo(map);
    if (labelLayer) labelLayer.addTo(map);
    if (!sdkLoadedAt) sdkLoadedAt = Date.now();
    setStatus(provider);
    postReady();
  }

  function initMap() {
    if (map || typeof L === "undefined") return;
    map = L.map(mapEl, {
      center: DEFAULT_CENTER,
      zoom: FOLLOW_ZOOM,
      zoomControl: false,
      attributionControl: true,
      zoomSnap: 0.5,
      zoomDelta: 0.5,
    });
    // dragging/pan breaks follow temporarily; double-click re-centers.
    map.on("dragstart", () => { following = false; });
    map.on("dblclick", () => { following = true; applyView(true); });
    routeLayer = L.polyline([], { color: "#378add", weight: 4, opacity: 0.95 }).addTo(map);
    // Base layer is installed by boot() only after the Tianditu token is read,
    // so the provider on the first `ready` post is already correct.
  }

  function effectiveZoom() {
    let z = FOLLOW_ZOOM + zoomBias;
    if (state.speed != null && state.speed > 22) z += 0.5; // ~80 km/h, pull out a touch
    if (state.speed != null && state.speed > 33) z += 0.5; // ~120 km/h
    return Math.max(10, Math.min(18.5, z));
  }

  function applyView(force) {
    if (!map || !validLatLon(finite(state.lat), finite(state.lon))) return;
    const lat = finite(state.lat);
    const lon = finite(state.lon);
    const center = [lat, lon];
    if (following && (force || !lastCenter || map.distance(lastCenter, center) > 0.5)) {
      map.setView(center, effectiveZoom(), { animate: true, duration: 0.25 });
    }
    lastCenter = center;
    arrowEl.style.transform = `rotate(${lastHeading}deg)`;
    vehicleEl.hidden = false;
  }

  function setRoute(payload) {
    const raw = Array.isArray(payload?.coordinates) ? payload.coordinates : [];
    const latlngs = [];
    for (const point of raw) {
      const lat = finite(point?.lat ?? point?.latitude);
      const lon = finite(point?.lon ?? point?.longitude);
      if (!validLatLon(lat, lon)) continue;
      latlngs.push([lat, lon]);
      if (latlngs.length >= ROUTE_MAX_POINTS) break;
    }
    routeState.active = Boolean(payload?.active) && latlngs.length > 1;
    routeState.coordinates = latlngs;
    if (routeLayer) {
      routeLayer.setLatLngs(routeState.active ? latlngs : []);
      if (routeState.active && following === false && validLatLon(finite(state.lat), finite(state.lon))) {
        // keep user-pan freedom; do not auto-fit
      }
    }
  }

  // cp turn-type codes (xTurnInfo) -> a compact arrow glyph. Falls back to the
  // provided localized text when the code is unmapped.
  const TURN_GLYPH = {
    0: "↑", 1: "↗", 2: "→", 3: "↘", 4: "↓", 5: "↙", 6: "←", 7: "↖",
    8: "⤴", 9: "⤵", 10: "↺", 11: "◎",
  };
  function formatDist(meters) {
    const d = finite(meters);
    if (d === null || d <= 0) return "";
    if (d >= 1000) return `${(d / 1000).toFixed(d >= 10000 ? 0 : 1)}km`;
    return `${Math.round(d)}m`;
  }

  function setNav(payload) {
    const active = Boolean(payload?.active);
    navCard.hidden = !active;
    if (!active) return;
    const info = finite(payload?.turn?.info);
    const glyph = info !== null && TURN_GLYPH[info] ? TURN_GLYPH[info] : "·";
    navTurn.textContent = glyph;
    navTurnText.textContent = String(payload?.turn?.text || "");
    navRoad.textContent = String(payload?.road || "");
    navTurnDist.textContent = formatDist(payload?.turn?.dist);
    const goal = formatDist(payload?.goal?.dist);
    navGoal.textContent = goal ? `剩余 ${goal}` : "";

    const limit = finite(payload?.sdi?.limit);
    if (limit !== null && limit > 0) {
      sdiBadge.hidden = false;
      sdiLimit.textContent = String(Math.round(limit));
      sdiDist.textContent = formatDist(payload?.sdi?.dist);
    } else {
      sdiBadge.hidden = true;
    }
  }

  function setVehicle(payload) {
    const lat = finite(payload?.lat);
    const lon = finite(payload?.lon);
    if (!validLatLon(lat, lon)) return;
    state.lat = lat;
    state.lon = lon;
    const heading = finite(payload?.heading);
    if (heading !== null) state.heading = lastHeading = ((heading % 360) + 360) % 360;
    state.speed = finite(payload?.speed) ?? state.speed;
    applyView(false);
    if (!readyPosted) postReady();
  }

  function postReady() {
    if (!window.parent || window.parent === window) return;
    readyPosted = true;
    window.parent.postMessage({
      source: "carrot-kmap",
      type: "ready",
      provider,
      sdkLoadedAt,
      status: "ready",
      ts: Date.now(),
    }, "*");
  }

  function handleMessage(event) {
    const data = event.data || {};
    if (!data || data.source !== "carrot-vision") return;
    switch (data.type) {
      case "vehicle":
        setVehicle(data);
        break;
      case "nav":
        if (data.active) setNav(data);
        else { navCard.hidden = true; sdiBadge.hidden = true; }
        break;
      case "route":
        setRoute(data);
        break;
      case "expanded":
        // Box mode only; expanded view is handled by the parent dock resize.
        break;
      case "zoom-bias":
        zoomBias = Math.max(-3, Math.min(3, Math.round(Number(data.bias ?? data.value ?? 0) || 0)));
        if (following) applyView(true);
        break;
      case "debug-request":
        try {
          window.parent.postMessage({
            source: "carrot-kmap",
            type: "debug-snapshot",
            snapshot: {
              provider, hasFix: validLatLon(finite(state.lat), finite(state.lon)),
              routePoints: routeState.coordinates.length, zoomBias, heading_up: HEADING_UP,
            },
          }, "*");
        } catch { /* noop */ }
        break;
      default:
        break;
    }
  }

  async function fetchTk() {
    try {
      const resp = await fetch("/api/web_settings", { cache: "no-store" });
      const body = await resp.json();
      const tk = String(body?.settings?.kmap_tianditu_tk || "").trim();
      state.tk = tk;
    } catch {
      state.tk = "";
    }
  }

  window.addEventListener("message", handleMessage);

  (async function boot() {
    await fetchTk();
    initMap();
    applyLayers();
    setStatus(state.tk ? "tianditu" : "osm-fallback");
    // Tell the parent we are alive with the final provider so the dock reveals
    // without waiting for the first GPS fix (which may never come off-road).
    postReady();
  })();
})();
