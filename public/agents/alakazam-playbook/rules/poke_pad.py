from __future__ import annotations

from dataclasses import dataclass

from cards import CardId


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


def plan_poke_pad_targets(view) -> tuple[PokePadTargetPlan, ...]:
    plans: list[PokePadTargetPlan] = []

    def add(
        kind: str,
        card_id: int | CardId,
        reason: str,
        rule_ids: tuple[str, ...],
    ) -> None:
        card_ids = (int(card_id),)
        if any(plan.card_ids == card_ids for plan in plans):
            return
        plans.append(PokePadTargetPlan(kind, card_ids, reason, rule_ids))

    abra_exists = _field_or_hand_count(view, CardId.ABRA) > 0
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
    hand_dudunsparce_count = view.hand_ids.count(int(CardId.DUDUNSPARCE))
    alakazam_visible = _field_or_hand_count(view, CardId.ALAKAZAM) > 0

    turn_two_kadabra_route = (
        view.own_turn_number == 2
        and old_abra_count > 0
        and hand_kadabra_count == 0
        and field_kadabra_count == 0
        and int(CardId.RARE_CANDY) not in view.hand_ids
    )
    turn_two_alakazam_route = (
        view.own_turn_number == 2
        and not alakazam_visible
        and (
            field_kadabra_count > 0
            or (old_abra_count > 0 and hand_kadabra_count > 0)
        )
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
    if turn_two_alakazam_route:
        add(
            "SEARCH_ALAKAZAM_FOR_T3",
            CardId.ALAKAZAM,
            "2ターン目に確保済みのユンゲラー線を完成させるため、3ターン目用フーディンを予約する",
            (
                "PLAYBOOK-POKE-PAD",
                "PLAYBOOK-T3-KADABRA",
                "PLAYBOOK-SEARCH-INTENT",
            ),
        )
    if not abra_exists:
        add(
            "SEARCH_ABRA_FOR_SETUP",
            CardId.ABRA,
            "他の合法なケーシィ着地経路がないため例外的に探す",
            ("PLAYBOOK-ABRA-ZERO", "PLAYBOOK-SEARCH-INTENT"),
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
    if waiting_dunsparce_count > hand_dudunsparce_count:
        add(
            "SEARCH_DUDUNSPARCE_FOR_DRAW",
            CardId.DUDUNSPARCE,
            "場の進化待ちノコッチに不足する手札ノココッチを優先して探す",
            ("PLAYBOOK-POKE-PAD", "PLAYBOOK-SEARCH-INTENT"),
        )
    elif waiting_dunsparce_count == 0:
        add(
            "SEARCH_DUNSPARCE_FOR_SETUP",
            CardId.DUNSPARCE,
            "不足するノコッチをポケパッドで探す",
            ("PLAYBOOK-POKE-PAD", "PLAYBOOK-SEARCH-INTENT"),
        )

    return tuple(plans)
