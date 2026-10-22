# Research R1: what release 1.8.1 must contain and pass (spec researcher, 2026-10-22)

Contents since v1.8.0 (9a2d8d3): CHANGELOG [Unreleased] "The known issues of 1.8.0" (PR #26). The UX merges #21-#25 are already in [1.8.0].
- Fixes: fixed port 8765 with fallback (59f4bfd); open/example/import refuse to replace unsaved work (df69e0f); batch move/delete under 1 s (b0a8466); AI Stop frees the slot (ca1444a); 1e-400 refused, -0 as 0 (9066346); Save As waits for the listing (cf898f6); 73a58ec, 51707a1 not named in the CHANGELOG.
- New: recovery copy in ~/.fta_editor/recovery (6e2002c); Change folder (aab9d3d).
- API: `force` on /api/file/open, /api/examples/open, /api/import/json; new /api/recovery (GET, restore, discard), /api/ai/cancel, /api/fs/root/choose; /api/fs/home gains canChooseRoot, relaunch.
- Release notes must name: port 8765, `force`, the recovery folder, Change folder, server-side Stop.

Procedure: version in pyproject.toml, uv.lock, report_docx.TOOL_VERSION, README badge, QUICKSTART (with date), .github/copilot-instructions.md, build/README --version example; CHANGELOG [Unreleased] -> [1.8.1]. Trap: test_known_issues_1_8.py:1882 indexes "## [Unreleased]" and must follow in the same commit. Exe built outside Dropbox (PyInstaller, CPython 3.14), launched once, full GUI suite with FTA_GUI_EXE. b2b: RELEASE_COMMIT defaults to 544492b (1.7.0) and the exe path to fta_build_170: set FTA_B2B_EXE and FTA_B2B_EXE_COMMIT explicitly.

Never verified: the native folder dialog (PowerShell from the frozen app, Japanese path round trip); recovery after a real kill of the exe; Ctrl-C cleanup; Firefox/WebKit only headless; AI only with a mock.

Risks: recovery-folder guard with a custom --root that contains home; two copies racing for 8765; 5 new endpoints in a patch release (1.9.0 would be more honest by semver).

Candidate requirements: R1 version bump + test fix (pytest green, --version prints 1.8.1); R2 release notes cover the 5 behaviour changes, new Known issues, SHA-256, not-tested list; R3 exe GUI suite 0 FAIL; R4 b2b against the new exe with explicit path/commit; R5 manual 3-item check by a person (Change folder incl. Japanese folder, kill-and-restore, preferences kept); R6 CI green, CEO merges and approves the release.
Open: 1.8.1 vs 1.9.0 (rec. 1.8.1, CEO's wording); who runs R5 (rec. Katey, via .bat); keep "No autosave" known issue reworded.
