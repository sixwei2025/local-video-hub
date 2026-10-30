#!/usr/bin/env python3
"""汇芯视频中心 · Grokbot 固定提交入口。详见 docs/Grokbot提交规范.md
退出码：0 成功 | 1 内部错误 | 2 参数错误 | 3 核对未通过/不满足提交条件 | 4 找不到作品或任务 | 5 状态不允许 | 6 文件或 ffprobe 错误
stdout 永远是一行 JSON：{"ok":bool, ...}；人能读的提示写到 stderr。"""
import argparse, json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hub_lib, queue_lib
from hub_lib import HubError

def out(ok, code=0, **kw):
    print(json.dumps({"ok": ok, "code": code, **kw}, ensure_ascii=False)); sys.exit(code)

class P(argparse.ArgumentParser):
    def error(self, m): sys.stderr.write(f"参数错误：{m}\n"); out(False, 2, error=f"参数错误：{m}")

def new_work(bot, line, title, style=None):
    """主动出片：不依赖任务，直接建作品（制作中）。line 可填产线 id（kepu/map3d…）或视频类型 key（psych/hotnews…）。"""
    import hashlib, uuid
    C = hub_lib.cfg(); lines = {l["id"] for l in C["lines"]}; tl = {k: v for k, v in C.get("type_lines", {}).items() if not k.startswith("_")}
    if line in tl: vtype, lid = line, tl[line]
    elif line in lines: vtype, lid = (line if line in C.get("output_dirs", {}) else None), line
    else: raise HubError(2, f"未知产线：{line}（可用：{' / '.join(sorted(lines | set(tl)))}）")
    if not (title or "").strip(): raise HubError(2, "--title 不能为空")
    if not (bot or "").strip(): raise HubError(2, "--bot 不能为空")
    try: bot=hub_lib.bot_registry.canonical(bot)
    except ValueError as e: raise HubError(2,str(e))
    od = C.get("output_dirs", {}).get(vtype or lid)
    wid = hashlib.sha1(("bot:" + uuid.uuid4().hex).encode()).hexdigest()[:12]; t = hub_lib.now(); c = hub_lib.db()
    c.execute("""insert into works(id,group_key,title,description,topics,state,featured,archived,created_at,updated_at,job_id,stage,origin,line,video_type,style_id,output_dir,check_errors)
                 values(?,?,?,?,?,?,0,0,?,?,?,?,?,?,?,?,?,'[]')""",
              (wid, "sub:" + wid, title.strip(), "", "[]", "making", t, t, None, f"开工（主动出片 · {bot.strip()}）", "bot", lid, vtype, style, od))
    c.execute("update works set producer_bot=? where id=?", (bot.strip(),wid)); c.commit(); c.close(); return wid, lid, vtype, od

def set_featured(wid, on=True):
    c = hub_lib.db(); hub_lib._work(c, wid)
    c.execute("update works set featured=?, updated_at=? where id=?", (int(bool(on)), hub_lib.now(), wid)); c.commit(); c.close()

def main():
    ap = P(prog="hub.py", description="Grokbot 提交入口"); sp = ap.add_subparsers(dest="cmd", parser_class=P)
    s = sp.add_parser("next", help="取最早的一条 pending 任务"); s.add_argument("--claim", action="store_true", help="同时开工（=start）"); s.add_argument("--bot",help="当前机器人实际名称，用于定向领单")
    s = sp.add_parser("start", help="开工：建作品(制作中)并把任务标 running"); s.add_argument("job_id"); s.add_argument("--title"); s.add_argument("--bot")
    s = sp.add_parser("new", help="主动出片：不需要任务，直接建作品(制作中)，返回 work_id")
    s.add_argument("--bot", required=True); s.add_argument("--line", required=True, help="产线 key，如 psych/map3d/koubo/promo/wenzhe/duanju/lab")
    s.add_argument("--title", required=True); s.add_argument("--style")
    s = sp.add_parser("producer",help="登记作品出品机器人");s.add_argument("work_id");s.add_argument("--bot",required=True)
    s = sp.add_parser("feature", help="打上/取消精选"); s.add_argument("work_id"); s.add_argument("--off", action="store_true")
    s = sp.add_parser("stage", help="更新当前阶段"); s.add_argument("work_id"); s.add_argument("text")
    s = sp.add_parser("submit", help="成套交付并自动核对")
    s.add_argument("work_id"); s.add_argument("--video"); s.add_argument("--cover"); s.add_argument("--title"); s.add_argument("--desc")
    s.add_argument("--topics", help="逗号分隔"); s.add_argument("--subs"); s.add_argument("--label")
    s.add_argument("--featured", action="store_true", help="提交时直接打上精选")
    s = sp.add_parser("check", help="重新核对"); s.add_argument("work_id")
    s = sp.add_parser("fail", help="标失败"); s.add_argument("ref", help="work_id 或 job_id"); s.add_argument("--reason", required=True)
    s = sp.add_parser("retry", help="失败/完成的任务复制一条重新排队"); s.add_argument("job_id")
    s = sp.add_parser("show", help="看作品"); s.add_argument("work_id")
    s = sp.add_parser("job", help="看任务"); s.add_argument("job_id")
    s = sp.add_parser("list", help="列 bot 作品"); s.add_argument("--state", choices=["making", "confirm", "ready", "published"])
    s = sp.add_parser("delete-work", help="删除作品记录；加 --trash 同时把它的视频/封面/字幕移到废纸篓（可恢复）"); s.add_argument("work_id"); s.add_argument("--yes", action="store_true"); s.add_argument("--trash", action="store_true")
    a = ap.parse_args()
    if not a.cmd: ap.print_help(sys.stderr); out(False, 2, error="缺少子命令")
    try:
        if a.cmd == "next":
            j = hub_lib.next_job(a.bot)
            if not j: out(True, 0, job=None, message="没有 pending 任务")
            wid = hub_lib.start(j["id"],bot=a.bot) if a.claim else None
            out(True, 0, job=queue_lib.load_jobs and next(x for x in queue_lib.load_jobs() if x["id"] == j["id"]), work_id=wid)
        if a.cmd == "start":
            wid = hub_lib.start(a.job_id, a.title, bot=a.bot); sys.stderr.write(f"已开工，作品 {wid}（制作中）\n"); out(True, 0, work_id=wid, job_id=a.job_id)
        if a.cmd == "new":
            wid, lid, vt, od = new_work(a.bot, a.line, a.title, a.style); sys.stderr.write(f"已建作品 {wid}（制作中），产线 {lid}；成片请放到 {od}\n")
            out(True, 0, work_id=wid, line=lid, video_type=vt, output_dir=od, state="making")
        if a.cmd == "producer": out(True,0,work_id=a.work_id,producer_bot=hub_lib.set_producer(a.work_id,a.bot))
        if a.cmd == "feature":
            set_featured(a.work_id, not a.off); hub_lib.ping_rescan(); out(True, 0, work_id=a.work_id, featured=not a.off)
        if a.cmd == "stage": hub_lib.stage(a.work_id, a.text); out(True, 0, work_id=a.work_id, stage=a.text)
        if a.cmd == "submit":
            if not any([a.video, a.cover, a.title, a.desc, a.topics, a.subs]): raise HubError(2, "submit 至少要带一项：--video/--cover/--title/--desc/--topics/--subs")
            lab = hub_lib.submit(a.work_id, a.video, a.cover, a.title, a.desc, a.topics.replace("，", ",").split(",") if a.topics is not None else None, a.subs, a.label)
            if a.featured: set_featured(a.work_id, True); hub_lib.ping_rescan()
            # 硬规则：核对通过后，同一选题旧版本自动去重（例外：已发布/精选/风格样片）。服务在线走 rescan 钩子，离线就地跑自检清理
            if not hub_lib.ping_rescan():
                import subprocess; subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "data/dup_audit.py"), "--fix"], capture_output=True, timeout=600)
            sys.stderr.write("提交成功，核对通过，作品已进入「待确认」\n"); out(True, 0, work_id=a.work_id, version=lab, state="confirm", featured=bool(a.featured))
        if a.cmd == "check":
            e = hub_lib.check(a.work_id)
            if e: raise HubError(3, "核对未通过", e)
            out(True, 0, work_id=a.work_id, errors=[])
        if a.cmd == "fail": wid = hub_lib.fail(a.ref, a.reason); out(True, 0, work_id=wid, reason=a.reason)
        if a.cmd == "retry": j = hub_lib.retry(a.job_id); out(True, 0, job_id=j["id"], retry_of=a.job_id)
        if a.cmd == "show": c = hub_lib.db(); w = hub_lib.work_view(c, a.work_id); c.close(); out(True, 0, work=w)
        if a.cmd == "job": out(True, 0, job=hub_lib._job(a.job_id))
        if a.cmd == "list":
            c = hub_lib.db(); q = "select id,title,state,stage,job_id,updated_at from works where origin='bot'" + (" and state=?" if a.state else "") + " order by updated_at desc"
            rows = [dict(r) for r in c.execute(q, (a.state,) if a.state else ())]; c.close(); out(True, 0, works=rows)
        if a.cmd == "delete-work":
            if not a.yes: raise HubError(2, "删除需要加 --yes（只删记录，不删文件）")
            trashed = []
            if a.trash:
                c = hub_lib.db(); w = hub_lib.work_view(c, a.work_id); c.close()
                files = list(dict.fromkeys(x["path"] for x in w["assets"] if x["kind"] in ("video", "cover", "subtitle") and x.get("path") and os.path.exists(x["path"])))
                trashed, bad = hub_lib.trash(files)
                hub_lib.log_delete([[hub_lib.now(), a.work_id, w.get("title") or "", "整个作品(CLI)", f, "已移到废纸篓", "否"] for f in trashed] + [[hub_lib.now(), a.work_id, w.get("title") or "", "整个作品(CLI)", f, "失败：" + r, "否"] for f, r in bad])
                hub_lib.forget_paths(trashed)
                if bad: raise HubError(6, "部分文件没移到废纸篓", [f"{p}：{r}" for p, r in bad])
            hub_lib.delete_work(a.work_id); hub_lib.ping_rescan(); out(True, 0, deleted=a.work_id, trashed=trashed)
    except HubError as e:
        sys.stderr.write(e.msg + ("".join("\n  - " + d for d in e.detail)) + "\n"); out(False, e.code, error=e.msg, errors=e.detail)
    except SystemExit: raise
    except Exception as e:
        sys.stderr.write(f"内部错误：{e!r}\n"); out(False, 1, error=f"内部错误：{e}")

if __name__ == "__main__": main()
