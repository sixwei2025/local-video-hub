#!/usr/bin/env python3
"""每个作品只留最新版本（硬规则，逻辑在 dedup_core.py）。dedupe.py --dry 只列清单；--apply 执行。清单写 data/去重清单-<时间>.csv"""
import csv, json, os, sys
os.environ["DEDUP_NO_AUTO"] = "1"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app, dedup_core
from datetime import datetime
app.scan(); hide, files, keep = dedup_core.plan(app)
out = app.ROOT / f"data/去重清单-{datetime.now():%Y%m%d-%H%M%S}.csv"
ok, bad = dedup_core.apply(app, hide, files, "去重(dedupe.py)") if "--apply" in sys.argv else ([], [])
with open(out, "w", newline="", encoding="utf-8-sig") as fh:
    c = csv.writer(fh); c.writerow(["保留作品", "落选作品", "文件", "处理", "原因"])
    for k, w in hide: c.writerow([f'{k["work_id"]} {k["work_title"]}', f'{w["work_id"]} {w["work_title"]}', "", "删卡片记录", "同一选题"])
    for k, w, p, r in files: c.writerow([k["work_id"], w["work_id"], p, "移到废纸篓", r])
    for w, p, r in keep: c.writerow(["", w["work_id"], p, "文件保留", r])
print(json.dumps({"mode": "apply" if "--apply" in sys.argv else "dry", "cards": len(hide),
  "hide": [f'{w["line"]} {w["work_title"]} → 留 {k["work_id"]}' for k, w in hide],
  "files": [p for *_, p, _ in files], "bytes": sum(os.path.getsize(p) for *_, p, _ in files if os.path.exists(p)) if not ok else None,
  "trashed": len(ok), "failed": bad, "csv": str(out)}, ensure_ascii=False, indent=1))
