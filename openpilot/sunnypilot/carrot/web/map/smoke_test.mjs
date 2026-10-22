import fs from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
const here = path.dirname(fileURLToPath(import.meta.url));
const listeners = {};
const posted = [];

function mkEl(id) {
  return {
    id, hidden: false, style: { setProperty() {} }, dataset: {},
    classList: { add() {}, remove() {}, contains() { return false; } },
    querySelector() { return mkEl("q"); },
    _t: "",
    set textContent(v) { this._t = v; },
    get textContent() { return this._t; },
  };
}

const polyline = { setLatLngs() {}, addTo() { return this; } };
const mapObj = {
  on() { return this; },
  removeLayer() {},
  addLayer() { return this; },
  setView() { return this; },
  distance() { return 1e9; },
};

globalThis.L = {
  map() { return mapObj; },
  tileLayer() { return { addTo() { return this; } }; },
  polyline() { return polyline; },
};

globalThis.window = {
  addEventListener: (t, fn) => { listeners[t] = fn; },
  parent: { postMessage: (m) => posted.push(m) },
  location: { search: "?map_type=roadmap&heading_up=1" },
};
globalThis.document = { getElementById: (id) => mkEl(id) };
globalThis.fetch = async () => ({ json: async () => ({ settings: { kmap_tianditu_tk: "test-tk-123" } }) });
globalThis.setTimeout = () => 0;
globalThis.URLSearchParams = URLSearchParams;

const code = fs.readFileSync(path.join(here, "map.js"), "utf8");
new Function(code)();

// Wait for the async boot (fetchTk -> initMap -> applyLayers -> ready) to settle.
await new Promise((r) => setImmediate(r));
await new Promise((r) => setImmediate(r));

const send = (msg) => listeners.message({ data: msg });
send({ source: "carrot-vision", type: "vehicle", lat: 31.23, lon: 121.47, heading: 90, speed: 15 });
send({ source: "carrot-vision", type: "nav", active: true, turn: { info: 2, dist: 120, text: "turn" }, sdi: { limit: 60, dist: 300 }, goal: { dist: 1500 }, road: "Nanjing Rd" });
send({ source: "carrot-vision", type: "route", active: true, coordinates: [{ lat: 31.23, lon: 121.47 }, { lat: 31.24, lon: 121.48 }] });
send({ source: "carrot-vision", type: "zoom-bias", bias: 2 });
send({ source: "carrot-vision", type: "debug-request" });
// foreign-source message must be ignored
send({ source: "evil", type: "vehicle", lat: 1, lon: 1 });

await new Promise((r) => setImmediate(r));
const ready = posted.find((p) => p.type === "ready" && p.source === "carrot-kmap");
const debug = posted.find((p) => p.type === "debug-snapshot");
let pass = 0, fail = 0;
function check(name, cond) {
  if (cond) { pass++; console.log("PASS  " + name); }
  else { fail++; console.log("FAIL  " + name); }
}
check("ready posted with correct source", !!ready);
check("ready provider is tianditu (tk present)", String(ready?.provider || "").startsWith("tianditu"));
check("ready includes sdkLoadedAt", typeof ready?.sdkLoadedAt === "number" && ready.sdkLoadedAt > 0);
check("debug snapshot responds with route count", debug?.snapshot?.routePoints === 2);
check("zoom bias stored", debug?.snapshot?.zoomBias === 2);
check("heading_up flag read from query", debug?.snapshot?.heading_up === true);
console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
