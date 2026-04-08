# Claude CLI + GLM-5 快速参考

## 一键安装（CentOS ECS）

```bash
# 在 ECS 上运行
cd /opt/myTrader
chmod +x scripts/setup-claude-cli.sh
./scripts/setup-claude-cli.sh
```

---

## 获取和配置 API Key

### GLM-5 API Key

```bash
# 1. 访问智谱官网并注册
# https://open.bigmodel.cn/

# 2. 设置环境变量
export GLM_API_KEY="your-glm-api-key"

# 3. 永久生效（添加到 ~/.bashrc）
echo 'export GLM_API_KEY="your-glm-api-key"' >> ~/.bashrc
source ~/.bashrc

# 4. 验证
echo $GLM_API_KEY
```

### Anthropic API Key (可选)

```bash
# 如果想同时支持 Claude API
export ANTHROPIC_API_KEY="your-anthropic-key"
echo 'export ANTHROPIC_API_KEY="your-key"' >> ~/.bashrc
```

---

## 基本使用

### 测试安装

```bash
# 检查版本
claude --version

# 简单对话
claude "你好，请自我介绍"

# 使用 GLM-5 模型
claude --model glm-5 "写一个 Python Hello World"

# 使用 Claude (Anthropic)
claude --model claude-3-5-sonnet "write hello world in Python"
```

### 交互模式

```bash
# 启动交互式对话
claude --interactive

# 指定模型
claude --model glm-5 --interactive

# 设置温度（创意度）
claude --temperature 0.5 "write a poem"

# 设置最大 token
claude --max-tokens 2000 "write a long article"
```

### 读取文件作为上下文

```bash
# 分析代码
claude < myfile.py "这个代码做什么？"

# 重写文件内容
cat myfile.txt | claude "用更简洁的语言重写"

# 从 stdin 读入
echo "问题内容" | claude "回答这个问题"
```

---

## 在项目中使用

### 方式 1: Shell 脚本调用

```bash
#!/bin/bash
# 在项目中调用 Claude

PROMPT="用 Python 实现快速排序"
RESPONSE=$(claude --model glm-5 "$PROMPT")
echo "回复: $RESPONSE"
```

### 方式 2: Python 中调用

```python
import subprocess
import os

def call_claude(prompt, model='glm-5'):
    """调用 Claude CLI"""
    result = subprocess.run(
        ['claude', '--model', model, prompt],
        capture_output=True,
        text=True
    )
    return result.stdout

# 使用
response = call_claude("解释什么是递归")
print(response)
```

### 方式 3: FastAPI 集成

```python
# api/routes/claude.py
from fastapi import APIRouter
import subprocess

router = APIRouter(prefix='/api/claude', tags=['claude'])

@router.post('/ask')
async def ask_claude(prompt: str, model: str = 'glm-5'):
    """调用 Claude 分析"""
    result = subprocess.run(
        ['claude', '--model', model, prompt],
        capture_output=True,
        text=True,
        timeout=60
    )
    
    if result.returncode != 0:
        return {'error': result.stderr}
    
    return {'response': result.stdout}

# 在 main.py 中注册
# app.include_router(router)
```

使用 API：

```bash
curl -X POST http://localhost:8000/api/claude/ask \
  -H "Content-Type: application/json" \
  -d '{"prompt": "写一个 Python 函数计算斐波那契数列"}'
```

---

## 常用命令速查

| 任务 | 命令 |
|------|------|
| 简单提问 | `claude "你的问题"` |
| 指定模型 | `claude --model glm-5 "..."` |
| 交互模式 | `claude --interactive` |
| 分析文件 | `claude < file.py "分析这段代码"` |
| 设置温度 | `claude --temperature 0.7 "..."` |
| 设置 token | `claude --max-tokens 2000 "..."` |
| 帮助信息 | `claude --help` |
| 查看版本 | `claude --version` |

---

## GLM-5 vs Claude 对比

| 特性 | GLM-5 | Claude |
|------|-------|--------|
| 来源 | 国内（智谱） | Anthropic |
| 语言支持 | 中英双语优化 | 英文为主 |
| 速度 | 快 | 中等 |
| 准确率 | 中等 | 高 |
| API 成本 | 便宜 | 中等 |
| 隐私 | 可本地化 | 云端 |

**推荐**：
- 中文内容 → 优先使用 GLM-5
- 英文专业内容 → 使用 Claude
- 两者都尝试 → 获得最好结果

---

## 配置文件位置

```
~/.claude/
├── config.json          # 主配置（模型、提供商）
├── settings.json        # 设置（编辑器、主题）
├── .env                 # 环境变量（可选）
└── logs/
    └── claude.log       # 日志文件
```

编辑配置：

```bash
# 编辑主配置
vi ~/.claude/config.json

# 查看当前配置
cat ~/.claude/config.json
```

---

## 故障排查

### 问题 1: 找不到 claude 命令

```bash
# 检查安装
npm list -g @anthropic-ai/claude-cli

# 重新安装
sudo npm install -g @anthropic-ai/claude-cli

# 更新 PATH
export PATH="/opt/node/bin:$PATH"
```

### 问题 2: API Key 无效

```bash
# 检查 API Key 是否设置
echo $GLM_API_KEY

# 手动测试 API
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
# 检查网络
curl -I https://open.bigmodel.cn

# 增加超时
claude --timeout 600 "your prompt"

# 检查防火墙（ECS 安全组需开放 443 端口）
```

### 问题 4: 权限错误

```bash
# 修复目录权限
chmod 700 ~/.claude
chmod 600 ~/.claude/*.json

# 修复文件权限
chmod 600 ~/.claude/.env
```

---

## 在 ECS systemd 服务中使用

### 修改 systemd 服务文件

编辑 `/etc/systemd/system/mytrader-api.service`：

```ini
[Service]
# ... 其他配置 ...

# 添加这些环境变量
Environment="GLM_API_KEY=your-api-key"
Environment="ANTHROPIC_API_KEY=your-anthropic-key"

# 确保 Claude CLI 在 PATH 中
Environment="PATH=/home/ubuntu/.local/bin:/opt/node/bin:/usr/local/bin:/usr/bin"

ExecStart=...
```

重启服务：

```bash
sudo systemctl daemon-reload
sudo systemctl restart mytrader-api
```

---

## 高级用法

### 使用系统提示词

```bash
# 创建系统角色
claude --system "You are a Python expert" "explain decorators"

# 创建自定义角色文件
cat > ~/.claude/roles/coder.txt << 'EOF'
You are an expert software engineer.
Always provide code examples.
Use the best practices.
EOF

claude --role coder "implement a cache decorator"
```

### 批量处理

```bash
# 遍历文件分析
for file in *.py; do
    echo "=== Analyzing $file ==="
    claude < "$file" "找出代码中的问题"
done

# 批量转换
ls *.md | while read f; do
    claude < "$f" "把这个文档翻译成英文" > "${f%.md}_en.md"
done
```

### 集成到 Git Hook

创建 `.git/hooks/pre-commit`：

```bash
#!/bin/bash
# 提交前自动检查代码

for file in $(git diff --cached --name-only | grep '\.py$'); do
    echo "[CLAUDE CHECK] $file"
    if ! claude < "$file" "Check for bugs and security issues" | grep -q "OK"; then
        echo "Code review failed. Commit aborted."
        exit 1
    fi
done
```

---

## 成本优化

### 监控 API 使用

```bash
# 查看 GLM-5 账户额度
curl -H "Authorization: Bearer $GLM_API_KEY" \
  https://open.bigmodel.cn/api/paas/v4/account

# 监控使用日志
tail -f ~/.claude/logs/claude.log | grep "tokens"
```

### 减少 API 调用

```bash
# 使用缓存
RESPONSE=$(claude "expensive query" --cache 3600)

# 重用结果
claude < input.txt "process this" | tee output.txt

# 批量请求
cat << 'EOF' | while read prompt; do
  claude "$prompt"
done
```

---

## 与 Claude Code IDE 扩展集成

如果使用 VS Code：

```bash
# 1. 安装 Claude Code 扩展
#    在 VS Code 中搜索 "Claude Code"

# 2. 配置 API Key
#    Settings → Claude → API Key → 输入你的 GLM Key

# 3. 在编辑器中使用
#    Ctrl+Shift+P → Claude: Ask Question
#    选中代码 → Claude: Explain Code
```

---

## 下一步

1. **运行安装脚本**
   ```bash
   ./scripts/setup-claude-cli.sh
   ```

2. **设置 API Key**
   ```bash
   export GLM_API_KEY="your-key"
   ```

3. **测试**
   ```bash
   claude "Hello, 你好"
   ```

4. **整合到项目**
   - 参考本文档的"在项目中使用"部分
   - 查看完整文档：`docs/CLAUDE_CLI_SETUP.md`

5. **进阶**
   - 创建自定义角色
   - 集成到 CI/CD 流程
   - 使用 Claude Code IDE 扩展

---

## 更多资源

- [Claude CLI 官方文档](https://github.com/anthropics/claude-cli)
- [智谱 GLM-5 文档](https://open.bigmodel.cn/dev/howuse/model-use)
- [Anthropic API 文档](https://docs.anthropic.com/)

