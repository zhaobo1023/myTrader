# Claude CLI 在 ECS (CentOS) 上的安装和配置

## 1. 安装 Claude CLI

### 1.1 前置条件

Claude CLI 要求：
- Node.js 18+
- npm 或 yarn

### 1.2 安装 Node.js (CentOS)

```bash
# 更新系统
sudo yum update -y

# 安装 Node.js 20 LTS
curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash -
sudo yum install -y nodejs

# 验证
node --version
npm --version
```

### 1.3 安装 Claude CLI

```bash
# 使用 npm 全局安装
sudo npm install -g @anthropic-ai/claude-cli

# 验证安装
claude --version
```

或者从源码编译（如果官方包不可用）：

```bash
git clone https://github.com/anthropics/claude-cli.git
cd claude-cli
npm install
sudo npm install -g .
```

### 1.4 创建 Claude CLI 配置目录

```bash
# 创建配置目录（Claude CLI 会自动使用）
mkdir -p ~/.claude
chmod 700 ~/.claude

# 创建基础配置文件
cat > ~/.claude/config.json << 'EOF'
{
  "default_model": "gpt-4",
  "api_key_provider": "anthropic",
  "log_level": "info"
}
EOF

cat > ~/.claude/settings.json << 'EOF'
{
  "editor": "vim",
  "theme": "dark",
  "timeout": 300
}
EOF
```

---

## 2. 配置 GLM-5 (智谱 AI)

智谱 GLM-5 是国内大模型，可作为 Claude 的替代或补充。

### 2.1 获取 GLM-5 API Key

1. 访问 [智谱 AI 官网](https://open.bigmodel.cn/)
2. 注册账户 → 获取 API Key
3. 保存 API Key（格式如 `xxxx-xxxx-xxxx`）

### 2.2 配置 Claude CLI 使用 GLM-5

创建 GLM-5 配置文件：

```bash
cat > ~/.claude/glm-config.json << 'EOF'
{
  "provider": "glm-5",
  "api_key": "your-glm-api-key-here",
  "api_endpoint": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
  "model": "glm-5",
  "timeout": 300,
  "max_tokens": 4096,
  "temperature": 0.7
}
EOF

# 设置权限（重要！）
chmod 600 ~/.claude/glm-config.json
```

### 2.3 更新主配置文件以支持 GLM-5

编辑 `~/.claude/config.json`：

```bash
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
```

---

## 3. 环境变量配置

### 3.1 设置 API Key 环境变量（安全方式）

```bash
# 将 API Key 添加到 shell 配置文件
echo 'export GLM_API_KEY="your-glm-api-key"' >> ~/.bashrc
echo 'export ANTHROPIC_API_KEY="your-anthropic-key"' >> ~/.bashrc

# 立即生效
source ~/.bashrc

# 验证
echo $GLM_API_KEY
```

或者使用 .env 文件：

```bash
cat > ~/.claude/.env << 'EOF'
GLM_API_KEY=your-glm-api-key
ANTHROPIC_API_KEY=your-anthropic-key
EOF

# 权限设置
chmod 600 ~/.claude/.env
```

### 3.2 创建 systemd 环境文件（用于守护进程）

如果要在 systemd 服务中使用 Claude CLI：

```bash
sudo cat > /etc/environment.d/claude.conf << 'EOF'
GLM_API_KEY=your-glm-api-key
ANTHROPIC_API_KEY=your-anthropic-key
EOF

sudo chmod 600 /etc/environment.d/claude.conf
```

---

## 4. 测试 Claude CLI + GLM-5

### 4.1 基本测试

```bash
# 测试 GLM-5
claude --model glm-5 "你好，请自我介绍"

# 交互模式
claude --model glm-5 --interactive
```

### 4.2 调用 API（编程方式）

创建测试脚本 `test-claude.js`：

```javascript
#!/usr/bin/env node

const axios = require('axios');

const GLM_API_KEY = process.env.GLM_API_KEY;
const GLM_ENDPOINT = 'https://open.bigmodel.cn/api/paas/v4/chat/completions';

async function testGLM() {
  try {
    console.log('[TEST] 调用 GLM-5...');
    
    const response = await axios.post(GLM_ENDPOINT, {
      model: 'glm-5',
      messages: [
        {
          role: 'user',
          content: '你好，请自我介绍'
        }
      ],
      max_tokens: 1024,
      temperature: 0.7
    }, {
      headers: {
        'Authorization': `Bearer ${GLM_API_KEY}`,
        'Content-Type': 'application/json'
      }
    });

    console.log('[SUCCESS] 响应：');
    console.log(response.data.choices[0].message.content);
  } catch (error) {
    console.error('[ERROR]', error.message);
    if (error.response) {
      console.error('Status:', error.response.status);
      console.error('Data:', error.response.data);
    }
  }
}

testGLM();
```

使用：

```bash
npm install axios
chmod +x test-claude.js
./test-claude.js
```

---

## 5. 在项目中集成 Claude CLI

### 5.1 创建 Claude 包装脚本

在项目中创建 `scripts/claude-helper.sh`：

```bash
#!/bin/bash

# Claude CLI 辅助脚本
# 用于在项目中调用 Claude 或 GLM-5

set -e

API_KEY="${GLM_API_KEY:-}"
MODEL="${MODEL:-glm-5}"
TEMPERATURE="${TEMPERATURE:-0.7}"

if [ -z "$API_KEY" ]; then
    echo "[ERROR] GLM_API_KEY not set"
    exit 1
fi

if [ $# -eq 0 ]; then
    # 交互模式
    claude --model "$MODEL" --interactive
else
    # 命令行模式
    claude --model "$MODEL" "$@"
fi
```

使用：

```bash
chmod +x scripts/claude-helper.sh

# 交互模式
./scripts/claude-helper.sh

# 命令模式
./scripts/claude-helper.sh "用Python写一个快速排序"
```

### 5.2 在 Python 项目中调用 Claude

创建 `utils/claude_helper.py`：

```python
import os
import subprocess
import json

class ClaudeHelper:
    def __init__(self, model: str = 'glm-5'):
        self.model = model
        self.api_key = os.getenv('GLM_API_KEY')
        if not self.api_key:
            raise ValueError('GLM_API_KEY not set')
    
    def call(self, prompt: str) -> str:
        """调用 Claude/GLM-5"""
        try:
            result = subprocess.run(
                ['claude', '--model', self.model, prompt],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                raise Exception(f"Claude error: {result.stderr}")
            
            return result.stdout.strip()
        except Exception as e:
            print(f"[ERROR] {e}")
            return None
    
    def call_api(self, messages: list) -> dict:
        """直接调用 GLM API"""
        import requests
        
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            'model': self.model,
            'messages': messages,
            'max_tokens': 4096,
            'temperature': 0.7
        }
        
        response = requests.post(
            'https://open.bigmodel.cn/api/paas/v4/chat/completions',
            json=payload,
            headers=headers,
            timeout=300
        )
        
        response.raise_for_status()
        return response.json()

# 使用示例
if __name__ == '__main__':
    helper = ClaudeHelper()
    
    # 调用 CLI
    response = helper.call('写一个 Hello World 程序')
    print(response)
    
    # 调用 API
    messages = [
        {'role': 'user', 'content': '你好'}
    ]
    api_response = helper.call_api(messages)
    print(api_response)
```

使用：

```bash
export GLM_API_KEY="your-key"
python utils/claude_helper.py
```

---

## 6. 与项目部署集成

### 6.1 在 systemd 服务中使用 Claude

编辑 `scripts/mytrader-api.service`，添加环境变量：

```ini
[Unit]
Description=myTrader API Service
After=network.target

[Service]
Type=notify
User=ubuntu
WorkingDirectory=/opt/myTrader

# 添加这些环境变量
Environment="GLM_API_KEY=your-glm-key"
Environment="ANTHROPIC_API_KEY=your-anthropic-key"
Environment="PATH=/home/ubuntu/.local/bin:/usr/local/bin:/usr/bin"

ExecStart=/home/ubuntu/.local/bin/uvicorn api.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 4

Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 6.2 在 API 中集成 Claude

创建 `api/services/claude_service.py`：

```python
import os
import httpx
from typing import Optional

class ClaudeService:
    def __init__(self):
        self.api_key = os.getenv('GLM_API_KEY')
        self.endpoint = 'https://open.bigmodel.cn/api/paas/v4/chat/completions'
        self.model = 'glm-5'
    
    async def call(self, messages: list, temperature: float = 0.7) -> Optional[str]:
        """调用 GLM-5 API"""
        if not self.api_key:
            raise ValueError('GLM_API_KEY not configured')
        
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            'model': self.model,
            'messages': messages,
            'max_tokens': 4096,
            'temperature': temperature
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.endpoint,
                json=payload,
                headers=headers,
                timeout=300.0
            )
            response.raise_for_status()
            
            result = response.json()
            return result['choices'][0]['message']['content']

# FastAPI 路由示例
from fastapi import APIRouter

router = APIRouter(prefix='/api/claude', tags=['claude'])
claude_service = ClaudeService()

@router.post('/ask')
async def ask_claude(prompt: str):
    """使用 Claude/GLM-5 回答问题"""
    messages = [
        {'role': 'user', 'content': prompt}
    ]
    
    response = await claude_service.call(messages)
    return {'response': response}
```

在主 API 中注册：

```python
# api/main.py
from api.services.claude_service import router as claude_router

app.include_router(claude_router)
```

---

## 7. 安全最佳实践

### 7.1 管理 API Key

**不要**：
- 硬编码在代码中
- 提交到 Git
- 在日志中打印

**应该**：
- 使用环境变量
- 使用 `.env` 文件（git ignore）
- 使用密钥管理工具（如 HashiCorp Vault）

### 7.2 防止 API Key 泄露

```bash
# 确保敏感文件权限正确
chmod 600 ~/.claude/.env
chmod 600 ~/.claude/*.json

# 添加到 .gitignore
echo ".env" >> .gitignore
echo ".claude/" >> .gitignore
echo "**/claude-config.json" >> .gitignore
```

### 7.3 审计和监控

```bash
# 查看 Claude CLI 日志
tail -f ~/.claude/logs/claude.log

# 检查 API 使用情况
curl -H "Authorization: Bearer $GLM_API_KEY" \
  https://open.bigmodel.cn/api/paas/v4/account
```

---

## 8. 故障排查

### 问题 1: 找不到 claude 命令

```bash
# 检查安装
npm list -g @anthropic-ai/claude-cli

# 重新安装
sudo npm install -g @anthropic-ai/claude-cli

# 检查 PATH
echo $PATH

# 手动添加 npm bin 到 PATH
export PATH="$(npm config get prefix)/bin:$PATH"
echo 'export PATH="$(npm config get prefix)/bin:$PATH"' >> ~/.bashrc
```

### 问题 2: API Key 无效

```bash
# 验证 API Key 格式
echo $GLM_API_KEY

# 测试 API 连接
curl -X POST https://open.bigmodel.cn/api/paas/v4/chat/completions \
  -H "Authorization: Bearer $GLM_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "glm-5",
    "messages": [{"role": "user", "content": "test"}],
    "max_tokens": 100
  }'
```

### 问题 3: 连接超时

```bash
# 增加超时时间
claude --timeout 600 "your-prompt"

# 检查网络连接
curl -I https://open.bigmodel.cn

# 检查防火墙（ECS 安全组）
# 确保允许出站 443 端口
```

### 问题 4: 权限不足

```bash
# 检查权限
ls -la ~/.claude/

# 修复权限
chmod 700 ~/.claude
chmod 600 ~/.claude/*.json
chmod 600 ~/.claude/.env
```

---

## 9. 快速参考命令

```bash
# 安装
curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash -
sudo yum install -y nodejs
sudo npm install -g @anthropic-ai/claude-cli

# 配置
export GLM_API_KEY="your-key"
mkdir -p ~/.claude
cat > ~/.claude/config.json << EOF
{"default_model": "glm-5"}
EOF

# 测试
claude --version
claude "Hello"

# 交互
claude --interactive --model glm-5

# 在项目中使用
cd /opt/myTrader
./scripts/claude-helper.sh "your prompt"
```

---

## 10. 集成 Claude Code (可选)

如果想要更强大的 AI 开发体验，可以使用 Claude Code（Web UI）：

```bash
# Claude Code 不需要安装，直接访问
# https://claude.ai/code

# 配置 Claude Code 连接到本地项目
# Settings → API Key → 输入你的 API Key
```

---

## 总结

| 步骤 | 命令 |
|------|------|
| 1. 安装 Node.js | `curl -fsSL https://rpm.nodesource.com/setup_20.x \| sudo bash -` && `sudo yum install -y nodejs` |
| 2. 安装 Claude CLI | `sudo npm install -g @anthropic-ai/claude-cli` |
| 3. 获取 GLM Key | https://open.bigmodel.cn/ |
| 4. 配置环境 | `export GLM_API_KEY="key"` |
| 5. 测试 | `claude "test"` |
| 6. 集成到项目 | 使用 `ClaudeService` 或 `claude-helper.sh` |

你现在可以：
- 在 ECS 上用 Claude CLI 分析代码、生成文档
- 用 GLM-5 作为国内替代方案
- 在 API 中集成 Claude 功能
- 使用 Claude Code (Web) 进行高级开发

