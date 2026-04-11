#!/bin/bash
# SSH 隧道启动脚本 - 在本地电脑运行
#
# 使用方法:
# 1. 将此脚本保存到本地电脑
# 2. chmod +x local-dev-start.sh
# 3. ./local-dev-start.sh

set -e

SERVER_IP="123.56.3.1"
SERVER_USER="root"
LOCAL_PORT_FRONTEND=3000
LOCAL_PORT_BACKEND=8000

echo "========================================="
echo "  myTrader SSH 隧道启动"
echo "========================================="
echo ""

# 检查 SSH 连接
echo "1. 测试 SSH 连接..."
if ! ssh -o ConnectTimeout=5 ${SERVER_USER}@${SERVER_IP} "echo 'SSH 连接成功'" > /dev/null 2>&1; then
    echo "错误: 无法连接到服务器 ${SERVER_USER}@${SERVER_IP}"
    echo "请检查:"
    echo "  - 服务器 IP 是否正确"
    echo "  - SSH 密钥是否配置"
    echo "  - 网络连接是否正常"
    exit 1
fi
echo "   [OK] SSH 连接正常"
echo ""

# 建立后台 SSH 隧道
echo "2. 建立 SSH 隧道..."
# 先检查是否已有隧道在运行
if pgrep -f "ssh.*-L.*${LOCAL_PORT_BACKEND}" > /dev/null; then
    echo "   [WARN] SSH 隧道已存在"
    read -p "   是否关闭现有隧道并重新建立? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        pkill -f "ssh.*-L.*${LOCAL_PORT_BACKEND}"
        sleep 1
    else
        echo "   使用现有隧道"
    fi
fi

# 建立新隧道（后台运行）
ssh -f -N -L ${LOCAL_PORT_FRONTEND}:localhost:${LOCAL_PORT_FRONTEND} \
        -L ${LOCAL_PORT_BACKEND}:localhost:${LOCAL_PORT_BACKEND} \
        ${SERVER_USER}@${SERVER_IP}

if [ $? -eq 0 ]; then
    echo "   [OK] SSH 隧道已建立"
else
    echo "   [FAIL] SSH 隧道建立失败"
    exit 1
fi
echo ""

# 测试后端连接
echo "3. 测试后端连接..."
sleep 2
HEALTH_CHECK=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:${LOCAL_PORT_BACKEND}/health)
if [ "$HEALTH_CHECK" = "200" ]; then
    echo "   [OK] 后端服务连接正常"
else
    echo "   [WARN] 后端服务响应异常 (HTTP $HEALTH_CHECK)"
fi
echo ""

# 显示访问地址
echo "========================================="
echo "  访问地址"
echo "========================================="
echo "前端: http://localhost:${LOCAL_PORT_FRONTEND}"
echo "后端: http://localhost:${LOCAL_PORT_BACKEND}"
echo "API 文档: http://localhost:${LOCAL_PORT_BACKEND}/docs"
echo "健康检查: http://localhost:${LOCAL_PORT_BACKEND}/health"
echo ""
echo "启动前端 (在项目目录执行):"
echo "  cd myTrader/web"
echo "  npm run dev"
echo ""
echo "停止 SSH 隧道:"
echo "  ./local-dev-stop.sh"
echo "  或: pkill -f 'ssh.*-L.*${LOCAL_PORT_BACKEND}'"
echo "========================================="
