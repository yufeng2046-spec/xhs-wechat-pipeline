#!/usr/bin/env python3
"""
XHS Creator Platform QR code login helper.

Opens creator.xiaohongshu.com/login, extracts the QR code, saves it as an image,
waits for user to scan with the XHS app. Once login succeeds, cookies are saved.

Usage:
    python3 xhs_login.py                      # headless, save QR to file
    python3 xhs_login.py --visible            # show browser for direct scan
    python3 xhs_login.py -o xhs_cookies.json  # custom output path

Pattern adapted from douyin_login.py.
"""

import asyncio
import base64
import json
import sys
import time
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright

from config import XHS_PROFILE_DIR, XHS_COOKIES_FILE

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

DEFAULT_COOKIES_PATH = "xhs_cookies.json"
LOGIN_CHECK_INTERVAL_S = 3
LOGIN_TIMEOUT_S = 180

# JS patches to evade headless detection (same as douyin_login.py)
STEALTH_JS = r"""
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = {
    runtime: {},
    loadTimes: function() {},
    csi: function() {},
    app: {}
};
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
"""


async def login_and_save_cookies(
    output_path: str = DEFAULT_COOKIES_PATH,
    visible: bool = False,
) -> bool:
    """Open XHS Creator login, extract QR, wait for user to scan."""

    async with async_playwright() as p:
        # Use persistent context — browser fingerprint preserved across sessions
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

        # ── 1. Visit XHS Creator login page ──
        print("Navigating to creator.xiaohongshu.com/login …")
        await page.goto(
            "https://creator.xiaohongshu.com/login",
            wait_until="domcontentloaded",
            timeout=30_000,
        )
        await page.wait_for_timeout(8_000)

        title = await page.title()
        print(f"  Page title: {title}")

        # ── 2. Look for QR code ──
        qr_base64 = await page.evaluate("""
            () => {
                // Search all images for a QR code (square, data:image)
                for (const img of document.querySelectorAll('img')) {
                    if (img.naturalWidth >= 140 && img.naturalWidth <= 300
                        && Math.abs(img.naturalWidth - img.naturalHeight) < 10
                        && img.src && img.src.startsWith('data:image/')) {
                        return img.src;
                    }
                }
                // Fallback: any base64 image in login area
                for (const el of document.querySelectorAll('[class*="login"], [class*="Login"], [class*="qrcode"], [class*="QR"]')) {
                    for (const img of el.querySelectorAll('img')) {
                        if (img.src && img.src.startsWith('data:image/')) {
                            return img.src;
                        }
                    }
                }
                return null;
            }
        """)

        if not qr_base64:
            await page.screenshot(path="xhs_login_debug.png")
            print("ERROR: Could not find QR code. Saved xhs_login_debug.png")
            print(f"  URL: {await page.evaluate('() => window.location.href')}")
            # Try waiting for page to fully render
            await page.wait_for_timeout(5_000)
            qr_base64 = await page.evaluate("""
                () => {
                    for (const img of document.querySelectorAll('img')) {
                        if (img.src && img.src.startsWith('data:image/')) return img.src;
                    }
                    return null;
                }
            """)
            if not qr_base64:
                await browser.close()
                return False

        # ── 3. Save QR image ──
        _, encoded = qr_base64.split(",", 1)
        qr_bytes = base64.b64decode(encoded)
        qr_path = Path(output_path).stem + "_qr.png"
        Path(qr_path).write_bytes(qr_bytes)
        print(f"\nQR code saved to: {qr_path}")
        if not visible:
            print(f"   Open this file and scan with XHS app.")
        print(f"   Waiting up to {LOGIN_TIMEOUT_S}s for login …")

        # ── 4. Poll for login success ──
        start = time.time()
        logged_in = False

        while time.time() - start < LOGIN_TIMEOUT_S:
            await page.wait_for_timeout(LOGIN_CHECK_INTERVAL_S * 1000)

            # Method 1: Check for post-login UI elements
            try:
                publish_btn = page.get_by_text("发布笔记", exact=False).first
                if await publish_btn.count() > 0:
                    logged_in = True
                    elapsed = int(time.time() - start)
                    print(f"\n  Login detected via '发布笔记' button! ({elapsed}s)")
                    break
            except Exception:
                pass

            # Method 2: Check for key auth cookies
            cookies = await context.cookies()
            cookie_names = {c["name"] for c in cookies}
            if "a1" in cookie_names and "webId" in cookie_names:
                logged_in = True
                elapsed = int(time.time() - start)
                print(f"\n  Login detected via auth cookies! ({elapsed}s)")
                break

            # Method 3: Check URL redirect
            current_url = await page.evaluate('() => window.location.href')
            if "/login" not in current_url:
                logged_in = True
                elapsed = int(time.time() - start)
                print(f"\n  Login detected (redirected)! ({elapsed}s)")
                break

            elapsed = int(time.time() - start)
            dots = "." * ((elapsed // 5) % 4 + 1)
            print(f"\r   Waiting{dots}   {elapsed}s", end="", flush=True)

        if not logged_in:
            print(f"\n  Login timed out after {LOGIN_TIMEOUT_S}s")
            await context.close()
            return False

        # ── 5. Navigate to home to capture full session ──
        await page.wait_for_timeout(2_000)
        # Navigate around to trigger all cookie sets
        await page.goto("https://creator.xiaohongshu.com", wait_until="domcontentloaded", timeout=30_000)
        await page.wait_for_timeout(5_000)
        print(f"  Home page: {page.url}")

        # ── 6. Save cookies & state ──
        await page.wait_for_timeout(2_000)
        cookies = await context.cookies()

        json_cookies = []
        for c in cookies:
            json_cookies.append({
                "name": c["name"],
                "value": c["value"],
                "domain": c["domain"],
                "path": c["path"],
                "expires": c.get("expires", -1),
                "httpOnly": c.get("httpOnly", False),
                "secure": c.get("secure", False),
                "sameSite": c.get("sameSite", "Lax"),
            })

        Path(output_path).write_text(
            json.dumps(json_cookies, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # Playwright storage_state (full browser context)
        state_path = output_path.replace(".json", "_state.json")
        await context.storage_state(path=state_path)

        print(f"  Saved {len(json_cookies)} cookies to: {output_path}")
        print(f"  Saved browser state to: {state_path}")
        print(f"  Profile dir: {XHS_PROFILE_DIR}")
        await context.close()
        return True


async def main() -> None:
    output_path = DEFAULT_COOKIES_PATH
    visible = False

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] in ("-o", "--output") and i + 1 < len(args):
            output_path = args[i + 1]
            i += 2
        elif args[i] == "--visible":
            visible = True
            i += 1
        else:
            i += 1

    print("=" * 55)
    print("  XHS Creator QR Code Login")
    print("=" * 55)

    success = await login_and_save_cookies(output_path=output_path, visible=visible)

    if success:
        print(f"\nCookies saved to: {output_path}")
    else:
        print("\nLogin failed. Tips:")
        print("  - Try --visible to see the browser and solve captchas")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
