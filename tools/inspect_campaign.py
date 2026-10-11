import inspect, sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")
import ahlcg.campaign as C
import ahlcg.campaign.game_builder as GB
import ahlcg.campaign.night_of_the_zealot as NZ

print("=== ahlcg.campaign ===")
print([n for n in dir(C) if not n.startswith("_")])
for name in ("CampaignState", "build_scenario_game", "CAMPAIGNS", "create_campaign"):
    obj = getattr(C, name, None)
    if obj is None:
        print(f"  {name}: (不存在)")
        continue
    if callable(obj):
        try:
            print(f"  {name}{inspect.signature(obj)}")
        except Exception as exc:
            print(f"  {name}: {exc}")
    else:
        print(f"  {name} = {obj}")

print("\n=== game_builder ===")
print([n for n in dir(GB) if not n.startswith("_")])
for name in ("build_scenario_game", "scenario_code_for"):
    obj = getattr(GB, name, None)
    if callable(obj):
        try:
            print(f"  {name}{inspect.signature(obj)}")
        except Exception as exc:
            print(f"  {name}: {exc}")

print("\n=== night_of_the_zealot ===")
print([n for n in dir(NZ) if not n.startswith("_")])

print("\n=== CampaignState 方法 ===")
for name in ("new", "scenario_code", "apply_resolution", "advance", "spend_xp", "to_dict", "from_dict"):
    obj = getattr(C.CampaignState, name, None)
    if obj is None:
        print(f"  {name}: (不存在)")
        continue
    try:
        print(f"  {name}{inspect.signature(obj)}")
    except Exception as exc:
        print(f"  {name}: {exc}")
