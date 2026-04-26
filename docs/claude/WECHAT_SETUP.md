# 公众号订阅快速开始

## 1. 环境配置

确保 `.env` 中有正确的 wechat2rss 数据库路径：

```bash
# 本地开发
WECHAT_RSS_DB=/path/to/wechat2rss/data/res.db

# 线上服务器（已配置）
WECHAT_RSS_DB=/root/wechat2rss/data/res.db
```

## 2. 启动 API

```bash
# 本地开发
make api-local

# Docker 启动（含 Redis + API + Nginx）
make dev
```

## 3. 访问前端

打开浏览器访问：`https://mytrader.cc/data-health`

或本地：`http://localhost:3000/data-health`

## 4. 使用步骤

### 同步现有公众号（首次）

1. 进入"公众号订阅"标签页
2. 点击"同步"按钮
3. 系统会自动从 wechat2rss 的 rsses 表读取所有公众号并保存到本地 DB

### 添加新公众号

1. 点击"[+] 添加"按钮展开表单
2. 填写信息：
   - **公众号ID**：wechat2rss 中该公众号的唯一标识
   - **公众号名称**：显示名称（如"财联社"）
   - **描述**：可选
   - **URL**：可选
3. 点击"确认添加"

### 查看文章统计

列表中的"今日文章"列显示该公众号过去 24 小时的文章数。

### 删除订阅

点击右侧"[x] 删除"按钮（会有确认对话）。

## 5. API 测试

### 获取公众号列表

```bash
curl -X GET http://localhost:8000/api/wechat-feed/list \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 添加公众号

```bash
curl -X POST http://localhost:8000/api/wechat-feed/add \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "feed_id": "cailianshe",
    "name": "财联社"
  }'
```

### 同步所有公众号

```bash
curl -X POST http://localhost:8000/api/wechat-feed/sync \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 获取文章统计（过去N天）

```bash
curl -X GET "http://localhost:8000/api/wechat-feed/articles-export?days=1" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 删除公众号

```bash
curl -X DELETE http://localhost:8000/api/wechat-feed/cailianshe \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## 6. 集成到日报/分析

现有的导出脚本已可自动拉取数据：

```bash
# 导出过去 24 小时的文章（带内容过滤）
python scripts/export_wechat_articles.py

# 输出：output/article_export/YYYY-MM-DD.json
```

定时任务配置见 `tasks/` 目录中的 YAML DAG。

## 7. 故障排查

### 提示"无法访问 wechat2rss 数据库"

- 确认 `WECHAT_RSS_DB` 环境变量设置正确
- 检查文件权限：`ls -la /root/wechat2rss/data/res.db`
- 确认 wechat2rss 服务正在运行

### "添加失败"或"公众号不存在"

- 确认该公众号已在 wechat2rss 中添加
- 检查 feed_id 是否正确（与 rsses 表中一致）

### 文章数显示为 0

- 检查 wechat2rss 是否已抓取该公众号的文章
- 确认查询时间范围内有新文章

## 相关文档

- [详细设计](wechat_subscription.md)
- [API 参考](wechat_subscription.md#api)
