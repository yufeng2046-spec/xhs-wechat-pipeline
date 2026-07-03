#!/usr/bin/env python3
"""
Daily XHS Content Pipeline Orchestrator.

Reads competitor-report/scripts/{date}.md, selects top 2 scripts, transforms
them into XHS 图文 posts, generates cover + carousel images, and publishes
drafts to XHS Creator Platform via Playwright.

Usage:
    python3 daily_xhs_pipeline.py --date 2026-05-24
    python3 daily_xhs_pipeline.py --date 2026-05-24 --no-upload --no-feishu
"""

import asyncio
import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

from config import (
    BASE_DIR, COMPETITOR_DIR, OUTPUT_DIR, FEISHU_WEBHOOK, DAILY_SCRIPT_LIMIT,
)
from content_transformer import (
    parse_scripts_md, select_best_scripts, transform_to_xhs,
)
from image_generator import generate_all_for_post

BEIJING_TZ = timezone(timedelta(hours=8))


def log(msg: str) -> None:
    ts = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def save_posts_json(posts, date_str: str) -> Path:
    """Save transformed posts to JSON for publisher consumption."""
    out_dir = OUTPUT_DIR / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "xhs_posts.json"

    data = []
    for post in posts:
        card_data = post.to_card_data()
        card_data["source_script_title"] = post.source_script.title if post.source_script else ""
        data.append(card_data)

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def push_summary_to_feishu(posts, results: list[dict], date_str: str) -> bool:
    """Push XHS pipeline summary to Feishu."""
    lines = [
        f"小红书内容管线 · {date_str}",
        "",
        f"**发布草稿**: {len(posts)} 篇",
    ]
    for i, (post, result) in enumerate(zip(posts, results), 1):
        status_emoji = "✅" if result.get("status") == "draft" else "❌"
        lines.append(f"{status_emoji} **{post.title}**")
        lines.append(f"&nbsp;&nbsp;&nbsp;&nbsp;标签: {' '.join(post.tags[:4])}")

    lines.append("")
    lines.append("---")
    lines.append("草稿已保存至小红书创作者平台，请审核后手动发布。")

    card = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"小红书图文草稿 {date_str}"},
                "template": "turquoise",
            },
            "elements": [
                {"tag": "markdown", "content": "\n".join(lines)},
                {"tag": "hr"},
                {
                    "tag": "note",
                    "elements": [
                        {"tag": "plain_text", "content": f"XHS Pipeline | 自动生成于 {datetime.now(BEIJING_TZ).strftime('%H:%M')} | 请审核后手动发布"}
                    ],
                },
            ],
        },
    }

    for attempt in range(3):
        try:
            resp = requests.post(FEISHU_WEBHOOK, json=card, timeout=30)
            if resp.status_code == 200 and resp.json().get("code") == 0:
                return True
            log(f"  Feishu error: {resp.text[:200]}")
        except Exception as e:
            log(f"  Feishu attempt {attempt + 1}/3: {e}")
            if attempt < 2:
                time.sleep(2)
    return False


def main():
    date_str = None
    no_upload = False
    no_feishu = False

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--date" and i + 1 < len(args):
            date_str = args[i + 1]
            i += 2
        elif args[i] == "--no-upload":
            no_upload = True
            i += 1
        elif args[i] == "--no-feishu":
            no_feishu = True
            i += 1
        else:
            i += 1

    if not date_str:
        date_str = (datetime.now(BEIJING_TZ) - timedelta(days=1)).strftime("%Y-%m-%d")

    log(f"XHS Pipeline start: {date_str}")

    # ── 1. Parse scripts ──
    scripts_path = COMPETITOR_DIR / "scripts" / f"{date_str}.md"
    if not scripts_path.exists():
        log(f"ERROR: Scripts file not found: {scripts_path}")
        sys.exit(1)

    log(f"Parsing scripts: {scripts_path}")
    scripts = parse_scripts_md(str(scripts_path))
    log(f"  Found {len(scripts)} scripts")

    if len(scripts) == 0:
        log("No scripts found, exiting.")
        sys.exit(1)

    # ── 2. Select best scripts for XHS ──
    log(f"Selecting top {DAILY_SCRIPT_LIMIT} scripts for XHS...")
    selected = select_best_scripts(scripts)
    log(f"  Selected: {', '.join(f'#{s.index} {s.title[:30]}' for s in selected)}")

    # ── 3. Transform to XHS posts ──
    log("Transforming scripts to XHS posts...")
    posts = []
    for s in selected:
        log(f"  Transforming script #{s.index}: {s.title[:40]}")
        post = transform_to_xhs(s)
        posts.append(post)
        log(f"    Title: {post.title}")
        log(f"    Points: {len(post.points)} | Hero: {post.hero_stat}")
        log(f"    Tags: {len(post.tags)} tags")

    # ── 4. Save posts JSON ──
    posts_path = save_posts_json(posts, date_str)
    log(f"Posts saved: {posts_path}")

    # ── 5. Generate images ──
    log("Generating images...")
    all_results = []

    for i, post in enumerate(posts):
        post_img_dir = OUTPUT_DIR / date_str / "images" / f"post_{i + 1:02d}"
        log(f"  Post {i + 1}/{len(posts)}: {post.title[:30]}")

        card_data = post.to_card_data()
        img_paths = generate_all_for_post(
            post_data=card_data,
            output_dir=str(post_img_dir),
        )
        log(f"    Cover: {Path(img_paths['cover']).name}")
        log(f"    Slides: {len(img_paths['slides'])}")
        all_results.append({"status": "generated", "images": img_paths})

    # ── 6. Publish drafts ──
    if not no_upload:
        log("Publishing drafts to XHS...")
        from xhs_publisher import publish_drafts

        results = asyncio.run(publish_drafts(
            posts_path=str(posts_path),
            images_base_dir=str(OUTPUT_DIR / date_str / "images"),
            visible=False,
            dry_run=False,
        ))

        ok = sum(1 for r in results if r["status"] == "draft")
        fail = sum(1 for r in results if r["status"] == "error")
        log(f"  Results: {ok} drafts, {fail} errors")
    else:
        log("Skipping upload (--no-upload)")
        results = [{"index": i + 1, "title": p.title, "status": "skipped"}
                   for i, p in enumerate(posts)]

    # ── 7. Feishu summary ──
    if not no_feishu:
        log("Pushing summary to Feishu...")
        ok = push_summary_to_feishu(posts, results, date_str)
        if ok:
            log("  Feishu push succeeded")
        else:
            log("  Feishu push failed")

    log(f"XHS Pipeline complete: {date_str}")


if __name__ == "__main__":
    main()
