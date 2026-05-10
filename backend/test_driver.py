"""端到端测试：预算预测驱动模块 M04 驱动参数导入 → 验证计算链路"""
import json
import os
import sys
import urllib.request
import http.cookiejar

# 1. Login
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

def api(method, path, body=None):
    url = f"http://127.0.0.1:8001{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        r = opener.open(req)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {"error": str(e)}

print("=== Step 1: Login ===")
# Try the credentials from the running frontend
for user, pwd in [("Arthur", "Abc12345"), ("admin", "Abc12345"), ("kevinchen", "Abc12345")]:
    status, resp = api("POST", "/api/login", {"user_name": user, "password": pwd})
    print(f"  Login {user}: {status} {resp}")
    if status == 200:
        break

print()
print("=== Step 2: Get driver categories ===")
status, cats = api("GET", "/api/driver/categories")
print(f"  Status: {status}")
if status == 200:
    for cat in cats:
        print(f"  {cat['category_code']}: {cat['category_name']} ({len(cat['indicators'])} indicators)")
        for ind in cat["indicators"]:
            print(f"    - {ind['indicator_code']}: {ind['indicator_name']} (products: {len(ind['products'])})")
else:
    print(f"  Error: {cats}")
