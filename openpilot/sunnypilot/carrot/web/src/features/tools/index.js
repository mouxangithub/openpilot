import "./web_settings/schema.js";
import "./web_settings/state.js";
import "./web_settings/components.js";
import "./web_settings/param_selects.js";
import "./web_settings/render.js";
import "./web_settings/drive_layout.js";
import "./web_settings/controller.js";
import "./notifications.js";
import "./egpu_model.js";
import "./bluetooth.js";
// Before runtime.js: it exposes initLanServices, which runtime.js calls from
// initToolsPage once the Tools DOM is in place.
import "./lan_services.js";
import "./runtime.js";
import "./settings_qr.js";
