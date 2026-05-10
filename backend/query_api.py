import urllib.request, json

def get(path):
    r = urllib.request.urlopen(f'http://127.0.0.1:8001{path}')
    return json.loads(r.read())

# Get data accounts
das = get('/api/data-accounts')
print("=== DATA ACCOUNTS ===")
for d in das:
    bf = (d.get('budget_formula') or '')[:80]
    af = (d.get('actual_formula') or '')[:80]
    pc = str(d.get('product_codes'))
    if pc == 'None': pc = 'NULL(ALL)'
    elif pc == '': pc = 'EMPTY(co)'
    print(f"{d['data_acct_code']:8s} | {d['data_acct_name']:35s} | {d['value_type']:6s} | pc={pc:20s} | bf={bf}")

print()
print("=== PRODUCTS ===")
prods = get('/api/product-types')
for p in prods:
    par = str(p.get('parent_code') or '-')
    print(f"{p['product_code']:10s} | {p['product_name']:30s} | parent={par:8s} | lv={p.get('level',1)}")
