"""
DOT generation and native Graphviz rendering for the fta_web editor.

Two renderers, one DOT source
-----------------------------
The editor can draw a diagram in two places, and both consume the *same* text
produced by :func:`build_dot_text`:

* the browser, which runs a WebAssembly build of Graphviz on the DOT it gets
  from ``GET /api/dot`` -- always available, no install required;
* a native ``dot`` binary, used by ``POST /api/render`` to produce a file the
  user can save. Only available when Graphviz is installed.

Reusing the vendored renderer, not re-implementing it
-----------------------------------------------------
``gather_nodes`` and ``build_dot`` are **imported** from the vendored
``json_viewer`` and called in-process. They are never invoked as a subprocess:
shelling out to ``python json_viewer.py`` would mean serializing the tree to a
temp file, paying interpreter startup on every keystroke-driven re-render, and
losing the exception in a parsed stderr string. The functions are pure -- tree
in, text out -- so calling them directly is both faster and more honest.

The title/date header
---------------------
``build_dot()`` does not emit the graph label; ``json_viewer.main()`` does,
by inserting four lines into the finished DOT (json_viewer.py:302-307). A
diagram exported from the web UI must look like one exported from the CLI, so
those inserts are **replicated here**, in the same order and at the same
indices. The vendored file is deliberately not patched: new behaviour belongs
in new modules, and every byte of divergence in ``fta_web/core/`` has to be
justified in ``fta_web/core/DIVERGENCE.md``. This module is new code, so it
costs the fork nothing.

One deliberate difference from ``main()``: the title and date are escaped for
the DOT string literal they land in (see :func:`_escape_label`). ``main()``
interpolates them raw, so a title containing a double quote emits a DOT file
that no Graphviz -- native or wasm -- will parse. Titles reach us from
``sanitize_name`` (which only collapses whitespace) and from whatever an opened
``.json`` file carries, so quotes are reachable input, and a diagram that
silently fails to render is exactly the outcome this phase exists to prevent.
For a title without a quote or a backslash the output is byte-identical to
``main()``'s.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

try:  # normal package import: ``import fta_web.rendering``
    from . import config  # noqa: F401  (imported for its sys.path side effect)
except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
    import config  # type: ignore[no-redef]  # noqa: F401

# Importing config placed fta_web/core on sys.path, so the vendored renderer
# imports under its bare name. See config.py for why that is mandatory.
from json_viewer import build_dot, gather_nodes  # noqa: E402

# ---- knobs ---------------------------------------------------------------

#: Wall-clock cap on one native ``dot`` invocation. A pathological tree can
#: make Graphviz' layout run for minutes; the request thread (and the user)
#: should not wait that long, and an orphaned child process would hold the
#: temp files open. subprocess.run kills the child when this expires.
RENDER_TIMEOUT_SECONDS = 30

#: Temp files carry a recognisable prefix so a leak is attributable, and so
#: the cleanup test can assert the temp directory is empty afterwards.
TEMP_PREFIX = "fta_render_"

#: format -> (MIME type, temp-file suffix). Also the whitelist: anything not
#: listed here never reaches the command line.
FORMATS = {
    "svg": ("image/svg+xml", ".svg"),
    "png": ("image/png", ".png"),
}

#: Copied from json_viewer.render_with_dot's high-quality branch so a
#: high-quality export from the web UI matches the CLI's.
HIGH_QUALITY_FLAGS = ("-Gdpi=300", "-Gfontsize=14", "-Nfontsize=12", "-Efontsize=9")

#: Named in every "native renderer missing" message, so the remedy travels
#: with the error instead of living only in the docs.
GRAPHVIZ_DOWNLOAD_URL = "https://graphviz.org/download/"


# ---- errors --------------------------------------------------------------


class RenderError(RuntimeError):
    """A native render was attempted and did not produce an image.

    ``reason`` is a stable machine-readable discriminator the API surfaces in
    the error detail: the frontend's recovery is the same in every case (fall
    back to the in-browser renderer), but the message it shows should not be.
    """

    reason = "render_failed"

    def __init__(self, message: str, reason: Optional[str] = None, stderr: str = ""):
        super().__init__(message)
        if reason is not None:
            self.reason = reason
        self.stderr = stderr


class RendererUnavailable(RenderError):
    """There is no usable native ``dot`` on this machine."""

    reason = "not_installed"


# ---- DOT -----------------------------------------------------------------


def _escape_label(text: object) -> str:
    """Escape a value for a double-quoted DOT string literal.

    Only backslash and double quote need it. ``\\n`` sequences we build
    ourselves are added *after* this runs, so they survive as Graphviz'
    line break rather than being escaped into a literal backslash-n.
    """
    return str(text).replace("\\", "\\\\").replace('"', '\\"')


def build_dot_text(core, hide_zero: bool = False) -> str:
    """Render the tree held by ``core`` to Graphviz DOT source.

    Args:
        core: an ``FTACore``. Read-only here -- probabilities are used as the
            caller last calculated them, so the caller is responsible for
            having run ``recalculate_probabilities()`` (every mutating
            endpoint does) and for holding ``state.lock`` across this call.
        hide_zero: drop nodes whose ``calculatedProbability`` is exactly 0.0,
            matching the CLI's ``--hide-zero``.

    Returns:
        The complete DOT document, title/date header included.
    """
    data = core.get_data() or {}
    metadata = core.get_metadata() or {}
    # The CLI falls back to "FTA Diagram" and today's date when the file
    # carries neither; an FTACore always has both, but an empty string would
    # otherwise produce a stray "Date: " header.
    title = metadata.get("title") or "FTA Diagram"
    date = metadata.get("date") or datetime.now().strftime("%Y-%m-%d")

    if data:
        nodes, edges = gather_nodes(data, hide_zero=hide_zero)
    else:
        # gather_nodes(root={}) would emit a node with the id ``None``.
        # An empty document is not an error -- it is a graph with no nodes.
        nodes, edges = {}, []

    dot_text = build_dot(nodes, edges)

    # json_viewer.py:302-307, replicated. Index order matters: each insert
    # shifts the ones after it, so 1,2,3,4 lands them in written order
    # directly under `digraph G {`.
    dot_lines = dot_text.split("\n")
    dot_lines.insert(1, '  labelloc="t";')
    dot_lines.insert(2, f'  label="{_escape_label(title)}\\nDate: {_escape_label(date)}";')
    dot_lines.insert(3, '  fontsize=14;')
    dot_lines.insert(4, '  fontname="Noto Sans CJK JP";')
    return "\n".join(dot_lines)


# ---- native renderer -----------------------------------------------------


def probe_native_dot() -> Optional[str]:
    """Path to the Graphviz ``dot`` binary, or None.

    Deliberately **not** cached, unlike ``state._probe_native_dot`` which
    answers the same question once at startup for ``/api/state``. A render
    request must report the renderer it actually used: Graphviz can be
    installed (or a PATH entry unmounted) while the editor is open, and
    answering from a startup cache would either refuse a render that would
    now work or promise one that no longer can.
    """
    return shutil.which("dot")


def content_type_for(fmt: str) -> str:
    """MIME type for a supported format. KeyError for anything else."""
    return FORMATS[fmt][0]


def render_native(dot_text: str, fmt: str, high_quality: bool = False) -> bytes:
    """Rasterize/vectorize DOT source with the native Graphviz binary.

    Args:
        dot_text: a complete DOT document, e.g. from :func:`build_dot_text`.
        fmt: ``"svg"`` or ``"png"``.
        high_quality: add the CLI's high-DPI flags. Slower, much larger PNG.

    Returns:
        The encoded image bytes.

    Raises:
        ValueError: unsupported ``fmt``.
        RendererUnavailable: no native ``dot`` (or it vanished before exec).
        RenderError: ``dot`` ran and failed, timed out, or wrote nothing.
    """
    fmt_key = (fmt or "").strip().lower()
    if fmt_key not in FORMATS:
        raise ValueError(
            "Unsupported render format %r; expected one of %s."
            % (fmt, ", ".join(sorted(FORMATS)))
        )

    dot_cmd = probe_native_dot()
    if not dot_cmd:
        raise RendererUnavailable(
            "Native rendering needs the Graphviz 'dot' binary, which was not "
            "found on this machine's PATH. Install Graphviz from %s (macOS: "
            "'brew install graphviz'; Debian/Ubuntu: 'sudo apt install "
            "graphviz'), then reload this page. The diagram shown in the "
            "browser is unaffected -- it is rendered locally in "
            "WebAssembly." % GRAPHVIZ_DOWNLOAD_URL
        )

    _content_type, suffix = FORMATS[fmt_key]
    command = [dot_cmd, "-T%s" % fmt_key]
    if high_quality:
        command.extend(HIGH_QUALITY_FLAGS)

    source_path: Optional[str] = None
    output_path: Optional[str] = None
    try:
        # Written to a file rather than piped through stdin so that any
        # Graphviz diagnostic names a real path, and so the invocation matches
        # json_viewer.render_with_dot's.
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".dot", prefix=TEMP_PREFIX, delete=False, encoding="utf-8"
        ) as source_file:
            source_file.write(dot_text)
            source_path = source_file.name
        with tempfile.NamedTemporaryFile(
            suffix=suffix, prefix=TEMP_PREFIX, delete=False
        ) as output_file:
            output_path = output_file.name

        command.extend(["-o", output_path, source_path])

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                timeout=RENDER_TIMEOUT_SECONDS,
                check=False,  # the return code is inspected below, so the
                              # message can carry Graphviz' own stderr.
            )
        except subprocess.TimeoutExpired as exc:
            raise RenderError(
                "Graphviz 'dot' did not finish within %d seconds. The tree may "
                "be too large to lay out natively; the browser renderer is "
                "still available." % RENDER_TIMEOUT_SECONDS,
                reason="timeout",
            ) from exc
        except OSError as exc:
            # Found by which() a moment ago, unusable now: uninstalled
            # mid-session, or a dangling symlink on PATH.
            raise RendererUnavailable(
                "Graphviz 'dot' was found at %s but could not be executed "
                "(%s). Reinstall Graphviz from %s."
                % (dot_cmd, exc, GRAPHVIZ_DOWNLOAD_URL)
            ) from exc

        if completed.returncode != 0:
            raise RenderError(
                "Graphviz 'dot' exited with status %d without producing a %s."
                % (completed.returncode, fmt_key.upper()),
                stderr=_decode(completed.stderr),
            )

        data = Path(output_path).read_bytes()
        if not data:
            raise RenderError(
                "Graphviz 'dot' reported success but wrote an empty %s."
                % fmt_key.upper(),
                stderr=_decode(completed.stderr),
            )
        return data
    finally:
        # Every exit path, including the raises above: a failed render must
        # not leave the user's temp directory filling up with .dot files.
        for path in (source_path, output_path):
            _unlink_quietly(path)


def _decode(raw: object) -> str:
    """Graphviz' stderr as text, best effort and never fatal."""
    if not raw:
        return ""
    if isinstance(raw, bytes):
        return raw.decode("utf-8", "replace").strip()
    return str(raw).strip()


def _unlink_quietly(path: Optional[str]) -> None:
    """Delete a temp file, ignoring the ways deletion can fail.

    A cleanup failure must never replace the real exception on the way out of
    the ``finally`` block -- losing "Graphviz exited 1" to a stray
    PermissionError from a virus scanner would be the worse outcome.
    """
    if not path:
        return
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    except OSError:
        pass


def describe_renderer() -> Tuple[str, Optional[str]]:
    """``("native", "/usr/bin/dot")`` or ``("wasm", None)``, probed now.

    The single place the two endpoints agree on what "the renderer" means, so
    ``/api/dot`` and ``/api/render`` cannot drift apart on the name they
    report.
    """
    path = probe_native_dot()
    return ("native", path) if path else ("wasm", None)
