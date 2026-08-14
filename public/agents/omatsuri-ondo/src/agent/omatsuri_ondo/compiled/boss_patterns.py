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


class BossDecisionClass(IntEnum):
    NONE = 0
    FINAL = 1
    MORE_PRIZES = 2
    TWO_HIT_BENCH = 3
    EVOLUTION_DENIAL = 4
    ATTACK_DENIAL = 5
    DOUBLE_KO = 6
    SUPPORT_FOLLOW_UP = 7


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
    one_hit_flags = tuple(
        target.serial is not None
        and _dipplin_damage(view, target, hit_count=1) >= max(0, int(target.hp))
        for target in bench
    )
    one_hit_count = sum(one_hit_flags)
    active_one_hit = bool(
        view.opponent_active is not None
        and _dipplin_damage(view, view.opponent_active, hit_count=1)
        >= max(0, int(view.opponent_active.hp))
    )
    active_prizes = _prizes(view, view.opponent_active)
    remaining_prizes = max(0, int(view.own_prize_count))
    festival_active = int(CardId.FESTIVAL_GROUNDS) in view.public_stadium_ids
    classes = tuple(
        _target_class(
            view,
            target,
            one_hit=bool(one_hit_flags[slot]),
            one_hit_count=one_hit_count,
            active_one_hit=active_one_hit,
            active_prizes=active_prizes,
            remaining_prizes=remaining_prizes,
            festival_active=festival_active,
        )
        for slot, target in enumerate(bench)
    )
    return (*classes, *((BossDecisionClass.NONE,) * (BOSS_BENCH_SLOTS - len(classes))))


def _target_class(
    view: GameView,
    target: PokemonRef,
    *,
    one_hit: bool,
    one_hit_count: int,
    active_one_hit: bool,
    active_prizes: int,
    remaining_prizes: int,
    festival_active: bool,
) -> BossDecisionClass:
    if target.serial is None:
        return BossDecisionClass.NONE
    two_hit = (
        festival_active
        and _dipplin_damage(view, target, hit_count=2)
        >= max(0, int(target.hp))
    )
    attack_denial = _has_public_ready_attack(view, target)
    if not one_hit and not two_hit and not attack_denial:
        return BossDecisionClass.NONE
    prizes = _prizes(view, target)
    return _decision_class(
        final_win=(
            one_hit and remaining_prizes > 0 and prizes >= remaining_prizes
        ),
        prizes=prizes,
        active_prizes=active_prizes,
        one_hit=one_hit,
        two_hit=two_hit,
        evolution_denial=(
            one_hit
            and _denies_valuable_evolution(
                view,
                target,
                one_hit_damage=_dipplin_damage(view, target, hit_count=1),
            )
        ),
        attack_denial=attack_denial,
        double_knockout=(one_hit and one_hit_count >= 2),
        active_one_hit=active_one_hit,
        support_follow_up=(remaining_prizes >= 4 and one_hit and active_one_hit),
    )


def _decision_class(
    *,
    final_win: bool,
    prizes: int,
    active_prizes: int,
    one_hit: bool,
    two_hit: bool,
    evolution_denial: bool,
    attack_denial: bool,
    double_knockout: bool,
    active_one_hit: bool,
    support_follow_up: bool,
) -> BossDecisionClass:
    if final_win:
        return BossDecisionClass.FINAL
    if one_hit and prizes > active_prizes:
        return BossDecisionClass.MORE_PRIZES
    if not one_hit and two_hit:
        return BossDecisionClass.TWO_HIT_BENCH
    if evolution_denial:
        return BossDecisionClass.EVOLUTION_DENIAL
    if attack_denial:
        return BossDecisionClass.ATTACK_DENIAL
    if double_knockout or (one_hit and not active_one_hit):
        return BossDecisionClass.DOUBLE_KO
    if support_follow_up:
        return BossDecisionClass.SUPPORT_FOLLOW_UP
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


__all__ = ["BossDecisionClass", "BossPattern", "lookup_boss_pattern"]
