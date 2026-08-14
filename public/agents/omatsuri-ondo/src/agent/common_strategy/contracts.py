from collections import Counter
from dataclasses import dataclass
from enum import IntEnum
import hashlib
from types import MappingProxyType
from typing import Mapping, Sequence


class DecisionTier(IntEnum):
    FALLBACK = 0
    BOARD = 100
    DISRUPTION = 200
    FOLLOW_UP = 300
    CURRENT_ATTACK = 400
    PRIMARY_EXTINCTION = 500
    FINAL_WIN = 600
    MANDATORY = 700


@dataclass(frozen=True)
class CapabilityVector:
    final_win: int = 0
    current_prizes: int = 0
    primary_lines_removed: int = 0
    current_attack_ready: int = 0
    next_attack_level: int = 0
    follow_up_lines: int = 0
    resource_margin: int = 0
    disruption_value: int = 0

    def rank_key(self) -> tuple[int, ...]:
        return (
            self.final_win,
            self.current_prizes,
            self.primary_lines_removed,
            self.current_attack_ready,
            self.next_attack_level,
            self.follow_up_lines,
            self.resource_margin,
            self.disruption_value,
        )


@dataclass(frozen=True)
class DeckContract:
    deck: tuple[int, ...]
    counts: Mapping[int, int]
    evolution_parent: Mapping[int, int]
    roles: Mapping[str, frozenset[int]]

    @property
    def signature(self) -> str:
        payload = ",".join(str(card_id) for card_id in sorted(self.deck))
        return hashlib.sha256(payload.encode("ascii")).hexdigest()

    @classmethod
    def from_deck(
        cls,
        deck: Sequence[int],
        *,
        evolution_parent: Mapping[int, int] | None = None,
        roles: Mapping[str, frozenset[int]] | None = None,
    ) -> "DeckContract":
        cards = tuple(int(card_id) for card_id in deck)
        if len(cards) != 60:
            raise ValueError("デッキは60枚必要です。")
        return cls(
            cards,
            MappingProxyType(dict(Counter(cards))),
            MappingProxyType(dict(evolution_parent or {})),
            MappingProxyType(dict(roles or {})),
        )

    @classmethod
    def for_test(cls, deck: Sequence[int]) -> "DeckContract":
        cards = tuple(int(card_id) for card_id in deck)
        return cls(
            cards,
            MappingProxyType(dict(Counter(cards))),
            MappingProxyType({}),
            MappingProxyType({}),
        )
