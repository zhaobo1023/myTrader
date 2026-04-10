# myTrader 数据库连接说明

## 当前配置状态

### 数据库信息
- **数据库类型**: MySQL 8.0.45
- **主机地址**: localhost
- **端口**: 3306
- **数据库名**: trade（统一数据库）
- **当前环境**: online（生产环境）

### 连接账号信息

#### 受限账号（推荐使用）
```
用户名: mytrader_user
密码: lGgS^uruPhv%AK0ZifeC
权限: SELECT, INSERT, UPDATE, DELETE
访问范围: mytrader.*, trade.*
```

**权限说明**:
- ✅ 可以查询、插入、更新、删除数据
- ❌ 无法创建/删除表、修改表结构
- ❌ 无管理员权限

#### 管理员账号（仅限本地）
```
用户名: root
密码: Root123456!
权限: ALL PRIVILEGES
```

**安全提示**: root 密码仅存储在本地 `.env` 文件中，不在代码仓库中。

---

## 连接方式

### 1. Python 代码中连接

```python
from config.db import get_connection, execute_query

# 方式1: 使用当前环境（DB_ENV=online）
conn = get_connection()

# 方式2: 显式指定环境
conn = get_connection('local')   # 本地环境
conn = get_connection('online')  # 线上环境

# 执行查询
results = execute_query('SELECT * FROM trade_stock_daily LIMIT 10')
```

### 2. 命令行连接

```bash
# 使用受限账号
mysql -u mytrader_user -p'lGgS^uruPhv%AK0ZifeC' -h localhost trade

# 使用 root 账号
mysql -u root -p'Root123456!' -h localhost trade
```

### 3. SQLAlchemy 连接（API 模块）

```python
from api.config import get_settings

settings = get_settings()
database_url = settings.database_url  # 自动构建连接字符串
# mysql+aiomysql://mytrader_user:password@localhost:3306/trade
```

---

## 配置文件说明

### .env 文件结构

```bash
# 当前环境
DB_ENV=online

# 本地环境配置
LOCAL_DB_HOST=localhost
LOCAL_DB_PORT=3306
LOCAL_DB_USER=mytrader_user
LOCAL_DB_PASSWORD=lGgS^uruPhv%AK0ZifeC
LOCAL_DB_NAME=trade

# 线上环境配置
ONLINE_DB_HOST=localhost
ONLINE_DB_PORT=3306
ONLINE_DB_USER=mytrader_user
ONLINE_DB_PASSWORD=lGgS^uruPhv%AK0ZifeC
ONLINE_DB_NAME=trade
```

### 环境变量优先级

1. 系统环境变量（最高）
2. .env 文件
3. 代码默认值（最低）

---

## 数据库表结构

### 主要数据表

| 表名 | 行数 | 大小 | 说明 |
|------|------|------|------|
| trade_stock_daily | 276万 | 220 MB | A股日线数据 |
| trade_hk_daily | 402万 | 374 MB | 港股日线数据 |
| trade_etf_daily | 119万 | 113 MB | ETF日线数据 |
| trade_stock_financial | 15万 | 10 MB | 财务数据 |
| trade_stock_factor | 4938 | 2 MB | 因子数据 |

### 辅助表

- `trade_calendar` - 交易日历
- `trade_calendar_event` - 日历事件
- `trade_stock_industry` - 股票行业分类
- `trade_stock_moneyflow` - 资金流向
- `trade_stock_news` - 股票新闻

---

## 远端连接配置

### 从其他服务器连接

如果需要从其他服务器连接到此数据库：

```bash
# 1. 确保防火墙允许 3306 端口
# 2. 确保 MySQL 允许远程连接
# 3. 使用以下连接信息

mysql -h <服务器IP> -P 3306 -u mytrader_user -p'lGgS^uruPhv%AK0ZifeC' trade
```

### Python 远端连接

```python
import pymysql

conn = pymysql.connect(
    host='<服务器IP>',
    port=3306,
    user='mytrader_user',
    password='lGgS^uruPhv%AK0ZifeC',
    database='trade',
    charset='utf8mb4'
)
```

---

## 安全建议

1. **定期更换密码**
   ```bash
   mysql -u root -p
   ALTER USER 'mytrader_user'@'localhost' IDENTIFIED BY '新密码';
   FLUSH PRIVILEGES;
   ```

2. **限制远程访问**
   - 在 MySQL 中配置仅允许特定 IP 访问
   - 使用防火墙限制 3306 端口访问

3. **备份策略**
   - 定期备份数据库
   - 保留最近 7 天的备份

4. **监控日志**
   - 监控慢查询日志
   - 监控异常访问

---

## 故障排查

### 连接失败

1. **检查 MySQL 服务状态**
   ```bash
   systemctl status mysqld
   ```

2. **检查账号权限**
   ```bash
   mysql -u mytrader_user -p -e "SHOW GRANTS;"
   ```

3. **测试连接**
   ```python
   from config.db import test_connection
   print(test_connection())
   ```

### 权限不足

如果遇到权限问题，需要联系管理员重新授权：

```sql
GRANT SELECT, INSERT, UPDATE, DELETE ON trade.* TO 'mytrader_user'@'localhost';
GRANT SELECT, INSERT, UPDATE, DELETE ON mytrader.* TO 'mytrader_user'@'localhost';
FLUSH PRIVILEGES;
```

---

## 更新历史

- **2026-04-10**: 创建受限账号 `mytrader_user`，替换 root 账号
- **2026-04-10**: 统一 local 和 online 环境都使用 `trade` 数据库
- **2026-04-10**: 更新默认 Python 版本为 3.10.19
