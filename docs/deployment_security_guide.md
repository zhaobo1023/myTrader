# 部署方案与安全指南

> 适用于域名备案期间的临时访问方案及正式部署方案

## 一、安全风险分析

### 外网直接访问的风险

| 风险类型 | 说明 | 影响 |
|---------|------|------|
| **无 HTTPS 加密** | 密码、Token、API 密钥等敏感信息明文传输 | 数据泄露、中间人攻击 |
| **IP 扫描攻击** | 暴露的公网 IP 容易被自动化扫描工具发现 | 暴力破解、漏洞探测 |
| **DDoS 风险** | 没有域名层防护和 CDN 加速 | 服务拒绝、带宽耗尽 |
| **API 滥用** | 任何人都可以调用 API 接口 | 恶意刷接口、数据爬取 |
| **合规问题** | 某些场景下未备案域名/IP 提供服务可能违规 | 服务被关停 |

### 云服务商安全组配置建议

**当前阶段（备案期间）**：
- 仅开放 SSH 端口（22）
- 不开放 Web 服务端口（80/443/3000/8000）
- 如需测试，使用 IP 白名单限制

**备案完成后**：
- 开放 80/443 端口给所有 IP
- 保留 SSH 端口，建议改为密钥登录
- 配置防火墙规则限制访问来源

---

## 二、当前阶段推荐方案

### 方案 1：SSH 隧道（最推荐）

**适用场景**：开发者在本地电脑访问服务器资源

#### 工作原理

```
本地浏览器 (localhost:3000)
    ↓
本地 SSH 客户端 (加密隧道)
    ↓
服务器后端 (localhost:8000)
```

#### 操作步骤

**1. 在本地电脑建立 SSH 隧道**

```bash
# macOS / Linux
ssh -L 3000:localhost:3000 -L 8000:localhost:8000 root@123.56.3.1

# Windows PowerShell
ssh -L 3000:localhost:3000 -L 8000:localhost:8000 root@123.56.3.1

# 保持此终端窗口打开
```

**2. 在本地电脑运行前端**

```bash
cd myTrader/web

# 配置 API 地址
echo "NEXT_PUBLIC_API_BASE_URL=http://localhost:8000" > .env.local

# 安装依赖
npm install

# 启动开发服务器
npm run dev

# 浏览器访问
# http://localhost:3000
```

**3. 测试连通性**

```bash
# 测试后端连接
curl http://localhost:8000/health

# 测试 API 文档
# 浏览器打开 http://localhost:8000/docs
```

#### 优缺点

| 优点 | 缺点 |
|------|------|
| 所有流量通过 SSH 加密 | 需要保持 SSH 连接 |
| 服务器端口不对外开放 | 仅适合开发者个人使用 |
| 开发体验和本地一致 | 团队成员需要各自建立隧道 |

---

### 方案 2：仅内网测试

**适用场景**：在服务器上直接测试后端 API

#### 操作步骤

```bash
# SSH 登录服务器
ssh root@123.56.3.1

# 测试后端 API
curl http://localhost:8000/health

# 查看 API 文档（纯文本）
curl http://localhost:8000/openapi.json | python3 -m json.tool
```

#### 优缺点

| 优点 | 缺点 |
|------|------|
| 无需额外配置 | 无法测试前端页面 |
| 完全内网访问，无安全风险 | 调试体验较差 |

---

### 方案 3：VPN / 内网穿透

**适用场景**：团队协作访问

#### 方案 A：ZeroTier / Tailscale（推荐）

**ZeroTier**：

```bash
# 1. 服务器上安装 ZeroTier
curl -s https://install.zerotier.com | sudo bash
sudo zerotier-cli join <NETWORK_ID>

# 2. 本地电脑安装 ZeroTier 客户端
# 下载: https://www.zerotier.com/download/

# 3. 在 ZeroTier 管理面板授权设备

# 4. 使用 ZeroTier 分配的虚拟 IP 访问
# http://<服务器虚拟IP>:8000
```

**Tailscale**：

```bash
# 1. 服务器上安装 Tailscale
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up

# 2. 本地电脑安装 Tailscale
# 下载: https://tailscale.com/download/

# 3. 使用 Tailscale 分配的 IP 访问
# http://<服务器TailscaleIP>:8000
```

#### 方案 B：frp 内网穿透

```bash
# 1. 在有公网 IP 的服务器上运行 frps
# 2. 在目标服务器上运行 frpc
# 3. 配置端口映射规则

# frpc.ini
[web]
type = tcp
local_ip = 127.0.0.1
local_port = 8000
remote_port = 8000
```

#### 优缺点

| 优点 | 缺点 |
|------|------|
| 团队成员可同时访问 | 需要额外部署 VPN 服务 |
| 数据传输加密 | 需要所有成员安装客户端 |
| 可扩展到多台服务器 | 免费方案可能有节点限制 |

---

### 方案 4：IP 白名单（临时方案）

如果确实需要临时外网访问，可配置 IP 白名单：

#### 云服务商安全组配置

**阿里云 ECS**：

1. 入方向规则 → 添加规则
2. 授权对象：填写你的**公网 IP**（查询：`curl ifconfig.me`）
3. 端口：3000, 8000

**腾讯云 CVM**：

1. 安全组 → 修改规则 → 添加入站规则
2. 来源：你的公网 IP /32
3. 协议端口：TCP:3000, TCP:8000

#### 服务器防火墙配置

```bash
# 使用 ufw (Ubuntu)
sudo ufw allow from YOUR_IP to any port 3000
sudo ufw allow from YOUR_IP to any port 8000

# 使用 firewalld (CentOS)
sudo firewall-cmd --permanent --add-rich-rule='rule family="ipv4" source address="YOUR_IP/32" port protocol="tcp" port="3000" accept'
sudo firewall-cmd --reload
```

#### 优缺点

| 优点 | 缺点 |
|------|------|
| 配置简单，立即可用 | IP 可能变化（动态 IP） |
| 仅限指定 IP 访问 | 无法在移动网络使用 |
| 相对安全 | 仍然没有 HTTPS 加密 |

---

## 三、域名备案完成后的正式方案

### 准备工作

1. **域名 DNS 解析**

```
# 在域名注册商处添加 A 记录
mytrader.cc         A  123.56.3.1
www.mytrader.cc     A  123.56.3.1
```

2. **验证 DNS 生效**

```bash
# 等待 5-10 分钟后检查
nslookup mytrader.cc
dig mytrader.cc

# 应返回 123.56.3.1
```

### 正式部署步骤

#### 步骤 1：获取 SSL 证书（Let's Encrypt）

```bash
# 安装 Certbot
sudo apt update
sudo apt install certbot python3-certbot-nginx

# 获取证书（自动配置 Nginx）
sudo certbot --nginx -d mytrader.cc -d www.mytrader.cc

# 按提示输入邮箱、同意条款

# 证书位置
# /etc/letsencrypt/live/mytrader.cc/fullchain.pem
# /etc/letsencrypt/live/mytrader.cc/privkey.pem

# 测试自动续期
sudo certbot renew --dry-run
```

#### 步骤 2：配置 Nginx HTTPS

更新 `/root/app/nginx.conf`：

```nginx
# 取消 HTTPS server 块的注释
server {
    listen 443 ssl http2;
    server_name mytrader.cc www.mytrader.cc;

    # SSL 证书
    ssl_certificate /etc/letsencrypt/live/mytrader.cc/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/mytrader.cc/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # 其他配置...
}

# HTTP 自动跳转 HTTPS
server {
    listen 80;
    server_name mytrader.cc www.mytrader.cc;
    return 301 https://$server_name$request_uri;
}
```

重启 Nginx：

```bash
docker compose restart nginx
# 或
sudo nginx -t && sudo nginx -s reload
```

#### 步骤 3：配置前端环境

```bash
cd /root/app/web

# 更新 API 地址
echo "NEXT_PUBLIC_API_BASE_URL=https://mytrader.cc/api" > .env.local

# 构建生产版本
npm run build

# 启动生产服务器（PM2）
pm2 start npm --name "mytrader-web" -- start

# 或使用 Docker 部署
# 取消 docker-compose.yml 中 nextjs 服务的注释
docker compose up -d nextjs
```

#### 步骤 4：配置云服务商

开放 80/443 端口：

```
安全组入站规则：
- 协议：TCP
- 端口：80, 443
- 授权对象：0.0.0.0/0
```

#### 步骤 5：验证部署

```bash
# 测试 HTTPS
curl https://mytrader.cc/health

# 浏览器访问
# https://mytrader.cc
```

---

## 四、方案对比总结

| 方案 | 安全性 | 易用性 | 适用场景 | 等待域名备案 |
|------|--------|--------|----------|-------------|
| **SSH 隧道** | 高 | 中 | 开发者个人测试 | 推荐 |
| **仅内网测试** | 高 | 低 | 后端 API 测试 | 可用 |
| **VPN 内网穿透** | 高 | 中 | 团队协作 | 推荐 |
| **IP 白名单** | 中 | 高 | 临时外网访问 | 谨慎使用 |
| **HTTPS 域名访问** | 高 | 高 | 正式生产环境 | 备案完成后 |

---

## 五、快速参考

### 当前服务器状态

- **内网 IP**: 172.29.26.62
- **外网 IP**: 123.56.3.1
- **后端服务**: 运行中 (端口 8000)
- **前端服务**: Node.js 版本不兼容，需本地运行

### SSH 隧道一键启动

保存为 `local-start.sh`（在本地电脑执行）：

```bash
#!/bin/bash
echo "建立 SSH 隧道..."
ssh -f -N -L 3000:localhost:3000 -L 8000:localhost:8000 root@123.56.3.1

if [ $? -eq 0 ]; then
    echo "SSH 隧道已建立"
    echo "前端: http://localhost:3000"
    echo "后端: http://localhost:8000"
    echo "API 文档: http://localhost:8000/docs"
    echo ""
    echo "启动前端 (在另一个终端)..."
    cd myTrader/web && npm run dev
else
    echo "SSH 隧道建立失败"
fi
```

### 停止 SSH 隧道

```bash
# 查找并杀死 SSH 隧道进程
ps aux | grep "ssh.*L 3000" | grep -v grep | awk '{print $2}' | xargs kill
```

---

## 六、检查清单

### 备案期间（当前）

- [ ] 后端服务正常运行
- [ ] 配置 SSH 隧道访问
- [ ] 在本地电脑运行前端测试
- [ ] 关闭云服务商安全组的 Web 端口
- [ ] 定期检查域名备案进度

### 备案完成后

- [ ] 配置域名 DNS 解析
- [ ] 等待 DNS 生效
- [ ] 获取 SSL 证书
- [ ] 配置 Nginx HTTPS
- [ ] 更新前端 API 地址
- [ ] 开放安全组 80/443 端口
- [ ] 测试 HTTPS 访问
- [ ] 配置 SSL 证书自动续期

---

## 七、常见问题

**Q: SSH 隧道断开后怎么办？**

A: 重新执行 SSH 隧道命令。可以使用 `autossh` 自动重连：

```bash
sudo apt install autossh
autossh -M 0 -L 3000:localhost:3000 -L 8000:localhost:8000 root@123.56.3.1
```

**Q: 如何在服务器上升级 Node.js？**

A: 使用 nvm 安装 Node.js 20：

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash
source ~/.bashrc
nvm install 20
nvm use 20
nvm alias default 20
```

**Q: SSL 证书过期怎么办？**

A: Certbot 配置了自动续期（cron/systemd timer），检查：

```bash
sudo systemctl status certbot.timer
sudo certbot renew
```

**Q: 如何检查域名备案进度？**

A:
- 阿里云: 控制台 → ICP 备案 → 备案进度
- 腾讯云: 控制台 → 域名与网站 → 备案管理
- 通常需要 7-20 个工作日

---

**更新时间**: 2026-04-11
**服务器信息**: 123.56.3.1 (外网) / 172.29.26.62 (内网)
**相关文档**:
- `/root/app/docs/ip_access_guide.md`
- `/root/app/IP_ACCESS_QUICKREF.md`
