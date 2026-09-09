/**
 * capabilities.js -- the "what can this build actually do" indicator.
 *
 * WHY THIS EXISTS
 * ===============
 * The editor degrades rather than fails when an optional dependency is absent:
 * without system Graphviz the diagram is drawn by the bundled WebAssembly
 * build, without openpyxl the .xlsx export is gone, without a provider key the
 * AI panel is inert. A user who is not told any of that reads the reduced
 * output as the product's real quality and never learns that a remedy exists.
 *
 * So every degraded capability is disclosed, and each disclosure has to have
 * three properties:
 *
 *   1. Discoverable without nagging. One quiet, persistent chip in the top bar.
 *      Never a modal, never a toast on every action; the user can ignore it and
 *      keep working, and it is still there when they come looking.
 *   2. Specific about what is lost. "Limited mode" tells nobody anything, so
 *      each row names the real consequence -- mis-sized CJK label boxes, a
 *      failing .xlsx export -- not a severity word.
 *   3. Carries the remedy. What to install, and where from.
 *
 * THE AI ROW IS FRAMED DIFFERENTLY ON PURPOSE
 * -------------------------------------------
 * An unconfigured AI assistant is the expected default, not a fault: it is
 * optional by design and every non-AI feature is unaffected. It therefore gets
 * an invitation ("Set up AI") and accent styling, never the warning styling.
 * Warning styling is reserved for a capability the user probably expected to
 * have and does not.
 *
 * CONTRACT
 * ========
 *   initCapabilities(host)   mount the chip + disclosure panel inside `host`
 *                            (the #capabilities container in the top bar).
 *                            -> {refresh(), destroy()}
 *   readCapabilities(state)  pure reader over an /api/state payload
 *                            -> {nativeDot, excelExport, aiConfigured}
 *   capabilities()           readCapabilities(store.state)
 *
 * Each value is TRI-STATE: true, false, or null for "the server did not say".
 * Null is not folded into false. Claiming a capability is missing when we do
 * not know would be a false alarm, and claiming it is present would be the very
 * silence this module exists to prevent -- so "not reported" is its own,
 * visible, unalarming state.
 *
 * The payload carries `capabilities: {nativeDot, excelExport, aiConfigured}`.
 * The P1 state also carried `nativeDot` and `aiConfigured` at the top level, so
 * those are read as a fallback and a server from either generation is handled.
 *
 * Capabilities are read once at boot and only change between launches, which is
 * why nothing here polls. The one thing that CAN change mid-session -- system
 * `dot` disappearing -- is reported per render by /api/dot's `renderer` field
 * and surfaced by diagram.js, not here.
 */
import { store } from './store.js';
import { clear, el } from './dialogs.js';

/* ------------------------------------------------------------- shell glue -- */

/**
 * Translate through the shell's table (main.js owns STRINGS and the EN/JA
 * toggle). Never hardcode English here: Japanese is a later phase and a literal
 * in this file would be work for it.
 */
function t(key, vars) {
  const shell = window.ftaShell;
  if (shell && typeof shell.t === 'function') {
    try {
      return shell.t(key, vars);
    } catch (_err) {
      /* fall through to the key, which is at least identifiable */
    }
  }
  return key;
}

/* ------------------------------------------------------------- the values -- */

/** true / false / null, preferring `capabilities` and falling back to legacy. */
function triState(caps, key, legacy) {
  if (caps && typeof caps[key] === 'boolean') return caps[key];
  if (typeof legacy === 'boolean') return legacy;
  return null;
}

/**
 * @param {object|null} state an /api/state payload (ok-stripped).
 * @returns {{nativeDot: boolean|null, excelExport: boolean|null,
 *            aiConfigured: boolean|null}}
 */
export function readCapabilities(state) {
  const src = state && typeof state === 'object' ? state : {};
  const caps =
    src.capabilities && typeof src.capabilities === 'object' ? src.capabilities : null;
  return {
    nativeDot: triState(caps, 'nativeDot', src.nativeDot),
    excelExport: triState(caps, 'excelExport', undefined),
    aiConfigured: triState(caps, 'aiConfigured', src.aiConfigured),
  };
}

/** The capabilities of the currently loaded state. */
export function capabilities() {
  return readCapabilities(store.state);
}

/* ------------------------------------------------------------ the content -- */

const GLYPH = { ok: '✓', warn: '⚠', invite: '+', unknown: '?' };

/**
 * One row per capability, in a fixed order so the panel never reshuffles.
 *
 * `kind` decides the tone, and it is deliberately NOT derived from the value:
 *   'expected' -- the user probably thought they had this. Missing => warning.
 *   'optional' -- absent by design. Missing => invitation, never a warning.
 */
const ROWS = [
  {
    id: 'dot',
    kind: 'expected',
    name: 'cap.dot.name',
    okState: 'cap.dot.okState',
    okBody: 'cap.dot.ok',
    badState: 'cap.dot.badState',
    badBody: 'cap.dot.bad',
    fix: 'cap.dot.fix',
    cmd: null,
  },
  {
    id: 'excel',
    kind: 'expected',
    name: 'cap.excel.name',
    okState: 'cap.state.ok',
    okBody: 'cap.excel.ok',
    badState: 'cap.state.off',
    badBody: 'cap.excel.bad',
    fix: 'cap.excel.fix',
    cmd: 'cap.excel.cmd',
  },
  {
    id: 'ai',
    kind: 'optional',
    name: 'cap.ai.name',
    okState: 'cap.state.ready',
    okBody: 'cap.ai.ok',
    badState: 'cap.state.optional',
    badBody: 'cap.ai.bad',
    fix: 'cap.ai.fix',
    cmd: null,
  },
];

const VALUE_OF = {
  dot: (caps) => caps.nativeDot,
  excel: (caps) => caps.excelExport,
  ai: (caps) => caps.aiConfigured,
};

/** 'ok' | 'warn' | 'invite' | 'unknown' for one row. */
function rowState(spec, value) {
  if (value === null) return 'unknown';
  if (value === true) return 'ok';
  return spec.kind === 'optional' ? 'invite' : 'warn';
}

/**
 * The chip's own state and label.
 *
 * A degraded expected capability outranks everything: that is the case the user
 * needs to see. With exactly one of them the chip names it outright, because
 * "1 limitation" would be the useless summary this whole module argues against.
 */
function summarise(caps) {
  const missing = [];
  if (caps.nativeDot === false) missing.push('cap.chip.graphviz');
  if (caps.excelExport === false) missing.push('cap.chip.excel');

  if (missing.length === 1) return { state: 'warn', text: t(missing[0]) };
  if (missing.length > 1) {
    return { state: 'warn', text: t('cap.chip.several', { n: missing.length }) };
  }
  if (caps.aiConfigured === false) return { state: 'invite', text: t('cap.chip.ai') };
  if (caps.nativeDot === null || caps.excelExport === null || caps.aiConfigured === null) {
    return { state: 'unknown', text: t('cap.chip.unknown') };
  }
  return { state: 'ok', text: t('cap.chip.ok') };
}

/* ------------------------------------------------------------------ panel -- */

/**
 * Mount the indicator inside `host`.
 *
 * The chip and the panel are built here rather than in index.html so every
 * string goes through t() and the whole thing re-labels itself on EN/JA.
 */
export function initCapabilities(host) {
  if (!host) throw new Error('initCapabilities(host): host is required');

  clear(host);

  const panelId = 'capabilities-panel';
  const summary = el('span', { class: 'capbar__text' });
  const glyph = el('span', { class: 'capbar__glyph', 'aria-hidden': 'true' });

  const button = el(
    'button',
    {
      type: 'button',
      class: 'capbar__button',
      id: 'btn-capabilities',
      'aria-expanded': 'false',
      'aria-controls': panelId,
      'aria-haspopup': 'true',
      dataset: { state: 'unknown' },
    },
    [glyph, summary]
  );

  const body = el('div', { class: 'capbar__rows' });
  const panel = el('div', { class: 'capbar__panel', id: panelId, hidden: true }, [
    el('p', { class: 'capbar__title' }),
    body,
    el('p', { class: 'capbar__foot' }),
  ]);

  host.append(button, panel);

  let open = false;

  /* ---- rendering ---- */

  function buildRow(spec, value) {
    const state = rowState(spec, value);
    const isOk = state === 'ok';
    const isUnknown = state === 'unknown';

    const head = el('div', { class: 'cap-row__head' }, [
      el('span', { class: 'cap-row__name', text: t(spec.name) }),
      el('span', {
        class: 'cap-row__state',
        text: t(isUnknown ? 'cap.state.unknown' : isOk ? spec.okState : spec.badState),
      }),
    ]);

    const main = el('div', { class: 'cap-row__main' }, [head]);
    main.appendChild(
      el('p', {
        class: 'cap-row__body',
        text: t(isUnknown ? 'cap.unknown' : isOk ? spec.okBody : spec.badBody),
      })
    );

    // The remedy is the whole point of naming the loss, so it rides along with
    // it -- but only when there is something to remedy.
    if (!isOk && !isUnknown) {
      main.appendChild(el('p', { class: 'cap-row__fix', text: t(spec.fix) }));
      if (spec.cmd) {
        main.appendChild(el('code', { class: 'cap-row__cmd', text: t(spec.cmd) }));
      }
    }

    return el('div', { class: 'cap-row', dataset: { state: state } }, [
      el('span', { class: 'cap-row__glyph', 'aria-hidden': 'true', text: GLYPH[state] }),
      main,
    ]);
  }

  function render() {
    const caps = capabilities();
    const chip = summarise(caps);

    button.dataset.state = chip.state;
    glyph.textContent = GLYPH[chip.state];
    summary.textContent = chip.text;
    // The visible chip is a summary; the accessible name says what it opens.
    button.setAttribute('aria-label', t('cap.button') + ': ' + chip.text);
    button.title = chip.text + ' — ' + t('cap.buttonHint');

    const title = panel.querySelector('.capbar__title');
    if (title) title.textContent = t('cap.title');
    const foot = panel.querySelector('.capbar__foot');
    if (foot) foot.textContent = t('cap.foot');
    panel.setAttribute('aria-label', t('cap.title'));

    clear(body);
    for (const spec of ROWS) {
      body.appendChild(buildRow(spec, VALUE_OF[spec.id](caps)));
    }
  }

  /* ---- open / close ---- */

  function setOpen(next) {
    if (open === next) return;
    open = next;
    panel.hidden = !open;
    button.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (open) {
      // Re-read on open: cheap, and it means a state refresh between boot and
      // the click is never shown stale.
      render();
      document.addEventListener('pointerdown', onOutside, true);
    } else {
      document.removeEventListener('pointerdown', onOutside, true);
    }
  }

  function onOutside(event) {
    const target = event.target;
    if (target instanceof Node && host.contains(target)) return;
    setOpen(false);
  }

  function onEscape(event) {
    if (!open) return;
    // Claim the Escape so the shell does not also dismiss a toast underneath.
    event.preventDefault();
    setOpen(false);
    button.focus();
  }

  button.addEventListener('click', () => setOpen(!open));
  window.addEventListener('fta:escape', onEscape);

  // Language switches re-label everything; the store gives us the values.
  const onLanguage = () => render();
  window.addEventListener('fta:language', onLanguage);
  const unsubscribe = store.subscribe(render);

  render();

  return {
    refresh: render,
    destroy() {
      if (typeof unsubscribe === 'function') unsubscribe();
      window.addEventListener; // no-op guard for minifiers; see removals below
      window.removeEventListener('fta:language', onLanguage);
      window.removeEventListener('fta:escape', onEscape);
      document.removeEventListener('pointerdown', onOutside, true);
      clear(host);
    },
  };
}

export default initCapabilities;
