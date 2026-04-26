# WeChat Feed 公众号订阅管理

## 概述

在 `/data-health` 页面下新增"公众号订阅"标签页，用于管理 wechat2rss 公众号订阅。

## 功能

### 前端 (Web UI)
- **列表查看**：显示所有已订阅的公众号及其实时文章数统计
- **添加订阅**：输入公众号 ID、名称、描述、URL 后添加新订阅
- **删除订阅**：从本地追踪数据库中删除订阅记录
- **同步订阅**：从 wechat2rss 数据库同步新增的公众号到本地 DB
- **刷新**：手动刷新公众号列表和文章统计

### 后端 API
位置：`api/routers/wechat_feed.py`

#### 端点列表

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/wechat-feed/list` | 获取已订阅公众号列表（从 wechat2rss rsses 表） |
| POST | `/api/wechat-feed/add` | 添加新公众号订阅 |
| DELETE | `/api/wechat-feed/{feed_id}` | 删除订阅（标记为不活跃） |
| POST | `/api/wechat-feed/sync` | 同步 wechat2rss 中的订阅到本地 DB |
| GET | `/api/wechat-feed/articles-export` | 获取指定天数内的文章统计 |

#### 权限
所有接口需要 `current_user.tier == 'admin'`（管理员）

#### 请求/响应示例

**添加公众号**
```bash
curl -X POST http://localhost:8000/api/wechat-feed/add \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "feed_id": "cailianshe",
    "name": "财联社",
    "description": "财经新闻快讯",
    "url": "https://example.com"
  }'
```

**获取公众号列表**
```bash
curl http://localhost:8000/api/wechat-feed/list \
  -H "Authorization: Bearer <token>"
```

## 数据库

### 表结构

表名：`wechat_feeds`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT | 主键 |
| feed_id | VARCHAR(255) | 公众号 ID（唯一） |
| name | VARCHAR(255) | 公众号名称 |
| description | TEXT | 描述 |
| url | VARCHAR(1024) | URL |
| is_active | INT | 是否活跃（1=活跃，0=已删除） |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

### 与 wechat2rss 的关系

- myTrader 的 `wechat_feeds` 表作为**本地追踪数据库**，记录用户关注的公众号配置
- 实际的文章数据存储在 wechat2rss 的 SQLite 数据库（`res.db`）中
  - rsses 表：公众号列表
  - articles 表：文章内容

## 工作流程

### 1. 初始化：同步现有订阅

```bash
# 在管理界面点击"同步"按钮
# 或通过 API：
curl -X POST http://localhost:8000/api/wechat-feed/sync \
  -H "Authorization: Bearer <token>"
```

### 2. 添加新公众号

```
前端流程：
1. 在公众号订阅面板点击"[+] 添加"
2. 输入公众号 ID、名称等信息
3. 点击"确认添加"
4. API 验证该公众号存在于 wechat2rss
5. 保存到本地 wechat_feeds 表
```

### 3. 定期拉取文章

项目中已有导出脚本：`scripts/export_wechat_articles.py`

```bash
# 导出过去 24 小时的文章（带过滤规则）
python scripts/export_wechat_articles.py

# 输出到 output/article_export/YYYY-MM-DD.json
```

### 4. 日报/分析流程

已集成到数据管道：
- `api/tasks/data_pipeline_tasks.py` 中的 `export_wechat_articles_task()`
- 导出后通过 LLM 生成摘要
- 发送到飞书

## 环境变量

添加到 `.env`：

```bash
# wechat2rss SQLite 数据库路径
WECHAT_RSS_DB=/root/wechat2rss/data/res.db
```

## 主要文件

| 文件 | 说明 |
|------|------|
| api/models/wechat_feed.py | SQLAlchemy 模型 |
| api/routers/wechat_feed.py | FastAPI 路由 |
| web/src/components/wechat-subscriptions-panel.tsx | 前端组件 |
| web/src/app/data-health/page.tsx | 修改（添加标签页） |
| alembic/versions/b1c2d3e4f5g6_add_wechat_feeds_table.py | 数据库迁移 |

## 限制与注意

1. 目前 API 仅限管理员访问
2. 删除操作标记为"不活跃"而非真正删除，便于审计
3. 文章数统计仅基于 wechat2rss 的 res.db，需要确保 WECHAT_RSS_DB 环境变量正确配置
4. 如果 wechat2rss 服务不可用，API 会返回 500 错误
