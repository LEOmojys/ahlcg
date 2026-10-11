"""Deckbuilding: starter decks, the 30-card rule, and validation."""

import pytest

from ahlcg.core.enums import CardType
from ahlcg.data.deck import (
    CORE_INVESTIGATORS,
    DeckList,
    build_starter_deck,
    is_investigator_specific,
    is_weakness,
    rules_for,
    standard_count,
    starter_decks,
    validate_deck,
)
from ahlcg.data.pool import CardPool


@pytest.fixture(scope="module")
def pool():
    return CardPool.load()


def test_deck_rules_come_from_the_card_data(pool):
    roland = pool.get("01001")
    rules = rules_for(roland)
    assert rules.size == 30
    assert set(rules.required_cards) == {"01006", "01007"}
    assert rules.random_basic_weakness == 1
    assert "guardian" in rules.primary_factions()
    assert rules.allows(pool.get("01020"))          # Machete, guardian level 0
    assert rules.allows(pool.get("01030"))          # Magnifying Glass, seeker splash level 0
    assert rules.allows(pool.get("01031"))          # Old Book of Lore, seeker splash level 0
    assert not rules.allows(pool.get("01043"))      # Cryptic Research, seeker level 4: not allowed
    assert not rules.allows(pool.get("01047"))      # .41 Derringer, rogue: not in Roland's options


def test_every_core_investigator_gets_a_legal_deck(pool):
    decks = starter_decks(pool)
    assert set(decks) == set(CORE_INVESTIGATORS)
    for code, deck in decks.items():
        problems = validate_deck(pool, deck)
        assert problems == [], (code, deck.name, problems)


def test_standard_cards_are_exactly_the_deck_size(pool):
    for code in CORE_INVESTIGATORS:
        deck = build_starter_deck(pool, code)
        assert standard_count(pool, deck) == 30, code
        # weaknesses and investigator-specific cards are carried in addition
        extra = [c for c in deck.cards if is_weakness(pool.get(c)) or is_investigator_specific(pool.get(c))]
        assert extra, code
        assert len(deck.cards) > 30


def test_deck_contains_required_cards_and_a_basic_weakness(pool):
    deck = build_starter_deck(pool, "01001")
    assert "01006" in deck.cards and "01007" in deck.cards
    assert sum(1 for c in deck.cards if pool.get(c).basic_weakness) == 1


def test_at_most_two_copies_by_title(pool):
    deck = build_starter_deck(pool, "01001")
    titles: dict[str, int] = {}
    for code in deck.cards:
        name = pool.get(code).name
        titles[name] = titles.get(name, 0) + 1
    assert max(titles.values()) <= 2


def test_validation_catches_violations(pool):
    legal = build_starter_deck(pool, "01001")

    too_many = DeckList(investigator="01001", cards=legal.cards + ("01020", "01020", "01020"))
    assert any("同名" in p for p in validate_deck(pool, too_many))

    wrong_size = DeckList(investigator="01001", cards=legal.cards[:-3])
    assert any("标准卡" in p for p in validate_deck(pool, wrong_size))

    illegal = DeckList(
        investigator="01001",
        cards=tuple(c for c in legal.cards if c != "01020") + ("01043",),  # level 4 seeker
    )
    problems = validate_deck(pool, illegal)
    assert any("Cryptic Research" in p for p in problems)

    missing_required = DeckList(investigator="01001", cards=tuple(c for c in legal.cards if c != "01007"))
    assert any("专属卡" in p for p in validate_deck(pool, missing_required))


def test_decks_only_contain_player_cards_and_weaknesses(pool):
    playable = (CardType.ASSET, CardType.EVENT, CardType.SKILL)
    for code in CORE_INVESTIGATORS:
        deck = build_starter_deck(pool, code)
        for card_code in deck.cards:
            defn = pool.get(card_code)
            assert defn.card_type in playable or is_weakness(defn), (code, card_code, defn.card_type)
