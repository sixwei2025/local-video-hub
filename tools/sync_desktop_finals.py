#!/usr/bin/env python3
"""桌面产线成片 → 视频中心「待确认」自动入库（兜底）。

只扫 config.output_dirs 里存在的桌面文件夹；跳过小样/中间版/已入库路径；
用 hub new + hub submit 建 bot 作品，状态停在待确认。不改待发布、不发平台。

用法：
  cd ~/video-hub && .venv/bin/python tools/sync_desktop_finals.py [--dry-run] [--limit N] [--days D] [--min-duration S]
stdout 永远一行 JSON。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HUB = ROOT / "hub.py"
VENV_PY = ROOT / ".venv/bin/python"
CFG_PATH = ROOT / "config.json"
DB_PATH = ROOT / "data/meta.db"
REG_PATH = ROOT / "bot_registry.json"

SKIP_NAME = re.compile(
    r"(小样|样片|dryrun|probe|test|测试|demo|_qc|qc_|_tmp|tmp_|preview|无声|nosub|silent)",
    re.I,
)
COVER_HINT = re.compile(r"封面|cover", re.I)
VER_IN_STEM = re.compile(r"(?i)(?:^|[-_])v(\d+)(?:[-_]|$)")
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}
VID_EXT = {".mp4", ".mov", ".m4v"}


def load_cfg():
    return json.loads(CFG_PATH.read_text(encoding="utf-8"))


def load_bots():
    return json.loads(REG_PATH.read_text(encoding="utf-8"))


def db():
    c = sqlite3.connect(str(DB_PATH))
    c.row_factory = sqlite3.Row
    return c


def known_video_paths(c) -> set[str]:
    out = set()
    for r in c.execute("select path from assets where kind='video' and path is not null"):
        if r["path"]:
            out.add(os.path.realpath(r["path"]))
    for r in c.execute("select selected_path from works where selected_path is not null"):
        if r["selected_path"]:
            out.add(os.path.realpath(r["selected_path"]))
    return out


def titled_norms(c) -> dict[str, dict]:
    """normalized title → best existing work (prefer published / has selected_path)."""
    best = {}
    for r in c.execute(
        "select id,title,state,selected_path,archived from works where title is not null and title!=''"
    ):
        n = norm_title(r["title"])
        if not n:
            continue
        score = (
            2 if r["state"] == "published" else 1 if r["selected_path"] else 0,
            0 if r["archived"] else 1,
        )
        cur = best.get(n)
        if not cur or score > cur[0]:
            best[n] = (score, dict(r))
    return {k: v[1] for k, v in best.items()}


def output_roots(cfg) -> list[str]:
    seen, roots = set(), []
    for k, v in cfg.get("output_dirs", {}).items():
        if str(k).startswith("_"):
            continue
        exp = os.path.expanduser(v)
        if not os.path.isdir(exp):
            continue
        rp = os.path.realpath(exp)
        if rp in seen:
            continue
        seen.add(rp)
        roots.append(rp)
    return roots


def line_of(path: str, cfg) -> str:
    for r in cfg.get("rules", []):
        if re.search(r["match"], path, re.I):
            return r["line"]
    return "other"


def type_style_of(path: str, cfg) -> tuple[str, str]:
    for r in cfg.get("style_rules", {}).get("rules", []):
        if re.search(r["match"], path, re.I):
            return r.get("type") or "", r.get("style") or ""
    return "", ""


def bot_for(vtype: str, line: str, bots_doc) -> str:
    for b in bots_doc.get("bots", []):
        if vtype and vtype in b.get("types", []):
            return b["name"]
    for b in bots_doc.get("bots", []):
        if line and line in b.get("lines", []):
            return b["name"]
    # fallback lab lead
    for b in bots_doc.get("bots", []):
        if b.get("id") == "lead":
            return b["name"]
    return "短视频部门负责人·实验室"


def topics_for(vtype: str, line: str, cfg) -> list[str]:
    pd = cfg.get("publish_defaults", {})
    for key in (vtype, line, "other"):
        if key and key in pd and isinstance(pd[key], dict):
            t = [x for x in pd[key].get("topics") or [] if x]
            if t:
                return t
    return ["短视频"]


def clean_stem_title(stem: str, cfg) -> str:
    tr = cfg.get("title_rules", {})
    s = stem
    s = re.sub(tr.get("strip_prefix", "^$"), "", s, flags=re.I)
    for _ in range(3):
        s = re.sub(tr.get("strip_suffix", "^$"), "", s, flags=re.I)
    s = re.sub(r"_+", " ", s).strip(" -_")
    al = tr.get("aliases") or {}
    for k, v in sorted(((k, v) for k, v in al.items() if not str(k).startswith("_")), key=lambda x: -len(x[0])):
        s = re.sub(r"(?<![A-Za-z0-9])" + re.escape(k) + r"(?![A-Za-z])", v, s, flags=re.I)
    return s.strip() or stem


def norm_title(t: str) -> str:
    t = (t or "").lower()
    t = re.sub(r"[·\-_|｜\s【】\[\]()（）]+", "", t)
    t = re.sub(r"v\d+$", "", t)
    return t


def version_key(stem: str, cfg) -> tuple[str, int | None]:
    """Return (group_stem_without_version, version_num or None if unversioned)."""
    vr = cfg.get("version_rules", {}).get("tokens", "")
    s = stem
    # explicit vN
    m = None
    for mm in VER_IN_STEM.finditer(stem):
        m = mm
    ver = int(m.group(1)) if m else None
    if vr:
        s2 = re.sub(r"(?:^|[-_\s])(?:" + vr + r")(?=$|[-_\s])", " ", s, flags=re.I)
        s2 = re.sub(r"\s+", " ", s2).strip(" -_")
        if s2:
            s = s2
    if m:
        # also strip the matched vN chunk
        s = (stem[: m.start()] + stem[m.end() :]).strip("-_ ")
        s = re.sub(r"[-_\s]+", "-", s).strip("-") or s
    return s.lower(), ver


def probe_duration(path: str) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return float((r.stdout or "0").strip() or 0)
    except Exception:
        return 0.0


def find_cover(video: str) -> str | None:
    p = Path(video)
    d = p.parent
    stem = p.stem
    cands = []
    for f in d.iterdir():
        if not f.is_file() or f.suffix.lower() not in IMG_EXT:
            continue
        if f.stem == stem or (f.stem.startswith(stem) and COVER_HINT.search(f.stem)):
            # prefer 3x4 / 封面 without 退回/旧/横
            name = f.name
            score = 0
            if COVER_HINT.search(name):
                score += 2
            if re.search(r"3x4|3：4|竖", name, re.I):
                score += 3
            if re.search(r"退回|旧|横封面|4x3", name, re.I):
                score -= 5
            if f.stem == stem:
                score += 1
            cands.append((score, f.stat().st_mtime, str(f)))
    if not cands:
        return None
    cands.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return cands[0][2]


def make_cover(video: str, out: str) -> str:
    # 抽首帧，裁成 3:4
    vf = "scale=1080:1440:force_original_aspect_ratio=increase,crop=1080:1440"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", video, "-frames:v", "1", "-vf", vf, out],
        check=True,
        timeout=90,
        stdin=subprocess.DEVNULL,
    )
    return out


def hub_run(args: list[str]) -> dict:
    cmd = [str(VENV_PY), str(HUB)] + args
    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    line = (r.stdout or "").strip().splitlines()[-1] if (r.stdout or "").strip() else ""
    try:
        data = json.loads(line) if line else {"ok": False, "error": "无 JSON 输出", "stderr": (r.stderr or "")[:400]}
    except json.JSONDecodeError:
        data = {"ok": False, "error": "非 JSON", "raw": line[:400], "stderr": (r.stderr or "")[:400]}
    data["_exit"] = r.returncode
    data["_stderr"] = (r.stderr or "").strip()[:500]
    return data


def collect_candidates(cfg, roots, known, titled, days: int | None, min_duration: float):
    cut = None
    if days is not None and days >= 0:
        cut = datetime.now() - timedelta(days=days)
    excl = [re.compile(x) for x in cfg.get("exclude", [])]
    raw = []
    for root in roots:
        for dp, dns, fns in os.walk(root):
            dns[:] = [d for d in dns if not d.startswith(".")]
            # exclude path segments
            if any(e.search(dp + "/") for e in excl):
                dns[:] = []
                continue
            for fn in fns:
                if Path(fn).suffix.lower() not in VID_EXT:
                    continue
                if fn.startswith("."):
                    continue
                if SKIP_NAME.search(fn) or SKIP_NAME.search(dp):
                    continue
                path = os.path.join(dp, fn)
                try:
                    st = os.stat(path)
                except OSError:
                    continue
                if cut and datetime.fromtimestamp(st.st_mtime) < cut:
                    continue
                rp = os.path.realpath(path)
                if rp in known:
                    continue
                raw.append({"path": path, "rp": rp, "mtime": st.st_mtime, "stem": Path(fn).stem, "size": st.st_size})

    # version dedup within same directory group stem
    groups: dict[tuple, list] = {}
    for it in raw:
        gstem, ver = version_key(it["stem"], cfg)
        parent = os.path.dirname(it["path"])
        key = (parent, gstem)
        it["ver"] = ver
        it["gstem"] = gstem
        groups.setdefault(key, []).append(it)

    winners = []
    for _, items in groups.items():
        unversioned = [x for x in items if x["ver"] is None]
        if unversioned:
            # 有无版本号最终版 → 丢掉旧 v*
            pick = max(unversioned, key=lambda x: x["mtime"])
        else:
            pick = max(items, key=lambda x: (x["ver"] or 0, x["mtime"]))
        winners.append(pick)

    # enrich + title skip
    out = []
    for it in winners:
        title = clean_stem_title(it["stem"], cfg)
        # hub 核对 title_max（六伟2026-10-30 放宽到 50）；发布页另截抖音≤30
        title_max = int((cfg.get("check_rules") or {}).get("title_max") or 50)
        if len(title) > title_max:
            title = title[:title_max].rstrip("，,、 ·-_|｜")
        nt = norm_title(title)
        exist = titled.get(nt)
        if exist and (exist.get("state") == "published" or exist.get("selected_path")):
            it["skip_reason"] = f"选题已有作品 {exist['id']} ({exist.get('state')})"
            it["title"] = title
            continue
        # duration
        dur = probe_duration(it["path"])
        it["duration"] = dur
        if min_duration and dur and dur < min_duration:
            it["skip_reason"] = f"时长过短 {dur:.1f}s"
            it["title"] = title
            continue
        line = line_of(it["path"], cfg)
        vtype, style = type_style_of(it["path"], cfg)
        if not vtype:
            # map line → a type key via reverse type_lines
            tl = {v: k for k, v in cfg.get("type_lines", {}).items() if not str(k).startswith("_")}
            # prefer first type that maps to this line from output_dirs keys near path
            vtype = next((k for k, v in cfg.get("type_lines", {}).items() if not str(k).startswith("_") and v == line), line)
        it.update(title=title, line=line, video_type=vtype, style=style, norm=nt)
        out.append(it)
    out.sort(key=lambda x: x["mtime"], reverse=True)
    return out, raw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=8, help="每轮最多入库条数")
    ap.add_argument("--days", type=int, default=None, help="只看最近 N 天；默认不限")
    ap.add_argument("--min-duration", type=float, default=8.0, help="短于此时长跳过；0 关闭")
    args = ap.parse_args()

    cfg = load_cfg()
    bots = load_bots()
    roots = output_roots(cfg)
    c = db()
    known = known_video_paths(c)
    titled = titled_norms(c)
    c.close()

    cands, raw = collect_candidates(cfg, roots, known, titled, args.days, args.min_duration)
    # also count skipped-by-title from collect (those not in cands)
    summary = {
        "ok": True,
        "dry_run": args.dry_run,
        "roots": [p.replace(str(Path.home()), "~") for p in roots],
        "scanned_videos_after_name_filter": len(raw),
        "gaps": len(cands),
        "limit": args.limit,
        "days": args.days,
        "submitted": [],
        "would_submit": [],
        "errors": [],
        "skipped_sample": [],
    }

    batch = cands[: max(0, args.limit)]
    for it in batch:
        line = it["line"]
        vtype = it["video_type"]
        bot = bot_for(vtype, line, bots)
        topics = topics_for(vtype, line, cfg)
        cover = find_cover(it["path"])
        cover_note = "existing" if cover else "ffmpeg"
        entry = {
            "path": it["path"].replace(str(Path.home()), "~"),
            "title": it["title"],
            "line": line,
            "video_type": vtype,
            "bot": bot,
            "mtime": datetime.fromtimestamp(it["mtime"]).strftime("%Y-%m-%d %H:%M"),
            "duration": round(it.get("duration") or 0, 1),
            "cover": (cover or "").replace(str(Path.home()), "~") if cover else "(will extract)",
        }
        if args.dry_run:
            summary["would_submit"].append(entry)
            continue

        # ensure cover
        if not cover:
            out_cover = str(Path(it["path"]).with_name(Path(it["path"]).stem + "_封面3x4_auto.jpg"))
            try:
                make_cover(it["path"], out_cover)
                cover = out_cover
            except Exception as e:
                summary["errors"].append({"path": entry["path"], "error": f"封面失败: {e}"})
                continue

        # hub new — line 用 type key 以便 output_dir / type_lines 正确
        line_arg = vtype or line
        new = hub_run(["new", "--bot", bot, "--line", line_arg, "--title", it["title"]] + (["--style", it["style"]] if it.get("style") else []))
        if not new.get("ok") or not new.get("work_id"):
            summary["errors"].append({"path": entry["path"], "step": "new", "resp": {k: new.get(k) for k in ("ok", "code", "error", "errors", "_exit")}})
            continue
        wid = new["work_id"]
        sub = hub_run(
            [
                "submit",
                wid,
                "--video",
                it["path"],
                "--cover",
                cover,
                "--title",
                it["title"],
                "--desc",
                "（简介由发布官填写）",
                "--topics",
                ",".join(topics),
            ]
        )
        if sub.get("ok") and sub.get("state") == "confirm":
            summary["submitted"].append({**entry, "work_id": wid, "cover_source": cover_note, "topics": topics})
        else:
            summary["errors"].append(
                {
                    "path": entry["path"],
                    "work_id": wid,
                    "step": "submit",
                    "resp": {k: sub.get(k) for k in ("ok", "code", "error", "errors", "state", "_exit")},
                    "stderr": sub.get("_stderr", "")[:300],
                }
            )

    # leftover gaps beyond limit (for report)
    summary["gaps_remaining_after_limit"] = max(0, len(cands) - len(batch))
    summary["gap_titles"] = [x["title"] for x in cands[:40]]
    print(json.dumps(summary, ensure_ascii=False))
    sys.exit(0 if not summary["errors"] else 1)


if __name__ == "__main__":
    main()
