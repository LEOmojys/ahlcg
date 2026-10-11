"""Exception types raised by the engine."""

from __future__ import annotations


class AhlcgError(Exception):
    """Base class for every error raised by this project."""


class RuleError(AhlcgError):
    """The requested operation is legal Python but illegal Arkham."""


class IllegalActionError(RuleError):
    """The action is not available to this player right now."""


class ChoiceError(AhlcgError):
    """A submitted choice does not match what the engine is waiting for."""


class CardDataError(AhlcgError):
    """Malformed card definition or scenario data."""
