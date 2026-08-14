from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from ..damage_patterns import DamageSupport
from ..ko_route_patterns import KoOutcomeKey, lookup_ko_outcome


class KoReachability(IntEnum):
    UNREACHABLE = 0
    PROBABILISTIC_KO = 1
    INSURED_KO_ATTEMPT = 2
    GUARANTEED_KO = 3


class KoRouteStep(IntEnum):
    NONE = 0
    ATTACK = 1
    PLAY_BASIC = 2
    PLAY_POFFIN = 3
    PLAY_BROCK_FOR_BASIC = 4
    USE_THWACKEY_FOR_POFFIN = 5
    PLAY_FESTIVAL = 6
    USE_THWACKEY_FOR_FESTIVAL = 7
    ATTACH_BANGLE = 8
    USE_THWACKEY_FOR_BANGLE = 9
    PLAY_KIERAN = 10
    USE_THWACKEY_FOR_KIERAN = 11
    PLAY_BLACK_BELT = 12
    USE_THWACKEY_FOR_BLACK_BELT = 13


@dataclass(frozen=True)
class KoRouteState:
    bench_count: int
    bench_free: int
    target_hp: int
    target_ex: bool
    grass_weakness: bool
    hit_count: int
    brave_bangle: bool
    support: DamageSupport
    supporter_available: bool = False
    direct_basic_count: int = 0
    poffin_in_hand: bool = False
    poffin_basic_count: int = 0
    brock_in_hand: bool = False
    brock_basic_count: int = 0
    can_use_thwackey: bool = False
    unused_thwackey: int = 0
    poffin_in_deck: bool = False
    festival_in_hand: bool = False
    festival_in_deck: bool = False
    bangle_in_hand: bool = False
    bangle_in_deck: bool = False
    kieran_in_hand: bool = False
    kieran_in_deck: bool = False
    black_belt_in_hand: bool = False
    black_belt_in_deck: bool = False
    black_belt_enabled: bool = False
    attacker_line_count: int = 3
    searcher_line_count: int = 2
    third_attacker_reachable: bool = False
    direct_attacker_count: int = 0
    direct_searcher_count: int = 0
    poffin_attacker_count: int = 0
    poffin_searcher_count: int = 0
    brock_attacker_count: int = 0
    brock_searcher_count: int = 0

    def __post_init__(self) -> None:
        if type(self.bench_count) is not int or not 0 <= self.bench_count <= 5:
            raise ValueError("bench_count must be from 0 through 5")
        if (
            type(self.bench_free) is not int
            or not 0 <= self.bench_free <= 5 - self.bench_count
        ):
            raise ValueError("bench_free is inconsistent with bench_count")
        if (
            type(self.target_hp) is not int
            or not 10 <= self.target_hp <= 400
            or self.target_hp % 10
        ):
            raise ValueError("target_hp must be a multiple of 10 from 10 through 400")
        if self.hit_count not in (1, 2):
            raise ValueError("hit_count must be 1 or 2")
        if not isinstance(self.support, DamageSupport):
            raise ValueError("support must be a DamageSupport")
        if min(
            self.direct_basic_count,
            self.poffin_basic_count,
            self.brock_basic_count,
            self.unused_thwackey,
            self.attacker_line_count,
            self.searcher_line_count,
            self.direct_attacker_count,
            self.direct_searcher_count,
            self.poffin_attacker_count,
            self.poffin_searcher_count,
            self.brock_attacker_count,
            self.brock_searcher_count,
        ) < 0:
            raise ValueError("Basic counts cannot be negative")
        if self.attacker_line_count + self.searcher_line_count > 6:
            raise ValueError("family line counts cannot exceed the field")


@dataclass(frozen=True)
class KoRoutePlan:
    reachability: KoReachability
    next_step: KoRouteStep
    goal_bench_count: int
    damage: int
    first_hit_ko: bool
    hits_remaining_after_ko: int
    goal_hit_count: int = 0
    goal_bangle: bool = False
    goal_support: DamageSupport = DamageSupport.NONE


_UNREACHABLE = KoRoutePlan(
    reachability=KoReachability.UNREACHABLE,
    next_step=KoRouteStep.NONE,
    goal_bench_count=0,
    damage=0,
    first_hit_ko=False,
    hits_remaining_after_ko=0,
)

_NEXT_STEP_PRIORITY = (
    KoRouteStep.PLAY_FESTIVAL,
    KoRouteStep.ATTACH_BANGLE,
    KoRouteStep.PLAY_BASIC,
    KoRouteStep.PLAY_POFFIN,
    KoRouteStep.PLAY_BROCK_FOR_BASIC,
    KoRouteStep.PLAY_BLACK_BELT,
    KoRouteStep.PLAY_KIERAN,
    KoRouteStep.USE_THWACKEY_FOR_BANGLE,
    KoRouteStep.USE_THWACKEY_FOR_FESTIVAL,
    KoRouteStep.USE_THWACKEY_FOR_POFFIN,
    KoRouteStep.USE_THWACKEY_FOR_BLACK_BELT,
    KoRouteStep.USE_THWACKEY_FOR_KIERAN,
)


def lookup_active_ko_route(state: KoRouteState) -> KoRoutePlan:
    """Traverse predeclared component rows; no game state is simulated."""

    maximum_bench = min(5, state.bench_count + state.bench_free)
    # A one-hit KO leaves the Festival Lead follow-up available.  Within the
    # same outcome class the larger fixed damage row is preferred so the
    # second hit makes the largest guaranteed progress after promotion.
    hit_goals = (2, 1) if state.hit_count == 1 else (2,)
    bangle_goals = (True,) if state.brave_bangle else (False, True)
    support_goals = (
        (state.support,)
        if state.support is not DamageSupport.NONE
        else (
            DamageSupport.NONE,
            DamageSupport.BLACK_BELT,
            DamageSupport.KIERAN,
        )
    )
    for require_first_hit_ko in (True, False):
        for goal_support in support_goals:
            for goal_bangle in bangle_goals:
                for goal_hit_count in hit_goals:
                    for goal_bench_count in range(
                        maximum_bench,
                        state.bench_count - 1,
                        -1,
                    ):
                        outcome = lookup_ko_outcome(KoOutcomeKey(
                            bench_count=goal_bench_count,
                            target_hp=state.target_hp,
                            target_ex=state.target_ex,
                            grass_weakness=state.grass_weakness,
                            brave_bangle=goal_bangle,
                            support=goal_support,
                            hit_count=goal_hit_count,
                        ))
                        if not outcome.ko_with_available_hits:
                            continue
                        if require_first_hit_ko != outcome.first_hit_ko:
                            continue
                        step = _next_step_for_goal(
                            state,
                            goal_bench_count=goal_bench_count,
                            goal_hit_count=goal_hit_count,
                            goal_bangle=goal_bangle,
                            goal_support=goal_support,
                        )
                        if step is KoRouteStep.NONE:
                            continue
                        return KoRoutePlan(
                            reachability=KoReachability.GUARANTEED_KO,
                            next_step=step,
                            goal_bench_count=goal_bench_count,
                            damage=outcome.per_hit_damage * goal_hit_count,
                            first_hit_ko=outcome.first_hit_ko,
                            hits_remaining_after_ko=outcome.hits_remaining,
                            goal_hit_count=goal_hit_count,
                            goal_bangle=goal_bangle,
                            goal_support=goal_support,
                        )
    return _UNREACHABLE


def _next_step_for_goal(
    state: KoRouteState,
    *,
    goal_bench_count: int,
    goal_hit_count: int,
    goal_bangle: bool,
    goal_support: DamageSupport,
) -> KoRouteStep:
    steps: set[KoRouteStep] = set()
    exact_searches = 0
    supporter_uses = 0

    if goal_hit_count > state.hit_count:
        if state.festival_in_hand:
            steps.add(KoRouteStep.PLAY_FESTIVAL)
        elif state.festival_in_deck:
            exact_searches += 1
            steps.add(KoRouteStep.USE_THWACKEY_FOR_FESTIVAL)
        else:
            return KoRouteStep.NONE

    if goal_bangle and not state.brave_bangle:
        if state.bangle_in_hand:
            steps.add(KoRouteStep.ATTACH_BANGLE)
        elif state.bangle_in_deck:
            exact_searches += 1
            steps.add(KoRouteStep.USE_THWACKEY_FOR_BANGLE)
        else:
            return KoRouteStep.NONE

    additions = goal_bench_count - state.bench_count
    bench_step = _bench_route_step(state, additions=additions)
    if bench_step is KoRouteStep.NONE:
        return KoRouteStep.NONE
    if bench_step is not KoRouteStep.ATTACK:
        steps.add(bench_step)
    if bench_step is KoRouteStep.PLAY_BROCK_FOR_BASIC:
        supporter_uses += 1
    elif bench_step is KoRouteStep.USE_THWACKEY_FOR_POFFIN:
        exact_searches += 1

    if goal_support is not state.support:
        if state.support is not DamageSupport.NONE or not state.supporter_available:
            return KoRouteStep.NONE
        supporter_uses += 1
        if goal_support is DamageSupport.KIERAN:
            if state.kieran_in_hand:
                steps.add(KoRouteStep.PLAY_KIERAN)
            elif state.kieran_in_deck:
                exact_searches += 1
                steps.add(KoRouteStep.USE_THWACKEY_FOR_KIERAN)
            else:
                return KoRouteStep.NONE
        elif goal_support is DamageSupport.BLACK_BELT:
            if not state.black_belt_enabled:
                return KoRouteStep.NONE
            if state.black_belt_in_hand:
                steps.add(KoRouteStep.PLAY_BLACK_BELT)
            elif state.black_belt_in_deck:
                exact_searches += 1
                steps.add(KoRouteStep.USE_THWACKEY_FOR_BLACK_BELT)
            else:
                return KoRouteStep.NONE

    available_searches = max(
        state.unused_thwackey,
        int(state.can_use_thwackey),
    )
    if supporter_uses > 1 or exact_searches > available_searches:
        return KoRouteStep.NONE
    if not steps:
        return KoRouteStep.ATTACK
    for step in _NEXT_STEP_PRIORITY:
        if step in steps:
            return step
    return KoRouteStep.NONE


def resolve_ko_route_step(
    state: KoRouteState,
    *,
    goal_bench_count: int,
    goal_hit_count: int,
    goal_bangle: bool,
    goal_support: DamageSupport,
) -> KoRouteStep:
    """Resolve one declared fixed-table goal without simulating game actions."""

    return _next_step_for_goal(
        state,
        goal_bench_count=goal_bench_count,
        goal_hit_count=goal_hit_count,
        goal_bangle=goal_bangle,
        goal_support=goal_support,
    )


def resolve_bench_route_step(
    state: KoRouteState,
    *,
    goal_bench_count: int,
) -> KoRouteStep:
    """Return the declared Basic-deployment component for one table row."""

    return _bench_route_step(
        state,
        additions=goal_bench_count - state.bench_count,
    )


def _bench_route_step(state: KoRouteState, *, additions: int) -> KoRouteStep:
    if additions == 0:
        return KoRouteStep.ATTACK
    if state.direct_basic_count >= additions:
        return KoRouteStep.PLAY_BASIC
    if state.poffin_in_hand and additions <= min(2, state.poffin_basic_count):
        return KoRouteStep.PLAY_POFFIN
    if (
        state.supporter_available
        and state.brock_in_hand
        and additions <= min(2, state.brock_basic_count)
    ):
        return KoRouteStep.PLAY_BROCK_FOR_BASIC
    if (
        state.can_use_thwackey
        and state.poffin_in_deck
        and additions <= min(2, state.poffin_basic_count)
    ):
        return KoRouteStep.USE_THWACKEY_FOR_POFFIN
    return KoRouteStep.NONE
