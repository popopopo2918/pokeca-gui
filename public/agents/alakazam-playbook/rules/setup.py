from __future__ import annotations

from cards import CardId
from model import Area, OptionType, SelectContext
from proposals import Proposal, covers


ACTIVE_PRIORITY = (
    CardId.FAN_ROTOM,
    CardId.DUNSPARCE,
    CardId.ABRA,
    CardId.PSYDUCK,
    CardId.SHAYMIN,
    CardId.GENESECT,
    CardId.FEZANDIPITI_EX,
)

BENCH_PRIORITY = (
    CardId.ABRA,
    CardId.DUNSPARCE,
    CardId.FAN_ROTOM,
)


def _hand_index(option) -> int:
    value = option.raw.get("index")
    return int(value) if value is not None else option.position


def _field_count(view, card_id: int) -> int:
    return sum(int(pokemon.id) == int(card_id) for pokemon in view.field)


def _can_add_bench_card(view, selected: list, card_id: int) -> bool:
    total = _field_count(view, card_id) + sum(
        int(option.card_id) == int(card_id) for option in selected
    )
    if int(card_id) == int(CardId.ABRA):
        return total < 3
    if int(card_id) == int(CardId.DUNSPARCE):
        return total < 3
    if int(card_id) == int(CardId.FAN_ROTOM):
        return total < 1
    return True


@covers("FLOW-SETUP-ACTIVE", "PLAYBOOK-FIRST-SECOND", "PLAYBOOK-ABRA-LIMIT")
def propose_setup(view, memory, prefer_first: bool) -> Proposal | None:
    context = int(view.select.get("context", -1))
    if context == int(SelectContext.IS_FIRST):
        wanted = int(OptionType.YES if prefer_first else OptionType.NO)
        option = next((item for item in view.options if item.type == wanted), None)
        if option is None:
            return None
        return Proposal(
            (option.position,),
            1000,
            "評価で選んだ先後を選択する",
            ("PLAYBOOK-FIRST-SECOND",),
        )

    if context == int(SelectContext.SETUP_ACTIVE_POKEMON):
        rank = {int(card_id): index for index, card_id in enumerate(ACTIVE_PRIORITY)}
        cards = [option for option in view.options if option.type == int(OptionType.CARD)]
        if not cards:
            return None
        option = min(
            cards,
            key=lambda item: (
                rank.get(int(item.card_id) if item.card_id is not None else -1, len(rank)),
                int(item.card_id) if item.card_id is not None else 10**9,
                item.position,
            ),
        )
        return Proposal(
            (option.position,),
            1000,
            "初期バトル場の優先順位で選択する",
            ("FLOW-SETUP-ACTIVE",),
        )

    if context != int(SelectContext.SETUP_BENCH_POKEMON):
        return None

    min_count = max(0, int(view.select.get("minCount", 0)))
    max_count = max(0, int(view.select.get("maxCount", 0)))
    bench_max = int(view.own.get("benchMax", 5))
    capacity = max(0, min(max_count, bench_max - len(view.bench)))
    rank = {int(card_id): index for index, card_id in enumerate(BENCH_PRIORITY)}
    cards = [option for option in view.options if option.type == int(OptionType.CARD)]
    ordered = sorted(
        cards,
        key=lambda item: (
            rank.get(int(item.card_id) if item.card_id is not None else -1, len(rank)),
            _hand_index(item),
            item.position,
        ),
    )

    selected = []
    for option in ordered:
        if len(selected) >= capacity:
            break
        if (
            option.card_id is None
            or int(option.card_id) not in rank
            or not _can_add_bench_card(view, selected, option.card_id)
        ):
            continue
        selected.append(option)

    # If the engine requires more selections than the strategic candidates provide,
    # satisfy minCount deterministically with the remaining legal cards.
    if len(selected) < min_count:
        for option in sorted(cards, key=lambda item: (_hand_index(item), item.position)):
            if len(selected) >= min(capacity, min_count):
                break
            if option in selected:
                continue
            selected.append(option)

    if len(selected) < min_count:
        return None
    return Proposal(
        tuple(option.position for option in selected),
        990,
        "ケーシィ上限とノコッチの初動展開を両立する",
        ("PLAYBOOK-ABRA-LIMIT", "FLOW-SETUP-ACTIVE"),
    )
