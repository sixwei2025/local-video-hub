#!/usr/bin/env python3
"""视频中心 · 发布队列 CLI（queue/publish.jsonl）
  pub.py list [--status pending|running|done|failed|all]
  pub.py show <id>                         # 含将要执行的发布器命令
  pub.py dryrun <id>                       # 演练：抖音=填表截图；视频号=--check-only；小红书=校验+查登录（不调 publish、不弹码）。不改状态、不发布
  pub.py run <id> --approved               # 真实发布（需六伟批准）：running → 调发布器 → done/failed，成功自动标「已发布」
                                           # 若 ~/GrokBridge/locks/publish.lock 存在且 owner 非本次，打印 PAUSED 退出码 3，任务保持 pending
  pub.py running <id>
  pub.py done <id> [--url 作品链接] [--record 记录文件路径]   # 手动回写，并在 meta.db 标「已发布」
  pub.py failed <id> [--error 原因]
  pub.py retry <id>                        # 失败的任务重新排队（pending）
  pub.py delete <id>
  pub.py account <id> <袁六伟|山河来电|汇芯袁总|auto>   # 改视频号发布账号（auto=按产线/内容自动判断）
  pub.py accounts                          # 列出视频号账号 + 小红书 MCP 状态
"""
import argparse, json, subprocess, sys
import publish_lib as P

def _note_desc_trunc(j, sink=None):
    """把简介截断说明打到终端，并可选写入日志文件/可写对象。"""
    msg = j.get("_desc_trunc_msg")
    if not msg and j.get("desc_truncated") and j.get("desc_original") is not None:
        msg = f"简介截断（≤{P.DESC_MAX}）：原文={j.get('desc_original')!r} → 改后={j.get('desc')!r}"
    if not msg: return
    print(msg, flush=True)
    if sink is not None:
        if hasattr(sink, "write"): sink.write(msg + "\n")
        elif isinstance(sink, list): sink.append(msg)

def run_cmd(j, real):
    j = P.ensure_required_topic(dict(j))  # 含简介 ≤30 截断
    cwd, argv = P.command(j, real); P.LOGS.mkdir(parents=True, exist_ok=True)
    log = P.LOGS / f'{j["id"]}-{"publish" if real else "dryrun"}.log'
    print("执行：", " ".join(argv), "\n目录：", cwd, "\n日志：", log, flush=True)
    with open(log, "w", encoding="utf-8") as f:
        _note_desc_trunc(j, f)
        r = subprocess.run(argv, cwd=cwd, stdout=f, stderr=subprocess.STDOUT, timeout=1800)
    out = log.read_text(encoding="utf-8", errors="replace"); return r.returncode, out, str(log)

def _plat_label(j):
    name = P.PLATFORM_NAMES.get(j["platform"], j["platform"])
    if j["platform"] == "channels": return name + "·" + P.job_account(j)
    if j["platform"] == "xhs": return name + "·袁六伟"
    return name

def main():
    a = argparse.ArgumentParser(description="视频中心发布队列"); s = a.add_subparsers(dest="cmd", required=True)
    l = s.add_parser("list"); l.add_argument("--status", default="pending")
    for n in ("show", "dryrun", "running", "delete", "retry"): s.add_parser(n).add_argument("id")
    r = s.add_parser("run"); r.add_argument("id"); r.add_argument("--approved", action="store_true")
    d = s.add_parser("done"); d.add_argument("id"); d.add_argument("--url", default=""); d.add_argument("--record", default="")
    ac = s.add_parser("account"); ac.add_argument("id"); ac.add_argument("name")
    s.add_parser("accounts")
    f = s.add_parser("failed"); f.add_argument("id"); f.add_argument("--error", default="")
    o = a.parse_args()
    if o.cmd == "list":
        js = [j for j in P.load() if o.status == "all" or j["status"] == o.status]
        for j in js: print(f'{j["id"]}  [{j["status"]}]  {_plat_label(j)}  {j["title"][:24]!r}  {j["video_path"]}')
        print(f"共 {len(js)} 条", file=sys.stderr); return
    if o.cmd == "accounts":
        for n, a in P.CHANNEL_ACCOUNTS.items():
            st = P.channel_account_status(n); print(f'{n}\t端口 {a["port"]}\t{a["profile"]}\t{"登录正常" if st["ok"] else st["reason"]}')
        for pl in P.platforms():
            if pl["id"] == "xhs":
                print(f'小红书·袁六伟\tMCP 18060\t{P.XHS_COOKIES}\t{"探测正常" if pl["ok"] else pl["reason"]}')
        return
    j = P.get(o.id)
    if not j: sys.exit("找不到发布任务 " + o.id)
    if o.cmd == "show":
        j = P.ensure_required_topic(dict(j)); _note_desc_trunc(j)
        print(json.dumps(j, ensure_ascii=False, indent=2)); e = P.validate(j)
        print("\n校验：", "通过" if not e else "；".join(e))
        for real in (False, True):
            cwd, argv = P.command(j, real); print(("演练命令：" if not real else "正式命令（需批准）："), f"cd {cwd} && " + " ".join(argv))
    elif o.cmd == "dryrun":
        j = P.ensure_required_topic(dict(j)); _note_desc_trunc(j)
        if j.get("desc_truncated"):
            P.update(j["id"], desc=j["desc"], desc_original=j.get("desc_original"), desc_truncated=True)
        e = P.validate(j)
        if e: sys.exit("校验失败：" + "；".join(e))
        code, out, log = run_cmd(j, False); tail = out.strip().splitlines()[-5:]
        fails = [x.split(" FAIL")[0].strip() for x in out.splitlines() if " FAIL" in x]
        if code == 10 or any("NEED_SCAN" in x for x in out.splitlines()):
            fails = fails or ["NEED_SCAN"]
        summ = ("有字段失败：" + "、".join(dict.fromkeys(fails))) if fails else (tail[-1] if tail else "")
        print("\n".join(tail)); print("演练结论：", summ or "OK")
        P.update(j["id"], last_dryrun={"at": P.now(), "code": code, "log": log, "fails": fails, "tail": summ})
        sys.exit(2 if fails else code)
    elif o.cmd == "run":
        if not o.approved: sys.exit("真实发布需加 --approved（确认六伟已批准此条）")
        pr = P.pause_reason()
        if pr: print("PAUSED", pr, file=sys.stderr); sys.exit(3)   # 任务保持 pending，不标失败
        n = P.today_count(j["platform"]); lim = P.DAILY_LIMIT.get(j["platform"], 10)
        if n >= lim: sys.exit(f"今日{P.PLATFORM_NAMES[j['platform']]}已发 {n} 条，达到上限 {lim}，明天再发")
        j = P.ensure_required_topic(dict(j)); _note_desc_trunc(j)
        if j.get("desc_truncated"):
            P.update(j["id"], desc=j["desc"], desc_original=j.get("desc_original"), desc_truncated=True)
        e = P.validate(j)
        if e: sys.exit("校验失败：" + "；".join(e))
        if not P.claim(j["id"]): sys.exit("任务已被处理或正在发布，未重复执行")
        try:
            code, out, log = run_cmd(j, True)
        except Exception as e:
            P.update(j["id"], status="failed", needs_verification=True, error="发布结果未确认，请先检查平台：" + str(e)[:180], finished_at=P.now())
            sys.exit("发布结果未确认")
        lines = out.strip().splitlines(); last = lines[-1] if lines else ""
        if j["platform"] == "douyin":
            m = [x for x in lines if x.startswith("发布结果")]; ok = code == 0 and bool(m) and " True " in m[-1] + " "
            url = m[-1].split()[-1] if m else ""; rec = str(P.DOUYIN / "发布记录.csv")
        elif j["platform"] == "xhs":
            pub = [x for x in lines if x.startswith("PUBLISHED")]
            ok = code == 0 and bool(pub)
            url = pub[-1].split(None, 1)[1].strip() if pub and len(pub[-1].split(None, 1)) > 1 else ""
            rec = str(P.ROOT / "docs/xhs.md") if ok else ""
            if code == 10 or "NEED_SCAN" in out:
                ok = False; last = next((x for x in lines if "NEED_SCAN" in x), last)
        else:
            ok = code == 0 and last == "PUBLISHED"; url = ""; rec = str(P.CHANNELS / "README-发布流程.md") if ok else ""
        if ok:
            P.update(j["id"], status="done", result_url=url, record_path=rec, log_path=log, finished_at=P.now())
            P.mark_published(j["video_path"], j["platform"], url); P.writeback_work(j, url, rec); print("DONE", url)
        else:
            uncertain = "already in list" in last or code not in (10, 11) and ("after click url:" in out or not last)
            hint = "请先在平台核对，避免重复发布：" if uncertain else ""
            P.update(j["id"], status="failed", needs_verification=uncertain, error=hint + last[:200], log_path=log, finished_at=P.now()); sys.exit("FAILED " + last)
    elif o.cmd == "account":
        if j["platform"] != "channels": sys.exit("只有视频号任务有账号")
        if j["status"] in ("running", "done"): sys.exit("任务已在发布或已完成，不能改账号")
        n = o.name
        if n == "auto":
            line = ""
            try:
                import sqlite3; c = sqlite3.connect(P.DB); r = c.execute("select line from works where id=?", (j.get("work_id") or "",)).fetchone(); c.close(); line = r[0] if r else ""
            except Exception: pass
            n = P.auto_account(line, j.get("title"), j.get("short_title"), j.get("desc"), j.get("topics", []))
        if n not in P.CHANNEL_ACCOUNTS: sys.exit("账号只能是：" + "/".join(P.CHANNEL_ACCOUNTS) + " 或 auto")
        P.update(j["id"], account=n); print("视频号账号 →", n, f'（端口 {P.CHANNEL_ACCOUNTS[n]["port"]}）')
    elif o.cmd == "running": print(json.dumps(P.update(j["id"], status="running", started_at=P.now()), ensure_ascii=False, indent=2))
    elif o.cmd == "done":
        j = P.update(j["id"], status="done", result_url=o.url, record_path=o.record, finished_at=P.now())
        P.mark_published(j["video_path"], j["platform"], o.url); P.writeback_work(j, o.url, o.record); print(json.dumps(j, ensure_ascii=False, indent=2)); print("已在 meta.db 标为「已发布」")
    elif o.cmd == "retry":
        if j["status"] != "failed": sys.exit("只有失败的发布任务能重试")
        print(json.dumps(P.update(j["id"], status="pending", error="", retry_count=j.get("retry_count", 0) + 1), ensure_ascii=False, indent=2))
    elif o.cmd == "failed": print(json.dumps(P.update(j["id"], status="failed", error=o.error, finished_at=P.now()), ensure_ascii=False, indent=2))
    elif o.cmd == "delete": sys.exit(0 if P.delete(j["id"]) else 1)

if __name__ == "__main__": main()
