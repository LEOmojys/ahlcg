import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")
from ahlcg.ai import robot
from ahlcg.campaign import CampaignState
from ahlcg.campaign.game_builder import build_scenario_game
from ahlcg.data.pool import CardPool

pool = CardPool.load()
campaign = CampaignState.new("night_of_the_zealot", ("01001",), "standard", seed=11, pool=pool)
game = build_scenario_game(campaign, pool)
print("pending after build:", (game.awaiting.prompt[:40] if game.awaiting else None))
report = robot.play(game, max_steps=40000)
print("report:", report)
print("resolution:", game.state.resolution, "| log tail:", [e.text for e in game.state.log_entries[-4:]])
inv = campaign.investigators[0]
print("campaign investigator before apply: killed=%s insane=%s trauma=%s/%s" % (inv.killed, inv.insane, inv.trauma_physical, inv.trauma_mental))
summary = campaign.apply_resolution(game)
print("summary:", {k: summary[k] for k in list(summary)[:8]})
inv = campaign.investigators[0]
print("after apply: killed=%s insane=%s trauma=%s/%s" % (inv.killed, inv.insane, inv.trauma_physical, inv.trauma_mental))
print("active investigators:", campaign.active_investigators())
campaign.advance()
try:
    g2 = build_scenario_game(campaign, pool)
    print("scenario 2 built:", g2.state.scenario_code)
except Exception as exc:
    print("scenario 2 FAILED:", type(exc).__name__, exc)
