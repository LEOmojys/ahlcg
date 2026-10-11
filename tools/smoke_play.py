import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")
from fastapi.testclient import TestClient
from ahlcg.data.pool import CardPool
from ahlcg.web.app import create_app
from ahlcg.web.cardimages import store_from_environment

store = store_from_environment(); store.enabled = False
c = TestClient(create_app(CardPool.load(), image_store=store), raise_server_exceptions=False)
sid = c.post("/api/campaign/new", json={"investigator_code": "01001", "difficulty": "standard"}).json()["session_id"]

for step in range(6):
    view = c.get("/api/state", params={"session": sid}).json()["view"]
    ch = view.get("choice")
    if not ch:
        print(step, "no choice; finished =", view.get("scenario", {}).get("finished"))
        break
    print(f"[{step}] kind={ch.get('kind')} prompt={ch.get('prompt')[:60]}")
    opts = [o for o in ch.get("options", []) if not o.get("disabled")]
    pick = None
    for want in ("investigate", "yes", "advance_act"):
        for o in opts:
            if o["id"] == want:
                pick = o["id"]; break
        if pick: break
    if pick is None:
        pick = opts[0]["id"] if opts else None
    if pick is None:
        print("   (no usable option, cancelling)" if ch.get("optional") else "   (stuck)")
        body = {"session_id": sid, "choice_id": ch["id"], "selected": [], "cancelled": True}
    else:
        print("   ->", pick)
        body = {"session_id": sid, "choice_id": ch["id"], "selected": [pick]}
    r = c.post("/api/choice", json=body)
    if r.status_code != 200:
        print("   HTTP", r.status_code, r.text[:200]); break
    v = r.json()["view"]
    st = v.get("last_skill_test")
    if st:
        print("   检定:", st.get("text") or (str(st.get("skill")) + " " + str(st.get("total")) + " vs " + str(st.get("difficulty")) + " success=" + str(st.get("success"))))
    clues = [l.get("clues") for l in v.get("locations", [])]
    inv = v.get("investigator", {})
    print("   线索:", clues, "| 调查员线索:", inv.get("clues"), "| 行动:", inv.get("actions_left"), "| 资源:", inv.get("resources"))
