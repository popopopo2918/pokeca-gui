from __future__ import annotations

from cards import CardId
from memory import card_may_be_in_deck
from model import Area, OptionType, SelectContext, SelectType
from proposals import PendingIntent, Proposal, covers
from rules.board_plan import (
    MINIMUM_ATTACK_LINES,
    OPENING_ATTACKER_COMPLETION_PRIORITY,
    has_taken_prize,
    is_opening_attack_phase,
    powered_alakazam_exists,
)
from rules.continuity import (
    CONTINUITY_DRAW_RESERVE_PRIORITY,
    CONTINUITY_EVOLUTION_PRIORITY,
    CONTINUITY_SEARCH_PRIORITY,
    evolution_draw_preserves_immediate_ko,
    nonfinal_immediate_ko,
    spend_preserves_immediate_ko,
)
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
    opening_attacker_completion = (
        is_opening_attack_phase(view)
        and not powered_alakazam_exists(view)
        and target is not None
        and target.area == int(Area.BENCH)
        and view.has_psychic_energy(target)
    )
    continuity_candy = (
        powered_alakazam_exists(view)
        and nonfinal_immediate_ko(view)
        and evolution_draw_preserves_immediate_ko(view, 3)
    )
    return Proposal(
        (option.position,),
        (
            OPENING_ATTACKER_COMPLETION_PRIORITY
            if opening_attacker_completion
            else CONTINUITY_EVOLUTION_PRIORITY
            if continuity_candy
            else 890
        ),
        (
            "非最終KO前に古い後続ケーシィをふしぎなアメで完成させ、次番の攻撃役を確保する"
            if continuity_candy
            else "前ターンからいる予約ケーシィをふしぎなアメでフーディンへ進化し、進化時ドローへつなぐ"
        ),
        (
            "PLAYBOOK-RARE-CANDY",
            "PLAYBOOK-CANDY-FIRST",
            *(("PLAYBOOK-BOARD-MINIMUM", "PLAYBOOK-STOP-WHEN-KO") if continuity_candy else ()),
        ),
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


def _on_time_kadabra_option(view, memory):
    """現在のKOを保ったまま、次番に間に合う通常進化先を返す。"""
    if not (
        nonfinal_immediate_ko(view)
        and evolution_draw_preserves_immediate_ko(view, 2)
    ):
        return None
    return min(
        (
            option
            for option in view.options
            if option.type == int(OptionType.EVOLVE)
            and option.card_id == int(CardId.KADABRA)
            and option.target is not None
            and int(option.target.id) == int(CardId.ABRA)
            and not option.target.appear_this_turn
        ),
        key=lambda option: (
            0 if view.has_psychic_energy(option.target) else 1,
            0 if option.target.serial == memory.reserved_attacker_serial else 1,
            _serial_key(option.target),
            option.position,
        ),
        default=None,
    )


@covers("PLAYBOOK-POKE-PAD", "PLAYBOOK-SEARCH-INTENT")
def _pokepad_after_candy(view, memory, eligible):
    pad = _main_play(view, int(CardId.POKE_PAD))
    if (
        not pad
        or view.own_turn_number < 2
        or int(CardId.RARE_CANDY) not in view.hand_ids
        or not eligible
        or int(CardId.ALAKAZAM) in {int(pokemon.id) for pokemon in view.field}
        or int(CardId.ALAKAZAM) in view.hand_ids
        or not card_may_be_in_deck(view, memory, CardId.ALAKAZAM)
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
def _pokepad_for_old_kadabra(view, memory):
    pad = _main_play(view, int(CardId.POKE_PAD))
    continuity_search = (
        nonfinal_immediate_ko(view)
        and spend_preserves_immediate_ko(view)
    )
    candidates = tuple(
        pokemon
        for pokemon in view.field
        if int(pokemon.id) == int(CardId.KADABRA)
        and not pokemon.appear_this_turn
    )
    if (
        not pad
        or not candidates
        or (
            not continuity_search
            and int(CardId.ALAKAZAM) in {
                int(pokemon.id) for pokemon in view.field
            }
        )
        or int(CardId.ALAKAZAM) in view.hand_ids
        or not card_may_be_in_deck(view, memory, CardId.ALAKAZAM)
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
        CONTINUITY_SEARCH_PRIORITY if continuity_search else 895,
        (
            "非最終KO前に後続ユンゲラー用フーディンをポケパッドで予約する"
            if continuity_search
            else "前の番からいるユンゲラーを今ターンのフーディン攻撃役へ完成させるため、ポケパッドでフーディンを探す"
        ),
        (
            "PLAYBOOK-POKE-PAD",
            "PLAYBOOK-T3-KADABRA",
            "PLAYBOOK-SEARCH-INTENT",
            *(
                ("PLAYBOOK-BOARD-MINIMUM", "PLAYBOOK-STOP-WHEN-KO")
                if continuity_search
                else ()
            ),
        ),
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
    "PLAYBOOK-BOARD-MINIMUM",
    "PLAYBOOK-STOP-WHEN-KO",
    "PLAYBOOK-MAX-DRAW",
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

    old_kadabra = _old_kadabra_options(view)
    opening_powered_kadabra = min(
        (
            option
            for option in old_kadabra
            if view.has_psychic_energy(option.target)
        ),
        key=lambda candidate: (
            0 if candidate.target.area == int(Area.ACTIVE) else 1,
            0 if candidate.target.serial == memory.reserved_attacker_serial else 1,
            _serial_key(candidate.target),
            candidate.position,
        ),
        default=None,
    )
    if (
        is_opening_attack_phase(view)
        and not powered_alakazam_exists(view)
        and opening_powered_kadabra is not None
    ):
        return Proposal(
            (opening_powered_kadabra.position,),
            OPENING_ATTACKER_COMPLETION_PRIORITY,
            "初回攻撃前は超付きユンゲラーを先にフーディンへ進化し、攻撃役と3枚ドローを確定する",
            (
                "FLOW-DEVELOP-KADABRA",
                "PLAYBOOK-T3-KADABRA",
                "PLAYBOOK-MAX-DRAW",
            ),
        )

    old_dunsparce = _old_dunsparce_options(view)
    if (
        old_dunsparce
        and old_kadabra
        and nonfinal_immediate_ko(view)
        and evolution_draw_preserves_immediate_ko(view, 3)
    ):
        option = min(
            old_kadabra,
            key=lambda candidate: (
                0 if view.has_psychic_energy(candidate.target) else 1,
                0
                if candidate.target.serial == memory.reserved_attacker_serial
                else 1,
                _serial_key(candidate.target),
                candidate.position,
            ),
        )
        return Proposal(
            (option.position,),
            CONTINUITY_EVOLUTION_PRIORITY,
            "非最終KO前はノココッチ準備より先に後続ユンゲラーをフーディンへ進化し、次の攻撃役を完成させる",
            (
                "FLOW-DEVELOP-KADABRA",
                "PLAYBOOK-T3-KADABRA",
                "PLAYBOOK-BOARD-MINIMUM",
                "PLAYBOOK-STOP-WHEN-KO",
            ),
        )

    mature_attack_lines = sum(
        int(pokemon.id) in (int(CardId.KADABRA), int(CardId.ALAKAZAM))
        for pokemon in view.field
    )
    continuity_kadabra_options = tuple(
        option
        for option in view.options
        if option.type == int(OptionType.EVOLVE)
        and option.card_id == int(CardId.KADABRA)
        and option.target is not None
        and option.target.id == int(CardId.ABRA)
        and not option.target.appear_this_turn
    )
    if (
        old_dunsparce
        and mature_attack_lines < MINIMUM_ATTACK_LINES
        and continuity_kadabra_options
        and nonfinal_immediate_ko(view)
        and evolution_draw_preserves_immediate_ko(view, 2)
    ):
        eligible = _eligible_abras(view)
        protected = _protected_abra(view, memory, eligible)
        protected_serial = None if protected is None else protected.serial
        option = min(
            continuity_kadabra_options,
            key=lambda candidate: (
                0 if view.has_psychic_energy(candidate.target) else 1,
                0 if candidate.target.serial != protected_serial else 1,
                0
                if candidate.target.serial == memory.reserved_attacker_serial
                else 1,
                _serial_key(candidate.target),
                candidate.position,
            ),
        )
        return Proposal(
            (option.position,),
            CONTINUITY_EVOLUTION_PRIORITY,
            "非最終KO前はノココッチ準備より先に後続ケーシィをユンゲラーへ進化し、連続KO用の次の攻撃役を成熟させる",
            (
                "PLAYBOOK-T3-KADABRA",
                "PLAYBOOK-PRESERVE-ABRA",
                "PLAYBOOK-BOARD-MINIMUM",
                "PLAYBOOK-STOP-WHEN-KO",
                "PLAYBOOK-MAX-DRAW",
            ),
        )

    if old_dunsparce:
        option = min(old_dunsparce, key=_old_dunsparce_key)
        continuity_draw_reserve = (
            nonfinal_immediate_ko(view)
            and spend_preserves_immediate_ko(view)
        )
        return Proposal(
            (option.position,),
            (
                CONTINUITY_DRAW_RESERVE_PRIORITY
                if continuity_draw_reserve
                else 905
                if int(CardId.ENRICHING_ENERGY) in option.target.energy_card_ids
                else 850
            ),
            (
                "非最終KO前にノココッチへ進化し、相手の手札妨害後に使う3枚ドローを温存する"
                if continuity_draw_reserve
                else "リッチ付きの古いノコッチを先にノココッチへ進化してリッチ再利用ドローをつなぐ"
                if int(CardId.ENRICHING_ENERGY) in option.target.energy_card_ids
                else "古いノコッチをノココッチへ進化してドローを準備する"
            ),
            (
                "FLOW-DEVELOP-ALAKAZAM",
                "PLAYBOOK-ENRICHING-RECYCLE",
                *(
                    (
                        "PLAYBOOK-MAX-DRAW",
                        "PLAYBOOK-BOARD-MINIMUM",
                        "PLAYBOOK-STOP-WHEN-KO",
                    )
                    if continuity_draw_reserve
                    else ()
                ),
            ),
            alternative="同じserialのRich attach→EVOLVE→ABILITYを再評価する",
        )

    eligible = _eligible_abras(view)
    candy = _candy_proposal(view, eligible)
    if old_kadabra:
        option = min(
            old_kadabra,
            key=lambda candidate: (
                0 if view.has_psychic_energy(candidate.target) else 1,
                0 if candidate.target.area == int(Area.ACTIVE) else 1,
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
        continuity_evolution = (
            nonfinal_immediate_ko(view)
            and evolution_draw_preserves_immediate_ko(view, 3)
        )
        if continuity_evolution or old_kadabra_is_attacker or not candy_is_immediate:
            return Proposal(
                (option.position,),
                CONTINUITY_EVOLUTION_PRIORITY if continuity_evolution else 900,
                (
                    "非最終KO前に後続ユンゲラーをフーディンへ進化し、次の攻撃役と3枚ドローを確保する"
                    if continuity_evolution
                    else "前の番からいるユンゲラーをフーディンへ通常進化して3枚ドローを準備する"
                ),
                (
                    "FLOW-DEVELOP-KADABRA",
                    "PLAYBOOK-T3-KADABRA",
                    *(
                        ("PLAYBOOK-BOARD-MINIMUM", "PLAYBOOK-STOP-WHEN-KO")
                        if continuity_evolution
                        else ()
                    ),
                ),
            )

    pad_for_kadabra = _pokepad_for_old_kadabra(view, memory)
    if pad_for_kadabra is not None:
        return pad_for_kadabra

    if not eligible:
        return None

    on_time_kadabra = _on_time_kadabra_option(view, memory)
    if candy is not None and on_time_kadabra is not None:
        return Proposal(
            (on_time_kadabra.position,),
            CONTINUITY_EVOLUTION_PRIORITY,
            "現在のフーディンで非最終KOできるため、後続ケーシィをユンゲラーへ通常進化して2枚引き、ふしぎなアメを温存する",
            (
                "PLAYBOOK-T3-KADABRA",
                "PLAYBOOK-MAX-DRAW",
                "PLAYBOOK-RARE-CANDY",
                "PLAYBOOK-BOARD-MINIMUM",
                "PLAYBOOK-STOP-WHEN-KO",
            ),
        )

    if candy is not None:
        return candy

    pad = _pokepad_after_candy(view, memory, eligible)
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
        continuity_evolution = (
            nonfinal_immediate_ko(view)
            and evolution_draw_preserves_immediate_ko(view, 2)
        )
        return Proposal(
            (protected_option.position,),
            CONTINUITY_EVOLUTION_PRIORITY if continuity_evolution else 885,
            (
                "非最終KO前に超付きケーシィもユンゲラーへ進化し、次番の連続KO役を成熟させる"
                if continuity_evolution
                else "無エネ個体のユンゲラー2枚ドローでアメを引けなかったため、2枚目は超付きケーシィを進化して3ターン目の攻撃役にする"
            ),
            (
                "PLAYBOOK-T3-KADABRA",
                "PLAYBOOK-PRESERVE-ABRA",
                *(
                    ("PLAYBOOK-BOARD-MINIMUM", "PLAYBOOK-STOP-WHEN-KO")
                    if continuity_evolution
                    else ()
                ),
            ),
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
        continuity_evolution = (
            nonfinal_immediate_ko(view)
            and evolution_draw_preserves_immediate_ko(view, 2)
        )
        return Proposal(
            (option.position,),
            CONTINUITY_EVOLUTION_PRIORITY if continuity_evolution else 880,
            (
                "非最終KO前に余剰ケーシィをユンゲラーへ進化し、アメ用ケーシィと通常進化の両経路を残す"
                if continuity_evolution
                else "ふしぎなアメ用に最低1体のケーシィを残し、余剰ケーシィだけをユンゲラーへ進化する"
            ),
            (
                "PLAYBOOK-PRESERVE-ABRA",
                "FLOW-DEVELOP-ABRA",
                "FLOW-DRAW-EVOLUTIONS",
                *(
                    ("PLAYBOOK-BOARD-MINIMUM", "PLAYBOOK-STOP-WHEN-KO")
                    if continuity_evolution
                    else ()
                ),
            ),
        )

    if protected_option is not None and (
        nonfinal_immediate_ko(view)
        or not _has_immediate_draw_option(view, memory)
    ):
        continuity_evolution = (
            nonfinal_immediate_ko(view)
            and evolution_draw_preserves_immediate_ko(view, 2)
        )
        active = view.active
        post_opening_energy_draw = (
            has_taken_prize(view)
            and active is not None
            and int(active.id) == int(CardId.ALAKAZAM)
            and not view.has_psychic_energy(active)
            and not bool(view.current.get("energyAttached", False))
            and not any(
                int(card_id)
                in (
                    int(CardId.BASIC_PSYCHIC),
                    int(CardId.TELEPATH_PSYCHIC_ENERGY),
                )
                for card_id in view.hand_ids
            )
        )
        turn_two_draw_before_dunsparce_search = (
            view.own_turn_number == 2
            and int(CardId.POKE_PAD) in view.hand_ids
            and int(CardId.ALAKAZAM) in view.hand_ids
            and not any(
                int(pokemon.id) == int(CardId.DUNSPARCE)
                for pokemon in view.field
            )
        )
        return Proposal(
            (protected_option.position,),
            (
                CONTINUITY_EVOLUTION_PRIORITY
                if continuity_evolution
                else 970
                if post_opening_energy_draw
                else 806
                if turn_two_draw_before_dunsparce_search
                else 700
            ),
            (
                "非最終KO前に後続ケーシィをユンゲラーへ進化し、次の番の二段進化詰まりを防ぐ"
                if continuity_evolution
                else "攻撃開始後の無エネ復旧ではサポートを使う前にユンゲラーへ進化し、2枚ドローで超エネルギーと検索札を再判定する"
                if post_opening_energy_draw
                else "2ターン目はノコッチの先取りより先にユンゲラーへ進化して2枚ドローし、ポケパッドを自然ドロー後まで温存する"
                if turn_two_draw_before_dunsparce_search
                else "合法な即時ドローを使い切ったため、保護していたケーシィをユンゲラーへ進化して3ターン目を準備する"
            ),
            (
                "PLAYBOOK-T3-KADABRA",
                "PLAYBOOK-PRESERVE-ABRA",
                *(
                    ("PLAYBOOK-POKE-PAD", "PLAYBOOK-MAX-DRAW")
                    if turn_two_draw_before_dunsparce_search
                    else ()
                ),
                *(
                    ("PLAYBOOK-BOARD-MINIMUM", "PLAYBOOK-STOP-WHEN-KO")
                    if continuity_evolution
                    else ()
                ),
            ),
        )
    return None
