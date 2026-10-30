# 登录保活（抖音 / 小红书 / 视频号）

目标：尽量少扫码。保活只检查登录、必要时落盘二维码；**绝不自动弹扫码窗 / open 图片**。不发片。

## 间隔

| 平台 | LaunchAgent | 间隔 |
|------|-------------|------|
| 视频号×3 | `com.huixin.channels-keepalive`（袁六伟）、`-huixin`、`-shanhe` | **1 天（86400s）** |
| 抖音 | `com.huixin.douyin-keepalive` | **60 分钟** |
| 小红书 | `com.huixin.xhs-keepalive` | **60 分钟** |

## 视频号（无头 CDP 9333/9334/9335）

- 目录：`~/GrokBridge/视频号/`；脚本 `keepalive.py` + `chlib.py`
- profile 目录名与号对调：山河来电→`汇芯袁总/chrome-profile`，汇芯袁总→`山河来电/chrome-profile`（勿改）
- 掉线：拉登录页，写 **`账号目录/qr_hires.png`**（同份 `qr_latest.png`，最短边≥400px），日志 `NEED_SCAN`
- 日志：袁六伟→`keepalive.log`；另两号→各自目录 `keepalive.log`
- 扫码：用微信扫对应 `qr_hires.png`（Finder 打开即可，保活不会帮你弹）

## 抖音

- profile：`~/lab/douyin-publisher/profile/`（持久化）
- 保活：`keepalive.py`（**headless**，不弹窗）
- 掉线：`~/lab/douyin-publisher/qr_hires.png` + `keepalive.log` 记 `NEED_SCAN`
- 人工重登（会开窗）：`cd ~/lab/douyin-publisher && .venv/bin/python login.py`（仅六伟需要时）

## 小红书

- MCP 常驻：`com.yuanliuwei.xiaohongshu-mcp` → `127.0.0.1:18060`，cookies：`~/.workbuddy/servers/xiaohongshu-mcp/cookies.json`
- 保活：`keepalive_check.sh` → `GET /api/v1/login/status`；掉线只记 `NEED_SCAN`，**不调** `get_login_qrcode`
- 人工重登：`~/.workbuddy/servers/xiaohongshu-mcp/xiaohongshu-login`

## 六伟需要扫码的唯一情形

保活或发布检测到 **NEED_SCAN**（会话过期/被踢）。其它时候不弹码。

## 备份

改动前备份：`~/GrokBridge/视频号/backup_*_keepalive/`
