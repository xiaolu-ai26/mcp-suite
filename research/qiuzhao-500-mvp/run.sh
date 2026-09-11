#!/bin/zsh
# 采集运行入口：run.sh [-- ARGS]
cd /Users/maxzhl/Projects/mcp-suite/research/qiuzhao-500-mvp
exec /Users/maxzhl/.workbuddy/binaries/python/envs/default/bin/python -m collector.run "$@"
