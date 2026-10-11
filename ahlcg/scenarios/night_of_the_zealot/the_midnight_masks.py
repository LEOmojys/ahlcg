"""第二章：午夜面具 (The Midnight Masks).

Setup, cultist deck and resolutions follow the official Chinese campaign guide
(reference/pdf/night_of_the_zealot_campaign_guide.txt).  The chaos token effects
are the scenario reference card 01120.

Two decks are in play here:
  * the encounter deck - 午夜的面具(arkham) + 阴冷 + 夜魔 + 黑暗信徒(pentagram) + 被锁住的门
  * the cultist deck   - the five named cultists, kept separate
"""

from __future__ import annotations

from ...core.cards import Ability, CardInstance
from ...core.enums import AbilityKind, CardType, Skill, TokenType, Trigger, Zone
from ..base import Scenario


class TheMidnightMasks(Scenario):
    code = "arkham"
    name = "第二章：午夜面具（The Midnight Masks）"
    campaign = "night_of_the_zealot"

    ENCOUNTER_SETS = ("arkham", "chilling_cold", "nightgaunts", "pentagram", "locked_doors")
    CULTISTS = ("01137", "01138", "01139", "01140", "01141")
    DOWNTOWN = ("01130", "01131")
    SOUTHSIDE = ("01126", "01127")
    FIXED = ("01134", "01132", "01125", "01128", "01133", "01129", "01124")
    ACT = "01123"
    AGENDA_FIRST = "01121a"
    AGENDA_LAST = "01122"
    YOUR_HOUSE = "01124"
    RIVERTOWN = "01125"

    # ------------------------------------------------------------------
    # setup
    # ------------------------------------------------------------------
    def setup(self, game):
        state = game.state
        rng = state.rng
        burned = bool(state.flags.get("house_burned"))

        codes = [rng.choice(list(self.DOWNTOWN)), rng.choice(list(self.SOUTHSIDE)), *self.FIXED]
        if burned and self.YOUR_HOUSE in codes:
            codes.remove(self.YOUR_HOUSE)
        start_code = self.RIVERTOWN if burned else self.YOUR_HOUSE

        ids: dict[str, str] = {}
        for code in codes:
            ids[code] = self.add_location(game, code, revealed=True).id
        self._connect(game, ids)

        self.add_act(game, self.ACT)
        self.add_agenda(game, self.AGENDA_FIRST)
        self.add_agenda(game, self.AGENDA_LAST)

        self.build_encounter_deck(game, self.ENCOUNTER_SETS)

        cultist_deck = [state.add_card(self.pool.get(code), zone=Zone.SET_ASIDE).id for code in self.CULTISTS]
        rng.shuffle(cultist_deck)
        state.flags["cultist_deck"] = cultist_deck
        state.flags["cultists_found"] = []
        state.flags["cultists_escaped"] = []
        state.flags.setdefault("midnight_passed", False)

        for player in state.players:
            investigator = state.investigator_of(player)
            investigator.meta["location_id"] = ids[start_code]

        state.flags["act_advance"] = {self.ACT: {"objective": "cultists"}}
        state.flags["resign_allowed"] = True

        self.install_reference(game)
        self.install_abilities(game, self.abilities(game))
        state.log("设置：阿卡姆的地图已经铺开，邪教徒藏在城里，午夜之前找到他们", kind="story")
        if burned:
            state.log("（你的屋子已被焚毁，调查员从河滨小镇出发）", kind="story")

    def _connect(self, game, ids: dict[str, str]) -> None:
        """The suggested Midnight Masks layout: a chain through Arkham."""
        south = ids.get("01126") or ids.get("01127")
        downtown = ids.get("01130") or ids.get("01131")
        chain = [
            (ids.get(self.YOUR_HOUSE), ids.get(self.RIVERTOWN)),
            (ids.get(self.RIVERTOWN), south),
            (ids.get(self.RIVERTOWN), ids.get("01129")),
            (south, downtown),
            (downtown, ids.get("01132")),
            (downtown, ids.get("01128")),
            (ids.get("01132"), ids.get("01134")),
            (ids.get("01134"), ids.get("01133")),
        ]
        for a, b in chain:
            if a and b:
                self.connect(game, a, b)

    # ------------------------------------------------------------------
    # scenario reference 01120
    # ------------------------------------------------------------------
    def install_reference(self, game):
        state = game.state
        hard = state.difficulty in ("hard", "expert")

        def modifier(token, ctx):
            if token.type is TokenType.SKULL:
                if hard:
                    return -state.total_doom()
                cultists = [e for e in state.enemies() if "cultist" in e.defn.traits]
                return -max([e.doom for e in cultists], default=0)
            if token.type is TokenType.CULTIST:
                return -2
            if token.type is TokenType.TABLET:
                return -4 if hard else -3
            return 0

        state.chaos_bag.modifiers.append(modifier)

    def abilities(self, game):
        return [
            Ability(kind=AbilityKind.FORCED, trigger=Trigger.ON_TEST_RESULT, effect=self._token_riders, label="混沌标记效果"),
            Ability(kind=AbilityKind.FORCED, trigger=Trigger.ON_ENEMY_DEFEATED, effect=self._enemy_defeated, label="邪教徒被击败"),
            Ability(kind=AbilityKind.FORCED, trigger=Trigger.ON_TURN_END, effect=self._check_cultists, label="邪教徒清点"),
            Ability(kind=AbilityKind.FORCED, trigger=Trigger.ON_ACT_ADVANCE, effect=self._act_advanced, label="幕卡推进"),
            Ability(kind=AbilityKind.FORCED, trigger=Trigger.ON_AGENDA_ADVANCE, effect=self._agenda_advanced, label="阴谋推进"),
            Ability(kind=AbilityKind.FORCED, trigger=Trigger.ON_SCENARIO_END, effect=self._scenario_end, label="记录邪教徒"),
        ]

    def _nearest_cultist(self, ctx, investigator: CardInstance) -> CardInstance | None:
        state = ctx.state
        location_id = investigator.meta.get("location_id")
        best = None
        best_dist = 999
        for enemy in state.enemies():
            if "cultist" not in enemy.defn.traits:
                continue
            where = enemy.location_id
            if where is None and enemy.engaged_with:
                for player in state.players:
                    if player.id in enemy.engaged_with:
                        where = state.investigator_of(player).meta.get("location_id")
            if where is None:
                continue
            dist = 0 if where == location_id else 999
            if where != location_id:
                seen = {location_id}
                frontier = [(location_id, 0)]
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
        if token.type is TokenType.CULTIST:
            cultists = [e for e in state.enemies() if "cultist" in e.defn.traits]
            if hard:
                for enemy in cultists:
                    yield from ctx.game.place_doom(enemy, 1)
            else:
                nearest = self._nearest_cultist(ctx, investigator)
                if nearest is not None:
                    yield from ctx.game.place_doom(nearest, 1)
        elif token.type is TokenType.TABLET and not result.success and investigator.clues > 0:
            location = state.maybe_card(investigator.meta.get("location_id"))
            if location is not None:
                moved = investigator.clues if hard else 1
                investigator.clues -= moved
                location.clues += moved
                state.log(f"{investigator.name} 把 {moved} 条线索掉在了{location.name}", kind="clue")

    # ------------------------------------------------------------------
    # finding the cultists
    # ------------------------------------------------------------------
    def _cultists_in_victory(self, state) -> list[CardInstance]:
        return [state.cards[cid] for cid in state.victory_display if state.cards[cid].code in self.CULTISTS]

    def _enemy_defeated(self, ctx):
        yield from self._check_cultists(ctx)

    def _check_cultists(self, ctx):
        state = ctx.state
        found = self._cultists_in_victory(state)
        if len(found) >= len(self.CULTISTS):
            state.log("六名邪教徒已全部被找出，线索拼凑完整", kind="story")
            yield from ctx.game.advance_act()

    # ------------------------------------------------------------------
    # resolutions
    # ------------------------------------------------------------------
    def _record_cultists(self, state) -> None:
        found = sorted({card.name for card in self._cultists_in_victory(state)})
        deck = state.flags.get("cultist_deck") or []
        escaped = {state.cards[cid].name for cid in deck}
        escaped |= {e.name for e in state.enemies() if e.code in self.CULTISTS}
        if state.act_index == 0:
            escaped.add("面具猎手")
        state.flags["cultists_found"] = found
        state.flags["cultists_escaped"] = sorted(escaped)
        state.log("我们发现的邪教徒：" + ("、".join(found) if found else "无"), kind="story")
        state.log("逃跑的邪教徒：" + ("、".join(sorted(escaped)) if escaped else "无"), kind="story")

    def _act_advanced(self, ctx):
        act = ctx.event.source
        if act is None or act.code != self.ACT:
            return
        self._record_cultists(ctx.state)
        yield from ctx.game.end_scenario("R1")

    def _agenda_advanced(self, ctx):
        agenda = ctx.event.source
        if agenda is None or agenda.code != self.AGENDA_LAST:
            return
        ctx.state.flags["midnight_passed"] = True
        ctx.state.log("十二点的钟声响起：午夜已过", kind="story")
        self._record_cultists(ctx.state)
        yield from ctx.game.end_scenario("R2")

    def _scenario_end(self, ctx):
        state = ctx.state
        if not state.flags.get("cultists_found") and not state.flags.get("cultists_escaped"):
            self._record_cultists(state)
