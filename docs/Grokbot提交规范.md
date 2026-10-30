# Grokbot 提交规范（汇芯视频中心 · Phase 2）

> 原则：**出片只走固定入口 `hub.py`**，不靠提示词约定。每个命令 stdout 只输出一行 JSON，看 `ok` 和进程退出码判断成败；中文提示在 stderr。
> 命令都在 Mac 上执行：`cd ~/video-hub && .venv/bin/python hub.py <子命令> ...`（下文简写 `hub`）

## 退出码
| 码 | 含义 | 队列例程该怎么做 |
|---|---|---|
| 0 | 成功 | 继续下一步 |
| 1 | 内部错误（程序异常） | 记日志，`hub fail <work> --reason "内部错误…"`，人工排查 |
| 2 | 参数错误（缺参数/格式不支持） | 修正命令后重试，不要原样重试 |
| 3 | 核对未通过 / 不满足提交条件 | 读 JSON 的 `errors`，**补齐缺的那几项再 submit**（只补缺项即可） |
| 4 | 找不到作品或任务 | 检查 id；不要重建 |
| 5 | 状态不允许（如任务已完成还 start） | 用 `hub job`/`hub show` 看当前状态再决定 |
| 6 | 文件不存在 / ffprobe 读不出视频 | 检查路径、等文件写完再提交 |

## 标准流程（每条任务）
1. **取任务并开工**
   `hub next --claim` → 返回 `{"job":{...},"work_id":"xxxx"}`；`job` 为 null 表示没有待办，结束。
   （或已知任务 id：`hub start <job_id> [--title "暂定标题"]`）
   开工即在网站建作品记录，状态「制作中」，任务标 running。
   任务字段：`prompt / video_type / style_id / style_custom_text / aspect(9:16|16:9|3:4|1:1|空) / voice(clone|tts|none|空) / output_dir / ref_videos / ref_video_urls / ref_images / kind(revise=修改任务) / work_id / revise_text / source_video`。
   用 `hub job <job_id>` 看完整任务；风格渲染方法用 `cli.py show <job_id>`。
2. **报阶段**（可多次，网站实时显示）：`hub stage <work_id> "写稿" | "配音" | "渲染中 60%" | "生成封面"`
3. **成片写到 `output_dir`**（任务里给的，就是该类型在桌面的文件夹）。视频必须在扫描目录内，否则 submit 返回 3。
4. **成套提交**（一次带齐最好）：
   ```
   hub submit <work_id> --video "<output_dir>/成片.mp4" --cover "<output_dir>/封面.jpg" \
     --title "≤30 字标题" --desc "简介占位（发前可覆盖）" --topics "话题1,话题2" [--subs 字幕.srt] [--label v1]
   ```
   - 自动核对：视频存在且能 ffprobe、时长>0.5s、画幅与任务 `aspect` 一致、封面存在、标题非空且≤30字、简介非空（占位即可）、话题≥1、字幕文件存在（若给）。
   - **简介分工**：操盘手/Bot 可交占位 `--desc`（字段预留），**发布官在点发布前统一改写**；不要假定操盘手简介必用。各平台硬顶 **≤30 字**（超长发布前自动截断并打日志）。写法见 [短视频简介≤30字写法](./2026-10-23-短视频简介30字写法.md)。
   - 通过 → 作品进入「待确认」，任务标 done，`result_paths`=[视频, 封面]，退出码 0。
   - 不通过 → 退出码 3，`errors` 列出缺项，作品仍「制作中」，网站显示卡点。**补缺项再 submit 一次**（例如只 `--desc ... --topics ...`）。
5. **失败**：`hub fail <work_id 或 job_id> --reason "一句人话说明卡在哪"` → 任务 failed，网站显示原因和「重试」按钮。
6. **重试**：`hub retry <job_id>` 复制原任务（所有参数保留、沿用原作品）重新排队，返回新 job_id。网站上的「重试/重新生成」按钮效果相同。

## 修改任务（网站「让 Grokbot 修改」）
- 任务 `kind=revise`，带 `work_id`、`revise_text`、`source_video`。
- `hub start <job_id>` 会沿用原作品（重新变为「制作中」）。
- **只改文案**：不要重出视频，直接 `hub submit <work_id> --title ... --desc ... --topics ...`（不带 --video）。
- **要改画面**：出新视频后 `hub submit <work_id> --video 新版.mp4 ...`，自动成为新版本（v2、v3…，标「最新」；「已选定」不自动改，由人确认）。

## 自动发现（兜底）
制作中的作品，若其 `output_dir` 里出现开工之后的新 mp4，网站扫描时会自动挂成该作品的版本（标「自动发现」），阶段显示「等待提交标题/简介/封面/话题」。之后仍需 `hub submit <work_id> --cover ... --title ... --desc ... --topics ...` 才会进入待确认。
注意：同一文件夹同时有多个制作中作品时会挂到第一个，建议每个任务用独立文件名并显式 `--video` 提交。

## 发布简介（≤30 字硬顶）
- 规范：`docs/2026-10-23-短视频简介30字写法.md`（发布官专用；源：`/workspace/obsidian/Grok产出/爆款文案/2026-10-23-短视频简介30字写法.md`）。
- 出片仍可带 `--desc` 占位（发前可覆盖）；正式简介由发布官写。`publish_lib.ensure_desc` / `validate` 对 douyin/channels/xhs 统一 **≤30**，超长自动截断（优先句读切开、去末尾标点），dryrun/正式日志写明原文与改后。

## 其他
- `hub show <work_id>`：作品详情（状态、阶段、核对结果、全部素材版本）
- `hub list [--state making|confirm|ready|published]`：bot 产出的作品
- `hub delete-work <work_id> --yes`：删作品记录（**不删文件**），仅用于测试清理
- 不做：发布。作品进入「待确认」后由六伟在网站确认、准备发布。

## 最小示例
```bash
cd ~/video-hub; H(){ .venv/bin/python hub.py "$@"; }
R=$(H next --claim); W=$(echo "$R" | python3 -c 'import json,sys;print(json.load(sys.stdin)["work_id"] or "")')
[ -z "$W" ] && exit 0
H stage "$W" "渲染中"
# …渲染到 output_dir…
H submit "$W" --video "$OUT/片.mp4" --cover "$OUT/封面.jpg" --title "标题" --desc "简介" --topics "话题A,话题B"
case $? in 0) echo 完成;; 3) echo 补缺项后再交;; *) H fail "$W" --reason "提交失败";; esac
```

## 主动出片（没有任务时）
Bot 自己出的片不需要先 `next/start`，用 `new` 直接建作品（制作中），之后的 stage / submit / check / fail 流程与任务完全相同。
- `hub new --bot <Bot名> --line <产线key> --title "标题" [--style <风格id>]` → 返回 `work_id`、`line`、`video_type`、`output_dir`。
  - `--line` 可填视频类型 key（psych / hotnews / wenzhe / duanju / map3d / koubo / promo / daihuo / collage，按 config.json `type_lines` 自动归到产线），或产线 id（kepu / lab / other …）。未知 key 返回 2。
  - 成片放到返回的 `output_dir`（必须在扫描目录内）。没有任务，所以不做画幅核对。
- `hub submit <work_id> ... --featured`：提交并核对通过后直接打上精选（与网站「精选」同一字段）。核对未通过时不打标。
- `hub feature <work_id>` 打上精选；`hub feature <work_id> --off` 取消精选。
- 状态规则不变：submit 通过后进入「待确认」，由六伟确认后才进「待发布」；Bot 没有改成待发布的命令。

```bash
cd ~/video-hub; H(){ .venv/bin/python hub.py "$@"; }
R=$(H new --bot 口播Bot --line koubo --title "今天的热点口播" --style koubo-news)
W=$(echo "$R" | python3 -c 'import json,sys;print(json.load(sys.stdin)["work_id"])')
OUT=$(echo "$R" | python3 -c 'import json,sys,os;print(os.path.expanduser(json.load(sys.stdin)["output_dir"]))')
H stage "$W" "渲染中"
# …渲染到 $OUT…
H submit "$W" --video "$OUT/片.mp4" --cover "$OUT/封面.jpg" --title "今天的热点口播" --desc "简介" --topics "热点,口播" --featured
case $? in 0) echo 完成，待确认;; 3) echo 补缺项后再交;; *) H fail "$W" --reason "提交失败";; esac
```

## 出品方登记与定向修改（2026-10-22）

- `hub new --bot "机器人实际名称" ...` 会永久登记出品方；不会因阶段更新丢失。
- 原有作品补登记：`hub producer <work_id> --bot "机器人实际名称"`；也可在网站预览的「出品方」处登记。不要仅凭视频类别猜测制作机器人。
- 每个机器人领单须带自己的名称：`hub next --bot "机器人实际名称" --claim`。已知任务则 `hub start <job_id> --bot "机器人实际名称"`。
- 网站修改意见生成 `target_bot`，只能由同名机器人领取。没有出品方的意见标为 `unassigned`，不会让其他机器人误领。登记出品方后，未领取意见自动进入对应队列。
- `received_at / claimed_by` 由实际领单写入。网站“排队”不代表“已送入聊天”或“已接单”。机器人须持续/定时调用领单命令，网站不会自动唤醒 Grok Bot 的聊天。
- 修改任务带 `source_version_id / source_video`，对应用户预览的具体版本，不擅自换成其他版本。

## 制作分工（袁六伟2026-10-22确认）

具体名称与类型映射保存在 bot_registry.json。六个专项操盘手负责心理科普、文哲、人物传记、3D地图、口播、宣传片；短视频部门负责人·实验室负责统筹、实验室和各类杂项视频测试。短视频发布官只负责发布，不参与本制作/修改队列，不修改其发布职责或设置。

老片没有实际制作人记录时，出品方仍显示未登记；但可以按照确认的职责将修改发给该类型负责人，routing_basis=responsibility。不能因此伪称该负责人就是历史出品方。机器人主动出片须通过new --bot登记真实身份；领取任务则带同一名称。空格和常见分隔符会规范化，兼容显示名称差异。

## 硬规则：每个作品只显示最新一版
- 同一选题（标题去版本号后相同或 md5 相同，不分产线）网站只留最新一张卡。`hub.py submit` 核对通过后会自动触发去重，旧版本卡片隐藏、桌面产线文件夹里的旧成片移到废纸篓（已发布/精选/风格样片不动）。
- 出新版请在原作品上 submit 新视频，不要另建作品；成片只放桌面产线文件夹，不要让网站去扫工程目录。
