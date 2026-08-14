from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class SearchRouteClass(IntEnum):
    NONE = 0
    BANK_KNOWN_COMPONENT = 1
    EXACT_SEARCH = 2
    PROBABILISTIC_DRAW = 3
    INSURED_DRAW = 4


class SearchEconomyStep(IntEnum):
    NONE = 0
    BANK_DIRECT_COMPONENT = 1
    PLAY_BUG_SET = 2
    PLAY_UNFAIR_STAMP = 3
    PLAY_LILLIE = 4
    PLAY_JUDGE = 5
    USE_EXACT_SEARCH = 6


@dataclass(frozen=True)
class SearchEconomyState:
    missing_component_count: int
    direct_component_count: int
    exact_searches_available: int
    exact_fallback_available: bool
    bug_set_available: bool = False
    unfair_stamp_available: bool = False
    lillie_available: bool = False
    judge_available: bool = False
    supporter_available: bool = False

    def __post_init__(self) -> None:
        if min(
            self.missing_component_count,
            self.direct_component_count,
            self.exact_searches_available,
        ) < 0:
            raise ValueError("component and exact-search counts cannot be negative")


@dataclass(frozen=True)
class SearchEconomyPlan:
    route_class: SearchRouteClass
    next_step: SearchEconomyStep
    consumes_supporter: bool
    reserved_exact_searches: int


def lookup_search_economy(state: SearchEconomyState) -> SearchEconomyPlan:
    if state.missing_component_count == 0:
        return _plan(SearchRouteClass.NONE, SearchEconomyStep.NONE, state, False)
    if state.direct_component_count > 0:
        return _plan(
            SearchRouteClass.BANK_KNOWN_COMPONENT,
            SearchEconomyStep.BANK_DIRECT_COMPONENT,
            state,
            False,
        )

    route_class = (
        SearchRouteClass.INSURED_DRAW
        if state.exact_fallback_available and state.exact_searches_available > 0
        else SearchRouteClass.PROBABILISTIC_DRAW
    )
    if state.bug_set_available:
        return _plan(route_class, SearchEconomyStep.PLAY_BUG_SET, state, False)
    if state.unfair_stamp_available:
        return _plan(
            route_class,
            SearchEconomyStep.PLAY_UNFAIR_STAMP,
            state,
            False,
        )
    if state.supporter_available and state.lillie_available:
        return _plan(route_class, SearchEconomyStep.PLAY_LILLIE, state, True)
    if state.supporter_available and state.judge_available:
        return _plan(route_class, SearchEconomyStep.PLAY_JUDGE, state, True)
    if state.exact_fallback_available and state.exact_searches_available > 0:
        return _plan(
            SearchRouteClass.EXACT_SEARCH,
            SearchEconomyStep.USE_EXACT_SEARCH,
            state,
            False,
        )
    return _plan(SearchRouteClass.NONE, SearchEconomyStep.NONE, state, False)


def _plan(
    route_class: SearchRouteClass,
    step: SearchEconomyStep,
    state: SearchEconomyState,
    consumes_supporter: bool,
) -> SearchEconomyPlan:
    return SearchEconomyPlan(
        route_class=route_class,
        next_step=step,
        consumes_supporter=consumes_supporter,
        reserved_exact_searches=(
            state.exact_searches_available
            if state.exact_fallback_available
            else 0
        ),
    )
