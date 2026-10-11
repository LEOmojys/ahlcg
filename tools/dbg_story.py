import sys, pathlib
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")
from ahlcg.campaign.night_of_the_zealot import scenario_intro
print("direct intro:", repr(scenario_intro("torch"))[:80])
from ahlcg.web.sessions import SessionStore
from ahlcg.data.pool import CardPool
pool = CardPool.load()
store = SessionStore(pool)
s = store.create("01001", "standard", 5)
from ahlcg.web.view import _scenario_story
print("state.scenario_code:", s.game.state.scenario_code)
try:
    t = _scenario_story(s.game.state, s)
    print("_scenario_story:", repr(t)[:80], "len", len(t))
except Exception as exc:
    import traceback; traceback.print_exc()
