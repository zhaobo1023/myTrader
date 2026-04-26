# 部署规范文档

**最后更新：2026-04-26**
**适用环境：阿里云 ECS / mytrader.cc**

---

## 核心原则

1. **所有部署必须通过 `/deploy` 命令或 CI/CD 自动触发，禁止手动执行 docker 命令替代部署**
2. **前端使用蓝绿部署，全程无停机**
3. **API 使用 Gunicorn USR2 优雅热重载，真正零停机（降级兜底：USR2 失败 40s 后自动 fallback 到 docker restart）**
4. **部署脚本是唯一可信来源，SKILL.md 与脚本保持同步**

---

## 服务器基本信息

| 项目 | 值 |
|------|----|
| SSH 别名 | `aliyun-ecs` |
| 代码目录 | `/app/myTrader`（容器 volume 挂载目录） |
| Docker 网络 | `mytrader_mytrader-network`（脚本自动检测） |
| 活跃槽记录 | `/app/myTrader/.deploy_slot` |
| Nginx upstream | `/app/myTrader/nginx_upstream_web.conf` |

---

## 架构说明

```
[用户请求 HTTPS]
       |
[Nginx :443]
       |
       +-- /api/*  --> mytrader-api:8000  (USR2 热重载, 零停机)
       |
       +-- /       --> upstream nextjs_frontend
                           |
                           由 nginx_upstream_web.conf 动态控制
                           当前活跃: blue (mytrader-web-blue:3000)
                                  或 green (mytrader-web-green:3000)

[Celery]
  mytrader-celery-worker-1  <- docker restart
  mytrader-celery-beat-1    <- docker restart
```

### 前端蓝绿槽

| 槽 | 容器名 | 宿主机健康检查端口 |
|----|--------|-----------------|
| blue | `mytrader-web-blue` | `127.0.0.1:3000` |
| green | `mytrader-web-green` | `127.0.0.1:3001` |

每次部署轮换：当前 blue 则部署 green，当前 green 则部署 blue。

---

## 标准部署流程

### 日常部署（推荐：通过 CI/CD）

push 到 `main` 分支后，GitHub Actions 自动：
1. 运行测试（`test.yml`，warn-only，失败不阻断部署）
2. `scp deploy_remote.sh` 到服务器并执行
3. 自动检测是否有 `web/` 目录变更（决定是否执行前端蓝绿切换）

**无需任何手动操作。**

---

### 手动部署（通过 `/deploy` 命令）

在对话中输入：

```
/deploy
```

Claude Code 会自动：
1. 运行本地测试
2. `scp scripts/deploy_remote.sh` 到服务器
3. SSH 执行，传入 `WEB_CHANGED=true|false`
4. 输出部署结果

仅前端有改动时才需要 `WEB_CHANGED=true`，纯后端改动用 `WEB_CHANGED=false`（跳过前端 build，速度快）。

---

### deploy_remote.sh 执行逻辑

```
[1] git fetch + reset --hard origin/main    <- 拉取最新代码到 /app/myTrader

[2] API USR2 热重载（零停机）
    -> find /app -name '*.pyc' -delete    清 .pyc 缓存
    -> pgrep gunicorn | head -1           获取 master pid
    -> kill -USR2 <pid>                   触发热重载
       master fork 新 master -> 新 worker 加载新代码
       旧 worker 处理完当前请求后退出
       全程 socket 持续监听，无请求丢失
    -> 等待 /health 恢复（最多 40s）
    -> 若 40s 未恢复：fallback 到 docker restart（停机 3-5s）

[3] Celery restart
    -> docker restart mytrader-celery-worker-1 mytrader-celery-beat-1

[4] 前端蓝绿切换（仅 WEB_CHANGED=true）
    a. 读 .deploy_slot 确定当前槽（假设为 blue）
    b. 确定新槽为 green
    c. 停止旧 green 容器（如存在）
    d. docker build -t mytrader-web:green ./web
    e. docker run mytrader-web-green（宿主机 :3001，Docker 网络内 :3000）
    f. 健康检查：curl http://127.0.0.1:3001（最多 60s）
    g. 写 nginx_upstream_web.conf 指向 mytrader-web-green:3000
    h. docker exec mytrader-nginx nginx -s reload（毫秒级，无停机）
    i. 端到端验证：curl https://mytrader.cc（期望 200 或 307）
    j. 成功 -> 停 mytrader-web-blue，写 .deploy_slot=green
       失败 -> 恢复旧 nginx_upstream_web.conf，reload nginx，停 green，exit 1

[5] 最终健康检查
    -> curl http://localhost:8000/health
    -> curl https://mytrader.cc
    -> 输出 [SUCCESS] 或 [ERROR]
```

---

## 关键文件

| 文件 | 用途 | 修改频率 |
|------|------|---------|
| `scripts/deploy_remote.sh` | 服务器端部署主脚本 | 部署逻辑变更时 |
| `scripts/init_blue_green.sh` | 蓝绿初始化（仅执行一次） | 几乎不改 |
| `nginx.conf` | Nginx 主配置 | 路由规则变更时 |
| `nginx_upstream_web.conf` | 当前活跃前端槽（服务器上动态生成） | 每次前端部署自动更新 |
| `.deploy_slot` | 当前活跃槽（blue/green，服务器上） | 每次前端部署自动更新 |
| `.github/workflows/deploy.yml` | CI/CD 触发与执行 | 流程变更时 |
| `.claude/skills/deploy/SKILL.md` | `/deploy` 命令的行为规范 | 与脚本同步更新 |

---

## 禁止事项

以下操作**禁止**在生产环境直接执行，必须走部署脚本：

```bash
# 禁止
docker stop mytrader-web && docker rm mytrader-web
docker run -d --name mytrader-web ...

# 禁止
docker compose up -d --build

# 禁止
直接修改 nginx_upstream_web.conf 而不走脚本
```

唯一例外：紧急回滚（见下方）。

---

## 紧急回滚

如果部署后发现问题，手动切回上一个槽：

```bash
# 查看当前活跃槽
ssh aliyun-ecs "cat /app/myTrader/.deploy_slot"

# 假设当前是 green，切回 blue（前提是 blue 容器还在）
ssh aliyun-ecs "
docker ps | grep mytrader-web-blue   # 确认 blue 还在

cat > /app/myTrader/nginx_upstream_web.conf << 'EOF'
upstream nextjs_frontend {
    server mytrader-web-blue:3000;
    keepalive 16;
}
EOF

docker exec mytrader-nginx nginx -s reload
echo blue > /app/myTrader/.deploy_slot
curl -sf https://mytrader.cc -o /dev/null -w 'HTTP %{http_code}\n'
"
```

注意：蓝绿切换成功后旧槽容器会被停止删除，无法直接回滚。**回滚窗口仅在切换后、下次部署前**（下次部署会重用旧槽名）。

如需回滚到更早版本，需重新走部署流程（git revert + push）。

---

## 首次初始化（新服务器）

仅在新服务器首次部署时执行：

```bash
# 1. 确保代码已拉取到 /app/myTrader
ssh aliyun-ecs "cd /app/myTrader && git pull origin main"

# 2. 执行蓝绿初始化
scp scripts/init_blue_green.sh aliyun-ecs:/tmp/init_blue_green.sh
ssh aliyun-ecs "bash /tmp/init_blue_green.sh"

# 3. 验证
curl -sf https://mytrader.cc -o /dev/null -w 'HTTP %{http_code}\n'
```

---

## 磁盘维护

服务器磁盘空间不足会导致前端 build 失败。**每月至少清理一次**：

```bash
ssh aliyun-ecs "docker builder prune -f && docker image prune -f && df -h /"
```

警戒线：磁盘使用率超过 80% 时清理。

---

## 健康检查标准

| 检查项 | 命令 | 期望结果 |
|--------|------|---------|
| API 直连 | `curl http://localhost:8000/health` | `{"status":"ok"}` |
| 站点端到端 | `curl -L https://mytrader.cc` | HTTP 200 或 307 |
| 前端容器 | `docker ps \| grep mytrader-web` | `Up` 状态 |
| Nginx | `docker exec mytrader-nginx nginx -t` | `syntax is ok` |

API `status: degraded` 表示 Redis 连接异常，属于已知问题（Redis 容器网络配置问题），不影响主要功能，不作为部署失败判断依据。

---

## 变更部署脚本的规范

修改 `deploy_remote.sh` 或 `SKILL.md` 时必须同步：

1. 修改 `scripts/deploy_remote.sh`
2. 同步更新 `.claude/skills/deploy/SKILL.md`（保持描述与脚本一致）
3. 同步更新本文档（如流程有变化）
4. commit + push，在服务器上测试一次完整部署验证

---

## 历史问题记录

| 时间 | 问题 | 根因 | 修复 |
|------|------|------|------|
| 2026-04-25 | 前端部署停机 | 原脚本 docker stop+rm+run 无缓冲 | 改为蓝绿切换 |
| 2026-04-25 | 网络名硬编码错误 | `app_mytrader-network` vs 实际 `mytrader_mytrader-network` | 改为运行时自动检测 |
| 2026-04-25 | CI/CD 部署代码无效 | git pull 在 `/root/app`，容器挂载的是 `/app/myTrader` | 统一到 `/app/myTrader` |
| 2026-04-25 | Nginx duplicate upstream | nginx.conf 有 include 同时 conf.d 自动加载 | 去掉 include，只用自动加载 |
| 2026-04-25 | upstream 用 127.0.0.1 失败 | Nginx 容器内 127.0.0.1 是自己，无法访问宿主机 | 改为容器名（Docker DNS 解析） |
| 2026-04-26 | API HUP reload 后新路由 404 | Gunicorn SIGHUP fork 新 worker 时，Python .pyc 缓存/模块缓存未更新，新增路由不生效 | 放弃 HUP reload，改用 docker restart（停机 3-5s 可接受） |
| 2026-04-26 | API docker restart 停机 3-5s | 每次部署均有短暂停机 | 改用 Gunicorn USR2 热重载（真正零停机），热重载前清 .pyc 缓存，fallback 降级保留 |
