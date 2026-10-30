# 小红书发布（video-hub）

统一由**短视频发布官**发。账号：袁六伟（本机 `xiaohongshu-mcp` cookies）。

## 加任务
```bash
cd ~/video-hub
.venv/bin/python -c "
import publish_lib as P
j=P.add({
  'platform':'xhs',
  'video_path':'/绝对路径/成片.mp4',
  'title':'标题最多二十个字以内啊',  # ≤20 字
  'desc':'正文简介',
  'topics':['心理学','科普'],       # 会自动把 vibe知识大赏 置首
})
print(j['id'])
"
```
或在网站发布表单勾选「小红书」。

## 演练（不发）
```bash
.venv/bin/python pub.py dryrun <pub-id>
```
只做：字段校验 + `check_login_status`。  
**不会**调用 `publish_with_video`，**不会**弹登录二维码。

## 真发（需六伟逐条批准）
```bash
.venv/bin/python pub.py run <pub-id> --approved
```
若 `~/GrokBridge/locks/publish.lock` 仍是 `owner=六伟要求暂停`，会打印 `PAUSED`（退出码 3），任务保持 pending。

## 登录失效（NEED_SCAN）
1. 发布官**不要**自动调 `get_login_qrcode`。
2. 请六伟本人在本机执行：
   `~/.workbuddy/servers/xiaohongshu-mcp/xiaohongshu-login`
   扫码后 cookies 写入同目录 `cookies.json`。
3. 确认服务：`launchctl list | grep xiaohongshu`（端口 `127.0.0.1:18060`）。
4. 再 `pub.py dryrun <id>` 看是否通过。

## 探测
```bash
.venv/bin/python pub.py accounts
.venv/bin/python -c "import publish_lib as P; print(P.platforms())"
```

## 简介字数
各平台（含小红书）简介硬顶 **≤30 字**，超长由 `publish_lib.ensure_desc` 发布前截断并打日志。写法见 [短视频简介≤30字写法](./2026-10-23-短视频简介30字写法.md)。
