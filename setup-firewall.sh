#!/bin/bash
# 防火墙配置脚本

echo "========================================="
echo "  myTrader 防火墙配置"
echo "========================================="
echo ""

# 检测防火墙类型
if command -v ufw &> /dev/null; then
    FIREWALL="ufw"
elif command -v firewall-cmd &> /dev/null; then
    FIREWALL="firewalld"
else
    echo "未检测到常见防火墙 (ufw/firewalld)"
    echo "请手动配置云服务商安全组:"
    echo ""
    echo "阿里云/腾讯云控制台 -> 安全组 -> 添加规则:"
    echo "  - 端口: 3000, 协议: TCP"
    echo "  - 端口: 8000, 协议: TCP"
    exit 1
fi

echo "检测到防火墙: $FIREWALL"
echo ""

if [ "$FIREWALL" = "ufw" ]; then
    echo "配置 UFW 防火墙..."
    sudo ufw allow 3000/tcp comment "myTrader frontend"
    sudo ufw allow 8000/tcp comment "myTrader backend API"
    sudo ufw status
elif [ "$FIREWALL" = "firewalld" ]; then
    echo "配置 firewalld 防火墙..."
    sudo firewall-cmd --permanent --add-port=3000/tcp
    sudo firewall-cmd --permanent --add-port=8000/tcp
    sudo firewall-cmd --reload
    sudo firewall-cmd --list-ports
fi

echo ""
echo "========================================="
echo "  云服务商安全组配置"
echo "========================================="
echo "除了服务器本地防火墙，还需在云控制台配置:"
echo ""
echo "阿里云:"
echo "  ECS 实例 -> 安全组 -> 配置规则 -> 入方向"
echo "  - 授权策略: 允许"
echo "  - 端口范围: 3000/3000, 8000/8000"
echo "  - 授权对象: 0.0.0.0/0"
echo ""
echo "腾讯云:"
echo "  云服务器 -> 安全组 -> 入站规则"
echo "  - 类型: 自定义"
echo "  - 来源: 0.0.0.0/0"
echo "  - 协议端口: TCP:3000, TCP:8000"
echo "========================================="
