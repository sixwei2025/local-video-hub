#!/bin/bash
# 启动本地视频中心：仅监听 127.0.0.1:8765
set -e
cd "$(dirname "$0")"
mkdir -p data queue cache
if [[ ! -f config.json ]]; then
  cp config.example.json config.json
  echo "已从 config.example.json 生成 config.json，请按桌面产线改 scan_roots / output_dirs"
fi
if [[ ! -x .venv/bin/uvicorn ]]; then
  echo "首次运行：创建虚拟环境并安装依赖…"
  python3 -m venv .venv
  .venv/bin/pip install -U pip
  .venv/bin/pip install -r requirements.txt
fi
if lsof -iTCP:8765 -sTCP:LISTEN -n >/dev/null 2>&1; then
  echo "已在运行：http://127.0.0.1:8765"
  exit 0
fi
nohup .venv/bin/uvicorn app:app --host 127.0.0.1 --port 8765 > data/server.log 2>&1 &
echo $! > data/server.pid
sleep 2
echo "已启动：http://127.0.0.1:8765 （日志 data/server.log，停止：kill \$(cat data/server.pid)）"
