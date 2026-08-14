from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .damage_pattern_table import DAMAGE_TABLE


class DamageSupport(str, Enum):
    NONE = "none"
    KIERAN = "kieran"
    BLACK_BELT = "black_belt"


@dataclass(frozen=True, order=True)
class DamagePatternKey:
    bench_count: int
    target_ex: bool
    grass_weakness: bool
    brave_bangle: bool
    support: DamageSupport
    hit_count: int

    def __post_init__(self) -> None:
        if type(self.bench_count) is not int or not 0 <= self.bench_count <= 5:
            raise ValueError("bench_count must be an integer from 0 through 5")
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
class DamagePattern:
    key: DamagePatternKey
    damage: int


def all_pattern_keys() -> tuple[DamagePatternKey, ...]:
    keys = (
        DamagePatternKey(
            bench_count=bench_count,
            target_ex=target_ex,
            grass_weakness=grass_weakness,
            brave_bangle=brave_bangle,
            support=support,
            hit_count=hit_count,
        )
        for bench_count in range(6)
        for target_ex in (False, True)
        for grass_weakness in (False, True)
        for brave_bangle in (False, True)
        for support in DamageSupport
        for hit_count in (1, 2)
    )
    return tuple(
        sorted(
            keys,
            key=lambda key: (
                key.bench_count,
                key.target_ex,
                key.grass_weakness,
                key.brave_bangle,
                key.support.value,
                key.hit_count,
            ),
        )
    )


def lookup_damage(key: DamagePatternKey) -> int:
    table_key = (
        key.bench_count,
        key.target_ex,
        key.grass_weakness,
        key.brave_bangle,
        key.support.value,
        key.hit_count,
    )
    return DAMAGE_TABLE[table_key]


def patterns_for_target(
    *,
    target_ex: bool,
    grass_weakness: bool,
    hit_count: int,
) -> tuple[DamagePattern, ...]:
    return tuple(
        DamagePattern(key=key, damage=lookup_damage(key))
        for key in all_pattern_keys()
        if key.target_ex is target_ex
        and key.grass_weakness is grass_weakness
        and key.hit_count == hit_count
    )
