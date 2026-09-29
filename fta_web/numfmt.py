"""
Probability formatting shared by the server-side outputs (report, CLI, Excel).

Mirrors ``static/js/numfmt.js`` ``formatProb(v, sf)`` so a number reads the
same in the browser, in a DOCX report and in a CLI table:

* ``sig_figs`` significant figures (1..6, default 3), JavaScript
  ``toPrecision`` style -- trailing zeros kept, so 0.5 is ``0.500``; a value
  with more integer digits than that is rounded and written plain (1234 at
  3 s.f. is ``1230``, as numfmt.js does);
* rounding as ``toPrecision``/``toExponential`` do it: on the exact binary
  value, an exact tie rounding up (0.25 at 1 s.f. is ``0.3``, not Python's
  round-half-even ``0.2``);
* exponent form when the (rounded) magnitude is below 1e-3 or at least 1e4,
  written as numfmt.js writes it: ``1.00e-7``, ``1.23e4`` (no ``+``, no zero
  padding in the exponent);
* ``0`` is ``"0"``; ``None``, NaN and non-numbers are ``"—"``.

The one intended difference from numfmt.js: it picks the plain or exponent
form from the *unrounded* magnitude (0.00099996 at 3 s.f. reads ``1.00e-3``
there, ``0.00100`` here). The USER_GUIDE specifies the rounded magnitude.

The old fixed six-decimal display turned every realistic component
probability (1e-7 ...) into ``0``; this is the replacement.
"""
from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

DEFAULT_SIG_FIGS = 3
MIN_SIG_FIGS = 1
MAX_SIG_FIGS = 6
MISSING = "—"  # em dash


def clamp_sig_figs(value: Any, default: int = DEFAULT_SIG_FIGS) -> int:
    """An integer in 1..6. Unparseable input gives ``default``."""
    if isinstance(value, bool):
        return default
    try:
        number = int(float(value))
    except (TypeError, ValueError, OverflowError):
        return default
    return max(MIN_SIG_FIGS, min(MAX_SIG_FIGS, number))


def format_prob(value: Any, sig_figs: Any = DEFAULT_SIG_FIGS) -> str:
    """``value`` with ``sig_figs`` significant figures (see module docstring)."""
    if value is None or isinstance(value, bool):
        return MISSING
    try:
        number = float(value)
    except (TypeError, ValueError):
        return MISSING
    if math.isnan(number):
        return MISSING
    if math.isinf(number):
        return "∞" if number > 0 else "-∞"
    if number == 0:
        return "0"

    sf = clamp_sig_figs(sig_figs)
    sign = "-" if number < 0 else ""
    # Decimal(float) is the exact binary value, so ROUND_HALF_UP rounds
    # exactly as toPrecision does (only a true tie rounds up).
    exact = Decimal(abs(number))
    rounded = exact.quantize(Decimal(1).scaleb(exact.adjusted() - sf + 1), rounding=ROUND_HALF_UP)
    # Rounding can carry into a new digit (9.996 -> 10.00): keep sf digits.
    rounded = rounded.quantize(Decimal(1).scaleb(rounded.adjusted() - sf + 1))
    # Round first, then decide the form from the rounded exponent, so
    # 0.00099996 at 3 s.f. reads 0.00100 rather than 1.00e-3.
    exponent = rounded.adjusted()
    if exponent < -3 or exponent >= 4:
        mantissa = format(rounded.scaleb(-exponent), "f")
        return "%s%se%d" % (sign, mantissa, exponent)
    return sign + format(rounded, "f")
