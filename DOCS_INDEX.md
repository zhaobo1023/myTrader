# 文档索引

快速查找项目部署和开发相关文档。

## 核心文档

### 主项目文档
- [CLAUDE.md](../CLAUDE.md) - 项目总体架构、代码规范、常用命令

### 部署相关

| 文档 | 说明 | 适用场景 |
|------|------|----------|
| [deployment_security_guide.md](./deployment_security_guide.md) | **部署方案与安全指南** | 完整的部署方案对比、安全风险分析、备案前后配置 |
| [ip_access_guide.md](./ip_access_guide.md) | IP 访问方式指南 | 使用 IP + 端口直接访问的详细步骤 |
| [IP_ACCESS_QUICKREF.md](../IP_ACCESS_QUICKREF.md) | 快速参考卡片 | 常用命令和配置速查 |

### 脚本工具

| 脚本 | 说明 | 运行位置 |
|------|------|----------|
| [local-dev-start.sh](../scripts/local-dev-start.sh) | SSH 隧道启动脚本 | 本地电脑 |
| [local-dev-stop.sh](../scripts/local-dev-stop.sh) | SSH 隧道停止脚本 | 本地电脑 |
| [start-backend.sh](../start-backend.sh) | 后端启动脚本 | 服务器 |
| [start-frontend.sh](../start-frontend.sh) | 前端启动脚本 | 服务器 |
| [test-ip-access.sh](../test-ip-access.sh) | 连通性测试脚本 | 服务器 |
| [setup-firewall.sh](../setup-firewall.sh) | 防火墙配置脚本 | 服务器 |

---

## 快速导航

### 我想要...

#### 开发期间访问服务
1. 阅读 [deployment_security_guide.md](./deployment_security_guide.md) 了解安全风险
2. 使用 [local-dev-start.sh](../scripts/local-dev-start.sh) 建立 SSH 隧道（推荐）
3. 或使用 IP 白名单临时访问（谨慎）

#### 配置正式域名访问
1. 确认域名备案已完成
2. 按照 deployment_security_guide.md 中"域名备案完成后的正式方案"操作
3. 配置 DNS 解析
4. 获取 SSL 证书
5. 配置 Nginx HTTPS

#### 检查服务状态
```bash
# 服务器上执行
make check
# 或
./test-ip-access.sh
```

#### 了解项目架构
查看 [CLAUDE.md](../CLAUDE.md) 的项目结构部分

---

## 当前服务器状态

| 项目 | 值 |
|------|-----|
| 内网 IP | 172.29.26.62 |
| 外网 IP | 123.56.3.1 |
| 后端端口 | 8000 |
| 前端端口 | 3000 |
| 域名 | mytrader.cc (备案中) |

---

## 文档更新记录

- **2026-04-11**: 创建部署安全指南，整理 IP 访问方案
- **2026-04-05**: 完成 Web 平台 & API 服务（28/29 任务）
- **2026-03-30**: 新增持仓技术面扫描模块
- **2026-03-29**: 新增 SVD 市场状态监控
- **2026-03-27**: 新增 XGBoost 截面预测策略

---

**提示**: 文档会持续更新，建议定期查看最新版本。如有疑问，参考 deployment_security_guide.md 中的常见问题部分。
