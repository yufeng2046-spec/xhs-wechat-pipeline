#!/usr/bin/env python3
"""
WeChat Cover Image Generator — HTML+CSS+Playwright screenshot.

Generates 900×500 cover images for WeChat Official Account articles.
Reuses the screenshot pattern from xhs-pipeline/image_generator.py.
"""

import asyncio
import base64
from pathlib import Path

from playwright.async_api import async_playwright
from md_to_wechat_html import pick_theme, THEMES


# ═══════════════════════════════════════════════════════════════════════════════
# Cover HTML template — 900×500
# ═══════════════════════════════════════════════════════════════════════════════

def build_cover_html(title: str, subtitle: str, date_str: str,
                     author: str, theme_keywords: str = "blue") -> str:
    """
    Build a full HTML page for the 900×500 WeChat cover image.

    Args:
        title: Article title (max ~20 chars)
        subtitle: Short subtitle or summary hook
        date_str: Display date (e.g. "2026.05.24")
        author: Author/brand name
        theme_keywords: Color theme selection keywords
    """
    theme_name, _ = pick_theme(theme_keywords)
    theme = THEMES[theme_name]

    # Extract accent and bg colors from theme
    accent = _extract_css_val(theme["h2"], "color")
    bg = _extract_css_val(theme["page"], "background-color")
    h2_color = accent or "#3B5998"
    bg_color = bg or "#F5F6FA"

    # Trim title if too long
    display_title = title if len(title) <= 24 else title[:23] + "…"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8">
<meta name="viewport" content="width=900,initial-scale=1,maximum-scale=1,user-scalable=no">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  width:900px; height:500px; overflow:hidden;
  background: linear-gradient(135deg, {bg_color} 0%, {_lighten(bg_color)} 100%);
  font-family: "PingFang SC","Microsoft YaHei","Helvetica Neue",sans-serif;
  display:flex; align-items:center; justify-content:center;
}}
.card {{
  width:840px; height:440px;
  background:#FFFFFF;
  border-radius:12px;
  box-shadow:0 4px 24px rgba(0,0,0,0.08);
  display:flex; flex-direction:column;
  padding:48px 56px;
  position:relative;
  overflow:hidden;
}}
.accent-bar {{
  position:absolute; top:0; left:0; width:6px; height:100%;
  background:{h2_color};
}}
.date-tag {{
  font-size:13px; color:#999; letter-spacing:2px; margin-bottom:24px;
}}
.title {{
  font-size:40px; font-weight:800; color:#1A1A1A;
  line-height:1.3; margin-bottom:16px;
  letter-spacing:1px;
}}
.subtitle {{
  font-size:18px; color:#666; line-height:1.6;
  margin-bottom:auto;
  max-width:600px;
}}
.divider {{
  width:60px; height:3px; background:{h2_color};
  margin:24px 0 20px;
}}
.brand {{
  font-size:14px; color:#B0B0B0;
  display:flex; align-items:center; gap:8px;
}}
.brand-dot {{
  width:8px; height:8px; border-radius:50%;
  background:{h2_color};
}}
</style>
</head>
<body>
<div class="card">
  <div class="accent-bar"></div>
  <div class="date-tag">{date_str} · 房产新媒体竞品日报</div>
  <div class="title">{_escape(display_title)}</div>
  <div class="subtitle">{_escape(subtitle)}</div>
  <div class="divider"></div>
  <div class="brand">
    <div class="brand-dot"></div>
    {_escape(author)}
  </div>
</div>
</body>
</html>"""
    return html


def _lighten(hex_color: str, factor: float = 0.05) -> str:
    """Slightly lighten a hex color."""
    hex_color = hex_color.lstrip("#")
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    r = min(255, int(r + (255 - r) * factor))
    g = min(255, int(g + (255 - g) * factor))
    b = min(255, int(b + (255 - b) * factor))
    return f"#{r:02x}{g:02x}{b:02x}"


def _extract_css_val(style_str: str, prop: str):
    """Extract a CSS property value from an inline style string."""
    import re
    match = re.search(rf"{prop}:\s*([^;]+)", style_str)
    return match.group(1).strip() if match else None


def _escape(text: str) -> str:
    """Basic HTML escaping."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


# ═══════════════════════════════════════════════════════════════════════════════
# Rendering
# ═══════════════════════════════════════════════════════════════════════════════

async def _render(html: str, output_path: str, width: int = 900, height: int = 500) -> str:
    """Render HTML to JPEG via Playwright headless Chromium."""
    data_uri = "data:text/html;base64," + base64.b64encode(html.encode()).decode()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": width, "height": height})
        await page.goto(data_uri, wait_until="networkidle")
        await page.screenshot(path=output_path, full_page=False, type="jpeg", quality=92)
        await browser.close()
    return output_path


def generate_cover(title: str, subtitle: str, date_str: str,
                   author: str, theme_keywords: str, output_dir: str) -> str:
    """
    Generate WeChat cover image (900×500). Returns path to cover.jpg.
    """
    html = build_cover_html(title, subtitle, date_str, author, theme_keywords)
    out_path = str(Path(output_dir) / "cover.jpg")
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    asyncio.run(_render(html, out_path, width=900, height=500))
    print(f"  ✓ Cover image saved: {out_path}")
    return out_path


# ═══════════════════════════════════════════════════════════════════════════════
# Product Card — embedded in article body
# ═══════════════════════════════════════════════════════════════════════════════

def build_product_card_html(theme_keywords: str = "blue") -> str:
    """Build a product promo card HTML (600×800) for embedding in article body."""
    theme_name, _ = pick_theme(theme_keywords)
    theme = THEMES[theme_name]
    accent = _extract_css_val(theme["h2"], "color") or "#3B5998"
    bg = _extract_css_val(theme["page"], "background-color") or "#F5F6FA"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8">
<meta name="viewport" content="width=600,initial-scale=1,maximum-scale=1,user-scalable=no">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  width:600px; height:800px; overflow:hidden;
  background:{bg};
  font-family: "PingFang SC","Microsoft YaHei",sans-serif;
  display:flex; align-items:center; justify-content:center;
}}
.card {{
  width:560px; height:760px;
  background:#FFFFFF;
  border-radius:12px;
  box-shadow:0 4px 20px rgba(0,0,0,0.08);
  padding:36px 32px;
  position:relative;
  overflow:hidden;
}}
.top-accent {{
  position:absolute; top:0; left:0; right:0; height:5px;
  background:linear-gradient(90deg, {accent}, {_lighten(accent)});
}}
.emoji {{ font-size:36px; margin-bottom:12px; }}
.title {{
  font-size:26px; font-weight:800; color:#1A1A1A;
  margin-bottom:16px; line-height:1.3;
}}
.modules {{ display:flex; flex-direction:column; gap:10px; margin-bottom:20px; }}
.module {{
  display:flex; align-items:center; gap:12px;
  padding:12px 14px; background:{bg};
  border-radius:8px; border-left:3px solid {accent};
}}
.module-num {{
  font-size:18px; font-weight:900; color:{accent};
  width:28px; text-align:center; flex-shrink:0;
}}
.module-text {{ font-size:14px; color:#2D2D2D; line-height:1.4; }}
.module-text strong {{ font-size:15px; color:#1A1A1A; }}
.features {{
  font-size:13px; color:#666; line-height:1.8;
  margin-bottom:16px;
}}
.price-box {{
  background:linear-gradient(135deg, {accent}, {_lighten(accent, 0.15)});
  border-radius:10px; padding:16px 20px; text-align:center;
  margin-bottom:12px;
}}
.price-original {{ font-size:14px; color:rgba(255,255,255,0.7); text-decoration:line-through; }}
.price-now {{ font-size:36px; font-weight:900; color:#FFFFFF; }}
.price-now .yen {{ font-size:22px; }}
.limit {{ font-size:12px; color:rgba(255,255,255,0.8); margin-top:4px; }}
.cta-text {{
  font-size:13px; color:#999; text-align:center; line-height:1.6;
}}
.cta-text strong {{ color:{accent}; }}
</style>
</head>
<body>
<div class="card">
  <div class="top-accent"></div>
  <div class="emoji">🎓</div>
  <div class="title">房产新媒体<br>实战训练营</div>
  <div class="modules">
    <div class="module">
      <div class="module-num">❶</div>
      <div class="module-text"><strong>短视频基础</strong> · 账号定位+选题+拍摄，搞定第一条视频</div>
    </div>
    <div class="module">
      <div class="module-num">❷</div>
      <div class="module-text"><strong>短视频提高</strong> · 表现力+数据优化，稳定流量增长</div>
    </div>
    <div class="module">
      <div class="module-num">❸</div>
      <div class="module-text"><strong>直播基础</strong> · 开播准备+讲盘框架，第一次就上手</div>
    </div>
    <div class="module">
      <div class="module-num">❹</div>
      <div class="module-text"><strong>直播提高</strong> · 留资转化+数据复盘，每场都有线索</div>
    </div>
  </div>
  <div class="features">
    📹 4节录播课无限回看　🤖 AI小助手每日推送脚本<br>
    💬 企业微信陪跑群　👨‍🏫 于老师亲自答疑<br>
    🎯 21天打卡+阶段复盘　📖 个性化口播脚本
  </div>
  <div class="price-box">
    <div class="price-original">原价 ¥299</div>
    <div class="price-now"><span class="yen">¥</span>29.9</div>
    <div class="limit">🔥 限时特价 · 首期限量20人</div>
  </div>
  <div class="cta-text">
    下载<strong>企业微信</strong> · 扫码加入于老师组织<br>
    回复「<strong>训练营</strong>」报名
  </div>
</div>
</body>
</html>"""
    return html


def generate_product_card(theme_keywords: str, output_dir: str) -> str:
    """Generate product promo card image (600×800). Returns path to product_card.jpg."""
    html = build_product_card_html(theme_keywords)
    out_path = str(Path(output_dir) / "product_card.jpg")
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    asyncio.run(_render(html, out_path, width=600, height=800))
    print(f"  ✓ Product card saved: {out_path}")
    return out_path


# ── Test ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "/tmp/wechat_test"
    path = generate_cover(
        title="房产经纪人获客日报：方法论的内卷与突围",
        subtitle="7个账号7条视频深度拆解，找到你的下一个爆款选题",
        date_str="2026.05.24",
        author="AI新媒体实战笔记",
        theme_keywords="蓝",
        output_dir=out_dir,
    )
    print(f"Done: {path}")
