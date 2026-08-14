from __future__ import annotations

from dataclasses import dataclass

from common_strategy import DeckContract, GameView

from .cards import CardId, DECK


OMATSURI_DECK_CONTRACT = DeckContract.from_deck(
    DECK,
    evolution_parent={
        int(CardId.DIPPLIN): int(CardId.APPLIN),
        int(CardId.THWACKEY): int(CardId.GROOKEY),
        int(CardId.SEAKING): int(CardId.GOLDEEN),
    },
)


@dataclass(frozen=True)
class BoardStatus:
    dipplin_lines: int
    thwackey_lines: int
    bench_count: int
    bench_space: int

    @property
    def minimum_complete(self) -> bool:
        return self.dipplin_lines >= 2 and self.thwackey_lines >= 2


def board_status(view: GameView) -> BoardStatus:
    """Return the own-board line counts without counting an evolution twice."""
    seen: set[tuple[object, ...]] = set()
    roots: list[int] = []
    for index, pokemon in enumerate(view.own_field):
        identity = (
            ("serial", int(pokemon.serial))
            if pokemon.serial is not None
            else ("area-index", int(pokemon.area or -1), int(pokemon.index or index))
        )
        if identity in seen:
            continue
        seen.add(identity)
        roots.append(_line_root(pokemon.id))
    bench_identities = {
        ("serial", int(pokemon.serial))
        if pokemon.serial is not None
        else ("bench-index", int(pokemon.index or index))
        for index, pokemon in enumerate(view.own_bench)
        if (
            ("serial", int(pokemon.serial))
            if pokemon.serial is not None
            else ("bench-index", int(pokemon.index or index))
        ) not in {
            ("serial", int(view.active.serial))
            if view.active is not None and view.active.serial is not None
            else ("active", 0)
        }
    }
    bench_count = len(bench_identities)
    return BoardStatus(
        dipplin_lines=roots.count(int(CardId.APPLIN)),
        thwackey_lines=roots.count(int(CardId.GROOKEY)),
        bench_count=bench_count,
        bench_space=max(0, int(view.own.get("benchMax", 5)) - bench_count),
    )


def _line_root(card_id: int) -> int:
    current = int(card_id)
    while current in OMATSURI_DECK_CONTRACT.evolution_parent:
        current = int(OMATSURI_DECK_CONTRACT.evolution_parent[current])
    return current
