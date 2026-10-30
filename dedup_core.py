"""硬规则：每个作品（同一选题）只显示最新一版。
同一选题 = 标题去掉版本号/空格/标点后相同，或视频 md5 相同（跨产线也算）。
- 卡片：落选卡记录进 data/hidden_cards.json（网站永不返回），并删 works 记录；文件不动。
- 文件：只有桌面产线文件夹里的旧成片移到废纸篓；已发布/精选/风格样片/bot 提交的/1 小时内改过/读不出的/中间件 一律不动。"""
import hashlib, json, os, re, subprocess, threading, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent
HIDDEN_F = ROOT / "data/hidden_cards.json"; MD5_F = ROOT / "data/md5_cache.json"
INTERMEDIATE = re.compile(r"(^|[/_\-.])(raw|backup|hypit-raw|tmp|temp)([/_\-.\d]|$)", re.I)
VER = re.compile(r"(?:[vV]\d+|版本\d*|第?\d+版|\d+版|ver\.?\d+|version\s*\d+)", re.I)
FRAG = re.compile(r"^(?:[A-Za-z0-9]{1,2}|[A-Za-z]\d+|film|raw|out|output|final|video|base|tmp|render)$", re.I)   # 碎片标题不显示
_lock = threading.Lock(); _md5 = None

def norm_title(t):
    t = (t or "").lower(); t = VER.sub("", t)
    return re.sub(r"[\s·\-_|｜【】\[\]()（）:：,，.。!！?？\"“”'‘’]+", "", t)

def md5(p):
    global _md5
    with _lock:
        if _md5 is None:
            try: _md5 = json.loads(MD5_F.read_text())
            except Exception: _md5 = {}
    try: st = os.stat(p)
    except OSError: return None
    k = f"{st.st_size}:{int(st.st_mtime)}"; e = _md5.get(p)
    if e and e[0] == k: return e[1]
    h = hashlib.md5()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""): h.update(b)
    with _lock: _md5[p] = [k, h.hexdigest()]
    return _md5[p][1]

def save_md5():
    with _lock:
        if _md5 is not None: MD5_F.write_text(json.dumps(_md5, ensure_ascii=False))

def hidden():
    try: return set(json.loads(HIDDEN_F.read_text())["group_keys"])
    except Exception: return set()

def _rank(w):  # 越大越优先保留：bot 提交 > 最新
    return (w.get("origin") == "bot", w.get("mtime") or 0)

def clusters(cards):
    """返回 [[保留卡, 落选卡...], ...]，只含 ≥2 张的选题。"""
    cs = [w for w in cards if w.get("path") or w.get("origin") == "bot"]
    par = list(range(len(cs)))
    def f(i):
        while par[i] != i: par[i] = par[par[i]]; i = par[i]
        return i
    seen = {}
    for i, w in enumerate(cs):
        keys = ["t:" + norm_title(w.get("work_title"))] if norm_title(w.get("work_title")) else []
        if w.get("path") and os.path.isfile(w["path"]):
            m = md5(w["path"]); keys += ["m:" + m] if m else []
        for k in keys:
            if k in seen: par[f(i)] = f(seen[k])
            else: seen[k] = i
    save_md5(); g = {}
    for i, w in enumerate(cs): g.setdefault(f(i), []).append(w)
    return [sorted(v, key=_rank, reverse=True) for v in g.values() if len(v) > 1]

def gate(cards):
    """数据层最后关卡：隐藏名单 + 同一选题只留最新一条。"""
    H = hidden(); cards = [w for w in cards if w.get("group_key") not in H and not (FRAG.match(os.path.splitext((w.get("work_title") or "").strip())[0])
             and w.get("origin") != "bot" and not w.get("really_published"))]
    drop = {id(w) for c in clusters(cards) for w in c[1:]}
    return [w for w in cards if id(w) not in drop]

def desktop_dirs(cfg):
    return {os.path.realpath(os.path.expanduser(v)) for k, v in cfg.get("output_dirs", {}).items() if not k.startswith("_")}

def readable(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p], capture_output=True, text=True, timeout=30)
    try: return r.returncode == 0 and float(r.stdout.strip() or 0) > 0
    except ValueError: return False

def plan(app):
    """返回 (要隐藏的卡[(保留,落选)], 要进废纸篓的文件[(保留,落选,路径,原因)], 保留例外[(落选,路径,原因)])"""
    import hub_lib
    items = app.with_meta(app.INDEX["items"]); cards = app._work_cards_raw(items)
    H = hidden(); cards = [w for w in cards if w["group_key"] not in H]
    st = app.queue_lib.STYLES.read_text(encoding="utf-8")
    refs = set(re.findall(r'"(/[^"]+\.(?:mp4|mov|m4v|webm))"', st)) | {os.path.expanduser(x) for x in re.findall(r'"(~/[^"]+\.(?:mp4|mov|m4v|webm))"', st)}
    SM = hub_lib.sub_map(); DD = desktop_dirs(app.cfg()); by = {}
    for i in items:
        if i["kind"] == "final": by.setdefault(i["group_key"], []).append(i)
    hide, files, keep = [], [], []
    def judge(w, k, v, kp):
        p = v["path"]
        why = ("已发布" if v["really_published"] else "精选" if w["featured"] else "风格样片" if p in refs else
               "hub.py 提交的作品" if p in SM else "保留版本同一文件" if p in kp else
               "不在桌面产线文件夹" if os.path.realpath(os.path.dirname(p)) not in DD else
               "中间件" if INTERMEDIATE.search(os.path.basename(p)) else
               "1 小时内改过" if time.time() - os.path.getmtime(p) < 3600 else "")
        if not why and not readable(p): why = "读不出的 mp4"
        if why: keep.append((w, p, why))
        else: files.append((k, w, p, "旧版本"))
    for w in cards:   # 同一张卡里的旧版本
        vs = [v for v in by.get(w["group_key"], []) if v["path"] != w.get("path")]
        for v in vs: judge(w, w, v, {w.get("path")})
    for c in clusters(cards):
        k = c[0]; kp = {v["path"] for v in by.get(k["group_key"], [])}
        for w in c[1:]:
            hide.append((k, w))
            for v in by.get(w["group_key"], []): judge(w, k, v, kp)
    return hide, files, keep

def apply(app, hide, files, scope="去重"):
    import hub_lib, queue_lib
    ok, bad = hub_lib.trash([p for *_, p, _ in files]) if files else ([], [])
    hub_lib.forget_paths(ok)
    H = hidden() | {w["group_key"] for _, w in hide}
    HIDDEN_F.write_text(json.dumps({"_说明": "去重落选的卡片 group_key，网站永不显示；文件不动", "group_keys": sorted(H)}, ensure_ascii=False, indent=1))
    c = hub_lib.db()
    for _, w in hide:
        if w.get("origin") != "bot": c.execute("delete from works where group_key=?", (w["group_key"],))
    c.commit(); c.close()
    t = queue_lib.now(); okset = set(ok); bd = dict(bad)
    hub_lib.log_delete([[t, w["work_id"], w["work_title"], f"{scope}·删卡片记录（保留 {k['work_id']}）", "", "已删卡片记录，文件不动", "是" if w.get("really_published") else "否"] for k, w in hide] +
                       [[t, w["work_id"], w["work_title"], f"{scope}·旧版本文件", p, "已移到废纸篓" if p in okset else "失败：" + bd.get(p, ""), "否"] for k, w, p, _ in files])
    app._CACHE.clear(); app._MEMO.clear()
    return ok, bad

_running = threading.Lock()
def auto(app, scope="自动去重"):
    if os.environ.get("DEDUP_NO_AUTO") or not _running.acquire(blocking=False): return
    try:
        hide, files, _ = plan(app)
        if hide or files: apply(app, hide, files, scope)
    except Exception as e: print("auto dedupe", repr(e))
    finally: _running.release()
