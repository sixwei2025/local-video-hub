#!/opt/homebrew/bin/python3.11
# -*- coding: utf-8 -*-
"""汇芯 · 高级感视频封面双画幅渲染引擎 (render_video_cover.py)

专为「竖屏 3:4 独立封面 (1080×1440 / 2160×2880) + 横屏 16:9 成片首帧 (1920×1080)」打造。
彻底淘汰 2010 年代电商五段金色渐变 + 3D 发光球 + 粗暴纯色大字报，融合 GitHub 四大高审美封面范式：
  1. op7418/guizang-social-card-skill (Editorial Magazine 杂志风 + Swiss International 瑞士网格风 +「越大越细」字重铁律)
  2. joeseesun/qiaomu-html-cover (0.5 秒停留测试 + 单一视觉所有者 + 离线 CJK 可变字体确定性排版)
  3. ponyodong2026/ponyo-cover-anchor-system (点击率 = 信息密度 × 视觉锚点：人像 / 巨型数字 / 真实界面 / 观点宣言)
  4. WhiteTowerAI/cut-as-code (Almanac / Editorial / Swiss Grid 内容卡片设计 Token)

支持 6 套主题 (Themes)：
  - swiss_dark  : 暗夜瑞士网格 (#0A0A0C + #F2F0ED + #C8102E 汇芯红 + 72px 建筑网格) —— AI 工具 / GitHub 开源 / 硬核实操默认
  - midnight    : 午夜墨 (#0E0D0C + #ECE2CF 暖白 + #D4A04A 香槟金 + 胶片颗粒) —— 深度复盘 / 商业变现 / 深夜长谈
  - paper       : 纸本墨 (#F1EFEA 暖灰纸 + #0A0A0B 浓墨 + #C8102E 汇芯红锚点) —— 方法论 / 教程清单 / 认知升级
  - kraft       : 牛皮纸 (#EEDFC7 大地色 + #2A1E13 深褐 + #9B5A2E 焦糖) —— 个人故事 / 踩坑复盘 / 案例拆解
  - indigo      : 靛蓝瓷 (#F1F3F5 冷白 + #0A1F3D 深海蓝 + #315D93 靛蓝) —— SaaS 演示 / 技术架构 / 评测对比
  - swiss_klein : 瑞士克莱因蓝 (#FAFAF8 + #0A0A0A + #002FA7 克莱因蓝顶栏与锚点) —— 榜单盘点 / 极客发布 / 纯数据横评
  - brand       : 汇芯红 (#FAF7F4 米白暖纸 + #1A1A1A + #C8102E 汇芯红) —— 汇芯品牌标准白底红锚点

支持 4 大版式原型 (Layouts)：
  - editorial-portrait : 杂志人像锚点风（袁总精修抠像 + 选择性高光压缩严禁纯黑白 + 纸色渐变过渡 + 衬线/无衬线混排）
  - swiss-metric       : 瑞士巨型数字风（72px 建筑网格 + 260~320px Tabular 巨型数字/符号 + 双行高对比钩子）
  - ui-showcase        : 真实界面画框风（上方 44% 瑞士/杂志排版大字 + 下方 56% 真实软件截图/关键帧 macOS 极简画框）
  - manifesto-poster   : 极简宣言大字风（Paula Scher / Müller-Brockmann 瑞士网格大字报 + 建筑感留白与微缩编号）

双画幅同步输出（一次调用同时产出）：
  1. cover-3x4.png / cover-3x4.jpg (1080×1440，支持 --dpr 2 输出 2160×2880 超清)：用于视频号/小红书/B站/video-hub 竖版 3:4 封面。
  2. cover-opening.png / cover-16x9.png (1920×1080)：用于 16:9 横屏视频前 0.01s~0.2s 首帧，且支持「中央 810×1080 (3:4) 安全区保护」，哪怕平台直接从 16:9 第一帧居中裁 3:4 也绝不切掉一个字！

用法：
  python3 render_video_cover.py --title "全自动剪辑流水线|3分钟出成片" --kicker "OPENMONTAGE · 实操" --metric "322K★" --theme swiss_dark --out cover/
  python3 render_video_cover.py --brief cover_brief.json --out cover/
  python3 render_video_cover.py --demo --out /tmp/video_cover_demo
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent

# 自动寻址人像抠图与面部坐标（跨 skill 共享）
CUTOUT_CANDIDATES = [
    SKILL_ROOT / "assets" / "owner_cutout_hd.png",
    Path.home() / ".gemini/skills/wechat-autopilot/skills/wechat-cover-skill/assets/owner_cutout_hd.png",
    Path.home() / ".codex/skills/auto-tutorial/assets/owner_cutout_hd.png",
    Path.home() / ".agents/skills/talking-head-video/assets/owner_cutout_hd.png",
]
FONT_CANDIDATES = [
    SKILL_ROOT / "assets" / "fonts" / "NotoSansSC-VF.ttf",
    Path.home() / ".codex/skills/auto-tutorial/assets/fonts/NotoSansSC-VF.ttf",
]

SERIF = '"Songti SC","STSong","Source Han Serif SC","Noto Serif CJK SC",serif'
SANS = '"NotoSansVF","PingFang SC","Hiragino Sans GB","Source Han Sans SC","Noto Sans CJK SC",sans-serif'
LATIN = '"Helvetica Neue","Inter","SF Pro Display","Arial",sans-serif'
MONO = '"JetBrains Mono","SF Mono","Menlo","Consolas",monospace'


# ============================================================ 主题 Token 表
THEMES = {
    "swiss_dark": dict(
        name="暗夜瑞士网格",
        paper="#0A0A0C", paper2="#151419", ink="#F2F0ED",
        accent="#C8102E", accent_sub="#E8B84B",
        muted="rgba(242,240,237,.54)", hair="rgba(242,240,237,.13)",
        grid="rgba(255,255,255,.045)",
        family=SANS, weight=700, accent_weight=900, track="-0.03em",
        brand_family=LATIN, brand_weight=500, brand_track="0.10em",
        small_family=MONO, small_weight=600, small_track="0.16em",
        portrait="warm_dark", grain=True, show_grid=True, top_bar=False,
        use="AI 工具 · GitHub 开源 · 实操教程（默认首选）",
    ),
    "midnight": dict(
        name="午夜墨",
        paper="#0E0D0C", paper2="#1B1712", ink="#ECE2CF",
        accent="#D4A04A", accent_sub="#C8102E",
        muted="rgba(236,226,207,.50)", hair="rgba(236,226,207,.18)",
        grid="rgba(236,226,207,.035)",
        family=SERIF, weight=500, accent_weight=600, track="-0.01em",
        brand_family=LATIN, brand_weight=300, brand_track="0.13em",
        small_family=LATIN, small_weight=500, small_track="0.22em",
        portrait="warm_dark", grain=True, show_grid=False, top_bar=False,
        use="数据复盘 · 商业搞钱 · 深度长谈",
    ),
    "paper": dict(
        name="纸本墨",
        paper="#F1EFEA", paper2="#E5E0D5", ink="#0A0A0B",
        accent="#C8102E", accent_sub="#0A0A0B",
        muted="rgba(10,10,11,.52)", hair="rgba(10,10,11,.18)",
        grid="rgba(10,10,11,.045)",
        family=SERIF, weight=600, accent_weight=700, track="-0.015em",
        brand_family=LATIN, brand_weight=400, brand_track="0.12em",
        small_family=MONO, small_weight=600, small_track="0.18em",
        portrait="muted", grain=True, show_grid=True, top_bar=False,
        use="方法论 · 认知升级 · 极简教程",
    ),
    "kraft": dict(
        name="牛皮纸",
        paper="#EEDFC7", paper2="#E0CCB0", ink="#2A1E13",
        accent="#9B5A2E", accent_sub="#C8102E",
        muted="rgba(42,30,19,.56)", hair="rgba(42,30,19,.20)",
        grid="rgba(42,30,19,.04)",
        family=SERIF, weight=600, accent_weight=700, track="-0.01em",
        brand_family=LATIN, brand_weight=400, brand_track="0.12em",
        small_family=LATIN, small_weight=600, small_track="0.20em",
        portrait="warm_muted", grain=True, show_grid=False, top_bar=False,
        use="个人经历 · 踩坑复盘 · 创业故事",
    ),
    "indigo": dict(
        name="靛蓝瓷",
        paper="#F1F3F5", paper2="#E1E8F0", ink="#0A1F3D",
        accent="#315D93", accent_sub="#C8102E",
        muted="rgba(10,31,61,.52)", hair="rgba(10,31,61,.18)",
        grid="rgba(10,31,61,.045)",
        family=SANS, weight=600, accent_weight=800, track="-0.02em",
        brand_family=LATIN, brand_weight=400, brand_track="0.11em",
        small_family=MONO, small_weight=600, small_track="0.18em",
        portrait="cool", grain=False, show_grid=True, top_bar=False,
        use="SaaS 产品 · 企业落地 · 技术评测",
    ),
    "swiss_klein": dict(
        name="瑞士克莱因蓝",
        paper="#FAFAF8", paper2="#EEF1F8", ink="#0A0A0A",
        accent="#002FA7", accent_sub="#C8102E",
        muted="rgba(10,10,10,.50)", hair="rgba(10,10,10,.16)",
        grid="rgba(0,47,167,.05)",
        family=SANS, weight=600, accent_weight=800, track="-0.025em",
        brand_family=LATIN, brand_weight=500, brand_track="0.10em",
        small_family=MONO, small_weight=600, small_track="0.16em",
        portrait="muted", grain=False, show_grid=True, top_bar=True,
        use="产品发布 · 榜单盘点 · 极客横评",
    ),
    "brand": dict(
        name="汇芯红",
        paper="#FAF7F4", paper2="#F0EAE3", ink="#161514",
        accent="#C8102E", accent_sub="#161514",
        muted="rgba(22,21,20,.52)", hair="rgba(22,21,20,.16)",
        grid="rgba(200,16,46,.04)",
        family=SERIF, weight=600, accent_weight=700, track="-0.015em",
        brand_family=LATIN, brand_weight=400, brand_track="0.12em",
        small_family=LATIN, small_weight=600, small_track="0.20em",
        portrait="normal", grain=False, show_grid=False, top_bar=True,
        use="汇芯品牌通用 · 政企交付 · 课程宣发",
    ),
}

SHADOW = {
    "swiss_dark":  "drop-shadow(-42px 12px 76px rgba(0,0,0,.68))",
    "midnight":    "drop-shadow(-48px 10px 82px rgba(0,0,0,.62))",
    "paper":       "drop-shadow(-20px 8px 42px rgba(0,0,0,.12))",
    "kraft":       "drop-shadow(-24px 8px 46px rgba(60,40,20,.16))",
    "indigo":      "drop-shadow(-20px 8px 42px rgba(10,31,61,.13))",
    "swiss_klein": "drop-shadow(-18px 6px 38px rgba(0,0,0,.11))",
    "brand":       "drop-shadow(-20px 8px 42px rgba(0,0,0,.12))",
}

# ============================================================ 汇芯品牌标准视频封面 6 大预设家族 (HUIXIN BRAND PRESETS)
BRAND_PRESETS = {
    "huixin-founder-gold": dict(
        name="汇芯 · 创始人黑金杂志风",
        theme="midnight",
        layout="editorial-portrait",
        portrait=True,
        kicker="袁六伟 · 一人AI公司实战复盘",
        brand="HUIXIN AI",
        strip_left="袁六伟 · 台州汇芯",
        strip_right="学员 7000+ · 企业客户 100+",
        use="个人 IP 故事 · 创业复盘 · 深度商业认知（主力人像黑金版）",
    ),
    "huixin-tech-flagship": dict(
        name="汇芯 · 暗夜瑞士黑红科技风",
        theme="swiss_dark",
        layout="swiss-metric",
        portrait=False,
        kicker="HUIXIN OPEN SOURCE · 旗舰发布",
        brand="AI WORKFLOW",
        strip_left="袁六伟 · 台州汇芯",
        strip_right="GITHUB · SIXWEI2025",
        use="开源 Skill 宣传片 · AI 工具评测 · 硬核自动化流水线（主力黑红科技版）",
    ),
    "huixin-ui-showcase": dict(
        name="汇芯 · 真实界面瑞士画框风",
        theme="swiss_dark",
        layout="ui-showcase",
        portrait=False,
        kicker="REAL INTERFACE · 实操演示",
        brand="HUIXIN STUDIO",
        strip_left="袁六伟 · 台州汇芯",
        strip_right="LIVE DEMO · 100% REAL",
        use="软件实操教程 · 产品界面演示 · 桌面自动化取证（主力真实界面版）",
    ),
    "huixin-brand-red": dict(
        name="汇芯 · 经典汇芯红白杂志风",
        theme="brand",
        layout="editorial-portrait",
        portrait=True,
        kicker="台州汇芯 · 企业 AI 智能体落地",
        brand="袁六伟",
        strip_left="袁六伟 · 台州汇芯",
        strip_right="覆盖近 20 个行业 · 全案交付",
        use="政企商单案例 · 训练营宣发 · 品牌官方介绍（主力白底汇芯红版）",
    ),
    "huixin-editorial-paper": dict(
        name="汇芯 · 纸本墨方法论杂志风",
        theme="paper",
        layout="editorial-portrait",
        portrait=True,
        kicker="AI 实战派 · 认知与方法论",
        brand="WorkBuddy",
        strip_left="袁六伟 · 台州汇芯",
        strip_right="EDITORIAL · ISSUE 2026",
        use="知识星球专栏 · 保姆级教程 · 行业热点拆解（主力暖纸杂志版）",
    ),
    "huixin-klein-data": dict(
        name="汇芯 · 克莱因蓝极客数据风",
        theme="swiss_klein",
        layout="swiss-metric",
        portrait=False,
        kicker="BENCHMARK · 实测数据报告",
        brand="HUIXIN LAB",
        strip_left="袁六伟 · 台州汇芯",
        strip_right="DATA BENCHMARK",
        use="多模型横评 · 榜单盘点 · 效率倍增对比（主力克莱因蓝数据版）",
    ),
}


def find_cutout() -> tuple[Path | None, list[int]]:
    for p in CUTOUT_CANDIDATES:
        if p.is_file():
            meta = p.with_suffix(".json")
            fb = [231, 13, 581, 503]
            if meta.is_file():
                try:
                    fb = json.loads(meta.read_text(encoding="utf-8")).get("face_box", fb)
                except Exception:
                    pass
            return p, fb
    return None, [231, 13, 581, 503]


def find_font_uri() -> str:
    for p in FONT_CANDIDATES:
        if p.is_file():
            return p.resolve().as_uri()
    return ""


def rgba(hexv: str, a: float) -> str:
    h = hexv.lstrip("#")
    if len(h) != 6:
        return f"rgba(0,0,0,{a})"
    return f"rgba({int(h[0:2],16)},{int(h[2:4],16)},{int(h[4:6],16)},{a})"


def trim_alpha(im: Image.Image, pad: int = 2) -> Image.Image:
    bb = im.split()[-1].getbbox()
    if not bb:
        return im
    x0, y0, x1, y1 = bb
    return im.crop((max(0, x0 - pad), max(0, y0 - pad),
                    min(im.width, x1 + pad), min(im.height, y1 + pad)))


def treat_portrait(src: Path, dst: Path, mode: str) -> tuple[Path, tuple[int, int]]:
    """人像影调融合：严禁纯黑白（袁总铁律），保留面部肤色与血色，只压高光白T或做环境色融合。"""
    im = trim_alpha(Image.open(src).convert("RGBA"))
    arr = np.asarray(im).astype(np.float32)
    rgb, alpha = arr[..., :3], arr[..., 3:4]
    g = (rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114) / 255.0

    if mode == "warm_dark":
        f = (1.04 - 0.40 * g).clip(0.58, 1.04)[..., None]
        out = rgb * f
        out[..., 0] *= 1.08
        out[..., 1] *= 1.00
        out[..., 2] *= 0.88
        out = np.clip(out, 0, 255)
    elif mode == "muted":
        gray = np.stack([g * 255.0] * 3, axis=-1)
        out = np.clip(rgb * 0.74 + gray * 0.26, 0, 255)
    elif mode == "warm_muted":
        gray = np.stack([g * 255.0] * 3, axis=-1)
        base = np.clip(rgb * 0.72 + gray * 0.28, 0, 255)
        out = np.clip(base * np.array([1.06, 1.00, 0.92]), 0, 255)
    elif mode == "cool":
        gray = np.stack([g * 255.0] * 3, axis=-1)
        mixed = rgb * 0.62 + gray * 0.38
        out = np.clip(mixed * np.array([0.95, 0.99, 1.06]), 0, 255)
    else:
        out = np.clip(rgb * 0.95, 0, 255)

    merged = np.concatenate([out, alpha], axis=-1).clip(0, 255).astype(np.uint8)
    img = Image.fromarray(merged)
    img = ImageEnhance.Sharpness(img).enhance(1.10)
    img.save(dst)
    return dst, im.size


def auto_select_layout(brief: dict) -> str:
    """根据 brief 字段智能路由 4 大版式原型。"""
    explicit = str(brief.get("layout", "")).strip().lower()
    if explicit in ("editorial-portrait", "swiss-metric", "ui-showcase", "manifesto-poster"):
        return explicit
    if brief.get("shot") and os.path.isfile(str(brief.get("shot"))):
        return "ui-showcase"
    if brief.get("metric"):
        return "swiss-metric"
    if brief.get("portrait", False) is True:
        return "editorial-portrait"
    # 如果没有 shot 也没有 metric，看是否默认启用人像或大字宣言
    if brief.get("portrait") is False:
        return "manifesto-poster"
    return "swiss-metric" if brief.get("metric") else "editorial-portrait"


def _font_face_css() -> str:
    uri = find_font_uri()
    if not uri:
        return ""
    return f"""@font-face {{
  font-family: 'NotoSansVF';
  src: url('{uri}') format('truetype');
  font-weight: 100 900;
  font-display: block;
}}"""


def _adaptive_title_size(lines: list[str], base_size: int, max_width: int) -> list[int]:
    """根据每行字符宽度自动微调字号，保证单行绝不折行、绝不越界。"""
    sizes = []
    for i, ln in enumerate(lines):
        is_last = (i == len(lines) - 1) and len(lines) > 1
        target = int(base_size * (1.08 if is_last else 0.94))
        # 估算宽度：中文字符算 1.0，ASCII 算 0.58
        cjk_units = sum(1.0 if ord(ch) > 127 else 0.58 for ch in ln)
        est_w = cjk_units * target * 0.98
        if est_w > max_width and cjk_units > 0:
            target = int(max_width / (cjk_units * 1.00))
        sizes.append(max(56, target))
    return sizes


# ============================================================ 竖版 3:4 (1080×1440) HTML 构建
def build_3x4_html(brief: dict, theme_key: str, layout: str,
                   portrait_uri: str = "", shot_uri: str = "",
                   psize: tuple[int, int] = (817, 883),
                   big_title: bool = False) -> str:
    W, H = 1080, 1440
    t = THEMES[theme_key]
    font_css = _font_face_css()

    kicker = html.escape(str(brief.get("kicker") or brief.get("badge") or "HUIXIN · AI STUDIO").strip())
    brand = html.escape(str(brief.get("brand") or "").strip())
    raw_lines = brief.get("title_lines") or ["AI 自动化工作流", "3分钟出成片"]
    lines = [str(x).strip() for x in raw_lines if str(x).strip()][:3]
    if not lines:
        lines = ["AI 自动化工作流"]
    sub = html.escape(str(brief.get("subtitle") or brief.get("sub") or "").strip())
    metric = html.escape(str(brief.get("metric") or "").strip())
    metric_label = html.escape(str(brief.get("metric_label") or "").strip())
    strip_left = html.escape(str(brief.get("strip_left") or brief.get("foot_left") or "袁六伟 · 台州汇芯").strip())
    strip_right = html.escape(str(brief.get("strip_right") or brief.get("foot_right") or "AI WORKFLOW").strip())

    grid_bg = ""
    if t["show_grid"]:
        grid_bg = f"""
        background-image:
          linear-gradient(to right, {t['grid']} 1px, transparent 1px),
          linear-gradient(to bottom, {t['grid']} 1px, transparent 1px);
        background-size: 72px 72px;"""

    grain_div = '<div class="grain"></div>' if t["grain"] else ""
    top_bar_div = f'<div class="top-bar"></div>' if t["top_bar"] else ""

    # 针对不同 layout 设定标题可用宽度与基准字号
    if big_title:
        base_fs = 192 if len(lines) <= 2 else 156
        max_tw = 936
    elif layout == "editorial-portrait":
        base_fs = 126 if len(lines) <= 2 else 104
        max_tw = 930
    elif layout == "swiss-metric":
        base_fs = 128 if len(lines) <= 2 else 106
        max_tw = 936
    elif layout == "ui-showcase":
        base_fs = 114 if len(lines) <= 2 else 96
        max_tw = 936
    else:  # manifesto-poster
        base_fs = 148 if len(lines) <= 2 else 120
        max_tw = 936

    line_sizes = _adaptive_title_size(lines, base_fs, max_tw)
    title_rows = []
    for i, ln in enumerate(lines):
        is_last = (i == len(lines) - 1) and (len(lines) > 1 or layout == "swiss-metric")
        cls = "tl accent" if is_last else "tl"
        # Editorial 遵循「越大越细」，Swiss 遵循高对比几何字重
        fw = (500 if t["family"] == SERIF else t["accent_weight"]) if is_last else t["weight"]
        fs = line_sizes[i]
        title_rows.append(
            f'<div class="{cls}" style="font-size:{fs}px;font-weight:{fw}"><span>{html.escape(ln)}</span></div>'
        )
    title_html = "\n".join(title_rows)
    brand_html = "" if big_title else (f'<div class="brand">{brand}</div>' if brand else "")
    sub_html = f'<div class="rule"></div><div class="sub">{sub}</div>' if sub else '<div class="rule"></div>'

    # 主视觉层构建
    body_extra = ""
    layout_css = ""

    if layout == "editorial-portrait" and portrait_uri:
        # 竖屏 3:4：上方文字，下方偏右杂志级半身人像，发顶绝不裁切，顶部渐变避开发顶杜绝雾化
        pw = 640 if big_title else 740
        ph = round(pw * psize[1] / psize[0])
        pl = W - pw + 32
        pt = H - ph + (60 if big_title else 44)
        txt_top = 175 if big_title else 84
        layout_css = f"""
        .portrait {{
          position:absolute; left:{pl}px; top:{pt}px; width:{pw}px; height:{ph}px;
          object-fit:contain; object-position:bottom right;
          filter:{SHADOW[theme_key]}; z-index:2;
        }}
        .tint {{
          position:absolute; inset:0; pointer-events:none; z-index:3;
          background:
            linear-gradient(180deg, {t['paper']} 0%, {t['paper']} 36%,
              {rgba(t['paper'], 0.0)} 46%),
            linear-gradient(90deg, {rgba(t['paper'], 0.90)} 0%, {rgba(t['paper'], 0.35)} 30%, {rgba(t['paper'], 0.0)} 56%),
            linear-gradient(0deg, {rgba(t['paper'], 0.82)} 0%, {rgba(t['paper'], 0.0)} 11%);
        }}
        .txt {{
          position:absolute; left:72px; top:{txt_top}px; width:936px; z-index:5;
        }}
        """
        body_extra = f'<img class="portrait" src="{portrait_uri}" alt=""><div class="tint"></div>'

    elif layout == "swiss-metric":
        # 瑞士巨型数字风：72px 网格 + 巨型数字锚点 + 双行主标题 + 极简规格栏
        m_text = metric or "10X"
        m_chars = sum(1.0 if ord(c) > 127 else 0.62 for c in m_text)
        m_fs = min(290, max(160, int(920 / max(1.8, m_chars))))
        m_label_html = f'<div class="metric-label">{metric_label}</div>' if metric_label else ""
        layout_css = f"""
        .txt {{
          position:absolute; left:72px; top:92px; width:936px; bottom:116px;
          display:flex; flex-direction:column; justify-content:space-between; z-index:5;
        }}
        .metric-wrap {{
          margin: 18px 0 10px;
          border-left: 8px solid {t['accent']};
          padding-left: 28px;
        }}
        .metric-num {{
          font-family: {LATIN}, {SANS};
          font-weight: 900;
          font-size: {m_fs}px;
          line-height: 0.90;
          letter-spacing: -0.045em;
          color: {t['ink']};
          font-variant-numeric: tabular-nums;
          white-space: nowrap;
        }}
        .metric-label {{
          margin-top: 14px;
          font-family: {t['small_family']};
          font-size: 26px;
          font-weight: 600;
          letter-spacing: 0.14em;
          color: {t['accent_sub']};
          text-transform: uppercase;
        }}
        """
        title_html = f"""
        <div class="top-group">
          <div class="kicker"><i class="sq"></i><span>{kicker}</span></div>
          {brand_html}
        </div>
        <div class="metric-wrap">
          <div class="metric-num">{m_text}</div>
          {m_label_html}
        </div>
        <div class="bottom-group">
          {title_html}
          {sub_html}
        </div>
        """

    elif layout == "ui-showcase" and shot_uri:
        # 真实界面杂志画框风：上方 43% 瑞士排版，下方 57% 真实软件截图/视频帧 + 极简浏览器顶栏
        layout_css = f"""
        .txt {{
          position:absolute; left:72px; top:76px; width:936px; z-index:5;
        }}
        .ui-frame {{
          position:absolute; left:64px; right:64px; top:654px; bottom:116px; z-index:4;
          border-radius: 20px;
          overflow: hidden;
          background: #111215;
          border: 1px solid {t['hair']};
          box-shadow: 0 32px 80px rgba(0,0,0,0.42), 0 0 0 1px rgba(255,255,255,0.06);
          display: flex; flex-direction: column;
        }}
        .ui-bar {{
          height: 38px; background: rgba(24,25,30,0.96);
          border-bottom: 1px solid rgba(255,255,255,0.08);
          display: flex; align-items: center; padding: 0 18px; gap: 9px; flex: 0 0 auto;
        }}
        .ui-dot {{ width: 11px; height: 11px; border-radius: 50%; background: rgba(255,255,255,0.22); }}
        .ui-dot.r {{ background: #FF5F56; }}
        .ui-dot.y {{ background: #FFBD2E; }}
        .ui-dot.g {{ background: #27C93F; }}
        .ui-url {{
          margin-left: 14px; font-family: {MONO}; font-size: 15px;
          color: rgba(255,255,255,0.45); letter-spacing: 0.06em;
        }}
        .ui-body {{
          flex: 1; width: 100%; height: 100%; overflow: hidden;
          background: #0C0D10; display: flex; align-items: center; justify-content: center;
        }}
        .ui-body img {{
          width: 100%; height: 100%; object-fit: cover; object-position: center top;
        }}
        """
        body_extra = f"""
        <div class="ui-frame">
          <div class="ui-bar">
            <span class="ui-dot r"></span><span class="ui-dot y"></span><span class="ui-dot g"></span>
            <span class="ui-url">{kicker}</span>
          </div>
          <div class="ui-body"><img src="{shot_uri}" alt=""></div>
        </div>
        """

    else:
        # manifesto-poster 极简宣言大字风：瑞士网格分割 + 大留白 + 建筑感几何线
        idx_tag = html.escape(str(brief.get("index") or "01").strip())
        layout_css = f"""
        .txt {{
          position:absolute; left:72px; top:96px; width:936px; bottom:124px;
          display:flex; flex-direction:column; justify-content:space-between; z-index:5;
        }}
        .poster-index {{
          font-family: {LATIN}; font-weight: 200; font-size: 180px;
          line-height: 0.85; letter-spacing: -0.04em; color: {t['accent']};
          opacity: 0.92;
        }}
        .poster-grid-line {{
          width: 100%; height: 1px; background: {t['hair']}; margin: 28px 0;
        }}
        """
        title_html = f"""
        <div class="top-group">
          <div class="kicker"><i class="sq"></i><span>{kicker}</span></div>
          <div class="poster-grid-line"></div>
          <div class="poster-index">{idx_tag}</div>
        </div>
        <div class="bottom-group">
          {brand_html}
          {title_html}
          {sub_html}
        </div>
        """

    # 非 swiss-metric / manifesto-poster 时使用标准顶层文字结构
    if layout in ("editorial-portrait", "ui-showcase") and (
        (layout == "editorial-portrait" and portrait_uri) or (layout == "ui-showcase" and shot_uri)
    ):
        inner_txt = f"""
        <div class="kicker"><i class="sq"></i><span>{kicker}</span></div>
        {brand_html}
        {title_html}
        {sub_html}
        """
    else:
        inner_txt = title_html

    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><style>
{font_css}
* {{ margin:0; padding:0; box-sizing:border-box; }}
html, body {{ width:{W}px; height:{H}px; overflow:hidden; background:{t['paper']}; }}
.cv {{
  position:relative; width:{W}px; height:{H}px; overflow:hidden;
  background-color:{t['paper']};
  {grid_bg}
  font-kerning:normal; -webkit-font-smoothing:antialiased;
}}
.paper2 {{
  position:absolute; inset:0; pointer-events:none;
  background:
    radial-gradient(95% 65% at 88% 12%, {rgba(t['accent'], 0.14 if theme_key=='swiss_dark' else 0.06)} 0%, transparent 62%),
    radial-gradient(110% 80% at 18% 15%, {t['paper2']} 0%, transparent 65%);
}}
.grain {{
  position:absolute; inset:0; opacity:0.42; pointer-events:none; z-index:4;
  mix-blend-mode:{"screen" if theme_key in ("midnight","swiss_dark") else "multiply"};
  background-image:radial-gradient(rgba(128,128,128,0.07) 1px, transparent 1px);
  background-size:3px 3px;
}}
.top-bar {{
  position:absolute; left:0; top:0; width:100%; height:22px; background:{t['accent']}; z-index:6;
}}
.kicker {{
  display:flex; align-items:center; gap:16px;
  font-family:{t['small_family']}; font-weight:{t['small_weight']};
  font-size:25px; letter-spacing:{t['small_track']}; color:{t['muted']};
  text-transform:uppercase; margin-bottom:28px;
}}
.kicker .sq {{ width:12px; height:12px; background:{t['accent']}; flex:0 0 auto; }}
.brand {{
  font-family:{t['brand_family']}; font-weight:{t['brand_weight']};
  font-size:68px; letter-spacing:{t['brand_track']}; color:{t['ink']};
  line-height:1.05; margin-bottom:16px; white-space:nowrap;
}}
.tl {{
  font-family:{t['family']}; line-height:1.13; letter-spacing:{t['track']};
  color:{t['ink']}; white-space:nowrap; margin-bottom:6px;
}}
.tl.accent {{
  color:{t['accent']}; line-height:1.08;
}}
.rule {{
  width:136px; height:5px; background:{t['accent']}; margin:30px 0 20px;
}}
.sub {{
  font-family:{t['family']}; font-weight:400; font-size:34px;
  letter-spacing:0.06em; color:{t['muted']}; white-space:nowrap;
}}
.strip {{
  position:absolute; left:72px; right:72px; bottom:46px; z-index:6;
  border-top:1px solid {t['hair']}; padding-top:18px;
  display:flex; justify-content:space-between; align-items:baseline;
  font-family:{t['small_family']}; font-weight:{t['small_weight']};
  font-size:21px; letter-spacing:0.18em; color:{t['muted']}; text-transform:uppercase;
}}
{layout_css}
</style></head><body>
<div class="cv">
  <div class="paper2"></div>
  {grain_div}{top_bar_div}
  {body_extra}
  <div class="txt">
    {inner_txt}
  </div>
  <div class="strip"><span>{strip_left}</span><span>{strip_right}</span></div>
</div>
</body></html>"""


# ============================================================ 横版 16:9 (1920×1080) 首帧 HTML 构建
def build_16x9_html(brief: dict, theme_key: str, layout: str,
                    portrait_uri: str = "", shot_uri: str = "",
                    psize: tuple[int, int] = (817, 883),
                    center_safe: bool = False,
                    big_title: bool = False) -> str:
    """1920×1080 横屏视频 0.01s 首帧。
    - 默认横屏杂志展开版：左半幅高冲击标题 + 锚点数字，右半幅精修人像或真实软件画框。
    - 若开启 center_safe=True：所有核心文字严格收敛在中央 810×1080 (x: 555..1365) 的 3:4 安全框内，
      供自动从 16:9 首帧居中裁 3:4 的平台无缝兼容。
    """
    W, H = 1920, 1080
    t = THEMES[theme_key]
    font_css = _font_face_css()

    kicker = html.escape(str(brief.get("kicker") or brief.get("badge") or "HUIXIN · AI STUDIO").strip())
    brand = html.escape(str(brief.get("brand") or "").strip())
    raw_lines = brief.get("title_lines") or ["AI 自动化工作流", "3分钟出成片"]
    lines = [str(x).strip() for x in raw_lines if str(x).strip()][:3]
    if not lines:
        lines = ["AI 自动化工作流"]
    sub = html.escape(str(brief.get("subtitle") or brief.get("sub") or "").strip())
    metric = html.escape(str(brief.get("metric") or "").strip())
    metric_label = html.escape(str(brief.get("metric_label") or "").strip())
    strip_left = html.escape(str(brief.get("strip_left") or brief.get("foot_left") or "袁六伟 · 台州汇芯").strip())
    strip_right = html.escape(str(brief.get("strip_right") or brief.get("foot_right") or "AI WORKFLOW").strip())

    grid_bg = ""
    if t["show_grid"]:
        grid_bg = f"""
        background-image:
          linear-gradient(to right, {t['grid']} 1px, transparent 1px),
          linear-gradient(to bottom, {t['grid']} 1px, transparent 1px);
        background-size: 72px 72px;"""

    grain_div = '<div class="grain"></div>' if t["grain"] else ""
    top_bar_div = '<div class="top-bar"></div>' if t["top_bar"] else ""

    txt_left = 570 if center_safe else 120
    max_tw = 780 if center_safe else (980 if (portrait_uri or shot_uri) else 1560)
    if big_title:
        base_fs = (152 if len(lines) <= 2 else 124) if center_safe else (176 if len(lines) <= 2 else 140)
    else:
        base_fs = 104 if center_safe else (136 if len(lines) <= 2 else 112)

    line_sizes = _adaptive_title_size(lines, base_fs, max_tw)
    title_rows = []
    for i, ln in enumerate(lines):
        is_last = (i == len(lines) - 1) and (len(lines) > 1 or layout == "swiss-metric")
        cls = "tl accent" if is_last else "tl"
        fw = (500 if t["family"] == SERIF else t["accent_weight"]) if is_last else t["weight"]
        title_rows.append(
            f'<div class="{cls}" style="font-size:{line_sizes[i]}px;font-weight:{fw}"><span>{html.escape(ln)}</span></div>'
        )
    title_html = "\n".join(title_rows)
    brand_html = "" if big_title else (f'<div class="brand">{brand}</div>' if brand else "")
    sub_html = f'<div class="rule"></div><div class="sub">{sub}</div>' if sub else '<div class="rule"></div>'

    metric_block = ""
    if metric:
        m_fs = 156 if center_safe else 196
        m_lbl = f'<span class="m-lbl">{metric_label}</span>' if metric_label else ""
        metric_block = f'<div class="m-row"><span class="m-num" style="font-size:{m_fs}px">{metric}</span>{m_lbl}</div>'

    right_visual = ""
    if layout == "ui-showcase" and shot_uri and not center_safe:
        right_visual = f"""
        <div class="ui-card">
          <div class="ui-bar">
            <span class="d r"></span><span class="d y"></span><span class="d g"></span>
            <span class="u">{kicker}</span>
          </div>
          <div class="ui-img"><img src="{shot_uri}" alt=""></div>
        </div>
        """
    elif portrait_uri and layout == "editorial-portrait":
        ph = 940 if (big_title and center_safe) else 1020
        pw = round(ph * psize[0] / psize[1])
        pl = (1920 - pw + 24) if not center_safe else (1365 - int(pw * (0.45 if big_title else 0.55)))
        pt = H - ph + 28
        right_visual = f'<img class="portrait" src="{portrait_uri}" style="left:{pl}px;top:{pt}px;width:{pw}px;height:{ph}px" alt=""><div class="tint"></div>'

    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><style>
{font_css}
* {{ margin:0; padding:0; box-sizing:border-box; }}
html, body {{ width:{W}px; height:{H}px; overflow:hidden; background:{t['paper']}; }}
.cv {{
  position:relative; width:{W}px; height:{H}px; overflow:hidden;
  background-color:{t['paper']};
  {grid_bg}
  font-kerning:normal; -webkit-font-smoothing:antialiased;
}}
.paper2 {{
  position:absolute; inset:0; pointer-events:none;
  background:
    radial-gradient(80% 75% at 78% 22%, {rgba(t['accent'], 0.14 if theme_key=='swiss_dark' else 0.06)} 0%, transparent 62%),
    radial-gradient(100% 85% at 20% 18%, {t['paper2']} 0%, transparent 64%);
}}
.grain {{
  position:absolute; inset:0; opacity:0.42; pointer-events:none; z-index:4;
  mix-blend-mode:{"screen" if theme_key in ("midnight","swiss_dark") else "multiply"};
  background-image:radial-gradient(rgba(128,128,128,0.07) 1px, transparent 1px);
  background-size:3px 3px;
}}
.top-bar {{ position:absolute; left:0; top:0; width:100%; height:18px; background:{t['accent']}; z-index:6; }}
.portrait {{
  position:absolute; object-fit:contain; object-position:bottom right;
  filter:{SHADOW[theme_key]}; z-index:2;
}}
.tint {{
  position:absolute; inset:0; pointer-events:none; z-index:3;
  background:linear-gradient(90deg, {t['paper']} 0%, {t['paper']} 42%,
    {rgba(t['paper'], 0.92)} 52%, {rgba(t['paper'], 0.35)} 66%, {rgba(t['paper'], 0.0)} 80%);
}}
.ui-card {{
  position:absolute; right:88px; top:110px; width:760px; height:810px; z-index:3;
  border-radius:18px; overflow:hidden; background:#111215;
  border:1px solid {t['hair']};
  box-shadow:0 30px 80px rgba(0,0,0,0.45);
  display:flex; flex-direction:column;
}}
.ui-bar {{
  height:36px; background:rgba(24,25,30,0.96); border-bottom:1px solid rgba(255,255,255,0.08);
  display:flex; align-items:center; padding:0 16px; gap:8px;
}}
.ui-bar .d {{ width:10px; height:10px; border-radius:50%; }}
.ui-bar .r {{ background:#FF5F56; }} .ui-bar .y {{ background:#FFBD2E; }} .ui-bar .g {{ background:#27C93F; }}
.ui-bar .u {{ margin-left:12px; font-family:{MONO}; font-size:14px; color:rgba(255,255,255,0.45); }}
.ui-img {{ flex:1; overflow:hidden; background:#0C0D10; }}
.ui-img img {{ width:100%; height:100%; object-fit:cover; object-position:center top; }}

.txt {{
  position:absolute; left:{txt_left}px; top:84px; bottom:110px; width:{max_tw}px; z-index:5;
  display:flex; flex-direction:column; justify-content:center;
}}
.kicker {{
  display:flex; align-items:center; gap:16px;
  font-family:{t['small_family']}; font-weight:{t['small_weight']};
  font-size:24px; letter-spacing:{t['small_track']}; color:{t['muted']};
  text-transform:uppercase; margin-bottom:24px;
}}
.kicker .sq {{ width:11px; height:11px; background:{t['accent']}; }}
.brand {{
  font-family:{t['brand_family']}; font-weight:{t['brand_weight']};
  font-size:64px; letter-spacing:{t['brand_track']}; color:{t['ink']};
  line-height:1.05; margin-bottom:14px; white-space:nowrap;
}}
.m-row {{
  display:flex; align-items:baseline; gap:24px;
  border-left:7px solid {t['accent']}; padding-left:24px; margin:8px 0 22px;
}}
.m-num {{
  font-family:{LATIN}, {SANS}; font-weight:900; line-height:0.90;
  letter-spacing:-0.04em; color:{t['ink']}; font-variant-numeric:tabular-nums;
}}
.m-lbl {{
  font-family:{t['small_family']}; font-size:24px; font-weight:600;
  letter-spacing:0.14em; color:{t['accent_sub']}; text-transform:uppercase;
}}
.tl {{
  font-family:{t['family']}; line-height:1.13; letter-spacing:{t['track']};
  color:{t['ink']}; white-space:nowrap; margin-bottom:6px;
}}
.tl.accent {{ color:{t['accent']}; line-height:1.08; }}
.rule {{ width:140px; height:5px; background:{t['accent']}; margin:28px 0 18px; }}
.sub {{
  font-family:{t['family']}; font-weight:400; font-size:32px;
  letter-spacing:0.06em; color:{t['muted']}; white-space:nowrap;
}}
.strip {{
  position:absolute; left:{txt_left}px; right:{580 if center_safe else 120}px; bottom:42px; z-index:6;
  border-top:1px solid {t['hair']}; padding-top:16px;
  display:flex; justify-content:space-between; align-items:baseline;
  font-family:{t['small_family']}; font-weight:{t['small_weight']};
  font-size:20px; letter-spacing:0.18em; color:{t['muted']}; text-transform:uppercase;
}}
</style></head><body>
<div class="cv">
  <div class="paper2"></div>
  {grain_div}{top_bar_div}
  {right_visual}
  <div class="txt">
    <div class="kicker"><i class="sq"></i><span>{kicker}</span></div>
    {brand_html}
    {metric_block}
    {title_html}
    {sub_html}
  </div>
  <div class="strip"><span>{strip_left}</span><span>{strip_right}</span></div>
</div>
</body></html>"""


# ============================================================ 浏览器渲染与机械硬闸
def _launch_chromium(p, dsf: int = 1):
    args = [f"--force-device-scale-factor={dsf}", "--hide-scrollbars"]
    for ch in ("chrome", "msedge", None):
        try:
            return p.chromium.launch(channel=ch, args=args) if ch else p.chromium.launch(args=args)
        except Exception:
            continue
    raise RuntimeError("无法启动 Chrome / Chromium，请检查 Playwright 或系统 Chrome 安装。")


def render_and_check(html_3x4: Path, out_3x4_png: Path,
                     html_16x9: Path | None, out_16x9_png: Path | None,
                     dpr: int = 2, face_box: list[int] | None = None,
                     psize: tuple[int, int] = (817, 883)) -> dict:
    from playwright.sync_api import sync_playwright

    errors, warns = [], []
    with sync_playwright() as p:
        b = _launch_chromium(p, dsf=dpr)
        pg = b.new_page(viewport={"width": 1080, "height": 1440}, device_scale_factor=dpr)
        pg.goto(html_3x4.resolve().as_uri())
        pg.wait_for_timeout(750)

        m = pg.evaluate("""() => {
          const rect = s => {
            const e = document.querySelector(s);
            if (!e) return null;
            const r = e.getBoundingClientRect();
            return {x:r.x, y:r.y, w:r.width, h:r.height, r:r.x+r.width, b:r.y+r.height};
          };
          const tls = [...document.querySelectorAll('.tl')].map(e => {
            const s = e.querySelector('span') || e;
            const r = s.getBoundingClientRect();
            return {t:e.textContent.trim(), x:r.x, y:r.y, w:r.width, h:r.height, r:r.x+r.width, b:r.y+r.height};
          });
          return {titles:tls, portrait:rect('.portrait'), metric:rect('.metric-num'), vw:window.innerWidth, vh:window.innerHeight};
        }""")

        for box in m.get("titles", []):
            if box["r"] > 1080 - 36:
                errors.append(f"3:4 标题「{box['t']}」右越界 ({round(box['r'])}px > 1044px)")
            if box["y"] < 36 or box["b"] > 1440 - 36:
                warns.append(f"3:4 标题「{box['t']}」上下贴边 (y={round(box['y'])}..{round(box['b'])})")

        pr = m.get("portrait")
        if pr and face_box:
            fx0 = pr["x"] + (face_box[0] / psize[0]) * pr["w"]
            fx1 = pr["x"] + (face_box[2] / psize[0]) * pr["w"]
            fy0 = pr["y"] + (face_box[1] / psize[1]) * pr["h"]
            fy1 = pr["y"] + (face_box[3] / psize[1]) * pr["h"]
            for box in m.get("titles", []):
                # 允许压在额头/头发边缘 25px 内，但严禁压住眉眼鼻唇核心区
                core_fy0 = fy0 + (fy1 - fy0) * 0.22
                if box["r"] > fx0 + 18 and box["x"] < fx1 - 18 and box["b"] > core_fy0 and box["y"] < fy1:
                    warns.append(f"3:4 标题「{box['t']}」与人像面部区域轻微交叠")

        pg.screenshot(path=str(out_3x4_png), full_page=True)

        if html_16x9 and out_16x9_png:
            pg16 = b.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
            pg16.goto(html_16x9.resolve().as_uri())
            pg16.wait_for_timeout(650)
            pg16.screenshot(path=str(out_16x9_png), full_page=True)

        b.close()

    # 同步导出高质量 JPG（视频号 / 公众号 / 小红书后台最认 RGB JPG）
    out_3x4_jpg = out_3x4_png.with_suffix(".jpg")
    Image.open(out_3x4_png).convert("RGB").save(out_3x4_jpg, quality=95, subsampling=0)
    if out_16x9_png and out_16x9_png.is_file():
        Image.open(out_16x9_png).convert("RGB").save(out_16x9_png.with_suffix(".jpg"), quality=95, subsampling=0)

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "warns": warns,
        "cover_3x4_png": str(out_3x4_png),
        "cover_3x4_jpg": str(out_3x4_jpg),
        "cover_16x9_png": str(out_16x9_png) if out_16x9_png else "",
    }


def apply_brand_preset(brief: dict, preset_key: str = "") -> dict:
    """将汇芯品牌标准预设 (BRAND_PRESETS) 注入 brief，用户显式传入的字段优先。"""
    pk = (preset_key or brief.get("preset") or "").strip().lower()
    if not pk or pk not in BRAND_PRESETS:
        return brief
    p = BRAND_PRESETS[pk]
    merged = dict(brief)
    merged["preset"] = pk
    if not merged.get("theme"):
        merged["theme"] = p["theme"]
    if not merged.get("layout"):
        merged["layout"] = p["layout"]
    if "portrait" not in merged:
        merged["portrait"] = p["portrait"]
    for k in ("kicker", "brand", "strip_left", "strip_right"):
        if not merged.get(k):
            merged[k] = p.get(k, "")
    return merged


def render_cover_pair(brief: dict, out_dir: Path,
                      theme_key: str | None = None,
                      layout: str | None = None,
                      preset_key: str | None = None,
                      out_3x4_name: str = "cover-3x4.png",
                      out_16x9_name: str = "cover-opening.png",
                      dpr: int = 2,
                      center_safe_16x9: bool = False,
                      big_title: bool = False) -> dict:
    """主入口：给定 brief 字典与输出目录，一键生成 3:4 竖版封面 + 16:9 横屏首帧。"""
    out_dir = Path(out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    brief = apply_brand_preset(brief, preset_key or "")
    tk = (theme_key or brief.get("theme") or "swiss_dark").strip().lower()
    if tk not in THEMES:
        tk = "swiss_dark"
    t = THEMES[tk]

    ly = layout or auto_select_layout(brief)
    cutout_path, face_box = find_cutout()

    portrait_uri = ""
    psize = (817, 883)
    if ly == "editorial-portrait" and cutout_path is not None:
        port_dst = out_dir / f".portrait_{tk}.png"
        port_path, psize = treat_portrait(cutout_path, port_dst, t["portrait"])
        portrait_uri = port_path.resolve().as_uri()
    elif ly == "editorial-portrait" and cutout_path is None:
        ly = "swiss-metric" if brief.get("metric") else "manifesto-poster"

    shot_uri = ""
    if brief.get("shot"):
        sp = Path(str(brief["shot"])).expanduser().resolve()
        if sp.is_file():
            shot_uri = sp.as_uri()

    html_3x4 = out_dir / ".cover_3x4.html"
    html_16x9 = out_dir / ".cover_16x9.html"
    html_3x4.write_text(
        build_3x4_html(brief, tk, ly, portrait_uri=portrait_uri, shot_uri=shot_uri, psize=psize, big_title=big_title),
        encoding="utf-8",
    )
    html_16x9.write_text(
        build_16x9_html(brief, tk, ly, portrait_uri=portrait_uri, shot_uri=shot_uri,
                        psize=psize, center_safe=center_safe_16x9, big_title=big_title),
        encoding="utf-8",
    )

    out_3x4_png = out_dir / out_3x4_name
    out_16x9_png = out_dir / out_16x9_name
    res = render_and_check(
        html_3x4, out_3x4_png, html_16x9, out_16x9_png,
        dpr=dpr, face_box=face_box, psize=psize,
    )
    res["theme"] = tk
    res["theme_name"] = t["name"]
    res["layout"] = ly
    return res


DEMO_BRIEFS = [
    dict(
        slug="01_huixin_founder_gold",
        preset="huixin-founder-gold",
        kicker="一人AI公司 · 创业实战复盘",
        brand="HUIXIN AI",
        title_lines=["我走过的弯路", "和交付的结果"],
        subtitle="学员 7000+ · 服务商单客户 100+ · 覆盖近 20 个行业",
        strip_left="袁六伟 · 台州汇芯",
        strip_right="FOUNDER EDITION",
    ),
    dict(
        slug="02_huixin_tech_flagship",
        preset="huixin-tech-flagship",
        kicker="WECHAT AUTOPILOT · 旗舰开源",
        brand="9-STEP PIPELINE",
        metric="9步闭环",
        metric_label="ZERO-FLUFF · MECHANICAL QUALITY GATE · AUTO DRAFT",
        title_lines=["把规矩写进代码", "一人就是编辑部"],
        subtitle="从热点雷达、真机取证到汇芯红排版自动进草稿箱",
        strip_left="袁六伟 · 台州汇芯",
        strip_right="GITHUB · SIXWEI2025",
    ),
    dict(
        slug="03_huixin_ui_showcase",
        preset="huixin-ui-showcase",
        kicker="HUIXIN SKILLS MANAGER · 中央大脑",
        brand="Skills Hub",
        title_lines=["统管全机技能", "告别散乱与重复"],
        subtitle="536 项技能去重精选 · 4 大 Agent 工具一键同步",
        shot="/Users/yuanliuwei/Workbuddy/github-skills-14/huixin-skills-manager/assets/showcase/01-real-interface.png",
        strip_left="袁六伟 · 台州汇芯",
        strip_right="REAL INTERFACE",
    ),
    dict(
        slug="04_huixin_brand_red",
        preset="huixin-brand-red",
        kicker="个人IP定位 · 真实创业故事",
        brand="台州汇芯",
        title_lines=["从时薪20块", "到一人AI公司"],
        subtitle="把复杂技术讲人话 · 做拿走就能跑的 AI 智能体",
        strip_left="袁六伟 · 台州汇芯",
        strip_right="HUIXIN BRAND RED",
    ),
    dict(
        slug="05_huixin_editorial_paper",
        preset="huixin-editorial-paper",
        kicker="WORKBUDDY · 实操方法论",
        brand="Skill 变现",
        title_lines=["写好一个Skill", "上架持续变现"],
        subtitle="把十年行业经验封装成可复用的数字资产",
        strip_left="袁六伟 · 台州汇芯",
        strip_right="EDITORIAL PAPER",
    ),
    dict(
        slug="06_huixin_klein_data",
        preset="huixin-klein-data",
        kicker="AI VIDEO SUITE · 生产力工具栈",
        brand="VIDEO LAB",
        metric="6大引擎",
        metric_label="CUT-AS-CODE · FFMPEG · REMOTION · VOICEBOX",
        title_lines=["做视频必装Skill", "10分钟出成片"],
        subtitle="台州汇芯开源视频工作流 · 审美与效率双重拉满",
        strip_left="袁六伟 · 台州汇芯",
        strip_right="SWISS KLEIN",
    ),
]


def build_contact_sheet(image_paths: list[Path], out_path: Path, cols: int = 3):
    """把多张 3:4 封面拼成一张高颜值展示矩阵图，方便一眼对比验收。"""
    imgs = [Image.open(p).convert("RGB") for p in image_paths if p.is_file()]
    if not imgs:
        return
    tw, th = 540, 720
    pad = 36
    rows = (len(imgs) + cols - 1) // cols
    cw = cols * tw + (cols + 1) * pad
    ch = rows * th + (rows + 1) * pad
    sheet = Image.new("RGB", (cw, ch), (18, 18, 22))
    for idx, im in enumerate(imgs):
        r, c = divmod(idx, cols)
        resized = im.resize((tw, th), Image.LANCZOS)
        sheet.paste(resized, (pad + c * (tw + pad), pad + r * (th + pad)))
    sheet.save(out_path, quality=94, subsampling=0)


def main():
    ap = argparse.ArgumentParser(description="汇芯 · 高级感视频封面双画幅渲染引擎 (3:4 封面 + 16:9 首帧)")
    ap.add_argument("--brief", help="JSON 配置文件路径")
    ap.add_argument("--title", help="主标题，多行用 | 分隔，例如 '全自动剪辑|10分钟出大片'")
    ap.add_argument("--kicker", default="", help="顶部微缩眉题")
    ap.add_argument("--brand", default="", help="品牌英文/副标引子")
    ap.add_argument("--sub", default="", help="底部副标题")
    ap.add_argument("--metric", default="", help="瑞士巨型数字锚点，如 '322K★' 或 '10X'")
    ap.add_argument("--metric-label", default="", help="巨型数字下方英文说明")
    ap.add_argument("--shot", default="", help="真实软件界面截图路径（触发 ui-showcase 版式）")
    ap.add_argument("--preset", default="", choices=[""] + list(BRAND_PRESETS.keys()),
                    help="汇芯品牌标准预设：huixin-founder-gold / huixin-tech-flagship / huixin-ui-showcase / huixin-brand-red / huixin-editorial-paper / huixin-klein-data")
    ap.add_argument("--theme", default="", help="视觉主题（留空则按 --preset 或默认 swiss_dark）")
    ap.add_argument("--layout", default="", help="版式：editorial-portrait / swiss-metric / ui-showcase / manifesto-poster")
    ap.add_argument("--portrait", action="store_true", help="强制启用真人抠像杂志版式")
    ap.add_argument("--no-portrait", action="store_true", help="禁用真人抠像")
    ap.add_argument("--dpr", type=int, default=2, help="3:4 渲染倍率（默认 2 即 2160x2880）")
    ap.add_argument("--center-safe-16x9", action="store_true", help="16:9 首帧文字收敛在中央 810x1080 (3:4) 安全区内")
    ap.add_argument("--big-title", action="store_true", help="视频号/抖音缩略图超大字中心安全区模式（隐藏英文副标，主标题拉大至 152~192px）")
    ap.add_argument("--out", default="cover", help="输出目录")
    ap.add_argument("--demo", action="store_true", help="一次生成 6 套高审美样板间 + Contact Sheet 总览图")
    ap.add_argument("--list", action="store_true", help="列出所有可用汇芯品牌预设、主题与版式")
    args = ap.parse_args()

    if args.list:
        print("=== 🏆 汇芯品牌视频封面 6 大标准预设 (Brand Presets) ===")
        for k, v in BRAND_PRESETS.items():
            print(f"  {k:<24} {v['name']:<16}  {v['use']}")
        print("\n=== 7 套高审美视觉主题 (Themes) ===")
        for k, v in THEMES.items():
            print(f"  {k:<13} {v['name']:<8}  {v['use']}")
        print("\n=== 4 大版式原型 (Layouts) ===")
        print("  swiss-metric       瑞士巨型数字风（72px 网格 + Tabular 巨型数字锚点 + 双行大字）")
        print("  editorial-portrait 杂志真人锚点风（精修人像 + 纸感渐变 + 衬线/无衬线高级混排）")
        print("  ui-showcase        真实界面画框风（上方大字钩子 + 下方 macOS 极简画框真实截图）")
        print("  manifesto-poster   极简宣言大字风（瑞士国际主义网格海报 + 巨型编号与大留白）")
        return

    out_root = Path(args.out).expanduser().resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    if args.demo:
        cards_3x4 = []
        for item in DEMO_BRIEFS:
            sub_dir = out_root / item["slug"]
            res = render_cover_pair(
                item, sub_dir,
                theme_key=item.get("theme"),
                layout=item.get("layout"),
                preset_key=item.get("preset"),
                dpr=1,
            )
            cards_3x4.append(Path(res["cover_3x4_png"]))
            status = "✅" if res["ok"] else "❌"
            print(f"{status} [{item['slug']}] theme={res['theme']} layout={res['layout']} -> {res['cover_3x4_jpg']}")
            for w in res["warns"]:
                print(f"   ⚠ {w}")
            for e in res["errors"]:
                print(f"   ! {e}")
        sheet_path = out_root / "showcase_3x4_grid.jpg"
        build_contact_sheet(cards_3x4, sheet_path, cols=3)
        print(f"\n🎨 六套样板间总览图已生成: {sheet_path}")
        return

    if args.brief:
        brief = json.loads(Path(args.brief).expanduser().read_text(encoding="utf-8"))
    else:
        t_lines = [x.strip() for x in (args.title or "AI 自动化工作流|3分钟出成片").split("|") if x.strip()]
        brief = {
            "preset": args.preset,
            "kicker": args.kicker,
            "brand": args.brand,
            "title_lines": t_lines,
            "subtitle": args.sub,
            "metric": args.metric,
            "metric_label": args.metric_label,
            "shot": args.shot,
            "theme": args.theme,
            "layout": args.layout,
        }
        if args.portrait:
            brief["portrait"] = True
        if args.no_portrait:
            brief["portrait"] = False

    res = render_cover_pair(
        brief, out_root,
        theme_key=args.theme if args.theme else None,
        layout=args.layout if args.layout else None,
        preset_key=args.preset if args.preset else brief.get("preset"),
        dpr=args.dpr,
        center_safe_16x9=args.center_safe_16x9,
        big_title=args.big_title,
    )
    print(f"✅ 3:4 竖版封面: {res['cover_3x4_png']} & {res['cover_3x4_jpg']}")
    print(f"✅ 16:9 视频首帧: {res['cover_16x9_png']}")
    for w in res["warns"]:
        print(f"   ⚠ {w}")
    for e in res["errors"]:
        print(f"   ❌ {e}")


if __name__ == "__main__":
    main()
