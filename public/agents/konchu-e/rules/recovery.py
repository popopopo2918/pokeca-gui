from __future__ import annotations

from dataclasses import dataclass

from cards import CardId
from memory import card_may_be_in_deck, possible_deck_count
from model import Area, OptionType, SelectContext, SelectType
from proposals import PendingIntent, Proposal, covers
from rules.board_plan import (
    ATTACK_LINE_IDS,
    MINIMUM_ATTACK_LINES,
    attack_line_count,
    is_opening_attack_phase,
    reserve_abra_needs_kadabra,
)
from rules.continuity import (
    CONTINUITY_BULK_RECYCLE_PRIORITY,
    CONTINUITY_DIRECT_RECOVERY_PRIORITY,
    CONTINUITY_GUARANTEED_RECOVERY_PRIORITY,
    CONTINUITY_MATURITY_SEARCH_PRIORITY,
    CONTINUITY_RECOVERY_PRIORITY,
    CURRENT_AND_RESERVE_DIRECT_RECOVERY_PRIORITY,
    immediate_ko_ends_game,
    needs_continuity_setup,
    nonfinal_immediate_ko,
    spend_preserves_immediate_ko,
)
from rules.deck_safety import (
    DECK_SAFETY_THRESHOLD,
    minimum_deck_reserve,
    minimum_deck_reserve_after_prizes,
)


SACRED_ASH_PRIORITY = (
    int(CardId.ABRA),
    int(CardId.KADABRA),
    int(CardId.ALAKAZAM),
)

LANA_RULELESS_PRIORITY = SACRED_ASH_PRIORITY

_SACRED_ASH_ONE_LINE_SLOTS = (
    int(CardId.ABRA),
    int(CardId.KADABRA),
    int(CardId.ALAKAZAM),
)

_SACRED_ASH_TWO_LINE_SLOTS = (
    int(CardId.ABRA),
    int(CardId.ABRA),
    int(CardId.KADABRA),
    int(CardId.ALAKAZAM),
    int(CardId.ALAKAZAM),
)

PROMOTION_PRIORITY = {
    int(CardId.ALAKAZAM): 4,
    int(CardId.KADABRA): 5,
    int(CardId.ABRA): 6,
    int(CardId.DUNSPARCE): 7,
    int(CardId.DUDUNSPARCE): 8,
    int(CardId.FAN_ROTOM): 5,
    int(CardId.PSYDUCK): 7,
    int(CardId.SHAYMIN): 8,
    int(CardId.GENESECT): 9,
    int(CardId.FEZANDIPITI_EX): 10,
}

_ONE_RETREAT_IDS = frozenset({
    int(CardId.ABRA),
    int(CardId.KADABRA),
    int(CardId.ALAKAZAM),
    int(CardId.DUNSPARCE),
    int(CardId.FEZANDIPITI_EX),
})

_ATTACK_PSYCHIC_IDS = frozenset({
    int(CardId.BASIC_PSYCHIC),
    int(CardId.TELEPATH_PSYCHIC_ENERGY),
})


@dataclass(frozen=True)
class NightStretcherRoute:
    target_serial: int
    purpose: str


@dataclass(frozen=True)
class ProactiveRecoveryPlan:
    required_lines: int
    accessible_lines: int
    missing_lines: int
    card_groups: tuple[tuple[int, ...], ...]
    follow_up_card_id: int | None
    follow_up_card_serial: int | None


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


def _active_can_leave_without_new_energy(view) -> bool:
    active = view.active
    if active is None:
        return False
    if any(option.type == int(OptionType.RETREAT) for option in view.options):
        return True
    return any(
        option.type in (int(OptionType.ABILITY), int(OptionType.SKILL))
        and option.card_id == int(CardId.DUDUNSPARCE)
        and option.source is not None
        and option.source.serial == active.serial
        for option in view.options
    )


def _can_become_alakazam_this_turn(view, pokemon) -> bool:
    if int(pokemon.id) == int(CardId.ALAKAZAM):
        return True
    if int(pokemon.id) == int(CardId.KADABRA):
        return (
            not pokemon.appear_this_turn
            and int(CardId.ALAKAZAM) in view.hand_ids
        )
    return (
        int(pokemon.id) == int(CardId.ABRA)
        and not pokemon.appear_this_turn
        and int(CardId.RARE_CANDY) in view.hand_ids
        and int(CardId.ALAKAZAM) in view.hand_ids
    )


def _has_legal_attack_psychic_attach(view, target_serial: int) -> bool:
    return any(
        option.type == int(OptionType.ATTACH)
        and option.card_id in _ATTACK_PSYCHIC_IDS
        and option.target is not None
        and option.target.serial == int(target_serial)
        for option in view.options
    )


@covers("PLAYBOOK-NIGHT-STRETCHER")
def night_stretcher_basic_psychic_route(
    view,
    memory=None,
) -> NightStretcherRoute | None:
    """夜のタンカで戻す基本超を、その番の攻撃または退避へ接続する。"""
    del memory
    if (
        not _is_main_selection(view)
        or bool(view.current.get("energyAttached", False))
        or int(CardId.BASIC_PSYCHIC) in view.hand_ids
        or int(CardId.BASIC_PSYCHIC) not in _discard_ids(view)
    ):
        return None

    active = view.active
    if (
        active is not None
        and not view.has_psychic_energy(active)
        and _can_become_alakazam_this_turn(view, active)
        and active.serial is not None
    ):
        target_serial = int(active.serial)
        if not _has_legal_attack_psychic_attach(view, target_serial):
            return NightStretcherRoute(target_serial, "attack_energy")

    if _active_can_leave_without_new_energy(view):
        target = min(
            (
                pokemon
                for pokemon in view.bench
                if not view.has_psychic_energy(pokemon)
                and _can_become_alakazam_this_turn(view, pokemon)
                and pokemon.serial is not None
            ),
            key=lambda pokemon: int(pokemon.serial),
            default=None,
        )
        if target is not None:
            target_serial = int(target.serial)
            if not _has_legal_attack_psychic_attach(view, target_serial):
                return NightStretcherRoute(target_serial, "attack_energy")

    powered_bench = any(
        int(pokemon.id) == int(CardId.ALAKAZAM)
        and view.has_psychic_energy(pokemon)
        for pokemon in view.bench
    )
    if (
        active is not None
        and active.serial is not None
        and int(active.id) in _ONE_RETREAT_IDS
        and not active.energy_card_ids
        and powered_bench
    ):
        target_serial = int(active.serial)
        if not _has_legal_attack_psychic_attach(view, target_serial):
            return NightStretcherRoute(target_serial, "retreat_energy")
    return None


@covers("PLAYBOOK-NIGHT-STRETCHER", "PLAYBOOK-SEARCH-INTENT")
def _night_stretcher_proposal(view, memory) -> Proposal | None:
    route = night_stretcher_basic_psychic_route(view, memory)
    option = _play_option(view, CardId.NIGHT_STRETCHER)
    if route is None or option is None:
        return None
    intent = PendingIntent.from_view(
        view,
        kind="NIGHT_STRETCHER_BASIC_PSYCHIC",
        card_ids=(CardId.BASIC_PSYCHIC,),
        card_groups=((CardId.BASIC_PSYCHIC,),),
        target_serial=route.target_serial,
        max_cards=1,
        metadata=(("purpose", route.purpose),),
        effect_card_id=CardId.NIGHT_STRETCHER,
        effect_serial=option.card_serial,
        remaining_contexts=(SelectContext.TO_HAND,),
    )
    return Proposal(
        (option.position,),
        998,
        (
            "夜のタンカで基本超を戻し、前をにがして超付きフーディンを攻撃位置へ出す"
            if route.purpose == "retreat_energy"
            else "夜のタンカで基本超を戻し、その番のフーディン攻撃を完成する"
        ),
        ("PLAYBOOK-NIGHT-STRETCHER", "PLAYBOOK-SEARCH-INTENT"),
        intent,
    )


def _forced_promotion(view, memory) -> Proposal | None:
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
        and (
            option.source.player_index is None
            or option.source.player_index == view.own_index
        )
        and option.source.serial is not None
    ]
    if not options:
        return None

    alakazam_is_available_now = (
        int(CardId.ALAKAZAM) in view.hand_ids
        or (
            int(CardId.POKE_PAD) in view.hand_ids
            and card_may_be_in_deck(view, memory, CardId.ALAKAZAM)
        )
    )

    def powered_line_can_complete_now(pokemon) -> bool:
        if pokemon.appear_this_turn or not pokemon.has_psychic_energy:
            return False
        if int(pokemon.id) == int(CardId.KADABRA):
            return alakazam_is_available_now
        if int(pokemon.id) == int(CardId.ABRA):
            return (
                int(CardId.RARE_CANDY) in view.hand_ids
                and alakazam_is_available_now
            )
        return False

    psychic_is_attachable_now = any(
        int(card_id) in (
            int(CardId.BASIC_PSYCHIC),
            int(CardId.TELEPATH_PSYCHIC_ENERGY),
        )
        for card_id in view.hand_ids
    )

    def line_can_attack_now(pokemon) -> bool:
        if int(pokemon.id) == int(CardId.ALAKAZAM):
            return pokemon.has_psychic_energy or psychic_is_attachable_now
        if powered_line_can_complete_now(pokemon):
            return True
        if pokemon.appear_this_turn or not psychic_is_attachable_now:
            return False
        if int(pokemon.id) == int(CardId.KADABRA):
            return alakazam_is_available_now
        if int(pokemon.id) == int(CardId.ABRA):
            return (
                int(CardId.RARE_CANDY) in view.hand_ids
                and alakazam_is_available_now
            )
        return False

    def unpowered_line_should_go_directly_active(pokemon) -> bool:
        if (
            int(pokemon.id) not in (int(CardId.ABRA), int(CardId.KADABRA))
            or not line_can_attack_now(pokemon)
        ):
            return False
        if is_opening_attack_phase(view):
            return True
        required_hand = view.required_hand_for_active_ko
        if required_hand is None:
            return False
        projected_hand = int(view.hand_size) + 1
        if int(pokemon.id) == int(CardId.KADABRA):
            projected_hand += 1
        return projected_hand >= int(required_hand)

    protect_old_attack_line_with_wall = (
        is_opening_attack_phase(view)
        and int(view.own_turn_number) >= 2
        and any(
            not option.source.appear_this_turn
            and int(option.source.id) in (
                int(CardId.ABRA),
                int(CardId.KADABRA),
            )
            for option in options
        )
        and any(
            int(option.source.id) == int(CardId.DUNSPARCE)
            for option in options
        )
        and not any(line_can_attack_now(option.source) for option in options)
    )

    def dudunsparce_route_is_safe(pokemon) -> bool:
        deck_after_next_draw = max(
            0,
            int(view.own.get("deckCount", 0)) - 1,
        )
        if deck_after_next_draw > DECK_SAFETY_THRESHOLD:
            return True
        if int(pokemon.id) == int(CardId.DUDUNSPARCE):
            returned = (
                1
                + len(pokemon.pre_evolution_ids)
                + len(pokemon.energy_card_ids)
                + len(pokemon.tool_ids)
            )
        else:
            returned = (
                2
                + len(pokemon.energy_card_ids)
                + len(pokemon.tool_ids)
            )
        available = deck_after_next_draw + returned
        projected = available - min(3, available)
        return projected >= minimum_deck_reserve_after_prizes(view, 0)

    def rank(option) -> tuple[int, int, int, int, int]:
        pokemon = option.source
        if (
            pokemon.id == int(CardId.ALAKAZAM)
            and pokemon.has_psychic_energy
        ):
            role = 0
        elif powered_line_can_complete_now(pokemon):
            role = 1
        elif (
            int(pokemon.id) == int(CardId.ALAKAZAM)
            and line_can_attack_now(pokemon)
        ):
            role = 1
        elif unpowered_line_should_go_directly_active(pokemon):
            role = 1
        elif (
            pokemon.id == int(CardId.DUDUNSPARCE)
            and dudunsparce_route_is_safe(pokemon)
        ):
            role = 2
        elif (
            pokemon.id == int(CardId.DUNSPARCE)
            and int(CardId.DUDUNSPARCE) in view.hand_ids
            and dudunsparce_route_is_safe(pokemon)
        ):
            role = 3
        elif (
            protect_old_attack_line_with_wall
            and pokemon.id == int(CardId.DUNSPARCE)
        ):
            role = 4
        else:
            role = PROMOTION_PRIORITY.get(int(pokemon.id), 100)
        return (
            role,
            0 if pokemon.has_psychic_energy else 1,
            PROMOTION_PRIORITY.get(int(pokemon.id), 100),
            int(pokemon.serial),
            option.position,
        )

    chosen = min(options, key=rank)
    powered = chosen.source.has_psychic_energy and chosen.source.id in (
        int(CardId.ABRA),
        int(CardId.KADABRA),
        int(CardId.ALAKAZAM),
    )
    reason = (
        "今番に攻撃できないためノコッチを壁にし、古いケーシィ系統をベンチで守る"
        if (
            protect_old_attack_line_with_wall
            and chosen.source.id == int(CardId.DUNSPARCE)
        )
        else "ポケパッドで進化先を検索し、即攻撃まで完成できる超付き進化前を優先して前へ出す"
        if (
            powered_line_can_complete_now(chosen.source)
            and int(CardId.ALAKAZAM) not in view.hand_ids
        )
        else "超エネルギー付きで即攻撃まで完成できる進化前を優先して前へ出す"
        if powered_line_can_complete_now(chosen.source)
        else "手札の進化札と超エネルギーで即攻撃まで完成できる進化前を優先して前へ出す"
        if unpowered_line_should_go_directly_active(chosen.source)
        else "手札の超エネルギーで即攻撃できるフーディンを優先して前へ出す"
        if line_can_attack_now(chosen.source)
        else "超エネルギー付きの攻撃役を同じ進化段階の中で優先して前へ出す"
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
    discard_ids: tuple[int, ...],
    required_lines: int,
) -> tuple[tuple[int, ...], ...]:
    """必要ラインの優先枠を、トラッシュに実在する枚数だけ予約する。"""
    target_ids = set(int(card_id) for card_id in targets)
    remaining = {
        card_id: discard_ids.count(card_id)
        for card_id in SACRED_ASH_PRIORITY
    }
    priority = (
        _SACRED_ASH_ONE_LINE_SLOTS
        if required_lines == 1
        else _SACRED_ASH_TWO_LINE_SLOTS
    )
    groups: list[tuple[int, ...]] = []
    for card_id in priority:
        if card_id not in target_ids or remaining[card_id] <= 0:
            continue
        groups.append((card_id,))
        remaining[card_id] -= 1
    return tuple(groups)


def _required_recovery_lines(
    view,
    discard_ids: tuple[int, ...],
    memory=None,
) -> int:
    """公開情報で非ケーシィ系統のきぜつが確定した時だけ1ラインにする。"""
    if (
        memory is not None
        and bool(getattr(memory, "own_knockout_history_complete", False))
    ):
        non_attack_line_knockouts = max(
            0,
            int(getattr(memory, "own_total_knockouts", 0))
            - int(getattr(memory, "own_attack_line_knockouts", 0)),
        )
        return 1 if non_attack_line_knockouts > 0 else 2
    opponent_prizes_taken = 6 - len(view.opponent.get("prize") or [])
    discarded_abra_count = discard_ids.count(int(CardId.ABRA))
    return 1 if opponent_prizes_taken > discarded_abra_count else 2


def _immediate_basic_search_option(view):
    if (
        not _is_main_selection(view)
        or len(view.bench) >= int(view.own.get("benchMax", 5))
    ):
        return None
    for card_id in (
        int(CardId.BUDDY_BUDDY_POFFIN),
        int(CardId.POKE_PAD),
    ):
        option = min(
            (
                candidate
                for candidate in view.options
                if candidate.type == int(OptionType.PLAY)
                and candidate.card_id == card_id
                and candidate.card_serial is not None
            ),
            key=lambda candidate: (
                int(candidate.card_serial),
                candidate.position,
            ),
            default=None,
        )
        if option is not None:
            return option
    return None


def plan_proactive_attack_line_recovery(
    view,
    memory,
    *,
    cards_spent: int,
) -> ProactiveRecoveryPlan | None:
    discard_ids = _discard_ids(view)
    if (
        int(CardId.ABRA) not in discard_ids
        or immediate_ko_ends_game(view)
        or not nonfinal_immediate_ko(view)
    ):
        return None

    in_play = attack_line_count(view)
    in_hand = view.hand_ids.count(int(CardId.ABRA))
    in_deck = possible_deck_count(view, memory, CardId.ABRA)
    accessible = min(
        MINIMUM_ATTACK_LINES,
        in_play + in_hand + in_deck,
    )
    missing = max(0, MINIMUM_ATTACK_LINES - accessible)
    if missing == 0 or not spend_preserves_immediate_ko(view, cards_spent):
        return None

    required = _required_recovery_lines(view, discard_ids, memory)
    follow_up = _immediate_basic_search_option(view)
    targets = _ordered_present(SACRED_ASH_PRIORITY, discard_ids)
    return ProactiveRecoveryPlan(
        required_lines=required,
        accessible_lines=accessible,
        missing_lines=missing,
        card_groups=_sacred_ash_card_groups(
            targets,
            discard_ids,
            required,
        ),
        follow_up_card_id=(
            None if follow_up is None else int(follow_up.card_id)
        ),
        follow_up_card_serial=(
            None if follow_up is None else int(follow_up.card_serial)
        ),
    )


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
    preliminary = plan_proactive_attack_line_recovery(
        view,
        memory,
        cards_spent=1,
    )
    proactive_rebuild = None
    if preliminary is not None:
        proactive_rebuild = plan_proactive_attack_line_recovery(
            view,
            memory,
            cards_spent=(
                2 if preliminary.follow_up_card_id is not None else 1
            ),
        )
    required_recovery_lines = (
        proactive_rebuild.required_lines
        if proactive_rebuild is not None
        else _required_recovery_lines(view, discard_ids, memory)
    )
    discarded_alakazam_count = discard_ids.count(int(CardId.ALAKAZAM))
    normal_line_recovery = (
        discarded_alakazam_count >= required_recovery_lines
        and not immediate_ko_ends_game(view)
        and (
            (
                nonfinal_immediate_ko(view)
                and spend_preserves_immediate_ko(view)
            )
            or not is_opening_attack_phase(view)
        )
    )
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
        not normal_line_recovery
        and not emergency_rebuild
        and not third_line_recycle
        and not lone_line_recycle
        and not next_alakazam_recycle
        and not next_alakazam_draw_recycle
        and not deckout_recycle
        and proactive_rebuild is None
    ):
        return None
    targeted_single_alakazam = (
        not deckout_recycle
        and proactive_rebuild is None
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
        card_groups=(
            proactive_rebuild.card_groups
            if proactive_rebuild is not None
            else _sacred_ash_card_groups(
                targets,
                discard_ids,
                required_recovery_lines,
            )
        ),
        max_cards=3 if required_recovery_lines == 1 else 5,
        metadata=(
            (
                "reason",
                "進化待ち時間を消化するため、枯渇前にケーシィを戻す"
                if proactive_rebuild is not None
                else "必要なケーシィ系統だけをライン数に応じて再利用する",
            ),
            ("priority", ",".join(str(card_id) for card_id in targets)),
            *(
                (
                    (
                        "follow_up_card_id",
                        int(proactive_rebuild.follow_up_card_id),
                    ),
                    (
                        "follow_up_card_serial",
                        int(proactive_rebuild.follow_up_card_serial),
                    ),
                    ("purpose", "sacred_ash"),
                )
                if proactive_rebuild is not None
                and proactive_rebuild.follow_up_card_id is not None
                and proactive_rebuild.follow_up_card_serial is not None
                else ()
            ),
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
            else "進化待ち時間を消化するため、枯渇前にケーシィを聖なる灰で戻す"
            if proactive_rebuild is not None
            else "公開情報から1ライン回収で足りるため、聖なる灰でケーシィ系統を復旧する"
            if required_recovery_lines == 1
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
    return False


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
    targets = [*fixed]
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
    "PLAYBOOK-NIGHT-STRETCHER",
    "PLAYBOOK-BOARD-MINIMUM",
    "PLAYBOOK-STOP-WHEN-KO",
)
def propose_recovery(view, memory) -> Proposal | None:
    promotion = _forced_promotion(view, memory)
    if promotion is not None:
        return promotion
    if not _is_main_selection(view):
        return None

    discard_ids = _discard_ids(view)
    proposals = (
        _night_stretcher_proposal(view, memory),
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
