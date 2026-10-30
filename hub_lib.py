"""Grokbot 固定提交入口的核心逻辑（CLI hub.py 与网站 app.py 共用）。
作品生命周期：start(开工建作品=制作中) → stage(阶段) → submit(成套交付) → check(核对) → 待确认；失败 fail/重试 retry。"""
import hashlib, json, os, sqlite3, subprocess, urllib.request
from datetime import datetime
from pathlib import Path
import queue_lib
import bot_registry

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data/meta.db"
CFG = ROOT / "config.json"
IMG = {".jpg", ".jpeg", ".png", ".webp"}
VID = {".mp4", ".mov", ".m4v", ".webm"}
SUB = {".srt", ".vtt", ".ass", ".json", ".txt"}

class HubError(Exception):
    def __init__(self, code, msg, detail=None): super().__init__(msg); self.code, self.msg, self.detail = code, msg, detail or []

def cfg(): return json.loads(CFG.read_text(encoding="utf-8"))
def now(): return queue_lib.now()
def db():
    c = sqlite3.connect(DB, timeout=30); c.row_factory = sqlite3.Row
    c.execute("""create table if not exists works(id text primary key, group_key text unique, title text, description text, topics text default '[]',
                 state text, featured int default 0, archived int default 0, selected_path text, cover_path text, subtitle_path text,
                 created_at text, updated_at text)""")
    c.execute("create table if not exists assets(id integer primary key autoincrement, work_id text, kind text, path text, value text, label text, created_at text)")
    cols = {r[1] for r in c.execute("pragma table_info(works)")}
    for col, t in (("job_id", "text"), ("stage", "text"), ("check_errors", "text"), ("origin", "text"), ("error", "text"),
                   ("line", "text"), ("video_type", "text"), ("style_id", "text"), ("output_dir", "text"), ("producer_bot", "text")):
        if col not in cols: c.execute(f"alter table works add column {col} {t}")
    return c

def _work(c, wid):
    r = c.execute("select * from works where id=?", (wid,)).fetchone()
    if not r: raise HubError(4, f"作品不存在：{wid}")
    return dict(r)

def _job(jid):
    j = next((x for x in queue_lib.load_jobs() if x["id"] == jid), None)
    if not j: raise HubError(4, f"任务不存在：{jid}")
    return j

def scan_roots(): return [os.path.realpath(os.path.expanduser(r)) for r in cfg()["scan_roots"]]
def under_roots(p): rp = os.path.realpath(p); return any(rp.startswith(r + "/") for r in scan_roots())

def probe(p):
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration",
                              "-of", "json", p], capture_output=True, text=True, timeout=30)
        d = json.loads(out.stdout or "{}"); s = (d.get("streams") or [{}])[0]
        return {"duration": float(d.get("format", {}).get("duration") or 0), "width": s.get("width"), "height": s.get("height")}
    except Exception as e:
        raise HubError(6, f"ffprobe 读不出视频：{p}（{e}）")

def ping_rescan():
    try: urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8765/api/rescan", method="POST"), timeout=60).read(); return True
    except Exception: return False

def work_view(c, wid):
    w = _work(c, wid); w["topics"] = json.loads(w.get("topics") or "[]"); w["check_errors"] = json.loads(w.get("check_errors") or "[]")
    w["assets"] = [dict(r) for r in c.execute("select kind,path,value,label,created_at from assets where work_id=? order by id", (wid,))]
    return w

# ---------- 生命周期 ----------
def next_job(bot=None):
    bot = bot_registry.canonical(bot)
    p = [j for j in queue_lib.load_jobs() if j["status"] == "pending" and not j.get("deleted") and j.get("dispatch_state") != "unassigned" and (not j.get("target_bot") or bot_registry.canonical(j["target_bot"]) == bot)]
    return sorted(p, key=lambda j: j.get("created_at", ""))[0] if p else None

def start(jid, title=None, bot=None):
    bot = bot_registry.canonical(bot)
    j = _job(jid)
    target = bot_registry.canonical(j.get("target_bot"))
    if target and bot != target: raise HubError(5, f"这是发给「{target}」的修改，请由该机器人使用 --bot 领取")
    if j.get("dispatch_state") == "unassigned": raise HubError(5, "修改任务尚未登记出品方，请先在预览页绑定机器人")
    if j["status"] != "pending": raise HubError(5, "任务已被领取或已完成，不能重复开工")
    if j["status"] in ("done",): raise HubError(5, f"任务 {jid} 已完成，不能再开工；要重做请用 retry")
    if not queue_lib.claim_job(jid,bot): raise HubError(5,"任务已被其他机器人领取，或不属于当前机器人")
    c = db(); t = now()
    wid = j.get("work_id")
    if wid and c.execute("select 1 from works where id=?", (wid,)).fetchone():   # 修改任务：沿用原作品
        c.execute("update works set state='making', stage=?, job_id=?, error=null, check_errors='[]', updated_at=? where id=?", ("开工：按修改意见处理", jid, t, wid))
    else:
        wid = j.get("work_id") or hashlib.sha1(("job:" + jid).encode()).hexdigest()[:12]
        if not c.execute("select 1 from works where id=?", (wid,)).fetchone():
            c.execute("""insert into works(id,group_key,title,description,topics,state,featured,archived,created_at,updated_at,job_id,stage,origin,line,video_type,style_id,output_dir,check_errors)
                         values(?,?,?,?,?,?,0,0,?,?,?,?,?,?,?,?,?,'[]')""",
                      (wid, "sub:" + wid, title or (j.get("topic") or j["prompt"])[:40], "", "[]", "making", t, t, jid, "开工", "bot",
                       j.get("line"), j.get("video_type"), j.get("style_id"), j.get("output_dir")))
        else:
            c.execute("update works set state='making', stage='重新开工', error=null, updated_at=? where id=?", (t, wid))
    if bot: c.execute("update works set producer_bot=? where id=?", (bot, wid))
    c.commit(); c.close()
    queue_lib.update_job(jid, "running"); queue_lib.patch_job(jid, work_id=wid, stage="开工", claimed_by=bot or "", received_at=now(), dispatch_state="accepted")
    return wid

def stage(wid, text):
    c = db(); w = _work(c, wid)
    if w["state"] != "making": raise HubError(5, f"作品当前是「{w['state']}」，只有制作中的作品能更新阶段")
    c.execute("update works set stage=?, updated_at=? where id=?", (text, now(), wid)); c.commit(); c.close()
    if w.get("job_id"): queue_lib.patch_job(w["job_id"], stage=text)

def check(wid, save=True):
    """核对齐全与一致。返回错误列表（空=通过）。"""
    c = db(); w = work_view(c, wid); errs = []
    vids = [a for a in w["assets"] if a["kind"] == "video"]
    if not vids: errs.append("缺视频：还没有提交成片")
    else:
        v = vids[-1]["path"]
        if not os.path.isfile(v): errs.append(f"视频文件不存在：{v}")
        else:
            try:
                p = probe(v)
                if p["duration"] <= 0.5: errs.append("视频时长为 0 或过短")
                j = None
                if w.get("job_id"):
                    try: j = _job(w["job_id"])
                    except HubError: pass
                asp = (j or {}).get("aspect") or ""
                if asp and p["width"] and p["height"]:
                    portrait = p["height"] > p["width"]
                    if asp in ("9:16", "3:4") and not portrait: errs.append(f"画幅不一致：要求 {asp} 竖屏，实际 {p['width']}x{p['height']}")
                    if asp == "16:9" and portrait: errs.append(f"画幅不一致：要求 16:9 横屏，实际 {p['width']}x{p['height']}")
            except HubError as e: errs.append(e.msg)
            if not under_roots(v): errs.append("视频不在扫描目录内（请放到任务的保存位置）")
    cov = [a for a in w["assets"] if a["kind"] == "cover"]
    if not cov: errs.append("缺封面")
    elif not os.path.isfile(cov[-1]["path"]): errs.append(f"封面文件不存在：{cov[-1]['path']}")
    if not (w.get("title") or "").strip(): errs.append("缺标题")
    elif len(w["title"]) > 30: errs.append(f"标题超过 30 字（{len(w['title'])} 字）")
    if not (w.get("description") or "").strip(): errs.append("缺简介")
    if not w["topics"]: errs.append("缺话题（至少 1 个）")
    for a in w["assets"]:
        if a["kind"] == "subtitle" and not os.path.isfile(a["path"]): errs.append(f"字幕文件不存在：{a['path']}")
    if save:
        st = "confirm" if not errs and w["state"] == "making" else w["state"]
        c.execute("update works set check_errors=?, state=?, stage=?, updated_at=? where id=?",
                  (json.dumps(errs, ensure_ascii=False), st, "核对通过，待确认" if not errs else "核对未通过：" + errs[0], now(), wid)); c.commit()
    c.close(); return errs

def submit(wid, video=None, cover=None, title=None, desc=None, topics=None, subs=None, label=None):
    c = db(); w = _work(c, wid)
    if w["state"] not in ("making",): raise HubError(5, f"作品当前是「{w['state']}」，先 start 对应任务再提交")
    t = now(); n_ver = c.execute("select count(*) from assets where work_id=? and kind='video'", (wid,)).fetchone()[0]
    def chk(p, exts, what):
        if not p: return None
        p = os.path.abspath(os.path.expanduser(p))
        if not os.path.isfile(p): raise HubError(6, f"{what}文件不存在：{p}")
        if Path(p).suffix.lower() not in exts: raise HubError(2, f"{what}格式不支持：{Path(p).suffix}（支持 {' '.join(sorted(exts))}）")
        return p
    video, cover, subs = chk(video, VID, "视频"), chk(cover, IMG, "封面"), chk(subs, SUB, "字幕")
    if video and not under_roots(video): raise HubError(3, f"视频必须放在扫描目录内（建议任务保存位置 {w.get('output_dir')}）：{video}")
    if not video and not n_ver: raise HubError(3, "第一次提交必须带 --video")
    lab = label or (f"v{n_ver + 1}" if video else "补充素材")
    if video:
        probe(video)
        if w.get("producer_bot"):
            c.execute("insert into assets(work_id,kind,path,value,label,created_at) values(?,?,?,?,?,?)", (wid,"producer",video,w["producer_bot"],lab,t))
        c.execute("insert into assets(work_id,kind,path,label,created_at) values(?,?,?,?,?)", (wid, "video", video, lab, t))
        if not w.get("selected_path"): c.execute("update works set selected_path=? where id=?", (video, wid))
    if cover: c.execute("insert into assets(work_id,kind,path,label,created_at) values(?,?,?,?,?)", (wid, "cover", cover, lab, t)); c.execute("update works set cover_path=? where id=?", (cover, wid))
    if subs: c.execute("insert into assets(work_id,kind,path,label,created_at) values(?,?,?,?,?)", (wid, "subtitle", subs, lab, t)); c.execute("update works set subtitle_path=? where id=?", (subs, wid))
    sets = {}
    if title is not None: sets["title"] = title.strip()
    if desc is not None: sets["description"] = desc.strip()
    if topics is not None: sets["topics"] = json.dumps([x.strip().lstrip("#") for x in topics if x.strip()], ensure_ascii=False)
    for k, v in sets.items(): c.execute(f"update works set {k}=? where id=?", (v, wid))
    for k in ("title", "description", "topics"):
        if k in sets: c.execute("insert into assets(work_id,kind,value,label,created_at) values(?,?,?,?,?)", (wid, k, sets[k], lab, t))
    c.execute("update works set stage='已提交，核对中', updated_at=? where id=?", (t, wid)); c.commit(); c.close()
    errs = check(wid)
    jid = w.get("job_id")
    if jid:
        if errs: queue_lib.patch_job(jid, stage="核对未通过", check_errors=errs)
        else:
            c = db(); paths = [a["path"] for a in work_view(c, wid)["assets"] if a["kind"] in ("video", "cover") and a["path"]]; c.close()
            queue_lib.update_job(jid, "done", results=paths[-2:]); queue_lib.patch_job(jid, stage="待确认", check_errors=[])
    if not errs and video: prune_old(wid, video, cover)
    ping_rescan()
    if errs: raise HubError(3, "核对未通过", errs)
    return lab

def prune_old(wid, keep_video, keep_cover=None):
    """新版本核对通过后：旧版本视频/封面移到废纸篓（已发布的保留）。"""
    c = db(); rows = [dict(r) for r in c.execute("select kind,path from assets where work_id=? and kind in ('video','cover') and path is not null", (wid,))]
    pubs = {r[0] for r in c.execute("select path from meta where tags like '%已发%' or status='published' or library='publish' or rating='love'")}
    feat = c.execute("select featured from works where id=?", (wid,)).fetchone()[0]; c.close()
    if feat: return []
    keep = {keep_video, keep_cover}
    old = [r["path"] for r in rows if r["path"] not in keep and r["path"] not in pubs and os.path.exists(r["path"])]
    old = list(dict.fromkeys(old))
    if not old: return []
    ok, bad = trash(old); forget_paths(ok)
    c = db(); c.execute("update works set selected_path=? where id=?", (keep_video, wid)); c.commit(); c.close()
    log_delete([[now(), wid, "", "新版本自动清理旧版本", f, "已移到废纸篓", "否"] for f in ok] + [[now(), wid, "", "新版本自动清理旧版本", f, "失败：" + r, "否"] for f, r in bad])
    return ok

def fail(ref, reason):
    c = db(); r = c.execute("select * from works where id=? or job_id=?", (ref, ref)).fetchone()
    jid = (r["job_id"] if r else None) or ref
    if r: c.execute("update works set state='failed', stage=?, error=?, updated_at=? where id=?", ("失败：" + reason, reason, now(), r["id"])); c.commit()
    c.close()
    if not queue_lib.update_job(jid, "failed", error=reason) and not r: raise HubError(4, f"找不到作品或任务：{ref}")
    if jid: queue_lib.patch_job(jid, stage="失败")
    return r["id"] if r else None

def retry(jid):
    j = _job(jid)
    if j["status"] not in ("failed", "done"): raise HubError(5, f"任务 {jid} 还在「{j['status']}」，不需要重试")
    keep = {k: v for k, v in j.items() if k not in ("id", "status", "result_paths", "error", "created_at", "updated_at", "started_at", "finished_at", "stage", "check_errors")}
    keep["retry_of"] = jid
    nj = queue_lib.add_job(keep.pop("prompt"), keep.pop("ref_images", []), keep.pop("output_dir"), keep.pop("line"),
                           keep.pop("video_type", ""), keep.pop("style_id", ""), keep.pop("style_custom_text", ""), keep.pop("style_ref_images", []), **keep)
    if j.get("work_id"):
        c = db(); c.execute("update works set stage='已重新排队', error=null where id=?", (j["work_id"],)); c.commit(); c.close()
    return nj

def set_producer(wid, bot):
    try: bot = bot_registry.canonical(bot)
    except ValueError as e: raise HubError(2,str(e))
    if not bot or len(bot) > 80: raise HubError(2, "请填写机器人实际名称（不超过80字）")
    c = db()
    try:
        _work(c, wid)
        c.execute("update works set producer_bot=?,updated_at=? where id=?", (bot,now(),wid));c.commit()
    finally: c.close()
    # Only route outstanding revisions for this work; never redirect a running job.
    for j in queue_lib.load_jobs():
        if j.get("work_id") == wid and j.get("kind") == "revise" and j["status"] == "pending":
            queue_lib.patch_job(j["id"],target_bot=bot,dispatch_state="queued",stage=f"等待{bot}领取")
    return bot

def revise(wid, text, version_id=None, source_video=None):
    """Queue to the recorded producer. A queued task is not a delivered chat message."""
    c = db(); w = work_view(c, wid); c.close()
    if not text.strip(): raise HubError(2, "请写清楚要改什么")
    vids = [a["path"] for a in w["assets"] if a["kind"] == "video"]
    creator = (w.get("producer_bot") or "").strip()
    producer = creator or bot_registry.responsible(w.get("video_type"),w.get("line"))
    return queue_lib.add_job(f"【修改】{text.strip()}\n作品：{w.get('title') or ''}", [], w.get("output_dir") or (os.path.dirname(source_video or w.get("selected_path") or (vids[-1] if vids else "")) or str(Path.home() / "Desktop")),
                             w.get("line") or "lab", w.get("video_type") or "", w.get("style_id") or "", "", [], kind="revise", work_id=wid,
                             revise_text=text.strip(), source_video=source_video or w.get("selected_path") or (vids[-1] if vids else ""), source_version_id=version_id or "",
                             topic=w.get("title") or "",target_bot=producer,routing_basis="producer" if creator else "responsibility",dispatch_state="queued" if producer else "unassigned",
                             stage=f"等待{producer}领取" if producer else "待指定出品方")

def delete_work(wid):
    c = db(); _work(c, wid); c.execute("delete from assets where work_id=?", (wid,)); c.execute("delete from works where id=?", (wid,)); c.commit(); c.close()

def autoattach(items):
    """第 9 项：制作中作品的保存目录里出现新成片 → 自动挂到该作品（只登记，不移动文件），等待补齐文案后提交。"""
    c = db(); n = 0
    known = {r[0] for r in c.execute("select path from assets where kind='video'")}
    for w in c.execute("select * from works where state='making' and origin='bot' and output_dir is not null").fetchall():
        od = os.path.realpath(os.path.expanduser(w["output_dir"]))
        try: t0 = datetime.fromisoformat(w["created_at"]).timestamp()
        except Exception: continue
        for it in items:
            if it["kind"] != "final" or it["path"] in known: continue
            if os.path.realpath(os.path.dirname(it["path"])) == od and it["mtime"] >= t0:
                c.execute("insert into assets(work_id,kind,path,label,created_at) values(?,?,?,?,?)", (w["id"], "video", it["path"], "自动发现", now()))
                c.execute("update works set stage=?, selected_path=coalesce(selected_path,?) where id=?", ("检测到新成片，等待提交标题/简介/封面/话题", it["path"], w["id"]))
                known.add(it["path"]); n += 1
    c.commit(); c.close(); return n

def sub_map():
    """被 bot 提交的视频路径 → 作品 group_key，用来把扫描到的文件归到对应作品。"""
    c = db(); m = {r[0]: (r[1], r[2] or "", r[3] or "") for r in c.execute("select a.path, w.group_key, w.video_type, w.style_id from assets a join works w on w.id=a.work_id where a.kind='video' and w.origin='bot'")}; c.close(); return m

# ---------- 手动删除：移到废纸篓（可恢复），绝不永久删除 ----------
import csv as _csv
DEL_LOG = ROOT / "data/删除记录.csv"
def trash(paths):
    """用 Finder 把文件移到废纸篓。返回 (成功列表, 失败[(路径,原因)])。"""
    ok, bad = [], []
    for p in paths:
        if not os.path.exists(p): bad.append((p, "文件不存在")); continue
        if not under_roots(p): bad.append((p, "不在扫描目录内，拒绝删除")); continue
        esc = p.replace("\\", "\\\\").replace('"', '\\"')
        r = subprocess.run(["osascript", "-e", f'tell application "Finder" to delete (POSIX file "{esc}")'], capture_output=True, text=True, timeout=60)
        if r.returncode == 0 and not os.path.exists(p): ok.append(p)
        else: bad.append((p, (r.stderr or "Finder 未完成").strip()[:120]))
    return ok, bad

def log_delete(rows):
    new = not DEL_LOG.exists()
    with open(DEL_LOG, "a", newline="", encoding="utf-8-sig" if new else "utf-8") as f:
        w = _csv.writer(f)
        if new: w.writerow(["时间", "作品id", "作品标题", "范围", "文件", "结果", "是否已发布"])
        for r in rows: w.writerow(r)

def forget_paths(paths, wid=None, whole=False):
    # Close/rollback even when another request temporarily owns the database.
    # BEGIN IMMEDIATE avoids a read→write upgrade racing other connections.
    import time
    for attempt in range(4):
        c = sqlite3.connect(DB, timeout=5); c.row_factory = sqlite3.Row
        try:
            c.execute("begin immediate")
            for p in paths:
                c.execute("delete from meta where path=?", (p,))
                c.execute("delete from assets where path=?", (p,))
                c.execute("update groups set selected_path=null where selected_path=?", (p,))
                for col in ("selected_path", "cover_path", "subtitle_path"):
                    c.execute(f"update works set {col}=null where {col}=?", (p,))
            if whole and wid:
                c.execute("delete from assets where work_id=?", (wid,))
                c.execute("delete from works where id=?", (wid,))
            c.commit()
            break
        except sqlite3.OperationalError as e:
            c.rollback()
            if "locked" not in str(e).lower() or attempt == 3: raise
            time.sleep(.15 * (attempt + 1))
        finally:
            c.close()
    # Keep the audit trail, remove obsolete previews from completed generation jobs.
    removed = set(paths)
    for job in queue_lib.load_jobs():
        result = [p for p in job.get("result_paths", []) if p not in removed]
        patch = {}
        if result != job.get("result_paths", []): patch["result_paths"] = result
        if whole and wid and job.get("work_id") == wid:
            patch.update(deleted=True, deleted_at=now())
        elif job.get("result_paths") and not result and job.get("status") == "done":
            patch.update(results_deleted=True, deleted_at=now())
        if patch: queue_lib.patch_job(job["id"], **patch)
