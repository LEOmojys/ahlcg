import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")
from fastapi.testclient import TestClient
from ahlcg.data.pool import CardPool
from ahlcg.web.app import create_app
from ahlcg.web.cardimages import store_from_environment

pool = CardPool.load()
store = store_from_environment()
store.enabled = False
app = create_app(pool, image_store=store)
c = TestClient(app)

try:
    print("GET /            ->", c.get("/").status_code)
except Exception as exc:
    print("GET /            -> 失败:", type(exc).__name__, str(exc)[:110])

r = c.get("/api/pool")
print("GET /api/pool    ->", r.status_code, str(r.json())[:160] if r.status_code == 200 else r.text[:160])

r = c.post("/api/campaign/new", json={"investigator_code": "01001", "difficulty": "standard"})
print("POST new         ->", r.status_code, (str(r.json())[:160] if r.status_code == 200 else r.text[:200]))
body = r.json() if r.status_code == 200 else {}
sid = body.get("session_id") or (body.get("view") or {}).get("session_id")
print("session:", sid)

v = c.get("/api/state", params={"session": sid})
view = v.json().get("view", v.json()) if v.status_code == 200 else {}
sc = view.get("scenario", {})
print("GET state        ->", v.status_code, "|", sc.get("name"), "round", sc.get("round"), sc.get("phase"))
print("hand:", [h.get("name") for h in view.get("hand", [])][:6])
print("locations:", [(l.get("name"), l.get("clues")) for l in view.get("locations", [])])
print("chaos tokens:", len(view.get("chaos_bag", [])), "| act:", (view.get("act") or {}).get("name"),
      "| agenda:", (view.get("agenda") or {}).get("name"))
ch = view.get("choice") or {}
print("choice prompt:", ch.get("prompt"))
print("choice options:", [o.get("label") for o in ch.get("options", [])][:8])

if ch:
    rr = c.post("/api/choice", json={"session_id": sid, "choice_id": ch["id"], "selected": ["investigate"]})
    print("POST choice      ->", rr.status_code)
    if rr.status_code == 200:
        v2 = rr.json().get("view", {})
        print("  after investigate:", str(v2.get("last_skill_test"))[:200])
        print("  log tail:", [e.get("text") for e in v2.get("log", [])][:4])
    else:
        print("  ", rr.text[:300])
