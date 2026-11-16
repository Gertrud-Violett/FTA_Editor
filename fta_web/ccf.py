"""
Common-cause failure (CCF) groups: the group model and the file format (FN-18).

This is the T1 part of F2 (DESIGN sections 3 and 4): what a stored group is,
how a file carries groups, and how the loader keeps them apart from the
analysis settings. Later tasks add to this module (assessment, expansion,
the one probability function); it has **no module-level import** of
``engine``, ``logic`` or ``lint`` (they import it), so there is no cycle.

Stored group (SPEC 7.1), exactly these eight keys::

    {"id", "name", "model", "beta", "alpha", "testing", "members", "source"}

A beta group has ``alpha: null`` and ``testing: null``; an alpha group has
``beta: null``, a list of alphas and ``testing`` ``"staggered"`` or
``"nonStaggered"`` (or null while no scheme is chosen). The groups of a
document live in its analysis dict as ``analysis["ccfGroups"]`` (a list, kept
verbatim), so the snapshots of undo, the export copy and the CLI already carry
them (DESIGN decision D1). ``engine.coerce_analysis`` knows nothing about the
key: the loader takes it out first (:func:`take_groups`), so no
``analysis_invalid`` warning is ever raised for it and an invalid group (a
beta that is not a number, a missing member, an entry that is not an object)
is kept exactly as the file had it. Lint reports such a group later; nothing
here repairs, coerces or drops it.

File format (SPEC 7.1, FN-18): a file with at least one group is written with
the top-level ``"fileFormatVersion": 2`` placed after ``mode``. A file without
a group is written exactly as FTA Editor 1.8.1 wrote it: no key is added and
none is reordered (FN-28). A ``fileFormatVersion`` above 2 opens with the
warning :data:`NEWER_FORMAT_MESSAGE` (FN-18).

T2 adds what the group API and the lint need: the assessment of each group
(:func:`assess`, FN-33: is it applied, and if not, why), the status and block
shapes built from it, the loader's member remap (FN-38 b) and the helper that
makes membership follow the tree (:func:`remove_members`, FN-38 a).

Sources of the beta-factor model are cited where its formulas live (the
probability function added in a later task of F2), not here.
"""
from __future__ import annotations

import copy
import itertools
import math
from collections import Counter
from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Set, Tuple

try:  # normal package import: ``import fta_web.ccf``
    from . import ccf_text
except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
    import ccf_text  # type: ignore[no-redef]

#: The key in the analysis dict that holds the stored groups.
ANALYSIS_KEY = "ccfGroups"

#: Private analysis keys start with this; they are never written to a file.
PRIVATE_PREFIX = "_ccf"

#: The eight keys of a stored group, in file order (SPEC 7.1).
GROUP_KEYS: Tuple[str, ...] = (
    "id", "name", "model", "beta", "alpha", "testing", "members", "source",
)

#: The ``fileFormatVersion`` written when a group exists (SPEC 7.1).
FORMAT_VERSION = 2

#: Load warning kinds added by F2 (they flow through ``last_load_warnings``
#: to the open response and to the Validation tab as ``LOAD_REPAIR``).
KIND_NEWER_FORMAT = "newer_format"
KIND_CCF_INVALID = "ccf_invalid"

#: FN-18, exact text (no final period).
NEWER_FORMAT_MESSAGE = "This file was saved by a newer FTA Editor; saving may lose data"

#: Shown when ``analysis.ccfGroups`` in a file is present but is not a list.
NOT_A_LIST_MESSAGE = "The ccfGroups entry in the file is not a list, so it was ignored."


# ---- the model --------------------------------------------------------------------


def make_group(group_id: str, name: str, beta: Any, members: Sequence[str],
               source: str = "", model: str = "beta", alpha: Any = None,
               testing: Any = None) -> Dict[str, Any]:
    """A new stored group with the eight keys of SPEC 7.1 in file order.

    ``alpha`` and ``testing`` are None for the beta model, ``beta`` is None for
    the alpha model. No value is checked here: the API validates input
    (``ccf_schema``) and lint judges what a file holds.
    """
    return {
        "id": group_id,
        "name": name,
        "model": model,
        "beta": beta,
        "alpha": alpha,
        "testing": testing,
        "members": list(members),
        "source": source,
    }


def groups_of(analysis: Any) -> List[Any]:
    """The stored groups of a (raw or loaded) analysis dict: the list itself,
    entries verbatim (they may not be objects), or ``[]`` when there is none.

    Read it from the raw ``analysis`` argument, not from the result of
    ``engine.coerce_analysis``, which drops the key (DESIGN D1).
    """
    if not isinstance(analysis, dict):
        return []
    groups = analysis.get(ANALYSIS_KEY)
    return groups if isinstance(groups, list) else []


# ---- loading ----------------------------------------------------------------------


def take_groups(raw_analysis: Any) -> Tuple[Any, Any]:
    """Split the ``analysis`` block of a file into ``(rest, raw_groups)``.

    ``rest`` is the block without ``ccfGroups`` (a shallow copy; the argument
    is not changed), ready for ``engine.coerce_analysis``, so that other
    invalid settings still warn and ``ccfGroups`` never does. ``raw_groups``
    is the value found under the key, untouched, or None when there was none.
    A block that is not an object is returned as it is with ``None``.
    """
    if not isinstance(raw_analysis, dict) or ANALYSIS_KEY not in raw_analysis:
        return raw_analysis, None
    rest = {key: value for key, value in raw_analysis.items() if key != ANALYSIS_KEY}
    return rest, raw_analysis[ANALYSIS_KEY]


def load_groups(raw_groups: Any) -> Tuple[Optional[List[Any]], List[Dict[str, Any]]]:
    """``(groups, warnings)`` for the value found under ``ccfGroups`` (FN-18).

    A list becomes a deep copy with every entry kept verbatim; an empty list
    stores nothing (``groups`` is None, so the key is never written back). A
    value that is neither a list nor None is ignored with one
    ``ccf_invalid`` load warning.
    """
    if raw_groups is None:
        return None, []
    if not isinstance(raw_groups, list):
        return None, [{
            "kind": KIND_CCF_INVALID,
            "old_id": None,
            "new_id": None,
            "message": NOT_A_LIST_MESSAGE,
        }]
    if not raw_groups:
        return None, []
    return copy.deepcopy(raw_groups), []


def format_version_warnings(raw_document: Any) -> List[Dict[str, Any]]:
    """The FN-18 warning when the file's top-level ``fileFormatVersion`` is a
    number above :data:`FORMAT_VERSION` (a bool, a string or null is not one)."""
    if not isinstance(raw_document, dict):
        return []
    version = raw_document.get("fileFormatVersion")
    if isinstance(version, bool) or not isinstance(version, (int, float)):
        return []
    # NaN (Python's json reads the bare token) is not a version number, like a
    # string; Infinity is a number above 2, so it warns like any newer version.
    if (isinstance(version, float) and math.isnan(version)) or version <= FORMAT_VERSION:
        return []
    return [{
        "kind": KIND_NEWER_FORMAT,
        "old_id": None,
        "new_id": None,
        "message": NEWER_FORMAT_MESSAGE,
    }]


# ---- saving -----------------------------------------------------------------------


def export_analysis(analysis: Dict[str, Any]) -> Dict[str, Any]:
    """A deep copy of ``analysis`` for a file: the private ``_ccf*`` keys are
    left out (they only live in a session)."""
    return {
        key: copy.deepcopy(value)
        for key, value in analysis.items()
        if not (isinstance(key, str) and key.startswith(PRIVATE_PREFIX))
    }


def public_analysis(analysis: Any) -> Any:
    """A deep copy of the document's ``analysis`` for an API payload: like
    ``export_analysis`` the private ``_ccf*`` session keys are left out (the
    browser never needs them; the engine state keeps them for undo and for
    ``CCF_MEMBER_RENAMED``, FN-33). A value that is not a dict is copied as it is."""
    if not isinstance(analysis, dict):
        return copy.deepcopy(analysis)
    return export_analysis(analysis)


def export_document(data: Dict[str, Any], analysis: Dict[str, Any]) -> Dict[str, Any]:
    """The document to write: ``data`` (title, date, mode, tree) plus
    ``analysis``, and ``fileFormatVersion`` 2 when a group exists (FN-18).

    With no group the result is ``data`` with ``analysis`` appended last, which
    is byte for byte what 1.8.1 wrote (FN-28). ``data`` itself is never changed:
    both branches return a new dict (the tree inside is shared, not copied).
    With a group the keys are
    ``title, date, mode, fileFormatVersion, tree, analysis``. A file that was
    opened with a newer version number is written as version 2.
    """
    out_analysis = export_analysis(analysis)
    if not groups_of(out_analysis):
        out_analysis.pop(ANALYSIS_KEY, None)  # an empty or odd value is never written
        plain = dict(data)
        plain["analysis"] = out_analysis
        return plain
    rebuilt: Dict[str, Any] = {}
    for key, value in data.items():
        if key == "tree":
            rebuilt["fileFormatVersion"] = FORMAT_VERSION
        if key != "fileFormatVersion":
            rebuilt[key] = value
    rebuilt.setdefault("fileFormatVersion", FORMAT_VERSION)
    rebuilt["analysis"] = out_analysis
    return rebuilt


# ---- membership follows the tree (FN-38) -------------------------------------------

#: Private analysis key: ``{groupId: [memberId, ...]}`` of members whose id the
#: loader had to change in a way that is not one to one (DESIGN D8).
RENAMED_KEY = "_ccfRenamed"


def remap_loaded_members(groups: Sequence[Any], warnings: Sequence[Dict[str, Any]],
                         node_ids: Set[str]) -> Dict[str, List[str]]:
    """FN-38 (b): follow the ids the loader changed, in ``groups`` in place.

    ``warnings`` are the core's ``last_load_warnings`` and ``node_ids`` the ids
    of the loaded tree. A member equal to the old top-level id (``root_id``
    warning) becomes the new id when the mapping is one to one. A member equal
    to an id that was repeated (``duplicate_id`` warnings), or to an old
    top-level id that another node still carries, names more than one node, so
    it is left as it is and reported as ``{groupId: [memberId, ...]}`` for
    ``CCF_MEMBER_RENAMED``. Entries that are not objects are not touched.
    """
    root_map = {w.get("old_id"): w.get("new_id") for w in warnings
                if isinstance(w, dict) and w.get("kind") == "root_id"}
    duplicated = {w.get("old_id") for w in warnings
                  if isinstance(w, dict) and w.get("kind") == "duplicate_id"}
    flagged: Dict[str, List[str]] = {}
    if not root_map and not duplicated:
        return flagged
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("members"), list):
            continue
        gid = group.get("id")
        members = group["members"]
        for position, member in enumerate(members):
            if not isinstance(member, str):
                continue
            ambiguous = member in duplicated or (member in root_map and member in node_ids)
            if ambiguous:
                if isinstance(gid, str) and member not in flagged.setdefault(gid, []):
                    flagged[gid].append(member)
            elif member in root_map:
                members[position] = root_map[member]
    return flagged


def remove_members(core: Any, ids: Any) -> bool:
    """FN-38 (a): take the node ids ``ids`` out of every group's members.

    Called with the ids of the nodes a tree operation removes (tree delete,
    batch delete, AI apply and update, FMEA re-import), after
    ``state.push_undo()`` and before ``state.mark_dirty()``, so the membership
    change is part of that operation's one undo step. A group is never
    deleted, even when it is left with fewer than two members (lint reports
    that). Returns True when something changed.
    """
    analysis = getattr(core, "analysis", None)
    gone = {str(i) for i in ids}
    if not gone or not isinstance(analysis, dict):
        return False
    changed = False
    for group in groups_of(analysis):
        members = group.get("members") if isinstance(group, dict) else None
        if not isinstance(members, list):
            continue
        kept = [m for m in members if not (isinstance(m, str) and m in gone)]
        if len(kept) != len(members):
            group["members"] = kept
            changed = True
    renamed = analysis.get(RENAMED_KEY)
    if isinstance(renamed, dict):
        for gid in list(renamed):
            left = [m for m in renamed[gid] if m not in gone]
            if left:
                renamed[gid] = left
            else:
                del renamed[gid]
        if not renamed:
            del analysis[RENAMED_KEY]
    return changed


# ---- assessment: is a group applied, and if not why (FN-33) ------------------------

#: Models the code can expand; a group with another model is kept and
#: reported ``CCF_BAD_PARAMETER`` (kind ``model``).
SUPPORTED_MODELS: Tuple[str, ...] = ("beta", "alpha")

#: The alpha-factor model handles groups of 2 to 4 members (FN-41).
ALPHA_MIN_MEMBERS, ALPHA_MAX_MEMBERS = 2, 4

#: The two testing schemes of the alpha-factor model (SPEC 7.1 spelling).
TESTING_SCHEMES: Tuple[str, ...] = ("staggered", "nonStaggered")

#: An alpha sum within this of 1 is accepted and divided out (FN-43); within
#: ``ALPHA_SUM_EXACT`` of 1 nothing is reported. ``ALPHA_SUM_SLACK`` absorbs
#: float noise in the sum, so that (0.899, 0.1), whose decimal deviation is
#: exactly 0.001, is inside the tolerance as FN-43 says.
ALPHA_SUM_TOLERANCE = 1e-3
ALPHA_SUM_EXACT = 1e-9
ALPHA_SUM_SLACK = 1e-15

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
SEVERITY_STATUS = "status"

#: ``CCF_HIGH_Q`` threshold: the editor's rule (FN-33), on Q_t. NUREG/CR-5485 p. 44
#: gives 10^-2 for the independent event unavailability, as one condition for the
#: global-term simplification of the beta factor model.
#: NUREG/CR-5485 p. A-5 says Eq. A.8 (Q_t = sum of C(m-1,k-1) Q_k) is still
#: valid "under the rare event approximation" when the common-cause basic
#: events are treated as independent instead of mutually exclusive.
HIGH_Q = 0.01

#: Relative tolerance of "members are identical" (FN-33).
REL_TOL = 1e-6

#: The compared parameters of each quantification model (FN-33).
_PARAMETER_KEYS = {
    "fixed": ("q",),
    "rate": ("lambda", "T"),
    "standby": ("lambda", "tau"),
    "repairable": ("lambda", "mu"),
}

_ORDERED_GATES = ("PAND", "XOR")


class Finding(NamedTuple):
    """One lint finding about one group (and one member, when it has one)."""

    code: str
    severity: str           # 'error' | 'warning' | 'status'
    group_id: Optional[str]
    group_name: str
    member_id: Optional[str]
    member_name: str        # for a group-level code: the member names, comma list
    kind: str
    params: Dict[str, str]  # reference, other, model, q (only those the text uses)

    def text(self) -> Dict[str, Dict[str, Optional[str]]]:
        """``{"en": {reason, message, fix}, "ja": {...}}`` (``ccf_text``)."""
        fields = {"group": self.group_name, "member": self.member_name}
        fields.update(self.params)
        kind = self.kind or None
        if fields.pop("reserved", None):
            kind = "reserved"  # kind stays "id" (DESIGN section 4); only the wording differs
        return ccf_text.lint_text(self.code, kind, fields)


class GroupAssessment(NamedTuple):
    """What is the matter with one stored group. ``applied`` is True iff there
    is no error and the document is in FTA mode; ``primary`` is the first
    error (or the ETA status), ``findings`` lists everything found."""

    id: Optional[str]
    name: str
    model: Any
    beta: Any
    members: List[str]
    applied: bool
    primary: Optional[Finding]
    findings: List[Finding]
    #: Alpha groups only: the stored ``alpha`` and ``testing`` and the original
    #: sum of the alphas (None unless the list is valid and within tolerance).
    alpha: Any = None
    testing: Any = None
    alpha_sum: Optional[float] = None


class _TreeView:
    """Lookups over a tree, built once per assessment: first node of an id,
    names, and the nodes that reach a node (its parents, the nodes linking to
    it and the transfers to it)."""

    def __init__(self, tree: Any):
        self.index: Dict[str, Dict[str, Any]] = {}
        self.reached_by: Dict[str, Set[str]] = {}
        self.reserved_id = False
        stack = [tree] if isinstance(tree, dict) else []
        while stack:
            node = stack.pop()
            nid = str(node.get("id"))
            self.index.setdefault(nid, node)
            if nid.startswith("ccf:"):
                self.reserved_id = True
            children = [c for c in node.get("children") or [] if isinstance(c, dict)]
            for child in children:
                self.reached_by.setdefault(str(child.get("id")), set()).add(nid)
            stack.extend(reversed(children))  # pre-order: the first node of an id wins
            for link in node.get("links") or []:
                if isinstance(link, dict) and link.get("target_id") not in (None, ""):
                    self.reached_by.setdefault(str(link["target_id"]), set()).add(nid)
            if gate_type(node) == "TRANSFER" and node.get("transferTo") not in (None, ""):
                self.reached_by.setdefault(str(node["transferTo"]), set()).add(nid)

    def name(self, node_id: str) -> str:
        node = self.index.get(node_id)
        if node is None:
            return node_id
        name = node.get("name")
        return name if isinstance(name, str) and name else node_id

    def has_ordered_ancestor(self, node_id: str) -> bool:
        seen = {node_id}
        stack = [node_id]
        while stack:
            for above in self.reached_by.get(stack.pop(), ()):
                if above in seen:
                    continue
                seen.add(above)
                stack.append(above)
                if gate_type(self.index.get(above) or {}) in _ORDERED_GATES:
                    return True
        return False


def gate_type(node: Dict[str, Any]) -> Optional[str]:
    """The node's ``gateType`` upper-cased, or None."""
    raw = node.get("gateType") if isinstance(node, dict) else None
    return raw.strip().upper() if isinstance(raw, str) and raw.strip() else None


def member_ids(group: Any) -> List[str]:
    """The distinct member ids of a stored group, in order. Anything that is
    not a non-empty string (or a members entry that is not a list) is left
    out; the group's own ``members`` value is never changed."""
    members = group.get("members") if isinstance(group, dict) else None
    seen: Set[str] = set()
    out: List[str] = []
    if isinstance(members, list):
        for item in members:
            if isinstance(item, str) and item and item not in seen:
                seen.add(item)
                out.append(item)
    return out


def beta_is_valid(value: Any) -> bool:
    """A finite JSON number from 0 to 1, both ends included (FN-70). A bool,
    a string, None or a missing key is not a beta."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return 0.0 <= float(value) <= 1.0
    except OverflowError:
        return False


def _not_basic_kind(view: _TreeView, member_id: str) -> Optional[str]:
    """Why a member is not a basic event (FN-33), or None when it is one.

    A leaf with a stray ``gateType`` is a leaf for the engine, hence basic."""
    node = view.index.get(member_id)
    if node is None:
        return "missing"
    if gate_type(node) == "TRANSFER":
        return "transfer"
    if node.get("children"):
        return "gate"
    kind = str(node.get("eventKind") or "").lower()
    if kind == "house":
        return "house"
    if kind == "conditioning":
        return "conditioning"
    return None


def _engine() -> Any:
    """The engine module, imported on first use (it imports this module)."""
    try:
        from . import engine
    except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
        import engine  # type: ignore[no-redef]
    return engine


def _quant_of(node: Dict[str, Any], analysis: Dict[str, Any]) -> Tuple[Dict[str, Any], Optional[float]]:
    """``(derive_quant result, Q_t or None)``; Q_t is None when the model cannot
    be evaluated or the value is not a finite number."""
    try:
        derived = _engine().derive_quant(node, analysis)
    except Exception:  # a malformed node must not break the assessment
        return {"model": "fixed", "params": {}, "q": None}, None
    q = derived.get("q")
    if isinstance(q, bool) or not isinstance(q, (int, float)) or not math.isfinite(q):
        return derived, None
    return derived, float(q)


def _close(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is None and b is None
    try:
        return math.isclose(float(a), float(b), rel_tol=REL_TOL, abs_tol=0.0)
    except (TypeError, ValueError):
        return a == b


def _uncertainty_of(node: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    quant = node.get("quant")
    unc = quant.get("unc") if isinstance(quant, dict) else None
    if isinstance(unc, dict) and unc.get("dist"):
        return unc
    return None


def _differs(ref: Tuple[Dict[str, Any], Dict[str, Any], float],
             other: Tuple[Dict[str, Any], Dict[str, Any], float]) -> Optional[str]:
    """The first way ``other`` differs from ``ref`` (FN-33): ``model``,
    ``parameter``, ``qt`` or ``uncertainty``; None when identical.
    Each argument is ``(node, derive_quant result, Q_t)``."""
    (ref_node, ref_d, ref_q), (node, d, q) = ref, other
    if ref_d.get("model") != d.get("model"):
        return "model"
    for key in _PARAMETER_KEYS.get(str(d.get("model")), ()):
        if not _close((ref_d.get("params") or {}).get(key), (d.get("params") or {}).get(key)):
            return "parameter"
    if not _close(ref_q, q):
        return "qt"
    ref_unc, unc = _uncertainty_of(ref_node), _uncertainty_of(node)
    if (ref_unc is None) != (unc is None):
        return "uncertainty"
    if ref_unc is not None and unc is not None:
        if str(ref_unc.get("dist")).lower() != str(unc.get("dist")).lower():
            return "uncertainty"
        for key in ("median", "mean", "ef"):
            if not _close(ref_unc.get(key), unc.get(key)):
                return "uncertainty"
    return None


def _members_text(names: Sequence[str]) -> str:
    """Member names for a group-level text: at most five, then ``, ...``."""
    if not names:
        return "-"
    shown = ", ".join(names[:5])
    return shown + (", ..." if len(names) > 5 else "")


def _alpha_checks(raw: Dict[str, Any], n: int, add: Any) -> Optional[float]:
    """The parameter checks of an alpha group (FN-43, DESIGN 4.1), reported
    through ``add``: ``CCF_ALPHA_SIZE`` (``n`` members, not 2 to 4; the sum is
    then not looked at), ``CCF_ALPHA_SUM`` (kind ``length``, ``range`` or
    ``sum``) and ``CCF_NO_TESTING`` (kind ``missing`` or ``unknown``).

    Returns the original sum of the alphas when the list is valid and within
    the tolerance of 1 (the group is applied; a sum not within 1e-9 of 1 is
    then warned with ``CCF_ALPHA_NORMALISED``), else None."""
    total = None
    if not ALPHA_MIN_MEMBERS <= n <= ALPHA_MAX_MEMBERS:
        add("CCF_ALPHA_SIZE", SEVERITY_ERROR, n=str(n))
    else:
        values = raw.get("alpha")
        if not isinstance(values, list) or len(values) != n:
            count = len(values) if isinstance(values, list) else 0
            add("CCF_ALPHA_SUM", SEVERITY_ERROR, "length", count=str(count), n=str(n))
        else:
            # an alpha_k is a finite JSON number from 0 to 1, like beta (FN-70)
            bad = next((k for k, value in enumerate(values, 1) if not beta_is_valid(value)), None)
            if bad is not None:
                add("CCF_ALPHA_SUM", SEVERITY_ERROR, "range", k=str(bad), n=str(n))
            else:
                total = float(sum(values))
                if abs(total - 1.0) > ALPHA_SUM_TOLERANCE + ALPHA_SUM_SLACK:
                    add("CCF_ALPHA_SUM", SEVERITY_ERROR, "sum", sum="%.12g" % total, n=str(n))
                    total = None
    testing = raw.get("testing")
    if testing is None or testing == "":
        add("CCF_NO_TESTING", SEVERITY_ERROR, "missing")
    elif testing not in TESTING_SCHEMES:
        add("CCF_NO_TESTING", SEVERITY_ERROR, "unknown", testing=str(testing))
    return total


def _event_id_clashes(entries: Sequence[Any], id_counts: Dict[str, int]) -> Dict[int, str]:
    """``{group index: a CCF event id}`` for each group that would create an
    event id which another event, of the same group or of another group, also
    creates (FN-41). Event ids join group and member ids with ``+`` and ``:``,
    so ids that contain these characters can clash (members ``a``, ``b+c``,
    ``a+b``, ``c`` give ``a+b+c`` twice; alpha group ``g`` on ``a``, ``b`` and
    beta group ``g:a+b`` both give ``ccf:g:a+b``); the structure would merge
    the two events. The ids are those ``build_plan`` makes, for every group
    that has a usable id, a supported model and a member count it can expand
    (whether or not other findings stop it later)."""
    planned: Dict[int, List[str]] = {}
    for index, group in enumerate(entries):
        gid = group.get("id") if isinstance(group, dict) else None
        if not (isinstance(gid, str) and gid) or id_counts.get(gid, 0) > 1:
            continue
        ids = member_ids(group)
        if group.get("model") == "alpha" and ALPHA_MIN_MEMBERS <= len(ids) <= ALPHA_MAX_MEMBERS:
            subsets = _alpha_subsets(len(ids))
        elif group.get("model") == "beta" and len(ids) >= 2:
            subsets = [tuple(range(len(ids)))]
        else:
            continue
        planned[index] = [event_id(gid, group["model"], ids, subset) for subset in subsets]
    counts = Counter(event for found in planned.values() for event in found)
    clashes: Dict[int, str] = {}
    for index, found in planned.items():
        repeated = next((event for event in found if counts[event] > 1), None)
        if repeated is not None:
            clashes[index] = repeated
    return clashes


def assess(groups: Any, tree: Any, analysis: Any, mode: str = "FTA",
           _view: Optional[_TreeView] = None) -> List[GroupAssessment]:
    """Judge every stored group (FN-33, DESIGN section 4): pure, O(nodes).

    ``groups`` are the raw stored entries (any may be invalid), ``tree`` the
    top node, ``analysis`` the raw analysis dict (it supplies the mission time
    and the loader's ``_ccfRenamed`` map). In ETA mode each group has one
    ``CCF_ETA_MODE`` status and nothing else. In FTA mode the error checks run
    in this order, the first one found is ``primary`` and all are listed:
    group id / model, too few members, member not basic, renamed member,
    member in two groups, bad parameters (beta, or the alpha checks of
    :func:`_alpha_checks`), no probability, members differ, Q = 1.
    A group with no error is applied; its warnings (``CCF_ALPHA_NORMALISED``,
    ``CCF_HIGH_Q``, ``CCF_ZERO_Q``, ``CCF_ORDERED_GATE``) are listed too.
    """
    entries = list(groups) if isinstance(groups, list) else []
    mode = "ETA" if str(mode or "FTA").upper() == "ETA" else "FTA"
    analysis = analysis if isinstance(analysis, dict) else {}
    view = _view if _view is not None else _TreeView(tree)
    renamed = analysis.get(RENAMED_KEY) if isinstance(analysis.get(RENAMED_KEY), dict) else {}
    quant_analysis = analysis
    if "missionTime" not in analysis:  # a partial analysis: the defaults fill the rest
        quant_analysis = dict(_engine().DEFAULT_ANALYSIS)
        quant_analysis.update(analysis)

    id_counts: Dict[str, int] = {}
    holders: Dict[str, List[int]] = {}  # member id -> indexes of the groups holding it
    for index, group in enumerate(entries):
        gid = group.get("id") if isinstance(group, dict) else None
        if isinstance(gid, str) and gid:
            id_counts[gid] = id_counts.get(gid, 0) + 1
        for mid in member_ids(group):
            holders.setdefault(mid, []).append(index)

    def group_name(group: Any) -> str:
        name = group.get("name") if isinstance(group, dict) else None
        gid = group.get("id") if isinstance(group, dict) else None
        if isinstance(name, str) and name.strip():
            return name
        return gid if isinstance(gid, str) and gid else "(unnamed)"

    clashes = _event_id_clashes(entries, id_counts) if mode == "FTA" else {}
    out: List[GroupAssessment] = []
    for index, group in enumerate(entries):
        raw = group if isinstance(group, dict) else {}
        gid = raw.get("id") if isinstance(raw.get("id"), str) and raw.get("id") else None
        gname = group_name(group)
        ids = member_ids(group)
        names = [view.name(m) for m in ids]
        listed = _members_text(names)
        findings: List[Finding] = []
        alpha_sum: Optional[float] = None

        def add(code: str, severity: str, kind: str = "", member: Optional[str] = None,
                **params: str) -> None:
            findings.append(Finding(
                code, severity, gid, gname, member,
                view.name(member) if member is not None else listed, kind, dict(params)))

        if mode == "ETA":
            add("CCF_ETA_MODE", SEVERITY_STATUS)
        else:
            if view.reserved_id:
                # FN-33: a node id "ccf:..." would collide with a CCF event id.
                add("CCF_BAD_PARAMETER", SEVERITY_ERROR, "id", reserved="1")
            elif gid is None or id_counts.get(gid, 0) > 1:
                add("CCF_BAD_PARAMETER", SEVERITY_ERROR, "id")
            if index in clashes:
                add("CCF_BAD_PARAMETER", SEVERITY_ERROR, "event_id", event=clashes[index])
            if raw.get("model") not in SUPPORTED_MODELS:
                add("CCF_BAD_PARAMETER", SEVERITY_ERROR, "model", model=str(raw.get("model")))
            if len(ids) < 2:
                if ids:
                    add("CCF_TOO_FEW_MEMBERS", SEVERITY_ERROR, "one", ids[0])
                else:
                    add("CCF_TOO_FEW_MEMBERS", SEVERITY_ERROR, "none")
            for mid in ids:
                kind = _not_basic_kind(view, mid)
                if kind:
                    add("CCF_MEMBER_NOT_BASIC", SEVERITY_ERROR, kind, mid)
            flagged = renamed.get(gid) if gid is not None else None
            for mid in ids:
                if isinstance(flagged, list) and mid in flagged:
                    add("CCF_MEMBER_RENAMED", SEVERITY_ERROR, "", mid)
            for mid in ids:
                others = [i for i in holders.get(mid, []) if i != index]
                if others:
                    add("CCF_MEMBER_IN_TWO_GROUPS", SEVERITY_ERROR, "", mid,
                        other=group_name(entries[others[0]]))
            if raw.get("model") == "alpha":
                alpha_sum = _alpha_checks(raw, len(ids), add)
            elif not beta_is_valid(raw.get("beta")):
                add("CCF_BAD_PARAMETER", SEVERITY_ERROR, "beta")

            eligible: List[Tuple[str, Tuple[Dict[str, Any], Dict[str, Any], float]]] = []
            for mid in ids:
                if _not_basic_kind(view, mid):
                    continue  # already reported; later checks skip it
                node = view.index[mid]
                derived, q = _quant_of(node, quant_analysis)
                if q is None:
                    add("CCF_NO_PROBABILITY", SEVERITY_ERROR, "", mid)
                else:
                    eligible.append((mid, (node, derived, q)))
            if eligible:
                ref_id, ref = eligible[0]
                for mid, item in eligible[1:]:
                    kind = _differs(ref, item)
                    if kind:
                        add("CCF_MEMBERS_DIFFER", SEVERITY_ERROR, kind, mid,
                            reference=view.name(ref_id))
            for mid, item in eligible:
                if item[2] >= 1.0:
                    add("CCF_Q_ONE", SEVERITY_ERROR, "", mid)

            if not any(f.severity == SEVERITY_ERROR for f in findings):
                if (alpha_sum is not None
                        and abs(alpha_sum - 1.0) > ALPHA_SUM_EXACT + ALPHA_SUM_SLACK):
                    add("CCF_ALPHA_NORMALISED", SEVERITY_WARNING, sum="%.12g" % alpha_sum)
                qts = [(item[2], mid) for mid, item in eligible]
                if qts:
                    high_q, high_id = max(qts, key=lambda pair: pair[0])
                    if high_q > HIGH_Q:
                        add("CCF_HIGH_Q", SEVERITY_WARNING,
                            "alpha" if raw.get("model") == "alpha" else "", high_id,
                            q="%.3g" % high_q)
                    if all(q == 0.0 for q, _mid in qts):
                        add("CCF_ZERO_Q", SEVERITY_WARNING)  # group-level: names all members
                for mid in ids:
                    if view.has_ordered_ancestor(mid):
                        add("CCF_ORDERED_GATE", SEVERITY_WARNING, "", mid)

        primary = next((f for f in findings
                        if f.severity in (SEVERITY_ERROR, SEVERITY_STATUS)), None)
        out.append(GroupAssessment(
            gid, gname, raw.get("model"), raw.get("beta"), ids,
            primary is None, primary, findings, raw.get("alpha"), raw.get("testing"),
            alpha_sum))
    return out


# ---- the shapes the API, lint and CLI hand out --------------------------------------


def _item(finding: Finding) -> Dict[str, Any]:
    texts = finding.text()
    return {
        "code": finding.code,
        "severity": finding.severity,
        "member": finding.member_name,
        "memberId": finding.member_id,
        "reason": {lang: texts[lang]["reason"] for lang in ccf_text.LANGS},
        "message": {lang: texts[lang]["message"] for lang in ccf_text.LANGS},
    }


def status_of(assessment: GroupAssessment) -> Dict[str, Any]:
    """The ``status`` object of one group in the API (DESIGN section 8)."""
    primary = assessment.primary
    status: Dict[str, Any] = {
        "applied": assessment.applied,
        "code": None, "severity": None, "reason": None, "message": None,
        "errors": [_item(f) for f in assessment.findings if f.severity == SEVERITY_ERROR],
        "warnings": [_item(f) for f in assessment.findings if f.severity == SEVERITY_WARNING],
    }
    if primary is not None:
        item = _item(primary)
        status.update(code=primary.code, severity=primary.severity,
                      reason=item["reason"], message=item["message"])
    return status


def block(assessments: Sequence[GroupAssessment]) -> Dict[str, Any]:
    """The ``ccf`` block of API and CLI results (DESIGN section 4): the groups
    applied (with their warnings; an alpha group also carries ``alpha``,
    ``testing``, ``alphaSum`` and ``alphaNormalised``, F2A DESIGN 2.3), the
    groups not applied with the English reason, and the FN-67 note. Present
    only when the document has a group."""
    applied: List[Dict[str, Any]] = []
    not_applied: List[Dict[str, Any]] = []
    for a in assessments:
        if a.applied:
            item = {
                "id": a.id, "name": a.name, "model": a.model, "beta": a.beta,
                "members": list(a.members),
                "warnings": [{"code": f.code, "member": f.member_name,
                              "reason": f.text()["en"]["reason"]}
                             for f in a.findings if f.severity == SEVERITY_WARNING],
            }
            if a.model == "alpha":  # F2A (DESIGN 2.3): beta items stay as F2 had them
                item.update(
                    alpha=copy.deepcopy(a.alpha), testing=a.testing, alphaSum=a.alpha_sum,
                    alphaNormalised=any(f.code == "CCF_ALPHA_NORMALISED" for f in a.findings))
            applied.append(item)
        else:
            primary = a.primary
            not_applied.append({
                "id": a.id, "name": a.name, "code": primary.code if primary else None,
                "reason": primary.text()["en"]["reason"] if primary else None,
            })
    return {"applied": applied, "notApplied": not_applied, "note": ccf_text.NOTE[0]}


def eta_block(tree: Any, analysis: Any) -> Optional[Dict[str, Any]]:
    """The ``ccf`` block of an event-tree (ETA) document: every group in
    ``notApplied`` with code ``CCF_ETA_MODE`` (FN-26). None without groups, so a
    file without groups gets no ``ccf`` key (FN-28)."""
    groups = groups_of(analysis)
    if not groups:
        return None
    return block(assess(groups, tree, analysis, "ETA"))


def display_name(event: Any, lang: str = "en") -> str:
    """The name of a cut-set or importance event in ``lang`` (FN-22, FN-25).

    A CCF event reads ``CCF: <group name>`` (an alpha subset event, whose
    marker holds ``memberNames``: ``CCF: <group name> (<name> + <name>)``) and
    the independent part of a member ``<name> (independent part)`` (ja
    ``<name>（独立部分）``); any other event keeps its own name (its id when it
    has none).
    """
    if not isinstance(event, dict):
        return str(event)
    marker = event.get("ccf")
    name = str(event.get("name") or event.get("id") or "")
    if not isinstance(marker, dict):
        return name
    base = str(marker.get("baseName") or "")
    if marker.get("role") == "independent":
        return ccf_text.text(lang, "event.independent", name=base)
    if marker.get("role") == "event":
        names = marker.get("memberNames")  # alpha subset events only
        if isinstance(names, list):
            return ccf_text.text(lang, "label.subset", name=base, members=" + ".join(names))
        return ccf_text.text(lang, "event.ccf", name=base)
    return name


def listing(tree: Any, analysis: Any, mode: str = "FTA") -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """``(groups, block)`` for ``GET /api/ccf/groups``: every stored group
    with its eight keys (a key the file lacked reads None; the stored value is
    otherwise returned as it is), ``memberNames`` (None for an id not in the
    tree) and ``status``."""
    raw_groups = groups_of(analysis)
    assessments = assess(raw_groups, tree, analysis, mode)
    view = _TreeView(tree)
    items: List[Dict[str, Any]] = []
    for group, assessment in zip(raw_groups, assessments):
        stored = group if isinstance(group, dict) else {}
        item = {key: copy.deepcopy(stored.get(key)) for key in GROUP_KEYS}
        members = stored.get("members")
        item["memberNames"] = [
            (view.name(m) if m in view.index else None) if isinstance(m, str) else None
            for m in members] if isinstance(members, list) else []
        item["status"] = status_of(assessment)
        if assessment.applied and assessment.model == "alpha":
            item["alphaParts"] = _alpha_parts(stored, assessment, view)
        items.append(item)
    return items, block(assessments)


def _alpha_parts(stored: Dict[str, Any], assessment: GroupAssessment, view: "_TreeView") -> Dict[str, Any]:
    """The numbers the Details panel shows for a member of an applied alpha
    group (F2A rework R1), straight from :func:`event_probabilities` so that
    the panel and the diagram agree: ``independent`` (``Q_1`` per member, in
    member order) and ``events`` (one ``{members, memberNames, q}`` per
    member subset of size 2 or more, the order of :func:`_alpha_subsets`).
    Only a listing item of an applied alpha group has it."""
    ids = list(assessment.members)
    qts = [_node_q(view.index[m]) for m in ids]
    params = {key: stored.get(key) for key in ("beta", "alpha", "testing")}
    expansion = event_probabilities(assessment.model, params, qts)
    return {
        "independent": list(expansion.independent),
        "events": [{"members": [ids[i] for i in idxs],
                    "memberNames": [view.name(ids[i]) for i in idxs], "q": q}
                   for idxs, q in expansion.events],
    }


#: Why a summary's cut sets are incomplete (DESIGN section 6 step 3).
INCOMPLETE_REASONS = ("time", "error", "summary cap")


def summary_fields(tree: Any, analysis: Any, failure: Optional[str] = None) -> Dict[str, Any]:
    """The CCF keys of a fault-tree ``summary`` (FN-37, FN-21): ``ccf`` (the
    block: groups applied, groups not applied with their reason, the FN-67
    note), ``ccfIncomplete`` and, when True, ``ccfIncompleteReason``.

    Empty (no key at all) for a document without groups, so its summary keeps
    the 1.8.1 key set (FN-28). ``failure`` is why the cut sets are incomplete
    (one of ``INCOMPLETE_REASONS``) or None; it only counts when at least one
    group is applied, because a group that is not applied changes no number.
    The summary is a fault-tree result, so the groups are judged in FTA mode.
    """
    groups = groups_of(analysis)
    if not groups:
        return {}
    assessments = assess(groups, tree, analysis, "FTA")
    incomplete = bool(failure) and any(a.applied for a in assessments)
    fields: Dict[str, Any] = {"ccf": block(assessments), "ccfIncomplete": incomplete}
    if incomplete:
        fields["ccfIncompleteReason"] = failure
    return fields


def lint_issues(analysis: Any, tree: Any, mode: str = "FTA") -> List[Tuple[str, Dict[str, Any], str]]:
    """``(code, params, English message)`` for each error and warning of each
    group, for ``lint.run`` (Validation tab). The ``CCF_ETA_MODE`` status is
    never an issue, and in ETA mode there is none at all (FN-37)."""
    if str(mode or "FTA").upper() == "ETA":
        return []
    issues: List[Tuple[str, Dict[str, Any], str]] = []
    for assessment in assess(groups_of(analysis), tree, analysis, "FTA"):
        for finding in assessment.findings:
            if finding.severity == SEVERITY_STATUS:
                continue
            texts = finding.text()
            params: Dict[str, Any] = {
                "groupId": finding.group_id,
                "group": finding.group_name,
                "memberId": finding.member_id,
                "member": finding.member_name,
                "text": texts,
            }
            if finding.kind:
                params["kind"] = finding.kind
            issues.append((finding.code, params, texts["en"]["message"]))
    return issues


# ---- the one probability function (FN-19, DESIGN section 4) -------------------------


class GroupExpansion(NamedTuple):
    """What one group adds to the structure.

    ``independent[i]`` is the probability of the independent part of member
    ``i`` (same order as the members). ``events`` lists the CCF events as
    ``(member indexes, q)``; the beta model has exactly one, over all members.
    """

    independent: Tuple[float, ...]
    events: Tuple[Tuple[Tuple[int, ...], float], ...]


def _beta_model(params: Any, member_qt: Sequence[float]) -> GroupExpansion:
    """The beta-factor model: split each member's total probability Q_t.

    Every member fails alone with the independent part ``Q_1 = (1 - beta) Q_t``,
    and one more event, shared by all members of the group, fails all of them
    together with ``Q_m = beta Q_t``.

    Sources (printed page numbers; the reference values are in SPEC 7.4):

    * NUREG/CR-4780 Vol. 2, Table C-1 p. C-5 (the beta-factor model in its
      basic-parameter form) and Eq. C.10-C.13 p. C-6 (``Q_1`` and ``Q_m``
      from ``Q_t`` and beta).
    * NUREG/CR-5485, Eq. 5.11-5.13 p. 42 (the same split) and Table 5-2 p. 49
      (the formulas for Case 1, AND of two, ``Q_1^2 + Q_2``, and Case 2, OR of
      two, ``2 Q_1 + Q_2``).  The numbers 1.0081e-4 and 1.9e-3 are those
      formulas evaluated at ``Q_t = 1e-3`` and beta = 0.1 (SPEC 7.4, R1 and
      R2); the analyst found no numeric worked example in the sources (SPEC
      7.4, OQ-5).
    * NASA/SP-2011-3421, Eq. 7-3 p. 7-5 (the beta-factor split of a
      two-component group).

    The members of a group are identical components (FN-33 judges that, equal
    within a relative 1e-6). The CCF event uses the first member's ``Q_t``; each
    independent part is ``(1 - beta)`` times that member's own ``Q_t``. In Monte
    Carlo all of them follow the one shared draw. The product is the plain float
    multiplication ``(1.0 - beta) * q``: ``(1 - 0.1) * 1e-3`` is
    ``9.000000000000001e-4``, so callers compare with a relative tolerance,
    never with ``==``.
    """
    beta = float(params["beta"])
    qts = tuple(float(q) for q in member_qt)
    independent = tuple((1.0 - beta) * q for q in qts)
    events: Tuple[Tuple[Tuple[int, ...], float], ...] = ()
    if qts:
        events = ((tuple(range(len(qts))), beta * qts[0]),)
    return GroupExpansion(independent, events)


def _alpha_subsets(m: int) -> List[Tuple[int, ...]]:
    """The member subsets of size 2 to m of an alpha group of m members, as
    position tuples: size ascending, then in group order (FN-41). Each one is
    a CCF event."""
    return [subset for k in range(2, m + 1) for subset in itertools.combinations(range(m), k)]


def _alpha_model(params: Any, member_qt: Sequence[float]) -> GroupExpansion:
    """The alpha-factor model for a group of m identical members (FN-41).

    ``params["alpha"]`` holds alpha_1 .. alpha_m (``alpha_k`` is the fraction
    of failure events that fail exactly k members) and ``params["testing"]``
    is ``"staggered"`` or ``"nonStaggered"``. Every alpha is first divided by
    the sum of the alphas (FN-43; assessment has already refused a sum more
    than 1e-3 from 1), written ``alpha'_k`` below. ``Q_k`` is the probability
    of EACH CCF event that fails one given set of k members; a member is in
    ``C(m-1, k-1)`` of the ``C(m, k)`` sets of size k.

    Sources (printed page numbers):

    * Staggered testing: ``Q_k = alpha'_k / C(m-1, k-1) * Q_t``
      (NUREG/CR-5485 Eq. 5.6 p. 40).
    * Non-staggered testing: ``alpha_t = sum_k k alpha'_k`` and
      ``Q_k = k / C(m-1, k-1) * (alpha'_k / alpha_t) * Q_t``
      (NUREG/CR-5485 Eq. 5.7-5.9 p. 41; NUREG/CR-4780 Vol. 2 Eq. C.23-C.24
      pp. C-10/C-11, as cited in SPEC 7.3, not independently checked).

    Consistency: ``sum_k C(m-1, k-1) Q_k = Q_t`` for both schemes. For m = 2
    and alpha = (1 - beta, beta) the staggered formula gives the beta-factor
    model (a derivation from Eq. 5.6, not a printed statement).

    Source errors that are NOT copied (SPEC 7.3):

    * NUREG/CR-5485 Eq. 5.10 prints ``Q_3 = 3 alpha_3 Q_t``; the right
      value is ``alpha_3 Q_t`` (this is the m = 3 case of Eq. 5.6, and
      NASA/SP-2011-3421 Eq. 7-16 p. 7-15 repeats the printed error).
    * NUREG/CR-5485 Tables 5-4 and 5-5 have their m = 4 rows swapped.
    * NUREG/CR-5485 Table 5-5 "2 of 5" has a stray division by 4.

    The members are identical (FN-33), so every ``Q_t`` is the first member's.
    The result lists one event per member subset of size k >= 2 (size
    ascending, then group order), each with ``Q_k``, even when it is 0.
    """
    qts = tuple(float(q) for q in member_qt)
    m = len(qts)
    alpha = [float(a) for a in params["alpha"]]
    if len(alpha) != m:
        raise ValueError("CCF alpha model: %d alpha values for %d members" % (len(alpha), m))
    total = sum(alpha)
    scaled = [a / total for a in alpha]
    testing = params["testing"]
    if testing == "staggered":
        q_k = [scaled[k - 1] / math.comb(m - 1, k - 1) * qts[0] for k in range(1, m + 1)]
    elif testing == "nonStaggered":
        alpha_t = sum(k * scaled[k - 1] for k in range(1, m + 1))
        q_k = [k / math.comb(m - 1, k - 1) * (scaled[k - 1] / alpha_t) * qts[0]
               for k in range(1, m + 1)]
    else:
        raise ValueError("CCF testing scheme %r is not available" % (testing,))
    events = tuple((subset, q_k[len(subset) - 1]) for subset in _alpha_subsets(m))
    return GroupExpansion((q_k[0],) * m, events)


#: Model name -> expansion function; the callers (the expansion, Monte Carlo)
#: only go through :func:`event_probabilities`.
MODELS: Dict[str, Any] = {"beta": _beta_model, "alpha": _alpha_model}


def event_probabilities(model: str, params: Any, member_qt: Sequence[float]) -> GroupExpansion:
    """The ONE place where a group's probabilities are computed (PLAN 4).

    ``model`` selects the formula (:data:`MODELS`), ``params`` holds its
    parameters (``beta``; ``alpha`` and ``testing``), ``member_qt`` the total
    probability ``Q_t`` of each member. The compile-time expansion and the
    Monte Carlo trial both call this function. See :func:`_beta_model` and
    :func:`_alpha_model` for the formulas and their sources.
    """
    try:
        function = MODELS[model]
    except (KeyError, TypeError):
        raise ValueError("CCF model %r is not available" % (model,))
    return function(params, member_qt)


def event_id(group_id: str, model: str, member_ids: Sequence[str],
             member_indexes: Sequence[int]) -> str:
    """The id of a CCF event: ``ccf:<groupId>`` for the beta model (one event
    per group); the alpha model has one event per member subset and adds the
    members it spans (``ccf:<gid>:<m1>+<m2>``, members in group order).

    The ids are joined with ``+`` and ``:``, so a group or member id that
    contains either could make two events share an id; ``assess`` refuses such
    groups (``CCF_BAD_PARAMETER``, kind ``event_id``)."""
    if model == "beta":
        return "ccf:%s" % group_id
    return "ccf:%s:%s" % (group_id, "+".join(member_ids[i] for i in member_indexes))


# ---- the expansion plan (FN-19) -------------------------------------------------------


class RuntimeGroup:
    """An applied group, ready to expand. ``events`` is a list of
    ``(event id, member positions, q)``; ``qts`` the members' Q_t;
    ``member_names`` their names in the tree (they name the subset events of an
    alpha group)."""

    __slots__ = ("id", "name", "model", "members", "qts", "expansion", "events", "params",
                 "member_names")

    def __init__(self, gid: str, name: str, model: str, members: List[str],
                 qts: List[float], expansion: GroupExpansion,
                 events: List[Tuple[str, Tuple[int, ...], float]],
                 params: Optional[Dict[str, Any]] = None,
                 member_names: Optional[List[str]] = None):
        self.id = gid
        self.name = name
        self.model = model
        self.members = members
        self.qts = qts
        self.expansion = expansion
        self.events = events
        #: The model parameters (``beta``, ``alpha``, ``testing``) that
        #: ``event_probabilities`` needs; Monte Carlo calls it again per trial (FN-24).
        self.params = params if params is not None else {}
        self.member_names = member_names if member_names is not None else list(members)


class Plan:
    """The judgement of every stored group and the expansion of the applied
    ones. ``by_member`` maps a member id to ``(RuntimeGroup, position)``."""

    def __init__(self, assessments: List[GroupAssessment], groups: List[RuntimeGroup],
                 by_member: Dict[str, Tuple[RuntimeGroup, int]]):
        self.assessments = assessments
        self.groups = groups
        self.by_member = by_member


def _node_q(node: Dict[str, Any]) -> float:
    """A node's probability as ``logic.Structure.var`` reads it (NaN -> 0)."""
    try:
        q = float(node.get("probability", 0.0))
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if math.isnan(q) else q


def build_plan(raw_groups: Any, renamed: Any, tree: Any, analysis: Any) -> Optional[Plan]:
    """Assess the stored groups and compute the expansion of those applied.

    ``raw_groups`` and ``renamed`` (the loader's ``_ccfRenamed`` map) are the
    RAW values read from the document's analysis before ``coerce_analysis``
    dropped them; ``tree`` is the recalculated tree, ``analysis`` the coerced
    settings (mission time). None when there is no group at all, so a
    document without groups takes the 1.8.1 path. A group that is not
    applied is in ``assessments`` only: the structure ignores it (FN-19).
    """
    entries = list(raw_groups) if isinstance(raw_groups, list) else []
    if not entries:
        return None
    merged = dict(analysis) if isinstance(analysis, dict) else {}
    if isinstance(renamed, dict) and renamed:
        merged[RENAMED_KEY] = renamed
    view = _TreeView(tree)
    assessments = assess(entries, tree, merged, "FTA", view)
    groups: List[RuntimeGroup] = []
    by_member: Dict[str, Tuple[RuntimeGroup, int]] = {}
    for raw, assessment in zip(entries, assessments):
        if not assessment.applied or not isinstance(raw, dict):
            continue
        ids = list(assessment.members)
        qts = [_node_q(view.index[m]) for m in ids]
        params = {key: raw.get(key) for key in ("beta", "alpha", "testing")}
        expansion = event_probabilities(assessment.model, params, qts)
        events = [(event_id(assessment.id, assessment.model, ids, idxs), idxs, q)
                  for idxs, q in expansion.events]
        group = RuntimeGroup(assessment.id, assessment.name, assessment.model, ids, qts,
                             expansion, events, params, [view.name(m) for m in ids])
        groups.append(group)
        for position, member in enumerate(ids):
            by_member[member] = (group, position)
    return Plan(assessments, groups, by_member)


def any_applied(tree: Any, analysis: Any, mode: str = "FTA") -> bool:
    """True when the document has a group that is applied (FN-21 selects the
    headline method on this, not on the mere presence of a group)."""
    groups = groups_of(analysis)
    if not groups:
        return False
    return any(a.applied for a in assess(groups, tree, analysis, mode))


def diagram_members(tree: Any, analysis: Any) -> Dict[str, Tuple[float, float]]:
    """``{member id: (Q_t, independent part)}`` for the members of the applied
    groups, for the member boxes of the diagram (FN-22). ``tree`` carries the
    recalculated probabilities (a document's own tree does)."""
    groups = groups_of(analysis)
    if not groups:
        return {}
    renamed = analysis.get(RENAMED_KEY) if isinstance(analysis, dict) else None
    plan = build_plan(groups, renamed, tree, analysis)
    out: Dict[str, Tuple[float, float]] = {}
    if plan is not None:
        for group in plan.groups:
            for position, member in enumerate(group.members):
                out[member] = (group.qts[position], group.expansion.independent[position])
    return out


def diagram_badges(tree: Any, analysis: Any) -> Dict[str, List[str]]:
    """``{member id: ["CCF: <group name>", ...]}`` for the member boxes of the
    diagram (UI-5, DESIGN 11.2). A group that is not applied reads
    ``CCF: <name> (off)``, so a box never suggests a CCF effect that the numbers
    do not have. Plain ASCII text in both languages (the diagram's convention).
    Empty for a document without groups, so its diagram is unchanged (FN-28)."""
    groups = groups_of(analysis)
    if not groups:
        return {}
    out: Dict[str, List[str]] = {}
    for group, assessment in zip(groups, assess(groups, tree, analysis, "FTA")):
        if not isinstance(group, dict):
            continue
        label = "CCF: %s%s" % (assessment.name, "" if assessment.applied else " (off)")
        for member in member_ids(group):
            out.setdefault(member, []).append(label)
    return out


# ---- gate values: the MCUB of the cut sets, never the tree walk (FN-66) -----------------

#: The text shown instead of a number when the cut sets are incomplete.
NA_TEXT = "n/a (CCF)"


def na_gates(structure: Any) -> Dict[str, Dict[str, str]]:
    """``{node id: {"method": "na"}}`` for every gate above a CCF member (a leaf
    with links counts as a gate, FN-66): the cut sets are incomplete, so no
    number is shown for them."""
    flags = getattr(structure, "ccf_flag", None) or []
    return {nid: {"method": "na"} for nid, op in structure.node_ops.items()
            if flags and flags[op]}


def gate_values(structure: Any, expander: Any, mcub: float) -> Dict[str, Dict[str, Any]]:
    """The min-cut upper bound of every gate whose subtree holds a CCF event. A
    gate is any node whose operator is not its own variable: it includes a leaf
    with links, a member leaf with links too (FN-66).

    ``expander`` is the ``cutsets._Expander`` that expanded ``structure``: its
    memo holds the cut sets of every reachable operator, so a gate's value
    costs one sort and one MCUB, not a second expansion (DESIGN D4). The top
    node uses ``mcub`` exactly (the headline's own number); a gate whose
    operator is not in the memo (unreachable) gets ``{"method": "na"}``,
    because the tree-walk value must never be shown for it. Call it after
    ``cutsets.compute`` has returned, so ``mcub`` is known.
    """
    try:
        from . import cutsets
    except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
        import cutsets  # type: ignore[no-redef]

    flags = getattr(structure, "ccf_flag", None) or []
    out: Dict[str, Dict[str, Any]] = {}
    if not flags:
        return out
    memo = expander.memo
    cache: Dict[int, Optional[float]] = {}
    for nid, op in structure.node_ops.items():
        if not flags[op]:
            continue
        if op == structure.top:
            out[nid] = {"method": "mcub", "value": mcub}
            continue
        if op not in cache:
            masks = memo.get(op)
            if masks is None:
                cache[op] = None
            else:
                prob = expander.prob
                ranked = sorted(masks, key=lambda m: (-prob(m), bin(m).count("1"), m))
                cache[op] = cutsets.mcub_of(prob(m) for m in ranked)
        value = cache[op]
        out[nid] = {"method": "na"} if value is None else {"method": "mcub", "value": value}
    return out


def substitute_gate_values(tree: Any, gates: Dict[str, Dict[str, Any]]) -> None:
    """In place on an export copy of ``tree``: a gate with a CCF value shows
    ``<v> (MCUB, CCF)`` or ``n/a (CCF)`` as its ``calculatedProbability`` text
    instead of the tree-walk number (the FTA sheet of the Excel export,
    FN-66). A gate is a node with children, a TRANSFER, or a leaf with links (a
    member leaf with links included); a bare member keeps its Q_t."""
    if not gates or not isinstance(tree, dict):
        return
    stack = [tree]
    while stack:
        node = stack.pop()
        children = [c for c in node.get("children") or [] if isinstance(c, dict)]
        stack.extend(children)
        gate = gates.get(str(node.get("id")))
        if gate is None or not (children or gate_type(node) == "TRANSFER"
                                or node.get("links")):
            continue
        if gate.get("method") == "mcub":
            node["calculatedProbability"] = "%r (MCUB, CCF)" % (float(gate["value"]),)
        else:
            node["calculatedProbability"] = NA_TEXT
