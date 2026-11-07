/**
 * Browser alert sounds — mirrors openpilot/selfdrive/ui/soundd.py + quiet_mode.py.
 * Plays when state.alert_sound changes (WS ~200ms); respects QuietMode on device.
 */

const SOUND_PREF_KEY = "opui-browser-sound";
const ASSET_BASE = "/api/opui/assets/selfdrive/assets/sounds/";

/** AudibleAlert → wav file, loop (null = infinite while alert active). */
const SOUND_CATALOG = {
  engage: { file: "engage.wav", loop: false },
  disengage: { file: "disengage.wav", loop: false },
  refuse: { file: "refuse.wav", loop: false },
  prompt: { file: "warning.wav", loop: false },
  promptRepeat: { file: "warning.wav", loop: true },
  promptDistracted: { file: "dm_warning.wav", loop: true },
  preAlert: { file: "pre_alert.wav", loop: false },
  warningSoft: { file: "critical.wav", loop: true },
  warningImmediate: { file: "dm_critical.wav", loop: true },
  promptSingleLow: { file: "prompt_single_low.wav", loop: false },
  promptSingleHigh: { file: "prompt_single_high.wav", loop: false },
};

const QUIET_ALWAYS_PLAY = new Set([
  "warningSoft",
  "warningImmediate",
  "promptDistracted",
  "promptRepeat",
]);

let currentAlertSound = "none";
let activeAudio = null;
let audioUnlocked = false;
let unlockBound = false;

function soundsEnabled() {
  try {
    return localStorage.getItem(SOUND_PREF_KEY) !== "0";
  } catch {
    return true;
  }
}

function shouldPlaySound(sound, quietMode) {
  if (!sound || sound === "none") return false;
  if (!quietMode) return true;
  return QUIET_ALWAYS_PLAY.has(sound);
}

function stopActiveSound() {
  if (!activeAudio) return;
  try {
    activeAudio.pause();
    activeAudio.currentTime = 0;
  } catch {
    /* ignore */
  }
  activeAudio = null;
}

async function unlockAudioContext() {
  if (audioUnlocked) return true;
  const Ctx = window.AudioContext || window.webkitAudioContext;
  if (Ctx) {
    try {
      const ctx = new Ctx();
      await ctx.resume();
      audioUnlocked = true;
      return true;
    } catch {
      /* fall through */
    }
  }
  try {
    const probe = new Audio();
    probe.volume = 0;
    await probe.play();
    probe.pause();
    audioUnlocked = true;
    return true;
  } catch {
    return false;
  }
}

function bindSoundUnlock() {
  if (unlockBound) return;
  unlockBound = true;
  const unlock = () => {
    unlockAudioContext().then((ok) => {
      if (ok) {
        document.removeEventListener("pointerdown", unlock);
        document.removeEventListener("keydown", unlock);
      }
    });
  };
  document.addEventListener("pointerdown", unlock, { passive: true });
  document.addEventListener("keydown", unlock, { passive: true });
}

function playAlertSound(sound) {
  const cfg = SOUND_CATALOG[sound];
  if (!cfg) return;

  stopActiveSound();
  const audio = new Audio(`${ASSET_BASE}${cfg.file}`);
  audio.volume = 0.85;
  audio.loop = !!cfg.loop;
  activeAudio = audio;
  audio.play().catch(() => {
    /* autoplay policy — unlock on next interaction */
  });
}

/**
 * @param {object} st — onroad state payload from WS / dev simulation
 */
export function updateAlertSound(st) {
  if (!st?.ok || !soundsEnabled()) {
    if (currentAlertSound !== "none") {
      stopActiveSound();
      currentAlertSound = "none";
    }
    return;
  }

  const sound = st.alert_sound || "none";
  const quiet = !!st.quiet_mode;

  if (sound === "none" || !shouldPlaySound(sound, quiet)) {
    if (currentAlertSound !== "none") {
      stopActiveSound();
      currentAlertSound = "none";
    }
    return;
  }

  if (sound === currentAlertSound) {
    if (activeAudio && !activeAudio.paused) return;
    if (SOUND_CATALOG[sound]?.loop) {
      playAlertSound(sound);
    }
    return;
  }

  currentAlertSound = sound;
  playAlertSound(sound);
}

/** Dev presets: replay same alert_sound on repeated clicks. */
export function replayAlertSoundFromState(st) {
  currentAlertSound = "none";
  stopActiveSound();
  updateAlertSound(st);
}

export function initBrowserSounds() {
  bindSoundUnlock();
}
