from __future__ import annotations

from cards import CardId
from model import Area, OptionType, SelectContext
from proposals import Proposal, covers
from rules.board_plan import (
    ATTACK_LINE_IDS,
    DRAW_LINE_IDS,
    MAXIMUM_ATTACK_LINES,
    MAXIMUM_DRAW_LINES,
    MINIMUM_ATTACK_LINES,
    MINIMUM_DRAW_LINES,
    full_board_plan_for_counts,
)


ACTIVE_PRIORITY = (
    CardId.DUNSPARCE,
    CardId.ABRA,
    CardId.FEZANDIPITI_EX,
)
CORE_BENCH_IDS = frozenset((int(CardId.ABRA), int(CardId.DUNSPARCE)))


def _hand_index(option) -> int:
    value = option.raw.get("index")
    return int(option.position) if value is None else int(value)


def _selection_key(option) -> tuple[int, int]:
    serial = option.card_serial
    return (
        _hand_index(option) if serial is None else int(serial),
        int(option.position),
    )


def _physical_card_identity(option) -> tuple[str, int]:
    if option.card_serial is not None:
        return ("serial", int(option.card_serial))
    hand_index = option.raw.get("index")
    if hand_index is not None:
        return ("hand", int(hand_index))
    return ("position", int(option.position))


def _representative_card_options(options) -> list:
    representatives = {}
    for option in options:
        identity = _physical_card_identity(option)
        current = representatives.get(identity)
        if current is None or _selection_key(option) < _selection_key(current):
            representatives[identity] = option
    return list(representatives.values())


def _line_counts(view, selected: list) -> tuple[int, int]:
    attack_lines = sum(
        int(pokemon.id) in ATTACK_LINE_IDS
        for pokemon in view.field
    ) + sum(
        option.card_id is not None
        and int(option.card_id) == int(CardId.ABRA)
        for option in selected
    )
    draw_lines = sum(
        int(pokemon.id) in DRAW_LINE_IDS
        for pokemon in view.field
    ) + sum(
        option.card_id is not None
        and int(option.card_id) == int(CardId.DUNSPARCE)
        for option in selected
    )
    return attack_lines, draw_lines


def _can_add_bench_card(view, selected: list, card_id: int) -> bool:
    attack_lines, draw_lines = _line_counts(view, selected)
    plan = full_board_plan_for_counts(
        attack_lines,
        draw_lines,
        len(view.field) + len(selected),
    )
    candidate_id = int(card_id)
    if candidate_id not in plan.target_basic_ids:
        return False

    next_plan = full_board_plan_for_counts(
        attack_lines + int(candidate_id == int(CardId.ABRA)),
        draw_lines + int(candidate_id == int(CardId.DUNSPARCE)),
        len(view.field) + len(selected) + 1,
    )
    minimum_slots = (
        max(0, MINIMUM_ATTACK_LINES - next_plan.attack_lines)
        + max(0, MINIMUM_DRAW_LINES - next_plan.draw_lines)
    )
    return minimum_slots <= next_plan.open_slots


def _mandatory_fallback_rank(view, selected: list, option) -> int:
    card_id = None if option.card_id is None else int(option.card_id)
    if card_id not in CORE_BENCH_IDS:
        return 1
    attack_lines, draw_lines = _line_counts(view, selected)
    within_limit = (
        attack_lines < MAXIMUM_ATTACK_LINES
        if card_id == int(CardId.ABRA)
        else draw_lines < MAXIMUM_DRAW_LINES
    )
    return 0 if within_limit else 2


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
        cards = _representative_card_options(
            option
            for option in view.options
            if option.type == int(OptionType.CARD)
        )
        if not cards:
            return None
        option = min(
            cards,
            key=lambda item: (
                rank.get(int(item.card_id) if item.card_id is not None else -1, len(rank)),
                *_selection_key(item),
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
    cards = _representative_card_options(
        option
        for option in view.options
        if option.type == int(OptionType.CARD)
    )

    selected = []
    while len(selected) < capacity:
        candidates = [
            option
            for option in cards
            if option not in selected
            and option.card_id is not None
            and int(option.card_id) in CORE_BENCH_IDS
            and _can_add_bench_card(view, selected, option.card_id)
        ]
        if not candidates:
            break
        selected.append(min(candidates, key=_selection_key))

    emergency_fezandipiti = (
        len(view.field) + len(selected) == 1
        and len(selected) < capacity
        and len(cards) == 1
        and cards[0].card_id is not None
        and int(cards[0].card_id) == int(CardId.FEZANDIPITI_EX)
    )
    if emergency_fezandipiti:
        selected.append(cards[0])

    # If the engine requires more selections than the strategic candidates provide,
    # satisfy minCount deterministically with the remaining legal cards.
    required_count = min(capacity, min_count)
    while len(selected) < required_count:
        remaining = [option for option in cards if option not in selected]
        if not remaining:
            break
        selected.append(min(
            remaining,
            key=lambda option: (
                _mandatory_fallback_rank(view, selected, option),
                *_selection_key(option),
            ),
        ))

    if len(selected) < min_count:
        return None
    return Proposal(
        tuple(option.position for option in selected),
        990,
        (
            "場が1体だけの初期配置でキチキギスexを2体目にし、場切れを防ぐ"
            if emergency_fezandipiti
            else "ケーシィ上限とノコッチの初動展開を両立する"
        ),
        ("PLAYBOOK-ABRA-LIMIT", "FLOW-SETUP-ACTIVE"),
    )
