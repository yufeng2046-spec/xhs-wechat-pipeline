#!/usr/bin/env python3
"""
Markdown → WeChat HTML Converter.

Converts Markdown to WeChat Official Account compatible HTML with inline CSS.
WeChat strips <style> blocks, class/ID attributes, and external stylesheets,
so all styling must be inline.

Theme system inspired by jiji262/wechat-publisher and doocs/md.
"""

import re
import html as html_mod


# ═══════════════════════════════════════════════════════════════════════════════
# CSS Themes — all styles are inline-safe for WeChat
# ═══════════════════════════════════════════════════════════════════════════════

THEMES = {
    "blue": {
        "name": "专业蓝",
        "page": "background-color:#F5F6FA;padding:16px;max-width:680px;margin:0 auto;",
        "h2": "font-size:22px;font-weight:700;color:#1E3A5F;margin:28px 0 14px;padding-left:12px;border-left:4px solid #3B5998;line-height:1.5;",
        "h3": "font-size:18px;font-weight:700;color:#2D4A7A;margin:22px 0 10px;line-height:1.5;",
        "h4": "font-size:16px;font-weight:600;color:#3B5998;margin:16px 0 8px;line-height:1.5;",
        "p": "font-size:15px;color:#2D2D2D;line-height:1.85;margin:0 0 16px;text-align:justify;",
        "strong": "color:#1E3A5F;font-weight:700;",
        "blockquote": "margin:16px 0;padding:12px 16px;background-color:#EDF1F8;border-left:4px solid #3B5998;color:#4A628A;font-size:14px;line-height:1.7;border-radius:0 4px 4px 0;",
        "ul": "margin:12px 0;padding-left:20px;font-size:15px;color:#2D2D2D;line-height:1.85;",
        "ol": "margin:12px 0;padding-left:20px;font-size:15px;color:#2D2D2D;line-height:1.85;",
        "li": "margin-bottom:6px;",
        "hr": "border:none;border-top:1px solid #E0E6F0;margin:24px 0;",
        "a": "color:#3B5998;text-decoration:none;border-bottom:1px solid #3B5998;",
    },
    "orange": {
        "name": "暖橙",
        "page": "background-color:#FDF8F0;padding:16px;max-width:680px;margin:0 auto;",
        "h2": "font-size:22px;font-weight:700;color:#C0502A;margin:28px 0 14px;padding-left:12px;border-left:4px solid #E8784A;line-height:1.5;",
        "h3": "font-size:18px;font-weight:700;color:#D4663A;margin:22px 0 10px;line-height:1.5;",
        "h4": "font-size:16px;font-weight:600;color:#E8784A;margin:16px 0 8px;line-height:1.5;",
        "p": "font-size:15px;color:#2D2D2D;line-height:1.85;margin:0 0 16px;text-align:justify;",
        "strong": "color:#C0502A;font-weight:700;",
        "blockquote": "margin:16px 0;padding:12px 16px;background-color:#FFF5EE;border-left:4px solid #E8784A;color:#8B5E3C;font-size:14px;line-height:1.7;border-radius:0 4px 4px 0;",
        "ul": "margin:12px 0;padding-left:20px;font-size:15px;color:#2D2D2D;line-height:1.85;",
        "ol": "margin:12px 0;padding-left:20px;font-size:15px;color:#2D2D2D;line-height:1.85;",
        "li": "margin-bottom:6px;",
        "hr": "border:none;border-top:1px solid #F0E4D4;margin:24px 0;",
        "a": "color:#E8784A;text-decoration:none;border-bottom:1px solid #E8784A;",
    },
    "green": {
        "name": "成长绿",
        "page": "background-color:#F6F8F4;padding:16px;max-width:680px;margin:0 auto;",
        "h2": "font-size:22px;font-weight:700;color:#3D6B3A;margin:28px 0 14px;padding-left:12px;border-left:4px solid #5B8C5A;line-height:1.5;",
        "h3": "font-size:18px;font-weight:700;color:#4A7A47;margin:22px 0 10px;line-height:1.5;",
        "h4": "font-size:16px;font-weight:600;color:#5B8C5A;margin:16px 0 8px;line-height:1.5;",
        "p": "font-size:15px;color:#2D332C;line-height:1.85;margin:0 0 16px;text-align:justify;",
        "strong": "color:#3D6B3A;font-weight:700;",
        "blockquote": "margin:16px 0;padding:12px 16px;background-color:#EEF4EC;border-left:4px solid #5B8C5A;color:#5A7A57;font-size:14px;line-height:1.7;border-radius:0 4px 4px 0;",
        "ul": "margin:12px 0;padding-left:20px;font-size:15px;color:#2D332C;line-height:1.85;",
        "ol": "margin:12px 0;padding-left:20px;font-size:15px;color:#2D332C;line-height:1.85;",
        "li": "margin-bottom:6px;",
        "hr": "border:none;border-top:1px solid #E0E8DC;margin:24px 0;",
        "a": "color:#5B8C5A;text-decoration:none;border-bottom:1px solid #5B8C5A;",
    },
    "dark": {
        "name": "暗夜黑",
        "page": "background-color:#1A1A1A;padding:16px;max-width:680px;margin:0 auto;",
        "h2": "font-size:22px;font-weight:700;color:#E8E8E8;margin:28px 0 14px;padding-left:12px;border-left:4px solid #E8784A;line-height:1.5;",
        "h3": "font-size:18px;font-weight:700;color:#D0D0D0;margin:22px 0 10px;line-height:1.5;",
        "h4": "font-size:16px;font-weight:600;color:#C0C0C0;margin:16px 0 8px;line-height:1.5;",
        "p": "font-size:15px;color:#C8C8C8;line-height:1.85;margin:0 0 16px;text-align:justify;",
        "strong": "color:#E8784A;font-weight:700;",
        "blockquote": "margin:16px 0;padding:12px 16px;background-color:#2A2A2A;border-left:4px solid #E8784A;color:#A0A0A0;font-size:14px;line-height:1.7;border-radius:0 4px 4px 0;",
        "ul": "margin:12px 0;padding-left:20px;font-size:15px;color:#C8C8C8;line-height:1.85;",
        "ol": "margin:12px 0;padding-left:20px;font-size:15px;color:#C8C8C8;line-height:1.85;",
        "li": "margin-bottom:6px;",
        "hr": "border:none;border-top:1px solid #333;margin:24px 0;",
        "a": "color:#E8784A;text-decoration:none;border-bottom:1px solid #E8784A;",
    },
}


def pick_theme(keywords: str) -> tuple:
    """Pick a theme by keyword matching. Returns (theme_name, theme_dict)."""
    kw = keywords.lower()
    if any(w in kw for w in ["暗", "黑", "dark", "night"]):
        return ("dark", THEMES["dark"])
    if any(w in kw for w in ["蓝", "专业", "navy", "pro", "企业", "信任"]):
        return ("blue", THEMES["blue"])
    if any(w in kw for w in ["橙", "暖", "warm", "blush", "红", "情感"]):
        return ("orange", THEMES["orange"])
    if any(w in kw for w in ["绿", "增长", "成长", "green", "sage", "干货", "实操"]):
        return ("green", THEMES["green"])
    return ("blue", THEMES["blue"])  # default


# ═══════════════════════════════════════════════════════════════════════════════
# Markdown → HTML Converter
# ═══════════════════════════════════════════════════════════════════════════════

def convert(md_text: str, theme_name: str = "blue", title: str = "",
            author: str = "", digest: str = "") -> str:
    """
    Convert Markdown to WeChat-compatible HTML.

    Args:
        md_text: Raw Markdown article
        theme_name: One of 'blue', 'orange', 'green', 'dark'
        title: Article title (wrapped in h1 with special styling)
        author: Author name
        digest: Article summary/abstract

    Returns:
        Full HTML string with inline styles, WeChat-safe
    """
    theme = THEMES.get(theme_name, THEMES["blue"])
    body = _md_to_html(md_text, theme)

    html = f"""<section style="{theme['page']}">
<h1 style="font-size:24px;font-weight:800;color:#1A1A1A;text-align:center;line-height:1.4;margin:8px 0 20px;padding:0 8px;">{html_mod.escape(title)}</h1>
<p style="font-size:13px;color:#999;text-align:center;margin:0 0 6px;">{html_mod.escape(author)}</p>
<p style="font-size:12px;color:#B0B0B0;text-align:center;margin:0 0 24px;padding:0 16px;line-height:1.6;">{html_mod.escape(digest)}</p>
{body}
<hr style="border:none;border-top:1px solid #E0E0E0;margin:32px 0 12px;">
<p style="font-size:12px;color:#B0B0B0;text-align:center;line-height:1.6;">— END —</p>
<p style="font-size:11px;color:#C0C0C0;text-align:center;margin-top:4px;">AI新媒体实战笔记 · 每日更新房产获客干货</p>
</section>"""
    return html


def _md_to_html(md_text: str, theme: dict) -> str:
    """Convert Markdown body to WeChat-safe HTML with inline styles."""
    lines = md_text.split("\n")
    result = []
    i = 0

    # Skip the first heading if it's the title (already rendered separately)
    if lines and lines[0].startswith("# ") and not lines[0].startswith("## "):
        i = _skip_title_section(lines, 0)

    in_list = None  # 'ul' or 'ol' or None
    list_tag = ""

    while i < len(lines):
        line = lines[i]

        # Skip title candidates (will be rendered in header)
        if line.startswith("# ") and not line.startswith("## "):
            i = _skip_title_section(lines, i)
            continue

        # Blank line: close current list if any
        if not line.strip():
            if in_list:
                result.append(f"</{in_list}>")
                in_list = None
            i += 1
            continue

        # Horizontal rule
        if line.strip() in ("---", "***", "___", "* * *"):
            if in_list:
                result.append(f"</{in_list}>")
                in_list = None
            result.append(f'<hr style="{theme["hr"]}">')
            i += 1
            continue

        # h2 - ## heading
        if line.startswith("## ") and not line.startswith("### "):
            if in_list:
                result.append(f"</{in_list}>")
                in_list = None
            text = _process_inline(line[3:], theme)
            result.append(f'<h2 style="{theme["h2"]}">{text}</h2>')
            i += 1
            continue

        # h3 - ### heading
        if line.startswith("### "):
            if in_list:
                result.append(f"</{in_list}>")
                in_list = None
            text = _process_inline(line[4:], theme)
            result.append(f'<h3 style="{theme["h3"]}">{text}</h3>')
            i += 1
            continue

        # h4 - #### heading
        if line.startswith("#### "):
            if in_list:
                result.append(f"</{in_list}>")
                in_list = None
            text = _process_inline(line[5:], theme)
            result.append(f'<h4 style="{theme["h4"]}">{text}</h4>')
            i += 1
            continue

        # Blockquote
        if line.startswith("> "):
            if in_list:
                result.append(f"</{in_list}>")
                in_list = None
            quote_lines = []
            while i < len(lines) and lines[i].startswith("> "):
                quote_lines.append(lines[i][2:])
                i += 1
            quote_text = "<br>".join(html_mod.escape(t) for t in quote_lines)
            quote_text = _process_inline_escaped(quote_text, theme)
            result.append(f'<blockquote style="{theme["blockquote"]}">{quote_text}</blockquote>')
            continue

        # Unordered list
        if re.match(r"^[\-\*]\s", line):
            if in_list != "ul":
                if in_list:
                    result.append(f"</{in_list}>")
                result.append(f'<ul style="{theme["ul"]}">')
                in_list = "ul"
            text = _process_inline(re.sub(r"^[\-\*]\s+", "", line), theme)
            result.append(f'<li style="{theme["li"]}">{text}</li>')
            i += 1
            continue

        # Ordered list
        ol_match = re.match(r"^(\d+)\.\s", line)
        if ol_match:
            if in_list != "ol":
                if in_list:
                    result.append(f"</{in_list}>")
                result.append(f'<ol style="{theme["ol"]}">')
                in_list = "ol"
            text = _process_inline(line[ol_match.end():], theme)
            result.append(f'<li style="{theme["li"]}">{text}</li>')
            i += 1
            continue

        # Image placeholder
        img_match = re.match(r"^!\[([^\]]*)\]\(([^\)]+)\)", line.strip())
        if img_match:
            alt = img_match.group(1)
            src = img_match.group(2)
            style = "max-width:100%;height:auto;display:block;margin:16px auto;border-radius:4px;"
            result.append(f'<img src="{src}" alt="{html_mod.escape(alt)}" style="{style}">')
            i += 1
            continue

        # Regular paragraph
        if in_list:
            result.append(f"</{in_list}>")
            in_list = None
        text = _process_inline(line, theme)
        if text.strip():
            result.append(f'<p style="{theme["p"]}">{text}</p>')
        i += 1

    if in_list:
        result.append(f"</{in_list}>")

    return "\n".join(result)


def _skip_title_section(lines: list, start: int) -> int:
    """Skip the # heading and any following metadata lines (date, author etc)."""
    i = start + 1
    while i < len(lines) and lines[i].strip():
        stripped = lines[i].strip()
        # Skip subtitle, date, author lines
        if any(stripped.startswith(p) for p in ("所属", "日期", "作者", "摘要", ">", "所属")):
            i += 1
            continue
        # skip frontmatter-like metadata
        if "：" in stripped and len(stripped) < 60:
            i += 1
            continue
        break
    return i


def _process_inline(text: str, theme: dict) -> str:
    """Process inline Markdown: bold, italic, code, links."""
    text = html_mod.escape(text)

    # Bold: **text** or __text__
    text = re.sub(
        r"\*\*(.+?)\*\*",
        lambda m: f'<strong style="{theme["strong"]}">{m.group(1)}</strong>',
        text
    )
    text = re.sub(
        r"__(.+?)__",
        lambda m: f'<strong style="{theme["strong"]}">{m.group(1)}</strong>',
        text
    )

    # Italic: *text* or _text_
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    text = re.sub(r"_(.+?)_", r"<em>\1</em>", text)

    # Inline code: `code`
    text = re.sub(
        r"`([^`]+)`",
        r'<code style="background-color:#F0F0F0;padding:2px 6px;border-radius:3px;font-family:monospace;font-size:13px;">\1</code>',
        text,
    )

    # Links: [text](url)
    text = re.sub(
        r"\[([^\]]+)\]\(([^\)]+)\)",
        lambda m: f'<a href="{m.group(2)}" style="{theme["a"]}">{m.group(1)}</a>',
        text,
    )

    return text


def _process_inline_escaped(escaped_text: str, theme: dict) -> str:
    """Process inline formatting on already-escaped text (for blockquotes etc)."""
    text = escaped_text

    text = re.sub(
        r"\*\*(.+?)\*\*",
        lambda m: f'<strong style="{theme["strong"]}">{m.group(1)}</strong>',
        text
    )

    return text


# ── Test ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from pathlib import Path
    sample_md = """## 今日概览

今日监测7个账号，共发布7条视频，总互动量235次。

> 核心结论：方法论类内容占据100%账号核心方向，但互动分化明显。

## 深度拆解

### "小博主"定位是获客的黄金切入点

**房产说理老米**的一条视频拿了94赞20评，远超其他账号。

说白了就是：用户对"成为大V"已经麻木了，但"先做个小博主"这个承诺更可信、更有操作感。

1. 降低用户的行动门槛
2. 用"小"字做差异化
3. 展示真实案例而非讲大道理

## 行动清单

- 明天试着把"大V"改成"小博主"
- 评论区找3个真实问题做下期选题
"""

    html = convert(sample_md, theme_name="blue",
                   title="房产经纪人获客日报：方法论内卷下的突围之道",
                   author="AI新媒体实战笔记",
                   digest="7个账号7条视频的竞争分析，帮你找到下一个爆款方向。")

    print(html[:500])
    print("...")

    # Also save for preview
    out = Path(__file__).parent / "output" / "test_wechat.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"\nSaved to {out}")
