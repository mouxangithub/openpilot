/**
 * Per-session chat model picker — routes from Model Hub, session-local ordering.
 */
const SessionModelPicker = (() => {
  let root = null;
  let btn = null;
  let menu = null;
  let deps = {};

  function routeKey(route) {
    if (!route?.accountId || !route?.model) return '';
    return `${route.accountId}\0${route.model}`;
  }

  function listHubRouteOptions(hub) {
    if (!hub?.accounts?.length) return [];
    const accMap = new Map(hub.accounts.map((a) => [a.id, a]));
    const routes = [];
    const push = (row, isPrimary) => {
      if (!row?.accountId || !row?.model) return;
      const acc = accMap.get(row.accountId);
      if (!acc || acc.enabled === false) return;
      routes.push({
        accountId: row.accountId,
        model: row.model,
        label: row.label || '',
        provider: acc.provider || '',
        providerLabel: deps.providerLabel?.(acc.provider) || acc.provider || '',
        isPrimary,
        routeKey: routeKey(row),
      });
    };
    push(hub.primary, true);
    for (const f of hub.fallbacks || []) push(f, false);
    return routes;
  }

  function orderOptionsForSession(options, session) {
    const seen = new Set();
    const out = [];
    const add = (opt) => {
      if (!opt || seen.has(opt.routeKey)) return;
      seen.add(opt.routeKey);
      out.push(opt);
    };
    const current = session?.chatRoute;
    if (current?.accountId) {
      add(options.find((o) => o.routeKey === routeKey(current)));
    }
    for (const key of session?.chatRoutePins || []) {
      add(options.find((o) => o.routeKey === key));
    }
    for (const opt of options) add(opt);
    return out;
  }

  function getEffectiveRoute(session, hub) {
    const options = listHubRouteOptions(hub);
    const cur = session?.chatRoute;
    if (cur?.accountId && options.some((o) => o.routeKey === routeKey(cur))) {
      return cur;
    }
    const primary = hub?.primary;
    if (primary?.accountId && primary?.model) {
      return { accountId: primary.accountId, model: primary.model };
    }
    return null;
  }

  function formatRouteLabel(route, hub) {
    if (!route?.model) return deps.t?.('modelUnset', 'Not configured') || '—';
    const options = listHubRouteOptions(hub);
    const opt = options.find((o) => o.routeKey === routeKey(route));
    if (opt?.label) return opt.label;
    const short = route.model.length > 28 ? `${route.model.slice(0, 26)}…` : route.model;
    return short;
  }

  function formatRouteTitle(route, hub) {
    const options = listHubRouteOptions(hub);
    const opt = options.find((o) => o.routeKey === routeKey(route));
    if (!opt) return route?.model || '';
    const parts = [opt.model];
    if (opt.providerLabel) parts.push(opt.providerLabel);
    if (opt.label) parts.unshift(opt.label);
    return parts.join(' · ');
  }

  function isSessionStreaming(sessionId) {
    if (typeof deps.isSessionStreaming === 'function') {
      return deps.isSessionStreaming(sessionId);
    }
    return false;
  }

  function closeMenu() {
    menu?.classList.add('hidden');
    btn?.setAttribute('aria-expanded', 'false');
  }

  function renderMenu() {
    if (!menu || !btn) return;
    const hub = deps.getHub?.();
    const session = deps.getSession?.();
    const options = orderOptionsForSession(listHubRouteOptions(hub), session);
    const effective = getEffectiveRoute(session, hub);
    const effectiveKey = routeKey(effective);
    const streaming = isSessionStreaming(session?.id || deps.SessionStore?.activeId);

    menu.innerHTML = '';
    if (!options.length) {
      const empty = document.createElement('p');
      empty.className = 'session-model-menu-empty';
      empty.textContent = deps.t?.('sessionModelEmpty', '在设置 → 模型中心配置聊天路由') || '';
      menu.appendChild(empty);
      return;
    }

    const defaultBtn = document.createElement('button');
    defaultBtn.type = 'button';
    defaultBtn.className = 'session-model-menu-item';
    const hubPrimary = hub?.primary;
    const defaultLabel = hubPrimary?.model
      ? `${deps.t?.('sessionModelDefault', '默认') || '默认'} · ${hubPrimary.model}`
      : (deps.t?.('sessionModelDefault', '默认（模型中心）') || '默认');
    defaultBtn.textContent = defaultLabel;
    if (!session?.chatRoute) defaultBtn.classList.add('active');
    defaultBtn.disabled = streaming;
    defaultBtn.addEventListener('click', () => {
      applySelection(null);
      closeMenu();
    });
    menu.appendChild(defaultBtn);

    for (const opt of options) {
      const item = document.createElement('button');
      item.type = 'button';
      item.className = 'session-model-menu-item';
      const title = document.createElement('span');
      title.className = 'session-model-menu-model';
      title.textContent = opt.label || opt.model;
      const sub = document.createElement('span');
      sub.className = 'session-model-menu-sub';
      sub.textContent = `${opt.providerLabel}${opt.isPrimary ? ` · ${deps.t?.('modelHubPrimary', '主模型') || '主'}` : ''}`;
      item.appendChild(title);
      item.appendChild(sub);
      if (opt.routeKey === effectiveKey && session?.chatRoute) item.classList.add('active');
      item.disabled = streaming;
      item.addEventListener('click', () => {
        applySelection({ accountId: opt.accountId, model: opt.model });
        closeMenu();
      });
      menu.appendChild(item);
    }
  }

  function applySelection(route) {
    const sessionId = deps.SessionStore?.activeId;
    if (!sessionId) {
      deps.SessionStore?.setDraftChatRoute(route);
    } else {
      deps.SessionStore?.setChatRoute(sessionId, route);
      deps.scheduleSessionSync?.();
    }
    refresh();
    deps.onRouteChange?.(route);
  }

  function refresh() {
    if (!btn) return;
    const hub = deps.getHub?.();
    const session = deps.getSession?.();
    const route = getEffectiveRoute(session, hub);
    const label = formatRouteLabel(route, hub);
    btn.textContent = label;
    btn.title = formatRouteTitle(route, hub);
    btn.classList.toggle('unset', !route?.model);
    btn.disabled = !listHubRouteOptions(hub).length;
    deps.onRouteChange?.(session?.chatRoute || null, route);
  }

  function mount(selector, d) {
    deps = d || {};
    root = typeof selector === 'string' ? document.querySelector(selector) : selector;
    if (!root) return;
    btn = root.querySelector('#sessionModelPickerBtn') || root.querySelector('.session-model-picker-btn');
    menu = root.querySelector('#sessionModelPickerMenu') || root.querySelector('.session-model-picker-menu');
    if (!btn || !menu) return;

    btn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (menu.classList.contains('hidden')) {
        renderMenu();
        menu.classList.remove('hidden');
        btn.setAttribute('aria-expanded', 'true');
      } else {
        closeMenu();
      }
    });

    document.addEventListener('click', (e) => {
      if (!root?.contains(e.target)) closeMenu();
    });

    refresh();
  }

  function getChatRouteForSend(sessionId) {
    const hub = deps.getHub?.();
    const session = sessionId ? deps.SessionStore?.getById?.(sessionId) : deps.getSession?.();
    const route = session?.chatRoute;
    if (route?.accountId && listHubRouteOptions(hub).some((o) => o.routeKey === routeKey(route))) {
      return { accountId: route.accountId, model: route.model };
    }
    const draft = deps.SessionStore?.getDraftChatRoute?.();
    if (!sessionId && draft?.accountId) return draft;
    return null;
  }

  return {
    mount,
    refresh,
    closeMenu,
    listHubRouteOptions,
    getEffectiveRoute,
    formatRouteLabel,
    formatRouteTitle,
    getChatRouteForSend,
    routeKey,
  };
})();
