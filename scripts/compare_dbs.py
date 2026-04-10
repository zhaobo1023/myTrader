"""Compare tables between local and online databases."""
import os
import pymysql
from pymysql.cursors import DictCursor
from dotenv import load_dotenv

load_dotenv(override=True)


def get_tables(host, port, user, password, db):
    conn = pymysql.connect(host=host, port=port, user=user, password=password,
                           database=db, charset='utf8mb4', connect_timeout=10,
                           cursorclass=DictCursor)
    cursor = conn.cursor()
    cursor.execute('SHOW TABLE STATUS FROM `%s`' % db)
    tables = cursor.fetchall()
    cursor.close()
    conn.close()
    return tables


local_tables = get_tables('192.168.97.1', 3306, 'quant_user', 'Quant@2024User', 'wucai_trade')
online_tables = get_tables('123.56.3.1', 3306, 'mytrader_user', 'lGgS^uruPhv%AK0ZifeC', 'trade')

local_map = {t['Name']: t for t in local_tables}
online_map = {t['Name']: t for t in online_tables}

all_tables = sorted(set(list(local_map.keys()) + list(online_map.keys())))

header = "{:<50} {:>12} {:>12} {:>12}  {}".format("Table", "Local Rows", "Online Rows", "Diff", "Status")
print(header)
print("-" * 105)

for name in all_tables:
    lt = local_map.get(name)
    ot = online_map.get(name)
    lr = lt['Rows'] if lt else 0
    orr = ot['Rows'] if ot else 0
    diff = orr - lr

    if lt and ot:
        if lr == 0 and orr == 0:
            status = "BOTH EMPTY"
        elif diff == 0:
            status = "SAME"
        elif diff > 0:
            status = "ONLINE > LOCAL"
        else:
            status = "LOCAL > ONLINE"
    elif lt:
        status = "LOCAL ONLY"
    else:
        status = "ONLINE ONLY"

    diff_str = "{:+,}".format(diff) if (lt and ot) else "-"
    print("{:<50} {:>12,} {:>12,} {:>12}  {}".format(name, lr, orr, diff_str, status))

print("-" * 105)
total_local = sum(t['Rows'] for t in local_tables)
total_online = sum(t['Rows'] for t in online_tables)
print("{:<50} {:>12,} {:>12,} {:>+12,}".format("TOTAL", total_local, total_online, total_online - total_local))
print("Local tables: {}  |  Online tables: {}".format(len(local_tables), len(online_tables)))
