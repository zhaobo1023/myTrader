# 授予 mytrader_user DDL 权限

## 问题说明

mytrader_user 需要建表和建索引的权限才能运行数据库迁移（Alembic）和创建表。

## 权限说明

需要授予以下权限：
- **CREATE**: 创建表
- **INDEX**: 创建索引
- **ALTER**: 修改表结构（包括添加/删除索引）
- **DROP**: 删除表（可选，开发环境需要）

## 方法一：使用 Python 脚本（推荐）

```bash
# 1. 设置 root 密码环境变量
export MYSQL_ROOT_PASSWORD=your_root_password

# 2. 运行授权脚本
python scripts/grant_ddl_privileges.py
```

## 方法二：手动执行 SQL

```bash
# 1. 以 root 用户登录 MySQL
mysql -u root -p -h localhost trade

# 2. 执行以下 SQL 语句
GRANT CREATE ON trade.* TO 'mytrader_user'@'%';
GRANT INDEX ON trade.* TO 'mytrader_user'@'%';
GRANT ALTER ON trade.* TO 'mytrader_user'@'%';
GRANT DROP ON trade.* TO 'mytrader_user'@'%';
FLUSH PRIVILEGES;

# 3. 查看授权结果
SHOW GRANTS FOR 'mytrader_user'@'%';
```

## 方法三：使用 SQL 文件

```bash
# 1. 输入 root 密码执行
mysql -u root -p -h localhost trade < scripts/grant_ddl_privileges.sql
```

## 验证权限

授权后，可以运行以下命令验证：

```bash
# 测试建表权限
python -c "
from config.db import get_connection
conn = get_connection()
cursor = conn.cursor()
cursor.execute('CREATE TABLE IF NOT EXISTS test_table (id INT)')
cursor.execute('DROP TABLE IF EXISTS test_table')
print('DDL 权限测试通过!')
"
```

## 常见问题

### Q: 为什么需要这些权限？
A: Alembic 数据库迁移需要 CREATE、ALTER、INDEX 权限来创建和修改表结构。

### Q: DROP 权限是必须的吗？
A: 开发环境建议授予，生产环境可以不授予。但 Alembic 的 downgrade 操作需要 DROP 权限。

### Q: 授权后仍报错权限不足？
A: 检查以下几点：
1. 确认 FLUSH PRIVILEGES 已执行
2. 检查连接的用户和主机是否正确（'mytrader_user'@'%'）
3. 检查数据库名是否正确（trade）
