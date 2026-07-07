#!/bin/bash
# Deploy content pipelines to CubeMini
# Run this ON CubeMini:
#   bash deploy_to_cubemini.sh

set -e

SCRIPT_DIR="/home/frank/ai-content"
VENV_PYTHON="/home/frank/ai-content/venv/bin/python3"
LOG_DIR="/home/frank/ai-content/logs"

echo "=== CubeMini Pipeline Deploy ==="

# 1. Pull latest code (fast-forward only, no merge commits)
echo ""
echo "[1/4] Pulling latest code..."
cd "$SCRIPT_DIR"
git pull --ff-only origin main

# 2. Verify Python and deps
echo ""
echo "[2/4] Checking dependencies..."
$VENV_PYTHON -c "import litellm; import playwright; import markdown; print('  Dependencies OK')"

# 3. Verify all required scripts exist
echo ""
echo "[3/4] Verifying scripts..."
for script in \
    competitor-report/daily_pipeline_cm.py \
    competitor-report/daily_distribution_pipeline.py \
    xhs-pipeline/daily_xhs_pipeline.py \
    wechat-pipeline/daily_wechat_pipeline.py; do
    if [ -f "$script" ]; then
        echo "  OK: $script"
    else
        echo "  MISSING: $script"
        exit 1
    fi
done

# 4. Update cron — preserve all existing jobs, only touch pipeline entries
echo ""
echo "[4/4] Updating cron..."
mkdir -p "$LOG_DIR"

CRON_5AM="0 5 * * * $VENV_PYTHON $SCRIPT_DIR/competitor-report/daily_pipeline_cm.py >> $LOG_DIR/pipeline_5am.log 2>&1"
CRON_830AM="27 8 * * * $VENV_PYTHON $SCRIPT_DIR/competitor-report/daily_distribution_pipeline.py >> $LOG_DIR/distribution_830am.log 2>&1"

# Save existing crontab, filter out ONLY our specific pipeline entries
EXISTING=$(crontab -l 2>/dev/null || true)
if [ -n "$EXISTING" ]; then
    # Only remove lines containing our exact script paths
    FILTERED=$(echo "$EXISTING" | grep -v 'competitor-report/daily_pipeline_cm.py\|competitor-report/daily_distribution_pipeline.py' || true)
else
    FILTERED=""
fi

# Build new crontab: preserved entries + our two pipeline jobs
NEW_CRONTAB=""
if [ -n "$FILTERED" ]; then
    NEW_CRONTAB="$FILTERED"$'\n'"$CRON_5AM"$'\n'"$CRON_830AM"
else
    NEW_CRONTAB="$CRON_5AM"$'\n'"$CRON_830AM"
fi

echo "$NEW_CRONTAB" | crontab -

echo ""
echo "=== Cron jobs installed ==="
crontab -l | grep 'daily_pipeline_cm\|daily_distribution_pipeline'
echo ""
echo "=== Deploy complete ==="
echo "Schedule:"
echo "  5:00 AM  — Scrape + Transcribe + Report + Scripts"
echo "  8:27 AM  — XHS drafts + WeChat draft"
echo ""
echo "Test manually:"
echo "  $VENV_PYTHON $SCRIPT_DIR/competitor-report/daily_distribution_pipeline.py --date \$(date -d 'yesterday' +%F)"
