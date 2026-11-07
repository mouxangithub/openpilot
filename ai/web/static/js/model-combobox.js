/**
 * Unified model picker: free-text input with fuzzy-match dropdown (no manual/dropdown toggle).
 */
const ModelCombobox = (() => {
  function normalizeOption(item) {
    if (typeof item === 'string') return { id: item, label: item };
    const id = item?.id || item?.value || '';
    return { id, label: item?.label || id };
  }

  function fuzzyMatch(query, text) {
    if (!query) return true;
    const q = query.toLowerCase();
    const target = String(text || '').toLowerCase();
    if (target.includes(q)) return true;
    let qi = 0;
    for (let i = 0; i < target.length && qi < q.length; i += 1) {
      if (target[i] === q[qi]) qi += 1;
    }
    return qi === q.length;
  }

  function mount(selectorOrEl, opts = {}) {
    const host = typeof selectorOrEl === 'string' ? document.querySelector(selectorOrEl) : selectorOrEl;
    if (!host) return null;

    host.innerHTML = '';
    host.classList.add('model-combobox');

    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'model-combobox-input';
    input.autocomplete = 'off';
    input.spellcheck = false;
    input.setAttribute('role', 'combobox');
    input.setAttribute('aria-expanded', 'false');
    input.setAttribute('aria-autocomplete', 'list');
    if (opts.placeholder) input.placeholder = opts.placeholder;

    const list = document.createElement('ul');
    list.className = 'model-combobox-list hidden';
    list.setAttribute('role', 'listbox');

    host.appendChild(input);
    host.appendChild(list);

    let options = [];
    let highlight = -1;
    let open = false;
    let loading = false;
    let blurTimer = null;

    function filteredOptions() {
      const q = input.value.trim();
      return options.filter((o) => fuzzyMatch(q, o.label || o.id));
    }

    function renderList() {
      list.innerHTML = '';
      if (!open) {
        list.classList.add('hidden');
        input.setAttribute('aria-expanded', 'false');
        return;
      }

      if (loading) {
        const li = document.createElement('li');
        li.className = 'model-combobox-empty';
        li.textContent = opts.loadingLabel || 'Loading...';
        li.setAttribute('role', 'option');
        list.appendChild(li);
        list.classList.remove('hidden');
        input.setAttribute('aria-expanded', 'true');
        return;
      }

      const filtered = filteredOptions();
      const custom = input.value.trim();
      if (!filtered.length) {
        const li = document.createElement('li');
        if (custom) {
          li.className = 'model-combobox-item is-custom';
          li.textContent = custom;
          li.dataset.value = custom;
          li.setAttribute('role', 'option');
          li.addEventListener('mousedown', (e) => {
            e.preventDefault();
            selectValue(custom);
          });
        } else {
          li.className = 'model-combobox-empty';
          li.textContent = opts.emptyLabel || 'No matches';
          li.setAttribute('role', 'option');
        }
        list.appendChild(li);
      } else {
        const max = 80;
        filtered.slice(0, max).forEach((o, i) => {
          const li = document.createElement('li');
          li.className = `model-combobox-item${i === highlight ? ' is-active' : ''}`;
          li.textContent = o.label || o.id;
          li.dataset.value = o.id;
          li.setAttribute('role', 'option');
          li.addEventListener('mousedown', (e) => {
            e.preventDefault();
            selectValue(o.id);
          });
          list.appendChild(li);
        });
      }

      list.classList.remove('hidden');
      input.setAttribute('aria-expanded', 'true');
    }

    function openList() {
      open = true;
      highlight = -1;
      renderList();
    }

    function closeList() {
      open = false;
      highlight = -1;
      list.classList.add('hidden');
      input.setAttribute('aria-expanded', 'false');
    }

    function selectValue(val) {
      input.value = val || '';
      closeList();
      opts.onChange?.(input.value);
    }

    function setOptions(items) {
      options = (items || []).map(normalizeOption).filter((o) => o.id);
      if (open) renderList();
    }

    function setValue(val, { silent } = {}) {
      input.value = val || '';
      if (!silent) opts.onChange?.(input.value);
    }

    function getValue() {
      return input.value;
    }

    function setLoading(on) {
      loading = !!on;
      input.classList.toggle('is-loading', loading);
      if (open) renderList();
    }

    function setPlaceholder(text) {
      opts.placeholder = text;
      if (!loading) input.placeholder = text;
    }

    input.addEventListener('focus', () => {
      clearTimeout(blurTimer);
      openList();
    });

    input.addEventListener('input', () => {
      highlight = -1;
      openList();
      opts.onInput?.(input.value);
    });

    input.addEventListener('keydown', (e) => {
      const items = filteredOptions();
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        if (!open) openList();
        highlight = Math.min(highlight + 1, Math.max(items.length - 1, 0));
        renderList();
        list.querySelector('.model-combobox-item.is-active')?.scrollIntoView({ block: 'nearest' });
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        highlight = Math.max(highlight - 1, 0);
        renderList();
        list.querySelector('.model-combobox-item.is-active')?.scrollIntoView({ block: 'nearest' });
      } else if (e.key === 'Enter' && highlight >= 0 && items[highlight]) {
        e.preventDefault();
        selectValue(items[highlight].id);
      } else if (e.key === 'Escape') {
        closeList();
      }
    });

    input.addEventListener('blur', () => {
      blurTimer = setTimeout(closeList, 150);
    });

    return {
      input,
      setOptions,
      getOptions: () => options.slice(),
      setValue,
      getValue,
      setLoading,
      setPlaceholder,
      open: openList,
      close: closeList,
      destroy() {
        host.innerHTML = '';
        host.classList.remove('model-combobox');
      },
    };
  }

  return { mount, fuzzyMatch };
})();
