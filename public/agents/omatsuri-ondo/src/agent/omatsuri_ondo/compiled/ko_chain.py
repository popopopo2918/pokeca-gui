from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from ..damage_patterns import DamageSupport
from ..ko_route_patterns import KoOutcome, KoOutcomeKey, lookup_ko_outcome
from .ko_routes import (
    KoRouteState,
    KoRouteStep,
    resolve_bench_route_step,
    resolve_ko_route_step,
)

MAX_ATTACKER_GENERATIONS = 7


class KoChainClass(IntEnum):
    BROKEN = 0
    CURRENT_KO_ONLY = 1
    NEXT_KO_INSURED = 2
    GAME_END_GUARANTEED = 3
    GAME_WIN_THIS_TURN = 4


@dataclass(frozen=True)
class KoTarget:
    hp: int
    prizes: int
    target_ex: bool = False
    grass_weakness: bool = False

    def __post_init__(self) -> None:
        if type(self.hp) is not int or not 10 <= self.hp <= 400 or self.hp % 10:
            raise ValueError("hp must be a multiple of 10 from 10 through 400")
        if type(self.prizes) is not int or self.prizes not in (1, 2, 3):
            raise ValueError("prizes must be 1, 2, or 3")
        if type(self.target_ex) is not bool:
            raise ValueError("target_ex must be a bool")
        if type(self.grass_weakness) is not bool:
            raise ValueError("grass_weakness must be a bool")


@dataclass(frozen=True)
class KoChainState:
    route: KoRouteState
    active: KoTarget
    promotions: tuple[KoTarget, ...]
    next_attack_preparation_class: int
    own_prizes_remaining: int
    future_attacker_generations: int

    def __post_init__(self) -> None:
        if (
            self.active.hp != self.route.target_hp
            or self.active.target_ex is not self.route.target_ex
            or self.active.grass_weakness is not self.route.grass_weakness
        ):
            raise ValueError("active target and route target must match")
        if self.next_attack_preparation_class not in (0, 1, 2):
            raise ValueError("next_attack_preparation_class must be 0, 1, or 2")
        if not 0 <= self.own_prizes_remaining <= 6:
            raise ValueError("own_prizes_remaining must be from 0 through 6")
        if not 0 <= self.future_attacker_generations <= 7:
            raise ValueError("future_attacker_generations must be from 0 through 7")


@dataclass(frozen=True)
class KoChainPlan:
    chain_class: KoChainClass
    next_step: KoRouteStep
    goal_bench_count: int
    goal_bangle: bool
    goal_support: DamageSupport
    first_hit_ko: bool
    guaranteed_prizes_this_turn: int
    second_hit_damage: int
    worst_promotion_remaining_hp: int
    worst_promotion_index: int
    resources_cover_game: bool


@dataclass(frozen=True)
class _FixedChainRow:
    step: KoRouteStep
    goal_bench_count: int
    goal_bangle: bool
    goal_support: DamageSupport
    first_hit_ko: bool
    guaranteed_prizes: int
    second_hit_damage: int
    worst_remaining_hp: int
    worst_promotion_index: int
    has_second_hit: bool
    board_continuity_rank: int
    goal_hit_count: int

    @property
    def order(self) -> tuple[int, ...]:
        # Every field is a fixed outcome label.  This tuple compares table rows;
        # it is not a game-tree score and never predicts a random draw.
        return (
            self.guaranteed_prizes,
            self.goal_hit_count,
            self.board_continuity_rank,
            int(self.has_second_hit),
            -self.worst_remaining_hp if self.has_second_hit else -401,
            self.second_hit_damage,
            -_step_resource_cost(self.step),
            -int(self.goal_bangle),
            -_support_damage_order(self.goal_support),
            -self.goal_bench_count,
        )


_BROKEN = KoChainPlan(
    chain_class=KoChainClass.BROKEN,
    next_step=KoRouteStep.NONE,
    goal_bench_count=0,
    goal_bangle=False,
    goal_support=DamageSupport.NONE,
    first_hit_ko=False,
    guaranteed_prizes_this_turn=0,
    second_hit_damage=0,
    worst_promotion_remaining_hp=0,
    worst_promotion_index=-1,
    resources_cover_game=False,
)


def lookup_ko_chain(state: KoChainState) -> KoChainPlan:
    """Select the best declared split-hit row under adversarial promotion.

    The bounded loops only traverse the already-declared damage/component
    domains (six Bench sizes, two Tool states, three Support states).  No game
    position is copied, no action is applied, and no random outcome is scored.
    """

    best: _FixedChainRow | None = None
    route = state.route
    maximum_bench = min(5, route.bench_count + route.bench_free)
    hit_goals = (2, 1) if route.hit_count == 1 else (2,)
    bangle_goals = (True,) if route.brave_bangle else (False, True)
    support_goals = (
        (route.support,)
        if route.support is not DamageSupport.NONE
        else (
            DamageSupport.NONE,
            DamageSupport.KIERAN,
            DamageSupport.BLACK_BELT,
        )
    )
    for goal_support in support_goals:
        for goal_bangle in bangle_goals:
            for goal_hit_count in hit_goals:
                for goal_bench_count in range(
                    route.bench_count,
                    maximum_bench + 1,
                ):
                    step = resolve_ko_route_step(
                        route,
                        goal_bench_count=goal_bench_count,
                        goal_hit_count=goal_hit_count,
                        goal_bangle=goal_bangle,
                        goal_support=goal_support,
                    )
                    if step is KoRouteStep.NONE:
                        continue
                    active_outcome = _outcome(
                        state.active,
                        bench_count=goal_bench_count,
                        brave_bangle=goal_bangle,
                        support=goal_support,
                        hit_count=goal_hit_count,
                    )
                    if not active_outcome.ko_with_available_hits:
                        continue
                    row = _chain_row(
                        state,
                        step=step,
                        goal_bench_count=goal_bench_count,
                        goal_bangle=goal_bangle,
                        goal_support=goal_support,
                        goal_hit_count=goal_hit_count,
                        first_hit_ko=active_outcome.first_hit_ko,
                    )
                    if best is None or row.order > best.order:
                        best = row
    if best is None:
        return _BROKEN

    prizes_after_turn = max(
        0,
        state.own_prizes_remaining - best.guaranteed_prizes,
    )
    resources_cover_game = (
        state.future_attacker_generations >= prizes_after_turn
    )
    if prizes_after_turn == 0:
        chain_class = KoChainClass.GAME_WIN_THIS_TURN
    elif not resources_cover_game:
        chain_class = KoChainClass.CURRENT_KO_ONLY
    elif state.next_attack_preparation_class == 2:
        chain_class = KoChainClass.GAME_END_GUARANTEED
    elif state.next_attack_preparation_class == 1:
        chain_class = KoChainClass.NEXT_KO_INSURED
    else:
        chain_class = KoChainClass.CURRENT_KO_ONLY
    return KoChainPlan(
        chain_class=chain_class,
        next_step=best.step,
        goal_bench_count=best.goal_bench_count,
        goal_bangle=best.goal_bangle,
        goal_support=best.goal_support,
        first_hit_ko=best.first_hit_ko,
        guaranteed_prizes_this_turn=best.guaranteed_prizes,
        second_hit_damage=best.second_hit_damage,
        worst_promotion_remaining_hp=best.worst_remaining_hp,
        worst_promotion_index=best.worst_promotion_index,
        resources_cover_game=resources_cover_game,
    )


def _chain_row(
    state: KoChainState,
    *,
    step: KoRouteStep,
    goal_bench_count: int,
    goal_bangle: bool,
    goal_support: DamageSupport,
    goal_hit_count: int,
    first_hit_ko: bool,
) -> _FixedChainRow:
    guaranteed_prizes = state.active.prizes
    board_continuity_rank = _board_continuity_rank(
        state.route,
        goal_bench_count=goal_bench_count,
    )
    if not first_hit_ko or goal_hit_count < 2 or not state.promotions:
        return _FixedChainRow(
            step=step,
            goal_bench_count=goal_bench_count,
            goal_bangle=goal_bangle,
            goal_support=goal_support,
            first_hit_ko=first_hit_ko,
            guaranteed_prizes=guaranteed_prizes,
            second_hit_damage=0,
            worst_remaining_hp=0,
            worst_promotion_index=-1,
            has_second_hit=False,
            board_continuity_rank=board_continuity_rank,
            goal_hit_count=goal_hit_count,
        )

    promotion_rows = tuple(
        _outcome(
            target,
            bench_count=goal_bench_count,
            brave_bangle=goal_bangle,
            support=goal_support,
            hit_count=1,
        )
        for target in state.promotions
    )
    all_promotions_ko = all(row.first_hit_ko for row in promotion_rows)
    if all_promotions_ko:
        guaranteed_prizes += min(target.prizes for target in state.promotions)
    worst_index = max(
        range(len(state.promotions)),
        key=lambda index: (
            int(not promotion_rows[index].first_hit_ko),
            promotion_rows[index].remaining_hp,
            -state.promotions[index].prizes,
            index,
        ),
    )
    worst = promotion_rows[worst_index]
    return _FixedChainRow(
        step=step,
        goal_bench_count=goal_bench_count,
        goal_bangle=goal_bangle,
        goal_support=goal_support,
        first_hit_ko=True,
        guaranteed_prizes=guaranteed_prizes,
        second_hit_damage=worst.per_hit_damage,
        worst_remaining_hp=worst.remaining_hp,
        worst_promotion_index=worst_index,
        has_second_hit=True,
        board_continuity_rank=board_continuity_rank,
        goal_hit_count=goal_hit_count,
    )


def _board_continuity_rank(
    route: KoRouteState,
    *,
    goal_bench_count: int,
) -> int:
    """Classify the fixed 2+2 core and third-attacker Bench contract.

    Rows first materialize the minimum two attacker/two searcher layout.  Once
    that core exists, a reachable third attacker is either materialized or a
    physical Bench slot is kept for it.  The rank is an outcome label used by
    the finite table; no future draw or game state is explored here.
    """

    additions = max(0, goal_bench_count - route.bench_count)
    bench_step = resolve_bench_route_step(
        route,
        goal_bench_count=goal_bench_count,
    )
    attacker_available, searcher_available = _basic_family_supply(
        route,
        bench_step,
    )
    attackers, searchers = _allocate_family_lines(
        attacker_lines=route.attacker_line_count,
        searcher_lines=route.searcher_line_count,
        attacker_available=attacker_available,
        searcher_available=searcher_available,
        additions=additions,
    )
    free_after_goal = max(0, 5 - goal_bench_count)
    missing_core = max(0, 2 - attackers) + max(0, 2 - searchers)
    if missing_core > free_after_goal:
        return 0
    if attackers < 2 or searchers < 2:
        return 1
    if attackers >= 3:
        return 4
    if not route.third_attacker_reachable:
        return 3
    if free_after_goal >= 3 - attackers:
        return 3
    return 2


def _basic_family_supply(
    route: KoRouteState,
    step: KoRouteStep,
) -> tuple[int, int]:
    if step is KoRouteStep.PLAY_BASIC:
        return route.direct_attacker_count, route.direct_searcher_count
    if step in (
        KoRouteStep.PLAY_POFFIN,
        KoRouteStep.USE_THWACKEY_FOR_POFFIN,
    ):
        return route.poffin_attacker_count, route.poffin_searcher_count
    if step is KoRouteStep.PLAY_BROCK_FOR_BASIC:
        return route.brock_attacker_count, route.brock_searcher_count
    return 0, 0


def _allocate_family_lines(
    *,
    attacker_lines: int,
    searcher_lines: int,
    attacker_available: int,
    searcher_available: int,
    additions: int,
) -> tuple[int, int]:
    attackers = int(attacker_lines)
    searchers = int(searcher_lines)
    attacker_supply = max(0, int(attacker_available))
    searcher_supply = max(0, int(searcher_available))
    for _ in range(max(0, int(additions))):
        prefer_attacker = attackers < 2 or (
            searchers >= 2 and attackers < 3
        )
        if prefer_attacker and attacker_supply > 0:
            attackers += 1
            attacker_supply -= 1
        elif searcher_supply > 0:
            searchers += 1
            searcher_supply -= 1
        elif attacker_supply > 0:
            attackers += 1
            attacker_supply -= 1
        else:
            break
    return attackers, searchers


def _outcome(
    target: KoTarget,
    *,
    bench_count: int,
    brave_bangle: bool,
    support: DamageSupport,
    hit_count: int,
) -> KoOutcome:
    return lookup_ko_outcome(KoOutcomeKey(
        bench_count=bench_count,
        target_hp=target.hp,
        target_ex=target.target_ex,
        grass_weakness=target.grass_weakness,
        brave_bangle=brave_bangle,
        support=support,
        hit_count=hit_count,
    ))


def _support_damage_order(support: DamageSupport) -> int:
    return {
        DamageSupport.NONE: 0,
        DamageSupport.KIERAN: 1,
        DamageSupport.BLACK_BELT: 2,
    }[support]


def _step_resource_cost(step: KoRouteStep) -> int:
    return {
        KoRouteStep.ATTACK: 0,
        KoRouteStep.PLAY_BASIC: 0,
        KoRouteStep.PLAY_POFFIN: 0,
        KoRouteStep.ATTACH_BANGLE: 0,
        KoRouteStep.PLAY_FESTIVAL: 0,
        KoRouteStep.PLAY_BROCK_FOR_BASIC: 1,
        KoRouteStep.PLAY_KIERAN: 1,
        KoRouteStep.PLAY_BLACK_BELT: 1,
        KoRouteStep.USE_THWACKEY_FOR_POFFIN: 2,
        KoRouteStep.USE_THWACKEY_FOR_FESTIVAL: 2,
        KoRouteStep.USE_THWACKEY_FOR_BANGLE: 2,
        KoRouteStep.USE_THWACKEY_FOR_KIERAN: 3,
        KoRouteStep.USE_THWACKEY_FOR_BLACK_BELT: 3,
        KoRouteStep.NONE: 9,
    }[step]
