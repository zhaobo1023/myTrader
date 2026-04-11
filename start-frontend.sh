#!/bin/bash
# 前端启动脚本 - 开发模式

cd "$(dirname "$0")/web"

# 检查 node_modules 是否存在
if [ ! -d "node_modules" ]; then
    echo "安装前端依赖..."
    npm install
fi

# 替换环境变量中的 IP
YOUR_IP=$(hostname -I | awk '{print $1}')
echo "检测到服务器 IP: $YOUR_IP"
sed -i "s/your-ip/$YOUR_IP/g" .env.local

# 启动开发服务器（绑定到 0.0.0.0，外部可访问）
echo "启动 Next.js 开发服务器..."
npm run dev
