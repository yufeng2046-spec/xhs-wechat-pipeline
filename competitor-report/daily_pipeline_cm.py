#!/usr/bin/env python3
"""
Daily ToB Competitive Report Pipeline — CubeMini Edition
All steps run locally on CubeMini (no SSH needed).

Usage:
    python3 daily_pipeline_cm.py [--date 2026-05-20]

Scheduled via cron on CubeMini (5am Beijing time).
Steps 1-5: Scrape → Transcribe → Import → Report → Scripts
Steps 6-7: Moved to daily_distribution_pipeline.py (8:30am cron)
"""

import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"
REPORT_DIR = BASE_DIR / "reports"
SCRIPTS_DIR = BASE_DIR / "scripts"
DB_PATH = BASE_DIR / "douyin.db"

BEIJING_TZ = timezone(timedelta(hours=8))
PYTHON = "/home/frank/ai-content/venv/bin/python3"

# ── Script paths (all local) ────────────────────────────────────────────
SCRAPE_SCRIPT = BASE_DIR / "daily_scrape.py"
TRANSCRIBE_SCRIPT = BASE_DIR / "daily_transcribe_cm.py"
IMPORT_SCRIPT = BASE_DIR / "daily_import.py"
REPORT_SCRIPT = BASE_DIR / "competitor_report_crew.py"
CONTENT_SCRIPT = BASE_DIR / "content_planner.py"


def log(msg: str) -> None:
    ts = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def run_step(step_name: str, cmd: list[str], timeout: int = 3600) -> bool:
    log(f"=== {step_name} ===")
    log(f"  CMD: {' '.join(cmd)}")
    t0 = time.time()

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.stdout:
            for line in result.stdout.strip().splitlines():
                print(f"  {line}")
        if result.stderr:
            for line in result.stderr.strip().splitlines():
                print(f"  [stderr] {line}", file=sys.stderr)
        ok = result.returncode == 0
        elapsed = time.time() - t0
        log(f"  {'✓' if ok else '✗'} {step_name} [{elapsed:.0f}s]")
        return ok
    except subprocess.TimeoutExpired:
        log(f"  ✗ {step_name} timed out after {timeout}s")
        return False


def main():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

    date_str = None
    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == "--date" and i + 1 < len(sys.argv):
            date_str = sys.argv[i + 1]
            i += 2
        else:
            i += 1

    if not date_str:
        date_str = (datetime.now(BEIJING_TZ) - timedelta(days=1)).strftime("%Y-%m-%d")

    log(f"Pipeline start: {date_str}")
    log(f"Base dir: {BASE_DIR}")

    # Step 1: Scrape
    ok = run_step(
        "daily_scrape",
        [PYTHON, str(SCRAPE_SCRIPT), "--date", date_str],
        timeout=1800,
    )
    if not ok:
        log("ABORT: scrape failed")
        sys.exit(1)

    # Step 2: Transcribe (faster-whisper local)
    ok = run_step(
        "daily_transcribe",
        [PYTHON, str(TRANSCRIBE_SCRIPT), "--date", date_str, "--concurrency", "1"],
        timeout=3600,
    )
    if not ok:
        log("WARNING: transcribe had errors, continuing...")

    # Step 3: Import (DB + Milvus + export JSON)
    ok = run_step(
        "daily_import",
        [PYTHON, str(IMPORT_SCRIPT), "--date", date_str],
        timeout=600,
    )
    if not ok:
        log("ABORT: import failed")
        sys.exit(1)

    # Step 4: Generate competitive report
    json_path = DATA_DIR / date_str / "daily_report_data.json"
    if not json_path.exists():
        log(f"WARNING: JSON not found: {json_path}, skipping report")
    else:
        report_path = REPORT_DIR / f"{date_str}.md"
        ok = run_step(
            "competitor_report",
            [PYTHON, str(REPORT_SCRIPT), "--data", str(json_path)],
            timeout=600,
        )
        if ok:
            log(f"Report: {report_path}")
        else:
            log("WARNING: Report generation failed")

    # Step 5: Content Planner (scripts generation)
    report_md = REPORT_DIR / f"{date_str}.md"
    if not report_md.exists():
        log(f"WARNING: Report not found: {report_md}, skipping content planner")
    else:
        ok = run_step(
            "content_planner",
            [PYTHON, str(CONTENT_SCRIPT), "--report", str(report_md)],
            timeout=600,
        )
        if ok:
            log(f"Scripts: {SCRIPTS_DIR / f'{date_str}.md'}")
        else:
            log("WARNING: Content planner failed")

    # Steps 6-7 moved to daily_distribution_pipeline.py (8:30 AM cron)
    log("Pipeline complete.")


if __name__ == "__main__":
    main()
