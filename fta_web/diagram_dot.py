"""
DOT generation with the 1.7 diagram options: gate symbols, layout direction
and significant figures.

Phase-0 stub (workstream B completes it): :func:`build_dot_text2` accepts the
final signature and returns the 1.6 DOT from ``rendering.build_dot_text`` with
an empty ``id_map``. Contract for the finished version:

* ``style``: ``compact`` (the 1.6 boxes) or ``symbols`` (IEC/IEEE gate shapes);
* ``rankdir``: ``LR`` (1.6 default) or ``TB``;
* ``sig_figs``: probability labels through ``numfmt.format_prob``;
* ``id_map``: DOT node name -> tree node id for every *synthetic* DOT node
  (gate symbols are named ``<sid>__gate``). Plain event ids are unchanged and
  absent from the map, so click-to-select keeps working without it.
"""
from __future__ import annotations

from typing import Dict, Tuple

try:  # normal package import: ``import fta_web.diagram_dot``
    from .numfmt import clamp_sig_figs
    from .rendering import DEFAULT_FONT, DEFAULT_SCALE, build_dot_text
except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
    from numfmt import clamp_sig_figs  # type: ignore[no-redef]
    from rendering import DEFAULT_FONT, DEFAULT_SCALE, build_dot_text  # type: ignore[no-redef]

STYLES = ("compact", "symbols")
RANKDIRS = ("LR", "TB")
DEFAULT_STYLE = "compact"
DEFAULT_RANKDIR = "LR"


def build_dot_text2(
    core,
    hide_zero: bool = False,
    font_name: str = DEFAULT_FONT,
    scale: float = DEFAULT_SCALE,
    dark: bool = False,
    style: str = DEFAULT_STYLE,
    rankdir: str = DEFAULT_RANKDIR,
    sig_figs: int = 3,
) -> Tuple[str, Dict[str, str]]:
    """``(dot_text, id_map)`` for the tree held by ``core``. Caller holds the lock."""
    style = style if style in STYLES else DEFAULT_STYLE
    rankdir = rankdir if rankdir in RANKDIRS else DEFAULT_RANKDIR
    sig_figs = clamp_sig_figs(sig_figs)
    dot = build_dot_text(
        core, hide_zero=hide_zero, font_name=font_name, scale=scale, dark=dark
    )
    return dot, {}
