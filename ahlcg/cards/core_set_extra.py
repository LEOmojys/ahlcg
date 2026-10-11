"""Cards implemented after the main core-set file grew too large to edit safely.

Keeping them in their own module means appending never risks truncating a big
file, and the engine hooks they need (skill substitution, attaching events,
barricades) live in the engine where they belong.
"""

from __future__ import annotations

from ..core.cards import Ability, Cost
from ..core.choices import ChoiceOption, PendingChoice
from ..core.enums import AbilityKind, CardType, ChoiceKind, CostKind, Skill, Trigger, Zone
from . import register


def _test_investigator(ctx):
    test = ctx.event.get("test")
    if test is None:
        return None
    return ctx.state.maybe_card(getattr(test, "investigator_id", None))


def _draw_if_successful(ctx):
    """"If this skill test is successful, draw 1 card." (Guts / Perception / Overpower / Manual Dexterity)"""
    investigator = _test_investigator(ctx)
    player = ctx.state.player_of(investigator) if investigator is not None else None
    if player is None:
        return
    yield from ctx.game.draw_cards(player, 1)


for _code in ("01089", "01090", "01091", "01092"):
    register(
        _code,
        meta={"max_one_committed": True},
        abilities=(
            Ability(
                kind=AbilityKind.FORCED,
                trigger=Trigger.ON_SUCCESS,
                effect=_draw_if_successful,
                label="成功时抽 1 张牌",
            ),
        ),
    )
register("01093", meta={"max_one_committed": True})


def _scavenging(ctx):
    """Scavenging: [reaction] After you successfully investigate by 2 or more, exhaust: return an Item from the discard pile."""
    card = ctx.source
    result = ctx.event.get("result")
    if card.exhausted or result is None or not result.success or result.margin < 2:
        return
    card.exhausted = True
    player = ctx.state.player_of(card)
    if player is None:
        return
    items = [cid for cid in player.discard if "item" in ctx.state.cards[cid].defn.traits]
    if not items:
        return
    choice = PendingChoice(
        id=ctx.game.next_choice_id(),
        kind=ChoiceKind.CARD,
        player_id=player.id,
        prompt="拾荒：从弃牌堆取回一件物品",
        options=[ChoiceOption(cid, ctx.state.cards[cid].name) for cid in items],
    )
    picked = yield from ctx.game.ask(choice)
    card_id = picked[0]
    player.discard.remove(card_id)
    ctx.state.cards[card_id].zone = Zone.HAND
    player.hand.append(card_id)


register(
    "01073",
    abilities=(Ability(kind=AbilityKind.TRIGGERED, trigger=Trigger.ON_INVESTIGATE, effect=_scavenging, label="Scavenging"),),
)


def _medical_texts(ctx):
    """Medical Texts: [action] Choose an investigator at your location, test intellect (2):
    success heals 1 damage, failure deals 1 damage."""
    investigator = ctx.investigator
    if investigator is None:
        return
    here = investigator.meta.get("location_id")
    others = [
        ctx.state.investigator_of(p)
        for p in ctx.state.players
        if p.is_active and ctx.state.investigator_of(p).meta.get("location_id") == here
    ]
    target = investigator
    if len(others) > 1:
        choice = PendingChoice(
            id=ctx.game.next_choice_id(),
            kind=ChoiceKind.INVESTIGATOR,
            player_id=ctx.controller.id,
            prompt="医学教科书：选择此地的调查员",
            options=[ChoiceOption(c.id, c.name) for c in others],
        )
        picked = yield from ctx.game.ask(choice)
        target = ctx.state.cards[picked[0]]
    result = yield from ctx.game.skill_test(
        investigator=investigator, skill=Skill.INTELLECT, difficulty=2, source=ctx.source, kind="activate"
    )
    if result.success:
        ctx.game.heal(target, damage=1)
    else:
        yield from ctx.game.deal_damage(target, 1, source=ctx.source, reason="Medical Texts")


register(
    "01035",
    abilities=(
        Ability(kind=AbilityKind.ACTIVATED, costs=(Cost(CostKind.ACTION),), effect=_medical_texts, label="诊断与治疗"),
    ),
)


def _blinding_light(ctx):
    """Blinding Light: Evade. Uses [willpower]. On success deal 1 damage to the evaded enemy."""
    investigator = ctx.investigator
    player = ctx.controller
    if investigator is None:
        return
    here = investigator.meta.get("location_id")
    targets = [e for e in ctx.state.enemies_at(here)] + [e for e in ctx.state.engaged_enemies(player.id)]
    if not targets:
        return
    choice = PendingChoice(
        id=ctx.game.next_choice_id(),
        kind=ChoiceKind.ENEMY,
        player_id=player.id,
        prompt="眩目强光：选择要闪避的敌人",
        options=[ChoiceOption(e.id, e.name) for e in targets],
    )
    picked = yield from ctx.game.ask(choice)
    enemy = ctx.state.cards[picked[0]]
    result = yield from ctx.game.skill_test(
        investigator=investigator,
        skill=Skill.WILLPOWER,
        difficulty=ctx.game.enemy_evade(enemy),
        source=ctx.source,
        target=enemy,
        kind="evade",
    )
    if result.success:
        enemy.exhausted = True
        if player.id in enemy.engaged_with:
            ctx.game.disengage(enemy, player)
        yield from ctx.game.deal_damage(enemy, 1, source=ctx.source, reason="Blinding Light")


register("01066", play=_blinding_light)


def _scrying(ctx):
    """Scrying: [action] Exhaust and spend 1 charge: look at the top 3 cards of a deck."""
    card = ctx.source
    player = ctx.controller
    if card.exhausted or card.uses.get("charge", 0) <= 0:
        return
    card.exhausted = True
    card.use("charge")
    choice = PendingChoice(
        id=ctx.game.next_choice_id(),
        kind=ChoiceKind.OPTION,
        player_id=player.id,
        prompt="占卜：查看哪个牌堆的顶部 3 张？",
        options=[ChoiceOption("encounter", "遭遇牌堆"), ChoiceOption("deck", "自己的牌库")],
    )
    picked = yield from ctx.game.ask(choice)
    source = ctx.state.encounter_deck if picked[0] == "encounter" else player.deck
    names = [ctx.state.cards[cid].name for cid in source[:3]]
    ctx.state.log("占卜看到的牌：" + ("、".join(names) if names else "（空）"), kind="story")


register(
    "01061",
    meta={"uses": {"charge": 3}},
    abilities=(
        Ability(kind=AbilityKind.ACTIVATED, costs=(Cost(CostKind.ACTION),), effect=_scrying, label="查看牌堆顶 3 张"),
    ),
)


def _barricade(ctx):
    """Barricade: attach to your location; non-elite enemies cannot move into it."""
    investigator = ctx.investigator
    if investigator is None:
        return
    location = ctx.state.maybe_card(investigator.meta.get("location_id"))
    if location is None:
        return
    ctx.source.meta["stays_in_play"] = True
    ctx.game.attach_to_location(ctx.source, location)


def _barricade_breaks(ctx):
    """Forced - When an investigator leaves the attached location: discard Barricade."""
    card = ctx.source
    location = ctx.event.target
    if location is None or card.attached_to != getattr(location, "id", None):
        return
    ctx.game.discard_from_play(card)


register(
    "01038",
    play=_barricade,
    meta={"blocks_enemy_movement": True},
    abilities=(
        Ability(kind=AbilityKind.FORCED, trigger=Trigger.ON_LEAVE_LOCATION, effect=_barricade_breaks, label="Barricade"),
    ),
)


def _mind_over_matter(ctx):
    """Mind over Matter: until the end of the round, use [intellect] for [combat] and [agility]."""
    ctx.state.flags["mind_over_matter_round"] = ctx.state.round
    ctx.state.log("思维胜于肉体：本回合以智力代替战斗力与敏捷", kind="story")


register("01036", play=_mind_over_matter)

# --------------------------------------------------------------------------
# Two more, both riding triggers that already exist.
# --------------------------------------------------------------------------
def _survival_instinct(ctx):
    """Survival Instinct: on a successful evasion, disengage from each other enemy engaged with you."""
    test = ctx.event.get("test")
    if test is None or test.kind != "evade":
        return
    investigator = ctx.state.maybe_card(getattr(test, "investigator_id", None))
    player = ctx.state.player_of(investigator) if investigator is not None else None
    if player is None:
        return
    evaded = ctx.event.get("target")
    for enemy in list(ctx.state.engaged_enemies(player.id)):
        if evaded is not None and enemy.id == getattr(evaded, "id", None):
            continue
        ctx.game.disengage(enemy, player)
        ctx.log(f"生存本能：摆脱了 {enemy.name}")


register(
    "01081",
    abilities=(
        Ability(kind=AbilityKind.FORCED, trigger=Trigger.ON_SUCCESS, effect=_survival_instinct, label="Survival Instinct"),
    ),
)


def _on_the_lam(ctx):
    """On the Lam: until the end of the round, non-Elite enemies cannot attack you."""
    player = ctx.controller
    ctx.state.flags["on_the_lam"] = {"player": player.id, "round": ctx.state.round}
    ctx.state.log(f"{ctx.investigator.name if ctx.investigator else '调查员'} 亡命天涯：本回合非精英敌人无法攻击他", kind="story")


register("01010", play=_on_the_lam)

# --------------------------------------------------------------------------
# Level 1-5 cards and the weakness enemies from the core set.
# --------------------------------------------------------------------------
# permanent slot upgrades
register("01694", meta={"extra_slots": {"ally": 1}})        # Charisma
register("01695", meta={"extra_slots": {"accessory": 1}})   # Relic Hunter
register("01070", meta={"extra_slots": {"arcane": 1}})      # Book of Shadows
# flat stat bonuses
register("01027", meta={"constant": [{"skill": "willpower", "amount": 1}]})   # Police Badge
register("01055", meta={"constant": [{"skill": "agility", "amount": 1}]})     # Cat Burglar
# weapons
register("01029", meta={"attack": {"combat_bonus": 3, "damage": 2, "spend": "ammo", "damage_per_success": True, "damage_cap": 5}, "uses": {"ammo": 2}})  # Shotgun


def _hot_streak(ctx):
    """Hot Streak: Gain 10 resources."""
    ctx.controller.resources += 10
    ctx.state.log("Hot Streak：获得 10 资源", kind="resource")


register("01057", play=_hot_streak)


def _cryptic_research(ctx):
    """Cryptic Research: Fast. Choose an investigator at your location: that investigator draws 3 cards."""
    yield from ctx.game.draw_cards(ctx.controller, 3)


register("01043", play=_cryptic_research)


def _seeking_answers(ctx):
    """Seeking Answers: Investigate; on success discover 2 clues from connected locations instead."""
    investigator = ctx.investigator
    if investigator is None:
        return
    location = ctx.state.maybe_card(investigator.meta.get("location_id"))
    if location is None:
        return
    result = yield from ctx.game.skill_test(
        investigator=investigator,
        skill=Skill.INTELLECT,
        difficulty=ctx.game.shroud_of(location),
        source=location,
        kind="investigate",
    )
    if not result.success:
        return
    found = 0
    for other_id in ctx.state.connections_of(location.id):
        other = ctx.state.maybe_card(other_id)
        if other is None or found >= 2:
            continue
        take = min(2 - found, other.clues)
        if take:
            other.clues -= take
            investigator.clues += take
            found += take
            ctx.state.log(f"Seeking Answers：在{other.name}发现了 {take} 条线索", kind="clue")


register("01685", play=_seeking_answers)


def _extra_ammunition(ctx):
    """Extra Ammunition: place 3 ammo on a Firearm asset controlled by an investigator at your location."""
    investigator = ctx.investigator
    if investigator is None:
        return
    here = investigator.meta.get("location_id")
    targets = []
    for player in ctx.state.players:
        if not player.is_active or ctx.state.investigator_of(player).meta.get("location_id") != here:
            continue
        targets += [a for a in ctx.state.assets_of(player.id) if "firearm" in a.defn.traits]
    if not targets:
        ctx.log("Extra Ammunition：此地没有枪械")
        return
    choice = PendingChoice(
        id=ctx.game.next_choice_id(),
        kind=ChoiceKind.CARD,
        player_id=ctx.controller.id,
        prompt="额外弹药：选择一把枪械",
        options=[ChoiceOption(a.id, f"{a.name}（弹药 {a.uses.get('ammo', 0)}）") for a in targets],
    )
    picked = yield from ctx.game.ask(choice)
    weapon = ctx.state.cards[picked[0]]
    weapon.add_uses("ammo", 3)
    ctx.state.log(f"{weapon.name} 装填了 3 发弹药", kind="resource")


register("01026", play=_extra_ammunition)


def _close_call(ctx):
    """Close Call: shuffle a non-weakness, non-Elite enemy at your location into the encounter deck."""
    investigator = ctx.investigator
    if investigator is None:
        return
    player = ctx.controller
    here = investigator.meta.get("location_id")
    targets = [e for e in ctx.state.enemies_at(here) if not e.defn.elite and not e.defn.weakness]
    targets += [e for e in ctx.state.engaged_enemies(player.id) if not e.defn.elite and not e.defn.weakness]
    if not targets:
        return
    choice = PendingChoice(
        id=ctx.game.next_choice_id(),
        kind=ChoiceKind.ENEMY,
        player_id=player.id,
        prompt="放它一马：选择要洗回遭遇牌堆的敌人",
        options=[ChoiceOption(e.id, e.name) for e in targets],
    )
    picked = yield from ctx.game.ask(choice)
    enemy = ctx.state.cards[picked[0]]
    enemy.engaged_with.clear()
    enemy.location_id = None
    enemy.damage = 0
    enemy.horror = 0
    enemy.exhausted = False
    enemy.zone = Zone.ENCOUNTER_DECK
    ctx.state.encounter_deck.append(enemy.id)
    ctx.state.rng.shuffle(ctx.state.encounter_deck)
    ctx.state.log(f"{enemy.name} 被洗回了遭遇牌堆", kind="encounter")


register("01083", play=_close_call)


def _encyclopedia(ctx):
    """Encyclopedia: [action] Exhaust: an investigator at your location gets +2 to a skill until the end of the phase."""
    investigator = ctx.investigator
    if investigator is None:
        return
    choice = PendingChoice(
        id=ctx.game.next_choice_id(),
        kind=ChoiceKind.OPTION,
        player_id=ctx.controller.id,
        prompt="百科全书：选择要强化的技能",
        options=[
            ChoiceOption(Skill.WILLPOWER.value, "意志 +2"),
            ChoiceOption(Skill.INTELLECT.value, "智力 +2"),
            ChoiceOption(Skill.COMBAT.value, "战斗力 +2"),
            ChoiceOption(Skill.AGILITY.value, "敏捷 +2"),
        ],
    )
    picked = yield from ctx.game.ask(choice)
    investigator.meta["temp_skill_bonus"] = {
        "skill": picked[0],
        "amount": 2,
        "round": ctx.state.round,
    }
    ctx.state.log(f"百科全书：{investigator.name} 的{picked[0]} +2（本回合）", kind="skill_test")


register(
    "01042",
    abilities=(Ability(kind=AbilityKind.ACTIVATED, costs=(Cost(CostKind.ACTION), Cost(CostKind.EXHAUST)), effect=_encyclopedia, label="强化技能"),),
)


def _disc_of_itzamna(ctx):
    """Disc of Itzamna: [reaction] When a non-Elite enemy spawns at your location, discard it."""
    enemy = ctx.event.source
    if enemy is None or enemy.defn.elite:
        return
    investigator = ctx.investigator
    if investigator is None or enemy.location_id != investigator.meta.get("location_id"):
        return
    ctx.game.discard_from_play(enemy)
    ctx.game.move_to_discard(ctx.controller, ctx.source.id)
    ctx.state.log(f"伊兹塔姆纳圆盘驱逐了 {enemy.name}", kind="story")


register(
    "01041",
    abilities=(Ability(kind=AbilityKind.TRIGGERED, trigger=Trigger.ON_ENEMY_SPAWN, effect=_disc_of_itzamna, label="Disc of Itzamna"),),
)


def _mind_wipe(ctx):
    """Mind Wipe: treat a non-Elite enemy's text box as blank until the end of the phase."""
    investigator = ctx.investigator
    if investigator is None:
        return
    here = investigator.meta.get("location_id")
    targets = [e for e in ctx.state.enemies_at(here) if not e.defn.elite]
    targets += [e for e in ctx.state.engaged_enemies(ctx.controller.id) if not e.defn.elite]
    if not targets:
        return
    choice = PendingChoice(
        id=ctx.game.next_choice_id(),
        kind=ChoiceKind.ENEMY,
        player_id=ctx.controller.id,
        prompt="心灵抹除：选择一名非精英敌人（其文本视为空白）",
        options=[ChoiceOption(e.id, e.name) for e in targets],
    )
    picked = yield from ctx.game.ask(choice)
    ctx.state.cards[picked[0]].meta["blank"] = True
    ctx.state.log("心灵抹除：该敌人的文本被视为空白", kind="story")


register("01068", play=_mind_wipe)


def _will_to_survive(ctx):
    """Will to Survive: until the end of your turn, do not reveal chaos tokens."""
    ctx.state.flags["no_chaos_tokens_round"] = ctx.state.round
    ctx.state.log("求生意志：本回合不再揭示混沌标记", kind="story")


register("01085", play=_will_to_survive)


def _parley_away(ctx):
    """Mob Enforcer: [action] Spend 4 resources: Parley. Discard it."""
    player = ctx.controller
    if player.resources < 4:
        ctx.log("暴徒：资源不足 4，谈判失败")
        return
    player.resources -= 4
    card = ctx.source
    card.engaged_with.clear()
    card.location_id = None
    ctx.game.to_encounter_discard(card)
    ctx.state.log("暴徒拿了钱走人了", kind="story")


register(
    "01101",
    meta={"parley": {"skill": "willpower", "difficulty": 0}},
    abilities=(Ability(kind=AbilityKind.ACTIVATED, costs=(Cost(CostKind.ACTION),), effect=_parley_away, label="花 4 资源谈判"),),
)


def _silver_twilight_attacks(ctx):
    """Silver Twilight Acolyte: Forced - After it attacks: place 1 doom on the current agenda."""
    agenda = ctx.state.current_agenda()
    if agenda is not None:
        yield from ctx.game.place_doom(agenda, 1)


register(
    "01102",
    abilities=(Ability(kind=AbilityKind.FORCED, trigger=Trigger.ON_ENEMY_ATTACK, effect=_silver_twilight_attacks, label="Silver Twilight Acolyte"),),
)

def _rite_of_seeking(ctx):
    """Rite of Seeking: [action] Spend 1 charge: Investigate using [willpower]; on success discover 1 extra clue."""
    card = ctx.source
    investigator = ctx.investigator
    if investigator is None or card.uses.get("charge", 0) <= 0:
        return
    location = ctx.state.maybe_card(investigator.meta.get("location_id"))
    if location is None:
        return
    card.use("charge")
    result = yield from ctx.game.skill_test(
        investigator=investigator,
        skill=Skill.WILLPOWER,
        difficulty=ctx.game.shroud_of(location),
        source=card,
        kind="investigate",
    )
    if result.success:
        ctx.game.discover_clue(investigator, location, 1 + int(result.meta.get("extra_clues", 0)) + 1)


register(
    "01689",
    meta={"uses": {"charge": 3}},
    abilities=(
        Ability(kind=AbilityKind.ACTIVATED, costs=(Cost(CostKind.ACTION),), effect=_rite_of_seeking, label="用意志调查"),
    ),
)

# --------------------------------------------------------------------------
# The chaos-token reveal window: peek, choose, or rewrite the revealed token.
# --------------------------------------------------------------------------
from ..engine.chaos import numeric as _numeric  # noqa: E402


def _token_value(ctx):
    token = (ctx.event.payload or {}).get("token")
    if token is None:
        return None, None
    test = ctx.event.get("test")
    return token, ctx.state.chaos_bag.value_of(token, test)


def _sure_gamble_condition(ctx):
    """"Play after you reveal a chaos token with a negative modifier." """
    _, value = _token_value(ctx)
    return value is not None and value < 0


def _sure_gamble(ctx):
    """Sure Gamble: switch that token's modifier to +4."""
    ctx.event.payload["token"] = _numeric(4)
    player = ctx.state.player_of(ctx.source)
    if player is not None:
        ctx.game.move_to_discard(player, ctx.source.id)
    ctx.log("Sure Gamble：把这个标记改成了 +4")


register(
    "01056",
    abilities=(
        Ability(
            kind=AbilityKind.TRIGGERED,
            trigger=Trigger.ON_REVEAL_TOKEN,
            condition=_sure_gamble_condition,
            effect=_sure_gamble,
            label="Sure Gamble",
        ),
    ),
)


def _eucatastrophe_condition(ctx):
    """"Play when you reveal a chaos token that would reduce your skill value to 0." """
    token, value = _token_value(ctx)
    test = ctx.event.get("test")
    if token is None or test is None:
        return False
    return test.skill_value() + value <= 0


def _eucatastrophe(ctx):
    """Eucatastrophe: cancel that token and reveal a new one."""
    ctx.event.payload["token"] = ctx.state.chaos_bag.draw(ctx.state.rng)
    player = ctx.state.player_of(ctx.source)
    if player is not None:
        ctx.game.move_to_discard(player, ctx.source.id)
    ctx.log("Eucatastrophe：取消该标记并揭示新的标记")


register(
    "01692",
    abilities=(
        Ability(
            kind=AbilityKind.TRIGGERED,
            trigger=Trigger.ON_REVEAL_TOKEN,
            condition=_eucatastrophe_condition,
            effect=_eucatastrophe,
            label="Eucatastrophe",
        ),
    ),
)

# Grotesque Statue: reveal two tokens and keep one, spending a charge
register(
    "01071",
    meta={"uses": {"charge": 4}, "reveal_choice": {"spend": "charge"}, "discard_when_empty": True},
)

def _lockpicks(ctx):
    """Lockpicks: [action] Exhaust: Investigate, adding your agility; below +2 success loses 1 supply."""
    card = ctx.source
    investigator = ctx.investigator
    if investigator is None:
        return
    location = ctx.state.maybe_card(investigator.meta.get("location_id"))
    if location is None:
        return
    result = yield from ctx.game.skill_test(
        investigator=investigator,
        skill=Skill.INTELLECT,
        difficulty=ctx.game.shroud_of(location),
        source=card,
        kind="investigate",
        bonus=int(investigator.defn.agility or 0),
    )
    if result.success:
        ctx.game.discover_clue(investigator, location, 1 + int(result.meta.get("extra_clues", 0)))
    if result.margin < 2:
        card.use("supply")
        ctx.log(f"开锁工具不太好用（剩余补给 {card.uses.get('supply', 0)}）")
        if card.uses.get("supply", 0) <= 0:
            ctx.game.move_to_discard(ctx.controller, card.id)
            ctx.log("开锁工具用尽了补给，被弃置")


register(
    "01687",
    meta={"uses": {"supply": 3}},
    abilities=(Ability(kind=AbilityKind.ACTIVATED, costs=(Cost(CostKind.ACTION), Cost(CostKind.EXHAUST)), effect=_lockpicks, label="用敏捷开锁调查"),),
)


def _aquinnah(ctx):
    """Aquinnah: [reaction] When an enemy attacks you, exhaust her and deal her 1 horror:
    deal that enemy's damage to another enemy at your location instead."""
    source = ctx.source
    investigator = ctx.investigator
    enemy = ctx.event.source
    if investigator is None or enemy is None or source.exhausted:
        return
    here = investigator.meta.get("location_id")
    others = [e for e in ctx.state.enemies() if e.id != enemy.id and e.location_id == here]
    if not others:
        return
    choice = PendingChoice(
        id=ctx.game.next_choice_id(),
        kind=ChoiceKind.ENEMY,
        player_id=ctx.controller.id,
        prompt="阿昆娜：把这名敌人的伤害转给谁？",
        options=[ChoiceOption(e.id, e.name) for e in others],
    )
    picked = yield from ctx.game.ask(choice)
    source.exhausted = True
    enemy.meta["redirect_damage_to"] = picked[0]
    yield from ctx.game.deal_horror(source, 1, source=enemy, reason="Aquinnah")
    ctx.log(f"阿昆娜挡下了 {enemy.name} 的攻击")


register(
    "01082",
    abilities=(Ability(kind=AbilityKind.TRIGGERED, trigger=Trigger.ON_ENEMY_ATTACK, effect=_aquinnah, label="Aquinnah"),),
)

# Stubborn Detective: while it is at your location your investigator's text box is blank
register("01103", meta={"blanks_investigator": True})

def _had_worse_condition(ctx):
    return int((ctx.event.payload or {}).get("amount", 0)) > 0


def _had_worse(ctx):
    """"I've had worse…": cancel up to 5 damage and/or horror just dealt, then gain that many resources."""
    payload = ctx.event.payload
    amount = int(payload.get("amount", 0))
    cancelled = min(5, amount)
    payload["amount"] = amount - cancelled
    player = ctx.state.player_of(ctx.source)
    if player is not None:
        player.resources += cancelled
        ctx.game.move_to_discard(player, ctx.source.id)
    ctx.log(f"“I've had worse…”：抵消 {cancelled} 点，并获得 {cancelled} 资源")


register(
    "01684",
    abilities=(
        Ability(
            kind=AbilityKind.TRIGGERED,
            trigger=Trigger.ON_DAMAGE_TAKEN,
            condition=_had_worse_condition,
            effect=_had_worse,
            label="I've had worse...",
        ),
        Ability(
            kind=AbilityKind.TRIGGERED,
            trigger=Trigger.ON_HORROR_TAKEN,
            condition=_had_worse_condition,
            effect=_had_worse,
            label="I've had worse...",
        ),
    ),
)

def _necronomicon(ctx):
    """Revelation - Put The Necronomicon into play in your threat area, with 3 horror on it."""
    player = ctx.controller
    card = ctx.source
    card.horror = 3
    ctx.game.move_to_threat_area(player, card)
    ctx.log("《死灵之书》进入你的威胁区（3 点恐惧）：你控制的典籍文本被视为空白")


register(
    "01009",
    meta={"blanks_tomes": True, "anchored": True},
    revelation=_necronomicon,
)


def _wendys_amulet(ctx):
    """Forced - After you play an event or discard an event from your hand, discard the topmost card of your deck."""
    played = ctx.event.source
    if played is None or played.card_type is not CardType.EVENT:
        return
    player = ctx.state.player_of(ctx.source)
    if player is None or not player.deck:
        return
    card_id = player.deck.pop(0)
    ctx.state.log(f"温蒂的护符：牌库顶的 {ctx.state.cards[card_id].name} 被弃置", kind="discard")
    ctx.game.move_to_discard(player, card_id)


register(
    "01014",
    meta={"play_from_discard": True},
    abilities=(Ability(kind=AbilityKind.FORCED, trigger=Trigger.ON_ENTER_PLAY, effect=_wendys_amulet, label="Wendy's Amulet"),),
)
