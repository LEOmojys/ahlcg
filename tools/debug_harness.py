import importlib, sys
sys.path.insert(0, ".")
sys.path.insert(0, "tests")
sys.stdout.reconfigure(encoding="utf-8")
m = importlib.import_module("test_core_set_player")

game, player, inv, here = m.base_game(combat=4)
weapon = m.put_in_play(game.state, player, "01016")
enemy = m.make_enemy(game.state, health=4)
m.Drive(game.engage(enemy, player)).run()
print("hand size:", len(player.hand), "| play area:", [game.state.cards[c].code for c in player.play_area])
print("pending before fight:", [c.prompt[:40] for c in game.state.pending])

from ahlcg.engine.actions import execute_action
gen = execute_action(game, player, "fight:" + enemy.id)
prompts = []
try:
    ch = next(gen)
    while len(prompts) < 8:
        prompts.append((ch.kind.value, ch.prompt[:70], [o.id[:14] for o in ch.options][:4]))
        try:
            ch = gen.send(())
        except StopIteration:
            break
except StopIteration:
    pass
except Exception as exc:
    print("EXCEPTION:", type(exc).__name__, exc)
for p in prompts:
    print("  prompt:", p)
print("damage:", enemy.damage, "| skill_test:", game.state.skill_test)
