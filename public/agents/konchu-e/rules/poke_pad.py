from __future__ import annotations

from dataclasses import dataclass

from cards import CardId
from memory import card_may_be_in_deck
from model import OptionType
from rules.board_plan import (
    ATTACK_LINE_IDS,
    MAXIMUM_DRAW_LINES,
    MINIMUM_ATTACK_LINES,
    attack_line_count,
    draw_line_count,
    full_board_plan,
    is_opening_attack_phase,
    next_turn_surviving_field,
    powered_alakazam_exists,
    reserve_abra_needs_kadabra,
)
from rules.search import rank_full_board_search_candidates


@dataclass(frozen=True)
class PokePadTargetPlan:
    kind: str
    card_ids: tuple[int, ...]
    reason: str
    rule_ids: tuple[str, ...]


def _field_count(view, card_id: int | CardId) -> int:
    return sum(int(pokemon.id) == int(card_id) for pokemon in view.field)


def _field_or_hand_count(view, card_id: int | CardId) -> int:
    return _field_count(view, card_id) + sum(
        int(hand_id) == int(card_id) for hand_id in view.hand_ids
    )


FUTURE_ALAKAZAM_SEARCH_IDS = frozenset({
    int(CardId.POKE_PAD),
    int(CardId.HILDA),
    int(CardId.DAWN),
})


def must_reserve_future_alakazam_search(
    view,
    card_id: int | CardId,
    memory=None,
) -> bool:
    """次ターンの通常ドロー後まで、最後のフーディンサーチ手段を残す。"""
    if int(card_id) not in FUTURE_ALAKAZAM_SEARCH_IDS:
        return False
    fresh_kadabra_exists = any(
        int(pokemon.id) == int(CardId.KADABRA)
        and pokemon.appear_this_turn
        for pokemon in view.field
    )
    kadabra_will_be_fresh = any(
        option.type == int(OptionType.EVOLVE)
        and option.card_id == int(CardId.KADABRA)
        for option in view.options
    )
    next_turn_kadabra_ready = (
        int(CardId.KADABRA) in view.hand_ids
        and any(
            int(pokemon.id) == int(CardId.ABRA)
            for pokemon in view.field
        )
    )
    opening_candy_route_ready = (
        is_opening_attack_phase(view)
        and int(CardId.RARE_CANDY) in view.hand_ids
        and not any(
            int(pokemon.id) == int(CardId.ALAKAZAM)
            for pokemon in view.field
        )
        and any(
            int(pokemon.id) == int(CardId.ABRA)
            for pokemon in view.field
        )
    )
    if (
        not (
            fresh_kadabra_exists
            or kadabra_will_be_fresh
            or next_turn_kadabra_ready
            or opening_candy_route_ready
        )
        or int(CardId.ALAKAZAM) in view.hand_ids
        or not card_may_be_in_deck(view, memory, CardId.ALAKAZAM)
    ):
        return False

    search_insurance_count = sum(
        int(hand_id) in FUTURE_ALAKAZAM_SEARCH_IDS
        for hand_id in view.hand_ids
    )
    return int(card_id) in view.hand_ids and search_insurance_count <= 1


def must_reserve_poke_pad_for_fresh_kadabra(view, memory=None) -> bool:
    return must_reserve_future_alakazam_search(
        view,
        CardId.POKE_PAD,
        memory,
    )


def must_reserve_poke_pad_for_opening_chain(
    view,
    target_card_ids: tuple[int, ...],
    memory=None,
) -> bool:
    """初動の不足進化段階を検索し切るまで、余分なポケパッドを残す。"""

    if (
        not is_opening_attack_phase(view)
        or int(CardId.POKE_PAD) not in view.hand_ids
        or attack_line_count(view) < 2
        or any(
            int(pokemon.id) == int(CardId.ALAKAZAM)
            for pokemon in view.field
        )
    ):
        return False

    field_or_hand_ids = {
        *(int(pokemon.id) for pokemon in view.field),
        *(int(card_id) for card_id in view.hand_ids),
    }
    missing_kadabra = (
        int(CardId.RARE_CANDY) not in view.hand_ids
        and int(CardId.KADABRA) not in field_or_hand_ids
        and card_may_be_in_deck(view, memory, CardId.KADABRA)
    )
    missing_alakazam = (
        int(CardId.ALAKAZAM) not in field_or_hand_ids
        and card_may_be_in_deck(view, memory, CardId.ALAKAZAM)
    )
    required_single_searches = int(missing_kadabra) + int(missing_alakazam)
    if required_single_searches == 0:
        return False

    targets = {int(card_id) for card_id in target_card_ids}
    if (
        (missing_kadabra and int(CardId.KADABRA) in targets)
        or (missing_alakazam and int(CardId.ALAKAZAM) in targets)
        or (
            attack_line_count(view) == 0
            and int(CardId.ABRA) in targets
        )
    ):
        return False

    # ヒカリはたね・1進化・2進化を同時に取れるため、残っていれば
    # ポケパッド／トウコを2段階分それぞれ残す必要はない。
    if int(CardId.DAWN) in view.hand_ids:
        return False

    single_searches = sum(
        int(card_id) in (int(CardId.POKE_PAD), int(CardId.HILDA))
        for card_id in view.hand_ids
    )
    return single_searches == required_single_searches


def plan_poke_pad_targets(
    view,
    memory=None,
) -> tuple[PokePadTargetPlan, ...]:
    plans: list[PokePadTargetPlan] = []

    def add_group(
        kind: str,
        card_ids: tuple[int, ...],
        reason: str,
        rule_ids: tuple[str, ...],
    ) -> None:
        normalized = tuple(int(card_id) for card_id in card_ids)
        if not normalized or any(plan.card_ids == normalized for plan in plans):
            return
        plans.append(PokePadTargetPlan(kind, normalized, reason, rule_ids))

    def add(
        kind: str,
        card_id: int | CardId,
        reason: str,
        rule_ids: tuple[str, ...],
    ) -> None:
        card_ids = (int(card_id),)
        if not card_may_be_in_deck(view, memory, card_id):
            return
        add_group(kind, card_ids, reason, rule_ids)

    abra_exists = _field_or_hand_count(view, CardId.ABRA) > 0
    attack_line_material_count = attack_line_count(view) + sum(
        int(hand_id) == int(CardId.ABRA) for hand_id in view.hand_ids
    )
    surviving_attack_line_material_count = sum(
        int(pokemon.id) in ATTACK_LINE_IDS
        for pokemon in next_turn_surviving_field(view)
    ) + sum(
        int(hand_id) == int(CardId.ABRA) for hand_id in view.hand_ids
    )
    bench_space = max(0, int(view.own.get("benchMax", 5)) - len(view.bench))
    waiting_dunsparce_count = _field_count(view, CardId.DUNSPARCE)
    old_abra_count = sum(
        int(pokemon.id) == int(CardId.ABRA) and not pokemon.appear_this_turn
        for pokemon in view.field
    )
    old_dunsparce_count = sum(
        int(pokemon.id) == int(CardId.DUNSPARCE)
        and not pokemon.appear_this_turn
        for pokemon in view.field
    )
    hand_kadabra_count = view.hand_ids.count(int(CardId.KADABRA))
    field_kadabra_count = _field_count(view, CardId.KADABRA)
    old_kadabra_count = sum(
        int(pokemon.id) == int(CardId.KADABRA)
        and not pokemon.appear_this_turn
        for pokemon in view.field
    )
    hand_alakazam_count = view.hand_ids.count(int(CardId.ALAKAZAM))
    hand_dudunsparce_count = view.hand_ids.count(int(CardId.DUDUNSPARCE))
    active_id = (
        None
        if view.active is None
        else int(view.active.id)
    )
    active_line_can_complete_this_turn = (
        active_id == int(CardId.ALAKAZAM)
        or (
            view.active is not None
            and not view.active.appear_this_turn
            and hand_alakazam_count > 0
            and (
                active_id == int(CardId.KADABRA)
                or (
                    active_id == int(CardId.ABRA)
                    and int(CardId.RARE_CANDY) in view.hand_ids
                )
            )
        )
    )

    turn_one_kadabra_draw_route = (
        view.own_turn_number == 1
        and attack_line_count(view) > 0
        and waiting_dunsparce_count == 0
        and hand_kadabra_count == 0
        and field_kadabra_count == 0
        and int(CardId.RARE_CANDY) not in view.hand_ids
    )
    if turn_one_kadabra_draw_route:
        add(
            "SEARCH_KADABRA_FOR_T2_DRAW",
            CardId.KADABRA,
            "1ターン目にユンゲラーを確保し、2ターン目の2枚ドローと3ターン目の通常進化を同時に準備する",
            (
                "PLAYBOOK-POKE-PAD",
                "PLAYBOOK-T3-KADABRA",
                "PLAYBOOK-MAX-DRAW",
                "PLAYBOOK-SEARCH-INTENT",
            ),
        )

    turn_two_kadabra_route = (
        view.own_turn_number == 2
        and old_abra_count > 0
        and hand_kadabra_count == 0
        and field_kadabra_count == 0
        and int(CardId.RARE_CANDY) not in view.hand_ids
    )
    if turn_two_kadabra_route:
        add(
            "SEARCH_KADABRA_FOR_T3",
            CardId.KADABRA,
            "2ターン目にふしぎなアメが無いため、古いケーシィをユンゲラーへ進化して2枚引き、3ターン目の通常進化も確保する",
            (
                "PLAYBOOK-POKE-PAD",
                "PLAYBOOK-T3-KADABRA",
                "PLAYBOOK-SEARCH-INTENT",
            ),
        )
    if reserve_abra_needs_kadabra(view):
        add(
            "SEARCH_KADABRA_FOR_CONTINUITY",
            CardId.KADABRA,
            "現在のフーディンが攻撃する前に、古い後続ケーシィ用のユンゲラーを確保する",
            (
                "PLAYBOOK-POKE-PAD",
                "PLAYBOOK-T3-KADABRA",
                "PLAYBOOK-BOARD-MINIMUM",
                "PLAYBOOK-SEARCH-INTENT",
            ),
        )
    if (
        is_opening_attack_phase(view)
        and bench_space > 0
        and view.active is not None
        and int(view.active.id) in ATTACK_LINE_IDS
        and not active_line_can_complete_this_turn
        and surviving_attack_line_material_count == 0
    ):
        add(
            "SEARCH_ABRA_FOR_SAFE_BENCH",
            CardId.ABRA,
            "バトル場のケーシィ系統は次の相手番に倒される前提のため、先にベンチへ後続ケーシィを確保する",
            (
                "PLAYBOOK-POKE-PAD",
                "PLAYBOOK-BOARD-MINIMUM",
                "PLAYBOOK-SEARCH-INTENT",
            ),
        )
    if attack_line_material_count == 0:
        add(
            "SEARCH_ABRA_FOR_SETUP",
            CardId.ABRA,
            "他の合法なケーシィ着地経路がないため例外的に探す",
            ("PLAYBOOK-ABRA-ZERO", "PLAYBOOK-SEARCH-INTENT"),
        )
    abra_known_absent = (
        not card_may_be_in_deck(view, memory, CardId.ABRA)
    )
    if (
        abra_known_absent
        and powered_alakazam_exists(view)
        and attack_line_count(view) < MINIMUM_ATTACK_LINES
        and old_abra_count > hand_kadabra_count
    ):
        add(
            "SEARCH_KADABRA_FOR_CONTINUITY",
            CardId.KADABRA,
            "3体目のケーシィが山札に残っていないため、場の進化前をユンゲラーへ進めて次番を守る",
            (
                "PLAYBOOK-POKE-PAD",
                "PLAYBOOK-T3-KADABRA",
                "PLAYBOOK-BOARD-MINIMUM",
                "PLAYBOOK-SEARCH-INTENT",
            ),
        )
    if (
        abra_known_absent
        and powered_alakazam_exists(view)
        and attack_line_count(view) < MINIMUM_ATTACK_LINES
        and old_kadabra_count > hand_alakazam_count
    ):
        add(
            "SEARCH_ALAKAZAM_FOR_CONTINUITY",
            CardId.ALAKAZAM,
            "3体目のケーシィが山札に残っていないため、場のユンゲラー用フーディンを確保して次番を守る",
            (
                "PLAYBOOK-POKE-PAD",
                "PLAYBOOK-BOARD-MINIMUM",
                "PLAYBOOK-SEARCH-INTENT",
            ),
        )
    if (
        old_kadabra_count > hand_alakazam_count
    ):
        add(
            "SEARCH_ALAKAZAM_FOR_CONTINUITY",
            CardId.ALAKAZAM,
            "前の番からいるユンゲラーを今フーディンへ進化させ、3枚引いて攻撃役を完成させる",
            (
                "PLAYBOOK-POKE-PAD",
                "PLAYBOOK-T3-KADABRA",
                "PLAYBOOK-BOARD-MINIMUM",
                "PLAYBOOK-SEARCH-INTENT",
            ),
        )
    if (
        view.own_turn_number >= 2
        and old_abra_count > hand_kadabra_count
        and old_dunsparce_count == 0
        and old_dunsparce_count <= hand_dudunsparce_count
    ):
        add(
            "SEARCH_KADABRA_FOR_T3",
            CardId.KADABRA,
            "今ターン進化できる古いケーシィ用のユンゲラーを取り、3ターン目攻撃を準備する",
            (
                "PLAYBOOK-POKE-PAD",
                "PLAYBOOK-T3-KADABRA",
                "PLAYBOOK-SEARCH-INTENT",
            ),
        )
    if (
        draw_line_count(view) < MAXIMUM_DRAW_LINES
        and waiting_dunsparce_count > hand_dudunsparce_count
    ):
        add(
            "SEARCH_DUDUNSPARCE_FOR_DRAW",
            CardId.DUDUNSPARCE,
            "場の進化待ちノコッチに不足する手札ノココッチを優先して探す",
            ("PLAYBOOK-POKE-PAD", "PLAYBOOK-SEARCH-INTENT"),
        )

    board_plan = full_board_plan(view)
    for candidate_group in rank_full_board_search_candidates(
        view,
        memory,
        board_plan,
    ):
        card_ids = tuple(
            card_id
            for card_id in candidate_group
            if card_may_be_in_deck(view, memory, card_id)
        )
        if bench_space <= 0 or not card_ids:
            continue
        add_group(
            (
                "SEARCH_ABRA_FOR_FULL_BOARD"
                if card_ids == (int(CardId.ABRA),)
                else "SEARCH_DUNSPARCE_FOR_FULL_BOARD"
                if card_ids == (int(CardId.DUNSPARCE),)
                else "SEARCH_BASIC_FOR_FULL_BOARD"
            ),
            card_ids,
            "6枠盤面を4-2または3-3へ近づける",
            (
                "PLAYBOOK-POKE-PAD",
                "PLAYBOOK-FULL-BOARD",
                "PLAYBOOK-SEARCH-INTENT",
            ),
        )

    return tuple(plans)
