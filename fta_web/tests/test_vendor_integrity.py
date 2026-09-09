"""
Vendor integrity guard for the fta_web fork of the FTA Editor core.

``fta_web/core/`` holds vendored copies of modules taken from ``src/`` at a
pinned baseline commit. Two things must stay true for that fork to remain
auditable:

1. ``src/`` is FROZEN -- it must never change while the fork is in flight.
2. Every intentional edit to ``fta_web/core/`` is recorded: the pin in
   ``BASELINE.json`` is refreshed and the reason is written up in
   ``DIVERGENCE.md``.

These tests enforce both, plus the manifest coverage that stops a newly added
``src/`` file from slipping past the freeze unnoticed.

The manifest is ``fta_web/core/BASELINE.json``:

    {
      "baseline_commit": "...",
      "vendored_at": "YYYY-MM-DD",
      "upstream":  {"src/<file>.py": "<sha256>", ...},
      "vendored":  {"fta_web/core/<file>.py": "<sha256>", ...},
      "divergences": ["D1", "D3", ...]
    }

Hashes are hex sha256 of the raw file bytes; paths are relative to the repo
root and use forward slashes.
"""
import hashlib
import json
import re
from pathlib import Path

import pytest

# fta_web/tests/test_vendor_integrity.py -> [0]=tests, [1]=fta_web, [2]=repo root
REPO_ROOT = Path(__file__).resolve().parents[2]
CORE_DIR = REPO_ROOT / "fta_web" / "core"
BASELINE_PATH = CORE_DIR / "BASELINE.json"
DIVERGENCE_PATH = CORE_DIR / "DIVERGENCE.md"
SRC_DIR = REPO_ROOT / "src"


def _load_baseline():
    """Return the parsed manifest, or None when it does not exist yet."""
    if not BASELINE_PATH.exists():
        return None
    with BASELINE_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


BASELINE = _load_baseline()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pairs(section: str):
    """Parametrization list of (relative path, pinned hash) for a manifest section."""
    if not BASELINE:
        return []
    return sorted((BASELINE.get(section) or {}).items())


def _divergence_ids():
    if not BASELINE:
        return []
    return list(BASELINE.get("divergences") or [])


def _src_py_files():
    """Every .py file actually present in src/, as repo-root-relative posix paths."""
    if not SRC_DIR.is_dir():
        return []
    return sorted(
        p.relative_to(REPO_ROOT).as_posix()
        for p in SRC_DIR.rglob("*.py")
        if "__pycache__" not in p.parts
    )


# --------------------------------------------------------------------------
# The manifest itself
# --------------------------------------------------------------------------

def test_baseline_manifest_exists():
    """
    BASELINE.json must exist. Without it every other check in this file
    degrades to a no-op and the fork is silently unauditable.
    """
    assert BASELINE_PATH.exists(), (
        f"Vendor manifest missing: {BASELINE_PATH}\n"
        "Without it the upstream freeze and the vendor pin cannot be verified, "
        "and this integrity suite is inert. It must be created alongside the "
        "vendored copies in fta_web/core/."
    )


def test_baseline_manifest_has_required_sections():
    """The manifest must carry the sections the rest of these tests read."""
    if not BASELINE:
        pytest.skip("BASELINE.json does not exist yet")

    for key in ("baseline_commit", "vendored_at", "upstream", "vendored", "divergences"):
        assert key in BASELINE, (
            f"BASELINE.json is missing the required '{key}' key. "
            f"Present keys: {sorted(BASELINE)}"
        )

    assert BASELINE["upstream"], "BASELINE.json 'upstream' map is empty"
    assert BASELINE["vendored"], "BASELINE.json 'vendored' map is empty"


# --------------------------------------------------------------------------
# 1. Upstream freeze
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "rel_path,pinned_hash", _pairs("upstream"), ids=lambda v: v if isinstance(v, str) else ""
)
def test_upstream_is_frozen(rel_path, pinned_hash):
    """
    Every upstream file must still hash to the value pinned at the baseline
    commit. src/ is frozen for the duration of this fork.
    """
    path = REPO_ROOT / rel_path

    assert path.exists(), (
        f"FROZEN TREE BROKEN: upstream file {rel_path} has been DELETED.\n"
        "src/ must not be modified while fta_web/core/ is vendored from it."
    )

    actual = _sha256(path)
    assert actual == pinned_hash, (
        f"FROZEN TREE BROKEN: src/ was MODIFIED.\n"
        f"  file:     {rel_path}\n"
        f"  expected: {pinned_hash}  (pinned at baseline commit "
        f"{BASELINE.get('baseline_commit', '?')})\n"
        f"  actual:   {actual}\n"
        "src/ is frozen for the duration of this fork. Revert the change to "
        "src/ -- do NOT re-pin the hash to make this pass. Fork-side changes "
        "belong in fta_web/core/."
    )


# --------------------------------------------------------------------------
# 2. Vendor pin
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "rel_path,pinned_hash", _pairs("vendored"), ids=lambda v: v if isinstance(v, str) else ""
)
def test_vendored_matches_pin(rel_path, pinned_hash):
    """
    Every vendored file must still hash to its pinned value. A mismatch means
    the fork was patched without recording the divergence.
    """
    path = REPO_ROOT / rel_path

    assert path.exists(), (
        f"VENDOR PIN BROKEN: vendored file {rel_path} has been DELETED "
        "but is still listed in BASELINE.json."
    )

    actual = _sha256(path)
    assert actual == pinned_hash, (
        f"VENDOR PIN BROKEN: the fork was patched without updating the pin.\n"
        f"  file:     {rel_path}\n"
        f"  expected: {pinned_hash}\n"
        f"  actual:   {actual}\n"
        "If this change is intentional: document it as a new divergence "
        f"(with a heading) in {DIVERGENCE_PATH.relative_to(REPO_ROOT)}, add its "
        "ID to the 'divergences' list, and update the hash in "
        "fta_web/core/BASELINE.json. If it is not intentional, revert it."
    )


# --------------------------------------------------------------------------
# 3. Divergence completeness
# --------------------------------------------------------------------------

@pytest.mark.parametrize("divergence_id", _divergence_ids())
def test_divergence_is_documented(divergence_id):
    """Every ID in the manifest must appear as a heading in DIVERGENCE.md."""
    assert DIVERGENCE_PATH.exists(), (
        f"DIVERGENCE.md missing: {DIVERGENCE_PATH}\n"
        f"BASELINE.json declares divergence {divergence_id!r} but there is no "
        "document to describe it."
    )

    text = DIVERGENCE_PATH.read_text(encoding="utf-8")
    headings = [
        m.group(1).strip()
        for m in re.finditer(r"^[ \t]{0,3}#{1,6}[ \t]+(.*)$", text, re.MULTILINE)
    ]

    # Word-boundary match so "D1" does not spuriously match "D10".
    token = re.compile(rf"(?<![A-Za-z0-9]){re.escape(divergence_id)}(?![A-Za-z0-9])")
    matching = [h for h in headings if token.search(h)]

    assert matching, (
        f"Divergence {divergence_id!r} is listed in BASELINE.json but has no "
        f"heading in {DIVERGENCE_PATH.relative_to(REPO_ROOT)}.\n"
        "Every declared divergence must be written up under its own heading so "
        "the fork stays auditable.\n"
        f"Headings found: {headings or '(none)'}"
    )


# --------------------------------------------------------------------------
# 4. Manifest coverage
# --------------------------------------------------------------------------

@pytest.mark.parametrize("rel_path", _src_py_files())
def test_src_file_is_covered_by_manifest(rel_path):
    """
    Every .py file present in src/ must appear in the upstream map, so a file
    added to src/ after the baseline cannot slip past the freeze unnoticed.
    """
    if not BASELINE:
        pytest.skip("BASELINE.json does not exist yet")

    upstream = BASELINE.get("upstream") or {}
    assert rel_path in upstream, (
        f"FREEZE COVERAGE GAP: {rel_path} exists in src/ but is not listed in "
        "the 'upstream' map of fta_web/core/BASELINE.json.\n"
        "An unlisted file is unprotected -- it could be added or edited without "
        "the freeze check noticing. Add it to the manifest with its sha256.\n"
        f"Currently pinned: {sorted(upstream)}"
    )


def test_manifest_lists_no_missing_src_files():
    """
    The upstream map must not reference src/ .py files that no longer exist.

    Scoped to src/*.py deliberately: the upstream map may also pin frozen
    non-src assets (e.g. data/examples/sampleFTA.json). Those are still
    hash-checked by test_upstream_is_frozen; they just are not enumerated by
    the src/ scan, so they must not be reported as stale here.
    """
    if not BASELINE:
        pytest.skip("BASELINE.json does not exist yet")

    present = set(_src_py_files())
    listed = {
        p
        for p in (BASELINE.get("upstream") or {})
        if p.startswith("src/") and p.endswith(".py")
    }
    stale = sorted(listed - present)

    assert not stale, (
        "FROZEN TREE BROKEN: BASELINE.json pins upstream files that are no "
        f"longer present in src/: {stale}\n"
        "src/ is frozen -- files must not be deleted or renamed."
    )
