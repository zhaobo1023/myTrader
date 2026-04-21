# Deploy Skill

## 触发条件
- 用户说 "/deploy <fix描述>" 或 "部署到线上" / "上线"

## 默认服务器配置（myTrader）

- SSH 别名：`aliyun-ecs` 或 `root@123.56.3.1`，密钥 `~/.ssh/id_ed25519`
- 应用目录：`/root/app`
- 服务组成：FastAPI web server + Celery workers（见 docker-compose.yml）
- 部署方式：`git pull` + `docker compose up -d --build`（无独立 docker compose 命令）

---

## 执行规则

**自主执行，不询问用户**。遇到脚本需要在远程运行时：
- **禁止** heredoc 或嵌套引号方式通过 SSH 传脚本
- **必须** 将脚本写到本地文件，用 `scp` 传到服务器，再 SSH 执行

---

## 部署流程（按顺序执行）

### 步骤 1 - 本地验证

```bash
python -m pytest tests/ -x -q 2>&1 | tail -10
```

测试必须全部通过才能继续。若有失败，停止并报告给用户。

### 步骤 2 - 准备部署脚本

将以下内容写到本地 `/tmp/deploy_<timestamp>.sh`：

```bash
#!/bin/bash
set -euo pipefail

APP_DIR="/root/app"
BACKUP_DIR="/root/app_backup_$(date +%Y%m%d_%H%M%S)"

echo "[DEPLOY] Backing up current version to $BACKUP_DIR"
cp -r "$APP_DIR" "$BACKUP_DIR"

echo "[DEPLOY] Pulling latest code"
cd "$APP_DIR"
git pull origin main

echo "[DEPLOY] Restarting services"
docker compose up -d --build

echo "[DEPLOY] Waiting 30s for services to stabilize..."
sleep 30

echo "[DEPLOY] Health check"
docker compose ps
docker compose logs --tail=20
```

传到服务器：
```bash
scp /tmp/deploy_<timestamp>.sh aliyun-ecs:/tmp/deploy.sh
ssh aliyun-ecs "chmod +x /tmp/deploy.sh && bash /tmp/deploy.sh"
```

### 步骤 3 - 确认服务健康

SSH 执行以下检查，**每60秒一次，共3次（3分钟）**：

```bash
ssh aliyun-ecs "cd /root/app && docker compose ps && docker compose logs --tail=10 2>&1"
```

判断标准：
- [OK] 所有容器状态为 `Up`，日志无 `ERROR` / `CRITICAL` / `Exception`
- [WARN] 有非致命警告但服务在运行
- [FAIL] 容器 `Exit` 或日志有致命错误

### 步骤 4 - 重新入队失败任务（如涉及 Celery）

**必须先确认新 worker 已启动**，再重新入队：

```bash
# 确认 worker 在线
ssh aliyun-ecs "cd /root/app && docker compose logs celery_worker --tail=20 | grep 'ready'"
```

只有看到 `ready` 输出后才能重新入队失败任务。

### 步骤 5 - 自动回滚（健康检查失败时）

如果 3 分钟监控中任意一次检查结果为 `[FAIL]`，立即执行：

将以下内容写到本地 `/tmp/rollback_<timestamp>.sh`：

```bash
#!/bin/bash
set -euo pipefail

BACKUP_DIR="$1"
APP_DIR="/root/app"

echo "[ROLLBACK] Restoring from $BACKUP_DIR"
rm -rf "$APP_DIR"
cp -r "$BACKUP_DIR" "$APP_DIR"

cd "$APP_DIR"
docker compose up -d

echo "[ROLLBACK] Done. Current status:"
docker compose ps
```

```bash
scp /tmp/rollback_<timestamp>.sh aliyun-ecs:/tmp/rollback.sh
ssh aliyun-ecs "chmod +x /tmp/rollback.sh && bash /tmp/rollback.sh <BACKUP_DIR>"
```

回滚完成后立即告知用户：服务已回滚、备份路径、失败原因。

---

## 输出格式

```
## Deploy: <fix描述>

### 本地测试
- pytest: PASSED N / FAILED N

### 部署步骤
- [OK] 备份完成：/root/app_backup_<timestamp>
- [OK] git pull 完成
- [OK] 服务重启完成

### 监控结果（3次 x 60秒）
- T+60s:  [OK/WARN/FAIL] - 容器状态 + 日志摘要
- T+120s: [OK/WARN/FAIL] - ...
- T+180s: [OK/WARN/FAIL] - ...

### 最终状态
[DEPLOYED / ROLLED_BACK] - 一句话总结
```
