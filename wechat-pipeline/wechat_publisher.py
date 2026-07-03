#!/usr/bin/env python3
"""
WeChat Official Account Draft Publisher — Playwright browser automation.

Publishes long-form articles as drafts to mp.weixin.qq.com.
Uses persistent browser context for QR login + cookie persistence.

Usage:
    python3 wechat_publisher.py --html article.html --title "标题" --cover cover.jpg \\
                                --digest "摘要" [--visible] [--dry-run]
"""

import asyncio
import base64
import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from playwright.async_api import async_playwright

from config import WECHAT_MP_URL, WECHAT_PROFILE_DIR

BEIJING_TZ = timezone(timedelta(hours=8))

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# Anti-detection JS (reused from XHS publisher)
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


async def wait_for_network(page, timeout: int = 10_000) -> None:
    try:
        await page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:
        await page.wait_for_timeout(3_000)


# ═══════════════════════════════════════════════════════════════════════════════
# Login
# ═══════════════════════════════════════════════════════════════════════════════

async def ensure_logged_in(context, page) -> bool:
    """Check if logged into WeChat MP. If not, wait for user to scan QR code."""
    log("Checking WeChat MP login status...")
    await page.goto(WECHAT_MP_URL, wait_until="domcontentloaded", timeout=30_000)
    await wait_for_network(page)
    await page.wait_for_timeout(2_000)

    if await _detect_login(page):
        log("Already logged into WeChat MP")
        return True

    log("Not logged in. Opening login page for QR scan...")
    log("Please scan the QR code in the browser window")
    log("(You have 3 minutes)")

    # Navigate to login page
    await page.goto("https://mp.weixin.qq.com/", wait_until="domcontentloaded", timeout=30_000)
    await page.wait_for_timeout(2_000)

    # Wait for login success (check every 2s, up to 180s)
    for i in range(90):
        if await _detect_login(page):
            log("Login detected!")
            await page.wait_for_timeout(3_000)
            return True
        await page.wait_for_timeout(2_000)
        if i % 15 == 14:
            log(f"  Still waiting for QR scan... ({((i+1)*2)}s elapsed)")

    log("Login timed out after 3 minutes")
    return False


async def _detect_login(page) -> bool:
    """Check if user is logged into WeChat MP."""
    try:
        current_url = page.url
        body = await page.content()

        # If we see dashboard elements, we're logged in
        dashboard_indicators = ["首页", "素材管理", "新的创作", "草稿箱", "已发布"]
        found = sum(1 for kw in dashboard_indicators if kw in body)

        # If redirected to login page
        if "scan" in current_url.lower() or "login" in current_url.lower():
            # Check if the page shows logged-in state despite URL
            pass

        return found >= 2
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# Draft Publishing
# ═══════════════════════════════════════════════════════════════════════════════

async def publish_draft(html_content: str, title: str, cover_path: str,
                         digest: str = "", author: str = "", visible: bool = False,
                         dry_run: bool = False) -> dict:
    """
    Publish a draft to WeChat MP.

    Args:
        html_content: WeChat-safe HTML article body
        title: Article title
        cover_path: Path to cover image (900×500 JPG)
        digest: Article summary (≤128 chars)
        author: Author name
        visible: Show browser UI
        dry_run: Don't actually save, just simulate

    Returns:
        dict with keys: success, title, error (if any)
    """
    result = {"success": False, "title": title}

    if dry_run:
        log(f"  [DRY RUN] Would publish: {title}")
        log(f"  Cover: {cover_path}")
        log(f"  HTML length: {len(html_content)} chars")
        result["success"] = True
        return result

    async with async_playwright() as p:
        # Launch persistent context (preserves login state)
        context = await p.chromium.launch_persistent_context(
            WECHAT_PROFILE_DIR,
            headless=not visible,
            user_agent=USER_AGENT,
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.add_init_script(STEALTH_JS)

        try:
            # 1. Ensure login
            if not await ensure_logged_in(context, page):
                result["error"] = "Login failed or timed out"
                return result

            # 2. Navigate to article editor
            log("Opening article editor...")
            await _open_editor(page)

            # 3. Fill title
            log(f"  Filling title: {title[:40]}...")
            await _fill_title(page, title)

            # 4. Fill author
            if author:
                await _fill_author(page, author)

            # 5. Fill content (HTML mode)
            log(f"  Filling content ({len(html_content)} chars)...")
            await _fill_content(page, html_content)

            # 6. Upload cover image
            log(f"  Uploading cover: {cover_path}")
            await _upload_cover(page, cover_path)

            # 7. Fill digest
            if digest:
                await _fill_digest(page, digest)

            # 8. Save as draft
            log("  Saving draft...")
            await _save_draft(page)

            log(f"  Draft saved: {title}")
            result["success"] = True

        except Exception as e:
            log(f"  ERROR: {e}")
            result["error"] = str(e)
            # Take error screenshot
            try:
                ss_path = "/tmp/wechat_publish_error.png"
                await page.screenshot(path=ss_path)
                log(f"  Error screenshot: {ss_path}")
            except Exception:
                pass

        finally:
            await context.close()

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Page Interaction Helpers
# ═══════════════════════════════════════════════════════════════════════════════

async def _extract_token(page) -> str:
    """Extract the session token from current page URL or page content."""
    import re
    current_url = page.url
    # Try URL query param
    match = re.search(r"token=(\d+)", current_url)
    if match:
        return match.group(1)
    # Try from page content
    content = await page.content()
    match = re.search(r"token=(\d+)", content)
    if match:
        return match.group(1)
    return ""


async def _open_editor(page) -> None:
    """Navigate to the article editor (new article)."""
    token = await _extract_token(page)
    log(f"  Token: {token[:10] if token else 'NOT FOUND'}...")

    if token:
        # Method 1: Direct URL with token
        editor_url = (
            f"https://mp.weixin.qq.com/cgi-bin/appmsg"
            f"?t=media/appmsg_edit_v2&action=edit&isNew=1"
            f"&type=77&createType=0&token={token}&lang=zh_CN"
        )
        log(f"  Navigating to editor URL...")
        await page.goto(editor_url, wait_until="domcontentloaded", timeout=30_000)
        await wait_for_network(page)
        await page.wait_for_timeout(3_000)

        current_url = page.url
        log(f"  Landed: {current_url[:120]}")

        # Check if editor loaded
        if "appmsg" in current_url:
            try:
                await page.wait_for_selector("#title", state="attached", timeout=10_000)
                log("  Editor loaded via direct URL!")
                await page.screenshot(path="/tmp/wechat_editor_loaded.png")
                return
            except Exception:
                log("  Direct URL loaded but #title not found, trying alternative selectors...")
                # Maybe the editor uses different selectors in newer versions
                alt_found = False
                for sel in ["input[placeholder*='标题']", "[class*='title'] input", "input.title-input"]:
                    try:
                        el = await page.wait_for_selector(sel, timeout=3_000)
                        if el:
                            log(f"  Editor loaded via alt selector: {sel}")
                            alt_found = True
                            break
                    except Exception:
                        continue
                if alt_found:
                    return

    # Method 2: Navigate through UI
    log("  Direct URL method failed, trying UI navigation...")
    await page.goto("https://mp.weixin.qq.com/", wait_until="domcontentloaded", timeout=30_000)
    await wait_for_network(page)
    await page.wait_for_timeout(3_000)
    await page.screenshot(path="/tmp/wechat_home.png")

    # Extract fresh token after navigation
    token = await _extract_token(page)
    log(f"  Fresh token: {token[:10] if token else 'NOT FOUND'}")

    # Try clicking "新的创作" → hover approach
    log("  Looking for '新的创作' area...")
    # Hover over the create area first (sometimes it's hover-triggered)
    try:
        create_area = page.locator("[class*='create'], .creation-area, .header-create").first
        if await create_area.count() > 0:
            await create_area.hover()
            await page.wait_for_timeout(1_000)
    except Exception:
        pass

    # Click "新的创作"
    create_clicked = False
    for sel in ["text=新的创作", "a:has-text('新的创作')", "span:has-text('新的创作')"]:
        try:
            btn = page.locator(sel).first
            if await btn.count() > 0:
                await btn.click()
                await page.wait_for_timeout(2_000)
                create_clicked = True
                log(f"  Clicked '新的创作' via {sel}")
                break
        except Exception:
            continue

    if create_clicked:
        await page.screenshot(path="/tmp/wechat_after_create.png")

    # Try to find any dropdown item for new article
    for sel in [
        "text=写新图文", "text=新建图文消息", "text=新建图文",
        "a:has-text('写新图文')", "li:has-text('写新图文')",
        "[class*='dropdown'] a", ".popup-menu a",
    ]:
        try:
            el = page.locator(sel).first
            if await el.count() > 0:
                text = await el.inner_text()
                log(f"  Found dropdown item: '{text.strip()}' via {sel}")
                await el.click()
                await page.wait_for_timeout(3_000)
                if "appmsg" in page.url:
                    log("  Landed on editor via dropdown!")
                    break
        except Exception:
            continue

    # Final fallback: try with fresh token again
    token = await _extract_token(page)
    if token and "appmsg" not in page.url:
        editor_url = (
            f"https://mp.weixin.qq.com/cgi-bin/appmsg"
            f"?t=media/appmsg_edit_v2&action=edit&isNew=1"
            f"&type=77&createType=0&token={token}&lang=zh_CN"
        )
        await page.goto(editor_url, wait_until="domcontentloaded", timeout=30_000)
        await wait_for_network(page)
        await page.wait_for_timeout(3_000)

    # Wait for editor
    await page.wait_for_timeout(3_000)
    await page.screenshot(path="/tmp/wechat_final.png")

    current_url = page.url
    if "appmsg" not in current_url:
        raise Exception(f"Could not reach editor. Final URL: {current_url[:120]}. Check /tmp/wechat_*.png")

    log("  Editor loaded!")


async def _fill_title(page, title: str) -> None:
    """Fill the article title input (hidden textarea in WeChat MP)."""
    # WeChat MP uses a hidden <textarea id="title"> — use evaluate to set value
    js = """
    (title) => {
        const el = document.querySelector('#title');
        if (!el) return 'not found';
        // Simulate the editor's own behavior: set value and trigger events
        el.value = title;
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        // Also update the visible title bar if it exists
        const visibleTitle = document.querySelector('.js_title_bar .js_title');
        if (visibleTitle) visibleTitle.textContent = title;
        return 'ok';
    }
    """
    result = await page.evaluate(js, title)
    if result == 'ok':
        log(f"    Title set via JS: {title}")
    else:
        log(f"    Title JS returned: {result}")
        # Try force fill as fallback
        await page.locator("#title").fill(title, timeout=5_000, force=True)
        log(f"    Title filled via force")


async def _fill_author(page, author: str) -> None:
    """Fill the author input via JS (may be hidden)."""
    try:
        await page.evaluate("""
        (author) => {
            const el = document.querySelector('#author');
            if (el) {
                el.value = author;
                el.dispatchEvent(new Event('input', { bubbles: true }));
            }
        }
        """, author)
        log(f"    Author set: {author}")
    except Exception as e:
        log(f"    Author fill error: {e}")


async def _fill_content(page, html_content: str) -> None:
    """
    Fill article content in the WeChat MP editor.
    WeChat MP uses a rich text editor (UEditor-based) which is usually an iframe.
    """
    # Escape backticks and backslashes for JS
    safe_html = html_content.replace("\\", "\\\\").replace("`", "\\`")

    # Method 1: Try the UEditor iframe
    try:
        iframe = page.locator("#ueditor_0")
        if await iframe.count() > 0:
            frame = await iframe.content_frame()
            if frame:
                body = frame.locator("body")
                if await body.count() > 0:
                    await body.evaluate(f"el => el.innerHTML = `{safe_html}`")
                    await page.wait_for_timeout(1_000)
                    log(f"    Content filled via ueditor iframe ({len(html_content)} chars)")
                    return
    except Exception as e:
        log(f"    UEditor iframe failed: {e}")

    # Method 2: Try contenteditable elements
    try:
        editables = page.locator("[contenteditable='true']")
        count = await editables.count()
        log(f"    Found {count} contenteditable elements")
        if count > 0:
            # Use the largest one (likely the editor body)
            largest = editables.first
            max_len = 0
            for i in range(count):
                try:
                    el = editables.nth(i)
                    html_len = await el.evaluate("el => el.innerHTML.length")
                    if html_len > max_len:
                        max_len = html_len
                        largest = el
                except Exception:
                    pass
            await largest.evaluate(f"el => el.innerHTML = `{safe_html}`")
            await page.wait_for_timeout(1_000)
            log(f"    Content filled via contenteditable ({len(html_content)} chars)")
            return
    except Exception as e:
        log(f"    Contenteditable failed: {e}")

    # Method 3: Try to find a textarea
    try:
        textareas = page.locator("textarea")
        count = await textareas.count()
        for i in range(count):
            el = textareas.nth(i)
            name = await el.get_attribute("name") or ""
            if "content" in name or "editor" in name:
                await el.fill(html_content, timeout=5_000)
                log(f"    Content filled via textarea")
                return
    except Exception:
        pass

    raise Exception("Could not find any content editor")


async def _upload_cover(page, cover_path: str) -> None:
    """Upload cover image through WeChat MP cover selection flow."""
    abs_path = str(Path(cover_path).resolve())
    if not Path(abs_path).exists():
        log(f"    Cover image not found: {abs_path}")
        return

    try:
        # Step 1: Click the cover thumbnail/area in the sidebar
        # The cover area is typically on the right side of the editor
        cover_clicked = False
        for sel in [
            ".js_cover_thumb", "#js_cover_area", ".cover_thumb",
            "[class*='cover_thumb']", "[class*='cover-area']",
            "div.js_cover_area", ".js_cover_container",
        ]:
            try:
                el = page.locator(sel).first
                if await el.count() > 0 and not cover_clicked:
                    await el.click(timeout=3_000)
                    await page.wait_for_timeout(2_000)
                    log(f"    Clicked cover area: {sel}")
                    cover_clicked = True
                    break
            except Exception:
                continue

        if not cover_clicked:
            # Try finding by text near "封面"
            page_text = await page.content()
            if "封面" not in page_text:
                log("    No cover-related text found on page, skipping cover upload")
                return

        # Step 2: After clicking cover area, a modal/dialog appears
        # Look for "本地上传" or "从本地添加" button
        for upload_text in ["本地上传", "从本地添加", "上传图片", "选择图片"]:
            try:
                btn = page.locator(f"text={upload_text}").first
                if await btn.count() > 0:
                    await btn.click(timeout=3_000)
                    await page.wait_for_timeout(1_500)
                    log(f"    Clicked '{upload_text}'")
                    break
            except Exception:
                continue

        # Step 3: Now the file chooser should appear
        # Try to find and use any file input
        file_inputs = page.locator("input[type='file']")
        fi_count = await file_inputs.count()
        log(f"    File inputs after cover interaction: {fi_count}")

        uploaded = False
        for i in range(fi_count):
            try:
                fi = file_inputs.nth(i)
                async with page.expect_file_chooser(timeout=10_000) as fc_info:
                    await fi.click(force=True, timeout=5_000)
                file_chooser = await fc_info.value
                await file_chooser.set_files(abs_path)
                uploaded = True
                log(f"    Cover uploaded via input {i}")
                break
            except Exception:
                continue

        # Also try: just set the file directly without file chooser
        if not uploaded:
            for i in range(fi_count):
                try:
                    fi = file_inputs.nth(i)
                    await fi.set_input_files(abs_path, timeout=5_000)
                    uploaded = True
                    log(f"    Cover set via set_input_files {i}")
                    break
                except Exception:
                    continue

        if uploaded:
            # Wait for upload and crop dialog to appear
            await page.wait_for_timeout(5_000)

            # Take screenshot to see what's happening
            await page.screenshot(path="/tmp/wechat_after_cover_upload.png")

            # In WeChat MP cover flow, after upload:
            # 1. A crop dialog appears with a "确定" or "完成" button
            # 2. Sometimes it's a two-step: crop → confirm
            log("    Looking for cover confirm button...")
            confirmed = False
            for confirm_text in ["确定", "完成", "下一步", "确认", "保存"]:
                try:
                    btn = page.locator(f"button:has-text('{confirm_text}')").first
                    if await btn.count() == 0:
                        btn = page.locator(f"text={confirm_text}").first
                    if await btn.count() > 0:
                        await btn.click(timeout=5_000)
                        await page.wait_for_timeout(2_000)
                        log(f"    Clicked '{confirm_text}' post-upload")
                        confirmed = True
                        # Check if there's a second confirm (sometimes cascade)
                        await page.wait_for_timeout(1_000)
                        for second in ["确定", "完成"]:
                            try:
                                btn2 = page.locator(f"button:has-text('{second}')").first
                                if await btn2.count() > 0:
                                    await btn2.click(timeout=3_000)
                                    log(f"    Clicked second confirm '{second}'")
                                    await page.wait_for_timeout(1_000)
                            except Exception:
                                pass
                        break
                except Exception:
                    continue

            if not confirmed:
                # Maybe the dialog closed already or didn't appear
                log("    No confirm button found, cover may already be accepted")
        else:
            log("    WARNING: Cover upload failed, continuing without cover")

    except Exception as e:
        log(f"    Cover upload error: {e}")


async def _fill_digest(page, digest: str) -> None:
    """Fill the article digest/abstract via JS."""
    try:
        await page.evaluate("""
        (digest) => {
            const el = document.querySelector('#js_description') ||
                      document.querySelector('textarea[name=\"description\"]');
            if (el) {
                el.value = digest;
                el.dispatchEvent(new Event('input', { bubbles: true }));
            }
        }
        """, digest)
        log(f"    Digest filled")
    except Exception as e:
        log(f"    Digest fill error: {e}")


async def _save_draft(page) -> None:
    """Click save draft button."""
    await page.wait_for_timeout(1_000)

    # Try clicking save by JS (most reliable for WeChat MP)
    js_clicked = await page.evaluate("""
    () => {
        // Try save buttons by ID
        let saveBtn = document.querySelector('#js_save') ||
                     document.querySelector('#bottom_save');
        if (saveBtn) { saveBtn.click(); return 'clicked by id'; }
        // Try by text content
        const all = document.querySelectorAll('a, button, span');
        for (const el of all) {
            if (el.textContent && el.textContent.includes('保存')) {
                el.click();
                return 'clicked by text';
            }
        }
        return 'not found';
    }
    """)
    log(f"    Save JS result: {js_clicked}")

    # If JS didn't find it, try Playwright locators
    if js_clicked != 'clicked':
        for sel in ["#js_save", "text=保存为草稿", "text=保存", "a:has-text('保存')"]:
            try:
                btn = page.locator(sel).first
                if await btn.count() > 0:
                    await btn.click(timeout=5_000, force=True)
                    log(f"    Clicked save via {sel}")
                    break
            except Exception:
                continue

    # Wait and verify
    await page.wait_for_timeout(3_000)
    body = await page.content()
    if any(kw in body for kw in ["保存成功", "已保存"]):
        log("    Save confirmed!")
    else:
        log("    Save clicked, verify manually")


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="WeChat MP Draft Publisher")
    ap.add_argument("--html", required=True, help="Path to HTML article file")
    ap.add_argument("--title", required=True, help="Article title")
    ap.add_argument("--cover", required=True, help="Path to cover image JPG")
    ap.add_argument("--digest", default="", help="Article summary")
    ap.add_argument("--author", default="AI新媒体实战笔记")
    ap.add_argument("--visible", action="store_true", help="Show browser window")
    ap.add_argument("--dry-run", action="store_true", help="Simulate without saving")

    args = ap.parse_args()

    html_content = Path(args.html).read_text(encoding="utf-8")

    result = asyncio.run(publish_draft(
        html_content=html_content,
        title=args.title,
        cover_path=args.cover,
        digest=args.digest,
        author=args.author,
        visible=args.visible,
        dry_run=args.dry_run,
    ))

    print(json.dumps(result, ensure_ascii=False, indent=2))
