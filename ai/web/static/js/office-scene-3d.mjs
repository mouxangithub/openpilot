/**
 * OP 办公室 — Three.js 完整 3D（OrbitControls + GLTF + 动画角色）
 */
import * as THREE from '/static/vendor/three/three.module.js';
import { OrbitControls } from '/static/vendor/three/examples/jsm/controls/OrbitControls.js';
import { clone as cloneSkinned } from '/static/vendor/three/examples/jsm/utils/SkeletonUtils.js';

const IDLE_BEHAVIORS = ['desk', 'coffee', 'walk', 'stretch', 'nap'];
const STATUS_LABEL = {
  idle: '空闲',
  assigned: '已派活',
  working: '执行中',
  waiting: '待确认',
};

const AGENT_COLORS = {
  op: 0xff6b6b,
  triage: 0xfbbf24,
  tune: 0x4ecdc4,
  route: 0x60a5fa,
  adapt: 0xa78bfa,
  secoc: 0xf472b6,
  devops: 0x94a3b8,
  cloud: 0x38bdf8,
  pc: 0x34d399,
};

const ROOM = {
  floorW: 14,
  floorH: 11,
  hw: 7,
  hh: 5.5,
  deskCols: 3,
  deskGapX: 2.05,
  deskGapZ: 2.1,
  deskOriginX: -2.2,
  deskOriginZ: 0.5,
};

const ROAD = {
  aisleX: -4.85,
  tile: 1.0,
  officeMinX: -3.35,
  bedW: 2.1,
};

function wallNorthZ() {
  return -(ROOM.hh ?? ROOM.floorH / 2) + 0.18;
}

function wallSouthZ() {
  return (ROOM.hh ?? ROOM.floorH / 2) - 0.18;
}

function wallEastX() {
  return (ROOM.hw ?? ROOM.floorW / 2) - 0.18;
}

function wallWestX() {
  return -(ROOM.hw ?? ROOM.floorW / 2) + 0.18;
}

function sceneOverviewCenter() {
  const rugCx = ROOM.deskOriginX + ROOM.deskGapX;
  const rugCz = ROOM.deskOriginZ - ROOM.deskGapZ;
  return new THREE.Vector3((rugCx + ROAD.aisleX) * 0.5, 0.35, rugCz);
}

const FLOOR_PLANE = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
const _focusHit = new THREE.Vector3();
const _focusDir = new THREE.Vector3();

function setupSceneControls(ctrl, cam) {
  const center = sceneOverviewCenter();
  ctrl.target.copy(center);
  ctrl.enableDamping = true;
  ctrl.dampingFactor = 0.07;
  ctrl.enablePan = true;
  ctrl.screenSpacePanning = true;
  ctrl.zoomToCursor = true;
  ctrl.enableZoom = true;
  ctrl.zoomSpeed = 1.15;
  ctrl.panSpeed = 1.15;
  ctrl.rotateSpeed = 0.7;
  ctrl.minDistance = 2.5;
  ctrl.maxDistance = 42;
  ctrl.minPolarAngle = 0.12;
  ctrl.maxPolarAngle = Math.PI / 2.02;
  ctrl.mouseButtons = {
    LEFT: THREE.MOUSE.ROTATE,
    MIDDLE: THREE.MOUSE.PAN,
    RIGHT: THREE.MOUSE.PAN,
  };
  ctrl.touches = {
    ONE: THREE.TOUCH.ROTATE,
    TWO: THREE.TOUCH.DOLLY_PAN,
  };
  cam.position.set(center.x + 11, 13.5, center.z + 11);
  ctrl.update();
}

function resetSceneView() {
  if (!camera || !controls) return;
  setupSceneControls(controls, camera);
}

function focusCameraAt(clientX, clientY, { dollyIn = false } = {}) {
  if (!renderer || !camera || !raycaster || !pointer || !controls) return false;
  const rect = renderer.domElement.getBoundingClientRect();
  pointer.x = ((clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((clientY - rect.top) / rect.height) * 2 + 1;
  raycaster.setFromCamera(pointer, camera);
  if (!raycaster.ray.intersectPlane(FLOOR_PLANE, _focusHit)) return false;
  controls.target.copy(_focusHit);
  if (dollyIn) {
    _focusDir.subVectors(camera.position, controls.target);
    const dist = _focusDir.length();
    const next = Math.max(controls.minDistance, Math.min(dist * 0.72, controls.maxDistance * 0.45));
    camera.position.copy(controls.target).add(_focusDir.normalize().multiplyScalar(next));
  }
  controls.update();
  return true;
}

/** 区域 POI — 坐标与功能一一对应（南墙休闲区在办公室东侧，车道南端仅 Replay） */
const ZONE_POIS = {
  engage: { x: ROAD.aisleX, z: wallNorthZ() + 0.85 },
  alertWall: { x: -2.4, z: wallNorthZ() },
  ci: { x: 0.8, z: wallNorthZ() },
  routeWall: { x: 2.6, z: wallNorthZ() },
  steering: { x: 4.8, z: wallNorthZ() },
  replay: { x: ROAD.aisleX, z: wallSouthZ() - 0.5 },
  secoc: { x: wallEastX(), z: 0.5 },
  adapt: { x: 0.8, z: wallSouthZ() - 0.5 },
  cloud: { x: 2.8, z: wallSouthZ() - 0.5 },
  coffee: { x: 4.6, z: wallSouthZ() - 0.55 },
  lounge: { x: 6.1, z: wallSouthZ() - 0.55 },
  door: { x: ROAD.aisleX, z: wallNorthZ() + 0.42 },
};

const ZONE_EMOJI = {
  alertWall: '🚦',
  ci: '⚙️',
  routeWall: '🗺️',
  steering: '🎛️',
  adapt: '📡',
  cloud: '☁️',
  coffee: '☕',
  lounge: '🛋️',
  engage: '🚧',
  replay: '🏎️',
  secoc: '🔐',
  door: '🚪',
};

/** 墙面标牌 — 中文主标题 + 专员 id 副标题 */
const WALL_LABELS = {
  north: [
    { key: 'alertWall', title: '分诊告警墙', sub: '分诊员' },
    { key: 'ci', title: 'CI 流水线', sub: 'DevOps 工程师' },
    { key: 'routeWall', title: '路线分析墙', sub: '路线分析师' },
    { key: 'steering', title: '调参工位', sub: '调参师' },
  ],
  south: [
    { key: 'adapt', title: '场景适配区', sub: '适配工程师' },
    { key: 'cloud', title: '云端对接', sub: '云对接员' },
    { key: 'coffee', title: '茶水间', sub: '休息补给' },
    { key: 'lounge', title: '休息区', sub: '沙发 · 茶桌' },
  ],
  roadNorth: [
    { key: 'door', title: '正门入口', sub: '办公室' },
    { key: 'engage', title: 'Engage 闸口', sub: 'OP 主调度' },
  ],
  roadSouth: [
    { key: 'replay', title: '行程复盘', sub: 'PC 联调员' },
  ],
  east: [
    { key: 'secoc', title: 'SecOC 密钥柜', sub: 'SecOC 专员' },
  ],
};

const POIs = ZONE_POIS;

const AGENT_ZONE = {
  op: 'engage',
  triage: 'alertWall',
  tune: 'steering',
  route: 'routeWall',
  adapt: 'adapt',
  secoc: 'secoc',
  devops: 'ci',
  cloud: 'cloud',
  pc: 'replay',
};

/** 专员 → Kenney Mini Character 模型 */
const AGENT_CHARACTERS = {
  op: 'characterMaleA',
  triage: 'characterFemaleA',
  tune: 'characterMaleB',
  route: 'characterFemaleB',
  adapt: 'characterMaleC',
  secoc: 'characterFemaleC',
  devops: 'characterMaleD',
  cloud: 'characterFemaleD',
  pc: 'characterMaleE',
};

const CHARACTER_POOL = [
  'characterMaleA', 'characterMaleB', 'characterMaleC',
  'characterFemaleA', 'characterFemaleB', 'characterFemaleC',
];

/** 场景中可动画 / 可刷新的引用 */
const sceneRefs = {
  gateArms: [],
  gateLight: null,
  laneFlow: [],
  alertPanel: null,
  routeWallMat: null,
  offroadCar: null,
  trafficLight: null,
  deskScreens: [],
  ciLights: [],
  vehicleState: null,
  driving: false,
  flowPhase: 0,
};

let mount = null;
let renderer = null;
let scene = null;
let camera = null;
let controls = null;
let clock = null;
let running = false;
let rafId = 0;
let officeState = null;
let characters = new Map();
let agentRigs = new Map();
let pickables = [];
let selectedId = null;
let onSelectAgent = null;
let reducedMotion = false;
let drivingPaused = false;
let lastFrameMs = 0;
const FPS_CAP = 30;
const FPS_MS = 1000 / FPS_CAP;
let raycaster = null;
let pointer = null;
let resizeObserver = null;
let clickDrag = null;
let assetKit = null;
let initPromise = null;

function mat(color, opts = {}) {
  return new THREE.MeshStandardMaterial({
    color,
    roughness: opts.roughness ?? 0.78,
    metalness: opts.metalness ?? 0.05,
    emissive: opts.emissive || 0x000000,
    emissiveIntensity: opts.emissiveIntensity ?? 0,
    flatShading: !!opts.flat,
    transparent: !!opts.transparent,
    opacity: opts.opacity ?? 1,
  });
}

function box(w, h, d, color, opts = {}) {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat(color, opts));
  mesh.castShadow = opts.noShadow !== true;
  mesh.receiveShadow = true;
  return mesh;
}

function hashBehavior(id) {
  let h = 0;
  const s = String(id || '');
  for (let i = 0; i < s.length; i += 1) h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  return IDLE_BEHAVIORS[Math.abs(h) % IDLE_BEHAVIORS.length];
}

function deskSlot(index) {
  const col = index % ROOM.deskCols;
  const row = Math.floor(index / ROOM.deskCols);
  return {
    x: ROOM.deskOriginX + col * ROOM.deskGapX,
    z: ROOM.deskOriginZ - row * ROOM.deskGapZ,
    row,
    col,
  };
}

function workstationOffsets() {
  const deskFp = assetKit?.templates.get('desk')?.meta?.footprint ?? 0.9;
  const chairFp = assetKit?.templates.get('chair')?.meta?.footprint ?? 0.5;
  const halfDesk = deskFp * 0.5;
  const halfChair = chairFp * 0.5;
  const gap = 0.06;
  const chairZ = halfDesk + halfChair + gap;
  return {
    deskFp,
    chairZ,
    monitorZ: -halfDesk * 0.48,
    standZ: chairZ - 0.02,
  };
}

function agentDeskPos(agent, index) {
  const desk = agent?.desk || {};
  let x;
  let z;
  if (Number.isFinite(desk.col) && Number.isFinite(desk.row)) {
    x = ROOM.deskOriginX + desk.col * ROOM.deskGapX;
    z = ROOM.deskOriginZ - desk.row * ROOM.deskGapZ;
  } else {
    const slot = deskSlot(index);
    x = slot.x;
    z = slot.z;
  }
  const off = workstationOffsets();
  return { x, z, standZ: z + off.standZ };
}

function agentColor(id) {
  return AGENT_COLORS[id] || 0x4ecdc4;
}

class AssetKit {
  constructor() {
    this.templates = new Map();
    this.characterTemplates = new Map();
    this.colormapTextures = new Map();
    this.colormapUrls = new Map();
    this.gltfLoaderClass = null;
  }

  colormapKeyForModel(key, spec) {
    if (spec.character) return 'characters';
    if (/^(road|barrier|cone|streetLight|trafficLight)/.test(key)) return 'roads';
    if (/^(track|vehicle|race|flag)/.test(key)) return 'racing';
    return 'furniture';
  }

  async loadColormapFile(texLoader, base, candidates) {
    for (const rel of candidates) {
      const url = `${base}${rel}`;
      try {
        const res = await fetch(url, { method: 'HEAD' });
        if (!res.ok) continue;
        const tex = await texLoader.loadAsync(url);
        tex.colorSpace = THREE.SRGBColorSpace;
        tex.flipY = false;
        return { key: url, tex };
      } catch { /* try next */ }
    }
    return null;
  }

  async loadColormaps(base) {
    const texLoader = new THREE.TextureLoader();
    const files = {
      characters: ['textures/characters-colormap.png'],
      roads: ['textures/roads-colormap.png'],
      furniture: ['textures/furniture-colormap.png', 'textures/GLB format-colormap.png'],
      racing: ['textures/racing-colormap.png', 'textures/furniture-colormap.png', 'textures/GLB format-colormap.png'],
    };
    await Promise.all(Object.entries(files).map(async ([key, candidates]) => {
      const loaded = await this.loadColormapFile(texLoader, base, candidates);
      if (!loaded) {
        console.warn(`OfficeScene: colormap ${key} 加载失败`);
        return;
      }
      this.colormapTextures.set(key, loaded.tex);
      this.colormapUrls.set(key, loaded.key);
    }));
  }

  applyColormap(root, key) {
    const tex = this.colormapTextures.get(key);
    if (!tex) return;
    root.traverse((o) => {
      if (!o.isMesh || !o.material) return;
      const mats = Array.isArray(o.material) ? o.material : [o.material];
      const cloned = mats.map((m) => {
        const c = m.clone();
        c.map = tex;
        c.needsUpdate = true;
        return c;
      });
      o.material = Array.isArray(o.material) ? cloned : cloned[0];
    });
  }

  cloneMaterials(root) {
    root.traverse((o) => {
      if (!o.isMesh || !o.material) return;
      const mats = Array.isArray(o.material) ? o.material : [o.material];
      const cloned = mats.map((m) => m.clone());
      o.material = Array.isArray(o.material) ? cloned : cloned[0];
    });
  }

  normalizeRoot(root, footprint, opts = {}) {
    const box = new THREE.Box3().setFromObject(root);
    const size = new THREE.Vector3();
    const center = new THREE.Vector3();
    box.getSize(size);
    box.getCenter(center);
    root.position.set(-center.x, -box.min.y, -center.z);
    root.updateMatrixWorld(true);
    box.setFromObject(root);
    box.getSize(size);
    if (opts.height) {
      const s = opts.height / Math.max(size.y, 0.001);
      root.scale.setScalar(s);
    } else {
      const fp = footprint || Math.max(size.x, size.z, 0.001);
      const s = fp / Math.max(size.x, size.z, 0.001);
      root.scale.setScalar(s);
    }
    root.updateMatrixWorld(true);
    box.setFromObject(root);
    return { footprint: footprint || Math.max(size.x, size.z), height: box.max.y - box.min.y };
  }

  async ensureLoaderClass() {
    if (this.gltfLoaderClass) return this.gltfLoaderClass;
    try {
      const mod = await import('/static/vendor/three/examples/jsm/loaders/GLTFLoader.js');
      this.gltfLoaderClass = mod.GLTFLoader;
    } catch (e) {
      console.warn('OfficeScene: GLTFLoader unavailable, using procedural props only', e);
      this.gltfLoaderClass = null;
    }
    return this.gltfLoaderClass;
  }

  createModelLoader(cmapKey) {
    const LoaderClass = this.gltfLoaderClass;
    if (!LoaderClass) return null;
    const colormapUrl = this.colormapUrls.get(cmapKey);
    if (!colormapUrl) return new LoaderClass();
    const manager = new THREE.LoadingManager();
    manager.setURLModifier((url) => (
      /colormap\.png$/i.test(url) ? colormapUrl : url
    ));
    return new LoaderClass(manager);
  }

  async load() {
    let manifest = { models: {} };
    try {
      const res = await fetch('/static/vendor/office/manifest.json');
      if (res.ok) manifest = await res.json();
    } catch { /* procedural only */ }

    const LoaderClass = await this.ensureLoaderClass();
    if (!LoaderClass) return;

    const base = manifest.base || '/static/vendor/office/';
    await this.loadColormaps(base);
    const entries = Object.entries(manifest.models || {});
    await Promise.all(entries.map(async ([key, spec]) => {
      const url = `${base}${spec.file}`;
      const cmap = this.colormapKeyForModel(key, spec);
      const loader = this.createModelLoader(cmap);
      if (!loader) return;
      try {
        const gltf = await loader.loadAsync(url);
        const root = gltf.scene;
        this.applyColormap(root, cmap);
        root.traverse((o) => {
          if (o.isMesh) {
            o.castShadow = true;
            o.receiveShadow = true;
          }
        });
        const footprint = spec.footprint ?? spec.scale ?? 1;
        const meta = this.normalizeRoot(root, footprint, { height: spec.height });
        const entry = { root, spec, meta, animations: gltf.animations || [] };
        if (spec.character) this.characterTemplates.set(key, entry);
        else this.templates.set(key, entry);
      } catch {
        if (spec?.character) this.characterTemplates.set(key, null);
        else this.templates.set(key, null);
      }
    }));
  }

  clone(key, x, z, rotY = 0, scaleMul = 1) {
    const tpl = this.templates.get(key);
    if (!tpl?.root) return null;
    const g = tpl.root.clone(true);
    if (scaleMul !== 1) g.scale.multiplyScalar(scaleMul);
    g.position.set(x, tpl.spec.y || 0, z);
    g.rotation.y = rotY;
    scene.add(g);
    return g;
  }

  has(key) {
    return !!this.templates.get(key)?.root;
  }

  hasCharacter(key) {
    return !!this.characterTemplates.get(key)?.root;
  }

  cloneCharacter(key) {
    const tpl = this.characterTemplates.get(key);
    if (!tpl?.root) return null;
    const model = cloneSkinned(tpl.root);
    this.cloneMaterials(model);
    model.position.set(0, 0, 0);
    model.rotation.set(0, 0, 0);
    model.scale.copy(tpl.root.scale);
    const mixer = new THREE.AnimationMixer(model);
    const clips = {};
    for (const clip of tpl.animations) {
      const clonedClip = clip.clone();
      clips[clonedClip.name] = mixer.clipAction(clonedClip);
    }
    return { model, mixer, clips, meta: tpl.meta };
  }
}

function placeAsset(key, x, z, rotY = 0, scaleMul = 1) {
  return assetKit?.clone(key, x, z, rotY, scaleMul) || null;
}

function placeAssetLocal(parent, key, lx, lz, rotY = 0, scaleMul = 1) {
  const tpl = assetKit?.templates.get(key);
  if (!tpl?.root || !parent) return null;
  const g = tpl.root.clone(true);
  if (scaleMul !== 1) g.scale.multiplyScalar(scaleMul);
  g.position.set(lx, tpl.spec.y || 0, lz);
  g.rotation.y = rotY;
  parent.add(g);
  return g;
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

function createEmojiSprite(emoji, scale = 0.58) {
  const size = 96;
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d');
  ctx.font = `${Math.round(size * 0.72)}px "Segoe UI Emoji", "Apple Color Emoji", sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(emoji, size / 2, size / 2 + 4);
  const tex = new THREE.CanvasTexture(canvas);
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: false }));
  sprite.scale.set(scale, scale, 1);
  sprite.renderOrder = 10;
  return sprite;
}

function createLabelSprite(lines, { active = false, selected = false, compact = false } = {}) {
  const padY = compact ? 5 : 6;
  const lineH = compact ? 14 : 16;
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  const width = compact ? 168 : 190;
  const height = padY * 2 + lineH * lines.length;
  canvas.width = width;
  canvas.height = height;
  ctx.fillStyle = selected
    ? 'rgba(78, 205, 196, 0.24)'
    : (active ? 'rgba(74, 222, 128, 0.18)' : 'rgba(15, 23, 42, 0.78)');
  ctx.strokeStyle = selected
    ? 'rgba(78, 205, 196, 0.85)'
    : (active ? 'rgba(74, 222, 128, 0.55)' : 'rgba(148, 163, 184, 0.35)');
  ctx.lineWidth = 1.5;
  roundRect(ctx, 1, 1, width - 2, height - 2, 8);
  ctx.fill();
  ctx.stroke();
  ctx.textAlign = 'center';
  lines.forEach((line, i) => {
    const y = padY + lineH * i + lineH * 0.72;
    ctx.font = i === 0
      ? `600 ${compact ? 12 : 13}px system-ui, sans-serif`
      : `${compact ? 10 : 11}px system-ui, sans-serif`;
    ctx.fillStyle = i === 0 ? '#f1f5f9' : (active ? '#86efac' : '#94a3b8');
    ctx.fillText(line, width / 2, y);
  });
  const tex = new THREE.CanvasTexture(canvas);
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: false }));
  const scaleY = compact ? 1.05 : 1.2;
  sprite.scale.set(scaleY * (width / height), scaleY, 1);
  sprite.position.y = compact ? 1.35 : 1.48;
  sprite.renderOrder = 11;
  return sprite;
}

function createAreaSign(title, emoji, sub = '', opts = {}) {
  const canvas = document.createElement('canvas');
  canvas.width = 168;
  canvas.height = sub ? 54 : 44;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = 'rgba(15, 23, 42, 0.82)';
  roundRect(ctx, 2, 2, 164, canvas.height - 4, 8);
  ctx.fill();
  ctx.strokeStyle = 'rgba(148, 163, 184, 0.35)';
  ctx.lineWidth = 1;
  roundRect(ctx, 2, 2, 164, canvas.height - 4, 8);
  ctx.stroke();
  ctx.font = '16px "Segoe UI Emoji", sans-serif';
  ctx.fillText(emoji, 14, sub ? 26 : 28);
  ctx.font = '600 11px system-ui, sans-serif';
  ctx.fillStyle = '#e2e8f0';
  ctx.fillText(title, 36, sub ? 24 : 28);
  if (sub) {
    ctx.font = '9px system-ui, sans-serif';
    ctx.fillStyle = '#94a3b8';
    ctx.fillText(sub, 36, 40);
  }
  const tex = new THREE.CanvasTexture(canvas);
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({
    map: tex,
    transparent: true,
    depthTest: opts.depthTest ?? true,
  }));
  const scaleY = 0.32 * (canvas.height / 44);
  sprite.scale.set(1.05, scaleY, 1);
  sprite.position.y = opts.y ?? 1.55;
  return sprite;
}

function mountWallSign(wall, key, title, sub = '') {
  const poi = ZONE_POIS[key];
  if (!poi) return null;
  const emoji = ZONE_EMOJI[key] || '📍';
  const sign = createAreaSign(title, emoji, sub);
  const y = 1.78;
  if (wall === 'north') sign.position.set(poi.x, y, wallNorthZ() + 0.38);
  else if (wall === 'south') sign.position.set(poi.x, y, wallSouthZ() - 0.32);
  else if (wall === 'east') sign.position.set(wallEastX() - 0.35, y, poi.z);
  else if (wall === 'roadNorth') {
    const zOff = key === 'door' ? 0.48 : key === 'engage' ? 0.92 : 0.62;
    sign.position.set(poi.x, y, wallNorthZ() + zOff);
  } else if (wall === 'roadSouth') sign.position.set(poi.x, y, wallSouthZ() - 0.62);
  scene.add(sign);
  return sign;
}

function buildWallLabels() {
  for (const { key, title, sub } of WALL_LABELS.north) mountWallSign('north', key, title, sub);
  for (const { key, title, sub } of WALL_LABELS.south) mountWallSign('south', key, title, sub);
  for (const { key, title, sub } of WALL_LABELS.roadNorth) mountWallSign('roadNorth', key, title, sub);
  for (const { key, title, sub } of WALL_LABELS.roadSouth) mountWallSign('roadSouth', key, title, sub);
  for (const { key, title, sub } of WALL_LABELS.east) mountWallSign('east', key, title, sub);
}

function createZonePin(emoji) {
  const sprite = createEmojiSprite(emoji, 0.38);
  sprite.position.y = 0.1;
  return sprite;
}

function createScreenTexture(kind, extra = '') {
  const w = 256;
  const h = 144;
  const canvas = document.createElement('canvas');
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext('2d');
  const grad = ctx.createLinearGradient(0, 0, w, h);
  grad.addColorStop(0, '#0f172a');
  grad.addColorStop(1, '#1e293b');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, w, h);

  if (kind === 'route') {
    ctx.strokeStyle = '#4ecdc4';
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(24, 110);
    for (let i = 0; i < 8; i += 1) {
      const x = 24 + i * 28;
      const y = 110 - Math.sin(i * 0.9) * 42 - i * 4;
      ctx.lineTo(x, y);
    }
    ctx.stroke();
    ctx.fillStyle = '#86efac';
    ctx.beginPath();
    ctx.arc(210, 38, 6, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = '#94a3b8';
    ctx.font = '600 13px system-ui,sans-serif';
    ctx.fillText('ROUTE · qlog', 14, 24);
  } else if (kind === 'comma') {
    ctx.fillStyle = '#4ecdc4';
    ctx.font = '700 28px system-ui,sans-serif';
    ctx.fillText('comma', 18, 52);
    ctx.fillStyle = '#94a3b8';
    ctx.font = '12px system-ui,sans-serif';
    ctx.fillText('openpilot · AGNOS', 18, 76);
    ctx.strokeStyle = 'rgba(78,205,196,0.5)';
    ctx.strokeRect(12, 12, w - 24, h - 24);
  } else if (kind === 'alert') {
    ctx.fillStyle = '#fbbf24';
    ctx.font = '600 14px system-ui,sans-serif';
    const lines = (extra || '无告警').slice(0, 48);
    ctx.fillText(lines, 14, 40, w - 28);
    ctx.fillStyle = '#64748b';
    ctx.font = '11px system-ui,sans-serif';
    ctx.fillText('ALERT · triage', 14, 22);
  } else if (kind === 'tool') {
    ctx.fillStyle = '#4ade80';
    ctx.font = '600 13px monospace';
    const tool = (extra || 'running…').slice(0, 40);
    ctx.fillText(tool, 14, 56, w - 28);
    ctx.fillStyle = '#64748b';
    ctx.font = '11px system-ui,sans-serif';
    ctx.fillText('TOOL EXEC', 14, 28);
    const barW = (w - 28) * (0.35 + 0.25 * Math.sin(performance.now() / 200));
    ctx.fillStyle = 'rgba(74,222,128,0.35)';
    ctx.fillRect(14, 72, barW, 8);
  } else {
    ctx.fillStyle = '#4ecdc4';
    ctx.font = '12px system-ui,sans-serif';
    ctx.fillText('OP DESK', 14, 40);
  }

  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

function refreshAlertPanel() {
  if (!sceneRefs.alertPanel) return;
  const alert = sceneRefs.vehicleState?.alert_text1
    || sceneRefs.vehicleState?.alertText1
    || '待机 · 无告警';
  const tex = createScreenTexture('alert', alert);
  const old = sceneRefs.alertPanel.material.map;
  sceneRefs.alertPanel.material.map = tex;
  sceneRefs.alertPanel.material.needsUpdate = true;
  old?.dispose?.();
}

function refreshRouteWall() {
  if (!sceneRefs.routeWallMat) return;
  const tex = createScreenTexture('route');
  const old = sceneRefs.routeWallMat.map;
  sceneRefs.routeWallMat.map = tex;
  sceneRefs.routeWallMat.needsUpdate = true;
  old?.dispose?.();
}

function pulseDeskScreens(toolName) {
  for (const entry of sceneRefs.deskScreens) {
    const tex = createScreenTexture('tool', toolName || '…');
    const old = entry.mat.map;
    entry.mat.map = tex;
    entry.mat.emissive = new THREE.Color(0x4ade80);
    entry.mat.emissiveIntensity = 0.35;
    entry.mat.needsUpdate = true;
    entry.pulseT = 2.5;
    old?.dispose?.();
  }
}

function updateGateFromVehicle() {
  const vs = sceneRefs.vehicleState || {};
  const active = !!vs.active;
  const engageable = !!vs.engageable;
  const enabled = !!vs.enabled;
  const open = active || (engageable && !enabled);
  let color = 0x94a3b8;
  if (active) color = 0x4ade80;
  else if (engageable) color = 0xfbbf24;
  else if (enabled) color = 0x60a5fa;
  const angle = open ? Math.PI / 2.2 : 0.12;
  sceneRefs.gateArms.forEach((arm, i) => {
    arm.rotation.y = (i === 0 ? 1 : -1) * angle;
  });
  if (sceneRefs.gateLight) {
    sceneRefs.gateLight.material.emissive.setHex(color);
    sceneRefs.gateLight.material.emissiveIntensity = active ? 0.85 : 0.45;
  }
  if (sceneRefs.trafficLight) {
    sceneRefs.trafficLight.traverse((o) => {
      if (!o.isMesh || !o.material) return;
      const mats = Array.isArray(o.material) ? o.material : [o.material];
      mats.forEach((m) => {
        if (!m.emissive) return;
        m.emissive.setHex(color);
        m.emissiveIntensity = active ? 0.9 : engageable ? 0.55 : 0.25;
      });
    });
  }
}

function proceduralCar(x, z, rotY = 0) {
  const g = new THREE.Group();
  g.position.set(x, 0, z);
  g.rotation.y = rotY;
  const body = box(1.6, 0.42, 3.2, 0x334155, { metalness: 0.35, roughness: 0.55 });
  body.position.y = 0.38;
  g.add(body);
  const cabin = box(1.35, 0.38, 1.5, 0x1e293b, { metalness: 0.2 });
  cabin.position.set(0, 0.78, -0.15);
  g.add(cabin);
  const windshield = new THREE.Mesh(
    new THREE.PlaneGeometry(1.2, 0.32),
    new THREE.MeshStandardMaterial({ color: 0x7dd3fc, transparent: true, opacity: 0.55, metalness: 0.1 }),
  );
  windshield.position.set(0, 0.82, 0.58);
  windshield.rotation.x = -0.35;
  g.add(windshield);
  [[-0.72, 0.18, 1.0], [0.72, 0.18, 1.0], [-0.72, 0.18, -1.0], [0.72, 0.18, -1.0]].forEach(([wx, wy, wz]) => {
    const wheel = new THREE.Mesh(new THREE.CylinderGeometry(0.22, 0.22, 0.14, 14), mat(0x0f172a, { metalness: 0.5 }));
    wheel.rotation.z = Math.PI / 2;
    wheel.position.set(wx, wy, wz);
    g.add(wheel);
  });
  const comma = new THREE.Mesh(
    new THREE.PlaneGeometry(0.5, 0.12),
    new THREE.MeshBasicMaterial({ color: 0x4ecdc4 }),
  );
  comma.position.set(0, 0.55, 1.62);
  g.add(comma);
  return g;
}

function createAccessory(agentId, color) {
  const g = new THREE.Group();
  const c = color;
  switch (agentId) {
    case 'op': {
      const ring = new THREE.Mesh(new THREE.TorusGeometry(0.14, 0.02, 8, 20), mat(c, { emissive: c, emissiveIntensity: 0.3 }));
      ring.rotation.x = Math.PI / 2;
      ring.position.y = 0.98;
      g.add(ring);
      break;
    }
    case 'triage': {
      const cone = new THREE.Mesh(new THREE.ConeGeometry(0.12, 0.22, 4), mat(0xfbbf24, { flat: true }));
      cone.position.y = 1.05;
      g.add(cone);
      break;
    }
    case 'tune': {
      for (let i = -1; i <= 1; i += 1) {
        const knob = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.04, 0.03, 10), mat(c));
        knob.position.set(i * 0.09, 0.72, 0.14);
        g.add(knob);
      }
      break;
    }
    case 'route': {
      const chart = box(0.18, 0.24, 0.02, 0xffffff);
      chart.position.set(0.22, 0.75, 0.1);
      g.add(chart);
      break;
    }
    case 'adapt': {
      const bar = box(0.28, 0.04, 0.04, 0x94a3b8, { metalness: 0.5 });
      bar.position.set(0.2, 0.78, 0.08);
      bar.rotation.z = Math.PI / 4;
      g.add(bar);
      break;
    }
    case 'secoc': {
      const lock = box(0.1, 0.12, 0.05, c, { metalness: 0.3 });
      lock.position.set(0, 0.95, 0.12);
      g.add(lock);
      break;
    }
    case 'devops': {
      const gear = new THREE.Mesh(new THREE.TorusGeometry(0.08, 0.025, 8, 16), mat(0x94a3b8, { metalness: 0.4 }));
      gear.position.set(0.18, 0.92, 0.1);
      g.add(gear);
      break;
    }
    case 'cloud': {
      [[0, 0], [-0.07, 0.03], [0.07, 0.03]].forEach(([x, z]) => {
        const puff = new THREE.Mesh(new THREE.SphereGeometry(0.06, 8, 8), mat(0x38bdf8, { flat: true }));
        puff.position.set(x, 1.0, z);
        g.add(puff);
      });
      break;
    }
    case 'pc': {
      const laptop = box(0.22, 0.02, 0.16, 0x334155);
      laptop.position.set(0.2, 0.72, 0.12);
      g.add(laptop);
      break;
    }
    default:
      break;
  }
  return g;
}

function characterKeyForAgent(id) {
  if (AGENT_CHARACTERS[id]) return AGENT_CHARACTERS[id];
  let h = 0;
  const s = String(id || '');
  for (let i = 0; i < s.length; i += 1) h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  return CHARACTER_POOL[Math.abs(h) % CHARACTER_POOL.length];
}

function setCharacterAction(rig, name, fade = 0.18) {
  const action = rig.clips?.[name] || rig.clips?.idle;
  if (!action || rig.currentClip === name) return;
  if (rig.currentAction) rig.currentAction.fadeOut(fade);
  action.reset().setEffectiveWeight(1).fadeIn(fade).play();
  rig.currentAction = action;
  rig.currentClip = name;
}

function playGlbAnimation(rig, ch, walking) {
  let clip = 'idle';
  if (walking) clip = 'walk';
  else if (ch.status === 'working') clip = 'interact-right';
  else if (ch.status === 'idle' && ch.behavior === 'nap') clip = 'sit';
  setCharacterAction(rig, clip);
}

function createAgentRig(ch) {
  try {
    const charKey = characterKeyForAgent(ch.id);
    if (assetKit?.hasCharacter(charKey)) {
      const inst = assetKit.cloneCharacter(charKey);
      if (inst) return createGlbAgentRig(ch, inst);
    }
  } catch (e) {
    console.warn('OfficeScene: Kenney 角色加载失败，回退方块人', ch.id, e);
  }
  return createProceduralAgentRig(ch);
}

function createGlbAgentRig(ch, inst) {
  const group = new THREE.Group();
  group.userData.agentId = ch.id;
  const headY = (inst.meta?.height || 0.95) * 0.92;

  const shadow = new THREE.Mesh(
    new THREE.CircleGeometry(0.3, 24),
    new THREE.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.24 }),
  );
  shadow.rotation.x = -Math.PI / 2;
  shadow.position.y = 0.02;
  group.add(shadow);

  inst.model.traverse((o) => {
    if (o.isMesh) {
      o.castShadow = true;
      o.receiveShadow = true;
    }
  });
  group.add(inst.model);

  const emoji = createEmojiSprite(ch.icon, 0.5);
  emoji.position.y = headY;

  const ring = new THREE.Mesh(
    new THREE.RingGeometry(0.36, 0.42, 32),
    new THREE.MeshBasicMaterial({ color: 0x94a3b8, transparent: true, opacity: 0.5, side: THREE.DoubleSide }),
  );
  ring.rotation.x = -Math.PI / 2;
  ring.position.y = 0.025;

  const hit = new THREE.Mesh(
    new THREE.CylinderGeometry(0.36, 0.36, headY, 12),
    new THREE.MeshBasicMaterial({ visible: false }),
  );
  hit.position.y = headY * 0.5;
  hit.userData.agentId = ch.id;

  [emoji, ring, hit].forEach((o) => group.add(o));
  pickables.push(hit);
  scene.add(group);

  const rig = {
    kind: 'gltf',
    group,
    mixer: inst.mixer,
    clips: inst.clips,
    currentAction: null,
    currentClip: '',
    headY,
    parts: { emoji, ring, hit },
    label: null,
    labelSig: '',
  };
  setCharacterAction(rig, 'idle', 0);
  agentRigs.set(ch.id, rig);
  return rig;
}

function createProceduralAgentRig(ch) {
  const group = new THREE.Group();
  group.userData.agentId = ch.id;

  const shadow = new THREE.Mesh(
    new THREE.CircleGeometry(0.3, 24),
    new THREE.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.24 }),
  );
  shadow.rotation.x = -Math.PI / 2;
  shadow.position.y = 0.02;
  group.add(shadow);

  const bodyMat = mat(0x1e293b, { roughness: 0.55 });
  const legGeo = new THREE.CylinderGeometry(0.065, 0.07, 0.4, 8);
  legGeo.translate(0, -0.2, 0);
  const legL = new THREE.Mesh(legGeo, bodyMat);
  legL.position.set(-0.11, 0.42, 0);
  legL.castShadow = true;
  const legR = legL.clone();
  legR.position.x = 0.11;

  const torso = new THREE.Mesh(new THREE.CylinderGeometry(0.22, 0.26, 0.44, 12), bodyMat);
  torso.position.y = 0.68;
  torso.castShadow = true;

  const armGeo = new THREE.CylinderGeometry(0.045, 0.05, 0.32, 8);
  armGeo.translate(0, -0.16, 0);
  const armL = new THREE.Mesh(armGeo, bodyMat);
  armL.position.set(-0.28, 0.82, 0);
  armL.rotation.z = 0.25;
  const armR = armL.clone();
  armR.position.x = 0.28;
  armR.rotation.z = -0.25;

  const head = new THREE.Mesh(new THREE.SphereGeometry(0.19, 16, 16), mat(0x0f172a, { roughness: 0.4 }));
  head.position.y = 1.02;
  head.castShadow = true;

  const scarf = new THREE.Mesh(
    new THREE.TorusGeometry(0.22, 0.045, 10, 24),
    mat(ch.color, { emissive: ch.color, emissiveIntensity: 0.28, roughness: 0.4 }),
  );
  scarf.rotation.x = Math.PI / 2;
  scarf.position.y = 0.82;

  const emoji = createEmojiSprite(ch.icon);
  emoji.position.y = 1.02;

  const ring = new THREE.Mesh(
    new THREE.RingGeometry(0.36, 0.42, 32),
    new THREE.MeshBasicMaterial({ color: 0x94a3b8, transparent: true, opacity: 0.5, side: THREE.DoubleSide }),
  );
  ring.rotation.x = -Math.PI / 2;
  ring.position.y = 0.025;

  const accessory = createAccessory(ch.id, ch.color);
  const hit = new THREE.Mesh(
    new THREE.CylinderGeometry(0.36, 0.36, 1.2, 12),
    new THREE.MeshBasicMaterial({ visible: false }),
  );
  hit.position.y = 0.6;
  hit.userData.agentId = ch.id;

  [legL, legR, torso, armL, armR, head, scarf, emoji, ring, accessory, hit].forEach((o) => group.add(o));
  pickables.push(hit);
  scene.add(group);

  const rig = {
    kind: 'procedural',
    group,
    parts: { legL, legR, armL, armR, torso, head, scarf, emoji, ring, accessory, hit },
    headY: 1.02,
    label: null,
    labelSig: '',
  };
  agentRigs.set(ch.id, rig);
  return rig;
}

function animateRig(rig, ch, walking) {
  if (rig.kind === 'gltf') {
    playGlbAnimation(rig, ch, walking);
    return;
  }
  const { parts } = rig;
  if (walking) {
    const swing = Math.sin(ch.walkT) * 0.65;
    parts.legL.rotation.x = swing;
    parts.legR.rotation.x = -swing;
    parts.armL.rotation.x = -swing * 0.55;
    parts.armR.rotation.x = swing * 0.55;
    parts.torso.rotation.z = Math.sin(ch.walkT * 0.5) * 0.04;
  } else {
    parts.legL.rotation.x = 0;
    parts.legR.rotation.x = 0;
    parts.armL.rotation.x = ch.status === 'working' ? -0.35 : 0;
    parts.armR.rotation.x = ch.status === 'working' ? -0.35 : 0;
    parts.torso.rotation.z = 0;
  }

  if (ch.status === 'idle' && ch.behavior === 'nap' && !walking) {
    parts.torso.rotation.x = 0.35;
    parts.head.position.y = 0.88;
  } else {
    parts.torso.rotation.x = 0;
    parts.head.position.y = 1.02;
  }
}

function buildWorkstation(x, z, screenKind = 'comma') {
  const hasDesk = assetKit?.has('desk');
  if (!hasDesk) {
    proceduralDesk(x, z, screenKind);
    return;
  }
  const off = workstationOffsets();
  const deskH = assetKit?.templates.get('desk')?.meta?.height || 0.42;
  const ws = new THREE.Group();
  ws.position.set(x, 0, z);
  placeAssetLocal(ws, 'desk', 0, 0, 0);
  placeAssetLocal(ws, 'chair', 0, off.chairZ, Math.PI);
  placeAssetLocal(ws, 'monitor', 0, off.monitorZ, 0, 0.82);
  const screen = new THREE.Mesh(
    new THREE.PlaneGeometry(0.34, 0.2),
    new THREE.MeshStandardMaterial({
      map: createScreenTexture(screenKind === 'route' ? 'route' : 'comma'),
      emissive: 0x4ecdc4,
      emissiveIntensity: 0.15,
      roughness: 0.35,
    }),
  );
  screen.position.set(0, deskH + 0.1, off.monitorZ - 0.06);
  ws.add(screen);
  sceneRefs.deskScreens.push({ mat: screen.material, pulseT: 0 });
  scene.add(ws);
}

function proceduralDesk(x, z, screenKind = 'comma') {
  const g = new THREE.Group();
  g.position.set(x, 0, z);
  const top = box(1.6, 0.08, 0.85, 0xf8fafc, { flat: true });
  top.position.y = 0.76;
  g.add(top);
  [[-0.65, -0.32], [0.65, -0.32], [-0.65, 0.32], [0.65, 0.32]].forEach(([lx, lz]) => {
    const leg = box(0.08, 0.76, 0.08, 0xcbd5e1);
    leg.position.set(lx, 0.38, lz);
    g.add(leg);
  });
  const screen = new THREE.Mesh(
    new THREE.PlaneGeometry(0.48, 0.28),
    new THREE.MeshStandardMaterial({
      map: createScreenTexture(screenKind === 'route' ? 'route' : 'comma'),
      emissive: 0x4ecdc4,
      emissiveIntensity: 0.12,
      roughness: 0.4,
    }),
  );
  screen.position.set(0, 1.05, -0.168);
  g.add(screen);
  sceneRefs.deskScreens.push({ mat: screen.material, pulseT: 0 });
  const seat = box(0.44, 0.08, 0.44, 0x475569);
  seat.position.set(0, 0.44, 0.58);
  g.add(seat);
  scene.add(g);
}

function buildBreakRoom() {
  const { x, z } = ZONE_POIS.coffee;
  placeAsset('coffeeMachine', x - 0.3, z, 0);
  placeAsset('coffeeTable', x + 0.55, z + 0.35, 0);
  placeAsset('plant', x + 1.05, z - 0.25, -Math.PI / 6, 0.75);
}

function buildLounge() {
  const { x, z } = ZONE_POIS.lounge;
  placeAsset('sofa', x, z, Math.PI);
  placeAsset('coffeeTable', x - 0.85, z + 0.35, Math.PI / 2);
  placeAsset('plant', x + 0.55, z + 0.3, 0, 0.75);
}

function buildReplayTrack() {
  const { x, z } = ZONE_POIS.replay;
  if (assetKit?.has('trackStraight')) {
    placeAsset('trackStraight', x, z, Math.PI / 2);
    placeAsset('trackCorner', x, z - 1.05, 0);
    placeAsset('flagCheckers', x + 0.55, z - 0.35, 0);
    placeAsset('raceBarrier', x + 0.9, z + 0.15, Math.PI);
    placeAsset('cone', x + 0.55, z + 0.45, 0);
  }
  if (assetKit?.has('vehicle')) {
    placeAsset('vehicle', x - 0.15, z + 1.1, Math.PI / 2, 0.82);
  }
}

function buildWallsAndWindows() {
  const h = 2.7;
  const hw = ROOM.hw ?? ROOM.floorW / 2;
  const hh = ROOM.hh ?? ROOM.floorH / 2;

  const back = box(ROOM.floorW + 0.12, h, 0.12, 0xffffff, { flat: true });
  back.position.set(0, h / 2, -hh);
  scene.add(back);

  const left = box(0.12, h, ROOM.floorH, 0xf8fafc, { flat: true });
  left.position.set(-hw, h / 2, 0);
  scene.add(left);

  const right = box(0.12, h, ROOM.floorH, 0xf8fafc, { flat: true });
  right.position.set(hw, h / 2, 0);
  scene.add(right);

  const glass = new THREE.Mesh(
    new THREE.PlaneGeometry(2.2, 1.0),
    new THREE.MeshPhysicalMaterial({
      color: 0xbae6fd,
      transparent: true,
      opacity: 0.35,
      roughness: 0.05,
      metalness: 0,
      transmission: 0.55,
      thickness: 0.2,
    }),
  );
  glass.position.set(0.2, 1.32, -hh + 0.08);
  scene.add(glass);
}

function buildFloor() {
  const hh = ROOM.hh ?? ROOM.floorH / 2;
  const rx = ROAD.aisleX;
  const t = ROAD.tile;

  const floor = new THREE.Mesh(
    new THREE.PlaneGeometry(ROOM.floorW + 2, ROOM.floorH + 2),
    mat(0x0b1220, { roughness: 0.98 }),
  );
  floor.rotation.x = -Math.PI / 2;
  floor.receiveShadow = true;
  scene.add(floor);

  const roadBed = new THREE.Mesh(
    new THREE.PlaneGeometry(ROAD.bedW, ROOM.floorH + 0.5),
    mat(0x4a5568, { roughness: 0.85 }),
  );
  roadBed.rotation.x = -Math.PI / 2;
  roadBed.position.set(rx, 0.008, 0);
  scene.add(roadBed);

  const officeMinX = ROAD.officeMinX;
  const officeW = wallEastX() - officeMinX + 0.25;
  const officeBed = new THREE.Mesh(
    new THREE.PlaneGeometry(officeW, ROOM.floorH - 0.6),
    mat(0x1a2433, { roughness: 0.95 }),
  );
  officeBed.rotation.x = -Math.PI / 2;
  officeBed.position.set(officeMinX + officeW * 0.5, 0.005, 0);
  scene.add(officeBed);

  const rugCx = ROOM.deskOriginX + ROOM.deskGapX;
  const rugCz = ROOM.deskOriginZ - ROOM.deskGapZ;
  const rug = new THREE.Mesh(new THREE.PlaneGeometry(4.8, 5.2), mat(0x243044, { roughness: 1 }));
  rug.rotation.x = -Math.PI / 2;
  rug.position.set(rugCx, 0.01, rugCz);
  scene.add(rug);

  const hasRoads = assetKit?.has('roadStraight');
  if (hasRoads) {
    for (let z = Math.ceil(-hh); z <= Math.floor(hh); z += 1) {
      const tile = placeAsset('roadStraight', rx, z, 0);
      if (tile) tile.position.y = 0.02;
    }
    const egZ = ZONE_POIS.engage.z;
    const cross = placeAsset('roadCrossroadPath', rx, Math.round(egZ), 0);
    if (cross) cross.position.y = 0.02;
    const end = placeAsset('roadEnd', rx, -hh - 0.55, 0);
    if (end) end.position.y = 0.02;
    placeAsset('streetLight', rx - 0.9, egZ, Math.PI / 2);
    placeAsset('streetLight', rx - 0.9, hh - 0.7, Math.PI / 2);
    placeAsset('cone', rx + 0.55, egZ + 0.55, 0);
    placeAsset('cone', rx + 0.55, egZ - 0.55, 0);
  } else {
    const grid = new THREE.GridHelper(ROOM.floorW, 14, 0x334155, 0x1e293b);
    grid.position.y = 0.01;
    grid.material.transparent = true;
    grid.material.opacity = 0.22;
    scene.add(grid);
  }

  if (assetKit?.has('vehicle')) {
    sceneRefs.offroadCar = placeAsset('vehicle', rx, 1.4, Math.PI / 2, 0.88);
    if (sceneRefs.offroadCar) sceneRefs.offroadCar.position.y = 0.025;
  }

  const dashMat = new THREE.MeshBasicMaterial({
    color: 0xfbbf24,
    transparent: true,
    opacity: 0.7,
    side: THREE.DoubleSide,
  });
  for (let i = -3; i <= 3; i += 1) {
    const stripe = new THREE.Mesh(new THREE.PlaneGeometry(0.1, 0.7), dashMat.clone());
    stripe.rotation.x = -Math.PI / 2;
    stripe.position.set(rx, 0.022, i * t);
    scene.add(stripe);
    sceneRefs.laneFlow.push(stripe);
  }
  [-0.55, 0.55].forEach((lx) => {
    const edge = new THREE.Mesh(
      new THREE.PlaneGeometry(0.06, ROOM.floorH - 1),
      new THREE.MeshBasicMaterial({ color: 0xf8fafc, transparent: true, opacity: 0.4, side: THREE.DoubleSide }),
    );
    edge.rotation.x = -Math.PI / 2;
    edge.position.set(rx + lx, 0.021, 0);
    scene.add(edge);
    sceneRefs.laneFlow.push(edge);
  });
}

function buildEngageGate() {
  const g = new THREE.Group();
  const { x, z } = ZONE_POIS.engage;
  placeAsset('barrier', x - 0.65, z + 0.15, Math.PI / 2);
  placeAsset('barrier', x + 0.65, z + 0.15, -Math.PI / 2);
  const tl = placeAsset('trafficLight', x, z, Math.PI);
  sceneRefs.trafficLight = tl;
  if (!tl) {
    const postL = box(0.14, 1.1, 0.14, 0x64748b, { metalness: 0.4 });
    postL.position.set(x - 1.1, 0.55, z);
    const postR = postL.clone();
    postR.position.x = x + 1.1;
    g.add(postL, postR);
    const armGeo = new THREE.BoxGeometry(1.05, 0.08, 0.1);
    const armMat = mat(0xfbbf24, { emissive: 0xfbbf24, emissiveIntensity: 0.35, metalness: 0.3 });
    const armL = new THREE.Mesh(armGeo, armMat);
    armL.position.set(x - 0.55, 0.95, z);
    const armR = new THREE.Mesh(armGeo, armMat.clone());
    armR.position.set(x + 0.55, 0.95, z);
    g.add(armL, armR);
    sceneRefs.gateArms = [armL, armR];
    sceneRefs.gateLight = armL;
  }
  const light = new THREE.PointLight(0xfbbf24, 0.35, 4);
  light.position.set(x, 1.2, z);
  g.add(light);
  scene.add(g);
}

function buildObdCorner() { /* 已合并到北墙屏幕，保留空函数避免引用断裂 */ }

function buildOffroadBay() { /* 已移除独立 Offroad 角 */ }

function buildNorthWallScreens() {
  const wallZ = wallNorthZ() + 0.08;
  const wallY = 1.32;
  const specs = [
    { x: ZONE_POIS.ci.x, kind: 'tool', extra: 'CI pipeline' },
    { x: ZONE_POIS.routeWall.x, kind: 'route' },
    { x: ZONE_POIS.steering.x, kind: 'comma' },
  ];
  specs.forEach((spec) => {
    const screenMat = new THREE.MeshStandardMaterial({
      map: createScreenTexture(spec.kind, spec.extra),
      emissive: spec.kind === 'route' ? 0x4ecdc4 : 0x38bdf8,
      emissiveIntensity: 0.12,
    });
    const screen = new THREE.Mesh(new THREE.PlaneGeometry(1.15, 0.62), screenMat);
    screen.position.set(spec.x, wallY, wallZ);
    scene.add(screen);
    if (spec.kind === 'route') sceneRefs.routeWallMat = screenMat;
  });
  sceneRefs.ciLights = [];
  for (let i = 0; i < 5; i += 1) {
    const led = new THREE.Mesh(
      new THREE.SphereGeometry(0.05, 8, 8),
      mat(i % 2 ? 0x4ade80 : 0x38bdf8, { emissive: i % 2 ? 0x4ade80 : 0x38bdf8, emissiveIntensity: 0.45 }),
    );
    led.position.set(ZONE_POIS.ci.x - 0.42 + i * 0.21, wallY + 0.38, wallZ + 0.04);
    scene.add(led);
    sceneRefs.ciLights.push(led);
  }
}

function buildEastWallFeatures() {
  const { z } = ZONE_POIS.secoc;
  const wallX = (ROOM.hw ?? ROOM.floorW / 2) - 0.1;
  const panel = box(0.08, 1.0, 1.35, 0x0f172a);
  panel.position.set(wallX, 1.05, z);
  scene.add(panel);
  const lock = box(0.18, 0.24, 0.06, 0xfbbf24, { emissive: 0xfbbf24, emissiveIntensity: 0.22 });
  lock.position.set(wallX, 1.05, z);
  scene.add(lock);
  placeAsset('bookcase', wallX - 0.85, z - 0.55, -Math.PI / 2);
}

function buildZoneProps() {
  const { x: ax, z: az } = ZONE_POIS.adapt;
  placeAsset('bookcase', ax, az, 0);
  const { x: cx, z: cz } = ZONE_POIS.cloud;
  placeAsset('monitor', cx, cz, Math.PI, 0.75);
  placeAsset('plant', cx + 0.65, cz + 0.25, 0, 0.7);
  placeAsset('bookcase', ROOM.deskOriginX + ROOM.deskGapX * 2 + 0.85, ROOM.deskOriginZ - ROOM.deskGapZ, Math.PI);
}

function buildOfficeDivider() {
  const x = ROAD.officeMinX - 0.08;
  for (let z = -4.5; z <= 4.5; z += 1.4) {
    if (assetKit?.has('barrier')) placeAsset('barrier', x, z, Math.PI / 2);
    else if (assetKit?.has('cone') && z % 2 === 0) placeAsset('cone', x + 0.2, z, 0);
  }
}

function buildLaneSign() {
  const sign = createAreaSign('ADAS 车道', '🚗', 'openpilot');
  sign.position.set(ROAD.aisleX + 0.72, 1.62, 2.35);
  scene.add(sign);
  if (assetKit?.has('streetLight')) {
    placeAsset('streetLight', ROAD.aisleX - 0.95, -2.2, Math.PI / 2);
    placeAsset('streetLight', ROAD.aisleX - 0.95, 3.6, Math.PI / 2);
  }
}

function buildAlertWall() {
  const g = new THREE.Group();
  const { x } = ZONE_POIS.alertWall;
  const z = wallNorthZ() + 0.1;
  const panel = box(1.6, 1.0, 0.08, 0x0f172a);
  panel.position.set(x, 1.05, z);
  g.add(panel);
  const screen = new THREE.Mesh(
    new THREE.PlaneGeometry(1.45, 0.82),
    new THREE.MeshStandardMaterial({ map: createScreenTexture('alert', '待机'), emissive: 0xfbbf24, emissiveIntensity: 0.15 }),
  );
  screen.position.set(x, 1.05, z + 0.05);
  g.add(screen);
  sceneRefs.alertPanel = screen;
  scene.add(g);
}

function buildSteeringStation() { /* 已改为北墙屏幕 */ }

function buildRouteWall() { /* 已改为北墙屏幕 */ }

function buildSecocStation() { /* 已改为东墙面板 */ }

function buildAdaptShelf() { /* 已改为南墙标牌 */ }

function buildCiStrip() { /* 已改为北墙屏幕 */ }

function buildCloudAntenna() { /* 已改为南墙标牌 */ }

function buildDrivingTheme() {
  buildEngageGate();
  buildAlertWall();
  buildNorthWallScreens();
  buildEastWallFeatures();
  buildZoneProps();
  buildOfficeDivider();
  buildLaneSign();
  buildWallLabels();
  updateGateFromVehicle();
  refreshAlertPanel();
}

function buildLights() {
  scene.add(new THREE.AmbientLight(0xffffff, 0.55));
  scene.add(new THREE.HemisphereLight(0xf8fafc, 0x475569, 0.45));
  const sun = new THREE.DirectionalLight(0xffffff, 1.05);
  sun.position.set(10, 18, 12);
  sun.castShadow = true;
  sun.shadow.mapSize.set(1024, 1024);
  sun.shadow.camera.near = 1;
  sun.shadow.camera.far = 45;
  const s = 12;
  sun.shadow.camera.left = -s;
  sun.shadow.camera.right = s;
  sun.shadow.camera.top = s;
  sun.shadow.camera.bottom = -s;
  sun.shadow.bias = -0.0002;
  scene.add(sun);
}

async function buildOfficeScene() {
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0b1220);
  scene.fog = new THREE.Fog(0x0b1220, 20, 48);

  assetKit = new AssetKit();
  await assetKit.load();

  buildFloor();
  buildWallsAndWindows();
  buildDrivingTheme();
  buildBreakRoom();
  buildLounge();
  buildReplayTrack();

  for (let i = 0; i < 9; i += 1) {
    const slot = deskSlot(i);
    buildWorkstation(slot.x, slot.z, i % 2 === 0 ? 'route' : 'comma');
  }

  buildLights();
  rebuildAgentRigs();
}

function ensureCharacter(agent, index) {
  const id = agent.id;
  let ch = characters.get(id);
  const desk = agentDeskPos(agent, index);
  if (!ch) {
    ch = {
      id,
      name: agent.name || id,
      icon: agent.icon || '🤖',
      color: agentColor(id),
      deskX: desk.x,
      deskZ: desk.z,
      standZ: desk.standZ,
      x: desk.x,
      z: desk.standZ,
      y: 0,
      targetX: desk.x,
      targetZ: desk.standZ,
      status: 'idle',
      tool: '',
      behavior: hashBehavior(id),
      phase: Math.random() * Math.PI * 2,
      walkT: 0,
      bubble: '',
      bubbleT: 0,
    };
    characters.set(id, ch);
  }
  ch.name = agent.name || id;
  ch.icon = agent.icon || '🤖';
  ch.color = agentColor(id);
  ch.deskX = desk.x;
  ch.deskZ = desk.z;
  ch.standZ = desk.standZ;
  return ch;
}

function syncAgents(list) {
  const ids = new Set();
  const sorted = [...(list || [])].sort((a, b) => {
    const da = a.desk || {};
    const db = b.desk || {};
    return (da.row - db.row) || (da.col - db.col) || String(a.id).localeCompare(b.id);
  });
  sorted.forEach((agent, index) => {
    if (!agent?.id) return;
    ids.add(agent.id);
    ensureCharacter(agent, index);
  });
  for (const id of [...characters.keys()]) {
    if (!ids.has(id)) {
      characters.delete(id);
      removeAgentRig(id);
    }
  }
}

function applyLiveStatus() {
  const statusMap = new Map();
  for (const a of officeState?.agents || []) statusMap.set(a.id, a);
  let workingTool = '';
  for (const ch of characters.values()) {
    const live = statusMap.get(ch.id) || {};
    const next = live.status || 'idle';
    if (next !== ch.status) {
      ch.status = next;
      ch.tool = live.tool || '';
      if (next === 'working') {
        ch.bubble = live.tool ? `🔧 ${live.tool}` : '执行中…';
        ch.bubbleT = 2.5;
        ch.targetX = ch.deskX;
        ch.targetZ = ch.standZ;
        workingTool = live.tool || 'tool';
      } else if (next === 'assigned') {
        ch.bubble = '收到任务';
        ch.bubbleT = 2;
        ch.targetX = ch.deskX;
        ch.targetZ = ch.standZ;
      } else if (next === 'idle') ch.tool = '';
    } else if (live.tool && live.tool !== ch.tool) {
      ch.tool = live.tool;
      if (ch.status === 'working') {
        ch.bubble = `🔧 ${live.tool}`;
        ch.bubbleT = 2.5;
        workingTool = live.tool;
      }
    }
  }
  if (workingTool) pulseDeskScreens(workingTool);
}

function pickIdleTarget(ch, t) {
  if (ch.status !== 'idle') return;
  const cycle = Math.floor(t / 14 + ch.phase) % 8;
  if (ch.behavior === 'coffee' && cycle === 0) {
    ch.targetX = ZONE_POIS.coffee.x;
    ch.targetZ = ZONE_POIS.coffee.z;
    return;
  }
  if (ch.behavior === 'walk' && cycle === 0) {
    ch.targetX = ZONE_POIS.lounge.x;
    ch.targetZ = ZONE_POIS.lounge.z;
    return;
  }
  if (ch.id === 'pc' && ch.behavior === 'walk' && cycle === 1) {
    ch.targetX = ZONE_POIS.replay.x;
    ch.targetZ = ZONE_POIS.replay.z;
    return;
  }
  ch.targetX = ch.deskX;
  ch.targetZ = ch.standZ;
}

function updateCharacter(ch, dt, t) {
  if (ch.bubbleT > 0) ch.bubbleT -= dt;
  if (ch.status === 'idle') pickIdleTarget(ch, t);

  const dx = ch.targetX - ch.x;
  const dz = ch.targetZ - ch.z;
  const dist = Math.hypot(dx, dz);
  const speed = ch.status === 'working' ? 0 : 1.2;
  if (dist > 0.05) {
    const step = Math.min(dist, speed * dt);
    ch.x += (dx / dist) * step;
    ch.z += (dz / dist) * step;
    ch.walkT += dt * 10;
  } else {
    ch.walkT = 0;
  }

  if (ch.status === 'working') ch.y = Math.sin(t * 12 + ch.phase) * 0.02;
  else if (ch.status === 'idle' && ch.behavior === 'nap') ch.y = Math.sin(t * 1.2 + ch.phase) * 0.01;
  else if (ch.walkT > 0) ch.y = Math.abs(Math.sin(ch.walkT)) * 0.03;
  else ch.y = Math.sin(t * 2 + ch.phase) * 0.01;
}

function removeAgentRig(id) {
  const rig = agentRigs.get(id);
  if (!rig) return;
  pickables = pickables.filter((m) => m.userData?.agentId !== id);
  if (rig.mixer) rig.mixer.stopAllAction();
  scene?.remove(rig.group);
  agentRigs.delete(id);
}

function rebuildAgentRigs() {
  if (!scene) return;
  for (const id of [...agentRigs.keys()]) removeAgentRig(id);
  for (const ch of characters.values()) createAgentRig(ch);
}

function syncAgentRigs() {
  for (const ch of characters.values()) {
    if (!agentRigs.has(ch.id)) createAgentRig(ch);
  }
}

function updateAgentVisual(ch, t) {
  const rig = agentRigs.get(ch.id);
  if (!rig) return;

  const walking = ch.walkT > 0;
  rig.group.position.set(ch.x, ch.y, ch.z);
  if (walking) {
    rig.group.rotation.y = Math.atan2(ch.targetX - ch.x, ch.targetZ - ch.z);
  } else if (Math.hypot(ch.x - ch.deskX, ch.z - ch.standZ) < 0.2) {
    rig.group.rotation.y = 0;
  }
  animateRig(rig, ch, walking);

  const active = ch.status !== 'idle';
  const selected = ch.id === selectedId;
  rig.parts.ring.material.color.setHex(
    selected ? 0x4ecdc4 : (active ? (ch.status === 'working' ? 0x4ade80 : 0xfbbf24) : 0x94a3b8),
  );
  rig.parts.ring.material.opacity = selected ? 0.95 : (active ? 0.8 : 0.35);

  let icon = ch.icon;
  if (ch.status === 'idle' && ch.behavior === 'nap' && !walking) icon = '😴';
  if (ch.status === 'idle' && ch.behavior === 'stretch' && !walking) icon = '🧘';

  const statusText = ch.status === 'working' && ch.tool ? ch.tool : (STATUS_LABEL[ch.status] || ch.status);
  const showLabel = selected || active || (ch.bubbleT > 0 && ch.bubble);
  const lines = showLabel
    ? (ch.bubbleT > 0 && ch.bubble && !selected && !active
      ? [ch.bubble]
      : [ch.name, statusText].filter(Boolean))
    : [];
  const labelSig = `${lines.join('|')}|${active}|${selected}|${icon}|${showLabel}`;
  if (rig.labelSig !== labelSig) {
    if (rig.label) {
      rig.group.remove(rig.label);
      rig.label.material?.map?.dispose?.();
      rig.label.material?.dispose?.();
      rig.label = null;
    }
    rig.parts.emoji.material?.map?.dispose?.();
    rig.group.remove(rig.parts.emoji);
    rig.parts.emoji = createEmojiSprite(icon);
    rig.parts.emoji.position.y = rig.headY || 1.02;
    rig.group.add(rig.parts.emoji);
    if (showLabel && lines.length) {
      rig.label = createLabelSprite(lines.slice(0, 2), { active, selected, compact: true });
      rig.group.add(rig.label);
    }
    rig.labelSig = labelSig;
  }
}

function resize() {
  if (!renderer || !camera || !mount) return;
  const rect = mount.getBoundingClientRect();
  const w = Math.max(280, rect.width);
  const h = Math.max(220, rect.height);
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  controls?.update();
}

function updateSceneDynamics(dt, t) {
  sceneRefs.flowPhase += dt * (sceneRefs.driving ? 2.8 : 0.6);
  sceneRefs.laneFlow.forEach((stripe, i) => {
    if (!stripe.material) return;
    const pulse = 0.45 + 0.35 * Math.sin(sceneRefs.flowPhase * 2 + i * 0.7);
    stripe.material.opacity = sceneRefs.driving ? Math.min(0.95, pulse + 0.25) : pulse;
    if (sceneRefs.driving) {
      stripe.position.z = 0.3 + Math.sin(sceneRefs.flowPhase + i * 0.4) * 0.08;
    }
  });

  updateGateFromVehicle();

  if (sceneRefs.offroadCar) {
    const driving = sceneRefs.driving;
    sceneRefs.offroadCar.visible = !driving;
    if (!driving) {
      sceneRefs.offroadCar.position.y = Math.sin(t * 1.5) * 0.01;
    }
  }

  sceneRefs.ciLights.forEach((led, i) => {
    const on = (Math.floor(t * 2) + i) % 3 !== 0;
    led.material.emissiveIntensity = on ? 0.55 + Math.sin(t * 4 + i) * 0.2 : 0.08;
  });

  for (const entry of sceneRefs.deskScreens) {
    if (entry.pulseT > 0) {
      entry.pulseT -= dt;
      entry.mat.emissiveIntensity = 0.15 + Math.sin(t * 10) * 0.2;
      if (entry.pulseT <= 0) {
        entry.mat.emissiveIntensity = 0.12;
        entry.mat.emissive.setHex(0x4ecdc4);
      }
    }
  }
}

function renderFrame() {
  if (!renderer || !scene || !camera) return;
  const dt = Math.min(0.05, clock?.getDelta() ?? 0.016);
  const now = performance.now() / 1000;

  updateSceneDynamics(dt, now);

  if (!drivingPaused && !reducedMotion) {
    [...characters.values()].forEach((ch) => updateCharacter(ch, dt, now));
    for (const rig of agentRigs.values()) rig.mixer?.update(dt);
  }
  for (const ch of characters.values()) updateAgentVisual(ch, now);

  controls?.update();
  renderer.render(scene, camera);

  let overlay = mount?.querySelector('.office-driving-overlay');
  if (drivingPaused && mount) {
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.className = 'office-driving-overlay';
      mount.appendChild(overlay);
    }
    const vs = sceneRefs.vehicleState || {};
    const alert = vs.alert_text1 || vs.alertText1 || '';
    const speed = vs.vEgoKph ?? (vs.v_ego != null ? Math.round(vs.v_ego * 3.6) : null);
    const op = vs.active ? 'OP 已激活' : (vs.engageable ? '可 Engage' : (vs.enabled ? '待机' : ''));
    const bits = [speed != null ? `${speed} km/h` : '', op, alert].filter(Boolean);
    overlay.innerHTML = `<strong>🚗 行驶中</strong><span>${bits.join(' · ') || '可观赏场景 · 专员动画已暂停'}</span>`;
  } else {
    overlay?.remove();
  }
}

function loop(t) {
  if (!running) return;
  if (document.hidden) {
    rafId = requestAnimationFrame(loop);
    return;
  }
  if (!drivingPaused && !reducedMotion && t - lastFrameMs < FPS_MS) {
    rafId = requestAnimationFrame(loop);
    return;
  }
  lastFrameMs = t;
  renderFrame();
  rafId = requestAnimationFrame(loop);
}

function pickAgentAt(clientX, clientY) {
  if (!renderer || !camera || !raycaster || !pointer) return null;
  const rect = renderer.domElement.getBoundingClientRect();
  pointer.x = ((clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((clientY - rect.top) / rect.height) * 2 + 1;
  raycaster.setFromCamera(pointer, camera);
  const hits = raycaster.intersectObjects(pickables, false);
  return hits[0]?.object?.userData?.agentId || null;
}

function onPointerDown(ev) {
  clickDrag = { x0: ev.clientX, y0: ev.clientY, moved: false };
}

function onPointerMove(ev) {
  if (!clickDrag) return;
  if (Math.hypot(ev.clientX - clickDrag.x0, ev.clientY - clickDrag.y0) > 5) clickDrag.moved = true;
}

function onPointerUp(ev) {
  if (clickDrag && !clickDrag.moved) {
    const id = pickAgentAt(ev.clientX, ev.clientY);
    if (id) {
      selectedId = id;
      onSelectAgent?.(id);
      renderFrame();
    }
  }
  clickDrag = null;
}

function onDoubleClick(ev) {
  ev.preventDefault();
  focusCameraAt(ev.clientX, ev.clientY, { dollyIn: true });
}

function onKeyDown(ev) {
  if (!controls || !camera) return;
  if (ev.target?.matches?.('input, textarea, select, [contenteditable="true"]')) return;
  if (ev.key === '0' || ev.key === 'Home') {
    ev.preventDefault();
    resetSceneView();
    renderFrame();
  }
}

function bindEvents() {
  const el = renderer.domElement;
  el.addEventListener('pointerdown', onPointerDown);
  el.addEventListener('pointermove', onPointerMove);
  el.addEventListener('pointerup', onPointerUp);
  el.addEventListener('pointercancel', onPointerUp);
  el.addEventListener('dblclick', onDoubleClick);
  window.addEventListener('keydown', onKeyDown);
}

function unbindEvents() {
  const el = renderer?.domElement;
  if (el) {
    el.removeEventListener('pointerdown', onPointerDown);
    el.removeEventListener('pointermove', onPointerMove);
    el.removeEventListener('pointerup', onPointerUp);
    el.removeEventListener('pointercancel', onPointerUp);
    el.removeEventListener('dblclick', onDoubleClick);
  }
  window.removeEventListener('keydown', onKeyDown);
}

function showLoadError(msg) {
  if (!mount) return;
  mount.innerHTML = `<div class="office-scene-error">3D 场景加载失败<br><small>${msg || '请检查 static/vendor/three'}</small></div>`;
}

async function init(el) {
  if (initPromise) return initPromise;
  initPromise = initOffice(el);
  return initPromise;
}

async function initOffice(el) {
  mount = el || document.getElementById('officeSceneHost');
  if (!mount) return false;

  try {
    reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches;
    mount.innerHTML = '';
    mount.classList.add('office-scene-mount');

    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.05;
    renderer.domElement.className = 'office-scene-gl';
    mount.appendChild(renderer.domElement);

    camera = new THREE.PerspectiveCamera(38, 1, 0.1, 120);

    clock = new THREE.Clock();
    raycaster = new THREE.Raycaster();
    pointer = new THREE.Vector2();

    await buildOfficeScene();

    controls = new OrbitControls(camera, renderer.domElement);
    setupSceneControls(controls, camera);

    bindEvents();
    resize();

    if (typeof ResizeObserver !== 'undefined') {
      resizeObserver = new ResizeObserver(() => resize());
      resizeObserver.observe(mount);
    } else {
      window.addEventListener('resize', resize);
    }
    document.addEventListener('visibilitychange', onVisibilityChange);
    return true;
  } catch (e) {
    console.error('OfficeScene init failed', e);
    initPromise = null;
    showLoadError(e?.message);
    return false;
  }
}

function onVisibilityChange() {
  if (!document.hidden && running && !drivingPaused) {
    lastFrameMs = 0;
    renderFrame();
  }
}

function start() {
  if (running || !renderer) return;
  running = true;
  lastFrameMs = 0;
  clock?.getDelta();
  rafId = requestAnimationFrame(loop);
}

function stop() {
  running = false;
  if (rafId) cancelAnimationFrame(rafId);
  rafId = 0;
}

function destroy() {
  stop();
  unbindEvents();
  controls?.dispose();
  controls = null;
  resizeObserver?.disconnect();
  resizeObserver = null;
  window.removeEventListener('resize', resize);
  document.removeEventListener('visibilitychange', onVisibilityChange);
  renderer?.dispose();
  renderer?.domElement?.remove();
  renderer = null;
  scene = null;
  camera = null;
  characters.clear();
  agentRigs.clear();
  pickables = [];
  mount = null;
  initPromise = null;
  assetKit = null;
}

function setDrivingPaused(paused) {
  drivingPaused = !!paused;
  sceneRefs.driving = !!paused;
  if (running && renderer) {
    lastFrameMs = 0;
    renderFrame();
  }
}

function setVehicleState(vs) {
  sceneRefs.vehicleState = vs && typeof vs === 'object' ? { ...vs } : null;
  refreshAlertPanel();
  updateGateFromVehicle();
  if (running && renderer) renderFrame();
}

function setAgents(list) {
  syncAgents(list);
  if (scene) rebuildAgentRigs();
}

function applyOffice(data) {
  officeState = data || null;
  applyLiveStatus();
}

function setSelectedAgent(id) {
  selectedId = id || null;
  if (running && renderer) renderFrame();
}

function setOnSelectAgent(fn) {
  onSelectAgent = typeof fn === 'function' ? fn : null;
}

export const OfficeScene = {
  init,
  destroy,
  start,
  stop,
  resize,
  setAgents,
  applyOffice,
  setDrivingPaused,
  setVehicleState,
  setSelectedAgent,
  setOnSelectAgent,
};

if (typeof window !== 'undefined') {
  window.OfficeScene = OfficeScene;
}
