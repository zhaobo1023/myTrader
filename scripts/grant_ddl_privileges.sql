-- 授予 mytrader_user 建表和建索引的权限
-- 需要以 root 用户执行此脚本

-- 授予创建表的权限
GRANT CREATE ON trade.* TO 'mytrader_user'@'%';

-- 授予创建索引的权限
GRANT INDEX ON trade.* TO 'mytrader_user'@'%';

-- 授予修改表结构的权限（包括添加/删除索引）
GRANT ALTER ON trade.* TO 'mytrader_user'@'%';

-- 授予删除表的权限（可选，开发环境通常需要）
GRANT DROP ON trade.* TO 'mytrader_user'@'%';

-- 刷新权限
FLUSH PRIVILEGES;

-- 查看当前权限
SHOW GRANTS FOR 'mytrader_user'@'%';
