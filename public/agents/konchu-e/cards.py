from collections import Counter
from enum import IntEnum
from pathlib import Path
from typing import Iterable


class CardId(IntEnum):
    BASIC_PSYCHIC = 5
    MIST_ENERGY = 11
    ENRICHING_ENERGY = 13
    TELEPATH_PSYCHIC_ENERGY = 19
    ROCK_FIGHTING_ENERGY = 20
    DUDUNSPARCE = 66
    FEZANDIPITI_EX = 140
    GENESECT = 142
    FAN_ROTOM = 174
    DUNSPARCE = 305
    SHAYMIN = 343
    ABRA = 741
    KADABRA = 742
    ALAKAZAM = 743
    PSYDUCK = 858
    RARE_CANDY = 1079
    UNFAIR_STAMP = 1080
    ENHANCED_HAMMER = 1081
    BUDDY_BUDDY_POFFIN = 1086
    NIGHT_STRETCHER = 1097
    SACRED_ASH = 1129
    POKE_PAD = 1152
    AIR_BALLOON = 1174
    BOSSES_ORDERS = 1182
    LANAS_AID = 1184
    TEAM_ROCKETS_PETREL = 1219
    XEROSICS_MACHINATIONS = 1197
    HILDA = 1225
    DAWN = 1231
    BATTLE_CAGE = 1264


class AttackId(IntEnum):
    ASSAULT_LANDING = 230
    TELEPORT_ATTACK = 1070
    KADABRA_ATTACK = 1071
    HAND_POWER = 1072


DECK_COUNTS: dict[int, int] = {
    CardId.DUDUNSPARCE: 4,
    CardId.FEZANDIPITI_EX: 1,
    CardId.DUNSPARCE: 4,
    CardId.ABRA: 4,
    CardId.KADABRA: 4,
    CardId.ALAKAZAM: 4,
    CardId.RARE_CANDY: 4,
    CardId.ENHANCED_HAMMER: 3,
    CardId.BUDDY_BUDDY_POFFIN: 4,
    CardId.NIGHT_STRETCHER: 1,
    CardId.SACRED_ASH: 1,
    CardId.POKE_PAD: 4,
    CardId.BOSSES_ORDERS: 3,
    CardId.LANAS_AID: 1,
    CardId.TEAM_ROCKETS_PETREL: 1,
    CardId.HILDA: 4,
    CardId.DAWN: 4,
    CardId.BATTLE_CAGE: 2,
    CardId.BASIC_PSYCHIC: 2,
    CardId.ENRICHING_ENERGY: 1,
    CardId.TELEPATH_PSYCHIC_ENERGY: 4,
}
DECK: tuple[int, ...] = tuple(
    int(card_id) for card_id, count in DECK_COUNTS.items() for _ in range(count)
)


def read_deck_csv(path: Path | None = None) -> list[int]:
    deck_path = path or Path(__file__).with_name("deck.csv")
    return [
        int(line)
        for line in deck_path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]


def validate_deck(deck: Iterable[int]) -> None:
    values = list(deck)
    if len(values) != 60:
        raise ValueError(f"デッキは60枚必要です: {len(values)}")
    if Counter(values) != Counter(DECK):
        raise ValueError("デッキ内容が正規フーディンリストと一致しません。")
