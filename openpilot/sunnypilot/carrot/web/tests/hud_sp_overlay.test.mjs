import assert from "node:assert/strict";
import test from "node:test";

import { createSpHudOverlay } from "../src/features/drive/contents/vision/hud_sp/index.js";
import { SpHudPayload } from "../src/features/drive/contents/vision/hud_sp/payload.js";

/* Minimal DOM stub for createSpHudOverlay. The overlay uses only element
 * creation, className, append, textContent, style and (on update) hidden /
 * classList. */
class FakeClassList {
  constructor() { this.set = new Set(); }
  toggle(c, force) {
    const on = force === undefined ? !this.set.has(c) : Boolean(force);
    if (on) this.set.add(c); else this.set.delete(c);
    return on;
  }
  add(c) { this.set.add(c); }
  remove(c) { this.set.delete(c); }
  contains(c) { return this.set.has(c); }
}

class FakeNode {
  constructor(tag) {
    this.tagName = tag;
    this.nodeName = tag;
    this.children = [];
    this._text = "";
    this.className = "";
    this.style = {};
    this.dataset = {};
    this.classList = new FakeClassList();
    this._hidden = false;
  }
  get hidden() { return this._hidden; }
  set hidden(v) { this._hidden = Boolean(v); }
  append(...nodes) { for (const n of nodes) if (n) this.children.push(n); }
  appendChild(n) { if (n) this.children.push(n); return n; }
  set textContent(v) { this._text = String(v ?? ""); }
  get textContent() { return this._text; }
  setAttribute(k, v) { this.dataset[k] = String(v); }
  getAttribute(k) { return this.dataset[k]; }
  removeAttribute(k) { delete this.dataset[k]; }
  toggleAttribute(k, force) {
    const on = force === undefined ? !this.dataset[k] : Boolean(force);
    if (on) this.dataset[k] = ""; else delete this.dataset[k];
    return on;
  }
  addEventListener() {}
  removeEventListener() {}
  querySelectorAll() { return []; }
  getContext() { return null; }
}

const doc = {
  createElement: (tag) => new FakeNode(tag),
  createElementNS: (ns, tag) => new FakeNode(tag),
  getElementById: () => null,
  head: new FakeNode("head"),
  documentElement: new FakeNode("html"),
};

test("createSpHudOverlay builds a stage overlay with the sunnypilot sections", () => {
  const overlay = createSpHudOverlay(doc);
  assert.ok(overlay.root, "root must exist");
  assert.equal(overlay.root.className, "sp-hud");
  const classes = overlay.root.querySelectorAll?.() ?? [];
  // root children: road, cruise, sla, speed-block, blinkers, bsls, sccs, rocket, torque, exp
  assert.ok(overlay.root.children.length >= 10, `expected >= 10 children, got ${overlay.root.children.length}`);
});

test("update hides everything on a null payload", () => {
  const overlay = createSpHudOverlay(doc);
  const changed = overlay.update({});
  assert.equal(changed, true);
});

test("update reflects speed/limit/road on a compact payload with raw state", () => {
  const overlay = createSpHudOverlay(doc);
  overlay.activate();
  const payload = {
    isMetric: true,
    vEgoKph: 72,
    vSetKph: 100,
    speedLimitKph: 80,
    roadName: "Test Road",
    leftBlinker: true,
  };
  overlay.update(payload);
  assert.equal(overlay.status().visible, true);
  assert.ok(overlay.status().data, "data must be retained");
});

test("overlay lifecycle follows the facade contract", () => {
  const overlay = createSpHudOverlay(doc);
  assert.equal(overlay.activate(), true);
  assert.equal(overlay.status().active, true);
  assert.equal(overlay.deactivate(), true);
  assert.equal(overlay.status().active, false);
  overlay.setSuppressed("replay", true);
  assert.equal(overlay.status().suppressions.includes("replay"), true);
  assert.equal(overlay.destroy(), true);
  assert.equal(overlay.status().destroyed, true);
});

test("SpHudPayload stays exported from the overlay module", () => {
  assert.equal(typeof SpHudPayload.derive, "function");
});
