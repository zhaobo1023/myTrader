# ECS SSH 密钥配置指南

## 问题诊断

### 你遇到的错误

```
git pull origin master
Permission denied (publickey).
fatal: Could not read from remote repository.
```

### 原因

ECS 上没有配置 GitHub SSH 密钥。你的本地机器配置正确，但 ECS 上是一个独立的系统。

---

## 解决方案（3 选 1）

### 方案 A：生成 ECS 的 SSH 密钥并添加到 GitHub（推荐）

#### 步骤 1：在 ECS 上生成 SSH 密钥

```bash
# SSH 连接到 ECS
ssh ubuntu@your-ecs-ip

# 在 ECS 上执行
ssh-keygen -t ed25519 -C "your-github-email@example.com" -f ~/.ssh/id_ed25519 -N ""

# 或者使用 RSA（兼容性更好）
ssh-keygen -t rsa -b 4096 -C "your-github-email@example.com" -f ~/.ssh/id_rsa -N ""
```

#### 步骤 2：获取公钥

```bash
# 在 ECS 上执行，查看公钥
cat ~/.ssh/id_ed25519.pub

# 或 RSA
cat ~/.ssh/id_rsa.pub

# 复制输出的公钥（从 ssh-ed25519 或 ssh-rsa 开头到结尾）
```

#### 步骤 3：添加公钥到 GitHub

1. 访问 GitHub → Settings → SSH and GPG keys
2. 点击 "New SSH key"
3. Title: 输入 "ECS Server" 或类似名称
4. Key: 粘贴刚才复制的公钥
5. 点击 "Add SSH key"

#### 步骤 4：验证（在 ECS 上执行）

```bash
ssh -T git@github.com

# 应该看到类似输出：
# Hi zhaobo03! You've successfully authenticated, but GitHub does not provide shell access.
```

#### 步骤 5：测试 Git 操作

```bash
cd /opt/myTrader
git pull origin main

# 或者如果分支是 master
git pull origin master
```

---

### 方案 B：使用 GitHub Token 代替 SSH（更简单）

如果不想配置 SSH，可以用 GitHub Token。

#### 步骤 1：生成 GitHub Personal Access Token

1. 访问 GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
2. 点击 "Generate new token (classic)"
3. 权限勾选：`repo` (完整仓库访问)
4. 生成 token 并复制

#### 步骤 2：在 ECS 上配置 Git

```bash
# SSH 连接到 ECS
ssh ubuntu@your-ecs-ip

# 配置 Git 使用 token
git config --global credential.helper store

# 执行任意 git 操作（会提示输入凭证）
cd /opt/myTrader
git pull origin main

# 当提示用户名和密码时：
# Username: your-github-username
# Password: paste-your-github-token
```

#### 步骤 3：验证

```bash
# 应该成功拉取代码
git status

# token 已保存到 ~/.git-credentials（自动）
cat ~/.git-credentials  # 可以看到已保存的 token
```

**优点**：简单直接，无需在多台服务器管理 SSH 密钥

**缺点**：Token 有过期风险，需定期更新

---

### 方案 C：从本地复制 SSH 密钥到 ECS（最快但不推荐）

#### 步骤 1：从本地复制到 ECS

```bash
# 在本地执行
scp ~/.ssh/id_ed25519 ubuntu@your-ecs-ip:~/.ssh/id_ed25519
scp ~/.ssh/id_ed25519.pub ubuntu@your-ecs-ip:~/.ssh/id_ed25519.pub

# 设置权限
ssh ubuntu@your-ecs-ip "chmod 600 ~/.ssh/id_ed25519 && chmod 644 ~/.ssh/id_ed25519.pub"
```

#### 步骤 2：验证

```bash
ssh ubuntu@your-ecs-ip "ssh -T git@github.com"
```

**警告**：这种方式如果 ECS 服务器被破坏，你的 GitHub 密钥会暴露。不推荐生产环境使用。

---

## 推荐方案对比

| 方案 | 安全性 | 易用性 | 维护成本 |
|------|--------|--------|---------|
| A: 生成新密钥 | 高 | 中等 | 低 | [推荐]
| B: GitHub Token | 中等 | 高 | 中 | [快速]
| C: 复制密钥 | 低 | 高 | 高 | [不推荐]

**最佳实践**：
- 生产环境 → 使用方案 A（为每台服务器生成不同密钥）
- 开发/测试 → 方案 B 或 C（快速迭代）

---

## 完整操作流程（方案 A）

### 本地操作（无需 SSH 到 ECS）

```bash
# 1. 远程生成密钥和获取公钥（一条命令）
ssh ubuntu@your-ecs-ip "ssh-keygen -t ed25519 -C 'your-email@example.com' -f ~/.ssh/id_ed25519 -N '' && cat ~/.ssh/id_ed25519.pub"

# 会输出类似：
# ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAbcdef...xyz your-email@example.com
```

### GitHub 上添加（Web UI）

1. 访问 https://github.com/settings/keys
2. New SSH key
3. Title: "ECS Production"
4. Key: 粘贴上面的公钥
5. Add SSH key

### 测试（远程验证）

```bash
ssh ubuntu@your-ecs-ip "ssh -T git@github.com"

# 应该输出：
# Hi zhaobo03! You've successfully authenticated...
```

### 部署（最后一步）

```bash
# ECS 上执行
cd /opt/myTrader
git pull origin main
```

---

## 常见问题

### Q1: Permission denied (publickey) 的其他原因

```bash
# 1. 检查 SSH 密钥是否存在
ssh ubuntu@your-ecs-ip "ls -la ~/.ssh/"

# 2. 检查密钥权限（应该是 600）
ssh ubuntu@your-ecs-ip "ls -l ~/.ssh/id_*"

# 3. 检查 GitHub 连接
ssh ubuntu@your-ecs-ip "ssh -vT git@github.com"

# 4. 检查 git remote 是否为 SSH 格式
cd /opt/myTrader && git remote -v
# 应该是 git@github.com:zhaobo03/myTrader.git
# 而不是 https://github.com/zhaobo03/myTrader.git
```

### Q2: 能否为多个服务器配置同一个 SSH 密钥？

可以，但**不推荐**。最佳实践：
- 每台服务器一个密钥
- GitHub 上添加多个 SSH 密钥（每个对应一台服务器）
- 如果一台服务器被破坏，只需删除该服务器的密钥

### Q3: 密钥过期了怎么办？

```bash
# SSH 密钥本身不过期，但 GitHub Token 会

# 更新 Token（方案 B）
git config --global --unset credential.helper
git config --global credential.helper store
git pull  # 重新输入新 token

# 或删除已保存的凭证
rm ~/.git-credentials
```

### Q4: 如何在 CI/CD 中使用？

```yaml
# GitHub Actions 中已有 SSH 密钥
name: Deploy
on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Deploy to ECS
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.ECS_HOST }}
          username: ${{ secrets.ECS_USER }}
          key: ${{ secrets.ECS_SSH_KEY }}  # 这是你 ECS 的私钥
          script: |
            cd /opt/myTrader
            git pull origin main  # 如果 ECS 已配置 SSH 密钥，这里会自动工作
```

---

## 诊断脚本

如果还有问题，在 ECS 上运行此脚本诊断：

```bash
#!/bin/bash

echo "=== SSH Key Configuration Diagnostics ==="
echo ""

echo "[1] SSH 目录"
ls -la ~/.ssh/

echo ""
echo "[2] 密钥权限"
ls -l ~/.ssh/id_*

echo ""
echo "[3] GitHub 连接测试"
ssh -T git@github.com 2>&1

echo ""
echo "[4] Git remote 配置"
cd /opt/myTrader && git remote -v

echo ""
echo "[5] SSH 密钥有效性"
ssh-keygen -l -f ~/.ssh/id_ed25519.pub 2>/dev/null || echo "No ED25519 key found"
ssh-keygen -l -f ~/.ssh/id_rsa.pub 2>/dev/null || echo "No RSA key found"
```

保存为 `diagnose-ssh.sh` 并执行：

```bash
chmod +x diagnose-ssh.sh
./diagnose-ssh.sh
```

---

## 总结

| 场景 | 推荐方案 |
|------|---------|
| 生产环境单服务器 | A：生成新密钥 |
| 生产环境多服务器 | A：每个服务器一个密钥 |
| 快速部署/测试 | B：GitHub Token |
| 一次性配置 | A：生成新密钥（一劳永逸） |

**立即操作**：

```bash
# 方案 A（推荐）
ssh ubuntu@your-ecs-ip "ssh-keygen -t ed25519 -C 'your-email' -f ~/.ssh/id_ed25519 -N '' && cat ~/.ssh/id_ed25519.pub"

# 复制输出的公钥 → 添加到 GitHub Settings → SSH Keys

# 验证
ssh ubuntu@your-ecs-ip "ssh -T git@github.com"

# 测试
ssh ubuntu@your-ecs-ip "cd /opt/myTrader && git pull origin main"
```

完成！

