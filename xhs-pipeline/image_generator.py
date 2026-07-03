#!/usr/bin/env python3
"""
Image Generator — Professional XHS card templates via HTML+CSS + Playwright.

Design inspired by guizang-social-card-skill, Postgen, card-xiaohongshu.
Multi-template system: cover, point, quote, summary card types.
"""

import asyncio
import base64
import json
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright


# ═══════════════════════════════════════════════════════════════════════════════
# Color themes — XHS-appropriate palettes
# ═══════════════════════════════════════════════════════════════════════════════

THEMES = {
    # Warm cream — popular on XHS for educational content
    "cream": {
        "bg": "#FDF8F0",
        "card_bg": "#FFFFFF",
        "accent": "#E8784A",
        "accent_light": "#FDF0E8",
        "text_primary": "#2D2D2D",
        "text_secondary": "#6B6B6B",
        "text_muted": "#A0A0A0",
        "border": "#F0E4D4",
        "tag_bg": "#FFF5EE",
        "tag_text": "#D4724A",
    },
    # Soft sage green — fresh, growth-oriented
    "sage": {
        "bg": "#F6F8F4",
        "card_bg": "#FFFFFF",
        "accent": "#5B8C5A",
        "accent_light": "#EEF4EC",
        "text_primary": "#2D332C",
        "text_secondary": "#6B7269",
        "text_muted": "#A0A59E",
        "border": "#E0E8DC",
        "tag_bg": "#F0F5ED",
        "tag_text": "#4A7A49",
    },
    # Professional navy — trust, authority
    "navy": {
        "bg": "#F5F6FA",
        "card_bg": "#FFFFFF",
        "accent": "#3B5998",
        "accent_light": "#EDF1F8",
        "text_primary": "#1E2A3A",
        "text_secondary": "#5A6A7E",
        "text_muted": "#9AA8B8",
        "border": "#E0E6F0",
        "tag_bg": "#EEF2FA",
        "tag_text": "#3B5998",
    },
    # Warm blush — emotional, relatable
    "blush": {
        "bg": "#FEF9F7",
        "card_bg": "#FFFFFF",
        "accent": "#D4786E",
        "accent_light": "#FDF0ED",
        "text_primary": "#3D2420",
        "text_secondary": "#7A5E58",
        "text_muted": "#B5A09C",
        "border": "#F2E0DA",
        "tag_bg": "#FEF2EF",
        "tag_text": "#C4685E",
    },
}


def pick_theme(keywords: str) -> dict:
    """Select theme by keyword matching."""
    kw = keywords.lower()
    if any(w in kw for w in ["蓝", "专业", "信任", "navy", "pro", "企业"]):
        return THEMES["navy"]
    if any(w in kw for w in ["绿", "增长", "成长", "实操", "green", "sage", "干货"]):
        return THEMES["sage"]
    if any(w in kw for w in ["暖", "粉", "红", "情感", "warm", "blush", "共鸣"]):
        return THEMES["blush"]
    return THEMES["cream"]


# ═══════════════════════════════════════════════════════════════════════════════
# HTML template builder
# ═══════════════════════════════════════════════════════════════════════════════

def _build_page(theme: dict, body_class: str, content_html: str, body_html: str) -> str:
    """Wrap content in a full 1080x1440 HTML page with theme CSS."""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8">
<meta name="viewport" content="width=1080,initial-scale=1,maximum-scale=1,user-scalable=no">
<style>
  *, *::before, *::after {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    width: 1080px; height: 1440px; margin: 0; overflow: hidden;
    font-family: "PingFang SC", "Noto Sans CJK SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
    background: {theme['bg']};
    color: {theme['text_primary']};
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
  }}
  .badge {{
    display: inline-block; padding: 10px 24px; border-radius: 20px;
    background: {theme['accent_light']}; color: {theme['accent']};
    font-size: 28px; font-weight: 700; letter-spacing: 2px;
  }}
  .badge-solid {{
    display: inline-block; padding: 10px 24px; border-radius: 20px;
    background: {theme['accent']}; color: #fff;
    font-size: 28px; font-weight: 700; letter-spacing: 2px;
  }}
  .tag {{
    display: inline-block; padding: 6px 18px; border-radius: 16px;
    background: {theme['tag_bg']}; color: {theme['tag_text']};
    font-size: 25px; font-weight: 500; letter-spacing: 1px;
  }}
  .footer-brand {{
    position: absolute; bottom: 52px; left: 0; right: 0; text-align: center;
    font-size: 25px; color: {theme['text_muted']}; letter-spacing: 3px;
  }}
  .page-dot {{
    position: absolute; top: 60px; right: 72px;
    font-size: 30px; color: {theme['text_muted']}; letter-spacing: 3px;
  }}
{content_html}
</style></head><body class="{body_class}">
{body_html}
</body></html>"""


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ═══════════════════════════════════════════════════════════════════════════════
# Card type 1: COVER — pain-point hero + kicker + title + subtitle + tags
# ═══════════════════════════════════════════════════════════════════════════════

def build_cover(title: str, subtitle: str, hero_stat: str = "",
                kicker: str = "", pre_badge: str = "",
                tags: Optional[list] = None, theme_name: str = "cream",
                footer: str = "房产新媒体获客 · 每日干货") -> str:
    t = pick_theme(theme_name)

    css = f"""
  .cover-page {{
    display: flex; flex-direction: column; justify-content: center;
    height: 100%; padding: 80px 100px 100px; position: relative;
  }}
  .cover-accent-dot {{
    position: absolute; border-radius: 50%; pointer-events: none;
    background: {t['accent']}; opacity: 0.06;
  }}
  .cover-pre-badge {{ margin-bottom: 40px; }}
  .cover-hero-row {{
    display: flex; align-items: baseline; gap: 16px; margin-bottom: 24px;
    flex-wrap: wrap;
  }}
  .cover-hero {{
    font-size: 150px; font-weight: 900; line-height: 1; letter-spacing: -4px;
    color: {t['accent']};
  }}
  .cover-kicker {{
    font-size: 37px; font-weight: 600; line-height: 1.4;
    color: {t['text_primary']}; letter-spacing: 1px;
  }}
  .cover-title {{
    font-size: 64px; font-weight: 900; line-height: 1.35; letter-spacing: 3px;
    color: {t['text_primary']}; margin-bottom: 28px; max-width: 880px;
  }}
  .cover-divider {{
    width: 80px; height: 5px; border-radius: 3px;
    background: {t['accent']}; margin-bottom: 32px; opacity: 0.7;
  }}
  .cover-subtitle {{
    font-size: 37px; font-weight: 400; line-height: 1.7;
    color: {t['text_secondary']}; max-width: 820px;
  }}
  .cover-tags {{ margin-top: 48px; display: flex; gap: 16px; flex-wrap: wrap; }}
"""

    badge_html = f'<div class="cover-pre-badge"><div class="badge">{_escape(pre_badge)}</div></div>' if pre_badge else ""

    hero_html = ""
    if hero_stat:
        if kicker:
            hero_html = f"""    <div class="cover-hero-row">
      <span class="cover-hero">{_escape(hero_stat)}</span>
      <span class="cover-kicker">{_escape(kicker)}</span>
    </div>"""
        else:
            hero_html = f'    <div class="cover-hero">{_escape(hero_stat)}</div>'

    tags_html = ""
    if tags:
        chips = "\n    ".join(f'<span class="tag">{_escape(t)}</span>' for t in tags[:4])
        tags_html = f'  <div class="cover-tags">{chips}\n  </div>'

    body = f"""  <div class="cover-accent-dot" style="top:-140px;right:-80px;width:520px;height:520px;"></div>
  <div class="cover-accent-dot" style="bottom:-80px;left:-60px;width:340px;height:340px;"></div>
  <div class="cover-page">
    {badge_html}
    {hero_html}
    <div class="cover-title">{_escape(title)}</div>
    <div class="cover-divider"></div>
    <div class="cover-subtitle">{_escape(subtitle)}</div>
    {tags_html}
  </div>
  <div class="footer-brand">{_escape(footer)}</div>"""

    return _build_page(t, "cover", css, body)


# ═══════════════════════════════════════════════════════════════════════════════
# Card type 2: POINT — emoji icon + heading + body + highlight box
# ═══════════════════════════════════════════════════════════════════════════════

def build_point(icon: str, heading: str, body: str,
                section_num: str = "", highlight_label: str = "",
                highlight_text: str = "", theme_name: str = "cream",
                footer: str = "房产新媒体获客 · 每日干货") -> str:
    t = pick_theme(theme_name)

    css = f"""
  .point-page {{
    display: flex; flex-direction: column;
    height: 100%; padding: 80px 100px 70px; position: relative;
  }}
  .point-top-row {{
    display: flex; justify-content: space-between; align-items: flex-start;
    margin-bottom: 40px;
  }}
  .point-icon {{
    font-size: 74px; line-height: 1;
  }}
  .point-section-num {{
    font-size: 30px; font-weight: 700; color: {t['text_muted']};
    letter-spacing: 2px;
  }}
  .point-heading {{
    font-size: 51px; font-weight: 800; line-height: 1.4; letter-spacing: 2px;
    color: {t['text_primary']}; margin-bottom: 32px; max-width: 860px;
  }}
  .point-body {{
    font-size: 35px; font-weight: 400; line-height: 1.85; letter-spacing: 1px;
    color: {t['text_secondary']}; max-width: 860px; flex: 1;
  }}
  .point-hl-box {{
    margin-top: 36px; padding: 28px 36px; border-radius: 16px;
    background: {t['accent_light']};
    border-left: 4px solid {t['accent']};
  }}
  .point-hl-label {{
    font-size: 25px; font-weight: 700; color: {t['accent']};
    letter-spacing: 2px; margin-bottom: 8px;
  }}
  .point-hl-text {{
    font-size: 32px; line-height: 1.65; color: {t['text_secondary']};
  }}
"""

    hl_html = ""
    if highlight_text:
        lbl = f'<div class="point-hl-label">{_escape(highlight_label)}</div>' if highlight_label else ""
        hl_html = f"""  <div class="point-hl-box">
    {lbl}
    <div class="point-hl-text">{_escape(highlight_text)}</div>
  </div>"""

    body_html = f"""  <div class="point-page">
    <div class="point-top-row">
      <div class="point-icon">{icon}</div>
      <div class="point-section-num">{_escape(section_num)}</div>
    </div>
    <div class="point-heading">{_escape(heading)}</div>
    <div class="point-body">{_escape(body)}</div>
    {hl_html}
  </div>
  <div class="footer-brand">{_escape(footer)}</div>"""

    return _build_page(t, "point", css, body_html)


# ═══════════════════════════════════════════════════════════════════════════════
# Card type 3: QUOTE — pullquote + attribution
# ═══════════════════════════════════════════════════════════════════════════════

def build_quote(quote: str, attribution: str = "", theme_name: str = "cream",
                footer: str = "房产新媒体获客 · 每日干货") -> str:
    t = pick_theme(theme_name)

    css = f"""
  .quote-page {{
    display: flex; flex-direction: column; justify-content: center;
    height: 100%; padding: 110px 110px 130px; position: relative;
  }}
  .quote-mark {{
    font-size: 184px; line-height: 0.4; color: {t['accent']};
    font-family: Georgia, "Noto Serif CJK SC", "Songti SC", serif;
    margin-bottom: 36px; opacity: 0.4;
  }}
  .quote-text {{
    font-size: 46px; font-weight: 600; line-height: 1.65; letter-spacing: 2px;
    color: {t['text_primary']}; max-width: 840px; margin-bottom: 50px;
  }}
  .quote-attr-row {{
    display: flex; align-items: center; gap: 16px;
  }}
  .quote-attr-line {{
    width: 50px; height: 3px; border-radius: 2px;
    background: {t['accent']}; opacity: 0.5;
  }}
  .quote-attr-text {{
    font-size: 30px; color: {t['text_muted']}; letter-spacing: 2px;
  }}
  .quote-deco {{
    position: absolute; border-radius: 50%; pointer-events: none;
    background: {t['accent']}; opacity: 0.04;
  }}
"""

    body_html = f"""  <div class="quote-deco" style="top:-100px;left:-60px;width:460px;height:460px;"></div>
  <div class="quote-page">
    <div class="quote-mark">&#x201C;</div>
    <div class="quote-text">{_escape(quote)}</div>
    <div class="quote-attr-row">
      <div class="quote-attr-line"></div>
      <div class="quote-attr-text">{_escape(attribution)}</div>
    </div>
  </div>
  <div class="footer-brand">{_escape(footer)}</div>"""

    return _build_page(t, "quote", css, body_html)


# ═══════════════════════════════════════════════════════════════════════════════
# Card type 4: SUMMARY — checklist + CTA
# ═══════════════════════════════════════════════════════════════════════════════

def build_summary(title: str, checklist: list[str], cta: str = "收藏笔记 · 立即行动",
                  label: str = "今日行动清单", theme_name: str = "cream",
                  footer: str = "房产新媒体获客 · 每日干货") -> str:
    t = pick_theme(theme_name)

    css = f"""
  .summary-page {{
    display: flex; flex-direction: column; justify-content: center;
    height: 100%; padding: 80px 100px 100px; position: relative;
  }}
  .summary-label {{ margin-bottom: 36px; }}
  .summary-title {{
    font-size: 51px; font-weight: 800; line-height: 1.35; letter-spacing: 2px;
    color: {t['text_primary']}; margin-bottom: 50px; max-width: 860px;
  }}
  .summary-list {{ display: flex; flex-direction: column; gap: 24px; margin-bottom: 52px; }}
  .summary-item {{ display: flex; align-items: flex-start; gap: 20px; }}
  .summary-check {{
    width: 41px; height: 41px; border-radius: 50%;
    background: {t['accent']}; color: #fff; flex-shrink: 0;
    display: flex; align-items: center; justify-content: center;
    font-size: 21px; font-weight: 700; margin-top: 2px;
  }}
  .summary-item-text {{
    font-size: 35px; font-weight: 400; line-height: 1.5;
    color: {t['text_secondary']};
  }}
  .summary-cta-box {{
    padding: 32px 44px; border-radius: 20px;
    background: {t['accent_light']}; text-align: center;
    border: 1.5px solid {t['accent']}; border-opacity: 0.2;
  }}
  .summary-cta-text {{
    font-size: 37px; font-weight: 700; color: {t['accent']}; letter-spacing: 2px;
  }}
"""

    items_html = "\n    ".join(
        f"""<div class="summary-item">
      <div class="summary-check">&#x2713;</div>
      <div class="summary-item-text">{_escape(item)}</div>
    </div>"""
        for item in checklist[:5]
    )

    body_html = f"""  <div class="summary-page">
    <div class="summary-label"><div class="badge">{_escape(label)}</div></div>
    <div class="summary-title">{_escape(title)}</div>
    <div class="summary-list">
    {items_html}
    </div>
    <div class="summary-cta-box">
      <div class="summary-cta-text">{_escape(cta)}</div>
    </div>
  </div>
  <div class="footer-brand">{_escape(footer)}</div>"""

    return _build_page(t, "summary", css, body_html)


# ═══════════════════════════════════════════════════════════════════════════════
# Build full post carousel
# ═══════════════════════════════════════════════════════════════════════════════

def build_post_cards(post_data: dict) -> list[str]:
    """Build ordered HTML strings for all cards in a post."""
    cards = []
    kv = post_data.get("key_visual", "cream")

    cards.append(build_cover(
        title=post_data.get("title", ""),
        subtitle=post_data.get("subtitle", ""),
        hero_stat=post_data.get("hero_stat", ""),
        kicker=post_data.get("kicker", ""),
        pre_badge=post_data.get("pre_badge", ""),
        tags=post_data.get("tags", []),
        theme_name=kv,
    ))

    for i, pt in enumerate(post_data.get("points", []), 1):
        cards.append(build_point(
            icon=pt.get("icon", "💡"),
            heading=pt.get("heading", ""),
            body=pt.get("body", ""),
            section_num=pt.get("section_num", f"干货 {i}/{len(post_data.get('points', []))}"),
            highlight_label=pt.get("highlight_label", ""),
            highlight_text=pt.get("highlight", ""),
            theme_name=kv,
        ))

    if post_data.get("quote"):
        q = post_data["quote"]
        cards.append(build_quote(
            quote=q.get("text", ""),
            attribution=q.get("attribution", ""),
            theme_name=kv,
        ))

    if post_data.get("summary"):
        s = post_data["summary"]
        cards.append(build_summary(
            title=s.get("title", ""),
            checklist=s.get("checklist", []),
            cta=s.get("cta", "收藏笔记 · 立即行动"),
            theme_name=kv,
        ))

    return cards


# ═══════════════════════════════════════════════════════════════════════════════
# Render HTML → JPEG
# ═══════════════════════════════════════════════════════════════════════════════

async def _render(html: str, output_path: str) -> str:
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        page = await browser.new_page(viewport={"width": 1080, "height": 1440})
        html_b64 = base64.b64encode(html.encode("utf-8")).decode("ascii")
        await page.goto(f"data:text/html;base64,{html_b64}",
                        wait_until="networkidle", timeout=15_000)
        await page.screenshot(path=output_path, type="jpeg", quality=92,
                              clip={"x": 0, "y": 0, "width": 1080, "height": 1440})
        await browser.close()
    return output_path


def generate_all_for_post(post_data: dict, output_dir: str) -> dict:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    cards_html = build_post_cards(post_data)
    paths = []

    for i, html in enumerate(cards_html):
        fname = "cover.jpg" if i == 0 else f"slide_{i:02d}.jpg"
        path = str(out / fname)
        asyncio.run(_render(html, path))
        paths.append(path)

    return {"cover": paths[0], "slides": paths[1:]}


# ═══════════════════════════════════════════════════════════════════════════════
# Self-test
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import tempfile
    tmp = tempfile.mkdtemp(prefix="xhs_v5_")

    sample = {
        "title": "别再瞎拍了！",
        "subtitle": "一条视频反复拍，客户追着你问房源",
        "hero_stat": "90%",
        "kicker": "的经纪人还在用错误的方法拍视频",
        "pre_badge": "房产获客真相",
        "tags": ["#房产经纪人", "#新媒体获客", "#短视频运营", "#获客技巧"],
        "key_visual": "cream",
        "points": [
            {
                "icon": "🎯", "heading": "找到你的种子视频",
                "body": "翻翻之前发的视频，找播放量最高、评论区有人问「这房子在哪」、有人私信你的那条。它就是你的种子视频。",
                "highlight_label": "💡 关键洞察",
                "highlight": "90%的经纪人拍完就扔，种子视频的价值才刚起步。",
            },
            {
                "icon": "🔄", "heading": "换个包装，反复拍",
                "body": "内容不变，只换包装：换场景、换开头、换形式。同一个配方，不同的摆盘。",
                "highlight_label": "📌 记住",
                "highlight": "算法会把每次重发当成新内容推荐，总有一次踩中流量风口。",
            },
            {
                "icon": "📈", "heading": "30天重复拍10遍",
                "body": "给自己定个小目标：把种子视频用不同形式在30天内反复拍10遍。10遍后回头看，咨询量翻倍。",
            },
        ],
        "quote": {
            "text": "别做视频生产工，要做视频复利家。一条好内容，值得被反复打磨。",
            "attribution": "6年房产新媒体实战经验",
        },
        "summary": {
            "title": "从今天开始，换个打法",
            "checklist": [
                "翻作品集，找到播放量最高的那条",
                "列出3种不同的开头和场景",
                "设定30天拍10遍的小目标",
                "每次发布后记录数据变化",
            ],
            "cta": "收藏这篇 · 评论区打卡你的种子视频",
        },
    }

    result = generate_all_for_post(sample, tmp)
    print(f"Generated {len(result['slides']) + 1} cards:")
    for k, v in result.items():
        if k == "cover":
            print(f"  {k}: {v} ({Path(v).stat().st_size:,} bytes)")
        else:
            for s in v:
                print(f"  slide: {s} ({Path(s).stat().st_size:,} bytes)")
    print(f"\nDir: {tmp}")

    # Also save editable HTML test files
    cards = build_post_cards(sample)
    for i, html in enumerate(cards):
        name = ["cover", "point1", "point2", "point3", "quote", "summary"][i]
        Path(f"test_{name}.html").write_text(html, encoding="utf-8")
    print("Saved test HTML files: test_cover.html, test_point*.html, test_quote.html, test_summary.html")
