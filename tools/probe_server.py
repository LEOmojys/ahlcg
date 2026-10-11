import json, sys, urllib.request
sys.stdout.reconfigure(encoding="utf-8")
BASE = "http://127.0.0.1:8765"

def get(path):
    with urllib.request.urlopen(BASE + path, timeout=25) as r:
        return r.status, r.read()

try:
    status, body = get("/")
    text = body.decode("utf-8", "replace")
    print("GET /        ->", status, len(body), "bytes")
    print("   含「诡镇奇谈」:", "诡镇奇谈" in text)
    print("   含选择面板 id=choice:", 'id="choice"' in text)
    print("   含开始按钮:", "开始战役" in text)
except Exception as exc:
    print("GET /        -> 失败:", type(exc).__name__, exc)

try:
    status, body = get("/api/pool")
    data = json.loads(body)
    print("GET /api/pool->", status)
    print("   调查员:", [i.get("name_zh") or i.get("name") for i in data.get("investigators", [])])
    print("   难度:", data.get("difficulties"))
    print("   剧本科目:", data.get("scenarios"))
except Exception as exc:
    print("GET /api/pool-> 失败:", type(exc).__name__, exc)

try:
    req = urllib.request.Request(
        BASE + "/api/campaign/new",
        data=json.dumps({"investigator_code": "01004", "difficulty": "easy"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=40) as r:
        data = json.loads(r.read())
    print("POST new     ->", r.status, "| session:", data.get("session_id"))
    view = data["view"]
    print("   调查员:", view["investigator"]["name"], "| 幕:", (view.get("act") or {}).get("name"),
          "| 阴谋:", (view.get("agenda") or {}).get("name"))
    print("   手牌:", [c["name"] for c in view.get("hand", [])])
    print("   选择:", (view.get("choice") or {}).get("prompt"))
except Exception as exc:
    print("POST new     -> 失败:", type(exc).__name__, exc)
