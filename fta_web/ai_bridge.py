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

Two things are added around the vendored handler rather than inside it (the
core is hash-pinned, and both need this package's engine and validators):

* **What the model is told about the numbers** (:func:`analysis_section`).
  The handler's context gives every node's tree-walk value and calls the
  root's the "Top-level Probability". For a tree with repeated events the
  editor's headline is the MCUB, so the model would "find" the double
  counting the tool already corrects. An "Analysis results" section with the
  headline, its method, the repeated events and the top cut sets is appended
  to the context (FTA mode only).
* **Links in a suggestion** (:func:`apply_change`). The handler's add/edit
  write name, type, probability, gate and notes and nothing else, while its
  prompt invites link suggestions: a suggested link was dropped and the
  change still reported as applied.

What applying a suggestion promises
-----------------------------------
A suggestion is applied **as a whole or not at all**. Anything in it that is
not valid -- a link whose target does not exist, a link to the node itself,
the same link twice, a relation other than AND/OR, a probability outside
[0, 1] -- rejects that one suggestion with the reason, and the tree is as it
was before it; the other suggestions of the batch are still applied. Nothing
is ever applied in part and reported as done.

The one thing that is not an error: keys a suggestion can never change
(``children`` on an added node -- each child is its own suggestion -- and the
1.7 keys the model is not shown). They are returned per applied change as
``ignored`` and the chat names them, so "applied" never claims them either.


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

:func:`cancel_ai_call` (Stop in the chat) frees the slot without waiting for
the worker: the call is abandoned, and the process moves to a new handler so
that the abandoned worker has nothing shared left to write to.


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
import weakref
from typing import Any, Callable, Dict, List, Optional, Tuple

try:  # normal package import: ``import fta_web.ai_bridge``
    from . import config
    from .engine import derive_quant, summary_with_cut_sets
    from .errors import ApiError
    from .node_schema import (
        NODE_KEYS,
        VALIDATORS,
        canonical_mode,
        drop_duplicate_links,
        refuse_unsavable_text,
        validate_links,
    )
    from .tree_ops import all_ids
except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
    import config  # type: ignore[no-redef]
    from engine import derive_quant, summary_with_cut_sets  # type: ignore[no-redef]
    from errors import ApiError  # type: ignore[no-redef]
    from node_schema import (  # type: ignore[no-redef]
        NODE_KEYS,
        VALIDATORS,
        canonical_mode,
        drop_duplicate_links,
        refuse_unsavable_text,
        validate_links,
    )
    from tree_ops import all_ids  # type: ignore[no-redef]

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


class AiCancelled(AiError):
    """The call was abandoned by :func:`cancel_ai_call` (Stop in the chat)."""


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



class WebAgentHandler(AIAgentHandler):
    """The vendored handler, with the editor's own results in its context.

    ``set_fta_context`` is where every path (chat, Analyze, Update FTA)
    builds what the model is shown, two of them from inside the handler, so
    this is the one place that reaches all three without editing the core.
    """

    #: The "Analysis results" text for the call in flight, set and cleared by
    #: :func:`with_analysis` inside the call slot. Empty: the context is the
    #: vendored handler's, byte for byte (ETA mode, cut sets unavailable).
    analysis_section = ""

    def set_fta_context(self, fta_data, mode="FTA", title=""):
        super().set_fta_context(fta_data, mode, title)
        if self.analysis_section:
            # The summary's first line calls the root's tree-walk value the
            # top-level probability; with the headline below it, say which.
            self.current_fta_context = self.current_fta_context.replace(
                "- Top-level Probability: ", "- Top-level Probability (tree walk): ", 1
            ) + "\n\n" + self.analysis_section


_handler: Optional[AIAgentHandler] = None
_handler_lock = threading.Lock()


def get_handler() -> AIAgentHandler:
    """The one ``AIAgentHandler`` for this process, created on first use."""
    global _handler
    with _handler_lock:
        if _handler is None:
            _handler = WebAgentHandler()
        return _handler


def existing_handler() -> Optional[AIAgentHandler]:
    """The handler if one has been created, else None -- without creating it.

    For a read that must stay free of side effects (GET /api/ai/conversation
    runs on every page load): creating a handler makes ``~/.fta_editor``.
    """
    with _handler_lock:
        return _handler


def reset_handler() -> AIAgentHandler:
    """Replace the handler with a fresh one and return it.

    Used by tests to get an isolated conversation, and the honest way to drop
    a session's AI state without leaving stale references behind. Mirrors
    ``state.reset_state()``.
    """
    global _handler
    with _handler_lock:
        _handler = WebAgentHandler()
        return _handler


# ---- worker thread + timeout --------------------------------------------


class _Call:
    """One provider call in flight: what :func:`cancel_ai_call` needs of it."""

    __slots__ = ("label", "request_id", "done", "abandoned", "outcome",
                 "handler", "history", "history_len", "pending")

    def __init__(self, label: str, request_id: Optional[str]) -> None:
        self.label = label
        self.request_id = request_id
        #: Set when the worker returned, or when the call was abandoned.
        self.done = threading.Event()
        self.abandoned = False
        self.outcome: Dict[str, Any] = {}
        #: The handler the call works on, and what it held when the call
        #: began (see cancel_ai_call).
        self.handler: Optional[AIAgentHandler] = None
        self.history: Any = None
        self.history_len = 0
        self.pending: List[Any] = []


#: The call that holds the single AI slot, or None. Taken by the request
#: thread and given back by the worker -- see the module docstring -- or by
#: :func:`cancel_ai_call`, which abandons the call instead of waiting for it.
_active: Optional[_Call] = None
#: Guards ``_active`` and the handler swap of a cancel. Never held across a
#: provider call.
_active_lock = threading.Lock()


class _CallSlot:
    """The single slot, seen as the lock it used to be: ``locked()`` says
    whether a call holds it."""

    @staticmethod
    def locked() -> bool:
        return _active is not None


_call_slot = _CallSlot()

_next_request = threading.local()


def tag_next_call(request_id: Optional[str]) -> None:
    """Name the call this thread is about to make with :func:`run_ai_call`
    (the ``requestId`` the page sent), so that a cancel can say which call it
    means. One call only: :func:`run_ai_call` takes the name and clears it."""
    _next_request.value = request_id


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
        AiCancelled: :func:`cancel_ai_call` abandoned this call. Whatever the
            provider answers later is dropped.
        AiCallFailed: ``func`` raised.
    """
    global _active
    timeout = _timeout_seconds()
    request_id = getattr(_next_request, "value", None)
    _next_request.value = None

    call = _Call(label, request_id)
    with _active_lock:
        if _active is not None:
            raise AiBusy(
                "Another AI request is still running. The AI is answered one "
                "request at a time so replies cannot interleave in the "
                "conversation; wait for the current one to finish, or restart the "
                "editor if the provider has stopped responding."
            )
        _active = call
        # What the handler holds now. A cancelled call's late answer must not
        # stay in the conversation, and "what was there before" is how the
        # cancel tells the two apart.
        handler = existing_handler()
        call.handler = handler
        if handler is not None:
            call.history = handler.conversation_history
            call.history_len = len(call.history)
            call.pending = list(handler.pending_changes)

    outcome = call.outcome

    def release() -> None:
        global _active
        with _active_lock:
            if _active is call:  # not when it was abandoned: the slot moved on
                _active = None

    def worker() -> None:
        try:
            outcome["value"] = func(*args, **kwargs)
        except BaseException as exc:  # noqa: BLE001 - re-raised on the caller
            outcome["error"] = exc
        finally:
            # Released before ``done`` is set, so a caller that wakes up
            # immediately finds the slot free instead of a spurious AiBusy.
            # Safe in either order for the timed-out case: by the time this
            # runs the worker has stopped touching the handler.
            release()
            call.done.set()

    thread = threading.Thread(target=worker, name="ai-%s" % label, daemon=True)
    try:
        thread.start()
    except BaseException:
        release()
        raise

    finished = call.done.wait(timeout)
    if call.abandoned:
        raise AiCancelled(
            "The AI request was stopped. Nothing was changed, and whatever the "
            "provider still answers to it is ignored."
        )
    if not finished:
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


def cancel_ai_call(request_id: Optional[str] = None) -> bool:
    """Abandon the provider call in flight, and free the slot at once.

    The provider's HTTP call cannot be interrupted (Python cannot stop a
    thread in a socket read), so the call is *abandoned*: its request is
    answered :class:`AiCancelled` now, the next request is accepted now, and
    whatever the provider answers later goes nowhere.

    "Nowhere" needs one more step than a flag, because the vendored handler
    itself writes the answer down: ``send_message`` appends the two turns to
    ``conversation_history`` and the parsed proposals to ``pending_changes``
    when the provider returns, on the worker, long after this function. So
    the process gets a **new handler** that holds what the old one held when
    the call began, and the worker is left with the old one, which nothing
    reads any more. The next call cannot race the abandoned one for the
    conversation either: they no longer share it.

    ``request_id`` (when given) must be the id the call was started with:
    Stop in one tab does not abandon a request another tab has made since.
    A call that timed out and still holds the slot is abandoned the same way.

    Returns whether a call was abandoned. False is not an error: the call
    had finished, or there was none.
    """
    global _active, _handler
    with _active_lock:
        call = _active
        if call is None:
            return False
        if request_id is not None and call.request_id != request_id:
            return False
        call.abandoned = True
        _active = None
        with _handler_lock:
            old = _handler
            if old is not None and old is call.handler:
                fresh = WebAgentHandler()
                history = old.conversation_history
                if history is call.history:
                    # Only the abandoned call appends while it runs.
                    fresh.conversation_history = list(history[:call.history_len])
                # else: the conversation was cleared during the call, and
                # anything in it since is the abandoned call's. Left empty.
                before = {id(change) for change in call.pending}
                fresh.pending_changes = [change for change in list(old.pending_changes)
                                         if id(change) in before]
                fresh.on_message_callback = old.on_message_callback
                _handler = fresh
    call.done.set()
    log.info("AI call %r was abandoned on request.", call.label)
    return True


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


def call_secret() -> Optional[str]:
    """The saved key, read *before* a provider call, to scrub its answer with.

    :func:`scrub` redacts the key stored when it runs. A call that is still
    out when the user clears the credentials answers after its key is gone,
    so a provider error quoting that key would otherwise reach the browser.
    For ``extra_secrets`` only; it never goes into a payload.
    """
    return _stored_api_key()


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
    shows (``desktop/src/FTA_Editor_UI.py:339``) and cannot drift from it.
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

    ``source: "live"`` means the provider reported no error. OpenAI,
    Anthropic (divergence D22) and Gemini really ask; Azure answers with its
    built-in list and a warning, so it is always "fallback".
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

    Saving a different recipient -- another provider, or another endpoint,
    which for an OpenAI-compatible gateway is another service -- forgets the
    conversation history, so the new one is never sent the old conversation.
    Nothing saved counts as different: that also covers a call that was still
    out when the credentials were cleared and appended its exchange later
    (this save needs the call slot, so that call has finished by now). A new
    key for the same recipient keeps it. Pending proposals belong to the
    document and are kept.
    """
    canonical, provider = resolve_provider(provider_name)
    resolved_endpoint = (
        endpoint.strip() if isinstance(endpoint, str) and endpoint.strip() else None
    ) or provider.get_default_endpoint()
    previous = _recipient(load_stored_credentials() or {})
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

    handler = get_handler()
    saved, error = handler.configure(
        api_key, resolved_endpoint, resolved_model, canonical
    )
    if not saved:
        return False, scrub(str(error or "Could not save credentials."), api_key), resolved
    if previous != (canonical, resolved_endpoint):
        handler.conversation_history = []

    return True, message, resolved


def _recipient(credentials: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """``(canonical provider, endpoint)`` a saved conversation is sent to."""
    name = credentials.get("provider")
    try:
        canonical = resolve_provider(name)[0] if name else None
    except UnknownProvider:
        canonical = None
    endpoint = credentials.get("api_endpoint")
    return canonical, endpoint.strip() if isinstance(endpoint, str) else None


def delete_credentials() -> Tuple[bool, Optional[str]]:
    """Forget the saved key -- and the conversation that went with it.

    The handler caches its provider instance after the first call
    (``AI_agent_handler.py:351``) and ``AICredentialManager.delete_credentials``
    knows nothing about that cache, so it is cleared here. Without this the
    next request would still find a live provider object and try to use the
    key that was just deleted.

    The conversation history goes too: Clear Chat cannot run without
    credentials, so after Clear here it would otherwise be kept and sent to
    whichever provider is configured next. Pending proposals stay; they belong
    to the document, not to the provider.
    """
    handler = get_handler()
    ok, error = handler.credential_manager.delete_credentials()
    handler.provider = None
    if ok:
        handler.conversation_history = []
    return ok, error


# ---- proposed changes ----------------------------------------------------


def change_view(change: AIProposedChange, index: Optional[int], tree: Any = None,
                pending: Any = ()) -> Dict[str, Any]:
    """One proposed change, camelCased like the rest of the API.

    ``index`` is the change's position in the handler's pending list, which is
    what ``POST /api/ai/changes/apply`` takes. The client needs it because
    ``pending_changes`` accumulates across a conversation while each reply only
    reports the changes it just parsed.

    With ``tree`` (the document the model was shown), a change that sets
    ``links`` also carries ``linkChanges`` -- see :func:`link_changes` -- so
    the chat card can show what approving it adds and removes.
    """
    view = {
        "index": index,
        "changeType": change.change_type,
        "targetId": change.target_id,
        "description": change.description,
        "data": copy.deepcopy(change.data or {}),
    }
    if tree is not None:
        preview = link_changes(change, tree, pending)
        if preview is not None:
            view["linkChanges"] = preview
    return view


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
    handler: AIAgentHandler, changes: List[AIProposedChange], tree: Any = None
) -> List[Dict[str, Any]]:
    """Serialize the changes one call proposed, with their pending indices
    (and, given the ``tree`` they were proposed for, their link changes)."""
    pending = list(handler.pending_changes)
    return [change_view(change, pending_index(handler, change), tree, pending)
            for change in changes or []]


def pending_changes_view(handler: AIAgentHandler) -> List[Dict[str, Any]]:
    """The whole pending list, indices included."""
    return [
        change_view(change, index)
        for index, change in enumerate(handler.pending_changes)
    ]


# ---- what the model is told about the results ----------------------------
#
# Deterministic text, built from the same summary the top bar shows and the
# cut sets it was derived from (one expansion, the summary's own caps and its
# 2 s budget). Compact on purpose: it is sent with every message.

#: How many minimal cut sets, and repeated events, the section lists.
ANALYSIS_TOP_CUT_SETS = 10
ANALYSIS_MAX_REPEATED = 20
#: A node name in the section is cut to this many characters.
ANALYSIS_NAME_CHARS = 48

ANALYSIS_HEADER = "--- Analysis results (computed by FTA Editor; use these, do not recompute) ---"
ANALYSIS_FOOTER = "--- End of analysis results ---"

_APPROXIMATION_TEXT = {
    "PAND_APPROX": "priority-AND gate %s is computed as product/n! (the sequence is not "
                   "modelled; the cut sets treat it as AND)",
    "XOR_ARITY": "XOR gate %s has other than two inputs and is computed as odd parity",
    "STANDBY_LARGE_LT": "standby event %s has lambda*tau > 0.2, where the lambda*tau/2 "
                        "approximation is inaccurate",
}


def _six(value: Any) -> str:
    """A number at six significant figures; "n/a" when there is none."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "n/a"
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        return "n/a"
    return "%.6g" % number


def _named(node_id: Any, name: Any) -> str:
    """``id "name"``, the name on one line and cut to ANALYSIS_NAME_CHARS."""
    text = " ".join(str(name if name is not None else "").split())
    if len(text) > ANALYSIS_NAME_CHARS:
        text = text[: ANALYSIS_NAME_CHARS - 1] + "…"
    return '%s "%s"' % (node_id, text)


def analysis_section(tree: Any, mode: Any = "FTA", analysis: Any = None) -> str:
    """The "Analysis results" text appended to the model's context, or "".

    "" -- nothing is added, the context is the vendored handler's -- in ETA
    mode (an event tree has no cut sets) and when the cut sets cannot be had
    (a voting gate too large, the 2 s budget, any failure): the section must
    never cost the user their AI call.

    Otherwise, in this order: the headline and its method, with one sentence
    saying that an MCUB headline already counts each repeated event once; the
    tree-walk value; the other bound; the repeated events; the top
    ``ANALYSIS_TOP_CUT_SETS`` minimal cut sets with probability and share;
    approximations and truncation; the mission time. Numbers have six
    significant figures. The same document always gives the same text.
    """
    if canonical_mode(mode) == "ETA" or not isinstance(tree, dict) or not tree:
        return ""
    try:
        summary, cut = summary_with_cut_sets(tree, analysis)
    except Exception:  # noqa: BLE001 -- see the docstring
        return ""
    if not isinstance(cut, dict) or not isinstance(summary, dict):
        return ""

    lines = [ANALYSIS_HEADER]
    headline, walk = _six(summary.get("headline")), _six(summary.get("treeWalk"))
    if summary.get("headlineMethod") == "mcub":
        lines.append("Top event probability (headline): %s by MCUB (min-cut upper bound "
                     "over the minimal cut sets)." % headline)
        lines.append("The headline already counts each repeated event once, so the double "
                     "counting in the tree-walk value is corrected in it.")
        lines.append("Tree walk: %s (every branch taken as independent; the 'Top-level "
                     "Probability' and every 'Calculated Probability' above are tree-walk "
                     "values)." % walk)
    else:
        lines.append("Top event probability (headline): %s by tree walk (no event is "
                     "repeated, so no branch is counted twice)." % headline)
        lines.append("MCUB (min-cut upper bound) for comparison: %s." % _six(summary.get("mcub")))
    lines.append("Rare-event approximation (sum of the cut sets): %s."
                 % _six(summary.get("rareEvent")))

    repeated = [e for e in summary.get("repeatedEvents") or [] if isinstance(e, dict)]
    if repeated:
        shown = "; ".join(_named(e.get("id"), e.get("name"))
                          for e in repeated[:ANALYSIS_MAX_REPEATED])
        more = len(repeated) - ANALYSIS_MAX_REPEATED
        lines.append("Repeated events (%d), each reached by more than one branch: %s%s."
                     % (len(repeated), shown, "; and %d more" % more if more > 0 else ""))
    else:
        lines.append("Repeated events: none.")

    cut_sets = [c for c in cut.get("cutSets") or [] if isinstance(c, dict)]
    total = cut.get("total", len(cut_sets))
    top = cut_sets[:ANALYSIS_TOP_CUT_SETS]
    if top:
        lines.append("Minimal cut sets: %s; the top %d by probability, as probability "
                     "(share of the rare-event sum): events" % (total, len(top)))
        for position, cut_set in enumerate(top, start=1):
            events = " AND ".join(_named(e.get("id"), e.get("name"))
                                  for e in cut_set.get("events") or [] if isinstance(e, dict))
            lines.append("%d. %s (%s%%): %s" % (
                position, _six(cut_set.get("probability")),
                "%.3g" % (100.0 * float(cut_set.get("share") or 0.0)), events))
    else:
        lines.append("Minimal cut sets: none.")

    notes = []
    for item in summary.get("approximations") or []:
        if not isinstance(item, dict):
            continue
        text = _APPROXIMATION_TEXT.get(str(item.get("code")))
        notes.append(text % item.get("nodeId") if text
                     else "%s at %s" % (item.get("code"), item.get("nodeId")))
    if summary.get("nonCoherent"):
        notes.append("the tree has XOR gates and is non-coherent (the cut sets treat XOR as OR)")
    lines.append("Approximations: %s." % ("; ".join(notes) if notes else "none"))

    truncated_by = [str(b) for b in summary.get("truncatedBy") or []]
    if summary.get("truncated"):
        lines.append("Cut sets truncated by the document's limits (%s): the MCUB is from "
                     "the sets kept." % (", ".join(truncated_by) or "limit"))
    if summary.get("capped"):
        lines.append("The headline is computed from the first %s cut sets only (the "
                     "headline's own cap); the Cut Sets tab may list more." % total)

    settings = analysis if isinstance(analysis, dict) else {}
    lines.append("Mission time: %s h (shown to the user in %s)."
                 % (_six(settings.get("missionTime")), settings.get("timeUnit") or "h"))
    lines.append(ANALYSIS_FOOTER)
    return "\n".join(lines)


def with_analysis(handler: AIAgentHandler, section: str, func: Callable[..., Any]
                  ) -> Callable[..., Any]:
    """``func`` for :func:`run_ai_call`, with ``section`` appended to the
    context the handler builds during it (:class:`WebAgentHandler`).

    Set on the worker, inside the call slot, and cleared when the handler
    returns: calls are serialised, so one call's section can never be read
    by another -- also not by a call that timed out and is still running.
    """

    def call(*args: Any, **kwargs: Any) -> Any:
        handler.analysis_section = section or ""
        try:
            return func(*args, **kwargs)
        finally:
            handler.analysis_section = ""

    return call


# ---- which document a proposal was made for -----------------------------
#
# A proposal names node ids of the tree the model was shown. New, Open and
# Import replace ``state.core`` with a fresh object, and in the new document
# the same ids can name unrelated nodes ("root_0" is the first child of every
# tree), so a proposal is only ever applied to the document it was made for.
# Held weakly on both sides: a pending list that outlives its document must
# not keep the old tree in memory.

_proposal_documents: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()

#: The ``rejected`` message for a proposal whose document is gone.
OTHER_DOCUMENT_MESSAGE = (
    "Not applied: this suggestion was made for a different analysis, which "
    "New or Open has replaced since, and its node ids may name unrelated "
    "nodes here."
)


def proposing(handler: AIAgentHandler, document: Any, func: Callable[..., Any]) -> Callable[..., Any]:
    """``func`` (a handler call that may propose changes) for
    :func:`run_ai_call`, recording what it proposes as made for ``document``.

    The recording runs on the worker, inside the call slot, as soon as the
    handler returns: calls are serialised, so the not-yet-recorded pending
    changes are exactly this call's -- also for a call that timed out and
    finishes after its request has gone.
    """

    def call(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        finally:
            ref = weakref.ref(document)
            for change in handler.pending_changes:
                if change not in _proposal_documents:
                    _proposal_documents[change] = ref

    return call


def made_for(change: AIProposedChange, document: Any) -> bool:
    """False when ``change`` was proposed for a document other than ``document``."""
    ref = _proposal_documents.get(change)
    return ref is None or ref() is document


# ---- what the model may write -------------------------------------------
#
# The vendored validators accept what float() accepts and range-check it, but
# every comparison with NaN is False, so NaN -- JSON ``NaN`` or the string
# "nan" -- passes both the proposal parser and verify_updated_fta_json. One
# NaN leaf makes every gate above it NaN, the top event included (null in the
# browser, an MCUB of 0.0). ``notes`` is stored whatever its type, and the XML
# export cannot serialise a list. The tree API refuses both from a person;
# these refuse them from the model.


def _is_probability(value: Any) -> bool:
    """Whether what the handler stores, ``float(value)``, is in [0, 1]."""
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return False
    return 0.0 <= number <= 1.0


#: The node types a suggestion may give (``_parse_proposed_changes``).
_NODE_TYPES = ("Event", "Gate", "Intermediate")


def change_problem(change: AIProposedChange, document: Any = None) -> Optional[str]:
    """Why a proposed add/edit must not be applied to ``document``, or None."""
    if change.change_type not in ("add", "edit"):
        return None
    data = change.data if isinstance(change.data, dict) else {}
    if "probability" in data and not _is_probability(data["probability"]):
        return (
            "Not applied: the suggested probability %r is not a number between "
            "0 and 1." % (data["probability"],)
        )
    # The parser drops a suggestion with either of these; the handler's edit
    # would skip the field and report the rest as updated.
    if "type" in data and data["type"] not in _NODE_TYPES:
        return ("Not applied: the suggested type %r is not Event, Gate or Intermediate."
                % (data["type"],))
    if data.get("logicGate") not in (None, "", "AND", "OR"):
        return "Not applied: the suggested gate %r is not AND or OR." % (data["logicGate"],)
    notes = data.get("notes")
    if notes is not None and not isinstance(notes, str):
        return "Not applied: the suggested notes are not text."
    unsavable = _unsavable_text(data, _PLAIN_TEXT_KEYS)
    if unsavable:
        return "Not applied: the suggested %s contains text that cannot be saved." % unsavable[0]
    if change.change_type == "edit" and "probability" in data and document is not None:
        return derived_probability_reason(document.find_node_by_id(change.target_id), document)
    return None


# ---- links in a suggestion ----------------------------------------------
#
# ``links`` in a suggestion's DATA is the node's complete new list, as the
# schema the model is given describes a node: it replaces the links the node
# has, ``[]`` removes them all, and leaving the key out keeps them. The
# vendored add/edit ignore the key, so it is validated and written here.

#: What the vendored handler answers to an edit none of whose fields it
#: writes -- which is what an edit of the links alone looks like to it.
NO_FIELDS_MESSAGE = "No valid fields to update"

#: Keys of an add/edit DATA that are applied: the handler's own, and links.
_APPLIED_KEYS = frozenset(("id", "name", "type", "probability", "logicGate", "notes", "links"))


def _link_owner(change: AIProposedChange) -> Optional[str]:
    """The id of the node whose links an add/edit sets."""
    data = change.data if isinstance(change.data, dict) else {}
    owner = data.get("id") if change.change_type == "add" else change.target_id
    return None if owner is None else str(owner)


def _suggested_links(change: AIProposedChange) -> Any:
    """The raw ``links`` an add/edit carries, or None when it sets none
    (the key is absent or null: the node's links stay as they are)."""
    if change.change_type not in ("add", "edit"):
        return None
    data = change.data if isinstance(change.data, dict) else {}
    return data.get("links")


def _link_problem(raw: Any, owner: Optional[str], known_ids: Any
                  ) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
    """``(links, None)`` -- normalised as ``PATCH /api/nodes`` stores them --
    or ``(None, why they cannot be applied)``.

    ``node_schema.validate_links`` (a list of ``{target_id, relation}``,
    relation AND or OR, no link twice), and then what a person's edit is not
    held to but a model's is: every target exists and none is the node
    itself. A dangling link is legal in a file; one the model invented is a
    mistake, and it would silently change nothing in the numbers.
    """
    try:
        links = validate_links(raw)
    except ApiError as exc:
        return None, "Not applied: the suggested links are not valid. %s" % exc.message
    for link in links:
        target = link["target_id"]
        if owner is not None and target == owner:
            return None, ("Not applied: the suggested link points from '%s' to itself."
                          % owner)
        if target not in known_ids:
            return None, ("Not applied: the suggested link target '%s' does not exist "
                          "in this analysis." % target)
    return links, None


def proposed_links(change: AIProposedChange, core: Any
                   ) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
    """``(links to store, None)``, ``(None, None)`` when the change sets no
    links, or ``(None, reason)`` when its links must not be applied to the
    document in ``core``. Caller holds the lock."""
    raw = _suggested_links(change)
    if raw is None:
        return None, None
    return _link_problem(raw, _link_owner(change), all_ids(core))


def _link_key(link: Any) -> Optional[Tuple[str, str]]:
    """``(target id, effective relation)`` of a stored link, as the engine
    reads it ("AND" in any case is AND, anything else OR), or None."""
    target = link.get("target_id") if isinstance(link, dict) else None
    if target in (None, ""):
        return None
    relation = "AND" if str(link.get("relation") or "OR").strip().upper() == "AND" else "OR"
    return str(target), relation


def link_changes(change: AIProposedChange, tree: Any, pending: Any = ()
                 ) -> Optional[Dict[str, Any]]:
    """What a suggestion would do to its node's links, for the chat card:
    ``{"added": [...], "removed": [...], "problem": str | None}``, or None
    when it sets no links. Each entry is ``{targetId, targetName, relation}``.

    Compared with ``tree``, the document the model was shown. A target that
    an earlier ``add`` of ``pending`` creates counts as known -- suggestions
    are applied in order -- so only a target nobody creates is a ``problem``
    here; the same check runs again, against the live tree, on apply.
    """
    raw = _suggested_links(change)
    if raw is None:
        return None
    nodes = _nodes_by_id(tree)
    names = {node_id: node.get("name") for node_id, node in nodes.items()}
    for other in pending or ():
        data = other.data if isinstance(getattr(other, "data", None), dict) else {}
        if getattr(other, "change_type", None) == "add" and data.get("id") is not None:
            names.setdefault(str(data["id"]), data.get("name"))
    owner = _link_owner(change)
    wanted, problem = _link_problem(raw, owner, names)
    if wanted is None:
        try:  # still show what was asked for, beside why it will be refused
            wanted = validate_links(raw)
        except ApiError:
            wanted = []
    current: List[Tuple[str, str]] = []
    if change.change_type == "edit" and owner in nodes:
        for link in nodes[owner].get("links") or []:
            key = _link_key(link)
            if key is not None and key not in current:
                current.append(key)
    asked = [(link["target_id"], link["relation"]) for link in wanted]

    def entry(key: Tuple[str, str]) -> Dict[str, Any]:
        return {"targetId": key[0], "targetName": names.get(key[0]), "relation": key[1]}

    return {
        "added": [entry(key) for key in asked if key not in current],
        "removed": [entry(key) for key in current if key not in asked],
        "problem": problem,
    }


def ignored_fields(change: AIProposedChange) -> List[str]:
    """Keys of an add/edit's DATA that applying it does not use, sorted.

    ``children`` (non-empty: each child is its own suggestion), the 1.7 keys
    and anything else the model made up. Not reported: an empty ``children``
    and ``calculatedProbability``, which the schema the model is shown lists
    on every node and which say nothing.
    """
    if change.change_type not in ("add", "edit"):
        return []
    data = change.data if isinstance(change.data, dict) else {}
    ignored = []
    for key, value in data.items():
        if key in _APPLIED_KEYS or key == "calculatedProbability":
            continue
        if key == "children" and not value:
            continue
        ignored.append(str(key))
    return sorted(ignored)


def apply_change(handler: AIAgentHandler, core: Any, change: AIProposedChange
                 ) -> Tuple[bool, str, List[str]]:
    """Apply one proposed change to ``core``: ``(ok, message, ignored)``.

    The vendored ``apply_change_to_fta`` does the work, as in the desktop
    editor; this adds the suggestion's ``links``, which it ignores. They are
    checked first (:func:`proposed_links`), so a suggestion with a bad link
    is refused before anything of it is written -- see the module docstring
    for the all-or-nothing rule. ``ignored`` is :func:`ignored_fields` for a
    change that was applied. Caller holds the lock and recalculates.
    """
    links, problem = proposed_links(change, core)
    if problem:
        return False, problem, []
    ok, message = handler.apply_change_to_fta(core, change)
    if links is not None:
        node = core.find_node_by_id(_link_owner(change))
        links_only = (not ok and change.change_type == "edit" and node is not None
                      and message == NO_FIELDS_MESSAGE)
        if links_only:  # the links are the whole edit
            ok, message = True, "✓ Updated '%s': links" % node.get("name")
        elif ok and change.change_type == "edit":
            message = "%s, links" % message
        elif ok:
            message = "%s, with %d link%s" % (message, len(links), "" if len(links) == 1 else "s")
        if ok and node is not None:
            node["links"] = links
    if not ok:
        return False, message, []
    ignored = ignored_fields(change)
    if ignored:
        message = "%s. Not changed by a suggestion: %s" % (message, ", ".join(ignored))
    return True, message, ignored


def derived_probability_reason(node: Any, document: Any) -> Optional[str]:
    """Why ``node``'s probability cannot be set directly, or None.

    The engine rewrites it on every recalculation for a transfer gate (the
    target's value), a house event (1 or 0) and an event whose quantification
    model can be evaluated -- so an AI edit of it was reported as applied and
    silently overruled. Asks :func:`engine.derive_quant` itself, so an
    incomplete model (no λ) is "not derived", exactly as the engine treats it.
    """
    if not isinstance(node, dict):
        return None
    name = node.get("name") or node.get("id")
    if str(node.get("gateType") or "").strip().upper() == "TRANSFER":
        return (
            "Not applied: '%s' is a transfer gate, so its probability is that of "
            "the node it transfers to (%s). Edit that node instead."
            % (name, node.get("transferTo") or "none set")
        )
    if not (node.get("children") or []) and str(node.get("eventKind") or "").strip().lower() == "house":
        return (
            "Not applied: '%s' is a house event, so its probability is 1 or 0 "
            "from its state. Change the house state instead." % name
        )
    if isinstance(node.get("quant"), dict):
        derived = derive_quant(node, getattr(document, "analysis", None))
        if derived["model"] != "fixed" and derived["q"] is not None:
            return (
                "Not applied: the probability of '%s' is computed from its %s model "
                "(%s), so an edited value would be overwritten. Change the model's "
                "parameters in the Quantification tab instead."
                % (name, derived["model"], derived["formula"])
            )
    return None


def update_problem(tree: Any) -> Optional[str]:
    """The first thing in an AI-written tree that ``verify_updated_fta_json``
    lets through and the tree API would refuse, or None.

    Run after that validator, so every node is a dict with a valid id. Worded
    like it ("... for node <id> ..."), so :func:`locate_offending_node` finds
    the node for the diagnostics. The 1.7 keys go through the validators
    ``PATCH /api/nodes`` uses: the model is never shown them, so any it writes
    are invented, and ``houseState: "yes"`` would silently count as false.
    """
    stack = [(tree, 0)] if isinstance(tree, dict) else []
    while stack:
        node, depth = stack.pop()
        node_id = node.get("id")
        if depth > config.MAX_TREE_DEPTH:
            return ("Tree too deep at node %s: it is more than %d levels below the top "
                    "event, the most the editor supports" % (node_id, config.MAX_TREE_DEPTH))
        if not _is_probability(node.get("probability")):
            return "Invalid probability for node %s: %r" % (node_id, node.get("probability"))
        notes = node.get("notes")
        if notes is not None and not isinstance(notes, str):
            return "Invalid notes for node %s: notes must be text" % node_id
        unsavable = _unsavable_text(node, _PLAIN_TEXT_KEYS)
        if unsavable:
            return "Invalid %s for node %s: %s" % (unsavable[0], node_id, unsavable[1])
        links = node.get("links")
        if isinstance(links, list):
            for link in links:
                unsavable = _unsavable_text(link, _LINK_TEXT_KEYS) if isinstance(link, dict) else None
                if unsavable:
                    return "Invalid link for node %s: %s" % (node_id, unsavable[1])
            if drop_duplicate_links({"links": copy.deepcopy(links)}):
                return ("Invalid links for node %s: the same link appears more than once, "
                        "so it would be counted twice" % node_id)
        for key in NODE_KEYS:
            if node.get(key) is None:
                continue
            try:
                VALIDATORS[key](node[key])
            except ApiError as exc:
                return "Invalid %s for node %s: %s" % (key, node_id, exc.message)
        stack.extend(reversed([(c, depth + 1) for c in node.get("children") or []
                               if isinstance(c, dict)]))
    return None


#: The text a node carries outside the 1.7 keys (``VALIDATORS`` check those),
#: and a link's.
_PLAIN_TEXT_KEYS = ("id", "name", "type", "notes", "logicGate")
_LINK_TEXT_KEYS = ("target_id", "relation")


def _unsavable_text(values: Dict[str, Any], keys: Tuple[str, ...]) -> Optional[Tuple[str, str]]:
    """``(key, message)`` for the first text in ``values`` that could never be
    saved (an unpaired surrogate: ``node_schema.refuse_unsavable_text``), or
    None. The model writes these straight into the tree, past the validators
    ``PATCH /api/nodes`` and the loader apply."""
    for key in keys:
        value = values.get(key)
        if isinstance(value, str):
            try:
                refuse_unsavable_text(value, key)
            except ApiError as exc:
                return key, exc.message
    return None


# ---- what a full-JSON update did ----------------------------------------


def _nodes_by_id(tree: Any) -> Dict[str, Dict[str, Any]]:
    """id -> node in pre-order (the first node of a repeated id)."""
    nodes: Dict[str, Dict[str, Any]] = {}
    stack = [tree] if isinstance(tree, dict) else []
    while stack:
        node = stack.pop()
        nodes.setdefault(str(node.get("id")), node)
        stack.extend(reversed([c for c in node.get("children") or [] if isinstance(c, dict)]))
    return nodes


def _as_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def update_summary(before: Any, after: Any) -> Dict[str, List[Dict[str, Any]]]:
    """What a full-tree AI update did to the document, by node id.

    ``added`` and ``removed`` are ``{id, name}``; ``changed`` lists the nodes
    present in both whose ``name``, ``probability`` (of a leaf -- a gate's own
    value is ignored by the engine), ``gate`` (``gateType`` or ``logicGate`` of a
    node with children) or ``quant`` differ, with those ``fields``. Compare
    recalculated trees: a probability the engine derives (a rate model the
    update kept) is then not reported as changed, because it is not.
    """
    old, new = _nodes_by_id(before), _nodes_by_id(after)

    def gate(node: Dict[str, Any]) -> str:
        return str(node.get("gateType") or node.get("logicGate") or "OR").strip().upper()

    changed: List[Dict[str, Any]] = []
    for node_id, node in new.items():
        was = old.get(node_id)
        if was is None:
            continue
        fields = []
        if was.get("name") != node.get("name"):
            fields.append("name")
        if not (node.get("children") or []) and _as_float(was.get("probability")) != _as_float(node.get("probability")):
            fields.append("probability")
        if (node.get("children") or was.get("children")) and gate(was) != gate(node):
            fields.append("gate")
        if was.get("quant") != node.get("quant"):
            fields.append("quant")
        if fields:
            changed.append({"id": node_id, "name": node.get("name"), "fields": fields})
    return {
        "added": [{"id": i, "name": n.get("name")} for i, n in new.items() if i not in old],
        "removed": [{"id": i, "name": n.get("name")} for i, n in old.items() if i not in new],
        "changed": changed,
    }


# ---- full-JSON update diagnostics ---------------------------------------
#
# The desktop editor's Update FTA flow (desktop/src/FTA_Editor_UI.py:855-895) does not
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
