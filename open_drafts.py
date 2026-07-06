#!/usr/bin/env python3
"""
Open XHS and WeChat draft boxes for manual review and publishing.

Uses ISOLATED Playwright persistent browser profiles — completely separate
from the automated pipeline profiles. No risk of cross-contamination.

First run: scan QR codes to log in (once per platform). Cookies persist.
Subsequent runs: opens directly to draft pages, already logged in.

Usage:
    python3 open_drafts.py             # Open both platforms
    python3 open_drafts.py --xhs       # XHS only
    python3 open_drafts.py --wechat    # WeChat only
"""

import asyncio
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent
XHS_PROFILE = str(WORKSPACE / "xhs-pipeline" / "xhs_profile_manual")
WECHAT_PROFILE = str(WORKSPACE / "wechat-pipeline" / "wechat_profile_manual")

XHS_URL = "https://creator.xiaohongshu.com/"
WECHAT_URL = "https://mp.weixin.qq.com/"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


async def open_platform(profile_dir: str, url: str, label: str) -> None:
    """Launch a persistent-context browser and navigate to url."""
    from playwright.async_api import async_playwright

    p = await async_playwright().start()
    context = await p.chromium.launch_persistent_context(
        profile_dir,
        headless=False,
        user_agent=USER_AGENT,
        viewport={"width": 1440, "height": 900},
        locale="zh-CN",
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ],
    )

    page = context.pages[0] if context.pages else await context.new_page()
    print(f"[{label}] Navigating to {url}")
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    print(f"[{label}] Ready — review and publish drafts manually.")
    print(f"[{label}] Close the browser window when done.")

    try:
        while context.pages:
            await asyncio.sleep(0.5)
    except Exception:
        pass

    await context.close()
    await p.stop()
    print(f"[{label}] Browser closed.")


async def main():
    args = set(sys.argv[1:])
    xhs_only = "--xhs" in args
    wechat_only = "--wechat" in args
    both = not xhs_only and not wechat_only

    if "--help" in args or "-h" in args:
        print(__doc__)
        return

    tasks = []
    if both or xhs_only:
        tasks.append(open_platform(XHS_PROFILE, XHS_URL, "XHS"))
    if both or wechat_only:
        tasks.append(open_platform(WECHAT_PROFILE, WECHAT_URL, "WeChat"))

    if not tasks:
        print("Usage: python3 open_drafts.py [--xhs] [--wechat]")
        return

    print("Opening draft boxes...")
    print("⚠️  Do NOT click 'logout' in either platform — it will invalidate the session.")
    print("   Close browser windows when done to release the profile lock.")
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
