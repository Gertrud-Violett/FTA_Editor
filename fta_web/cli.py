"""
Command-line batch interface (1.7).

    fta_editor <command> <files...> [options]
    python fta_web/run.py <command> <files...> [options]

``run.py`` hands any argv whose first word is in :data:`COMMANDS` to
:func:`main` before it builds the Flask app, so these never start a server or
open a browser.

Commands
--------
``quantify``    top-event probability (tree walk / MCUB / rare event) and the
                per-event q and calculated probability
``cutsets``     minimal cut sets, ranked
``importance``  FV, Birnbaum, RAW, RRW per basic event
``mc``          Monte Carlo uncertainty (mean, median, 5/95 %, std)
``validate``    the Validation tab's issues; exit 1 on errors (or on
                warnings with ``--strict``)
``report``      the DOCX report, written to ``--out`` (default:
                ``<input stem>_report.docx`` beside the input)

Exit codes: 0 ok, 1 validation errors / analysis failure, 2 usage error,
3 unreadable input file. With several inputs the highest code wins.
"""
from __future__ import annotations

import argparse
import copy
import csv
import glob
import io
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:  # normal package import: ``import fta_web.cli``
    from . import report_docx
    from .engine import AnalysisError, WebCore
    from .excel_events import event_row, iter_nodes, node_kind
    from .numfmt import clamp_sig_figs, format_prob
except ImportError:  # fallback: ``fta_web/`` itself is on sys.path (run.py, frozen)
    import report_docx  # type: ignore[no-redef]
    from engine import AnalysisError, WebCore  # type: ignore[no-redef]
    from excel_events import event_row, iter_nodes, node_kind  # type: ignore[no-redef]
    from numfmt import clamp_sig_figs, format_prob  # type: ignore[no-redef]

COMMANDS = ("quantify", "cutsets", "importance", "mc", "validate", "report")

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2
EXIT_UNREADABLE = 3

VERSION = report_docx.TOOL_VERSION


class UsageError(Exception):
    """Bad arguments discovered after parsing (exit 2)."""


class AnalysisFailure(Exception):
    """The analysis for one file could not run (exit 1)."""


def _prog() -> str:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).name
    return "fta_web/run.py"


# ---- argument parsing -----------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=_prog(),
        description="FTA Editor batch analysis. Without a command, the web UI starts.",
        epilog="Exit codes: 0 ok, 1 validation errors / analysis failure, "
               "2 usage error, 3 unreadable file.",
    )
    parser.add_argument("--version", action="version", version="FTA Editor %s" % VERSION)
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("files", nargs="+", metavar="FILE",
                        help="FTA JSON file(s); wildcards are expanded")
    fmt = common.add_mutually_exclusive_group()
    fmt.add_argument("--json", action="store_true", help="JSON output")
    fmt.add_argument("--csv", action="store_true", help="CSV output (one row per item)")
    common.add_argument("--out", metavar="PATH",
                        help="write output to PATH (a directory when several files are given)")
    common.add_argument("--sig-figs", type=int, default=3, metavar="N",
                        help="significant figures in tables (1-6, default 3)")
    common.add_argument("--mission-time", type=float, metavar="H",
                        help="override the document's mission time (hours)")

    limits = argparse.ArgumentParser(add_help=False)
    limits.add_argument("--max-order", type=int, metavar="N", help="cut-set order limit")
    limits.add_argument("--max-count", type=int, metavar="N", help="cut-set count limit")
    limits.add_argument("--cutoff", type=float, metavar="P", help="cut-set probability cutoff")

    mc = argparse.ArgumentParser(add_help=False)
    mc.add_argument("--n", type=int, metavar="N", help="Monte Carlo samples")
    mc.add_argument("--seed", type=int, metavar="S", help="random seed")
    mc.add_argument("--time-limit", type=float, default=30.0, metavar="SEC",
                    help="Monte Carlo time cap in seconds (default 30)")

    sub.add_parser("quantify", parents=[common], help="top-event and per-event probabilities")
    p = sub.add_parser("cutsets", parents=[common, limits], help="minimal cut sets")
    p.add_argument("--top", type=int, metavar="N", help="show only the N most probable")
    p = sub.add_parser("importance", parents=[common, limits], help="importance measures")
    p.add_argument("--top", type=int, metavar="N", help="show only the N most important")
    sub.add_parser("mc", parents=[common, mc], help="Monte Carlo uncertainty")
    p = sub.add_parser("validate", parents=[common], help="validation issues")
    p.add_argument("--strict", action="store_true", help="warnings also fail (exit 1)")
    p = sub.add_parser("report", parents=[common, limits, mc], help="DOCX report")
    p.add_argument("--sections", metavar="LIST",
                   help="comma-separated sections (default: all but uncertainty); "
                        "known: " + ",".join(report_docx.SECTIONS))
    p.add_argument("--lang", choices=("en", "ja"), default="en", help="report language")
    p.add_argument("--uncertainty", action="store_true",
                   help="run Monte Carlo (n capped at %d) and include it" % report_docx.MAX_REPORT_MC_N)
    return parser


def expand_files(patterns: Sequence[str]) -> List[str]:
    """Wildcards expanded (cmd.exe does not); a pattern with no match is kept
    literally so it is reported as unreadable."""
    out: List[str] = []
    for pattern in patterns:
        if any(ch in pattern for ch in "*?[") and not os.path.exists(pattern):
            matches = sorted(glob.glob(pattern))
            out.extend(matches or [pattern])
        else:
            out.append(pattern)
    return out


# ---- loading ---------------------------------------------------------------------


def load_core(path: str, args) -> WebCore:
    """A WebCore with ``path`` loaded and the CLI overrides applied.

    Raises OSError / ValueError for an unreadable file.
    """
    if not os.path.isfile(path):
        raise OSError("no such file: %s" % path)
    core = WebCore()
    ok, error = core.load_from_json(path)
    if not ok:
        raise ValueError(error or "unrecognised format")
    patch: Dict[str, Any] = {}
    if getattr(args, "mission_time", None) is not None:
        patch["missionTime"] = args.mission_time
    cut = {k: v for k, v in (("maxOrder", getattr(args, "max_order", None)),
                              ("maxCount", getattr(args, "max_count", None)),
                              ("cutoff", getattr(args, "cutoff", None))) if v is not None}
    if cut:
        patch["cutsets"] = cut
    mc = {k: v for k, v in (("n", getattr(args, "n", None)),
                             ("seed", getattr(args, "seed", None))) if v is not None}
    if mc:
        patch["mc"] = mc
    if patch:
        try:
            core.set_analysis(patch)
        except AnalysisError as exc:
            raise UsageError(str(exc))
        core.recalculate_probabilities()
    return core


def session_issues(core) -> List[Dict[str, Any]]:
    """Load repairs as Validation issues (the shape state.load_warning_issues builds)."""
    return [{
        "severity": "warning",
        "code": "LOAD_REPAIR",
        "nodeId": w.get("new_id"),
        "message": w.get("message", ""),
        "params": copy.deepcopy(w),
    } for w in getattr(core, "last_load_warnings", None) or []]


def _limits(core) -> Dict[str, Any]:
    return copy.deepcopy((core.analysis or {}).get("cutsets") or {})


def _require_fta(core, command: str) -> None:
    if (core.mode or "FTA") == "ETA":
        raise AnalysisFailure("'%s' applies to fault trees only; this file is in ETA mode." % command)


def _call(module: str, fn: str, *a: Any, **kw: Any) -> Any:
    result, reason = report_docx.try_call(module, fn, *a, **kw)
    if result is None:
        if reason == "unavailable":
            raise AnalysisFailure("%s.%s is not available in this build." % (module, fn))
        raise AnalysisFailure("%s.%s %s" % (module, fn, reason))
    return result


# ---- commands --------------------------------------------------------------------
# Each returns (results, rows, status): results for --json, rows (list of flat
# dicts) for --csv and the human table, status an exit code.


def cmd_quantify(core, args) -> Tuple[Dict[str, Any], List[Dict[str, Any]], int]:
    tree = copy.deepcopy(core.get_data())
    events = []
    for node, parent, depth in iter_nodes(tree):
        if node_kind(node) != "event":
            continue
        row = event_row(node, parent, depth)
        events.append({"id": row["Id"], "name": row["Name"], "model": row["Model"],
                       "q": row["Base probability"], "calculated": row["Calculated probability"]})
    if (core.mode or "FTA") == "ETA":
        summary = {"treeWalk": tree.get("calculatedProbability") if isinstance(tree, dict) else None}
        summary["headline"] = summary["treeWalk"]
        summary["headlineMethod"] = "treeWalk"
    else:
        summary = _call("engine", "summary", tree, copy.deepcopy(core.analysis))
    return {"summary": summary, "events": events}, events, EXIT_OK


def cmd_cutsets(core, args):
    _require_fta(core, "cutsets")
    result = _call("cutsets", "compute", copy.deepcopy(core.get_data()),
                   copy.deepcopy(core.analysis), _limits(core))
    rows = []
    cut_sets = list(result.get("cutSets") or [])
    if getattr(args, "top", None):
        cut_sets = cut_sets[: max(1, args.top)]
    for c in cut_sets:
        rows.append({
            "rank": c.get("rank"), "order": c.get("order"),
            "probability": c.get("probability"), "share": c.get("share"),
            "events": ";".join(str(e.get("id")) for e in c.get("events") or []),
            "names": ";".join(str(e.get("name", "")) for e in c.get("events") or []),
        })
    return result, rows, EXIT_OK


def cmd_importance(core, args):
    _require_fta(core, "importance")
    cut = _call("cutsets", "compute", copy.deepcopy(core.get_data()),
                copy.deepcopy(core.analysis), _limits(core))
    measures = list(_call("importance", "compute", cut))
    measures.sort(key=lambda m: -(m.get("fv") or 0.0))
    if getattr(args, "top", None):
        measures = measures[: max(1, args.top)]
    rows = [{k: m.get(k) for k in ("id", "name", "q", "fv", "birnbaum", "raw", "rrw", "cutSetCount")}
            for m in measures]
    return {"measures": measures}, rows, EXIT_OK


def cmd_mc(core, args):
    _require_fta(core, "mc")
    mc = (core.analysis or {}).get("mc") or {}
    result = _call("uncertainty", "run", copy.deepcopy(core.get_data()),
                   copy.deepcopy(core.analysis), n=mc.get("n"), seed=mc.get("seed"),
                   time_limit=args.time_limit)
    row = {k: result.get(k) for k in ("pointEstimate", "mean", "median", "p05", "p95", "std",
                                       "requested", "completed", "seed", "method")}
    return result, [row], EXIT_OK


def cmd_validate(core, args):
    tree = copy.deepcopy(core.get_data())
    warnings = session_issues(core)
    extra = None
    if (core.mode or "FTA") != "ETA":
        # Cut-set truncation under the document's limits (lint: CUTSETS_TRUNCATED).
        signal, _why = report_docx.try_call("cutsets", "truncation_signal", copy.deepcopy(tree),
                                            copy.deepcopy(core.analysis))
        if signal:
            extra = {"cutsets": signal}
    issues, reason = report_docx.try_call("lint", "run", tree, copy.deepcopy(core.analysis), warnings,
                                          mode=core.mode or "FTA", extra=extra)
    note = None
    if issues is None:
        if reason != "unavailable":
            raise AnalysisFailure("lint.run %s" % reason)
        # Lint has not landed in this build: report what the engine knows.
        note = "lint.run unavailable; showing load repairs and engine warnings only"
        issues = warnings + [{"severity": "warning", "code": w.get("code"), "nodeId": w.get("nodeId"),
                              "message": w.get("code"), "params": w.get("params")}
                             for w in core.quant_warnings]
    issues = [dict(i) for i in issues]
    counts = {"error": 0, "warning": 0, "info": 0}
    for issue in issues:
        sev = str(issue.get("severity") or "info")
        counts[sev] = counts.get(sev, 0) + 1
    status = EXIT_OK
    if counts.get("error") or (args.strict and counts.get("warning")):
        status = EXIT_FAIL
    rows = [{"severity": i.get("severity"), "code": i.get("code"), "nodeId": i.get("nodeId"),
             "nodeName": i.get("nodeName"), "message": i.get("message")} for i in issues]
    results: Dict[str, Any] = {"issues": issues, "counts": counts}
    if note:
        results["note"] = note
    return results, rows, status


def cmd_report(core, args, out_path: Path):
    try:
        import docx  # noqa: F401
    except ImportError:
        raise AnalysisFailure("the DOCX report needs python-docx: uv sync --extra report")
    sections = None
    if args.sections:
        sections = [s.strip() for s in args.sections.split(",") if s.strip()]
        unknown = [s for s in sections if s not in report_docx.SECTIONS]
        if unknown:
            raise UsageError("unknown section(s): %s" % ", ".join(unknown))
    elif args.uncertainty:
        sections = list(report_docx.DEFAULT_SECTIONS) + ["uncertainty"]
    options = report_docx.normalize_options({
        "sections": sections, "sigFigs": args.sig_figs, "lang": args.lang,
        "runUncertainty": bool(args.uncertainty), "limits": _limits(core),
        "uncertaintyN": args.n or report_docx.MAX_REPORT_MC_N,
    })
    if "diagram" in options["sections"]:
        options["diagramPng"] = report_docx.render_png(
            report_docx.diagram_dot_text(core, options["sigFigs"]))
    data = report_docx.collect_report_data(core, session_issues(core), options)
    blob = report_docx.build_report(data, options)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(blob)
    results = {"out": str(out_path), "bytes": len(blob),
               "unavailable": data.get("unavailable") or {},
               "diagram": bool(options.get("diagramPng"))}
    return results, [{"out": str(out_path), "bytes": len(blob)}], EXIT_OK


HANDLERS = {
    "quantify": cmd_quantify,
    "cutsets": cmd_cutsets,
    "importance": cmd_importance,
    "mc": cmd_mc,
    "validate": cmd_validate,
}


# ---- output ----------------------------------------------------------------------

_PROB_KEYS = {"q", "calculated", "probability", "share", "fv", "birnbaum", "raw", "rrw",
              "pointEstimate", "mean", "median", "p05", "p95", "std", "headline", "treeWalk",
              "mcub", "rareEvent"}


def _cell(key: str, value: Any, sf: int) -> str:
    if value is None:
        return "—"
    if key in _PROB_KEYS and isinstance(value, (int, float)) and not isinstance(value, bool):
        return format_prob(value, sf)
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def human_table(rows: List[Dict[str, Any]], sf: int) -> str:
    if not rows:
        return "(none)"
    headers = list(rows[0].keys())
    for row in rows[1:]:
        for key in row:
            if key not in headers:
                headers.append(key)
    cells = [[_cell(h, row.get(h), sf) for h in headers] for row in rows]
    widths = [max(len(h), *(len(c[i]) for c in cells)) for i, h in enumerate(headers)]
    numeric = [all(_looks_numeric(c[i]) for c in cells) for i in range(len(headers))]

    def line(values):
        return "  ".join(v.rjust(w) if num else v.ljust(w)
                         for v, w, num in zip(values, widths, numeric)).rstrip()

    out = [line(headers), line(["-" * w for w in widths])]
    out.extend(line(c) for c in cells)
    return "\n".join(out)


def _looks_numeric(text: str) -> bool:
    try:
        float(text)
        return True
    except ValueError:
        return text == "—"


def human_block(entry: Dict[str, Any], command: str, rows: List[Dict[str, Any]], sf: int) -> str:
    lines = ["== %s  [%s] %s" % (entry["file"], entry.get("mode") or "", entry.get("title") or "")]
    if "error" in entry:
        lines.append("error: %s" % entry["error"])
        return "\n".join(lines)
    res = entry.get("results") or {}
    if command == "quantify":
        s = res.get("summary") or {}
        lines.append("Top event: %s  (%s)" % (format_prob(s.get("headline"), sf),
                                              s.get("headlineMethod") or "treeWalk"))
        for key in ("treeWalk", "mcub", "rareEvent"):
            if s.get(key) is not None:
                lines.append("  %-10s %s" % (key, format_prob(s.get(key), sf)))
    elif command == "cutsets":
        lines.append("Cut sets: %s%s   MCUB %s   rare-event %s" % (
            res.get("total", len(rows)), " (truncated)" if res.get("truncated") else "",
            format_prob(res.get("mcub"), sf), format_prob(res.get("rareEvent"), sf)))
    elif command == "validate":
        c = res.get("counts") or {}
        lines.append("errors %d, warnings %d, info %d" % (c.get("error", 0), c.get("warning", 0),
                                                          c.get("info", 0)))
        if res.get("note"):
            lines.append("note: %s" % res["note"])
    elif command == "report":
        lines.append("wrote %s (%d bytes)" % (res.get("out"), res.get("bytes", 0)))
        return "\n".join(lines)
    lines.append(human_table(rows, sf))
    return "\n".join(lines)


def csv_text(entries: List[Tuple[Dict[str, Any], List[Dict[str, Any]]]]) -> str:
    headers: List[str] = ["file"]
    for _entry, rows in entries:
        for row in rows:
            for key in row:
                if key not in headers:
                    headers.append(key)
    if any("error" in entry for entry, _rows in entries) and "error" not in headers:
        headers.append("error")
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=headers, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for entry, rows in entries:
        if "error" in entry:
            writer.writerow({"file": entry["file"], "error": entry["error"]})
        for row in rows:
            writer.writerow(dict(row, file=entry["file"]))
    return buf.getvalue()


def _json_default(value: Any):
    if isinstance(value, (set, tuple)):
        return list(value)
    if isinstance(value, (bytes, bytearray)):
        return None
    return str(value)


def render_output(fmt: str, command: str, entries, sf: int) -> str:
    if fmt == "json":
        payload = [e for e, _rows in entries]
        body = payload[0] if len(payload) == 1 else payload
        return json.dumps(body, ensure_ascii=False, indent=2, default=_json_default) + "\n"
    if fmt == "csv":
        return csv_text(entries)
    return "\n\n".join(human_block(e, command, rows, sf) for e, rows in entries) + "\n"


# ---- main ----------------------------------------------------------------------------


def _force_utf8() -> None:
    """cp932 / cp1252 consoles must not crash on λ, τ or Japanese names."""
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")


def main(argv: Optional[Sequence[str]] = None) -> int:
    _force_utf8()
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # --help / --version (0) or a usage error (2)
        return int(exc.code or 0) if isinstance(exc.code, int) else EXIT_USAGE
    if not args.command:
        parser.print_help()
        return EXIT_USAGE
    command = args.command
    fmt = "json" if args.json else ("csv" if args.csv else "text")
    ext = {"json": ".json", "csv": ".csv", "text": ".txt"}[fmt]
    sf = clamp_sig_figs(args.sig_figs)
    files = expand_files(args.files)
    many = len(files) > 1

    out = Path(args.out) if args.out else None
    out_is_dir = out is not None and (out.is_dir() or str(args.out).endswith(("/", "\\")))
    if command == "report" and many and out is not None and not out_is_dir:
        print("error: --out must be a directory when several files are given", file=sys.stderr)
        return EXIT_USAGE

    entries: List[Tuple[Dict[str, Any], List[Dict[str, Any]]]] = []
    worst = EXIT_OK
    for path in files:
        entry: Dict[str, Any] = {"file": path, "title": None, "mode": None}
        rows: List[Dict[str, Any]] = []
        try:
            core = load_core(path, args)
        except UsageError as exc:
            print("error: %s" % exc, file=sys.stderr)
            return EXIT_USAGE
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            entry["error"] = "unreadable: %s" % exc
            print("error: %s: %s" % (path, exc), file=sys.stderr)
            worst = max(worst, EXIT_UNREADABLE)
            entries.append((entry, rows))
            continue
        meta = core.get_metadata()
        entry["title"], entry["mode"] = meta.get("title"), meta.get("mode")
        try:
            if command == "report":
                stem = Path(path).stem
                if out is None:
                    target = Path(path).with_name(stem + "_report.docx")
                elif out_is_dir:
                    target = out / (stem + "_report.docx")
                else:
                    target = out
                results, rows, status = cmd_report(core, args, target)
            else:
                results, rows, status = HANDLERS[command](core, args)
            entry["results"] = results
        except UsageError as exc:
            print("error: %s" % exc, file=sys.stderr)
            return EXIT_USAGE
        except AnalysisFailure as exc:
            entry["error"] = str(exc)
            print("error: %s: %s" % (path, exc), file=sys.stderr)
            status = EXIT_FAIL
        worst = max(worst, status)
        entries.append((entry, rows))

    if out is not None and command != "report":
        if many and out_is_dir:
            for entry, rows in entries:
                target = out / ("%s.%s%s" % (Path(entry["file"]).stem, command, ext))
                _write(target, render_output(fmt, command, [(entry, rows)], sf))
        else:
            target = out / ("%s.%s%s" % (Path(files[0]).stem, command, ext)) if out_is_dir else out
            _write(target, render_output(fmt, command, entries, sf))
    else:
        sys.stdout.write(render_output(fmt, command, entries, sf))
    sys.stdout.flush()
    return worst


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
