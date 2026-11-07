/** Optional WebCodecs decode path for lower-latency WebRTC preview (Chrome / Edge). */

const WEBCODECS_PREF_KEY = "opui-webcodecs";

let activeCleanup = null;
let decodePath = "video";

export function getWebCodecsPreference() {
  const v = localStorage.getItem(WEBCODECS_PREF_KEY) || "auto";
  return ["auto", "on", "off"].includes(v) ? v : "auto";
}

export function setWebCodecsPreference(mode) {
  if (!["auto", "on", "off"].includes(mode)) return;
  localStorage.setItem(WEBCODECS_PREF_KEY, mode);
}

export function webCodecsCapability() {
  const secureContext = typeof window !== "undefined" && window.isSecureContext;
  const videoDecoder = typeof VideoDecoder !== "undefined";
  const trackGenerator = typeof MediaStreamTrackGenerator !== "undefined";
  const encodedStreams = typeof RTCRtpReceiver !== "undefined"
    && typeof RTCRtpReceiver.prototype?.createEncodedStreams === "function";
  return { secureContext, videoDecoder, trackGenerator, encodedStreams };
}

export function webCodecsCapable() {
  const c = webCodecsCapability();
  return c.secureContext && c.videoDecoder && c.trackGenerator && c.encodedStreams;
}

export function getStreamDecodePath() {
  return decodePath;
}

function h264CodecFromReceiver(receiver) {
  try {
    const codecs = receiver?.getParameters?.().codecs || [];
    for (const c of codecs) {
      const mime = String(c.mimeType || "").toLowerCase();
      if (!mime.startsWith("video/")) continue;
      if (mime !== "video/h264" && mime !== "video/avc") continue;
      const fmtp = String(c.sdpFmtpLine || "");
      const m = fmtp.match(/profile-level-id=([0-9a-fA-F]{6})/i);
      if (m) return `avc1.${m[1].toUpperCase()}`;
    }
  } catch {
    /* ignore */
  }
  return null;
}

function shouldTryWebCodecs(receiver) {
  const pref = getWebCodecsPreference();
  if (pref === "off") return false;
  if (!webCodecsCapable() || !receiver?.createEncodedStreams) return false;
  if (pref === "on") return true;
  // auto: only when we know the negotiated H.264 profile (avoids green macroblock glitches).
  return !!h264CodecFromReceiver(receiver);
}

function tuneReceiverLatency(receiver) {
  if (!receiver) return;
  try {
    if (typeof receiver.jitterBufferTarget !== "undefined") receiver.jitterBufferTarget = 0;
  } catch { /* ignore */ }
  try {
    if (typeof receiver.playoutDelayHint !== "undefined") receiver.playoutDelayHint = 0;
  } catch { /* ignore */ }
}

async function pumpEncodedFrames(readable, decoder, onFatal) {
  const reader = readable.getReader();
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      if (!value) continue;
      try {
        const chunk = new EncodedVideoChunk({
          type: value.type === "key" ? "key" : "delta",
          timestamp: value.timestamp,
          data: value.data,
        });
        if (decoder.state === "configured") decoder.decode(chunk);
      } catch (err) {
        onFatal?.(err);
        break;
      } finally {
        if (typeof value.close === "function") value.close();
      }
    }
  } catch (err) {
    onFatal?.(err);
  } finally {
    reader.releaseLock();
  }
}

export async function tryAttachWebCodecsDecode(receiver, videoEl, opts = {}) {
  const { fallback } = opts;
  stopWebCodecsDecode();
  if (!shouldTryWebCodecs(receiver) || !videoEl) {
    decodePath = "video";
    return false;
  }

  const codec = h264CodecFromReceiver(receiver) || "avc1.64001F";
  let decoder;
  let generator;
  let writer;
  let aborted = false;
  let fellBack = false;

  const doFallback = (reason) => {
    if (fellBack || aborted) return;
    fellBack = true;
    aborted = true;
    decodePath = "video";
    try { decoder?.close(); } catch { /* ignore */ }
    try { writer?.close(); } catch { /* ignore */ }
    try { generator?.stop(); } catch { /* ignore */ }
    activeCleanup = null;
    if (reason) console.warn("WebCodecs preview fallback:", reason);
    fallback?.();
  };

  const cleanup = () => {
    aborted = true;
    decodePath = "video";
    try { decoder?.close(); } catch { /* ignore */ }
    try { writer?.close(); } catch { /* ignore */ }
    try { generator?.stop(); } catch { /* ignore */ }
    activeCleanup = null;
  };

  try {
    const { readable } = receiver.createEncodedStreams();
    generator = new MediaStreamTrackGenerator({ kind: "video" });
    writer = generator.writable.getWriter();

    decoder = new VideoDecoder({
      output(frame) {
        if (aborted) {
          frame.close();
          return;
        }
        writer.write(frame).catch(() => {}).finally(() => frame.close());
      },
      error(err) {
        doFallback(err);
      },
    });

    decoder.configure({
      codec,
      optimizeForLatency: true,
      hardwareAcceleration: "prefer-hardware",
    });

    pumpEncodedFrames(readable, decoder, doFallback).catch(doFallback);
    videoEl.srcObject = new MediaStream([generator]);
    videoEl.playsInline = true;
    videoEl.muted = true;
    tuneReceiverLatency(receiver);
    await videoEl.play().catch(() => {});

    if (fellBack) return false;

    decodePath = "webcodecs";
    activeCleanup = cleanup;
    return true;
  } catch (err) {
    console.warn("WebCodecs preview path unavailable:", err);
    doFallback(err);
    return false;
  }
}

export function stopWebCodecsDecode() {
  if (activeCleanup) activeCleanup();
  decodePath = "video";
}

export function tuneVideoReceiver(receiver) {
  tuneReceiverLatency(receiver);
}
