(function (global) {
  const app = global.SettingsApp = global.SettingsApp || {};
  class SettingsRegistry {
    constructor() { this.domains = new Map(); }
    register(domain) { if (!domain || !domain.id) throw new Error('domain.id required'); this.domains.set(domain.id, domain); return domain; }
    get(id) { return this.domains.get(id) || null; }
    all() { return Array.from(this.domains.values()); }
    search(query) {
      const q = String(query || '').trim().toLowerCase(); if (!q) return [];
      const out = [];
      this.all().forEach((d) => (d.cards || []).forEach((c) => (c.fields || []).forEach((f) => {
        const hay = [d.label, d.id, c.title, c.id, f.label, f.key, f.description].join(' ').toLowerCase();
        if (hay.includes(q)) out.push({ domain: d, card: c, field: f });
      })));
      return out;
    }
  }
  app.SettingsRegistry = SettingsRegistry;
  app.registry = app.registry || new SettingsRegistry();
})(window);
