#!/bin/bash
# myTrader 服务停止脚本

echo "停止 myTrader 服务..."

docker stop mytrader-api mytrader-web mytrader-nginx-new 2>/dev/null || true
docker rm mytrader-api mytrader-web mytrader-nginx-new 2>/dev/null || true

echo "✓ 所有服务已停止"
