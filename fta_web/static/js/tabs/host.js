/**
 * tabs/host.js -- the bottom panel's tab strip (1.7).
 *
 * The markup (nine role="tab" buttons and nine role="tabpanel" divs) is static
 * in index.html so it paints before any JS; this module wires it.
 *
 * TAB MODULE CONTRACT (frozen in Phase 0)
 * =======================================
 *   tabs/<id>.js exports
 *     id        string, equal to the file name
 *     advanced  boolean; true hides the tab while Advanced is off
 *     mount(panelEl, ctx) -> {activate?, deactivate?, dispose?, onStale?}
 *                           (may return a promise of that object)
 *
 *   The host imports a tab the first time it is shown and calls mount() once.
 *   activate() runs every time the tab becomes visible, deactivate() when it
 *   is hidden. onStale() runs when `tree` or `analysis` changed since the tab
 *   last saw them, at the moment the tab is visible: right after activate()
 *   for a tab that was in the background, immediately for the visible one.
 *   dispose() runs only when the host itself is destroyed.
 *
 *   `details` is special: its panel wraps the existing #details-root, which
 *   main.js initialises with details.js exactly as before. Nothing is imported.
 *
 *   ctx (built by main.js, see buildTabContext there):
 *     store, api, t, toast, showError,
 *     fmt: {prob(v), sigFigs()}, onSigFigs(cb) -> unsub,
 *     advanced(), onAdvanced(cb) -> unsub,
 *     highlight(ids, source), clearHighlight(source), setOverlay(o),
 *     jumpTo(nodeId), capabilities(), pickPath(opts), diagramPng()
 *
 * The selected tab persists in localStorage `fta.bottomTab`.
 */

export const STORAGE_KEY = 'fta.bottomTab';

/** Order is the on-screen order. `advanced` must match each module's export. */
export const TAB_DEFS = Object.freeze([
  Object.freeze({ id: 'details', advanced: false }),
  Object.freeze({ id: 'quant', advanced: true }),
  Object.freeze({ id: 'cutsets', advanced: true }),
  Object.freeze({ id: 'importance', advanced: true }),
  Object.freeze({ id: 'uncertainty', advanced: true }),
  Object.freeze({ id: 'validation', advanced: false }),
  Object.freeze({ id: 'trace', advanced: true }),
  Object.freeze({ id: 'fmea', advanced: true }),
  Object.freeze({ id: 'report', advanced: true }),
]);

const DEFAULT_TAB = 'details';

function readLocal(key) {
  try {
    return window.localStorage.getItem(key);
  } catch (_err) {
    return null;
  }
}

function writeLocal(key, value) {
  try {
    window.localStorage.setItem(key, value);
  } catch (_err) {
    /* private mode: the choice just does not persist */
  }
}

/**
 * @param {object} opts
 * @param {HTMLElement} opts.strip   the role="tablist" element
 * @param {object} opts.ctx          the tab context (see header)
 * @param {(id: string) => Promise<object>} [opts.importer]  test seam
 */
export function initTabHost({ strip, ctx, importer } = {}) {
  if (!strip) throw new Error('tab host: no tab strip');
  const load = importer || ((id) => import('./' + id + '.js'));
  const t = (key, vars) => (ctx && typeof ctx.t === 'function' ? ctx.t(key, vars) : key);

  const tabs = new Map(); // id -> {def, button, panel, handle, loading, failed, stale}
  for (const def of TAB_DEFS) {
    const button = strip.querySelector('[role="tab"][data-tab="' + def.id + '"]');
    const panel = button && document.getElementById(button.getAttribute('aria-controls'));
    if (!button || !panel) {
      // eslint-disable-next-line no-console
      console.error('[tabs] markup for tab "' + def.id + '" is missing');
      continue;
    }
    tabs.set(def.id, {
      def: { ...def },
      button,
      panel,
      handle: null,
      loading: null,
      failed: false,
      stale: false,
    });
  }

  let activeId = null;
  let destroyed = false;

  const isAdvancedOn = () => Boolean(ctx && typeof ctx.advanced === 'function' && ctx.advanced());
  const isVisible = (id) => {
    const tab = tabs.get(id);
    return Boolean(tab) && (!tab.def.advanced || isAdvancedOn());
  };
  const visibleIds = () => Array.from(tabs.keys()).filter(isVisible);
  const label = (id) => t('tab.' + id);

  function call(tab, name) {
    const fn = tab.handle && tab.handle[name];
    if (typeof fn !== 'function') return;
    try {
      const result = fn.call(tab.handle);
      if (result && typeof result.catch === 'function') result.catch(report);
    } catch (err) {
      report(err);
    }
  }

  function report(err) {
    if (ctx && typeof ctx.showError === 'function') ctx.showError(err);
    // eslint-disable-next-line no-console
    else console.error('[tabs]', err);
  }

  function renderFallback(tab, err) {
    const panel = tab.panel;
    panel.textContent = '';
    const box = document.createElement('div');
    box.className = 'placeholder tabpanel__fallback';
    const glyph = document.createElement('span');
    glyph.className = 'placeholder__glyph';
    glyph.setAttribute('aria-hidden', 'true');
    glyph.textContent = '⚠';
    const title = document.createElement('p');
    title.className = 'placeholder__title';
    title.textContent = label(tab.def.id);
    const note = document.createElement('p');
    note.className = 'placeholder__note';
    note.textContent = t('tab.loadFailed', {
      tab: label(tab.def.id),
      error: err && err.message ? err.message : String(err),
    });
    box.append(glyph, title, note);
    panel.appendChild(box);
  }

  /** Import + mount once; resolves the handle or null on failure. */
  function ensureMounted(tab) {
    if (tab.def.id === DEFAULT_TAB) return Promise.resolve(null);
    if (tab.handle) return Promise.resolve(tab.handle);
    if (tab.loading) return tab.loading;
    tab.panel.setAttribute('aria-busy', 'true');
    tab.loading = (async () => {
      try {
        const module = await load(tab.def.id);
        if (!module || typeof module.mount !== 'function') {
          throw new Error('tabs/' + tab.def.id + '.js has no mount() export');
        }
        if (module.id !== undefined && module.id !== tab.def.id) {
          // eslint-disable-next-line no-console
          console.warn('[tabs] tabs/' + tab.def.id + '.js exports id "' + module.id + '"');
        }
        if (typeof module.advanced === 'boolean' && module.advanced !== tab.def.advanced) {
          // The module is authoritative; keep the strip consistent with it.
          tab.def.advanced = module.advanced;
          applyVisibility();
        }
        tab.panel.textContent = '';
        const handle = (await module.mount(tab.panel, ctx)) || {};
        if (destroyed) {
          if (typeof handle.dispose === 'function') handle.dispose();
          return null;
        }
        tab.handle = handle;
        tab.failed = false;
        tab.stale = false;
        return handle;
      } catch (err) {
        tab.failed = true;
        // eslint-disable-next-line no-console
        console.error('[tabs] could not load tab "' + tab.def.id + '"', err);
        renderFallback(tab, err);
        return null;
      } finally {
        tab.loading = null;
        tab.panel.removeAttribute('aria-busy');
      }
    })();
    return tab.loading;
  }

  function paintSelection() {
    for (const [id, tab] of tabs) {
      const on = id === activeId;
      tab.button.setAttribute('aria-selected', on ? 'true' : 'false');
      tab.button.tabIndex = on ? 0 : -1;
      tab.button.classList.toggle('is-active', on);
      tab.panel.hidden = !on;
    }
  }

  /**
   * Show a tab. Hidden (advanced-in-basic) or unknown ids fall back to
   * details. `persist` false keeps the stored preference (used for fallbacks).
   * @returns {string} the id actually shown
   */
  function select(id, { focus = false, persist = true } = {}) {
    if (destroyed) return activeId;
    const wanted = isVisible(id) ? id : DEFAULT_TAB;
    const tab = tabs.get(wanted);
    if (!tab) return activeId;

    if (wanted !== activeId) {
      const previous = activeId ? tabs.get(activeId) : null;
      activeId = wanted;
      paintSelection();
      if (previous) call(previous, 'deactivate');
      ensureMounted(tab).then((handle) => {
        if (!handle || activeId !== wanted) return;
        call(tab, 'activate');
        if (tab.stale) {
          tab.stale = false;
          call(tab, 'onStale');
        }
      });
    }
    if (persist && wanted === id) writeLocal(STORAGE_KEY, wanted);
    if (focus) tab.button.focus();
    return wanted;
  }

  function applyVisibility() {
    for (const [id, tab] of tabs) {
      const show = isVisible(id);
      tab.button.hidden = !show;
      tab.button.setAttribute('aria-hidden', show ? 'false' : 'true');
    }
    if (activeId && !isVisible(activeId)) {
      select(DEFAULT_TAB, { persist: false });
      return;
    }
    // Advanced just came back on: restore the tab the user had chosen.
    const preferred = readLocal(STORAGE_KEY);
    if (preferred && preferred !== activeId && isVisible(preferred) && activeId === DEFAULT_TAB) {
      select(preferred, { persist: false });
    }
  }

  // ---- keyboard: roving tabindex, automatic activation --------------------
  function onKeyDown(event) {
    const button = event.target instanceof Element ? event.target.closest('[role="tab"]') : null;
    if (!button) return;
    const ids = visibleIds();
    const here = ids.indexOf(button.dataset.tab);
    if (here === -1) return;
    let next = null;
    switch (event.key) {
      case 'ArrowRight':
        next = ids[(here + 1) % ids.length];
        break;
      case 'ArrowLeft':
        next = ids[(here - 1 + ids.length) % ids.length];
        break;
      case 'Home':
        next = ids[0];
        break;
      case 'End':
        next = ids[ids.length - 1];
        break;
      default:
        return;
    }
    event.preventDefault();
    select(next, { focus: true });
  }

  function onClick(event) {
    const button = event.target instanceof Element ? event.target.closest('[role="tab"]') : null;
    if (!button || !strip.contains(button)) return;
    select(button.dataset.tab);
  }

  strip.addEventListener('keydown', onKeyDown);
  strip.addEventListener('click', onClick);

  // ---- staleness: tree / analysis identity changes ------------------------
  let seenTree;
  let seenAnalysis;
  let primed = false;
  const unsubscribe =
    ctx && ctx.store && typeof ctx.store.subscribe === 'function'
      ? ctx.store.subscribe((state) => {
          const tree = state ? state.tree : undefined;
          const analysis = state ? state.analysis : undefined;
          if (!primed) {
            primed = true;
            seenTree = tree;
            seenAnalysis = analysis;
            return;
          }
          if (tree === seenTree && analysis === seenAnalysis) return;
          seenTree = tree;
          seenAnalysis = analysis;
          for (const [id, tab] of tabs) {
            if (!tab.handle) continue;
            if (id === activeId) call(tab, 'onStale');
            else tab.stale = true;
          }
        })
      : null;

  const unAdvanced =
    ctx && typeof ctx.onAdvanced === 'function' ? ctx.onAdvanced(() => applyVisibility()) : null;

  // ---- first paint ---------------------------------------------------------
  for (const tab of tabs.values()) tab.panel.hidden = true;
  applyVisibility();
  select(readLocal(STORAGE_KEY) || DEFAULT_TAB, { persist: false });

  return {
    select: (id, opts) => select(id, opts),
    get active() {
      return activeId;
    },
    isVisible,
    visibleIds,
    /** Re-apply visibility (after an Advanced toggle outside onAdvanced). */
    refresh: applyVisibility,
    destroy() {
      destroyed = true;
      strip.removeEventListener('keydown', onKeyDown);
      strip.removeEventListener('click', onClick);
      if (typeof unsubscribe === 'function') unsubscribe();
      if (typeof unAdvanced === 'function') unAdvanced();
      for (const tab of tabs.values()) call(tab, 'dispose');
    },
  };
}

export default initTabHost;
