/** Body (notCar) home layout — mirrors openpilot/selfdrive/ui/body/layouts/onroad.py + animations.py */

import { tr } from "./i18n.js?v=3";

const GRID_COLS = 16;
const GRID_ROWS = 8;
const DOT_RADIUS_RATIO = 0.018; // relative to min(w/h)

const AnimationMode = {
  ONCE_FORWARD: 1,
  ONCE_FORWARD_BACKWARD: 2,
  REPEAT_FORWARD: 3,
  REPEAT_FORWARD_BACKWARD: 4,
};

function mirror(dots) {
  return dots.map(([r, c]) => [r, 15 - c]);
}

function mirrorNoFlip(dots) {
  const minC = Math.min(...dots.map(([, c]) => c));
  const maxC = Math.max(...dots.map(([, c]) => c));
  return dots.map(([r, c]) => [r, 15 - maxC - minC + c]);
}

function shift(dots, [dr, dc]) {
  return dots.map(([r, c]) => [r + dr, c + dc]);
}

function makeFrame(leftEye, rightEye, leftBrow, rightBrow, mouth) {
  return [...leftEye, ...leftBrow, ...rightEye, ...rightBrow, ...mouth];
}

// Eyes (left side)
const EYE_OPEN = [
  [2, 2], [2, 3],
  [3, 1], [3, 2], [3, 3], [3, 4],
  [4, 1], [4, 2], [4, 3], [4, 4],
  [5, 2], [5, 3],
];
const EYE_HALF = [
  [4, 1], [4, 2], [4, 3], [4, 4],
  [5, 2], [5, 3],
];
const EYE_CLOSED = [
  [4, 1], [4, 4],
  [5, 2], [5, 3],
];
const EYE_LEFT_LOOK = [
  [2, 2], [2, 3],
  [3, 1], [3, 2],
  [4, 1], [4, 2],
  [5, 2], [5, 3],
];
const EYE_RIGHT_LOOK = [
  [2, 2], [2, 3],
  [3, 3], [3, 4],
  [4, 3], [4, 4],
  [5, 2], [5, 3],
];

// Eyebrows (left side)
const BROW_HIGH = [
  [0, 1], [0, 2],
  [1, 0],
];
const BROW_LOWERED = [
  [1, 1], [1, 2],
  [2, 0],
];
const BROW_STRAIGHT = [[1, 0], [1, 1], [1, 2]];

// Mouths (centered)
const MOUTH_SMILE = [[6, 6], [6, 9], [7, 7], [7, 8]];
const MOUTH_NORMAL = [[7, 7], [7, 8]];

const NORMAL = {
  frames: [
    makeFrame(EYE_OPEN, mirror(EYE_OPEN), BROW_HIGH, mirror(BROW_HIGH), MOUTH_SMILE),
    makeFrame(EYE_HALF, mirror(EYE_HALF), BROW_HIGH, mirror(BROW_HIGH), MOUTH_SMILE),
    makeFrame(EYE_CLOSED, mirror(EYE_CLOSED), BROW_LOWERED, mirror(BROW_LOWERED), MOUTH_SMILE),
  ],
  frameDuration: 0.15,
  mode: AnimationMode.REPEAT_FORWARD_BACKWARD,
  repeatInterval: 5.0,
  leftTurnRemove: [
    [3, 3], [3, 4], [4, 3], [4, 4],
  ].concat(mirrorNoFlip([[3, 1], [3, 2], [4, 1], [4, 2]])),
  rightTurnRemove: [
    [3, 1], [3, 2], [4, 1], [4, 2],
  ].concat(mirrorNoFlip([[3, 3], [3, 4], [4, 3], [4, 4]])),
};

const ASLEEP = {
  frames: [makeFrame(EYE_CLOSED, mirror(EYE_CLOSED), [], [], MOUTH_NORMAL)],
  frameDuration: 0.15,
  mode: AnimationMode.REPEAT_FORWARD,
  repeatInterval: 5.0,
};

const SLEEPY = {
  frames: [
    makeFrame(EYE_CLOSED, mirror(EYE_CLOSED), shift(BROW_STRAIGHT, [1, 0]), [], MOUTH_NORMAL),
    makeFrame(EYE_HALF, mirror(EYE_CLOSED), BROW_LOWERED, [], MOUTH_NORMAL),
    makeFrame(EYE_OPEN, mirror(EYE_CLOSED), BROW_HIGH, [], MOUTH_NORMAL),
  ],
  frameDuration: 0.25,
  mode: AnimationMode.ONCE_FORWARD_BACKWARD,
  repeatInterval: 10.0,
  holdEnd: 1.5,
};

const INQUISITIVE = {
  frames: [
    makeFrame(EYE_OPEN, mirror(EYE_OPEN), BROW_HIGH, mirror(BROW_HIGH), MOUTH_SMILE),
    makeFrame(EYE_LEFT_LOOK, mirror(EYE_RIGHT_LOOK), BROW_HIGH, mirror(BROW_HIGH), MOUTH_SMILE),
    makeFrame(shift(EYE_LEFT_LOOK, [0, -1]), shift(mirror(EYE_RIGHT_LOOK), [0, -1]), BROW_HIGH, mirror(BROW_HIGH), MOUTH_SMILE),
    makeFrame(shift(EYE_LEFT_LOOK, [0, -1]), shift(mirror(EYE_RIGHT_LOOK), [0, -1]), BROW_HIGH, mirror(BROW_HIGH), MOUTH_SMILE),
    makeFrame(shift(EYE_LEFT_LOOK, [0, -1]), shift(mirror(EYE_RIGHT_LOOK), [0, -1]), BROW_HIGH, mirror(BROW_HIGH), MOUTH_SMILE),
    makeFrame(EYE_LEFT_LOOK, mirror(EYE_RIGHT_LOOK), BROW_HIGH, mirror(BROW_HIGH), MOUTH_SMILE),
    makeFrame(EYE_RIGHT_LOOK, mirror(EYE_LEFT_LOOK), BROW_HIGH, mirror(BROW_HIGH), MOUTH_SMILE),
    makeFrame(shift(EYE_RIGHT_LOOK, [0, 1]), shift(mirror(EYE_LEFT_LOOK), [0, 1]), BROW_HIGH, mirror(BROW_HIGH), MOUTH_SMILE),
    makeFrame(shift(EYE_RIGHT_LOOK, [0, 1]), shift(mirror(EYE_LEFT_LOOK), [0, 1]), BROW_HIGH, mirror(BROW_HIGH), MOUTH_SMILE),
    makeFrame(shift(EYE_RIGHT_LOOK, [0, 1]), shift(mirror(EYE_LEFT_LOOK), [0, 1]), BROW_HIGH, mirror(BROW_HIGH), MOUTH_SMILE),
    makeFrame(EYE_RIGHT_LOOK, mirror(EYE_LEFT_LOOK), BROW_HIGH, mirror(BROW_HIGH), MOUTH_SMILE),
    makeFrame(EYE_OPEN, mirror(EYE_OPEN), BROW_HIGH, mirror(BROW_HIGH), MOUTH_SMILE),
  ],
  frameDuration: 0.15,
  mode: AnimationMode.REPEAT_FORWARD,
  repeatInterval: 10.0,
};

function getFrameIndex(animation, elapsed, gapFirst = false) {
  const numFrames = animation.frames.length;
  if (numFrames === 1) return 0;
  const fd = animation.frameDuration;
  const hasBackward = animation.mode === AnimationMode.ONCE_FORWARD_BACKWARD || animation.mode === AnimationMode.REPEAT_FORWARD_BACKWARD;
  const repeats = animation.mode === AnimationMode.REPEAT_FORWARD || animation.mode === AnimationMode.REPEAT_FORWARD_BACKWARD;
  const forwardDuration = numFrames * fd;
  const backwardFrames = Math.max(numFrames - 2, 0);
  const hold = hasBackward ? (animation.holdEnd || 0) : 0;
  const cycleDuration = forwardDuration + hold + backwardFrames * fd;
  let t = repeats ? ((elapsed + (gapFirst ? cycleDuration : 0)) % animation.repeatInterval) : Math.min(elapsed, cycleDuration);
  if (t < forwardDuration) return Math.min(Math.floor(t / fd), numFrames - 1);
  t -= forwardDuration;
  if (t < hold) return numFrames - 1;
  t -= hold;
  if (backwardFrames && t < backwardFrames * fd) return numFrames - 2 - Math.min(Math.floor(t / fd), backwardFrames - 1);
  return hasBackward ? 0 : numFrames - 1;
}

class FaceAnimator {
  constructor(animation) {
    this.animation = animation;
    this.nextAnimation = null;
    this.startTime = performance.now() / 1000;
    this.rewinding = false;
    this.rewindStart = 0;
    this.rewindFrom = 0;
    this.seenNonzero = false;
  }

  setAnimation(animation) {
    if (animation !== this.animation) {
      this.nextAnimation = animation;
    }
  }

  switchToNext(now) {
    this.animation = this.nextAnimation;
    this.nextAnimation = null;
    this.rewinding = false;
    this.seenNonzero = false;
    this.startTime = now;
    return this.animation.frames[0];
  }

  getDots() {
    const now = performance.now() / 1000;
    const elapsed = now - this.startTime;

    if (this.rewinding) {
      const rewindElapsed = now - this.rewindStart;
      const framesBack = Math.round(rewindElapsed / this.animation.frameDuration);
      const frameIndex = this.rewindFrom - framesBack;
      if (frameIndex <= 0) {
        if (this.nextAnimation === null) {
          this.rewinding = false;
          return this.animation.frames[0];
        }
        return this.switchToNext(now);
      }
      return this.animation.frames[frameIndex];
    }

    const starting = this.animation.startingFrames || [];
    const startingDuration = starting.length * this.animation.frameDuration;
    if (starting.length && elapsed < startingDuration) {
      return starting[Math.min(Math.floor(elapsed / this.animation.frameDuration), starting.length - 1)];
    }

    const loopElapsed = starting.length ? elapsed - startingDuration : elapsed;
    const frameIndex = getFrameIndex(this.animation, loopElapsed, !!starting.length);

    if (frameIndex !== 0) this.seenNonzero = true;

    if (this.nextAnimation !== null) {
      if (frameIndex === 0 && (this.animation.frames.length === 1 || this.seenNonzero)) {
        return this.switchToNext(now);
      }
      if (this.animation.mode === AnimationMode.ONCE_FORWARD || this.animation.mode === AnimationMode.REPEAT_FORWARD) {
        this.rewinding = true;
        this.rewindStart = now;
        this.rewindFrom = frameIndex;
      }
    }

    return this.animation.frames[frameIndex];
  }
}

let container = null;
let canvas = null;
let ctx = null;
let labelEl = null;
let animator = new FaceAnimator(ASLEEP);
let rafId = null;
let turningLeft = false;
let turningRight = false;
let lastInputTime = 0;
let wasActive = false;
let isOffroad = true;
let mouseXRatio = 0.5;

function ensureDom() {
  if (container) return;
  const screen = document.getElementById("screen-body");
  if (!screen) return;
  container = screen;
  canvas = document.createElement("canvas");
  canvas.className = "opui-body-canvas";
  labelEl = document.createElement("div");
  labelEl.className = "opui-body-label";
  container.appendChild(canvas);
  container.appendChild(labelEl);
  ctx = canvas.getContext("2d");

  screen.addEventListener("click", () => {
    if (!wasActive) {
      animator.setAnimation(SLEEPY);
    }
  });

  screen.addEventListener("mousemove", (e) => {
    const rect = screen.getBoundingClientRect();
    mouseXRatio = (e.clientX - rect.left) / rect.width;
  });

  screen.addEventListener("touchmove", (e) => {
    const rect = screen.getBoundingClientRect();
    if (e.touches[0]) {
      mouseXRatio = (e.touches[0].clientX - rect.left) / rect.width;
    }
  }, { passive: true });
}

function resizeCanvas() {
  if (!canvas || !container) return;
  const rect = container.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.round(rect.width * dpr);
  canvas.height = Math.round(rect.height * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function drawGrid(dots) {
  if (!ctx || !canvas) return;
  const rect = canvas.getBoundingClientRect();
  ctx.clearRect(0, 0, rect.width, rect.height);

  const spacing = Math.min(rect.height / GRID_ROWS, rect.width / GRID_COLS);
  const gridW = (GRID_COLS - 1) * spacing;
  const gridH = (GRID_ROWS - 1) * spacing;
  const offsetX = (rect.width - gridW) / 2;
  const offsetY = (rect.height - gridH) / 2;
  const radius = Math.max(2, Math.min(rect.width, rect.height) * DOT_RADIUS_RATIO);

  ctx.fillStyle = "#ffffff";
  for (const [row, col] of dots) {
    const x = Math.round(offsetX + col * spacing);
    const y = Math.round(offsetY + row * spacing);
    ctx.beginPath();
    ctx.arc(x, y, radius, 0, Math.PI * 2);
    ctx.fill();
  }

  if (isOffroad) {
    ctx.fillStyle = "rgba(0, 0, 0, 0.68)";
    ctx.fillRect(0, 0, rect.width, rect.height);
  }
}

function updateLabel() {
  if (!labelEl) return;
  labelEl.textContent = isOffroad ? tr("turn on ignition to use") : "";
  labelEl.hidden = !isOffroad;
}

function updateTurnState() {
  // Mirror testJoystick.axes[1] with mouse/touch position: left half = turn left, right half = turn right
  const steer = (mouseXRatio - 0.5) * -2;
  turningLeft = steer >= 0.05;
  turningRight = steer <= -0.05;
}

function updateAnimationState(state) {
  const started = !!state?.started;
  const bodyActive = started && !isOffroad;

  if (bodyActive) {
    if (!wasActive) {
      lastInputTime = performance.now() / 1000;
      wasActive = true;
    }
    const now = performance.now() / 1000;
    const hasInput = Math.abs((mouseXRatio - 0.5) * 2) > 0.1;
    if (hasInput) lastInputTime = now;
    if (now - lastInputTime > 30) {
      animator.setAnimation(INQUISITIVE);
    } else {
      animator.setAnimation(NORMAL);
    }
  } else {
    wasActive = false;
    animator.setAnimation(ASLEEP);
  }
}

function frameLoop() {
  if (!container) return;
  updateTurnState();
  let dots = animator.getDots();
  if (turningLeft && animator.animation.leftTurnRemove) {
    const remove = new Set(animator.animation.leftTurnRemove.map(([r, c]) => `${r},${c}`));
    dots = dots.filter(([r, c]) => !remove.has(`${r},${c}`));
  } else if (turningRight && animator.animation.rightTurnRemove) {
    const remove = new Set(animator.animation.rightTurnRemove.map(([r, c]) => `${r},${c}`));
    dots = dots.filter(([r, c]) => !remove.has(`${r},${c}`));
  }
  drawGrid(dots);
  rafId = requestAnimationFrame(frameLoop);
}

export function initBodyLayout() {
  ensureDom();
  resizeCanvas();
  if (!rafId) frameLoop();
  window.addEventListener("resize", resizeCanvas);
}

export function updateBodyLayout(state) {
  ensureDom();
  if (!rafId) frameLoop();
  isOffroad = !state?.started;
  updateAnimationState(state);
  updateLabel();
}

export function stopBodyLayout() {
  if (rafId) {
    cancelAnimationFrame(rafId);
    rafId = null;
  }
}
