"""The game engine.

The whole flow is written as one generator.  Whenever a player must decide
something the generator yields a PendingChoice; the driver parks it on
state.pending and returns.  Feeding an answer back in resumes the generator
exactly where it stopped.  Card abilities are generators too, so a card that
asks a question reads like its own card text:

    def effect(ctx):
        if (yield from ctx.ask_yes_no("闪避这次攻击？")):
            ...

This keeps timing and interaction in one place without a hand written state
machine per card.
"""

from __future__ import annotations

import inspect
from typing import Any, Callable, Generator, Iterable, Sequence

from ..core.cards import Ability, CardInstance
from ..core.choices import ChoiceAnswer, ChoiceOption, PendingChoice
from ..core.enums import AbilityKind, CardType, ChoiceKind, Phase, Skill, Trigger, Zone
from ..core.errors import AhlcgError, ChoiceError, RuleError
from ..core.events import AbilityRef, GameEvent, Modifier, order_triggered
from .chaos import ChaosBag
from .effects import EffectContext
from .skill_test import SkillTest, SkillTestResult, resolve_skill_test
from .state import GameState, Player

HAND_SIZE = 8


class Game:
    """Runs one scenario over a GameState."""

    def __init__(self, state: GameState | None = None, scenario: Any = None) -> None:
        self.state = state if state is not None else GameState()
        self.scenario = scenario
        self._gen: Generator[PendingChoice, Any, Any] | None = None

    # ------------------------------------------------------------------
    # driver
    # ------------------------------------------------------------------
    def next_choice_id(self) -> str:
        return self.state.choice_ids.next()

    def start(self, flow: Generator[PendingChoice, Any, Any] | None = None) -> None:
        """Begin driving the game.

        An explicit flow always replaces the current driver (test harnesses use this
        to run a single action or card effect).  Calling start() with no argument is
        idempotent, so the campaign builder and the robot may both call it without
        the scenario setup running twice.
        """
        if flow is not None:
            self._gen = flow
        else:
            if self._gen is not None:
                return
            self._gen = self.run_scenario()
        self._pump(None)

    @property
    def awaiting(self) -> PendingChoice | None:
        return self.state.pending[-1] if self.state.pending else None

    def _pump(self, value: Any) -> None:
        """Resume the flow until it asks a question (or finishes).

        A bare "yield" inside the flow means "just keep going" and is skipped,
        which lets helper generators be written without ceremony.
        """
        if self._gen is None:
            raise AhlcgError("game has not been started")
        while True:
            try:
                yielded = self._gen.send(value)
            except StopIteration:
                self.state.finished = True
                return
            if yielded is None:
                value = None
                continue
            if not isinstance(yielded, PendingChoice):
                raise AhlcgError(f"flow yielded {type(yielded).__name__}, expected PendingChoice")
            self.state.pending.append(yielded)
            return

    def resolve(self, answer: ChoiceAnswer) -> None:
        if not self.state.pending:
            raise ChoiceError("there is nothing waiting to be resolved")
        choice = self.state.pending[-1]
        selected = choice.validate(answer)
        self.state.pending.pop()
        self._pump(selected)

    def answer(self, *selected: str, choice_id: str | None = None) -> None:
        """Testing / robot convenience: answer the pending choice."""
        choice = self.awaiting
        if choice is None:
            raise ChoiceError("no pending choice to answer")
        self.resolve(ChoiceAnswer(choice_id or choice.id, tuple(selected)))

    def answer_first(self) -> None:
        """Answer with the first non-disabled option (used by simple robots)."""
        choice = self.awaiting
        if choice is None:
            raise ChoiceError("no pending choice to answer")
        for option in choice.options:
            if not option.disabled:
                self.resolve(ChoiceAnswer(choice.id, (option.id,)))
                return
        if choice.optional:
            self.resolve(ChoiceAnswer(choice.id, cancelled=True))
            return
        raise ChoiceError(f"choice {choice.id!r} has no legal option")

    def ask(self, choice: PendingChoice) -> Generator[PendingChoice, tuple[str, ...], tuple[str, ...]]:
        return (yield choice)

    def run_effect(self, effect: Callable[[EffectContext], Any] | None, ctx: EffectContext):
        """Run a card effect, which may be a plain function or a generator."""
        if effect is None:
            return
        result = effect(ctx)
        if inspect.isgenerator(result):
            yield from result

    # ------------------------------------------------------------------
    # scenario flow
    # ------------------------------------------------------------------
    def run_scenario(self):
        if self.scenario is None:
            raise AhlcgError("no scenario attached to this game")
        self.state.scenario_code = self.scenario.code
        self.state.scenario_name = self.scenario.name
        self.state.log(f"=== {self.scenario.name} 开始 ===", kind="story")
        # a scenario's setup may be a plain function or a generator
        setup = self.scenario.setup(self)
        if inspect.isgenerator(setup):
            yield from setup
        yield from self.mulligan()
        yield from self.emit(Trigger.ON_SCENARIO_START, source=None)
        while not self.state.finished:
            yield from self.run_round()
        yield from self.emit(Trigger.ON_SCENARIO_END, source=None)

    def mulligan(self):
        """Opening hand mulligan: set any number of cards aside, draw replacements,
        then shuffle the set-aside cards back into the deck."""
        if not self.state.flags.get("mulligan", True):
            return
        for player in self.state.players:
            if not player.hand:
                continue
            options = [
                ChoiceOption(
                    card_id,
                    self.state.cards[card_id].name,
                    detail=(self.state.cards[card_id].defn.text_zh or self.state.cards[card_id].defn.text or "")[:60],
                )
                for card_id in player.hand
            ]
            choice = PendingChoice(
                id=self.next_choice_id(),
                kind=ChoiceKind.CARDS,
                player_id=player.id,
                prompt="起手重抽：选择任意张手牌换掉（也可全部保留）",
                options=options,
                min_selected=0,
                max_selected=len(options),
                optional=True,
            )
            picked = yield from self.ask(choice)
            if not picked:
                continue
            set_aside = []
            for card_id in picked:
                if card_id in player.hand:
                    player.hand.remove(card_id)
                    set_aside.append(card_id)
            for _ in set_aside:
                if player.deck:
                    new_id = player.deck.pop(0)
                    self.state.cards[new_id].zone = Zone.HAND
                    player.hand.append(new_id)
            player.deck.extend(set_aside)
            for card_id in set_aside:
                self.state.cards[card_id].zone = Zone.DECK
            self.state.rng.shuffle(player.deck)
            self.state.log(
                f"{self.state.investigator_of(player).name} 重抽了 {len(set_aside)} 张起手牌", kind="draw"
            )

    def run_round(self):
        self.state.round += 1
        self.state.log(f"--- 第 {self.state.round} 轮 ---", kind="round")
        yield from self.emit(Trigger.ON_ROUND_START, source=None)
        for phase in (Phase.MYTHOS, Phase.INVESTIGATION, Phase.ENEMY, Phase.UPKEEP):
            if self.state.finished:
                return
            if phase is Phase.MYTHOS and self.state.round == 1:
                # Rules Reference, I. Mythos phase: skip during the first round of the game.
                self.state.log("（第一轮跳过神话阶段）", kind="phase")
                continue
            self.state.phase = phase
            yield from self.emit(Trigger.ON_PHASE_START, source=None, phase=phase)
            if phase is Phase.MYTHOS:
                yield from self.phase_mythos()
            elif phase is Phase.INVESTIGATION:
                yield from self.phase_investigation()
            elif phase is Phase.ENEMY:
                yield from self.phase_enemy()
            else:
                yield from self.phase_upkeep()
            yield from self.emit(Trigger.ON_PHASE_END, source=None, phase=phase)
        yield from self.emit(Trigger.ON_ROUND_END, source=None)

    # -- phases ---------------------------------------------------------
    def phase_mythos(self):
        self.state.log("【神话阶段】", kind="phase")
        agenda = self.state.current_agenda()
        if agenda is not None:
            yield from self.place_doom(agenda, 1)

        drawn: list[tuple[Player, CardInstance | None]] = []
        for player in self.state.active_players_in_order():
            if not player.is_active:
                continue
            drawn.append((player, self.draw_encounter(player)))
        for player, card in drawn:
            if card is None or self.state.finished:
                continue
            yield from self.resolve_encounter(player, card)

    def phase_investigation(self):
        self.state.log("【调查阶段】", kind="phase")
        for player in self.state.active_players_in_order():
            if not player.is_active or self.state.finished:
                continue
            yield from self.take_turn(player)

    def phase_enemy(self):
        self.state.log("【敌人阶段】", kind="phase")
        # 3.2 hunter enemies move towards their prey
        for enemy in list(self.state.enemies()):
            if self.state.finished:
                return
            if enemy.exhausted or not enemy.defn.hunter or enemy.meta.get("blank"):
                continue
            yield from self.hunter_move(enemy)
        # 3.3 each investigator resolves the attacks of enemies engaged with them
        for player in self.state.active_players_in_order():
            if not player.is_active:
                continue
            for enemy in list(self.state.engaged_enemies(player.id)):
                if self.state.finished:
                    return
                if enemy.exhausted:
                    continue
                yield from self.enemy_attack(enemy, player)

    def phase_upkeep(self):
        self.state.log("【维持阶段】", kind="phase")
        # 4.3 ready each exhausted card (investigators, their assets, and enemies)
        for player in self.state.active_players_in_order():
            if not player.is_active:
                continue
            self.state.investigator_of(player).exhausted = False
            for asset in self.state.assets_of(player.id):
                asset.exhausted = False
        for enemy in self.state.enemies():
            enemy.exhausted = False
        # 4.4 each investigator draws 1 card and gains 1 resource
        for player in self.state.active_players_in_order():
            if not player.is_active:
                continue
            investigator = self.state.investigator_of(player)
            player.resources += 1
            self.state.log(f"{investigator.name} 获得 1 资源（维持阶段）", kind="resource")
            yield from self.draw_cards(player, 1)
            yield from self.discard_down_to_hand_size(player)

    def take_turn(self, player: Player):
        from .actions import execute_action, legal_actions

        investigator = self.state.investigator_of(player)
        player.actions_left = 3 + self.extra_actions(player)
        if player.actions_left > 3:
            self.state.log(f"{investigator.name} 本回合有 {player.actions_left} 个行动", kind="turn")
        self.state.log(f"== {investigator.name} 的回合 ==", kind="turn")
        while player.actions_left > 0 and not self.state.finished and player.is_active:
            options = legal_actions(self, player)
            options.append(ChoiceOption("pass", "结束回合", detail=f"剩余行动：{player.actions_left}"))
            choice = PendingChoice(
                id=self.next_choice_id(),
                kind=ChoiceKind.OPTION,
                player_id=player.id,
                prompt=f"选择行动（剩余 {player.actions_left}）",
                options=options,
            )
            picked = yield from self.ask(choice)
            action_id = picked[0]
            if action_id == "pass":
                break
            yield from execute_action(self, player, action_id)
        self.state.log(f"{investigator.name} 结束回合", kind="turn")
        yield from self.emit(Trigger.ON_TURN_END, source=investigator, player=player.id)
        # Dark Memory: "If Dark Memory is in your hand at the end of your turn: reveal it and take 2 horror."
        for card_id in list(player.hand):
            card = self.state.cards[card_id]
            if card.code == "01013":
                self.state.log(f"{investigator.name} 手中的黑暗记忆发作了", kind="horror")
                yield from self.deal_horror(investigator, 2, source=card, reason="Dark Memory")

    # ------------------------------------------------------------------
    # triggered abilities
    # ------------------------------------------------------------------
    def constant_bonus(self, investigator: CardInstance, skill: Skill, kind: str | None = None) -> int:
        """Static bonuses/penalties from cards the investigator controls.

        A card declares them as data:
            meta["constant"] = [{"skill": "intellect", "amount": 1, "kind": ["investigate"]}]
            meta["penalty"]  = [{"skill": "willpower", "amount": 1}]
        """
        total = 0
        owner = investigator.controller_id
        for card in list(self.state.cards.values()):
            if card.zone not in (Zone.PLAY, Zone.THREAT_AREA, Zone.PLAY_AREA):
                continue
            if owner is not None and card.controller_id != owner:
                continue
            for key, sign in (("constant", 1), ("penalty", -1)):
                for spec in card.defn.meta.get(key) or ():
                    if spec.get("skill") and spec["skill"] != skill.value:
                        continue
                    kinds = spec.get("kind")
                    if kind and kinds and kind not in kinds:
                        continue
                    total += sign * int(spec.get("amount", 0))
        return total

    def extra_actions(self, player: Player) -> int:
        """Extra actions per turn granted by cards in play (Leo De Luca)."""
        return sum(int(card.defn.meta.get("extra_action", 0)) for card in self.state.assets_of(player.id))

    def collect_abilities(
        self, trigger: Trigger, event: GameEvent, extra_sources: Sequence[CardInstance] = ()
    ) -> list[AbilityRef]:
        refs: list[AbilityRef] = []
        for card in list(self.state.cards.values()):
            if card.zone not in (Zone.PLAY, Zone.THREAT_AREA, Zone.PLAY_AREA):
                continue
            if card.card_type is CardType.INVESTIGATOR and self.is_blanked(card):
                continue  # Stubborn Detective blanks the investigator's text box
            if card.card_type is CardType.ASSET and "tome" in card.defn.traits and self.tomes_blanked(card):
                continue  # The Necronomicon blanks the text box of every Tome you control
            for ability in card.defn.abilities:
                if ability.trigger is trigger:
                    refs.append(AbilityRef(source=card, ability=ability, event=event))
        for card in extra_sources:
            for ability in card.defn.abilities:
                if ability.trigger is trigger:
                    refs.append(AbilityRef(source=card, ability=ability, event=event))
        for ability in self.state.global_abilities.get(trigger.value, []):
            refs.append(AbilityRef(source=ability.source if hasattr(ability, "source") else None, ability=ability, event=event))
        return refs

    def emit(
        self,
        trigger: Trigger,
        *,
        source: Any = None,
        target: Any = None,
        extra_sources: Sequence[CardInstance] = (),
        payload: dict[str, Any] | None = None,
        **kwargs: Any,
    ):
        # callers may pass a payload dict to observe (or let abilities rewrite) it;
        # when they do, we must use their dict itself, not a copy
        data: dict[str, Any] = payload if payload is not None else {}
        data.update(kwargs)
        event = GameEvent(trigger=trigger, source=source, target=target, payload=data)
        refs = self.collect_abilities(trigger, event, extra_sources)
        if not refs:
            return
        active_id = self.state.active_player.id if self.state.active_player else None
        for ref in order_triggered(refs, active_id, owner_of=lambda src: getattr(src, "controller_id", None)):
            if self.state.finished:
                return
            controller = self.state.player_of(ref.source) if ref.source is not None else None
            ctx = EffectContext(game=self, source=ref.source, controller=controller, event=event)
            ability = ref.ability
            if ability.condition is not None and not ability.condition(ctx):
                continue
            if not ref.is_forced:
                label = ability.label or getattr(ref.source, "name", "能力")
                asked = yield from EffectContext(game=self, source=ref.source, controller=controller).ask_yes_no(
                    f"是否发动「{label}」？"
                )
                if not asked:
                    continue
            yield from self.run_effect(ability.effect, ctx)

    # ------------------------------------------------------------------
    # skill tests
    # ------------------------------------------------------------------
    def skill_test(
        self,
        *,
        investigator: CardInstance,
        skill: Skill,
        difficulty: int,
        source: Any = None,
        target: Any = None,
        kind: str = "skill",
        bonus: int = 0,
    ) -> Generator[PendingChoice, Any, SkillTestResult]:
        # Mind over Matter: "you may use your [intellect] in place of your [combat] and [agility]"
        if self.state.flags.get("mind_over_matter_round") == self.state.round and skill in (Skill.COMBAT, Skill.AGILITY):
            skill = Skill.INTELLECT
        base = int(investigator.defn.stat(skill) or 0) + self.constant_bonus(investigator, skill, kind)
        # temporary bonuses such as Encyclopedia ("+2 to a skill until the end of the phase")
        temp = investigator.meta.get("temp_skill_bonus") or {}
        if temp.get("round") == self.state.round and temp.get("skill") == skill.value:
            base += int(temp.get("amount", 0))
        test = SkillTest(
            skill=skill,
            difficulty=difficulty,
            base_value=base + bonus,
            kind=kind,
            investigator_id=investigator.id,
            source=source,
            target=target,
        )
        yield from self.emit(Trigger.ON_TEST_START, source=source or investigator, target=target, test=test)
        player = self.state.player_of(investigator)
        if player is not None:
            yield from self.commit_window(player, test)
            yield from self.in_test_window(player, test)
        yield from self.emit(Trigger.ON_BEFORE_REVEAL, source=source or investigator, target=target, test=test)
        bag = self.state.chaos_bag
        if self.state.flags.get("no_chaos_tokens_round") == self.state.round:
            # Will to Survive: "do not reveal chaos tokens for the rest of your turn"
            from .chaos import numeric as _numeric

            token = _numeric(0)
            self.state.log("（本回合不再揭示混沌标记）", kind="skill_test")
        else:
            token = bag.draw(self.state.rng)

        # "reveal two tokens and choose one" (Grotesque Statue)
        if player is not None:
            for asset in list(self.state.assets_of(player.id)):
                spec = asset.defn.meta.get("reveal_choice")
                if not spec:
                    continue
                key = str(spec.get("spend", "charge"))
                if asset.uses.get(key, 0) <= 0:
                    continue
                asked = yield from EffectContext(game=self, source=asset, controller=player).ask_yes_no(
                    f"使用「{asset.name}」额外揭示 1 个标记并从中选择？"
                )
                if not asked:
                    continue
                asset.use(key)
                other = bag.draw(self.state.rng)
                choice = PendingChoice(
                    id=self.next_choice_id(),
                    kind=ChoiceKind.OPTION,
                    player_id=player.id,
                    prompt=f"{asset.name}：选择要使用的标记",
                    options=[
                        ChoiceOption("first", f"{token.label}（{bag.value_of(token, test):+d}）"),
                        ChoiceOption("second", f"{other.label}（{bag.value_of(other, test):+d}）"),
                    ],
                )
                picked = yield from self.ask(choice)
                token = other if picked[0] == "second" else token
                if asset.defn.meta.get("discard_when_empty") and asset.uses.get(key, 0) <= 0:
                    self.move_to_discard(player, asset.id)
                    self.state.log(f"{asset.name} 用尽了充能，被弃置", kind="discard")
                break

        # cards may rewrite the revealed token (Sure Gamble, Eucatastrophe)
        reveal_payload: dict[str, Any] = {"token": token, "test": test}
        hand_cards = [self.state.cards[cid] for cid in player.hand] if player is not None else []
        yield from self.emit(
            Trigger.ON_REVEAL_TOKEN,
            source=source or investigator,
            target=target,
            extra_sources=hand_cards,
            payload=reveal_payload,
            test=test,
        )
        token = reveal_payload["token"]
        from .skill_test import evaluate_skill_test

        result = evaluate_skill_test(test, token, bag, test)
        self.state.skill_test = result
        self.state.log(result.describe(), kind="skill_test")
        yield from self.emit(Trigger.ON_TEST_RESULT, source=source or investigator, target=target, test=test, result=result)
        committed_cards = [
            self.state.cards[entry.card_id] for entry in test.committed if entry.card_id in self.state.cards
        ]
        yield from self.emit(
            Trigger.ON_SUCCESS if result.success else Trigger.ON_FAIL,
            source=source or investigator,
            target=target,
            extra_sources=committed_cards,
            test=test,
            result=result,
        )
        if player is not None:
            keep = set(test.meta.get("keep_cards") or ())
            for entry in list(test.committed):
                if entry.card_id and entry.card_id in player.hand and entry.card_id not in keep:
                    self.move_to_discard(player, entry.card_id)
        yield from self.emit(Trigger.ON_TEST_END, source=source or investigator, target=target, test=test, result=result)
        return result

    def in_test_window(self, player: Player, test: SkillTest):
        """Offer "during a skill test" abilities (Physical Training, Arcane Studies).

        A card declares them as data:
            meta["in_test"] = {"skills": ["willpower", "combat"], "cost": 1, "bonus": 1, "label": "..."}
        """
        while True:
            options: list[ChoiceOption] = []
            for card in self.state.assets_of(player.id):
                spec = card.defn.meta.get("in_test")
                if not spec:
                    continue
                skills = spec.get("skills") or ([spec["skill"]] if spec.get("skill") else [])
                if skills and test.skill.value not in skills:
                    continue
                kinds = spec.get("kind")
                if kinds and test.kind not in kinds:
                    continue
                if player.resources < int(spec.get("cost", 1)):
                    continue
                options.append(
                    ChoiceOption(
                        card.id,
                        f"{card.name}：花 {int(spec.get('cost', 1))} 资源 +{int(spec.get('bonus', 1))}",
                        detail=spec.get("label", ""),
                    )
                )
            if not options:
                return
            odds = self.state.chaos_bag.success_probability(test.skill_value(), test.difficulty, test)
            choice = PendingChoice(
                id=self.next_choice_id(),
                kind=ChoiceKind.OPTION,
                player_id=player.id,
                prompt=f"{test.describe()}，成功率 {odds:.0%}。要使用检定中的能力吗？",
                options=options,
                min_selected=0,
                max_selected=1,
                optional=True,
            )
            picked = yield from self.ask(choice)
            if not picked:
                return
            card = self.state.cards[picked[0]]
            spec = card.defn.meta["in_test"]
            player.resources -= int(spec.get("cost", 1))
            test.add_modifier(int(spec.get("bonus", 1)), source=card, reason=card.name)
            self.state.log(f"{card.name}：技能值 +{int(spec.get('bonus', 1))}（花费 {int(spec.get('cost', 1))} 资源）", kind="skill_test")

    def commit_window(self, player: Player, test: SkillTest):
        options: list[ChoiceOption] = []
        max_one_names: set[str] = set()
        for card_id in player.hand:
            card = self.state.cards[card_id]
            bonus = card.defn.commit_bonus(test.skill)
            if bonus <= 0:
                continue
            if card.defn.meta.get("max_one_committed"):
                max_one_names.add(card.defn.name)
            icons = card.defn.icon_count(test.skill)
            wild = card.defn.wild_icons
            detail = f"投入 +{bonus}" + (f"（本技能 {icons} + 万能 {wild}）" if wild else "")
            if card.defn.meta.get("max_one_committed"):
                detail += "（每次检定限 1 张）"
            options.append(ChoiceOption(card_id, card.name, detail=detail))
        if not options:
            return
        odds = self.state.chaos_bag.success_probability(test.skill_value(), test.difficulty, test)
        choice = PendingChoice(
            id=self.next_choice_id(),
            kind=ChoiceKind.COMMIT,
            player_id=player.id,
            prompt=f"{test.describe()}，当前成功率 {odds:.0%}。要投入卡牌吗？",
            options=options,
            min_selected=0,
            max_selected=len(options),
            optional=True,
        )
        picked = yield from self.ask(choice)
        seen_max_one: set[str] = set()
        for card_id in picked:
            card = self.state.cards[card_id]
            if card.defn.meta.get("max_one_committed"):
                if card.defn.name in seen_max_one:
                    self.state.log(f"「{card.name}」每次检定只能投入 1 张，已忽略多余的", kind="skill_test")
                    continue
                seen_max_one.add(card.defn.name)
            test.commit_card(card_id, card.defn.icons, card.defn.wild_icons, card.name)

    # ------------------------------------------------------------------
    # board mutation
    # ------------------------------------------------------------------
    def move_to_discard(self, player: Player, card_id: str) -> None:
        card = self.state.cards[card_id]
        # The Necronomicon: "It cannot leave play while it has 1 or more horror on it."
        if card.zone in (Zone.PLAY, Zone.PLAY_AREA, Zone.THREAT_AREA) and card.defn.meta.get("anchored") and card.horror > 0:
            self.state.log(f"{card.name} 无法离开场上（其上仍有恐惧）", kind="story")
            return
        self.remove_from_zones(player, card_id)
        card.zone = Zone.DISCARD
        card.exhausted = False
        card.damage = 0
        card.horror = 0
        player.discard.append(card_id)

    def remove_from_zones(self, player: Player, card_id: str) -> None:
        for zone in (player.hand, player.play_area, player.threat_area, player.deck, player.set_aside):
            if card_id in zone:
                zone.remove(card_id)

    def draw_cards(self, player: Player, count: int):
        investigator = self.state.investigator_of(player)
        for _ in range(count):
            if player.deck:
                card_id = player.deck.pop(0)
                card = self.state.cards[card_id]
                player.hand.append(card_id)
                card.zone = Zone.HAND
                self.state.log(f"{investigator.name} 抽了 1 张牌（{len(player.hand)} 张手牌）", kind="draw")
                if card.defn.weakness and card.defn.meta.get("resolve"):
                    # a weakness drawn from the deck resolves its Revelation immediately
                    from .effects import EffectContext as _Ctx

                    self.state.log(f"{investigator.name} 抽到了弱点：{card.name}", kind="story")
                    yield from self.run_effect(
                        card.defn.meta["resolve"],
                        _Ctx(game=self, source=card, controller=player, payload={"investigator": investigator}),
                    )
            else:
                self.state.log(f"{investigator.name} 的牌库已空，受到 1 点恐惧", kind="horror")
                yield from self.deal_horror(investigator, 1, reason="牌库为空")
                break

    def discard_down_to_hand_size(self, player: Player):
        investigator = self.state.investigator_of(player)
        while len(player.hand) > HAND_SIZE:
            options = []
            for card_id in player.hand:
                card = self.state.cards[card_id]
                options.append(
                    ChoiceOption(
                        card_id,
                        card.name,
                        detail=card.defn.text_zh or card.defn.text or "",
                    )
                )
            choice = PendingChoice(
                id=self.next_choice_id(),
                kind=ChoiceKind.CARD,
                player_id=player.id,
                prompt=f"手牌上限 {HAND_SIZE}，请弃掉 1 张牌",
                options=options,
            )
            picked = yield from self.ask(choice)
            self.state.log(f"{investigator.name} 弃掉了 {self.state.cards[picked[0]].name}", kind="discard")
            self.move_to_discard(player, picked[0])

    def deal_damage(self, target: CardInstance, amount: int, source: Any = None, reason: str = ""):
        if amount <= 0:
            return
        if target.card_type is CardType.INVESTIGATOR:
            yield from self.assign_damage(target, amount, source=source, reason=reason)
            return
        target.damage += amount
        self.state.log(f"{target.name} 受到 {amount} 点伤害（{target.damage}/{target.defn.health}）", kind="damage")
        yield from self.emit(Trigger.ON_DAMAGE_TAKEN, source=source, target=target, amount=amount)
        if target.is_defeated():
            yield from self.defeat_card(target, source=source)

    def deal_horror(self, target: CardInstance, amount: int, source: Any = None, reason: str = ""):
        if amount <= 0:
            return
        if target.card_type is CardType.INVESTIGATOR:
            yield from self.assign_horror(target, amount, source=source, reason=reason)
            return
        target.horror += amount
        self.state.log(f"{target.name} 受到 {amount} 点恐惧（{target.horror}/{target.defn.sanity}）", kind="horror")
        yield from self.emit(Trigger.ON_HORROR_TAKEN, source=source, target=target, amount=amount)
        if target.is_defeated():
            yield from self.defeat_card(target, source=source)

    def soak_options(self, investigator: CardInstance, kind: str) -> list[CardInstance]:
        player = self.state.player_of(investigator)
        if player is None:
            return []
        out = []
        for asset in self.state.assets_of(player.id):
            if kind == "damage" and asset.health_remaining() is not None and asset.health_remaining() > 0:
                out.append(asset)
            if kind == "horror" and asset.sanity_remaining() is not None and asset.sanity_remaining() > 0:
                out.append(asset)
        return out

    def _assign(self, investigator: CardInstance, amount: int, kind: str, source: Any, reason: str):
        player = self.state.player_of(investigator)
        if player is None:
            return
        for _ in range(amount):
            options = []
            if kind == "damage" and (investigator.health_remaining() or 0) > 0:
                options.append(ChoiceOption(investigator.id, f"{investigator.name}（{investigator.health_remaining()} 生命）"))
            if kind == "horror" and (investigator.sanity_remaining() or 0) > 0:
                options.append(ChoiceOption(investigator.id, f"{investigator.name}（{investigator.sanity_remaining()} 理智）"))
            for asset in self.soak_options(investigator, kind):
                remaining = asset.health_remaining() if kind == "damage" else asset.sanity_remaining()
                options.append(ChoiceOption(asset.id, f"{asset.name}（可承受 {remaining}）"))
            if len(options) <= 1:
                chosen = options[0].id if options else investigator.id
            else:
                choice = PendingChoice(
                    id=self.next_choice_id(),
                    kind=ChoiceKind.ASSIGN_DAMAGE,
                    player_id=player.id,
                    prompt=f"分配 1 点{'伤害' if kind == 'damage' else '恐惧'}" + (f"（{reason}）" if reason else ""),
                    options=options,
                )
                picked = yield from self.ask(choice)
                chosen = picked[0]
            card = self.state.cards[chosen]
            if kind == "damage":
                card.damage += 1
                self.state.log(f"{card.name} 受到 1 点伤害（{card.damage}/{card.defn.health}）", kind="damage")
            else:
                card.horror += 1
                self.state.log(f"{card.name} 受到 1 点恐惧（{card.horror}/{card.defn.sanity}）", kind="horror")
            if card.is_defeated():
                yield from self.defeat_card(card, source=source)

    def assign_damage(self, investigator: CardInstance, amount: int, source: Any = None, reason: str = ""):
        payload = {"amount": amount}
        player = self.state.player_of(investigator)
        hand = [self.state.cards[cid] for cid in player.hand] if player is not None else []
        yield from self.emit(
            Trigger.ON_DAMAGE_TAKEN,
            source=source,
            target=investigator,
            extra_sources=hand,
            payload=payload,
            amount=amount,
        )
        amount = max(0, int(payload.get("amount", amount)))
        if amount <= 0:
            self.state.log(f"{investigator.name} 抵消了这次伤害", kind="damage")
            return
        yield from self._assign(investigator, amount, "damage", source, reason)

    def assign_horror(self, investigator: CardInstance, amount: int, source: Any = None, reason: str = ""):
        payload = {"amount": amount}
        player = self.state.player_of(investigator)
        hand = [self.state.cards[cid] for cid in player.hand] if player is not None else []
        yield from self.emit(
            Trigger.ON_HORROR_TAKEN,
            source=source,
            target=investigator,
            extra_sources=hand,
            payload=payload,
            amount=amount,
        )
        amount = max(0, int(payload.get("amount", amount)))
        if amount <= 0:
            self.state.log(f"{investigator.name} 抵消了这次恐惧", kind="horror")
            return
        yield from self._assign(investigator, amount, "horror", source, reason)

    def heal(self, target: CardInstance, *, damage: int = 0, horror: int = 0) -> None:
        target.damage = max(0, target.damage - damage)
        target.horror = max(0, target.horror - horror)
        self.state.log(f"{target.name} 回复 {damage} 伤害 / {horror} 恐惧", kind="heal")

    def defeat_card(self, card: CardInstance, source: Any = None):
        if card.card_type is CardType.ENEMY:
            player = None
            self.state.log(f"{card.name} 被击败！", kind="defeat")
            card.engaged_with.clear()
            card.zone = Zone.ENCOUNTER_DISCARD
            if card.location_id:
                pass
            card.location_id = None
            if card.defn.victory:
                self.state.victory_display.append(card.id)
                self.state.log(f"{card.name} 进入胜利点弃牌堆（{card.defn.victory} 胜利点）", kind="victory")
            else:
                self.state.encounter_discard.append(card.id)
            yield from self.emit(Trigger.ON_ENEMY_DEFEATED, source=source, target=card)
            return
        if card.card_type is CardType.INVESTIGATOR:
            player = self.state.player_of(card)
            if player is None:
                return
            killed = (card.health_remaining() or 0) <= 0
            insane = (card.sanity_remaining() or 0) <= 0
            player.defeated = True
            player.killed = player.killed or killed
            player.insane = player.insane or insane
            cause = "被杀害" if killed else "陷入疯狂"
            self.state.log(f"{card.name} {cause}！", kind="defeat")
            yield from self.emit(Trigger.ON_DEFEATED, source=source, target=card)
            yield from self.check_all_defeated()
            return
        # assets and everything else go to their owner's discard pile
        owner = self.state.player_of(card)
        self.state.log(f"{card.name} 被弃置", kind="discard")
        yield from self.emit(Trigger.ON_ASSET_DEFEATED, source=source, target=card)
        if owner is not None:
            self.move_to_discard(owner, card.id)

    def check_all_defeated(self):
        if not self.state.players:
            return
        if all(not p.is_active for p in self.state.players):
            self.state.log("所有调查员都已放弃或被击败", kind="story")
            yield from self.end_scenario("defeated")

    def discover_clue(self, investigator: CardInstance, location: CardInstance | None = None, count: int = 1) -> int:
        if location is None:
            location = self.state.cards[investigator.meta.get("location_id")] if investigator.meta.get("location_id") else None
        if location is None:
            return 0
        taken = min(count, location.clues)
        location.clues -= taken
        investigator.clues += taken
        self.state.log(f"{investigator.name} 在{location.name}发现 {taken} 条线索", kind="clue")
        return taken

    def spend_clues(self, investigator: CardInstance, count: int) -> int:
        spent = min(count, investigator.clues)
        investigator.clues -= spent
        return spent

    def place_doom(self, card: CardInstance, count: int = 1):
        card.doom += count
        self.state.log(f"{card.name} 上放置 {count} 个毁灭标记（{card.doom}）", kind="doom")
        yield from self.emit(Trigger.ON_PLACE_DOOM, source=card, target=card, amount=count)
        yield from self.check_agenda_advance()

    def check_agenda_advance(self):
        # re-read the current agenda every pass: advance_agenda() moves
        # agenda_index forward and does not clear the old card's doom, so a
        # stale local would loop on the same card for ever
        # Rules Reference 1.3: compare the TOTAL doom in play (the agenda plus
        # every other card) with the agenda's doom threshold.
        while True:
            agenda = self.state.current_agenda()
            if agenda is None or agenda.defn.doom_threshold is None:
                return
            if self.state.total_doom() < agenda.defn.doom_threshold:
                return
            yield from self.advance_agenda()

    def advance_agenda(self):
        agenda = self.state.current_agenda()
        if agenda is None:
            return
        self.state.log(f"阴谋卡推进：{agenda.name}", kind="story")
        yield from self.emit(Trigger.ON_AGENDA_ADVANCE, source=agenda, target=agenda)
        # "When the agenda deck advances, remove all doom from play."
        for card in self.state.cards.values():
            if card.doom:
                card.doom = 0
        self.state.agenda_index += 1
        nxt = self.state.current_agenda()
        if nxt is not None:
            self.state.log(f"新阴谋卡：{nxt.name}", kind="story")
        elif not self.state.flags.get("suppress_agenda_exhausted"):
            # 第三章：最后一张阴谋卡背面会变成"既是幕卡也是阴谋卡"，此时不能结束剧本
            self.state.log("阴谋牌堆已空，阿卡姆陷入黑暗……", kind="story")
            yield from self.end_scenario("agenda_exhausted")

    def check_act_advance(self):
        act = self.state.current_act()
        if act is None:
            return
        required = act.defn.clues_required
        if act.defn.clues_per_investigator_required and required is not None:
            required = required * max(1, len([p for p in self.state.players if p.is_active]))
        if required is None:
            return
        total = sum(self.state.investigator_of(p).clues for p in self.state.players if p.is_active)
        if total >= required:
            yield from self.advance_act()

    def advance_act(self):
        act = self.state.current_act()
        if act is None:
            return
        act_def = act.defn
        rule = self.act_advance_rule(act)
        required = rule.get("clues", act_def.clues_required) or 0
        required = int(required)
        if rule.get("per_investigator") or act_def.clues_per_investigator_required:
            required *= max(1, len([p for p in self.state.players if p.is_active]))
        self.state.log(f"幕卡推进：{act.name}", kind="story")
        yield from self.emit(Trigger.ON_ACT_ADVANCE, source=act, target=act)
        self.state.act_index += 1
        nxt = self.state.current_act()
        if nxt is not None:
            self.state.log(f"新幕卡：{nxt.name}", kind="story")
        else:
            self.state.log("所有幕卡已完成", kind="story")

    def move_investigator(self, investigator: CardInstance, destination_id: str):
        player = self.state.player_of(investigator)
        origin_id = investigator.meta.get("location_id")
        origin = self.state.maybe_card(origin_id)
        dest = self.state.cards[destination_id]
        investigator.meta["location_id"] = destination_id
        if origin is not None:
            self.state.log(f"{investigator.name} 从{origin.name}移动到{dest.name}", kind="move")
            yield from self.emit(Trigger.ON_LEAVE_LOCATION, source=investigator, target=origin)
        else:
            self.state.log(f"{investigator.name} 进入{dest.name}", kind="move")
        yield from self.emit(Trigger.ON_MOVE, source=investigator, target=dest)
        if not dest.meta.get("revealed"):
            dest.meta["revealed"] = True
            self.state.log(f"{dest.name} 被揭示（遮蔽值 {dest.defn.shroud}）", kind="story")
            yield from self.emit(Trigger.ON_LOCATION_REVEAL, source=dest, target=dest)
        yield from self.emit(Trigger.ON_ENTER_LOCATION, source=investigator, target=dest)
        for enemy in list(self.state.enemies_at(destination_id)):
            if enemy.defn.spawn and enemy.defn.spawn not in ("", destination_id):
                continue
            if player is not None:
                yield from self.engage(enemy, player)

    def engage(self, enemy: CardInstance, player: Player):
        if player.id in enemy.engaged_with:
            return
        enemy.engaged_with.append(player.id)
        enemy.location_id = None
        investigator = self.state.investigator_of(player)
        self.state.log(f"{enemy.name} 与 {investigator.name} 交战", kind="engage")
        yield from self.emit(Trigger.ON_ENEMY_ENGAGED, source=enemy, target=investigator)

    def disengage(self, enemy: CardInstance, player: Player):
        if player.id in enemy.engaged_with:
            enemy.engaged_with.remove(player.id)
            investigator = self.state.investigator_of(player)
            enemy.location_id = investigator.meta.get("location_id")
            self.state.log(f"{enemy.name} 与 {investigator.name} 解除交战", kind="engage")

    def enemy_attack(self, enemy: CardInstance, player: Player):
        # On the Lam: non-Elite enemies cannot attack that investigator this round
        lam = self.state.flags.get("on_the_lam") or {}
        if lam.get("player") == player.id and lam.get("round") == self.state.round and not enemy.defn.elite:
            self.state.log(f"{enemy.name} 找不到 {self.state.investigator_of(player).name}", kind="attack")
            return
        investigator = self.state.investigator_of(player)
        enemy.exhausted = True
        damage = enemy.defn.enemy_damage
        horror = enemy.defn.enemy_horror
        self.state.log(f"{enemy.name} 攻击 {investigator.name}（{damage} 伤害 / {horror} 恐惧）", kind="attack")
        yield from self.emit(Trigger.ON_ENEMY_ATTACK, source=enemy, target=investigator, damage=damage, horror=horror)
        # Aquinnah: "deal that enemy's damage to another enemy at your location instead"
        redirect_id = enemy.meta.pop("redirect_damage_to", None)
        if redirect_id:
            other = self.state.maybe_card(redirect_id)
            if other is not None:
                yield from self.deal_damage(other, damage, source=enemy, reason="Aquinnah")
                damage = 0
        # abilities triggered by the attack may sharpen it (e.g. Yithian Observer)
        damage += int(enemy.meta.get("attack_damage_bonus", 0))
        horror += int(enemy.meta.get("attack_horror_bonus", 0))
        enemy.meta.pop("attack_damage_bonus", None)
        enemy.meta.pop("attack_horror_bonus", None)
        yield from self.deal_damage(investigator, damage, source=enemy, reason=f"{enemy.name} 的攻击")
        yield from self.deal_horror(investigator, horror, source=enemy, reason=f"{enemy.name} 的攻击")

    def hunter_move(self, enemy: CardInstance):
        target_player = self.preferred_target(enemy)
        if target_player is None:
            return
        investigator = self.state.investigator_of(target_player)
        current = enemy.location_id
        destination = investigator.meta.get("location_id")
        if current is None or destination is None or current == destination:
            return
        step = self.step_toward(current, destination)
        if step is None or step == current:
            return
        if not enemy.defn.elite:
            for card in self.attachments_of(self.state.cards[step]):
                if card.defn.meta.get("blocks_enemy_movement"):
                    self.state.log(f"{card.name} 挡住了 {enemy.name} 的去路", kind="move")
                    return
        enemy.location_id = step
        self.state.log(f"{enemy.name} 向 {self.state.cards[step].name} 移动（猎手）", kind="move")
        if step == destination:
            yield from self.engage(enemy, target_player)

    def preferred_target(self, enemy: CardInstance) -> Player | None:
        candidates = [p for p in self.state.players if p.is_active]
        if not candidates:
            return None
        prey = (enemy.defn.prey or "").lower()
        if not prey:
            return candidates[0]
        def key(player: Player) -> int:
            investigator = self.state.investigator_of(player)
            for skill in Skill:
                if skill.value in prey:
                    return -(int(investigator.defn.stat(skill) or 0))
            return 0
        return sorted(candidates, key=key)[0]

    def step_toward(self, start: str, goal: str) -> str | None:
        """Breadth first search over the location graph, returning the next hop."""
        if start == goal:
            return start
        seen = {start}
        queue: list[tuple[str, str]] = [(start, start)]
        while queue:
            node, first_step = queue.pop(0)
            for nxt in self.state.connections_of(node):
                if nxt in seen:
                    continue
                if nxt == goal:
                    return first_step if node != start else nxt
                seen.add(nxt)
                queue.append((nxt, first_step if node != start else nxt))
        return None

    def draw_encounter(self, player: Player) -> CardInstance | None:
        if not self.state.encounter_deck:
            return None
        card_id = self.state.encounter_deck.pop(0)
        card = self.state.cards[card_id]
        card.zone = Zone.LIMBO
        investigator = self.state.investigator_of(player)
        self.state.log(f"{investigator.name} 抽取遭遇卡：{card.name}", kind="encounter")
        return card

    def resolve_encounter(self, player: Player, card: CardInstance):
        investigator = self.state.investigator_of(player)
        yield from self.emit(Trigger.ON_ENCOUNTER_DRAW, source=card, target=investigator)
        if card.card_type is CardType.ENEMY:
            yield from self.spawn_enemy(card, player)
        else:
            yield from self.emit(Trigger.ON_TREACHERY_REVEALED, source=card, target=investigator)
            effect = card.defn.meta.get("resolve")
            if effect is not None:
                ctx = EffectContext(game=self, source=card, controller=player, payload={"investigator": investigator})
                yield from self.run_effect(effect, ctx)
            else:
                self.state.log(f"{card.name} 没有实现的效果", kind="encounter")
            yield from self.emit(Trigger.ON_ENCOUNTER_RESOLVE, source=card, target=investigator)
            if card.zone is Zone.LIMBO:
                self.to_encounter_discard(card)

    def to_encounter_discard(self, card: CardInstance) -> None:
        if card.defn.victory:
            self.state.victory_display.append(card.id)
            card.zone = Zone.REMOVED
        else:
            card.zone = Zone.ENCOUNTER_DISCARD
            self.state.encounter_discard.append(card.id)

    def spawn_enemy(self, enemy: CardInstance, player: Player | None = None, location_id: str | None = None):
        """Spawn an enemy.

        Without an explicit location the enemy spawns at the location of the
        investigator who drew it and engages that investigator.  A printed spawn
        instruction sends it elsewhere; it then engages whoever is there.
        """
        investigator = self.state.investigator_of(player) if player is not None else None
        if location_id is None and investigator is not None:
            location_id = investigator.meta.get("location_id")
        # "Forced - When the Ghoul Priest spawns: Spawn it here instead" (Your House)
        for loc in self.state.locations():
            if loc.defn.meta.get("attracts_code") == enemy.code:
                location_id = loc.id
                break
        spawn = (enemy.defn.spawn or "").strip()
        if "empty" in spawn.lower():
            # "Spawn - Any empty location": a location with no investigators and no enemies
            occupied = {e.location_id for e in self.state.enemies()}
            for other in self.state.players:
                if other.is_active:
                    occupied.add(self.state.investigator_of(other).meta.get("location_id"))
            for loc in self.state.locations():
                if loc.id not in occupied:
                    location_id = loc.id
                    break
            enemy.defn.meta["unengaged_spawn"] = True
        elif spawn and spawn.lower() not in ("", "any"):
            for loc in self.state.locations():
                if spawn.lower() in loc.name.lower():
                    location_id = loc.id
                    break
        enemy.zone = Zone.PLAY
        enemy.location_id = location_id
        enemy.exhausted = False
        place = self.state.cards[location_id].name if location_id and location_id in self.state.cards else "?"
        self.state.log(f"{enemy.name} 现身于{place}", kind="spawn")
        yield from self.emit(Trigger.ON_ENEMY_SPAWN, source=enemy, target=enemy)
        if location_id is None:
            return
        if investigator is not None and investigator.meta.get("location_id") == location_id:
            yield from self.engage(enemy, player)
            return
        if enemy.defn.meta.get("unengaged_spawn"):
            return
        for other in self.state.players:
            if not other.is_active:
                continue
            if self.state.investigator_of(other).meta.get("location_id") == location_id:
                yield from self.engage(enemy, other)
                break

    def shroud_of(self, location: CardInstance) -> int:
        """Shroud value including cards attached to the location."""
        value = int(location.defn.shroud or 0)
        for card in self.state.cards.values():
            if card.attached_to == location.id:
                value += int(card.defn.meta.get("shroud_bonus", 0))
        return value

    def attachments_of(self, card: CardInstance) -> list[CardInstance]:
        return [c for c in self.state.cards.values() if c.attached_to == card.id]

    def move_to_threat_area(self, player: Player, card: CardInstance) -> None:
        self.remove_from_zones(player, card.id)
        card.zone = Zone.THREAT_AREA
        card.controller_id = player.id
        player.threat_area.append(card.id)
        self.state.log(f"{card.name} 进入 {self.state.investigator_of(player).name} 的威胁区", kind="encounter")

    def discard_from_play(self, card: CardInstance) -> None:
        card.zone = Zone.ENCOUNTER_DISCARD
        card.attached_to = None
        self.state.encounter_discard.append(card.id)

    def attach_to_location(self, card: CardInstance, location: CardInstance) -> None:
        card.zone = Zone.PLAY
        card.attached_to = location.id
        card.location_id = location.id
        self.state.log(f"{card.name} 附着于{location.name}", kind="encounter")

    def is_blanked(self, investigator: CardInstance) -> bool:
        """True while an enemy with a blanking ability sits at the investigator's location."""
        location_id = investigator.meta.get("location_id")
        if not location_id:
            return False
        for enemy in self.state.enemies():
            if enemy.location_id != location_id or enemy.meta.get("blank"):
                continue
            if enemy.defn.meta.get("blanks_investigator"):
                return True
        return False

    def tomes_blanked(self, asset: CardInstance) -> bool:
        """True while the asset's controller has a blanking card (The Necronomicon) in their threat area."""
        player = self.state.player_of(asset)
        if player is None:
            return False
        for card_id in player.threat_area:
            holder = self.state.cards.get(card_id)
            if holder is not None and holder.defn.meta.get("blanks_tomes"):
                return True
        return False

    def enemy_fight(self, enemy: CardInstance) -> int:
        """Enemy fight value: printed + scenario modifier (agenda 01144) + per-card bonus."""
        bonus = int((self.state.flags.get("enemy_stat_bonus") or {}).get("fight", 0))
        return int(enemy.defn.fight or 0) + bonus + int(enemy.meta.get("fight_bonus", 0))

    def enemy_evade(self, enemy: CardInstance) -> int:
        bonus = int((self.state.flags.get("enemy_stat_bonus") or {}).get("evade", 0))
        return int(enemy.defn.evade or 0) + bonus + int(enemy.meta.get("evade_bonus", 0))

    def location_action_uses(self, location: CardInstance, action_id: str) -> dict:
        return dict(self.state.counters.get(f"locact:{location.id}:{action_id}") or {})

    def note_location_action(self, location: CardInstance, action_id: str) -> None:
        key = f"locact:{location.id}:{action_id}"
        used = dict(self.state.counters.get(key) or {})
        used["count"] = int(used.get("count", 0)) + 1
        used["round"] = self.state.round
        self.state.counters[key] = used

    def ghouls_at(self, location_id: str | None) -> list[CardInstance]:
        if location_id is None:
            return []
        return [
            e
            for e in self.state.enemies()
            if e.location_id == location_id and "ghoul" in e.defn.traits
        ]

    def attacks_of_opportunity(self, player: Player, verb: str):
        """Each ready enemy engaged with the player attacks (rule: attack of opportunity)."""
        if verb in ("fight", "evade", "parley", "resign", "activate", "advance_act", "pass"):
            return
        investigator = self.state.investigator_of(player)
        for enemy in list(self.state.engaged_enemies(player.id)):
            if enemy.exhausted:
                continue
            self.state.log(f"{enemy.name} 发动借机攻击（{investigator.name} 进行了其他行动）", kind="attack")
            yield from self.enemy_attack(enemy, player)

    def extra_action_cost(self, player: Player, verb: str) -> int:
        """Additional action cost imposed by cards in the player's threat area."""
        extra = 0
        for card in self.state.threat_area_of(player.id):
            verbs = card.defn.meta.get("extra_action_verbs") or ()
            if verb in verbs and card.meta.get("charged_round") != self.state.round:
                card.meta["charged_round"] = self.state.round
                extra += int(card.defn.meta.get("extra_action_amount", 1))
        return extra

    def act_advance_rule(self, act: CardInstance | None = None) -> dict:
        """Scenario supplied advance rule for an act (kept in game state, not on the shared CardDef)."""
        if act is None:
            act = self.state.current_act()
        if act is None:
            return {}
        return dict((self.state.flags.get("act_advance") or {}).get(act.code) or {})

    def can_advance_act(self, player: Player) -> bool:
        """Whether this player may spend clues to advance the current act."""
        act = self.state.current_act()
        if act is None:
            return False
        rule = self.act_advance_rule(act)
        if not rule or rule.get("objective"):
            # objective driven acts advance through their own trigger, not by spending clues
            return False
        required = rule.get("clues")
        if required is None:
            required = act.defn.clues_required
        if required is None:
            return False
        required = int(required)
        if rule.get("per_investigator"):
            required *= max(1, len([p for p in self.state.players if p.is_active]))
        investigator = self.state.investigator_of(player)
        if rule.get("location") and investigator.meta.get("location_id") != rule["location"]:
            return False
        group = sum(self.state.investigator_of(p).clues for p in self.state.players if p.is_active)
        return group >= required

    def end_scenario(self, resolution: str):
        if self.state.finished:
            return
        self.state.resolution = resolution
        self.state.finished = True
        self.state.log(f"=== 场景结束：{resolution} ===", kind="story")
        yield
