# Deploy Skill

## 触发条件
- 用户说 "/deploy"、"部署到线上"、"上线" 时触发

## 服务器配置

- SSH 别名：`aliyun-ecs`
- 代码目录：`/app/myTrader`（容器 volume 挂载目录，CI/CD 和手动部署均使用此路径）
- Docker 网络：`mytrader_mytrader-network`（由脚本运行时自动检测，不硬编码）

## 执行规则

**自主执行，不询问用户**。遇到需要在远程运行的脚本时：
- **禁止** heredoc 或嵌套引号方式通过 SSH 传脚本
- **必须** 将脚本写到本地文件，用 `scp` 传到服务器，再 SSH 执行

---

## 部署架构

```
API  ── docker restart（停机 3-5s，确保新代码/新路由可靠加载）
前端 ── 蓝绿切换（blue:3000 / green:3001，新版验证后再切 Nginx）
任务 ── Celery docker restart
```

前端蓝绿流程：
1. 构建新镜像到非活跃槽（blue/green 轮换）
2. 启动新槽容器，直连验证健康（最多 60s）
3. 写 `nginx_upstream_web.conf` 指向新槽，`nginx -s reload`（毫秒级，无停机）
4. 端到端验证 `https://mytrader.cc`
5. 成功 → 停旧槽、写 `.deploy_slot`；失败 → 恢复旧 upstream、停新槽、退出

---

## 部署流程

### 步骤 1 — 本地验证

```bash
python3 -m pytest tests/unit/ -x -q 2>&1 | tail -10
```

测试全部通过才继续。有失败则停止并告知用户。

### 步骤 2 — 准备部署脚本

将 `scripts/deploy_remote.sh` 传到服务器并执行：

```bash
scp scripts/deploy_remote.sh aliyun-ecs:/tmp/deploy_remote.sh
ssh aliyun-ecs "WEB_CHANGED=true bash /tmp/deploy_remote.sh"
```

`WEB_CHANGED=true` 时执行前端蓝绿切换；`false` 时跳过前端，仅做 API reload。

### 步骤 3 — 确认部署结果

脚本末尾会输出：

```
[SUCCESS] Deploy complete.
  Commit     : <git hash> <message>
  Active slot: blue|green
  API status : ok|degraded
  Site e2e   : HTTP 200|307
```

HTTP 200 或 307 均为正常（307 是登录跳转）。

### 步骤 4 — 失败处理

脚本内置自动回滚：
- 前端新槽健康检查失败 → 自动停新槽容器，不切换 Nginx
- 端到端验证失败 → 自动恢复旧 upstream，`nginx -s reload`，停新槽容器

脚本退出码非 0 时，告知用户失败原因，不需要手动回滚。

---

## 首次初始化（仅执行一次）

若服务器上不存在 `.deploy_slot` 和 `nginx_upstream_web.conf`，需先初始化蓝绿环境：

```bash
scp scripts/init_blue_green.sh aliyun-ecs:/tmp/init_blue_green.sh
ssh aliyun-ecs "bash /tmp/init_blue_green.sh"
```

---

## 输出格式

```
## Deploy

### 本地测试
- pytest: PASSED N

### 部署步骤
- [OK] git pull: <commit>
- [OK] API: HUP reload / docker restart
- [OK] Celery: restarted
- [OK] 前端: blue -> green (蓝绿切换) 或 跳过
- [OK] 端到端: HTTP 307

### 最终状态
[DEPLOYED] Active slot: green | API: ok | Site: HTTP 307
```
