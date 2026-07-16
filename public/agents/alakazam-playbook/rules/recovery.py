from __future__ import annotations

from cards import CardId
from model import CardType, OptionType, SelectContext, SelectType
from proposals import PendingIntent, Proposal, covers
from rules.attack import can_hand_power_ko


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


def _spend_preserves_immediate_ko(view) -> bool:
    if not can_hand_power_ko(view):
        return True
    return can_hand_power_ko(
        view,
        hand_size=max(0, view.hand_size - 1),
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


def _sacred_ash_proposal(view, discard_ids: tuple[int, ...]) -> Proposal | None:
    targets = _ordered_present(SACRED_ASH_PRIORITY, discard_ids)
    if not targets:
        return None
    option = _play_option(view, CardId.SACRED_ASH)
    if option is None:
        return None
    intent = PendingIntent.from_view(
        view,
        kind="RECOVER_POKEMON_LINES",
        card_ids=targets,
        card_groups=tuple(targets for _ in range(5)),
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
        760,
        "後続の攻撃・進化・大量ドローに必要なポケモンを山札へ戻す",
        ("PLAYBOOK-SACRED-ASH", "PLAYBOOK-BOARD-MINIMUM"),
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
    fixed = list(_ordered_present(LANA_RULELESS_PRIORITY, discard_ids))
    fixed_set = set(fixed)
    additional_ruleless = sorted(
        card_id
        for card_id in present
        if card_id not in fixed_set
        and card_id != int(CardId.FEZANDIPITI_EX)
        and _is_known_ruleless_pokemon(view, card_id)
    )
    targets = [*fixed, *additional_ruleless]
    if int(CardId.BASIC_PSYCHIC) in present:
        targets.append(int(CardId.BASIC_PSYCHIC))
    return tuple(targets)


def _lanas_aid_proposal(view, discard_ids: tuple[int, ...]) -> Proposal | None:
    targets = _lana_targets(view, discard_ids)
    if not targets:
        return None
    option = _play_option(view, CardId.LANAS_AID)
    if option is None:
        return None
    intent = PendingIntent.from_view(
        view,
        kind="RECOVER_RULELESS_AND_BASIC_PSYCHIC",
        card_ids=targets,
        card_groups=tuple(targets for _ in range(3)),
        max_cards=3,
        metadata=(
            ("reason", "ルールを持たない盤面役と基本超だけを手札へ戻す"),
            ("priority", ",".join(str(card_id) for card_id in targets)),
        ),
        effect_card_id=CardId.LANAS_AID,
        effect_serial=option.card_serial,
        remaining_contexts=(SelectContext.TO_HAND,),
    )
    return Proposal(
        (option.position,),
        750,
        "ルールを持たないポケモンと基本超を手札へ復旧する",
        ("PLAYBOOK-LANAS-AID", "PLAYBOOK-BOARD-MINIMUM"),
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
    if not _is_main_selection(view) or not _spend_preserves_immediate_ko(view):
        return None

    discard_ids = _discard_ids(view)
    proposals = (
        _sacred_ash_proposal(view, discard_ids),
        _lanas_aid_proposal(view, discard_ids),
    )
    return max(
        (proposal for proposal in proposals if proposal is not None),
        key=lambda proposal: (
            proposal.priority,
            -proposal.option_indices[0],
        ),
        default=None,
    )
