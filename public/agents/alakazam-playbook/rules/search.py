from __future__ import annotations

from cards import CardId
from model import OptionType, SelectContext, SelectType
from proposals import PendingIntent, Proposal, covers
from rules.draw_engine import legal_rich_attach_options


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


def _task4_has_priority(view) -> bool:
    poke_pad = _has_play_option(view, CardId.POKE_PAD)
    if poke_pad and _missing_dudunsparce(view):
        return True
    if _field_count(view, CardId.ABRA) != 0:
        return False
    return poke_pad or any(
        _has_play_option(view, card_id)
        for card_id in (CardId.BUDDY_BUDDY_POFFIN, CardId.ABRA)
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
    intent = PendingIntent.from_view(
        view,
        kind="HILDA_SEARCH",
        card_ids=card_ids,
        card_groups=groups,
        max_cards=1,
        metadata=(("reason", reason),),
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


def _dawn_proposal(
    view,
    option,
    priority: int,
    reason: str,
    extra_rule_ids: tuple[str, ...] = (),
) -> Proposal:
    groups = _dawn_groups(view)
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


def _turn_one_hilda_energy_group(view, memory) -> tuple[int, ...]:
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
    "PLAYBOOK-SEARCH-INTENT",
)
def propose_search(view, memory) -> Proposal | None:
    if not _is_main_selection(view):
        return None

    hilda = _support_option(view, CardId.HILDA)
    dawn = _support_option(view, CardId.DAWN)
    turn_two_kadabras = tuple(
        pokemon
        for pokemon in view.field
        if int(pokemon.id) == int(CardId.KADABRA)
    )
    must_secure_turn_three_alakazam = (
        hilda is not None
        and view.own_turn_number == 2
        and bool(turn_two_kadabras)
        and _hand_count(view, CardId.ALAKAZAM) == 0
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
        and not must_secure_turn_three_alakazam
        and not must_search_immediate_candy_alakazam
    ):
        return None

    if _task4_has_priority(view):
        return None

    if _field_attack_line_is_empty(view):
        if dawn is not None:
            return _dawn_proposal(
                view,
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
        return _hilda_proposal(
            view,
            hilda,
            _turn_one_hilda_evolution_group(view),
            _turn_one_hilda_energy_group(view, memory),
            (
                "攻撃役の超は確保済みなので、進化先とリッチを抜いて追加ドローを準備する"
                if attack_psychic_secured
                else (
                    "1ターン目に手札のふしぎなアメを活かす進化先とテレパス超を確保し、2ターン目攻撃を準備する"
                    if candy_visible
                    else "1ターン目に進化ドロー装置とテレパス超を山札から抜き、ふしぎなアメの後続ドロー率を上げる"
                )
            ),
            extra_rule_ids=("PLAYBOOK-T1-HILDA-SETUP",),
            priority=799,
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
        )

    if (
        must_secure_turn_three_alakazam
    ):
        target = _planned_attacker(view, memory, turn_two_kadabras)
        energy_group = (
            (
                int(CardId.ENRICHING_ENERGY),
                int(CardId.BASIC_PSYCHIC),
                int(CardId.TELEPATH_PSYCHIC_ENERGY),
            )
            if _attacking_psychic_secured(
                view,
                memory,
                turn_two_kadabras,
            )
            else (
                int(CardId.BASIC_PSYCHIC),
                int(CardId.TELEPATH_PSYCHIC_ENERGY),
            )
        )
        return _hilda_proposal(
            view,
            hilda,
            _evolution_priority(view, force_missing_alakazam=True),
            energy_group,
            "2ターン目に進化したユンゲラーのフーディンをトウコで確保し、3ターン目攻撃を保証する",
            extra_rule_ids=("PLAYBOOK-T3-KADABRA",),
            priority=935,
        )

    route_target, needs_alakazam, candy_route = _attack_route(view, memory)
    route_candidates = () if route_target is None else (route_target,)
    route_psychic_secured = _attacking_psychic_secured(
        view,
        memory,
        route_candidates,
    )
    if (
        hilda is not None
        and route_target is not None
        and (needs_alakazam or not route_psychic_secured)
    ):
        return _hilda_proposal(
            view,
            hilda,
            _evolution_priority(
                view,
                force_missing_alakazam=needs_alakazam,
            ),
            (
                (
                    int(CardId.ENRICHING_ENERGY),
                    int(CardId.BASIC_PSYCHIC),
                    int(CardId.TELEPATH_PSYCHIC_ENERGY),
                )
                if route_psychic_secured
                else _attack_energy_group(view, route_target, candy_route)
            ),
            (
                "ふしぎなアメを直ちに成立させるフーディンをトウコで確保する"
                if candy_route and needs_alakazam and route_psychic_secured
                else "ふしぎなアメ用フーディンと不足する攻撃用超エネルギーをトウコでそろえる"
                if candy_route and needs_alakazam
                else "攻撃用超は確保済みなので、攻撃予定個体の進化先とリッチをトウコでそろえる"
                if route_psychic_secured
                else "攻撃予定個体の進化先と不足する攻撃用超エネルギーをトウコでそろえる"
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
            dawn,
            875,
            (
                "攻撃役の超は確保済みなので、ヒカリでユンゲラーと"
                "フーディンを同時に予約して3ターン目の通常進化を確定する"
            ),
            extra_rule_ids=("PLAYBOOK-T3-KADABRA", "PLAYBOOK-MAX-DRAW"),
        )
    if (
        hilda is not None
        and route_target is None
        and view.own_turn_number == 2
        and old_abras
    ):
        target = _planned_attacker(view, memory, old_abras)
        energy_group = (
            (
                int(CardId.ENRICHING_ENERGY),
                int(CardId.TELEPATH_PSYCHIC_ENERGY),
                int(CardId.BASIC_PSYCHIC),
            )
            if _attacking_psychic_secured(view, memory, old_abras)
            else _attack_energy_group(view, target, False)
        )
        return _hilda_proposal(
            view,
            hilda,
            (
                int(CardId.KADABRA),
                int(CardId.DUDUNSPARCE),
                int(CardId.ALAKAZAM),
            ),
            energy_group,
            "2ターン目の古いケーシィ用にユンゲラーを最優先で確保し、3ターン目のフーディン攻撃を保証する",
        )

    attack_candidates = route_candidates or _fallback_attack_candidates(view)
    attack_psychic_secured = _attacking_psychic_secured(
        view,
        memory,
        attack_candidates,
    )
    if (
        hilda is not None
        and attack_psychic_secured
        and _old_field_count(view, CardId.DUNSPARCE) > 0
    ):
        return _hilda_proposal(
            view,
            hilda,
            _evolution_priority(view),
            (
                int(CardId.ENRICHING_ENERGY),
                int(CardId.TELEPATH_PSYCHIC_ENERGY),
                int(CardId.BASIC_PSYCHIC),
            ),
            "攻撃用超を確保済みなのでノココッチ系統とリッチをトウコで補う",
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
        return _hilda_proposal(
            view,
            hilda,
            _evolution_priority(view),
            (
                (
                    int(CardId.ENRICHING_ENERGY),
                    int(CardId.BASIC_PSYCHIC),
                    int(CardId.TELEPATH_PSYCHIC_ENERGY),
                )
                if attack_psychic_secured
                else _attack_energy_group(view, target, False)
            ),
            (
                "攻撃用超は確保済みなので、古いケーシィ用のユンゲラーとリッチをそろえる"
                if attack_psychic_secured
                else "古いケーシィをユンゲラーへ進化させ、次のフーディン攻撃を準備する"
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
    if dawn is None or (
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
        dawn,
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
