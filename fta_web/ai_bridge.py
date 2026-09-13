"""
The seam between the fta_web API and the vendored AI agent.

Everything AI-shaped that is *not* HTTP lives here: the one
``AIAgentHandler`` this process owns, the worker-thread/timeout wrapper every
provider call goes through, credential masking and redaction, and the
diagnostics the full-JSON update flow needs. ``routes/ai.py`` is then a thin
translation of those into request bodies and error envelopes.

No AI logic is re-implemented. Prompts, response parsing, change application
and JSON validation all belong to ``AI_agent_handler``; this module only calls
it, off the request thread and under a timeout.


Threading: the network call never holds the document lock
---------------------------------------------------------
``state.lock`` guards the one open document. A provider call takes seconds on
a good day and can hang for as long as the socket stays open, so it must never
be made with that lock held -- the whole editor (rendering, saving, undo)
would freeze behind an unreachable API. Every route therefore follows:

1. take ``state.lock``, deep-copy the tree, release it,
2. call the provider through :func:`run_ai_call` -- a fresh daemon thread with
   a ``config.AI_TIMEOUT_SECONDS`` deadline,
3. take ``state.lock`` again to apply whatever came back.

The worker thread only ever talks to the provider and to the handler. It never
touches ``AppState``, so a request that timed out cannot mutate the document
later from a thread nobody is waiting on any more.

Python cannot kill a thread stuck in a socket read, so a timed-out call leaves
its worker running. :func:`run_ai_call` accounts for that with a single-slot
lock that the *worker* releases, not the caller: while a zombie call is still
out there the next AI request is refused with :class:`AiBusy` rather than being
allowed to race it for the handler's conversation history. The thread is a
daemon so a hung provider can never stop the process from exiting on Ctrl-C.


The API key never leaves this process
-------------------------------------
Two mechanisms, because one is not enough:

* **Nothing reports the key.** :func:`credentials_status` returns
  :func:`mask_key`'s preview (``sk-...AB12``) and never the key itself; no
  payload assembled here carries an ``api_key`` field.
* **Everything provider-shaped is scrubbed.** Provider SDKs put their own
  strings into error messages, and at least one provider (Gemini) puts the key
  in a URL query parameter that can surface in one. So every string that
  originates outside this process -- connection-test messages, model-fetch
  warnings, chat replies, raw AI output excerpts -- goes through
  :func:`scrub`/:func:`scrub_deep` before it reaches a response body or a log
  line. The route layer applies it at the boundary; see ``routes/ai.py``.

Import style
------------
Mirrors ``state.py``: prefer ``from fta_web.ai_bridge import ...``. The bare
fallback exists for a launcher that puts ``fta_web/`` itself on ``sys.path``,
and mixing the two in one process would create two module objects and
therefore two handlers with two separate conversation histories.
"""
from __future__ import annotations

import copy
import json
import logging
import re
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

try:  # normal package import: ``import fta_web.ai_bridge``
    from . import config
except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
    import config  # type: ignore[no-redef]

# Importing config placed fta_web/core on sys.path, so the vendored modules
# import under their bare names. See config.py for why that is mandatory.
from AI_agent_handler import (  # noqa: E402
    AIAgentHandler,
    AICredentialManager,
    AIProposedChange,
)
# Aliased on import: the vendored name would look like a test to pytest and
# like a local helper to a reader. It is the module-level convenience wrapper
# at AI_agent_handler.py:1037, and it is the only supported way to check a key.
from AI_agent_handler import test_connection as provider_test_connection  # noqa: E402
from ai_providers import AIProviderFactory  # noqa: E402

log = logging.getLogger(__name__)


# ---- failures ------------------------------------------------------------


class AiError(Exception):
    """Base class for the failures this module reports to the route layer."""


class AiBusy(AiError):
    """Another AI call is still in flight (possibly a timed-out zombie)."""


class AiTimeout(AiError):
    """The provider did not answer within ``config.AI_TIMEOUT_SECONDS``."""


class AiCallFailed(AiError):
    """The provider call raised. ``__cause__`` carries the original."""


class UnknownProvider(AiError):
    """The requested provider name is not one the vendored factory knows."""


# ---- the process-wide handler -------------------------------------------
#
# One handler, because the conversation history and the pending change list
# are per-session state that the desktop editor also keeps per-process. It is
# created lazily: AIAgentHandler.__init__ builds an AICredentialManager, which
# mkdir's ~/.fta_editor as a side effect, and merely importing this module
# should not touch the user's home directory.

_handler: Optional[AIAgentHandler] = None
_handler_lock = threading.Lock()


def get_handler() -> AIAgentHandler:
    """The one ``AIAgentHandler`` for this process, created on first use."""
    global _handler
    with _handler_lock:
        if _handler is None:
            _handler = AIAgentHandler()
        return _handler


def reset_handler() -> AIAgentHandler:
    """Replace the handler with a fresh one and return it.

    Used by tests to get an isolated conversation, and the honest way to drop
    a session's AI state without leaving stale references behind. Mirrors
    ``state.reset_state()``.
    """
    global _handler
    with _handler_lock:
        _handler = AIAgentHandler()
        return _handler


# ---- worker thread + timeout --------------------------------------------

#: Single-slot mutex around the handler. Acquired by the request thread,
#: released by the worker -- see the module docstring. A plain Lock, not an
#: RLock, precisely because it is released by a different thread than the one
#: that took it.
_call_slot = threading.Lock()


def _timeout_seconds() -> float:
    """The provider deadline, read at call time so tests can shorten it."""
    return float(getattr(config, "AI_TIMEOUT_SECONDS", 120))


def run_ai_call(label: str, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run one provider call off the request thread, under a deadline.

    Args:
        label: short name for the thread, e.g. ``"chat"``. Diagnostic only.
        func: the vendored callable to run. It must not touch ``AppState``.

    Returns:
        Whatever ``func`` returned.

    Raises:
        AiBusy: another call holds the slot.
        AiTimeout: the deadline passed. The worker keeps running and keeps the
            slot until it finishes, so the next request is refused rather than
            racing it.
        AiCallFailed: ``func`` raised.
    """
    timeout = _timeout_seconds()

    if not _call_slot.acquire(blocking=False):
        raise AiBusy(
            "Another AI request is still running. The AI is answered one "
            "request at a time so replies cannot interleave in the "
            "conversation; wait for the current one to finish, or restart the "
            "editor if the provider has stopped responding."
        )

    outcome: Dict[str, Any] = {}
    finished = threading.Event()

    def worker() -> None:
        try:
            outcome["value"] = func(*args, **kwargs)
        except BaseException as exc:  # noqa: BLE001 - re-raised on the caller
            outcome["error"] = exc
        finally:
            # Released before ``finished`` is set, so a caller that wakes up
            # immediately finds the slot free instead of a spurious AiBusy.
            # Safe in either order for the timed-out case: by the time this
            # runs the worker has stopped touching the handler.
            _call_slot.release()
            finished.set()

    thread = threading.Thread(target=worker, name="ai-%s" % label, daemon=True)
    try:
        thread.start()
    except BaseException:
        _call_slot.release()
        raise

    if not finished.wait(timeout):
        # Worth a log line: the slot stays held until this worker returns, so
        # the next AI request will be refused with AiBusy, and this is the only
        # place that explains why.
        log.warning(
            "AI call %r exceeded %gs. Its worker is still running and keeps "
            "the AI call slot until the provider answers.",
            label,
            timeout,
        )
        raise AiTimeout(
            "The AI provider did not respond within %g seconds. Nothing was "
            "changed. Check the endpoint and model in AI settings, or try "
            "again -- a large tree can take a while to analyse."
            % timeout
        )

    if "error" in outcome:
        raise AiCallFailed(str(outcome["error"]) or outcome["error"].__class__.__name__) from outcome["error"]

    return outcome["value"]


# ---- secrets -------------------------------------------------------------

#: What a redacted secret is replaced with. Deliberately not a run of asterisks
#: matching the key's length -- that leaks the length.
REDACTED = "[redacted]"

#: Below this, a "key" is more likely to be a placeholder than a credential,
#: and replacing short strings would corrupt unrelated text.
_MIN_SECRET_LENGTH = 8

#: Below this, revealing three leading and four trailing characters would show
#: most of the value, so the preview shows nothing at all.
_MASK_MIN_LENGTH = 16


def mask_key(api_key: Any) -> str:
    """A preview safe to put in a response: ``sk-...AB12``.

    Never returns anything that could be pasted back into a provider. Short
    values are masked completely rather than partially.
    """
    if not isinstance(api_key, str):
        return ""
    key = api_key.strip()
    if not key:
        return ""
    if len(key) < _MASK_MIN_LENGTH:
        return "…"
    return "%s…%s" % (key[:3], key[-4:])


def _stored_api_key() -> Optional[str]:
    """The saved key, for redaction only. Never returned to a caller."""
    credentials = load_stored_credentials()
    if not credentials:
        return None
    key = credentials.get("api_key")
    return key if isinstance(key, str) and key.strip() else None


def scrub(text: Any, *extra_secrets: Optional[str]) -> Any:
    """Remove every known API key from a string.

    Applied to anything that came from a provider before it is put in a
    response body or a log line: SDK error messages quote request URLs and
    headers, and a key in a query parameter would otherwise ride straight out
    to the browser. ``extra_secrets`` covers the key being tested, which is not
    on disk yet.
    """
    if not isinstance(text, str):
        return text
    cleaned = text
    for secret in list(extra_secrets) + [_stored_api_key()]:
        if not isinstance(secret, str):
            continue
        secret = secret.strip()
        if len(secret) >= _MIN_SECRET_LENGTH:
            cleaned = cleaned.replace(secret, REDACTED)
    return cleaned


def scrub_deep(value: Any, *extra_secrets: Optional[str]) -> Any:
    """:func:`scrub`, applied through lists and dicts.

    Error details carry raw AI output and reconstructed JSON nodes, which are
    attacker-adjacent text this process is about to echo back. Scrubbing the
    whole structure costs nothing and removes the need to remember which field
    is provider-derived.
    """
    if isinstance(value, str):
        return scrub(value, *extra_secrets)
    if isinstance(value, list):
        return [scrub_deep(item, *extra_secrets) for item in value]
    if isinstance(value, dict):
        return {key: scrub_deep(item, *extra_secrets) for key, item in value.items()}
    return value


# ---- credentials ---------------------------------------------------------


def load_stored_credentials() -> Optional[Dict[str, Any]]:
    """The saved credential dict, or None. Failures are "not configured"."""
    try:
        credentials, error = AICredentialManager().load_credentials()
    except Exception:  # pragma: no cover - unreadable home directory
        return None
    if error or not isinstance(credentials, dict):
        return None
    return credentials


def is_configured() -> bool:
    """Whether AI credentials are on disk.

    Deliberately the same question ``state._ai_configured()`` asks, by the same
    route (``AICredentialManager.has_credentials()``), so ``/api/ai/credentials``
    and ``/api/state``'s ``capabilities.aiConfigured`` can never disagree.
    """
    try:
        return bool(AICredentialManager().has_credentials())
    except Exception:  # pragma: no cover - unreadable home directory
        return False


def credentials_status() -> Dict[str, Any]:
    """The masked credential view. This is the *only* credential payload.

    There is no variant of this that includes the key, on purpose: a single
    function means a single place to audit.
    """
    if not is_configured():
        return {
            "configured": False,
            "provider": None,
            "endpoint": None,
            "model": None,
            "keyPreview": None,
        }

    credentials = load_stored_credentials() or {}
    return {
        "configured": True,
        "provider": credentials.get("provider"),
        "endpoint": credentials.get("api_endpoint"),
        "model": credentials.get("model"),
        "keyPreview": mask_key(credentials.get("api_key")),
    }


# ---- providers -----------------------------------------------------------


def resolve_provider(name: Any) -> Tuple[str, Any]:
    """``(canonical display name, provider instance)`` for a provider name.

    Accepts every spelling ``AIProviderFactory`` accepts ("claude",
    "Anthropic Claude", ...) and returns the display name the factory itself
    reports, which is what gets written to the credentials file -- so a key
    saved here is a key the desktop editor's dialog can read back.
    """
    if not isinstance(name, str) or not name.strip():
        raise UnknownProvider("A provider name is required.")
    provider = AIProviderFactory.get_provider(name)
    if provider is None:
        raise UnknownProvider(
            "Unknown AI provider %r. Supported: %s."
            % (name, ", ".join(provider_names()))
        )
    return provider.get_provider_name(), provider


def provider_names() -> List[str]:
    """Canonical display names, in the factory's registration order."""
    return list(AIProviderFactory.get_all_providers().keys())


def provider_catalog() -> List[Dict[str, Any]]:
    """Every provider the vendored factory offers, with its defaults.

    Read from ``AIProviderFactory.get_all_providers()`` rather than hardcoded,
    so this list is by construction the same one the desktop settings dialog
    shows (``src/FTA_Editor_UI.py:339``) and cannot drift from it.
    """
    catalog: List[Dict[str, Any]] = []
    for display_name, provider in AIProviderFactory.get_all_providers().items():
        catalog.append(
            {
                "name": display_name,
                "defaultEndpoint": provider.get_default_endpoint(),
                "defaultModels": list(provider.get_default_models()),
            }
        )
    return catalog


def default_model_for(provider: Any) -> str:
    """The model a settings dialog would pre-select: the first default."""
    models = list(provider.get_default_models())
    return models[0] if models else ""


def list_models(provider_name: Any, endpoint: Any = None) -> Dict[str, Any]:
    """The model list for a provider, live where possible.

    A live fetch needs a key, and the key is never accepted in a query string
    (it would land in every access log and browser history on the way), so the
    saved one is used -- and only when it belongs to the provider being asked
    about. Anything that stops a live answer, including no saved key at all,
    degrades to the provider's built-in list with ``source: "fallback"`` and a
    ``warning`` that says why. It never fails: a settings dialog with no model
    list is a dialog the user cannot complete.

    ``source: "live"`` means the provider reported no error. Anthropic has no
    list-models endpoint and answers with its built-in list and no error
    (``ai_providers.py:144``), so "live" is the provider's claim, not proof of
    a round trip.
    """
    canonical, provider = resolve_provider(provider_name)
    resolved_endpoint = (
        endpoint.strip() if isinstance(endpoint, str) and endpoint.strip() else None
    ) or provider.get_default_endpoint()
    defaults = list(provider.get_default_models())

    def fallback(warning: str) -> Dict[str, Any]:
        return {
            "provider": canonical,
            "endpoint": resolved_endpoint,
            "models": defaults,
            "source": "fallback",
            "warning": warning,
        }

    stored = load_stored_credentials() or {}
    api_key = stored.get("api_key")
    stored_provider = stored.get("provider")
    try:
        stored_canonical = resolve_provider(stored_provider)[0] if stored_provider else None
    except UnknownProvider:
        stored_canonical = None

    if not api_key or stored_canonical != canonical:
        return fallback(
            "No saved API key for %s, so the live model list could not be "
            "fetched. These are the built-in defaults; the model field accepts "
            "any name you type." % canonical
        )

    try:
        models, warning = run_ai_call(
            "models", provider.get_available_models, api_key, resolved_endpoint
        )
    except AiError as exc:
        return fallback(scrub(str(exc), api_key))

    if warning:
        return fallback(scrub(warning, api_key))
    if not models:
        return fallback(
            "%s returned an empty model list. These are the built-in defaults."
            % canonical
        )

    return {
        "provider": canonical,
        "endpoint": resolved_endpoint,
        "models": [scrub(str(name), api_key) for name in models],
        "source": "live",
    }


def test_and_save_credentials(
    provider_name: Any,
    api_key: str,
    endpoint: Any = None,
    model: Any = None,
) -> Tuple[bool, str, Dict[str, Any]]:
    """Test a key against its provider and save it only if the test passes.

    Returns ``(saved, message, resolved)``. ``message`` is the provider's own
    wording -- scrubbed -- because "OpenAI connection failed: 401
    Incorrect API key provided" tells the user what to fix and a generic
    "connection failed" does not. ``resolved`` carries the provider, endpoint
    and model actually used, so the caller can echo back what was stored
    rather than what was typed.

    Nothing is written on failure. A bad key that overwrote a working one
    would break the editor's AI for a typo.
    """
    canonical, provider = resolve_provider(provider_name)
    resolved_endpoint = (
        endpoint.strip() if isinstance(endpoint, str) and endpoint.strip() else None
    ) or provider.get_default_endpoint()
    resolved_model = (
        model.strip() if isinstance(model, str) and model.strip() else None
    ) or default_model_for(provider)

    resolved = {
        "provider": canonical,
        "endpoint": resolved_endpoint,
        "model": resolved_model,
    }

    ok, message = run_ai_call(
        "test-connection",
        provider_test_connection,
        api_key,
        resolved_endpoint,
        resolved_model,
        canonical,
    )
    message = scrub(str(message), api_key)

    if not ok:
        return False, message, resolved

    saved, error = get_handler().configure(
        api_key, resolved_endpoint, resolved_model, canonical
    )
    if not saved:
        return False, scrub(str(error or "Could not save credentials."), api_key), resolved

    return True, message, resolved


def delete_credentials() -> Tuple[bool, Optional[str]]:
    """Forget the saved key.

    The handler caches its provider instance after the first call
    (``AI_agent_handler.py:351``) and ``AICredentialManager.delete_credentials``
    knows nothing about that cache, so it is cleared here. Without this the
    next request would still find a live provider object and try to use the
    key that was just deleted.
    """
    handler = get_handler()
    ok, error = handler.credential_manager.delete_credentials()
    handler.provider = None
    return ok, error


# ---- proposed changes ----------------------------------------------------


def change_view(change: AIProposedChange, index: Optional[int]) -> Dict[str, Any]:
    """One proposed change, camelCased like the rest of the API.

    ``index`` is the change's position in the handler's pending list, which is
    what ``POST /api/ai/changes/apply`` takes. The client needs it because
    ``pending_changes`` accumulates across a conversation while each reply only
    reports the changes it just parsed.
    """
    return {
        "index": index,
        "changeType": change.change_type,
        "targetId": change.target_id,
        "description": change.description,
        "data": copy.deepcopy(change.data or {}),
    }


def pending_index(handler: AIAgentHandler, change: AIProposedChange) -> Optional[int]:
    """Where ``change`` sits in ``handler.pending_changes``, by identity.

    By identity rather than by arithmetic on list lengths: ``send_message``
    extends the pending list itself, and an identity search cannot be wrong
    about which entry a returned change actually is.
    """
    for index, pending in enumerate(handler.pending_changes):
        if pending is change:
            return index
    return None


def changes_view(
    handler: AIAgentHandler, changes: List[AIProposedChange]
) -> List[Dict[str, Any]]:
    """Serialize the changes one call proposed, with their pending indices."""
    return [change_view(change, pending_index(handler, change)) for change in changes or []]


def pending_changes_view(handler: AIAgentHandler) -> List[Dict[str, Any]]:
    """The whole pending list, indices included."""
    return [
        change_view(change, index)
        for index, change in enumerate(handler.pending_changes)
    ]


# ---- full-JSON update diagnostics ---------------------------------------
#
# The desktop editor's Update FTA flow (src/FTA_Editor_UI.py:855-895) does not
# just say "invalid JSON": on a parse failure it prints the first 500
# characters of what the model actually said, and on a validation failure it
# locates the offending node and prints that node's JSON. That detail is the
# only thing that makes an unusable AI answer diagnosable, so it is reproduced
# here rather than collapsed into a status code.

#: Excerpt length and snippet cap, both from the desktop flow.
PARSE_EXCERPT_CHARS = 500
SECTION_SNIPPET_CHARS = 1500

#: How a node id is recovered from a validator message. The first pattern is
#: the desktop's (FTA_Editor_UI.py:867) and matches the majority of
#: ``verify_updated_fta_json``'s wording ("Invalid type for node X: ...",
#: "NOT gates are not supported (node X): ..."). It mis-fires on
#: "Duplicate node ID: X", where it captures the literal "ID"; the second
#: pattern recovers that case. Patterns are tried in order and the first one
#: that names a node actually present in the tree wins, so adding one can only
#: turn a missing snippet into a correct one.
_OFFENDING_ID_PATTERNS = (
    re.compile(r"node\s+([A-Za-z0-9_]+)"),
    re.compile(r"Duplicate node ID:\s*([A-Za-z0-9_]+)"),
)


def parse_excerpt(assistant_text: Any) -> str:
    """The first 500 characters of raw AI output, on one line.

    Byte-for-byte the desktop's excerpt (FTA_Editor_UI.py:858): stripped,
    newlines flattened to spaces, truncated. Flattened because it is shown as
    a single diagnostic line, and truncated because a model that ignored
    "return only JSON" can return an essay.
    """
    if not isinstance(assistant_text, str):
        assistant_text = "" if assistant_text is None else str(assistant_text)
    return assistant_text.strip().replace("\n", " ")[:PARSE_EXCERPT_CHARS]


def find_node_in_tree(root: Any, node_id: Any) -> Optional[Dict[str, Any]]:
    """Depth-first search of a raw (unvalidated) tree for a node id.

    Works on the AI's output, which has not been through ``FTACore`` and may be
    malformed anywhere -- hence the isinstance guards rather than
    ``core.find_node_by_id``.
    """
    if not isinstance(root, dict) or node_id is None:
        return None
    if root.get("id") == node_id:
        return root
    for child in root.get("children") or []:
        found = find_node_in_tree(child, node_id)
        if found is not None:
            return found
    return None


def locate_offending_node(
    updated: Any, validator_message: Any
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """``(node id, node)`` for the node a validator message blames.

    Both are None when the message names no node that exists in the tree --
    "Missing root field: children" and "Top-level FTA must be a JSON object"
    are about the document, not a node.
    """
    message = validator_message if isinstance(validator_message, str) else ""
    for pattern in _OFFENDING_ID_PATTERNS:
        match = pattern.search(message)
        if not match:
            continue
        candidate = match.group(1)
        node = find_node_in_tree(updated, candidate)
        if node is not None:
            return candidate, node
    return None, None


def validation_diagnostics(updated: Any, validator_message: Any) -> Dict[str, Any]:
    """Everything known about why an updated tree was rejected.

    ``node`` is the offending node's own JSON, which is what makes the
    validator message actionable -- "Invalid type for node n_3: Condition" is
    a shrug until you can see that n_3 is the node the model invented a type
    for. ``section`` is that node pretty-printed and capped, matching what the
    desktop writes into its chat log; when no node can be located it falls back
    to the document's top-level keys, exactly as the desktop does.
    """
    node_id, node = locate_offending_node(updated, validator_message)

    section: Optional[str] = None
    if node is not None:
        try:
            section = json.dumps(node, indent=2)
        except (TypeError, ValueError):  # pragma: no cover - non-serializable AI output
            section = str(node)
    elif isinstance(updated, dict):
        section = "Top-level keys: " + ", ".join(str(key) for key in updated.keys())

    return {
        "validatorMessage": validator_message,
        "nodeId": node_id,
        "node": copy.deepcopy(node) if node is not None else None,
        "section": section[:SECTION_SNIPPET_CHARS] if section else None,
    }
