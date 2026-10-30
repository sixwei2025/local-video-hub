# 本地视频中心（Local Video Hub）

> 🔴 **作者：袁六伟 · 台州汇芯**｜一人 AI 公司创业者，6000+ 学员，100+ 客户，得到/华为分享老师
> 📮 更多 AI 视频与自动化实战，关注 **公众号 / 视频号：袁六伟**

**它不只是视频管理工具——它是把所有 AI 员工连在一起的通道。**

本地视频中心 = **视频版的本地 Obsidian**：一个跑在你本机的知识/作战面。Grok Bot、Codex、Claude、WorkBuddy……每个 AI 员工做完片，都把成片、封面、状态、风格交到这里。合伙人克隆同一套之后，自家 AI 员工共用一个视频中央云台——也是本地最强的视频知识库。

**English**: A local FastAPI + static UI video hub (127.0.0.1:8765). AI staff submit finished videos via `hub.py`. Think Obsidian-for-video: one local ops surface where every agent deposits cuts, covers, status and styles.

| 作品库 | 作品管理 | 客户展示 |
|---|---|---|
| <img src="assets/showcase/library.png" width="280" alt="作品库"> | <img src="assets/showcase/home.png" width="280" alt="首页"> | <img src="assets/showcase/client-showcase.png" width="280" alt="展示页"> |

## 它解决什么

| 没有它 | 有它 |
|---|---|
| 成片散落在桌面各产线文件夹，人肉翻找 | 统一作品卡：状态、封面、风格、出品 bot |
| 每个 AI 员工各交各的，对不上 | 固定入口 `hub.py`，stdout 一行 JSON，机器可读 |
| 发布前靠聊天对口令 | 制作中 → 待确认 → 待发布 → 已发布，流水线可查 |
| 合伙人难复制整套作战面 | `git clone` + `./start.sh`，改 `config.json` 产线即可 |

## 快速开始

依赖：**Python 3.11+**、**ffmpeg**（含 ffprobe）。可选：Playwright（`tools/resolve_ref.py` 拉参考片）。

```bash
git clone https://github.com/sixwei2025/local-video-hub.git
cd local-video-hub
# 首次会自动建 .venv 并 pip install；也可手动：
# python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp config.example.json config.json   # 已自带一份 starter，按需改产线路径
./start.sh
# 打开 http://127.0.0.1:8765
```

停止：`kill $(cat data/server.pid)`。

### 改成你的产线

编辑 `config.json`：

- `scan_roots` / `output_dirs`：桌面上的成片目录（`~/Desktop/产线A-…` 占位，换成你的）
- `lines` / `rules` / `style_rules`：产线颜色与路径匹配
- `bot_registry.json`：AI 员工名单（可作示例，按团队改）
- `styles.json`：风格库（可与各视频 skill 对齐）

只扫白名单桌面产线；工程目录、`.venv`、`node_modules` 默认排除。

## AI 员工怎么交片（hub.py）

原则：**出片只走固定入口**，不靠提示词约定。每条命令 stdout 一行 JSON（看 `ok` + 退出码）；中文提示在 stderr。

```bash
cd ~/local-video-hub   # 或你的安装目录
.venv/bin/python hub.py new --bot "短视频操盘手1·心理科普" --line psych --title "选题标题"
.venv/bin/python hub.py stage <work_id> "渲染中"
.venv/bin/python hub.py submit <work_id> \
  --video ~/Desktop/产线A-心理科普/成片.mp4 \
  --cover ~/Desktop/产线A-心理科普/封面.jpg \
  --title "发布标题" --desc "简介" --topics "心理学,科普"
.venv/bin/python hub.py show <work_id>
```

常用子命令：`next` / `start` / `new` / `stage` / `submit` / `check` / `fail` / `list` / `feature`。详见 [`docs/Grokbot提交规范.md`](docs/Grokbot提交规范.md)、[`docs/成片自动入库.md`](docs/成片自动入库.md)。机器人接单说明在 [`docs/机器人接单/`](docs/机器人接单/)。

## 目录一览

```
app.py              FastAPI 主服务 + 扫描/作品 API
hub.py / hub_lib.py AI 员工提交入口
queue_lib.py        任务队列
cli.py / pub.py     队列 CLI / 发布 CLI
publish_*.py        发布队列与平台适配（需本机已登录的发布器，按环境改路径）
dedup_*.py          同选题去重门闸
bot_registry.*      AI 员工登记
styles.json         风格库
config.example.json 示例配置（复制为 config.json）
static/             工作台 + /showcase 客户展示页
docs/               设计规范与接单说明
tests/              基础流程测试
tools/              桌面成片补扫、封面工具等
```

设计硬规则见 [`docs/设计规范.md`](docs/设计规范.md)（电影幕布、品牌红、删=移废纸篓等）。

## 安全与边界

- 默认只绑 **127.0.0.1:8765**，不对外网开端口。
- 仓库不含个人数据库、发布日志、成片媒体、`.venv`。
- `data/meta.db`、`queue/*`、缓存与日志均在 `.gitignore`；本地跑起来后会自动生成。
- 发布到抖音/视频号/小红书依赖你本机已有的发布器与登录态；开源包只带适配层，请按自己的路径改 `publish_lib.py`。

## License

MIT © 2026 台州汇芯

---

合伙人用法：克隆 → 改产线配置 → 让每个 AI 员工把成片交到同一个本地中心。这就是视频版本地 Obsidian。
