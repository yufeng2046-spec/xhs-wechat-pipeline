#!/usr/bin/env python3
"""
Content Transformer — Daily competitor report → WeChat long-form article.

Takes the structured daily report (reports/{date}.md) and uses DeepSeek to
rewrite it as a 3000-5000 word deep-dive article for WeChat Official Account.
Audience: real estate agents learning new media customer acquisition.
"""

import re
import json
from datetime import datetime
from pathlib import Path

from litellm import completion

from config import API_KEY, MODEL, ARTICLE_TARGET_CHARS

# ── Article frontmatter ─────────────────────────────────────────────────────────

ARTICLE_META_PROMPT = """你是一个公众号运营专家。根据文章内容，生成以下元数据：

文章全文：
{article}

请输出JSON（不要markdown代码块）：
{{
  "title": "公众号标题（≤32字，吸引眼球，含关键词）",
  "title_options": ["备选标题1", "备选标题2", "备选标题3"],
  "digest": "摘要（≤128字，钩子式，让人想点进去看）",
  "key_visual": "配色关键词（蓝/橙/绿/暖/暗 之一）",
  "tags": ["话题标签1", "话题标签2"]
}}"""


# ── Author bio (fixed, prepended to every article) ─────────────────────────────

AUTHOR_BIO_MD = """
> **关于作者：于老师**
>
> 🏅 原抖音房产内容运营负责人（规则制定者）
> 🏅 原快手理想家城市运营负责人（生态搭建者）
> 🏅 培训赋能数百位房产经纪人（实战导师）
>
> 带领团队全员来自前抖音、前快手核心岗位。一门课，集结两个平台的实战智慧。结合 **AI最前沿技术** 与 **海量房产数据库**，为房产经纪人提供从内容创作到精准获客的全程智能辅助。
"""

# ── Product promo (fixed, appended to every article) ────────────────────────────

PRODUCT_PROMO_MD = """
---

## 🎓 想系统学习？加入「房产新媒体实战训练营」

**4大模块，21天陪跑，从0到1拿到第一单：**

- **❶ 短视频基础** — 账号定位+选题+拍摄剪辑，搞定第一条房产视频
- **❷ 短视频提高** — 表现力+选题优化+数据分析，稳定流量增长
- **❸ 直播基础** — 开播准备+讲盘框架+互动留人，第一次就上手
- **❹ 直播提高** — 直播节奏+留资转化+数据复盘，每场都有线索进线

**21天训练营交付：**
- 📹 4节录播课无限次回看
- 🤖 AI小助手每日推送个性化口播脚本
- 💬 企业微信陪跑群，@于老师亲自答疑
- 🎯 3次打卡提醒+阶段复盘报告

> 💡 **限时特价 ¥29.9**（原价¥299）· 首期限量20人
>
> 📱 下载企业微信，扫码加入于老师组织，回复「**训练营**」报名

---

*每天一篇实战干货，陪你从0到1搞定房产新媒体获客。收藏本文，明天拍视频前拿出来对照一遍。*
"""


# ── Main transform prompt ───────────────────────────────────────────────────────

SYSTEM_PROMPT = """你是一位在房产行业深耕6年的新媒体运营专家，曾在抖音和快手负责房产内容运营，培训过数百位房产经纪人。

你现在经营自己的公众号，每天分享房产经纪人怎么做短视频/直播获客的实战干货。你的读者是全国各地的一线房产经纪人，他们每天很忙、想做短视频但不知道从哪下手、发了视频没流量、开了直播没人看。

## 你的任务

写一篇公众号深度长文，分享你今天对房产新媒体行业的观察和思考。目标是帮读者看完文章后，能立刻用上一个具体方法，明天拍视频就能用。

## 背景素材（仅供你参考，不要在文章里提"日报"或"监测"）

以下是你今天收集到的行业竞品动态信息，作为你写作的素材弹药库：

{report}

## 写作要求

### 结构
1. **开篇引言**（100-150字）：直接切入，用一个大家都有共鸣的痛点或现象开场，快速进入主题
2. **正文**（2500-3500字）：选2-3个关键洞察展开，每个包含：
   - 你看到了什么（具体案例/现象）
   - 为什么重要（底层逻辑）
   - 怎么做（可操作的步骤、模板、脚本框架）
   - 容易踩的坑
3. **今日行动清单**（100-150字）：3条明天就能做的事

### 语气风格
- 你是一个有6年实战经验的前辈，说话直接、有料、不装
- 多用第一人称："我见过太多经纪人...""我之前在抖音的时候..."
- 口语化但不随意，像在跟同行喝咖啡聊天
- 每讲一个道理，跟一个具体案例
- 善用对比："别再说XX，改成XX"

### 格式
- Markdown格式，用 ## / ### 做层级
- 金句用 **加粗**
- 操作步骤用有序列表
- 案例用 > 引用块

### 字数
目标 {target_chars} 字左右。

**重要：不要在文章里出现"日报""监测""竞品""今日监测"等词。你就是行业专家在分享心得，不是在写分析报告。**"""


# ── Title/metadata prompt ───────────────────────────────────────────────────────

ARTICLE_META_PROMPT = """你是一个公众号运营专家。根据以下文章，生成元数据：

文章：
{article}

输出JSON（不要markdown代码块）：
{{
  "title": "公众号标题（≤32字，要有吸引力，含关键词，不要出现日报/监测等词）",
  "title_options": ["备选1", "备选2", "备选3"],
  "digest": "摘要（≤128字，钩子式，让人想点进来看）",
  "key_visual": "配色关键词（蓝/橙/绿 之一）",
  "tags": ["标签1", "标签2"]
}}"""


# ── LLM call ────────────────────────────────────────────────────────────────────

def _call_llm(prompt: str, max_tokens: int = 8192, temperature: float = 0.8) -> str:
    resp = completion(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        api_key=API_KEY,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return resp.choices[0].message.content


# ── Public API ──────────────────────────────────────────────────────────────────

def transform_report_to_article(report_md: str, date_str: str = "") -> dict:
    """
    Transform a daily competitor report into a WeChat long-form article.

    Args:
        report_md: Full markdown content of the daily report (used as reference)
        date_str: Date string for context

    Returns:
        dict with: title, title_options, digest, key_visual, article_md, tags
        The article_md includes author bio (top) and product promo (bottom).
    """
    print("  [1/2] Generating long-form article via LLM...")

    prompt = SYSTEM_PROMPT.format(
        target_chars=ARTICLE_TARGET_CHARS,
        report=report_md,
    )
    article_body = _call_llm(prompt, max_tokens=8192, temperature=0.8)

    if not article_body:
        raise RuntimeError("LLM returned empty article")

    word_count = len(article_body.replace(" ", ""))
    print(f"  ✓ Article body generated ({word_count} chars)")

    print("  [2/2] Generating title options and metadata...")
    meta_prompt = ARTICLE_META_PROMPT.format(article=article_body[:3000])
    meta_raw = _call_llm(meta_prompt, max_tokens=1024, temperature=0.7)

    meta = _parse_meta(meta_raw, article_body)

    # Assemble: bio + body + promo
    full_article = AUTHOR_BIO_MD + "\n\n" + article_body + "\n\n" + PRODUCT_PROMO_MD

    result = {
        "title": meta.get("title", "房产新媒体获客实战干货"),
        "title_options": meta.get("title_options", []),
        "digest": meta.get("digest", ""),
        "key_visual": meta.get("key_visual", "蓝"),
        "tags": meta.get("tags", []),
        "article_md": full_article,
    }
    return result


def _parse_meta(raw: str, article_md: str) -> dict:
    """Parse metadata JSON from LLM response, with fallback."""
    try:
        # Extract JSON block
        json_match = re.search(r"\{[^}]+\}", raw, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))
    except (json.JSONDecodeError, AttributeError):
        pass

    # Fallback: extract title from first line of article
    first_line = article_md.strip().split("\n")[0]
    first_line = re.sub(r"^#+\s*", "", first_line).strip()
    return {
        "title": first_line[:32] if first_line else "房产新媒体获客日报",
        "title_options": [],
        "digest": "",
        "key_visual": "蓝",
        "tags": [],
    }


# ── Test ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    from pathlib import Path

    date_str = sys.argv[1] if len(sys.argv) > 1 else "2026-05-24"
    report_path = Path(__file__).parent.parent / "competitor-report" / "reports" / f"{date_str}.md"

    if not report_path.exists():
        print(f"Report not found: {report_path}")
        sys.exit(1)

    report_md = report_path.read_text()
    result = transform_report_to_article(report_md, date_str)

    print(f"\n=== Title: {result['title']} ===")
    print(f"Digest: {result['digest']}")
    print(f"Theme: {result['key_visual']}")
    print(f"Tags: {result['tags']}")
    print(f"\n--- Article (first 500 chars) ---")
    print(result["article_md"][:500])
