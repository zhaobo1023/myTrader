# IP + Port 访问方式指南

适用于域名备案期间，使用 IP + 端口直接访问服务。

## 方案 1: 最简单 - 端口直连（推荐）

访问地址：
- 前端: `http://your-ip:3000`
- 后端: `http://your-ip:8000`

### 快速启动

```bash
# 一键启动前后端
make start-ip

# 或者分步启动
make start-backend-ip   # 仅启动后端（Docker）
make start-frontend-ip  # 仅启动前端（Next.js dev）
```

### 手动启动

**启动后端：**
```bash
./start-backend.sh
# 访问: http://your-ip:8000/health
```

**启动前端：**
```bash
./start-frontend.sh
# 访问: http://your-ip:3000
```

### 配置说明

1. **后端（docker-compose.yml）**
   - 端口绑定已改为 `0.0.0.0:8000:8000`（外部可访问）
   - 使用 Docker Compose 启动

2. **前端（web/.env.local）**
   - 启动脚本会自动替换 `your-ip` 为实际服务器 IP
   - Next.js 开发模式自动代理 `/api/*` 到后端

3. **防火墙配置**
   ```bash
   # 阿里云/腾讯云控制台安全组放行端口:
   # - 3000 (前端)
   # - 8000 (后端 API)
   ```

## 方案 2: Nginx 统一 80 端口

如果希望统一使用 80 端口，可修改 `nginx.conf`:

```nginx
server {
    listen 80;
    server_name _;  # 接受所有域名/IP

    # API 路由
    location /api/ {
        proxy_pass http://fastapi_backend/;
        # ... 其他配置
    }

    # 前端路由
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

启动：
```bash
docker compose up -d nginx
# 访问: http://your-ip
```

## 方案 3: 前端独立部署（生产推荐）

如果前端也用 Docker 部署，取消 `docker-compose.yml` 中 `nextjs` 服务的注释:

```yaml
nextjs:
  build:
    context: ./web
  ports:
    - "0.0.0.0:3000:3000"
  environment:
    - NEXT_PUBLIC_API_BASE_URL=http://your-ip:8000
```

启动：
```bash
docker compose up -d api nextjs
```

## 域名备案完成后的迁移

### 1. 配置域名解析

在域名 DNS 管理中添加 A 记录：
```
mytrader.cc  A  your-ip
```

### 2. 更新前端配置

修改 `web/.env.local`:
```bash
NEXT_PUBLIC_API_BASE_URL=http://mytrader.cc/api
```

### 3. 启用 HTTPS

```bash
# 安装 Certbot
sudo apt install certbot python3-certbot-nginx

# 获取 SSL 证书
sudo certbot --nginx -d mytrader.cc -d www.mytrader.cc

# Nginx 会自动配置 HTTPS，取消 nginx.conf 中 HTTPS 部分的注释
```

## 常见问题

**Q: 前端无法连接后端 API？**
A: 检查 `web/.env.local` 中的 IP 是否正确，防火墙是否放行 8000 端口。

**Q: Next.js 开发模式启动失败？**
A: 确保已安装依赖 `cd web && npm install`。

**Q: 如何查看服务状态？**
A: 运行 `make check` 查看所有服务健康状态。
