# myTrader 小程序技术方案

## 1. 项目背景

myTrader 策略模拟池 (SimPool) 系统已完成后端 API 和 Web 前端实现。为方便移动端查看和管理模拟池，需要开发微信小程序。

**当前架构：**

```
用户浏览器  <--HTTP-->  Nginx(:80)  <--Docker Network-->  FastAPI(:8000)
                                                      |
                                                   Celery Worker/Beat
                                                      |
                                                    MySQL
```

**目标架构：**

```
                    +-- 用户浏览器 <--HTTP--> Nginx(:80) ---+
                    |                                         |
微信小程序 <--HTTPS--> Nginx(:443) --------+  FastAPI(:8000) |
                                          |                  |
                                       FastAPI(:8000)   Celery Worker/Beat
                                          |                  |
                                        MySQL             MySQL
```

Web 端和移动端共享同一个 FastAPI 后端，小程序通过 HTTPS 访问。

## 2. 技术选型

| 维度 | 选型 | 理由 |
|------|------|------|
| 框架 | uni-app (Vue 3 + TypeScript) | 一套代码可编译为小程序和 H5，Vue 生态成熟 |
| 状态管理 | Pinia | Vue 3 官方方案，轻量 |
| HTTP | uni.request (封装) | 小程序环境不支持 axios |
| 图表 | uCharts | ~100KB，canvas 原生渲染，适配小程序 |
| 开发方式 | CLI + VS Code | 与现有项目结构一致，不依赖 HBuilderX IDE |
| 构建目标 | 仅 mp-weixin | 暂不需要 H5/App，保持简单 |

**关于 Web 端和小程序端的关系：**

采用**独立前端**策略（路线 A），不做替换：

- `web/` (Next.js)：Web 端保持不动，拥有 SSR、SSE 流式、复杂路由等能力
- `mini-app/` (uni-app)：仅编译为微信小程序，专注移动端轻量体验

原因：Next.js 功能远强于 uni-app H5 端，替换成本高且得不偿失。后续如需共享数据层，可抽取 `shared/` 目录存放类型定义和 API 封装。

## 3. 前置准备清单

### 3.1 微信小程序账号

- 注册地址：https://mp.weixin.qq.com
- 类型：**个人**即可（SimPool 不涉及微信支付）
- 注册后获得 **AppID**

### 3.2 域名与 HTTPS（关键瓶颈）

微信小程序强制要求所有网络请求使用 HTTPS，且域名必须在小程序后台白名单配置。

**需要完成：**

1. 注册域名（.com 约 60 元/年）
2. ICP 备案（约 1-2 周，通过阿里云/腾讯云提交）
3. DNS A 记录指向服务器 IP（当前 `123.56.3.1`）
4. 申请 SSL 证书（Let's Encrypt 免费）
5. Nginx 配置 HTTPS

**Nginx HTTPS 配置**（基于现有 `nginx.conf` 注释模板）：

```nginx
# HTTP -> HTTPS 重定向
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$host$request_uri;
}

# HTTPS
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # ... 与现有 HTTP server 相同的 location 配置
}
```

**SSL 证书申请步骤：**

```bash
# 安装 certbot
sudo apt install certbot python3-certbot-nginx

# 申请证书（需要先确保域名已解析到服务器）
sudo certbot --nginx -d your-domain.com

# 自动续期（certbot 会自动添加 cron）
sudo certbot renew --dry-run
```

### 3.3 小程序后台域名配置

登录小程序后台 -> 开发管理 -> 开发设置 -> 服务器域名：

| 类型 | 填写 |
|------|------|
| request 合法域名 | `https://your-domain.com` |

### 3.4 开发工具

- 下载微信开发者工具：https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html
- 开发阶段勾选"不校验合法域名"可跳过 HTTPS 限制

## 4. 功能范围

### MVP（第一期）

| 功能 | 说明 |
|------|------|
| 模拟池列表 | 按状态/策略类型筛选，下拉刷新 |
| 创建模拟池 | 填写表单 -> 异步创建 -> 轮询状态 |
| 模拟池详情 | 四个 Tab：概览、持仓、报告、交易记录 |
| 概览 Tab | 8 项核心指标 + 净值曲线图 |
| 持仓 Tab | 持仓中/已退出筛选，退出原因中文标注 |
| 报告 Tab | 日报/周报/终报列表，展开查看指标 |
| 交易记录 Tab | 买入/卖出流水 |
| 强制关闭 | 确认弹窗 -> 平仓 |
| 设置页 | API 地址配置、登录/登出 |

### 不包含（后续迭代）

- 微信登录（wx.login 对接后端）
- 消息订阅（池状态变更通知）
- 分享功能
- 其他策略模块（回测、RAG 研报等）

## 5. 页面结构

```
[TabBar: 模拟池]                          [TabBar: 设置]
  pages/index/index (模拟池列表)              pages/settings/index
    |--> pages/create/index (创建模拟池)        - API 地址配置
    |--> pages/pool-detail/index?id=N           - 登录/登出
           |-[Tab 1] 概览 (指标 + 净值图)
           |-[Tab 2] 持仓 (筛选列表)
           |-[Tab 3] 报告 (展开/收起)
           |-[Tab 4] 交易记录 (流水)
           |--> pages/pool-detail/report-detail
                (单篇报告详情)
```

**导航方式：**
- 模拟池详情页使用 `<swiper>` 实现四个 Tab 切换（组件级别，非页面跳转）
- 报告详情通过 `uni.navigateTo` 跳转（页面级别）

## 6. API 接口对接

小程序直接复用现有 `/api/sim-pool` 全部 10 个接口，无需后端改动。

| 端点 | 方法 | 用途 | 小程序页面 |
|------|------|------|-----------|
| `/api/sim-pool` | GET | 列表 | 模拟池列表 |
| `/api/sim-pool` | POST | 创建 | 创建模拟池 |
| `/api/sim-pool/tasks/{id}` | GET | 轮询状态 | 创建模拟池 |
| `/api/sim-pool/{id}` | GET | 详情 | 模拟池详情 |
| `/api/sim-pool/{id}/positions` | GET | 持仓 | 持仓 Tab |
| `/api/sim-pool/{id}/nav` | GET | 净值曲线 | 概览 Tab |
| `/api/sim-pool/{id}/reports` | GET | 报告列表 | 报告 Tab |
| `/api/sim-pool/{id}/reports/{date}/{type}` | GET | 单篇报告 | 报告详情 |
| `/api/sim-pool/{id}/trades` | GET | 交易记录 | 交易记录 Tab |
| `/api/sim-pool/{id}/close` | POST | 强制关闭 | 概览 Tab |

**数据结构（TypeScript 类型）：**

```typescript
interface Pool {
  id: number;
  strategy_type: string;       // momentum | industry | micro_cap
  signal_date: string;         // YYYY-MM-DD
  status: 'pending' | 'active' | 'closed';
  initial_cash: number;
  current_value: number | null;
  total_return: number | null;
  max_drawdown: number | null;
  sharpe_ratio: number | null;
  created_at: string;
  closed_at: string | null;
}

interface Position {
  id: number;
  stock_code: string;
  stock_name: string;
  status: 'pending' | 'active' | 'exited';
  entry_price: number | null;
  current_price: number | null;
  shares: number | null;
  net_return: number | null;
  exit_reason: string | null;  // stop_loss | take_profit | max_hold | strategy
  entry_date: string | null;
  exit_date: string | null;
  hold_days: number | null;
}

interface NavPoint {
  nav_date: string;
  nav: number;
  benchmark_nav?: number | null;
}

interface TradeLog {
  id: number;
  stock_code: string;
  trade_date: string;
  action: 'buy' | 'sell';
  price: number;
  shares: number;
  amount: number | null;
  commission: number | null;
  stamp_tax: number | null;
  net_amount: number | null;
  trigger: string | null;
}

interface Report {
  id: number;
  report_date: string;
  report_type: 'daily' | 'weekly' | 'final';
  metrics: Record<string, unknown> | null;
}
```

## 7. 项目结构

```
mini-app/
  package.json
  tsconfig.json
  vite.config.ts
  pages.json                  # uni-app 路由 + tabBar 配置
  manifest.json               # 微信 AppID + 平台设置
  App.vue                     # 全局生命周期
  main.ts                     # 入口，注册 Pinia
  .env                        # VITE_API_BASE_URL
  .env.development
  .env.production
  src/
    api/
      index.ts                # uni.request 封装（base URL、token 注入、错误处理）
      sim-pool.ts             # 10 个 SimPool 接口函数 + TypeScript 类型
      auth.ts                 # 登录/登出（复用现有 /api/auth/login）
    constants/
      index.ts                # 中文标签映射 + 格式化工具函数
    composables/
      useTaskPoll.ts          # 创建池 -> 轮询任务状态
    stores/
      auth.ts                 # token 存储（uni.setStorageSync）
      pool.ts                 # 模拟池列表缓存 + 筛选条件
    components/
      PoolCard.vue            # 列表卡片
      MetricsGrid.vue         # 8 项指标网格
      StatusBadge.vue         # 状态标签（待买入/运行中/已关闭）
      StrategyBadge.vue       # 策略类型标签
      EmptyState.vue          # 空列表占位
      pool-detail/
        OverviewTab.vue       # 指标 + 净值图
        PositionsTab.vue      # 持仓列表（筛选）
        ReportsTab.vue        # 报告列表（展开/收起）
        TradesTab.vue         # 交易记录
    pages/
      index/index.vue         # [TabBar] 模拟池列表
      create/index.vue        # 创建模拟池
      pool-detail/index.vue   # 详情页（swiper 四 Tab）
      pool-detail/report-detail.vue  # 报告详情
      settings/index.vue      # [TabBar] 设置
    static/                   # tabBar 图标 PNG
```

## 8. API 层设计

```typescript
// src/api/index.ts

function getBaseUrl(): string {
  // 优先从本地存储读取（用户可在设置页修改）
  const custom = uni.getStorageSync('api_base_url');
  if (custom) return custom;
  return import.meta.env.VITE_API_BASE_URL;
}

function request<T>(opts: {
  url: string;
  method?: 'GET' | 'POST';
  data?: Record<string, unknown>;
}): Promise<T> {
  return new Promise((resolve, reject) => {
    const token = uni.getStorageSync('access_token');
    uni.request({
      url: `${getBaseUrl()}${opts.url}`,
      method: opts.method || 'GET',
      data: opts.data,
      header: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data as T);
        } else {
          reject(new Error(res.data?.detail || `HTTP ${res.statusCode}`));
        }
      },
      fail(err) {
        reject(new Error(err.errMsg || 'Network error'));
      },
    });
  });
}
```

## 9. 中文标签映射

```typescript
// src/constants/index.ts

// 策略类型
const STRATEGY_LABELS: Record<string, string> = {
  momentum: '动量反转',
  industry: '行业轮动',
  micro_cap: '微盘股',
};

// 状态
const STATUS_LABELS: Record<string, { text: string; color: string }> = {
  pending: { text: '待买入', color: '#f59e0b' },
  active:  { text: '运行中', color: '#3b82f6' },
  closed:  { text: '已关闭', color: '#6b7280' },
};

// 退出原因
const EXIT_LABELS: Record<string, string> = {
  stop_loss: '止损',
  take_profit: '止盈',
  max_hold: '到期',
  strategy: '停牌',
};

// 报告类型
const REPORT_LABELS: Record<string, string> = {
  daily: '日报',
  weekly: '周报',
  final: '终报',
};

// 格式化
function fmtPct(v: number | null | undefined): string {
  if (v == null) return '--';
  return `${v >= 0 ? '+' : ''}${(v * 100).toFixed(2)}%`;
}

function fmtMoney(v: number | null | undefined): string {
  if (v == null) return '--';
  return v >= 10000 ? `${(v / 10000).toFixed(2)}万` : v.toFixed(0);
}
```

## 10. 关键交互流程

### 10.1 创建模拟池（异步任务）

```
用户填写表单 -> POST /api/sim-pool
  -> 返回 { task_id }
  -> 每 3 秒轮询 GET /api/sim-pool/tasks/{task_id}
  -> status: PENDING -> STARTED -> SUCCESS/FAILURE
  -> SUCCESS: toast 提示，返回列表
  -> FAILURE: 显示错误原因
```

### 10.2 强制关闭

```
用户点击"强制关闭" -> uni.showModal 确认
  -> POST /api/sim-pool/{id}/close
  -> 成功: 刷新页面数据
  -> 失败: toast 显示错误
```

### 10.3 下拉刷新

```
用户下拉 -> onPullDownRefresh 触发
  -> 重新请求当前列表数据
  -> uni.stopPullDownRefresh()
```

## 11. 后续迭代（不在本期范围）

### 11.1 微信登录对接

当前 SimPool 接口无鉴权（`user_id=0` 硬编码）。如需加入微信登录：

**后端新增：**

```
POST /api/auth/wx-login
  Body: { code: string }       // wx.login() 获取的 code
  Response: { access_token, refresh_token, token_type }

后端流程:
  1. 用 code + appid + secret 调用微信 API
     GET https://api.weixin.qq.com/sns/jscode2session
       ?appid={APPID}&secret={SECRET}&js_code={code}&grant_type=authorization_code
  2. 获取 openid + session_key
  3. 在 users 表中查找/创建对应用户
  4. 签发 JWT token 返回
```

**小程序端：**

```typescript
// wx.login 获取 code -> 发送到后端 -> 换取 JWT
wx.login({
  success(res) {
    request({ url: '/api/auth/wx-login', method: 'POST', data: { code: res.code } });
  }
});
```

### 11.2 消息订阅通知

- 模拟池创建完成、持仓触发止损/止盈时推送消息
- 使用微信模板消息（需在小程序后台申请模板）
- 后端通过微信 API 发送：

```
POST https://api.weixin.qq.com/cgi-bin/message/subscribe/send
  ?access_token={ACCESS_TOKEN}
Body: { touser: openid, template_id, page, data }
```

### 11.3 共享数据层

当小程序端页面增多时，可抽取共享层：

```
shared/
  types.ts        # Pool, Position, NavPoint 等类型定义
  api.ts          # API 封装
  constants.ts    # 标签映射、格式化函数
```

Web 端（Next.js）和小程序端各自引用 shared，避免重复定义。

## 12. 部署流程

### 开发阶段

```bash
cd mini-app
npm install
npm run dev:mp-weixin    # 编译到 dist/build/mp-weixin/
# 用微信开发者工具打开 dist/build/mp-weixin/ 目录
# 勾选"不校验合法域名"
```

### 生产发布

```bash
npm run build:mp-weixin  # 生产构建
# 微信开发者工具 -> 上传 -> 设置为体验版 -> 提交审核
```

### 审核上线流程

```
上传代码 -> 体验版（添加体验者测试） -> 提交审核（1-7天） -> 审核通过 -> 正式发布
```

## 13. 时间线规划

| 阶段 | 依赖 | 预估工作量 |
|------|------|-----------|
| 域名备案 + HTTPS 配置 | 域名注册后 1-2 周 | 0.5 天（配置部分） |
| 小程序注册 | 即时 | 10 分钟 |
| 小程序开发 | HTTPS 就绪后 | 3-4 天 |
| 测试 + 提审 | 开发完成后 | 1 天 |

**建议**：域名备案期间可以并行开发小程序（开发者工具勾选"不校验域名"即可调试），等备案和 HTTPS 就绪后直接联调上线。
