# P0 事故复盘：Docker 清理脚本导致全站不可用

**事故时间：** 2026-04-24 08:00 ~ 08:55 (约 55 分钟)
**影响范围：** 全站不可用（API / 前端 / Celery 任务队列全部中断）
**严重程度：** P0
**撰写人：** Claude (辅助操作者) + wenwen (项目负责人)

---

## 一、事故经过

| 时间 | 事件 |
|------|------|
| 每 8h | crontab 执行 `docker image prune -af --filter "until=8h"`，删除所有 8 小时前的未使用镜像 |
| 04-24 凌晨 | 定时任务删除了 `app-api`、`app-celery-beat`、`app-celery-worker` 和 `python:3.11-slim` 基础镜像 |
| 08:00 | 操作者尝试部署前端更新，执行 `docker compose stop web` |
| 08:00 | docker compose 删除并重建了 `app_mytrader-network`，导致 api/celery/nginx 等容器全部断开网络 |
| 08:02 | 发现其他容器消失，执行 `docker compose up -d` 尝试恢复 |
| 08:02 | 失败：api/celery 镜像已被 prune 删除，需要重新 build |
| 08:03 | `docker compose build` 失败：Docker Hub 超时（`registry-1.docker.io` 不可达）|
| 08:08 | 配置国内 Docker 镜像源，拉取 `python:3.11-slim` 成功 |
| 08:09 | 重启 Docker daemon 导致 web 容器 network 再次断开 |
| 08:12 | 开始 build api/celery 镜像，但 `apt-get update` 从 `deb.debian.org` 下载极慢（14.8 kB/s）|
| 08:30 | apt-get 耗时 11 分钟完成，进入 pip install 阶段 |
| 08:48 | 修改 Dockerfile 加入阿里云 apt 镜像源，push 到服务器 |
| 08:50 | 新 build 启动，apt-get 1 秒完成（8649 kB/s）|
| 08:53 | 全部 build 完成，6 个容器启动 |
| 08:54 | 发现 Redis 容器不在 docker-compose.yml 中，手动启动并配置密码 |
| 08:55 | 全部服务恢复正常，health check 通过 |

---

## 二、根因分析

### 直接原因

服务器 crontab 中配置了**极度激进的镜像清理策略**：

```crontab
# 每 8 小时执行，删除所有 8 小时前创建的未使用镜像（-a = all，不仅仅是 dangling）
0 */8 * * * docker image prune -af --filter "until=8h"
# 每 8 小时执行，清除所有 build cache（仅保留 2G）
0 */8 * * * docker builder prune -af --keep-storage=2g
```

`docker image prune -af` 中的 `-a` 参数含义是**删除所有未被运行中容器引用的镜像**，而不仅仅是 `<none>` 悬空镜像。这意味着：
- 如果一个容器短暂停止（比如重启），它的镜像立即符合清理条件
- build cache 被频繁清除，导致每次 rebuild 都要从零开始

### 间接原因（放大了影响）

1. **Docker Hub 在国内不可达**：ECS 无法直接访问 `registry-1.docker.io`，连最基础的 `python:3.11-slim` 都拉不到
2. **Dockerfile 没有配置国内 apt 源**：`apt-get update` 从 `deb.debian.org` 下载，在阿里云 ECS 上速度 14.8 kB/s（正常应为 8000+ kB/s）
3. **pip 没有配置国内源**：下载 scipy/chromadb/xgboost 等大包从 PyPI 官方源，速度同样受限
4. **Redis 不在 docker-compose.yml 中**：独立运行的 Redis 容器在 network 重建后未自动恢复
5. **操作者（Claude）对部署架构理解不足**：错误使用 `docker compose stop/up` 触发了 network 重建

### 根本原因

**空间释放任务（04-24 [DONE]）的 crontab 配置从未正确落地到服务器**。
- `scripts/docker_cleanup.sh` 被提交到 Git
- 但 GitHub Actions deploy.yml 只做 `git pull + docker restart`，不会更新 crontab
- 实际服务器上跑的是另一套更早写入的 inline crontab 命令
- 新脚本从未被激活过（`/var/log/docker_cleanup.log` 为空）

---

## 三、修复措施

### 已完成

| # | 措施 | commit / 操作 |
|---|------|---------------|
| 1 | 服务器 crontab 替换为安全版本 | 手动 SSH 执行，旧 `prune -af` 已移除 |
| 2 | `docker_cleanup.sh` 重写 | commit `80c3c25`：只清 dangling 镜像，build cache 保留 14 天，不清 network |
| 3 | Dockerfile 加阿里云 apt 镜像源 | commit `229293f`：`sed -i 's/deb.debian.org/mirrors.aliyun.com/g'` |
| 4 | Docker daemon 配置国内 registry mirror | `/etc/docker/daemon.json` 加 `docker.m.daocloud.io` 等镜像 |
| 5 | Redis 容器启动并配置密码 | 手动 `docker run` 加入 `app_mytrader-network` |

### 待完成

| # | 措施 | 优先级 | 说明 |
|---|------|--------|------|
| 1 | Redis 加入 docker-compose.yml | P1 | 避免 Redis 成为独立管理的"隐形依赖"，确保 `docker compose up -d` 能完整拉起全部服务 |
| 2 | pip 配置国内镜像源 | P2 | Dockerfile 中 `pip install` 加 `-i https://mirrors.aliyun.com/pypi/simple/`，rebuild 速度再提升 5-10x |
| 3 | deploy.yml 中加入 crontab 同步步骤 | P2 | 确保服务器 crontab 与仓库中的脚本保持一致，防止"代码更新了但 crontab 没换"的问题重演 |
| 4 | 部署前后自动 health check + 回滚 | P2 | 当前 deploy.yml 只有简单 curl，没有回滚机制 |

---

## 四、经验教训

### 1. `docker image prune -a` 是生产环境的定时炸弹

`-a` 会删除所有未被运行容器引用的镜像，包括 build 的基础镜像和服务镜像。在生产环境中：
- 只用 `docker image prune`（不加 `-a`），仅清理 `<none>` 悬空镜像
- 或者用 `--filter` 精确控制清理范围
- 永远不要在 crontab 中放 `-af`（all + force）组合

### 2. crontab 不归 Git 管 = 配置漂移

代码仓库里的脚本和服务器上实际执行的 crontab 是两套独立系统。如果部署流程不包含 crontab 同步，迟早会出现：
- 旧配置继续运行，新修复不生效
- 多人操作服务器，crontab 被覆盖无人知晓

### 3. 操作前先确认架构

本次事故中，操作者不了解：
- web 服务没有 `build:` 字段，`docker compose build web` 实际上什么都不做
- Redis 是独立于 docker-compose 运行的
- `docker compose stop` 会触发 network 生命周期变化

对生产环境的任何操作，应先 `docker ps` + `docker network ls` + `docker-compose.yml` 三者交叉确认。

### 4. ECS 国内网络环境必须预配置

阿里云 ECS 访问 Docker Hub / PyPI / Debian 官方源速度极差甚至不可达。**所有 Dockerfile 和 pip install 必须预配置国内镜像源**，否则 rebuild 从正常 2 分钟变成 40+ 分钟。

### 5. 不可逆操作需要 dry-run

`docker image prune -af` 是不可逆的。清理脚本应该：
- 先 `--dry-run` 列出将被删除的内容
- 排除关键镜像（用 `--filter` 或 label）
- 记录完整日志便于事后审计

---

## 五、时间线回顾（决策复盘）

| 决策点 | 实际做法 | 更好的做法 |
|--------|----------|-----------|
| 发现 web 需要 rebuild | 直接在服务器 `docker compose stop web` | 应该用 `docker stop mytrader-web && docker rm mytrader-web` 单独操作，不触发 compose 的 network 管理 |
| Docker Hub 超时 | 尝试多种方式绕过 | 应该第一时间配镜像源，而不是尝试 `--no-pull` 等 workaround |
| apt-get 慢 | 等了 11 分钟才意识到需要换源 | 应该在 Dockerfile 中预配置，或者第一时间发现速度异常就停下来改 |
| 整体恢复策略 | 逐步排查，多次尝试 | 应该先完整评估（缺什么镜像、网络状态、磁盘空间），制定一次性恢复计划再执行 |

---

## 六、行动项清单

- [x] 替换服务器 crontab（移除 `prune -af`）
- [x] 重写 `docker_cleanup.sh`
- [x] Dockerfile 加阿里云 apt 源
- [x] Docker daemon 加国内 registry mirror
- [ ] Redis 加入 docker-compose.yml
- [ ] pip install 加国内源
- [ ] deploy.yml 加 crontab 同步
- [ ] 建立部署操作 checklist（操作前确认项）
