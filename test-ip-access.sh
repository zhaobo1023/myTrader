#!/bin/bash
# IP 访问测试脚本

echo "========================================="
echo "  myTrader IP 访问测试"
echo "========================================="
echo ""

# 获取服务器 IP
SERVER_IP=$(hostname -I | awk '{print $1}')
echo "检测到服务器 IP: $SERVER_IP"
echo ""

# 测试后端 API
echo "1. 测试后端 API (端口 8000)..."
API_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://$SERVER_IP:8000/health)
if [ "$API_HEALTH" = "200" ]; then
    echo "   [OK] 后端 API 运行正常"
    curl -s http://$SERVER_IP:8000/health | python3 -m json.tool
else
    echo "   [FAIL] 后端 API 无法访问 (HTTP $API_HEALTH)"
    echo "   请检查: docker compose ps"
fi
echo ""

# 测试前端
echo "2. 测试前端 (端口 3000)..."
FRONTEND_CHECK=$(curl -s -o /dev/null -w "%{http_code}" http://$SERVER_IP:3000)
if [ "$FRONTEND_CHECK" = "200" ]; then
    echo "   [OK] 前端服务运行正常"
else
    echo "   [FAIL] 前端服务无法访问 (HTTP $FRONTEND_CHECK)"
    echo "   请检查: cd web && npm run dev"
fi
echo ""

# 检查端口监听
echo "3. 检查端口监听状态..."
if netstat -tuln | grep -q ":8000"; then
    echo "   [OK] 端口 8000 已监听（后端）"
else
    echo "   [WARN] 端口 8000 未监听"
fi

if netstat -tuln | grep -q ":3000"; then
    echo "   [OK] 端口 3000 已监听（前端）"
else
    echo "   [WARN] 端口 3000 未监听"
fi
echo ""

# Docker 容器状态
echo "4. Docker 容器状态..."
docker compose ps
echo ""

# 访问地址汇总
echo "========================================="
echo "  访问地址"
echo "========================================="
echo "前端: http://$SERVER_IP:3000"
echo "后端: http://$SERVER_IP:8000"
echo "API 文档: http://$SERVER_IP:8000/docs"
echo "健康检查: http://$SERVER_IP:8000/health"
echo "========================================="
