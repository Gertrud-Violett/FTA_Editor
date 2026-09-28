"""
The ``.xlsx`` export: the core's workbook plus an "Events" sheet.

Phase-0 stub: :func:`export_xlsx` delegates to ``core.export_to_excel`` so the
export behaves exactly as in 1.6. Workstream D adds the Events sheet (one row
per basic event: id, name, model, parameters, q, calculated probability,
trace and FMEA columns) by re-opening the workbook the core wrote.
"""
from __future__ import annotations

from typing import Optional, Tuple


def export_xlsx(core, path: str) -> Tuple[bool, Optional[str]]:
    """Write ``core``'s document to ``path`` as .xlsx. ``(ok, error)``."""
    return core.export_to_excel(path)
