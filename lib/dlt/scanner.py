"""
DLT Batch Scanner.

Iterates over a set of DLT log entries, runs each payload through the
anonymization pipeline, and collects per-entry results plus aggregate
statistics used by the reporter.
"""

from __future__ import annotations

import os
import re
import sys
import time
import datetime
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Iterator

from lib.dlt.parser import DltEntry, parse_file
from lib.types import PipelineInput, ProcessedMessage
from lib.pipeline.index import run_pipeline


# ---------------------------------------------------------------------------
# Per-entry result
# ---------------------------------------------------------------------------

@dataclass
class EntryResult:
    """Scan result for a single DLT log entry."""
    entry: DltEntry
    processed: ProcessedMessage
    has_pii: bool                          # any token found
    pii_types: List[str]                   # deduplicated list of token types
    routing: str                           # pass / pass_flagged / review
    confidence: float
    elapsed_ms: float


# ---------------------------------------------------------------------------
# Aggregate report model
# ---------------------------------------------------------------------------

@dataclass
class ScanReport:
    """Aggregate report for a full scan run."""

    # Run metadata
    scanned_at: str = ""
    source_files: List[str] = field(default_factory=list)
    blocklist_terms: List[str] = field(default_factory=list)

    # Counters
    total_entries: int = 0
    parsed_entries: int = 0          # entries with non-empty payloads
    skipped_entries: int = 0         # empty payloads (no text to check)
    pipeline_errors: int = 0

    # Routing summary
    pass_count: int = 0
    pass_flagged_count: int = 0
    review_count: int = 0

    # PII statistics
    entries_with_pii: int = 0
    pii_type_counts: Dict[str, int] = field(default_factory=dict)

    # Confidence distribution
    avg_confidence: float = 0.0
    min_confidence: float = 1.0
    max_confidence: float = 0.0

    # Per-ECU / per-App breakdown
    ecu_stats: Dict[str, Dict] = field(default_factory=dict)
    app_stats: Dict[str, Dict] = field(default_factory=dict)

    # Entries that need attention
    flagged_results: List[EntryResult] = field(default_factory=list)

    # Timing
    total_elapsed_s: float = 0.0


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

class DltScanner:
    """
    Scan DLT log files and produce a ScanReport.

    Parameters
    ----------
    blocklist : str
        Comma-separated list of custom terms to treat as PII.
    sample_size : int, optional
        If > 0, stop after processing this many entries (useful for quick
        smoke-tests on large files).
    skip_control : bool
        When True (default) silently skip DLT control/app-trace messages that
        have no human-readable payload (e.g. [service(0), ok]).
    min_payload_len : int
        Payloads shorter than this (after stripping) are skipped.
    progress_callback : callable, optional
        Called with (processed_count, total_so_far) after each entry if provided.
    """

    def __init__(
        self,
        blocklist: str = "",
        sample_size: int = 0,
        skip_control: bool = True,
        min_payload_len: int = 3,
        progress_callback=None,
    ):
        self.blocklist = blocklist
        self.sample_size = sample_size
        self.skip_control = skip_control
        self.min_payload_len = min_payload_len
        self.progress_callback = progress_callback

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _should_skip(self, entry: DltEntry) -> bool:
        """Return True if this entry is not worth scanning for PII."""
        if not entry.payload or len(entry.payload.strip()) < self.min_payload_len:
            return True
        if self.skip_control and entry.message_type in ("control", "network_trace", "app_trace"):
            return True
        # Entries that are purely hex (binary dump) – no textual PII possible
        if re.fullmatch(r"[0-9a-fA-F\s]+", entry.payload):
            return True
        # DLT internal service messages
        if entry.payload.startswith("[service(") or entry.payload.startswith("[getloginfo"):
            return True
        return False

    def _scan_entry(self, entry: DltEntry, session_id: str) -> EntryResult:
        """Run the pipeline on a single entry and return an EntryResult."""
        t0 = time.monotonic()
        pipeline_input = PipelineInput(
            rawText=entry.payload,
            blocklist=self.blocklist,
            sessionId=session_id,
        )
        processed = run_pipeline(pipeline_input)
        elapsed_ms = (time.monotonic() - t0) * 1000

        pii_types = list({t.type for t in processed.tokens})
        has_pii = len(pii_types) > 0
        routing = processed.confidence.routing
        confidence = processed.confidence.overall

        return EntryResult(
            entry=entry,
            processed=processed,
            has_pii=has_pii,
            pii_types=pii_types,
            routing=routing,
            confidence=confidence,
            elapsed_ms=elapsed_ms,
        )

    def _update_stats(self, report: ScanReport, result: EntryResult):
        """Accumulate per-entry result into the report."""
        report.parsed_entries += 1

        # Routing counters
        if result.routing == "pass":
            report.pass_count += 1
        elif result.routing == "pass_flagged":
            report.pass_flagged_count += 1
        else:
            report.review_count += 1

        # PII
        if result.has_pii:
            report.entries_with_pii += 1
            for ptype in result.pii_types:
                report.pii_type_counts[ptype] = report.pii_type_counts.get(ptype, 0) + 1

        # Confidence
        conf = result.confidence
        report.avg_confidence = (
            (report.avg_confidence * (report.parsed_entries - 1) + conf)
            / report.parsed_entries
        )
        if conf < report.min_confidence:
            report.min_confidence = conf
        if conf > report.max_confidence:
            report.max_confidence = conf

        # ECU breakdown
        ecu = result.entry.ecu_id or "UNKNOWN"
        if ecu not in report.ecu_stats:
            report.ecu_stats[ecu] = {"total": 0, "pii": 0, "review": 0}
        report.ecu_stats[ecu]["total"] += 1
        if result.has_pii:
            report.ecu_stats[ecu]["pii"] += 1
        if result.routing == "review":
            report.ecu_stats[ecu]["review"] += 1

        # App breakdown
        app = result.entry.app_id or "UNKNOWN"
        if app not in report.app_stats:
            report.app_stats[app] = {"total": 0, "pii": 0, "review": 0}
        report.app_stats[app]["total"] += 1
        if result.has_pii:
            report.app_stats[app]["pii"] += 1
        if result.routing == "review":
            report.app_stats[app]["review"] += 1

        # Collect flagged entries (pass_flagged or review, or has PII)
        if result.routing in ("pass_flagged", "review") or result.has_pii:
            report.flagged_results.append(result)

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def scan_file(self, path: str) -> ScanReport:
        """Scan a single DLT file and return a ScanReport."""
        return self.scan_files([path])

    def scan_files(self, paths: List[str]) -> ScanReport:
        """Scan one or more DLT files and return a combined ScanReport."""
        report = ScanReport(
            scanned_at=datetime.datetime.utcnow().isoformat() + "Z",
            source_files=paths,
            blocklist_terms=[t.strip() for t in self.blocklist.split(",") if t.strip()],
        )

        t_start = time.monotonic()
        processed_total = 0

        for path in paths:
            for entry in parse_file(path):
                report.total_entries += 1

                if self._should_skip(entry):
                    report.skipped_entries += 1
                    continue

                session_id = f"dlt_scan_{os.path.basename(path)}_{entry.index}"
                try:
                    result = self._scan_entry(entry, session_id)
                    self._update_stats(report, result)
                except Exception as exc:
                    report.pipeline_errors += 1
                    # Do not abort – log and continue
                    print(
                        f"[WARN] Pipeline error on entry {entry.index} "
                        f"in '{path}': {exc}",
                        file=sys.stderr,
                    )

                processed_total += 1
                if self.progress_callback:
                    self.progress_callback(processed_total, report.total_entries)

                if self.sample_size and processed_total >= self.sample_size:
                    break

            if self.sample_size and processed_total >= self.sample_size:
                break

        report.total_elapsed_s = time.monotonic() - t_start

        # Fix edge case: if nothing was processed, reset min to 0
        if report.parsed_entries == 0:
            report.min_confidence = 0.0

        return report
