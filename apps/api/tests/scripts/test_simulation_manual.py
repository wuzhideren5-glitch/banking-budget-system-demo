"""Manual end-to-end check for the simulation-result API."""
import json
import http.cookiejar
import urllib.request


def api(opener: urllib.request.OpenerDirector, method: str, path: str, body=None):
    url = f"http://127.0.0.1:8009{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        r = opener.open(req)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {"error": str(e)}


def main() -> int:
    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPCookieProcessor(cookie_jar),
    )

    print("=== Step 1: Login ===")
    logged_in = False
    for user, pwd in [
        ("Arthur", "Arthur2026"),
        ("Arthur", "Abc12345"),
        ("admin", "Abc12345"),
        ("kevinchen", "Abc12345"),
    ]:
        status, resp = api(opener, "POST", "/api/login", {"user_name": user, "password": pwd})
        print(f"  Login {user}: {status} {resp}")
        if status == 200:
            logged_in = True
            break
    if not logged_in:
        raise SystemExit("Login failed for all test users")

    print()
    print("=== Step 2: Get simulation result ===")
    status, rows = api(opener, "POST", "/api/budget-simulation/result", [])
    print(f"  Status: {status}")
    if status == 200:
        print(f"  Rows: {len(rows)}")
        for row in rows[:10]:
            print(f"  {row['metric_group']}: {row['indicator_code']} {row['indicator_name']}")
        return 0
    print(f"  Error: {rows}")
    raise SystemExit("Simulation result request failed")


if __name__ == "__main__":
    raise SystemExit(main())
