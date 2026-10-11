import json, sys, time, urllib.request
sys.stdout.reconfigure(encoding="utf-8")
B = "http://127.0.0.1:8770"

def alive():
    try:
        with urllib.request.urlopen(B + "/api/pool", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False

def post(path, payload):
    req = urllib.request.Request(B + path, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())

for _ in range(30):
    if alive():
        break
    time.sleep(1)
print("1) 服务已启动:", alive())

# emulate a real page: ping every 2 seconds for 11 seconds (well past the 8s threshold)
deadline = time.time() + 11
while time.time() < deadline:
    post("/api/ping", {"client": "tab"})
    time.sleep(2)
print("2) 页面持续心跳 11 秒（超过 8 秒阈值）仍在运行:", alive())

post("/api/bye", {"client": "tab"})
start = time.time()
while time.time() - start < 30:
    if not alive():
        print(f"3) 页面关闭后 {time.time() - start:.1f} 秒自动退出 ✓")
        raise SystemExit(0)
    time.sleep(0.5)
print("3) 30 秒后仍未退出 ✗")
raise SystemExit(1)
