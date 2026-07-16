from __future__ import annotations

from cards import CardId
from model import Area, OptionType, SelectContext, SelectType
from proposals import PendingIntent, Proposal, covers
from rules.draw_engine import legal_rich_attach_options


@covers("PLAYBOOK-PRESERVE-ABRA")
def _serial_key(pokemon) -> int:
    return 10**9 if pokemon.serial is None else int(pokemon.serial)


@covers("PLAYBOOK-PRESERVE-ABRA", "FLOW-DEVELOP-ABRA")
def _eligible_abras(view):
    return tuple(view.eligible_abras)


@covers("PLAYBOOK-PRESERVE-ABRA", "PLAYBOOK-CANDY-FIRST")
def _protected_abra(view, memory, eligible):
    memory_serial = memory.protected_abra_serial
    if memory_serial is not None:
        remembered = next(
            (pokemon for pokemon in eligible if pokemon.serial == int(memory_serial)),
            None,
        )
        if remembered is not None:
            return remembered
    powered = [pokemon for pokemon in eligible if view.has_psychic_energy(pokemon)]
    candidates = powered or list(eligible)
    return min(
        candidates,
        key=lambda pokemon: (_serial_key(pokemon), int(pokemon.area), int(pokemon.index or 0)),
        default=None,
    )


@covers("FLOW-DEVELOP-ALAKAZAM", "PLAYBOOK-RARE-CANDY")
def _old_dunsparce_options(view):
    return tuple(
        option
        for option in view.options
        if (
            option.type == int(OptionType.EVOLVE)
            and option.card_id == int(CardId.DUDUNSPARCE)
            and option.target is not None
            and option.target.id == int(CardId.DUNSPARCE)
            and not option.target.appear_this_turn
        )
    )


@covers("PLAYBOOK-ENRICHING-RECYCLE", "FLOW-DEVELOP-ALAKAZAM")
def _old_dunsparce_key(option):
    target = option.target
    has_rich = target is not None and int(CardId.ENRICHING_ENERGY) in target.energy_card_ids
    area_rank = 0 if target is not None and target.area == int(Area.ACTIVE) else 1
    serial = 10**9 if target is None or target.serial is None else int(target.serial)
    return (0 if has_rich else 1, area_rank, serial, option.position)


@covers("FLOW-DEVELOP-KADABRA", "PLAYBOOK-T3-KADABRA")
def _old_kadabra_options(view):
    return tuple(
        option
        for option in view.options
        if (
            option.type == int(OptionType.EVOLVE)
            and option.card_id == int(CardId.ALAKAZAM)
            and option.target is not None
            and option.target.id == int(CardId.KADABRA)
            and not option.target.appear_this_turn
        )
    )


@covers("FLOW-DEVELOP-ABRA", "PLAYBOOK-PRESERVE-ABRA")
def _kadabra_options_for_abra(view, protected_serial: int | None):
    return tuple(
        option
        for option in view.options
        if (
            option.type == int(OptionType.EVOLVE)
            and option.card_id == int(CardId.KADABRA)
            and option.target is not None
            and option.target.id == int(CardId.ABRA)
            and not option.target.appear_this_turn
            and option.target.serial != protected_serial
        )
    )


@covers("PLAYBOOK-RARE-CANDY", "PLAYBOOK-SEARCH-INTENT")
def _context_effect_matches(view) -> bool:
    effect = view.select.get("effect")
    return (
        int(view.select.get("type", -1)) == int(SelectType.EVOLVE)
        and int(view.select.get("context", -1)) == int(SelectContext.EVOLVE)
        and isinstance(effect, dict)
        and int(effect.get("id", -1)) == int(CardId.RARE_CANDY)
        and effect.get("serial") is not None
    )


@covers("PLAYBOOK-RARE-CANDY", "PLAYBOOK-SEARCH-INTENT")
def _candy_context_target(view, memory):
    if not _context_effect_matches(view):
        return None
    eligible = _eligible_abras(view)
    eligible_by_serial = {
        pokemon.serial: pokemon for pokemon in eligible if pokemon.serial is not None
    }
    intent = memory.pending_intent
    preferred_serial = None
    if (
        intent is not None
        and intent.kind == "RARE_CANDY_ATTACKER"
        and intent.matches(view)
        and intent.target_serial in eligible_by_serial
    ):
        preferred_serial = int(intent.target_serial)

    candidates = []
    for option in view.options:
        if (
            option.type != int(OptionType.EVOLVE)
            or option.card_id != int(CardId.ALAKAZAM)
            or option.target is None
            or option.target.id != int(CardId.ABRA)
            or option.target.serial not in eligible_by_serial
        ):
            continue
        target = eligible_by_serial[option.target.serial]
        preferred = preferred_serial is not None and target.serial == preferred_serial
        powered_rank = 0 if view.has_psychic_energy(target) else 1
        candidates.append((0 if preferred else 1, powered_rank, _serial_key(target), option.position, option))
    if not candidates:
        return None
    return min(candidates, key=lambda item: item[:4])[4]


@covers("PLAYBOOK-RARE-CANDY", "PLAYBOOK-SEARCH-INTENT")
def _main_play(view, card_id: int):
    return tuple(
        option
        for option in view.options
        if option.type == int(OptionType.PLAY)
        and option.card_id == int(card_id)
        and option.card_serial is not None
    )


@covers("PLAYBOOK-CANDY-FIRST", "PLAYBOOK-SEARCH-INTENT")
def _candy_proposal(view, eligible):
    candy = _main_play(view, int(CardId.RARE_CANDY))
    if not candy or int(CardId.ALAKAZAM) not in view.hand_ids or not eligible:
        return None
    preserve_only_alakazam_for_powered_kadabra = (
        bool(view.current.get("energyAttached"))
        and sum(
            int(card_id) == int(CardId.ALAKAZAM)
            for card_id in view.hand_ids
        ) == 1
        and any(
            int(pokemon.id) == int(CardId.KADABRA)
            and view.has_psychic_energy(pokemon)
            for pokemon in view.field
        )
        and not any(
            view.has_psychic_energy(abra)
            for abra in eligible
        )
    )
    if preserve_only_alakazam_for_powered_kadabra:
        return None
    option = min(candy, key=lambda candidate: candidate.position)
    target = _deterministic_powered_or_old(view, eligible)
    target_serial = None if target is None else target.serial
    return Proposal(
        (option.position,),
        890,
        "前ターンからいる予約ケーシィをふしぎなアメでフーディンへ進化し、進化時ドローへつなぐ",
        ("PLAYBOOK-RARE-CANDY", "PLAYBOOK-CANDY-FIRST"),
        PendingIntent.from_view(
            view,
            kind="RARE_CANDY_ATTACKER",
            card_ids=(CardId.ALAKAZAM,),
            target_serial=target_serial,
            max_cards=1,
            metadata=(("reason", "合法な公開盤面と手札だけで次の進化経路を予約する"),),
            effect_card_id=CardId.RARE_CANDY,
            effect_serial=option.card_serial,
            remaining_contexts=(SelectContext.EVOLVE,),
        ),
    )


@covers("PLAYBOOK-CANDY-FIRST", "PLAYBOOK-PRESERVE-ABRA")
def _deterministic_powered_or_old(view, eligible):
    powered = [pokemon for pokemon in eligible if view.has_psychic_energy(pokemon)]
    return min(
        powered or list(eligible),
        key=lambda pokemon: (_serial_key(pokemon), int(pokemon.area), int(pokemon.index or 0)),
        default=None,
    )


@covers("PLAYBOOK-POKE-PAD", "PLAYBOOK-SEARCH-INTENT")
def _pokepad_after_candy(view, eligible):
    pad = _main_play(view, int(CardId.POKE_PAD))
    if (
        not pad
        or int(CardId.RARE_CANDY) not in view.hand_ids
        or not eligible
        or int(CardId.ALAKAZAM) in {int(pokemon.id) for pokemon in view.field}
        or int(CardId.ALAKAZAM) in view.hand_ids
    ):
        return None
    option = min(pad, key=lambda candidate: candidate.position)
    target = _deterministic_powered_or_old(view, eligible)
    return Proposal(
        (option.position,),
        895,
        "ふしぎなアメと前ターンからいるケーシィがあるため、通常の展開よりポケパッドでフーディンを先に作る",
        ("PLAYBOOK-POKE-PAD", "PLAYBOOK-CANDY-FIRST", "PLAYBOOK-SEARCH-INTENT"),
        PendingIntent.from_view(
            view,
            kind="SEARCH_ALAKAZAM_AFTER_CANDY",
            card_ids=(CardId.ALAKAZAM,),
            target_serial=None if target is None else target.serial,
            max_cards=1,
            metadata=(("reason", "合法な公開盤面と手札だけで次の進化経路を予約する"),),
            effect_card_id=CardId.POKE_PAD,
            effect_serial=option.card_serial,
            remaining_contexts=(SelectContext.TO_HAND,),
        ),
    )


@covers("PLAYBOOK-POKE-PAD", "PLAYBOOK-SEARCH-INTENT", "PLAYBOOK-T3-KADABRA")
def _pokepad_for_old_kadabra(view):
    pad = _main_play(view, int(CardId.POKE_PAD))
    turn_two_setup = view.own_turn_number == 2
    candidates = tuple(
        pokemon
        for pokemon in view.field
        if int(pokemon.id) == int(CardId.KADABRA)
        and (turn_two_setup or not pokemon.appear_this_turn)
    )
    if (
        not pad
        or not candidates
        or int(CardId.ALAKAZAM) in {int(pokemon.id) for pokemon in view.field}
        or int(CardId.ALAKAZAM) in view.hand_ids
    ):
        return None
    option = min(pad, key=lambda candidate: candidate.position)
    target = min(
        candidates,
        key=lambda pokemon: (
            0 if view.has_psychic_energy(pokemon) else 1,
            _serial_key(pokemon),
            int(pokemon.area),
            int(pokemon.index or 0),
        ),
    )
    return Proposal(
        (option.position,),
        895,
        (
            "2ターン目に作ったユンゲラーを3ターン目にフーディンへ進化させるため、ポケパッドで先に確保する"
            if target.appear_this_turn
            else "前の番からいるユンゲラーを今ターンのフーディン攻撃役へ完成させるため、ポケパッドでフーディンを探す"
        ),
        ("PLAYBOOK-POKE-PAD", "PLAYBOOK-T3-KADABRA", "PLAYBOOK-SEARCH-INTENT"),
        PendingIntent.from_view(
            view,
            kind="SEARCH_ALAKAZAM_FOR_KADABRA",
            card_ids=(CardId.ALAKAZAM,),
            target_serial=target.serial,
            max_cards=1,
            metadata=(("reason", "進化可能なユンゲラーから即時攻撃線を作る"),),
            effect_card_id=CardId.POKE_PAD,
            effect_serial=option.card_serial,
            remaining_contexts=(SelectContext.TO_HAND,),
        ),
    )


@covers("FLOW-DRAW-FEZANDIPITI", "PLAYBOOK-BOARD-MINIMUM")
def _has_immediate_draw_option(view, memory) -> bool:
    if any(
        option.type == int(OptionType.ABILITY)
        and option.card_id == int(CardId.FEZANDIPITI_EX)
        for option in view.options
    ):
        return True
    if any(
        option.type == int(OptionType.ABILITY)
        and option.card_id == int(CardId.DUDUNSPARCE)
        and option.source is not None
        and view.field_count_after_return(option.source.serial) >= 2
        for option in view.options
    ):
        return True
    return bool(legal_rich_attach_options(view, memory))


@covers(
    "FLOW-DEVELOP-ALAKAZAM",
    "FLOW-DEVELOP-KADABRA",
    "FLOW-DEVELOP-ABRA",
    "PLAYBOOK-PRESERVE-ABRA",
    "PLAYBOOK-CANDY-FIRST",
    "PLAYBOOK-RARE-CANDY",
    "PLAYBOOK-T3-KADABRA",
    "PLAYBOOK-ENRICHING-RECYCLE",
    "PLAYBOOK-POKE-PAD",
    "PLAYBOOK-SEARCH-INTENT",
)
def propose_evolution(view, memory) -> Proposal | None:
    context_target = _candy_context_target(view, memory)
    if context_target is not None:
        return Proposal(
            (context_target.position,),
            960,
            "ふしぎなアメの実CABT context37で予約対象のフーディンを選ぶ",
            ("PLAYBOOK-RARE-CANDY", "PLAYBOOK-SEARCH-INTENT"),
        )

    if int(view.select.get("type", SelectType.MAIN)) != int(SelectType.MAIN):
        return None

    old_dunsparce = _old_dunsparce_options(view)
    if old_dunsparce:
        option = min(old_dunsparce, key=_old_dunsparce_key)
        return Proposal(
            (option.position,),
            905 if int(CardId.ENRICHING_ENERGY) in option.target.energy_card_ids else 850,
            "リッチ付きの古いノコッチを先にノココッチへ進化してリッチ再利用ドローをつなぐ"
            if int(CardId.ENRICHING_ENERGY) in option.target.energy_card_ids
            else "古いノコッチをノココッチへ進化してドローを準備する",
            ("FLOW-DEVELOP-ALAKAZAM", "PLAYBOOK-ENRICHING-RECYCLE"),
            alternative="同じserialのRich attach→EVOLVE→ABILITYを再評価する",
        )

    eligible = _eligible_abras(view)
    candy = _candy_proposal(view, eligible)
    old_kadabra = _old_kadabra_options(view)
    if old_kadabra:
        option = min(
            old_kadabra,
            key=lambda candidate: (
                0 if view.has_psychic_energy(candidate.target) else 1,
                0 if candidate.target.serial == memory.reserved_attacker_serial else 1,
                _serial_key(candidate.target),
                int(candidate.target.area),
                int(candidate.target.index or 0),
                candidate.position,
            ),
        )
        old_kadabra_is_attacker = view.has_psychic_energy(option.target)
        candy_is_immediate = candy is not None and any(
            view.has_psychic_energy(abra) for abra in eligible
        )
        if old_kadabra_is_attacker or not candy_is_immediate:
            return Proposal(
                (option.position,),
                900,
                "前の番からいるユンゲラーをフーディンへ通常進化して3枚ドローを準備する",
                ("FLOW-DEVELOP-KADABRA", "PLAYBOOK-T3-KADABRA"),
            )

    pad_for_kadabra = _pokepad_for_old_kadabra(view)
    if pad_for_kadabra is not None:
        return pad_for_kadabra

    if not eligible:
        return None

    if candy is not None:
        return candy

    pad = _pokepad_after_candy(view, eligible)
    if pad is not None:
        return pad

    protected = _protected_abra(view, memory, eligible)
    protected_serial = None if protected is None else protected.serial
    protected_option = next(
        (
            option for option in view.options
            if option.type == int(OptionType.EVOLVE)
            and option.card_id == int(CardId.KADABRA)
            and option.target is not None
            and option.target.id == int(CardId.ABRA)
            and option.target.serial == protected_serial
            and not option.target.appear_this_turn
        ),
        None,
    )
    first_unpowered_kadabra_draw_finished = any(
        int(pokemon.id) == int(CardId.KADABRA)
        and pokemon.appear_this_turn
        and not view.has_psychic_energy(pokemon)
        for pokemon in view.field
    )
    if (
        view.own_turn_number == 2
        and protected_option is not None
        and view.has_psychic_energy(protected_option.target)
        and int(CardId.RARE_CANDY) not in view.hand_ids
        and first_unpowered_kadabra_draw_finished
    ):
        return Proposal(
            (protected_option.position,),
            885,
            "無エネ個体のユンゲラー2枚ドローでアメを引けなかったため、2枚目は超付きケーシィを進化して3ターン目の攻撃役にする",
            ("PLAYBOOK-T3-KADABRA", "PLAYBOOK-PRESERVE-ABRA"),
        )

    spare = _kadabra_options_for_abra(view, protected_serial)
    if spare:
        option = min(
            spare,
            key=lambda candidate: (
                _serial_key(candidate.target),
                int(candidate.target.area),
                int(candidate.target.index or 0),
                candidate.position,
            ),
        )
        return Proposal(
            (option.position,),
            880,
            "ふしぎなアメ用に最低1体のケーシィを残し、余剰ケーシィだけをユンゲラーへ進化する",
            ("PLAYBOOK-PRESERVE-ABRA", "FLOW-DEVELOP-ABRA", "FLOW-DRAW-EVOLUTIONS"),
        )

    if protected_option is not None and not _has_immediate_draw_option(view, memory):
        return Proposal(
            (protected_option.position,),
            700,
            "合法な即時ドローを使い切ったため、保護していたケーシィをユンゲラーへ進化して3ターン目を準備する",
            ("PLAYBOOK-T3-KADABRA", "PLAYBOOK-PRESERVE-ABRA"),
        )
    return None
