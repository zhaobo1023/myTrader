#!/bin/bash

# Setup Claude CLI + GLM-5 on CentOS
# Usage: ./scripts/setup-claude-cli.sh

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

echo "========== Claude CLI + GLM-5 Setup =========="
echo ""

# Step 1: Check system
echo "[1/6] Checking system..."
if ! command -v yum &> /dev/null; then
    log_error "This script requires CentOS/RHEL with yum"
    exit 1
fi
log_ok "CentOS/RHEL system detected"

# Step 2: Install Node.js
echo ""
echo "[2/6] Installing Node.js..."

if command -v node &> /dev/null; then
    NODE_VERSION=$(node --version)
    log_ok "Node.js already installed: $NODE_VERSION"
else
    log_info "Installing Node.js 20 LTS..."
    curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash -
    sudo yum install -y nodejs
    log_ok "Node.js installed successfully"
fi

# Step 3: Install Claude CLI
echo ""
echo "[3/6] Installing Claude CLI..."

if sudo npm list -g @anthropic-ai/claude-cli &> /dev/null; then
    log_ok "Claude CLI already installed"
else
    log_info "Installing Claude CLI from npm..."
    sudo npm install -g @anthropic-ai/claude-cli
    log_ok "Claude CLI installed successfully"
fi

# Step 4: Create config directory
echo ""
echo "[4/6] Creating config directory..."

mkdir -p ~/.claude
chmod 700 ~/.claude
log_ok "Config directory: ~/.claude"

# Step 5: Create config files
echo ""
echo "[5/6] Creating configuration files..."

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

# Step 6: API Key configuration
echo ""
echo "[6/6] API Key Configuration..."
echo ""

# Check if GLM_API_KEY is set
if [ -z "$GLM_API_KEY" ]; then
    log_info "GLM_API_KEY not set"
    echo ""
    echo "To configure GLM_API_KEY:"
    echo ""
    echo "1. Visit: https://open.bigmodel.cn/"
    echo "2. Login or register"
    echo "3. Get your API Key"
    echo "4. Run:"
    echo ""
    echo "   export GLM_API_KEY='your-api-key'"
    echo "   echo 'export GLM_API_KEY=\"your-api-key\"' >> ~/.bashrc"
    echo ""
else
    log_ok "GLM_API_KEY detected: ${GLM_API_KEY:0:10}..."
fi

echo ""
echo "========== Setup Complete =========="
echo ""

# Verify installation
echo "Verifying installation..."
if command -v claude &> /dev/null; then
    CLAUDE_VERSION=$(claude --version 2>/dev/null || echo "unknown")
    log_ok "Claude CLI ready! Version: $CLAUDE_VERSION"
else
    log_error "Claude CLI not found. Please check installation"
    exit 1
fi

echo ""
echo "Next steps:"
echo ""
echo "1. Set GLM_API_KEY:"
echo "   export GLM_API_KEY='your-api-key'"
echo ""
echo "2. Test Claude CLI:"
echo "   claude 'Hello, how are you?'"
echo ""
echo "3. Interactive mode:"
echo "   claude --interactive"
echo ""
echo "4. View config:"
echo "   cat ~/.claude/config.json"
echo ""
echo "For more info, see:"
echo "   docs/CLAUDE_CLI_SETUP.md"
echo ""
