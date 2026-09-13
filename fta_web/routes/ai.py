"""
AI assistant endpoints -- the ``/api/ai`` blueprint.

============================================  ==============================
``GET    /api/ai/providers``                  provider names and defaults
``GET    /api/ai/models``                     model list for one provider
``GET    /api/ai/credentials``                masked credential status
``POST   /api/ai/credentials``                test a key, save it if it works
``DELETE /api/ai/credentials``                forget the saved key
``POST   /api/ai/chat``                       one turn of conversation
``POST   /api/ai/analyze``                    one-shot analysis, read-only
``POST   /api/ai/update``                     full-JSON rewrite of the tree
``POST   /api/ai/changes/apply``              apply selected proposals
``DELETE /api/ai/conversation``               forget the chat history
============================================  ==============================

This module is HTTP and nothing else. The AI logic is the vendored
``AI_agent_handler``'s, and ``fta_web/ai_bridge.py`` is the seam -- read its
docstring first: it owns the worker-thread/timeout model, the redaction rules
and the update diagnostics that the routes below merely shape into envelopes.

Decisions a reviewer should know about
--------------------------------------
**The API key is never in a response, and this is enforced twice.** No payload
built here has a place to put it -- ``ai_bridge.credentials_status()`` is the
only credential view and it returns a mask -- and every string that came from a
provider is passed through ``ai_bridge.scrub``/``scrub_deep`` on the way out,
because SDK error messages quote request URLs and Gemini puts the key in one.
``keyPreview`` (``sk-...AB12``) exists so the settings page can show *which*
key is saved without being able to show the key.

**The document lock is never held across a provider call.** Each route reads a
deep copy of the tree under ``state.lock``, releases it, calls the provider on
a worker thread with a deadline, then takes the lock again to apply the result.
A provider that hangs costs one AI request, not the whole editor.

**Everything that mutates goes through the normal mutation contract**
(``routes/tree.py``): ``push_undo()`` first, then mutate, then
``recalculate_probabilities()``, then ``mark_dirty()``, then return the full
post-mutation view. An AI edit is undoable in exactly one Ctrl-Z, like any
other edit -- which is what makes accepting a suggestion a safe thing to try.

**Changes are applied by the vendored handler**, never by re-implementing
add/edit/delete/move here. ``AIAgentHandler.apply_change_to_fta`` is the same
code path the desktop editor uses, including its refusals (root deletion,
duplicate ids, circular moves).

**``/analyze`` cannot write.** It hands the handler a deep copy and never
touches ``state.core``; the tree is byte-identical afterwards, and
``test_api_ai.py`` pins that.

Which endpoints require a key
-----------------------------
``chat``, ``analyze``, ``update``, ``changes/apply`` and ``conversation``
answer 400 ``AI_NOT_CONFIGURED`` when nothing is saved -- they cannot do
anything without a provider. ``providers``, ``models`` and the ``credentials``
endpoints must work *un*configured: they are what the AI settings dialog is
built from, and a first-time user has no key yet by definition. ``models``
degrades to the provider's built-in list with a ``warning`` instead of
failing, for the same reason.

NOT gates are absent from this file on purpose: they are rejected by the
vendored validator and by ``routes/tree.py`` (divergence D5), so an AI answer
containing one is refused with the validator's own message rather than
quietly scored as OR.
"""
from __future__ import annotations

import contextlib
import copy
import logging
from typing import Any, Dict, List, Optional, Tuple

from flask import Blueprint, request

try:  # normal package import: ``import fta_web.routes.ai``
    from .. import ai_bridge
    from ..errors import (
        AI_NOT_CONFIGURED,
        INVALID_FIELD,
        INVALID_JSON,
        ApiError,
        ok_response,
    )
    from ..state import get_state
except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
    import ai_bridge  # type: ignore[no-redef]
    from errors import (  # type: ignore[no-redef]
        AI_NOT_CONFIGURED,
        INVALID_FIELD,
        INVALID_JSON,
        ApiError,
        ok_response,
    )
    from state import get_state  # type: ignore[no-redef]

log = logging.getLogger(__name__)

ai_bp = Blueprint("ai", __name__, url_prefix="/api/ai")

# ---------------------------------------------------------------------------
# Error codes owned by this blueprint.
#
# errors.py holds the shared vocabulary and already owns AI_NOT_CONFIGURED,
# which the frontend branches on. These are local for the same reason
# routes/files.py keeps EXPORT_UNAVAILABLE local -- promote any of them into
# errors.py the day something else needs to raise it.
# ---------------------------------------------------------------------------
AI_BUSY = "AI_BUSY"
AI_TIMEOUT = "AI_TIMEOUT"
AI_CALL_FAILED = "AI_CALL_FAILED"
AI_CONNECTION_FAILED = "AI_CONNECTION_FAILED"
AI_INVALID_JSON = "AI_INVALID_JSON"
AI_UPDATE_REJECTED = "AI_UPDATE_REJECTED"
AI_CHANGE_REJECTED = "AI_CHANGE_REJECTED"

#: Says where to go, not just what is wrong. This is the one error a new user
#: is guaranteed to hit, so it is the one that has to teach.
NOT_CONFIGURED_MESSAGE = (
    "The AI assistant is not configured. Open AI settings, choose a provider "
    "and paste its API key -- the key is tested before it is saved and is "
    "stored only on this machine, in ~/.fta_editor/ai_credentials.json."
)


@ai_bp.errorhandler(ApiError)
def _handle_api_error(exc: ApiError):
    # Registered on the blueprint as well as the app (see routes/tree.py) so
    # the blueprint returns the documented envelope wherever it is mounted.
    return exc.to_payload(), exc.status


# ---- request helpers -----------------------------------------------------


def _body() -> Dict[str, Any]:
    """The request's JSON object. An absent body is an empty object."""
    data = request.get_json(silent=True)
    if data is None:
        if not request.get_data():
            return {}
        raise ApiError(INVALID_JSON, "Request body must be a JSON object.", 400)
    if not isinstance(data, dict):
        raise ApiError(INVALID_JSON, "Request body must be a JSON object.", 400)
    return data


def _require_configured() -> None:
    """400 ``AI_NOT_CONFIGURED`` unless a key is saved."""
    if not ai_bridge.is_configured():
        raise ApiError(AI_NOT_CONFIGURED, NOT_CONFIGURED_MESSAGE, 400)


def _required_text(payload: Dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ApiError(
            INVALID_FIELD,
            "'%s' is required and must be a non-empty string." % field,
            400,
            {"field": field},
        )
    return value


@contextlib.contextmanager
def _ai_failures(secret: Optional[str] = None):
    """Translate ``ai_bridge`` failures into the error envelope.

    ``secret`` is the key currently in hand -- the one being tested, which is
    not on disk yet -- so a provider error quoting it is scrubbed here too.

    A timeout is 504 and a provider exception is 502: both say "the request was
    fine, the upstream was not", which is the distinction that tells a user to
    retry rather than to change what they typed.
    """
    try:
        yield
    except ai_bridge.AiBusy as exc:
        raise ApiError(AI_BUSY, str(exc), 409)
    except ai_bridge.AiTimeout as exc:
        raise ApiError(
            AI_TIMEOUT,
            str(exc),
            504,
            {"timeoutSeconds": ai_bridge.config.AI_TIMEOUT_SECONDS},
        )
    except ai_bridge.UnknownProvider as exc:
        raise ApiError(
            INVALID_FIELD,
            str(exc),
            400,
            {"field": "provider", "supported": ai_bridge.provider_names()},
        )
    except ai_bridge.AiCallFailed as exc:
        # The provider layer normally reports failure by return value; reaching
        # here means it raised, which is a bug or an SDK surprise. The detail
        # goes to the log, the scrubbed summary to the client.
        log.warning("AI provider call raised: %s", ai_bridge.scrub(str(exc), secret))
        raise ApiError(AI_CALL_FAILED, ai_bridge.scrub(str(exc), secret), 502)


# ---- state helpers -------------------------------------------------------


def _document_snapshot() -> Tuple[Dict[str, Any], str, str]:
    """``(tree, mode, title)``, deep-copied under the lock.

    A copy, not the live tree: it is about to be walked and formatted on a
    worker thread that will outlive this request if the provider hangs, and
    that walk must not be able to see a half-applied edit -- or to be handed a
    structure another request is mutating.
    """
    state = get_state()
    with state.lock:
        return (
            copy.deepcopy(state.core.get_data()),
            state.core.mode,
            state.core.title,
        )


def _mutation_payload(state) -> Dict[str, Any]:
    """The post-mutation view every mutating endpoint returns.

    Mirrors ``routes/tree.py``'s payload of the same name -- deliberately
    duplicated rather than imported across blueprints, for the same reason each
    blueprint registers its own ``ApiError`` handler: neither has to be mounted
    for the other to answer correctly.
    """
    core = state.core
    return {
        "tree": copy.deepcopy(core.get_data()),
        "zeroNodes": core.get_zero_probability_nodes(),
        "dirty": state.dirty,
        "canUndo": state.can_undo,
        "canRedo": state.can_redo,
    }


# ---- providers and models ------------------------------------------------


@ai_bp.get("/providers")
def get_providers():
    """The providers this build supports, with their defaults.

    Works without a key: this is what the settings dialog is populated from.
    ``defaultModels`` is a fallback list, not a promise -- prefer
    ``GET /api/ai/models``, and let the user type a name that is on neither
    list, since a model released after this build shipped is still valid.
    """
    return ok_response(providers=ai_bridge.provider_catalog())


@ai_bp.get("/models")
def get_models():
    """Model names for one provider, live where a saved key allows it.

    Query: ``?provider=<name>&endpoint=<url>``. ``endpoint`` is optional and
    defaults to the provider's own. Never fails for a known provider: a fetch
    that cannot happen comes back as the built-in list with ``source:
    "fallback"`` and a ``warning`` saying why, because a settings dialog with
    an empty model list is one the user cannot finish.
    """
    provider = request.args.get("provider")
    if not provider or not provider.strip():
        # Fall back to whatever is configured, so a page that just wants "the
        # models for my current setup" does not have to ask twice.
        provider = (ai_bridge.credentials_status() or {}).get("provider")
    if not provider:
        raise ApiError(
            INVALID_FIELD,
            "'provider' is required when no AI credentials are saved.",
            400,
            {"field": "provider", "supported": ai_bridge.provider_names()},
        )

    with _ai_failures():
        result = ai_bridge.list_models(provider, request.args.get("endpoint"))
    return ok_response(**result)


# ---- credentials ---------------------------------------------------------


@ai_bp.get("/credentials")
def get_credentials():
    """Whether a key is saved, and which -- masked.

    ``keyPreview`` is ``sk-...AB12``: enough to recognise which key is in
    place, never enough to use it. There is no endpoint, parameter or debug
    flag anywhere in this app that returns the key itself.
    """
    status = ai_bridge.credentials_status()
    return ok_response(aiConfigured=status["configured"], **status)


@ai_bp.post("/credentials")
def post_credentials():
    """Test a key against its provider, and save it only if the test passes.

    Body: ``{provider, apiKey, endpoint?, model?}``. ``endpoint`` and ``model``
    default to the provider's own.

    The test is not a formality. Saving first and discovering later would
    replace a working configuration with a broken one because of a typo, and
    the failure would surface at the next chat message instead of here, where
    the user is looking at the field they got wrong. On failure the provider's
    own message is returned -- scrubbed -- because "401 Incorrect API key"
    is actionable and "could not connect" is not.

    Written to ``~/.fta_editor/ai_credentials.json``: the same file the desktop
    editor reads, so a key configured in either tool works in both.
    """
    payload = _body()
    api_key = _required_text(payload, "apiKey")
    provider = payload.get("provider")
    if not isinstance(provider, str) or not provider.strip():
        raise ApiError(
            INVALID_FIELD,
            "'provider' is required.",
            400,
            {"field": "provider", "supported": ai_bridge.provider_names()},
        )

    with _ai_failures(secret=api_key):
        saved, message, resolved = ai_bridge.test_and_save_credentials(
            provider, api_key, payload.get("endpoint"), payload.get("model")
        )

    if not saved:
        # Unsaved: whatever was configured before is still configured.
        raise ApiError(
            AI_CONNECTION_FAILED,
            message,
            400,
            {
                "provider": resolved["provider"],
                "endpoint": resolved["endpoint"],
                "model": resolved["model"],
                "saved": False,
            },
        )

    status = ai_bridge.credentials_status()
    return ok_response(
        aiConfigured=status["configured"], message=message, **status
    )


@ai_bp.delete("/credentials")
def delete_credentials():
    """Forget the saved key. Succeeds when there was nothing to forget."""
    ok, error = ai_bridge.delete_credentials()
    if not ok:
        raise ApiError(
            AI_CALL_FAILED, ai_bridge.scrub(str(error or "Could not delete credentials.")), 500
        )
    status = ai_bridge.credentials_status()
    return ok_response(aiConfigured=status["configured"], **status)


# ---- conversation --------------------------------------------------------


@ai_bp.post("/chat")
def post_chat():
    """One turn of conversation. Body: ``{message}``.

    Returns ``{reply, changes}``. ``changes`` are the proposals parsed out of
    this reply, each carrying its ``index`` into the pending list --
    ``POST /api/ai/changes/apply`` takes those indices. Nothing is applied
    here; a chat message can never move the tree on its own.

    A provider failure arrives as a normal reply beginning "AI Error:":
    ``AIAgentHandler.send_message`` catches everything and reports in-band
    (AI_agent_handler.py:483). That is what the desktop chat shows too, so it
    is passed through rather than re-raised -- the alternative is sniffing the
    handler's error strings, which would break the first time the wording
    changed.
    """
    _require_configured()
    payload = _body()
    message = _required_text(payload, "message")

    handler = ai_bridge.get_handler()
    tree, mode, title = _document_snapshot()

    with _ai_failures():
        # set_fta_context is pure formatting, but it writes to the handler, so
        # it runs inside the same single-call slot as send_message -- see
        # ai_bridge.run_ai_call.
        def _send():
            handler.set_fta_context(tree, mode, title)
            return handler.send_message(message, include_fta_context=True)

        reply, changes = ai_bridge.run_ai_call("chat", _send)

    return ok_response(
        reply=ai_bridge.scrub(reply),
        changes=ai_bridge.scrub_deep(ai_bridge.changes_view(handler, changes)),
    )


@ai_bp.post("/analyze")
def post_analyze():
    """A one-shot review of the current tree. Read-only, always.

    The handler is given a deep copy and ``state.core`` is never touched, so
    the document is byte-identical when this returns -- including its undo
    stack and dirty flag. Suggestions come back as ``changes`` for the user to
    apply deliberately through ``POST /api/ai/changes/apply``; the point of a
    separate analyze endpoint is that asking the AI what it thinks is not the
    same as letting it edit.
    """
    _require_configured()

    handler = ai_bridge.get_handler()
    tree, mode, title = _document_snapshot()

    with _ai_failures():
        reply, changes = ai_bridge.run_ai_call(
            "analyze", handler.get_quick_analysis, tree, mode, title
        )

    return ok_response(
        reply=ai_bridge.scrub(reply),
        changes=ai_bridge.scrub_deep(ai_bridge.changes_view(handler, changes)),
    )


@ai_bp.delete("/conversation")
def delete_conversation():
    """Forget the chat history and every pending proposal.

    Both, because they are one thing: the indices in ``changes`` only mean
    anything against the pending list they were issued from, and keeping stale
    proposals alive after their conversation was dropped would let a client
    apply a change whose reasoning no longer exists anywhere.
    """
    _require_configured()
    ai_bridge.get_handler().clear_conversation()
    return ok_response(cleared=True, changes=[])


# ---- applying proposals --------------------------------------------------


@ai_bp.post("/changes/apply")
def post_apply_changes():
    """Apply selected proposals. Body: ``{indices: [0, 2, ...]}``.

    Indices address the handler's pending list, which accumulates across the
    conversation -- so a proposal from three messages ago is still applicable,
    and the ``index`` returned with every change is stable until the
    conversation is cleared.

    They are applied **in the order given**, not sorted: the system prompt
    tells the model to sequence a parent before its children
    (AI_agent_handler.py:297), and re-ordering them here would break exactly
    the nested additions that instruction exists to make work.

    Partial success is reported, not hidden: each index lands in ``applied`` or
    in ``rejected`` with the handler's own message. If every one is rejected
    the tree is untouched and the whole request is a 400.
    """
    _require_configured()
    payload = _body()
    handler = ai_bridge.get_handler()
    pending = handler.pending_changes

    raw = payload.get("indices")
    if not isinstance(raw, list) or not raw:
        raise ApiError(
            INVALID_FIELD,
            "'indices' must be a non-empty list of pending-change indices.",
            400,
            {"field": "indices", "pendingCount": len(pending)},
        )

    indices: List[int] = []
    for position, value in enumerate(raw):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ApiError(
                INVALID_FIELD,
                "Each entry of 'indices' must be an integer.",
                400,
                {"field": "indices", "position": position, "value": value},
            )
        if not 0 <= value < len(pending):
            raise ApiError(
                INVALID_FIELD,
                "No pending change at index %d; there %s %d."
                % (value, "is" if len(pending) == 1 else "are", len(pending)),
                400,
                {"field": "indices", "index": value, "pendingCount": len(pending)},
            )
        if value in indices:
            # Applying the same proposal twice is never what was meant, and
            # the second attempt would fail confusingly ("id already exists").
            raise ApiError(
                INVALID_FIELD,
                "Index %d is listed more than once." % value,
                400,
                {"field": "indices", "index": value},
            )
        indices.append(value)

    state = get_state()
    applied: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []

    with state.lock:
        # Pushed before the first attempt so one Ctrl-Z reverses the whole
        # batch. If every change is rejected below the tree is untouched and
        # this entry is a harmless no-op on the stack -- the same trade
        # routes/tree.py's move endpoint makes.
        state.push_undo()

        for index in indices:
            change = pending[index]
            ok, message = handler.apply_change_to_fta(state.core, change)
            record = ai_bridge.change_view(change, index)
            record["message"] = ai_bridge.scrub(message)
            (applied if ok else rejected).append(record)

        if not applied:
            raise ApiError(
                AI_CHANGE_REJECTED,
                "None of the selected changes could be applied; the analysis "
                "is unchanged.",
                400,
                {"rejected": ai_bridge.scrub_deep(rejected)},
            )

        state.core.recalculate_probabilities()
        state.mark_dirty()

        return ok_response(
            applied=ai_bridge.scrub_deep(applied),
            rejected=ai_bridge.scrub_deep(rejected),
            **_mutation_payload(state),
        )


# ---- full-JSON update ----------------------------------------------------


@ai_bp.post("/update")
def post_update():
    """Ask the AI to rewrite the whole tree, then verify it and install it.

    Three outcomes, and the two failures are where the value is:

    * **Unparseable.** 400 ``AI_INVALID_JSON`` carrying ``excerpt`` -- the
      first 500 characters of what the model actually said. A model that
      ignored "return only JSON" usually says why in its first sentence
      ("I can't modify the root node, but here's what I'd suggest..."), and
      that sentence is the entire diagnosis. Reducing this to "invalid JSON"
      throws away the only evidence there is.
    * **Structurally invalid.** 400 ``AI_UPDATE_REJECTED`` carrying the
      validator's message *and* the offending node's own JSON, located by the
      node id in that message. "Invalid type for node n_3: Condition" is a
      shrug on its own; with n_3's JSON beside it the fix is obvious.

    Both reproduce the desktop editor's Update FTA diagnostics
    (``src/FTA_Editor_UI.py:855-895``). Nothing is applied in either case.

    On success the tree is replaced wholesale under the lock, with an undo
    entry pushed first -- so a rewrite that turns out to be wrong is one
    Ctrl-Z away, which is what makes it reasonable to try at all.
    """
    _require_configured()

    handler = ai_bridge.get_handler()
    tree, mode, title = _document_snapshot()

    with _ai_failures():
        assistant_text, updated = ai_bridge.run_ai_call(
            "update", handler.generate_full_fta_update, tree, mode, title
        )

    reply = ai_bridge.scrub(assistant_text)

    if updated is None:
        raise ApiError(
            AI_INVALID_JSON,
            "The AI did not return valid JSON, so nothing was changed.",
            400,
            {
                "excerpt": ai_bridge.scrub(ai_bridge.parse_excerpt(assistant_text)),
                "excerptChars": ai_bridge.PARSE_EXCERPT_CHARS,
            },
        )

    valid, validator_message = handler.verify_updated_fta_json(updated)
    if not valid:
        raise ApiError(
            AI_UPDATE_REJECTED,
            "The updated analysis was rejected: %s" % (validator_message or "unknown"),
            400,
            ai_bridge.scrub_deep(
                ai_bridge.validation_diagnostics(updated, validator_message)
            ),
        )

    state = get_state()
    with state.lock:
        state.push_undo()
        # Deep-copied on the way in: set_data stores the reference it is given
        # (FTA_Editor_core.py:53), and the parsed object is also about to be
        # walked for the response payload.
        state.core.set_data(copy.deepcopy(updated))
        state.core.recalculate_probabilities()
        state.mark_dirty()

        return ok_response(reply=reply, **_mutation_payload(state))
