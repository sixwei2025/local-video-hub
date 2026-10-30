"""发布队列 ~/video-hub/queue/publish.jsonl + 平台探测 + 封面截取 + 调用现有发布器。"""
import json, os, re, sqlite3, subprocess, uuid, fcntl, tempfile
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parent
QUEUE = ROOT / "queue/publish.jsonl"; LOCK = QUEUE.with_suffix(".lock")
PKG = ROOT / "queue/publish_packages"; COVERS = ROOT / "cache/covers"; LOGS = ROOT / "data/publish_logs"
DB = ROOT / "data/meta.db"
H = Path.home()
DOUYIN = H / "lab/douyin-publisher"; CHANNELS = H / "GrokBridge/视频号"
XHS_MCP_DIR = H / ".workbuddy/servers/xiaohongshu-mcp"
XHS_COOKIES = XHS_MCP_DIR / "cookies.json"
XHS_MCP_URL = "http://127.0.0.1:18060/mcp"
STATUSES = ("pending", "running", "done", "failed")
PLATFORM_NAMES = {"douyin": "抖音", "channels": "视频号", "xhs": "小红书"}
# 视频号多账号：每号固定 Chrome user-data-dir + CDP 端口（与 ~/GrokBridge/视频号/chlib.py ACCOUNTS 保持一致）
CHANNEL_ACCOUNTS = {
    "袁六伟":   {"port": 9333, "profile": str(H / "GrokBridge/视频号/chrome-profile"), "log": str(H / "GrokBridge/视频号/keepalive.log"), "desc": "主号 · AI 相关"},
    "山河来电": {"port": 9335, "profile": str(H / "GrokBridge/视频号/汇芯袁总/chrome-profile"), "log": str(H / "GrokBridge/视频号/山河来电/keepalive.log"), "desc": "3D 地图"},
    "汇芯袁总": {"port": 9334, "profile": str(H / "GrokBridge/视频号/山河来电/chrome-profile"), "log": str(H / "GrokBridge/视频号/汇芯袁总/keepalive.log"), "desc": "其他内容"},
}
DEFAULT_CHANNEL_ACCOUNT = "袁六伟"
_AI_RE = re.compile(r"(?<![A-Za-z])AI(?![A-Za-z])|AIGC|人工智能|大模型|GPT|Grok|Claude|Gemini|DeepSeek|智能体|Agent|Cursor|Codex|LLM|提示词|Prompt|Workbuddy|Skill|自动化", re.I)
def auto_account(line="", *texts):
    """默认账号：3D 地图产线 → 山河来电；AI 相关内容 → 袁六伟；其他 → 汇芯袁总。"""
    if (line or "") == "map3d": return "山河来电"
    t = " ".join(" ".join(x) if isinstance(x, (list, tuple)) else str(x or "") for x in texts)
    if re.search(r"3D\s*地图|三维地图", t if False else " ".join(" ".join(x) if isinstance(x, (list, tuple)) else str(x or "") for x in texts), re.I): return "山河来电"
    t = re.sub(r"内容(含|由)?AI(生成|辅助)[^\s]*", "", t)   # 每条都带的 AI 声明尾巴不算
    return "袁六伟" if _AI_RE.search(t) else "汇芯袁总"
def job_account(j):
    a = j.get("account") or DEFAULT_CHANNEL_ACCOUNT
    return a if a in CHANNEL_ACCOUNTS else DEFAULT_CHANNEL_ACCOUNT

def now(): return datetime.now().astimezone().isoformat(timespec="seconds")
class _L:
    def __enter__(self):
        QUEUE.parent.mkdir(parents=True, exist_ok=True); self.f = open(LOCK, "w"); fcntl.flock(self.f, fcntl.LOCK_EX)
    def __exit__(self, *a): fcntl.flock(self.f, fcntl.LOCK_UN); self.f.close()
def _read():
    out = {}
    if QUEUE.exists():
        for l in QUEUE.read_text(encoding="utf-8").splitlines():
            try: j = json.loads(l)
            except Exception: continue
            out.setdefault(j["id"], {}).update(j)
    return list(out.values())
def _write(js):
    fd, t = tempfile.mkstemp(dir=QUEUE.parent)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        for j in js: f.write(json.dumps(j, ensure_ascii=False) + "\n")
    os.replace(t, QUEUE)
def load():
    with _L(): return sorted(_read(), key=lambda j: j["created_at"], reverse=True)
def get(jid): return next((j for j in load() if j["id"] == jid), None)
def add(d):
    d = ensure_required_topic(dict(d))
    j = {"id": "pub-" + datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4], "status": "pending",
         "result_url": "", "record_path": "", "error": "", "log_path": "", "created_at": now(), "updated_at": now(), **d}
    with _L():
        with open(QUEUE, "a", encoding="utf-8") as f: f.write(json.dumps(j, ensure_ascii=False) + "\n")
    return j
def update(jid, **kw):
    with _L():
        js = _read(); j = next((x for x in js if x["id"] == jid), None)
        if not j: return None
        j.update(kw); j["updated_at"] = now(); _write(js); return j
def delete(jid):
    with _L():
        js = _read(); n = [x for x in js if x["id"] != jid]
        if len(n) == len(js): return False
        _write(n); return True

def mark_published(video_path, platform, url=""):
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    c.execute("create table if not exists meta(path text primary key, status text, tags text default '[]', note text default '', updated_at text)")
    r = c.execute("select * from meta where path=?", (video_path,)).fetchone()
    tags = set(json.loads(r["tags"])) if r else set(); tags.add("已发" + PLATFORM_NAMES.get(platform, platform))
    note = (r["note"] if r else "") or ""
    if url and url not in note: note = (note + f" {PLATFORM_NAMES.get(platform)}:{url}").strip()
    c.execute("insert into meta(path,status,tags,note,updated_at) values(?,?,?,?,?) on conflict(path) do update set status=excluded.status,tags=excluded.tags,note=excluded.note,updated_at=excluded.updated_at",
              (video_path, "published", json.dumps(sorted(tags), ensure_ascii=False), note, now()))
    c.commit(); c.close()

# ---------- 平台探测（只读，不碰浏览器） ----------
def _pg(pat):
    return subprocess.run(["pgrep", "-f", pat], capture_output=True, text=True).stdout.strip()
def platforms():
    dy = {"id": "douyin", "name": "抖音", "ok": True, "reason": "", "mode": "自动（Playwright + 已登录 profile，默认演练）"}
    if not (DOUYIN / "publish.py").exists(): dy.update(ok=False, reason="找不到 ~/lab/douyin-publisher/publish.py")
    elif not (DOUYIN / "profile").exists(): dy.update(ok=False, reason="没有登录 profile，先跑 login.py 扫码")
    else:
        st = (DOUYIN / "login_status.txt").read_text().strip() if (DOUYIN / "login_status.txt").exists() else ""
        if st and "LOGGED_IN" not in st: dy.update(ok=False, reason=f"登录状态 {st}，需重新扫码 login.py")
        if _pg("user-data-dir=.*douyin-publisher/profile"): dy["busy"] = "profile 正被另一个发布进程占用，执行时需等待"
    ch = {"id": "channels", "name": "视频号", "ok": False, "reason": "", "mode": "自动（按账号 CDP 接管各自专用 Chrome，脚本不点登录）", "accounts": []}
    for name, a in CHANNEL_ACCOUNTS.items():
        x = channel_account_status(name); ch["accounts"].append(x)
    if not (CHANNELS / "upload_draft.py").exists(): ch.update(reason="找不到 ~/GrokBridge/视频号/upload_draft.py")
    else:
        ch["ok"] = any(x["ok"] for x in ch["accounts"])
        ch["reason"] = "；".join(f'{x["account"]}：{x["reason"]}' for x in ch["accounts"] if not x["ok"])
    xhs = {"id": "xhs", "name": "小红书", "ok": True, "reason": "", "mode": "自动（xiaohongshu-mcp · cookies；演练=校验+查登录，不发）", "account": "袁六伟"}
    if not (ROOT / "xhs_publish.py").exists():
        xhs.update(ok=False, reason="找不到 ~/video-hub/xhs_publish.py")
    elif not XHS_COOKIES.exists():
        xhs.update(ok=False, reason="NEED_SCAN 无 cookies，需人工跑 xiaohongshu-login（发布官不自动弹码）")
    elif not _pg("xiaohongshu-mcp"):
        # 端口探测：服务进程名
        import socket
        s = socket.socket(); s.settimeout(0.4)
        try:
            s.connect(("127.0.0.1", 18060)); s.close()
        except Exception:
            xhs.update(ok=False, reason="小红书 MCP 未在 127.0.0.1:18060 监听（launchctl start com.yuanliuwei.xiaohongshu-mcp）")
    return [dy, ch, xhs]

def channel_account_status(name):
    a = CHANNEL_ACCOUNTS[name]; x = {"account": name, "port": a["port"], "profile": a["profile"], "ok": True, "reason": "", "last_check": ""}
    if not _pg(f"remote-debugging-port={a['port']}"): x.update(ok=False, reason=f"{a['port']} 专用 Chrome 没在运行（脚本会自行拉起，但需先确认登录）")
    else:
        lg = Path(a["log"]); lines = lg.read_text(encoding="utf-8").strip().splitlines() if lg.exists() else []
        last = next((l for l in reversed(lines) if " SKIP " not in f" {l} "), "")
        if not last: x.update(ok=False, reason="还没有保活检查记录")
        elif " OK " not in f" {last} ": x.update(ok=False, reason="保活检查未通过：" + last[:80] + f"（NEED_SCAN 时需微信扫 ~/GrokBridge/视频号/{name}/qr_latest.png）")
        x["last_check"] = last[:60]
    return x

# ---------- 封面：第 0.01 秒，3:4 与 4:3 ----------
def make_covers(vid, video):
    """从成片截封面。竖 3:4 适当放大（中心再裁约 1.25x）让字更大更清晰；横 4:3 同理。"""
    COVERS.mkdir(parents=True, exist_ok=True)
    v, h = COVERS / f"{vid}-3x4.jpg", COVERS / f"{vid}-4x3.jpg"
    # 先按比例取框，再中心放大 1.25 倍后 scale 到目标尺寸
    vf_v = ("crop='min(iw,ih*3/4)':'min(ih,iw*4/3)',"
            "crop='iw/1.25':'ih/1.25',scale=1080:1440")
    vf_h = ("crop='min(iw,ih*4/3)':'min(ih,iw*3/4)',"
            "crop='iw/1.25':'ih/1.25',scale=1440:1080")
    for out, vf in ((v, vf_v), (h, vf_h)):
        if not out.exists() or out.stat().st_mtime < os.path.getmtime(video):
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "0.01", "-i", video, "-frames:v", "1", "-vf", vf, "-q:v", "2", str(out)],
                           stdin=subprocess.DEVNULL, timeout=60)
    return str(v), str(h)


# ---------- 强制话题「vibe知识大赏」（六伟规则）+ 发布暂停锁 ----------
REQUIRED_TOPIC = "vibe知识大赏"
TOPIC_LIMITS = {"douyin": {"max_topics": 5, "max_len": 1000}, "channels": {"max_topics": 10, "max_len": 1000}, "xhs": {"max_topics": 10, "max_len": 1000}}
DESC_MAX = 30  # 各平台简介统一上限（汉字/字符按 Unicode 码点计）
_DESC_TRAIL = "，。！？；：、…,.!?;: \t\n\r　"
PAUSE_LOCK = Path.home() / "GrokBridge/locks/publish.lock"

def truncate_desc(text, max_len=DESC_MAX):
    """截断简介至 ≤max_len；优先在句读/分句处切开，并去掉末尾标点。返回 (结果, 是否截断)。"""
    s = (text or "").strip()
    if len(s) <= max_len:
        return s, False
    cut = s[:max_len]
    best = -1
    for i, ch in enumerate(cut):
        if ch in "。！？；\n":
            best = i
    if best >= max(6, max_len // 4):
        cut = cut[: best + 1]
    else:
        best = -1
        for i, ch in enumerate(cut):
            if ch in "，、, ":
                best = i
        if best >= max(6, max_len // 4):
            cut = cut[:best]
    while cut and cut[-1] in _DESC_TRAIL:
        cut = cut[:-1]
    if len(cut) > max_len:
        cut = cut[:max_len]
        while cut and cut[-1] in _DESC_TRAIL:
            cut = cut[:-1]
    if not cut:
        cut = s[:max_len]
        while cut and cut[-1] in _DESC_TRAIL:
            cut = cut[:-1]
        cut = cut or s[:max_len]
    return cut, True

def ensure_desc(j, log=None):
    """发布前保证 desc ≤ DESC_MAX；超长自动截断。写 desc_original / desc_truncated / _desc_trunc_msg；可选写入 log。"""
    raw = j.get("desc", "") or ""
    new, truncated = truncate_desc(raw)
    j["desc"] = new
    if truncated:
        j["desc_original"] = raw
        j["desc_truncated"] = True
        msg = f"简介截断（≤{DESC_MAX}）：原文={raw!r} → 改后={new!r}"
        j["_desc_trunc_msg"] = msg
        if log is not None:
            if hasattr(log, "write"):
                log.write(msg + "\n")
            elif isinstance(log, list):
                log.append(msg)
    else:
        j.pop("desc_truncated", None)
        j.pop("_desc_trunc_msg", None)
    return j

def ensure_required_topic(j):
    """原地补齐必带话题：去重、置首、超出平台话题个数/字数时从末尾挤掉；并保证简介 ≤ DESC_MAX。"""
    ensure_desc(j)
    if j.get("platform") not in TOPIC_LIMITS: return j
    lim = TOPIC_LIMITS[j["platform"]]; seen = set(); tps = []
    for t in [REQUIRED_TOPIC] + [str(x).strip().lstrip("#") for x in (j.get("topics") or [])]:
        if t and t not in seen: seen.add(t); tps.append(t)
    while len(tps) > lim["max_topics"]: tps.pop()
    desc = j.get("desc", "") or ""
    def total(ts): return len(desc) + sum(len(t) + 2 for t in ts if ("#" + t) not in desc)
    while len(tps) > 1 and total(tps) > lim["max_len"]: tps.pop()
    j["topics"] = tps; return j

def pause_reason(self_owner=None):
    """锁存在且 owner 不是本次运行自己 → 返回原因（暂停）；否则 None。从不删除锁。"""
    if not PAUSE_LOCK.exists(): return None
    try: txt = PAUSE_LOCK.read_text(encoding="utf-8", errors="replace").strip()
    except Exception as e: txt = "unreadable:" + str(e)
    m = re.search(r"owner=(\S+)", txt); owner = m.group(1) if m else ""
    self_owner = self_owner or os.environ.get("PUBLISH_LOCK_OWNER")
    if self_owner and owner == self_owner: return None
    return f"发布已暂停（{PAUSE_LOCK} 被占用：{txt[:120]}）"

# ---------- 参数校验 ----------
def validate(j):
    e = []
    ensure_desc(j)  # 超长简介发布前自动截断；校验看截断后结果
    if not os.path.isfile(j["video_path"]): e.append("视频文件不存在")
    d = (j.get("desc") or "").strip()
    if len(d) > DESC_MAX: e.append(f"简介必填且 ≤{DESC_MAX} 字")
    if j["platform"] == "douyin":
        if not j["title"] or len(j["title"]) > 30: e.append("抖音标题必填且 ≤30 字")
        if j.get("cover") and not os.path.isfile(j["cover"]): e.append("封面文件不存在")
    elif j["platform"] == "channels":
        st = j.get("short_title") or ""
        if not st or len(st) > 16: e.append("视频号短标题必填且 ≤16 字")
        if re.search(r"[，。！？；：、“”《》（）,]", st): e.append("视频号短标题不支持标点（用空格代替）")
        if not d: e.append("视频号描述必填")
        if j.get("account") and j["account"] not in CHANNEL_ACCOUNTS: e.append("未知视频号账号：" + j["account"])
        if not j.get("cover"): e.append("视频号必须指定 3:4 竖封面（cover）")
        elif not os.path.isfile(j["cover"]): e.append("封面文件不存在")
    elif j["platform"] == "xhs":
        # 小红书 MCP：标题最多 20 个中文字/英文词；此处按 Unicode 码点计 ≤20
        t = j.get("title") or ""
        if not t or len(t) > 20: e.append("小红书标题必填且 ≤20 字")
        if not d: e.append("小红书正文/简介必填")
        if j.get("cover") and not os.path.isfile(j["cover"]): e.append("封面文件不存在")
    else: e.append("未知平台")
    return e

def douyin_package(j):
    j = ensure_required_topic(dict(j))
    PKG.mkdir(parents=True, exist_ok=True)
    pkg = {"video": j["video_path"], "cover": j.get("cover") or None, "cover_h": j.get("cover_h") or None,
           "title": j["title"], "desc": j.get("desc", ""), "topics": j.get("topics", []), "ai_declare": bool(j.get("ai_declare"))}
    if j.get("mentions"): pkg["mentions"] = j["mentions"]
    pkg = {k: v for k, v in pkg.items() if v is not None}
    p = PKG / f'{j["id"]}.json'; p.write_text(json.dumps(pkg, ensure_ascii=False, indent=1), encoding="utf-8"); return p

def channels_desc(j):
    j = ensure_required_topic(dict(j))
    d = j.get("desc", "").strip(); tp = " ".join("#" + t for t in j.get("topics", []) if ("#" + t) not in d)
    return (d + (" " + tp if tp else "")).strip()

def xhs_package(j):
    """小红书 MCP 包：title/content/video/tags；必带话题已由 ensure_required_topic 置首。"""
    j = ensure_required_topic(dict(j))
    PKG.mkdir(parents=True, exist_ok=True)
    pkg = {"video": j["video_path"], "title": j["title"], "content": (j.get("desc") or "").strip(),
           "tags": j.get("topics") or [], "topics": j.get("topics") or []}
    p = PKG / f'{j["id"]}.json'; p.write_text(json.dumps(pkg, ensure_ascii=False, indent=1), encoding="utf-8"); return p

def command(j, real=False):
    """返回 (cwd, argv)。real=False 为演练：
    抖音=填表停在发布前截图；视频号=--check-only；
    小红书= xhs_publish.py --check-only（只校验字段+check_login_status，不调 publish_*，不弹码）。"""
    if j["platform"] == "douyin":
        p = douyin_package(j)
        argv = [str(DOUYIN / ".venv/bin/python"), "publish.py", str(p), "--shot", str(LOGS / f'{j["id"]}.png')]
        if real: argv.insert(3, "--publish")
        return str(DOUYIN), argv
    if j["platform"] == "xhs":
        p = xhs_package(j)
        py = str(ROOT / ".venv/bin/python") if (ROOT / ".venv/bin/python").exists() else "python3"
        argv = [py, str(ROOT / "xhs_publish.py"), str(p), "--publish" if real else "--check-only"]
        return str(ROOT), argv
    # channels
    argv = [str(CHANNELS / "venv/bin/python"), "upload_draft.py"]
    argv += [j["video_path"], j["short_title"], channels_desc(j)] if real else ["--check-only"]
    if real:  # 六伟硬性要求：视频号必须上传指定 3:4 竖封面；横封面(4:3)仅在平台必填时由脚本使用
        if not j.get("cover"): raise ValueError("视频号任务缺少 cover（3:4 竖封面），拒绝发布")
        argv += ["--cover", j["cover"]]
        ch = j.get("cover_h")
        if not ch:
            try: ch = make_covers(j["id"], j["video_path"])[1]
            except Exception: ch = None
        if ch and os.path.isfile(ch): argv += ["--cover-h", ch]
    argv += ["--account", job_account(j)]
    return str(CHANNELS), argv


# ---------- Phase 3：回写作品 / 今日计数 ----------
def writeback_work(j, url="", record=""):
    """拿到真实结果（pub.py run 成功或 done 回写）后：作品 → 已发布，记平台+时间+链接到 assets(kind=publish)。"""
    wid = j.get("work_id")
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    if not wid:
        r = c.execute("select w.id from works w left join assets a on a.work_id=w.id and a.kind='video' where w.selected_path=? or a.path=? limit 1", (j["video_path"], j["video_path"])).fetchone()
        wid = r["id"] if r else None
    if wid:
        t = now()
        c.execute("insert into assets(work_id,kind,value,label,created_at) values(?,?,?,?,?)",
                  (wid, "publish", json.dumps({"platform": j["platform"], "url": url, "record": record, "pub_id": j["id"], "time": t}, ensure_ascii=False), PLATFORM_NAMES.get(j["platform"]), t))
        c.execute("update works set state='published', updated_at=? where id=?", (t, wid)); c.commit()
    c.close(); return wid

def today_count(platform="douyin"):
    d = datetime.now().strftime("%Y-%m-%d"); n = sum(1 for j in load() if j["platform"] == platform and j["status"] == "done" and (j.get("finished_at") or "").startswith(d))
    if platform == "douyin":
        f = DOUYIN / "发布记录.csv"
        if f.exists():
            for line in f.read_text(encoding="utf-8-sig").splitlines()[1:]:
                if line.startswith(d) and ",成功," in line: n += 1
    return n
DAILY_LIMIT = {"douyin": 10, "channels": 10, "xhs": 10}


def enqueue_batch(specs, approved=False):
    """Atomic platform batch; repeated clicks reuse the same platform/video job."""
    with _L():
        js = _read(); result = []; created = []
        for spec in specs:
            spec = ensure_required_topic(dict(spec))
            if any(j['platform'] == spec['platform'] and j['video_path'] == spec['video_path']
                   and j.get('needs_verification') and j['status'] != 'done' for j in js):
                raise ValueError('上次发布结果未确认，请先在平台核对，避免重复发布')
            old = next((j for j in reversed(js) if j['platform'] == spec['platform']
                        and j['video_path'] == spec['video_path']
                        and j['status'] in ('pending', 'running', 'done')), None)
            if old:
                if old['status'] == 'pending':
                    keys = ('title', 'short_title', 'desc', 'topics', 'cover', 'cover_h', 'ai_declare', 'account')
                    ensure_required_topic(old)
                    if any(old.get(k) != spec.get(k) for k in keys):
                        raise ValueError('该平台已有此视频的待发布任务，文案不一致，请先处理原任务')
                    if approved: old.update(approved_at=now(), approved_by='website-user')
                result.append(old); continue
            j = {'id': 'pub-' + datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8],
                 'status': 'pending', 'result_url': '', 'record_path': '', 'error': '', 'log_path': '',
                 'created_at': now(), 'updated_at': now(), **spec}
            if approved: j.update(approved_at=now(), approved_by='website-user')
            js.append(j); created.append(j); result.append(j)
        _write(js)
        return result


def claim(jid):
    """Only one executor may transition a queued job to running."""
    with _L():
        js = _read(); j = next((x for x in js if x['id'] == jid), None)
        if not j or j['status'] != 'pending': return False
        j.update(status='running', started_at=now(), updated_at=now()); _write(js)
        return True
