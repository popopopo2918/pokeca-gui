from __future__ import annotations

from cards import CardId
from memory import possible_deck_count
from model import SelectContext
from proposals import PendingIntent
from rules.board_plan import (
    MAXIMUM_ATTACK_LINES,
    attack_line_count,
    full_board_plan,
)


def build_telepath_bench_intent(
    view,
    option,
    target,
    reason: str,
    memory,
) -> PendingIntent | None:
    plan = full_board_plan(view)
    possible_abra = possible_deck_count(view, memory, CardId.ABRA)
    if (
        int(CardId.ABRA) not in plan.target_basic_ids
        or possible_abra <= 0
    ):
        return None
    max_cards = min(
        2,
        MAXIMUM_ATTACK_LINES - attack_line_count(view),
        plan.open_slots,
        possible_abra,
    )
    if max_cards <= 0:
        return None
    return PendingIntent.from_view(
        view,
        kind="BENCH_PSYCHIC_BASICS",
        card_ids=(int(CardId.ABRA),),
        target_serial=target.serial,
        max_cards=max_cards,
        metadata=(
            ("reason", reason),
            ("search_max", max_cards),
        ),
        effect_card_id=CardId.TELEPATH_PSYCHIC_ENERGY,
        effect_serial=option.card_serial,
        remaining_contexts=(SelectContext.TO_BENCH,),
    )
