#!/usr/bin/env python3
"""Configuration for XHS content pipeline.

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

# XHS Creator Platform
XHS_LOGIN_URL = "https://creator.xiaohongshu.com/login"
XHS_CREATOR_URL = "https://creator.xiaohongshu.com"
XHS_COOKIES_FILE = str(BASE_DIR / "xhs_cookies.json")

# Persistent browser profile (shared between login and publisher)
XHS_PROFILE_DIR = str(BASE_DIR / "xhs_profile")

# Image dimensions (XHS optimal 3:4)
XHS_COVER_SIZE = (1080, 1440)
XHS_CAROUSEL_SIZE = (1080, 1440)

# Image templates (color palettes keyed by keyword)
TEMPLATES = {
    "professional": {
        "bg_top": (26, 58, 92),
        "bg_bottom": (44, 62, 80),
        "title_fill": (255, 255, 255),
        "title_stroke": (0, 0, 0),
        "title_stroke_width": 5,
        "subtitle_fill": (255, 215, 0),
        "subtitle_stroke": (0, 0, 0),
        "subtitle_stroke_width": 4,
        "brand_fill": (189, 195, 199),
    },
    "growth": {
        "bg_top": (46, 204, 113),
        "bg_bottom": (39, 174, 96),
        "title_fill": (255, 255, 255),
        "title_stroke": (0, 0, 0),
        "title_stroke_width": 5,
        "subtitle_fill": (255, 255, 255),
        "subtitle_stroke": (0, 0, 0),
        "subtitle_stroke_width": 3,
        "brand_fill": (200, 247, 197),
    },
    "warning": {
        "bg_top": (230, 126, 34),
        "bg_bottom": (211, 84, 0),
        "title_fill": (255, 255, 255),
        "title_stroke": (0, 0, 0),
        "title_stroke_width": 5,
        "subtitle_fill": (255, 255, 255),
        "subtitle_stroke": (0, 0, 0),
        "subtitle_stroke_width": 3,
        "brand_fill": (245, 203, 167),
    },
    "default": {
        "bg_top": (44, 62, 80),
        "bg_bottom": (52, 73, 94),
        "title_fill": (255, 255, 255),
        "title_stroke": (0, 0, 0),
        "title_stroke_width": 5,
        "subtitle_fill": (236, 240, 241),
        "subtitle_stroke": (0, 0, 0),
        "subtitle_stroke_width": 3,
        "brand_fill": (189, 195, 199),
    },
}

# Number of scripts to select and publish daily
DAILY_SCRIPT_LIMIT = 2
