export function normalizeSettingsCatalog(catalog) {
  if (!catalog || !Array.isArray(catalog.categories) || !catalog.categories.length) return catalog;

  const itemIndex = new Map();
  Object.values(catalog.items_by_group || {}).forEach((items) => {
    (items || []).forEach((item) => {
      if (item?.name) itemIndex.set(item.name, item);
    });
  });

  // `device_owned` lists the params the Device tab renders. Both tabs read the
  // same catalog menu, so without this filter every sunnypilot device setting
  // (models, vehicle, steering, maps, sunnylink...) was listed twice.
  const deviceOwned = new Set(Array.isArray(catalog.device_owned) ? catalog.device_owned : []);

  const groups = [];
  const itemsByGroup = {};
  const categories = [];
  catalog.categories.forEach((category) => {
    const categoryGroups = [];
    (category.groups || []).forEach((group) => {
      const items = [];
      (group.sections || []).forEach((section) => {
        const sectionLabel = {
          id: section.id,
          ko: section.ko,
          en: section.en,
          zh: section.zh,
        };
        (section.items || []).forEach((name) => {
          if (deviceOwned.has(name)) return;
          const item = itemIndex.get(name);
          if (item) items.push({ ...item, __section: sectionLabel });
        });
      });
      // The server counts the raw menu; recount after the Device-tab filter so
      // the group list never advertises rows that are not there.
      const count = items.filter((item) => !item.detail_parent && !item.search_only).length;
      if (!count) return;
      categoryGroups.push({
        id: group.id,
        ko: group.ko,
        en: group.en,
        zh: group.zh,
        count,
      });
      groups.push({
        group: group.id,
        ko: group.ko,
        en: group.en,
        zh: group.zh,
        count,
        category: category.id,
      });
      itemsByGroup[group.id] = items;
    });
    // A category whose every group belongs to the Device tab would otherwise
    // render as an empty divider.
    if (categoryGroups.length) categories.push({ ...category, groups: categoryGroups });
  });

  catalog.categories = categories;
  catalog.groups = groups;
  catalog.items_by_group = itemsByGroup;
  return catalog;
}

export function createSettingsCatalogState() {
  let currentCatalog = null;
  let currentSnapshot = null;

  function commit(catalog, snapshot = null) {
    if (!catalog || typeof catalog !== "object") throw new TypeError("Settings catalog must be an object");
    if (currentCatalog === catalog && currentSnapshot === snapshot) {
      return { catalog: currentCatalog, changed: false };
    }

    currentCatalog = normalizeSettingsCatalog(catalog);
    currentSnapshot = snapshot;
    return { catalog: currentCatalog, changed: true };
  }

  function peek() {
    return currentCatalog;
  }

  return Object.freeze({ commit, peek });
}
