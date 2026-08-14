from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from common_strategy import EnergyType, GameView, PokemonRef

from ..cards import CardId
from ..damage_patterns import DamagePatternKey, DamageSupport, lookup_damage
from .boss_target_table import (
    BOSS_BENCH_SLOTS,
    BOSS_CLASS_COUNT,
    BOSS_TARGET_SLOT_TABLE,
)
from .opponent_attack_profiles import (
    OpponentAttackProfile,
    lookup_opponent_attack_profile,
    target_extinguishes_mainline,
)


FEZANDIPITI_EX_CARD_ID = 140


class BossDecisionClass(IntEnum):
    NONE = 0
    FINAL = 1
    MAINLINE_EXTINCTION = 2
    FEZANDIPITI_EX = 3
    MORE_PRIZES = 4
    # Legacy classes stay addressable for public compatibility, but the
    # compiled selector no longer emits them as standalone Boss purposes.
    TWO_HIT_BENCH = 5
    EVOLUTION_DENIAL = 6
    ATTACK_DENIAL = 7
    DOUBLE_KO = 8
    SUPPORT_FOLLOW_UP = 9


@dataclass(frozen=True)
class BossPattern:
    decision_class: BossDecisionClass
    target_serial: int
    target_prizes: int
    target_ko_now: bool


def lookup_boss_pattern(view: GameView) -> BossPattern | None:
    """Map five normalized Bench slots through the generated Boss lookup table."""

    active = view.own_active
    if active is None or active.id != int(CardId.DIPPLIN):
        return None
    bench = _normalized_bench(view)
    classes = _bench_class_vector(view, bench)
    table_key = sum(
        int(decision_class) * (BOSS_CLASS_COUNT ** slot)
        for slot, decision_class in enumerate(classes)
    )
    target_slot = int(BOSS_TARGET_SLOT_TABLE[table_key])
    if target_slot < 0 or target_slot >= len(bench):
        return None
    target = bench[target_slot]
    if target.serial is None:
        return None
    hit_count = (
        2
        if int(CardId.FESTIVAL_GROUNDS) in view.public_stadium_ids
        else 1
    )
    return BossPattern(
        decision_class=classes[target_slot],
        target_serial=int(target.serial),
        target_prizes=_prizes(view, target),
        target_ko_now=_damage_reaches_hp(
            _dipplin_damage(view, target, hit_count=hit_count),
            target.hp,
        ),
    )


def _damage_reaches_hp(damage: int, hp: int) -> bool:
    return int(damage) >= int(hp) and int(hp) >= 0


def _normalized_bench(view: GameView) -> tuple[PokemonRef, ...]:
    return tuple(sorted(
        view.opponent_bench[:BOSS_BENCH_SLOTS],
        key=lambda target: (
            -_prizes(view, target),
            target.serial is None,
            int(target.serial) if target.serial is not None else 0,
        ),
    ))


def _bench_class_vector(
    view: GameView,
    bench: tuple[PokemonRef, ...],
) -> tuple[BossDecisionClass, ...]:
    active_prizes = _prizes(view, view.opponent_active)
    remaining_prizes = max(0, int(view.own_prize_count))
    hit_count = (
        2
        if int(CardId.FESTIVAL_GROUNDS) in view.public_stadium_ids
        else 1
    )
    opponent_profile = lookup_opponent_attack_profile(view)
    classes = tuple(
        _target_class(
            view,
            target,
            active_prizes=active_prizes,
            remaining_prizes=remaining_prizes,
            hit_count=hit_count,
            opponent_profile=opponent_profile,
        )
        for target in bench
    )
    return (*classes, *((BossDecisionClass.NONE,) * (BOSS_BENCH_SLOTS - len(classes))))


def _target_class(
    view: GameView,
    target: PokemonRef,
    *,
    active_prizes: int,
    remaining_prizes: int,
    hit_count: int,
    opponent_profile: OpponentAttackProfile | None,
) -> BossDecisionClass:
    if target.serial is None:
        return BossDecisionClass.NONE
    target_ko_now = _damage_reaches_hp(
        _dipplin_damage(view, target, hit_count=hit_count),
        target.hp,
    )
    if not target_ko_now:
        return BossDecisionClass.NONE
    prizes = _prizes(view, target)
    if remaining_prizes > 0 and prizes >= remaining_prizes:
        return BossDecisionClass.FINAL
    if (
        opponent_profile is not None
        and target_extinguishes_mainline(
            view,
            opponent_profile,
            target_serial=int(target.serial),
        )
    ):
        return BossDecisionClass.MAINLINE_EXTINCTION
    if int(target.id) == FEZANDIPITI_EX_CARD_ID:
        return BossDecisionClass.FEZANDIPITI_EX
    if prizes > active_prizes:
        return BossDecisionClass.MORE_PRIZES
    return BossDecisionClass.NONE


def _dipplin_damage(
    view: GameView,
    target: PokemonRef,
    *,
    hit_count: int,
) -> int:
    target_meta = view.catalog.card(target.id)
    active = view.own_active
    return lookup_damage(DamagePatternKey(
        bench_count=min(5, len(view.own_bench)),
        target_ex=bool(
            target_meta is not None and (target_meta.ex or target_meta.mega_ex)
        ),
        grass_weakness=bool(
            target_meta is not None
            and target_meta.weakness == int(EnergyType.GRASS)
        ),
        brave_bangle=bool(
            active is not None and int(CardId.BRAVE_BANGLE) in active.tool_ids
        ),
        support=DamageSupport.NONE,
        hit_count=1 if int(hit_count) <= 1 else 2,
    ))


def _prizes(view: GameView, target: PokemonRef | None) -> int:
    if target is None:
        return 1
    meta = view.catalog.card(target.id)
    return 1 if meta is None else int(meta.prize_value)


def _denies_valuable_evolution(
    view: GameView,
    target: PokemonRef,
    *,
    one_hit_damage: int,
) -> bool:
    target_meta = view.catalog.card(target.id)
    if target_meta is None or not target_meta.is_basic_pokemon:
        return False
    return any(
        _evolves_from(meta.evolves_from, target.id)
        and int(meta.hp) > int(one_hit_damage)
        for meta in view.catalog.cards.values()
    )


def _evolves_from(value: int | str | None, card_id: int) -> bool:
    if value is None:
        return False
    try:
        return int(value) == int(card_id)
    except (TypeError, ValueError):
        return False


def _has_public_ready_attack(view: GameView, target: PokemonRef) -> bool:
    target_meta = view.catalog.card(target.id)
    return bool(
        target_meta is not None
        and any(
            view.public_attack_is_ready(target, attack_id)
            for attack_id in target_meta.attacks
        )
    )


__all__ = [
    "FEZANDIPITI_EX_CARD_ID",
    "BossDecisionClass",
    "BossPattern",
    "lookup_boss_pattern",
]
