import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")
from ahlcg.core.enums import ChoiceKind, Skill, Zone
from ahlcg.data.pool import CardPool
from ahlcg.engine.actions import execute_action
from ahlcg.engine.chaos import ChaosBag, numeric
from ahlcg.session import GameSetup, create_game

pool = CardPool.load()
game = create_game(GameSetup(pool=pool, seed=3))
game.start()
state = game.state
player = state.players[0]
inv = state.investigator_of(player)
state.flags["mulligan"] = False
player.hand.clear()
weapon = state.add_card(pool.get("01016"), zone=Zone.PLAY, controller_id=player.id)
player.play_area.append(weapon.id)
state.chaos_bag = ChaosBag.from_tokens([numeric(0)])

ghoul = state.add_card(pool.get("01160"), zone=Zone.PLAY, location_id=inv.meta["location_id"])
ghoul.defn.fight = 2  # make the test deterministic
print("ghoul fight:", game.enemy_fight(ghoul), "investigator combat:", inv.defn.combat)

gen = execute_action(game, player, f"fight:{ghoul.id}")
step = 0
try:
    choice = next(gen)
    while True:
        step += 1
        picked = ()
        if choice.kind is ChoiceKind.COMMIT:
            picked = ()
        elif choice.options:
            picked = (choice.options[0].id,)
        print(f"  prompt[{step}] kind={choice.kind.value}: {choice.prompt[:60]} -> {picked}")
        choice = gen.send(picked)
except StopIteration:
    pass
print("enemy damage:", ghoul.damage)
print("skill test seen:", state.skill_test)
print("weapon uses:", weapon.uses, "| weapon exhausted:", weapon.exhausted)
