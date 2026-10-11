"""The chaos bag.

The bag is a multiset of tokens.  Symbol tokens (skull, cultist, tablet, elder
thing) have no printed value: their value comes from scenario specific
modifiers, which scenarios register as callables on the bag.  Keeping that as a
hook means one bag implementation covers every campaign.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence

from ..core.enums import SYMBOL_TOKEN_TYPES, TokenType
from ..core.errors import RuleError
from ..core.rng import Rng

#: Printed base values for the special tokens that always modify by a fixed amount.
FIXED_TOKEN_VALUES: dict[TokenType, int] = {
    TokenType.BLESS: 2,
    TokenType.CURSE: -2,
    TokenType.FROST: -1,
}

#: A scenario hook adjusting a revealed token.  Receives the token and the
#: skill test context (or None) and returns the additional modifier.
ChaosModifier = Callable[[Any, Any], int]


@dataclass(frozen=True, slots=True)
class ChaosToken:
    type: TokenType
    value: int = 0

    @property
    def is_autofail(self) -> bool:
        return self.type is TokenType.AUTOFAIL

    @property
    def is_symbol(self) -> bool:
        return self.type in SYMBOL_TOKEN_TYPES

    @property
    def is_elder_sign(self) -> bool:
        return self.type is TokenType.ELDER_SIGN

    @property
    def base_value(self) -> int:
        if self.type is TokenType.NUMERIC:
            return self.value
        if self.type in FIXED_TOKEN_VALUES:
            return FIXED_TOKEN_VALUES[self.type]
        # skull / cultist / tablet / elder thing / elder sign / autofail
        return 0

    @property
    def label(self) -> str:
        from ..core.enums import TOKEN_ZH

        if self.type is TokenType.NUMERIC:
            return f"{self.value:+d}"
        return TOKEN_ZH[self.type]


def numeric(value: int) -> ChaosToken:
    return ChaosToken(TokenType.NUMERIC, value)


SKULL = ChaosToken(TokenType.SKULL)
CULTIST = ChaosToken(TokenType.CULTIST)
TABLET = ChaosToken(TokenType.TABLET)
ELDER_THING = ChaosToken(TokenType.ELDER_THING)
AUTOFAIL = ChaosToken(TokenType.AUTOFAIL)
ELDER_SIGN = ChaosToken(TokenType.ELDER_SIGN)
BLESS = ChaosToken(TokenType.BLESS)
CURSE = ChaosToken(TokenType.CURSE)


#: The 16 token bag shipped with the core set (Night of the Zealot).
CORE_SET_BAG: tuple[ChaosToken, ...] = (
    numeric(1),
    numeric(0),
    numeric(0),
    numeric(-1),
    numeric(-1),
    numeric(-1),
    numeric(-2),
    numeric(-2),
    numeric(-3),
    numeric(-4),
    SKULL,
    SKULL,
    CULTIST,
    TABLET,
    AUTOFAIL,
    ELDER_SIGN,
)


@dataclass
class ChaosBag:
    tokens: list[ChaosToken] = field(default_factory=list)
    sealed: list[ChaosToken] = field(default_factory=list)
    modifiers: list[ChaosModifier] = field(default_factory=list)
    #: flat bonus applied to every revealed token (some scenarios do this)
    global_modifier: int = 0

    # -- construction ---------------------------------------------------
    @classmethod
    def core_set(cls) -> "ChaosBag":
        return cls(tokens=list(CORE_SET_BAG))

    @classmethod
    def from_tokens(cls, tokens: Iterable[ChaosToken]) -> "ChaosBag":
        return cls(tokens=list(tokens))

    @classmethod
    def from_counts(cls, counts: dict[ChaosToken, int]) -> "ChaosBag":
        tokens: list[ChaosToken] = []
        for token, count in counts.items():
            tokens.extend([token] * count)
        return cls(tokens=tokens)

    # -- mutation -------------------------------------------------------
    def add(self, token: ChaosToken, count: int = 1) -> None:
        self.tokens.extend([token] * count)

    def remove(self, token: ChaosToken, count: int = 1) -> None:
        for _ in range(count):
            try:
                self.tokens.remove(token)
            except ValueError:
                raise RuleError(f"chaos bag has no {token.label} token to remove") from None

    def remove_all_of_type(self, token_type: TokenType) -> int:
        before = len(self.tokens)
        self.tokens = [t for t in self.tokens if t.type is not token_type]
        return before - len(self.tokens)

    def clear(self) -> None:
        self.tokens.clear()

    def seal(self, token: ChaosToken) -> None:
        """Seal a token: it leaves the bag until unsealed."""
        self.remove(token)
        self.sealed.append(token)

    def unseal(self, token: ChaosToken) -> None:
        self.sealed.remove(token)
        self.tokens.append(token)

    def unseal_all(self) -> None:
        self.tokens.extend(self.sealed)
        self.sealed.clear()

    # -- queries --------------------------------------------------------
    @property
    def size(self) -> int:
        return len(self.tokens)

    def count(self, token: ChaosToken) -> int:
        return self.tokens.count(token)

    def count_type(self, token_type: TokenType) -> int:
        return sum(1 for t in self.tokens if t.type is token_type)

    def composition(self) -> Counter[ChaosToken]:
        return Counter(self.tokens)

    # -- drawing --------------------------------------------------------
    def draw(self, rng: Rng) -> ChaosToken:
        if not self.tokens:
            raise RuleError("cannot draw from an empty chaos bag")
        return rng.choice(self.tokens)

    # -- value resolution ----------------------------------------------
    def modifier_for(self, token: ChaosToken, context: Any = None) -> int:
        total = self.global_modifier
        for hook in self.modifiers:
            total += int(hook(token, context))
        return total

    def value_of(self, token: ChaosToken, context: Any = None) -> int:
        if token.is_autofail:
            return 0
        return token.base_value + self.modifier_for(token, context)

    def distribution(self, skill_value: int, context: Any = None) -> dict[int, float]:
        """Probability of each final total, for a given skill value."""
        from collections import defaultdict

        out: dict[int, float] = defaultdict(float)
        n = len(self.tokens)
        if n == 0:
            return {}
        for token in self.tokens:
            out[skill_value + self.value_of(token, context)] += 1.0 / n
        return dict(out)

    def success_probability(self, skill_value: int, difficulty: int, context: Any = None) -> float:
        """Chance that a skill test succeeds.  The auto-fail token never does."""
        n = len(self.tokens)
        if n == 0:
            return 0.0
        hits = 0
        for token in self.tokens:
            if token.is_autofail:
                continue
            if skill_value + self.value_of(token, context) >= difficulty:
                hits += 1
        return hits / n

    def chance_at_least(self, skill_value: int, difficulty: int, token_type: TokenType, context: Any = None) -> float:
        """Chance of drawing a given token type (used by scenario design and AI)."""
        n = len(self.tokens)
        if n == 0:
            return 0.0
        return sum(1 for t in self.tokens if t.type is token_type) / n
