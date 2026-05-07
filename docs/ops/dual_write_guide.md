# Dual-Write 双写改造指南

## 1. 背景

项目数据分布在两个 MySQL 实例:

| 环境 | 地址 | 说明 |
|------|------|------|
| local | 192.168.97.1 | 内网 Mac Mini |
| online | 123.56.3.1 | 阿里云 |

改造前, 所有数据写入操作只写一个库 (由 `.env` 中 `DB_ENV` 控制)。改造后, 开启双写后每个写操作会同时写 local + online, 保持两边数据同步。

**核心原则**: 主库写入必须成功, 副库写入失败只记 warning 日志, 不影响主流程。

---

## 2. 配置方法

### 2.1 .env 配置

在 `.env` 文件中增加两行:

```bash
# 是否开启双写 (默认 false, 不影响现有行为)
DUAL_WRITE=true

# 副库目标环境 (对应 DB_ENV 的值)
DUAL_WRITE_TARGET=online
```

Windows 端如果 primary 是 online, 要同步到 local, 则配置为:

```bash
DB_ENV=online
DUAL_WRITE=true
DUAL_WRITE_TARGET=local
```

**不配置或 `DUAL_WRITE=false` 时, 所有行为与改造前完全一致, 零侵入。**

### 2.2 数据库连接配置

双写需要 `.env` 中同时配置两套数据库连接, 确保两个库都能连通:

```bash
# 主库 (DB_ENV 指向的那个)
ONLINE_DB_HOST=123.56.3.1
ONLINE_DB_PORT=3306
ONLINE_DB_USER=xxx
ONLINE_DB_PASSWORD=xxx
ONLINE_DB_NAME=trade

# 副库 (DUAL_WRITE_TARGET 指向的那个)
LOCAL_DB_HOST=192.168.97.1
LOCAL_DB_PORT=3306
LOCAL_DB_USER=xxx
LOCAL_DB_PASSWORD=xxx
LOCAL_DB_NAME=mytrader
```

---

## 3. config/db.py 新增的 API

改造在 `config/db.py` 中新增了 5 个函数, 不修改任何已有函数:

### 3.1 配置变量

```python
from config.db import DUAL_WRITE, DUAL_WRITE_TARGET

# DUAL_WRITE: bool, 是否开启双写
# DUAL_WRITE_TARGET: str, 副库环境名 ('local' 或 'online')
```

### 3.2 `get_dual_connections(primary_env=None, secondary_env=None)`

返回 `(主库连接, 副库连接)` 的元组。副库连接可能为 `None`。

- `DUAL_WRITE=false` 且 `secondary_env=None` 时, 返回 `(conn, None)`
- `DUAL_WRITE=true` 且 `secondary_env=None` 时, 返回 `(conn, secondary_conn)`
- `secondary_env` 显式传值时, 无论 `DUAL_WRITE` 开关如何, 都会创建该连接

**用途**: 适用于需要自己管理 cursor/commit 的场景 (替代 `get_connection()`)。

### 3.3 `execute_dual_update(sql, params=None, env=None, env2=None)`

`execute_update()` 的双写版本。API 完全兼容, 直接替换即可。

- 主库成功后才写副库
- 副库失败重试 1 次, 仍失败则 log warning, 不抛异常
- 返回主库的 affected rows

### 3.4 `execute_dual_many(sql, data_list, env=None, env2=None)`

`execute_many()` 的双写版本。API 完全兼容, 直接替换即可。

### 3.5 `dual_executemany(conn, conn2, sql, rows, _logger=None, retries=1)`

底层辅助函数。适用于调用方已持有 `conn` 对象的场景。

- 在 `conn` (主库) 上执行 `executemany` + `commit`
- 然后在 `conn2` (副库) 上 best-effort 执行相同操作
- **注意**: 该函数内部会关闭 `conn2`, 调用方不要再 close

### 3.6 `dual_execute(conn, conn2, sql, params=None, _logger=None, retries=1)`

与 `dual_executemany` 类似, 但执行的是单条 SQL (`cursor.execute` 而非 `cursor.executemany`)。

---

## 4. 三种改造模式

根据原代码的写法, 对应三种改造模式:

### 模式 A: 原来调用 `execute_many()` -- 最简单, 一行替换

**改造前**:

```python
from config.db import execute_many

def save_data(rows):
    if rows:
        execute_many(INSERT_SQL, rows)
```

**改造后**:

```python
from config.db import execute_dual_many

def save_data(rows):
    if rows:
        execute_dual_many(INSERT_SQL, rows)
```

> 适用场景: 原来就用 `execute_many` / `execute_update` 的高层封装函数。
> 文件示例: `macro_fetcher.py`, `macro_factor_calculator.py`

---

### 模式 B: 原来调用 `execute_update()` -- 一行替换

**改造前**:

```python
from config.db import execute_update

execute_update(UPSERT_SQL, params)
```

**改造后**:

```python
from config.db import execute_dual_update

execute_dual_update(UPSERT_SQL, params)
```

> 文件示例: `market_monitor/storage.py` 中的 `save_record()`

---

### 模式 C: 原来直接使用 `get_connection()` -- 需要改写法

这是最常见的模式, 约占 80% 的改造量。原代码自己管理 cursor/commit/close。

#### 子模式 C1: 简单写入 (一次性 executemany)

**改造前**:

```python
from config.db import get_connection

def _bulk_update(updates):
    conn = get_connection()
    cursor = conn.cursor()
    sql = "UPDATE trade_stock_daily_basic SET dv_ttm = %s WHERE stock_code = %s AND trade_date = %s"
    cursor.executemany(sql, updates)
    conn.commit()
    cursor.close()
    conn.close()
```

**改造后**:

```python
from config.db import get_dual_connections, dual_executemany

def _bulk_update(updates):
    conn, conn2 = get_dual_connections()
    try:
        sql = "UPDATE trade_stock_daily_basic SET dv_ttm = %s WHERE stock_code = %s AND trade_date = %s"
        dual_executemany(conn, conn2, sql, updates, _logger=logger)
    finally:
        conn.close()
```

要点:
- `get_dual_connections()` 替代 `get_connection()`
- `dual_executemany()` 封装了主库+副库的写入逻辑
- `conn` 由调用方关闭; `conn2` 由 `dual_executemany` 内部关闭
- 传 `_logger=logger` 以便副库失败时记录日志

#### 子模式 C2: 分批写入 (循环中 executemany)

**改造前**:

```python
from config.db import get_connection

def save_factors_batch(factors_data):
    conn = get_connection()
    cursor = conn.cursor()
    # ... 构建 records ...

    batch_insert_size = 1000
    total_saved = 0
    for i in range(0, len(records), batch_insert_size):
        batch = records[i:i+batch_insert_size]
        try:
            cursor.executemany(sql, batch)
            conn.commit()
            total_saved += len(batch)
        except Exception as e:
            logger.error(f"保存失败: {e}")

    cursor.close()
    conn.close()
    return len(records)
```

**改造后**:

```python
from config.db import get_connection, get_dual_connections

def save_factors_batch(factors_data):
    conn, conn2 = get_dual_connections()
    # ... 构建 records ...

    batch_insert_size = 1000
    total_saved = 0
    for i in range(0, len(records), batch_insert_size):
        batch = records[i:i+batch_insert_size]
        try:
            cursor = conn.cursor()
            cursor.executemany(sql, batch)
            conn.commit()
            cursor.close()
            total_saved += len(batch)
        except Exception as e:
            logger.error(f"保存失败: {e}")

    conn.close()

    # Secondary write (best-effort)
    if conn2:
        try:
            for i in range(0, len(records), batch_insert_size):
                batch = records[i:i+batch_insert_size]
                cursor2 = conn2.cursor()
                cursor2.executemany(sql, batch)
                conn2.commit()
                cursor2.close()
        except Exception as e:
            logger.warning("Dual-write failed: %s", e)
        finally:
            conn2.close()

    return len(records)
```

要点:
- 主库逻辑保持不变, 只是 cursor 管理更精细 (每次循环内创建和关闭)
- 主库全部写完后, 再用同样逻辑写副库
- 副库整体包在 try/except 中, 失败不影响返回值

#### 子模式 C3: DDL (CREATE TABLE)

**改造前**:

```python
from config.db import get_connection

def create_factor_table():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(CREATE_TABLE_SQL)
    conn.commit()
    cursor.close()
    conn.close()
```

**改造后**:

```python
from config.db import get_connection, get_dual_connections

def create_factor_table():
    conn, conn2 = get_dual_connections()
    try:
        cursor = conn.cursor()
        cursor.execute(CREATE_TABLE_SQL)
        conn.commit()
        cursor.close()
    finally:
        conn.close()
    if conn2:
        try:
            cursor2 = conn2.cursor()
            cursor2.execute(CREATE_TABLE_SQL)
            conn2.commit()
            cursor2.close()
        except Exception as e:
            logger.warning("Dual-write CREATE TABLE failed: %s", e)
        finally:
            conn2.close()
```

要点:
- DDL 用 `CREATE TABLE IF NOT EXISTS`, 所以副库失败不影响主库
- 主库用 `try/finally` 确保关闭, 副库用 `try/except` 吞掉异常

---

## 5. 带自定义 env 参数的场景

有些模块原来就有 `env` 参数 (比如 `RPSStorage(env='online')`), 双写时需要保留主库 env:

### 5.1 execute_dual_many 带固定 env

```python
# 原来: execute_many(self.UPSERT_SQL, batch, env=self.env)
# 改后:
execute_dual_many(self.UPSERT_SQL, batch, env=self.env)
```

`execute_dual_many` 会自动根据 `DUAL_WRITE` 配置决定是否写副库。

### 5.2 get_dual_connections 指定主库

```python
# 原来: conn = get_connection(self.env)
# 改后:
conn, conn2 = get_dual_connections(primary_env=self.env, secondary_env=None)
```

传 `secondary_env=None` 表示 "使用 DUAL_WRITE 配置决定是否创建副库连接"。

---

## 6. 不需要改造的文件

| 类型 | 原因 |
|------|------|
| `execute_query()` 调用 | 只读, 不涉及写入 |
| `qmt_fetcher.py` | QMT 在 Windows 端写 `trade_stock_daily`, 这张表由 QMT 自己管理 |
| `akshare_fetcher.py` | 写 `trade_stock_daily`, 同上 |
| `tushare_fetcher.py` | 写 `trade_stock_daily`, 同上 |
| `etf_fetcher.py` | 写 `etf_daily`, 同上 |
| `paper_trading/` | 模拟交易状态, 只需本地 |

---

## 7. Windows 端改造检查清单

### 第一步: 确认 config/db.py 已同步

Windows 端的 `config/db.py` 需要包含新增的 5 个函数和 2 个配置变量。直接从 Mac 端复制即可。

关键检查点:

```python
# 文件头部新增 import
import time
import logging
from typing import Optional, Tuple

# 配置变量
DUAL_WRITE = os.getenv('DUAL_WRITE', 'false').lower() == 'true'
DUAL_WRITE_TARGET = os.getenv('DUAL_WRITE_TARGET', 'online')
logger = logging.getLogger(__name__)

# 5 个新函数
get_dual_connections()
dual_executemany()
dual_execute()
execute_dual_update()
execute_dual_many()
```

### 第二步: 逐文件排查写操作

在 Windows 端代码中搜索所有写操作:

```bash
# 搜索所有使用 get_connection 的文件
grep -rn "get_connection" --include="*.py" .

# 搜索所有使用 execute_many 的文件
grep -rn "execute_many" --include="*.py" .

# 搜索所有使用 execute_update 的文件
grep -rn "execute_update" --include="*.py" .
```

对每个文件判断:

1. 是否是写操作 (有 `cursor.execute` 写类 SQL / `executemany` / `commit`)
2. 是否在排除列表中 (QMT 管理的 3 张表)
3. 如果是写操作且不在排除列表中, 按上面的模式改造

### 第三步: 配置 .env

```bash
# Windows 端: primary=online, secondary=local
DB_ENV=online
DUAL_WRITE=true
DUAL_WRITE_TARGET=local

# 确保 LOCAL_DB_* 指向 192.168.97.1
LOCAL_DB_HOST=192.168.97.1
LOCAL_DB_PORT=3306
LOCAL_DB_USER=xxx
LOCAL_DB_PASSWORD=xxx
LOCAL_DB_NAME=mytrader

# 确保 ONLINE_DB_* 指向 123.56.3.1
ONLINE_DB_HOST=123.56.3.1
ONLINE_DB_PORT=3306
ONLINE_DB_USER=xxx
ONLINE_DB_PASSWORD=xxx
ONLINE_DB_NAME=trade
```

### 第四步: 验证

1. 先不开双写 (`DUAL_WRITE=false`), 运行一次确认功能正常
2. 开启双写 (`DUAL_WRITE=true`), 运行一次
3. 检查两边数据库的行数是否一致:

```sql
-- 在 local 和 online 分别执行
SELECT COUNT(*) FROM trade_stock_daily_basic;
SELECT COUNT(*) FROM trade_stock_basic_factor;
```

4. 断开副库 (比如关掉副库 MySQL), 运行一次, 确认主库正常写入, 日志中有 warning
5. 恢复副库, 运行一次, 确认两边数据再次同步

---

## 8. 失败策略说明

```
主库写入
  |
  +-- 成功 --> 副库写入
  |               |
  |               +-- 成功 --> 完成
  |               |
  |               +-- 失败 --> 等 1 秒 --> 重试一次
  |                                   |
  |                                   +-- 成功 --> 完成
  |                                   |
  |                                   +-- 失败 --> logger.warning() --> 完成 (不抛异常)
  |
  +-- 失败 --> 抛异常 (原有行为不变)
```

- 主库失败: 直接抛异常, 与改造前行为完全一致
- 副库失败: 重试 1 次 (间隔 1 秒), 仍失败则记录 warning 日志, **不影响主流程**
- 副库连接失败: `get_dual_connections()` 中创建副库连接时如果抛异常, 会直接被外层 try/except 捕获, `conn2` 为 `None`, 跳过副库写入

---

## 9. 完整改造示例 (从零开始)

假设有一个新的写入模块 `data_writer.py`, 原始代码如下:

```python
# -*- coding: utf-8 -*-
from config.db import get_connection, execute_query

def save_results(results: list):
    """保存计算结果到数据库"""
    conn = get_connection()
    cursor = conn.cursor()

    sql = """
        INSERT INTO my_results (stock_code, date, value)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE value = VALUES(value)
    """
    cursor.executemany(sql, results)
    conn.commit()
    cursor.close()
    conn.close()
    return len(results)


def ensure_table():
    """确保表存在"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS my_results (
            stock_code VARCHAR(20) NOT NULL,
            date DATE NOT NULL,
            value DOUBLE,
            PRIMARY KEY (stock_code, date)
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()


def get_latest():
    """查询最新数据 (只读, 不需要改造)"""
    return execute_query("SELECT * FROM my_results ORDER BY date DESC LIMIT 10")
```

改造后的完整代码:

```python
# -*- coding: utf-8 -*-
import logging

from config.db import get_connection, execute_query, get_dual_connections, dual_executemany

logger = logging.getLogger(__name__)


def save_results(results: list):
    """保存计算结果到数据库"""
    if not results:
        return 0

    conn, conn2 = get_dual_connections()
    try:
        sql = """
            INSERT INTO my_results (stock_code, date, value)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE value = VALUES(value)
        """
        dual_executemany(conn, conn2, sql, results, _logger=logger)
    finally:
        conn.close()
    return len(results)


def ensure_table():
    """确保表存在"""
    conn, conn2 = get_dual_connections()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS my_results (
                stock_code VARCHAR(20) NOT NULL,
                date DATE NOT NULL,
                value DOUBLE,
                PRIMARY KEY (stock_code, date)
            )
        """)
        conn.commit()
        cursor.close()
    finally:
        conn.close()
    if conn2:
        try:
            cursor2 = conn2.cursor()
            cursor2.execute("""
                CREATE TABLE IF NOT EXISTS my_results (
                    stock_code VARCHAR(20) NOT NULL,
                    date DATE NOT NULL,
                    value DOUBLE,
                    PRIMARY KEY (stock_code, date)
                )
            """)
            conn2.commit()
            cursor2.close()
        except Exception as e:
            logger.warning("Dual-write CREATE TABLE failed: %s", e)
        finally:
            conn2.close()


def get_latest():
    """查询最新数据 (只读, 不需要改造)"""
    return execute_query("SELECT * FROM my_results ORDER BY date DESC LIMIT 10")
```

改造点汇总:

| 函数 | 改造内容 |
|------|---------|
| `save_results` | `get_connection()` -> `get_dual_connections()`, 用 `dual_executemany` |
| `ensure_table` | 同上, DDL 手动写副库逻辑 |
| `get_latest` | **不改造**, 只读操作 |
