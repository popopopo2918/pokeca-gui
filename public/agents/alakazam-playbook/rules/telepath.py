from __future__ import annotations

from cards import CardId
from model import SelectContext
from proposals import PendingIntent


def build_telepath_bench_intent(view, option, target, reason: str) -> PendingIntent:
    abra_field_count = sum(
        int(pokemon.id) == int(CardId.ABRA)
        for pokemon in view.field
    )
    bench_space = max(0, int(view.own.get("benchMax", 5)) - len(view.bench))
    max_cards = min(2, max(0, 3 - abra_field_count), bench_space)
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
