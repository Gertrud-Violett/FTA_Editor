#!/usr/bin/env python3
"""secret-scan.py [--staged] [PATH ...]

Looks for secrets (tokens, webhooks, keys) in text that is about to be committed. Standalone:
Python 3.10+, standard library only, no import of the division package, so install.sh can copy
it to ~/.claude/division/ and the pre-commit hook can run it in any repo (also on Windows).

  PATH ...    files, or folders scanned recursively (.git is skipped)
  --staged    every staged added/copied/modified/type-changed file (code, docs and .division/ alike), read from
              the git index (`git show :<path>`), i.e. exactly what a commit would record

Each finding is printed as `<path>:<line>: <kind>` (UTF-8 on stdout and stderr, whatever the console code page);
the value itself is never printed.
Binary files (a NUL byte in the first 8 KB) and files over 5 MB are skipped.
Exit status: 0 clean, 1 findings, 2 error (bad path, git failure, nothing to scan).
"""
import argparse
import os
import re
import subprocess
import sys
import threading

# (kind, regex). Keep this a superset of division/core.py SECRET_TEXT_RE (the runner's redaction
# regex); tests/test_secret_scan.py checks that.
PATTERNS = [
    ("slack-webhook", re.compile(r"https://hooks\.slack\.com/\S+")),
    ("slack-token", re.compile(r"xox[abpr]-[\w-]+")),
    ("github-token", re.compile(r"gh[pousr]_\w{20,}|github_pat_\w+")),
    ("anthropic-key", re.compile(r"sk-ant-[\w-]+")),
    ("aws-key-id", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY(?: BLOCK)?-----")),
    ("google-api-key", re.compile(r"AIza[0-9A-Za-z_-]{35}")),
]
MAX_BYTES = 5 * 1024 * 1024
BINARY_PROBE = 8192
HINT = "build test tokens by concatenation, or keep secrets out of the repo"


def scan_bytes(data: bytes, label: str) -> list[str]:
    """Findings (`label:line: kind`) in one file's content; none for binary or oversized content."""
    if len(data) > MAX_BYTES or b"\0" in data[:BINARY_PROBE]:
        return []
    found = []
    for n, line in enumerate(data.decode("utf-8", "replace").split("\n"), 1):
        for kind, rx in PATTERNS:
            if rx.search(line):
                found.append(f"{label}:{n}: {kind}")
    return found


def label_of(path: str) -> str:
    return path.replace(os.sep, "/")


def walk(root: str):
    """The files of a path: the file itself, or every file under a folder (not .git, not symlinks)."""
    if not os.path.isdir(root):
        yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d != ".git")
        for name in sorted(filenames):
            p = os.path.join(dirpath, name)
            if not os.path.islink(p):
                yield p


def scan_paths(paths: list[str], errors: list[str]) -> list[str]:
    found = []
    for root in paths:
        if not os.path.exists(root):
            errors.append(f"no such path: {root}")
            continue
        for p in walk(root):
            try:
                if os.path.getsize(p) > MAX_BYTES:
                    continue
                with open(p, "rb") as f:
                    data = f.read()
            except OSError as e:
                errors.append(f"cannot read {p}: {e.strerror}")
                continue
            found += scan_bytes(data, label_of(p))
    return found


def git(*args: str, data: bytes | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, input=data)


def git_error(what: str, r: subprocess.CompletedProcess) -> str:
    return f"{what} failed: " + (r.stderr.decode("utf-8", "replace").strip() or "unknown error")


def scan_staged(errors: list[str]) -> list[str]:
    """Every staged added/copied/modified/type-changed file, as the index holds it. Submodule entries are not
    files and are skipped; oversized blobs are skipped by their size, without reading them."""
    # --no-renames: a renamed file shows up as added, so edits made along with the rename are scanned.
    # T: a type change (a symlink replaced by a regular file) brings new content too.
    r = git("diff", "--cached", "--no-renames", "--name-only", "-z", "--diff-filter=ACMT", "--", ":(top)")
    if r.returncode != 0:
        errors.append(git_error("git diff --cached", r))
        return []
    names = [x.decode("utf-8", "surrogateescape") for x in r.stdout.split(b"\0") if x]
    if not names:
        return []
    top = git("rev-parse", "--show-toplevel")
    idx = git("-C", top.stdout.decode("utf-8", "surrogateescape").rstrip("\n"), "ls-files", "-s", "-z") \
        if top.returncode == 0 else top
    if idx.returncode != 0:
        errors.append(git_error("git ls-files --stage", idx))
        return []
    blobs = {}                                   # path -> object id, stage 0 regular files and symlinks
    for rec in idx.stdout.split(b"\0"):
        if not rec:
            continue
        meta, _, path = rec.partition(b"\t")
        mode, oid, stage = meta.decode().split(" ")
        if stage == "0" and mode != "160000":
            blobs[path.decode("utf-8", "surrogateescape")] = oid
    wanted = [(n, blobs[n]) for n in names if n in blobs]
    sizes = git("cat-file", "--batch-check", data="".join(oid + "\n" for _, oid in wanted).encode())
    if sizes.returncode != 0:
        errors.append(git_error("git cat-file --batch-check", sizes))
        return []
    size_of = {}
    for line in sizes.stdout.decode().splitlines():
        parts = line.split(" ")
        if len(parts) == 3 and parts[2].isdigit():
            size_of[parts[0]] = int(parts[2])
    names_of: dict[str, list[str]] = {}          # object id -> the staged paths with that content
    for name, oid in wanted:
        if oid not in size_of:
            errors.append(f"git cat-file: object for {name} is missing")
        elif size_of[oid] <= MAX_BYTES:
            names_of.setdefault(oid, []).append(name)
    return read_blobs(names_of, errors)


def read_blobs(names_of: dict[str, list[str]], errors: list[str]) -> list[str]:
    """Scan the blobs through one `git cat-file --batch` process (one process per file is slow on big
    commits). Each answer is `<oid> <type> <size>\\n<content>\\n`; only blobs within the size cap are asked for."""
    if not names_of:
        return []
    order = list(names_of)
    proc = subprocess.Popen(["git", "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)

    def feed():                                  # a writer thread: git's output must be read while we write
        try:
            proc.stdin.write("".join(o + "\n" for o in order).encode())
            proc.stdin.close()
        except OSError:
            pass
    writer = threading.Thread(target=feed, daemon=True)
    writer.start()
    found = []
    try:
        for oid in order:
            header = proc.stdout.readline().decode("utf-8", "replace").split()
            if len(header) != 3 or header[0] != oid or not header[2].isdigit():
                errors.append(f"git cat-file --batch: unexpected answer for {names_of[oid][0]}")
                break
            data = proc.stdout.read(int(header[2]))
            proc.stdout.read(1)                  # the newline after the content
            for name in names_of[oid]:
                found += scan_bytes(data, name)
    finally:
        proc.stdout.close()
        writer.join()
        err = proc.stderr.read()
        proc.stderr.close()
        if proc.wait() != 0:
            errors.append("git cat-file --batch failed: " + (err.decode("utf-8", "replace").strip() or "unknown error"))
    return found


def main(argv: list[str] | None = None) -> int:
    # UTF-8 whatever the console code page (cp932 on a Japanese Windows); an odd file name must not crash the report
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(prog="secret-scan.py", description="Scan files for secrets; prints path:line: kind.")
    ap.add_argument("--staged", action="store_true", help="scan every staged file in the git index")
    ap.add_argument("paths", nargs="*", metavar="PATH", help="files, or folders scanned recursively")
    args = ap.parse_args(argv)
    if not args.staged and not args.paths:
        ap.error("give --staged and/or at least one PATH")
    errors: list[str] = []
    found = scan_paths(args.paths, errors)
    if args.staged:
        found += scan_staged(errors)
    for line in found:
        print(line)
    for e in errors:
        print(f"secret-scan: {e}", file=sys.stderr)
    if found:
        print(f"secret-scan: {len(found)} possible secret(s) found; values are not shown", file=sys.stderr)
        print(f"secret-scan: {HINT}", file=sys.stderr)
        return 1
    return 2 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
