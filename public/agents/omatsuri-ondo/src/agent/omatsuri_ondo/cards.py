from collections import Counter
from enum import IntEnum
from pathlib import Path
from typing import Iterable


class CardId(IntEnum):
    BASIC_GRASS = 1
    GROOKEY = 89
    THWACKEY = 90
    APPLIN = 92
    DIPPLIN = 93
    GOLDEEN = 100
    SEAKING = 240
    BUDEW = 235
    SHAYMIN = 343
    PSYDUCK = 858
    UNFAIR_STAMP = 1080
    BUDDY_BUDDY_POFFIN = 1086
    BUG_CATCHING_SET = 1094
    NIGHT_STRETCHER = 1097
    SACRED_ASH = 1129
    POKE_PAD = 1152
    AIR_BALLOON = 1174
    BRAVE_BANGLE = 1175
    BOSSES_ORDERS = 1182
    LANAS_AID = 1184
    KIERAN = 1191
    BROCKS_SCOUTING = 1210
    BLACK_BELTS_TRAINING = 1211
    JUDGE = 1213
    LILLIES_DETERMINATION = 1227
    FESTIVAL_GROUNDS = 1245


class AttackId(IntEnum):
    DIPPLIN_DO_THE_WAVE = 115
    BUDEW_ITTY_BITTY_POLLEN = 323


DECK_COUNTS: dict[int, int] = {
    CardId.BASIC_GRASS: 5,
    CardId.GROOKEY: 4,
    CardId.THWACKEY: 4,
    CardId.APPLIN: 4,
    CardId.DIPPLIN: 4,
    CardId.GOLDEEN: 1,
    CardId.BUDEW: 1,
    CardId.SEAKING: 1,
    CardId.SHAYMIN: 1,
    CardId.PSYDUCK: 1,
    CardId.UNFAIR_STAMP: 1,
    CardId.BUDDY_BUDDY_POFFIN: 4,
    CardId.BUG_CATCHING_SET: 4,
    CardId.NIGHT_STRETCHER: 1,
    CardId.SACRED_ASH: 1,
    CardId.POKE_PAD: 4,
    CardId.AIR_BALLOON: 2,
    CardId.BRAVE_BANGLE: 2,
    CardId.BOSSES_ORDERS: 2,
    CardId.LANAS_AID: 1,
    CardId.KIERAN: 1,
    CardId.BROCKS_SCOUTING: 2,
    CardId.BLACK_BELTS_TRAINING: 1,
    CardId.JUDGE: 1,
    CardId.LILLIES_DETERMINATION: 3,
    CardId.FESTIVAL_GROUNDS: 4,
}

DECK: tuple[int, ...] = tuple(
    int(card_id)
    for card_id, count in DECK_COUNTS.items()
    for _ in range(count)
)


def read_deck_csv(path: Path | None = None) -> list[int]:
    source = path or Path(__file__).with_name("deck.csv")
    return [
        int(line.strip())
        for line in source.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]


def validate_deck(deck: Iterable[int]) -> None:
    values = list(deck)
    if len(values) != 60:
        raise ValueError(f"おまつりおんどデッキは60枚必要です: {len(values)}")
    if Counter(values) != Counter(DECK):
        raise ValueError("おまつりおんどデッキ内容が正規リストと一致しません。")


if Counter(read_deck_csv()) != Counter(DECK):
    raise ValueError("おまつりおんどのdeck.csvが正規デッキリストと一致しません。")
