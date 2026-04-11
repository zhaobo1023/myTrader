#!/bin/bash
# SSH 隧道停止脚本 - 在本地电脑运行

set -e

LOCAL_PORT_BACKEND=8000

echo "正在停止 SSH 隧道..."

# 查找并杀死 SSH 隧道进程
TUNNEL_PIDS=$(pgrep -f "ssh.*-L.*${LOCAL_PORT_BACKEND}" || true)

if [ -z "$TUNNEL_PIDS" ]; then
    echo "未找到运行中的 SSH 隧道"
else
    echo "发现 SSH 隧道进程: $TUNNEL_PIDS"
    pkill -f "ssh.*-L.*${LOCAL_PORT_BACKEND}"
    sleep 1

    # 验证是否已停止
    if pgrep -f "ssh.*-L.*${LOCAL_PORT_BACKEND}" > /dev/null; then
        echo "警告: 部分进程可能仍在运行"
        pgrep -f "ssh.*-L.*${LOCAL_PORT_BACKEND}"
    else
        echo "SSH 隧道已停止"
    fi
fi
