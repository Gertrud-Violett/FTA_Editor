"""
Tests for the Content-Type of the static frontend assets.

These exist because of a shipped bug that made the entire application look
dead. On a Windows machine whose HKEY_CLASSES_ROOT entry for ``.js`` had been
overridden to ``text/plain`` by other software, Flask's static handler --
which asks the stdlib ``mimetypes`` module -- served ``main.js`` as plain
text. Browsers refuse to execute a ``<script type="module">`` that does not
arrive as a JavaScript MIME type, so no frontend code ran and every button in
the UI did nothing. The server was healthy and the logs were clean; it took a
user on a real build to find it, because the development machine was Linux,
where the bug does not exist.

**The obvious test for this is one that passes for the wrong reason.** On
Linux, ``mimetypes`` already answers ``text/javascript`` for ``.js`` all by
itself, so asserting that ``/static/js/main.js`` comes back as JavaScript
passes identically whether or not ``app.register_web_mime_types()`` exists at
all. It would pin nothing and quietly go green forever.

So the regression test below does what the platform did: it poisons
``mimetypes`` to report ``text/plain`` for ``.js`` first, reproducing the
broken host, and only then checks that the app's registration still wins.
That one fails if the fix is removed, on every platform.
"""
import mimetypes
import sys
from pathlib import Path

import pytest

# fta_web/tests/test_static_mime.py -> [0]=tests, [1]=fta_web
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app as app_module  # noqa: E402

#: What a browser will accept for `<script type="module">`. The HTML spec's
#: list of JavaScript MIME types is longer, but these are the two any stdlib or
#: OS is plausibly going to produce, and `text/javascript` is the one the app
#: registers. Asserted as a set rather than a single literal because the
#: contract that matters is "a JavaScript type", not which spelling.
JAVASCRIPT_TYPES = {"text/javascript", "application/javascript"}


@pytest.fixture
def client():
    flask_app = app_module.create_app()
    flask_app.config.update(TESTING=True)
    with flask_app.test_client() as test_client:
        yield test_client


@pytest.fixture
def clean_mimetypes():
    """Restore the process-wide ``mimetypes`` maps after a test mutates them.

    ``mimetypes.add_type`` writes to module-level dicts shared by the whole
    interpreter. A test that poisons ``.js`` and does not put it back would
    leak into every later test in the session -- and, because the poisoning is
    exactly the production bug, it would leak as a *plausible-looking* failure
    somewhere unrelated.

    Restoring ``types_map`` in place is enough, and deliberately does not touch
    the private ``_db``: ``mimetypes.init()`` binds the module-level
    ``types_map`` to the very same dict object as ``_db.types_map[True]``, so
    mutating one is mutating both. (Replacing ``_db`` instead would *discard*
    the poison rather than restore the original -- see the note in the
    regression test.)
    """
    saved_types_map = dict(mimetypes.types_map)
    yield
    mimetypes.types_map.clear()
    mimetypes.types_map.update(saved_types_map)


# --------------------------------------------------------------------------
# the contract
# --------------------------------------------------------------------------


def test_module_javascript_is_served_as_a_javascript_type(client):
    """The frontend entry point must arrive executable.

    This is the user-visible contract. It does not, on its own, prove the fix
    is present -- see the module docstring and the regression test below.
    """
    response = client.get("/static/js/main.js")

    assert response.status_code == 200
    assert response.mimetype in JAVASCRIPT_TYPES, (
        "main.js served as %r; a <script type=\"module\"> that does not arrive "
        "as a JavaScript MIME type is refused by the browser and no frontend "
        "code runs at all." % response.mimetype
    )


def test_stylesheets_are_served_as_css(client):
    response = client.get("/static/css/app.css")

    assert response.status_code == 200
    assert response.mimetype == "text/css"


# --------------------------------------------------------------------------
# the regression test that actually bites
# --------------------------------------------------------------------------


def test_javascript_survives_a_host_that_maps_js_to_text_plain(
    clean_mimetypes, client
):
    """Reproduce the broken Windows host, then assert the app overrides it.

    Removing ``register_web_mime_types()`` from app.py makes this fail on
    Linux too, which is the entire point: the bug was invisible on the
    platform the project is developed on.
    """
    # The broken registry state, as the stdlib would have reported it.
    #
    # Do NOT reset mimetypes._db here to "force a rebuild": add_type writes
    # *into* the live _db, so replacing it throws the poison away and the test
    # silently stops testing anything. The precondition below is what catches
    # that, and it caught exactly that mistake while this test was written.
    mimetypes.add_type("text/plain", ".js")
    assert mimetypes.guess_type("main.js")[0] == "text/plain", (
        "precondition failed: the poison did not take, so this test would "
        "pass without proving anything"
    )

    # What app.py does at import time, re-applied on top of the poison.
    app_module.register_web_mime_types()

    response = client.get("/static/js/main.js")

    assert response.mimetype in JAVASCRIPT_TYPES, (
        "a host that maps .js to text/plain still breaks the app: served %r"
        % response.mimetype
    )


def test_the_registration_is_applied_at_import_not_only_on_demand(
    clean_mimetypes,
):
    """Importing app must be enough; no caller should have to opt in.

    ``create_app`` is not the only way into the static handler, and a fix that
    only ran there would leave the frozen build's entry point exposed.
    """
    mimetypes.add_type("text/plain", ".js")
    assert mimetypes.guess_type("main.js")[0] == "text/plain"

    # Re-importing is what a fresh process does.
    import importlib

    importlib.reload(app_module)

    assert mimetypes.guess_type("main.js")[0] in JAVASCRIPT_TYPES
