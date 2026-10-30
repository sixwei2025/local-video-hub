#!/bin/bash
# 热点新闻统一封面（与口播封面同款）。参数同 hotnews_cover.py，例：
#   hotnews_cover.sh --line1 "4万个账号" --line2 "AI额度被多扣" --kicker "一个周末" --out ov/cover.png
exec ~/GrokBridge/口播/_cover_template/.venv/bin/python "$(dirname "$0")/hotnews_cover.py" "$@"
