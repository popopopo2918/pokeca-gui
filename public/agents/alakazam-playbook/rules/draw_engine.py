from __future__ import annotations

from cards import CardId
from memory import card_may_be_in_deck
from model import Area, OptionType, SelectContext
from proposals import Proposal, covers
from rules.board_plan import is_opening_attack_phase
from rules.continuity import (
    CONTINUITY_LINE_DRAW_PRIORITY,
    CONTINUITY_SPACE_PRIORITY,
    continuity_space_release_needed,
    immediate_ko_ends_game,
    needs_continuity_setup,
)
from rules.deck_safety import (
    can_remove_from_deck,
    deck_safety_active,
    minimum_deck_reserve,
    returned_dudunsparce_cards,
)


_ATTACKER_IDS = frozenset({
    int(CardId.ABRA),
    int(CardId.KADABRA),
    int(CardId.ALAKAZAM),
})
_ONE_RETREAT_PIVOT_IDS = frozenset({
    int(CardId.ABRA),
    int(CardId.KADABRA),
    int(CardId.ALAKAZAM),
    int(CardId.DUNSPARCE),
    int(CardId.FAN_ROTOM),
    int(CardId.GENESECT),
    int(CardId.SHAYMIN),
    int(CardId.PSYDUCK),
    int(CardId.FEZANDIPITI_EX),
})


@covers("FLOW-DRAW-EVOLUTIONS")
def _evolution_draw_option(view):
    context_card = view.select.get("contextCard")
    if int(view.select.get("context", 0)) != int(SelectContext.ACTIVATE):
        return None
    if not isinstance(context_card, dict):
        return None
    card_id = int(context_card.get("id", -1))
    draw_count = {
        int(CardId.KADABRA): 2,
        int(CardId.ALAKAZAM): 3,
    }.get(card_id)
    if draw_count is None:
        return None
    actual_draw = min(
        draw_count,
        max(0, int(view.own.get("deckCount", 0))),
    )
    wanted = (
        OptionType.YES
        if can_remove_from_deck(
            view,
            cards_removed=draw_count,
            hand_delta=actual_draw,
        )
        else OptionType.NO
    )
    return next(
        (option for option in view.options if option.type == int(wanted)),
        None,
    )


@covers("PLAYBOOK-MAX-DRAW")
def _option_position(option) -> int:
    return int(option.position)


@covers("PLAYBOOK-ENRICHING-CONDITION")
def _powered_attacker_exists(view, memory) -> bool:
    attackers = tuple(
        pokemon for pokemon in view.field if int(pokemon.id) in _ATTACKER_IDS
    )
    active = view.active
    if active is not None and int(active.id) == int(CardId.ALAKAZAM):
        return view.has_psychic_energy(active)

    reserved_serial = memory.reserved_attacker_serial
    if reserved_serial is not None:
        reserved = next(
            (pokemon for pokemon in attackers if pokemon.serial == reserved_serial),
            None,
        )
        if reserved is not None:
            return view.has_psychic_energy(reserved)

    protected_serial = memory.protected_abra_serial
    if protected_serial is not None:
        protected = next(
            (pokemon for pokemon in attackers if pokemon.serial == protected_serial),
            None,
        )
        if protected is not None:
            return view.has_psychic_energy(protected)

    attacker = min(
        attackers,
        key=lambda pokemon: (
            0 if pokemon.area == int(Area.ACTIVE) else 1,
            10**9 if pokemon.serial is None else int(pokemon.serial),
        ),
        default=None,
    )
    return attacker is not None and view.has_psychic_energy(attacker)


@covers("PLAYBOOK-ENRICHING-CONDITION", "PLAYBOOK-MAX-DRAW")
def _turn_two_rich_recovery_is_safe(view, memory) -> bool:
    """今番に超を付けられない2Tだけ、リッチ7枚ドローへ切り替える。"""
    if (
        not is_opening_attack_phase(view)
        or view.own_turn_number != 2
        or bool(view.current.get("energyAttached", False))
        or _powered_attacker_exists(view, memory)
    ):
        return False
    attackers = tuple(
        pokemon
        for pokemon in view.field
        if int(pokemon.id) in _ATTACKER_IDS
    )
    if not attackers:
        return True
    if any(view.has_psychic_energy(attacker) for attacker in attackers):
        return False
    if any(
        int(card_id)
        in (
            int(CardId.BASIC_PSYCHIC),
            int(CardId.TELEPATH_PSYCHIC_ENERGY),
        )
        for card_id in view.hand_ids
    ):
        return False
    hilda_can_supply_psychic = (
        any(
            option.type == int(OptionType.PLAY)
            and option.card_id == int(CardId.HILDA)
            for option in view.options
        )
        and any(
            card_may_be_in_deck(view, memory, card_id)
            for card_id in (
                CardId.BASIC_PSYCHIC,
                CardId.TELEPATH_PSYCHIC_ENERGY,
            )
        )
    )
    return not hilda_can_supply_psychic


@covers("PLAYBOOK-ENRICHING-CONDITION")
def _turn_three_immediate_alakazam_routes_need_energy(view) -> bool:
    if view.own_turn_number < 3:
        return False

    routes = [
        pokemon
        for pokemon in view.field
        if int(pokemon.id) == int(CardId.ALAKAZAM)
    ]
    routes.extend(
        option.target
        for option in view.options
        if (
            option.type == int(OptionType.EVOLVE)
            and option.card_id == int(CardId.ALAKAZAM)
            and option.target is not None
        )
    )
    candy_route_ready = (
        int(CardId.RARE_CANDY) in view.hand_ids
        and int(CardId.ALAKAZAM) in view.hand_ids
        and any(
            option.type == int(OptionType.PLAY)
            and option.card_id == int(CardId.RARE_CANDY)
            for option in view.options
        )
    )
    if candy_route_ready:
        routes.extend(view.eligible_abras)

    return bool(routes) and not any(
        view.has_psychic_energy(route)
        for route in routes
    )


@covers("PLAYBOOK-ENRICHING-CONDITION", "PLAYBOOK-ENRICHING-RECYCLE")
def legal_rich_attach_options(view, memory):
    active = view.active
    powered_completion_waits = any(
        int(pokemon.id) == int(CardId.ALAKAZAM)
        and view.has_psychic_energy(pokemon)
        for pokemon in view.bench
    )
    powered_completion_waits = powered_completion_waits or any(
        option.type == int(OptionType.EVOLVE)
        and option.card_id == int(CardId.ALAKAZAM)
        and option.target is not None
        and option.target.area == int(Area.BENCH)
        and view.has_psychic_energy(option.target)
        for option in view.options
    )
    powered_completion_waits = powered_completion_waits or (
        int(CardId.RARE_CANDY) in view.hand_ids
        and int(CardId.ALAKAZAM) in view.hand_ids
        and any(
            option.type == int(OptionType.PLAY)
            and option.card_id == int(CardId.RARE_CANDY)
            for option in view.options
        )
        and any(
            int(pokemon.id) == int(CardId.ABRA)
            and pokemon.area == int(Area.BENCH)
            and view.has_psychic_energy(pokemon)
            for pokemon in view.eligible_abras
        )
    )
    bench_dudunsparce_draw_can_find_pivot = (
        any(
            option.type == int(OptionType.EVOLVE)
            and option.card_id == int(CardId.DUDUNSPARCE)
            and option.target is not None
            and option.target.area == int(Area.BENCH)
            and not option.target.appear_this_turn
            for option in view.options
        )
        and any(
            card_may_be_in_deck(view, memory, card_id)
            for card_id in (
                CardId.BASIC_PSYCHIC,
                CardId.TELEPATH_PSYCHIC_ENERGY,
                CardId.HILDA,
            )
        )
    )
    opening_pivot_needs_attachment = (
        is_opening_attack_phase(view)
        and view.own_turn_number >= 2
        and active is not None
        and int(active.id) in _ONE_RETREAT_PIVOT_IDS
        and powered_completion_waits
        and not any(
            option.type == int(OptionType.RETREAT)
            for option in view.options
        )
        and not any(
            option.type == int(OptionType.ATTACH)
            and option.card_id == int(CardId.AIR_BALLOON)
            and option.target is not None
            and option.target.serial == active.serial
            for option in view.options
        )
        and not any(
            option.type == int(OptionType.EVOLVE)
            and option.card_id == int(CardId.DUDUNSPARCE)
            and option.target is not None
            and option.target.serial == active.serial
            for option in view.options
        )
        and (
            any(
                option.type == int(OptionType.ATTACH)
                and option.card_id == int(CardId.BASIC_PSYCHIC)
                and option.target is not None
                and option.target.serial == active.serial
                for option in view.options
            )
            or any(
                option.type == int(OptionType.ATTACH)
                and option.card_id == int(CardId.TELEPATH_PSYCHIC_ENERGY)
                and option.target is not None
                and option.target.serial == active.serial
                for option in view.options
            )
            or (
                card_may_be_in_deck(
                    view,
                    memory,
                    CardId.BASIC_PSYCHIC,
                )
                and any(
                    option.type == int(OptionType.PLAY)
                    and option.card_id == int(CardId.HILDA)
                    for option in view.options
                )
            )
            or bench_dudunsparce_draw_can_find_pivot
        )
    )
    if opening_pivot_needs_attachment:
        return ()
    if _turn_three_immediate_alakazam_routes_need_energy(view):
        return ()
    if (
        not _powered_attacker_exists(view, memory)
        and not _turn_two_rich_recovery_is_safe(view, memory)
    ):
        return ()
    if any(
        option.type == int(OptionType.ATTACH)
        and option.card_id == int(CardId.BASIC_PSYCHIC)
        and option.target is not None
        and int(option.target.id) == int(CardId.ALAKAZAM)
        and not view.has_psychic_energy(option.target)
        for option in view.options
    ):
        return ()
    evolvable_serials = {
        option.target.serial
        for option in view.options
        if (
            option.type == int(OptionType.EVOLVE)
            and option.card_id == int(CardId.DUDUNSPARCE)
            and option.target is not None
            and option.target.id == int(CardId.DUNSPARCE)
            and option.target.serial is not None
            and not option.target.appear_this_turn
        )
    }
    return tuple(
        option
        for option in view.options
        if (
            option.type == int(OptionType.ATTACH)
            and option.card_id == int(CardId.ENRICHING_ENERGY)
            and option.target is not None
            and option.target.id == int(CardId.DUNSPARCE)
            and option.target.serial in evolvable_serials
            and not option.target.appear_this_turn
        )
    )


@covers("PLAYBOOK-ENRICHING-CONDITION", "PLAYBOOK-ENRICHING-RECYCLE")
def _rich_sort_key(option):
    target = option.target
    area_rank = 0 if target is not None and target.area == int(Area.ACTIVE) else 1
    serial = 10**9 if target is None or target.serial is None else int(target.serial)
    return (
        area_rank,
        serial,
        _option_position(option),
    )


@covers("PLAYBOOK-BOARD-MINIMUM", "PLAYBOOK-MAX-DRAW")
def _active_dudunsparce_can_pivot(view, option) -> bool:
    return (
        option.source is not None
        and option.source.area == int(Area.ACTIVE)
        and view.field_count_after_return(option.source.serial) >= 1
    )


@covers("PLAYBOOK-MAX-DRAW", "PLAYBOOK-PROMOTE-COMPLETE")
def _active_dudunsparce_opens_ready_alakazam(view, option) -> bool:
    return (
        _active_dudunsparce_can_pivot(view, option)
        and any(
            int(pokemon.id) == int(CardId.ALAKAZAM)
            and view.has_psychic_energy(pokemon)
            for pokemon in view.bench
        )
    )


@covers("PLAYBOOK-BOARD-MINIMUM", "PLAYBOOK-MAX-DRAW", "PLAYBOOK-T3-KADABRA")
def _turn_three_last_attacker_needs_draw(view, option) -> bool:
    if (
        view.own_turn_number != 3
        or option.source is None
        or option.source.area != int(Area.BENCH)
        or view.field_count_after_return(option.source.serial) != 1
    ):
        return False
    remaining = tuple(
        pokemon
        for pokemon in view.field
        if pokemon.serial != option.source.serial
    )
    if len(remaining) != 1:
        return False
    attacker = remaining[0]
    if int(attacker.id) == int(CardId.ALAKAZAM):
        return (
            not view.has_psychic_energy(attacker)
            and not any(
                int(card_id)
                in (
                    int(CardId.BASIC_PSYCHIC),
                    int(CardId.TELEPATH_PSYCHIC_ENERGY),
                )
                for card_id in view.hand_ids
            )
        )
    return (
        int(attacker.id) in (int(CardId.ABRA), int(CardId.KADABRA))
        and not attacker.appear_this_turn
    )


@covers(
    "PLAYBOOK-BOARD-MINIMUM",
    "PLAYBOOK-MAX-DRAW",
    "PLAYBOOK-PROMOTE-COMPLETE",
)
def _dudunsparce_options(view):
    return tuple(
        option
        for option in view.options
        if (
            option.type == int(OptionType.ABILITY)
            and option.card_id == int(CardId.DUDUNSPARCE)
            and option.source is not None
            and (
                view.field_count_after_return(option.source.serial) >= 2
                or _active_dudunsparce_can_pivot(view, option)
                or _turn_three_last_attacker_needs_draw(view, option)
            )
        )
    )


@covers(
    "PLAYBOOK-AIR-BALLOON",
    "PLAYBOOK-ENRICHING-RECYCLE",
    "PLAYBOOK-DECK-SAFETY",
)
def _deck_floor_balloon_recycle(view, dudunsparce_options):
    """最低残数では、ふうせんを戻す束へ加えて循環用の1枚を作る。"""
    deck_count = max(0, int(view.own.get("deckCount", 0)))
    if (
        not deck_safety_active(view)
        or deck_count > minimum_deck_reserve(view)
    ):
        return None

    actual_draw = min(3, deck_count)
    recyclable_sources = {}
    for ability in dudunsparce_options:
        source = ability.source
        if (
            source is None
            or source.serial is None
            or int(CardId.AIR_BALLOON) in source.tool_ids
        ):
            continue
        returned = returned_dudunsparce_cards(ability)
        projected_without_balloon = deck_count - actual_draw + returned
        if projected_without_balloon > deck_count:
            continue
        if not can_remove_from_deck(
            view,
            cards_removed=actual_draw,
            cards_returned=returned + 1,
            hand_delta=actual_draw - 1,
        ):
            continue
        recyclable_sources[int(source.serial)] = ability

    balloon_options = tuple(
        option
        for option in view.options
        if (
            option.type == int(OptionType.ATTACH)
            and option.card_id == int(CardId.AIR_BALLOON)
            and option.target is not None
            and option.target.serial is not None
            and int(option.target.serial) in recyclable_sources
        )
    )
    if not balloon_options:
        return None
    return min(
        balloon_options,
        key=lambda option: (
            _dudunsparce_sort_key(
                recyclable_sources[int(option.target.serial)]
            ),
            _option_position(option),
        ),
    )


@covers("PLAYBOOK-ENRICHING-RECYCLE", "PLAYBOOK-BOARD-MINIMUM")
def _dudunsparce_sort_key(option):
    source = option.source
    has_rich = source is not None and int(CardId.ENRICHING_ENERGY) in source.energy_card_ids
    area_rank = 0 if source is not None and source.area == int(Area.ACTIVE) else 1
    serial = 10**9 if source is None or source.serial is None else int(source.serial)
    position = _option_position(option)
    return (0 if has_rich else 1, area_rank, serial, position)


@covers(
    "FLOW-DRAW-FEZANDIPITI",
    "FLOW-DRAW-EVOLUTIONS",
    "PLAYBOOK-FEZANDIPITI",
    "PLAYBOOK-ENRICHING-CONDITION",
    "PLAYBOOK-ENRICHING-RECYCLE",
    "PLAYBOOK-NO-ENRICHING-RETREAT",
    "PLAYBOOK-MAX-DRAW",
    "PLAYBOOK-BOARD-MINIMUM",
    "PLAYBOOK-STOP-WHEN-KO",
    "PLAYBOOK-T3-KADABRA",
    "PLAYBOOK-DECK-SAFETY",
)
def propose_draw(view, memory) -> Proposal | None:
    evolution_draw = _evolution_draw_option(view)
    if evolution_draw is not None:
        declined_for_deck = evolution_draw.type == int(OptionType.NO)
        return Proposal(
            (evolution_draw.position,),
            940,
            (
                "山札10枚以下では勝利までのターン開始ドローを残すため、進化時ドローだけ断る"
                if declined_for_deck
                else "ユンゲラーまたはフーディンの進化時ドローを必ず使う"
            ),
            ("FLOW-DRAW-EVOLUTIONS",),
        )

    fez = next(
        (
            option for option in view.options
            if option.type == int(OptionType.ABILITY)
            and option.card_id == int(CardId.FEZANDIPITI_EX)
        ),
        None,
    )
    if fez is not None:
        actual_draw = min(
            3,
            max(0, int(view.own.get("deckCount", 0))),
        )
        if not can_remove_from_deck(
            view,
            cards_removed=3,
            hand_delta=actual_draw,
        ):
            fez = None
    if fez is not None:
        return Proposal(
            (fez.position,),
            930,
            "合法提示されたキチキギスexの3枚ドローを最優先する",
            ("FLOW-DRAW-FEZANDIPITI", "PLAYBOOK-FEZANDIPITI"),
        )

    rich_options = tuple(
        option
        for option in legal_rich_attach_options(view, memory)
        if can_remove_from_deck(
            view,
            cards_removed=4,
            hand_delta=(
                min(4, max(0, int(view.own.get("deckCount", 0)))) - 1
            ),
        )
    )
    if rich_options:
        option = min(rich_options, key=_rich_sort_key)
        target_serial = None if option.target is None else option.target.serial
        return Proposal(
            (option.position,),
            920,
            "攻撃役の超エネルギーを確保済みなのでリッチをノコッチへ付け、ノココッチ化後に山札へ戻して再利用する",
            (
                "PLAYBOOK-ENRICHING-CONDITION",
                "PLAYBOOK-ENRICHING-RECYCLE",
                "PLAYBOOK-NO-ENRICHING-RETREAT",
            ),
            alternative=(f"target_serial={target_serial};Richは逃げるコストにしない"),
        )

    raw_dudunsparce_options = _dudunsparce_options(view)
    deck_floor_balloon = _deck_floor_balloon_recycle(
        view,
        raw_dudunsparce_options,
    )
    if deck_floor_balloon is not None:
        target_serial = (
            None
            if deck_floor_balloon.target is None
            else deck_floor_balloon.target.serial
        )
        return Proposal(
            (deck_floor_balloon.position,),
            918,
            "山札が最低残数なので、ふうせんをノココッチの戻す束へ加えて循環用の1枚を作る",
            (
                "PLAYBOOK-DECK-SAFETY",
                "PLAYBOOK-ENRICHING-RECYCLE",
                "PLAYBOOK-AIR-BALLOON",
            ),
            alternative=(
                f"target_serial={target_serial};次に同じノココッチのにげあしドローを使う"
            ),
        )

    dudunsparce_draw = min(
        3,
        max(0, int(view.own.get("deckCount", 0))),
    )
    dudunsparce_options = tuple(
        option
        for option in raw_dudunsparce_options
        if can_remove_from_deck(
            view,
            cards_removed=dudunsparce_draw,
            cards_returned=returned_dudunsparce_cards(option),
            hand_delta=dudunsparce_draw,
        )
    )
    if dudunsparce_options:
        option = min(dudunsparce_options, key=_dudunsparce_sort_key)
        has_rich = (
            option.source is not None
            and int(CardId.ENRICHING_ENERGY) in option.source.energy_card_ids
        )
        active_pivot = _active_dudunsparce_can_pivot(view, option)
        opens_ready_alakazam = _active_dudunsparce_opens_ready_alakazam(view, option)
        completes_turn_three = _turn_three_last_attacker_needs_draw(view, option)
        opens_continuity_slot = continuity_space_release_needed(view)
        draws_for_attack_line = needs_continuity_setup(view)
        uses_deck_floor_balloon = (
            deck_safety_active(view)
            and max(0, int(view.own.get("deckCount", 0)))
            <= minimum_deck_reserve(view)
            and option.source is not None
            and int(CardId.AIR_BALLOON) in option.source.tool_ids
        )
        deck_floor_recycle = (
            deck_safety_active(view)
            and max(0, int(view.own.get("deckCount", 0)))
            <= minimum_deck_reserve(view)
            and not immediate_ko_ends_game(view)
        )
        if uses_deck_floor_balloon:
            reason = (
                "山札が最低残数なので、ふうせん付きノココッチを戻して"
                "通常ドローと次の循環に使う山札を増やす"
            )
            rule_ids = (
                "PLAYBOOK-DECK-SAFETY",
                "PLAYBOOK-ENRICHING-RECYCLE",
                "PLAYBOOK-MAX-DRAW",
            )
        elif deck_floor_recycle:
            reason = (
                "次のターン開始ドロー後も山札を残すため、"
                "非最終KOより先にノココッチで進化束を循環する"
            )
            rule_ids = (
                "PLAYBOOK-DECK-SAFETY",
                "PLAYBOOK-MAX-DRAW",
                "PLAYBOOK-STOP-WHEN-KO",
            )
        elif opens_continuity_slot:
            reason = (
                "満員盤面のノココッチを山札へ戻して3枚引き、"
                "ケーシィ系統3体目を置く枠を空ける"
            )
            rule_ids = (
                "PLAYBOOK-BOARD-MINIMUM",
                "PLAYBOOK-MAX-DRAW",
                "PLAYBOOK-STOP-WHEN-KO",
            )
            if has_rich:
                rule_ids = ("PLAYBOOK-ENRICHING-RECYCLE", *rule_ids)
        elif draws_for_attack_line:
            reason = (
                "非最終KO前にノココッチで3枚引き、"
                "ケーシィ系統3体目の着地札を探す"
            )
            rule_ids = (
                "PLAYBOOK-BOARD-MINIMUM",
                "PLAYBOOK-MAX-DRAW",
                "PLAYBOOK-STOP-WHEN-KO",
            )
            if has_rich:
                rule_ids = ("PLAYBOOK-ENRICHING-RECYCLE", *rule_ids)
        elif opens_ready_alakazam:
            reason = (
                "バトル場のノココッチを山札へ戻して3枚引き、前を空けて"
                "超エネルギー付きフーディンを昇格させる"
            )
            rule_ids = (
                "PLAYBOOK-MAX-DRAW",
                "PLAYBOOK-PROMOTE-COMPLETE",
            )
            if has_rich:
                rule_ids = ("PLAYBOOK-ENRICHING-RECYCLE", *rule_ids)
        elif active_pivot:
            reason = (
                "バトル場のノココッチを山札へ戻して3枚引き、前を空けて"
                "ベンチポケモンへ交代する"
            )
            rule_ids = ("PLAYBOOK-MAX-DRAW",)
            if has_rich:
                rule_ids = ("PLAYBOOK-ENRICHING-RECYCLE", *rule_ids)
        elif completes_turn_three:
            reason = (
                "3ターン目の攻撃用超や進化札を引くため、盤面1体になっても"
                "ノココッチで3枚ドローする"
            )
            rule_ids = (
                "PLAYBOOK-BOARD-MINIMUM",
                "PLAYBOOK-MAX-DRAW",
                "PLAYBOOK-T3-KADABRA",
            )
        else:
            reason = (
                "リッチ付きノココッチを優先して1回3枚ドローし、使用後も盤面を2体以上維持する"
                if has_rich
                else "ノココッチで1回3枚ドローするが、使用後も盤面を2体以上維持する"
            )
            rule_ids = (
                (
                    "PLAYBOOK-ENRICHING-RECYCLE",
                    "PLAYBOOK-BOARD-MINIMUM",
                    "PLAYBOOK-MAX-DRAW",
                )
                if has_rich
                else ("PLAYBOOK-BOARD-MINIMUM", "PLAYBOOK-MAX-DRAW")
            )
        return Proposal(
            (option.position,),
            (
                1200
                if deck_floor_recycle
                else CONTINUITY_SPACE_PRIORITY
                if opens_continuity_slot
                else CONTINUITY_LINE_DRAW_PRIORITY
                if draws_for_attack_line
                else 996
                if opens_ready_alakazam
                else (925 if active_pivot else (915 if completes_turn_three else 910))
            ),
            reason,
            rule_ids,
            alternative=(
                "特性後のTO_ACTIVEで完成済みフーディンを選ぶ"
                if opens_ready_alakazam
                else (
                    "特性後のTO_ACTIVEで唯一のベンチを選ぶ"
                    if active_pivot
                    else (
                        "3ターン目の攻撃完成時だけ盤面1体を許容する"
                        if completes_turn_three
                        else "盤面を2体以上維持できるノココッチだけを使う"
                    )
                )
            ),
        )
    return None
