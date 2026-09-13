/**
 * api.js -- the only place in the frontend that talks HTTP.
 *
 * CONTRACT
 * ========
 *   bootstrapToken()                 read ?t= from the URL, stash it in
 *                                    sessionStorage, strip it from the address
 *                                    bar. Returns the active token or null.
 *   hasToken()                       true when this tab holds a token.
 *   class ApiError extends Error     fields: code, message, detail, status.
 *   api.get(path)
 *   api.post(path, body)
 *   api.patch(path, body)
 *   api.del(path)
 *
 * Every method resolves to the UNWRAPPED payload: the server's
 * `{"ok": true, ...}` body with the `ok` key removed. So
 *
 *     const state = await api.get('/state');   // -> {tree, metadata, dirty, ...}
 *     const res   = await api.del('/nodes/root_0');
 *                   // -> {deletedId, tree, zeroNodes, dirty, canUndo, canRedo}
 *
 * Every failure -- transport, non-2xx, or a 200 carrying `ok: false` -- throws
 * an ApiError. There is no success/failure branch on the return value; if the
 * promise resolves, the call worked.
 *
 * `path` is relative to /api. '/state' and 'state' and '/api/state' all work.
 * Absolute URLs are rejected outright: this app ships offline and must never
 * reach off-box.
 *
 * TOKEN / SECURITY (see fta_web/security.py for the full threat model)
 * ===================================================================
 * The token travels in the X-FTA-Token header -- never a cookie, so a foreign
 * page cannot ride on ambient authority. It arrives once, in the launch URL,
 * because a browser navigation cannot carry a header; bootstrapToken() moves
 * it into sessionStorage and rewrites the address bar so it stops leaking into
 * history and bookmarks.
 *
 * sessionStorage is per tab. A second tab opened without ?t= has no token and
 * every call here would 403. Rather than firing a wall of doomed requests, a
 * tokenless call fails immediately with code NO_SESSION, and both that case
 * and a real 403 dispatch `fta:session-invalid` on window so the shell can put
 * up one clear "relaunch the app" screen.
 */

/** Must equal config.TOKEN_HEADER in fta_web/config.py. */
export const TOKEN_HEADER = 'X-FTA-Token';

/** Fired on window when this tab has no usable session. detail: {reason}. */
export const SESSION_INVALID_EVENT = 'fta:session-invalid';

const TOKEN_KEY = 'fta.session.token';
const API_PREFIX = '/api';
const QUERY_PARAM = 't';

/**
 * Fallback when sessionStorage is unavailable (some privacy modes throw on
 * access rather than returning null). The app still works for the life of the
 * page; only a reload loses the token, which is the same failure the user
 * would get from a blocked sessionStorage anyway.
 */
let memoryToken = null;

export class ApiError extends Error {
  /**
   * @param {string} code    stable machine code, e.g. NODE_NOT_FOUND. Client
   *                         side codes: NO_SESSION, NETWORK_ERROR,
   *                         BAD_RESPONSE, INVALID_PATH.
   * @param {string} message human-readable; safe to show to the user.
   * @param {object} [detail] structured context from the server envelope.
   * @param {number} [status] HTTP status, 0 when the request never completed.
   */
  constructor(code, message, detail = null, status = 0) {
    super(message || code || 'Request failed');
    this.name = 'ApiError';
    this.code = code || 'UNKNOWN';
    this.detail = detail && typeof detail === 'object' ? detail : {};
    this.status = Number.isFinite(status) ? status : 0;
  }
}

// ---------------------------------------------------------------------------
// token storage
// ---------------------------------------------------------------------------

function readStoredToken() {
  try {
    return window.sessionStorage.getItem(TOKEN_KEY) || memoryToken;
  } catch (_err) {
    return memoryToken;
  }
}

function writeStoredToken(token) {
  memoryToken = token;
  try {
    window.sessionStorage.setItem(TOKEN_KEY, token);
  } catch (_err) {
    /* memoryToken above is the fallback; nothing else to do. */
  }
}

/** The token this tab will send, or null. */
export function getToken() {
  return readStoredToken();
}

/** True when this tab holds a session token. */
export function hasToken() {
  return Boolean(readStoredToken());
}

/** Forget the token (used when the server rejects it, so we stop retrying). */
export function clearToken() {
  memoryToken = null;
  try {
    window.sessionStorage.removeItem(TOKEN_KEY);
  } catch (_err) {
    /* ignore */
  }
}

/**
 * Bootstrap problem #1: the token can only arrive by navigation, i.e. in the
 * query string. Capture it, persist it, then scrub the URL.
 *
 * Storing happens BEFORE the rewrite on purpose: if history.replaceState were
 * to throw, we would still hold the token rather than having erased the only
 * copy the tab was given.
 *
 * @returns {string|null} the active token.
 */
export function bootstrapToken() {
  let fromUrl = null;
  try {
    const url = new URL(window.location.href);
    fromUrl = url.searchParams.get(QUERY_PARAM);
    if (fromUrl) {
      writeStoredToken(fromUrl);
      url.searchParams.delete(QUERY_PARAM);
      const query = url.searchParams.toString();
      // Rebuild by hand: URL.toString() would re-add the origin, and we only
      // ever want a same-document replace.
      window.history.replaceState(
        null,
        '',
        url.pathname + (query ? '?' + query : '') + url.hash
      );
    }
  } catch (_err) {
    // A malformed location or a blocked history API must not stop the app --
    // the token may still be in sessionStorage from an earlier load.
  }
  return readStoredToken();
}

function announceSessionInvalid(reason) {
  window.dispatchEvent(
    new CustomEvent(SESSION_INVALID_EVENT, { detail: { reason } })
  );
}

// ---------------------------------------------------------------------------
// requests
// ---------------------------------------------------------------------------

/** '/state' | 'state' | '/api/state' -> '/api/state'. Absolute URLs rejected. */
function toApiPath(path) {
  const raw = String(path == null ? '' : path);
  if (/^[a-z][a-z0-9+.-]*:/i.test(raw) || raw.startsWith('//')) {
    throw new ApiError(
      'INVALID_PATH',
      'Refusing to call an absolute address: the editor only talks to its own local server.',
      { path: raw }
    );
  }
  const withSlash = raw.startsWith('/') ? raw : '/' + raw;
  if (withSlash === API_PREFIX || withSlash.startsWith(API_PREFIX + '/')) {
    return withSlash;
  }
  return API_PREFIX + withSlash;
}

async function request(method, path, body) {
  const url = toApiPath(path);
  const token = readStoredToken();

  if (!token) {
    // Bootstrap problem #2. Fail here rather than sending a request that is
    // guaranteed to 403, so a tokenless tab produces one clear event instead
    // of a burst of failures in the network log.
    announceSessionInvalid('no_token');
    throw new ApiError(
      'NO_SESSION',
      'This browser tab has no editor session, so it cannot reach the server.',
      { reason: 'no_token' }
    );
  }

  const headers = { Accept: 'application/json' };
  headers[TOKEN_HEADER] = token;

  const init = {
    method,
    headers,
    cache: 'no-store',
    credentials: 'same-origin',
    redirect: 'follow',
  };
  if (body !== undefined && body !== null) {
    headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(url, init);
  } catch (cause) {
    throw new ApiError(
      'NETWORK_ERROR',
      'Could not reach the editor server. It may have been stopped in the terminal.',
      { method, path: url, cause: String(cause && cause.message ? cause.message : cause) }
    );
  }

  const text = await response.text().catch(() => '');
  let payload = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch (_err) {
      payload = null;
    }
  }

  if (payload === null || typeof payload !== 'object' || Array.isArray(payload)) {
    // app.py installs handlers so that even 404/405/413/500 come back as the
    // JSON envelope. Anything else means we are not talking to our server.
    throw new ApiError(
      'BAD_RESPONSE',
      `The server returned an unexpected response (HTTP ${response.status}).`,
      { method, path: url, body: text.slice(0, 200) },
      response.status
    );
  }

  if (!response.ok || payload.ok === false) {
    const envelope = (payload.error && typeof payload.error === 'object') ? payload.error : {};
    const error = new ApiError(
      envelope.code || `HTTP_${response.status}`,
      envelope.message || `Request failed with HTTP ${response.status}.`,
      envelope.detail || null,
      response.status
    );
    if (response.status === 403) {
      // Either the token is wrong/stale or Host/Origin were refused. Either
      // way this tab is done: drop the token so nothing retries with it.
      clearToken();
      announceSessionInvalid(error.detail.reason || 'forbidden');
    }
    throw error;
  }

  // Unwrap: callers get the payload without the `ok` flag.
  const { ok: _ok, ...rest } = payload;
  return rest;
}

export const api = {
  /** @returns {Promise<object>} */
  get(path) {
    return request('GET', path);
  },
  /** Body defaults to {} -- every POST endpoint tolerates an empty object. */
  post(path, body) {
    return request('POST', path, body === undefined ? {} : body);
  },
  patch(path, body) {
    return request('PATCH', path, body === undefined ? {} : body);
  },
  del(path) {
    return request('DELETE', path);
  },
};

export default api;
