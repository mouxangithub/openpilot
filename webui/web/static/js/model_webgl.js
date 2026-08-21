/** WebGL2 model overlay (lanes / path ribbon / leads) — falls back to Canvas 2D in model_canvas.js */

let canvas = null;
let gl = null;
let prog = null;
let posLoc = null;
let colorLoc = null;
let resLoc = null;
let vbo = null;
let staticVbo = null;
let staticGpuVertCount = 0;
let rainbowProg = null;
let rainbowHueLoc = null;
let rainbowResLoc = null;
let rainbowPosLoc = null;
let rainbowHueTLoc = null;
let rainbowPathVbo = null;
let rainbowHueVbo = null;
let rainbowPathVertCount = 0;
let rainbowPathGeometryKey = null;
let hueScratch = new Float32Array(0);
let ready = false;
let lastOverlay = null;
let lastFrameKey = null;
let lastGeometryKey = null;
let lastAnimKey = null;
let cachedStaticVerts = null;
let cachedStaticColors = null;
let rainbowHue = 0;
let rainbowRafId = null;

const PATH_WHITE = [242 / 255, 242 / 255, 242 / 255, 0.7];

let cssW = 1600;
let cssH = 900;
let pixelRatio = 1;
let posScratch = new Float32Array(0);
let colorScratch = new Float32Array(0);

function compileShader(type, src) {
  const s = gl.createShader(type);
  gl.shaderSource(s, src);
  gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
    gl.deleteShader(s);
    return null;
  }
  return s;
}

function asPoints(raw) {
  if (!raw?.length) return [];
  if (Array.isArray(raw[0])) return raw;
  const pts = [];
  for (let i = 0; i + 1 < raw.length; i += 2) pts.push([raw[i], raw[i + 1]]);
  return pts;
}

function resize(w, h) {
  if (!canvas || !gl) return;
  cssW = w;
  cssH = h;
  pixelRatio = window.devicePixelRatio || 1;
  const pw = Math.max(1, Math.floor(w * pixelRatio));
  const ph = Math.max(1, Math.floor(h * pixelRatio));
  if (canvas.width !== pw || canvas.height !== ph) {
    canvas.width = pw;
    canvas.height = ph;
    canvas.style.width = `${w}px`;
    canvas.style.height = `${h}px`;
    gl.viewport(0, 0, pw, ph);
  }
}

function ensureScratch(vertCount) {
  const posLen = vertCount * 2;
  const colorLen = vertCount * 4;
  if (posScratch.length < posLen) posScratch = new Float32Array(posLen);
  if (colorScratch.length < colorLen) colorScratch = new Float32Array(colorLen);
}

function drawTriangles(verts, colors) {
  if (!verts.length) return;
  const n = verts.length;
  ensureScratch(n);
  for (let i = 0; i < n; i++) {
    posScratch[i * 2] = verts[i][0] * pixelRatio;
    posScratch[i * 2 + 1] = verts[i][1] * pixelRatio;
    colorScratch[i * 4] = colors[i][0];
    colorScratch[i * 4 + 1] = colors[i][1];
    colorScratch[i * 4 + 2] = colors[i][2];
    colorScratch[i * 4 + 3] = colors[i][3];
  }
  const posBytes = n * 8;
  const colorBytes = n * 16;
  gl.bindBuffer(gl.ARRAY_BUFFER, vbo);
  gl.bufferData(gl.ARRAY_BUFFER, posBytes + colorBytes, gl.DYNAMIC_DRAW);
  gl.bufferSubData(gl.ARRAY_BUFFER, 0, posScratch.subarray(0, n * 2));
  gl.bufferSubData(gl.ARRAY_BUFFER, posBytes, colorScratch.subarray(0, n * 4));

  gl.enableVertexAttribArray(posLoc);
  gl.vertexAttribPointer(posLoc, 2, gl.FLOAT, false, 0, 0);
  gl.enableVertexAttribArray(colorLoc);
  gl.vertexAttribPointer(colorLoc, 4, gl.FLOAT, false, 0, posBytes);

  gl.drawArrays(gl.TRIANGLES, 0, n);
}

function uploadStaticGpu(verts, colors) {
  if (!gl) return;
  const n = verts.length;
  if (!n) {
    staticGpuVertCount = 0;
    return;
  }
  if (!staticVbo) staticVbo = gl.createBuffer();
  ensureScratch(n);
  for (let i = 0; i < n; i++) {
    posScratch[i * 2] = verts[i][0] * pixelRatio;
    posScratch[i * 2 + 1] = verts[i][1] * pixelRatio;
    colorScratch[i * 4] = colors[i][0];
    colorScratch[i * 4 + 1] = colors[i][1];
    colorScratch[i * 4 + 2] = colors[i][2];
    colorScratch[i * 4 + 3] = colors[i][3];
  }
  const posBytes = n * 8;
  const colorBytes = n * 16;
  gl.bindBuffer(gl.ARRAY_BUFFER, staticVbo);
  gl.bufferData(gl.ARRAY_BUFFER, posBytes + colorBytes, gl.STATIC_DRAW);
  gl.bufferSubData(gl.ARRAY_BUFFER, 0, posScratch.subarray(0, n * 2));
  gl.bufferSubData(gl.ARRAY_BUFFER, posBytes, colorScratch.subarray(0, n * 4));
  staticGpuVertCount = n;
}

function drawStaticGpu() {
  if (!gl || !staticVbo || !staticGpuVertCount) return;
  const n = staticGpuVertCount;
  const posBytes = n * 8;
  gl.bindBuffer(gl.ARRAY_BUFFER, staticVbo);
  gl.enableVertexAttribArray(posLoc);
  gl.vertexAttribPointer(posLoc, 2, gl.FLOAT, false, 0, 0);
  gl.enableVertexAttribArray(colorLoc);
  gl.vertexAttribPointer(colorLoc, 4, gl.FLOAT, false, 0, posBytes);
  gl.drawArrays(gl.TRIANGLES, 0, n);
}

function drawOverlayMeshes(merged) {
  if (merged.rainbow && rainbowProg) {
    syncRainbowPathGpu(merged, merged.geometry_key || lastGeometryKey);
    if (staticGpuVertCount > 0) drawStaticGpu();
    else if (cachedStaticVerts?.length) {
      uploadStaticGpu(cachedStaticVerts, cachedStaticColors);
      drawStaticGpu();
    }
    drawRainbowPathGpu(rainbowHue);
    return;
  }
  const pathMesh = buildPathMeshes(merged);
  if (staticGpuVertCount > 0) drawStaticGpu();
  else if (cachedStaticVerts?.length) {
    uploadStaticGpu(cachedStaticVerts, cachedStaticColors);
    drawStaticGpu();
  }
  if (pathMesh.allVerts.length) drawTriangles(pathMesh.allVerts, pathMesh.allColors);
}

function appendRainbowFan(allPos, allHueT, poly, halo = 1.06) {
  if (poly.length < 3) return;
  const haloPoly = expandPoly(poly, halo);
  const pushFan = (pts) => {
    const n = pts.length;
    for (let i = 1; i < n - 1; i++) {
      allPos.push(pts[0], pts[i], pts[i + 1]);
      const t1 = i / Math.max(1, n - 1);
      const t2 = (i + 1) / Math.max(1, n - 1);
      allHueT.push(0, t1, t2);
    }
  };
  pushFan(haloPoly);
  pushFan(poly);
}

function syncRainbowPathGpu(data, geometryKey) {
  if (!gl || !data?.rainbow) return;
  if (geometryKey && geometryKey === rainbowPathGeometryKey && rainbowPathVertCount > 0) return;
  const pathPoly = asPoints(data.path_polygon);
  if (pathPoly.length < 4) {
    rainbowPathVertCount = 0;
    return;
  }
  const allPos = [];
  const allHueT = [];
  appendRainbowFan(allPos, allHueT, pathPoly, 1.06);
  const n = allPos.length;
  if (!n) {
    rainbowPathVertCount = 0;
    return;
  }
  if (!rainbowPathVbo) rainbowPathVbo = gl.createBuffer();
  if (!rainbowHueVbo) rainbowHueVbo = gl.createBuffer();
  ensureScratch(n);
  if (hueScratch.length < n) hueScratch = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    posScratch[i * 2] = allPos[i][0] * pixelRatio;
    posScratch[i * 2 + 1] = allPos[i][1] * pixelRatio;
    hueScratch[i] = allHueT[i];
  }
  gl.bindBuffer(gl.ARRAY_BUFFER, rainbowPathVbo);
  gl.bufferData(gl.ARRAY_BUFFER, n * 8, gl.STATIC_DRAW);
  gl.bufferSubData(gl.ARRAY_BUFFER, 0, posScratch.subarray(0, n * 2));
  gl.bindBuffer(gl.ARRAY_BUFFER, rainbowHueVbo);
  gl.bufferData(gl.ARRAY_BUFFER, n * 4, gl.STATIC_DRAW);
  gl.bufferSubData(gl.ARRAY_BUFFER, 0, hueScratch.subarray(0, n));
  rainbowPathVertCount = n;
  rainbowPathGeometryKey = geometryKey || null;
}

function drawRainbowPathGpu(hueDeg) {
  if (!gl || !rainbowProg || !rainbowPathVertCount) return;
  const n = rainbowPathVertCount;
  gl.useProgram(rainbowProg);
  gl.uniform2f(rainbowResLoc, canvas.width, canvas.height);
  gl.uniform1f(rainbowHueLoc, hueDeg / 360);
  gl.bindBuffer(gl.ARRAY_BUFFER, rainbowPathVbo);
  gl.enableVertexAttribArray(rainbowPosLoc);
  gl.vertexAttribPointer(rainbowPosLoc, 2, gl.FLOAT, false, 0, 0);
  gl.bindBuffer(gl.ARRAY_BUFFER, rainbowHueVbo);
  gl.enableVertexAttribArray(rainbowHueTLoc);
  gl.vertexAttribPointer(rainbowHueTLoc, 1, gl.FLOAT, false, 0, 0);
  gl.drawArrays(gl.TRIANGLES, 0, n);
  gl.useProgram(prog);
}

function fanTriangulate(poly, rgbaFn) {
  if (poly.length < 3) return { verts: [], colors: [] };
  const verts = [];
  const colors = [];
  const c0 = rgbaFn(poly[0], 0, poly);
  for (let i = 1; i < poly.length - 1; i++) {
    verts.push(poly[0], poly[i], poly[i + 1]);
    colors.push(c0, rgbaFn(poly[i], i, poly), rgbaFn(poly[i + 1], i + 1, poly));
  }
  return { verts, colors };
}

function centroid(poly) {
  let x = 0;
  let y = 0;
  for (const p of poly) {
    x += p[0];
    y += p[1];
  }
  return [x / poly.length, y / poly.length];
}

function expandPoly(poly, scale) {
  const [cx, cy] = centroid(poly);
  return poly.map(([x, y]) => [cx + (x - cx) * scale, cy + (y - cy) * scale]);
}

function appendMesh(allVerts, allColors, mesh) {
  for (let i = 0; i < mesh.verts.length; i++) allVerts.push(mesh.verts[i]);
  for (let i = 0; i < mesh.colors.length; i++) allColors.push(mesh.colors[i]);
}

function pushLaneMesh(allVerts, allColors, poly, rgbaFn, halo = 1.04) {
  if (poly.length < 3) return;
  const haloPoly = expandPoly(poly, halo);
  const haloMesh = fanTriangulate(haloPoly, (_p, _i) => {
    const c = rgbaFn(_p, _i, poly);
    return [c[0], c[1], c[2], c[3] * 0.35];
  });
  const coreMesh = fanTriangulate(poly, rgbaFn);
  appendMesh(allVerts, allColors, haloMesh);
  appendMesh(allVerts, allColors, coreMesh);
}

function rainbowColor(i, n) {
  const hue = ((rainbowHue + (i / n) * 120) % 360) / 360;
  const s = 0.95;
  const l = 0.55;
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
  const p = 2 * l - q;
  const hk = hue + 1 / 3;
  return [hue2rgb(p, q, hk + 1), hue2rgb(p, q, hk), hue2rgb(p, q, hk - 1), 0.85];
}

function hue2rgb(p, q, t) {
  let tt = t;
  if (tt < 0) tt += 1;
  if (tt > 1) tt -= 1;
  if (tt < 1 / 6) return p + (q - p) * 6 * tt;
  if (tt < 1 / 2) return q;
  if (tt < 2 / 3) return p + (q - p) * (2 / 3 - tt) * 6;
  return p;
}

function resolveAnimOverlay(data) {
  if (!data?.anim_only || !lastOverlay) return data;
  const gk = data.geometry_key || lastOverlay.geometry_key;
  if (gk && lastGeometryKey && gk !== lastGeometryKey) return data;
  return {
    ...lastOverlay,
    path_blend: data.path_blend ?? lastOverlay.path_blend,
    chevron_alpha: data.chevron_alpha ?? lastOverlay.chevron_alpha,
    anim_key: data.anim_key,
    frame_key: data.frame_key,
    geometry_key: gk,
    width: data.width ?? lastOverlay.width,
    height: data.height ?? lastOverlay.height,
    _animFast: true,
  };
}

function buildPathMeshes(data) {
  const allVerts = [];
  const allColors = [];

  const pathPoly = asPoints(data.path_polygon);
  if (pathPoly.length >= 4) {
    if (data.rainbow) {
      pushLaneMesh(allVerts, allColors, pathPoly, (_p, i, arr) => rainbowColor(i, arr.length), 1.06);
    } else if (data.experimental && data.path_gradient?.length) {
      const pathMinY = Math.min(...pathPoly.map((q) => q[1]));
      const pathMaxY = Math.max(...pathPoly.map((q) => q[1]));
      const stops = data.path_gradient;
      const rgbaFn = (p) => {
        const t = pathMaxY === pathMinY ? 0 : (p[1] - pathMinY) / (pathMaxY - pathMinY);
        let lo = stops[0];
        let hi = stops[stops.length - 1];
        for (let s = 0; s < stops.length - 1; s++) {
          if (t >= stops[s].pos && t <= stops[s + 1].pos) {
            lo = stops[s];
            hi = stops[s + 1];
            break;
          }
        }
        const span = Math.max(1e-6, (hi.pos ?? 1) - (lo.pos ?? 0));
        const k = (t - (lo.pos ?? 0)) / span;
        const la = lo.rgba || [13, 248, 122, 102];
        const ha = hi.rgba || la;
        return [
          (la[0] + (ha[0] - la[0]) * k) / 255,
          (la[1] + (ha[1] - la[1]) * k) / 255,
          (la[2] + (ha[2] - la[2]) * k) / 255,
          ((la[3] + (ha[3] - la[3]) * k) / 255) * (data.path_blend ?? 1),
        ];
      };
      pushLaneMesh(allVerts, allColors, pathPoly, rgbaFn, 1.08);
    } else {
      const allow = data.allow_throttle !== false;
      const blend = typeof data.path_blend === "number" ? data.path_blend : 1;
      const base = allow ? [13 / 255, 248 / 255, 122 / 255] : PATH_WHITE.slice(0, 3);
      const pathMinY = Math.min(...pathPoly.map((q) => q[1]));
      const pathMaxY = Math.max(...pathPoly.map((q) => q[1]));
      const pathAlpha = (allow ? 0.55 : 0.35) * blend;
      const rgbaFn = (p) => {
        const t = pathMaxY === pathMinY ? 0 : (p[1] - pathMinY) / (pathMaxY - pathMinY);
        const g = base[1] + (114 / 255 - base[1]) * t;
        return [base[0], g, base[2], pathAlpha * (1 - t * 0.3)];
      };
      pushLaneMesh(allVerts, allColors, pathPoly, rgbaFn, 1.07);
    }
  }

  return { allVerts, allColors };
}

function buildStaticMeshes(data) {
  const allVerts = [];
  const allColors = [];

  for (const lane of data.lanes || []) {
    const poly = asPoints(lane.polygon);
    const prob = lane.prob ?? 0.5;
    const alpha = Math.max(0.15, Math.min(0.85, prob)) * 0.7;
    if (poly.length >= 3) {
      pushLaneMesh(allVerts, allColors, poly, () => [1, 1, 1, alpha], 1.05);
    }
  }

  for (const edge of data.edges || []) {
    const poly = asPoints(edge.polygon);
    if (poly.length >= 3) {
      const std = typeof edge.std === "number" ? edge.std : 0;
      const alpha = Math.max(0, Math.min(1, 1 - std));
      pushLaneMesh(allVerts, allColors, poly, () => [1, 0, 0, alpha], 1.04);
    }
  }

  for (const lead of data.leads || []) {
    const glow = asPoints(lead.glow);
    const chevron = asPoints(lead.chevron);
    const alpha = (lead.alpha ?? 180) / 255;
    if (glow.length >= 3) {
      pushLaneMesh(allVerts, allColors, glow, () => [1, 0.77, 0, alpha * 0.18], 1.12);
      pushLaneMesh(allVerts, allColors, glow, () => [1, 0.77, 0, alpha * 0.28], 1.06);
      appendMesh(allVerts, allColors, fanTriangulate(glow, () => [1, 0.77, 0, alpha * 0.42]));
    }
    if (chevron.length >= 3) {
      pushLaneMesh(allVerts, allColors, chevron, () => [0.79, 0.13, 0.19, alpha * 0.55], 1.04);
      appendMesh(allVerts, allColors, fanTriangulate(chevron, () => [0.79, 0.13, 0.19, alpha]));
    }
  }

  return { allVerts, allColors };
}

function buildMeshes(data) {
  const staticMesh = buildStaticMeshes(data);
  const pathMesh = buildPathMeshes(data);
  return {
    allVerts: [...staticMesh.allVerts, ...pathMesh.allVerts],
    allColors: [...staticMesh.allColors, ...pathMesh.allColors],
  };
}

function buildMeshesFromCache(data) {
  const pathMesh = buildPathMeshes(data);
  if (!cachedStaticVerts?.length) return buildMeshes(data);
  return {
    allVerts: [...cachedStaticVerts, ...pathMesh.allVerts],
    allColors: [...cachedStaticColors, ...pathMesh.allColors],
  };
}

function stopRainbowLoop() {
  if (rainbowRafId != null) {
    cancelAnimationFrame(rainbowRafId);
    rainbowRafId = null;
  }
}

function scheduleRainbowLoop() {
  if (rainbowRafId != null) return;
  const tick = () => {
    rainbowRafId = null;
    if (!lastOverlay?.rainbow || !ready) return;
    rainbowHue = (rainbowHue + 2) % 360;
    drawModelWebGL({ ...lastOverlay, _animate: true, _rainbowHueOnly: true });
    rainbowRafId = requestAnimationFrame(tick);
  };
  rainbowRafId = requestAnimationFrame(tick);
}

export function initModelWebGL() {
  const host = document.getElementById("model-overlay");
  if (!host || gl) return ready;

  canvas = document.createElement("canvas");
  canvas.className = "opui-model-canvas opui-model-webgl";
  host.appendChild(canvas);
  gl = canvas.getContext("webgl2", { alpha: true, antialias: false, premultipliedAlpha: false });
  if (!gl) {
    canvas.remove();
    canvas = null;
    return false;
  }

  const vs = compileShader(gl.VERTEX_SHADER, `#version 300 es
    in vec2 a_pos;
    in vec4 a_color;
    uniform vec2 u_resolution;
    out vec4 v_color;
    void main() {
      vec2 clip = (a_pos / u_resolution) * 2.0 - 1.0;
      gl_Position = vec4(clip.x, -clip.y, 0.0, 1.0);
      v_color = a_color;
    }`);
  const fs = compileShader(gl.FRAGMENT_SHADER, `#version 300 es
    precision mediump float;
    in vec4 v_color;
    out vec4 outColor;
    void main() { outColor = v_color; }`);
  if (!vs || !fs) return false;

  prog = gl.createProgram();
  gl.attachShader(prog, vs);
  gl.attachShader(prog, fs);
  gl.linkProgram(prog);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return false;

  const rvs = compileShader(gl.VERTEX_SHADER, `#version 300 es
    in vec2 a_pos;
    in float a_hueT;
    uniform vec2 u_resolution;
    out float v_hueT;
    void main() {
      vec2 clip = (a_pos / u_resolution) * 2.0 - 1.0;
      gl_Position = vec4(clip.x, -clip.y, 0.0, 1.0);
      v_hueT = a_hueT;
    }`);
  const rfs = compileShader(gl.FRAGMENT_SHADER, `#version 300 es
    precision mediump float;
    in float v_hueT;
    uniform float u_hue;
    out vec4 outColor;
    vec3 hue2rgb(float p, float q, float t) {
      float tt = t;
      if (tt < 0.0) tt += 1.0;
      if (tt > 1.0) tt -= 1.0;
      if (tt < 1.0 / 6.0) return vec3(p + (q - p) * 6.0 * tt);
      if (tt < 1.0 / 2.0) return vec3(q);
      if (tt < 2.0 / 3.0) return vec3(p + (q - p) * (2.0 / 3.0 - tt) * 6.0);
      return vec3(p);
    }
    void main() {
      float h = mod(u_hue + v_hueT * 0.33, 1.0);
      float s = 0.95;
      float l = 0.55;
      float q = l < 0.5 ? l * (1.0 + s) : l + s - l * s;
      float p = 2.0 * l - q;
      vec3 rgb = hue2rgb(p, q, h + 1.0 / 3.0);
      outColor = vec4(rgb, 0.85);
    }`);
  if (rvs && rfs) {
    rainbowProg = gl.createProgram();
    gl.attachShader(rainbowProg, rvs);
    gl.attachShader(rainbowProg, rfs);
    gl.linkProgram(rainbowProg);
    if (gl.getProgramParameter(rainbowProg, gl.LINK_STATUS)) {
      rainbowPosLoc = gl.getAttribLocation(rainbowProg, "a_pos");
      rainbowHueTLoc = gl.getAttribLocation(rainbowProg, "a_hueT");
      rainbowResLoc = gl.getUniformLocation(rainbowProg, "u_resolution");
      rainbowHueLoc = gl.getUniformLocation(rainbowProg, "u_hue");
    } else {
      rainbowProg = null;
    }
  }

  posLoc = gl.getAttribLocation(prog, "a_pos");
  colorLoc = gl.getAttribLocation(prog, "a_color");
  resLoc = gl.getUniformLocation(prog, "u_resolution");
  vbo = gl.createBuffer();
  staticVbo = gl.createBuffer();
  gl.enable(gl.BLEND);
  gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
  if (gl.canvas) {
    gl.canvas.style.imageRendering = "auto";
  }
  ready = true;
  return true;
}

export function isModelWebGLReady() {
  return ready;
}

export function clearModelWebGL() {
  stopRainbowLoop();
  lastOverlay = null;
  lastFrameKey = null;
  lastGeometryKey = null;
  lastAnimKey = null;
  cachedStaticVerts = null;
  cachedStaticColors = null;
  rainbowPathVertCount = 0;
  rainbowPathGeometryKey = null;
  staticGpuVertCount = 0;
  if (!ready || !gl) return;
  gl.clearColor(0, 0, 0, 0);
  gl.clear(gl.COLOR_BUFFER_BIT);
}

export function drawModelWebGL(data) {
  if (!ready || !gl || !data?.ok) return false;

  if (data.clear) {
    clearModelWebGL();
    return true;
  }

  const merged = resolveAnimOverlay(data);
  const frameKey = merged.frame_key || null;
  const geometryKey = merged.geometry_key || null;
  const animKey = merged.anim_key || null;
  const animateOnly = !!merged._animate;
  const animFast = !!merged._animFast;
  const rainbowHueOnly = !!merged._rainbowHueOnly;

  if (rainbowHueOnly && lastOverlay?.rainbow) {
    const host = document.getElementById("model-overlay");
    const w = lastOverlay.width || host?.clientWidth || 1600;
    const h = lastOverlay.height || host?.clientHeight || 900;
    resize(w, h);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.useProgram(prog);
    gl.uniform2f(resLoc, canvas.width, canvas.height);
    drawOverlayMeshes(lastOverlay);
    return true;
  }

  if (!animateOnly) {
    if (animFast) {
      if (animKey && animKey === lastAnimKey) return true;
      if (animKey) lastAnimKey = animKey;
      lastOverlay = merged;
    } else {
      lastOverlay = merged;
      if (frameKey && frameKey === lastFrameKey) {
        if (merged.rainbow) scheduleRainbowLoop();
        else stopRainbowLoop();
        return true;
      }
      if (frameKey) lastFrameKey = frameKey;
      if (animKey) lastAnimKey = animKey;
      if (geometryKey && geometryKey !== lastGeometryKey) {
        const staticMesh = buildStaticMeshes(merged);
        cachedStaticVerts = staticMesh.allVerts;
        cachedStaticColors = staticMesh.allColors;
        uploadStaticGpu(cachedStaticVerts, cachedStaticColors);
        lastGeometryKey = geometryKey;
        if (merged.rainbow) syncRainbowPathGpu(merged, geometryKey);
      }
      if (merged.rainbow) scheduleRainbowLoop();
      else stopRainbowLoop();
    }
  } else if (!merged.rainbow) {
    return true;
  }

  const host = document.getElementById("model-overlay");
  const w = merged.width || host?.clientWidth || 1600;
  const h = merged.height || host?.clientHeight || 900;
  resize(w, h);

  gl.clearColor(0, 0, 0, 0);
  gl.clear(gl.COLOR_BUFFER_BIT);
  gl.useProgram(prog);
  gl.uniform2f(resLoc, canvas.width, canvas.height);

  drawOverlayMeshes(merged);
  return true;
}
