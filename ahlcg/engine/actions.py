"""The actions an investigator may take during the investigation phase.

Legal actions are handed to the player as one PendingChoice whose option ids are
"verb" or "verb:target".  The web client, a test script and a robot all speak the
same vocabulary, so there is exactly one implementation of every action.
"""

from __future__ import annotations

import inspect
from typing import Any, Generator

from ..core.cards import CardInstance
from ..core.choices import ChoiceOption, PendingChoice
from ..core.enums import AbilityKind, CardType, ChoiceKind, CostKind, Skill, TokenType, Trigger, Zone
from ..core.errors import IllegalActionError, RuleError
from ..core.events import GameEvent

from .effects import EffectContext
from .state import Player


#: location / act actions contributed by card modules: action_id -> handler(game, player, location)
LOCATION_ACTIONS: dict[str, Any] = {}


def register_location_action(action_id: str, handler: Any) -> None:
    LOCATION_ACTIONS[action_id] = handler


def current_location(state, investigator: CardInstance) -> CardInstance | None:
    loc_id = investigator.meta.get("location_id")
    return state.maybe_card(loc_id) if loc_id else None


def attack_assets(state, player: Player) -> list[CardInstance]:
    """Attack assets that still have the resources their attack needs (charges, ammo)."""
    out = []
    for asset in state.assets_of(player.id):
        attack = asset.defn.meta.get("attack")
        if not attack:
            continue
        spend = attack.get("spend")
        if spend and str(spend) in asset.uses and asset.uses.get(str(spend), 0) <= 0:
            continue
        out.append(asset)
    return out


def play_is_blocked(state, player: Player) -> bool:
    return any(card.defn.meta.get("no_play") for card in state.threat_area_of(player.id))


def legal_actions(game, player: Player) -> list[ChoiceOption]:
    state = game.state
    investigator = state.investigator_of(player)
    location = current_location(state, investigator)
    options: list[ChoiceOption] = []

    if location is not None:
        locked = state.flags.get("move_locked_at") == location.id
        for destination_id in state.connections_of(location.id):
            destination = state.cards.get(destination_id)
            if destination is None or destination.zone is not Zone.PLAY:
                continue
            if destination.meta.get("blocked"):
                continue
            options.append(
                ChoiceOption(
                    f"move:{destination_id}",
                    f"移动 → {destination.name}",
                    detail=destination.defn.text_zh or destination.defn.text or "",
                    disabled=locked,
                )
            )
        if location.defn.shroud is not None:
            options.append(
                ChoiceOption(
                    "investigate",
                    f"调查 {location.name}",
                    detail=f"智力 {investigator.defn.intellect} vs 遮蔽 {game.shroud_of(location)}，线索 {location.clues}",
                )
            )
        if location.defn.meta.get("resign") or state.flags.get("resign_allowed"):
            options.append(ChoiceOption("resign", "放弃（Resign）", detail="逃离这场噩梦"))

        for spec in location.defn.meta.get("location_actions") or ():
            action_id = str(spec.get("id") or "")
            if not action_id or action_id not in LOCATION_ACTIONS:
                continue
            used = game.location_action_uses(location, action_id)
            limit = spec.get("limit")
            if limit == "turn" and used.get("round") == state.round:
                continue
            if limit == "game" and int(used.get("count", 0)) >= 1:
                continue
            options.append(
                ChoiceOption(
                    f"locact:{location.id}:{action_id}",
                    spec.get("label", action_id),
                    detail=spec.get("detail", ""),
                )
            )

    for enemy in state.engaged_enemies(player.id):
        options.append(ChoiceOption(f"fight:{enemy.id}", f"战斗 → {enemy.name}", detail=_enemy_detail(enemy)))
        options.append(ChoiceOption(f"evade:{enemy.id}", f"闪避 → {enemy.name}", detail=_enemy_detail(enemy)))
    if location is not None:
        for enemy in state.enemies_at(location.id):
            options.append(ChoiceOption(f"engage:{enemy.id}", f"交战 → {enemy.name}", detail=_enemy_detail(enemy)))
            options.append(ChoiceOption(f"fight:{enemy.id}", f"战斗 → {enemy.name}", detail=_enemy_detail(enemy)))
        for card in state.cards_in_play():
            if card.defn.meta.get("parley") and card.location_id == location.id and card.controller_id is None:
                options.append(
                    ChoiceOption(f"parley:{card.id}", f"谈判 → {card.name}", detail=card.defn.text_zh or card.defn.text or "")
                )

    act = state.current_act()
    if act is not None and act.code == "01148" and investigator.clues > 0:
        options.append(
            ChoiceOption(
                "disrupt",
                "花费 1 条线索干扰仪式",
                detail="测试意志(3)或敏捷(3)，成功则在此幕卡上放置 1 条线索",
            )
        )
    if any(state.cards[cid].code == "01117" for cid in player.play_area):
        options.append(
            ChoiceOption("sacrifice_lita", "把丽塔·钱德勒献给阿布霍斯", detail="牺牲她以保全性命（→R3）")
        )

    if any(state.cards[cid].code == "01014" for cid in player.play_area) and player.discard:
        top = state.cards[player.discard[-1]]
        if top.card_type is CardType.EVENT and (top.defn.cost or 0) <= player.resources:
            options.append(
                ChoiceOption(
                    f"playdiscard:{top.id}",
                    f"从弃牌堆打出 {top.name}",
                    detail=(top.defn.text or "")[:80],
                    disabled=play_is_blocked(state, player),
                )
            )

    cultist_deck = state.flags.get("cultist_deck") or []
    if cultist_deck:
        needed = 2 * max(1, len([p for p in state.players if p.is_active]))
        group_clues = sum(state.investigator_of(p).clues for p in state.players if p.is_active)
        options.append(
            ChoiceOption(
                "cultist",
                "花费线索抽取邪教徒牌库",
                detail=f"每人 2 条线索（共需 {needed}，当前 {group_clues}）：抽邪教徒牌库顶牌",
                disabled=group_clues < needed,
            )
        )
    if game.can_advance_act(player):
        act = state.current_act()
        rule = game.act_advance_rule(act)
        options.append(
            ChoiceOption(
                "advance_act",
                f"推进幕卡：{act.name}",
                detail=rule.get("label") or act.defn.text_zh or act.defn.text or "",
            )
        )

    blocked_play = play_is_blocked(state, player)
    for card_id in player.hand:
        card = state.cards[card_id]
        cost = card.defn.cost or 0
        disabled = cost > player.resources or blocked_play
        options.append(
            ChoiceOption(
                f"play:{card_id}",
                f"打出 {card.name}" + (f"（{cost} 资源）" if card.defn.cost is not None else ""),
                detail=card.defn.text_zh or card.defn.text or "",
                disabled=disabled,
            )
        )

    # activated abilities on your assets and on cards in your threat area
    for asset in [*state.assets_of(player.id), *state.threat_area_of(player.id)]:
        if asset.card_type is CardType.ASSET and "tome" in asset.defn.traits and game.tomes_blanked(asset):
            continue  # The Necronomicon blanks your Tomes
        for index, ability in enumerate(asset.defn.abilities):
            if not ability.is_activated:
                continue
            costs = "，".join(str(c) for c in ability.costs)
            disabled = asset.exhausted or any(
                c.kind is CostKind.RESOURCE and c.amount > player.resources for c in ability.costs
            )
            options.append(
                ChoiceOption(
                    f"activate:{asset.id}:{index}",
                    f"激活 {asset.name}" + (f"（{costs}）" if costs else ""),
                    detail=ability.label or asset.defn.text_zh or asset.defn.text or "",
                    disabled=disabled,
                )
            )

    options.append(ChoiceOption("draw", "抽 1 张牌"))
    options.append(ChoiceOption("resource", "获得 1 资源"))
    return options


def _enemy_detail(enemy: CardInstance) -> str:
    return (
        f"战力 {enemy.defn.fight} / 闪避 {enemy.defn.evade} / "
        f"生命 {max(0, (enemy.defn.health or 0) - enemy.damage)} / "
        f"伤害 {enemy.defn.enemy_damage} / 恐惧 {enemy.defn.enemy_horror}"
    )


FREE_ACTIONS = ("advance_act", "parley")


def execute_action(game, player: Player, action_id: str):
    state = game.state
    investigator = state.investigator_of(player)
    verb, _, target = action_id.partition(":")

    fast = False
    if verb == "activate":
        card_id, _, index = target.partition(":")
        try:
            ability = state.cards[card_id].defn.abilities[int(index)]
            fast = ability.limit == "fast"  # "[fast]" abilities cost no action
        except (KeyError, IndexError, ValueError):
            fast = False

    if verb not in FREE_ACTIONS and not fast:
        extra = game.extra_action_cost(player, verb)
        if extra:
            player.actions_left = max(0, player.actions_left - extra)
            state.log(f"{investigator.name} 因威胁区卡牌额外消耗 {extra} 个行动", kind="action")
        player.actions_left -= 1
        # rules: costs are paid first, then attacks of opportunity, then the effect
        yield from game.attacks_of_opportunity(player, verb)
        if state.finished:
            return

    if verb == "move":
        origin = current_location(state, investigator)
        if origin is not None and origin.defn.meta.get("move_test"):
            rule = origin.defn.meta["move_test"]
            result = yield from game.skill_test(
                investigator=investigator,
                skill=Skill(rule.get("skill", "intellect")),
                difficulty=int(rule.get("difficulty", 3)),
                source=origin,
                kind="move",
            )
            if not result.success:
                state.log(f"{origin.name}：移动被取消", kind="move")
                return
        yield from game.move_investigator(investigator, target)
        return
    if verb == "investigate":
        yield from _investigate(game, player, investigator)
        return
    if verb == "fight":
        yield from _fight(game, player, investigator, state.cards[target])
        return
    if verb == "evade":
        yield from _evade(game, player, investigator, state.cards[target])
        return
    if verb == "engage":
        yield from game.engage(state.cards[target], player)
        return
    if verb == "play":
        yield from _play_card(game, player, investigator, state.cards[target])
        return
    if verb == "playdiscard":
        yield from _play_from_discard(game, player, investigator, state.cards[target])
        return
    if verb == "activate":
        card_id, _, index = target.partition(":")
        yield from _activate(game, player, state.cards[card_id], int(index))
        return
    if verb == "parley":
        yield from _parley(game, player, investigator, state.cards[target])
        return
    if verb == "advance_act":
        yield from _advance_act(game, player)
        return
    if verb == "cultist":
        yield from _draw_from_cultist_deck(game, player)
        return
    if verb == "locact":
        loc_id, _, action_id = target.partition(":")
        yield from _use_location_action(game, player, state.cards[loc_id], action_id)
        return
    if verb == "disrupt":
        yield from _disrupt_ritual(game, player)
        return
    if verb == "sacrifice_lita":
        state.log(f"{investigator.name} 把丽塔·钱德勒推向阿布霍斯……", kind="story")
        state.flags["investigators_sacrificed_lita"] = True
        yield from game.end_scenario("R3")
        return
    if verb == "draw":
        yield from game.draw_cards(player, 1)
        return
    if verb == "resource":
        player.resources += 1
        state.log(f"{investigator.name} 获得 1 资源", kind="resource")
        return
    if verb == "resign":
        state.log(f"{investigator.name} 放弃调查", kind="story")
        player.resigned = True
        yield from game.emit(Trigger.ON_SCENARIO_END, source=investigator, resigned=True)
        yield from game.check_all_defeated()
        return
    raise IllegalActionError(f"unknown action {action_id!r}")


def _investigate(game, player: Player, investigator: CardInstance):
    state = game.state
    location = current_location(state, investigator)
    if location is None:
        raise IllegalActionError("investigator is not at a location")
    # some woods force you to investigate with a different skill (01152-01154)
    skill = Skill(location.defn.meta.get("investigate_skill", Skill.INTELLECT.value))
    result = yield from game.skill_test(
        investigator=investigator,
        skill=skill,
        difficulty=game.shroud_of(location),
        source=location,
        kind="investigate",
    )
    yield from game.emit(Trigger.ON_INVESTIGATE, source=investigator, target=location, result=result)
    if result.success:
        taken = game.discover_clue(investigator, location, 1 + int(result.meta.get("extra_clues", 0)))
        if taken:
            yield from game.emit(Trigger.ON_DISCOVER_CLUE, source=investigator, target=location, amount=taken)


def _fight(game, player: Player, investigator: CardInstance, enemy: CardInstance):
    state = game.state
    weapons = attack_assets(state, player)
    weapon = None
    if len(weapons) == 1:
        weapon = weapons[0]
    elif weapons:
        options = [ChoiceOption(w.id, w.name, detail=str(w.defn.meta.get("attack"))) for w in weapons]
        options.append(ChoiceOption("bare", "徒手攻击（1 伤害）"))
        choice = PendingChoice(
            id=game.next_choice_id(),
            kind=ChoiceKind.OPTION,
            player_id=player.id,
            prompt=f"用什么攻击 {enemy.name}？",
            options=options,
        )
        picked = yield from game.ask(choice)
        weapon = None if picked[0] == "bare" else state.cards[picked[0]]
    attack = (weapon.defn.meta.get("attack") if weapon is not None else None) or {}
    bonus = int(attack.get("combat_bonus", 0))
    damage = int(attack.get("damage", 1))
    # Machete: "If the attacked enemy is the only enemy engaged with you, this attack deals +1 damage."
    if attack.get("only_engaged_bonus") and enemy is not None:
        engaged = [e for e in state.enemies() if player.id in e.engaged_with]
        if len(engaged) == 1 and engaged[0].id == enemy.id:
            damage += int(attack["only_engaged_bonus"])
    skill = Skill(attack.get("skill", Skill.COMBAT.value))
    # only cards that opt in with "spend" consume a counter here; cards that manage
    # their own ammo/charges inside their ability are left alone
    spend = attack.get("spend")
    if spend and weapon is not None and str(spend) in weapon.uses:
        weapon.use(str(spend))
    result = yield from game.skill_test(
        investigator=investigator,
        skill=skill,
        difficulty=game.enemy_fight(enemy),
        source=weapon or investigator,
        target=enemy,
        kind="fight",
        bonus=bonus,
    )
    if weapon is not None and attack.get("breaks_on_bad_token") and result.token is not None:
        if result.token.type in (TokenType.SKULL, TokenType.AUTOFAIL):
            state.log(f"{weapon.name} 在这次攻击中损坏了", kind="discard")
            game.move_to_discard(player, weapon.id)
    yield from game.emit(Trigger.ON_ATTACK, source=weapon or investigator, target=enemy, result=result, damage=damage)
    if result.success:
        # Shotgun: "this attack deals 1 damage for each point you succeed by (min 1, max 5)"
        per_success = attack.get("damage_per_success")
        if per_success:
            cap = int(attack.get("damage_cap", 5))
            damage = min(max(result.margin, 1), cap)
        damage += int(result.meta.get("damage_bonus", 0))
        yield from game.deal_damage(enemy, damage, source=investigator, reason=f"{investigator.name} 的攻击")
        yield from game.emit(Trigger.ON_DAMAGE_DEALT, source=investigator, target=enemy, amount=damage)
        return
    if "retaliate" in enemy.defn.keywords and not enemy.exhausted and not enemy.meta.get("blank"):
        state.log(f"{enemy.name} 反击（Retaliate）", kind="attack")
        yield from game.enemy_attack(enemy, player)


def _evade(game, player: Player, investigator: CardInstance, enemy: CardInstance):
    result = yield from game.skill_test(
        investigator=investigator,
        skill=Skill.AGILITY,
        difficulty=game.enemy_evade(enemy),
        source=investigator,
        target=enemy,
        kind="evade",
    )
    yield from game.emit(Trigger.ON_EVADE, source=investigator, target=enemy, result=result)
    if result.success:
        enemy.exhausted = True
        game.disengage(enemy, player)


def _occupied_slots(state, player: Player) -> dict:
    used: dict = {}
    for asset in state.assets_of(player.id):
        for slot in asset.defn.slots:
            used[slot] = used.get(slot, 0) + 1
    return used


def _make_room_for(game, player: Player, card: CardInstance):
    """Enforce support slot limits: the player discards cards until the slot fits."""
    from ..core.enums import SLOT_CAPACITY

    if not card.defn.slots:
        return
    for slot in card.defn.slots:
        capacity = SLOT_CAPACITY.get(slot, 1)
        for asset in game.state.assets_of(player.id):
            capacity += int((asset.defn.meta.get("extra_slots") or {}).get(slot.value, 0))
        used = _occupied_slots(game.state, player)
        if used.get(slot, 0) < capacity:
            continue
        holders = [a for a in game.state.assets_of(player.id) if slot in a.defn.slots]
        choice = PendingChoice(
            id=game.next_choice_id(),
            kind=ChoiceKind.CARD,
            player_id=player.id,
            prompt=f"{slot.value} 槽位已满（{capacity}），要打出「{card.name}」请先弃掉 1 张",
            options=[ChoiceOption(a.id, a.name, detail=(a.defn.text or "")[:80]) for a in holders],
        )
        picked = yield from game.ask(choice)
        chosen = game.state.cards[picked[0]]
        game.state.log(f"{chosen.name} 被弃置以为「{card.name}」腾出槽位", kind="discard")
        game.move_to_discard(player, chosen.id)


def _play_card(game, player: Player, investigator: CardInstance, card: CardInstance):
    state = game.state
    cost = card.defn.cost or 0
    # Easttown: "While you are in Easttown, reduce the cost of each [[Ally]] asset you play by 2."
    if "ally" in card.defn.traits:
        here = current_location(state, investigator)
        if here is not None:
            cost = max(0, cost - int(here.defn.meta.get("ally_cost_reduction", 0)))
    if cost > player.resources:
        raise RuleError(f"not enough resources to play {card.name}")
    if card.card_type is CardType.ASSET and state.flags.get("slot_limits"):
        yield from _make_room_for(game, player, card)
    player.resources -= cost
    state.log(f"{investigator.name} 打出 {card.name}" + (f"（支付 {cost} 资源）" if cost else ""), kind="play")
    if card.card_type is CardType.ASSET:
        game.remove_from_zones(player, card.id)
        card.zone = Zone.PLAY
        card.controller_id = player.id
        card.in_play_since_round = state.round
        player.play_area.append(card.id)
        if card.defn.uses:
            card.uses = dict(card.defn.uses)
        yield from game.emit(Trigger.ON_ENTER_PLAY, source=card, target=investigator)
        return
    effect = card.defn.meta.get("play")
    if effect is not None:
        ctx = EffectContext(game=game, source=card, controller=player, payload={"investigator": investigator})
        yield from game.run_effect(effect, ctx)
    yield from game.emit(Trigger.ON_ENTER_PLAY, source=card, target=investigator)
    if card.meta.get("stays_in_play"):
        return  # attached to a location (Barricade)
    game.move_to_discard(player, card.id)


def _play_from_discard(game, player: Player, investigator: CardInstance, card: CardInstance):
    """Wendy's Amulet: play the topmost event in your discard pile as if it were in your hand."""
    state = game.state
    cost = card.defn.cost or 0
    if cost > player.resources:
        raise RuleError(f"not enough resources to play {card.name}")
    player.resources -= cost
    if card.id in player.discard:
        player.discard.remove(card.id)
    state.log(f"{investigator.name} 通过温蒂的护符打出 {card.name}", kind="play")
    effect = card.defn.meta.get("play")
    if effect is not None:
        ctx = EffectContext(game=game, source=card, controller=player, payload={"investigator": investigator})
        yield from game.run_effect(effect, ctx)
    yield from game.emit(Trigger.ON_ENTER_PLAY, source=card, target=investigator)
    card.zone = Zone.DISCARD
    if card.id not in player.discard:
        player.discard.append(card.id)


def _activate(game, player: Player, card: CardInstance, index: int):
    state = game.state
    investigator = state.investigator_of(player)
    try:
        ability = card.defn.abilities[index]
    except IndexError:
        raise IllegalActionError(f"{card.name} has no ability #{index}") from None
    for cost in ability.costs:
        if cost.kind is CostKind.RESOURCE:
            if player.resources < cost.amount:
                raise RuleError(f"not enough resources to activate {card.name}")
            player.resources -= cost.amount
        elif cost.kind is CostKind.EXHAUST:
            if card.exhausted:
                raise RuleError(f"{card.name} is already exhausted")
            card.exhausted = True
        elif cost.kind is CostKind.ACTION:
            player.actions_left -= max(0, cost.amount - 1)
        elif cost.kind is CostKind.DAMAGE:
            yield from game.deal_damage(investigator, cost.amount, source=card, reason=f"{card.name} 的代价")
        elif cost.kind is CostKind.HORROR:
            yield from game.deal_horror(investigator, cost.amount, source=card, reason=f"{card.name} 的代价")
        else:
            raise RuleError(f"unhandled cost {cost.kind} on {card.name}")
    state.log(f"{investigator.name} 使用 {card.name}" + (f"：{ability.label}" if ability.label else ""), kind="activate")
    ctx = EffectContext(game=game, source=card, controller=player, payload={"investigator": investigator})
    yield from game.run_effect(ability.effect, ctx)


def _parley(game, player: Player, investigator: CardInstance, card: CardInstance):
    state = game.state
    rule = card.defn.meta.get("parley") or {}
    cost = rule.get("cost")
    # the Midnight Masks cultists are bought, not beaten: pay, then they join the victory display
    if cost == "cards":
        if len(player.hand) < 4:
            raise IllegalActionError("手牌不足 4 张，无法谈判")
        for remaining in (4, 3, 2, 1):
            choice = PendingChoice(
                id=game.next_choice_id(),
                kind=ChoiceKind.CARD,
                player_id=player.id,
                prompt=f"谈判 {card.name}：选择要弃掉的牌（还剩 {remaining} 张）",
                options=[ChoiceOption(cid, state.cards[cid].name) for cid in player.hand],
            )
            picked = yield from game.ask(choice)
            game.move_to_discard(player, picked[0])
    elif cost == "clues":
        if investigator.clues < 2:
            raise IllegalActionError("线索不足 2 条，无法谈判")
        investigator.clues -= 2
    elif cost == "resources":
        if player.resources < 5:
            raise IllegalActionError("资源不足 5，无法谈判")
        player.resources -= 5

    skill = Skill(rule.get("skill", "intellect"))
    difficulty = int(rule.get("difficulty", 4))
    result = yield from game.skill_test(
        investigator=investigator, skill=skill, difficulty=difficulty, source=card, kind="parley"
    )
    if not result.success:
        return
    if rule.get("victory"):
        card.engaged_with.clear()
        card.zone = Zone.ENCOUNTER_DISCARD
        card.location_id = None
        game.state.victory_display.append(card.id)
        state.log(f"{card.name} 通过谈判进入胜利展示区", kind="victory")
        return
    card.controller_id = player.id
    card.zone = Zone.PLAY
    card.location_id = None
    player.play_area.append(card.id)
    state.log(f"{investigator.name} 通过谈判获得了 {card.name} 的控制权", kind="story")


def _use_location_action(game, player: Player, location: CardInstance, action_id: str):
    handler = LOCATION_ACTIONS.get(action_id)
    if handler is None:
        raise IllegalActionError(f"地点行动 {action_id} 未注册")
    result = handler(game, player, location)
    if inspect.isgenerator(result):
        yield from result
    game.note_location_action(location, action_id)


def _disrupt_ritual(game, player: Player):
    """Act 01148: [action] Spend 1 clue: test willpower (3) or agility (3); on success place 1 clue on the act."""
    state = game.state
    investigator = state.investigator_of(player)
    if investigator.clues <= 0:
        raise IllegalActionError("没有线索可以花费")
    choice = PendingChoice(
        id=game.next_choice_id(),
        kind=ChoiceKind.OPTION,
        player_id=player.id,
        prompt="仪式：用意志（3）还是敏捷（3）？",
        options=[ChoiceOption("willpower", "意志 3"), ChoiceOption("agility", "敏捷 3")],
    )
    picked = yield from game.ask(choice)
    skill = Skill.WILLPOWER if picked[0] == "willpower" else Skill.AGILITY
    investigator.clues -= 1
    state.log(f"{investigator.name} 花费 1 条线索干扰仪式", kind="clue")
    result = yield from game.skill_test(
        investigator=investigator, skill=skill, difficulty=3, source=state.current_act(), kind="activate"
    )
    if result.success:
        state.act_progress += 1
        state.log(f"幕卡上现在有 {state.act_progress} 条线索", kind="story")


def _draw_from_cultist_deck(game, player: Player):
    """Act 01123: the investigators spend 2 clues per investigator to draw a cultist."""
    state = game.state
    deck = state.flags.get("cultist_deck") or []
    if not deck:
        raise IllegalActionError("邪教徒牌库已空")
    needed = 2 * max(1, len([p for p in state.players if p.is_active]))
    remaining = needed
    for other in state.players:
        if remaining <= 0:
            break
        if not other.is_active:
            continue
        investigator = state.investigator_of(other)
        remaining -= game.spend_clues(investigator, min(investigator.clues, remaining))
    if remaining > 0:
        raise IllegalActionError("线索不足，无法抽取邪教徒牌库")
    card_id = deck.pop(0)
    card = state.cards[card_id]
    state.log(f"调查员们花费 {needed} 条线索，{card.name} 被找了出来", kind="story")
    yield from game.spawn_enemy(card, player)


def _advance_act(game, player: Player):
    state = game.state
    act = state.current_act()
    if act is None:
        raise IllegalActionError("there is no act to advance")
    rule = game.act_advance_rule(act)
    required = int(rule.get("clues", act.defn.clues_required) or 0)
    if rule.get("per_investigator"):
        required *= max(1, len([p for p in state.players if p.is_active]))
    remaining = required
    location_id = rule.get("location")
    for other in state.players:
        if remaining <= 0:
            break
        if not other.is_active:
            continue
        investigator = state.investigator_of(other)
        if location_id and investigator.meta.get("location_id") != location_id:
            continue
        remaining -= game.spend_clues(investigator, min(investigator.clues, remaining))
    yield from game.advance_act()
