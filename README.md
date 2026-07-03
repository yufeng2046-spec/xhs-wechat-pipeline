# 房产新媒体内容分发管线 v1.0

> 从竞品日报到小红书图文 + 公众号长文，全自动 AI 内容分发系统

## 概述

本系统是 CubeMini 每日自动化管线（[competitor-report](https://github.com/yufeng2046/competitor-report)）的扩展模块。每天凌晨 5 点，CubeMini 会自动：

1. 抓取抖音房产竞品视频
2. 转写 + 分析生成竞品日报
3. 策划 5 条短视频脚本
4. **→ 精选 2 条脚本，AI 转化为小红书图文草稿（xhs-pipeline）**
5. **→ 基于竞品日报，AI 撰写公众号深度长文草稿（wechat-pipeline）**

所有草稿保存到平台草稿箱，**人工审核后手动发布**。不自动群发。

## 架构

```
competitor-report/ (CubeMini 每日 5 点 cron)
  daily_pipeline_cm.py
    ├── Step 1-3: 抓取 → 转写 → 入库
    ├── Step 4:   生成竞品日报 (reports/{date}.md)
    ├── Step 5:   策划 5 条视频脚本 (scripts/{date}.md)
    ├── Step 6:   xhs-pipeline      → 小红书图文草稿
    └── Step 7:   wechat-pipeline   → 公众号长文草稿

xhs-pipeline/
  ├── config.py              # 配置（API key 用环境变量）
  ├── content_transformer.py # LLM 脚本 → 小红书卡片文案
  ├── image_generator.py     # HTML+CSS → Playwright 截图 1080×1440
  ├── xhs_login.py           # QR 扫码登录 + cookie 持久化
  ├── xhs_publisher.py       # Playwright 浏览器自动化发布草稿
  └── daily_xhs_pipeline.py  # 每日编排器

wechat-pipeline/
  ├── config.py              # 配置
  ├── content_transformer.py # LLM 日报 → 公众号深度长文（含作者介绍+产品推广）
  ├── md_to_wechat_html.py   # Markdown → 微信兼容 HTML（4 套主题）
  ├── image_generator.py     # HTML+CSS → Playwright 截图 900×500 + 产品卡片
  ├── wechat_publisher.py    # Playwright 浏览器自动化发布草稿到 mp.weixin.qq.com
  └── daily_wechat_pipeline.py # 每日编排器
```

## 小红书管线 (xhs-pipeline)

### 流程

```
scripts/{date}.md (5条脚本)
  → LLM 评分筛选 Top 2（话题热度/视觉化/干货密度/情绪共鸣）
  → LLM 转化：口头脚本 → 小红书图文卡片文案
  → 生成封面图 + 干货卡片（1080×1440, 3:4）
  → Playwright 浏览器自动化 → 保存草稿到 creator.xiaohongshu.com
  → 飞书推送发布摘要
```

### 内容输出

每篇小红书笔记包含 4-6 张卡片：

| 卡片 | 内容 |
|------|------|
| 封面 | 核心数据 + 主标题 + 副标题 + tags |
| 观点卡 ×2-3 | emoji 图标 + 小标题 + 正文 + 金句高亮 |
| 金句卡 | 引用语 + 署名 |
| 总结卡 | 行动清单 checklist + CTA |

### 使用

```bash
# 完整管线
python3 daily_xhs_pipeline.py --date 2026-07-03

# 仅生成文案和图片，不上传
python3 daily_xhs_pipeline.py --date 2026-07-03 --no-upload --no-feishu

# 首次使用需要扫码登录（visible 模式）
python3 xhs_login.py --visible
```

## 公众号管线 (wechat-pipeline)

### 设计理念

与小红书的短卡片不同，公众号采用 **万字长文 + 专家洞察** 的深度内容策略。

- **内容来源**：基于竞品日报的行业数据，但不提"日报"二字
- **人设定位**：于老师（6 年房产新媒体运营专家，原抖音/快手房产运营负责人）
- **文章结构**：作者介绍 → 痛点切入 → 深度拆解 → 行动清单 → 训练营推广
- **排版**：4 套微信兼容 HTML 主题（专业蓝/暖橙/成长绿/暗夜黑），全部 inline style

### 流程

```
reports/{date}.md (竞品日报)
  → LLM 改写为 4000-5000 字深度长文（Markdown）
  → Markdown → 微信兼容 HTML（全 inline style）
  → 生成封面图 900×500 + 产品卡片图 600×800
  → Playwright 浏览器自动化 → 保存草稿到 mp.weixin.qq.com
  → 飞书推送发布摘要
```

### 使用

```bash
# 完整管线
python3 daily_wechat_pipeline.py --date 2026-07-03

# 仅生成文案和图片
python3 daily_wechat_pipeline.py --date 2026-07-03 --no-upload --no-feishu

# 首次需要扫码登录微信公众号后台（visible 模式）
python3 daily_wechat_pipeline.py --date 2026-07-03 --visible
```

## 环境要求

### 依赖

```bash
pip install litellm playwright requests markdown
python3 -m playwright install chromium
```

### 配置

```bash
# 方式一：环境变量
export DEEPSEEK_API_KEY=sk-xxxxxxxx
export FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxxxx

# 方式二：本地配置文件（gitignored）
cp xhs-pipeline/config_local.example.py xhs-pipeline/config_local.py
cp wechat-pipeline/config_local.example.py wechat-pipeline/config_local.py
# 编辑文件填入真实的 API Key
```

### 平台账号

| 平台 | 要求 | 首次操作 |
|------|------|----------|
| 小红书 | 创作者账号 | 用 `--visible` 模式扫码登录，cookie 持久化到 `xhs_profile/` |
| 微信公众号 | 公众号后台账号 | 用 `--visible` 模式扫码登录，cookie 持久化到 `wechat_profile/` |

## 关键设计

### 浏览器自动化

- **Persistent Context**：Playwright 使用 `launch_persistent_context`，登录状态持久化
- **反检测**：注入 stealth JS（屏蔽 webdriver 检测、强制 Shadow DOM open 模式）
- **分离 Profile**：小红书和公众号各自独立的浏览器 profile 目录

### LLM 调用

- **模型**：DeepSeek Chat（通过 litellm）
- **温度**：内容生成 0.8（创意），元数据提取 0.7（稳定）
- **Prompt 设计**：每个平台独立 System Prompt，模拟不同人设

### 图片生成

- **技术方案**：HTML+CSS+Playwright 截图 → JPEG 92% 质量
- **优点**：纯代码渲染，无需设计工具，支持中文排版，可精确控制布局

### 飞书通知

- 每个管线完成后推送 interactive card 到飞书群
- 包含标题、摘要、发布状态

## CubeMini 集成

在 `competitor-report/daily_pipeline_cm.py` 中：

```python
# Step 6: XHS 管线
XHS_PIPELINE_SCRIPT = BASE_DIR.parent / "xhs-pipeline" / "daily_xhs_pipeline.py"
ok = run_step("xhs_pipeline",
    [PYTHON, str(XHS_PIPELINE_SCRIPT), "--date", date_str], timeout=1200)

# Step 7: 公众号管线
WECHAT_PIPELINE_SCRIPT = BASE_DIR.parent / "wechat-pipeline" / "daily_wechat_pipeline.py"
ok = run_step("wechat_pipeline",
    [PYTHON, str(WECHAT_PIPELINE_SCRIPT), "--date", date_str], timeout=1200)
```

两个步骤均设为 **warning only**，失败不中断整条管线。

## 部署

```bash
# 1. 克隆仓库
git clone https://github.com/yufeng2046/xhs-wechat-pipeline.git
cd xhs-wechat-pipeline

# 2. 安装依赖
pip install -r requirements.txt
python3 -m playwright install chromium

# 3. 配置密钥
export DEEPSEEK_API_KEY=sk-xxxxxxxx
export FEISHU_WEBHOOK_URL=https://open.feishu.cn/...

# 4. 首次扫码登录（两个平台各一次）
python3 xhs-pipeline/xhs_login.py --visible       # 小红书
# 打开公众号管线，浏览器中扫码登录
python3 wechat-pipeline/daily_wechat_pipeline.py --date $(date +%F) --visible

# 5. 测试运行
python3 xhs-pipeline/daily_xhs_pipeline.py --date $(date +%F) --no-upload --no-feishu
python3 wechat-pipeline/daily_wechat_pipeline.py --date $(date +%F) --no-upload --no-feishu

# 6. 添加到 cron（在 CubeMini 上）
# 已在 competitor-report 的 daily_pipeline_cm.py 中集成，无需额外 cron
```

## 输出目录结构

```
xhs-pipeline/output/{date}/
  ├── xhs_posts.json          # 结构化帖子数据
  └── images/
      └── post_01/
          ├── cover.jpg       # 封面 1080×1440
          ├── slide_01.jpg    # 观点卡
          ├── slide_02.jpg
          ├── slide_03.jpg
          └── slide_04.jpg    # 总结卡

wechat-pipeline/output/{date}/
  └── wechat/
      ├── article.md          # Markdown 原文
      ├── article.html        # 微信兼容 HTML
      ├── cover.jpg           # 封面 900×500
      └── product_card.jpg    # 产品卡片 600×800
```

## 开源参考

本项目参考了以下优秀开源项目：

- [jiji262/wechat-publisher](https://github.com/jiji262/wechat-publisher) — 微信公众号全流程 AI 发布工具
- [doocs/md](https://github.com/doocs/md) — 最全微信 Markdown CSS 主题库
- [baoyu-skills](https://github.com/JimLiu/baoyu-skills) — 宝玉的公众号发布技能组合

## License

MIT
