"""終盤だけ有効になる、任意ドロー・検索の共通山札予算。"""

from __future__ import annotations

from cards import CardId
from model import OptionType, SelectContext
from rules.attack import can_hand_power_ko


DECK_SAFETY_THRESHOLD = 10
DECK_SEARCH_EFFECT_IDS = frozenset({
    int(CardId.BUDDY_BUDDY_POFFIN),
    int(CardId.POKE_PAD),
    int(CardId.FAN_ROTOM),
    int(CardId.TELEPATH_PSYCHIC_ENERGY),
    int(CardId.HILDA),
    int(CardId.DAWN),
})
PURE_SEARCH_EFFECT_IDS = DECK_SEARCH_EFFECT_IDS - {
    int(CardId.TELEPATH_PSYCHIC_ENERGY),
}
ATTACK_PSYCHIC_IDS = frozenset({
    int(CardId.BASIC_PSYCHIC),
    int(CardId.TELEPATH_PSYCHIC_ENERGY),
})


def _deck_count(view) -> int:
    return max(0, int(view.own.get("deckCount", 0)))


def deck_safety_active(view) -> bool:
    """現在の山札が安全計算を開始する10枚以下か返す。"""
    return _deck_count(view) <= DECK_SAFETY_THRESHOLD


def guaranteed_prizes_this_turn(view, hand_delta: int = 0) -> int:
    """予定行動後も公開情報だけで確定する今ターンの取得サイド枚数。"""
    hand_size = max(0, int(view.hand_size) + int(hand_delta))
    if not can_hand_power_ko(
        view,
        hand_size=hand_size,
        require_legal_option=False,
    ):
        return 0
    if len(view.opponent_field) <= 1:
        return int(view.own_prize_count)
    active = view.opponent_active
    meta = None if active is None else view.catalog.card(active.id)
    prize_value = 1 if meta is None else max(1, int(meta.prize_value))
    return min(int(view.own_prize_count), prize_value)


def minimum_deck_reserve(view, hand_delta: int = 0) -> int:
    """残りサイド取得までの通常ドローと循環起動用に残す最低枚数。"""
    guaranteed_after = guaranteed_prizes_this_turn(
        view,
        hand_delta=hand_delta,
    )
    return minimum_deck_reserve_after_prizes(view, guaranteed_after)


def minimum_deck_reserve_after_prizes(view, prizes_taken: int) -> int:
    """この番に取ると確定したサイドを反映した最低山札枚数。"""
    remaining_prizes = max(0, int(view.own_prize_count) - int(prizes_taken))
    if remaining_prizes == 0:
        return 0
    # CABTは山札0枚ではノココッチの特性を提示しない。残りサイド1枚で
    # 山札1枚を残すだけでは、次の通常ドロー後に循環できず山切れする。
    # 最終KOが今確定していない限り、最後の通常ドローに加えて特性を
    # 起動できる1枚を残す。
    return max(2, remaining_prizes)


def can_remove_from_deck(
    view,
    *,
    cards_removed: int,
    cards_returned: int = 0,
    hand_delta: int = 0,
) -> bool:
    """予定する正味の山札消費後も最低残数を保てるか返す。"""
    if not deck_safety_active(view):
        return True
    current = _deck_count(view)
    available = current + max(0, int(cards_returned))
    actual_removed = min(available, max(0, int(cards_removed)))
    projected = available - actual_removed
    if projected >= current:
        # すでに通常の最低残数を下回っていても、ノココッチのように
        # 解決後の山札を減らさない循環は山切れを近づけない。
        return True
    return projected >= minimum_deck_reserve(
        view,
        hand_delta=hand_delta,
    )


def max_safe_deck_removals(
    view,
    *,
    requested: int,
    cards_returned: int = 0,
    cards_to_hand: bool = False,
    base_hand_delta: int = 0,
) -> int:
    """現在の安全予算内で山札から動かせる最大枚数。"""
    maximum = min(
        max(0, int(requested)),
        _deck_count(view) + max(0, int(cards_returned)),
    )
    if not deck_safety_active(view):
        return maximum
    for count in range(maximum, -1, -1):
        if can_remove_from_deck(
            view,
            cards_removed=count,
            cards_returned=cards_returned,
            hand_delta=(
                int(base_hand_delta)
                + (count if cards_to_hand else 0)
            ),
        ):
            return count
    return 0


def returned_dudunsparce_cards(option) -> int:
    """にげあしドローで山札へ戻る進化束・付属カードの公開枚数。"""
    source = option.source
    if source is None:
        return 0
    return (
        1
        + len(source.pre_evolution_ids)
        + len(source.energy_card_ids)
        + len(source.tool_ids)
    )


def _selected_options(view, proposal):
    by_position = {option.position: option for option in view.options}
    return tuple(
        by_position[position]
        for position in proposal.option_indices
        if position in by_position
    )


def _actual_draw(view, requested: int, cards_returned: int = 0) -> int:
    return min(
        max(0, int(requested)),
        _deck_count(view) + max(0, int(cards_returned)),
    )


def _intent_flag(intent, key: str) -> bool:
    if intent is None:
        return False
    return any(
        name == key and bool(value)
        for name, value in intent.metadata
    )


def _search_start_is_safe(view, proposal) -> bool:
    intent = proposal.next_intent
    if (
        intent is None
        or int(intent.effect_card_id or -1) not in PURE_SEARCH_EFFECT_IDS
    ):
        return True
    if _intent_flag(intent, "final_ko_energy_search"):
        return True
    requested = (
        1
        if intent.max_cards is None
        else max(0, int(intent.max_cards))
    )
    multi_screen_search = int(intent.effect_card_id) in (
        int(CardId.HILDA),
        int(CardId.DAWN),
    )
    if multi_screen_search:
        # max_cards は各画面の上限であり、トウコは2画面、ヒカリは
        # 3画面とも検索が成立し得る。通常は開始時点で全画面分を確保する。
        # ただし空のカード群は、その画面を意図的に0枚で通す指定なので、
        # 実際に取る予定のある画面だけを山札消費として数える。
        planned_screens = (
            sum(bool(group) for group in intent.card_groups)
            if intent.card_groups
            else len(intent.remaining_contexts)
        )
        requested = max(requested, planned_screens)
    if requested <= 0:
        return False
    effect_id = int(intent.effect_card_id)
    cards_to_hand = effect_id != int(CardId.BUDDY_BUDDY_POFFIN)
    selected = _selected_options(view, proposal)
    spent_from_hand = any(
        option.type == int(OptionType.PLAY)
        for option in selected
    )
    safe_removals = max_safe_deck_removals(
        view,
        requested=requested,
        cards_to_hand=cards_to_hand,
        base_hand_delta=-1 if spent_from_hand else 0,
    )
    return (
        safe_removals >= requested
        if multi_screen_search
        else safe_removals > 0
    )


def proposal_is_deck_safe(
    view,
    proposal,
    *,
    pending_intent=None,
) -> bool:
    """既知の山札消費を持つ提案が終盤の安全予算内か検証する。"""
    if not deck_safety_active(view):
        return True

    selected = _selected_options(view, proposal)
    context_card = view.select.get("contextCard")
    context_card_id = (
        -1
        if not isinstance(context_card, dict)
        else int(context_card.get("id", -1))
    )
    evolution_draw = {
        int(CardId.KADABRA): 2,
        int(CardId.ALAKAZAM): 3,
    }.get(context_card_id)
    if evolution_draw is not None and any(
        option.type == int(OptionType.YES)
        for option in selected
    ):
        actual = _actual_draw(view, evolution_draw)
        return can_remove_from_deck(
            view,
            cards_removed=evolution_draw,
            hand_delta=actual,
        )

    effect = view.select.get("effect")
    effect_id = (
        -1
        if not isinstance(effect, dict)
        else int(effect.get("id", -1))
    )
    context = int(view.select.get("context", -1))
    if effect_id in DECK_SEARCH_EFFECT_IDS and context in (
        int(SelectContext.TO_HAND),
        int(SelectContext.TO_BENCH),
    ):
        count = len(selected)
        active_intent = proposal.next_intent or pending_intent
        if (
            effect_id == int(CardId.HILDA)
            and _intent_flag(active_intent, "final_ko_energy_search")
        ):
            return (
                count <= max(0, int(view.select.get("maxCount", 0)))
                and all(
                    option.card_id is not None
                    and int(option.card_id) in ATTACK_PSYCHIC_IDS
                    for option in selected
                )
            )
        safe_count = max_safe_deck_removals(
            view,
            requested=count,
            cards_to_hand=context == int(SelectContext.TO_HAND),
        )
        forced = max(0, int(view.select.get("minCount", 0)))
        return count <= max(safe_count, forced)

    if not _search_start_is_safe(view, proposal):
        return False

    for option in selected:
        if (
            option.type == int(OptionType.ABILITY)
            and option.card_id == int(CardId.FEZANDIPITI_EX)
        ):
            actual = _actual_draw(view, 3)
            return can_remove_from_deck(
                view,
                cards_removed=3,
                hand_delta=actual,
            )
        if (
            option.type == int(OptionType.ABILITY)
            and option.card_id == int(CardId.DUDUNSPARCE)
        ):
            returned = returned_dudunsparce_cards(option)
            # にげあしドローは「3枚引く」→「進化束と付属カードを戻す」順。
            # 山札が3枚未満なら、戻すカードを先にドロー可能枚数へ足さない。
            actual = _actual_draw(view, 3)
            return can_remove_from_deck(
                view,
                cards_removed=actual,
                cards_returned=returned,
                hand_delta=actual,
            )
        if (
            option.type == int(OptionType.ATTACH)
            and option.card_id == int(CardId.ENRICHING_ENERGY)
        ):
            actual = _actual_draw(view, 4)
            return can_remove_from_deck(
                view,
                cards_removed=4,
                hand_delta=actual - 1,
            )
    return True
