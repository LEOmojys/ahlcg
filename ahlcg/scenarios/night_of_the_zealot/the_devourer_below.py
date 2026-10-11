"""第三章：深渊吞噬者 (The Devourer Below).

Setup, the escaped-cultist legacy and the resolutions follow the official Chinese
campaign guide; the chaos token effects are the scenario reference card 01142.
"""

from __future__ import annotations

from ...core.cards import Ability, CardInstance
from ...core.enums import AbilityKind, CardType, Skill, TokenType, Trigger, Zone
from ...engine.chaos import ELDER_THING
from ..base import Scenario


class TheDevourerBelow(Scenario):
    code = "tentacles"
    name = "第三章：深渊吞噬者（The Devourer Below）"
    campaign = "night_of_the_zealot"

    BASE_SETS = ("tentacles", "ancient_evils", "striking_fear", "ghouls", "pentagram")
    AGENT_SETS = ("agents_of_yog", "agents_of_cthulhu", "agents_of_shub", "agents_of_hastur")
    WOODS = ("01150", "01151", "01152", "01153", "01154", "01155")
    MAIN_PATH = "01149"
    RITUAL_SITE = "01156"
    UMORDHOTH = "01157"
    GHOUL_PRIEST = "01116"
    LITA = "01117"
    ACT_TRAIL = "01146"
    ACT_DARKNESS = "01147"
    ACT_DISRUPT = "01148"
    AGENDA_WOODS = "01143"
    AGENDA_RITUAL = "01144"
    AGENDA_VENGEANCE = "01145"

    # ------------------------------------------------------------------
    # setup
    # ------------------------------------------------------------------
    def setup(self, game):
        state = game.state
        rng = state.rng

        main = self.add_location(game, self.MAIN_PATH, revealed=True)
        woods = list(self.WOODS)
        rng.shuffle(woods)
        chosen, removed = woods[:4], woods[4:]
        ids = {self.MAIN_PATH: main.id}
        for code in chosen:
            ids[code] = self.add_location(game, code, revealed=True).id
        for code in removed:
            card = self.set_aside(game, code)
            card.zone = Zone.REMOVED
        for code in chosen:
            self.connect(game, main.id, ids[code])

        for code in (self.ACT_TRAIL, self.ACT_DARKNESS, self.ACT_DISRUPT):
            self.add_act(game, code)
        for code in (self.AGENDA_WOODS, self.AGENDA_RITUAL, self.AGENDA_VENGEANCE):
            self.add_agenda(game, code)
        self.set_aside(game, self.RITUAL_SITE)
        self.set_aside(game, self.UMORDHOTH)

        agent_set = rng.choice(list(self.AGENT_SETS))
        state.flags["devourer_agent_set"] = agent_set
        self.build_encounter_deck(game, (*self.BASE_SETS, agent_set), exclude=(self.UMORDHOTH,))

        if state.flags.get("ghoul_priest_alive"):
            state.encounter_deck.append(state.add_card(self.pool.get(self.GHOUL_PRIEST), zone=Zone.ENCOUNTER_DECK).id)
            state.rng.shuffle(state.encounter_deck)
            state.log("食尸鬼祭司依然存活：它被洗进了遭遇牌堆", kind="story")

        escaped = list(state.flags.get("cultists_escaped") or [])
        doom = 0 if not escaped else 1 if len(escaped) <= 2 else 2 if len(escaped) <= 4 else 3
        agenda = state.current_agenda()
        if doom and agenda is not None:
            agenda.doom = doom
            state.log(f"逃跑的邪教徒有 {len(escaped)} 名：阴谋卡上已有 {doom} 个毁灭标记", kind="story")

        state.chaos_bag.add(ELDER_THING)
        state.log("混沌袋中加入了 1 个远古之物指示物", kind="story")

        for player in state.players:
            state.investigator_of(player).meta["location_id"] = main.id

        if state.flags.get("midnight_passed"):
            for player in state.players:
                for _ in range(2):
                    if not player.hand:
                        break
                    card_id = state.rng.choice(list(player.hand))
                    state.log(f"{state.investigator_of(player).name} 随机弃掉 {state.cards[card_id].name}", kind="discard")
                    game.move_to_discard(player, card_id)

        state.flags["act_advance"] = {
            self.ACT_TRAIL: {"clues": 3, "per_investigator": True, "label": "在树林中花 3 条线索/人"},
            self.ACT_DARKNESS: {"objective": "ritual_site"},
            self.ACT_DISRUPT: {"objective": "clues_on_act", "per_investigator": 2},
        }
        state.flags["resign_allowed"] = True
        state.flags["suppress_agenda_exhausted"] = True

        self.install_reference(game)
        self.install_abilities(game, self.abilities(game))
        state.log("设置：阿卡姆树林深处，仪式即将完成", kind="story")

    def loc(self, game, code: str) -> CardInstance | None:
        for card in game.state.locations():
            if card.code == code:
                return card
        return None

    # ------------------------------------------------------------------
    # scenario reference 01142
    # ------------------------------------------------------------------
    def install_reference(self, game):
        state = game.state
        hard = state.difficulty in ("hard", "expert")

        def monsters():
            return [e for e in state.enemies() if "monster" in e.defn.traits]

        def modifier(token, ctx):
            if token.type is TokenType.SKULL:
                return -3 if hard else -len(monsters())
            if token.type is TokenType.CULTIST:
                return -4 if hard else -2
            if token.type is TokenType.TABLET:
                return -5 if hard else -3
            if token.type is TokenType.ELDER_THING:
                return -7 if hard else -5
            return 0

        state.chaos_bag.modifiers.append(modifier)

    def abilities(self, game):
        return [
            Ability(kind=AbilityKind.FORCED, trigger=Trigger.ON_TEST_RESULT, effect=self._token_riders, label="混沌标记效果"),
            Ability(kind=AbilityKind.FORCED, trigger=Trigger.ON_ENTER_LOCATION, effect=self._entered_location, label="地点进入"),
            Ability(kind=AbilityKind.FORCED, trigger=Trigger.ON_ACT_ADVANCE, effect=self._act_advanced, label="幕卡推进"),
            Ability(kind=AbilityKind.FORCED, trigger=Trigger.ON_AGENDA_ADVANCE, effect=self._agenda_advanced, label="阴谋推进"),
            Ability(kind=AbilityKind.FORCED, trigger=Trigger.ON_TURN_END, effect=self._turn_end, label="仪式清点"),
            Ability(kind=AbilityKind.FORCED, trigger=Trigger.ON_ENEMY_DEFEATED, effect=self._enemy_defeated, label="阿布霍斯被击败"),
        ]

    def _nearest_enemy(self, ctx, investigator):
        state = ctx.state
        here = investigator.meta.get("location_id")
        best, best_dist = None, 999
        for enemy in state.enemies():
            where = enemy.location_id
            if where is None and enemy.engaged_with:
                for player in state.players:
                    if player.id in enemy.engaged_with:
                        where = state.investigator_of(player).meta.get("location_id")
            if where is None:
                continue
            dist = 0 if where == here else 999
            if dist:
                seen = {here}
                frontier = [(here, 0)]
                while frontier:
                    node, d = frontier.pop(0)
                    for nxt in state.connections_of(node):
                        if nxt in seen:
                            continue
                        if nxt == where:
                            dist = d + 1
                            frontier = []
                            break
                        seen.add(nxt)
                        frontier.append((nxt, d + 1))
            if dist < best_dist:
                best, best_dist = enemy, dist
        return best

    def _token_riders(self, ctx):
        result = ctx.event.get("result")
        test = ctx.event.get("test")
        if result is None or test is None:
            return
        state = ctx.state
        hard = state.difficulty in ("hard", "expert")
        investigator = state.maybe_card(getattr(test, "investigator_id", None))
        if investigator is None:
            return
        token = result.token
        monsters_here = [
            e for e in state.enemies()
            if "monster" in e.defn.traits and e.location_id == investigator.meta.get("location_id")
        ]
        if token.type is TokenType.CULTIST:
            amount = 2 if hard else 1
            target = self._nearest_enemy(ctx, investigator)
            if target is not None:
                yield from ctx.game.place_doom(target, amount)
        elif token.type is TokenType.TABLET and monsters_here:
            yield from ctx.game.deal_damage(investigator, 1, reason="石板标记")
            if hard:
                yield from ctx.game.deal_horror(investigator, 1, reason="石板标记")
        elif token.type is TokenType.SKULL and hard and not result.success:
            state.log("困难难度：需要从遭遇牌堆中找出一名怪物", kind="encounter")

    # ------------------------------------------------------------------
    # acts
    # ------------------------------------------------------------------
    def _entered_location(self, ctx):
        target = ctx.event.target
        ritual = self.loc(ctx.game, self.RITUAL_SITE)
        if target is None or ritual is None or target.id != ritual.id:
            return
        act = ctx.state.current_act()
        if act is not None and act.code == self.ACT_DARKNESS:
            yield from ctx.game.advance_act()

    def _act_advanced(self, ctx):
        act = ctx.event.source
        if act is None:
            return
        if act.code == self.ACT_TRAIL:
            yield from self._trail_advanced(ctx)
        elif act.code == self.ACT_DARKNESS:
            yield from self._darkness_advanced(ctx)
        elif act.code == self.ACT_DISRUPT:
            yield from ctx.game.end_scenario("R1")

    def _bring_ritual_site(self, game) -> CardInstance | None:
        """Put the set-aside Ritual Site into play as a real location (connected to the Main Path)."""
        ritual = self.loc(game, self.RITUAL_SITE)
        if ritual is not None:
            return ritual
        state = game.state
        card = self.find_card(game, self.RITUAL_SITE)
        if card is None:
            card = self.set_aside(game, self.RITUAL_SITE)
        card.zone = Zone.PLAY
        card.meta["revealed"] = True
        card.clues = self.clues_for(card.defn, len(state.players))
        if card.id not in state.location_ids:
            state.location_ids.append(card.id)
        main = self.loc(game, self.MAIN_PATH)
        if main is not None:
            self.connect(game, main.id, card.id)
        state.log(f"{card.name} 出现在树林深处", kind="story")
        return card

    def _trail_advanced(self, ctx):
        """Act 01146 back: reveal the Ritual Site and drag the escaped cultists back in."""
        game, state = ctx.game, ctx.state
        ritual = self._bring_ritual_site(game)
        main = self.loc(game, self.MAIN_PATH)
        for name in state.flags.get("cultists_escaped") or []:
            defn = None
            for card in self.pool.all():
                if card.name == name:
                    defn = card
                    break
            if defn is None or defn.card_type is not CardType.ENEMY:
                continue
            enemy = state.add_card(defn, zone=Zone.SET_ASIDE)
            state.log(f"逃跑的邪教徒 {enemy.name} 回到了主干道", kind="story")
            yield from game.spawn_enemy(enemy, location_id=main.id if main else None)

    def _darkness_advanced(self, ctx):
        """Act 01147 back: shuffle the discard pile back in and spawn enemies at the Ritual Site."""
        game, state = ctx.game, ctx.state
        state.encounter_deck.extend(state.encounter_discard)
        state.encounter_discard.clear()
        state.rng.shuffle(state.encounter_deck)
        ritual = self._bring_ritual_site(game)
        wanted = 2 if len([p for p in state.players if p.is_active]) >= 3 else 1
        found = 0
        while state.encounter_deck and found < wanted:
            card_id = state.encounter_deck.pop(0)
            card = state.cards[card_id]
            if card.card_type is not CardType.ENEMY:
                card.zone = Zone.ENCOUNTER_DISCARD
                state.encounter_discard.append(card_id)
                continue
            found += 1
            state.log(f"{card.name} 被仪式吸引而来", kind="encounter")
            yield from game.spawn_enemy(card, location_id=ritual.id if ritual else None)

    def _turn_end(self, ctx):
        """Act 01148 objective: 2 clues per investigator on the act."""
        state = ctx.state
        act = state.current_act()
        if act is None or act.code != self.ACT_DISRUPT:
            return
        needed = 2 * max(1, len([p for p in state.players if p.is_active]))
        if state.act_progress >= needed:
            yield from ctx.game.advance_act()

    # ------------------------------------------------------------------
    # agendas
    # ------------------------------------------------------------------
    def _agenda_advanced(self, ctx):
        agenda = ctx.event.source
        if agenda is None:
            return
        if agenda.code == self.AGENDA_WOODS:
            yield from self._woods_advanced(ctx)
            ctx.state.flags["enemy_stat_bonus"] = {"fight": 1, "evade": 1}
        elif agenda.code == self.AGENDA_RITUAL:
            ctx.state.flags["enemy_stat_bonus"] = {}
            yield from self._ritual_advanced(ctx)
        elif agenda.code == self.AGENDA_VENGEANCE:
            yield from self._vengeance_advanced(ctx)

    def _woods_advanced(self, ctx):
        """Agenda 01143 back: dig for a Monster and spawn it (with 1 doom) in the Main Path."""
        game, state = ctx.game, ctx.state
        state.encounter_deck.extend(state.encounter_discard)
        state.encounter_discard.clear()
        state.rng.shuffle(state.encounter_deck)
        while state.encounter_deck:
            card_id = state.encounter_deck.pop(0)
            card = state.cards[card_id]
            if card.card_type is CardType.ENEMY and "monster" in card.defn.traits:
                main = self.loc(game, self.MAIN_PATH)
                yield from game.spawn_enemy(card, location_id=main.id if main else None)
                yield from game.place_doom(card, 1)
                return
            card.zone = Zone.ENCOUNTER_DISCARD
            state.encounter_discard.append(card_id)

    def _ritual_advanced(self, ctx):
        """Agenda 01144 back: every investigator tests willpower (6) or takes a Madness weakness."""
        for player in list(ctx.state.players):
            if not player.is_active:
                continue
            investigator = ctx.state.investigator_of(player)
            result = yield from ctx.game.skill_test(
                investigator=investigator, skill=Skill.WILLPOWER, difficulty=6, source=ctx.event.source, kind="revelation"
            )
            if result.success:
                continue
            for card_id, card in list(ctx.state.cards.items()):
                if card.defn.basic_weakness and "madness" in card.defn.traits and card.zone is not Zone.HAND:
                    ctx.game.remove_from_zones(player, card.id)
                    card.zone = Zone.HAND
                    player.hand.append(card.id)
                    ctx.state.log(f"{investigator.name} 的理智出现裂痕：获得 {card.name}", kind="story")
                    break

    def _vengeance_advanced(self, ctx):
        """Agenda 01145: the final card becomes both act and agenda - Umördhoth arrives."""
        game, state = ctx.game, ctx.state
        act = state.current_act()
        ritual = self._bring_ritual_site(game)
        if act is not None and act.code == self.ACT_TRAIL:
            state.log("复仇降临：阿布霍斯在仪式所现身", kind="story")
        else:
            for enemy in list(state.enemies()):
                if ritual is not None and enemy.location_id == ritual.id:
                    game.discard_from_play(enemy)
            state.log("复仇降临：仪式所上的敌人被献祭，阿布霍斯现身", kind="story")
        card = self.find_card(game, self.UMORDHOTH)
        if card is None:
            card = self.set_aside(game, self.UMORDHOTH)
        card.meta["health_bonus"] = 4 * max(1, len([p for p in state.players if p.is_active]))
        yield from game.spawn_enemy(card, location_id=ritual.id if ritual else None)

    def _enemy_defeated(self, ctx):
        target = ctx.event.target
        if target is not None and target.code == self.UMORDHOTH:
            yield from ctx.game.end_scenario("R2")
