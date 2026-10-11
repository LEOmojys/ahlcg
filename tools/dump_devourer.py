import json, sys
sys.stdout.reconfigure(encoding="utf-8")
data = json.loads(open("reference/notz_scenario_data.json", encoding="utf-8").read())
cards = data["tentacles"]["cards"]
for code, c in sorted(cards.items()):
    stats = []
    for k, label in (("shroud", "遮蔽"), ("clues", "线索"), ("doom", "毁灭阈值"), ("victory", "胜利点"),
                     ("enemy_fight", "战力"), ("enemy_evade", "闪避"), ("health", "生命"),
                     ("enemy_damage", "伤害"), ("enemy_horror", "恐惧"), ("quantity", "张数"),
                     ("health_per_investigator", "生命按人数")):
        if c.get(k) not in (None, "", 0, False):
            stats.append(f"{label}={c[k]}")
    print(f"[{code}] {c.get('type_code')} {c.get('name')}  {' '.join(stats)}")
    text = (c.get("real_text") or "").strip()
    back = (c.get("back_text") or "").strip()
    if text:
        print("   ", " | ".join(text.splitlines()))
    if back:
        print("   BACK:", " | ".join(back.splitlines()))
