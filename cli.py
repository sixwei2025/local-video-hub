#!/usr/bin/env python3
"""视频中心任务队列 CLI
用法:
  ./cli.py list [--status pending|running|done|failed|all]
  ./cli.py show <id>
  ./cli.py running <id>
  ./cli.py done <id> --result /path/a.mp4 [--result /path/b.jpg]
  ./cli.py failed <id> [--error 原因]
  ./cli.py delete <id>
"""
import argparse, json, sys
from queue_lib import load_jobs, update_job, delete_job, find_style

def print_refs(j):
    print("\n==== 参考 ====")
    for p in j.get("ref_videos", []): print("参考视频：" + p)
    for u in j.get("ref_video_urls", []): print("参考视频链接：" + u)
    for p in j.get("ref_images", []): print("参考图：" + p)
    if not (j.get("ref_videos") or j.get("ref_video_urls") or j.get("ref_images")): print("无")

def print_style(j):
    sid = j.get("style_id")
    print("\n==== 风格 ====")
    if not sid: print("未指定风格"); return
    t, p, doc = find_style(j.get("video_type", ""), sid)
    print(f"视频类型：{t['name'] if t else j.get('video_type','?')} ({j.get('video_type','')})")
    if sid == "custom":
        print("风格：自定义风格"); print("风格描述：" + (j.get("style_custom_text") or "（空）"))
        for r in j.get("style_ref_videos", []): print("风格参考视频：" + r)
        for r in j.get("style_ref_images", []): print("风格参考图：" + r)
        return
    if not p: print(f"风格 {sid} 在 styles.json 里找不到（可能已改名）"); return
    print(f"风格：{p['name']} ({sid})"); print("说明：" + p["description"])
    print("源项目：" + p.get("source_project", "自定义风格")); print("渲染方法：" + p.get("render_method", "按风格描述和参考材料制作"))
    if j.get("style_recipe"): print("任务配方快照：" + json.dumps(j["style_recipe"], ensure_ascii=False))
    print("自动化程度：" + doc.get("automation_levels", {}).get(p.get("automation", ""), p.get("automation", "")))

def main():
    p = argparse.ArgumentParser(description="视频中心任务队列")
    sp = p.add_subparsers(dest="cmd", required=True)
    l = sp.add_parser("list"); l.add_argument("--status", default="pending"); l.add_argument("--json", action="store_true")
    s = sp.add_parser("show"); s.add_argument("id")
    for st in ("running", "done", "failed"):
        x = sp.add_parser(st); x.add_argument("id")
        x.add_argument("--result", action="append", default=[]); x.add_argument("--error", default="")
    d = sp.add_parser("delete"); d.add_argument("id")
    a = p.parse_args()
    if a.cmd == "list":
        jobs = [j for j in load_jobs() if a.status == "all" or j["status"] == a.status]
        if a.json: print(json.dumps(jobs, ensure_ascii=False, indent=2)); return
        for j in jobs:
            print(f'{j["id"]}  [{j["status"]}]  {j.get("line","")}/{j.get("video_type","")}:{j.get("style_id","")}  {j["created_at"]}  {j["prompt"][:40]!r}  -> {j["output_dir"]}')
        print(f"共 {len(jobs)} 条", file=sys.stderr)
    elif a.cmd == "show":
        j = next((j for j in load_jobs() if j["id"] == a.id), None)
        if not j: sys.exit("找不到任务 " + a.id)
        print(json.dumps(j, ensure_ascii=False, indent=2))
        print_refs(j); print_style(j)
    elif a.cmd == "delete":
        sys.exit(0 if delete_job(a.id) else "找不到任务 " + a.id)
    else:
        j = update_job(a.id, a.cmd, a.result or None, a.error or None)
        if not j: sys.exit("找不到任务 " + a.id)
        print(json.dumps(j, ensure_ascii=False, indent=2))

if __name__ == "__main__": main()
