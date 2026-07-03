#!/usr/bin/env python3
"""
Daily WeChat Official Account Pipeline Orchestrator.

7-stage pipeline:
  1. Read daily competitor report (reports/{date}.md)
  2. LLM transform → long-form WeChat article (Markdown)
  3. Save Markdown to output/{date}/wechat/article.md
  4. Markdown → WeChat-compatible HTML with inline CSS
  5. Generate 900×500 cover image via Playwright screenshot
  6. Publish draft to mp.weixin.qq.com via Playwright
  7. Push summary to Feishu

Usage:
    python3 daily_wechat_pipeline.py --date 2026-07-02
    python3 daily_wechat_pipeline.py --date 2026-07-02 --no-upload --no-feishu
    python3 daily_wechat_pipeline.py --date 2026-07-02 --visible  # show browser
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

from config import (
    COMPETITOR_DIR, OUTPUT_DIR, FEISHU_WEBHOOK,
    AUTHOR_NAME, WECHAT_JPEG_QUALITY,
)
from content_transformer import transform_report_to_article
from md_to_wechat_html import convert as md_to_html
from md_to_wechat_html import pick_theme
from image_generator import generate_cover
from wechat_publisher import publish_draft, log as pub_log

BEIJING_TZ = timezone(timedelta(hours=8))


def log(msg: str) -> None:
    ts = datetime.now(BEIJING_TZ).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ═══════════════════════════════════════════════════════════════════════════════
# Core Pipeline
# ═══════════════════════════════════════════════════════════════════════════════

def run_pipeline(date_str: str, no_upload: bool = False, no_feishu: bool = False,
                 visible: bool = False, dry_run: bool = False) -> dict:
    """
    Run the full WeChat daily pipeline.

    Returns:
        dict with status info for Feishu notification
    """
    result = {
        "date": date_str,
        "success": False,
        "title": "",
        "digest": "",
        "article_path": "",
        "cover_path": "",
        "publish_result": None,
        "error": None,
    }

    try:
        # ── Step 1: Read report ──
        log("=" * 60)
        log(f"Step 1/6: Reading daily report for {date_str}")
        report_path = COMPETITOR_DIR / "reports" / f"{date_str}.md"

        if not report_path.exists():
            raise FileNotFoundError(f"Report not found: {report_path}")

        report_md = report_path.read_text(encoding="utf-8")
        log(f"  Report loaded: {len(report_md)} chars")

        # ── Step 2: Transform to article ──
        log(f"Step 2/6: Transforming report → WeChat long-form article")
        article_data = transform_report_to_article(report_md, date_str)

        title = article_data["title"]
        digest = article_data["digest"]
        key_visual = article_data["key_visual"]
        article_md = article_data["article_md"]

        result["title"] = title
        result["digest"] = digest

        log(f"  Title: {title}")
        log(f"  Digest: {digest[:60]}...")
        log(f"  Theme: {key_visual}")

        # ── Step 3: Save Markdown ──
        log(f"Step 3/6: Saving article Markdown")
        out_dir = OUTPUT_DIR / date_str / "wechat"
        out_dir.mkdir(parents=True, exist_ok=True)

        md_path = out_dir / "article.md"
        md_path.write_text(article_md, encoding="utf-8")
        log(f"  Saved: {md_path}")
        result["article_path"] = str(md_path)

        # ── Step 4: Markdown → HTML ──
        log(f"Step 4/6: Converting Markdown → WeChat HTML")
        theme_name, _ = pick_theme(key_visual)
        log(f"  Using theme: {theme_name}")

        html_content = md_to_html(
            article_md, theme_name=theme_name,
            title=title, author=AUTHOR_NAME, digest=digest,
        )

        html_path = out_dir / "article.html"
        html_path.write_text(html_content, encoding="utf-8")
        log(f"  Saved: {html_path} ({len(html_content)} chars)")

        # ── Step 5: Generate cover image ──
        log(f"Step 5/6: Generating cover image")
        # Format date for display
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            display_date = dt.strftime("%Y.%m.%d")
        except ValueError:
            display_date = date_str

        # Build subtitle from first line of article
        first_content_line = ""
        for line in article_md.split("\n"):
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and len(stripped) > 10:
                first_content_line = stripped[:80]
                break

        cover_path = generate_cover(
            title=title,
            subtitle=first_content_line or digest,
            date_str=display_date,
            author=AUTHOR_NAME,
            theme_keywords=key_visual,
            output_dir=str(out_dir),
        )
        result["cover_path"] = cover_path

        # Also generate product card image (for manual embedding)
        from image_generator import generate_product_card
        product_card_path = generate_product_card(key_visual, str(out_dir))
        log(f"  Product card: {product_card_path}")

        # ── Step 6: Publish draft ──
        log(f"Step 6/6: Publishing to WeChat MP")

        if dry_run or no_upload:
            log("  Skipping upload (dry-run / --no-upload)")
            result["publish_result"] = {"success": True, "skipped": True}
        else:
            import asyncio
            pub_result = asyncio.run(publish_draft(
                html_content=html_content,
                title=title,
                cover_path=cover_path,
                digest=digest,
                author=AUTHOR_NAME,
                visible=visible,
                dry_run=False,
            ))
            result["publish_result"] = pub_result
            if pub_result.get("success"):
                log("  Draft published successfully!")
            else:
                log(f"  Draft publish issue: {pub_result.get('error', 'unknown')}")

        result["success"] = True
        log("=" * 60)
        log("Pipeline complete!")

    except Exception as e:
        log(f" PIPELINE ERROR: {e}")
        result["error"] = str(e)

    # ── Step 7: Feishu notification ──
    if not no_feishu:
        push_summary_to_feishu(result)

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Feishu Notification
# ═══════════════════════════════════════════════════════════════════════════════

def push_summary_to_feishu(result: dict) -> None:
    """Push a summary card to Feishu."""
    date_str = result["date"]
    title = result.get("title", "未生成")
    digest = result.get("digest", "")
    success = result.get("success", False)
    error = result.get("error", "")
    pub = result.get("publish_result", {})

    status_icon = "✅" if success else "❌"
    draft_status = "已保存草稿" if pub.get("success") else ("已跳过上传" if pub.get("skipped") else "保存失败")

    body = f"""**{status_icon} 公众号长文草稿 {date_str}**

**标题**：{title}
**摘要**：{digest}

**状态**：{draft_status}"""

    if error:
        body += f"\n\n**错误**：{error}"

    card = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"公众号长文草稿 {date_str}"},
                "template": "turquoise",
            },
            "elements": [
                {"tag": "markdown", "content": body},
                {"tag": "hr"},
                {
                    "tag": "note",
                    "elements": [
                        {"tag": "plain_text", "content": "公众号草稿已保存至 mp.weixin.qq.com → 草稿箱，请手动审核后发出"}
                    ]
                }
            ]
        }
    }

    for attempt in range(3):
        try:
            resp = requests.post(FEISHU_WEBHOOK, json=card, timeout=30)
            if resp.status_code == 200 and resp.json().get("code") == 0:
                log("  Feishu notification sent")
                return
        except Exception as e:
            log(f"  Feishu retry {attempt + 1}: {e}")
            time.sleep(2)

    log("  Feishu notification failed after 3 retries")


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Daily WeChat Pipeline")
    ap.add_argument("--date", default=None, help="Date YYYY-MM-DD (default: yesterday BJT)")
    ap.add_argument("--no-upload", action="store_true", help="Skip publishing draft")
    ap.add_argument("--no-feishu", action="store_true", help="Skip Feishu notification")
    ap.add_argument("--visible", action="store_true", help="Show browser during publishing")
    ap.add_argument("--dry-run", action="store_true", help="Simulate without saving")

    args = ap.parse_args()

    if args.date:
        date_str = args.date
    else:
        date_str = (datetime.now(BEIJING_TZ) - timedelta(days=1)).strftime("%Y-%m-%d")

    log(f"Daily WeChat Pipeline — {date_str}")
    log(f"Upload: {not args.no_upload} | Feishu: {not args.no_feishu}")

    result = run_pipeline(
        date_str=date_str,
        no_upload=args.no_upload,
        no_feishu=args.no_feishu,
        visible=args.visible,
        dry_run=args.dry_run,
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))

    sys.exit(0 if result.get("success") else 1)
