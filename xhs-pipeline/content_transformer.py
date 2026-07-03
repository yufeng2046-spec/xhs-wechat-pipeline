#!/usr/bin/env python3
"""
Content Transformer — parse video scripts and transform into XHS 图文 posts.

- ScriptParser: extracts individual scripts from scripts/{date}.md
- ScriptSelector: LLM scores scripts for XHS suitability, picks top 2
- XHSTransformer: LLM transforms a video script into XHS-optimized 图文 post
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from litellm import completion

from config import API_KEY, MODEL, DAILY_SCRIPT_LIMIT

# ── Data classes ────────────────────────────────────────────────────────────

@dataclass
class Script:
    index: int
    title: str
    duration: str
    core_tip: str
    hook: str
    tips: list[dict] = field(default_factory=list)  # [{"label": "干货1: ...", "body": "..."}]
    cta: str = ""
    full_text: str = ""

@dataclass
class XHSPost:
    """Rich structured data for multi-card XHS post generation."""
    title: str              # Cover main title (≤14 chars)
    subtitle: str           # Cover subtitle (≤30 chars)
    hero_stat: str          # Hero number/stat (e.g. "90%", "0客户")
    kicker: str             # Pain-point kicker paired with hero_stat (e.g. "的经纪人还在瞎拍")
    pre_badge: str          # Top badge text (e.g. "干货预警")
    tags: list[str]         # 5-8 hashtags
    key_visual: str         # Theme description for color selection
    points: list[dict] = field(default_factory=list)
    # Each point: {"icon": "🎯", "heading": "...", "body": "...", "highlight": "(optional)"}
    quote: dict = field(default=None)
    # {"text": "...", "attribution": "..."}
    summary: dict = field(default=None)
    # {"title": "...", "checklist": [...], "cta": "..."}
    source_script: Script = field(default=None)

    def to_card_data(self) -> dict:
        """Convert to dict format expected by image_generator.build_post_cards()."""
        return {
            "title": self.title,
            "subtitle": self.subtitle,
            "hero_stat": self.hero_stat,
            "kicker": self.kicker,
            "pre_badge": self.pre_badge,
            "tags": self.tags,
            "key_visual": self.key_visual,
            "points": self.points,
            "quote": self.quote,
            "summary": self.summary,
        }


# ── Script Parser ────────────────────────────────────────────────────────────

def parse_scripts_md(md_path: str) -> list[Script]:
    """Parse content_planner.py output into individual Script objects."""
    text = Path(md_path).read_text(encoding="utf-8")

    # Split on ### 脚本N： or ## 脚本N：
    blocks = re.split(r"\n(?=#{2,3} 脚本\d+[：:])", text)
    scripts = []

    for block in blocks:
        # Extract script number
        m = re.match(r"#{2,3} 脚本(\d+)[：:]\s*【?(.+?)】?\s*$", block, re.MULTILINE)
        if not m:
            continue
        idx = int(m.group(1))
        title = m.group(2).strip().rstrip("】").strip()

        # Extract duration
        dur_m = re.search(r"⏱\s*时长[：:]\s*(\d+秒)", block)
        duration = dur_m.group(1) if dur_m else "?"

        # Extract core tip
        tip_m = re.search(r"🎯\s*核心干货[：:]\s*(.+?)(?:\n|$)", block)
        core_tip = tip_m.group(1).strip() if tip_m else ""

        # Extract opening hook
        hook = ""
        hook_m = re.search(r"\*\*开场钩子\*\*[：:]?\s*\n(.+?)(?=\n\*\*)", block, re.DOTALL)
        if hook_m:
            hook = hook_m.group(1).strip()

        # Extract 干货 sections
        tips = []
        for tm in re.finditer(r"\*\*(干货\d+[：:]\s*.+?)\*\*\s*\n(.+?)(?=\n\*\*|\n\*\*结尾|\Z)", block, re.DOTALL):
            tips.append({"label": tm.group(1).strip(), "body": tm.group(2).strip()})

        # Extract CTA
        cta = ""
        cta_m = re.search(r"\*\*结尾CTA\*\*[：:]?\s*\n(.+?)(?=\n---|\Z)", block, re.DOTALL)
        if cta_m:
            cta = cta_m.group(1).strip()

        scripts.append(Script(
            index=idx,
            title=title,
            duration=duration,
            core_tip=core_tip,
            hook=hook,
            tips=tips,
            cta=cta,
            full_text=block.strip(),
        ))

    scripts.sort(key=lambda s: s.index)
    return scripts


# ── LLM Helpers ──────────────────────────────────────────────────────────────

def _call_llm(prompt: str, max_tokens: int = 4096, temperature: float = 0.8) -> str:
    resp = completion(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        api_key=API_KEY,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return resp.choices[0].message.content


# ── Script Selector ──────────────────────────────────────────────────────────

SELECTOR_PROMPT = """你是一个小红书内容运营专家。从以下5个房产经纪人培训脚本中，选出最适合发小红书的2个。

评分标准（每项1-5分）：
1. 话题热度：这个话题在小红书上是否有讨论度
2. 视觉化程度：内容是否容易用图片展示（对比：纯理论 vs 可展示步骤/场景）
3. 干货密度：有多少条具体的、可操作的方法论
4. 情绪共鸣：标题能否引发房产经纪人的痛点共鸣

对每个脚本打分，然后选出总分最高的2个。

脚本列表：
{scripts}

输出格式（只输出JSON）：
```json
[
  {{"index": 1, "scores": {{"heat": 4, "visual": 5, "density": 4, "emotion": 3}}, "reason": "一句话理由"}},
  ...
]
```"""


def select_best_scripts(scripts: list[Script]) -> list[Script]:
    """Use LLM to score and select the top scripts for XHS publishing."""
    if len(scripts) <= DAILY_SCRIPT_LIMIT:
        return scripts

    summaries = []
    for s in scripts:
        summaries.append(f"### 脚本{s.index}：【{s.title}】\n"
                         f"时长：{s.duration}\n"
                         f"核心干货：{s.core_tip}\n"
                         f"钩子：{s.hook[:100]}...\n")

    prompt = SELECTOR_PROMPT.format(scripts="\n".join(summaries))
    raw = _call_llm(prompt, max_tokens=2048, temperature=0.3)

    # Extract JSON from markdown code block
    json_match = re.search(r"```(?:json)?\s*\n?(.*?)```", raw, re.DOTALL)
    if json_match:
        raw = json_match.group(1)

    try:
        scores = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: take first 2
        print(f"  WARNING: Could not parse LLM scores, falling back to first {DAILY_SCRIPT_LIMIT}")
        return scripts[:DAILY_SCRIPT_LIMIT]

    scored = [(s["index"], sum(s["scores"].values())) for s in scores]
    scored.sort(key=lambda x: x[1], reverse=True)
    selected_indices = {idx for idx, _ in scored[:DAILY_SCRIPT_LIMIT]}

    return [s for s in scripts if s.index in selected_indices]


# ── XHS Transformer ──────────────────────────────────────────────────────────

TRANSFORM_PROMPT = """你是一个小红书房产教育类博主的内容设计师。把短视频口播脚本转化为一套5-7张图文卡片的内容结构。

## 卡片结构设计

**卡片1 - 封面**: 直击房产经纪人痛点。hero数字（如"90%""0个客户""3个月"）+ kicker痛点描述（如"的经纪人还在瞎拍""咨询都没有"）+ 大字标题 + 副标题 + 标签。hero+kicker连读是一句完整的痛点陈述，目标是让经纪人一看到就觉得"说的就是我"

**卡片2-4 - 干货点**: 每张一个核心观点。emoji图标 + 观点标题(≤14字) + 1-2句解释(≤80字) + 可选高亮框（关键洞察/案例/数据）

**卡片5 - 金句**(可选): 一个让人想截图的观点句，大字展示，标注来源

**卡片6 - 行动总结**: 3-5条行动清单(checklist格式) + CTA引导收藏/评论

## 口播转图文规则
- 口语→书面扫读式，保留emoji增强
- 每张卡片只承载一个核心信息
- 标题≤14字，观点标题≤14字
- 标签5-8个，混搭大类+细分

## 原始脚本
**标题**: {title}
**核心干货**: {core_tip}
**开场钩子**: {hook}

**干货内容**:
{tips}

**结尾CTA**: {cta}

输出严格JSON（不要markdown代码块）:
{{
  "title": "封面主标题(≤14字)",
  "subtitle": "封面副标题(≤30字)",
  "hero_stat": "hero数字或短词(如90%、0客户、3个月)",
  "kicker": "痛点陈述，连接hero形成完整痛点句(如'的经纪人还在瞎拍'、'没有一条客户咨询')",
  "pre_badge": "封面小标签(如干货预警、建议收藏)",
  "tags": ["#标签1", "#标签2", "#标签3", "#标签4", "#标签5", "#标签6"],
  "key_visual": "配色关键词(蓝专业/绿实操/橙警示)",
  "points": [
    {{"icon": "🎯", "heading": "观点标题(≤14字)", "body": "1-2句解释(≤80字)", "highlight_label": "💡 关键洞察", "highlight": "一句话亮点/案例/数据(可选，空字符串则不显示)"}}
  ],
  "quote": {{"text": "让人想截图的观点句", "attribution": "来源(如6年房产实战经验)"}},
  "summary": {{"title": "总结标题(≤20字)", "checklist": ["行动项1", "行动项2", "行动项3"], "cta": "引导收藏/评论的话"}}
}}"""


def transform_to_xhs(script: Script) -> XHSPost:
    """Transform one video script into a rich XHS card structure."""
    tips_text = "\n".join(
        f"- {t['label']}: {t['body'][:200]}" for t in script.tips
    ) if script.tips else "（无干货）"

    prompt = TRANSFORM_PROMPT.format(
        title=script.title,
        core_tip=script.core_tip,
        hook=script.hook,
        tips=tips_text,
        cta=script.cta,
    )

    raw = _call_llm(prompt, max_tokens=4096, temperature=0.8)

    # Parse JSON from response
    json_str = raw
    json_match = re.search(r"```(?:json)?\s*\n?(.*?)```", raw, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        print(f"  WARNING: Could not parse LLM output for script {script.index}, using fallback")
        data = _fallback_transform(script)

    # Ensure points have highlight_label if highlight is present
    for pt in data.get("points", []):
        if pt.get("highlight") and not pt.get("highlight_label"):
            pt["highlight_label"] = "💡 关键洞察"

    return XHSPost(
        title=data.get("title", script.title[:14]),
        subtitle=data.get("subtitle", ""),
        hero_stat=data.get("hero_stat", ""),
        kicker=data.get("kicker", ""),
        pre_badge=data.get("pre_badge", "干货预警"),
        tags=data.get("tags", []),
        key_visual=data.get("key_visual", "蓝色专业背景"),
        points=data.get("points", []),
        quote=data.get("quote"),
        summary=data.get("summary"),
        source_script=script,
    )


def _fallback_transform(script: Script) -> dict:
    """Fallback rich card transformation without LLM."""
    points = []
    for t in script.tips[:3]:
        points.append({
            "icon": ["🎯", "💡", "📌"][len(points)] if len(points) < 3 else "💡",
            "heading": t["label"].replace("：", ": ")[:14],
            "body": t["body"][:80],
            "highlight_label": "",
            "highlight": "",
        })

    checklist = [t["label"].replace("：", ": ")[:25] for t in script.tips[:3]]
    if script.cta:
        checklist.append(script.cta[:25])

    return {
        "title": script.title[:14],
        "subtitle": script.hook[:30] if script.hook else script.core_tip[:30],
        "hero_stat": f"{len(script.tips)}步",
        "kicker": "实操方法，学会了就能用",
        "pre_badge": "干货预警",
        "tags": ["#房产经纪人", "#新媒体获客", "#短视频运营", "#房产抖音", "#经纪人转型"],
        "key_visual": "蓝色专业背景",
        "points": points,
        "quote": {"text": script.hook[:80] if script.hook else "", "attribution": "实战经验总结"},
        "summary": {"title": "今日行动", "checklist": checklist[:4], "cta": "收藏这篇，评论区打卡"},
    }


# ── Main entry point (for testing) ───────────────────────────────────────────

def main():
    import sys
    scripts_dir = Path(__file__).resolve().parent.parent / "competitor-report" / "scripts"
    candidates = sorted(scripts_dir.glob("*.md"))
    if not candidates:
        print("No scripts found.")
        return

    path = str(candidates[-1])
    print(f"Parsing: {path}")

    scripts = parse_scripts_md(path)
    print(f"Found {len(scripts)} scripts")

    selected = select_best_scripts(scripts)
    print(f"Selected {len(selected)} scripts:")
    for s in selected:
        print(f"  [{s.index}] {s.title}")

    for s in selected:
        post = transform_to_xhs(s)
        print(f"\n=== Post: {post.title} ===")
        print(f"Body ({len(post.body)} chars): {post.body[:200]}...")
        print(f"Tags: {post.tags}")
        print(f"Key visual: {post.key_visual}")


if __name__ == "__main__":
    main()
