# 快速参考 - IP 访问方式

## 当前访问地址

```
前端: http://<your-ip>:3000
后端: http://<your-ip>:8000
健康检查: http://<your-ip>:8000/health
```

## 一键启动

```bash
make start-ip
```

## 服务管理

```bash
# 查看服务状态
make check

# 查看后端日志
docker logs -f mytrader-api

# 重启后端
docker compose restart api

# 停止所有服务
docker compose down
```

## 防火墙配置

确保服务器防火墙/安全组放行以下端口：
- **3000** - 前端
- **8000** - 后端 API

## 配置文件

| 文件 | 说明 |
|------|------|
| `docker-compose.yml` | 后端端口绑定（已改为 0.0.0.0:8000） |
| `web/.env.local` | 前端 API 地址配置 |
| `web/next.config.ts` | Next.js 开发模式代理配置 |
| `start-backend.sh` | 后端启动脚本 |
| `start-frontend.sh` | 前端启动脚本 |

## 手动操作

```bash
# 启动后端（Docker）
cd /root/app
docker compose up -d api

# 启动前端（开发模式）
cd /root/app/web
npm install  # 首次运行
npm run dev  # 绑定到 0.0.0.0，外部可访问
```

## 获取服务器 IP

```bash
hostname -I | awk '{print $1}'
```

## 域名备案完成后的迁移

详见 `/root/app/docs/ip_access_guide.md`
