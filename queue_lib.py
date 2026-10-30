"""jobs.jsonl 读写：追加写新任务；状态更新时把同 id 的最新记录合并（整文件原子重写，带文件锁）。"""
import json, os, fcntl, uuid, tempfile
from datetime import datetime
from pathlib import Path
QUEUE = Path.home() / "video-hub/queue/jobs.jsonl"
LOCK = QUEUE.with_suffix(".lock")
STATUSES = ("pending", "running", "done", "failed")

def now(): return datetime.now().astimezone().isoformat(timespec="seconds")

class _Lock:
    def __enter__(self):
        QUEUE.parent.mkdir(parents=True, exist_ok=True)
        self.f = open(LOCK, "w"); fcntl.flock(self.f, fcntl.LOCK_EX); return self
    def __exit__(self, *a): fcntl.flock(self.f, fcntl.LOCK_UN); self.f.close()

def _read():
    if not QUEUE.exists(): return []
    out = {}
    for line in QUEUE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line: continue
        try: j = json.loads(line)
        except Exception: continue
        if "id" in j: out.setdefault(j["id"], {}).update(j)
    return list(out.values())

def _write(jobs):
    fd, tmp = tempfile.mkstemp(dir=QUEUE.parent)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        for j in jobs: f.write(json.dumps(j, ensure_ascii=False) + "\n")
    os.replace(tmp, QUEUE)

def load_jobs():
    with _Lock(): return sorted(_read(), key=lambda j: j.get("created_at", ""), reverse=True)

def add_job(prompt, ref_images, output_dir, line, video_type="", style_id="", style_custom_text="", style_ref_images=None, **extra):
    import bot_registry
    # Snapshot the recipe so later catalog edits cannot change a queued production brief.
    if style_id and style_id != "custom":
        _, preset, _ = find_style(video_type, style_id)
        if preset and (preset.get("prompt_template") or preset.get("mine")):
            extra.setdefault("style_recipe", dict(preset))
            extra.setdefault("production_skill", preset.get("skill", ""))
            style_custom_text = style_custom_text or preset.get("prompt_template") or preset.get("description", "")
    if not extra.get("target_bot") and extra.get("kind") != "revise":
        target = bot_registry.responsible(video_type,line)
        if target: extra.update(target_bot=target,routing_basis="responsibility",dispatch_state="queued")
    j = {"id": datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6], "prompt": prompt,
         "ref_images": ref_images, "output_dir": output_dir, "line": line, "video_type": video_type, "style_id": style_id,
         "style_custom_text": style_custom_text, "style_ref_images": style_ref_images or [], "status": "pending",
         "result_paths": [], "error": "", "created_at": now(), "updated_at": now(), **extra}
    with _Lock():
        with open(QUEUE, "a", encoding="utf-8") as f: f.write(json.dumps(j, ensure_ascii=False) + "\n")
    return j

def update_job(jid, status, results=None, error=None):
    assert status in STATUSES
    with _Lock():
        jobs = _read(); j = next((x for x in jobs if x["id"] == jid), None)
        if not j: return None
        j["status"] = status; j["updated_at"] = now()
        if status == "running": j["started_at"] = now()
        if status in ("done", "failed"): j["finished_at"] = now()
        if results is not None: j["result_paths"] = [os.path.abspath(os.path.expanduser(r)) for r in results]
        if error is not None: j["error"] = error
        _write(jobs); return j

def delete_job(jid):
    with _Lock():
        jobs = _read(); n = [j for j in jobs if j["id"] != jid]
        if len(n) == len(jobs): return False
        _write(n); return True

STYLES = Path(__file__).resolve().parent / "styles.json"
_SC = {"m": 0, "d": None}
MY_STYLES = Path(__file__).resolve().parent / "my_styles.json"   # 「我的风格」：{"styles":[{id,video_type,name,description,ref_videos,thumbnail,created_at}]}
def load_my_styles():
    try: return json.loads(MY_STYLES.read_text(encoding="utf-8"))
    except Exception: return {"styles": []}
def save_my_styles(d):
    tmp = MY_STYLES.with_suffix(".tmp"); tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8"); tmp.replace(MY_STYLES)
def load_styles():
    m = (STYLES.stat().st_mtime, MY_STYLES.stat().st_mtime if MY_STYLES.exists() else 0)
    if _SC["m"] != m:
        d = json.loads(STYLES.read_text(encoding="utf-8")); mine = load_my_styles()["styles"]
        for t in d["types"]:
            ms = [dict(x, mine=True, automation="custom-ref") for x in mine if x.get("video_type") == t["id"]]
            if ms:
                ci = next((k for k, p in enumerate(t["presets"]) if p["id"] == "custom"), len(t["presets"]))
                t["presets"][ci:ci] = ms
        _SC["d"] = d; _SC["m"] = m
    return _SC["d"]
def find_style(video_type, style_id):
    doc = load_styles()
    for t in doc["types"]:
        if video_type and t["id"] != video_type: continue
        for p in t["presets"]:
            if p["id"] == style_id: return t, p, doc
    return None, None, doc

def patch_job(jid, **fields):
    """给任务补字段（阶段、作品 id 等），不改状态。"""
    with _Lock():
        jobs = _read(); j = next((x for x in jobs if x["id"] == jid), None)
        if not j: return None
        j.update(fields); j["updated_at"] = now(); _write(jobs); return j


def claim_job(jid, bot=None):
    """Atomic directed claim. Another robot must never take an assigned revision."""
    import bot_registry
    bot=bot_registry.canonical(bot)
    with _Lock():
        jobs = _read(); j = next((x for x in jobs if x['id'] == jid), None)
        if not j or j['status'] != 'pending' or j.get('deleted'): return False
        if j.get('dispatch_state') == 'unassigned': return False
        if j.get('target_bot') and bot_registry.canonical(j['target_bot']) != bot: return False
        j.update(status='running', claimed_by=bot or '', received_at=now(), started_at=now(), updated_at=now(),dispatch_state='accepted')
        _write(jobs);return True
