import sqlite3, os
conn = sqlite3.connect(os.path.join(os.path.dirname(__file__), 'data', 'common.db'))
cur = conn.cursor()

print("=== DATA ACCOUNTS ===")
rows = cur.execute('SELECT data_acct_code, data_acct_name, value_type, budget_formula, actual_formula, product_codes FROM data_account ORDER BY data_acct_code').fetchall()
for r in rows:
    bf = (r[3] or '')[:80]
    pc = str(r[5])
    if pc == 'None': pc = 'NULL(ALL)'
    elif pc == '': pc = 'EMPTY(company)'
    print(f'{r[0]:8s} | {r[1]:35s} | {r[2]:6s} | bf={bf} | pc={pc}')

print()
print("=== PRODUCTS ===")
for r in cur.execute('SELECT product_code, product_name, parent_code, level FROM product_type ORDER BY product_code').fetchall():
    pc = str(r[2])
    if pc == 'None': pc = '-'
    print(f'{r[0]:10s} | {r[1]:30s} | parent={pc:8s} | lv={r[3]}')

conn.close()
