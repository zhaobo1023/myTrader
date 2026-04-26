# 公众号订阅管理功能 - 实现总结

## 项目目标

在 `https://mytrader.cc/data-health` 页面下增加一个工具入口，用于：
- 添加和管理 wechat2rss 的公众号订阅
- 查看已关注的公众号列表
- 拉取数据用于日报推送和数据分析

## 实现概述

### 架构设计

```
前端 (React)
    ↓
Web API (FastAPI)
    ↓
本地数据库 (MySQL)
wechat_feeds 表
    ↓
wechat2rss SQLite DB
(rsses 表 + articles 表)
```

### 核心功能

| 功能 | 位置 | 说明 |
|------|------|------|
| 列表查看 | 前端表格 | 显示所有公众号及实时文章数 |
| 添加订阅 | 表单 + API | 验证后保存到 wechat_feeds 表 |
| 删除订阅 | 按钮 + API | 软删除（标记 is_active=0） |
| 同步订阅 | 按钮 + API | 从 wechat2rss rsses 表同步 |
| 文章统计 | 实时计算 | 从 wechat2rss articles 表查询 |

## 文件清单

### 后端文件

#### 1. 数据库模型
**文件**: `api/models/wechat_feed.py`
- SQLAlchemy ORM 模型
- 字段: id, feed_id, name, description, url, is_active, created_at, updated_at
- 约束: feed_id 唯一索引，is_active 索引

#### 2. API 路由
**文件**: `api/routers/wechat_feed.py`
- 5 个核心端点：
  - `GET /api/wechat-feed/list` - 获取公众号列表
  - `POST /api/wechat-feed/add` - 添加公众号
  - `DELETE /api/wechat-feed/{feed_id}` - 删除公众号
  - `POST /api/wechat-feed/sync` - 同步公众号
  - `GET /api/wechat-feed/articles-export` - 获取文章统计

- 所有接口检查管理员权限
- 直接读写 wechat2rss SQLite 数据库
- 错误处理和日志记录

#### 3. 主程序入口
**文件**: `api/main.py` (修改)
- 导入 wechat_feed 路由
- 注册路由到 FastAPI 应用

#### 4. 数据库迁移
**文件**: `alembic/versions/b1c2d3e4f5g6_add_wechat_feeds_table.py`
- 创建 wechat_feeds 表
- 添加索引和约束
- (注: 实际已直接创建表，该文件作为记录)

### 前端文件

#### 1. 组件
**文件**: `web/src/components/wechat-subscriptions-panel.tsx`
- React 函数组件，使用 TanStack Query 进行数据管理
- 功能:
  - 列表展示（公众号名、ID、今日文章数、描述）
  - 添加表单（feed_id, name, description, url）
  - 删除按钮（带确认对话）
  - 同步按钮（批量导入）
  - 刷新按钮（重新加载数据）
- UI 使用 Tailwind CSS，符合项目风格

#### 2. 页面整合
**文件**: `web/src/app/data-health/page.tsx` (修改)
- 导入 WechatSubscriptionsPanel 组件
- 添加新的 'wechat' 标签页
- 集成到现有的标签页架构中

### 配置文件

**文件**: `.env.example` (修改)
- 添加 `WECHAT_RSS_DB` 配置项
- 默认路径: `/root/wechat2rss/data/res.db`

### 文档文件

#### 1. 详细设计文档
**文件**: `docs/claude/wechat_subscription.md`
- 功能概述
- API 详细文档
- 数据库设计
- 工作流程说明
- 环境配置
- 故障排查

#### 2. 快速开始指南
**文件**: `docs/claude/WECHAT_SETUP.md`
- 环境配置步骤
- 启动说明
- 使用步骤（同步、添加、查看、删除）
- API 测试命令
- 集成说明

## 数据库

### 表结构

```sql
CREATE TABLE wechat_feeds (
    id INT AUTO_INCREMENT PRIMARY KEY,
    feed_id VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    url VARCHAR(1024),
    is_active INT DEFAULT 1 NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX ix_wechat_feeds_feed_id (feed_id),
    INDEX ix_wechat_feeds_is_active (is_active)
)
```

### 与 wechat2rss 的关系

- **本地库** (`wechat_feeds`): 用户配置和追踪
- **wechat2rss** (`res.db`):
  - `rsses` 表: 公众号定义
  - `articles` 表: 文章内容

集成点:
- 添加公众号时验证其存在于 wechat2rss
- 文章统计直接查询 wechat2rss articles 表
- 同步操作从 wechat2rss rsses 表读取数据

## API 示例

### 获取公众号列表

```bash
curl -X GET http://localhost:8000/api/wechat-feed/list \
  -H "Authorization: Bearer <token>"
```

Response:
```json
[
  {
    "id": 1,
    "feed_id": "cailianshe",
    "name": "财联社",
    "description": "财经新闻快讯",
    "url": null,
    "is_active": 1,
    "created_at": "2026-04-26T10:00:00"
  }
]
```

### 添加公众号

```bash
curl -X POST http://localhost:8000/api/wechat-feed/add \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d {
    "feed_id": "huaerjiejianjian",
    "name": "华尔街见闻",
    "description": "全球资讯",
    "url": "https://example.com"
  }
```

### 同步公众号

```bash
curl -X POST http://localhost:8000/api/wechat-feed/sync \
  -H "Authorization: Bearer <token>"
```

Response:
```json
{
  "message": "Sync completed",
  "synced_count": 3,
  "total_feeds": 15
}
```

### 获取文章统计

```bash
curl -X GET "http://localhost:8000/api/wechat-feed/articles-export?days=1" \
  -H "Authorization: Bearer <token>"
```

Response:
```json
{
  "period_days": 1,
  "feeds": [
    {
      "feed_id": "cailianshe",
      "name": "财联社",
      "article_count": 12,
      "latest_article": "2026-04-26 14:23:45"
    }
  ]
}
```

## 权限与安全

- **要求**: `current_user.tier == 'admin'`
- 所有修改操作（添加、删除、同步）仅限管理员
- 列表查看和文章统计也仅限管理员
- wechat2rss 数据库访问仅限本地文件系统

## 工作流程

### 初次使用

1. 确保 `WECHAT_RSS_DB` 环境变量正确配置
2. 登录管理员账户
3. 访问 `/data-health` 的"公众号订阅"标签页
4. 点击"同步"按钮导入现有公众号

### 日常使用

1. 在 wechat2rss 中添加新公众号
2. 在管理界面点击"同步"按钮
3. 新公众号自动出现在列表中

### 数据导出

```bash
# 每日导出脚本（已有）
python scripts/export_wechat_articles.py

# 输出到 output/article_export/YYYY-MM-DD.json
# 后续通过 LLM 摘要和飞书推送
```

## 限制与注意事项

1. **权限**: 仅管理员可访问
2. **删除策略**: 使用软删除（is_active=0），便于审计
3. **数据同步**: 单向同步（wechat2rss → 本地），不会修改 wechat2rss
4. **依赖**: 需要 wechat2rss 服务运行且数据库可访问
5. **文章统计**: 基于 wechat2rss articles 表的实时数据

## 测试清单

- [x] 数据库表创建
- [x] API 路由注册
- [x] 前端组件导入
- [x] 权限检查
- [x] 错误处理

## 后续扩展

可能的功能扩展:
- 用户级别的订阅管理（非仅限管理员）
- Web UI 的公众号搜索功能
- 自动定时导出任务
- 文章内容预览
- 订阅分组和标签
- 导出规则的自定义配置

## 部署注意事项

1. 运行数据库迁移或直接创建表
2. 检查 wechat2rss 数据库路径
3. 确保 API 服务正确加载 wechat_feed 路由
4. 验证管理员账户可访问

## 相关资源

- 现有脚本: `scripts/export_wechat_articles.py`
- 任务定义: `tasks/` YAML DAG
- 数据管道: `api/services/article_digest_service.py`
- 飞书推送: `api/tasks/data_pipeline_tasks.py`
