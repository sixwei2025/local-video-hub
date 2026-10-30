"""参考视频链接解析 API（独立路由，挂载到主 app，尽量不动 app.py）。
用法：在 app.py 里加一行  from resolve_api import router as resolve_router; app.include_router(resolve_router)
对外暴露 POST /api/resolve  body: {"url": "<链接或分享文案>"}
返回 resolve_ref.py 的 JSON，并补上可直接播放的 preview 地址。"""
import json, os, subprocess, sys
from pathlib import Path
from fastapi import APIRouter
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent
PY = str(ROOT / ".venv/bin/python")
RESOLVER = str(ROOT / "tools/resolve_ref.py")
REFS = ROOT / "uploads/refs"
router = APIRouter()

class ResolveReq(BaseModel):
    url: str

@router.post("/api/resolve")
def api_resolve(req: ResolveReq):
    REFS.mkdir(parents=True, exist_ok=True)
    try:
        p = subprocess.run([PY, RESOLVER, req.url, "--out", str(REFS)],
                           capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return {"ok": False, "platform": None, "error": "解析超时（>10 分钟），请重试或改用上传。", "need_upload": True}
    out = (p.stdout or "").strip().splitlines()
    data = None
    for ln in reversed(out):
        ln = ln.strip()
        if ln.startswith("{"):
            try: data = json.loads(ln); break
            except Exception: continue
    if data is None:
        return {"ok": False, "platform": None, "error": (p.stderr or "解析器无输出")[-300:], "need_upload": True}
    # 规范化为绝对路径 + 预览地址
    if data.get("path"):
        ap = str((ROOT / data["path"]).resolve()) if not os.path.isabs(data["path"]) else data["path"]
        data["path"] = ap
        data["preview"] = "/file?path=" + ap
    return data
