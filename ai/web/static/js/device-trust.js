/**
 * Device trust — fingerprint + pairing (OpenClaw-inspired).
 */
const DeviceTrust = (() => {
  const STORAGE_ID = 'ai-device-id';
  const STORAGE_FP = 'ai-device-fp';

  function uuid() {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID();
    return `dev_${Date.now()}_${Math.random().toString(16).slice(2)}`;
  }

  function fingerprint() {
    let fp = localStorage.getItem(STORAGE_FP);
    if (fp) return fp;
    const parts = [
      navigator.userAgent || '',
      navigator.language || '',
      screen?.width || 0,
      screen?.height || 0,
      screen?.colorDepth || 0,
    ];
    fp = btoa(unescape(encodeURIComponent(parts.join('|')))).slice(0, 48);
    localStorage.setItem(STORAGE_FP, fp);
    return fp;
  }

  function deviceId() {
    let id = localStorage.getItem(STORAGE_ID);
    if (!id) {
      id = uuid();
      localStorage.setItem(STORAGE_ID, id);
    }
    return id;
  }

  function headers() {
    return {
      'X-AI-Device-Id': deviceId(),
      'X-AI-Device-Fingerprint': fingerprint(),
    };
  }

  async function refreshTrust(apiFn) {
    if (typeof apiFn !== 'function') return null;
    const { data } = await apiFn('GET', '/api/ai/device/trust');
    return data;
  }

  async function ensureTrusted(apiFn) {
    const status = await refreshTrust(apiFn);
    if (!status?.ok) return status;
    if (!status.needsPairing) return status;
    const { data } = await apiFn('POST', '/api/ai/device/pair', {
      deviceId: deviceId(),
      fingerprint: fingerprint(),
      label: 'Browser',
    });
    return data?.ok ? { ...status, trusted: true, needsPairing: false } : status;
  }

  return { deviceId, fingerprint, headers, refreshTrust, ensureTrusted };
})();
