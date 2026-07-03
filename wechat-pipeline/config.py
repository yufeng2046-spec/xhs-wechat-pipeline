#!/usr/bin/env python3
"""Configuration for WeChat Official Account publishing pipeline.

Secrets are read from environment variables. For local development,
create a config.local.py or set env vars:
  export DEEPSEEK_API_KEY=sk-...
  export FEISHU_WEBHOOK_URL=https://...
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
COMPETITOR_DIR = BASE_DIR.parent / "competitor-report"
OUTPUT_DIR = BASE_DIR / "output"

# LLM — use env var or local config
API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek/deepseek-chat")

# Feishu
FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK_URL", "")

# Override from local config file (gitignored)
try:
    from config_local import *  # noqa: F401, F403
except ImportError:
    pass

# WeChat Official Account Platform
WECHAT_MP_URL = "https://mp.weixin.qq.com"
WECHAT_LOGIN_URL = "https://mp.weixin.qq.com"

# Persistent browser profile (separate from XHS)
WECHAT_PROFILE_DIR = str(BASE_DIR / "wechat_profile")

# Image dimensions (WeChat cover)
WECHAT_COVER_SIZE = (900, 500)
WECHAT_JPEG_QUALITY = 92

# Content targets
ARTICLE_MIN_CHARS = 2000
ARTICLE_TARGET_CHARS = 4000

# Author info
AUTHOR_NAME = "于老师"
