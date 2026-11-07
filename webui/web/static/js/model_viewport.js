/** Align model overlay canvas with WebRTC video object-fit: cover region. */

let lastViewportKey = "";

/**
 * @returns {{ x: number, y: number, w: number, h: number, cw: number, ch: number } | null}
 */
export function syncModelOverlayViewport() {
  const wrap = document.getElementById("camera-wrap");
  const video = document.getElementById("road-video");
  const overlay = document.getElementById("model-overlay");
  if (!wrap || !overlay) return null;

  const cw = wrap.clientWidth || 1600;
  const ch = wrap.clientHeight || 900;
  const devPc = wrap.classList.contains("is-dev-pc");

  let x = 0;
  let y = 0;
  let w = cw;
  let h = ch;

  if (!devPc && video) {
    const vw = video.videoWidth || 0;
    const vh = video.videoHeight || 0;
    if (vw > 0 && vh > 0) {
      const scale = Math.max(cw / vw, ch / vh);
      w = vw * scale;
      h = vh * scale;
      x = (cw - w) / 2;
      y = (ch - h) / 2;
    }
  }

  overlay.style.left = `${x}px`;
  overlay.style.top = `${y}px`;
  overlay.style.width = `${w}px`;
  overlay.style.height = `${h}px`;
  overlay.style.right = "auto";
  overlay.style.bottom = "auto";

  const key = `${Math.round(x)}|${Math.round(y)}|${Math.round(w)}|${Math.round(h)}`;
  if (key !== lastViewportKey) {
    lastViewportKey = key;
    window.dispatchEvent(new CustomEvent("opui:overlay-viewport", { detail: { x, y, w, h, cw, ch } }));
  }

  return { x, y, w, h, cw, ch };
}

export function getOverlayProjectionSize() {
  const vp = syncModelOverlayViewport();
  if (!vp) return { w: 1600, h: 900 };
  return { w: Math.max(1, Math.round(vp.w)), h: Math.max(1, Math.round(vp.h)) };
}
