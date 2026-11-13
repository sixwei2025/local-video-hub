#!/opt/homebrew/bin/python3.11
# -*- coding: utf-8 -*-
"""热点新闻 / 口播封面生成器 (升级为汇芯双画幅高级感杂志封面引擎)

完全向后兼容原 `hotnews_cover.py` / `hotnews_cover.sh` 参数：
  --line1 "4万个账号" [--line2 "AI额度被多扣"] [--kicker "一个周末"] [--subtitle "..."]
  [--bg 背景图.jpg] [--no-person] --out cover.png [--sheet sheet.jpg] [--theme midnight|swiss_dark|brand|paper]

升级亮点：
  1. 彻底告别粗糙 `rembg` 边缘灰块，默认直接调用高清精修抠像 `owner_cutout_hd.png`（保留温暖真实肤色，严禁纯黑白）。
  2. 同时生成 `--out`（16:9 横版首帧，支持中央 810px 3:4 安全区）与同目录 `*_封面3x4.jpg` 竖版 3:4 独立封面。
"""
import argparse
import os
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from render_video_cover import render_cover_pair

BANNED = ["采集快照", "快照", "抓取", "AI生成", "AI 生成", "ai生成"]


def make_sheet(img_16x9_path: Path, img_3x4_path: Path, out_sheet: Path):
    im16 = Image.open(img_16x9_path).convert("RGB").resize((1280, 720), Image.LANCZOS)
    im34 = Image.open(img_3x4_path).convert("RGB").resize((540, 720), Image.LANCZOS)
    s = Image.new("RGB", (1280 + 540 + 60, 800), (18, 18, 22))
    s.paste(im16, (20, 60))
    s.paste(im34, (1320, 60))
    d = ImageDraw.Draw(s)
    d.text((20, 22), "16:9 Opening Frame (1920x1080)", fill=(230, 230, 230))
    d.text((1320, 22), "3:4 Vertical Cover (1080x1440)", fill=(230, 230, 230))
    out_sheet.parent.mkdir(parents=True, exist_ok=True)
    s.save(out_sheet, quality=92)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--line1", required=True)
    ap.add_argument("--line2", default="")
    ap.add_argument("--kicker", default="")
    ap.add_argument("--subtitle", default="")
    ap.add_argument("--brand", default="袁六伟 · 一人AI公司")
    ap.add_argument("--bg", default="")
    ap.add_argument("--photo", default="")
    ap.add_argument("--person_h", type=int, default=760)
    ap.add_argument("--no-person", dest="no_person", action="store_true")
    ap.add_argument("--theme", default="midnight")
    ap.add_argument("--preset", default="huixin-founder-gold")
    ap.add_argument("--out", required=True)
    ap.add_argument("--sheet", default="")
    a = ap.parse_args()

    for s in (a.line1, a.line2, a.kicker, a.subtitle, a.brand):
        for b in BANNED:
            if b.lower() in (s or "").lower():
                raise SystemExit(f"封面文字含禁用词「{b}」：{s}")

    out_path = Path(a.out).expanduser().resolve()
    out_dir = out_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    lines = [x.strip() for x in (a.line1, a.line2) if x and x.strip()]
    brief = {
        "preset": a.preset if not a.no_person else "huixin-tech-flagship",
        "theme": a.theme,
        "kicker": a.kicker or "袁六伟 · 深度热点洞察",
        "brand": "HUIXIN INSIGHT",
        "title_lines": lines,
        "subtitle": a.subtitle or a.brand,
        "portrait": not a.no_person,
        "strip_left": "袁六伟 · 台州汇芯",
        "strip_right": "HOTNEWS INSIGHT",
    }
    if a.bg and os.path.isfile(a.bg) and a.no_person:
        brief["shot"] = a.bg
        brief["layout"] = "ui-showcase"

    stem = out_path.stem
    res = render_cover_pair(
        brief,
        out_dir,
        theme_key=a.theme,
        preset_key=brief["preset"],
        out_3x4_name=f"{stem}_3x4.png",
        out_16x9_name=f"{stem}_16x9.png",
        dpr=2,
        center_safe_16x9=False,
    )

    # 根据 --out 的后缀以及文件名判断调用方期望 3:4 还是 16:9
    wants_3x4 = ("3x4" in stem.lower()) or ("竖" in stem)
    src_png = Path(res["cover_3x4_png"] if wants_3x4 else res["cover_16x9_png"])
    if out_path.suffix.lower() in (".jpg", ".jpeg"):
        Image.open(src_png).convert("RGB").save(out_path, quality=95, subsampling=0)
    else:
        Image.open(src_png).save(out_path)

    if a.sheet:
        make_sheet(Path(res["cover_16x9_png"]), Path(res["cover_3x4_png"]), Path(a.sheet).expanduser().resolve())

    print("saved", str(out_path))


if __name__ == "__main__":
    main()
