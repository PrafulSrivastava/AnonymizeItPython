"""
DLT Scan Report Generator.

Produces three output formats from a ScanReport:

1. Terminal summary  (always printed)
2. JSON report file  (--output path.json)
3. HTML report file  (--html   path.html)

The legal-perspective section classifies the dataset risk level using the
following heuristic:

    SAFE     – review_rate == 0 % and pii_rate < 5 %
    LOW      – review_rate < 5 % or pii_rate < 20 %
    MEDIUM   – review_rate < 15 % or pii_rate < 50 %
    HIGH     – review_rate >= 15 % or pii_rate >= 50 %

  where:
    pii_rate    = entries_with_pii / parsed_entries
    review_rate = review_count / parsed_entries
"""

from __future__ import annotations

import json
import html as html_module
from typing import List

from lib.dlt.scanner import ScanReport, EntryResult


# ---------------------------------------------------------------------------
# Risk classification
# ---------------------------------------------------------------------------

def classify_risk(report: ScanReport) -> str:
    if report.parsed_entries == 0:
        return "UNKNOWN"
    pii_rate    = report.entries_with_pii / report.parsed_entries
    review_rate = report.review_count     / report.parsed_entries

    if review_rate == 0.0 and pii_rate < 0.05:
        return "SAFE"
    if review_rate < 0.05 or pii_rate < 0.20:
        return "LOW"
    if review_rate < 0.15 or pii_rate < 0.50:
        return "MEDIUM"
    return "HIGH"


_RISK_RECOMMENDATIONS = {
    "SAFE": [
        "Logs appear safe for production release.",
        "Maintain current anonymization controls and re-run scan after each build.",
    ],
    "LOW": [
        "A small fraction of log entries contain detectable PII.",
        "Review flagged entries before releasing logs externally.",
        "Consider adding the detected identifiers to the custom blocklist.",
    ],
    "MEDIUM": [
        "A significant proportion of log entries contain or may contain PII.",
        "Logs should NOT be released externally without further manual review.",
        "Engage a data-protection officer (DPO) before sharing these logs.",
        "Improve anonymization at the log-source level (reduce PII in log statements).",
    ],
    "HIGH": [
        "A high proportion of log entries contain PII – release is NOT recommended.",
        "Immediate action required: audit logging code and apply redaction at source.",
        "Under GDPR / CCPA these logs may qualify as personal data; legal review needed.",
        "Do not store or transmit these logs without explicit DPO sign-off.",
    ],
}


# ---------------------------------------------------------------------------
# Terminal summary
# ---------------------------------------------------------------------------

_RISK_COLOUR = {
    "SAFE":    "\033[92m",   # green
    "LOW":     "\033[93m",   # yellow
    "MEDIUM":  "\033[33m",   # dark yellow / orange
    "HIGH":    "\033[91m",   # red
    "UNKNOWN": "\033[90m",   # grey
}
_RESET = "\033[0m"


def print_summary(report: ScanReport, use_colour: bool = True):
    """Print a human-readable scan summary to stdout."""
    risk = classify_risk(report)
    colour  = _RISK_COLOUR.get(risk, "") if use_colour else ""
    nocolor = _RESET if use_colour else ""

    pii_pct    = (report.entries_with_pii / max(report.parsed_entries, 1)) * 100
    review_pct = (report.review_count     / max(report.parsed_entries, 1)) * 100

    width = 70
    sep   = "─" * width

    print(sep)
    print("  DLT Anonymization Scan Report")
    print(sep)
    print(f"  Scanned at        : {report.scanned_at}")
    print(f"  Source files      : {', '.join(report.source_files)}")
    if report.blocklist_terms:
        print(f"  Custom blocklist  : {', '.join(report.blocklist_terms)}")
    print(sep)
    print(f"  Total DLT entries : {report.total_entries:,}")
    print(f"  Scanned (w/ text) : {report.parsed_entries:,}")
    print(f"  Skipped (no text) : {report.skipped_entries:,}")
    if report.pipeline_errors:
        print(f"  Pipeline errors   : {report.pipeline_errors:,}  ← investigate")
    print(sep)
    print("  Routing breakdown")
    print(f"    ✔  pass          : {report.pass_count:,}")
    print(f"    ⚠  pass_flagged  : {report.pass_flagged_count:,}")
    print(f"    ✖  review needed : {report.review_count:,}  ({review_pct:.1f} %)")
    print(sep)
    print("  PII statistics")
    print(f"    Entries with PII : {report.entries_with_pii:,}  ({pii_pct:.1f} %)")
    if report.pii_type_counts:
        for ptype, cnt in sorted(report.pii_type_counts.items(), key=lambda x: -x[1]):
            print(f"      {ptype:<18}: {cnt:,}")
    print(f"    Avg confidence   : {report.avg_confidence:.3f}")
    print(f"    Min confidence   : {report.min_confidence:.3f}")
    print(sep)
    print("  ECU breakdown (top 10 by PII)")
    _print_breakdown(report.ecu_stats)
    print("  App-ID breakdown (top 10 by PII)")
    _print_breakdown(report.app_stats)
    print(sep)
    print(f"  {colour}Legal risk level  : {risk}{nocolor}")
    for rec in _RISK_RECOMMENDATIONS[risk]:
        print(f"    • {rec}")
    print(sep)
    print(f"  Elapsed           : {report.total_elapsed_s:.1f} s")
    print(sep)


def _print_breakdown(stats: dict, top: int = 10):
    if not stats:
        print("    (none)")
        return
    rows = sorted(stats.items(), key=lambda kv: -kv[1].get("pii", 0))
    for name, s in rows[:top]:
        pct = (s["pii"] / max(s["total"], 1)) * 100
        print(f"    {name:<8}  total={s['total']:>6,}  pii={s['pii']:>5,} ({pct:.0f} %)  review={s['review']:>4,}")


# ---------------------------------------------------------------------------
# JSON export
# ---------------------------------------------------------------------------

def _entry_result_to_dict(result: EntryResult) -> dict:
    entry = result.entry
    return {
        "index":       entry.index,
        "source_file": entry.source_file,
        "ecu_id":      entry.ecu_id,
        "app_id":      entry.app_id,
        "ctx_id":      entry.ctx_id,
        "log_level":   entry.log_level,
        "timestamp":   entry.timestamp,
        "payload":     entry.payload,
        "cleaned":     result.processed.cleanedText,
        "routing":     result.routing,
        "confidence":  round(result.confidence, 4),
        "pii_types":   result.pii_types,
        "tokens": [
            {
                "type":        t.type,
                "value":       t.value,
                "startIndex":  t.startIndex,
                "endIndex":    t.endIndex,
                "confidence":  round(t.confidence, 4),
            }
            for t in result.processed.tokens
        ],
        "failure_reasons": result.processed.confidence.failureReasons,
    }


def write_json_report(report: ScanReport, path: str):
    """Write a machine-readable JSON report to *path*."""
    risk = classify_risk(report)
    pii_rate    = report.entries_with_pii / max(report.parsed_entries, 1)
    review_rate = report.review_count     / max(report.parsed_entries, 1)

    data = {
        "meta": {
            "scanned_at":       report.scanned_at,
            "source_files":     report.source_files,
            "blocklist_terms":  report.blocklist_terms,
            "total_elapsed_s":  round(report.total_elapsed_s, 2),
        },
        "summary": {
            "total_entries":    report.total_entries,
            "parsed_entries":   report.parsed_entries,
            "skipped_entries":  report.skipped_entries,
            "pipeline_errors":  report.pipeline_errors,
            "pass_count":       report.pass_count,
            "pass_flagged":     report.pass_flagged_count,
            "review_count":     report.review_count,
            "entries_with_pii": report.entries_with_pii,
            "pii_rate":         round(pii_rate, 4),
            "review_rate":      round(review_rate, 4),
            "avg_confidence":   round(report.avg_confidence, 4),
            "min_confidence":   round(report.min_confidence, 4),
            "max_confidence":   round(report.max_confidence, 4),
        },
        "pii_type_counts": report.pii_type_counts,
        "ecu_stats":        report.ecu_stats,
        "app_stats":        report.app_stats,
        "legal": {
            "risk_level":        risk,
            "recommendations":   _RISK_RECOMMENDATIONS[risk],
        },
        "flagged_entries": [_entry_result_to_dict(r) for r in report.flagged_results],
    }

    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    print(f"JSON report written to: {path}")


# ---------------------------------------------------------------------------
# HTML export
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DLT Anonymization Scan Report</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg: #fafafa;
    --card: #ffffff;
    --text: #0f172a;
    --muted: #334155;
    --border: #e2e8f0;
    --accent: #14b8a6;
    --accent-light: rgba(20, 184, 166, 0.1);
    --accent-glow: rgba(20, 184, 166, 0.2);
    --dark-soft: #1e293b;
    --safe: #10b981;
    --low: #f59e0b;
    --medium: #f97316;
    --high: #ef4444;
    --radius: 16px;
    --shadow: 0 1px 3px rgba(15, 23, 42, 0.08);
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  @keyframes fadeInUp {{
    from {{ opacity: 0; transform: translateY(16px); }}
    to   {{ opacity: 1; transform: translateY(0); }}
  }}
  body {{
    font-family: 'Outfit', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    font-size: 14px;
    line-height: 1.5;
  }}

  /* ── Page header ── */
  .page-header {{
    background: #0f172a;
    color: #fff;
    padding: 20px 32px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 12px;
  }}
  .page-header h1 {{ font-size: 1.3rem; font-weight: 700; letter-spacing: -0.02em; }}
  .page-header .meta {{ font-size: 0.8rem; color: #94a3b8; margin-top: 4px; }}
  .page-header .meta strong {{ color: #fff; }}
  .page-header .meta code {{
    background: rgba(255,255,255,0.1);
    padding: 1px 7px; border-radius: 4px; font-size: 0.78rem;
    font-family: 'IBM Plex Mono', monospace;
  }}
  .header-badge {{
    display: inline-flex; align-items: center;
    background: rgba(20, 184, 166, 0.18); color: #14b8a6;
    padding: 4px 12px; border-radius: 100px;
    font-size: 0.67rem; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 8px;
  }}

  /* ── Risk pill ── */
  .risk-pill {{
    font-size: 0.8rem; font-weight: 700;
    padding: 6px 18px; border-radius: 100px;
    text-transform: uppercase; letter-spacing: 0.06em; white-space: nowrap;
  }}
  .risk-safe   {{ background: var(--safe);   color: #fff; }}
  .risk-low    {{ background: var(--low);    color: #fff; }}
  .risk-medium {{ background: var(--medium); color: #fff; }}
  .risk-high   {{ background: var(--high);   color: #fff; }}
  .risk-unknown {{ background: #718096;      color: #fff; }}

  /* ── Layout ── */
  .main {{ max-width: 1320px; margin: 0 auto; padding: 28px 24px; animation: fadeInUp 0.5s ease-out; }}
  .section-label {{
    font-size: 0.68rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.1em; color: var(--accent);
    margin: 28px 0 10px;
  }}
  .section-label:first-child {{ margin-top: 0; }}

  /* ── Card ── */
  .card {{
    background: var(--card);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
    border: 1px solid rgba(15, 23, 42, 0.06);
    padding: 20px 24px;
    margin-bottom: 0;
    transition: box-shadow 0.2s ease, border-color 0.2s ease;
  }}
  .card:hover {{
    box-shadow: 0 4px 16px rgba(15, 23, 42, 0.1);
    border-color: rgba(20, 184, 166, 0.25);
  }}
  .card-title {{
    font-size: 0.95rem; font-weight: 600; color: var(--text); margin-bottom: 14px;
  }}

  /* ── Risk card ── */
  .risk-card {{ border-left: 5px solid var(--medium); }}
  .risk-card.risk-safe   {{ border-color: var(--safe); }}
  .risk-card.risk-low    {{ border-color: var(--low); }}
  .risk-card.risk-medium {{ border-color: var(--medium); }}
  .risk-card.risk-high   {{ border-color: var(--high); }}
  .risk-card .risk-header {{
    display: flex; align-items: center; gap: 12px; margin-bottom: 14px;
  }}
  .risk-card .risk-sub {{ font-size: 0.8rem; color: var(--muted); }}
  .recs {{ padding-left: 18px; }}
  .recs li {{ margin: 5px 0; color: #475569; font-size: 0.88rem; }}

  /* ── Stats grid ── */
  .stats-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
    gap: 10px;
  }}
  .stat-box {{
    background: var(--bg); border: 1px solid var(--border);
    border-radius: 12px; padding: 14px 10px; text-align: center;
    transition: border-color 0.2s ease;
  }}
  .stat-box:hover {{ border-color: var(--accent); }}
  .stat-num {{
    font-size: 1.7rem; font-weight: 700; line-height: 1; color: var(--text);
  }}
  .stat-num.green {{ color: var(--safe); }}
  .stat-num.amber {{ color: var(--low); }}
  .stat-num.red   {{ color: var(--high); }}
  .stat-lbl {{
    font-size: 0.68rem; color: var(--muted);
    margin-top: 5px; text-transform: uppercase; letter-spacing: 0.04em;
  }}

  /* ── Two-column ── */
  .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  @media (max-width: 760px) {{ .two-col {{ grid-template-columns: 1fr; }} }}

  /* ── Tables ── */
  table {{ border-collapse: collapse; width: 100%; font-size: 0.86em; }}
  thead th {{
    background: var(--bg); color: var(--muted);
    font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.06em;
    padding: 8px 10px; border-bottom: 1px solid var(--border); text-align: left;
    white-space: nowrap;
  }}
  tbody td {{
    padding: 8px 10px; border-bottom: 1px solid var(--border); vertical-align: middle;
  }}
  tbody tr:last-child td {{ border-bottom: none; }}
  tbody tr:hover td {{ background: var(--bg); }}

  /* ── Progress bar ── */
  .pbar-wrap {{ display: flex; align-items: center; gap: 7px; }}
  .pbar {{ flex: 1; height: 6px; background: #e2e8f0; border-radius: 4px; overflow: hidden; }}
  .pbar-fill {{ height: 100%; border-radius: 4px; }}
  .pbar-fill.green {{ background: linear-gradient(90deg, #10b981, #34d399); }}
  .pbar-fill.amber {{ background: linear-gradient(90deg, #f59e0b, #fbbf24); }}
  .pbar-fill.red   {{ background: linear-gradient(90deg, #ef4444, #f87171); }}
  .pbar-val {{ font-size: 0.75rem; color: var(--muted); min-width: 34px; text-align: right; }}

  /* ── PII bar chart ── */
  .pii-chart {{ display: flex; flex-direction: column; gap: 6px; }}
  .pii-row {{ display: flex; align-items: center; gap: 10px; }}
  .pii-label {{
    min-width: 80px; font-size: 0.78rem; font-family: 'IBM Plex Mono', monospace;
    font-weight: 600; color: #334155; text-align: right;
  }}
  .pii-bar {{ flex: 1; height: 20px; background: #e2e8f0; border-radius: 5px; overflow: hidden; }}
  .pii-bar-fill {{
    height: 100%; border-radius: 5px;
    background: linear-gradient(90deg, #14b8a6, #0d9488);
    display: flex; align-items: center; justify-content: flex-end; padding-right: 7px;
    min-width: 28px;
  }}
  .pii-bar-num {{ font-size: 0.7rem; font-weight: 700; color: #fff; }}
  .pii-total {{ font-size: 0.75rem; color: var(--muted); min-width: 24px; }}

  /* ── Chips ── */
  .chip {{
    display: inline-block; padding: 2px 8px; border-radius: 100px;
    font-size: 0.68rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.04em; white-space: nowrap;
  }}
  .chip-info    {{ background: var(--accent-light); color: var(--accent); }}
  .chip-warn    {{ background: #fffbeb; color: #b7791f; }}
  .chip-warning {{ background: #fffbeb; color: #b7791f; }}
  .chip-error   {{ background: #fff5f5; color: #c53030; }}
  .chip-debug   {{ background: #f0fff4; color: #276749; }}
  .chip-verbose {{ background: #faf5ff; color: #553c9a; }}
  .chip-pass         {{ background: #f0fff4; color: #276749; }}
  .chip-pass_flagged {{ background: #fffbeb; color: #b7791f; }}
  .chip-review       {{ background: #fff5f5; color: #c53030; }}
  .chip-pii {{
    background: var(--accent-light); color: var(--accent);
    font-size: 0.63rem; padding: 1px 6px; margin: 1px;
  }}

  /* ── Confidence mini-bar ── */
  .conf-wrap {{ display: flex; align-items: center; gap: 6px; white-space: nowrap; }}
  .conf-bar {{ width: 44px; height: 5px; background: #e2e8f0; border-radius: 3px; overflow: hidden; }}
  .conf-fill {{ height: 100%; border-radius: 3px; }}
  .conf-val {{ font-size: 0.78rem; font-variant-numeric: tabular-nums; }}

  /* ── Flagged entries ── */
  .flagged-controls {{
    display: flex; align-items: center; gap: 8px; margin-bottom: 14px; flex-wrap: wrap;
  }}
  .search-box {{
    flex: 1; min-width: 180px; padding: 7px 12px;
    border: 1px solid var(--border); border-radius: 8px;
    font-size: 0.85rem; outline: none; background: var(--bg);
    font-family: 'Outfit', sans-serif;
  }}
  .search-box:focus {{
    border-color: var(--accent); background: #fff;
    box-shadow: 0 0 0 3px var(--accent-light);
  }}
  .filter-btn {{
    padding: 6px 13px; border-radius: 8px; border: 1px solid var(--border);
    background: #fff; cursor: pointer; font-size: 0.75rem; font-weight: 600;
    color: var(--muted); transition: all 0.15s; font-family: 'Outfit', sans-serif;
  }}
  .filter-btn:hover {{ border-color: var(--accent); color: var(--accent); }}
  .filter-btn.active {{ background: var(--accent); color: #fff; border-color: var(--accent); }}
  .result-count {{ font-size: 0.75rem; color: var(--muted); margin-left: auto; white-space: nowrap; }}
  .table-wrap {{ overflow-x: auto; }}
  .payload-cell {{ max-width: 280px; }}
  .mono-text {{
    font-family: 'IBM Plex Mono', 'Consolas', 'Cascadia Code', 'SF Mono', monospace;
    font-size: 0.76rem; overflow: hidden; text-overflow: ellipsis;
    white-space: nowrap; max-width: 260px; cursor: pointer; display: block;
  }}
  .mono-text.orig {{ color: #334155; }}
  .mono-text.clean {{ color: var(--accent); }}
  .mono-text.expanded {{
    white-space: pre-wrap; word-break: break-all;
    overflow: visible; text-overflow: unset; max-width: none;
  }}
  .expand-hint {{ font-size: 0.65rem; color: #a0aec0; margin-top: 1px; }}

  /* ── Footer ── */
  .footer {{
    text-align: center; color: var(--muted); font-size: 0.72rem;
    padding: 28px 0 16px; border-top: 1px solid var(--border); margin-top: 32px;
  }}
  .footer span {{ color: var(--accent); font-weight: 600; }}
</style>
</head>
<body>

<header class="page-header">
  <div>
    <div class="header-badge">DLT Scanner</div>
    <h1>Anonymization Scan Report</h1>
    <div class="meta">
      Scanned at <strong>{scanned_at}</strong>
      &nbsp;&bull;&nbsp; Source: <code>{source_files}</code>
      &nbsp;&bull;&nbsp; Elapsed: <strong>{elapsed_s:.1f} s</strong>
    </div>
  </div>
  <span class="risk-pill risk-{risk_level_lower}">{risk_level}</span>
</header>

<div class="main">

  <!-- Risk Assessment -->
  <div class="section-label">Risk Assessment</div>
  <div class="card risk-card risk-{risk_level_lower}">
    <div class="risk-header">
      <span class="risk-pill risk-{risk_level_lower}">{risk_level}</span>
      <span class="risk-sub">Legal / Compliance Risk Level</span>
    </div>
    <ul class="recs">{recommendations}</ul>
  </div>

  <!-- Summary -->
  <div class="section-label">Scan Summary</div>
  <div class="card">
    <div class="stats-grid">
      <div class="stat-box">
        <div class="stat-num">{total_entries}</div>
        <div class="stat-lbl">Total Entries</div>
      </div>
      <div class="stat-box">
        <div class="stat-num">{parsed_entries}</div>
        <div class="stat-lbl">Scanned</div>
      </div>
      <div class="stat-box">
        <div class="stat-num">{skipped_entries}</div>
        <div class="stat-lbl">Skipped</div>
      </div>
      <div class="stat-box">
        <div class="stat-num green">{pass_count}</div>
        <div class="stat-lbl">Pass</div>
      </div>
      <div class="stat-box">
        <div class="stat-num amber">{pass_flagged_count}</div>
        <div class="stat-lbl">Pass (Flagged)</div>
      </div>
      <div class="stat-box">
        <div class="stat-num red">{review_count}</div>
        <div class="stat-lbl">Review Needed</div>
      </div>
      <div class="stat-box">
        <div class="stat-num red">{pii_pct:.1f}%</div>
        <div class="stat-lbl">Entries w/ PII</div>
      </div>
      <div class="stat-box">
        <div class="stat-num">{avg_confidence:.3f}</div>
        <div class="stat-lbl">Avg Confidence</div>
      </div>
    </div>
  </div>

  <!-- PII Distribution -->
  <div class="section-label">PII Type Distribution</div>
  <div class="card">{pii_chart}</div>

  <!-- ECU & App Breakdown -->
  <div class="section-label">Breakdown</div>
  <div class="two-col">
    <div class="card">
      <div class="card-title">ECU Breakdown</div>
      {ecu_table}
    </div>
    <div class="card">
      <div class="card-title">App-ID Breakdown</div>
      {app_table}
    </div>
  </div>

  <!-- Flagged Entries -->
  <div class="section-label">Flagged Entries</div>
  <div class="card">
    <div class="flagged-controls">
      <input class="search-box" id="entrySearch" type="search"
             placeholder="Search ECU, App, payload, PII type&#x2026;"
             oninput="filterTable()">
      <button class="filter-btn active" id="btn-all"         onclick="setFilter('all')">All ({flagged_count})</button>
      <button class="filter-btn"        id="btn-pass"        onclick="setFilter('pass')">Pass</button>
      <button class="filter-btn"        id="btn-pass_flagged" onclick="setFilter('pass_flagged')">Flagged</button>
      <button class="filter-btn"        id="btn-review"      onclick="setFilter('review')">Review</button>
      <span class="result-count" id="resultCount">{flagged_count} entries</span>
    </div>
    <div class="table-wrap">
      <table id="flaggedTable">
        <thead>
          <tr>
            <th>#</th><th>ECU</th><th>App</th><th>Ctx</th>
            <th>Level</th><th>Routing</th><th>Confidence</th>
            <th>PII Types</th><th>Original Payload</th><th>Cleaned</th>
          </tr>
        </thead>
        <tbody>
{flagged_rows}
        </tbody>
      </table>
    </div>
  </div>

</div><!-- /.main -->

<div class="footer">Generated by <span>AnonymizeIt</span> &bull; DLT Anonymization Scanner</div>

<script>
  var activeFilter = 'all';

  function setFilter(f) {{
    activeFilter = f;
    document.querySelectorAll('.filter-btn').forEach(function(b) {{
      b.classList.remove('active');
    }});
    var btn = document.getElementById('btn-' + f);
    if (btn) btn.classList.add('active');
    filterTable();
  }}

  function filterTable() {{
    var query = document.getElementById('entrySearch').value.toLowerCase();
    var rows = document.querySelectorAll('#flaggedTable tbody tr');
    var visible = 0;
    rows.forEach(function(row) {{
      var routing = row.getAttribute('data-routing') || '';
      var matchFilter = (activeFilter === 'all' || routing === activeFilter);
      var matchSearch = !query || row.textContent.toLowerCase().indexOf(query) !== -1;
      row.style.display = (matchFilter && matchSearch) ? '' : 'none';
      if (matchFilter && matchSearch) visible++;
    }});
    document.getElementById('resultCount').textContent = visible + ' entries';
  }}

  function toggleMono(el) {{
    el.classList.toggle('expanded');
    var hint = el.nextElementSibling;
    if (hint && hint.classList.contains('expand-hint')) {{
      hint.textContent = el.classList.contains('expanded') ? 'click to collapse' : 'click to expand';
    }}
  }}
</script>
</body>
</html>
"""


def _pct_bar(pct: float) -> str:
    color = "red" if pct >= 75 else ("amber" if pct >= 40 else "green")
    return (
        f"<div class='pbar-wrap'>"
        f"<div class='pbar'><div class='pbar-fill {color}' style='width:{pct:.0f}%'></div></div>"
        f"<span class='pbar-val'>{pct:.0f}%</span>"
        f"</div>"
    )


def _conf_color(conf: float) -> str:
    if conf >= 0.85:
        return "#10b981"
    if conf >= 0.70:
        return "#f59e0b"
    return "#ef4444"


def _breakdown_table(stats: dict) -> str:
    if not stats:
        return "<p style='color:#a0aec0;font-size:0.85rem'>No data.</p>"
    rows = sorted(stats.items(), key=lambda kv: -kv[1].get("pii", 0))
    html = [
        "<table><thead><tr>"
        "<th>ID</th><th>Total</th><th>PII %</th><th>PII</th><th>Review</th>"
        "</tr></thead><tbody>"
    ]
    for name, s in rows:
        pct = (s["pii"] / max(s["total"], 1)) * 100
        html.append(
            f"<tr>"
            f"<td><code style='font-size:0.8rem'>{html_module.escape(name)}</code></td>"
            f"<td>{s['total']:,}</td>"
            f"<td>{_pct_bar(pct)}</td>"
            f"<td>{s['pii']:,}</td>"
            f"<td>{s['review']:,}</td>"
            f"</tr>"
        )
    html.append("</tbody></table>")
    return "\n".join(html)


def _pii_type_chart(counts: dict) -> str:
    if not counts:
        return "<p style='color:#a0aec0;font-size:0.85rem'>No PII detected.</p>"
    rows = sorted(counts.items(), key=lambda kv: -kv[1])
    max_cnt = rows[0][1] if rows else 1
    html = ['<div class="pii-chart">']
    for ptype, cnt in rows:
        pct = (cnt / max_cnt) * 100
        html.append(
            f"<div class='pii-row'>"
            f"<span class='pii-label'>{html_module.escape(ptype)}</span>"
            f"<div class='pii-bar'>"
            f"<div class='pii-bar-fill' style='width:{pct:.0f}%'>"
            f"<span class='pii-bar-num'>{cnt}</span>"
            f"</div></div>"
            f"</div>"
        )
    html.append("</div>")
    return "\n".join(html)


def _flagged_rows(results: List[EntryResult]) -> str:
    if not results:
        return (
            "<tr><td colspan='10' style='text-align:center;color:#a0aec0;"
            "padding:28px;font-size:0.85rem'>No flagged entries</td></tr>"
        )
    html = []
    for r in results:
        e = r.entry
        level_cls   = f"chip-{e.log_level.lower()}"
        routing_cls = f"chip-{r.routing}"
        conf_col    = _conf_color(r.confidence)
        conf_pct    = int(r.confidence * 100)
        pii_chips   = "".join(
            f"<span class='chip chip-pii'>{html_module.escape(p)}</span>"
            for p in r.pii_types
        )
        conf_html = (
            f"<div class='conf-wrap'>"
            f"<div class='conf-bar'>"
            f"<div class='conf-fill' style='width:{conf_pct}%;background:{conf_col}'></div>"
            f"</div>"
            f"<span class='conf-val'>{r.confidence:.2f}</span>"
            f"</div>"
        )
        html.append(
            f"          <tr data-routing='{r.routing}'>"
            f"<td style='color:var(--muted);font-size:0.78rem'>{e.index}</td>"
            f"<td><code style='font-size:0.8rem'>{html_module.escape(e.ecu_id)}</code></td>"
            f"<td><code style='font-size:0.8rem'>{html_module.escape(e.app_id)}</code></td>"
            f"<td style='color:var(--muted);font-size:0.75rem'>{html_module.escape(e.ctx_id)}</td>"
            f"<td><span class='chip {level_cls}'>{html_module.escape(e.log_level)}</span></td>"
            f"<td><span class='chip {routing_cls}'>{r.routing}</span></td>"
            f"<td>{conf_html}</td>"
            f"<td style='white-space:nowrap'>{pii_chips}</td>"
            f"<td class='payload-cell'>"
            f"<span class='mono-text orig' onclick='toggleMono(this)'>"
            f"{html_module.escape(e.payload)}</span>"
            f"<div class='expand-hint'>click to expand</div>"
            f"</td>"
            f"<td class='payload-cell'>"
            f"<span class='mono-text clean' onclick='toggleMono(this)'>"
            f"{html_module.escape(r.processed.cleanedText)}</span>"
            f"<div class='expand-hint'>click to expand</div>"
            f"</td>"
            f"</tr>"
        )
    return "\n".join(html)


def write_html_report(report: ScanReport, path: str):
    """Write an HTML anonymization report to *path*."""
    risk    = classify_risk(report)
    pii_pct = (report.entries_with_pii / max(report.parsed_entries, 1)) * 100
    recs_html = "\n".join(
        f"      <li>{html_module.escape(r)}</li>"
        for r in _RISK_RECOMMENDATIONS[risk]
    )

    content = _HTML_TEMPLATE.format(
        scanned_at        = html_module.escape(report.scanned_at),
        source_files      = html_module.escape(", ".join(report.source_files)),
        elapsed_s         = report.total_elapsed_s,
        risk_level        = risk,
        risk_level_lower  = risk.lower(),
        recommendations   = recs_html,
        total_entries     = f"{report.total_entries:,}",
        parsed_entries    = f"{report.parsed_entries:,}",
        skipped_entries   = f"{report.skipped_entries:,}",
        pass_count        = f"{report.pass_count:,}",
        pass_flagged_count = f"{report.pass_flagged_count:,}",
        review_count      = f"{report.review_count:,}",
        pii_pct           = pii_pct,
        avg_confidence    = report.avg_confidence,
        pii_chart         = _pii_type_chart(report.pii_type_counts),
        ecu_table         = _breakdown_table(report.ecu_stats),
        app_table         = _breakdown_table(report.app_stats),
        flagged_count     = len(report.flagged_results),
        flagged_rows      = _flagged_rows(report.flagged_results),
    )

    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    print(f"HTML report written to: {path}")
