#!/usr/bin/env python3
"""
XHS Creator Platform Draft Publisher.

Uses Playwright to automate publishing drafts to creator.xiaohongshu.com.
Loads saved browser state from xhs_login.py, then:
  1. Clicks "发布笔记" on creator home
  2. Uploads cover image via filechooser event
  3. Fills title (via get_by_role textbox) and body (via paragraph/contenteditable)
  4. Clicks "保存草稿"

Key improvements over v1:
- filechooser event for reliable image upload (RedBookC pattern)
- Playwright-native get_by_role()/get_by_text() selectors
- storage_state for full browser context persistence
- Better SPA navigation handling
- Screenshot-on-error for debugging

Usage:
    python3 xhs_publisher.py --posts output/2026-05-24/xhs_posts.json \\
                             --images output/2026-05-24/images/ \\
                             [--visible] [--dry-run]
"""

import asyncio
import base64
import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright

from config import XHS_CREATOR_URL, XHS_PROFILE_DIR

BEIJING_TZ = timezone(timedelta(hours=8))

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

PUBLISH_URL = "https://creator.xiaohongshu.com/publish/publish?source=official"
LOGIN_URL = "https://www.xiaohongshu.com/explore"

STEALTH_JS = r"""
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = { runtime: {}, loadTimes: function() {}, csi: function() {}, app: {} };
const _origQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : _origQuery(parameters)
);
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const arr = [
            { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
            { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
            { name: 'Native Client', filename: 'internal-nacl-plugin' },
        ];
        arr.item = (i) => arr[i];
        arr.namedItem = (n) => arr.find(p => p.name === n);
        arr.refresh = () => {};
        Object.setPrototypeOf(arr, PluginArray.prototype);
        return arr;
    }
});
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
// Force shadow DOM to open mode so we can access custom element internals
const _origAttachShadow = Element.prototype.attachShadow;
Element.prototype.attachShadow = function(init) {
    if (init && init.mode === 'closed') {
        init = Object.assign({}, init, { mode: 'open' });
    }
    return _origAttachShadow.call(this, init);
};
"""



def log(msg: str) -> None:
    ts = datetime.now(BEIJING_TZ).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def load_posts(posts_path: str) -> list[dict]:
    with open(posts_path, encoding="utf-8") as f:
        return json.load(f)


async def wait_for_network(page, timeout: int = 10_000) -> None:
    """Wait for SPA to settle."""
    try:
        await page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:
        pass
    await page.wait_for_timeout(2_000)


async def setup_filechooser(page, images: list[str]) -> None:
    """Set up filechooser handler to upload images when triggered.

    Playwright's filechooser event fires when a file input is clicked.
    We pre-register the handler so it's ready when we click the upload trigger.
    """
    async def handle_filechooser(fc):
        log(f"    FileChooser: uploading {len(images)} images")
        await fc.set_files(images)

    page.once("filechooser", handle_filechooser)


async def ensure_logged_in(page, context) -> bool:
    """Check if logged in. If not, show QR login."""
    # Go directly to publish page — if it loads, we're logged in
    await page.goto(PUBLISH_URL, wait_until="domcontentloaded", timeout=30_000)
    await page.wait_for_timeout(6_000)

    body = await page.evaluate('() => document.body.innerText')
    if any(kw in body for kw in ["发布笔记", "笔记管理", "数据看板", "草稿箱"]):
        log("  Already logged in to Creator")
        return True

    # Not logged in — show QR from xiaohongshu.com
    log("  Not logged in. Opening xiaohongshu.com for QR login...")
    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
    await page.wait_for_timeout(8_000)

    await page.screenshot(path="xhs_login_screen.png")
    log("  Login screen saved: xhs_login_screen.png")
    import subprocess
    subprocess.run(["open", "xhs_login_screen.png"], check=False)
    log("  Scan QR code in the browser window or screenshot (180s timeout)...")

    start = time.time()
    while time.time() - start < 180:
        await page.wait_for_timeout(3_000)
        try:
            # Check 1: Auth cookies
            cookies = await context.cookies()
            cookie_names = {c["name"] for c in cookies}
            has_auth = "a1" in cookie_names and "webId" in cookie_names

            # Check 2: URL redirect away from login + UI elements
            current_url = page.url
            body = await page.evaluate('() => document.body.innerText')
            has_ui = any(kw in body for kw in ["个人主页", "发布", "我", "通知"])

            if has_auth or (has_ui and "/login" not in current_url):
                log("  Login detected!")
                await page.goto(PUBLISH_URL, wait_until="domcontentloaded", timeout=30_000)
                await page.wait_for_timeout(5_000)
                body2 = await page.evaluate('() => document.body.innerText')
                if any(kw in body2 for kw in ["发布笔记", "笔记管理", "草稿箱"]):
                    log("  Creator login confirmed")
                    return True
        except Exception:
            pass
        elapsed = int(time.time() - start)
        if elapsed % 30 == 0:
            log(f"    Waiting for QR scan... {elapsed}s")
    return False


async def publish_one_draft(page, post: dict, images_dir: str,
                            index: int) -> dict:
    """Publish a single XHS post as draft. Returns result dict."""
    result = {"index": index, "title": post.get("title", "?"), "status": "unknown"}
    title = post.get("title", "")
    tags = post.get("tags", [])

    # Build body text from rich card data
    body_parts = []
    if post.get("subtitle"):
        body_parts.append(post["subtitle"])
    for pt in post.get("points", []):
        heading = pt.get("heading", "")
        pt_body = pt.get("body", "")
        body_parts.append(f"{pt.get('icon', '💡')} {heading}\n{pt_body}")
        if pt.get("highlight"):
            body_parts.append(f"📌 {pt['highlight']}")
    if post.get("quote"):
        body_parts.append(f"「{post['quote'].get('text', '')}」\n——{post['quote'].get('attribution', '')}")
    if post.get("summary"):
        items = post["summary"].get("checklist", [])
        if items:
            body_parts.append("✅ 今日行动\n" + "\n".join(f"□ {item}" for item in items))
        if post["summary"].get("cta"):
            body_parts.append(post["summary"]["cta"])
    body = "\n\n".join(body_parts)

    # Collect image paths
    img_dir = Path(images_dir)
    cover = str(img_dir / "cover.jpg")
    slides = sorted([str(p) for p in img_dir.glob("slide_*.jpg")])
    all_images = [cover] + slides
    # Keep only existing files
    all_images = [p for p in all_images if Path(p).exists()]

    if not all_images:
        result["status"] = "error"
        result["error"] = "No images found"
        return result

    log(f"  Post {index}: {title[:40]} ({len(all_images)} images)")

    try:
        # ── 1. Navigate to publish page ──
        await page.goto(PUBLISH_URL, wait_until="domcontentloaded", timeout=30_000)
        await wait_for_network(page)

        # ── 2. Click "上传图文" tab (page defaults to video upload) ──
        tabs = page.locator("div.creator-tab")
        tab_count = await tabs.count()
        log(f"    Found {tab_count} creator tabs")
        for ti in range(tab_count):
            tab = tabs.nth(ti)
            try:
                text = await tab.text_content()
                if text and "上传图文" in text:
                    await tab.click()
                    log(f"    Clicked '上传图文' tab")
                    await page.wait_for_timeout(1_500)
                    break
            except Exception:
                continue

        # ── 3. Upload images ──
        log(f"    Uploading {len(all_images)} images...")

        upload_triggered = False

        # Method 1: .upload-input (reference implementation pattern)
        upload_input = page.locator(".upload-input").first
        if await upload_input.count() > 0:
            try:
                await upload_input.set_input_files(all_images)
                upload_triggered = True
                log(f"    .upload-input upload OK")
                # Wait for upload to complete & edit interface to appear
                for attempt in range(15):
                    await page.wait_for_timeout(1_000)
                    edit_indicators = page.locator('div.d-input input, div.ql-editor, [contenteditable="true"]').first
                    if await edit_indicators.count() > 0:
                        log(f"    Edit interface ready")
                        break
            except Exception as e:
                log(f"    .upload-input failed: {e}")

        # Method 2: Any file input
        if not upload_triggered:
            file_input = page.locator('input[type="file"]').first
            if await file_input.count() > 0:
                try:
                    await file_input.set_input_files(all_images)
                    upload_triggered = True
                    log(f"    Direct file input upload OK")
                    await page.wait_for_timeout(4_000)
                except Exception as e:
                    log(f"    Direct file input failed: {e}")

        if not upload_triggered:
            log(f"    WARNING: could not upload images")
            await page.screenshot(path=f"xhs_upload_debug_{index}.png")

        await page.wait_for_timeout(3_000)

        # ── 4. Fill title (XHS limit: ~20 chars)
        title_truncated = title[:20]
        log(f"    Filling title: {title_truncated}")

        # Reference selectors: div.d-input input
        title_selectors = [
            "div.d-input input",
            ".d-input input",
            "input[placeholder*='标题']",
            "textarea[placeholder*='标题']",
        ]
        title_filled = False
        for sel in title_selectors:
            try:
                inp = page.locator(sel).first
                if await inp.count() > 0:
                    await inp.click()
                    await inp.fill("")
                    await inp.type(title_truncated, delay=50)
                    title_filled = True
                    log(f"    Title filled via '{sel}'")
                    break
            except Exception:
                continue

        if not title_filled:
            log(f"    WARNING: title fill failed, using JS fallback")
            await page.evaluate(f"""
                () => {{
                    const input = document.querySelector('div.d-input input')
                        || document.querySelector('.d-input input')
                        || document.querySelector('input[placeholder*=\"标题\"]');
                    if (input) {{
                        input.focus();
                        input.value = {json.dumps(title_truncated)};
                        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    }}
                }}
            """)

        await page.wait_for_timeout(800)

        # ── 5. Fill body ──
        full_body = body
        if tags:
            full_body += "\n\n" + " ".join(tags)

        log(f"    Filling body ({len(full_body)} chars)")
        body_filled = False

        # Reference selector: div.ql-editor (Quill rich text editor)
        for sel in ["div.ql-editor", '[contenteditable="true"]', 'textarea']:
            try:
                body_el = page.locator(sel).first
                if await body_el.count() > 0:
                    await body_el.click()
                    await body_el.evaluate("el => { el.innerHTML = ''; el.innerText = ''; }")
                    await page.wait_for_timeout(300)
                    await body_el.type(full_body, delay=15)
                    body_filled = True
                    log(f"    Body filled via '{sel}'")
                    break
            except Exception:
                continue

        if not body_filled:
            log(f"    WARNING: no body element found, using JS")
            await page.evaluate(f"""
                () => {{
                    const el = document.querySelector('div.ql-editor')
                        || document.querySelector('[contenteditable=\"true\"]')
                        || document.querySelector('textarea');
                    if (el) {{
                        el.focus();
                        if (el.contentEditable === 'true') {{
                            el.innerText = {json.dumps(full_body)};
                        }} else {{
                            el.value = {json.dumps(full_body)};
                        }}
                        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    }}
                }}
            """)

        await page.wait_for_timeout(1_500)

        # ── 6. Save as draft ──
        log(f"    Saving draft...")
        saved = False

        # Shadow DOM patched to open mode via STEALTH_JS.
        # Buttons inside <xhs-publish-btn>: "暂存离开" (save) + "发布" (publish)
        try:
            save_btn = page.locator("xhs-publish-btn").locator("text=暂存离开").first
            if await save_btn.count() > 0:
                await save_btn.click(timeout=5_000)
                saved = True
                log(f"    Clicked '暂存离开'")
        except Exception as e:
            log(f"    Save click error: {e}")

        # Verify save via toast
        await page.wait_for_timeout(2_000)
        try:
            success_el = page.locator('[class*="toast"], [class*="message"], [class*="el-message"]').first
            if await success_el.count() > 0:
                text = await success_el.inner_text()
                log(f"    Response: {text[:80]}")
        except Exception:
            pass

        if not saved:
            log(f"    WARNING: draft save button not found")
            await page.screenshot(path=f"xhs_save_debug_{index}.png")

        if not saved:
            result["status"] = "error"
            result["error"] = "Save button not found"
            log(f"    FAILED: could not save draft")
            return result

        # Wait for save
        await page.wait_for_timeout(3_000)

        # Check for success
        try:
            success_el = page.locator('[class*="toast"], [class*="success"], [class*="message"]').first
            if await success_el.count() > 0:
                text = await success_el.inner_text()
                log(f"    Response: {text[:80]}")
        except Exception:
            pass

        result["status"] = "draft"
        log(f"    DONE: draft saved")

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)[:200]
        log(f"    ERROR: {e}")
        try:
            await page.screenshot(path=f"xhs_error_{index}.png")
        except Exception:
            pass

    return result


async def publish_drafts(posts_path: str, images_base_dir: str,
                         visible: bool = False, dry_run: bool = False,
                         start_index: int = 1, count: Optional[int] = None) -> list[dict]:
    """Publish XHS posts as drafts via Playwright."""
    posts = load_posts(posts_path)
    if count is not None:
        posts = posts[start_index - 1:start_index - 1 + count]
    else:
        posts = posts[start_index - 1:]

    log(f"Publishing {len(posts)} posts to XHS drafts...")
    if dry_run:
        log("DRY RUN — skipping actual publishing")
        return [{"index": i + start_index, "title": p.get("title", "?"),
                 "status": "dry_run"} for i, p in enumerate(posts)]

    results = []

    async with async_playwright() as p:
        # Use the same persistent profile as login — preserves browser fingerprint
        Path(XHS_PROFILE_DIR).mkdir(parents=True, exist_ok=True)
        context = await p.chromium.launch_persistent_context(
            user_data_dir=XHS_PROFILE_DIR,
            headless=not visible,
            user_agent=USER_AGENT,
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-infobars",
            ],
        )

        page = await context.new_page()
        await page.add_init_script(STEALTH_JS)

        # Ensure logged in (shows QR if needed)
        if not await ensure_logged_in(page, context):
            log("FATAL: Could not log in to XHS Creator")
            await context.close()
            return [{"index": i + start_index, "title": p.get("title", "?"),
                     "status": "error", "error": "Login failed"} for i, p in enumerate(posts)]

        for i, post in enumerate(posts):
            post_img_dir = str(Path(images_base_dir) / f"post_{i + start_index:02d}")
            if not Path(post_img_dir).exists():
                post_img_dir = images_base_dir

            result = await publish_one_draft(page, post, post_img_dir, i + start_index)
            results.append(result)

            # Delay between posts
            if i < len(posts) - 1:
                delay = 3 + (i % 3)  # 3-5 seconds
                await page.wait_for_timeout(delay * 1000)

        await context.close()

    return results


async def main() -> None:
    posts_path = None
    images_dir = None
    visible = False
    dry_run = False
    start_index = 1
    count = None

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--posts" and i + 1 < len(args):
            posts_path = args[i + 1]
            i += 2
        elif args[i] == "--images" and i + 1 < len(args):
            images_dir = args[i + 1]
            i += 2
        elif args[i] == "--start" and i + 1 < len(args):
            start_index = int(args[i + 1])
            i += 2
        elif args[i] == "--count" and i + 1 < len(args):
            count = int(args[i + 1])
            i += 2
        elif args[i] == "--visible":
            visible = True
            i += 1
        elif args[i] == "--dry-run":
            dry_run = True
            i += 1
        else:
            i += 1

    if not posts_path:
        print("ERROR: --posts required", file=sys.stderr)
        sys.exit(1)
    if not images_dir:
        print("ERROR: --images required", file=sys.stderr)
        sys.exit(1)

    results = await publish_drafts(
        posts_path=posts_path, images_base_dir=images_dir,
        visible=visible, dry_run=dry_run,
        start_index=start_index, count=count,
    )

    ok = sum(1 for r in results if r["status"] in ("draft", "dry_run"))
    fail = sum(1 for r in results if r["status"] == "error")
    print(f"\nResults: {ok} drafts, {fail} errors")

    log_path = Path(posts_path).parent / "xhs_publish_log.json"
    log_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Log saved to: {log_path}")


if __name__ == "__main__":
    asyncio.run(main())
