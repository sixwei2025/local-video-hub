#!/usr/bin/env python3
"""小红书发布适配器：调本机 xiaohongshu-mcp（127.0.0.1:18060）。

演练（默认 / --check-only）：
  只校验任务字段 + check_login_status，绝不调用 publish_with_video / publish_content，
  也绝不调用 get_login_qrcode（避免弹码）。

正式（--publish）：
  先 check_login_status；未登录则打印 NEED_SCAN 并以码 10 退出；
  已登录才调 publish_with_video。
"""
from __future__ import annotations
import argparse, json, os, sys, urllib.error, urllib.request
from pathlib import Path

MCP_URL = os.environ.get("XHS_MCP_URL", "http://127.0.0.1:18060/mcp")
COOKIES = Path.home() / ".workbuddy/servers/xiaohongshu-mcp/cookies.json"


def _post(payload: dict, sid: str | None = None, timeout: int = 120):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        MCP_URL, data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
    )
    if sid:
        req.add_header("Mcp-Session-Id", sid)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8", "replace")
        new_sid = r.headers.get("Mcp-Session-Id") or sid
    if not raw.strip():
        return None, new_sid
    try:
        return json.loads(raw), new_sid
    except json.JSONDecodeError:
        for line in raw.splitlines():
            if line.startswith("data:"):
                try:
                    return json.loads(line[5:].strip()), new_sid
                except json.JSONDecodeError:
                    pass
        return {"raw": raw[:500]}, new_sid


def mcp_session():
    body, sid = _post({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "video-hub-xhs", "version": "1.0"},
        },
    })
    if not sid:
        raise RuntimeError("MCP 无会话：服务是否在 127.0.0.1:18060？")
    _post({"jsonrpc": "2.0", "method": "notifications/initialized"}, sid)
    return sid


def call_tool(sid: str, name: str, args: dict, timeout: int = 600):
    body, _ = _post({
        "jsonrpc": "2.0", "id": 99, "method": "tools/call",
        "params": {"name": name, "arguments": args},
    }, sid, timeout=timeout)
    if not body or "result" not in body:
        err = (body or {}).get("error") or body
        raise RuntimeError(f"MCP 工具 {name} 失败：{err}")
    parts = body["result"].get("content") or []
    txt = "\n".join(p.get("text", "") for p in parts if p.get("type") == "text")
    return txt


def check_login(sid: str) -> tuple[bool, str]:
    txt = call_tool(sid, "check_login_status", {}, timeout=60)
    ok = ("已登录" in txt) or ("logged" in txt.lower() and "not" not in txt.lower())
    return ok, txt.strip()


def main():
    ap = argparse.ArgumentParser(description="video-hub 小红书 MCP 适配器")
    ap.add_argument("package", help="publish_packages 里的 JSON（含 video/title/content/tags）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--check-only", action="store_true", help="演练：只校验+查登录，不发布（默认）")
    g.add_argument("--publish", action="store_true", help="正式发布（需 pub.py run --approved）")
    args = ap.parse_args()
    if not args.publish:
        args.check_only = True

    pkg_path = Path(args.package)
    if not pkg_path.is_file():
        print("FAIL package 不存在", pkg_path); return 11
    pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
    title = (pkg.get("title") or "").strip()
    content = (pkg.get("content") or pkg.get("desc") or "").strip()
    video = pkg.get("video") or pkg.get("video_path") or ""
    tags = [str(t).strip().lstrip("#") for t in (pkg.get("tags") or pkg.get("topics") or []) if str(t).strip()]

    errs = []
    if not title: errs.append("标题为空")
    elif len(title) > 20: errs.append(f"标题超过 20 字（当前 {len(title)}）")
    if not content: errs.append("正文/简介为空")
    if not video or not os.path.isfile(video): errs.append("视频文件不存在")
    if "vibe知识大赏" not in tags: errs.append("话题缺少 vibe知识大赏")
    if errs:
        for e in errs: print("FAIL", e)
        print("校验失败：" + "；".join(errs))
        return 11

    if not COOKIES.exists():
        print("NEED_SCAN 缺少 cookies：", COOKIES)
        print("请人工在本机跑 xiaohongshu-login 扫码（发布官不要自动弹码）")
        return 10

    try:
        sid = mcp_session()
        ok, status = check_login(sid)
    except Exception as e:
        print("NEED_SCAN MCP/登录检查失败：", str(e)[:200])
        print("请确认 launchctl 服务 com.yuanliuwei.xiaohongshu-mcp 在跑，或人工扫码刷新 cookies")
        return 10

    print("LOGIN", status.replace("\n", " | "))
    if not ok:
        print("NEED_SCAN 小红书未登录（账号需人工扫码，见 ~/.workbuddy/servers/xiaohongshu-mcp/）")
        return 10

    if args.check_only:
        # MCP 无官方 dry-run：演练到此为止，绝不 publish_*
        print("DRY-RUN：字段与登录已通过，未调用 publish_with_video")
        return 0

    # 正式发布
    try:
        txt = call_tool(sid, "publish_with_video", {
            "title": title,
            "content": content,
            "video": os.path.abspath(video),
            "tags": tags or None,
        }, timeout=900)
    except Exception as e:
        print("FAILED", str(e)[:300])
        return 12

    print(txt)
    low = txt.lower()
    if any(k in txt for k in ("成功", "已发布", "发布成功")) or "http" in low:
        # 尽量抽出链接
        url = ""
        for tok in txt.replace("\n", " ").split():
            if tok.startswith("http"):
                url = tok.strip("，。,)")
                break
        print("PUBLISHED", url or "ok")
        return 0
    if "NEED_SCAN" in txt or "未登录" in txt or "登录" in txt and "失败" in txt:
        print("NEED_SCAN", txt[:200])
        return 10
    print("FAILED", txt[:300])
    return 12


if __name__ == "__main__":
    try:
        sys.exit(main())
    except urllib.error.URLError as e:
        print("NEED_SCAN 无法连接小红书 MCP：", e)
        sys.exit(10)
