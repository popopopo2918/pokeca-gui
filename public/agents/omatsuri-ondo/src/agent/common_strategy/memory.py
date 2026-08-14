from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass, field

from .proposals import PendingIntent


@dataclass
class AgentMemory:
    pending_intent: PendingIntent | None = None
    known_deck_counts: Counter[int] | None = None
    known_prize_counts: Counter[int] = field(default_factory=Counter)
    known_absent_deck_ids: set[int] = field(default_factory=set)
    known_snapshot_deck_count: int | None = None
    known_snapshot_prize_count: int | None = None
    known_snapshot_generation: tuple[object, ...] | None = None
    opponent_public_card_ids: set[int] = field(default_factory=set)
    trace: list[dict[str, object]] = field(default_factory=list)
    strategy_state: object | None = None

    def clone_for_rule(self) -> "AgentMemory":
        return deepcopy(self)
