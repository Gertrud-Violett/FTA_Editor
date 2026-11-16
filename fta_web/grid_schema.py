"""
Validators and constants of ``POST /api/grid/paste`` (F3, FN-70 grid fields).

The grid endpoint reads numbers in one way only: a finite JSON number inside the
range of its field, through :func:`strict_input.number_field`. A string, a bool,
``null``, ``NaN`` or an infinity is never converted: the browser has already read
the clipboard text with the field's own parser (FN-46), so anything but a number
here means a broken client and answers ``INVALID_FIELD`` (400) naming the field.

``validate_grid_q``         q, a probability in [0, 1]
``validate_grid_lambda``    lambda, per hour, >= 0
``validate_grid_duration``  T and tau, hours, > 0
``validate_grid_mu``        mu, per hour, >= 0
Revision and document serial use :func:`strict_input.validate_revision`.

The existing validators of the node routes are not touched or reused here: they
read numbers more leniently (``"0.25"`` is a probability there) and keep doing so.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

try:  # normal package import: ``import fta_web.grid_schema``
    from .strict_input import number_field
except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
    from strict_input import number_field  # type: ignore[no-redef]

#: The most rows one paste may hold (FN-50). More is refused whole.
MAX_PASTE_ROWS = 2000

#: The keys of a row's ``cells``, in table order (UI-9).
GRID_COLUMNS: Tuple[str, ...] = (
    "id", "name", "model", "lambda", "T", "tau", "mu", "q", "source", "tags",
)

#: Cells that are text (strings) and cells that are numbers.
TEXT_COLUMNS: Tuple[str, ...] = ("id", "name", "model", "source", "tags")
NUMBER_COLUMNS: Tuple[str, ...] = ("lambda", "T", "tau", "mu", "q")

#: The quantification models a ``model`` cell may name.
MODELS: Tuple[str, ...] = ("fixed", "rate", "standby", "repairable")

#: Which models use a number column (DESIGN section 3). q is not listed: it is
#: written only on ``fixed`` and computed on every other model.
USED_BY_MODEL: Dict[str, Tuple[str, ...]] = {
    "lambda": ("rate", "standby", "repairable"),
    "T": ("rate",),
    "tau": ("standby",),
    "mu": ("repairable",),
}

#: Separators of a tags cell: the ASCII and the full-width semicolon and the
#: ideographic comma (the same rule as a typed tags cell in the browser).
TAG_SEPARATORS = (";", "；", "、")


def validate_grid_q(value: Any, field: str = "q") -> Any:
    """A probability: a finite JSON number in [0, 1]."""
    return number_field(value, field, 0, 1)


def validate_grid_lambda(value: Any, field: str = "lambda") -> Any:
    """A failure rate per hour: a finite JSON number >= 0."""
    return number_field(value, field, 0, math.inf)


def validate_grid_duration(value: Any, field: str) -> Any:
    """T or tau in hours: a finite JSON number > 0."""
    return number_field(value, field, 0, math.inf, lo_open=True)


def validate_grid_mu(value: Any, field: str = "mu") -> Any:
    """A repair rate per hour: a finite JSON number >= 0."""
    return number_field(value, field, 0, math.inf)


def validate_number_cell(key: str, value: Any) -> Any:
    """The validator of the number column ``key``."""
    if key == "q":
        return validate_grid_q(value, key)
    if key == "lambda":
        return validate_grid_lambda(value, key)
    if key in ("T", "tau"):
        return validate_grid_duration(value, key)
    return validate_grid_mu(value, key)


def split_tags(text: str) -> List[str]:
    """The tags of a tags cell: split on every separator, trimmed, empties dropped."""
    for separator in TAG_SEPARATORS[1:]:
        text = text.replace(separator, TAG_SEPARATORS[0])
    return [part.strip() for part in text.split(TAG_SEPARATORS[0]) if part.strip()]
