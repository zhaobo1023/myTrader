#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
授予 mytrader_user 建表和建索引权限的脚本

使用方法:
1. 设置环境变量: export MYSQL_ROOT_PASSWORD=your_root_password
2. 运行脚本: python scripts/grant_ddl_privileges.py
"""
import os
import sys
import pymysql

def grant_privileges():
    """授予 DDL 权限"""
    print("=== 授予 mytrader_user DDL 权限 ===")
    print()

    # 从环境变量获取 root 密码
    root_password = os.getenv('MYSQL_ROOT_PASSWORD')
    if not root_password:
        print("错误: 请设置环境变量 MYSQL_ROOT_PASSWORD")
        print("使用方法:")
        print("  export MYSQL_ROOT_PASSWORD=your_root_password")
        print("  python scripts/grant_ddl_privileges.py")
        return False

    try:
        # 连接数据库
        print("连接数据库...")
        conn = pymysql.connect(
            host='localhost',
            port=3306,
            user='root',
            password=root_password,
            database='mysql'
        )
        cursor = conn.cursor()

        # 授权语句
        grants = [
            "GRANT CREATE ON trade.* TO 'mytrader_user'@'%'",
            "GRANT INDEX ON trade.* TO 'mytrader_user'@'%'",
            "GRANT ALTER ON trade.* TO 'mytrader_user'@'%'",
            "GRANT DROP ON trade.* TO 'mytrader_user'@'%'",
        ]

        print("\n执行授权:")
        for grant in grants:
            print(f"  {grant}")
            cursor.execute(grant)

        # 刷新权限
        print("\n刷新权限...")
        cursor.execute("FLUSH PRIVILEGES")

        # 查看授权结果
        print("\n当前 mytrader_user 的权限:")
        cursor.execute("SHOW GRANTS FOR 'mytrader_user'@'%'")
        results = cursor.fetchall()
        for result in results:
            print(f"  {result[0]}")

        cursor.close()
        conn.close()

        print("\n[OK] 授权成功!")

    except Exception as e:
        print(f"\n[ERROR] 授权失败: {e}")
        return False

    return True

if __name__ == "__main__":
    grant_privileges()
