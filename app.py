import hub_lib, dedup_core, sys, glob
import shutil, csv, hashlib, json, os, re, sqlite3, subprocess, threading, time
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import queue_lib

ROOT = Path(__file__).resolve().parent
HOME = Path.home()
CFG_PATH = ROOT / "config.json"
DB = ROOT / "data/meta.db"
THUMBS = ROOT / "cache/thumbs"
UPLOADS = ROOT / "uploads"
# launchd 无 shell PATH，裸调 ffmpeg 会 FileNotFound；webp 编码器在 brew ffmpeg 8.1 也常缺
FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
if not Path(FFMPEG).is_file():
    FFMPEG = "/usr/local/bin/ffmpeg"
STATUS_NAMES = {"test": "测试", "review": "待审", "published": "已发布"}

app = FastAPI(title="视频中心")
from fastapi.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1024)
class CachedStatic(StaticFiles):
    async def get_response(self, path, scope):
        r = await super().get_response(path, scope)
        r.headers["Cache-Control"] = "public, max-age=300, must-revalidate"   # 带 ETag，改了能刷新
        return r
app.mount("/static", CachedStatic(directory=ROOT / "static"), name="static")
INDEX = {"items": [], "by_id": {}, "scanned_at": None, "scanning": False}
LOCK = threading.Lock()

def cfg(): return json.loads(CFG_PATH.read_text(encoding="utf-8"))
def ex(p): return os.path.expanduser(p)
def db():
    c = sqlite3.connect(DB, timeout=30); c.row_factory = sqlite3.Row
    c.execute("create table if not exists meta(path text primary key, status text, tags text default '[]', note text default '', updated_at text)")
    cols = {r[1] for r in c.execute("pragma table_info(meta)")}
    if "rating" not in cols: c.execute("alter table meta add column rating text")      # love | ok | scrap | NULL
    if "library" not in cols: c.execute("alter table meta add column library text")    # publish | normal | scrap
    if "video_type" not in cols: c.execute("alter table meta add column video_type text")  # 手动指定，空=用自动推断
    if "style_id" not in cols: c.execute("alter table meta add column style_id text")
    c.execute("create table if not exists groups(key text primary key, selected_path text, updated_at text)")
    hub_lib.db().close()   # works/assets 新列迁移
    # 作品为单位：works 一行一个作品；版本=同 group_key 的视频文件；assets 记封面/字幕/文案等附属物
    c.execute("""create table if not exists works(id text primary key, group_key text unique, title text, description text, topics text default '[]',
                 state text, featured int default 0, archived int default 0, selected_path text, cover_path text, subtitle_path text,
                 created_at text, updated_at text)""")
    c.execute("""create table if not exists assets(id integer primary key autoincrement, work_id text, kind text, path text, value text,
                 label text, created_at text)""")
    if "first_seen" not in [r[1] for r in c.execute("pragma table_info(works)")]:
        c.execute("alter table works add column first_seen int default 0")  # 首次入库时间(epoch)；0=基线（存量作品，不算新增）
    c.execute("""create trigger if not exists works_first_seen after insert on works when coalesce(new.first_seen,0)=0
                 begin update works set first_seen=cast(strftime('%s','now') as int) where id=new.id; end""")
    c.commit()
    return c
LIB_OF = {"love": "publish", "ok": "normal", "scrap": "scrap", None: "normal"}
RATING_NAMES = {"love": "特别满意", "ok": "一般", "scrap": "特别不满意"}
def fid(path): return hashlib.sha1(path.encode()).hexdigest()[:16]

def published_set(c):
    s = {}
    for f in c.get("publish_records", []):
        p = Path(ex(f))
        if not p.exists(): continue
        with open(p, encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                v = (r.get("视频") or "").strip()
                if v and (r.get("结果") or "").strip() == "成功":
                    s[os.path.normpath(ex(v))] = {"title": r.get("标题", ""), "time": r.get("时间", "")}
    return s

_SCAN_LOCK = threading.Lock()
def scan():
    with _SCAN_LOCK:
        return _scan_files()

def _scan_files():
    c = cfg()
    excl = [re.compile(x) for x in c["exclude"]]
    rules = [(re.compile(r["match"], re.I), r["line"]) for r in c["rules"]]
    draft_re = re.compile(c["kind_rules"]["draft"], re.I)
    test_re = re.compile(c["status_rules"]["test"], re.I)
    vext, iext = set(c["video_ext"]), set(c["image_ext"])
    pub = published_set(c)
    videos, images = [], []
    seen = set()
    # 白名单扫描：只扫 output_dirs 里的桌面产线文件夹 + hub.py 登记的文件；已发布/风格样片在白名单外也按登记显示
    try: _st = queue_lib.STYLES.read_text(encoding="utf-8")
    except Exception: _st = ""
    protect = set(pub) | set(re.findall(r'"(/[^"]+)"', _st)) | {ex(x) for x in re.findall(r'"(~/[^"]+)"', _st)} | set(hub_lib.sub_map())
    roots = sorted({os.path.realpath(ex(v)) for k, v in c.get("output_dirs", {}).items() if not k.startswith("_")})
    frag_re = re.compile(r"^(?:[A-Za-z0-9]{1,2}|[A-Za-z]\d+|film|raw|out|output|final|video|base|tmp|render)$", re.I)   # 碎片名：v / p2 / film / raw …
    def _add(p):
        e = os.path.splitext(p)[1].lower()
        if p in seen or not (e in vext or e in iext) or os.path.basename(p).startswith("."): return
        if e in vext and frag_re.match(Path(p).stem) and os.path.normpath(p) not in pub: return
        seen.add(p); (videos if e in vext else images).append(p)
    for pp in protect:
        if os.path.isfile(pp): _add(pp)
        if os.path.isfile(pp) and os.path.splitext(pp)[1].lower() in vext:
            for ip in glob.glob(glob.escape(os.path.splitext(pp)[0]) + "*"):
                if os.path.splitext(ip)[1].lower() in iext: _add(ip)
    for root in roots:
        for dp, dns, fns in os.walk(root):
            if "node_modules" in dns or "package.json" in fns: dns[:] = []; continue
            dns[:] = [d for d in dns if not d.startswith(".") and not any(e.search(os.path.join(dp, d) + "/") for e in excl)]
            for fn in fns:
                _add(os.path.join(dp, fn))
    def line_of(p):
        for r, l in rules:
            if r.search(p): return l
        return "other"
    # 封面：同目录同名图片，或文件名含 封面/cover 且与视频同前缀
    imgs_by_dir = {}
    for p in images: imgs_by_dir.setdefault(os.path.dirname(p), []).append(p)
    items, used_imgs = [], set()
    for p in videos:
        try: st = os.stat(p)
        except OSError: continue
        stem = Path(p).stem; cover = None
        for ip in imgs_by_dir.get(os.path.dirname(p), []):
            istem = Path(ip).stem
            if istem == stem or (istem.startswith(stem) and re.search("封面|cover", istem, re.I)):
                cover = ip; used_imgs.add(ip); break
        is_draft = bool(draft_re.search(p))
        items.append({"id": fid(p), "path": p, "name": Path(p).name, "dir": os.path.dirname(p).replace(str(HOME), "~"),
                      "kind": "draft" if is_draft else "final", "line": line_of(p), "size": st.st_size,
                      "mtime": st.st_mtime, "date": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d"),
                      "cover": cover, "auto_status": "published" if os.path.normpath(p) in pub else ("test" if test_re.search(Path(p).name + "/" + os.path.dirname(p)[-40:]) or is_draft else "review"),
                      "publish": pub.get(os.path.normpath(p))})
    for ip in images:
        if ip in used_imgs or not re.search("封面|cover", Path(ip).name, re.I): continue
        if draft_re.search(ip): continue
        try: st = os.stat(ip)
        except OSError: continue
        items.append({"id": fid(ip), "path": ip, "name": Path(ip).name, "dir": os.path.dirname(ip).replace(str(HOME), "~"),
                      "kind": "cover", "line": line_of(ip), "size": st.st_size, "mtime": st.st_mtime,
                      "date": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d"), "cover": ip,
                      "auto_status": "review", "publish": None})
    # 发布记录里的文件若已被移动到子目录：按“同名 + 原目录之下”回退匹配
    for rp, info in pub.items():
        if os.path.exists(rp): continue
        for it in items:
            if it["kind"] != "cover" and it["name"] == os.path.basename(rp) and it["path"].startswith(os.path.dirname(rp) + "/"):
                it["auto_status"] = "published"; it["publish"] = info
    srules = [(re.compile(r["match"], re.I), r["type"], r["style"]) for r in c.get("style_rules", {}).get("rules", [])]
    for it in items:
        it["auto_type"], it["auto_style"] = "", ""
        for rx, t, s in srules:
            if rx.search(it["path"]): it["auto_type"], it["auto_style"] = t, s; break
    items = [it for it in items if os.path.isfile(it["path"])]
    items.sort(key=lambda x: x["mtime"], reverse=True)
    with LOCK:
        INDEX["items"] = items; INDEX["by_id"] = {i["id"]: i for i in items}
        INDEX["scanned_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        INDEX["allowed"] = {i["path"] for i in items} | {i["cover"] for i in items if i["cover"]}
    try: hub_lib.autoattach(items)
    except Exception as e: print("autoattach", e)
    _CACHE.clear(); _MEMO.clear()
    threading.Thread(target=lambda: dedup_core.auto(sys.modules[__name__], "扫描后自动去重"), daemon=True).start()   # 硬规则：每个作品只显示最新一版
    threading.Thread(target=warm_thumbs, daemon=True).start()

PROBE_F = ROOT / "data/probe.json"
try: PROBE = json.loads(PROBE_F.read_text())
except Exception: PROBE = {}
def probe_all():
    changed = 0
    for it in list(INDEX["items"]):
        if it["kind"] == "cover": continue
        old = PROBE.get(it["path"])
        if old and old.get("mtime") == it["mtime"]: continue
        try:
            r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:stream_side_data=rotation:format=duration",
                                "-of", "json", it["path"]], capture_output=True, text=True, timeout=20, stdin=subprocess.DEVNULL)
            j = json.loads(r.stdout or "{}"); s = (j.get("streams") or [{}])[0]
            w, h = s.get("width"), s.get("height")
            rot = abs(int(float(((s.get("side_data_list") or [{}])[0]).get("rotation", 0) or 0)))
            if rot in (90, 270): w, h = h, w
            PROBE[it["path"]] = {"mtime": it["mtime"], "width": w, "height": h, "duration": round(float((j.get("format") or {}).get("duration") or 0), 2)}
            changed += 1
            if changed % 50 == 0: PROBE_F.write_text(json.dumps(PROBE))
        except Exception: pass
    if changed: PROBE_F.write_text(json.dumps(PROBE))

def warm_thumbs():
    probe_all()
    for it in list(INDEX["items"]):
        if it["kind"] != "cover" and not it["cover"]:
            try: thumb_path(it)
            except Exception: pass

def thumb_path(it):
    t = THUMBS / f'{it["id"]}.jpg'
    if t.exists() and t.stat().st_mtime >= it["mtime"]: return t
    src = it["cover"] or it["path"]
    try:
        if it["cover"] or it["kind"] == "cover":
            cmd = [FFMPEG, "-y", "-loglevel", "error", "-i", src, "-vf", "scale=480:-2", str(t)]
        else:
            cmd = [FFMPEG, "-y", "-loglevel", "error", "-ss", "1", "-i", src, "-frames:v", "1", "-vf", "scale=480:-2", str(t)]
        subprocess.run(cmd, timeout=60, stdin=subprocess.DEVNULL)
        if not t.exists() and it["kind"] != "cover":
            subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", src, "-frames:v", "1", "-vf", "scale=480:-2", str(t)], timeout=60, stdin=subprocess.DEVNULL)
    except Exception:
        pass
    return t

def style_names(t, s):
    try: doc = queue_lib.load_styles()
    except Exception: return "未识别", "未识别"
    tt = next((x for x in doc["types"] if x["id"] == t), None)
    if not tt: return "未识别", "未识别"
    p = next((x for x in tt["presets"] if x["id"] == s), None)
    return tt["name"], (p["name"] if p else "未识别")

SKIP_DIRS = {"out", "output", "renders", "build", "成片", "视频作品", "proj", "镜", "样片", "final", "deliver"}
def _alias(s, al):
    for k, v in sorted(((k, v) for k, v in al.items() if not k.startswith("_")), key=lambda x: -len(x[0])):
        s = re.sub(r"(?<![A-Za-z0-9])" + re.escape(k) + r"(?![A-Za-z])", v, s, flags=re.I)
    return s
def base_title(it):
    """不看发布记录的文件名标题（用于分组和兜底显示）。"""
    tr = cfg().get("title_rules", {}); p = Path(it["path"]); gen = re.compile(tr.get("generic", "^$"), re.I)
    def clean(s):
        s = re.sub(tr.get("strip_prefix", "^$"), "", s, flags=re.I)
        for _ in range(3): s = re.sub(tr.get("strip_suffix", "^$"), "", s, flags=re.I)
        return _alias(re.sub(r"_+", " ", s).strip(" -_"), tr.get("aliases", {}))
    t = clean(p.stem)
    if t and not gen.match(t): return t
    for par in list(p.parents)[:4]:
        if par.name.lower() in SKIP_DIRS: continue
        cc = clean(par.name)
        if cc and not gen.match(cc): return cc + (f" · {t}" if t and not gen.match(t) else "")
    return p.stem
def human_title(it):
    if it.get("publish") and it["publish"].get("title"): return it["publish"]["title"]
    return base_title(it)
def group_norm(it):
    vr = cfg().get("version_rules", {}); tok = vr.get("tokens", "")
    t = base_title(it).lower()
    t = re.sub(r"[·\-_|｜\s【】\[\]()（）]+", " ", t)
    words = [w for w in t.split() if not re.fullmatch(tok, w, re.I)] if tok else t.split()
    n = "".join(words) or t.replace(" ", "")
    n = re.sub(r"(?<=[^\d])v\d+$", "", n) or n     # 「雷军传记v3」与「雷军传记」同一作品
    return f'{it["line"]}|{n}'

def _with_meta(items):
    c = db(); m = {r["path"]: r for r in c.execute("select * from meta")}; c.close(); SM = hub_lib.sub_map(); FX = _frag_ctx()
    out = []
    for it in items:
        if not os.path.isfile(it["path"]): continue
        r = m.get(it["path"]); d = dict(it)
        d["status"] = (r["status"] if r and r["status"] else None) or it["auto_status"]
        if it["auto_status"] == "published" and not (r and r["status"]): d["status"] = "published"
        d["tags"] = json.loads(r["tags"]) if r else []
        d["note"] = r["note"] if r else ""
        d["rating"] = r["rating"] if r else None
        d["library"] = (r["library"] if r and r["library"] else None) or LIB_OF[d["rating"]]
        mt = r["video_type"] if r else None; ms = r["style_id"] if r else None
        d["video_type"] = mt if mt is not None else it.get("auto_type", "")
        d["style_id"] = ms if ms is not None else (it.get("auto_style", "") if mt is None else "")
        if it["path"] in SM and mt is None and SM[it["path"]][1]: d["video_type"], d["style_id"] = SM[it["path"]][1], SM[it["path"]][2]
        d["style_manual"] = mt is not None
        tn, sn = style_names(d["video_type"], d["style_id"])
        d["video_type_name"], d["style_name"] = tn, sn
        d["title"] = human_title(it)
        d["group_key"] = SM[it["path"]][0] if it["path"] in SM else group_norm(it)
        pr = PROBE.get(it["path"]) or {}
        d["duration"] = pr.get("duration"); d["width"] = pr.get("width"); d["height"] = pr.get("height")
        d["portrait"] = bool(pr.get("height") and pr.get("width") and pr["height"] > pr["width"])
        d["really_published"] = bool(it.get("publish")) or any(t.startswith("已发") for t in d["tags"])
        d["status_name"] = STATUS_NAMES[d["status"]]
        if d["kind"] == "final" and it["path"] not in SM and _is_fragment(d, FX): d["kind"] = "fragment"   # 碎片不进网站（原文件不动）
        out.append(d)
    return out

def _frag_ctx():
    """碎片判定上下文：config 规则 + 审计清单 data/fragments.json + 豁免集合（精选、风格小样）"""
    fr = cfg()["kind_rules"].get("fragment") or {}
    try: listed = set(json.loads((ROOT / "data" / "fragments.json").read_text(encoding="utf-8"))["paths"])
    except Exception: listed = set()
    c = db(); feat = {r[0] for r in c.execute("select group_key from works where featured=1")}; c.close()
    spaths = {ex(p.get(k)) for t in queue_lib.load_styles()["types"] for p in t["presets"] for k in ("thumbnail_source", "sample") if p.get(k)}
    return {"min": fr.get("min_duration", 8), "rx": re.compile(fr["name_regex"], re.I) if fr.get("name_regex") else None, "listed": listed, "feat": feat, "spaths": spaths}
def _is_fragment(d, X):
    if not X or d["really_published"] or d["group_key"] in X["feat"] or d["path"] in X["spaths"]: return False
    if d["path"] in X["listed"]: return True
    if d.get("duration") is not None and d["duration"] < X["min"]: return True
    if X["rx"] and (X["rx"].search(d["name"]) or X["rx"].search(os.path.basename(os.path.dirname(d["path"])))): return True
    return False

@app.on_event("startup")
def _start():
    THUMBS.mkdir(parents=True, exist_ok=True); UPLOADS.mkdir(exist_ok=True); DB.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(DB, timeout=30)
    try: con.execute("pragma journal_mode=WAL")
    finally: con.close()
    db().close()
    threading.Thread(target=scan, daemon=True).start()

def _versioned(name):
    """给 /static/xxx 引用自动加 ?v=<mtime>，HTML 本身 no-cache，避免浏览器用旧 CSS/JS"""
    html = (ROOT / "static" / name).read_text(encoding="utf-8")
    def rep(m):
        f = ROOT / "static" / m.group(2)
        v = int(f.stat().st_mtime) if f.exists() else 0
        return f'{m.group(1)}/static/{m.group(2)}?v={v}{m.group(3)}'
    html = re.sub(r'((?:href|src)=")/static/([^"?]+)(?:\?[^"]*)?(")', rep, html)
    return HTMLResponse(html, headers={"Cache-Control": "no-cache, must-revalidate"})

@app.get("/", response_class=HTMLResponse)
def index(): return _versioned("index.html")

@app.get("/api/config")
def api_config():
    c = cfg(); return {"lines": c["lines"], "type_lines": {k: v for k, v in c.get("type_lines", {}).items() if not k.startswith("_")}, "statuses": STATUS_NAMES, "scanned_at": INDEX["scanned_at"], "config_path": str(CFG_PATH)}

@app.post("/api/rescan")
def api_rescan(): scan(); return {"ok": True, "count": len(INDEX["items"]), "scanned_at": INDEX["scanned_at"]}

def visible_final(i):
    """统一计数口径：成片 + 不在废片库。"""
    return i["kind"] == "final" and i["library"] != "scrap"

def selected_map():
    c = db(); m = {r["key"]: r["selected_path"] for r in c.execute("select * from groups")}; c.close(); return m

def build_groups(items, sel=None):
    """按 group_key 合并版本。代表版本 = 已选定（若在集合内）否则最新。"""
    sel = selected_map() if sel is None else sel; g = {}
    for i in items: g.setdefault(i["group_key"], []).append(i)
    out = []
    for k, vs in g.items():
        vs.sort(key=lambda x: x["mtime"], reverse=True)
        rep = next((v for v in vs if v["path"] == sel.get(k)), vs[0])
        d = dict(rep); d["versions_count"] = len(vs); d["is_selected"] = sel.get(k) == rep["path"]
        d["online"] = any(v["really_published"] for v in vs); d["featured"] = any(v["rating"] == "love" for v in vs)
        d["pending"] = any(v["library"] == "publish" for v in vs) and not d["online"]
        pub = next((v for v in vs if v.get("publish")), None)
        d["group_title"] = pub["publish"]["title"] if pub else min((v["title"] for v in vs), key=len)
        d["version_ids"] = [v["id"] for v in vs]
        out.append(d)
    return out

_CACHE = {}
def cached(key, ttl, fn):
    v = _CACHE.get(key)
    if v and time.time() - v[0] < ttl: return v[1]
    if v and not _CACHE.get(key + "!"):   # 过期：先返回旧值，后台刷新
        _CACHE[key + "!"] = 1
        def bg():
            try: _CACHE[key] = (time.time(), fn())
            finally: _CACHE.pop(key + "!", None)
        threading.Thread(target=bg, daemon=True).start(); return v[1]
    r = fn(); _CACHE[key] = (time.time(), r); return r

@app.middleware("http")
async def _bust_cache(request, call_next):
    resp = await call_next(request)
    if request.method != "GET": _CACHE.clear(); _MEMO.clear()   # 任何写操作后失效
    return resp

def week_new():
    c = db(); t = int(time.time()) - 7 * 86400
    n = c.execute("select count(*) from works where archived=0 and first_seen>?", (t,)).fetchone()[0]; c.close(); return n

# ---- 性能：with_meta / work_cards 结果缓存；版本键 = 扫描时间 + 数据库/队列文件 mtime；写请求清空 ----
_MEMO = {}
def _ver():
    v = [INDEX["scanned_at"], id(INDEX["items"])]
    for f in (ROOT / "data" / "meta.db", ROOT / "data" / "meta.db-wal", ROOT / "queue" / "jobs.jsonl", ROOT / "queue" / "publish.jsonl"):
        try: v.append(f.stat().st_mtime_ns)
        except OSError: v.append(0)
    return tuple(v)
def _memo(name, items, fn):
    if items is not INDEX["items"] and items is not _MEMO.get("wm", (None, None))[1]: return fn(items)
    k = (name, _ver(), id(items)); hit = _MEMO.get(name)
    if hit and hit[0] == k: return hit[1]
    r = fn(items); _MEMO[name] = (k, r); return r
def with_meta(items):
    r = _memo("wm_r", items, _with_meta)
    if items is INDEX["items"]: _MEMO["wm"] = (None, r)
    return r
def work_cards(items): return _memo("wc", items, _work_cards)

@app.get("/api/stats")
def api_stats(): return cached("stats", 15, _api_stats)
def _api_stats():
    cards = [w for w in work_cards(with_meta(INDEX["items"])) if not w["archived"]]; s = {}
    for w in cards:
        x = s.setdefault(w["line"], {"final": 0, "versions": 0}); x["final"] += 1; x["versions"] += w["versions_count"]
    return {"lines": s, "top": _api_todo(), "scanned_at": INDEX["scanned_at"], "config_lines": len([l for l in cfg()["lines"] if l["id"] != "other"])}

def _old_stats():
    items = with_meta(INDEX["items"]); vf = [i for i in items if visible_final(i)]
    groups = build_groups(vf); s = {}
    for g in groups:
        x = s.setdefault(g["line"], {"final": 0, "versions": 0}); x["final"] += 1; x["versions"] += g["versions_count"]
    scrap_groups = build_groups([i for i in items if i["kind"] == "final" and i["library"] == "scrap"])
    libs = {"all": len(groups), "versions": len(vf), "featured": sum(g["featured"] for g in groups),
            "pending": sum(g["pending"] for g in groups), "scrap": len(scrap_groups)}
    top = {"works": len(groups), "versions": len(vf), "review": sum(1 for g in groups if g["status"] == "review" and not g["online"]),
           "online": sum(g["online"] for g in groups), "lines": len([l for l in cfg()["lines"] if l["id"] != "other"])}
    return {"lines": s, "libs": libs, "top": top, "scanned_at": INDEX["scanned_at"]}

@app.get("/api/videos")
def api_videos(line: str = "", status: str = "", kind: str = "final", q: str = "", tag: str = "",
               date_from: str = "", date_to: str = "", lib: str = "", style: str = "", aspect: str = "",
               sort: str = "new", group: int = 1, offset: int = 0, limit: int = 60):
    items = with_meta(INDEX["items"]); ql = q.lower().strip()
    def ok(i):
        if line and i["line"] != line: return False
        if kind and kind != "all" and i["kind"] != kind: return False
        if lib == "scrap":
            if i["library"] != "scrap": return False
        elif i["library"] == "scrap": return False
        if tag and tag not in i["tags"]: return False
        if date_from and i["date"] < date_from: return False
        if date_to and i["date"] > date_to: return False
        if style and i["style_id"] != (style if style != "none" else ""): return False
        if aspect == "portrait" and not i["portrait"]: return False
        if aspect == "landscape" and (i["portrait"] or not i["width"]): return False
        if ql and ql not in (i["title"] + " " + i["path"] + " " + " ".join(i["tags"]) + " " + i["note"]).lower(): return False
        return True
    r = [i for i in items if ok(i)]
    out = build_groups(r) if group and kind != "cover" else [dict(i, versions_count=1, online=i["really_published"], featured=i["rating"] == "love",
                                                                 pending=i["library"] == "publish" and not i["really_published"], group_title=i["title"], is_selected=False) for i in r]
    def st_ok(g):
        if lib == "featured" and not g["featured"]: return False
        if lib == "pending" and not g["pending"]: return False
        if status == "online": return g["online"]
        if status == "featured": return g["featured"]
        if status == "pending": return g["pending"]
        if status in ("test", "review") and (g["status"] != status or g["online"]): return False
        return True
    out = [g for g in out if st_ok(g)]
    if sort == "old": out.sort(key=lambda x: x["mtime"])
    elif sort == "duration": out.sort(key=lambda x: x.get("duration") or 0, reverse=True)
    else: out.sort(key=lambda x: x["mtime"], reverse=True)
    limit = max(1, min(limit, 2000))
    return {"total": len(out), "versions": len(r), "offset": offset, "limit": limit, "items": out[offset:offset + limit]}

STATES = {"making": "制作中", "failed": "失败", "confirm": "待确认", "ready": "待发布", "exported": "已导出", "published": "已发布"}
def wid_of(key): return hashlib.sha1(key.encode()).hexdigest()[:12]

def migrate_state(vs):
    """旧数据 → 新状态：真实发布记录=已发布；特别满意/发布库=待发布；其余(测试/待审/一般)=待确认；全部特别不满意=归档。"""
    if any(v["really_published"] for v in vs): st = "published"
    elif any(v["rating"] == "love" or v["library"] == "publish" for v in vs): st = "ready"
    else: st = "confirm"
    return st, int(any(v["rating"] == "love" for v in vs)), int(all(v["library"] == "scrap" for v in vs))

def ensure_works(finals):
    g = {}
    for i in finals: g.setdefault(i["group_key"], []).append(i)
    c = db(); have = {r["group_key"]: dict(r) for r in c.execute("select * from works")}
    sel = {r["key"]: r["selected_path"] for r in c.execute("select * from groups")}
    now = queue_lib.now(); n = 0
    for k, vs in g.items():
        if k in have: continue
        st, fe, ar = migrate_state(vs)
        c.execute("insert into works(id,group_key,title,description,topics,state,featured,archived,selected_path,created_at,updated_at) values(?,?,?,?,?,?,?,?,?,?,?)",
                  (wid_of(k), k, None, "", "[]", st, fe, ar, sel.get(k), now, now)); n += 1
        for v in vs:
            if v.get("cover"): c.execute("insert into assets(work_id,kind,path,label,created_at) values(?,?,?,?,?)", (wid_of(k), "cover", v["cover"], v["name"], now))
    c.commit()
    rows = {r["group_key"]: dict(r) for r in c.execute("select * from works")}; c.close()
    return rows

def _work_cards(items): return dedup_core.gate(_work_cards_raw(items))   # 最后关卡：同一选题只返回最新一条

def _work_cards_raw(items):
    finals = [i for i in items if i["kind"] == "final"]
    rows = ensure_works(finals); g = {}
    for i in finals: g.setdefault(i["group_key"], []).append(i)
    out = []
    for k, vs in g.items():
        w = rows.get(k) or {}; vs.sort(key=lambda x: (max([int(n) for n in re.findall(r"[vV](\d+)(?!\d)", x["name"])] or [0]), x["mtime"]), reverse=True)
        rep = next((v for v in vs if v["path"] == w.get("selected_path")), vs[0])
        online = any(v["really_published"] for v in vs)
        state = "published" if online else (w.get("state") or "confirm")
        if state == "published" and not online: state = "ready"          # 只有真实记录才算已发布
        pub = next((v for v in vs if v.get("publish")), None)
        if w.get("origin") == "bot" and w.get("state") in ("making", "failed"): state = w["state"]
        title = w.get("title") or (pub["publish"]["title"] if pub else min((v["title"] for v in vs), key=len))
        d = dict(rep); d.update(work_id=w.get("id") or wid_of(k), group_key=k, versions_count=len(vs), is_selected=bool(w.get("selected_path")) and w.get("selected_path") == rep["path"],
            state=state, state_name=STATES[state], featured=bool(w.get("featured")), archived=bool(w.get("archived")), work_title=title,
            description=w.get("description") or "", topics=json.loads(w.get("topics") or "[]"), version_ids=[v["id"] for v in vs])
        d["thumb_url"] = f"/workcover/{d['work_id']}?v={cover_ver(w)}" if w.get("cover_path") and w.get("origin") == "bot" else f"/thumb/{rep['id']}"
        d.update(responsible_bot=hub_lib.bot_registry.responsible(d.get("video_type"),d.get("line")), producer_bot=w.get("producer_bot") or "", stage=w.get("stage") or "", origin=w.get("origin") or "scan", check_errors=json.loads(w.get("check_errors") or "[]"), job_id=w.get("job_id"), error=w.get("error"))
        out.append(d)
    for k, w in rows.items():   # bot 作品还没有成片：占位卡（制作中）
        if k in g or w.get("origin") != "bot": continue
        out.append({"id": "", "work_id": w["id"], "group_key": k, "path": "", "title": w["title"] or "", "work_title": w["title"] or "未命名作品", "line": w.get("line") or "lab",
            "kind": "final", "mtime": time.mktime(time.strptime(w["created_at"][:19], "%Y-%m-%dT%H:%M:%S")), "date": w["created_at"][:10], "tags": [], "duration": None,
            "portrait": False, "width": None, "video_type": w.get("video_type") or "", "style_id": w.get("style_id") or "",
            "video_type_name": style_names(w.get("video_type") or "", w.get("style_id") or "")[0], "style_name": style_names(w.get("video_type") or "", w.get("style_id") or "")[1],
            "versions_count": 0, "version_ids": [], "is_selected": False, "state": w["state"], "state_name": STATES.get(w["state"], w["state"]),
            "featured": bool(w["featured"]), "archived": bool(w["archived"]), "description": w.get("description") or "", "topics": json.loads(w.get("topics") or "[]"),
            "thumb_url": f"/workcover/{w['id']}?v={cover_ver(w)}" if w.get("cover_path") else "", "stage": w.get("stage") or "", "origin": "bot",
            "producer_bot": w.get("producer_bot") or "", "check_errors": json.loads(w.get("check_errors") or "[]"), "job_id": w.get("job_id"), "error": w.get("error"), "really_published": False, "size": 0, "dir": ""})
    return out

def making_jobs(): return [j for j in queue_lib.load_jobs() if j["status"] in ("pending", "running")]

@app.get("/api/works")
def api_works(line: str = "", state: str = "", featured: int = 0, archived: int = 0, q: str = "", tag: str = "",
              date_from: str = "", date_to: str = "", style: str = "", aspect: str = "", sort: str = "new", offset: int = 0, limit: int = 60):
    items = with_meta(INDEX["items"]); ql = q.lower().strip()
    def vok(i):
        if tag and tag not in i["tags"]: return False
        if date_from and i["date"] < date_from: return False
        if date_to and i["date"] > date_to: return False
        if style and i["style_id"] != (style if style != "none" else ""): return False
        if aspect == "portrait" and not i["portrait"]: return False
        if aspect == "landscape" and (i["portrait"] or not i["width"]): return False
        return True
    cards = work_cards(items)
    def ok(w):
        if line and w["line"] != line: return False
        if bool(archived) != w["archived"]: return False
        if featured and not w["featured"]: return False
        if state and w["state"] not in state.split(","): return False
        if ql and ql not in (w["work_title"] + " " + w["title"] + " " + w["path"] + " " + " ".join(w["tags"])).lower(): return False
        return vok(w)
    out = [w for w in cards if ok(w)]
    if sort == "old": out.sort(key=lambda x: x["mtime"])
    elif sort == "duration": out.sort(key=lambda x: x.get("duration") or 0, reverse=True)
    else: out.sort(key=lambda x: x["mtime"], reverse=True)
    return {"total": len(out), "versions": sum(w["versions_count"] for w in out), "offset": offset, "items": out[offset:offset + max(1, min(limit, 2000))]}

@app.get("/api/work/{wid}")
def api_work(wid: str):
    items = with_meta(INDEX["items"]); card = next((w for w in work_cards(items) if w["work_id"] == wid), None)
    if not card: raise HTTPException(404, "作品不存在")
    vs = sorted([i for i in items if i["group_key"] == card["group_key"] and i["kind"] == "final"], key=lambda x: x["mtime"], reverse=True)
    if card.get("origin") == "bot":   # 版本标签（v1/v2/自动发现）来自 assets
        c0 = db(); lab = {r["path"]: r["label"] for r in c0.execute("select path,label from assets where work_id=? and kind='video'", (wid,))}; c0.close()
        for v in vs: v["version_label"] = lab.get(v["path"], "")
    c = db(); w = dict(c.execute("select * from works where id=?", (wid,)).fetchone()); assets = [dict(r) for r in c.execute("select * from assets where work_id=?", (wid,))]; c.close()
    for n, v in enumerate(vs): v["is_latest"] = n == 0; v["is_selected"] = v["path"] == w.get("selected_path")
    producers = {a["path"]:a["value"] for a in assets if a["kind"] == "producer" and a.get("path")}
    for v in vs: v["producer_bot"] = producers.get(v["path"]) or card.get("producer_bot") or ""
    return {"work": card, "versions": vs, "assets": assets}

@app.post("/api/work/{wid}")
def api_work_update(wid: str, body: dict):
    c = db(); w = c.execute("select * from works where id=?", (wid,)).fetchone()
    if not w: raise HTTPException(404, "作品不存在")
    sets = {}
    if "producer_bot" in body:
        c.close()
        try: hub_lib.set_producer(wid,body["producer_bot"])
        except hub_lib.HubError as e: raise HTTPException(400,e.msg)
        c = db()
    if "title" in body: sets["title"] = (body["title"] or "").strip() or None
    if "description" in body: sets["description"] = body["description"] or ""
    if "topics" in body: sets["topics"] = json.dumps([t.strip().lstrip("#") for t in body["topics"] if t.strip()], ensure_ascii=False)
    if "state" in body:
        if body["state"] not in ("confirm", "ready"): raise HTTPException(400, "这里只能在 待确认 / 待发布 之间切换；已导出/已发布由导出和真实发布结果决定")
        sets["state"] = body["state"]
    if "featured" in body: sets["featured"] = int(bool(body["featured"]))
    if "archived" in body: sets["archived"] = int(bool(body["archived"]))
    if "selected_version_id" in body:
        v = INDEX["by_id"].get(body["selected_version_id"] or "")
        sets["selected_path"] = v["path"] if v else None
    was_making = w["state"] == "making"
    if sets:
        sets["updated_at"] = queue_lib.now()
        c.execute("update works set " + ",".join(f"{k}=?" for k in sets) + " where id=?", (*sets.values(), wid)); c.commit()
    meta_touch = any(k in sets for k in ("title", "description", "topics"))
    c.close()
    if was_making and meta_touch and sets.get("state", "making") == "making":
        try: hub_lib.check(wid, save=True)
        except Exception: pass
    return api_work(wid)

def cover_ver(w):
    """封面版本参数：封面文件 mtime 整数；文件不存在用 updated_at（避免 /workcover 缓存显示旧图）"""
    p = (w or {}).get("cover_path") or ""
    try: return str(int(os.path.getmtime(p)))
    except Exception: return re.sub(r"\D", "", (w or {}).get("updated_at") or "") or "0"
def cover_ver_id(wid):
    con = db(); r = con.execute("select cover_path, updated_at from works where id=?", (wid,)).fetchone(); con.close()
    return cover_ver(dict(r) if r else {})

@app.get("/workcover/{wid}")
def workcover(wid: str):
    c = db(); r = c.execute("select cover_path from works where id=?", (wid,)).fetchone(); c.close()
    if not r or not r[0] or not os.path.isfile(r[0]): raise HTTPException(404)
    src = r[0]; t = THUMBS / f"wc_{wid}.jpg"  # jpg：brew ffmpeg 8.x 常无 webp 编码器
    if not t.exists() or t.stat().st_mtime < os.path.getmtime(src):
        try:
            subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", src, "-vf", "scale='min(480,iw)':-2", "-q:v", "4", str(t)], timeout=20, stdin=subprocess.DEVNULL, check=False)
        except Exception:
            pass
    return FileResponse(t if t.exists() else src, headers={"Cache-Control": "max-age=86400"})

@app.post("/api/work/{wid}/revise")
def api_revise(wid: str, body: dict):
    r = api_work(wid)
    version_id = body.get("version_id")
    current = next((v for v in r["versions"] if v["id"] == version_id),None) if version_id else next((v for v in r["versions"] if v.get("is_selected")),None)
    if version_id and not current: raise HTTPException(400,"当前版本不存在，请重新打开作品")
    try: j = hub_lib.revise(wid, body.get("text") or "", version_id, current["path"] if current else None)
    except hub_lib.HubError as e: raise HTTPException(400 if e.code in (2, 3, 5) else 404, e.msg)
    return j

@app.get("/api/work/{wid}/revision_status")
def api_revision_status(wid: str):
    return {"items":[{k:j.get(k) for k in ("id","status","target_bot","dispatch_state","claimed_by","received_at","stage","error","revise_text","source_version_id","created_at")} for j in queue_lib.load_jobs() if j.get("work_id")==wid and j.get("kind")=="revise" and not j.get("deleted")][:10]}

@app.get("/api/producers")
def api_producers():
    c=db()
    try:
        registry=hub_lib.bot_registry.load()
        registered=[b["name"] for b in registry["bots"]]
        known=[r[0] for r in c.execute("select distinct producer_bot from works where coalesce(producer_bot,'')!='' order by producer_bot") if r[0] not in registry.get("excluded_roles",[])]
        return {"items":list(dict.fromkeys(registered+known)),"bots":registry["bots"]}
    finally: c.close()

@app.post("/api/jobs/{jid}/retry")
def api_retry(jid: str):
    try: return hub_lib.retry(jid)
    except hub_lib.HubError as e: raise HTTPException(400 if e.code in (2, 3, 5) else 404, e.msg)

@app.get("/api/style_samples")
def api_style_samples():
    """每个风格挑一条真实成片当效果演示（优先已发布、竖屏、最近）。"""
    best = {}
    for i in with_meta(INDEX["items"]):
        if i["kind"] != "final" or not i["style_id"]: continue
        sc = (i["really_published"], i["mtime"])
        if i["style_id"] not in best or sc > best[i["style_id"]][0]: best[i["style_id"]] = (sc, i["id"])
    return {k: v[1] for k, v in best.items()}

@app.get("/api/todo")
def api_todo(): return cached("todo", 15, _api_todo)
def _api_todo():
    cards = [w for w in work_cards(with_meta(INDEX["items"])) if not w["archived"]]
    linked = {c["job_id"] for c in cards if c.get("job_id")}
    return {"failed": sum(w["state"] == "failed" for w in cards), "exported": sum(w["state"] == "exported" for w in cards),
            "making": sum(w["state"] == "making" for w in cards) + sum(1 for j in making_jobs() if j["id"] not in linked and not j.get("work_id")), "confirm": sum(w["state"] == "confirm" for w in cards), "ready": sum(w["state"] == "ready" for w in cards),
            "published": sum(w["state"] == "published" for w in cards), "works": len(cards), "versions": sum(w["versions_count"] for w in cards),
            "featured": sum(w["featured"] for w in cards), "week_new": week_new(),
            "today_pub": sum(publish_lib.today_count(p) for p in publish_lib.PLATFORM_NAMES), "archived": len(work_cards(with_meta(INDEX["items"]))) - len(cards)}

@app.get("/api/group")
def api_group(key: str):
    items = [i for i in with_meta(INDEX["items"]) if i["group_key"] == key and i["kind"] != "cover"]
    items.sort(key=lambda x: x["mtime"], reverse=True); sel = selected_map().get(key)
    for n, i in enumerate(items): i["is_latest"] = n == 0; i["is_selected"] = i["path"] == sel
    return {"key": key, "selected": sel, "items": items}

@app.post("/api/group/select")
def api_group_select(body: dict):
    it = INDEX["by_id"].get(body.get("video_id", ""))
    key = body.get("key", "")
    c = db()
    if body.get("clear"): c.execute("delete from groups where key=?", (key,))
    else:
        if not it: raise HTTPException(404, "版本不存在")
        c.execute("insert or replace into groups(key,selected_path,updated_at) values(?,?,?)", (key, it["path"], queue_lib.now()))
    c.commit(); c.close(); return {"ok": True}

@app.get("/api/tags")
def api_tags():
    c = db(); t = {}
    for r in c.execute("select tags from meta"):
        for x in json.loads(r["tags"] or "[]"): t[x] = t.get(x, 0) + 1
    c.close(); return t

@app.post("/api/videos/{vid}")
def api_update(vid: str, body: dict):
    it = INDEX["by_id"].get(vid)
    if not it: raise HTTPException(404, "不存在")
    c = db(); r = c.execute("select * from meta where path=?", (it["path"],)).fetchone()
    status = body.get("status", r["status"] if r else None)
    if status and status not in STATUS_NAMES: raise HTTPException(400, "状态无效")
    tags = body.get("tags", json.loads(r["tags"]) if r else [])
    tags = sorted({t.strip() for t in tags if t and t.strip()})
    note = body.get("note", r["note"] if r else "")
    rating = body["rating"] if "rating" in body else (r["rating"] if r else None)
    vt = body["video_type"] if "video_type" in body else (r["video_type"] if r else None)
    sid = body["style_id"] if "style_id" in body else (r["style_id"] if r else None)
    if rating not in LIB_OF: raise HTTPException(400, "评价无效")
    library = LIB_OF[rating]
    c.execute("insert or replace into meta(path,status,tags,note,updated_at,rating,library,video_type,style_id) values(?,?,?,?,?,?,?,?,?)",
              (it["path"], status, json.dumps(tags, ensure_ascii=False), note, queue_lib.now(), rating, library, vt, sid))
    c.commit(); c.close(); return with_meta([it])[0]

def _allowed(p):
    if p in INDEX.get("allowed", set()): return True
    p2 = os.path.realpath(p)
    if p2.startswith(str(UPLOADS)): return True
    for j in queue_lib.load_jobs():
        if p in j.get("result_paths", []) or p in j.get("ref_images", []) or p in j.get("style_ref_images", []) \
           or p in j.get("ref_videos", []) or p in j.get("style_ref_videos", []): return True
    return False

@app.get("/media/{vid}")
def media(vid: str):
    it = INDEX["by_id"].get(vid)
    if not it: raise HTTPException(404)
    return FileResponse(it["path"])

@app.get("/thumb/{vid}")
def thumb(vid: str):
    it = INDEX["by_id"].get(vid)
    if not it: raise HTTPException(404)
    t = thumb_path(it)
    if not t.exists(): raise HTTPException(404)
    return FileResponse(t, headers={"Cache-Control": "max-age=86400"})

@app.get("/file")
def file(path: str):
    if not _allowed(path) or not os.path.isfile(path): raise HTTPException(403, "不允许访问")
    return FileResponse(path)

# ---------- 生成队列 ----------
@app.get("/api/jobs")
def api_jobs():
    c = db(); ws = {r["id"]: dict(r) for r in c.execute("select id,state,stage,error,check_errors,title from works where origin='bot'")}; c.close()
    items = [j for j in queue_lib.load_jobs() if not j.get("deleted") and not j.get("results_deleted")]
    for j in items:
        j["result_paths"] = [p for p in j.get("result_paths", []) if os.path.isfile(p)]
        w = ws.get(j.get("work_id") or "")
        if w: j["work"] = {**w, "check_errors": json.loads(w.get("check_errors") or "[]"), "state_name": STATES.get(w["state"], w["state"])}
    return {"items": items}

VIDEO_EXT = {".mp4", ".mov", ".webm", ".m4v"}; MAX_VIDEO = 800 << 20

@app.post("/api/jobs")
async def api_add_job(prompt: str = Form(...), line: str = Form(...), output_dir: str = Form(""),
                      video_type: str = Form(""), style_id: str = Form(""), style_custom_text: str = Form(""),
                      refs: list[UploadFile] = File(default=[]), style_refs: list[UploadFile] = File(default=[]),
                      ref_videos: list[UploadFile] = File(default=[]), style_ref_videos: list[UploadFile] = File(default=[]),
                      ref_video_urls: str = Form(""), ref_library_ids: str = Form(""), aspect: str = Form(""), voice: str = Form(""),
                      style_ref_paths: str = Form("")):
    if not prompt.strip(): raise HTTPException(400, "提示词不能为空")
    if not output_dir.strip(): output_dir = cfg().get("output_dirs", {}).get(video_type) or cfg().get("output_dirs", {}).get(line) or ""
    if not output_dir: raise HTTPException(400, "请填写保存位置")
    out = os.path.abspath(ex(output_dir.strip()))
    p = None
    if style_id:
        t, p, _ = queue_lib.find_style(video_type, style_id)
        if not p: raise HTTPException(400, "风格不存在")
        if p.get("mine"): style_custom_text = style_custom_text or p.get("description") or p["name"]
        if style_id == "custom" and not style_custom_text.strip() and not style_ref_paths.strip() and not any(f.filename for f in style_ref_videos):
            raise HTTPException(400, "自定义风格需要风格描述或至少一条参考视频")
    paths = []
    d = UPLOADS / datetime.now().strftime("%Y%m%d"); d.mkdir(parents=True, exist_ok=True)
    for f in refs:
        if not f.filename: continue
        name = f'{datetime.now().strftime("%H%M%S")}-{hashlib.sha1(os.urandom(8)).hexdigest()[:6]}-{Path(f.filename).name}'
        (d / name).write_bytes(await f.read()); paths.append(str(d / name))
    spaths = []
    if style_id == "custom":
        for f in style_refs:
            if not f.filename: continue
            name = f'{datetime.now().strftime("%H%M%S")}-style-{hashlib.sha1(os.urandom(8)).hexdigest()[:6]}-{Path(f.filename).name}'
            (d / name).write_bytes(await f.read()); spaths.append(str(d / name))
    async def save_video(f, tag):
        ext = Path(f.filename).suffix.lower()
        if ext not in VIDEO_EXT: raise HTTPException(400, f"参考视频只支持 mp4 / mov / webm：{f.filename}")
        name = f'{datetime.now().strftime("%H%M%S")}-{tag}-{hashlib.sha1(os.urandom(8)).hexdigest()[:6]}-{Path(f.filename).name}'
        dst = d / name; size = 0
        with open(dst, "wb") as o:
            while chunk := await f.read(4 << 20):
                size += len(chunk)
                if size > MAX_VIDEO: o.close(); dst.unlink(missing_ok=True); raise HTTPException(400, "参考视频太大了（上限 800MB）")
                o.write(chunk)
        return str(dst)
    rv = [await save_video(f, "refv") for f in ref_videos if f.filename]
    for vid in [x for x in re.split(r"[,\s]+", ref_library_ids) if x]:
        it = INDEX["by_id"].get(vid)
        if it and it["kind"] != "cover": rv.append(it["path"])
    urls = [u.strip() for u in re.split(r"[\n\s]+", ref_video_urls) if u.strip()]
    bad = [u for u in urls if not re.match(r"^https?://", u)]
    if bad: raise HTTPException(400, "视频链接要以 http:// 或 https:// 开头")
    srv = [await save_video(f, "stylev") for f in style_ref_videos if f.filename] if style_id == "custom" else []
    if style_id == "custom":   # 链接解析出来的参考视频（已在 uploads/refs）
        srv += [x for x in style_ref_paths.split("\n") if x.strip() and _ref_ok(x.strip()) and os.path.isfile(x.strip())]
    if style_id and p and p.get("mine"): srv = [x for x in p.get("ref_videos", []) if os.path.isfile(x)]   # 我的风格：带上它的参考视频
    return queue_lib.add_job(prompt.strip(), paths, out, line, video_type, style_id,
                             style_custom_text.strip() if style_id == "custom" or (p and p.get("mine")) else "", spaths,
                             ref_videos=rv, ref_video_urls=urls, style_ref_videos=srv, aspect=aspect, voice=voice)

@app.get("/api/styles")
def api_styles(): return queue_lib.load_styles()

MYSTY = ROOT / "data" / "my_styles"
def _ref_ok(pth):
    a = os.path.abspath(pth); return a.startswith(str(UPLOADS) + os.sep) or a.startswith(str(MYSTY) + os.sep)
def _probe(pth):
    try:
        o = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height:format=duration", "-of", "json", pth], capture_output=True, text=True, timeout=15)
        j = json.loads(o.stdout); st = next((x for x in j.get("streams", []) if x.get("width")), {})
        return {"duration": float(j.get("format", {}).get("duration") or 0), "portrait": (st.get("height") or 0) > (st.get("width") or 0)}
    except Exception: return {"duration": 0, "portrait": False}

@app.post("/api/my_styles")
async def api_add_my_style(name: str = Form(...), video_type: str = Form(...), description: str = Form(""),
                           style_ref_videos: list[UploadFile] = File(default=[]), style_ref_paths: str = Form("")):
    """把自定义风格存成可复用的「我的风格」：名字 + 参考视频（上传或链接解析结果）"""
    if not name.strip(): raise HTTPException(400, "请给风格起个名字")
    if not any(t["id"] == video_type for t in queue_lib.load_styles()["types"]): raise HTTPException(400, "视频类型不存在")
    sid = "my-" + hashlib.sha1(os.urandom(8)).hexdigest()[:8]; d = MYSTY / sid; d.mkdir(parents=True, exist_ok=True); vids = []
    for f in style_ref_videos:
        if not f.filename: continue
        if Path(f.filename).suffix.lower() not in VIDEO_EXT: raise HTTPException(400, f"参考视频只支持 mp4 / mov / webm：{f.filename}")
        dst = d / Path(f.filename).name
        with open(dst, "wb") as o:
            while chunk := await f.read(4 << 20): o.write(chunk)
        vids.append(str(dst))
    for x in [x.strip() for x in style_ref_paths.split("\n") if x.strip()]:
        if _ref_ok(x) and os.path.isfile(x):
            dst = d / Path(x).name; shutil.copy2(x, dst); vids.append(str(dst))
    if not vids and not description.strip(): shutil.rmtree(d, ignore_errors=True); raise HTTPException(400, "请填写风格描述或添加参考视频")
    th = ROOT / "cache" / "styles" / f"{sid}.jpg"; th.parent.mkdir(parents=True, exist_ok=True)
    if vids: subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", "1", "-i", vids[0], "-frames:v", "1", "-vf", "scale=480:-2", str(th)], timeout=30)
    doc = queue_lib.load_my_styles()
    st = {"id": sid, "video_type": video_type, "name": name.strip(), "description": description.strip() or "我的风格 · 照参考视频做",
          "ref_videos": vids, "thumbnail": str(th.relative_to(ROOT)) if th.exists() else "", "created_at": datetime.now().isoformat(timespec="seconds")}
    doc["styles"].append(st); queue_lib.save_my_styles(doc); _CACHE.clear(); return st

ETA = {"script-with-spec": "约 10–20 分钟", "custom-ref": "约 20–40 分钟（按参考视频仿制）"}
@app.get("/api/style_info")
def api_style_info():
    """风格小样弹窗数据：每个风格的类型、特点、适合选题、默认画幅/时长、预计耗时、小样地址"""
    def build():
        samples = api_style_samples(); out = {}; WM = {i["id"]: i for i in with_meta(INDEX["items"])}
        for t in queue_lib.load_styles()["types"]:
            for p in t["presets"]:
                if p["id"] == "custom": continue
                smp = None
                if p.get("mine") and p.get("ref_videos"):
                    v = p["ref_videos"][0]; smp = dict(_probe(v), url=f"/stylesample/{p['id']}")
                elif p.get("sample") and os.path.isfile(ex(p["sample"])): smp = dict(_probe(ex(p["sample"])), url=f"/stylesample/{p['id']}")   # styles.json 显式指定的小样优先于自动挑的成片
                elif samples.get(p["id"]) and WM.get(samples[p["id"]]):
                    it = WM[samples[p["id"]]]
                    if not it.get("duration"): it = dict(it, **_probe(it["path"]))
                    smp = {"url": f"/media/{it['id']}", "duration": it.get("duration") or 0, "portrait": bool(it.get("portrait"))}
                elif p.get("sample") and os.path.isfile(ex(p["sample"])): smp = dict(_probe(ex(p["sample"])), url=f"/stylesample/{p['id']}")
                out[p["id"]] = {"id": p["id"], "name": p["name"], "type": t["id"], "type_name": t["name"], "features": p.get("description", ""),
                    "topics": p.get("topics") or t.get("description", ""), "aspect": p.get("aspect") or (("9:16 竖屏" if smp["portrait"] else "16:9 横屏") if smp else "—"),
                    "duration": p.get("duration") or (f"约 {round(smp['duration'])} 秒" if smp and smp.get("duration") else "—"),
                    "eta": p.get("eta") or ETA.get(p.get("automation"), "约 15–30 分钟"), "mine": bool(p.get("mine")),
                    "thumb": f"/stylethumb/{p['id']}", "sample": smp,
                    "cover": f"/stylecover/{p['id']}" if p.get("cover_sample") and os.path.isfile(ex(p["cover_sample"])) else ""}
        return out
    return cached("style_info", 30, build)

@app.get("/stylesample/{sid}")
def style_sample(sid: str):
    for t in queue_lib.load_styles()["types"]:
        for p in t["presets"]:
            if p["id"] != sid: continue
            v = (p.get("ref_videos") or [None])[0] or (ex(p["sample"]) if p.get("sample") else None)
            if v and os.path.isfile(v): return FileResponse(v)
    raise HTTPException(404)

@app.get("/stylecover/{sid}")
def style_cover(sid: str):
    for t in queue_lib.load_styles()["types"]:
        for p in t["presets"]:
            if p["id"] == sid and p.get("cover_sample") and os.path.isfile(ex(p["cover_sample"])):
                return FileResponse(ex(p["cover_sample"]), headers={"Cache-Control": "no-cache"})
    raise HTTPException(404)

@app.get("/stylethumb/{sid}")
def style_thumb(sid: str):
    for t in queue_lib.load_styles()["types"]:
        for p in t["presets"]:
            if p["id"] == sid and p.get("thumbnail") and (ROOT / p["thumbnail"]).exists():
                return FileResponse(ROOT / p["thumbnail"], headers={"Cache-Control": "no-cache"})
    raise HTTPException(404)

@app.get("/api/output_dirs")
def api_output_dirs():
    seen = {}
    for it in INDEX["items"]:
        if it["kind"] == "final":
            dd = os.path.dirname(it["path"]); seen.setdefault(it["line"], {}); seen[it["line"]][dd] = seen[it["line"]].get(dd, 0) + 1
    out = {k: [x for x, _ in sorted(v.items(), key=lambda y: -y[1])][:8] for k, v in seen.items()}
    by_type = {k: os.path.expanduser(v) for k, v in cfg().get("output_dirs", {}).items() if not k.startswith("_")}
    return {"by_line": out, "by_type": by_type}

# ---------- 发布 ----------
import publish_lib

@app.get("/api/platforms")
def api_platforms(): return publish_lib.platforms()

@app.get("/api/publish/prefill/{vid}")
def api_prefill(vid: str):
    it = INDEX["by_id"].get(vid)
    if not it or it["kind"] == "cover": raise HTTPException(404)
    m = with_meta([it])[0]; c = cfg(); pd = c.get("publish_defaults", {}); dft = pd.get(m["video_type"]) or pd.get(it["line"]) or {"topics": [], "desc_tail": "内容含AI生成"}
    stem = Path(it["path"]).stem
    base = re.sub(r"^(vibe|文学哲学|来龙去脉|ainews)[-_]", "", stem); base = re.sub(r"[-_](样片|v\d+|封面版|抖音版|YouTube版)$", "", base)
    title = (it["publish"] or {}).get("title") or base
    v, h = publish_lib.make_covers(vid, it["path"])
    short = re.sub(r"[，。！？；：、“”《》（）,|｜\-_]", " ", base).strip()[:16]
    wk = next((w for w in work_cards(with_meta(INDEX["items"])) if vid in w["version_ids"]), None)
    if wk and wk["work_title"]: title = wk["work_title"]
    if wk and wk["topics"]: dft = dict(dft, topics=wk["topics"])
    if wk:
        con = db(); row = con.execute("select cover_path from works where id=?", (wk["work_id"],)).fetchone(); con.close()
        if row and row["cover_path"] and os.path.isfile(row["cover_path"]): v = row["cover_path"]
    return {"video_id": vid, "video_path": it["path"], "library": m["library"], "title": title[:30], "short_title": re.sub(r"[^\w\s\u4e00-\u9fff]", " ", title).strip()[:16],
            "desc": (wk.get("description") if wk else "") or f"{base}\n{dft.get('desc_tail','')}".strip(), "topics": dft.get("topics", []),
            "account": publish_lib.auto_account(it["line"], title, (wk.get("description") if wk else "") or base, dft.get("topics", [])),
            "accounts": [dict(x, desc=publish_lib.CHANNEL_ACCOUNTS[x["account"]]["desc"]) for x in publish_lib.platforms()[1].get("accounts", [])],
            "cover": v, "cover_h": h, "cover_url": f"/workcover/{wk['work_id']}?v={cover_ver_id(wk['work_id'])}" if wk and wk.get("origin") == "bot" else f"/cover/{vid}?r=3x4", "ai_declare": True, "platforms": publish_lib.platforms()}

@app.get("/cover/{vid}")
def cover_img(vid: str, r: str = "3x4"):
    f = publish_lib.COVERS / f"{vid}-{'4x3' if r == '4x3' else '3x4'}.jpg"
    if not f.exists(): raise HTTPException(404)
    return FileResponse(f, headers={"Cache-Control": "no-cache"})

@app.get("/api/publish")
def api_pub_list():
    items = publish_lib.load()
    for j in items: j["dry_running"] = DRY.get(j["id"]) == "running"; j["dry_shot"] = (publish_lib.LOGS / f"{j['id']}.png").exists()
    return {"items": items}

@app.post("/api/publish")
def api_pub_add(body: dict):
    clean = dict(body); clean.pop("_website_approved", None)
    return _create_publish_jobs(clean)

def _create_publish_jobs(body: dict):
    it = INDEX["by_id"].get(body.get("video_id", ""))
    if not it: raise HTTPException(404, "视频不存在")
    m = with_meta([it])[0]
    wk = next((w for w in work_cards(with_meta(INDEX["items"])) if it["id"] in w["version_ids"]), None)
    if not (wk and wk["state"] in ("ready", "exported", "published")) and not body.get("force"): raise HTTPException(400, "只发布「待发布」的作品：先在作品里点「确认成片」")
    plats = [p for p in body.get("platforms", []) if p in publish_lib.PLATFORM_NAMES]
    if not plats: raise HTTPException(400, "至少选一个平台")
    ok = {p["id"]: p for p in publish_lib.platforms()}
    out = []
    for p in plats:
        if body.get("_website_approved") and publish_lib.today_count(p) >= publish_lib.DAILY_LIMIT[p]: raise HTTPException(400, f"{ok[p]['name']}今日发布数量已达上限")
        if not ok[p]["ok"]: raise HTTPException(400, f"{ok[p]['name']} 暂不可用：{ok[p]['reason']}")
        j = {"video_id": it["id"], "video_path": it["path"], "platform": p, "title": body.get("title", "").strip(),
             "short_title": body.get("short_title", "").strip(), "desc": body.get("desc", "").strip(),
             "topics": [t.strip().lstrip("#") for t in body.get("topics", []) if t.strip()],
             "cover": body.get("cover") or "", "cover_h": body.get("cover_h") or "",
             "ai_declare": bool(body.get("ai_declare")) if p == "douyin" else False, "work_id": wk["work_id"] if wk else ""}
        if p == "channels":
            j["account"] = (body.get("account") or "").strip() or publish_lib.auto_account(it["line"], j["title"], j["short_title"], j["desc"], j["topics"])
            st = publish_lib.channel_account_status(j["account"]) if j["account"] in publish_lib.CHANNEL_ACCOUNTS else None
            if st and not st["ok"]: raise HTTPException(400, f"视频号「{j['account']}」暂不可用：{st['reason']}")
        e = publish_lib.validate(j)
        if e: raise HTTPException(400, f"{publish_lib.PLATFORM_NAMES[p]}：" + "；".join(e))
        out.append(j)
    try: return {"items": publish_lib.enqueue_batch(out, approved=body.get("_website_approved") is True)}
    except ValueError as e: raise HTTPException(409, str(e))

@app.post("/api/publish/start")
def api_publish_start(body: dict, request: Request):
    # A visible, explicit confirmation in the website is the approval for these jobs.
    from urllib.parse import urlsplit
    origin = request.headers.get("origin")
    if origin and urlsplit(origin).netloc != request.headers.get("host"):
        raise HTTPException(403, "请在本站确认发布")
    if body.get("approved") is not True:
        raise HTTPException(400, "请先确认视频、文案和发布平台")
    it = INDEX["by_id"].get(body.get("video_id", ""))
    wk = next((w for w in work_cards(with_meta(INDEX["items"])) if it and it["id"] in w["version_ids"]), None)
    if not wk or wk.get("archived") or wk["state"] in ("making", "failed"):
        raise HTTPException(400, "此作品尚无可发布的完整成片，或已归档")
    # Validate and queue the whole selected platform set before starting either upload.
    r = _create_publish_jobs(dict(body, force=True, _website_approved=True))
    if wk["state"] == "confirm":
        api_review(wk["work_id"], {"action": "ok", "version_id": it["id"], "checks": ["网站确认发布"]})
    import publish_runner
    publish_runner.start([j["id"] for j in r["items"]])
    return r

@app.post("/api/publish/{pid}/run")
def api_publish_run(pid: str, body: dict, request: Request):
    from urllib.parse import urlsplit
    origin = request.headers.get("origin")
    if origin and urlsplit(origin).netloc != request.headers.get("host"):
        raise HTTPException(403, "请在本站确认发布")
    if body.get("approved") is not True: raise HTTPException(400, "请先确认发布")
    j = publish_lib.get(pid)
    if not j: raise HTTPException(404, "发布任务不存在")
    if j["status"] == "done": return j
    if j["status"] == "running": return j
    if j.get("needs_verification"): raise HTTPException(409, "上次结果未确认，请先在平台检查是否已发布，避免重复")
    errors = publish_lib.validate(j)
    if errors: raise HTTPException(400, "；".join(errors))
    available = next(p for p in publish_lib.platforms() if p["id"] == j["platform"])
    if j["platform"] == "channels": available = publish_lib.channel_account_status(publish_lib.job_account(j))
    if not available["ok"]: raise HTTPException(400, available["reason"])
    if publish_lib.today_count(j["platform"]) >= publish_lib.DAILY_LIMIT[j["platform"]]:
        raise HTTPException(400, "今日发布数量已达上限")
    j = publish_lib.update(pid, status="pending", error="", approved_at=publish_lib.now(), approved_by="website-user")
    import publish_runner
    publish_runner.start([pid])
    return j

# ---------- Phase 3：审核 / 导出 / 演练 ----------
@app.post("/api/work/{wid}/review")
def api_review(wid: str, body: dict):
    """确认成片(ok) 或 退回(back，需写原因)。退回会生成一条修改任务给 Grokbot。"""
    act = body.get("action"); reason = (body.get("reason") or "").strip(); vid = body.get("version_id")
    c = db(); w = c.execute("select * from works where id=?", (wid,)).fetchone()
    if not w: raise HTTPException(404, "作品不存在")
    t = queue_lib.now(); v = INDEX["by_id"].get(vid or "")
    if act == "ok":
        sets = "state='ready', updated_at=?" + (", selected_path=?" if v else ""); args = [t] + ([v["path"]] if v else []) + [wid]
        c.execute(f"update works set {sets} where id=?", args)
        c.execute("insert into assets(work_id,kind,value,label,created_at) values(?,?,?,?,?)", (wid, "review", json.dumps({"action": "ok", "version": v["path"] if v else None, "checks": body.get("checks", [])}, ensure_ascii=False), "确认成片", t))
        c.commit(); c.close(); return {"ok": True, "state": "ready"}
    if act == "back":
        if not reason: raise HTTPException(400, "退回请写一句原因，Grokbot 会照着改")
        c.execute("insert into assets(work_id,kind,value,label,created_at) values(?,?,?,?,?)", (wid, "review", json.dumps({"action": "back", "reason": reason}, ensure_ascii=False), "退回", t))
        c.execute("update works set state='confirm', stage=?, updated_at=? where id=?", ("已退回：" + reason, t, wid)); c.commit(); c.close()
        j = hub_lib.revise(wid, reason)
        return {"ok": True, "state": "confirm", "job_id": j["id"]}
    raise HTTPException(400, "action 只能是 ok 或 back")

@app.post("/api/work/{wid}/export")
def api_export(wid: str, body: dict):
    """导出给不能直发的平台：记录导出（平台+内容），作品 待发布 → 已导出。不会标已发布。"""
    c = db(); w = c.execute("select * from works where id=?", (wid,)).fetchone()
    if not w: raise HTTPException(404, "作品不存在")
    t = queue_lib.now(); plat = body.get("platform") or "manual"
    c.execute("insert into assets(work_id,kind,value,label,created_at) values(?,?,?,?,?)", (wid, "export", json.dumps({"platform": plat, "what": body.get("what", []), "pub_id": body.get("pub_id")}, ensure_ascii=False), "导出", t))
    if w["state"] in ("ready", "exported"): c.execute("update works set state='exported', updated_at=? where id=?", (t, wid))
    c.commit(); c.close()
    if body.get("pub_id") and publish_lib.get(body["pub_id"]): publish_lib.update(body["pub_id"], exported=True, exported_at=t)
    return {"ok": True, "state": "exported" if w["state"] != "published" else "published"}

@app.get("/api/work/{wid}/history")
def api_history(wid: str):
    c = db(); rows = [dict(r) for r in c.execute("select kind,value,label,created_at from assets where work_id=? and kind in ('review','export','publish') order by id desc", (wid,))]; c.close()
    for r in rows:
        try: r["value"] = json.loads(r["value"] or "{}")
        except Exception: pass
    pubs = [j for j in publish_lib.load() if j.get("work_id") == wid]
    return {"events": rows, "publish_jobs": pubs}

@app.get("/download/{vid}")
def download(vid: str):
    it = INDEX["by_id"].get(vid)
    if not it: raise HTTPException(404)
    return FileResponse(it["path"], filename=it["name"])

@app.get("/api/publish/{pid}/cover")
def pub_cover(pid: str, h: int = 0):
    j = publish_lib.get(pid); p = (j or {}).get("cover_h" if h else "cover")
    if not p or not os.path.isfile(p): raise HTTPException(404)
    return FileResponse(p, filename=f"{pid}-{'横' if h else '竖'}封面{Path(p).suffix}")

DRY = {}
@app.post("/api/publish/{pid}/dryrun")
def pub_dryrun(pid: str):
    """只演练：抖音=填表截图；视频号=--check-only；小红书=校验+查登录（不 publish、不弹码）。永不带 --publish / --approved。"""
    j = publish_lib.get(pid)
    if not j: raise HTTPException(404)
    if DRY.get(pid) == "running": return {"running": True}
    def run():
        DRY[pid] = "running"
        try: subprocess.run([str(ROOT / ".venv/bin/python"), str(ROOT / "pub.py"), "dryrun", pid], cwd=ROOT, capture_output=True, timeout=1800)
        finally: DRY[pid] = "done"
    threading.Thread(target=run, daemon=True).start(); return {"running": True}

@app.get("/api/publish/{pid}/dryshot")
def pub_dryshot(pid: str):
    p = publish_lib.LOGS / f"{pid}.png"
    if not p.exists(): raise HTTPException(404)
    return FileResponse(p)

@app.post("/api/publish/{pid}/retry")
def pub_retry(pid: str):
    j = publish_lib.get(pid)
    if not j or j["status"] != "failed": raise HTTPException(400, "只有失败的发布任务能重试")
    if j.get("needs_verification"): raise HTTPException(409, "请先在平台核对上次发布结果，避免重复发布")
    return publish_lib.update(pid, status="pending", error="", retry_count=j.get("retry_count", 0) + 1)

@app.get("/api/publish_status")
def pub_status():
    return {"platforms": publish_lib.platforms(), "today": {p: publish_lib.today_count(p) for p in publish_lib.PLATFORM_NAMES}, "limit": publish_lib.DAILY_LIMIT,
            "dry": DRY}

@app.post("/api/rerender")
def api_rerender(body: dict):
    it = INDEX["by_id"].get(body.get("video_id", ""))
    if not it: raise HTTPException(404, "视频不存在")
    m = with_meta([it])[0]; vt = body.get("video_type") or m["video_type"]; sid = body.get("style_id", "")
    t, p, _ = queue_lib.find_style(vt, sid)
    if not p or p.get("custom"): raise HTTPException(400, "请选一个该类型下的风格预设")
    topic = (body.get("prompt") or "").strip() or ((it["publish"] or {}).get("title") or "") or (m["note"] or "")
    if not topic: raise HTTPException(400, "这条片没有原提示词/标题，请补一句主题")
    prompt = f"【换风格重出】主题：{topic}\n原片：{it['path']}\n原风格：{m['style_name']} → 新风格：{p['name']}"
    return queue_lib.add_job(prompt, [], os.path.dirname(it["path"]), it["line"], vt, sid, "", [], ref_videos=[it["path"]], ref_video_urls=[],
                             source_video=it["path"], source_style_id=m["style_id"], topic=topic)

# ---------- 手动删除（移到废纸篓） ----------
def _del_scope(wid, vid=""):
    r = api_work(wid); w, vs = r["work"], r["versions"]
    if vid: vs = [v for v in vs if v["id"] == vid]
    if vid and not vs: raise HTTPException(404, "版本不存在")
    files = []
    for v in vs:
        files.append(v["path"])
        if v.get("cover") and v["cover"] != v["path"]: files.append(v["cover"])
    if not vid:
        for a_ in r["assets"]:
            if a_["kind"] in ("cover", "subtitle", "video") and a_.get("path"): files.append(a_["path"])
    files = [f for f in dict.fromkeys(files) if f and os.path.exists(f)]
    pub = any(v["really_published"] for v in vs) or (not vid and w["state"] == "published")
    return w, vs, files, pub

@app.get("/api/work/{wid}/delete_preview")
def api_del_preview(wid: str, vid: str = ""):
    w, vs, files, pub = _del_scope(wid, vid)
    return {"title": w["work_title"], "scope": "version" if vid else "work", "versions": len(vs), "total_versions": w["versions_count"],
            "files": [f.replace(str(HOME), "~") for f in files], "published": pub}

@app.post("/api/work/{wid}/delete")
def api_delete(wid: str, body: dict):
    vid = body.get("version_id") or ""; w, vs, files, pub = _del_scope(wid, vid)
    if pub and not body.get("confirm_published"): raise HTTPException(409, "这是已发布的作品，需要再次确认")
    whole = not vid or len(vs) >= w["versions_count"]
    ok, bad = hub_lib.trash(files)
    t = queue_lib.now()
    hub_lib.log_delete([[t, wid, w["work_title"], "整个作品" if whole else "单个版本", f, "已移到废纸篓", "是" if pub else "否"] for f in ok] +
                       [[t, wid, w["work_title"], "整个作品" if whole else "单个版本", f, "失败：" + why, "是" if pub else "否"] for f, why in bad])
    cleanup_error = ""
    try:
        # Missing files from an earlier interrupted delete need record cleanup too.
        missing = [v["path"] for v in vs if not os.path.exists(v["path"])]
        hub_lib.forget_paths(list(dict.fromkeys(ok + missing)), wid, whole and not bad)
    except Exception as e:
        cleanup_error = str(e)
    finally:
        # File removal has already happened: refresh even if metadata cleanup fails.
        # Never leave stale playable cards behind a successful Finder operation.
        scan()
        _CACHE.clear(); _MEMO.clear()
    if bad and not ok: raise HTTPException(500, "没删成：" + bad[0][1])
    return {"ok": True, "trashed": len(ok), "failed": [{"path": p, "reason": r} for p, r in bad],
            "whole": whole and not bad, "cleanup_warning": cleanup_error}

# ---------- Phase 4：客户展示 ----------
def showcase_items():
    sc = cfg().get("showcase", {}); order = sc.get("order") or []
    cards = [w for w in work_cards(with_meta(INDEX["items"])) if w["featured"] and not w["archived"] and w.get("id")]
    out = []
    for w in cards:
        desc = (w.get("description") or "").strip().splitlines()
        out.append({"id": w["id"], "work_id": w["work_id"], "title": w["work_title"], "intro": desc[0][:60] if desc else "",
                    "type": w["video_type_name"] if w["video_type"] else "", "style": re.sub(r"^" + re.escape(w["video_type_name"]) + r"\s*·\s*", "", w["style_name"]) if w["style_id"] else "",
                    "video_type": w["video_type"], "style_id": w["style_id"], "duration": w.get("duration"), "portrait": w["portrait"], "mtime": w["mtime"]})
    out.sort(key=lambda x: (order.index(x["work_id"]) if x["work_id"] in order else 999, -x["mtime"]))
    for x in out: x.pop("mtime")
    return out

@app.get("/api/showcase")
def api_showcase():
    sc = cfg().get("showcase", {}); st = queue_lib.load_styles()
    items = showcase_items(); used = {i["video_type"] for i in items}
    types = [{"id": t["id"], "name": t["name"], "desc": t.get("description", "")} for t in st["types"]]
    return {"title": sc.get("title"), "tagline": sc.get("tagline"), "intro": sc.get("intro"), "client_mode": bool(sc.get("client_mode")),
            "contact": sc.get("contact", ""), "types": types, "types_with_items": [t for t in types if t["id"] in used], "items": items}

@app.get("/showcase", response_class=HTMLResponse)
def showcase_page(): return _versioned("showcase.html")

@app.post("/api/showcase/export")
def showcase_export():
    """离线演示用：导出一个静态 HTML（视频用 file:// 引用原文件，不复制、不改动原片），放在 ~/video-hub/export/showcase/。"""
    d = api_showcase(); out = ROOT / "export/showcase"; out.mkdir(parents=True, exist_ok=True)
    for it in d["items"]:
        it["src"] = "file://" + INDEX["by_id"][it["id"]]["path"]
        tp = thumb_path(INDEX["by_id"][it["id"]])
        it["poster"] = "file://" + str(tp) if tp and Path(tp).exists() else ""
    html = (ROOT / "static/showcase.html").read_text(encoding="utf-8").replace('<link rel="stylesheet" href="/static/showcase.css">', "<style>" + (ROOT / "static/showcase.css").read_text(encoding="utf-8") + "</style>")
    html = html.replace("/*__STATIC_DATA__*/", "window.SHOWCASE_DATA=" + json.dumps(d, ensure_ascii=False) + ";")
    (out / "index.html").write_text(html, encoding="utf-8")
    return {"ok": True, "path": str(out / "index.html"), "count": len(d["items"])}

# 参考视频链接解析路由（独立模块，见 resolve_api.py）
from resolve_api import router as resolve_router
app.include_router(resolve_router)


@app.get("/api/story-style-kit")
def story_style_kit():
    return FileResponse(ROOT / "data/story-style-video.zip", filename="story-style-video.zip", media_type="application/zip")
