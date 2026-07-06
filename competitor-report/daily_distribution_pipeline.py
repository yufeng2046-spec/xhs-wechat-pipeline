#!/usr/bin/env python3
"""
Daily Content Distribution Pipeline — XHS + WeChat
Runs at 8:30 AM Beijing time, after the 5 AM CubeMini pipeline finishes.

Usage:
    python3 daily_distribution_pipeline.py [--date 2026-07-06]
"""

import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
BEIJING_TZ = timezone(timedelta(hours=8))

# ── Python path on CubeMini ─────────────────────────────────────────────
PYTHON = "/home/frank/ai-content/venv/bin/python3"

XHS_PIPELINE_SCRIPT = BASE_DIR.parent / "xhs-pipeline" / "daily_xhs_pipeline.py"
WECHAT_PIPELINE_SCRIPT = BASE_DIR.parent / "wechat-pipeline" / "daily_wechat_pipeline.py"


def log(msg: str) -> None:
    ts = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def run_step(step_name: str, cmd: list[str], timeout: int = 1200) -> bool:
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
        log(f"  {'OK' if ok else 'FAILED'} {step_name} [{elapsed:.0f}s]")
        return ok
    except subprocess.TimeoutExpired:
        log(f"  TIMEOUT {step_name} after {timeout}s")
        return False


def main():
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

    log(f"Distribution Pipeline start: {date_str}")

    # Step 6: XHS Content Pipeline
    if XHS_PIPELINE_SCRIPT.exists():
        ok = run_step(
            "xhs_pipeline",
            [PYTHON, str(XHS_PIPELINE_SCRIPT), "--date", date_str],
            timeout=1200,
        )
        if ok:
            log("XHS drafts published successfully")
        else:
            log("WARNING: XHS pipeline had errors, check logs")
    else:
        log(f"XHS pipeline script not found: {XHS_PIPELINE_SCRIPT}")

    # Step 7: WeChat Content Pipeline
    if WECHAT_PIPELINE_SCRIPT.exists():
        ok = run_step(
            "wechat_pipeline",
            [PYTHON, str(WECHAT_PIPELINE_SCRIPT), "--date", date_str],
            timeout=1200,
        )
        if ok:
            log("WeChat draft published successfully")
        else:
            log("WARNING: WeChat pipeline had errors, check logs")
    else:
        log(f"WeChat pipeline script not found: {WECHAT_PIPELINE_SCRIPT}")

    log("Distribution Pipeline complete.")


if __name__ == "__main__":
    main()
