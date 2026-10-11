"""第一章：集结 (The Gathering).

Card texts and setup come from the official campaign guide
(reference/pdf/night_of_the_zealot_campaign_guide.txt) and the scenario reference
card 01104 for the chaos token effects.
"""

from __future__ import annotations

from ...core.cards import Ability, CardInstance
from ...core.choices import ChoiceOption, PendingChoice
from ...core.enums import AbilityKind, CardType, ChoiceKind, Phase, TokenType, Trigger, Zone
from ..base import Scenario


class TheGathering(Scenario):
    code = "torch"
    name = "第一章：集结（The Gathering）"
    campaign = "night_of_the_zealot"

    ENCOUNTER_SETS = ("torch", "rats", "ghouls", "striking_fear", "ancient_evils", "chilling_cold")
    SET_ASIDE = ("01116", "01117")  # Ghoul Priest, Lita Chantler
    STUDY = "01111"
    HALLWAY = "01112"
    ATTIC = "01113"
    CELLAR = "01114"
    PARLOR = "01115"
    ACT_TRAPPED = "01108"
    ACT_BARRIER = "01109"
    ACT_WHAT_HAVE_YOU_DONE = "01110"
    AGENDA_WHATS_GOING_ON = "01105"
    AGENDA_RISE = "01106"
    AGENDA_GETTING_OUT = "01107"
    GHOUL_PRIEST = "01116"
    LITA = "01117"

    # ------------------------------------------------------------------
    # setup
    # ------------------------------------------------------------------
    def setup(self, game):
        state = game.state
        state.log("设置：书房、遭遇牌组、幕卡与阴谋卡", kind="story")

        study = self.add_location(game, self.STUDY, revealed=True)
        for code in (self.HALLWAY, self.ATTIC, self.CELLAR, self.PARLOR):
            self.set_aside(game, code)
        for code in (self.ACT_TRAPPED, self.ACT_BARRIER, self.ACT_WHAT_HAVE_YOU_DONE):
            self.add_act(game, code)
        for code in (self.AGENDA_WHATS_GOING_ON, self.AGENDA_RISE, self.AGENDA_GETTING_OUT):
            self.add_agenda(game, code)
        for code in self.SET_ASIDE:
            self.set_aside(game, code)

        self.build_encounter_deck(game, self.ENCOUNTER_SETS, exclude=self.SET_ASIDE)

        for player in state.players:
            investigator = state.investigator_of(player)
            investigator.meta["location_id"] = study.id

        # The Study only connects to the Hallway, which is not in play yet.
        self.connect(game, study.id, self._pending(self.HALLWAY))

        state.flags["act_advance"] = {
            self.ACT_TRAPPED: {"clues": 2, "location": study.id, "label": "在书房花费 2 条线索"},
            self.ACT_BARRIER: {"clues": 3, "label": "在门厅花费 3 条线索"},
            self.ACT_WHAT_HAVE_YOU_DONE: {"objective": "enemy_defeated"},
        }
        state.flags["move_locked_at"] = study.id

        self.install_reference(game)
        self.install_abilities(game, self.abilities(game))

    def _pending(self, code: str) -> str:
        """Placeholder id for a location that is not in play yet (never matched)."""
        return f"pending:{code}"

    def loc(self, game, code: str) -> CardInstance | None:
        for card in game.state.locations():
            if card.code == code:
                return card
        return None

    def bring_location(self, game, code: str, *, revealed: bool = True, blocked: bool = False) -> CardInstance:
        state = game.state
        card = self.find_card(game, code)
        if card is None:
            return self.add_location(game, code, revealed=revealed, blocked=blocked)
        card.zone = Zone.PLAY
        card.meta["revealed"] = revealed
        card.meta["blocked"] = blocked
        card.clues = self.clues_for(card.defn, len(state.players))
        if card.id not in state.location_ids:
            state.location_ids.append(card.id)
        return card

    # ------------------------------------------------------------------
    # scenario reference 01104: chaos token effects
    # ------------------------------------------------------------------
    def install_reference(self, game):
        state = game.state
        hard = state.difficulty in ("hard", "expert")

        def modifier(token, ctx):
            if token.type is TokenType.SKULL:
                if hard:
                    return -2
                investigator = state.maybe_card(getattr(ctx, "investigator_id", None))
                location_id = investigator.meta.get("location_id") if investigator is not None else None
                return -len(game.ghouls_at(location_id))
            if token.type is TokenType.CULTIST:
                return -1
            if token.type is TokenType.TABLET:
                return -4 if hard else -2
            return 0

        state.chaos_bag.modifiers.append(modifier)

    def abilities(self, game):
        return [
            Ability(kind=AbilityKind.FORCED, trigger=Trigger.ON_ACT_ADVANCE, effect=self._act_advanced, label="幕卡推进"),
            Ability(kind=AbilityKind.FORCED, trigger=Trigger.ON_AGENDA_ADVANCE, effect=self._agenda_advanced, label="阴谋推进"),
            Ability(kind=AbilityKind.FORCED, trigger=Trigger.ON_ENEMY_DEFEATED, effect=self._enemy_defeated, label="敌人被击败"),
            Ability(kind=AbilityKind.FORCED, trigger=Trigger.ON_TEST_RESULT, effect=self._token_riders, label="混沌标记效果"),
            Ability(kind=AbilityKind.FORCED, trigger=Trigger.ON_PHASE_END, effect=self._phase_end, label="它们要出来了！"),
            Ability(kind=AbilityKind.FORCED, trigger=Trigger.ON_ROUND_END, effect=self._round_end, label="它们要出来了！"),
        ]

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
        if token.type is TokenType.CULTIST and not result.success:
            yield from ctx.game.deal_horror(investigator, 2 if hard else 1, reason="邪教徒标记")
        elif token.type is TokenType.TABLET:
            location_id = investigator.meta.get("location_id")
            if ctx.game.ghouls_at(location_id):
                yield from ctx.game.deal_damage(investigator, 1, reason="石板标记")
                if hard:
                    yield from ctx.game.deal_horror(investigator, 1, reason="石板标记")

    # ------------------------------------------------------------------
    # acts
    # ------------------------------------------------------------------
    def _act_advanced(self, ctx):
        act = ctx.event.source
        if act is None:
            return
        handlers = {
            self.ACT_TRAPPED: self._advance_trapped,
            self.ACT_BARRIER: self._advance_barrier,
            self.ACT_WHAT_HAVE_YOU_DONE: self._advance_what_have_you_done,
        }
        handler = handlers.get(act.code)
        if handler is not None:
            # run_effect accepts both plain functions and generators
            yield from ctx.game.run_effect(handler, ctx)

    def _advance_trapped(self, ctx):
        """Act 1 back: bring the house into play, discard ghouls in the Study, move everyone to the Hallway."""
        game, state = ctx.game, ctx.state
        study = self.loc(game, self.STUDY)
        hallway = self.bring_location(game, self.HALLWAY, revealed=True)
        attic = self.bring_location(game, self.ATTIC, revealed=False)
        cellar = self.bring_location(game, self.CELLAR, revealed=False)
        parlor = self.bring_location(game, self.PARLOR, revealed=False, blocked=True)
        for other in (attic, cellar, parlor):
            self.connect(game, hallway.id, other.id)
        if study is not None:
            self.connect(game, study.id, hallway.id)
            state.connections[study.id] = [hallway.id]
            for enemy in list(state.enemies_at(study.id)):
                state.log(f"{enemy.name} 被弃置（书房）", kind="discard")
                game.discard_from_play(enemy)
            for player in state.players:
                state.investigator_of(player).meta["location_id"] = hallway.id
            state.location_ids.remove(study.id)
            study.zone = Zone.REMOVED
            state.connections.pop(study.id, None)
            state.flags["move_locked_at"] = None
        state.log("幕卡推进：书房的门被打开了，调查员冲进门厅", kind="story")

    def _advance_barrier(self, ctx):
        """Act 2 back: reveal the Parlor, put Lita there, and spawn the Ghoul Priest in the Hallway."""
        game, state = ctx.game, ctx.state
        parlor = self.loc(game, self.PARLOR)
        hallway = self.loc(game, self.HALLWAY)
        if parlor is not None:
            parlor.meta["blocked"] = False
            parlor.meta["revealed"] = True
        lita = self.bring_into_play(game, self.LITA, location_id=parlor.id if parlor else None)
        state.log(f"{lita.name} 出现在客厅", kind="story")
        priest = self.bring_into_play(game, self.GHOUL_PRIEST)
        if hallway is not None:
            yield from game.spawn_enemy(priest, location_id=hallway.id)

    def _advance_what_have_you_done(self, ctx):
        """Act 3 back: the lead investigator decides the fate of the house."""
        game, state = ctx.game, ctx.state
        lead = state.players[0]
        choice = PendingChoice(
            id=game.next_choice_id(),
            kind=ChoiceKind.OPTION,
            player_id=lead.id,
            prompt="食尸鬼祭司倒下了。要烧掉这栋房子吗？",
            options=[
                ChoiceOption("R1", "烧掉它！（结局 1）"),
                ChoiceOption("R2", "这是我的家，绝不烧！（结局 2）"),
            ],
        )
        picked = yield from game.ask(choice)
        yield from game.end_scenario(picked[0])

    def _enemy_defeated(self, ctx):
        target = ctx.event.target
        act = ctx.state.current_act()
        if target is not None and target.code == self.GHOUL_PRIEST and act is not None and act.code == self.ACT_WHAT_HAVE_YOU_DONE:
            yield from ctx.game.advance_act()

    # ------------------------------------------------------------------
    # agendas
    # ------------------------------------------------------------------
    def _agenda_advanced(self, ctx):
        agenda = ctx.event.source
        if agenda is None:
            return
        handlers = {
            self.AGENDA_WHATS_GOING_ON: self._agenda_whats_going_on,
            self.AGENDA_RISE: self._agenda_rise,
            self.AGENDA_GETTING_OUT: self._agenda_getting_out,
        }
        handler = handlers.get(agenda.code)
        if handler is not None:
            yield from ctx.game.run_effect(handler, ctx)

    def _agenda_whats_going_on(self, ctx):
        game, state = ctx.game, ctx.state
        lead = state.players[0]
        choice = PendingChoice(
            id=game.next_choice_id(),
            kind=ChoiceKind.OPTION,
            player_id=lead.id,
            prompt="发生什么事了？！：领袖调查员必须选择",
            options=[
                ChoiceOption("discard", "每名调查员随机弃掉 1 张手牌"),
                ChoiceOption("horror", "领袖调查员承受 2 点恐惧"),
            ],
        )
        picked = yield from game.ask(choice)
        if picked[0] == "discard":
            for player in state.players:
                if not player.hand:
                    continue
                card_id = state.rng.choice(list(player.hand))
                state.log(f"{state.investigator_of(player).name} 随机弃掉 {state.cards[card_id].name}", kind="discard")
                game.move_to_discard(player, card_id)
        else:
            investigator = state.investigator_of(lead)
            yield from game.deal_horror(investigator, 2, reason="发生什么事了？！")

    def _agenda_rise(self, ctx):
        """Agenda 2 back: reshuffle, dig for a Ghoul, and the lead investigator draws it."""
        game, state = ctx.game, ctx.state
        state.encounter_deck.extend(state.encounter_discard)
        state.encounter_discard.clear()
        state.rng.shuffle(state.encounter_deck)
        lead = state.players[0]
        found = None
        while state.encounter_deck:
            card_id = state.encounter_deck.pop(0)
            card = state.cards[card_id]
            if card.card_type is CardType.ENEMY and "ghoul" in card.defn.traits:
                found = card
                break
            card.zone = Zone.ENCOUNTER_DISCARD
            state.encounter_discard.append(card_id)
        if found is not None:
            state.log(f"食尸鬼崛起：领袖调查员抽到了 {found.name}", kind="encounter")
            yield from game.spawn_enemy(found, lead)

    def _agenda_getting_out(self, ctx):
        game, state = ctx.game, ctx.state
        if state.act_index <= 1:
            state.log("食尸鬼撕开了墙壁，调查员被困在屋里……", kind="story")
            yield from game.end_scenario("R3")
            return
        for player in state.players:
            if not player.is_active:
                continue
            investigator = state.investigator_of(player)
            investigator.damage = investigator.defn.health or 0
            yield from game.defeat_card(investigator, source=ctx.event.source)
        yield from game.end_scenario("defeated")

    # ------------------------------------------------------------------
    # agenda 3 forced effects
    # ------------------------------------------------------------------
    def _agenda_is_getting_out(self, ctx) -> bool:
        agenda = ctx.state.current_agenda()
        return agenda is not None and agenda.code == self.AGENDA_GETTING_OUT

    def _ghoul_there(self, ctx, enemy) -> bool:
        hallway = self.loc(ctx.game, self.HALLWAY)
        parlor = self.loc(ctx.game, self.PARLOR)
        watch = {c.id for c in (hallway, parlor) if c is not None}
        if enemy.location_id in watch:
            return True
        for player in ctx.state.players:
            if player.id in enemy.engaged_with:
                return ctx.state.investigator_of(player).meta.get("location_id") in watch
        return False

    def _phase_end(self, ctx):
        if not self._agenda_is_getting_out(ctx):
            return
        if ctx.event.get("phase") is not Phase.ENEMY:
            return
        parlor = self.loc(ctx.game, self.PARLOR)
        if parlor is None:
            return
        for enemy in list(ctx.state.enemies()):
            if enemy.engaged_with or "ghoul" not in enemy.defn.traits or enemy.location_id is None:
                continue
            step = ctx.game.step_toward(enemy.location_id, parlor.id)
            if step and step != enemy.location_id:
                enemy.location_id = step
                ctx.state.log(f"{enemy.name} 向{ctx.state.cards[step].name}移动", kind="move")

    def _round_end(self, ctx):
        if not self._agenda_is_getting_out(ctx):
            return
        count = sum(1 for enemy in ctx.state.enemies() if "ghoul" in enemy.defn.traits and self._ghoul_there(ctx, enemy))
        if count:
            agenda = ctx.state.current_agenda()
            yield from ctx.game.place_doom(agenda, count)
