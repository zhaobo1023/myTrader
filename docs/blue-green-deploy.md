# 蓝绿部署技术方案

## 背景与问题

### 现有部署方式的缺陷

| 问题 | 现象 | 根因 |
|------|------|------|
| 前端切换有停机 | `docker stop` → `docker rm` → `docker run` 期间 Nginx 返回 502 | 单容器原地替换 |
| 网络名硬编码错误 | 新容器加入 `app_mytrader-network`，Nginx 在 `mytrader_mytrader-network` 找不到 | `deploy_remote.sh:75` 写死 |
| SKILL.md 与脚本不一致 | SKILL.md 写 `docker compose up -d --build`，实际跑 HUP reload | 两套逻辑并存 |
| 健康检查不完整 | 只验证 `localhost:8000/health`，不验证 Nginx 是否能路由到前端 | 缺少端到端检查 |
| 前端 build 步骤缺失 | SKILL.md 完全没有前端镜像重建流程 | 文档未覆盖 |

---

## 蓝绿部署设计

### 核心思路

- **API**：维持现有 Gunicorn HUP reload（已是准零停机，不改动）
- **前端**：双槽（blue/green）轮换，新版本预热验证后再切流
- **Nginx**：通过动态 upstream 文件 + `nginx -s reload` 完成毫秒级切换（不中断已有连接）
- **Celery**：`docker restart`，不影响用户请求，维持现状

### 架构图

```
[用户请求]
    |
[Nginx :443]
    |
    +-- /api/*  --> mytrader-api:8000  (Gunicorn HUP reload, 无停机)
    |
    +-- /       --> upstream nextjs_frontend
                        |
                        当前活跃槽 (由 /etc/nginx/conf.d/upstream_web.conf 决定)
                        +--> blue:  mytrader-web-blue  127.0.0.1:3000
                        +--> green: mytrader-web-green 127.0.0.1:3001

部署时：
  1. 构建新镜像 mytrader-web:new
  2. 启动非活跃槽（假设当前 blue 活跃，则启动 green:3001）
  3. 健康验证 green（curl green 直连 + curl 经 Nginx 路由）
  4. 写 upstream_web.conf 指向 green，执行 nginx -s reload（毫秒级，无停机）
  5. 验证切换成功
  6. 停止旧 blue 容器
  7. 记录当前活跃槽到 /root/app/.deploy_slot（持久化）
```

### 端口分配

| 槽 | 容器名 | 宿主机端口 |
|----|--------|-----------|
| blue | mytrader-web-blue | 127.0.0.1:3000 |
| green | mytrader-web-green | 127.0.0.1:3001 |

Nginx upstream 始终只指向其中一个槽。

### Nginx upstream 动态文件机制

`nginx.conf` 中 `upstream nextjs_frontend` 改为从独立文件 include：

```nginx
# nginx.conf 中
include /etc/nginx/conf.d/upstream_web.conf;
```

`upstream_web.conf` 内容由部署脚本动态写入，示例：

```nginx
upstream nextjs_frontend {
    server 127.0.0.1:3000;  # blue 活跃
    keepalive 16;
}
```

切换时只需重写此文件，然后 `docker exec mytrader-nginx nginx -s reload`。

---

## 文件改动清单

| 文件 | 改动类型 | 内容 |
|------|---------|------|
| `nginx.conf` | 修改 | upstream nextjs_frontend 改为 include 动态文件；删除 `server mytrader-web:3000`（容器名解析不可靠） |
| `scripts/deploy_remote.sh` | 重写 | 实现完整蓝绿切换逻辑；修复网络名；完善健康检查 |
| `scripts/init_blue_green.sh` | 新增 | 首次初始化：创建 blue 容器、upstream_web.conf、.deploy_slot |
| `.claude/skills/deploy/SKILL.md` | 重写 | 与实际脚本对齐；明确前端蓝绿流程；删除错误的 `docker compose up --build` 描述 |
| `docker-compose.yml` | 不改动 | web 服务从 compose 管理中移出，由部署脚本直接管理 |
| `.github/workflows/deploy.yml` | 小改 | 透传 `DEPLOY_NETWORK` 环境变量（消除硬编码） |

---

## deploy_remote.sh 新流程（伪代码）

```
1. git fetch + reset --hard origin/main

2. API 热重载（维持现有 HUP reload 逻辑）

3. Celery restart（维持现有逻辑）

4. 前端蓝绿切换（仅 WEB_CHANGED=true 时执行）：
   a. 读取当前活跃槽：ACTIVE=$(cat .deploy_slot)  # blue 或 green
   b. 确定新槽：NEW = blue 和 green 中非 ACTIVE 的那个
   c. 确定端口：blue=3000, green=3001
   d. 停止旧的 NEW 槽容器（如果存在）
   e. 构建新镜像：docker build -t mytrader-web:$NEW ./web
   f. 启动新槽容器（加入 mytrader_mytrader-network，绑定对应端口）
   g. 等待新槽健康（curl 直连新槽端口，最多 60s）
   h. 切换 Nginx：写 upstream_web.conf 指向新槽端口，nginx -s reload
   i. 端到端验证：curl https://mytrader.cc 确认 200/307
   j. 成功：停止旧 ACTIVE 槽容器，写 .deploy_slot = NEW
   k. 失败：恢复 upstream_web.conf 指向旧槽，nginx -s reload，停止新槽容器，exit 1

5. 最终健康检查：
   - curl http://localhost:8000/health  (API)
   - curl -I https://mytrader.cc        (端到端，经 Nginx)
```

---

## 任务拆解

### T1 - 初始化脚本 `scripts/init_blue_green.sh`
- 在服务器上执行一次，建立初始状态
- 创建 `.deploy_slot = blue`
- 将现有 `mytrader-web` 容器重命名/重建为 `mytrader-web-blue`
- 生成初始 `upstream_web.conf`（指向 blue:3000）
- 挂载 `upstream_web.conf` 到 Nginx 容器（需要重启 Nginx）

### T2 - 修改 `nginx.conf`
- upstream nextjs_frontend 改为 `include /etc/nginx/conf.d/upstream_web.conf`
- upstream 块从 nginx.conf 移走，改为动态文件控制

### T3 - 重写 `scripts/deploy_remote.sh`
- 实现完整蓝绿切换逻辑
- 修复网络名（从 `.deploy_network` 文件读取，或运行时自动检测）
- 完善健康检查（直连 + 端到端）
- 自动回滚逻辑

### T4 - 更新 `.github/workflows/deploy.yml`
- Nginx 容器需挂载动态 upstream 文件目录
- 检测网络名自动传入（消除硬编码）

### T5 - 重写 `.claude/skills/deploy/SKILL.md`
- 与实际脚本对齐
- 明确蓝绿流程步骤
- 删除 `docker compose up --build` 错误描述

### T6 - 服务器执行初始化
- SSH 到服务器，运行 `init_blue_green.sh`
- 验证 Nginx 动态 upstream 生效
- 验证站点正常

---

## 风险与注意事项

1. **初始化需要短暂停机**：`init_blue_green.sh` 需要重启 Nginx 来挂载新的 volume，约 2-3 秒
2. **首次无 green 容器**：第一次部署时 green 不存在，脚本需处理此情况（直接 build+run 即可）
3. **`.deploy_slot` 丢失**：若文件丢失，默认当前活跃为 blue，从 blue 开始部署 green
4. **磁盘空间**：两个前端镜像并存，各约 200-300MB，ECS 需有足够空间
