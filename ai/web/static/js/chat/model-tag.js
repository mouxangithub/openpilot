/**
 * Chat message model tag rendering.
 */
const ChatModelTag = (() => {
  function formatResolvedModelLabel(model) {
    const raw = String(model || '').trim();
    if (!raw) return '';
    return raw.length > 28 ? `${raw.slice(0, 26)}…` : raw;
  }

  function setMessageModelTag(metaEl, resolvedModel) {
    if (!metaEl) return;
    let tag = metaEl.querySelector('.message-model-tag');
    if (!tag) {
      tag = document.createElement('span');
      tag.className = 'message-model-tag hidden';
      metaEl.insertBefore(tag, metaEl.firstChild);
    }
    const label = formatResolvedModelLabel(resolvedModel);
    if (!label) {
      tag.classList.add('hidden');
      tag.textContent = '';
      tag.removeAttribute('title');
      return;
    }
    tag.classList.remove('hidden');
    tag.textContent = label;
    tag.title = String(resolvedModel);
  }

  return { formatResolvedModelLabel, setMessageModelTag };
})();
