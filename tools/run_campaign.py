"""One-command end-to-end acceptance run: play all three scenarios with the robot.

    python tools/run_campaign.py
"""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from ahlcg.ai import robot
from ahlcg.campaign import CampaignState
from ahlcg.campaign.game_builder import build_scenario_game
from ahlcg.data.deck import build_starter_deck
from ahlcg.data.pool import CardPool

INVESTIGATORS = ["01001", "01002", "01003", "01004", "01005"]
NAMES = {"01001": "罗兰·班克斯", "01002": "黛西·沃克", "01003": "斯基兹·奥图尔",
         "01004": "阿格尼丝·贝克", "01005": "温迪·亚当斯"}


def main() -> int:
    pool = CardPool.load()
    decks = [list(build_starter_deck(pool, code).cards) for code in INVESTIGATORS]
    campaign = CampaignState.new("night_of_the_zealot", INVESTIGATORS, "standard", decks=decks, seed=7)

    print("=" * 66)
    print("狂热者之夜：三幕连贯试玩（机器人）")
    print("调查员：" + "、".join(NAMES[c] for c in INVESTIGATORS))
    print("=" * 66)

    while campaign.scenario_code() is not None:
        name = campaign.scenario_name()
        print(f"\n--- 第 {campaign.scenario_index + 1} 幕：{name} ---")
        game = build_scenario_game(campaign, pool)
        report = robot.play(game, max_steps=80000)
        print(f"    （机器人走了 {report.get('steps', '?')} 步）")
        resolution = campaign.apply_resolution(game)
        print(f"    结局：{resolution.get('resolution', '（无）')} — {resolution.get('title', '')}")
        for investigator in campaign.investigators:
            state = "存活" if investigator.is_active else ("被杀" if investigator.killed else "疯狂")
            print(f"    {investigator.name}：{state}，创伤 伤害{investigator.trauma_physical}/恐惧{investigator.trauma_mental}，经验 {investigator.xp_earned}")
        if campaign.scenario_code() is not None:
            campaign.advance()

    print("\n" + "=" * 66)
    print("战役结束。结局记录：")
    for section, entries in (campaign.log or {}).items():
        for entry in entries:
            print(f"  [{section}] {entry}")
    alive = [i for i in campaign.investigators if i.is_active]
    print(f"存活调查员：{len(alive)} / {len(campaign.investigators)}")
    print("=" * 66)
    return 0 if alive or campaign.scenario_index >= 3 else 1


if __name__ == "__main__":
    raise SystemExit(main())
