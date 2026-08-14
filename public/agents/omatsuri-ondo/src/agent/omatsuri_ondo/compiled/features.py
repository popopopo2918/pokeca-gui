from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from common_strategy import (
    EnergyType,
    GameView,
    LegalOption,
    OptionType,
    PokemonRef,
)

from ..cards import AttackId, CardId, DECK_COUNTS
from ..damage_patterns import DamagePatternKey, DamageSupport, lookup_damage
from .boss_patterns import BossDecisionClass, lookup_boss_pattern
from .ko_chain import (
    MAX_ATTACKER_GENERATIONS,
    KoChainClass,
    KoChainPlan,
    KoChainState,
    KoTarget,
    lookup_ko_chain,
)
from .ko_routes import (
    KoReachability,
    KoRoutePlan,
    KoRouteState,
    KoRouteStep,
    lookup_active_ko_route,
)
from .memory import CompiledMemory
from .search_economy import SearchEconomyState, lookup_search_economy
from .schema import CardZone, PolicyFeatures, PokemonRole, ScalarFeature


@dataclass(frozen=True)
class RoleBinding:
    role: PokemonRole
    card_id: int
    serial: int | None


@dataclass(frozen=True)
class RoleAssignment:
    bindings: tuple[RoleBinding, ...]

    def __post_init__(self) -> None:
        roles = tuple(binding.role for binding in self.bindings)
        if roles != tuple(sorted(roles, key=int)) or len(roles) != len(set(roles)):
            raise ValueError("role bindings must be unique and sorted")

    def serial_for(self, role: PokemonRole) -> int | None:
        for binding in self.bindings:
            if binding.role is role:
                return binding.serial
        return None

    def role_for_serial(self, serial: int | None) -> PokemonRole:
        if serial is None:
            return PokemonRole.NONE
        for binding in self.bindings:
            if binding.serial == int(serial):
                return binding.role
        return PokemonRole.NONE

    def semantic_key(self) -> tuple[int, ...]:
        by_role = {binding.role: binding.card_id for binding in self.bindings}
        return tuple(int(by_role.get(role, 0)) for role in PokemonRole)


def deck_bounds(
    *,
    original_count: int,
    visible_outside_deck_and_prizes: int,
    known_prize_count: int,
    unknown_prize_count: int,
    current_deck_count: int,
    known_deck_count: int | None,
) -> tuple[int, int]:
    deck_size = max(0, int(current_deck_count))
    if known_deck_count is not None:
        exact = max(0, min(int(known_deck_count), deck_size))
        return exact, exact
    unseen = max(
        0,
        int(original_count)
        - max(0, int(visible_outside_deck_and_prizes))
        - max(0, int(known_prize_count)),
    )
    lower = max(0, unseen - max(0, int(unknown_prize_count)))
    upper = max(0, min(unseen, deck_size))
    return min(lower, upper), upper


def assign_roles(view: GameView, memory: CompiledMemory) -> RoleAssignment:
    bindings: dict[PokemonRole, PokemonRef] = {}
    active = view.own_active
    field = tuple(view.own_field)
    if active is not None:
        bindings[PokemonRole.MOVEMENT_ACTIVE] = active

    dipplins = [pokemon for pokemon in field if pokemon.id == int(CardId.DIPPLIN)]
    if dipplins:
        powered = tuple(
            pokemon for pokemon in dipplins if _dipplin_has_energy(pokemon)
        )
        if (
            active is not None
            and active.id == int(CardId.DIPPLIN)
            and _dipplin_has_energy(active)
        ):
            chosen = active
        elif powered:
            chosen = min(powered, key=_attacker_order)
        elif active is not None and active.id == int(CardId.DIPPLIN):
            chosen = active
        else:
            chosen = min(dipplins, key=_attacker_order)
        bindings[PokemonRole.ATTACKER] = chosen
        dipplins = [
            pokemon
            for pokemon in dipplins
            if not _same_pokemon(pokemon, chosen)
        ]

    if dipplins:
        chosen = min(dipplins, key=_attacker_order)
        bindings[PokemonRole.NEXT_ATTACKER] = chosen

    applins = [pokemon for pokemon in field if pokemon.id == int(CardId.APPLIN)]
    if applins:
        bindings[PokemonRole.SECOND_NEXT_ATTACKER] = min(
            applins,
            key=lambda pokemon: (
                0 if _pokemon_has_grass(pokemon) else 1,
                *_stable_pokemon_order(pokemon),
            ),
        )

    bench_dipplin_waiting = bool(
        active is not None
        and active.id == int(CardId.GROOKEY)
        and any(
            pokemon.id == int(CardId.DIPPLIN)
            and not _same_pokemon(pokemon, active)
            for pokemon in field
        )
    )
    grookeys = sorted(
        (
            pokemon
            for pokemon in field
            if pokemon.id == int(CardId.GROOKEY)
            and not (
                bench_dipplin_waiting
                and active is not None
                and _same_pokemon(pokemon, active)
            )
        ),
        key=lambda pokemon: (
            int(pokemon.appear_this_turn),
            int(active is not None and _same_pokemon(pokemon, active)),
            -int(pokemon.hp),
            int(pokemon.area or 0),
            _serial_order(pokemon.serial),
        ),
    )
    if grookeys:
        bindings[PokemonRole.NEXT_SEARCHER] = grookeys[0]
    if len(grookeys) > 1:
        bindings[PokemonRole.SECOND_NEXT_SEARCHER] = grookeys[1]

    thwackeys = sorted(
        (pokemon for pokemon in field if pokemon.id == int(CardId.THWACKEY)),
        key=lambda pokemon: (
            0
            if pokemon.serial is not None
            and int(pokemon.serial) in memory.unused_thwackey_serials
            else 1,
            *_stable_pokemon_order(pokemon),
        ),
    )
    if thwackeys:
        bindings[PokemonRole.SEARCHER_ONE] = thwackeys[0]
    if len(thwackeys) > 1:
        bindings[PokemonRole.SEARCHER_TWO] = thwackeys[1]

    festival_leads = sorted(
        (
            pokemon
            for pokemon in view.own_bench
            if pokemon.id == int(CardId.DIPPLIN)
        ),
        key=_stable_pokemon_order,
    )
    if festival_leads:
        bindings[PokemonRole.FESTIVAL_LEAD] = festival_leads[0]

    for role, card_ids in (
        (PokemonRole.BUDEW, (CardId.BUDEW,)),
        (PokemonRole.GOLDEEN, (CardId.GOLDEEN, CardId.SEAKING)),
        (PokemonRole.SHAYMIN, (CardId.SHAYMIN,)),
        (PokemonRole.PSYDUCK, (CardId.PSYDUCK,)),
    ):
        allowed_ids = {int(card_id) for card_id in card_ids}
        candidates = [pokemon for pokemon in field if pokemon.id in allowed_ids]
        if candidates:
            bindings[role] = min(candidates, key=_stable_pokemon_order)

    occupied_serials = {
        pokemon.serial
        for pokemon in bindings.values()
        if pokemon.serial is not None
    }
    if active is not None and active.serial not in occupied_serials:
        bindings[PokemonRole.ACTIVE] = active

    return RoleAssignment(tuple(
        RoleBinding(role, int(pokemon.id), pokemon.serial)
        for role, pokemon in sorted(bindings.items(), key=lambda item: int(item[0]))
    ))


def extract_policy_features(
    view: GameView,
    memory: CompiledMemory,
) -> PolicyFeatures:
    roles = assign_roles(view, memory)
    options = tuple(view.options)
    hand = Counter(int(card_id) for card_id in view.own_hand_ids)
    discard = Counter(
        int(card["id"])
        for card in (view.own.get("discard") or ())
        if isinstance(card, dict) and card.get("id") is not None
    )
    looking = Counter(int(card_id) for card_id in view.looking_ids)
    legal_play = Counter({
        int(option.card_id): 1
        for option in options
        if option.card_id is not None
        and int(option.type)
        in (
            int(OptionType.PLAY),
            int(OptionType.ATTACH),
            int(OptionType.EVOLVE),
        )
    })
    card_counts: dict[tuple[CardZone, int], int] = {}
    visible_outside = Counter(view.own_non_prize_card_ids)
    visible_outside.update(looking)
    known_prizes = Counter(memory.known_prize_counts)
    unknown_prizes = max(0, int(view.own_prize_count) - sum(known_prizes.values()))
    current_deck_count = max(0, int(view.own.get("deckCount", 0)))

    for raw_card_id, original_count in DECK_COUNTS.items():
        card_id = int(raw_card_id)
        known_deck_count = (
            None
            if memory.known_deck_counts is None
            else int(memory.known_deck_counts[card_id])
        )
        minimum, maximum = deck_bounds(
            original_count=int(original_count),
            visible_outside_deck_and_prizes=int(visible_outside[card_id]),
            known_prize_count=int(known_prizes[card_id]),
            unknown_prize_count=unknown_prizes,
            current_deck_count=current_deck_count,
            known_deck_count=known_deck_count,
        )
        card_counts[(CardZone.HAND, card_id)] = int(hand[card_id])
        card_counts[(CardZone.DECK_MIN, card_id)] = minimum
        card_counts[(CardZone.DECK_MAX, card_id)] = maximum
        card_counts[(CardZone.DISCARD, card_id)] = int(discard[card_id])
        card_counts[(CardZone.LOOKING, card_id)] = int(looking[card_id])
        card_counts[(CardZone.LEGAL_PLAY, card_id)] = int(legal_play[card_id])

    active = view.own_active
    opponent = view.opponent_active
    active_role = roles.role_for_serial(None if active is None else active.serial)
    exact_field_counts = Counter(int(pokemon.id) for pokemon in view.own_field)
    opponent_meta = None if opponent is None else view.catalog.card(opponent.id)
    first_player = int(view.current.get("firstPlayer", -1))
    own_is_first = int(first_player == int(view.own_index)) if first_player in (0, 1) else 0
    first_hit_resolved = bool(memory.first_hit_resolved)
    previous_ko = (
        memory.previous_opponent_knockout_turn is not None
        and int(memory.previous_opponent_knockout_turn)
        == int(view.current.get("turn", 0)) - 1
    )
    dipplin_family_lines = (
        exact_field_counts[int(CardId.APPLIN)]
        + exact_field_counts[int(CardId.DIPPLIN)]
    )
    thwackey_family_lines = (
        exact_field_counts[int(CardId.GROOKEY)]
        + exact_field_counts[int(CardId.THWACKEY)]
    )
    minimum_board_complete = (
        dipplin_family_lines >= 2 and thwackey_family_lines >= 2
    )
    bench_free = max(
        0,
        int(view.own.get("benchMax", 5)) - len(view.own_bench),
    )
    attacker = _pokemon_for_role(view, roles, PokemonRole.ATTACKER)
    next_attacker = _pokemon_for_role(view, roles, PokemonRole.NEXT_ATTACKER)
    second_next_attacker = _pokemon_for_role(
        view,
        roles,
        PokemonRole.SECOND_NEXT_ATTACKER,
    )
    next_searcher = _pokemon_for_role(view, roles, PokemonRole.NEXT_SEARCHER)
    second_next_searcher = _pokemon_for_role(
        view,
        roles,
        PokemonRole.SECOND_NEXT_SEARCHER,
    )
    searcher_one = _pokemon_for_role(view, roles, PokemonRole.SEARCHER_ONE)
    festival_lead = _pokemon_for_role(view, roles, PokemonRole.FESTIVAL_LEAD)
    shaymin = _pokemon_for_role(view, roles, PokemonRole.SHAYMIN)
    goldeen = _pokemon_for_role(view, roles, PokemonRole.GOLDEEN)
    psyduck = _pokemon_for_role(view, roles, PokemonRole.PSYDUCK)
    legal_evolution_targets = {
        option.target.serial
        for option in options
        if int(option.type) == int(OptionType.EVOLVE)
        and option.target is not None
    }
    festival_active = int(CardId.FESTIVAL_GROUNDS) in view.public_stadium_ids
    damage = _damage_features(
        view,
        memory,
        active=active,
        opponent=opponent,
        festival_active=festival_active,
    )
    can_use_thwackey = any(
        int(option.type) == int(OptionType.ABILITY)
        and option.source is not None
        and option.source.id == int(CardId.THWACKEY)
        and option.source.serial is not None
        and int(option.source.serial) in memory.unused_thwackey_serials
        for option in options
    )
    can_dipplin_attack = _has_attack(options, AttackId.DIPPLIN_DO_THE_WAVE)
    basic_ids = (
        CardId.APPLIN,
        CardId.GROOKEY,
    )
    direct_basic_count = min(
        bench_free,
        sum(
            int(hand[int(card_id)])
            for card_id in basic_ids
            if legal_play[int(card_id)]
        ),
    )
    poffin_basic_count = min(
        bench_free,
        sum(
            card_counts[(CardZone.DECK_MIN, int(card_id))]
            for card_id in basic_ids
        ),
    )
    brock_basic_count = min(
        bench_free,
        sum(
            card_counts[(CardZone.DECK_MIN, int(card_id))]
            for card_id in basic_ids
        ),
    )
    direct_attacker_count = (
        int(hand[int(CardId.APPLIN)])
        if legal_play[int(CardId.APPLIN)]
        else 0
    )
    direct_searcher_count = (
        int(hand[int(CardId.GROOKEY)])
        if legal_play[int(CardId.GROOKEY)]
        else 0
    )
    poffin_attacker_count = int(
        card_counts[(CardZone.DECK_MIN, int(CardId.APPLIN))]
    )
    poffin_searcher_count = int(
        card_counts[(CardZone.DECK_MIN, int(CardId.GROOKEY))]
    )
    third_attacker_reachable = bool(
        dipplin_family_lines >= 3
        or hand[int(CardId.APPLIN)] > 0
        or card_counts[(CardZone.DECK_MAX, int(CardId.APPLIN))] > 0
        or discard[int(CardId.APPLIN)] > 0
    )
    active_ko_plan = KoRoutePlan(
        reachability=KoReachability.UNREACHABLE,
        next_step=KoRouteStep.NONE,
        goal_bench_count=0,
        damage=0,
        first_hit_ko=False,
        hits_remaining_after_ko=0,
    )
    active_route_state: KoRouteState | None = None
    opponent_hp = 0 if opponent is None else max(0, int(opponent.hp))
    normalized_opponent_hp = ((opponent_hp + 9) // 10) * 10
    if (
        can_dipplin_attack
        and opponent is not None
        and 10 <= normalized_opponent_hp <= 400
    ):
        opponent_meta = view.catalog.card(opponent.id)
        active_route_state = KoRouteState(
            bench_count=min(5, len(view.own_bench)),
            bench_free=bench_free,
            target_hp=normalized_opponent_hp,
            target_ex=bool(
                opponent_meta is not None
                and (opponent_meta.ex or opponent_meta.mega_ex)
            ),
            grass_weakness=bool(
                opponent_meta is not None
                and opponent_meta.weakness == int(EnergyType.GRASS)
            ),
            hit_count=max(1, int(damage["hit_count"])),
            brave_bangle=bool(
                active is not None
                and int(CardId.BRAVE_BANGLE) in active.tool_ids
            ),
            support={
                1: DamageSupport.KIERAN,
                2: DamageSupport.BLACK_BELT,
            }.get(int(memory.damage_support), DamageSupport.NONE),
            supporter_available=memory.supporter_available,
            direct_basic_count=direct_basic_count,
            poffin_in_hand=bool(legal_play[int(CardId.BUDDY_BUDDY_POFFIN)]),
            poffin_basic_count=poffin_basic_count,
            brock_in_hand=bool(legal_play[int(CardId.BROCKS_SCOUTING)]),
            brock_basic_count=brock_basic_count,
            can_use_thwackey=can_use_thwackey,
            unused_thwackey=len(memory.unused_thwackey_serials),
            poffin_in_deck=(
                card_counts[
                    (CardZone.DECK_MIN, int(CardId.BUDDY_BUDDY_POFFIN))
                ] > 0
            ),
            festival_in_hand=bool(
                not memory.first_hit_resolved
                and legal_play[int(CardId.FESTIVAL_GROUNDS)]
            ),
            festival_in_deck=bool(
                not memory.first_hit_resolved
                and card_counts[
                    (CardZone.DECK_MIN, int(CardId.FESTIVAL_GROUNDS))
                ] > 0
            ),
            bangle_in_hand=bool(legal_play[int(CardId.BRAVE_BANGLE)]),
            bangle_in_deck=bool(
                card_counts[(CardZone.DECK_MIN, int(CardId.BRAVE_BANGLE))] > 0
            ),
            kieran_in_hand=bool(legal_play[int(CardId.KIERAN)]),
            kieran_in_deck=bool(
                card_counts[(CardZone.DECK_MIN, int(CardId.KIERAN))] > 0
            ),
            black_belt_in_hand=bool(
                legal_play[int(CardId.BLACK_BELTS_TRAINING)]
            ),
            black_belt_in_deck=bool(
                card_counts[
                    (CardZone.DECK_MIN, int(CardId.BLACK_BELTS_TRAINING))
                ] > 0
            ),
            black_belt_enabled=(
                int(view.own_prize_count)
                > len(view.opponent.get("prize") or ())
            ),
            attacker_line_count=dipplin_family_lines,
            searcher_line_count=thwackey_family_lines,
            third_attacker_reachable=third_attacker_reachable,
            direct_attacker_count=direct_attacker_count,
            direct_searcher_count=direct_searcher_count,
            poffin_attacker_count=poffin_attacker_count,
            poffin_searcher_count=poffin_searcher_count,
            brock_attacker_count=poffin_attacker_count,
            brock_searcher_count=poffin_searcher_count,
        )
        active_ko_plan = lookup_active_ko_route(active_route_state)
    need_dipplin_line = int(dipplin_family_lines < 2)
    need_thwackey_line = int(thwackey_family_lines < 2)
    missing_search_components = need_dipplin_line + need_thwackey_line
    direct_search_components = (
        int(
            need_dipplin_line
            and bool(legal_play[int(CardId.APPLIN)])
        )
        + int(
            need_thwackey_line
            and bool(legal_play[int(CardId.GROOKEY)])
        )
    )
    if (
        missing_search_components > 0
        and legal_play[int(CardId.BUDDY_BUDDY_POFFIN)]
        and poffin_basic_count > 0
    ):
        direct_search_components = max(1, direct_search_components)
    if (
        missing_search_components > 0
        and legal_play[int(CardId.POKE_PAD)]
        and (
            need_dipplin_line
            and card_counts[(CardZone.DECK_MIN, int(CardId.APPLIN))] > 0
            or need_thwackey_line
            and card_counts[(CardZone.DECK_MIN, int(CardId.GROOKEY))] > 0
        )
    ):
        direct_search_components = max(1, direct_search_components)
    exact_basic_targets = (
        int(
            need_dipplin_line
            and card_counts[(CardZone.DECK_MIN, int(CardId.APPLIN))] > 0
        )
        + int(
            need_thwackey_line
            and card_counts[(CardZone.DECK_MIN, int(CardId.GROOKEY))] > 0
        )
    )
    poffin_covers_all_gaps = bool(
        card_counts[
            (CardZone.DECK_MIN, int(CardId.BUDDY_BUDDY_POFFIN))
        ] > 0
        and poffin_basic_count >= missing_search_components
    )
    exact_board_fallback = bool(
        can_use_thwackey
        and missing_search_components > 0
        and (
            poffin_covers_all_gaps
            or (
                len(memory.unused_thwackey_serials)
                >= missing_search_components
                and exact_basic_targets >= missing_search_components
            )
        )
    )
    search_economy_plan = lookup_search_economy(SearchEconomyState(
        missing_component_count=missing_search_components,
        direct_component_count=direct_search_components,
        exact_searches_available=len(memory.unused_thwackey_serials),
        exact_fallback_available=exact_board_fallback,
        bug_set_available=bool(legal_play[int(CardId.BUG_CATCHING_SET)]),
        unfair_stamp_available=bool(
            previous_ko and legal_play[int(CardId.UNFAIR_STAMP)]
        ),
        lillie_available=bool(
            legal_play[int(CardId.LILLIES_DETERMINATION)]
        ),
        judge_available=bool(legal_play[int(CardId.JUDGE)]),
        supporter_available=memory.supporter_available,
    ))
    boss_accessible = bool(
        legal_play[int(CardId.BOSSES_ORDERS)]
        or (
            can_use_thwackey
            and card_counts[
                (CardZone.DECK_MAX, int(CardId.BOSSES_ORDERS))
            ] > 0
        )
    )
    boss_pattern = lookup_boss_pattern(view)
    boss_decision_class = (
        BossDecisionClass.NONE
        if boss_pattern is None
        else boss_pattern.decision_class
    )
    boss_candidate_preferred = bool(
        memory.supporter_available
        and boss_accessible
        and boss_decision_class is not BossDecisionClass.NONE
    )
    boss_target_ko_now = bool(
        boss_pattern is not None and boss_pattern.target_ko_now
    )
    selected_boss_prizes = (
        0 if boss_pattern is None else int(boss_pattern.target_prizes)
    )
    boss_class_requires_target_ko = boss_decision_class in (
        BossDecisionClass.FINAL,
        BossDecisionClass.MAINLINE_EXTINCTION,
        BossDecisionClass.FEZANDIPITI_EX,
        BossDecisionClass.MORE_PRIZES,
    )
    # The fixed flow is: finish the game, extinguish every public mainline,
    # remove Fezandipiti ex, then attack the Active.  An ordinary higher-prize
    # Boss route is consulted only after every guaranteed Active KO row failed.
    boss_outcome_can_overtake_active_ko = bool(
        boss_decision_class in (
            BossDecisionClass.FINAL,
            BossDecisionClass.MAINLINE_EXTINCTION,
            BossDecisionClass.FEZANDIPITI_EX,
        )
    )
    boss_preferred = bool(
        boss_candidate_preferred
        and (
            active_ko_plan.reachability < KoReachability.GUARANTEED_KO
            or boss_outcome_can_overtake_active_ko
        )
        and (
            boss_target_ko_now
            if boss_class_requires_target_ko
            else True
        )
    )
    thwackey_unlock_route = _thwackey_unlock_route(
        memory,
        festival_lead=festival_lead,
        festival_active=festival_active,
        legal_play=legal_play,
        card_counts=card_counts,
    )
    missing_core_lines = (
        max(0, 2 - dipplin_family_lines)
        + max(0, 2 - thwackey_family_lines)
    )
    counter_slot_reserve = (
        max(0, 3 - dipplin_family_lines)
        + max(0, 2 - thwackey_family_lines)
    )
    promotable_applin_route = _promotable_applin_route(
        view,
        memory,
        candidate=second_next_attacker,
        festival_active=festival_active,
        hand=hand,
        discard=discard,
        card_counts=card_counts,
    )
    next_turn_attack_route = _next_turn_attack_route(
        view,
        memory,
        current_attacker=attacker,
        hand=hand,
        discard=discard,
        legal_play=legal_play,
        card_counts=card_counts,
    )
    next_attack_preparation_class = _next_attack_preparation_class(
        view,
        memory,
        current_attacker=attacker,
        festival_active=festival_active,
        hand=hand,
        discard=discard,
        card_counts=card_counts,
    )
    ko_chain_plan = KoChainPlan(
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
    if active_route_state is not None and opponent is not None:
        active_meta = view.catalog.card(opponent.id)
        promotions = tuple(
            _ko_chain_target(view, target)
            for target in view.opponent_bench
            if 0 < int(target.hp) <= 400
        )
        current_generation_already_counted = bool(
            memory.first_attack_source_serial is not None
        )
        generations_after_current = max(
            0,
            MAX_ATTACKER_GENERATIONS
            - int(memory.attacker_generations_used)
            - int(not current_generation_already_counted),
        )
        ko_chain_plan = lookup_ko_chain(KoChainState(
            route=active_route_state,
            active=KoTarget(
                hp=active_route_state.target_hp,
                prizes=1 if active_meta is None else int(active_meta.prize_value),
                target_ex=active_route_state.target_ex,
                grass_weakness=active_route_state.grass_weakness,
            ),
            promotions=promotions,
            next_attack_preparation_class=next_attack_preparation_class,
            own_prizes_remaining=int(view.own_prize_count),
            future_attacker_generations=generations_after_current,
        ))
    energy_retreat_prep_route = _energy_retreat_prep_route(
        view,
        memory,
        candidate=second_next_attacker,
        festival_active=festival_active,
        hand=hand,
        discard=discard,
        card_counts=card_counts,
    )
    energy_retreat_attack_route = _energy_retreat_attack_route(
        view,
        memory,
        candidate=festival_lead,
        hand=hand,
        card_counts=card_counts,
    )
    # Legacy damage-only Boss classes remain in the schema for compatibility,
    # but the canonical selector no longer emits them.
    bench_ko_strictly_dominates_boss = bool(
        boss_candidate_preferred
        and boss_decision_class in (
            BossDecisionClass.TWO_HIT_BENCH,
            BossDecisionClass.DOUBLE_KO,
        )
        and damage["ko_bench"]
        and next_turn_attack_route == 0
        and selected_boss_prizes > 0
        and damage["active_prizes"] >= selected_boss_prizes
    )

    scalars = {
        ScalarFeature.SELECT_TYPE: int(view.select.get("type", -1)),
        ScalarFeature.SELECT_CONTEXT: int(view.select.get("context", -1)),
        ScalarFeature.SELECT_MIN: int(view.select.get("minCount", 0)),
        ScalarFeature.SELECT_MAX: int(view.select.get("maxCount", 0)),
        ScalarFeature.OWN_TURN_NUMBER: int(view.own_turn_number),
        ScalarFeature.FIRST_PLAYER: own_is_first,
        ScalarFeature.ACTIVE_ROLE: int(active_role),
        ScalarFeature.APPLIN_LINES: exact_field_counts[int(CardId.APPLIN)],
        ScalarFeature.DIPPLIN_LINES: exact_field_counts[int(CardId.DIPPLIN)],
        ScalarFeature.GROOKEY_LINES: exact_field_counts[int(CardId.GROOKEY)],
        ScalarFeature.THWACKEY_LINES: exact_field_counts[int(CardId.THWACKEY)],
        ScalarFeature.BENCH_FREE: bench_free,
        ScalarFeature.EVOLVABLE_APPLIN: _legal_evolution_target_count(
            options,
            CardId.DIPPLIN,
            CardId.APPLIN,
        ),
        ScalarFeature.EVOLVABLE_GROOKEY: _legal_evolution_target_count(
            options,
            CardId.THWACKEY,
            CardId.GROOKEY,
        ),
        ScalarFeature.READY_DIPPLIN: sum(
            _dipplin_has_energy(pokemon) for pokemon in view.own_field
            if pokemon.id == int(CardId.DIPPLIN)
        ),
        ScalarFeature.UNUSED_THWACKEY: len(memory.unused_thwackey_serials),
        ScalarFeature.SUPPORTER_AVAILABLE: int(memory.supporter_available),
        ScalarFeature.ATTACHMENT_AVAILABLE: int(memory.attachment_available),
        ScalarFeature.RETREAT_AVAILABLE: int(memory.retreat_available),
        ScalarFeature.FESTIVAL_ACTIVE: int(
            int(CardId.FESTIVAL_GROUNDS) in view.public_stadium_ids
        ),
        ScalarFeature.FIRST_HIT_RESOLVED: int(first_hit_resolved),
        ScalarFeature.PREVIOUS_OPPONENT_KO: int(previous_ko),
        ScalarFeature.CAN_DIPPLIN_ATTACK: int(can_dipplin_attack),
        ScalarFeature.CAN_BUDEW_ATTACK: int(_has_attack(options, AttackId.BUDEW_ITTY_BITTY_POLLEN)),
        ScalarFeature.CAN_RETREAT: int(_has_option(options, OptionType.RETREAT)),
        ScalarFeature.CAN_END: int(_has_option(options, OptionType.END)),
        ScalarFeature.EFFECT_CARD_ID: _effect_card_id(view),
        ScalarFeature.OPPONENT_ACTIVE_HP: 0 if opponent is None else max(0, int(opponent.hp)),
        ScalarFeature.OPPONENT_ACTIVE_GRASS_WEAK: int(
            opponent_meta is not None
            and opponent_meta.weakness == int(EnergyType.GRASS)
        ),
        ScalarFeature.OPPONENT_ACTIVE_EX: int(
            opponent_meta is not None
            and (opponent_meta.ex or opponent_meta.mega_ex)
        ),
        ScalarFeature.OPPONENT_BENCH_COUNT: len(view.opponent_bench),
        ScalarFeature.OWN_PRIZES: int(view.own_prize_count),
        ScalarFeature.OPPONENT_PRIZES: len(view.opponent.get("prize") or ()),
        ScalarFeature.OPPONENT_TARGET_CLASS: 0 if opponent_meta is None else int(opponent_meta.prize_value),
        ScalarFeature.TURN_ACTION_COUNT: int(view.current.get("turnActionCount", 0)),
        ScalarFeature.HAND_SIZE: len(view.own_hand_ids),
        ScalarFeature.DECK_COUNT: current_deck_count,
        ScalarFeature.OWN_FIELD_COUNT: len(view.own_field),
        ScalarFeature.OWN_BENCH_COUNT: len(view.own_bench),
        ScalarFeature.ACTIVE_CARD_ID: 0 if active is None else int(active.id),
        ScalarFeature.DIPPLIN_FAMILY_LINES: dipplin_family_lines,
        ScalarFeature.THWACKEY_FAMILY_LINES: thwackey_family_lines,
        ScalarFeature.MINIMUM_BOARD_COMPLETE: int(minimum_board_complete),
        ScalarFeature.NEED_DIPPLIN_LINE: int(dipplin_family_lines < 2),
        ScalarFeature.NEED_THWACKEY_LINE: int(thwackey_family_lines < 2),
        ScalarFeature.SAFE_EXTRA_SLOT: int(
            minimum_board_complete
            and bench_free > 0
        ),
        ScalarFeature.READY_BENCH_DIPPLIN: sum(
            _dipplin_has_energy(pokemon)
            for pokemon in view.own_bench
            if pokemon.id == int(CardId.DIPPLIN)
        ),
        ScalarFeature.ATTACKER_NEEDS_ENERGY: int(
            attacker is not None and not _pokemon_has_grass(attacker)
        ),
        ScalarFeature.NEXT_ATTACKER_NEEDS_ENERGY: int(
            next_attacker is not None and not _pokemon_has_grass(next_attacker)
        ),
        ScalarFeature.SECOND_NEXT_ATTACKER_NEEDS_ENERGY: int(
            second_next_attacker is not None
            and not _pokemon_has_grass(second_next_attacker)
        ),
        ScalarFeature.ATTACKER_ON_BENCH: int(
            attacker is not None
            and active is not None
            and not _same_pokemon(attacker, active)
        ),
        ScalarFeature.NEXT_SEARCHER_EVOLVABLE: int(
            next_searcher is not None
            and next_searcher.serial in legal_evolution_targets
        ),
        ScalarFeature.SECOND_NEXT_SEARCHER_EVOLVABLE: int(
            second_next_searcher is not None
            and second_next_searcher.serial in legal_evolution_targets
        ),
        ScalarFeature.CAN_USE_THWACKEY: int(can_use_thwackey),
        ScalarFeature.ACTIVE_HAS_BALLOON: int(
            active is not None and int(CardId.AIR_BALLOON) in active.tool_ids
        ),
        ScalarFeature.ACTIVE_TOOL_FREE: int(
            active is not None and not active.tool_ids
        ),
        ScalarFeature.ACTIVE_RETREAT_COST: _retreat_cost(view, active),
        ScalarFeature.OPPONENT_BENCH_DAMAGE_THREAT: int(
            view.opponent_has_public_bench_damage_attack
        ),
        ScalarFeature.OPPONENT_SELF_KO_THREAT: int(
            view.opponent_has_public_self_ko_ability
        ),
        ScalarFeature.SHAYMIN_DEPLOYED: int(
            exact_field_counts[int(CardId.SHAYMIN)] > 0
        ),
        ScalarFeature.PSYDUCK_DEPLOYED: int(
            exact_field_counts[int(CardId.PSYDUCK)] > 0
        ),
        ScalarFeature.BALLOON_SEARCHER_TARGET: int(
            _has_attach_target(options, CardId.AIR_BALLOON, searcher_one)
        ),
        ScalarFeature.BALLOON_SHAYMIN_TARGET: int(
            _has_attach_target(options, CardId.AIR_BALLOON, shaymin)
        ),
        ScalarFeature.BALLOON_GOLDEEN_TARGET: int(
            _has_attach_target(options, CardId.AIR_BALLOON, goldeen)
        ),
        ScalarFeature.BALLOON_PSYDUCK_TARGET: int(
            _has_attach_target(options, CardId.AIR_BALLOON, psyduck)
        ),
        ScalarFeature.BALLOON_GOLDEEN_READY: int(
            goldeen is not None
            and int(CardId.AIR_BALLOON) in goldeen.tool_ids
        ),
        ScalarFeature.BOSS_PREFERRED: int(boss_preferred),
        ScalarFeature.BEST_KOABLE_BENCH_PRIZES: damage["best_boss_prizes"],
        ScalarFeature.BOSS_DECISION_CLASS: int(boss_decision_class),
        ScalarFeature.CURRENT_HIT_COUNT: damage["hit_count"],
        ScalarFeature.CURRENT_DAMAGE: damage["current"],
        ScalarFeature.CAN_KO_NOW: damage["ko_now"],
        ScalarFeature.CAN_KO_WITH_FESTIVAL: damage["ko_festival"],
        ScalarFeature.CAN_KO_WITH_BANGLE: damage["ko_bangle"],
        ScalarFeature.CAN_KO_WITH_KIERAN: damage["ko_kieran"],
        ScalarFeature.CAN_KO_WITH_BLACK_BELT: damage["ko_black_belt"],
        ScalarFeature.CAN_KO_WITH_ONE_MORE_BENCH: damage["ko_bench"],
        ScalarFeature.CAN_KO_WITH_TWO_MORE_BENCH: damage["ko_two_bench"],
        ScalarFeature.CAN_KO_WITH_FULL_BENCH: damage["ko_full_bench"],
        ScalarFeature.DAMAGE_GAIN_WITH_FESTIVAL: damage["gain_festival"],
        ScalarFeature.DAMAGE_GAIN_WITH_BANGLE: damage["gain_bangle"],
        ScalarFeature.DAMAGE_GAIN_WITH_KIERAN: damage["gain_kieran"],
        ScalarFeature.DAMAGE_GAIN_WITH_BLACK_BELT: damage["gain_black_belt"],
        ScalarFeature.DAMAGE_GAIN_WITH_ONE_MORE_BENCH: damage["gain_bench"],
        ScalarFeature.KOABLE_OPPONENT_BENCH: damage["koable_bench"],
        ScalarFeature.OPPONENT_HAND_SIZE: int(
            view.opponent.get("handCount", len(view.opponent.get("hand") or ()))
        ),
        ScalarFeature.ACTIVE_APPLIN_EVOLVABLE: int(
            active is not None
            and active.id == int(CardId.APPLIN)
            and active.serial in legal_evolution_targets
        ),
        ScalarFeature.BACKUP_APPLIN_EVOLVABLE: int(any(
            pokemon.id == int(CardId.APPLIN)
            and pokemon.serial in legal_evolution_targets
            and (active is None or not _same_pokemon(pokemon, active))
            for pokemon in view.own_field
        )),
        ScalarFeature.ACTIVE_DIPPLIN_READY: int(
            active is not None
            and active.id == int(CardId.DIPPLIN)
            and _pokemon_has_grass(active)
        ),
        ScalarFeature.BUG_SET_USED_THIS_TURN: int(
            int(CardId.BUG_CATCHING_SET) in memory.played_card_ids_this_turn
        ),
        ScalarFeature.POFFIN_USED_THIS_TURN: int(
            int(CardId.BUDDY_BUDDY_POFFIN) in memory.played_card_ids_this_turn
        ),
        ScalarFeature.MATURE_APPLIN: sum(
            int(not pokemon.appear_this_turn)
            for pokemon in view.own_field
            if pokemon.id == int(CardId.APPLIN)
        ),
        ScalarFeature.MATURE_GROOKEY: sum(
            int(not pokemon.appear_this_turn)
            for pokemon in view.own_field
            if pokemon.id == int(CardId.GROOKEY)
        ),
        ScalarFeature.ACTIVE_APPLIN_MATURE: int(
            active is not None
            and active.id == int(CardId.APPLIN)
            and not active.appear_this_turn
        ),
        ScalarFeature.BUDEW_DEPLOYED: int(
            exact_field_counts[int(CardId.BUDEW)] > 0
        ),
        ScalarFeature.BUDEW_ON_BENCH: int(any(
            pokemon.id == int(CardId.BUDEW)
            for pokemon in view.own_bench
        )),
        ScalarFeature.ACTIVE_FESTIVAL_LEAD: int(
            active is not None
            and active.id == int(CardId.DIPPLIN)
        ),
        ScalarFeature.THWACKEY_UNLOCK_ROUTE: int(thwackey_unlock_route),
        ScalarFeature.SAFE_SURVIVAL_SLOT: int(
            bench_free > missing_core_lines
        ),
        ScalarFeature.PROMOTABLE_APPLIN_ROUTE: int(promotable_applin_route),
        ScalarFeature.NEXT_TURN_ATTACK_ROUTE: int(next_turn_attack_route),
        ScalarFeature.NEXT_ATTACK_PREPARATION_CLASS: int(
            next_attack_preparation_class
        ),
        ScalarFeature.ACTIVE_KO_REACHABILITY: int(
            active_ko_plan.reachability
        ),
        ScalarFeature.ACTIVE_KO_NEXT_STEP: int(active_ko_plan.next_step),
        ScalarFeature.ACTIVE_KO_FIRST_HIT: int(active_ko_plan.first_hit_ko),
        ScalarFeature.ACTIVE_KO_HITS_REMAINING: int(
            active_ko_plan.hits_remaining_after_ko
        ),
        ScalarFeature.ACTIVE_KO_GOAL_BENCH: int(
            active_ko_plan.goal_bench_count
        ),
        ScalarFeature.ACTIVE_KO_ROUTE_DAMAGE: int(active_ko_plan.damage),
        ScalarFeature.SEARCH_ECONOMY_CLASS: int(
            search_economy_plan.route_class
        ),
        ScalarFeature.SEARCH_ECONOMY_NEXT_STEP: int(
            search_economy_plan.next_step
        ),
        ScalarFeature.SEARCH_ECONOMY_RESERVED_EXACT: int(
            search_economy_plan.reserved_exact_searches
        ),
        ScalarFeature.KO_CHAIN_CLASS: int(ko_chain_plan.chain_class),
        ScalarFeature.KO_CHAIN_NEXT_STEP: int(ko_chain_plan.next_step),
        ScalarFeature.KO_CHAIN_GOAL_BENCH: int(
            ko_chain_plan.goal_bench_count
        ),
        ScalarFeature.KO_CHAIN_GUARANTEED_PRIZES: int(
            ko_chain_plan.guaranteed_prizes_this_turn
        ),
        ScalarFeature.KO_CHAIN_SECOND_HIT_DAMAGE: int(
            ko_chain_plan.second_hit_damage
        ),
        ScalarFeature.KO_CHAIN_WORST_REMAINING_HP: int(
            ko_chain_plan.worst_promotion_remaining_hp
        ),
        ScalarFeature.KO_CHAIN_RESOURCES_COVER_GAME: int(
            ko_chain_plan.resources_cover_game
        ),
        ScalarFeature.KO_CHAIN_BENCH_ADDITIONS: max(
            0,
            int(ko_chain_plan.goal_bench_count) - len(view.own_bench),
        ),
        ScalarFeature.BENCH_KO_STRICTLY_DOMINATES_BOSS: int(
            bench_ko_strictly_dominates_boss
        ),
        ScalarFeature.BENCH_KO_DOMINANCE_COMMITTED: int(
            memory.bench_ko_dominance_committed
        ),
        ScalarFeature.SAFE_COUNTER_SLOT: int(
            bench_free > counter_slot_reserve
        ),
        ScalarFeature.ENERGY_RETREAT_PREP_ROUTE: int(
            energy_retreat_prep_route
        ),
        ScalarFeature.ENERGY_RETREAT_ATTACK_ROUTE: int(
            energy_retreat_attack_route
        ),
    }
    return PolicyFeatures.from_maps(
        scalars=cast(Mapping[ScalarFeature | int, int], scalars),
        card_counts=cast(
            Mapping[tuple[CardZone | int, int], int],
            card_counts,
        ),
    )


def _pokemon_for_role(
    view: GameView,
    roles: RoleAssignment,
    role: PokemonRole,
) -> PokemonRef | None:
    serial = roles.serial_for(role)
    return next(
        (
            pokemon
            for pokemon in view.own_field
            if pokemon.serial is not None and pokemon.serial == serial
        ),
        None,
    )


def _retreat_cost(view: GameView, pokemon: PokemonRef | None) -> int:
    if pokemon is None:
        return 0
    meta = view.catalog.card(pokemon.id)
    printed = (
        0
        if meta is None or meta.retreat_cost is None
        else max(0, int(meta.retreat_cost))
    )
    return max(
        0,
        printed - (2 if int(CardId.AIR_BALLOON) in pokemon.tool_ids else 0),
    )


def _thwackey_unlock_route(
    memory: CompiledMemory,
    *,
    festival_lead: PokemonRef | None,
    festival_active: bool,
    legal_play: Counter[int],
    card_counts: dict[tuple[CardZone, int], int],
) -> bool:
    """Recognize a precompiled, deterministic switch-to-search attack route."""

    if festival_lead is None or not memory.unused_thwackey_serials:
        return False
    if _pokemon_has_grass(festival_lead):
        return True
    if not memory.attachment_available:
        return False
    if legal_play[int(CardId.BASIC_GRASS)] > 0:
        return True
    if card_counts[(CardZone.DECK_MIN, int(CardId.BASIC_GRASS))] > 0:
        return True
    return bool(
        card_counts[(CardZone.DECK_MAX, int(CardId.BASIC_GRASS))] > 0
        and (
            festival_active
            or legal_play[int(CardId.FESTIVAL_GROUNDS)] > 0
        )
    )


def _energy_retreat_prep_route(
    view: GameView,
    memory: CompiledMemory,
    *,
    candidate: PokemonRef | None,
    festival_active: bool,
    hand: Counter[int],
    discard: Counter[int],
    card_counts: dict[tuple[CardZone, int], int],
) -> int:
    """Classify the fixed T1 Grass-as-retreat fallback component table.

    Two means every deck component is known present and zero rejects the route.
    A merely possible ``DECK_MAX`` component is intentionally excluded: the
    first Grass stays on Applin unless the post-retreat attack is guaranteed.
    """

    active = view.own_active
    if (
        not view.is_own_turn
        or view.own_turn_number != 1
        or active is None
        or active.id != int(CardId.GROOKEY)
        or candidate is None
        or candidate.id != int(CardId.APPLIN)
        or _same_pokemon(active, candidate)
        or _pokemon_has_grass(candidate)
        or not memory.attachment_available
        or _retreat_cost(view, active) != 1
        or _has_option(view.options, OptionType.RETREAT)
        or not _has_attach_target(view.options, CardId.BASIC_GRASS, active)
        or hand[int(CardId.BASIC_GRASS)] <= 0
        or hand[int(CardId.AIR_BALLOON)] > 0
        or hand[int(CardId.KIERAN)] > 0
    ):
        return 0

    # The Grass under consideration is consumed by the opening Grookey.  The
    # remaining component table must still evolve Applin and power Dipplin via
    # a second Grass or a post-retreat Drum Beat.
    future_hand = hand.copy()
    future_hand[int(CardId.BASIC_GRASS)] -= 1
    return 2 * int(_fixed_promotion_attack_route(
        view,
        memory,
        candidate=candidate,
        festival_active=festival_active,
        hand=future_hand,
        discard=discard,
        card_counts=card_counts,
        deck_zone=CardZone.DECK_MIN,
        future_turn=True,
        require_festival_for_thwackey_energy=False,
    ))


def _energy_retreat_attack_route(
    view: GameView,
    memory: CompiledMemory,
    *,
    candidate: PokemonRef | None,
    hand: Counter[int],
    card_counts: dict[tuple[CardZone, int], int],
) -> int:
    """Classify retreat-before-evolution routes to an unpowered Dipplin."""

    active = view.own_active
    if (
        not view.is_own_turn
        or view.own_turn_number < 2
        or active is None
        or active.id != int(CardId.GROOKEY)
        or candidate is None
        or candidate.id != int(CardId.DIPPLIN)
        or _pokemon_has_grass(candidate)
        or not memory.attachment_available
        or not memory.retreat_available
        or _retreat_cost(view, active) not in (0, 1)
        or not _has_option(view.options, OptionType.RETREAT)
    ):
        return 0

    attached_units = max(len(active.energy_card_ids), len(active.energies))
    if attached_units < 1:
        return 0

    if (
        hand[int(CardId.BASIC_GRASS)] > 0
        and _has_attach_target(view.options, CardId.BASIC_GRASS, candidate)
    ):
        return 2

    thwackey_targets = tuple(
        option.target
        for option in view.options
        if int(option.type) == int(OptionType.EVOLVE)
        and option.card_id == int(CardId.THWACKEY)
        and option.target is not None
        and option.target.id == int(CardId.GROOKEY)
    )
    active_is_only_thwackey_base = bool(
        thwackey_targets
        and all(_same_pokemon(target, active) for target in thwackey_targets)
    )
    if memory.unused_thwackey_serials or not active_is_only_thwackey_base:
        return 0

    return 2 * int(
        card_counts[(CardZone.DECK_MIN, int(CardId.BASIC_GRASS))] > 0
    )


def _promotable_applin_route(
    view: GameView,
    memory: CompiledMemory,
    *,
    candidate: PokemonRef | None,
    festival_active: bool,
    hand: Counter[int],
    discard: Counter[int],
    card_counts: dict[tuple[CardZone, int], int],
) -> int:
    """Classify a precompiled post-promotion attack route.

    Values are fixed policy labels: 2 is guaranteed from known resources, 1 is
    contingent on a Bug Catching Set or draw result, and 0 has no recognized
    route.  The function only evaluates component predicates; it never searches
    action sequences during a match.
    """

    promotion_is_between_turns = not view.is_own_turn
    if (
        candidate is None
        or candidate.id != int(CardId.APPLIN)
        # During the opponent's turn the simulator may still mark an Applin
        # played on the preceding own turn as new.  Promotion is legal now and
        # the marker clears before the next own turn, when evolution occurs.
        or candidate.appear_this_turn and not promotion_is_between_turns
    ):
        return 0
    if _fixed_promotion_attack_route(
        view,
        memory,
        candidate=candidate,
        festival_active=festival_active,
        hand=hand,
        discard=discard,
        card_counts=card_counts,
        deck_zone=CardZone.DECK_MIN,
        future_turn=promotion_is_between_turns,
    ):
        return 2
    uncertain_components: list[CardId] = []
    if (
        hand[int(CardId.DIPPLIN)] <= 0
        and discard[int(CardId.DIPPLIN)] <= 0
    ):
        uncertain_components.append(CardId.DIPPLIN)
    if (
        not _pokemon_has_grass(candidate)
        and hand[int(CardId.BASIC_GRASS)] <= 0
        and discard[int(CardId.BASIC_GRASS)] <= 0
    ):
        uncertain_components.append(CardId.BASIC_GRASS)
    components_can_coexist = _component_world_can_coexist(
        view,
        card_counts=card_counts,
        required=tuple(uncertain_components),
    )
    if components_can_coexist and _fixed_promotion_attack_route(
        view,
        memory,
        candidate=candidate,
        festival_active=festival_active,
        hand=hand,
        discard=discard,
        card_counts=card_counts,
        deck_zone=CardZone.DECK_MAX,
        future_turn=promotion_is_between_turns,
    ):
        return 1
    if not components_can_coexist:
        return 0
    return int(_contingent_promotion_attack_route(
        memory,
        candidate=candidate,
        hand=hand,
        card_counts=card_counts,
    ))


def _next_turn_attack_route(
    view: GameView,
    memory: CompiledMemory,
    *,
    current_attacker: PokemonRef | None,
    hand: Counter[int],
    discard: Counter[int],
    legal_play: Counter[int],
    card_counts: dict[tuple[CardZone, int], int],
) -> int:
    """Classify the fixed T+1 attacker component table.

    This deliberately answers only whether today's public resources already
    guarantee tomorrow's Dipplin attack.  Chance cards such as Bug Catching
    Set and Lillie's Determination are not a guarantee; the policy may use
    them only when this label is zero.
    """

    # From T2 onward, classify the backup only after today's Dipplin attack is
    # already legal.  Before that point, evolution cards, Grass Energy, search
    # activations, and the attachment may still be consumed by the current
    # attacker.  Treating those same components as T+1 resources would count a
    # single card twice.  The fixed policy reevaluates this label after every
    # deterministic preparation action, so no guaranteed backup route is lost.
    if (
        view.is_own_turn
        and view.own_turn_number >= 2
        and not _has_attack(view.options, AttackId.DIPPLIN_DO_THE_WAVE)
    ):
        return 0

    # Reserve one physical line for today's attack before classifying T+1.
    # The line may currently be on the Bench behind Budew: the fixed policy
    # can evolve/switch it and consume it this turn.  Counting that same
    # Pokemon as tomorrow's backup produced a false guarantee after promotion.
    # Turn one is the exception because every Applin is being prepared for T2.
    front_attack_line: PokemonRef | None = None
    if view.is_own_turn and view.own_turn_number >= 2:
        active = view.own_active
        if current_attacker is not None:
            front_attack_line = current_attacker
        elif (
            active is not None
            and active.id == int(CardId.APPLIN)
            and not active.appear_this_turn
        ):
            front_attack_line = active
        else:
            mature_applins = tuple(
                pokemon
                for pokemon in view.own_field
                if pokemon.id == int(CardId.APPLIN)
                and not pokemon.appear_this_turn
            )
            if mature_applins:
                front_attack_line = min(
                    mature_applins,
                    key=_stable_pokemon_order,
                )
    candidates = tuple(
        pokemon
        for pokemon in view.own_field
        if pokemon.id in (int(CardId.APPLIN), int(CardId.DIPPLIN))
        and not (
            memory.first_attack_source_serial is not None
            and pokemon.serial is not None
            and int(pokemon.serial) == int(memory.first_attack_source_serial)
        )
        and (
            front_attack_line is None
            or not _same_pokemon(pokemon, front_attack_line)
        )
    )
    if not candidates:
        return 0

    # When Festival Grounds must be played to unlock today's attack, that
    # physical copy cannot also be retained as tomorrow's Stadium guarantee.
    # Reserve it before evaluating the T+1 component table.  A second copy in
    # hand remains a valid answer to an opponent replacing the Stadium.
    future_hand = hand.copy()
    if (
        view.is_own_turn
        and view.own_turn_number >= 2
        and int(CardId.FESTIVAL_GROUNDS) not in view.public_stadium_ids
        and legal_play[int(CardId.FESTIVAL_GROUNDS)] > 0
        and future_hand[int(CardId.FESTIVAL_GROUNDS)] > 0
    ):
        future_hand[int(CardId.FESTIVAL_GROUNDS)] -= 1

    front_attacker_is_active = bool(
        front_attack_line is not None
        and view.own_active is not None
        and _same_pokemon(front_attack_line, view.own_active)
    )
    for candidate in candidates:
        committed_energy_retreat = _committed_t1_energy_retreat_route(
            view,
            candidate=candidate,
        )
        # From T2 onward, an Applin still left unevolved is not a guaranteed
        # T+1 attacker.  Its evolution/search/recovery components must remain
        # in hand through the opponent's turn and can be removed by disruption.
        # Any deterministic main-phase route is materialized by earlier fixed
        # rows; if the line remains Applin, classify it as provisional so the
        # preparation table continues.  T1 keeps its opening component table.
        if (
            view.is_own_turn
            and view.own_turn_number >= 2
            and (
                candidate.id == int(CardId.APPLIN)
                or not _pokemon_has_grass(candidate)
            )
        ):
            continue
        if (
            (
                # The continuation contract is evaluated for the branch where
                # today's front Dipplin is Knocked Out.  Its replacement is
                # promoted between turns and therefore pays no retreat cost.
                front_attacker_is_active
                or _fixed_next_turn_pivot_route(
                    view,
                    candidate=candidate,
                    hand=future_hand,
                )
            )
            and _fixed_promotion_attack_route(
            view,
            memory,
            candidate=candidate,
            # A Stadium already in play may be replaced before T+1.  Only a
            # Festival Grounds retained in hand is a guaranteed future route.
            festival_active=False,
            hand=future_hand,
            discard=discard,
            card_counts=card_counts,
            deck_zone=CardZone.DECK_MIN,
            future_turn=True,
            require_evolution=candidate.id == int(CardId.APPLIN),
            supporter_available=True,
            attachment_available=True,
            # When T1 Grass has already been committed to the opening Grookey,
            # that Energy guarantees next turn's retreat.  After promotion the
            # same Grookey can evolve and fetch the replacement Grass.  This is
            # the precompiled last-resort route, so it does not additionally
            # require Festival Grounds.
            require_festival_for_thwackey_energy=not committed_energy_retreat,
            )
        ):
            return 1
    return 0


def _committed_t1_energy_retreat_route(
    view: GameView,
    *,
    candidate: PokemonRef,
) -> bool:
    """Recognize the post-attachment half of the fixed T1 pivot pattern."""

    active = view.own_active
    return bool(
        view.is_own_turn
        and view.own_turn_number == 1
        and active is not None
        and active.id == int(CardId.GROOKEY)
        and candidate.id == int(CardId.APPLIN)
        and not _same_pokemon(active, candidate)
        and _pokemon_has_grass(active)
        and _retreat_cost(view, active) in (0, 1)
    )


def _next_attack_preparation_class(
    view: GameView,
    memory: CompiledMemory,
    *,
    current_attacker: PokemonRef | None,
    festival_active: bool,
    hand: Counter[int],
    discard: Counter[int],
    card_counts: dict[tuple[CardZone, int], int],
) -> int:
    """Classify the precompiled T+1 preparation table.

    ``2`` means that the next attacker can be completed from exact public
    components after the between-turn promotion, including an Applin played
    this turn. ``1`` is a declared contingent route and ``0`` means that a
    component is still missing.  This is a finite component-table lookup; it
    never explores actions during a match.
    """

    if (
        view.is_own_turn
        and view.own_turn_number >= 2
        and not _has_attack(view.options, AttackId.DIPPLIN_DO_THE_WAVE)
    ):
        return 0

    candidates = tuple(
        pokemon
        for pokemon in view.own_field
        if pokemon.id in (int(CardId.APPLIN), int(CardId.DIPPLIN))
        and (
            current_attacker is None
            or not _same_pokemon(pokemon, current_attacker)
        )
        and not (
            memory.first_attack_source_serial is not None
            and pokemon.serial is not None
            and int(pokemon.serial) == int(memory.first_attack_source_serial)
        )
    )
    contingent = 0
    for candidate in candidates:
        require_evolution = candidate.id == int(CardId.APPLIN)
        if _fixed_promotion_attack_route(
            view,
            memory,
            candidate=candidate,
            # An opposing Stadium can replace the current Festival Grounds
            # between turns.  Class 2 therefore counts only a held replacement
            # (or a route that does not need Drum Beat at all) as fixed.
            festival_active=False,
            hand=hand,
            discard=discard,
            card_counts=card_counts,
            deck_zone=CardZone.DECK_MIN,
            future_turn=True,
            require_evolution=require_evolution,
            supporter_available=True,
            attachment_available=True,
        ):
            return 2
        if _fixed_promotion_attack_route(
            view,
            memory,
            candidate=candidate,
            festival_active=festival_active,
            hand=hand,
            discard=discard,
            card_counts=card_counts,
            deck_zone=CardZone.DECK_MAX,
            future_turn=True,
            require_evolution=require_evolution,
            supporter_available=True,
            attachment_available=True,
        ) or _contingent_promotion_attack_route(
            memory,
            candidate=candidate,
            hand=hand,
            card_counts=card_counts,
        ):
            contingent = 1
    return contingent


def _fixed_next_turn_pivot_route(
    view: GameView,
    *,
    candidate: PokemonRef,
    hand: Counter[int],
) -> bool:
    """Require a fixed way to put a Bench attacker Active on T+1."""

    active = view.own_active
    if active is None or _same_pokemon(active, candidate):
        return True
    retreat_cost = _retreat_cost(view, active)
    if retreat_cost <= 0:
        return True
    attached_units = max(len(active.energy_card_ids), len(active.energies))
    if attached_units >= retreat_cost:
        return True
    return bool(
        not active.tool_ids
        and retreat_cost <= 2
        and hand[int(CardId.AIR_BALLOON)] > 0
    )


def _component_world_can_coexist(
    view: GameView,
    *,
    card_counts: dict[tuple[CardZone, int], int],
    required: tuple[CardId, ...],
) -> bool:
    """Reject marginal DECK_MAX combinations that cannot share one deck."""

    missing = sum(
        card_counts[(CardZone.DECK_MIN, int(card_id))] <= 0
        and card_counts[(CardZone.DECK_MAX, int(card_id))] > 0
        for card_id in required
    )
    return missing <= max(0, int(view.own.get("deckCount", 0)))


def _fixed_promotion_attack_route(
    view: GameView,
    memory: CompiledMemory,
    *,
    candidate: PokemonRef,
    festival_active: bool,
    hand: Counter[int],
    discard: Counter[int],
    card_counts: dict[tuple[CardZone, int], int],
    deck_zone: CardZone,
    future_turn: bool = False,
    require_evolution: bool = True,
    supporter_available: bool | None = None,
    attachment_available: bool | None = None,
    require_festival_for_thwackey_energy: bool = True,
) -> bool:
    """Look up the finite exact-resource component table for one promotion."""

    def deck_has(card_id: CardId) -> bool:
        return card_counts[(deck_zone, int(card_id))] > 0

    supporter = bool(
        future_turn or memory.supporter_available
        if supporter_available is None
        else supporter_available
    )
    attachment = bool(
        future_turn or memory.attachment_available
        if attachment_available is None
        else attachment_available
    )
    mature_grookey = any(
        pokemon.id == int(CardId.GROOKEY)
        and (future_turn or not pokemon.appear_this_turn)
        for pokemon in view.own_field
    )
    festival_access = bool(
        festival_active or hand[int(CardId.FESTIVAL_GROUNDS)] > 0
    )
    evolution_in_hand = bool(
        not require_evolution or hand[int(CardId.DIPPLIN)] > 0
    )
    evolution_by_pad = hand[int(CardId.POKE_PAD)] > 0 and deck_has(CardId.DIPPLIN)
    evolution_by_brock = bool(
        supporter
        and hand[int(CardId.BROCKS_SCOUTING)] > 0
        and deck_has(CardId.DIPPLIN)
    )
    evolution_by_stretcher = bool(
        hand[int(CardId.NIGHT_STRETCHER)] > 0
        and discard[int(CardId.DIPPLIN)] > 0
    )
    evolution_by_lana = bool(
        supporter
        and hand[int(CardId.LANAS_AID)] > 0
        and discard[int(CardId.DIPPLIN)] > 0
    )

    energy_immediate = bool(
        _pokemon_has_grass(candidate)
        or attachment and hand[int(CardId.BASIC_GRASS)] > 0
    )
    thwackey_energy_base = bool(
        attachment
        and (
            festival_access
            or not require_festival_for_thwackey_energy
        )
        and deck_has(CardId.BASIC_GRASS)
    )
    energy_by_existing_thwackey = bool(
        thwackey_energy_base
        and (
            memory.unused_thwackey_serials
            or future_turn
            and any(
                pokemon.id == int(CardId.THWACKEY)
                for pokemon in view.own_field
            )
        )
    )
    energy_by_hand_thwackey = bool(
        thwackey_energy_base
        and mature_grookey
        and hand[int(CardId.THWACKEY)] > 0
    )
    energy_by_pad_thwackey = bool(
        thwackey_energy_base
        and mature_grookey
        and hand[int(CardId.POKE_PAD)] > 0
        and deck_has(CardId.THWACKEY)
    )
    energy_by_stretcher_thwackey = bool(
        thwackey_energy_base
        and mature_grookey
        and hand[int(CardId.NIGHT_STRETCHER)] > 0
        and discard[int(CardId.THWACKEY)] > 0
    )
    energy_by_brock_thwackey = bool(
        thwackey_energy_base
        and mature_grookey
        and supporter
        and hand[int(CardId.BROCKS_SCOUTING)] > 0
        and deck_has(CardId.THWACKEY)
    )
    energy_by_stretcher = bool(
        attachment
        and hand[int(CardId.NIGHT_STRETCHER)] > 0
        and discard[int(CardId.BASIC_GRASS)] > 0
    )
    energy_by_lana = bool(
        attachment
        and supporter
        and hand[int(CardId.LANAS_AID)] > 0
        and discard[int(CardId.BASIC_GRASS)] > 0
    )
    existing_thwackey_count = (
        sum(
            pokemon.id == int(CardId.THWACKEY)
            for pokemon in view.own_field
        )
        if future_turn
        else len(memory.unused_thwackey_serials)
    )
    evolution_by_existing_thwackey = bool(
        require_evolution
        and festival_access
        and existing_thwackey_count > 0
        and deck_has(CardId.DIPPLIN)
    )
    evolution_by_new_thwackey = bool(
        require_evolution
        and festival_access
        and mature_grookey
        and deck_has(CardId.DIPPLIN)
        and (
            hand[int(CardId.THWACKEY)] > 0
            or hand[int(CardId.POKE_PAD)] > 0
            and deck_has(CardId.THWACKEY)
            or hand[int(CardId.NIGHT_STRETCHER)] > 0
            and discard[int(CardId.THWACKEY)] > 0
            or supporter
            and hand[int(CardId.BROCKS_SCOUTING)] > 0
            and deck_has(CardId.THWACKEY)
        )
    )
    resource_free_energy = bool(
        energy_immediate
        or energy_by_existing_thwackey
        or energy_by_hand_thwackey
    )

    direct_route = evolution_in_hand and (
        resource_free_energy
        or energy_by_pad_thwackey
        or energy_by_stretcher_thwackey
        or energy_by_brock_thwackey
        or energy_by_stretcher
        or energy_by_lana
    )
    poke_pad_route = evolution_by_pad and (
        resource_free_energy
        or (hand[int(CardId.POKE_PAD)] > 1 and energy_by_pad_thwackey)
        or energy_by_stretcher_thwackey
        or energy_by_brock_thwackey
        or energy_by_stretcher
        or energy_by_lana
    )
    brock_route = evolution_by_brock and (
        resource_free_energy
        or energy_by_pad_thwackey
        or energy_by_stretcher_thwackey
        or energy_by_stretcher
    )
    stretcher_route = evolution_by_stretcher and (
        resource_free_energy
        or energy_by_pad_thwackey
        or energy_by_brock_thwackey
        or energy_by_lana
    )
    lana_route = evolution_by_lana and (
        resource_free_energy
        or energy_by_pad_thwackey
        or energy_by_stretcher_thwackey
        or energy_by_stretcher
        or energy_by_lana
    )
    thwackey_evolution_route = bool(
        evolution_by_existing_thwackey
        and (
            energy_immediate
            or energy_by_stretcher
            or energy_by_lana
            or thwackey_energy_base
            and existing_thwackey_count >= 2
            or energy_by_hand_thwackey
            or energy_by_pad_thwackey
            or energy_by_stretcher_thwackey
            or energy_by_brock_thwackey
        )
        or evolution_by_new_thwackey
        and (
            energy_immediate
            or existing_thwackey_count > 0
            and thwackey_energy_base
        )
    )
    return bool(
        direct_route
        or poke_pad_route
        or brock_route
        or stretcher_route
        or lana_route
        or thwackey_evolution_route
    )


def _contingent_promotion_attack_route(
    memory: CompiledMemory,
    *,
    candidate: PokemonRef,
    hand: Counter[int],
    card_counts: dict[tuple[CardZone, int], int],
) -> bool:
    """Recognize predeclared chance routes without evaluating their outcomes."""

    possible_evolution = bool(
        hand[int(CardId.DIPPLIN)] > 0
        or card_counts[(CardZone.DECK_MAX, int(CardId.DIPPLIN))] > 0
    )
    possible_energy = bool(
        _pokemon_has_grass(candidate)
        or memory.attachment_available
        and (
            hand[int(CardId.BASIC_GRASS)] > 0
            or card_counts[(CardZone.DECK_MAX, int(CardId.BASIC_GRASS))] > 0
        )
    )
    if not (possible_evolution and possible_energy):
        return False
    if hand[int(CardId.BUG_CATCHING_SET)] > 0:
        return True
    return bool(
        memory.supporter_available
        and (
            hand[int(CardId.LILLIES_DETERMINATION)] > 0
            or hand[int(CardId.JUDGE)] > 0
        )
    )


def _damage_features(
    view: GameView,
    memory: CompiledMemory,
    *,
    active: PokemonRef | None,
    opponent: PokemonRef | None,
    festival_active: bool,
) -> dict[str, int]:
    empty = {
        "hit_count": 0,
        "current": 0,
        "ko_now": 0,
        "ko_festival": 0,
        "ko_bangle": 0,
        "ko_kieran": 0,
        "ko_black_belt": 0,
        "ko_bench": 0,
        "ko_two_bench": 0,
        "ko_full_bench": 0,
        "gain_festival": 0,
        "gain_bangle": 0,
        "gain_kieran": 0,
        "gain_black_belt": 0,
        "gain_bench": 0,
        "koable_bench": 0,
        "active_prizes": 0,
        "best_boss_prizes": 0,
    }
    if (
        active is None
        or active.id != int(CardId.DIPPLIN)
        or opponent is None
    ):
        return empty
    opponent_meta = view.catalog.card(opponent.id)
    target_ex = bool(
        opponent_meta is not None
        and (opponent_meta.ex or opponent_meta.mega_ex)
    )
    grass_weak = bool(
        opponent_meta is not None
        and opponent_meta.weakness == int(EnergyType.GRASS)
    )
    bangle = int(CardId.BRAVE_BANGLE) in active.tool_ids
    support = {
        1: DamageSupport.KIERAN,
        2: DamageSupport.BLACK_BELT,
    }.get(int(memory.damage_support), DamageSupport.NONE)
    # After the first Festival Lead hit resolves, only one attack remains this
    # turn.  Damage and KO predicates must describe that remaining hit rather
    # than reusing the original two-hit budget.
    hit_count = 1 if memory.first_hit_resolved else (2 if festival_active else 1)
    bench_count = min(5, len(view.own_bench))

    def value(
        *,
        hits: int = hit_count,
        benches: int = bench_count,
        use_bangle: bool = bangle,
        use_support: DamageSupport = support,
        is_ex: bool = target_ex,
        weak: bool = grass_weak,
    ) -> int:
        return lookup_damage(DamagePatternKey(
            bench_count=max(0, min(5, int(benches))),
            target_ex=bool(is_ex),
            grass_weakness=bool(weak),
            brave_bangle=bool(use_bangle),
            support=use_support,
            hit_count=1 if int(hits) <= 1 else 2,
        ))

    current = value()
    festival = value(hits=2)
    with_bangle = value(use_bangle=True)
    with_kieran = value(use_support=DamageSupport.KIERAN)
    black_belt_active = int(view.own_prize_count) > len(
        view.opponent.get("prize") or ()
    )
    with_black_belt = (
        value(use_support=DamageSupport.BLACK_BELT)
        if black_belt_active
        else current
    )
    with_bench = value(benches=min(5, bench_count + 1))
    with_two_bench = value(benches=min(5, bench_count + 2))
    with_full_bench = value(benches=5)
    hp = max(0, int(opponent.hp))
    koable_bench = 0
    best_boss_prizes = 0
    for target in view.opponent_bench:
        meta = view.catalog.card(target.id)
        projected = value(
            is_ex=bool(meta is not None and (meta.ex or meta.mega_ex)),
            weak=bool(
                meta is not None and meta.weakness == int(EnergyType.GRASS)
            ),
        )
        if projected >= max(0, int(target.hp)):
            koable_bench += 1
            best_boss_prizes = max(
                best_boss_prizes,
                1 if meta is None else int(meta.prize_value),
            )
    return {
        "hit_count": hit_count,
        "current": current,
        "ko_now": int(current >= hp),
        "ko_festival": int(festival >= hp),
        "ko_bangle": int(with_bangle >= hp),
        "ko_kieran": int(with_kieran >= hp),
        "ko_black_belt": int(with_black_belt >= hp),
        "ko_bench": int(with_bench >= hp),
        "ko_two_bench": int(with_two_bench >= hp),
        "ko_full_bench": int(with_full_bench >= hp),
        "gain_festival": int(festival > current),
        "gain_bangle": int(with_bangle > current),
        "gain_kieran": int(with_kieran > current),
        "gain_black_belt": int(with_black_belt > current),
        "gain_bench": int(with_bench > current),
        "koable_bench": koable_bench,
        "active_prizes": 1 if opponent_meta is None else int(opponent_meta.prize_value),
        "best_boss_prizes": best_boss_prizes,
    }


def _ko_chain_target(view: GameView, target: PokemonRef) -> KoTarget:
    meta = view.catalog.card(target.id)
    hp = max(10, min(400, ((int(target.hp) + 9) // 10) * 10))
    return KoTarget(
        hp=hp,
        prizes=1 if meta is None else int(meta.prize_value),
        target_ex=bool(meta is not None and (meta.ex or meta.mega_ex)),
        grass_weakness=bool(
            meta is not None and meta.weakness == int(EnergyType.GRASS)
        ),
    )


def _attacker_order(pokemon: PokemonRef) -> tuple[int, int, int, int, int]:
    return (
        0 if _dipplin_has_energy(pokemon) else 1,
        -int(pokemon.hp),
        int(pokemon.appear_this_turn),
        int(pokemon.area or 0),
        _serial_order(pokemon.serial),
    )


def _stable_pokemon_order(pokemon: PokemonRef) -> tuple[int, int, int, int]:
    return (
        int(pokemon.appear_this_turn),
        -int(pokemon.hp),
        int(pokemon.area or 0),
        _serial_order(pokemon.serial),
    )


def _serial_order(serial: int | None) -> int:
    return 2**31 - 1 if serial is None else int(serial)


def _same_pokemon(first: PokemonRef, second: PokemonRef) -> bool:
    if first.serial is not None and second.serial is not None:
        return int(first.serial) == int(second.serial)
    return (
        int(first.area or -1),
        int(first.index or 0),
        int(first.id),
    ) == (
        int(second.area or -1),
        int(second.index or 0),
        int(second.id),
    )


def _dipplin_has_energy(pokemon: PokemonRef) -> int:
    return int(_pokemon_has_grass(pokemon))


def _pokemon_has_grass(pokemon: PokemonRef) -> bool:
    return pokemon.has_energy_type(
        int(EnergyType.GRASS),
        compatible_card_ids=(int(CardId.BASIC_GRASS),),
    )


def _legal_evolution_target_count(
    options: tuple[LegalOption, ...],
    evolution_id: CardId,
    base_id: CardId,
) -> int:
    targets = {
        option.target.serial
        for option in options
        if (
            int(option.type) == int(OptionType.EVOLVE)
            and option.card_id == int(evolution_id)
            and option.target is not None
            and option.target.id == int(base_id)
        )
    }
    return len(targets)


def _has_attack(options: tuple[LegalOption, ...], attack_id: AttackId) -> bool:
    return any(
        int(option.type) == int(OptionType.ATTACK)
        and option.attack_id == int(attack_id)
        for option in options
    )


def _has_option(options: tuple[LegalOption, ...], option_type: OptionType) -> bool:
    return any(int(option.type) == int(option_type) for option in options)


def _has_attach_target(
    options: tuple[LegalOption, ...],
    card_id: CardId,
    target: PokemonRef | None,
) -> bool:
    if target is None:
        return False
    return any(
        option.card_id == int(card_id)
        and int(option.type) in (int(OptionType.PLAY), int(OptionType.ATTACH))
        and option.target is not None
        and _same_pokemon(option.target, target)
        for option in options
    )


def _effect_card_id(view: GameView) -> int:
    effect = view.select.get("effect")
    if not isinstance(effect, dict):
        return 0
    raw = effect.get("id", effect.get("cardId", 0))
    return 0 if raw is None else int(raw)
