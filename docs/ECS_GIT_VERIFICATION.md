# ECS Git SSH 配置验证清单

## 1. 验证 SSH 密钥已生成

在 ECS 上执行：

```bash
# 检查密钥文件是否存在
ls -la ~/.ssh/

# 应该看到（至少其中之一）：
# id_ed25519
# id_ed25519.pub
# id_rsa
# id_rsa.pub
```

---

## 2. 验证 GitHub 连接

在 ECS 上执行：

```bash
# 测试 SSH 连接到 GitHub
ssh -T git@github.com

# 成功应该看到：
# Hi zhaobo03! You've successfully authenticated, but GitHub does not provide shell access.

# 如果失败，运行详细诊断
ssh -vT git@github.com
```

---

## 3. 验证 Git 配置

在 ECS 上执行：

```bash
# 检查 git config
git config --global user.name
git config --global user.email

# 如果为空，需要设置
git config --global user.name "Your Name"
git config --global user.email "your-email@example.com"
```

---

## 4. 测试 Git Clone/Pull

在 ECS 上执行：

```bash
# 进入项目目录
cd /opt/myTrader

# 测试 pull
git pull origin main

# 或者如果分支是 master
git pull origin master

# 应该看到：
# Already up to date.
# 或
# Updating xxxxx..yyyyy
# Fast-forward (if there are new changes)
```

---

## 5. 如果还有问题，运行诊断脚本

在 ECS 上执行：

```bash
#!/bin/bash

echo "========== Git SSH 诊断 =========="
echo ""

echo "[1] SSH 密钥检查"
echo "密钥文件列表:"
ls -la ~/.ssh/
echo ""

echo "[2] 密钥权限检查"
echo "私钥权限（应该是 600）："
ls -l ~/.ssh/id_* | grep -v pub
echo ""

echo "[3] GitHub SSH 连接"
ssh -T git@github.com 2>&1
echo ""

echo "[4] Git 配置"
echo "User name: $(git config --global user.name)"
echo "User email: $(git config --global user.email)"
echo ""

echo "[5] Git Remote 检查"
cd /opt/myTrader 2>/dev/null
git remote -v
echo ""

echo "[6] Git Status"
git status 2>/dev/null || echo "Not a git repository"
echo ""

echo "========== 诊断完成 =========="
```

保存并运行：

```bash
cat > diagnose-git.sh << 'EOF'
[上面的脚本代码]
EOF

chmod +x diagnose-git.sh
./diagnose-git.sh
```

---

## 6. 常见问题修复

### 问题：SSH 连接仍然失败

```bash
# 尝试用指定密钥连接
ssh -i ~/.ssh/id_ed25519 -T git@github.com

# 或
ssh -i ~/.ssh/id_rsa -T git@github.com

# 如果仍然失败，检查密钥权限
chmod 600 ~/.ssh/id_*
chmod 700 ~/.ssh/
```

### 问题：Permission denied 在 /opt/myTrader

```bash
# 检查目录权限
ls -la /opt/ | grep myTrader

# 如果当前用户无权限，需要修复
sudo chown -R root:root /opt/myTrader
# 或者
sudo chown -R ubuntu:ubuntu /opt/myTrader
```

### 问题：Git config user 未设置

```bash
# 全局设置
git config --global user.name "Your Name"
git config --global user.email "your-email@example.com"

# 或仅对本项目
cd /opt/myTrader
git config user.name "Your Name"
git config user.email "your-email@example.com"

# 验证
git config --global --list
```

---

## 7. 部署脚本兼容性检查

如果要用我们之前的 `scripts/deploy.sh`，需要确保：

```bash
# 1. 脚本中的 git pull 会使用 SSH
cd /opt/myTrader
git pull origin main  # 应该使用 ~/.ssh 中的密钥

# 2. 如果是 root 用户运行脚本
# 确保 /root/.ssh 中有密钥（你已经有了）

# 3. systemd 服务中的用户
# 检查 mytrader-api.service 中的 User=
# 如果是 ubuntu，需要确保 ~/.ssh 也在 /home/ubuntu 下
```

---

## 8. 为 ubuntu 用户也配置 SSH 密钥（如果需要）

如果 systemd 服务以 `ubuntu` 用户运行，也需要为其配置 SSH 密钥：

```bash
# SSH 到 ECS，切换到 ubuntu 用户
sudo su - ubuntu

# 为 ubuntu 用户生成密钥
ssh-keygen -t ed25519 -C 'your-email@example.com' -f ~/.ssh/id_ed25519 -N ''

# 查看公钥并添加到 GitHub
cat ~/.ssh/id_ed25519.pub

# 测试
ssh -T git@github.com
```

---

## 9. 快速验证一行命令

```bash
# 一条命令检查是否一切正常
git pull origin main && echo "✓ Git pull 成功" || echo "✗ Git pull 失败"

# 或者
cd /opt/myTrader && git pull origin main && echo "✓ 项目更新成功"
```

---

## 10. 如果完全卡住，使用 HTTPS Token 作为临时方案

```bash
# 配置 git 使用 credential helper
git config --global credential.helper store

# 下次 pull 时会提示输入凭证
cd /opt/myTrader
git pull origin main

# 输入：
# Username: your-github-username
# Password: your-github-token
```

---

## 下一步

### 验证清单

- [ ] SSH 密钥存在于 `/root/.ssh`
- [ ] 公钥已添加到 GitHub settings
- [ ] `ssh -T git@github.com` 返回成功信息
- [ ] `git config user.name` 和 `git config user.email` 已设置
- [ ] `cd /opt/myTrader && git pull origin main` 成功
- [ ] `/opt/myTrader/.git/config` 使用 SSH 格式 (`git@github.com:...`)

### 一旦验证通过

```bash
# 1. 测试部署脚本
cd /opt/myTrader
./scripts/deploy.sh

# 2. 验证服务状态
sudo systemctl status mytrader-api
sudo systemctl status mytrader-web

# 3. 查看日志
sudo journalctl -u mytrader-api -f
```

---

## 完整快速参考

```bash
# 验证 SSH 密钥
ls -la ~/.ssh/

# 验证 GitHub 连接
ssh -T git@github.com

# 验证 Git 配置
git config --global user.name
git config --global user.email

# 验证项目可以 pull
cd /opt/myTrader && git pull origin main

# 一键诊断
cd /opt/myTrader && (
  echo "[SSH] $(ssh -T git@github.com 2>&1 | head -1)" &&
  echo "[Git User] $(git config --global user.name)" &&
  echo "[Git Status] $(git status | head -1)" &&
  echo "✓ All checks passed"
)
```

