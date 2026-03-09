"""
scan_dlt.py – CLI tool to scan DLT log files for PII and produce
an anonymization-degree report suitable for legal review.

Usage
-----
  python scan_dlt.py <file_or_dir> [<file_or_dir> ...]
        [--blocklist "term1,term2"]
        [--output  report.json]
        [--html    report.html]
        [--sample  N]
        [--no-colour]
        [--only-flagged]

Examples
--------
  # Scan one text-exported DLT log, write HTML + JSON reports
  python scan_dlt.py logs/system.dlt.txt --html out/report.html --output out/report.json

  # Scan a binary .dlt file with custom blocklist
  python scan_dlt.py dump.dlt --blocklist "alice,bob,acme-corp"

  # Quick smoke test on a large file (first 500 entries)
  python scan_dlt.py big_dump.dlt --sample 500

  # Scan all .dlt and .txt files in a directory
  python scan_dlt.py logs/

Supported input formats
-----------------------
  • Binary .dlt files (AUTOSAR DLT storage-header format)
  • Text exports from DLT Viewer (.txt / .csv / .log)
    – DLT Viewer 2.x default export
    – Wall-clock-prefixed variant (some older exporters)
    – Minimal legacy format

Exit codes
----------
  0   SAFE or LOW risk
  1   MEDIUM risk
  2   HIGH risk
  3   Scan error / no entries found
"""

from __future__ import annotations

import argparse
import os
import sys
import glob


def _collect_paths(args_paths: list[str]) -> list[str]:
    """Expand directories and glob patterns; return sorted unique file paths."""
    collected = []
    for p in args_paths:
        if os.path.isdir(p):
            # Collect common DLT-related file extensions
            for ext in ("*.dlt", "*.txt", "*.log", "*.csv"):
                collected.extend(glob.glob(os.path.join(p, "**", ext), recursive=True))
        elif os.path.isfile(p):
            collected.append(p)
        else:
            # Try treating as a glob
            matches = glob.glob(p, recursive=True)
            if matches:
                collected.extend(matches)
            else:
                print(f"[WARN] Path not found: {p}", file=sys.stderr)

    # Deduplicate and sort
    seen = set()
    result = []
    for path in sorted(collected):
        real = os.path.realpath(path)
        if real not in seen:
            seen.add(real)
            result.append(path)
    return result


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="scan_dlt",
        description="Scan DLT log files for residual PII and produce a legal-grade anonymization report.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "paths",
        nargs="+",
        metavar="FILE_OR_DIR",
        help="DLT file(s) or directory to scan. Binary .dlt and text exports accepted.",
    )
    p.add_argument(
        "--blocklist",
        default="",
        metavar="TERMS",
        help='Comma-separated custom terms to treat as PII, e.g. "alice,project-x".',
    )
    p.add_argument(
        "--output",
        default="",
        metavar="PATH",
        help="Write machine-readable JSON report to PATH.",
    )
    p.add_argument(
        "--html",
        default="",
        metavar="PATH",
        help="Write human-readable HTML report to PATH.",
    )
    p.add_argument(
        "--sample",
        type=int,
        default=0,
        metavar="N",
        help="Stop after processing N entries (0 = unlimited).",
    )
    p.add_argument(
        "--no-colour",
        action="store_true",
        help="Disable ANSI colour codes in terminal output.",
    )
    p.add_argument(
        "--only-flagged",
        action="store_true",
        help="In the JSON / HTML reports include only flagged entries (pass_flagged or review).",
    )
    p.add_argument(
        "--include-control",
        action="store_true",
        help="Also scan DLT control / network-trace messages (skipped by default).",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-entry progress to stderr.",
    )
    return p


def main(argv: list[str] | None = None):
    parser = _build_parser()
    args   = parser.parse_args(argv)

    # Collect files
    paths = _collect_paths(args.paths)
    if not paths:
        print("ERROR: No files found to scan.", file=sys.stderr)
        sys.exit(3)

    print(f"Files to scan: {len(paths)}")
    for p in paths:
        print(f"  {p}")
    print()

    # Progress callback (only when --verbose)
    def _progress(done: int, total: int):
        print(f"\r  Processed {done:,} entries …", end="", file=sys.stderr, flush=True)

    progress_cb = _progress if args.verbose else None

    # Import here so that model loading (spaCy / Presidio) only happens when
    # the user actually runs the scanner, not on import.
    from lib.dlt.scanner  import DltScanner
    from lib.dlt.reporter import print_summary, write_json_report, write_html_report, classify_risk

    print("Loading NLP models … (first run may take 10-30 s)")
    scanner = DltScanner(
        blocklist=args.blocklist,
        sample_size=args.sample,
        skip_control=not args.include_control,
        progress_callback=progress_cb,
    )

    report = scanner.scan_files(paths)

    if args.verbose:
        print(file=sys.stderr)  # newline after progress line

    if report.parsed_entries == 0:
        print("WARNING: No scannable entries found. Check that the file format is supported.")
        sys.exit(3)

    # Terminal summary
    print_summary(report, use_colour=not args.no_colour)

    # JSON report
    if args.output:
        if args.only_flagged:
            # Already filtered – flagged_results already contains only flagged entries
            pass
        write_json_report(report, args.output)

    # HTML report
    if args.html:
        write_html_report(report, args.html)

    # Exit code based on risk
    risk = classify_risk(report)
    if risk in ("SAFE", "LOW"):
        sys.exit(0)
    elif risk == "MEDIUM":
        sys.exit(1)
    else:
        sys.exit(2)


if __name__ == "__main__":
    main()
