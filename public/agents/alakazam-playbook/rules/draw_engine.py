from __future__ import annotations

from cards import CardId
from model import Area, OptionType, SelectContext
from proposals import Proposal, covers


_ATTACKER_IDS = frozenset({
    int(CardId.ABRA),
    int(CardId.KADABRA),
    int(CardId.ALAKAZAM),
})


@covers("FLOW-DRAW-EVOLUTIONS")
def _evolution_draw_option(view):
    context_card = view.select.get("contextCard")
    if int(view.select.get("context", 0)) != int(SelectContext.ACTIVATE):
        return None
    if not isinstance(context_card, dict) or int(context_card.get("id", -1)) not in (
        int(CardId.KADABRA), int(CardId.ALAKAZAM)
    ):
        return None
    return next(
        (option for option in view.options if option.type == int(OptionType.YES)),
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
    if _turn_three_immediate_alakazam_routes_need_energy(view):
        return ()
    if not _powered_attacker_exists(view, memory):
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
)
def propose_draw(view, memory) -> Proposal | None:
    evolution_draw = _evolution_draw_option(view)
    if evolution_draw is not None:
        return Proposal(
            (evolution_draw.position,),
            940,
            "ユンゲラーまたはフーディンの進化時ドローを必ず使う",
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
        return Proposal(
            (fez.position,),
            930,
            "合法提示されたキチキギスexの3枚ドローを最優先する",
            ("FLOW-DRAW-FEZANDIPITI", "PLAYBOOK-FEZANDIPITI"),
        )

    rich_options = legal_rich_attach_options(view, memory)
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

    dudunsparce_options = _dudunsparce_options(view)
    if dudunsparce_options:
        option = min(dudunsparce_options, key=_dudunsparce_sort_key)
        has_rich = (
            option.source is not None
            and int(CardId.ENRICHING_ENERGY) in option.source.energy_card_ids
        )
        active_pivot = _active_dudunsparce_can_pivot(view, option)
        opens_ready_alakazam = _active_dudunsparce_opens_ready_alakazam(view, option)
        completes_turn_three = _turn_three_last_attacker_needs_draw(view, option)
        if opens_ready_alakazam:
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
                "3ターン目の攻撃完成に必要な不足札を引くため、盤面1体になっても"
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
                996
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
