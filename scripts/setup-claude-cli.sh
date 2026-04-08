#!/bin/bash

# ============================================================
# Claude CLI + GLM-5 一键安装脚本 (CentOS)
# 在 ECS 上运行此脚本来安装和配置 Claude CLI
# 用法: ./scripts/setup-claude-cli.sh
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_ok() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_info() {
    echo -e "${YELLOW}[INFO]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

echo "========== Claude CLI + GLM-5 安装脚本 =========="
echo ""

# 1. 检查 CentOS 版本
echo "[1/6] 检查系统..."
if ! command -v yum &> /dev/null; then
    log_error "此脚本仅支持 CentOS/RHEL (yum)"
    exit 1
fi
log_ok "检测到 CentOS/RHEL 系统"

# 2. 安装 Node.js
echo ""
echo "[2/6] 安装 Node.js..."

if command -v node &> /dev/null; then
    NODE_VERSION=$(node --version)
    log_ok "Node.js 已安装: $NODE_VERSION"
else
    log_info "安装 Node.js 20 LTS..."
    curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash -
    sudo yum install -y nodejs
    log_ok "Node.js 安装成功"
fi

# 3. 安装 Claude CLI
echo ""
echo "[3/6] 安装 Claude CLI..."

if sudo npm list -g @anthropic-ai/claude-cli &> /dev/null; then
    log_ok "Claude CLI 已安装"
else
    log_info "从 npm 安装 Claude CLI..."
    sudo npm install -g @anthropic-ai/claude-cli
    log_ok "Claude CLI 安装成功"
fi

# 4. 创建配置目录
echo ""
echo "[4/6] 创建配置目录..."

mkdir -p ~/.claude
chmod 700 ~/.claude
log_ok "配置目录: ~/.claude"

# 5. 创建基础配置
echo ""
echo "[5/6] 创建配置文件..."

# 主配置
cat > ~/.claude/config.json << 'EOF'
{
  "default_model": "glm-5",
  "providers": {
    "anthropic": {
      "enabled": true,
      "api_key_env": "ANTHROPIC_API_KEY"
    },
    "glm-5": {
      "enabled": true,
      "api_key_env": "GLM_API_KEY",
      "api_endpoint": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
      "model": "glm-5"
    }
  },
  "active_provider": "glm-5"
}
EOF

# 设置配置
cat > ~/.claude/settings.json << 'EOF'
{
  "editor": "vim",
  "theme": "dark",
  "timeout": 300,
  "log_level": "info"
}
EOF

log_ok "配置文件已创建"

# 6. 提示配置 API Key
echo ""
echo "[6/6] 配置 API Key..."
echo ""

# 检查是否已设置
if [ -z "$GLM_API_KEY" ]; then
    log_info "需要配置 GLM_API_KEY"
    echo ""
    echo "请按照以下步骤配置:"
    echo ""
    echo "1. 访问智谱 AI 官网: https://open.bigmodel.cn/"
    echo "2. 登录或注册账户"
    echo "3. 获取 API Key"
    echo "4. 执行以下命令设置环境变量:"
    echo ""
    echo "   export GLM_API_KEY='your-api-key'"
    echo "   echo 'export GLM_API_KEY=\"your-api-key\"' >> ~/.bashrc"
    echo ""
else
    log_ok "已检测到 GLM_API_KEY: ${GLM_API_KEY:0:10}..."
fi

echo ""
echo "========== 安装完成 =========="
echo ""

# 验证安装
echo "验证安装..."
if command -v claude &> /dev/null; then
    CLAUDE_VERSION=$(claude --version 2>/dev/null || echo "unknown")
    log_ok "Claude CLI 已准备好！版本: $CLAUDE_VERSION"
else
    log_error "Claude CLI 未找到，请检查安装"
    exit 1
fi

echo ""
echo "后续步骤:"
echo ""
echo "1. 设置 GLM_API_KEY:"
echo "   export GLM_API_KEY='your-api-key'"
echo ""
echo "2. 测试 Claude CLI:"
echo "   claude 'Hello, 你好吗?'"
echo ""
echo "3. 交互模式:"
echo "   claude --interactive"
echo ""
echo "4. 查看配置:"
echo "   cat ~/.claude/config.json"
echo ""
echo "更多信息请参考:"
echo "   docs/CLAUDE_CLI_SETUP.md"
echo ""
