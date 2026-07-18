from __future__ import annotations

from cards import CardId
from memory import card_may_be_in_deck
from model import OptionType, SelectContext, SelectType
from proposals import PendingIntent, Proposal, covers
from rules.attack import can_hand_power_ko
from rules.board_plan import (
    MINIMUM_ATTACK_LINES,
    OPENING_PIVOT_SEARCH_PRIORITY,
    attack_line_count,
    available_bench_slots,
    is_opening_attack_phase,
    needs_attack_line_setup,
    reserve_abra_needs_kadabra,
)
from rules.continuity import (
    ATTACK_LINE_MATURITY_PRIORITY,
    ATTACK_LINE_SUPPORT_PRIORITY,
    CONTINUITY_MATURITY_SEARCH_PRIORITY,
    CONTINUITY_SUPPORT_SEARCH_PRIORITY,
    CURRENT_AND_RESERVE_EVOLUTION_SEARCH_PRIORITY,
    needs_continuity_setup,
    nonfinal_immediate_ko,
    search_preserves_immediate_ko,
    spend_preserves_immediate_ko,
)
from rules.draw_engine import legal_rich_attach_options
from rules.deck_safety import max_safe_deck_removals
from rules.poke_pad import must_reserve_future_alakazam_search


_ATTACKER_IDS = frozenset(
    {
        int(CardId.ABRA),
        int(CardId.KADABRA),
        int(CardId.ALAKAZAM),
    }
)
_ATTACK_PSYCHIC_IDS = frozenset(
    {
        int(CardId.BASIC_PSYCHIC),
        int(CardId.TELEPATH_PSYCHIC_ENERGY),
    }
)
_DRAW_EVOLUTION_IDS = frozenset(
    {
        int(CardId.DUDUNSPARCE),
        int(CardId.KADABRA),
        int(CardId.ALAKAZAM),
    }
)
_ONE_RETREAT_IDS = frozenset(
    {
        int(CardId.ABRA),
        int(CardId.KADABRA),
        int(CardId.ALAKAZAM),
        int(CardId.DUNSPARCE),
        int(CardId.FAN_ROTOM),
        int(CardId.GENESECT),
        int(CardId.SHAYMIN),
        int(CardId.PSYDUCK),
        int(CardId.FEZANDIPITI_EX),
    }
)


def _is_main_selection(view) -> bool:
    return (
        int(view.select.get("type", -1)) == int(SelectType.MAIN)
        and int(view.select.get("context", -1)) == int(SelectContext.MAIN)
    )


def _field_count(view, card_id: int) -> int:
    return sum(int(pokemon.id) == int(card_id) for pokemon in view.field)


def _hand_count(view, card_id: int) -> int:
    return sum(int(hand_id) == int(card_id) for hand_id in view.hand_ids)


def _visible_count(view, card_id: int) -> int:
    return _field_count(view, card_id) + _hand_count(view, card_id)


def _old_field_count(view, card_id: int) -> int:
    return sum(
        int(pokemon.id) == int(card_id) and not pokemon.appear_this_turn
        for pokemon in view.field
    )


def _option_hand_index(option) -> int:
    index = option.raw.get("index")
    return option.position if index is None else int(index)


def _support_option(view, card_id: int):
    return min(
        (
            option
            for option in view.options
            if option.type == int(OptionType.PLAY)
            and option.card_id == int(card_id)
            and option.card_serial is not None
        ),
        key=lambda option: (
            _option_hand_index(option),
            int(option.card_serial),
            option.position,
        ),
        default=None,
    )


def _air_balloon_can_attach_to_active(view) -> bool:
    active = view.active
    return active is not None and any(
        option.type == int(OptionType.ATTACH)
        and option.card_id == int(CardId.AIR_BALLOON)
        and option.target is not None
        and option.target.serial == active.serial
        for option in view.options
    )


def _opening_powered_lines_need_basic_pivot(
    view,
    memory,
    route_candidates,
) -> bool:
    """超付きのベンチ攻撃系統とは別に、前を逃がす基本超が必要か。"""
    active = view.active
    candidate_serials = {
        pokemon.serial
        for pokemon in route_candidates
        if pokemon is not None
        and pokemon.serial is not None
        and view.has_psychic_energy(pokemon)
    }
    if (
        not is_opening_attack_phase(view)
        or active is None
        or int(active.id) not in _ONE_RETREAT_IDS
        or not any(
            pokemon.serial in candidate_serials
            for pokemon in view.bench
        )
        or _hand_count(view, CardId.BASIC_PSYCHIC) > 0
        or not card_may_be_in_deck(
            view,
            memory,
            CardId.BASIC_PSYCHIC,
        )
        or _air_balloon_can_attach_to_active(view)
        or any(
            option.type == int(OptionType.RETREAT)
            for option in view.options
        )
    ):
        return False
    return not any(
        option.type == int(OptionType.EVOLVE)
        and option.card_id == int(CardId.DUDUNSPARCE)
        and option.target is not None
        and option.target.serial == active.serial
        for option in view.options
    )


def _opening_active_dunsparce_needs_evolution_pivot(view, memory) -> bool:
    """初回攻撃用フーディンがベンチで待つ時、前のノコッチ進化が必要か。"""
    active = view.active
    if (
        not is_opening_attack_phase(view)
        or active is None
        or int(active.id) != int(CardId.DUNSPARCE)
        or active.appear_this_turn
        or not any(
            int(pokemon.id) == int(CardId.ALAKAZAM)
            and view.has_psychic_energy(pokemon)
            for pokemon in view.bench
        )
        or _hand_count(view, CardId.DUDUNSPARCE) > 0
        or not card_may_be_in_deck(view, memory, CardId.DUDUNSPARCE)
        or _air_balloon_can_attach_to_active(view)
        or any(
            option.type == int(OptionType.RETREAT)
            for option in view.options
        )
    ):
        return False
    return not any(
        option.type == int(OptionType.EVOLVE)
        and option.card_id == int(CardId.DUDUNSPARCE)
        and option.target is not None
        and option.target.serial == active.serial
        for option in view.options
    )


def _has_play_option(view, card_id: int) -> bool:
    return any(
        option.type == int(OptionType.PLAY)
        and option.card_id == int(card_id)
        for option in view.options
    )


def _attacker_sort_key(pokemon) -> tuple[int, int, int]:
    return (
        10**9 if pokemon.serial is None else int(pokemon.serial),
        10**9 if pokemon.area is None else int(pokemon.area),
        10**9 if pokemon.index is None else int(pokemon.index),
    )


def _planned_attacker(view, memory, candidates):
    candidates = tuple(candidates)
    for serial in (
        memory.reserved_attacker_serial,
        memory.protected_abra_serial,
    ):
        if serial is None:
            continue
        remembered = next(
            (
                pokemon
                for pokemon in candidates
                if pokemon.serial == int(serial)
            ),
            None,
        )
        if remembered is not None:
            return remembered

    powered = tuple(
        pokemon
        for pokemon in candidates
        if view.has_psychic_energy(pokemon)
    )
    return min(powered or candidates, key=_attacker_sort_key, default=None)


def _attacking_psychic_secured(view, memory, candidates) -> bool:
    if any(
        int(card_id) in _ATTACK_PSYCHIC_IDS
        for card_id in view.hand_ids
    ):
        return True
    target = _planned_attacker(view, memory, candidates)
    return target is not None and view.has_psychic_energy(target)


def _support_search_preserves_immediate_ko(view, memory, groups) -> bool:
    """各検索カテゴリで公開情報上1枚以上取れる数を、解決後の手札へ反映する。"""
    cards_added = sum(
        any(card_may_be_in_deck(view, memory, card_id) for card_id in group)
        for group in groups
    )
    return search_preserves_immediate_ko(view, cards_added)


def _attack_route(view, memory) -> tuple[object | None, bool, bool]:
    """次にevolution規則が選ぶ攻撃役と同じ個体を返す。"""
    active = view.active
    if active is not None and int(active.id) == int(CardId.ALAKAZAM):
        return (active, False, False)

    powered_candy_route_exists = (
        int(CardId.RARE_CANDY) in view.hand_ids
        and any(
            view.has_psychic_energy(pokemon)
            for pokemon in view.eligible_abras
        )
    )
    trapped_active_kadabra = (
        active is not None
        and int(active.id) == int(CardId.KADABRA)
        and not active.appear_this_turn
        and not powered_candy_route_exists
        and not any(
            option.type == int(OptionType.RETREAT)
            for option in view.options
        )
    )
    if trapped_active_kadabra:
        return (
            active,
            _hand_count(view, CardId.ALAKAZAM) == 0,
            False,
        )

    field_alakazam = min(
        (
            pokemon
            for pokemon in view.field
            if int(pokemon.id) == int(CardId.ALAKAZAM)
        ),
        key=lambda pokemon: (
            0 if view.has_psychic_energy(pokemon) else 1,
            *_attacker_sort_key(pokemon),
        ),
        default=None,
    )
    if field_alakazam is not None:
        return (field_alakazam, False, False)

    old_kadabras = tuple(
        pokemon
        for pokemon in view.field
        if int(pokemon.id) == int(CardId.KADABRA)
        and not pokemon.appear_this_turn
    )
    eligible_abras = tuple(view.eligible_abras)
    candy_available = (
        int(CardId.RARE_CANDY) in view.hand_ids and bool(eligible_abras)
    )
    old_target = min(
        old_kadabras,
        key=lambda pokemon: (
            0 if view.has_psychic_energy(pokemon) else 1,
            0 if pokemon.serial == memory.reserved_attacker_serial else 1,
            *_attacker_sort_key(pokemon),
        ),
        default=None,
    )
    powered_abras = tuple(
        pokemon for pokemon in eligible_abras if view.has_psychic_energy(pokemon)
    )
    candy_target = min(
        powered_abras or eligible_abras,
        key=_attacker_sort_key,
        default=None,
    )
    needs_alakazam = _hand_count(view, CardId.ALAKAZAM) == 0

    if old_target is not None:
        candy_is_immediate = (
            candy_available
            and candy_target is not None
            and view.has_psychic_energy(candy_target)
        )
        if not view.has_psychic_energy(old_target) and candy_is_immediate:
            return (candy_target, needs_alakazam, True)
        return (old_target, needs_alakazam, False)
    if candy_available:
        return (candy_target, needs_alakazam, True)
    return (None, False, False)


def _fallback_attack_candidates(view) -> tuple:
    return tuple(
        pokemon
        for pokemon in view.field
        if int(pokemon.id) in _ATTACKER_IDS
    )


def _missing_dudunsparce(view) -> bool:
    return _old_field_count(view, CardId.DUNSPARCE) > _hand_count(
        view, CardId.DUDUNSPARCE
    )


def _field_attack_line_is_empty(view) -> bool:
    return all(
        _field_count(view, card_id) == 0
        for card_id in (CardId.ABRA, CardId.KADABRA, CardId.ALAKAZAM)
    )


def _has_obvious_immediate_draw(view, memory) -> bool:
    if legal_rich_attach_options(view, memory):
        return True
    for option in view.options:
        if (
            option.type in (int(OptionType.ABILITY), int(OptionType.SKILL))
            and option.card_id == int(CardId.FEZANDIPITI_EX)
        ):
            return True
        if (
            option.type == int(OptionType.ABILITY)
            and option.card_id == int(CardId.DUDUNSPARCE)
            and option.source is not None
            and view.field_count_after_return(option.source.serial) >= 2
        ):
            return True
        if (
            option.type == int(OptionType.EVOLVE)
            and option.card_id in _DRAW_EVOLUTION_IDS
        ):
            return True
        if (
            option.type == int(OptionType.PLAY)
            and option.card_id == int(CardId.RARE_CANDY)
        ):
            return True
    return False


def _task4_has_priority(view, memory) -> bool:
    poke_pad = _has_play_option(view, CardId.POKE_PAD)
    if (
        poke_pad
        and _missing_dudunsparce(view)
        and card_may_be_in_deck(view, memory, CardId.DUDUNSPARCE)
    ):
        return True
    if _field_count(view, CardId.ABRA) != 0:
        return False
    direct_abra = _has_play_option(view, CardId.ABRA)
    searchable_abra = card_may_be_in_deck(view, memory, CardId.ABRA)
    return direct_abra or searchable_abra and (
        poke_pad or _has_play_option(view, CardId.BUDDY_BUDDY_POFFIN)
    )


def _evolution_priority(
    view,
    *,
    force_missing_alakazam: bool = False,
) -> tuple[int, ...]:
    priority: list[int] = []

    def add(card_id: int) -> None:
        value = int(card_id)
        if value not in priority:
            priority.append(value)

    if force_missing_alakazam and _hand_count(view, CardId.ALAKAZAM) == 0:
        add(CardId.ALAKAZAM)
    if _missing_dudunsparce(view):
        add(CardId.DUDUNSPARCE)
    if len(view.eligible_abras) > _hand_count(view, CardId.KADABRA):
        add(CardId.KADABRA)
    if _old_field_count(view, CardId.KADABRA) > _hand_count(view, CardId.ALAKAZAM):
        add(CardId.ALAKAZAM)

    for fallback in (CardId.KADABRA, CardId.DUDUNSPARCE, CardId.ALAKAZAM):
        add(fallback)
    return tuple(priority)


def _dawn_groups(view) -> tuple[tuple[int, ...], ...]:
    basics: list[int] = []

    def add_basic(card_id: int) -> None:
        value = int(card_id)
        if value not in basics:
            basics.append(value)

    if _visible_count(view, CardId.ABRA) < 3:
        add_basic(CardId.ABRA)
    if _visible_count(view, CardId.DUNSPARCE) < 3:
        add_basic(CardId.DUNSPARCE)
    add_basic(CardId.ABRA)
    add_basic(CardId.DUNSPARCE)

    needs_turn_three_kadabra = (
        view.own_turn_number == 2
        and int(CardId.RARE_CANDY) not in view.hand_ids
        and _old_field_count(view, CardId.ABRA) > 0
        and _field_count(view, CardId.KADABRA) == 0
        and _hand_count(view, CardId.KADABRA) == 0
    )
    stage_one = (
        (int(CardId.KADABRA), int(CardId.DUDUNSPARCE))
        if needs_turn_three_kadabra or not _missing_dudunsparce(view)
        else (int(CardId.DUDUNSPARCE), int(CardId.KADABRA))
    )
    return (
        tuple(basics),
        stage_one,
        (int(CardId.ALAKAZAM),),
    )


def _dawn_attack_route_groups(
    *,
    include_dudunsparce: bool = False,
) -> tuple[tuple[int, ...], ...]:
    """攻撃系統を優先するヒカリの3段階検索を返す。"""
    return (
        (int(CardId.ABRA),),
        (
            (int(CardId.KADABRA), int(CardId.DUDUNSPARCE))
            if include_dudunsparce
            else (int(CardId.KADABRA),)
        ),
        (int(CardId.ALAKAZAM),),
    )


def _with_dawn_progress_fallbacks(view, memory, groups):
    """前段の本命が不在でも、有用札を取りながら後段の検索画面へ進む。"""
    filtered = [
        tuple(
            card_id
            for card_id in group
            if card_may_be_in_deck(view, memory, card_id)
        )
        for group in groups
    ]
    fallbacks = (
        (
            int(CardId.DUNSPARCE),
            int(CardId.FAN_ROTOM),
            int(CardId.GENESECT),
            int(CardId.SHAYMIN),
            int(CardId.FEZANDIPITI_EX),
        ),
        (int(CardId.DUDUNSPARCE), int(CardId.KADABRA)),
    )
    for index, candidates in enumerate(fallbacks):
        if (
            index >= len(filtered)
            or filtered[index]
            or not any(filtered[index + 1 :])
        ):
            continue
        filtered[index] = tuple(
            card_id
            for card_id in candidates
            if card_may_be_in_deck(view, memory, card_id)
        )
    return tuple(filtered)


def _hilda_energy_search_wins_now(view, energy_group: tuple[int, ...]) -> bool:
    """トウコで超を取り付ければ、その番のKOで対戦が終わるか返す。"""
    active = view.active
    target = view.opponent_active
    if (
        active is None
        or target is None
        or int(active.id) != int(CardId.ALAKAZAM)
        or view.has_psychic_energy(active)
        or bool(view.current.get("energyAttached", False))
        or not any(
            int(card_id) in _ATTACK_PSYCHIC_IDS
            for card_id in energy_group
        )
    ):
        return False
    target_meta = view.catalog.card(target.id)
    target_prizes = (
        1
        if target_meta is None
        else max(1, int(target_meta.prize_value))
    )
    return (
        int(view.own_prize_count) <= target_prizes
        and can_hand_power_ko(
            view,
            hand_size=max(0, int(view.hand_size) - 1),
            require_legal_option=False,
            assume_active_psychic=True,
        )
    )


def _hilda_proposal(
    view,
    option,
    evolution_group: tuple[int, ...],
    energy_group: tuple[int, ...],
    reason: str,
    extra_rule_ids: tuple[str, ...] = (),
    priority: int = 899,
) -> Proposal:
    groups = (evolution_group, energy_group)
    card_ids = tuple(dict.fromkeys(card_id for group in groups for card_id in group))
    final_ko_energy_search = _hilda_energy_search_wins_now(
        view,
        energy_group,
    )
    intent = PendingIntent.from_view(
        view,
        kind="HILDA_SEARCH",
        card_ids=card_ids,
        card_groups=groups,
        max_cards=1,
        metadata=(
            ("reason", reason),
            *((
                ("final_ko_energy_search", True),
            ) if final_ko_energy_search else ()),
        ),
        effect_card_id=CardId.HILDA,
        effect_serial=option.card_serial,
        remaining_contexts=(SelectContext.TO_HAND, SelectContext.TO_HAND),
    )
    return Proposal(
        (option.position,),
        priority,
        reason,
        ("PLAYBOOK-HILDA", "PLAYBOOK-SEARCH-INTENT", *extra_rule_ids),
        intent,
    )


def _current_attacker_hilda_evolution_group(
    view,
    evolution_group: tuple[int, ...],
) -> tuple[int, ...]:
    """終盤に今の攻撃用超1枚しか取れないなら、進化検索を見送る。"""
    safe_removals = max_safe_deck_removals(
        view,
        requested=2,
        cards_to_hand=True,
        base_hand_delta=-1,
    )
    if safe_removals <= 1:
        return ()
    return evolution_group


def _dawn_proposal(
    view,
    memory,
    option,
    priority: int,
    reason: str,
    extra_rule_ids: tuple[str, ...] = (),
    groups: tuple[tuple[int, ...], ...] | None = None,
) -> Proposal:
    groups = _dawn_groups(view) if groups is None else groups
    groups = _with_dawn_progress_fallbacks(view, memory, groups)
    card_ids = tuple(dict.fromkeys(card_id for group in groups for card_id in group))
    intent = PendingIntent.from_view(
        view,
        kind="DAWN_SEARCH",
        card_ids=card_ids,
        card_groups=groups,
        max_cards=1,
        metadata=(("reason", reason),),
        effect_card_id=CardId.DAWN,
        effect_serial=option.card_serial,
        remaining_contexts=(
            SelectContext.TO_HAND,
            SelectContext.TO_HAND,
            SelectContext.TO_HAND,
        ),
    )
    return Proposal(
        (option.position,),
        priority,
        reason,
        ("PLAYBOOK-DAWN", "PLAYBOOK-SEARCH-INTENT", *extra_rule_ids),
        intent,
    )


def _turn_one_hilda_evolution_group(view) -> tuple[int, ...]:
    bench_space = max(0, int(view.own.get("benchMax", 5)) - len(view.bench))
    waiting_dunsparce = _field_count(view, CardId.DUNSPARCE) + min(
        _hand_count(view, CardId.DUNSPARCE),
        bench_space,
    )
    held_dudunsparce = _hand_count(view, CardId.DUDUNSPARCE)
    if (
        int(CardId.RARE_CANDY) in view.hand_ids
        and _field_count(view, CardId.ABRA) > 0
        and _hand_count(view, CardId.ALAKAZAM) == 0
    ):
        return (
            int(CardId.ALAKAZAM),
            int(CardId.DUDUNSPARCE),
            int(CardId.KADABRA),
        )
    if waiting_dunsparce > held_dudunsparce:
        return (
            int(CardId.DUDUNSPARCE),
            int(CardId.KADABRA),
            int(CardId.ALAKAZAM),
        )
    return (int(CardId.KADABRA), int(CardId.ALAKAZAM))


def _turn_one_hilda_can_expand_with_telepath(view, memory) -> bool:
    return (
        view.own_turn_number == 1
        and not bool(view.current.get("energyAttached", False))
        and attack_line_count(view) < MINIMUM_ATTACK_LINES
        and available_bench_slots(view) > 0
        and _hand_count(view, CardId.TELEPATH_PSYCHIC_ENERGY) == 0
        and any(
            int(pokemon.id) == int(CardId.ABRA)
            and not view.has_psychic_energy(pokemon)
            for pokemon in view.field
        )
        and card_may_be_in_deck(
            view,
            memory,
            CardId.TELEPATH_PSYCHIC_ENERGY,
        )
        and card_may_be_in_deck(view, memory, CardId.ABRA)
    )


def _turn_one_hilda_energy_group(view, memory) -> tuple[int, ...]:
    if _turn_one_hilda_can_expand_with_telepath(view, memory):
        return (
            int(CardId.TELEPATH_PSYCHIC_ENERGY),
            int(CardId.BASIC_PSYCHIC),
            int(CardId.ENRICHING_ENERGY),
        )
    candidates = _fallback_attack_candidates(view)
    if _attacking_psychic_secured(view, memory, candidates):
        return (
            int(CardId.ENRICHING_ENERGY),
            int(CardId.TELEPATH_PSYCHIC_ENERGY),
            int(CardId.BASIC_PSYCHIC),
        )
    return (
        int(CardId.TELEPATH_PSYCHIC_ENERGY),
        int(CardId.BASIC_PSYCHIC),
    )


def _can_prepare_turn_three(view) -> bool:
    if view.own_turn_number != 2:
        return False
    return (
        _old_field_count(view, CardId.ABRA) > 0
        or _field_count(view, CardId.KADABRA) > 0
    )


def _dawn_draw_engine_card(view) -> int | None:
    if _old_field_count(view, CardId.DUNSPARCE) > _hand_count(
        view, CardId.DUDUNSPARCE
    ):
        return int(CardId.DUDUNSPARCE)
    if _old_field_count(view, CardId.ABRA) > _hand_count(view, CardId.KADABRA):
        return int(CardId.KADABRA)
    return None


def _attack_energy_group(view, target, candy_route: bool) -> tuple[int, ...]:
    bench_space = max(0, int(view.own.get("benchMax", 5)) - len(view.bench))
    no_candy_two_abra = (
        int(CardId.RARE_CANDY) not in view.hand_ids
        and _field_count(view, CardId.ABRA) == 2
    )
    telepath_first = (
        (candy_route or no_candy_two_abra)
        and target is not None
        and int(target.id) == int(CardId.ABRA)
        and _field_count(view, CardId.ABRA) < 3
        and bench_space > 0
    )
    if telepath_first:
        return (
            int(CardId.TELEPATH_PSYCHIC_ENERGY),
            int(CardId.BASIC_PSYCHIC),
        )
    return (
        int(CardId.BASIC_PSYCHIC),
        int(CardId.TELEPATH_PSYCHIC_ENERGY),
    )


@covers(
    "PLAYBOOK-HILDA",
    "PLAYBOOK-T1-HILDA-SETUP",
    "PLAYBOOK-DAWN",
    "PLAYBOOK-BOARD-MINIMUM",
    "PLAYBOOK-STOP-WHEN-KO",
    "PLAYBOOK-SEARCH-INTENT",
)
def propose_search(view, memory) -> Proposal | None:
    if not _is_main_selection(view):
        return None

    hilda = _support_option(view, CardId.HILDA)
    dawn = _support_option(view, CardId.DAWN)
    setup_hilda = (
        None
        if hilda is not None
        and must_reserve_future_alakazam_search(
            view,
            CardId.HILDA,
            memory,
        )
        else hilda
    )
    setup_dawn = (
        None
        if dawn is not None
        and must_reserve_future_alakazam_search(
            view,
            CardId.DAWN,
            memory,
        )
        else dawn
    )
    free_line_routes = any(
        option.type == int(OptionType.PLAY)
        and option.card_id in (
            int(CardId.ABRA),
            int(CardId.BUDDY_BUDDY_POFFIN),
            int(CardId.POKE_PAD),
        )
        for option in view.options
    )
    maturity_item_route = any(
        option.type == int(OptionType.PLAY)
        and option.card_id == int(CardId.POKE_PAD)
        for option in view.options
    )
    maturity_needed = reserve_abra_needs_kadabra(view)
    opening_dunsparce_pivot = _opening_active_dunsparce_needs_evolution_pivot(
        view,
        memory,
    )
    maturity_urgent = (
        maturity_needed
        and card_may_be_in_deck(view, memory, CardId.KADABRA)
        and nonfinal_immediate_ko(view)
        and search_preserves_immediate_ko(view, 1)
    )
    if maturity_needed and not maturity_item_route:
        old_reserve_abras = tuple(
            pokemon
            for pokemon in view.field
            if int(pokemon.id) == int(CardId.ABRA)
            and not pokemon.appear_this_turn
        )
        reserve_psychic_secured = any(
            view.has_psychic_energy(pokemon)
            for pokemon in old_reserve_abras
        )
        if setup_hilda is not None:
            return _hilda_proposal(
                view,
                setup_hilda,
                (
                    (int(CardId.DUDUNSPARCE), int(CardId.KADABRA))
                    if opening_dunsparce_pivot
                    else (int(CardId.KADABRA),)
                ),
                (
                    (
                        int(CardId.ENRICHING_ENERGY),
                        int(CardId.BASIC_PSYCHIC),
                        int(CardId.TELEPATH_PSYCHIC_ENERGY),
                    )
                    if reserve_psychic_secured
                    else (
                        int(CardId.BASIC_PSYCHIC),
                        int(CardId.TELEPATH_PSYCHIC_ENERGY),
                    )
                ),
                (
                    "バトル場のノコッチをノココッチへ進化させて山札へ戻し、超付きフーディンを前へ出す"
                    if opening_dunsparce_pivot
                    else
                    "現在のフーディンが攻撃する前にトウコでユンゲラーを確保し、古い後続ケーシィを進化させる"
                    if maturity_urgent
                    else "完成済みフーディンがいる間にトウコで後続ケーシィ用ユンゲラーを準備する"
                ),
                extra_rule_ids=(
                    "PLAYBOOK-T3-KADABRA",
                    "PLAYBOOK-BOARD-MINIMUM",
                    *(("PLAYBOOK-STOP-WHEN-KO",) if maturity_urgent else ()),
                ),
                priority=(
                    OPENING_PIVOT_SEARCH_PRIORITY
                    if opening_dunsparce_pivot
                    else CONTINUITY_MATURITY_SEARCH_PRIORITY
                    if maturity_urgent
                    else ATTACK_LINE_MATURITY_PRIORITY
                ),
            )
        if setup_dawn is not None:
            return _dawn_proposal(
                view,
                memory,
                setup_dawn,
                (
                    CONTINUITY_MATURITY_SEARCH_PRIORITY
                    if maturity_urgent
                    else ATTACK_LINE_MATURITY_PRIORITY
                ),
                (
                    "現在のフーディンが攻撃する前にヒカリでユンゲラーを確保し、古い後続ケーシィを進化させる"
                    if maturity_urgent
                    else "完成済みフーディンがいる間にヒカリで後続の進化段階を予約する"
                ),
                extra_rule_ids=(
                    "PLAYBOOK-T3-KADABRA",
                    "PLAYBOOK-BOARD-MINIMUM",
                    *(("PLAYBOOK-STOP-WHEN-KO",) if maturity_urgent else ()),
                ),
                groups=_dawn_attack_route_groups(),
            )
    dawn_continuity_groups = _dawn_attack_route_groups(
        include_dudunsparce=True,
    )
    if (
        setup_dawn is not None
        and needs_continuity_setup(view)
        and not free_line_routes
        and _support_search_preserves_immediate_ko(
            view,
            memory,
            dawn_continuity_groups,
        )
        and card_may_be_in_deck(view, memory, CardId.ABRA)
    ):
        return _dawn_proposal(
            view,
            memory,
            setup_dawn,
            CONTINUITY_SUPPORT_SEARCH_PRIORITY,
            "非最終KO前にヒカリでケーシィ・ユンゲラー・フーディンを予約し、攻撃系統を3体へ戻す",
            extra_rule_ids=(
                "PLAYBOOK-BOARD-MINIMUM",
                "PLAYBOOK-STOP-WHEN-KO",
            ),
            groups=dawn_continuity_groups,
        )
    if (
        setup_dawn is not None
        and needs_attack_line_setup(view)
        and not free_line_routes
        and card_may_be_in_deck(view, memory, CardId.ABRA)
    ):
        return _dawn_proposal(
            view,
            memory,
            setup_dawn,
            ATTACK_LINE_SUPPORT_PRIORITY,
            "完成済みフーディンがいる間にヒカリで進化前を確保し、ケーシィ系統3体を維持する",
            extra_rule_ids=("PLAYBOOK-BOARD-MINIMUM",),
            groups=_dawn_attack_route_groups(),
        )
    reserve_kadabras = tuple(
        pokemon
        for pokemon in view.field
        if int(pokemon.id) == int(CardId.KADABRA)
        and not pokemon.appear_this_turn
    )
    continuity_search = (
        bool(reserve_kadabras)
        and _hand_count(view, CardId.ALAKAZAM) == 0
        and nonfinal_immediate_ko(view)
        and spend_preserves_immediate_ko(view)
    )
    if continuity_search:
        reserve_psychic_secured = _attacking_psychic_secured(
            view,
            memory,
            reserve_kadabras,
        )
        if dawn is not None and (reserve_psychic_secured or hilda is None):
            return _dawn_proposal(
                view,
                memory,
                dawn,
                CONTINUITY_SUPPORT_SEARCH_PRIORITY,
                "非最終KO前にヒカリで次のフーディンと次々番の進化線を同時に予約する",
                extra_rule_ids=(
                    "PLAYBOOK-T3-KADABRA",
                    "PLAYBOOK-BOARD-MINIMUM",
                    "PLAYBOOK-STOP-WHEN-KO",
                ),
            )
        if hilda is not None:
            return _hilda_proposal(
                view,
                hilda,
                _evolution_priority(view, force_missing_alakazam=True),
                (
                    (
                        int(CardId.ENRICHING_ENERGY),
                        int(CardId.BASIC_PSYCHIC),
                        int(CardId.TELEPATH_PSYCHIC_ENERGY),
                    )
                    if reserve_psychic_secured
                    else (
                        int(CardId.BASIC_PSYCHIC),
                        int(CardId.TELEPATH_PSYCHIC_ENERGY),
                    )
                ),
                (
                    "非最終KO前に次のフーディンとリッチエネルギーを確保する"
                    if reserve_psychic_secured
                    else "非最終KO前に次のフーディンと攻撃用超エネルギーを確保する"
                ),
                extra_rule_ids=(
                    "PLAYBOOK-T3-KADABRA",
                    "PLAYBOOK-BOARD-MINIMUM",
                    "PLAYBOOK-STOP-WHEN-KO",
                ),
                priority=CONTINUITY_SUPPORT_SEARCH_PRIORITY,
            )
    unpowered_reserve_attackers = tuple(
        pokemon
        for pokemon in view.bench
        if int(pokemon.id) in _ATTACKER_IDS
        and not view.has_psychic_energy(pokemon)
    )
    continuity_energy_hilda = (
        hilda
        if any(
            int(pokemon.id) == int(CardId.KADABRA)
            and not pokemon.appear_this_turn
            for pokemon in unpowered_reserve_attackers
        )
        else setup_hilda
    )
    continuity_energy_search = (
        continuity_energy_hilda is not None
        and bool(unpowered_reserve_attackers)
        and any(
            card_may_be_in_deck(view, memory, card_id)
            for card_id in _ATTACK_PSYCHIC_IDS
        )
        and not any(
            int(card_id) in _ATTACK_PSYCHIC_IDS
            for card_id in view.hand_ids
        )
        and nonfinal_immediate_ko(view)
        and spend_preserves_immediate_ko(view)
    )
    if continuity_energy_search:
        reserve_kadabra_needs_alakazam = (
            any(
                int(pokemon.id) == int(CardId.KADABRA)
                for pokemon in unpowered_reserve_attackers
            )
            and _hand_count(view, CardId.ALAKAZAM) == 0
        )
        return _hilda_proposal(
            view,
            continuity_energy_hilda,
            _evolution_priority(
                view,
                force_missing_alakazam=reserve_kadabra_needs_alakazam,
            ),
            (
                int(CardId.BASIC_PSYCHIC),
                int(CardId.TELEPATH_PSYCHIC_ENERGY),
            ),
            "非最終KO前に後続攻撃役の超エネルギーをトウコで予約する",
            extra_rule_ids=(
                "PLAYBOOK-BOARD-MINIMUM",
                "PLAYBOOK-STOP-WHEN-KO",
            ),
            priority=CONTINUITY_SUPPORT_SEARCH_PRIORITY,
        )
    must_search_immediate_candy_alakazam = (
        (hilda is not None or dawn is not None)
        and int(CardId.RARE_CANDY) in view.hand_ids
        and _hand_count(view, CardId.ALAKAZAM) == 0
        and bool(view.eligible_abras)
        and _has_play_option(view, CardId.RARE_CANDY)
    )
    if (
        _has_obvious_immediate_draw(view, memory)
        and not must_search_immediate_candy_alakazam
    ):
        return None

    exact_ko_evolution_group = tuple(
        card_id
        for card_id in _evolution_priority(view)
        if card_may_be_in_deck(view, memory, card_id)
    )
    exact_ko_energy_group = tuple(
        int(card_id)
        for card_id in (
            CardId.BASIC_PSYCHIC,
            CardId.TELEPATH_PSYCHIC_ENERGY,
            CardId.ENRICHING_ENERGY,
        )
        if card_may_be_in_deck(view, memory, card_id)
    )
    if (
        hilda is not None
        and exact_ko_evolution_group
        and exact_ko_energy_group
        and not can_hand_power_ko(view)
        and can_hand_power_ko(
            view,
            hand_size=view.hand_size + 1,
            require_legal_option=False,
        )
    ):
        return _hilda_proposal(
            view,
            hilda,
            exact_ko_evolution_group,
            exact_ko_energy_group,
            "トウコで手札を1枚純増し、Hand Powerの確定KO打点を満たす",
            extra_rule_ids=(
                "PLAYBOOK-MAX-DRAW",
                "PLAYBOOK-STOP-WHEN-KO",
            ),
            priority=970,
        )

    task4_blocks_search = _task4_has_priority(view, memory)
    completed_unpowered_alakazam = any(
        int(pokemon.id) == int(CardId.ALAKAZAM)
        and not view.has_psychic_energy(pokemon)
        for pokemon in view.field
    )
    attack_psychic_in_hand = any(
        int(card_id) in _ATTACK_PSYCHIC_IDS
        for card_id in view.hand_ids
    )
    searchable_attack_psychic = any(
        card_may_be_in_deck(view, memory, card_id)
        for card_id in (
            CardId.BASIC_PSYCHIC,
            CardId.TELEPATH_PSYCHIC_ENERGY,
        )
    )
    if (
        hilda is not None
        and task4_blocks_search
        and completed_unpowered_alakazam
        and not attack_psychic_in_hand
        and searchable_attack_psychic
    ):
        fresh_kadabra_needs_alakazam = (
            _hand_count(view, CardId.ALAKAZAM) == 0
            and any(
                int(pokemon.id) == int(CardId.KADABRA)
                and pokemon.appear_this_turn
                for pokemon in view.field
            )
        )
        evolution_group = tuple(
            card_id
            for card_id in _evolution_priority(
                view,
                force_missing_alakazam=fresh_kadabra_needs_alakazam,
            )
            if card_may_be_in_deck(view, memory, card_id)
        )
        return _hilda_proposal(
            view,
            hilda,
            _current_attacker_hilda_evolution_group(
                view,
                evolution_group,
            ),
            (
                int(CardId.BASIC_PSYCHIC),
                int(CardId.TELEPATH_PSYCHIC_ENERGY),
            ),
            "明白なドローを使い切ったため、任意展開より先に完成済みフーディンの攻撃用超をトウコで確保する",
            extra_rule_ids=("PLAYBOOK-BASIC-PSYCHIC",),
            priority=960,
        )

    urgent_route_target, urgent_needs_alakazam, _ = _attack_route(view, memory)
    urgent_route_psychic_secured = _attacking_psychic_secured(
        view,
        memory,
        () if urgent_route_target is None else (urgent_route_target,),
    )
    old_kadabra_needs_completion = (
        urgent_route_target is not None
        and int(urgent_route_target.id) == int(CardId.KADABRA)
        and not urgent_route_target.appear_this_turn
        and urgent_needs_alakazam
        and card_may_be_in_deck(view, memory, CardId.ALAKAZAM)
    )
    if (
        old_kadabra_needs_completion
        and dawn is not None
        and urgent_route_psychic_secured
    ):
        existing_old_reserve_abra = any(
            int(pokemon.id) == int(CardId.ABRA)
            and not pokemon.appear_this_turn
            for pokemon in view.field
        )
        return _dawn_proposal(
            view,
            memory,
            dawn,
            (
                CURRENT_AND_RESERVE_EVOLUTION_SEARCH_PRIORITY
                if existing_old_reserve_abra
                else 960
            ),
            "古いユンゲラー用フーディンをヒカリで確保し、今ターンの攻撃役と後続を同時に準備する",
            extra_rule_ids=("PLAYBOOK-T3-KADABRA", "PLAYBOOK-BOARD-MINIMUM"),
            groups=_dawn_attack_route_groups(),
        )
    if (
        task4_blocks_search
        and old_kadabra_needs_completion
        and hilda is not None
    ):
        return _hilda_proposal(
            view,
            hilda,
            _evolution_priority(view, force_missing_alakazam=True),
            (
                (
                    int(CardId.ENRICHING_ENERGY),
                    int(CardId.BASIC_PSYCHIC),
                    int(CardId.TELEPATH_PSYCHIC_ENERGY),
                )
                if urgent_route_psychic_secured
                else (
                    int(CardId.BASIC_PSYCHIC),
                    int(CardId.TELEPATH_PSYCHIC_ENERGY),
                )
            ),
            "任意のたね展開より先に古いユンゲラー用フーディンをトウコで確保し、今ターンの攻撃役を完成させる",
            extra_rule_ids=("PLAYBOOK-T3-KADABRA",),
            priority=960,
        )

    if task4_blocks_search:
        return None

    if _field_attack_line_is_empty(view):
        if dawn is not None:
            return _dawn_proposal(
                view,
                memory,
                dawn,
                904,
                "場にケーシィ系統がいないためヒカリでたねから復旧する",
            )
        if hilda is not None and _old_field_count(view, CardId.DUNSPARCE) > 0:
            return _hilda_proposal(
                view,
                hilda,
                (int(CardId.DUDUNSPARCE),),
                (
                    int(CardId.ENRICHING_ENERGY),
                    int(CardId.TELEPATH_PSYCHIC_ENERGY),
                    int(CardId.BASIC_PSYCHIC),
                ),
                "ケーシィ系統の復旧前にノココッチとリッチで追加ドローを準備する",
            )
        return None

    if hilda is not None and view.own_turn_number == 1:
        candy_visible = int(CardId.RARE_CANDY) in view.hand_ids
        attack_candidates = _fallback_attack_candidates(view)
        attack_psychic_secured = _attacking_psychic_secured(
            view,
            memory,
            attack_candidates,
        )
        telepath_expansion = _turn_one_hilda_can_expand_with_telepath(
            view,
            memory,
        )
        telepath_before_attach = (
            telepath_expansion
            and any(
                option.type == int(OptionType.ATTACH)
                and option.card_id == int(CardId.BASIC_PSYCHIC)
                for option in view.options
            )
        )
        return _hilda_proposal(
            view,
            hilda,
            _turn_one_hilda_evolution_group(view),
            _turn_one_hilda_energy_group(view, memory),
            (
                "1ターン目にトウコでテレパス超を先に確保し、"
                "付与効果でケーシィ系統を合計3体へ展開する"
                if telepath_expansion
                else "攻撃役の超は確保済みなので、進化先とリッチを抜いて追加ドローを準備する"
                if attack_psychic_secured
                else (
                    "1ターン目に手札のふしぎなアメを活かす進化先とテレパス超を確保し、2ターン目攻撃を準備する"
                    if candy_visible
                    else "1ターン目に進化ドロー装置とテレパス超を山札から抜き、ふしぎなアメの後続ドロー率を上げる"
                )
            ),
            extra_rule_ids=(
                "PLAYBOOK-T1-HILDA-SETUP",
                *(("PLAYBOOK-BOARD-MINIMUM",) if telepath_expansion else ()),
            ),
            priority=935 if telepath_before_attach else 799,
        )

    active = view.active
    ready_bench_alakazam = any(
        int(pokemon.id) == int(CardId.ALAKAZAM)
        and view.has_psychic_energy(pokemon)
        for pokemon in view.bench
    )
    ready_bench_kadabra = any(
        int(pokemon.id) == int(CardId.KADABRA)
        and not pokemon.appear_this_turn
        and view.has_psychic_energy(pokemon)
        for pokemon in view.bench
    )
    if (
        hilda is not None
        and view.own_turn_number >= 2
        and active is not None
        and int(active.id) in _ONE_RETREAT_IDS
        and not any(
            option.type == int(OptionType.RETREAT)
            for option in view.options
        )
        and _hand_count(view, CardId.BASIC_PSYCHIC) == 0
        and card_may_be_in_deck(view, memory, CardId.BASIC_PSYCHIC)
        and (ready_bench_alakazam or ready_bench_kadabra)
        and not _air_balloon_can_attach_to_active(view)
    ):
        return _hilda_proposal(
            view,
            hilda,
            _evolution_priority(
                view,
                force_missing_alakazam=ready_bench_kadabra,
            ),
            (int(CardId.BASIC_PSYCHIC),),
            (
                "フーディン本体が手札にない超付きユンゲラーを完成させ、前が逃げるための基本超もトウコで確保する"
                if ready_bench_kadabra
                else "完成済みフーディンを前へ出すため、逃げ1のバトルポケモン用に基本超をトウコで確保する"
            ),
            priority=(
                OPENING_PIVOT_SEARCH_PRIORITY
                if is_opening_attack_phase(view)
                else 899
            ),
        )

    route_target, needs_alakazam, candy_route = _attack_route(view, memory)
    route_candidates = () if route_target is None else (route_target,)
    route_psychic_secured = _attacking_psychic_secured(
        view,
        memory,
        route_candidates,
    )
    opening_route_needs_basic_pivot = _opening_powered_lines_need_basic_pivot(
        view,
        memory,
        route_candidates,
    )
    old_reserve_abras = tuple(
        pokemon
        for pokemon in view.field
        if int(pokemon.id) == int(CardId.ABRA)
        and not pokemon.appear_this_turn
    )
    if (
        dawn is not None
        and route_target is not None
        and int(route_target.id) == int(CardId.KADABRA)
        and not route_target.appear_this_turn
        and needs_alakazam
        and route_psychic_secured
        and old_reserve_abras
        and _hand_count(view, CardId.KADABRA) == 0
        and card_may_be_in_deck(view, memory, CardId.ALAKAZAM)
        and card_may_be_in_deck(view, memory, CardId.KADABRA)
    ):
        return _dawn_proposal(
            view,
            memory,
            dawn,
            CURRENT_AND_RESERVE_EVOLUTION_SEARCH_PRIORITY,
            "手札の超で現在のユンゲラーを攻撃役にできるため、ヒカリでフーディンと後続ケーシィ用ユンゲラーを同時にそろえる",
            extra_rule_ids=(
                "PLAYBOOK-T3-KADABRA",
                "PLAYBOOK-BOARD-MINIMUM",
            ),
            groups=_dawn_attack_route_groups(),
        )
    if (
        hilda is not None
        and route_target is not None
        and (needs_alakazam or not route_psychic_secured)
    ):
        evolution_group = _evolution_priority(
            view,
            force_missing_alakazam=needs_alakazam,
        )
        if int(route_target.id) == int(CardId.ALAKAZAM):
            evolution_group = _current_attacker_hilda_evolution_group(
                view,
                evolution_group,
            )
        return _hilda_proposal(
            view,
            hilda,
            evolution_group,
            (
                (int(CardId.BASIC_PSYCHIC),)
                if opening_route_needs_basic_pivot
                else (
                    int(CardId.ENRICHING_ENERGY),
                    int(CardId.BASIC_PSYCHIC),
                    int(CardId.TELEPATH_PSYCHIC_ENERGY),
                )
                if route_psychic_secured
                else _attack_energy_group(view, route_target, candy_route)
            ),
            (
                "終盤は進化札を取らず、完成済みフーディンの不足する攻撃用超だけをトウコで確保する"
                if (
                    not evolution_group
                    and int(route_target.id) == int(CardId.ALAKAZAM)
                )
                else "完成予定のフーディンを前へ出せるよう、トウコで逃げ用の基本超を確保する"
                if opening_route_needs_basic_pivot
                else "ふしぎなアメを直ちに成立させるフーディンをトウコで確保する"
                if candy_route and needs_alakazam and route_psychic_secured
                else "ふしぎなアメ用フーディンと不足する攻撃用超エネルギーをトウコでそろえる"
                if candy_route and needs_alakazam
                else "攻撃用超は確保済みなので、攻撃予定個体の進化先とリッチをトウコでそろえる"
                if route_psychic_secured
                else "攻撃予定個体の進化先と不足する攻撃用超エネルギーをトウコでそろえる"
            ),
            priority=(
                OPENING_PIVOT_SEARCH_PRIORITY
                if opening_route_needs_basic_pivot
                else 960 if candy_route and needs_alakazam else 899
            ),
        )

    if (
        dawn is not None
        and route_target is not None
        and int(route_target.id) == int(CardId.KADABRA)
        and not route_target.appear_this_turn
        and needs_alakazam
    ):
        return _dawn_proposal(
            view,
            memory,
            dawn,
            875,
            "前の番からいるユンゲラー用のフーディンをヒカリで確保し、通常進化の3枚ドローへつなぐ",
            extra_rule_ids=("PLAYBOOK-T3-KADABRA", "PLAYBOOK-MAX-DRAW"),
        )

    if (
        dawn is not None
        and candy_route
        and needs_alakazam
    ):
        return _dawn_proposal(
            view,
            memory,
            dawn,
            875,
            "ヒカリでフーディンを確保し、ふしぎなアメの進化時3枚ドローへ直ちにつなぐ",
            extra_rule_ids=("PLAYBOOK-CANDY-FIRST", "PLAYBOOK-MAX-DRAW"),
        )

    old_abras = tuple(
        pokemon
        for pokemon in view.field
        if int(pokemon.id) == int(CardId.ABRA)
        and not pokemon.appear_this_turn
    )
    fresh_powered_kadabra_waits = any(
        int(pokemon.id) == int(CardId.KADABRA)
        and pokemon.appear_this_turn
        and view.has_psychic_energy(pokemon)
        for pokemon in view.field
    )
    if (
        dawn is not None
        and route_target is None
        and view.own_turn_number == 2
        and old_abras
        and _hand_count(view, CardId.KADABRA) == 0
        and _hand_count(view, CardId.ALAKAZAM) == 0
        and _attacking_psychic_secured(view, memory, old_abras)
    ):
        return _dawn_proposal(
            view,
            memory,
            dawn,
            875,
            (
                "攻撃役の超は確保済みなので、ヒカリでユンゲラーと"
                "フーディンを同時に予約して3ターン目の通常進化を確定する"
            ),
            extra_rule_ids=("PLAYBOOK-T3-KADABRA", "PLAYBOOK-MAX-DRAW"),
        )
    if (
        setup_hilda is not None
        and route_target is None
        and view.own_turn_number == 2
        and old_abras
        and not fresh_powered_kadabra_waits
    ):
        target = _planned_attacker(view, memory, old_abras)
        attack_psychic_secured = _attacking_psychic_secured(
            view,
            memory,
            old_abras,
        )
        opening_old_abra_needs_basic_pivot = (
            _opening_powered_lines_need_basic_pivot(
                view,
                memory,
                old_abras,
            )
        )
        reserve_psychic_needed = (
            attack_psychic_secured
            and not any(
                int(card_id) in (
                    int(CardId.BASIC_PSYCHIC),
                    int(CardId.TELEPATH_PSYCHIC_ENERGY),
                )
                for card_id in view.hand_ids
            )
            and any(
                pokemon.serial != target.serial
                and not view.has_psychic_energy(pokemon)
                for pokemon in old_abras
            )
        )
        energy_group = (
            (int(CardId.BASIC_PSYCHIC),)
            if opening_old_abra_needs_basic_pivot
            else (
                int(CardId.BASIC_PSYCHIC),
                int(CardId.TELEPATH_PSYCHIC_ENERGY),
                int(CardId.ENRICHING_ENERGY),
            )
            if reserve_psychic_needed
            else (
                int(CardId.ENRICHING_ENERGY),
                int(CardId.TELEPATH_PSYCHIC_ENERGY),
                int(CardId.BASIC_PSYCHIC),
            )
            if attack_psychic_secured
            else _attack_energy_group(view, target, False)
        )
        return _hilda_proposal(
            view,
            setup_hilda,
            (
                int(CardId.KADABRA),
                int(CardId.DUDUNSPARCE),
                int(CardId.ALAKAZAM),
            ),
            energy_group,
            (
                "2ターン目の超付きケーシィ用ユンゲラーと、3ターン目に前を逃がす基本超を確保する"
                if opening_old_abra_needs_basic_pivot
                else "2ターン目の古いケーシィ用にユンゲラーを最優先で確保し、3ターン目のフーディン攻撃を保証する"
            ),
            priority=(
                OPENING_PIVOT_SEARCH_PRIORITY
                if opening_old_abra_needs_basic_pivot
                else 899
            ),
        )

    attack_candidates = route_candidates or _fallback_attack_candidates(view)
    attack_psychic_secured = _attacking_psychic_secured(
        view,
        memory,
        attack_candidates,
    )
    opening_attack_candidates_need_basic_pivot = (
        _opening_powered_lines_need_basic_pivot(
            view,
            memory,
            attack_candidates,
        )
    )
    if (
        setup_hilda is not None
        and attack_psychic_secured
        and _old_field_count(view, CardId.DUNSPARCE) > 0
    ):
        return _hilda_proposal(
            view,
            setup_hilda,
            _evolution_priority(view),
            (
                (int(CardId.BASIC_PSYCHIC),)
                if opening_attack_candidates_need_basic_pivot
                else (
                    int(CardId.ENRICHING_ENERGY),
                    int(CardId.TELEPATH_PSYCHIC_ENERGY),
                    int(CardId.BASIC_PSYCHIC),
                )
            ),
            (
                "攻撃用超は盤面にあるため、ノココッチ系統と前を逃がす基本超をトウコで補う"
                if opening_attack_candidates_need_basic_pivot
                else "攻撃用超を確保済みなのでノココッチ系統とリッチをトウコで補う"
            ),
            priority=(
                OPENING_PIVOT_SEARCH_PRIORITY
                if opening_attack_candidates_need_basic_pivot
                else 899
            ),
        )

    if (
        hilda is not None
        and route_target is None
        and view.own_turn_number >= 3
        and old_abras
    ):
        target = _planned_attacker(view, memory, old_abras)
        attack_psychic_secured = _attacking_psychic_secured(
            view,
            memory,
            old_abras,
        )
        opening_old_abra_needs_basic_pivot = (
            _opening_powered_lines_need_basic_pivot(
                view,
                memory,
                old_abras,
            )
        )
        return _hilda_proposal(
            view,
            hilda,
            _evolution_priority(view),
            (
                (int(CardId.BASIC_PSYCHIC),)
                if opening_old_abra_needs_basic_pivot
                else (
                    int(CardId.ENRICHING_ENERGY),
                    int(CardId.BASIC_PSYCHIC),
                    int(CardId.TELEPATH_PSYCHIC_ENERGY),
                )
                if attack_psychic_secured
                else _attack_energy_group(view, target, False)
            ),
            (
                "攻撃用超は盤面にあるため、古いケーシィ用ユンゲラーと前を逃がす基本超をそろえる"
                if opening_old_abra_needs_basic_pivot
                else "攻撃用超は確保済みなので、古いケーシィ用のユンゲラーとリッチをそろえる"
                if attack_psychic_secured
                else "古いケーシィをユンゲラーへ進化させ、次のフーディン攻撃を準備する"
            ),
            priority=(
                OPENING_PIVOT_SEARCH_PRIORITY
                if opening_old_abra_needs_basic_pivot
                else 899
            ),
        )

    turn_three_preparation = _can_prepare_turn_three(view)
    dawn_draw_engine = _dawn_draw_engine_card(view)
    dawn_extends_unpowered_route = (
        not attack_psychic_secured
        and route_target is not None
        and int(route_target.id) == int(CardId.ALAKAZAM)
        and dawn_draw_engine is not None
    )
    candy_visible = int(CardId.RARE_CANDY) in view.hand_ids
    turn_one_dawn_compression = (
        view.own_turn_number == 1 and not candy_visible
    )
    if setup_dawn is None or (
        not attack_psychic_secured
        and not turn_three_preparation
        and not dawn_extends_unpowered_route
        and not turn_one_dawn_compression
    ):
        return None
    if not (
        candy_visible
        or turn_one_dawn_compression
        or view.own_turn_number >= 3
        or _can_prepare_turn_three(view)
    ):
        return None
    return _dawn_proposal(
        view,
        memory,
        setup_dawn,
        795 if turn_one_dawn_compression else 875,
        (
            "1ターン目にヒカリでたね・1進化・2進化を山札から抜き、ふしぎなアメの後続ドロー率を上げる"
            if turn_one_dawn_compression
            else "フーディンの攻撃用超がないため、ヒカリでノココッチを確保して進化時の追加3枚ドローから探す"
            if dawn_draw_engine == int(CardId.DUDUNSPARCE)
            else (
                "攻撃用超がないため、ヒカリで進化先を確保して進化時の追加ドローから探す"
                if dawn_extends_unpowered_route
                else (
                    "超エネルギーがなくてもヒカリでユンゲラーを確保し、3ターン目の通常進化線を準備する"
                    if turn_three_preparation and not attack_psychic_secured
                    else "明白なドローを使い切ったためヒカリで進化段階ごとの不足を補う"
                )
            )
        ),
        extra_rule_ids=("PLAYBOOK-MAX-DRAW",)
        if dawn_extends_unpowered_route or turn_one_dawn_compression
        else (),
    )
