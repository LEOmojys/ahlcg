"""Encounter card behaviour for 第二章《午夜面具》(The Midnight Masks).

Text quoted from the printed cards.  Registered from ahlcg/cards/__init__.py.
"""

from __future__ import annotations

from ..core.cards import Ability
from ..core.choices import ChoiceOption, PendingChoice
from ..core.enums import AbilityKind, CardType, ChoiceKind, Skill, TokenType, Trigger, Zone
from ..engine.actions import register_location_action
from . import register


def _investigator(ctx):
    return ctx.payload.get("investigator")


def _cultists(ctx):
    return [e for e in ctx.state.enemies() if "cultist" in e.defn.traits]


def _distance(state, start: str, goal: str) -> int:
    """Breadth first distance between two locations (for 'nearest')."""
    if start == goal:
        return 0
    seen = {start}
    frontier = [(start, 0)]
    while frontier:
        node, dist = frontier.pop(0)
        for nxt in state.connections_of(node):
            if nxt in seen:
                continue
            if nxt == goal:
                return dist + 1
            seen.add(nxt)
            frontier.append((nxt, dist + 1))
    return 99


def nearest_cultist(ctx, investigator):
    """The Cultist enemy reachable in the fewest connections."""
    location_id = investigator.meta.get("location_id")
    best = None
    best_dist = 999
    for enemy in _cultists(ctx):
        where = enemy.location_id
        if where is None and enemy.engaged_with:
            for player in ctx.state.players:
                if player.id in enemy.engaged_with:
                    where = ctx.state.investigator_of(player).meta.get("location_id")
        if where is None:
            continue
        dist = _distance(ctx.state, location_id, where) if location_id else 0
        if dist < best_dist:
            best, best_dist = enemy, dist
    return best


# --------------------------------------------------------------------------
# treacheries
# --------------------------------------------------------------------------
def hunting_shadow(ctx):
    """Hunting Shadow: Peril. Revelation - either spend 1 clue or take 2 damage."""
    investigator = _investigator(ctx)
    options = [ChoiceOption("damage", "承受 2 点伤害")]
    if investigator.clues > 0:
        options.insert(0, ChoiceOption("clue", "花费 1 条线索"))
    choice = PendingChoice(
        id=ctx.game.next_choice_id(),
        kind=ChoiceKind.OPTION,
        player_id=ctx.controller.id,
        prompt="Hunting Shadow：花费 1 条线索，或承受 2 点伤害",
        options=options,
    )
    picked = yield from ctx.game.ask(choice)
    if picked[0] == "clue":
        investigator.clues -= 1
        ctx.log(f"{investigator.name} 花费 1 条线索躲过追踪", kind="clue")
    else:
        yield from ctx.game.deal_damage(investigator, 2, source=ctx.source, reason="Hunting Shadow")


def false_lead(ctx):
    """False Lead: Revelation - no clues means surge; otherwise test intellect (4) and lose clues on failure."""
    investigator = _investigator(ctx)
    if investigator.clues == 0:
        ctx.log("False Lead：没有线索，获得涌潮（再抽 1 张遭遇卡）", kind="encounter")
        card = ctx.game.draw_encounter(ctx.controller)
        if card is not None:
            yield from ctx.game.resolve_encounter(ctx.controller, card)
        return
    result = yield from ctx.game.skill_test(
        investigator=investigator, skill=Skill.INTELLECT, difficulty=4, source=ctx.source, kind="revelation"
    )
    if not result.success:
        lost = min(investigator.clues, -result.margin)
        investigator.clues -= lost
        location = ctx.state.maybe_card(investigator.meta.get("location_id"))
        if location is not None:
            location.clues += lost
        ctx.log(f"False Lead：{lost} 条线索被放回{location.name if location else '地点'}", kind="clue")


def mysterious_chanting(ctx):
    """Mysterious Chanting: Revelation - 2 doom on the nearest Cultist, else draw a Cultist."""
    target = nearest_cultist(ctx, _investigator(ctx))
    if target is not None:
        yield from ctx.game.place_doom(target, 2)
        return
    ctx.log("Mysterious Chanting：场上没有邪教徒，改为抽 1 名邪教徒", kind="encounter")
    from ..core.enums import CardType as _CardType

    for card_id in list(ctx.state.encounter_deck):
        card = ctx.state.cards[card_id]
        if card.card_type is _CardType.ENEMY and "cultist" in card.defn.traits:
            ctx.state.encounter_deck.remove(card_id)
            yield from ctx.game.resolve_encounter(ctx.controller, card)
            return
    for card_id in list(ctx.state.encounter_discard):
        card = ctx.state.cards[card_id]
        if card.card_type is _CardType.ENEMY and "cultist" in card.defn.traits:
            ctx.state.encounter_discard.remove(card_id)
            yield from ctx.game.resolve_encounter(ctx.controller, card)
            return


def on_wings_of_darkness(ctx):
    """On Wings of Darkness: Revelation - test agility (4); on failure take 1 horror and 1 damage, then flee to a Central location."""
    investigator = _investigator(ctx)
    result = yield from ctx.game.skill_test(
        investigator=investigator, skill=Skill.AGILITY, difficulty=4, source=ctx.source, kind="revelation"
    )
    if result.success:
        return
    yield from ctx.game.deal_horror(investigator, 1, source=ctx.source, reason="On Wings of Darkness")
    yield from ctx.game.deal_damage(investigator, 1, source=ctx.source, reason="On Wings of Darkness")
    player = ctx.controller
    for enemy in list(ctx.state.engaged_enemies(player.id)):
        if "nightgaunt" not in enemy.defn.traits:
            ctx.game.disengage(enemy, player)
    central = [loc for loc in ctx.state.locations() if "central" in loc.defn.traits]
    if central:
        yield from ctx.game.move_investigator(investigator, central[0].id)


def locked_door(ctx):
    """Locked Door: Revelation - attach to the location with the most clues; that location cannot be investigated."""
    candidates = [loc for loc in ctx.state.locations() if not any(
        c.attached_to == loc.id and c.code == "01174" for c in ctx.state.cards.values()
    )]
    if not candidates:
        return
    target = max(candidates, key=lambda loc: loc.clues)
    ctx.game.attach_to_location(ctx.source, target)
    ctx.log(f"Locked Door 锁住了{target.name}（无法调查）", kind="encounter")


def locked_door_break(ctx):
    """[action]: test combat (4) or agility (4) to break down the door; on success discard Locked Door."""
    investigator = _investigator(ctx) or ctx.investigator
    door = ctx.source
    choice = PendingChoice(
        id=ctx.game.next_choice_id(),
        kind=ChoiceKind.OPTION,
        player_id=ctx.controller.id,
        prompt="撬开被锁住的门：用战斗力（4）还是敏捷（4）？",
        options=[ChoiceOption("combat", "战斗力 4 撞开"), ChoiceOption("agility", "敏捷 4 撬锁")],
    )
    picked = yield from ctx.game.ask(choice)
    skill = Skill.COMBAT if picked[0] == "combat" else Skill.AGILITY
    result = yield from ctx.game.skill_test(
        investigator=investigator, skill=skill, difficulty=4, source=door, kind="activate"
    )
    if result.success:
        ctx.game.discard_from_play(door)
        ctx.log("被锁住的门被打开了", kind="story")


# --------------------------------------------------------------------------
# enemies
# --------------------------------------------------------------------------
def acolyte_enters(ctx):
    """Acolyte: Forced - After Acolyte enters play: place 1 doom on it."""
    yield from ctx.game.place_doom(ctx.source, 1)


def wizard_end_of_mythos(ctx):
    """Wizard of the Order: Forced - At the end of the mythos phase: place 1 doom on it."""
    if ctx.event.get("phase") is not None and str(ctx.event.get("phase")) not in ("Phase.MYTHOS", "mythos"):
        return
    yield from ctx.game.place_doom(ctx.source, 1)


def wolfman_attacks(ctx):
    """Wolf-Man Drew: Forced - When he attacks: heal 1 damage from him."""
    if ctx.event.target is None or ctx.event.target.card_type is not CardType.INVESTIGATOR:
        return
    ctx.source.damage = max(0, ctx.source.damage - 1)
    ctx.log('"Wolf-Man" Drew 的攻击让他恢复了 1 点生命', kind="heal")


def ruth_evaded(ctx):
    """Ruth Turner: Forced - After she is evaded: add her to the victory display."""
    result = ctx.event.get("result")
    if result is None or not result.success:
        return
    card = ctx.source
    card.engaged_with.clear()
    card.location_id = None
    card.zone = Zone.REMOVED
    if card.id not in ctx.state.victory_display:
        ctx.state.victory_display.append(card.id)
    ctx.log("Ruth Turner 被闪避，记入胜利点弃牌堆", kind="victory")


def parley_victory(cost_kind):
    """Parley abilities that add a cultist to the victory display (Herman Collins, Peter Warren, Victoria Devereux)."""

    def effect(ctx):
        card = ctx.source
        player = ctx.controller
        if cost_kind == "cards":
            hand = [c for c in player.hand if c != card.id]
            if len(hand) < 4:
                ctx.log(f"{card.name}：手牌不足 4 张，无法谈判", kind="encounter")
                return
            choice = PendingChoice(
                id=ctx.game.next_choice_id(),
                kind=ChoiceKind.CARDS,
                player_id=player.id,
                prompt=f"谈判：从手牌选择 4 张弃掉（{card.name}）",
                options=[ChoiceOption(cid, ctx.state.cards[cid].name) for cid in hand],
                min_selected=4,
                max_selected=4,
            )
            picked = yield from ctx.game.ask(choice)
            for cid in picked:
                ctx.game.move_to_discard(player, cid)
        elif cost_kind == "clues":
            if player.clues < 2:
                ctx.log(f"{card.name}：线索不足 2 条，无法谈判", kind="encounter")
                return
            player.clues -= 2
        elif cost_kind == "resources":
            if player.resources < 5:
                ctx.log(f"{card.name}：资源不足 5，无法谈判", kind="encounter")
                return
            player.resources -= 5
        card.engaged_with.clear()
        card.location_id = None
        card.zone = Zone.REMOVED
        if card.id not in ctx.state.victory_display:
            ctx.state.victory_display.append(card.id)
        ctx.log(f"{card.name} 被说服，记入胜利点弃牌堆", kind="victory")

    return effect


def graveyard_enter(ctx):
    """Graveyard: Forced - After you enter: test willpower (3). On failure take 2 horror or move to Rivertown."""
    investigator = ctx.event.target
    if investigator is None or investigator.card_type is not CardType.INVESTIGATOR:
        return
    result = yield from ctx.game.skill_test(
        investigator=investigator, skill=Skill.WILLPOWER, difficulty=3, source=ctx.source, kind="revelation"
    )
    if result.success:
        return
    choice = PendingChoice(
        id=ctx.game.next_choice_id(),
        kind=ChoiceKind.OPTION,
        player_id=ctx.controller.id,
        prompt="墓地：承受 2 点恐惧，或移动到河滨小镇",
        options=[ChoiceOption("horror", "承受 2 点恐惧"), ChoiceOption("move", "移动到河滨小镇")],
    )
    picked = yield from ctx.game.ask(choice)
    if picked[0] == "horror":
        yield from ctx.game.deal_horror(investigator, 2, source=ctx.source, reason="Graveyard")
        return
    for location in ctx.state.locations():
        if location.code == "01125":
            yield from ctx.game.move_investigator(investigator, location.id)
            return


# --------------------------------------------------------------------------
# registration
# --------------------------------------------------------------------------
register(
    "01133",
    abilities=(Ability(kind=AbilityKind.FORCED, trigger=Trigger.ON_ENTER_LOCATION, effect=graveyard_enter, label="Graveyard"),),
)
register("01135", revelation=hunting_shadow)
register("01136", revelation=false_lead)
register("01171", revelation=mysterious_chanting)
register("01173", revelation=on_wings_of_darkness)
register(
    "01174",
    revelation=locked_door,
    meta={"blocks_investigate": True},
    abilities=(
        Ability(kind=AbilityKind.ACTIVATED, label="撬门 / 撬锁", effect=locked_door_break),
    ),
)
register(
    "01169",
    abilities=(Ability(kind=AbilityKind.FORCED, trigger=Trigger.ON_ENTER_PLAY, effect=acolyte_enters, label="Acolyte"),),
)
register(
    "01170",
    abilities=(
        Ability(kind=AbilityKind.FORCED, trigger=Trigger.ON_PHASE_END, effect=wizard_end_of_mythos, label="Wizard of the Order"),
    ),
)
register(
    "01137",
    abilities=(Ability(kind=AbilityKind.FORCED, trigger=Trigger.ON_ENEMY_ATTACK, effect=wolfman_attacks, label='"Wolf-Man" Drew'),),
)
register(
    "01141",
    abilities=(Ability(kind=AbilityKind.FORCED, trigger=Trigger.ON_EVADE, effect=ruth_evaded, label="Ruth Turner"),),
)
register("01138", meta={"parley": {"skill": "willpower", "difficulty": 0, "cost": "cards", "victory": True}})
register("01139", meta={"parley": {"skill": "willpower", "difficulty": 0, "cost": "clues", "victory": True}})
register("01140", meta={"parley": {"skill": "willpower", "difficulty": 0, "cost": "resources", "victory": True}})

# --------------------------------------------------------------------------
# The Midnight Masks: location actions (each is an [action] ability printed on
# the location).  Registered here; the engine exposes them automatically while
# an investigator is standing there, honouring the per-turn / per-game limits.
# --------------------------------------------------------------------------
from ..core.errors import IllegalActionError as _IllegalActionError  # noqa: E402


def your_house_action(game, player, location):
    """Your House: [action] Draw 1 card and gain 1 resource. (Limit once per turn.)"""
    investigator = game.state.investigator_of(player)
    yield from game.draw_cards(player, 1)
    player.resources += 1
    game.state.log(f"{investigator.name} 在家里稍作喘息：抽 1 张牌并得到 1 资源", kind="draw")


def southside_draw_action(game, player, location):
    """Southside (01126): [action] Draw 3 cards. (Limit once per game.)"""
    yield from game.draw_cards(player, 3)


def southside_ally_action(game, player, location):
    """Southside (01127): [action] Search your deck for an [[Ally]] asset and add it to your hand."""
    state = game.state
    candidates = [cid for cid in player.deck if "ally" in state.cards[cid].defn.traits]
    if not candidates:
        state.log("牌库里没有盟友卡", kind="draw")
        return
    choice = PendingChoice(
        id=game.next_choice_id(),
        kind=ChoiceKind.CARD,
        player_id=player.id,
        prompt="从牌库中找出一张盟友卡加入手牌",
        options=[ChoiceOption(cid, state.cards[cid].name) for cid in candidates],
    )
    picked = yield from game.ask(choice)
    card_id = picked[0]
    player.deck.remove(card_id)
    state.cards[card_id].zone = Zone.HAND
    player.hand.append(card_id)
    state.rng.shuffle(player.deck)
    state.log(f"找到了 {state.cards[card_id].name} 并洗牌", kind="draw")


def st_marys_action(game, player, location):
    """St. Mary's Hospital: [action] Heal 3 damage. (Limit once per game.)"""
    investigator = game.state.investigator_of(player)
    game.heal(investigator, damage=3)


def miskatonic_action(game, player, location):
    """Miskatonic University: [action] Search the top 6 cards of your deck for a Tome or Spell."""
    state = game.state
    top = player.deck[:6]
    candidates = [cid for cid in top if {"tome", "spell"} & set(state.cards[cid].defn.traits)]
    if not candidates:
        state.log("牌库顶 6 张里没有典籍或法术", kind="draw")
        state.rng.shuffle(player.deck)
        return
    choice = PendingChoice(
        id=game.next_choice_id(),
        kind=ChoiceKind.CARD,
        player_id=player.id,
        prompt="从牌库顶 6 张中找出一张典籍或法术",
        options=[ChoiceOption(cid, state.cards[cid].name) for cid in candidates],
    )
    picked = yield from game.ask(choice)
    card_id = picked[0]
    player.deck.remove(card_id)
    state.cards[card_id].zone = Zone.HAND
    player.hand.append(card_id)
    state.rng.shuffle(player.deck)


def downtown_resources_action(game, player, location):
    """Downtown (01130): [action] Gain 3 resources. (Limit once per game.)"""
    player.resources += 3
    game.state.log(f"在市中心筹到了 3 资源", kind="resource")


def downtown_heal_action(game, player, location):
    """Downtown (01131): [action] Heal 3 horror. (Limit once per game.)"""
    game.heal(game.state.investigator_of(player), horror=3)


def northside_action(game, player, location):
    """Northside: [action] Spend 5 resources: Gain 2 clues from the token pool."""
    investigator = game.state.investigator_of(player)
    if player.resources < 5:
        raise _IllegalActionError("需要 5 点资源")
    player.resources -= 5
    investigator.clues += 2
    game.state.log(f"{investigator.name} 在商业区打点关系，获得 2 条线索", kind="clue")


register_location_action("your_house", your_house_action)
register_location_action("southside_draw", southside_draw_action)
register_location_action("southside_ally", southside_ally_action)
register_location_action("st_marys_heal", st_marys_action)
register_location_action("miskatonic_search", miskatonic_action)
register_location_action("downtown_resources", downtown_resources_action)
register_location_action("downtown_heal", downtown_heal_action)
register_location_action("northside", northside_action)

register(
    "01124",
    meta={
        "attracts_code": "01116",
        "location_actions": [
            {"id": "your_house", "label": "抽 1 张牌并得到 1 资源", "limit": "turn"},
        ],
    },
)
register("01126", meta={"location_actions": [{"id": "southside_draw", "label": "抽 3 张牌", "limit": "game"}]})
register("01127", meta={"location_actions": [{"id": "southside_ally", "label": "从牌库找出 1 张盟友", "limit": "game"}]})
register("01128", meta={"location_actions": [{"id": "st_marys_heal", "label": "治疗 3 点伤害", "limit": "game"}]})
register(
    "01129",
    meta={"location_actions": [{"id": "miskatonic_search", "label": "从牌库顶 6 张找典籍/法术", "limit": "game"}]},
)
register("01130", meta={"location_actions": [{"id": "downtown_resources", "label": "获得 3 资源", "limit": "game"}]})
register("01131", meta={"location_actions": [{"id": "downtown_heal", "label": "治疗 3 点恐惧", "limit": "game"}]})
register("01132", meta={"ally_cost_reduction": 2})
register("01134", meta={"location_actions": [{"id": "northside", "label": "花 5 资源换 2 条线索", "limit": "game"}]})
