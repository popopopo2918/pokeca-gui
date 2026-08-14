from __future__ import annotations

from dataclasses import dataclass

from .damage_patterns import DamageSupport
from .ko_route_pattern_table import KO_OUTCOME_TABLE


@dataclass(frozen=True, order=True)
class KoOutcomeKey:
    bench_count: int
    target_hp: int
    target_ex: bool
    grass_weakness: bool
    brave_bangle: bool
    support: DamageSupport
    hit_count: int

    def __post_init__(self) -> None:
        if type(self.bench_count) is not int or not 0 <= self.bench_count <= 5:
            raise ValueError("bench_count must be an integer from 0 through 5")
        if (
            type(self.target_hp) is not int
            or not 10 <= self.target_hp <= 400
            or self.target_hp % 10
        ):
            raise ValueError("target_hp must be a multiple of 10 from 10 through 400")
        if type(self.target_ex) is not bool:
            raise ValueError("target_ex must be a bool")
        if type(self.grass_weakness) is not bool:
            raise ValueError("grass_weakness must be a bool")
        if type(self.brave_bangle) is not bool:
            raise ValueError("brave_bangle must be a bool")
        if not isinstance(self.support, DamageSupport):
            raise ValueError("support must be a DamageSupport")
        if type(self.hit_count) is not int or self.hit_count not in (1, 2):
            raise ValueError("hit_count must be 1 or 2")


@dataclass(frozen=True)
class KoOutcome:
    per_hit_damage: int
    first_hit_ko: bool
    ko_with_available_hits: bool
    hits_spent_on_first: int
    hits_remaining: int
    remaining_hp: int

    def prizes_taken(self, target_prizes: int) -> int:
        if type(target_prizes) is not int or target_prizes not in (1, 2, 3):
            raise ValueError("target_prizes must be 1, 2, or 3")
        return target_prizes if self.ko_with_available_hits else 0


def lookup_ko_outcome(key: KoOutcomeKey) -> KoOutcome:
    row = KO_OUTCOME_TABLE[
        (
            key.bench_count,
            key.target_hp,
            key.target_ex,
            key.grass_weakness,
            key.brave_bangle,
            key.support.value,
            key.hit_count,
        )
    ]
    return KoOutcome(*row)
