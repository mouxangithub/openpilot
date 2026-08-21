/** Developer UI overlay — bottom bar + right column (developer_ui/__init__.py). */

import { tr } from "./i18n.js";

export function updateDevUi(st) {
  const bottom = document.getElementById("dev-ui-bottom");
  const right = document.getElementById("dev-ui-right");
  const data = st?.dev_ui;

  if (!data || !st?.started) {
    if (bottom) bottom.hidden = true;
    if (right) right.hidden = true;
    return;
  }

  const mode = Number(data.mode) || 0;
  const showBottom = mode === 1 || mode === 3;
  const showRight = mode === 2 || mode === 3;
  const adj = showRight ? 180 : 100;
  document.documentElement.style.setProperty("--dev-ui-adj", `${adj}px`);

  if (bottom) {
    bottom.hidden = !showBottom;
    if (showBottom) renderBar(bottom, data.bottom || []);
  }
  if (right) {
    right.hidden = !showRight;
    if (showRight) renderColumn(right, data.right || []);
  }
}

function itemHtml(el) {
  return `<span class="opui-dev-ui-item">
    <span class="opui-dev-ui-label">${escapeHtml(tr(el.label))}</span>
    <span class="opui-dev-ui-value" style="color:${el.color || "#fff"}">${escapeHtml(el.value)}</span>
    ${el.unit ? `<span class="opui-dev-ui-unit">${escapeHtml(tr(el.unit))}</span>` : ""}
  </span>`;
}

function renderBar(container, items) {
  if (!items.length) {
    container.innerHTML = "";
    return;
  }

  container.innerHTML = items.map((el) => itemHtml(el)).join("");
  layoutBottomBar(container);
}

function layoutBottomBar(container) {
  const children = [...container.querySelectorAll(".opui-dev-ui-item")];
  if (!children.length) return;

  children.forEach((el) => {
    el.style.position = "absolute";
    el.style.left = "0";
    el.style.top = "50%";
    el.style.transform = "translateY(-50%)";
  });

  const widths = children.map((el) => el.getBoundingClientRect().width);
  const total = widths.reduce((sum, w) => sum + w, 0);
  const gap = Math.max(0, (container.clientWidth - total) / (children.length + 1));
  let x = gap;
  children.forEach((el, i) => {
    el.style.left = `${x}px`;
    x += widths[i] + gap;
  });
}

function renderColumn(container, items) {
  container.innerHTML = items.map((el) => `
    <div class="opui-dev-ui-col">
      <div class="opui-dev-ui-col-label">${escapeHtml(tr(el.label))}</div>
      <div class="opui-dev-ui-col-row">
        <span class="opui-dev-ui-col-value" style="color:${el.color || "#fff"}">${escapeHtml(el.value)}</span>
        ${el.unit ? `<span class="opui-dev-ui-col-unit">${escapeHtml(tr(el.unit))}</span>` : ""}
      </div>
    </div>`).join("");
}

function escapeHtml(s) {
  return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
