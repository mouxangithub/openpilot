"use strict";

/* sunnypilot onroad HUD overlay style.
 *
 * Ported from the webui's opui-hud look (opui.css) but container-query scaled
 * like the fork's carrot HUD: the overlay is anchored to the video viewport and
 * every size is a cqw() percentage of it, so the on-device 7000 panel and a
 * laptop browser stay legible at any window size.
 *
 * The overlay intentionally replaces the cluster-style carrot HUD on this fork:
 * the project's base is sunnypilot, so the driving view follows sunnypilot's
 * onroad presentation (speed block, SLA sign, cruise set chip, road name,
 * blinkers, blind spot, rocket fuel, border states).
 */

export const SP_HUD_STYLE_ID = "carrot-sp-hud-overlay-style";

const TURN_IMG = "/shared-assets/icons_mici/onroad/turn_signal_left.png";
const BSM_IMG = "/shared-assets/icons_mici/onroad/blind_spot_left.png";

export const SP_IMAGES = Object.freeze({
  TURN: TURN_IMG,
  BSM: BSM_IMG,
});

export const CSS = `
.sp-hud{
  position:absolute; pointer-events:none; z-index:7; isolation:isolate;
  left:var(--carrot-viewport-left, 0px);
  top:var(--carrot-viewport-top, 0px);
  width:var(--carrot-viewport-width, 100%);
  height:var(--carrot-viewport-height, 100%);
  container-type:size; container-name:sphud;
  --sp-hud-font:"Inter","CarrotClusterHud","Segoe UI",system-ui,sans-serif;
  --sp-hud-white:#fff; --sp-hud-engaged:#80d8a6; --sp-hud-lat:#00c8c8;
  --sp-hud-long:#961ca8; --sp-hud-amber:#f4ac36; --sp-hud-red:#eb2020;
  --sp-hud-muted:#919b95;
  color:var(--sp-hud-white);
  font-family:var(--sp-hud-font);
}
.sp-hud[hidden],.sp-hud [hidden]{display:none!important}

/* top/bottom gradients - same recipe as webui .opui-hud-gradient */
.sp-hud::before,.sp-hud::after{
  content:"";position:absolute;left:0;right:0;pointer-events:none;z-index:0;
}
.sp-hud::before{
  top:0;height:clamp(72px,18cqw,180px);
  background:linear-gradient(180deg,rgba(0,0,0,.45) 0%,transparent 100%);
}
.sp-hud::after{
  bottom:0;height:clamp(96px,22cqw,220px);
  background:linear-gradient(0deg,rgba(0,0,0,.55) 0%,transparent 100%);
  opacity:0;transition:opacity .15s ease;
}
.sp-hud.is-engaged::after{opacity:1}

/* border states (mirrors .opui-border__inner) */
.sp-hud::before{box-shadow:inset 0 0 0 0 rgba(0,0,0,0);}
.sp-hud.is-engaged{box-shadow:inset 0 0 0 clamp(4px,0.8cqw,9px) var(--sp-hud-engaged);}
.sp-hud.is-lat_only{box-shadow:inset 0 0 0 clamp(4px,0.8cqw,9px) var(--sp-hud-lat);}
.sp-hud.is-long_only{box-shadow:inset 0 0 0 clamp(4px,0.8cqw,9px) var(--sp-hud-long);}
.sp-hud.is-override{box-shadow:inset 0 0 0 clamp(4px,0.8cqw,9px) var(--sp-hud-muted);}

/* ---- speed block (top-center, webui #hud-speed + #hud-unit) ---- */
.sp-hud-speed-block{
  position:absolute; left:50%; top:clamp(52px,12cqw,120px);
  transform:translateX(-50%); text-align:center; line-height:1;
  white-space:nowrap; z-index:1;
}
.sp-hud-speed{
  display:block; font-size:clamp(72px,17cqw,176px); font-weight:700;
  font-variant-numeric:tabular-nums; letter-spacing:0;
  text-shadow:0 4px 18px rgba(0,0,0,.5);
}
.sp-hud-unit{
  display:block; margin-top:clamp(4px,1cqw,10px);
  font-size:clamp(24px,6cqw,66px); font-weight:500;
  color:rgba(255,255,255,.78); letter-spacing:0;
}
.sp-hud-speed.hidden-block{visibility:hidden;}

/* ---- cruise set chip (top-left, webui #hud-set-speed) ---- */
.sp-hud-cruise{
  position:absolute; left:clamp(16px,4cqw,60px); top:clamp(16px,3.4cqw,45px);
  width:clamp(88px,15cqw,200px); height:clamp(88px,15cqw,204px);
  box-sizing:border-box; border-radius:clamp(26px,4cqw,60px);
  border:clamp(3px,0.5cqw,6px) solid rgba(255,255,255,.29);
  background:rgba(0,0,0,.65); text-align:center; padding-top:clamp(8px,1.6cqw,20px);
  z-index:1;
}
.sp-hud-cruise-max{
  font-size:clamp(16px,3cqw,40px); font-weight:600; color:#a6a6a6; line-height:1;
}
.sp-hud-cruise-max.is-set{color:var(--sp-hud-engaged);}
.sp-hud-cruise-val{
  margin-top:clamp(5px,1cqw,12px); font-size:clamp(30px,6.4cqw,90px);
  font-weight:700; line-height:1.1; color:#727272; font-variant-numeric:tabular-nums;
}
.sp-hud-cruise.is-set .sp-hud-cruise-val{color:#fff;}

/* ---- SLA limit sign (webui #hud-speed-limit-wrap) ---- */
.sp-hud-sla{
  position:absolute; left:calc(clamp(16px,4cqw,60px) + clamp(88px,15cqw,200px) + clamp(12px,1.8cqw,24px));
  top:clamp(16px,3.4cqw,45px);
  width:clamp(88px,15cqw,200px); height:clamp(88px,15cqw,204px);
  border-radius:50%; background:#fff; color:#000;
  display:flex; align-items:center; justify-content:center;
  box-shadow:0 0 0 clamp(8px,1.4cqw,18px) var(--sp-hud-red);
  z-index:1;
}
.sp-hud-sla.is-assist{box-shadow:0 0 0 clamp(8px,1.4cqw,18px) #3ddc84;}
.sp-hud-sla.is-overspeed{box-shadow:0 0 0 clamp(8px,1.4cqw,18px) var(--sp-hud-red);}
.sp-hud-sla.is-invalid{opacity:.45;}
.sp-hud-sla-value{
  font-size:clamp(30px,6.4cqw,90px); font-weight:700; line-height:1;
  font-variant-numeric:tabular-nums;
}
.sp-hud-sla.is-three-digit .sp-hud-sla-value{font-size:clamp(24px,5cqw,70px);}
.sp-hud-sla.is-overspeed .sp-hud-sla-value{color:var(--sp-hud-red);}

/* ---- road name (top-center marquee, webui #hud-road-name) ---- */
.sp-hud-road{
  position:absolute; top:clamp(8px,1.6cqw,20px); left:50%;
  transform:translateX(-50%); max-width:min(70%,72cqw);
  min-width:clamp(120px,20cqw,200px);
  padding:clamp(4px,0.6cqw,8px) clamp(10px,1.6cqw,20px);
  border-radius:clamp(6px,1cqw,12px); background:rgba(0,0,0,.47);
  font-size:clamp(18px,4.2cqw,46px); color:rgba(255,255,255,.78);
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; text-align:center;
  z-index:1;
}
.sp-hud-road.is-marquee{text-overflow:clip;}
.sp-hud-road__text{display:inline-block;white-space:nowrap;}

/* ---- blinkers / blind spot (webui #hud-blinker-l/r, #hud-bsl/r) ---- */
.sp-hud-blinker{
  position:absolute; top:clamp(80px,15cqw,190px); width:clamp(60px,11cqw,150px);
  height:clamp(60px,11cqw,150px); font-size:0; z-index:1;
  background:center / contain no-repeat url("${TURN_IMG}");
  filter:drop-shadow(0 3px 8px rgba(0,0,0,.5));
}
.sp-hud-blinker.is-blink{animation:sp-hud-blink .6s step-end infinite;}
@keyframes sp-hud-blink{50%{opacity:.2}}
.sp-hud-blinker--l{left:calc(50% - clamp(120px,22cqw,230px));}
.sp-hud-blinker--r{
  right:auto; left:calc(50% + clamp(40px,8cqw,80px));
  background-image:url("${TURN_IMG}"); transform:scaleX(-1);
}
.sp-hud-bsl{
  position:absolute; top:clamp(40px,7cqw,100px); width:clamp(44px,8cqw,108px);
  height:clamp(52px,9.6cqw,128px); z-index:1; opacity:.9;
  background:center / contain no-repeat url("${BSM_IMG}");
  filter:drop-shadow(0 3px 8px rgba(0,0,0,.5));
}
.sp-hud-bsl--l{left:clamp(4px,1.2cqw,20px);}
.sp-hud-bsl--r{right:clamp(4px,1.2cqw,20px);}

/* ---- SCC labels (webui #hud-scc-v/m) ---- */
.sp-hud-scc{
  position:absolute; left:calc(50% - clamp(150px,26cqw,340px));
  min-width:clamp(64px,12cqw,160px); padding:clamp(2px,0.4cqw,5px) clamp(5px,1cqw,12px);
  border-radius:clamp(5px,1cqw,12px); background:#00ff00; color:#000;
  font-size:clamp(14px,3cqw,36px); font-weight:700; text-align:center; line-height:1.2;
  z-index:13;
}
.sp-hud-scc--map{top:calc(25% - clamp(60px,10cqw,100px));}
.sp-hud-scc:not(.sp-hud-scc--map){top:calc(25% - clamp(20px,3.6cqw,40px));}
.sp-hud-scc.is-override{background:#89928d;color:#000;}
.sp-hud-scc.is-dim{opacity:.35;}

/* ---- rocket fuel bar (webui #hud-rocket) ---- */
.sp-hud-rocket{
  position:absolute; left:0; top:0; bottom:0; width:clamp(12px,2.4cqw,28px);
  pointer-events:none; z-index:12;
}
.sp-hud-rocket__up,.sp-hud-rocket__down{
  position:absolute; left:0; width:100%; background:rgba(0,245,0,.78);
}
.sp-hud-rocket__up{bottom:50%; height:var(--rocket-up,0%);}
.sp-hud-rocket__down{top:50%; height:var(--rocket-down,0%); background:rgba(245,0,0,.78);}

/* ---- experimental button (webui #btn-experimental) ---- */
.sp-hud-exp{
  position:absolute; top:clamp(12px,2.2cqw,30px); right:clamp(12px,2.2cqw,30px);
  width:clamp(72px,14cqw,192px); height:clamp(72px,14cqw,192px);
  border-radius:50%; border:none; background:rgba(0,0,0,.65); color:#fff;
  pointer-events:auto; cursor:pointer; padding:0; z-index:14;
  display:flex; align-items:center; justify-content:center;
}
.sp-hud-exp-icon{
  width:clamp(54px,10.6cqw,144px); height:clamp(54px,10.6cqw,144px);
  object-fit:contain; opacity:1; transition:opacity .15s;
}
.sp-hud-exp:not(.is-engageable) .sp-hud-exp-icon{opacity:.706;}
.sp-hud-exp.is-disabled{opacity:.45;cursor:not-allowed;}

/* ---- torque bar (webui #torque-bar-canvas) ---- */
.sp-hud-torque{
  position:absolute; left:0; right:0; bottom:clamp(0px,1cqw,10px);
  height:clamp(40px,8cqw,120px); pointer-events:none; z-index:12;
}

/* small-viewport degradation: hide the chrome that would collide */
@container sphud (max-width:560px){
  .sp-hud-bsl{display:none}
  .sp-hud-scc{display:none}
}
@container sphud (max-width:420px){
  .sp-hud-blinker{display:none}
  .sp-hud-sla{display:none}
  .sp-hud-exp{display:none}
  .sp-hud-cruise{width:clamp(72px,16cqw,96px);height:clamp(72px,16cqw,96px);}
  .sp-hud-cruise-val{font-size:clamp(26px,6cqw,40px)}
  .sp-hud-cruise-max{font-size:clamp(13px,3cqw,20px)}
}
`;

export function injectSpHudStyle(doc) {
  if (!doc || doc.getElementById(SP_HUD_STYLE_ID)) return;
  const style = doc.createElement("style");
  style.id = SP_HUD_STYLE_ID;
  style.textContent = CSS;
  (doc.head || doc.documentElement).appendChild(style);
}
