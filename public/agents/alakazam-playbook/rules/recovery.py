from __future__ import annotations

from cards import CardId
from memory import card_may_be_in_deck
from model import CardType, OptionType, SelectContext, SelectType
from proposals import PendingIntent, Proposal, covers
from rules.board_plan import (
    ATTACK_LINE_IDS,
    MINIMUM_ATTACK_LINES,
    attack_line_count,
    reserve_abra_needs_kadabra,
)
from rules.continuity import (
    CONTINUITY_BULK_RECYCLE_PRIORITY,
    CONTINUITY_DIRECT_RECOVERY_PRIORITY,
    CONTINUITY_GUARANTEED_RECOVERY_PRIORITY,
    CONTINUITY_MATURITY_SEARCH_PRIORITY,
    CONTINUITY_RECOVERY_PRIORITY,
    CURRENT_AND_RESERVE_DIRECT_RECOVERY_PRIORITY,
    needs_continuity_setup,
    nonfinal_immediate_ko,
    spend_preserves_immediate_ko,
)
from rules.deck_safety import minimum_deck_reserve


SACRED_ASH_PRIORITY = (
    int(CardId.ALAKAZAM),
    int(CardId.ABRA),
    int(CardId.KADABRA),
    int(CardId.DUDUNSPARCE),
    int(CardId.DUNSPARCE),
    int(CardId.FAN_ROTOM),
    int(CardId.FEZANDIPITI_EX),
    int(CardId.GENESECT),
    int(CardId.SHAYMIN),
    int(CardId.PSYDUCK),
)

LANA_RULELESS_PRIORITY = tuple(
    card_id
    for card_id in SACRED_ASH_PRIORITY
    if card_id != int(CardId.FEZANDIPITI_EX)
)

PROMOTION_PRIORITY = {
    int(CardId.ALAKAZAM): 1,
    int(CardId.KADABRA): 2,
    int(CardId.ABRA): 3,
    int(CardId.DUDUNSPARCE): 4,
    int(CardId.FAN_ROTOM): 5,
    int(CardId.DUNSPARCE): 6,
    int(CardId.PSYDUCK): 7,
    int(CardId.SHAYMIN): 8,
    int(CardId.GENESECT): 9,
    int(CardId.FEZANDIPITI_EX): 10,
}


def _is_main_selection(view) -> bool:
    return (
        int(view.select.get("type", -1)) == int(SelectType.MAIN)
        and int(view.select.get("context", -1)) == int(SelectContext.MAIN)
    )


def _play_option(view, card_id: int):
    return min(
        (
            option
            for option in view.options
            if option.type == int(OptionType.PLAY)
            and option.card_id == int(card_id)
            and option.card_serial is not None
        ),
        key=lambda option: (int(option.card_serial), option.position),
        default=None,
    )


def _forced_promotion(view) -> Proposal | None:
    if (
        int(view.select.get("type", -1)) != int(SelectType.CARD)
        or int(view.select.get("context", -1)) != int(SelectContext.TO_ACTIVE)
        or view.select.get("effect") is not None
    ):
        return None

    options = [
        option
        for option in view.options
        if option.type == int(OptionType.CARD)
        and option.source is not None
        and option.source.player_index == view.own_index
        and option.source.serial is not None
    ]
    if not options:
        return None

    def rank(option) -> tuple[int, int, int, int, int]:
        pokemon = option.source
        if (
            pokemon.id == int(CardId.ALAKAZAM)
            and pokemon.has_psychic_energy
        ):
            role = 0
        else:
            role = PROMOTION_PRIORITY.get(int(pokemon.id), 100)
        return (
            role,
            0 if pokemon.has_psychic_energy else 1,
            int(pokemon.serial),
            int(pokemon.id),
            option.position,
        )

    chosen = min(options, key=rank)
    powered = chosen.source.has_psychic_energy and chosen.source.id in (
        int(CardId.ABRA),
        int(CardId.KADABRA),
        int(CardId.ALAKAZAM),
    )
    reason = (
        "超エネルギー付きの攻撃役を同じ進化段階の中で優先して前へ出す"
        if powered
        else "公開盤面の進化完成度を優先して前へ出す"
    )
    return Proposal(
        (chosen.position,),
        1080,
        reason,
        ("FLOW-DEVELOP-ALAKAZAM", "PLAYBOOK-PROMOTE-COMPLETE"),
    )


def _discard_ids(view) -> tuple[int, ...]:
    return tuple(
        int(card["id"])
        for card in (view.own.get("discard") or [])
        if card is not None and card.get("id") is not None
    )


def _ordered_present(
    priority: tuple[int, ...],
    present_ids: tuple[int, ...],
) -> tuple[int, ...]:
    present = set(int(card_id) for card_id in present_ids)
    return tuple(card_id for card_id in priority if card_id in present)


def _sacred_ash_card_groups(
    targets: tuple[int, ...],
) -> tuple[tuple[int, ...], ...]:
    """5枠を攻撃3段階とドロー1系統へ先に割り当てる。"""
    present = set(int(card_id) for card_id in targets)
    role_order = (
        int(CardId.ALAKAZAM),
        int(CardId.ABRA),
        int(CardId.KADABRA),
        int(CardId.DUDUNSPARCE),
        int(CardId.DUNSPARCE),
    )
    groups = [(card_id,) for card_id in role_order if card_id in present]
    abra_first_fallback = tuple(
        card_id
        for card_id in (
            int(CardId.ABRA),
            int(CardId.KADABRA),
            int(CardId.ALAKAZAM),
            *targets,
        )
        if card_id in present
    )
    abra_first_fallback = tuple(dict.fromkeys(abra_first_fallback))
    fallbacks = (targets, abra_first_fallback or targets)
    while len(groups) < 5:
        groups.append(fallbacks[(len(groups) - len(role_order)) % 2])
    return tuple(groups[:5])


def _can_immediately_rebuild_attack_lines(
    view,
    memory,
    discard_ids: tuple[int, ...],
) -> bool:
    if int(CardId.ABRA) not in discard_ids or not needs_continuity_setup(view):
        return False
    if card_may_be_in_deck(view, memory, CardId.ABRA):
        return False
    attack_lines = sum(
        int(pokemon.id) in ATTACK_LINE_IDS
        for pokemon in view.field
    )
    if attack_lines != 1:
        return False
    immediate_search = any(
        option.type == int(OptionType.PLAY)
        and option.card_id in (
            int(CardId.BUDDY_BUDDY_POFFIN),
            int(CardId.POKE_PAD),
            int(CardId.DAWN),
        )
        and option.card_serial is not None
        for option in view.options
    )
    return immediate_search or _has_immediate_random_draw_route(view)


def _must_restore_third_attack_line_before_ko(
    view,
    memory,
    discard_ids: tuple[int, ...],
) -> bool:
    """2本盤面で山札のケーシィが尽きた時だけ、灰から3本目を再建する。"""
    if (
        int(CardId.ABRA) not in discard_ids
        or not needs_continuity_setup(view)
        or card_may_be_in_deck(view, memory, CardId.ABRA)
        or attack_line_count(view) != MINIMUM_ATTACK_LINES - 1
        or not spend_preserves_immediate_ko(view, cards_spent=2)
    ):
        return False
    immediate_rebuild_route = any(
        option.type == int(OptionType.PLAY)
        and option.card_id in (
            int(CardId.BUDDY_BUDDY_POFFIN),
            int(CardId.POKE_PAD),
            int(CardId.DAWN),
        )
        and option.card_serial is not None
        for option in view.options
    )
    return immediate_rebuild_route or _has_immediate_random_draw_route(view)


def _must_restore_lone_attack_line_before_ko(
    view,
    discard_ids: tuple[int, ...],
) -> bool:
    """検索札が尽きても、次番用の進化前を山札へ戻してから非最終KOする。"""
    if int(CardId.ABRA) not in discard_ids or not needs_continuity_setup(view):
        return False
    attack_lines = sum(
        int(pokemon.id) in ATTACK_LINE_IDS
        for pokemon in view.field
    )
    discarded_attack_lines = sum(
        card_id in ATTACK_LINE_IDS
        for card_id in discard_ids
    )
    return attack_lines == 1 and discarded_attack_lines >= 2


def _has_immediate_random_draw_route(view) -> bool:
    """灰で戻した直後に、検索ではない公開ドローを開始できるか。"""
    return any(
        (
            option.type == int(OptionType.ABILITY)
            and option.card_id in (
                int(CardId.DUDUNSPARCE),
                int(CardId.FEZANDIPITI_EX),
            )
        )
        or (
            option.type == int(OptionType.EVOLVE)
            and option.card_id in (
                int(CardId.DUDUNSPARCE),
                int(CardId.KADABRA),
            )
        )
        for option in view.options
    )


def _must_recycle_next_alakazam_before_search(
    view,
    memory,
    discard_ids: tuple[int, ...],
) -> bool:
    if (
        int(CardId.ALAKAZAM) not in discard_ids
        or int(CardId.ALAKAZAM) in view.hand_ids
        or card_may_be_in_deck(view, memory, CardId.ALAKAZAM)
        or not nonfinal_immediate_ko(view)
    ):
        return False
    current_attacker_exists = any(
        int(pokemon.id) == int(CardId.ALAKAZAM)
        and view.has_psychic_energy(pokemon)
        for pokemon in view.field
    )
    mature_reserve_exists = any(
        int(pokemon.id) == int(CardId.KADABRA)
        and not pokemon.appear_this_turn
        for pokemon in view.bench
    )
    if not current_attacker_exists or not mature_reserve_exists:
        return False
    return any(
        option.type == int(OptionType.PLAY)
        and option.card_id in (
            int(CardId.POKE_PAD),
            int(CardId.HILDA),
            int(CardId.DAWN),
        )
        and option.card_serial is not None
        for option in view.options
    )


def _must_recycle_next_alakazam_before_draw(
    view,
    memory,
    discard_ids: tuple[int, ...],
) -> bool:
    if (
        int(CardId.ALAKAZAM) not in discard_ids
        or int(CardId.ALAKAZAM) in view.hand_ids
        or card_may_be_in_deck(view, memory, CardId.ALAKAZAM)
        or not nonfinal_immediate_ko(view)
        or not _has_immediate_random_draw_route(view)
    ):
        return False
    current_attacker_exists = any(
        int(pokemon.id) == int(CardId.ALAKAZAM)
        and view.has_psychic_energy(pokemon)
        for pokemon in view.field
    )
    powered_mature_reserve_exists = any(
        int(pokemon.id) == int(CardId.KADABRA)
        and not pokemon.appear_this_turn
        and view.has_psychic_energy(pokemon)
        for pokemon in view.bench
    )
    return current_attacker_exists and powered_mature_reserve_exists


def _sacred_ash_proposal(view, memory, discard_ids: tuple[int, ...]) -> Proposal | None:
    all_targets = _ordered_present(SACRED_ASH_PRIORITY, discard_ids)
    if not all_targets:
        return None
    option = _play_option(view, CardId.SACRED_ASH)
    if option is None:
        return None
    discarded_alakazam_count = discard_ids.count(int(CardId.ALAKAZAM))
    emergency_rebuild = _can_immediately_rebuild_attack_lines(
        view,
        memory,
        discard_ids,
    )
    third_line_recycle = _must_restore_third_attack_line_before_ko(
        view,
        memory,
        discard_ids,
    )
    lone_line_recycle = _must_restore_lone_attack_line_before_ko(
        view,
        discard_ids,
    )
    next_alakazam_recycle = _must_recycle_next_alakazam_before_search(
        view,
        memory,
        discard_ids,
    )
    next_alakazam_draw_recycle = _must_recycle_next_alakazam_before_draw(
        view,
        memory,
        discard_ids,
    )
    deckout_recycle = (
        int(view.own.get("deckCount", 0))
        <= minimum_deck_reserve(view)
    )
    if (
        discarded_alakazam_count < 2
        and not emergency_rebuild
        and not third_line_recycle
        and not lone_line_recycle
        and not next_alakazam_recycle
        and not next_alakazam_draw_recycle
        and not deckout_recycle
    ):
        return None
    targeted_single_alakazam = (
        not deckout_recycle
        and discarded_alakazam_count == 1
        and (
            next_alakazam_recycle
            or next_alakazam_draw_recycle
        )
    )
    targets = (
        (int(CardId.ALAKAZAM),)
        if targeted_single_alakazam
        else all_targets
    )
    intent = PendingIntent.from_view(
        view,
        kind="RECOVER_POKEMON_LINES",
        card_ids=targets,
        card_groups=_sacred_ash_card_groups(targets),
        max_cards=5,
        metadata=(
            ("reason", "攻撃・進化・大量ドロー・対策の役割順にポケモンを再利用する"),
            ("priority", ",".join(str(card_id) for card_id in targets)),
        ),
        effect_card_id=CardId.SACRED_ASH,
        effect_serial=option.card_serial,
        remaining_contexts=(SelectContext.TO_DECK,),
    )
    return Proposal(
        (option.position,),
        CONTINUITY_BULK_RECYCLE_PRIORITY,
        (
            "山札が勝利までの最低残数に達したため、聖なる灰でポケモンを戻して山札切れを防ぐ"
            if deckout_recycle
            else "山札のケーシィが尽きて現在の攻撃役しか残っていないため聖なる灰で戻し、"
            "手札の検索札から非最終KO前に控えを再建する"
            if emergency_rebuild
            else "山札のケーシィが尽きて攻撃系統が2本のため、聖なる灰で戻して"
            "現在のKO打点を保ったまま連続KO用の3本目を再建する"
            if third_line_recycle
            else "次番の超付きユンゲラーを進化させるフーディンが山札にないため、"
            "ノココッチ等で引く前に聖なる灰で戻す"
            if next_alakazam_draw_recycle
            else "次番の古いユンゲラーを進化させるフーディンが山札にないため、"
            "検索札を使う前に聖なる灰で戻す"
            if next_alakazam_recycle
            else "現在の攻撃役しか残っていないため、次番用のケーシィ系を"
            "聖なる灰で山札へ戻してから非最終KOする"
            if lone_line_recycle
            else "フーディンが2枚落ちるまで温存した聖なる灰で一括復旧し、連続KO用の3系統を循環させる"
        ),
        (
            "PLAYBOOK-SACRED-ASH",
            "PLAYBOOK-BOARD-MINIMUM",
            "PLAYBOOK-STOP-WHEN-KO",
        ),
        intent,
    )


def _is_known_ruleless_pokemon(view, card_id: int) -> bool:
    value = int(card_id)
    if value in LANA_RULELESS_PRIORITY:
        return True
    meta = view.catalog.card(value)
    return (
        meta is not None
        and meta.card_type == int(CardType.POKEMON)
        and not (meta.ex or meta.mega_ex or meta.tera)
    )


def _lana_targets(view, discard_ids: tuple[int, ...]) -> tuple[int, ...]:
    present = set(int(card_id) for card_id in discard_ids)
    recovered_basic_is_urgent = (
        int(CardId.BASIC_PSYCHIC) in present
        and not any(
            int(card_id) in (
                int(CardId.BASIC_PSYCHIC),
                int(CardId.TELEPATH_PSYCHIC_ENERGY),
            )
            for card_id in view.hand_ids
        )
        and any(
            int(pokemon.id) in ATTACK_LINE_IDS
            and not view.has_psychic_energy(pokemon)
            for pokemon in view.field
        )
    )
    fixed_priority = (
        (
            int(CardId.BASIC_PSYCHIC),
            int(CardId.ABRA),
            *(
                card_id
                for card_id in LANA_RULELESS_PRIORITY
                if card_id != int(CardId.ABRA)
            ),
        )
        if recovered_basic_is_urgent
        else LANA_RULELESS_PRIORITY
    )
    fixed = list(_ordered_present(fixed_priority, discard_ids))
    fixed_set = set(fixed)
    additional_ruleless = sorted(
        card_id
        for card_id in present
        if card_id not in fixed_set
        and card_id != int(CardId.FEZANDIPITI_EX)
        and _is_known_ruleless_pokemon(view, card_id)
    )
    targets = [*fixed, *additional_ruleless]
    if (
        int(CardId.BASIC_PSYCHIC) in present
        and int(CardId.BASIC_PSYCHIC) not in fixed_set
    ):
        targets.append(int(CardId.BASIC_PSYCHIC))
    return tuple(targets)


def _lana_card_groups(
    view,
    discard_ids: tuple[int, ...],
    targets: tuple[int, ...],
) -> tuple[tuple[int, ...], ...]:
    """回収上限3枚を、進化先・攻撃エネルギー・自由枠に分ける。"""
    present = set(int(card_id) for card_id in discard_ids)
    alakazam_role_needed = (
        int(CardId.ALAKAZAM) in present
        and int(CardId.ALAKAZAM) not in view.hand_ids
        and any(
            int(pokemon.id) in (int(CardId.ABRA), int(CardId.KADABRA))
            for pokemon in view.field
        )
    )
    current_and_reserve_recovery = _lana_completes_current_and_reserve(
        view,
        discard_ids,
    )
    abra_role_needed = (
        int(CardId.ABRA) in present
        and (
            needs_continuity_setup(view)
            or current_and_reserve_recovery
        )
    )
    basic_role_needed = (
        int(CardId.BASIC_PSYCHIC) in present
        and not any(
            int(card_id) in (
                int(CardId.BASIC_PSYCHIC),
                int(CardId.TELEPATH_PSYCHIC_ENERGY),
            )
            for card_id in view.hand_ids
        )
        and any(
            int(pokemon.id) in ATTACK_LINE_IDS
            and not view.has_psychic_energy(pokemon)
            for pokemon in view.field
        )
    )
    role_requirements = (
        (
            (int(CardId.ALAKAZAM), alakazam_role_needed),
            (int(CardId.BASIC_PSYCHIC), basic_role_needed),
            (int(CardId.ABRA), abra_role_needed),
        )
        if current_and_reserve_recovery
        else (
            (int(CardId.ALAKAZAM), alakazam_role_needed),
            (int(CardId.ABRA), abra_role_needed),
            (int(CardId.BASIC_PSYCHIC), basic_role_needed),
        )
    )
    reserved_roles = tuple(
        card_id
        for card_id, needed in role_requirements
        if needed
    )
    if not reserved_roles:
        return tuple(targets for _ in range(3))

    fallback = tuple(
        card_id for card_id in targets if card_id not in reserved_roles
    ) + reserved_roles
    groups = [(card_id,) for card_id in reserved_roles]
    groups.extend(fallback for _ in range(3 - len(groups)))
    return tuple(groups)


def _lana_completes_current_and_reserve(
    view,
    discard_ids: tuple[int, ...],
) -> bool:
    """古いユンゲラーの完成と次のケーシィ回収を同時に行えるか。"""
    return (
        int(CardId.ALAKAZAM) in discard_ids
        and int(CardId.ABRA) in discard_ids
        and int(CardId.ALAKAZAM) not in view.hand_ids
        and any(
            int(pokemon.id) == int(CardId.KADABRA)
            and not pokemon.appear_this_turn
            for pokemon in view.field
        )
    )


def _lanas_aid_proposal(
    view,
    memory,
    discard_ids: tuple[int, ...],
) -> Proposal | None:
    targets = _lana_targets(view, discard_ids)
    if not targets:
        return None
    option = _play_option(view, CardId.LANAS_AID)
    if option is None:
        return None
    active = view.active
    active_alakazam_needs_psychic = (
        active is not None
        and int(active.id) == int(CardId.ALAKAZAM)
        and not view.has_psychic_energy(active)
        and not bool(view.current.get("energyAttached", False))
        and not any(
            int(card_id) in (
                int(CardId.BASIC_PSYCHIC),
                int(CardId.TELEPATH_PSYCHIC_ENERGY),
            )
            for card_id in view.hand_ids
        )
    )
    free_evolution_draw_available = any(
        candidate.type == int(OptionType.EVOLVE)
        and candidate.card_id in (
            int(CardId.KADABRA),
            int(CardId.ALAKAZAM),
        )
        for candidate in view.options
    )
    if active_alakazam_needs_psychic and free_evolution_draw_available:
        # 先に無料の進化時ドローを解決すれば、超エネルギーを自然に引いて
        # サポート権を後続準備へ残せる可能性がある。スイレンを先に使うと、
        # 引いた後もトウコへ切り替えられず、実戦で初回攻撃を逃していた。
        return None
    intent = PendingIntent.from_view(
        view,
        kind="RECOVER_RULELESS_AND_BASIC_PSYCHIC",
        card_ids=targets,
        card_groups=_lana_card_groups(view, discard_ids, targets),
        max_cards=3,
        metadata=(
            ("reason", "ルールを持たない盤面役と基本超だけを手札へ戻す"),
            ("priority", ",".join(str(card_id) for card_id in targets)),
        ),
        effect_card_id=CardId.LANAS_AID,
        effect_serial=option.card_serial,
        remaining_contexts=(SelectContext.TO_HAND,),
    )
    reserve_line_exists = any(
        int(pokemon.id) in (
            int(CardId.ABRA),
            int(CardId.KADABRA),
        )
        for pokemon in view.bench
    )
    discarded_alakazam_count = discard_ids.count(int(CardId.ALAKAZAM))
    current_and_reserve_recovery = _lana_completes_current_and_reserve(
        view,
        discard_ids,
    )
    bulk_alakazam_recovery = (
        discarded_alakazam_count >= 2
        and reserve_line_exists
        and nonfinal_immediate_ko(view)
    )
    direct_alakazam_recovery = (
        int(CardId.ALAKAZAM) in discard_ids
        and int(CardId.ALAKAZAM) not in view.hand_ids
        and reserve_line_exists
    )
    direct_energy_recovery = (
        int(CardId.BASIC_PSYCHIC) in discard_ids
        and not any(
            int(card_id) in (
                int(CardId.BASIC_PSYCHIC),
                int(CardId.TELEPATH_PSYCHIC_ENERGY),
            )
            for card_id in view.hand_ids
        )
        and any(
            int(pokemon.id) in (
                int(CardId.ABRA),
                int(CardId.KADABRA),
                int(CardId.ALAKAZAM),
            )
            and not view.has_psychic_energy(pokemon)
            for pokemon in view.field
        )
    )
    hilda_can_supply_alakazam = (
        int(CardId.ALAKAZAM) in view.hand_ids
        or card_may_be_in_deck(view, memory, CardId.ALAKAZAM)
    )
    hilda_can_finish_unpowered_attacker = (
        any(
            int(pokemon.id) == int(CardId.ALAKAZAM)
            and not view.has_psychic_energy(pokemon)
            for pokemon in view.field
        )
        or (
            hilda_can_supply_alakazam
            and any(
                int(pokemon.id) == int(CardId.KADABRA)
                and not pokemon.appear_this_turn
                and not view.has_psychic_energy(pokemon)
                for pokemon in view.field
            )
        )
        or (
            hilda_can_supply_alakazam
            and int(CardId.RARE_CANDY) in view.hand_ids
            and any(
                not view.has_psychic_energy(pokemon)
                for pokemon in view.eligible_abras
            )
        )
    )
    current_attack_energy_is_unresolved = (
        not direct_energy_recovery
        and not any(
            int(pokemon.id) == int(CardId.ALAKAZAM)
            and view.has_psychic_energy(pokemon)
            for pokemon in view.field
        )
        and not any(
            int(card_id) in (
                int(CardId.BASIC_PSYCHIC),
                int(CardId.TELEPATH_PSYCHIC_ENERGY),
            )
            for card_id in view.hand_ids
        )
        and hilda_can_finish_unpowered_attacker
    )
    direct_abra_recovery = (
        int(CardId.ABRA) in discard_ids
        and needs_continuity_setup(view)
    )
    direct_continuity_recovery = (
        direct_alakazam_recovery
        or direct_energy_recovery
        or direct_abra_recovery
    )
    continuity_recovery = direct_continuity_recovery or (
        int(CardId.ABRA) in discard_ids
        and needs_continuity_setup(view)
    )
    maturity_search_available = (
        reserve_abra_needs_kadabra(view)
        and card_may_be_in_deck(view, memory, CardId.KADABRA)
        and any(
            option.type == int(OptionType.PLAY)
            and option.card_id in (
                int(CardId.POKE_PAD),
                int(CardId.HILDA),
                int(CardId.DAWN),
            )
            for option in view.options
        )
    )
    if current_and_reserve_recovery:
        reason = (
            "スイレンのお世話で現在のユンゲラー用フーディンと次のケーシィを同時に戻し、"
            "攻撃完成と後続再建を両立する"
        )
    elif direct_alakazam_recovery and direct_energy_recovery:
        reason = (
            "他のサポートより先にスイレンのお世話でフーディンと基本超を戻し、"
            "次番の攻撃役を完成させる"
        )
    elif bulk_alakazam_recovery:
        reason = (
            "非最終KO前にスイレンのお世話で落ちたフーディン2枚以上を直接戻し、"
            "聖なる灰を引けない試合でも後続進化を循環させる"
        )
    elif direct_alakazam_recovery:
        reason = (
            "他のサポートより先にスイレンのお世話でフーディンを直接戻し、"
            "次番の進化先を確保する"
        )
    elif direct_energy_recovery:
        reason = (
            "他のサポートより先にスイレンのお世話で基本超を戻し、"
            "現在または後続フーディンの攻撃エネルギーを予約する"
        )
    elif direct_abra_recovery:
        reason = (
            "山札の不確実な検索より先にスイレンのお世話でケーシィを直接戻し、"
            "攻撃役を含む3系統を確実に再建する"
        )
    elif continuity_recovery:
        reason = (
            "非最終KO前にスイレンのお世話でケーシィを戻し、"
            "次々ターンまでの攻撃系統を準備する"
        )
    else:
        reason = "ルールを持たないポケモンと基本超を手札へ復旧する"
    priority = (
        750
        if current_attack_energy_is_unresolved
        else CURRENT_AND_RESERVE_DIRECT_RECOVERY_PRIORITY
        if current_and_reserve_recovery
        else CONTINUITY_GUARANTEED_RECOVERY_PRIORITY
        if bulk_alakazam_recovery
        else CONTINUITY_GUARANTEED_RECOVERY_PRIORITY
        if direct_abra_recovery
        else CONTINUITY_DIRECT_RECOVERY_PRIORITY
        if direct_continuity_recovery
        else CONTINUITY_RECOVERY_PRIORITY
        if continuity_recovery
        else 750
    )
    if maturity_search_available:
        priority = min(priority, CONTINUITY_MATURITY_SEARCH_PRIORITY - 1)
    return Proposal(
        (option.position,),
        priority,
        reason,
        (
            "PLAYBOOK-LANAS-AID",
            "PLAYBOOK-BOARD-MINIMUM",
            "PLAYBOOK-STOP-WHEN-KO",
        ),
        intent,
    )


@covers(
    "FLOW-DEVELOP-ALAKAZAM",
    "PLAYBOOK-PROMOTE-COMPLETE",
    "PLAYBOOK-SACRED-ASH",
    "PLAYBOOK-LANAS-AID",
    "PLAYBOOK-BOARD-MINIMUM",
    "PLAYBOOK-STOP-WHEN-KO",
)
def propose_recovery(view, memory) -> Proposal | None:
    promotion = _forced_promotion(view)
    if promotion is not None:
        return promotion
    if not _is_main_selection(view):
        return None

    discard_ids = _discard_ids(view)
    proposals = (
        (
            _sacred_ash_proposal(view, memory, discard_ids)
            if spend_preserves_immediate_ko(view)
            else None
        ),
        _lanas_aid_proposal(view, memory, discard_ids),
    )
    return max(
        (proposal for proposal in proposals if proposal is not None),
        key=lambda proposal: (
            proposal.priority,
            -proposal.option_indices[0],
        ),
        default=None,
    )
