/** Map browser client coordinates to 2160×1080 OPUI logical space (portrait + scale aware). */

export function clientToOpui(clientX, clientY) {
  const root = document.getElementById("app");
  if (!root) return { x: 0, y: 0 };
  const rect = root.getBoundingClientRect();
  const scale = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--opui-scale")) || 1;
  if (!rect.width || !rect.height) return { x: 0, y: 0 };
  const x = (clientX - rect.left) / scale;
  const y = (clientY - rect.top) / scale;
  return {
    x: Math.max(0, Math.min(2160, x)),
    y: Math.max(0, Math.min(1080, y)),
  };
}

export function bindOpuiPointerDebug(enabled = false) {
  if (!enabled || bindOpuiPointerDebug._bound) return;
  bindOpuiPointerDebug._bound = true;
  document.addEventListener("pointerdown", (ev) => {
    const p = clientToOpui(ev.clientX, ev.clientY);
    if (typeof console !== "undefined" && console.debug) {
      console.debug("[opui]", Math.round(p.x), Math.round(p.y));
    }
  }, { passive: true });
}
