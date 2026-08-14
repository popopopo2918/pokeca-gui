from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from common_strategy import GameView, PokemonRef


class OpponentAttackProfileId(IntEnum):
    """事前生成済みの相手主力系統。実行時には追加・推測しない。"""

    ALAKAZAM = 1
    DRAGAPULT = 2
    OMATSURI_ONDO = 3


@dataclass(frozen=True)
class OpponentAttackProfile:
    profile_id: OpponentAttackProfileId
    mainline_card_ids: frozenset[int]


OPPONENT_ATTACK_PROFILES = (
    OpponentAttackProfile(
        OpponentAttackProfileId.ALAKAZAM,
        frozenset((741, 742, 743)),
    ),
    OpponentAttackProfile(
        OpponentAttackProfileId.DRAGAPULT,
        frozenset((119, 120, 121)),
    ),
    OpponentAttackProfile(
        OpponentAttackProfileId.OMATSURI_ONDO,
        frozenset((92, 93)),
    ),
)

_PROFILE_BY_MAINLINE_CARD_ID = {
    card_id: profile
    for profile in OPPONENT_ATTACK_PROFILES
    for card_id in profile.mainline_card_ids
}


def lookup_opponent_attack_profile(
    view: GameView,
) -> OpponentAttackProfile | None:
    """公開カードを固定対応表へ照合する。未知・混成なら全滅を推測しない。"""

    matched = {
        _PROFILE_BY_MAINLINE_CARD_ID[card_id]
        for card_id in view.opponent_public_card_ids
        if card_id in _PROFILE_BY_MAINLINE_CARD_ID
    }
    if len(matched) != 1:
        return None
    return next(iter(matched))


def public_restart_line_count(
    view: GameView,
    profile: OpponentAttackProfile,
) -> int:
    """公開盤面に残る主力進化ラインの面数を数える。"""

    return sum(
        _pokemon_belongs_to_profile(pokemon, profile)
        for pokemon in view.opponent_field
    )


def target_extinguishes_mainline(
    view: GameView,
    profile: OpponentAttackProfile,
    *,
    target_serial: int,
) -> bool:
    """指定対象を倒すと公開済み主力ラインが0面になるか返す。"""

    target_found = False
    remaining_lines = 0
    for pokemon in view.opponent_field:
        if not _pokemon_belongs_to_profile(pokemon, profile):
            continue
        if pokemon.serial is not None and int(pokemon.serial) == int(target_serial):
            target_found = True
        else:
            remaining_lines += 1
    return target_found and remaining_lines == 0


def _pokemon_belongs_to_profile(
    pokemon: PokemonRef,
    profile: OpponentAttackProfile,
) -> bool:
    public_line_ids = {
        int(pokemon.id),
        *(int(card_id) for card_id in pokemon.pre_evolution_ids),
    }
    return not public_line_ids.isdisjoint(profile.mainline_card_ids)


__all__ = [
    "OPPONENT_ATTACK_PROFILES",
    "OpponentAttackProfile",
    "OpponentAttackProfileId",
    "lookup_opponent_attack_profile",
    "public_restart_line_count",
    "target_extinguishes_mainline",
]
