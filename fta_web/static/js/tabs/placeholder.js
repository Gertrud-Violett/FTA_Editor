/**
 * tabs/placeholder.js -- the "coming soon" body the Phase 0 tab stubs share.
 * Each workstream replaces its tabs/<id>.js wholesale; nothing else imports
 * this, so it can be deleted once every tab is real.
 */

/**
 * @param {string} id   tab id, used for the `tab.<id>` title key
 * @returns {(panel: HTMLElement, ctx: object) => object} a tab `mount`
 */
export function placeholderMount(id) {
  return function mount(panel, ctx) {
    const t = (key, vars) => (ctx && typeof ctx.t === 'function' ? ctx.t(key, vars) : key);

    const box = document.createElement('div');
    box.className = 'placeholder tab-placeholder';
    box.dataset.placeholderFor = id;
    const glyph = document.createElement('span');
    glyph.className = 'placeholder__glyph';
    glyph.setAttribute('aria-hidden', 'true');
    glyph.textContent = '🛠';
    const title = document.createElement('p');
    title.className = 'placeholder__title';
    const badge = document.createElement('span');
    badge.className = 'placeholder__badge';
    const note = document.createElement('p');
    note.className = 'placeholder__note';
    box.append(glyph, title, badge, note);
    panel.appendChild(box);

    const paint = () => {
      const name = t('tab.' + id);
      title.textContent = name;
      badge.textContent = t('tab.comingSoon');
      note.textContent = t('tab.comingSoonNote', { tab: name });
    };
    paint();
    window.addEventListener('fta:language', paint);

    return {
      activate() {},
      deactivate() {},
      onStale() {},
      dispose() {
        window.removeEventListener('fta:language', paint);
        box.remove();
      },
    };
  };
}

export default placeholderMount;
