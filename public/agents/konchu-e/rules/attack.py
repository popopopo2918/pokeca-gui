from __future__ import annotations

from math import ceil
import re
from dataclasses import dataclass
from enum import IntEnum

from cards import AttackId, CardId
from memory import card_may_be_in_deck
from model import Area, OptionType, SelectContext, SelectType
from proposals import PendingIntent, Proposal, covers
from rules.board_plan import (
    OPENING_PIVOT_ATTACH_PRIORITY,
    OPENING_PIVOT_RETREAT_PRIORITY,
    attack_line_count,
    is_opening_attack_phase,
    opening_abra_survival_pivot,
    powered_alakazam_exists,
)
from rules.telepath import build_telepath_bench_intent
from rules.survival import best_survival_retreat_target


MIST_ENERGY_ID = int(CardId.MIST_ENERGY)
ROCK_FIGHTING_ENERGY_ID = int(CardId.ROCK_FIGHTING_ENERGY)
IMMUNITY_ENERGIES = frozenset({
    MIST_ENERGY_ID,
    ROCK_FIGHTING_ENERGY_ID,
})
ONE_RETREAT_IDS = frozenset({
    int(CardId.ABRA),
    int(CardId.KADABRA),
    int(CardId.ALAKAZAM),
    int(CardId.DUNSPARCE),
    int(CardId.FEZANDIPITI_EX),
})
DRAGAPULT_PROFILE_KEY = "dragapult"
DRAGAPULT_PRIMARY_LINE = (119, 120, 121)
_HILDA_SEARCH_GROUPS = (
    (
        int(CardId.DUDUNSPARCE),
        int(CardId.KADABRA),
        int(CardId.ALAKAZAM),
    ),
    (
        int(CardId.BASIC_PSYCHIC),
        int(CardId.ENRICHING_ENERGY),
        int(CardId.TELEPATH_PSYCHIC_ENERGY),
    ),
)
_DAWN_SEARCH_GROUPS = (
    (
        int(CardId.FEZANDIPITI_EX),
        int(CardId.DUNSPARCE),
        int(CardId.ABRA),
    ),
    (int(CardId.DUDUNSPARCE), int(CardId.KADABRA)),
    (int(CardId.ALAKAZAM),),
)
_SUPPORTER_SEARCH_GROUPS = {
    int(CardId.HILDA): _HILDA_SEARCH_GROUPS,
    int(CardId.DAWN): _DAWN_SEARCH_GROUPS,
}

@dataclass(frozen=True)
class HammerTarget:
    pokemon_serial: int
    pokemon_id: int
    energy_serial: int
    energy_id: int
    unlocks_ko: bool
    profile_key: str


class BossReason(IntEnum):
    PRIZE_ACCELERATION = 1
    LAST_STAGE_ONE = 2
    SOLE_PRIMARY_LINE = 3
    FINAL_WIN = 4


@dataclass(frozen=True)
class BossTarget:
    pokemon: object
    reason: BossReason
    prizes: int
    required_hand: int
    is_fezandipiti: bool


def pokemon_belongs_to_line(pokemon, line: tuple[int, ...]) -> bool:
    visible = {
        int(pokemon.id),
        *(int(card_id) for card_id in getattr(pokemon, "pre_evolution_ids", ())),
    }
    return bool(visible.intersection(int(card_id) for card_id in line))


def opponent_primary_line_instances(view, profile):
    if profile is None:
        return ()
    return tuple(
        pokemon
        for pokemon in view.opponent_field
        if any(
            pokemon_belongs_to_line(pokemon, line)
            for line in profile.primary_lines
        )
    )


def _visible_primary_lines(profile) -> tuple[tuple[int, ...], ...]:
    if profile is None:
        return (DRAGAPULT_PRIMARY_LINE,)
    lines = tuple(
        tuple(int(card_id) for card_id in line)
        for line in getattr(profile, "primary_lines", ())
    )
    if getattr(profile, "key", None) == DRAGAPULT_PROFILE_KEY:
        return lines
    return tuple(line for line in lines if line != DRAGAPULT_PRIMARY_LINE)


def sole_energy_loaded_primary_serial(view, profile) -> int | None:
    lines = _visible_primary_lines(profile)
    loaded = tuple(
        pokemon
        for pokemon in view.opponent_field
        if any(pokemon_belongs_to_line(pokemon, line) for line in lines)
        and bool(pokemon.energy_cards)
    )
    if len(loaded) != 1 or loaded[0].serial is None:
        return None
    return int(loaded[0].serial)


def remaining_public_attacker_can_ko(view, *, excluded_serial: int) -> bool:
    """Boss対象を除いた公開攻撃役が、次番に現在のバトル場を倒せるか。"""
    active = view.active
    if active is None:
        return False
    for attacker in view.opponent_field:
        if attacker.serial is not None and int(attacker.serial) == int(excluded_serial):
            continue
        card = view.catalog.card(attacker.id)
        if card is None:
            continue
        for attack_id in card.attacks:
            meta = view.catalog.attack_meta.get(int(attack_id))
            if (
                meta is not None
                and view.public_attack_is_ready(attacker, attack_id)
                and int(meta.damage) >= int(active.hp)
            ):
                return True
    return False


def rare_candy_absence_inferred(view, memory, profile) -> bool:
    """直前の相手番に中間進化で止まり攻撃した公開履歴からだけ推定する。"""
    if memory is None or profile is None or not memory.opponent_actions:
        return False
    last_turn = max(int(action.turn) for action in memory.opponent_actions)
    if int(view.current.get("turn", -1)) != last_turn + 1:
        return False
    actions = tuple(
        action for action in memory.opponent_actions
        if int(action.turn) == last_turn
    )
    if not any(int(action.log_type) == 15 for action in actions):
        return False
    if any(
        int(action.log_type) == 10
        and action.card_id == int(CardId.RARE_CANDY)
        for action in actions
    ):
        return False
    for line in profile.primary_lines:
        if len(line) < 3:
            continue
        basic_id, stage_one_id, stage_two_id = map(int, line[-3:])
        stopped_at_stage_one = any(
            int(action.log_type) == 12
            and action.card_id == stage_one_id
            and action.target_card_id == basic_id
            for action in actions
        )
        reached_stage_two = any(
            int(action.log_type) == 12 and action.card_id == stage_two_id
            for action in actions
        )
        if stopped_at_stage_one and not reached_stage_two:
            return True
    return False
_ATTACKER_IDS = frozenset({
    int(CardId.ABRA),
    int(CardId.KADABRA),
    int(CardId.ALAKAZAM),
})
_FAN_ROTOM_DAMAGE = 70
_FAN_ROTOM_STADIUM_PRIORITY = 640
_FAN_ROTOM_ATTACH_PRIORITY = 635
_FAN_ROTOM_BOSS_PRIORITY = 630
_FAN_ROTOM_ATTACK_PRIORITY = 625


def _normalized_text(text: str) -> str:
    return (
        text.replace("’", "'")
        .replace("Pokémon", "Pokemon")
        .replace("pokémon", "pokemon")
        .replace("\xa0", " ")
        .lower()
    )


def _is_main_selection(view) -> bool:
    return (
        int(view.select.get("type", -1)) == int(SelectType.MAIN)
        and int(view.select.get("context", -1)) == int(SelectContext.MAIN)
    )


def _hand_power_option(view):
    if not _is_main_selection(view):
        return None
    return min(
        (
            option
            for option in view.options
            if option.type == int(OptionType.ATTACK)
            and option.attack_id == int(AttackId.HAND_POWER)
        ),
        key=lambda option: option.position,
        default=None,
    )


def _active_alakazam_is_hand_power_ready(
    view,
    *,
    assume_active_psychic: bool = False,
) -> bool:
    active = view.active
    return (
        view.is_own_turn
        and active is not None
        and int(active.id) == int(CardId.ALAKAZAM)
        and (view.has_psychic_energy(active) or assume_active_psychic)
        and not _active_attack_is_blocked(view)
    )


def _active_attack_is_blocked(view) -> bool:
    return any(
        bool(view.own.get(status))
        for status in ("asleep", "paralyzed", "confused")
    )


def _teleport_attack_option(view):
    if not _is_main_selection(view):
        return None
    return min(
        (
            option
            for option in view.options
            if option.type == int(OptionType.ATTACK)
            and option.attack_id == int(AttackId.TELEPORT_ATTACK)
        ),
        key=lambda option: option.position,
        default=None,
    )


def _kadabra_attack_option(view):
    if not _is_main_selection(view):
        return None
    return min(
        (
            option
            for option in view.options
            if option.type == int(OptionType.ATTACK)
            and option.attack_id == int(AttackId.KADABRA_ATTACK)
        ),
        key=lambda option: option.position,
        default=None,
    )


def _teleport_wall(view):
    """超付きケーシィを守るため、次番価値の低い壁を選ぶ。"""
    return min(
        (
            pokemon
            for pokemon in view.bench
            if (
                int(pokemon.id) == int(CardId.DUNSPARCE)
                or (
                    int(pokemon.id) == int(CardId.ABRA)
                    and not view.has_psychic_energy(pokemon)
                )
            )
            and pokemon.serial is not None
        ),
        key=lambda pokemon: (
            0 if int(pokemon.id) == int(CardId.DUNSPARCE) else 1,
            bool(pokemon.energy_card_ids),
            bool(pokemon.tool_ids),
            int(pokemon.hp) < int(pokemon.max_hp),
            int(pokemon.serial),
        ),
        default=None,
    )


def _non_ko_hand_power_proposal(view) -> Proposal | None:
    option = _hand_power_option(view)
    active = view.active
    target = view.opponent_active
    if (
        option is None
        or active is None
        or int(active.id) != int(CardId.ALAKAZAM)
        or not view.has_psychic_energy(active)
        or target is None
        or int(view.hand_size) <= 0
        or _is_hand_power_effect_immune(view, target)
    ):
        return None
    return Proposal(
        (option.position,),
        2,
        "展開・生存・妨害行動を終えた後、次番KOへつなぐため非KOのハンドパワーで削る",
        (
            "FLOW-ATTACK-HAND",
            "PLAYBOOK-TURN-TWO-NON-KO",
        ),
        alternative="non-ko-softening-after-priority-actions",
    )


def _teleport_attack_proposal(view) -> Proposal | None:
    option = _teleport_attack_option(view)
    active = view.active
    wall = _teleport_wall(view)
    if (
        option is None
        or active is None
        or int(active.id) != int(CardId.ABRA)
        or active.serial is None
        or not view.has_psychic_energy(active)
        or wall is None
        or wall.serial is None
    ):
        return None
    intent = PendingIntent.from_view(
        view,
        kind="TELEPORT_ATTACK_WALL",
        card_ids=(int(wall.id),),
        target_serial=int(wall.serial),
        max_cards=1,
        effect_card_id=int(CardId.ABRA),
        effect_serial=int(active.serial),
        remaining_contexts=(int(SelectContext.SWITCH),),
    )
    return Proposal(
        (option.position,),
        2,
        "テレポートアタックで超エネルギーを失わずケーシィを守り、次番価値の低い個体を壁にする",
        (
            "PLAYBOOK-TELEPORT-ATTACK",
            "PLAYBOOK-PRESERVE-ABRA",
        ),
        next_intent=intent,
    )


def _kadabra_attack_proposal(view) -> Proposal | None:
    option = _kadabra_attack_option(view)
    active = view.active
    target = view.opponent_active
    if (
        option is None
        or not view.is_own_turn
        or active is None
        or int(active.id) != int(CardId.KADABRA)
        or not view.has_psychic_energy(active)
        or target is None
    ):
        return None
    knocks_out = int(target.hp) <= 50
    return Proposal(
        (option.position,),
        2,
        (
            "ユンゲラーの通常50ダメージで相手をきぜつさせる"
            if knocks_out
            else "優先行動後の物理fallbackとしてユンゲラーの通常50ダメージで削る"
        ),
        (
            "PLAYBOOK-TURN-TWO-NON-KO",
            "PLAYBOOK-STOP-WHEN-KO",
        ),
        alternative="kadabra-physical-damage-after-priority-actions",
    )


def _has_self_effect_immunity(view, pokemon) -> bool:
    meta = view.catalog.card(pokemon.id)
    if meta is None:
        return False
    return any(
        "prevent all effects of attacks" in (normalized := _normalized_text(text))
        and "done to this pokemon" in normalized
        for text in meta.skill_texts
    )


def _has_public_field_effect_immunity(view, pokemon) -> bool:
    target_meta = view.catalog.card(pokemon.id)
    if target_meta is None or not target_meta.is_basic_team_rocket_pokemon:
        return False
    return any(
        "prevent all effects of attacks" in (normalized := _normalized_text(text))
        and "done to your basic team rocket's pokemon" in normalized
        for source in view.opponent_field
        for text in (
            view.catalog.card(source.id).skill_texts
            if view.catalog.card(source.id) is not None
            else ()
        )
    )


def _blocking_energy_cards(view, pokemon):
    meta = view.catalog.card(pokemon.id)
    fighting = meta is not None and meta.is_fighting_pokemon
    return tuple(
        energy
        for energy in pokemon.energy_cards
        if (
            energy.id == MIST_ENERGY_ID
            or (energy.id == ROCK_FIGHTING_ENERGY_ID and fighting)
        )
    )


def _is_hand_power_effect_immune(view, pokemon) -> bool:
    return bool(_blocking_energy_cards(view, pokemon)) or (
        _has_self_effect_immunity(view, pokemon)
        or _has_public_field_effect_immunity(view, pokemon)
    )


def _legal_hammer_serials(view) -> frozenset[int]:
    return frozenset(
        int(option.card_serial)
        for option in view.options
        if option.type == int(OptionType.PLAY)
        and option.card_id == int(CardId.ENHANCED_HAMMER)
        and option.card_serial is not None
    )


def _hand_power_ko_after_public_hammer_chain(
    view,
    pokemon,
    *,
    other_cards_spent: int,
    planned_hammers: int = 0,
) -> bool:
    if (
        pokemon is None
        or _has_self_effect_immunity(view, pokemon)
        or _has_public_field_effect_immunity(view, pokemon)
    ):
        return False
    blockers = tuple(_blocking_energy_cards(view, pokemon))
    blocker_serials = frozenset(
        int(energy.serial)
        for energy in blockers
        if energy.serial is not None
        and view.catalog.is_special_energy(energy.id)
    )
    if len(blocker_serials) != len(blockers):
        return False
    available_hammers = len(_legal_hammer_serials(view)) + max(
        0,
        int(planned_hammers),
    )
    if available_hammers < len(blocker_serials):
        return False
    hand_after = max(
        0,
        view.hand_size - int(other_cards_spent) - len(blocker_serials),
    )
    return hand_after >= ceil(pokemon.hp / 20)


def can_hand_power_ko(
    view,
    hand_size: int | None = None,
    *,
    require_legal_option: bool = True,
    assume_active_psychic: bool = False,
) -> bool:
    """公開盤面上、ハンドパワーで相手をきぜつさせられるか返す。

    効果解決中はMAINの攻撃optionが提示されないため、山札安全計算だけは
    ``require_legal_option=False`` で盤面・エネルギー・状態異常から判定する。
    """
    target = view.opponent_active
    needed = view.required_hand_for_active_ko
    available_hand = view.hand_size if hand_size is None else int(hand_size)
    active = view.active
    attack_ready = (
        _hand_power_option(view) is not None
        if require_legal_option
        else _active_alakazam_is_hand_power_ready(
            view,
            assume_active_psychic=assume_active_psychic,
        )
    )
    return (
        attack_ready
        and target is not None
        and needed is not None
        and available_hand >= needed
        and not _is_hand_power_effect_immune(view, target)
    )


def can_current_legal_attack_ko(view) -> bool:
    """現在提示されている合法ワザのいずれかで相手バトル場を確実に倒せるか。"""
    target = view.opponent_active
    if target is None:
        return False
    for option in view.options:
        if option.type != int(OptionType.ATTACK) or option.attack_id is None:
            continue
        if int(option.attack_id) == int(AttackId.HAND_POWER):
            if can_hand_power_ko(view):
                return True
            continue
        if (
            int(option.attack_id) == int(AttackId.ASSAULT_LANDING)
            and not _stadium_is_in_play(view)
        ):
            continue
        attack = view.catalog.attack_meta.get(int(option.attack_id))
        if attack is not None and int(attack.damage) >= int(target.hp):
            return True
    return False


def ready_bench_alakazam_can_ko(view, hand_size: int) -> bool:
    """前を空けた直後、ベンチの完成済みフーディンで確定KOできるか返す。"""
    target = view.opponent_active
    needed = view.required_hand_for_active_ko
    return (
        view.is_own_turn
        and any(
            int(pokemon.id) == int(CardId.ALAKAZAM)
            and view.has_psychic_energy(pokemon)
            for pokemon in view.bench
        )
        and target is not None
        and needed is not None
        and int(hand_size) >= needed
        and not _is_hand_power_effect_immune(view, target)
    )


def _public_prize_value(view, pokemon) -> int:
    meta = view.catalog.card(pokemon.id)
    return 1 if meta is None else meta.prize_value


def _wins_by_knocking_out(view, pokemon) -> bool:
    return view.own_prize_count <= _public_prize_value(view, pokemon)


def _attack_priority(view, target) -> int:
    if (
        len(view.field) >= 2
        or len(view.opponent_field) <= 1
        or _wins_by_knocking_out(view, target)
    ):
        return 1000
    return 740


def _fan_rotom_active(view):
    active = view.active
    if (
        not is_opening_attack_phase(view)
        or active is None
        or int(active.id) != int(CardId.FAN_ROTOM)
    ):
        return None
    return active


def _stadium_is_in_play(view) -> bool:
    return any(
        card is not None
        for card in (view.current.get("stadium") or [])
    )


def _fan_rotom_attack_option(view):
    if not _is_main_selection(view) or _fan_rotom_active(view) is None:
        return None
    return min(
        (
            option
            for option in view.options
            if option.type == int(OptionType.ATTACK)
            and option.attack_id == int(AttackId.ASSAULT_LANDING)
        ),
        key=lambda option: option.position,
        default=None,
    )


def _fan_rotom_has_energy(view) -> bool:
    active = _fan_rotom_active(view)
    return active is not None and bool(
        active.energies or active.energy_card_ids
    )


def _fan_rotom_attach_option(view):
    active = _fan_rotom_active(view)
    if active is None or _fan_rotom_has_energy(view):
        return None
    energy_rank = {
        int(CardId.BASIC_PSYCHIC): 0,
        int(CardId.TELEPATH_PSYCHIC_ENERGY): 1,
    }
    return min(
        (
            option
            for option in view.options
            if option.type == int(OptionType.ATTACH)
            and option.card_id in energy_rank
            and option.target is not None
            and option.target.serial == active.serial
        ),
        key=lambda option: (
            energy_rank[int(option.card_id)],
            10**9 if option.card_serial is None else int(option.card_serial),
            option.position,
        ),
        default=None,
    )


def _development_supporter_is_playable(view) -> bool:
    return any(
        option.type == int(OptionType.PLAY)
        and option.card_id in (int(CardId.HILDA), int(CardId.DAWN))
        for option in view.options
    )


def _boss_play_option(view):
    return min(
        (
            option
            for option in view.options
            if option.type == int(OptionType.PLAY)
            and option.card_id == int(CardId.BOSSES_ORDERS)
            and option.card_serial is not None
        ),
        key=lambda option: (int(option.card_serial), option.position),
        default=None,
    )


def _fan_rotom_boss_target(view):
    if _boss_play_option(view) is None or _development_supporter_is_playable(view):
        return None
    return min(
        (
            pokemon
            for pokemon in view.opponent_bench
            if pokemon.serial is not None and int(pokemon.hp) <= _FAN_ROTOM_DAMAGE
        ),
        key=lambda pokemon: (
            -_public_prize_value(view, pokemon),
            int(pokemon.hp),
            int(pokemon.serial),
            int(pokemon.id),
        ),
        default=None,
    )


def _fan_rotom_ko_target(view):
    if _fan_rotom_active(view) is None or attack_line_count(view) < 1:
        return None
    active = view.opponent_active
    if active is not None and int(active.hp) <= _FAN_ROTOM_DAMAGE:
        return active
    return _fan_rotom_boss_target(view)


def _fan_rotom_stadium_proposal(view) -> Proposal | None:
    if _fan_rotom_ko_target(view) is None or _stadium_is_in_play(view):
        return None
    if not (_fan_rotom_has_energy(view) or _fan_rotom_attach_option(view) is not None):
        return None
    option = min(
        (
            candidate
            for candidate in view.options
            if candidate.type == int(OptionType.PLAY)
            and candidate.card_id == int(CardId.BATTLE_CAGE)
            and candidate.card_serial is not None
        ),
        key=lambda candidate: (int(candidate.card_serial), candidate.position),
        default=None,
    )
    if option is None:
        return None
    return Proposal(
        (option.position,),
        _FAN_ROTOM_STADIUM_PRIORITY,
        "スピンロトムの70ダメージで確実にKOするため、先にスタジアムを出す",
        ("PLAYBOOK-BATTLE-CAGE", "PLAYBOOK-STOP-WHEN-KO"),
    )


def _fan_rotom_attach_proposal(view) -> Proposal | None:
    if _fan_rotom_ko_target(view) is None or not _stadium_is_in_play(view):
        return None
    option = _fan_rotom_attach_option(view)
    if option is None:
        return None
    return Proposal(
        (option.position,),
        _FAN_ROTOM_ATTACH_PRIORITY,
        "70ダメージで確実にKOできる例外局面なのでスピンロトムへエネルギーを付ける",
        (
            "FLOW-ATTACK-ENERGY",
            "PLAYBOOK-BASIC-PSYCHIC",
            "PLAYBOOK-STOP-WHEN-KO",
        ),
    )


def _fan_rotom_boss_proposal(view) -> Proposal | None:
    target = _fan_rotom_boss_target(view)
    boss = _boss_play_option(view)
    if (
        target is None
        or boss is None
        or not _stadium_is_in_play(view)
        or _fan_rotom_attack_option(view) is None
    ):
        return None
    intent = PendingIntent.from_view(
        view,
        kind="BOSS_KO_TARGET",
        card_ids=(target.id,),
        target_serial=target.serial,
        max_cards=1,
        metadata=(("reason", "他の展開サポートがなく、70ダメージで確実にKOできる公開対象"),),
        effect_card_id=CardId.BOSSES_ORDERS,
        effect_serial=boss.card_serial,
        remaining_contexts=(SelectContext.SWITCH,),
    )
    return Proposal(
        (boss.position,),
        _FAN_ROTOM_BOSS_PRIORITY,
        "ヒカリ・トウコで展開できないため、ボスで70ダメージ圏内だけを呼び出す",
        ("FLOW-ATTACK-BOSS", "PLAYBOOK-BOSS", "PLAYBOOK-STOP-WHEN-KO"),
        intent,
    )


def _fan_rotom_attack_proposal(view) -> Proposal | None:
    target = view.opponent_active
    option = _fan_rotom_attack_option(view)
    if (
        option is None
        or target is None
        or _fan_rotom_ko_target(view) is None
        or int(target.hp) > _FAN_ROTOM_DAMAGE
        or not _stadium_is_in_play(view)
    ):
        return None
    return Proposal(
        (option.position,),
        _FAN_ROTOM_ATTACK_PRIORITY,
        f"スピンロトムの70ダメージで残りHP{target.hp}を確実にKOする",
        ("PLAYBOOK-STOP-WHEN-KO", "PLAYBOOK-BOARD-MINIMUM"),
    )


def _fan_rotom_fast_ko_proposal(view) -> Proposal | None:
    return max(
        (
            proposal
            for proposal in (
                _fan_rotom_stadium_proposal(view),
                _fan_rotom_attach_proposal(view),
                _fan_rotom_boss_proposal(view),
                _fan_rotom_attack_proposal(view),
            )
            if proposal is not None
        ),
        key=lambda proposal: proposal.priority,
        default=None,
    )


def _hammer_play_option(view):
    if not _is_main_selection(view):
        return None
    return min(
        (
            option
            for option in view.options
            if option.type == int(OptionType.PLAY)
            and option.card_id == int(CardId.ENHANCED_HAMMER)
            and option.card_serial is not None
        ),
        key=lambda option: (int(option.card_serial), option.position),
        default=None,
    )


def _powered_attack_role_exists(view, memory) -> bool:
    reserved_serial = memory.reserved_attacker_serial
    for pokemon in view.field:
        if not view.has_psychic_energy(pokemon):
            continue
        if int(pokemon.id) in (
            int(CardId.KADABRA),
            int(CardId.ALAKAZAM),
        ):
            return True
        if reserved_serial is not None and pokemon.serial == reserved_serial:
            return True
    return False


def _powered_kadabra_can_evolve_now(view) -> bool:
    return any(
        option.type == int(OptionType.EVOLVE)
        and option.card_id == int(CardId.ALAKAZAM)
        and option.target is not None
        and int(option.target.id) == int(CardId.KADABRA)
        and view.has_psychic_energy(option.target)
        for option in view.options
    )


def _powered_candy_route_can_evolve_now(view, pokemon) -> bool:
    return (
        pokemon is not None
        and int(pokemon.id) == int(CardId.ABRA)
        and pokemon.serial is not None
        and any(abra.serial == pokemon.serial for abra in view.eligible_abras)
        and view.has_psychic_energy(pokemon)
        and int(CardId.RARE_CANDY) in view.hand_ids
        and int(CardId.ALAKAZAM) in view.hand_ids
        and any(
            option.type == int(OptionType.PLAY)
            and option.card_id == int(CardId.RARE_CANDY)
            for option in view.options
        )
    )


def _opening_powered_candy_route_can_evolve_now(view) -> bool:
    return (
        is_opening_attack_phase(view)
        and not any(
            int(pokemon.id) == int(CardId.ALAKAZAM)
            and view.has_psychic_energy(pokemon)
            for pokemon in view.field
        )
        and any(
            pokemon.area == int(Area.BENCH)
            and _powered_candy_route_can_evolve_now(view, pokemon)
            for pokemon in view.eligible_abras
        )
    )


def _kadabra_draw_available(view) -> bool:
    return any(
        option.type == int(OptionType.EVOLVE)
        and option.card_id == int(CardId.KADABRA)
        for option in view.options
    )


def _active_dunsparce_can_evolve_now(view) -> bool:
    active = view.active
    return active is not None and any(
        option.type == int(OptionType.EVOLVE)
        and option.card_id == int(CardId.DUDUNSPARCE)
        and option.target is not None
        and option.target.serial == active.serial
        for option in view.options
    )


def _active_dudunsparce_can_return_now(view) -> bool:
    active = view.active
    return active is not None and any(
        option.type == int(OptionType.ABILITY)
        and option.card_id == int(CardId.DUDUNSPARCE)
        and option.source is not None
        and option.source.serial == active.serial
        for option in view.options
    )


def _dunsparce_can_evolve_now(view) -> bool:
    return any(
        option.type == int(OptionType.EVOLVE)
        and option.card_id == int(CardId.DUDUNSPARCE)
        and option.target is not None
        and int(option.target.id) == int(CardId.DUNSPARCE)
        for option in view.options
    )


def _air_balloon_can_attach_to_active(view) -> bool:
    active = view.active
    return active is not None and any(
        option.type == int(OptionType.ATTACH)
        and option.card_id == int(CardId.AIR_BALLOON)
        and option.target is not None
        and option.target.serial == active.serial
        for option in view.options
    )


def _psychic_attach_proposal(view, memory) -> Proposal | None:
    if not _is_main_selection(view) or _hand_power_option(view) is not None:
        return None
    if (
        _powered_kadabra_can_evolve_now(view)
        or _opening_powered_candy_route_can_evolve_now(view)
    ):
        return None
    basic_can_power_alakazam = any(
        option.type == int(OptionType.ATTACH)
        and option.card_id == int(CardId.BASIC_PSYCHIC)
        and option.target is not None
        and int(option.target.id) == int(CardId.ALAKAZAM)
        and not view.has_psychic_energy(option.target)
        for option in view.options
    )
    defer_energy_until_kadabra_draw = (
        int(CardId.RARE_CANDY) not in view.hand_ids
        and _kadabra_draw_available(view)
        and not basic_can_power_alakazam
    )
    telepath_compression_before_draw = (
        int(CardId.RARE_CANDY) not in view.hand_ids
        and sum(
            int(pokemon.id) == int(CardId.ABRA)
            for pokemon in view.field
        ) == 2
        and len(view.bench) < int(view.own.get("benchMax", 5))
    )
    if (
        _dunsparce_can_evolve_now(view)
        and not telepath_compression_before_draw
    ):
        return None
    active = view.active
    searchable_powered_kadabra_pivot = (
        active is not None
        and int(active.id) not in _ATTACKER_IDS
        and int(CardId.ALAKAZAM) not in view.hand_ids
        and card_may_be_in_deck(view, memory, CardId.ALAKAZAM)
        and any(
            int(pokemon.id) == int(CardId.KADABRA)
            and not pokemon.appear_this_turn
            and view.has_psychic_energy(pokemon)
            for pokemon in view.bench
        )
        and any(
            option.type == int(OptionType.PLAY)
            and option.card_id == int(CardId.DAWN)
            for option in view.options
        )
    )
    if searchable_powered_kadabra_pivot:
        return None
    immediate_alakazam_target_serials = {
        int(option.target.serial)
        for option in view.options
        if (
            option.type == int(OptionType.EVOLVE)
            and option.card_id == int(CardId.ALAKAZAM)
            and option.target is not None
            and option.target.serial is not None
            and not view.has_psychic_energy(option.target)
        )
    }
    candy_route_ready = (
        int(CardId.RARE_CANDY) in view.hand_ids
        and int(CardId.ALAKAZAM) in view.hand_ids
        and any(
            option.type == int(OptionType.PLAY)
            and option.card_id == int(CardId.RARE_CANDY)
            for option in view.options
        )
    )
    searchable_candy_route_ready = (
        int(CardId.RARE_CANDY) in view.hand_ids
        and int(CardId.ALAKAZAM) not in view.hand_ids
        and not any(
            int(pokemon.id) == int(CardId.ALAKAZAM)
            for pokemon in view.field
        )
        and card_may_be_in_deck(view, memory, CardId.ALAKAZAM)
        and any(
            option.type == int(OptionType.PLAY)
            and option.card_id == int(CardId.POKE_PAD)
            for option in view.options
        )
    )
    powered_candy_target_exists = any(
        view.has_psychic_energy(pokemon)
        for pokemon in view.eligible_abras
    )
    attachable_abra_serials = {
        int(option.target.serial)
        for option in view.options
        if (
            option.type == int(OptionType.ATTACH)
            and option.card_id in (
                int(CardId.BASIC_PSYCHIC),
                int(CardId.TELEPATH_PSYCHIC_ENERGY),
            )
            and option.target is not None
            and option.target.id == int(CardId.ABRA)
            and option.target.serial is not None
            and not view.has_psychic_energy(option.target)
        )
    }
    if (
        candy_route_ready or searchable_candy_route_ready
    ) and not powered_candy_target_exists:
        candy_target = min(
            (
                pokemon
                for pokemon in view.eligible_abras
                if pokemon.serial in attachable_abra_serials
            ),
            key=lambda pokemon: (
                0
                if (
                    view.own_turn_number >= 2
                    and active is not None
                    and pokemon.serial == active.serial
                )
                else 1,
                10**9 if pokemon.serial is None else int(pokemon.serial),
                int(pokemon.area),
                int(pokemon.index or 0),
            ),
            default=None,
        )
        if candy_target is not None and candy_target.serial is not None:
            immediate_alakazam_target_serials.add(int(candy_target.serial))
    immediate_alakazam_target_serials = frozenset(
        immediate_alakazam_target_serials
    )
    future_alakazam_target_serials = frozenset(
        int(pokemon.serial)
        for pokemon in view.field
        if (
            int(pokemon.id) == int(CardId.KADABRA)
            and pokemon.serial is not None
            and not view.has_psychic_energy(pokemon)
        )
    )
    old_unpowered_abra_serials = frozenset(
        int(pokemon.serial)
        for pokemon in view.field
        if (
            int(pokemon.id) == int(CardId.ABRA)
            and pokemon.serial is not None
            and not pokemon.appear_this_turn
            and not view.has_psychic_energy(pokemon)
        )
    )
    reserve_old_abra_before_next_kadabra_draw = (
        is_opening_attack_phase(view)
        and len(old_unpowered_abra_serials) >= 2
        and _kadabra_draw_available(view)
        and any(
            int(pokemon.id) == int(CardId.KADABRA)
            and pokemon.appear_this_turn
            for pokemon in view.field
        )
        and not any(
            int(pokemon.id) == int(CardId.KADABRA)
            and not pokemon.appear_this_turn
            and not view.has_psychic_energy(pokemon)
            for pokemon in view.field
        )
    )
    active_unpowered_alakazam = (
        active is not None
        and int(active.id) == int(CardId.ALAKAZAM)
        and not view.has_psychic_energy(active)
    )
    unpowered_alakazam_exists = any(
        int(pokemon.id) == int(CardId.ALAKAZAM)
        and not view.has_psychic_energy(pokemon)
        for pokemon in view.field
    )
    powered_alakazam_exists = any(
        int(pokemon.id) == int(CardId.ALAKAZAM)
        and view.has_psychic_energy(pokemon)
        for pokemon in view.field
    )
    powered_bench_alakazam_exists = any(
        int(pokemon.id) == int(CardId.ALAKAZAM)
        and view.has_psychic_energy(pokemon)
        for pokemon in view.bench
    )
    if (
        powered_bench_alakazam_exists
        and active is not None
        and int(active.id) not in _ATTACKER_IDS
    ):
        return None
    if (
        _powered_attack_role_exists(view, memory)
        and not active_unpowered_alakazam
        and (powered_alakazam_exists or not unpowered_alakazam_exists)
        and not immediate_alakazam_target_serials
        and not future_alakazam_target_serials
    ):
        return None

    reserved_serial = memory.reserved_attacker_serial
    stage_rank = {
        int(CardId.ALAKAZAM): 0,
        int(CardId.KADABRA): 1,
        int(CardId.ABRA): 2,
    }
    candidates = tuple(
        option
        for option in view.options
        if (
            option.type == int(OptionType.ATTACH)
            and option.card_id in (
                int(CardId.BASIC_PSYCHIC),
                int(CardId.TELEPATH_PSYCHIC_ENERGY),
            )
            and option.target is not None
            and int(option.target.id) in _ATTACKER_IDS
            and not view.has_psychic_energy(option.target)
            and not (
                defer_energy_until_kadabra_draw
                and (
                    option.card_id == int(CardId.BASIC_PSYCHIC)
                    or not telepath_compression_before_draw
                )
            )
        )
    )
    if not candidates:
        return None

    def key(option):
        target = option.target
        active_alakazam = (
            active is not None
            and int(active.id) == int(CardId.ALAKAZAM)
            and target.serial == active.serial
        )
        active_turn_two_attacker = (
            view.own_turn_number >= 2
            and active is not None
            and int(active.id) in _ATTACKER_IDS
            and target.serial == active.serial
        )
        mature_active_kadabra = (
            active_turn_two_attacker
            and int(target.id) == int(CardId.KADABRA)
            and not target.appear_this_turn
        )
        reserved = (
            reserved_serial is not None
            and target.serial == reserved_serial
        )
        immediate_alakazam_target = (
            target.serial is not None
            and int(target.serial) in immediate_alakazam_target_serials
        )
        active_immediate_alakazam_target = (
            immediate_alakazam_target
            and active is not None
            and target.serial == active.serial
        )
        future_alakazam_target = (
            target.serial is not None
            and int(target.serial) in future_alakazam_target_serials
        )
        candy_draw_reserve = (
            reserve_old_abra_before_next_kadabra_draw
            and target.serial is not None
            and int(target.serial) in old_unpowered_abra_serials
        )
        active_candy_draw_reserve = (
            candy_draw_reserve
            and active is not None
            and target.serial == active.serial
        )
        reserved_candy_draw_reserve = candy_draw_reserve and reserved
        target_rank = (
            0 if active_alakazam
            else 1 if active_immediate_alakazam_target
            else 2 if int(target.id) == int(CardId.ALAKAZAM)
            else 3 if immediate_alakazam_target
            else 4 if mature_active_kadabra
            else 5 if active_candy_draw_reserve
            else 6 if reserved_candy_draw_reserve
            else 7 if candy_draw_reserve
            else 8 if future_alakazam_target
            else 9 if active_turn_two_attacker
            else 10 if reserved
            else 11 + stage_rank[int(target.id)]
        )
        telepath_first = (
            option.card_id == int(CardId.TELEPATH_PSYCHIC_ENERGY)
            and (
                view.own_turn_number == 1
                or telepath_compression_before_draw
            )
        )
        energy_rank = (
            0
            if telepath_first
            or (
                view.own_turn_number != 1
                and not telepath_compression_before_draw
                and option.card_id == int(CardId.BASIC_PSYCHIC)
            )
            else 1
        )
        target_serial = 10**9 if target.serial is None else int(target.serial)
        card_serial = 10**9 if option.card_serial is None else int(option.card_serial)
        return (
            target_rank,
            energy_rank,
            target_serial,
            card_serial,
            option.position,
        )

    option = min(candidates, key=key)
    rule_ids = ["FLOW-ATTACK-ENERGY", "PLAYBOOK-BASIC-PSYCHIC"]
    if (
        view.own_turn_number == 1
        and option.card_id == int(CardId.TELEPATH_PSYCHIC_ENERGY)
    ):
        rule_ids.append("PLAYBOOK-T1-TELEPATH")
    reason = "Hand Powerの攻撃エネルギーが不足している攻撃役へ超エネルギーを付ける"
    next_intent = None
    if option.card_id == int(CardId.TELEPATH_PSYCHIC_ENERGY):
        rule_ids.extend(("PLAYBOOK-TELEPATH-LIMIT", "PLAYBOOK-SEARCH-INTENT"))
        next_intent = build_telepath_bench_intent(
            view,
            option,
            option.target,
            reason,
            memory,
        )
    compression_precedes_random_draw = (
        telepath_compression_before_draw
        and option.card_id == int(CardId.TELEPATH_PSYCHIC_ENERGY)
        and next_intent is not None
        and (next_intent.max_cards or 0) > 0
    )
    priority = 900
    if compression_precedes_random_draw:
        priority = 935
        reason = (
            "ケーシィ2匹・ふしぎなアメなしなので、テレパス超で山札を"
            "1枚圧縮してからランダムドローする"
        )
        rule_ids.append("PLAYBOOK-MAX-DRAW")
        next_intent = build_telepath_bench_intent(
            view,
            option,
            option.target,
            reason,
            memory,
        )
    return Proposal(
        (option.position,),
        priority,
        reason,
        tuple(rule_ids),
        next_intent,
    )


def _opponent_attack_blocks_one_energy_retreat(view, memory) -> bool:
    """直前の公開ワザが退避禁止・退避コスト増加を残しているか返す。"""
    current_turn = int(view.current.get("turn", 0))
    for action in reversed(getattr(memory, "opponent_actions", ())):
        if action.attack_id is None or int(action.turn) != current_turn:
            continue
        text = str(
            view.catalog.attack_text.get(int(action.attack_id), "")
        ).replace("’", "'").lower()
        if "during your opponent's next turn" not in text:
            continue
        if (
            "can't retreat" in text
            or "cannot retreat" in text
            or "retreat cost is" in text
        ):
            return True
    return False


def _turn_three_retreat_energy_attach(view, memory) -> Proposal | None:
    if not _is_main_selection(view) or view.own_turn_number < 2:
        return None
    active = view.active
    if active is None or (
        int(active.id) == int(CardId.ALAKAZAM)
        and view.has_psychic_energy(active)
    ):
        return None
    if (
        _active_dunsparce_can_evolve_now(view)
        or _active_dudunsparce_can_return_now(view)
        or _air_balloon_can_attach_to_active(view)
        or _kadabra_draw_available(view)
    ):
        return None
    if not any(
        int(pokemon.id) == int(CardId.ALAKAZAM)
        and view.has_psychic_energy(pokemon)
        for pokemon in view.bench
    ):
        return None

    from rules.continuity import rich_retreat_enables_priority_goal
    legal_retreat_now = any(
        option.type == int(OptionType.RETREAT)
        for option in view.options
    )
    # CABTは逃げコストをまだ満たしていない時点ではRETREATをlegal optionへ
    # 出さない。1逃げの前にエネルギーが1枚もなく、特殊状態・既退避でも
    # ない場合だけ、手貼り直後にRETREATが現れることを公開情報から確定する。
    retreat_becomes_legal_after_attach = (
        int(active.id) in ONE_RETREAT_IDS
        and not active.energy_cards
        and not active.energy_card_ids
        and bool(view.bench)
        and not bool(view.current.get("retreated", False))
        and not any(
            bool(view.own.get(status))
            for status in ("asleep", "paralyzed")
        )
        and not _opponent_attack_blocks_one_energy_retreat(view, memory)
    )
    certain_pivot_ko = (
        int(active.id) in ONE_RETREAT_IDS
        and (legal_retreat_now or retreat_becomes_legal_after_attach)
        and _hand_power_ko_after_public_hammer_chain(
            view,
            view.opponent_active,
            other_cards_spent=1,
        )
    )
    rich_enables_ko = (
        int(active.id) in ONE_RETREAT_IDS
        and not _is_hand_power_effect_immune(view, view.opponent_active)
        if view.opponent_active is not None
        else False
    ) and rich_retreat_enables_priority_goal(
        view,
        memory,
        attach_from_hand=True,
    )

    options = tuple(
        candidate
        for candidate in view.options
        if candidate.type == int(OptionType.ATTACH)
        and (
            candidate.card_id in (
                int(CardId.BASIC_PSYCHIC),
                int(CardId.TELEPATH_PSYCHIC_ENERGY),
            )
            or (
                candidate.card_id == int(CardId.ENRICHING_ENERGY)
                and rich_enables_ko
            )
        )
        and candidate.target is not None
        and candidate.target.area == int(Area.ACTIVE)
        and candidate.target.serial == active.serial
    )
    option = min(
        (
            candidate
            for candidate in options
        ),
        key=lambda candidate: (
            {
                int(CardId.BASIC_PSYCHIC): 0,
                int(CardId.TELEPATH_PSYCHIC_ENERGY): 1,
                int(CardId.ENRICHING_ENERGY): 2,
            }.get(int(candidate.card_id), 3),
            candidate.position,
        ),
        default=None,
    )
    if option is None:
        return None
    emergency_telepath = option.card_id == int(CardId.TELEPATH_PSYCHIC_ENERGY)
    emergency_rich = option.card_id == int(CardId.ENRICHING_ENERGY)
    if emergency_telepath and (
        any(
            candidate.type == int(OptionType.PLAY)
            and candidate.card_id == int(CardId.HILDA)
            for candidate in view.options
        )
        or any(
            candidate.type == int(OptionType.ABILITY)
            and candidate.card_id in (
                int(CardId.DUDUNSPARCE),
                int(CardId.FEZANDIPITI_EX),
            )
            for candidate in view.options
        )
        or any(
            candidate.type == int(OptionType.EVOLVE)
            and candidate.card_id in (
                int(CardId.KADABRA),
                int(CardId.ALAKAZAM),
            )
            for candidate in view.options
        )
        or (
            int(CardId.RARE_CANDY) in view.hand_ids
            and int(CardId.ALAKAZAM) in view.hand_ids
            and any(
                candidate.type == int(OptionType.PLAY)
                and candidate.card_id == int(CardId.RARE_CANDY)
                for candidate in view.options
            )
        )
    ) and not certain_pivot_ko:
        return None
    reason = (
        f"{view.own_turn_number}ターン目の攻撃を開始するため、"
        + (
            "他の退避経路がない最終手段としてリッチを前の逃げコストにする"
            if emergency_rich
            else
            "他の退避経路がない場合だけテレパス超を前の逃げコストとして確保する"
            if emergency_telepath
            else "基本超を前の逃げコストとして確保する"
        )
    )
    rule_ids = [
        "FLOW-ATTACK-HAND",
        "PLAYBOOK-PROMOTE-COMPLETE",
        "PLAYBOOK-NO-ENRICHING-RETREAT",
    ]
    next_intent = None
    if emergency_telepath:
        rule_ids.extend(("PLAYBOOK-TELEPATH-LIMIT", "PLAYBOOK-SEARCH-INTENT"))
        next_intent = build_telepath_bench_intent(
            view,
            option,
            active,
            reason,
            memory,
        )
    return Proposal(
        (option.position,),
        (
            OPENING_PIVOT_ATTACH_PRIORITY
            if is_opening_attack_phase(view)
            else 985
        ),
        reason,
        tuple(rule_ids),
        next_intent,
        alternative=(
            "リッチを消費しても同番KOできるため、完成済みフーディンを攻撃位置へ出す"
            if emergency_rich
            else "リッチは逃げコスト用に貼らず、テレパス超も他の退避・ドロー経路を使い切ってから使う"
        ),
    )


def _retreat_to_powered_alakazam(view) -> Proposal | None:
    if not _is_main_selection(view):
        return None
    active = view.active
    if active is None or (
        int(active.id) == int(CardId.ALAKAZAM)
        and view.has_psychic_energy(active)
    ):
        return None
    retreat = min(
        (
            option
            for option in view.options
            if option.type == int(OptionType.RETREAT)
        ),
        key=lambda option: option.position,
        default=None,
    )
    powered_alakazam = min(
        (
            pokemon
            for pokemon in view.bench
            if int(pokemon.id) == int(CardId.ALAKAZAM)
            and view.has_psychic_energy(pokemon)
        ),
        key=lambda pokemon: (
            10**9 if pokemon.serial is None else int(pokemon.serial),
            int(pokemon.index or 0),
        ),
        default=None,
    )
    if retreat is None or powered_alakazam is None:
        return None

    attached_energy_ids = tuple(int(card_id) for card_id in active.energy_card_ids)
    has_balloon = int(CardId.AIR_BALLOON) in active.tool_ids
    only_enriching_would_be_spent = (
        bool(attached_energy_ids)
        and all(
            card_id == int(CardId.ENRICHING_ENERGY)
            for card_id in attached_energy_ids
        )
        and not has_balloon
    )
    from rules.continuity import rich_retreat_enables_priority_goal
    if only_enriching_would_be_spent and not rich_retreat_enables_priority_goal(
        view,
        None,
        attach_from_hand=False,
    ):
        return None

    target = view.opponent_active
    immediate_ko = (
        target is not None
        and view.hand_size >= ceil(target.hp / 20)
        and not _is_hand_power_effect_immune(view, target)
    )
    return Proposal(
        (retreat.position,),
        (
            OPENING_PIVOT_RETREAT_PRIORITY
            if is_opening_attack_phase(view)
            else 995 if immediate_ko else 760
        ),
        "退避役をにがして、超エネルギー付きフーディンをバトル場へ出す",
        (
            "FLOW-ATTACK-HAND",
            "PLAYBOOK-PROMOTE-COMPLETE",
            "PLAYBOOK-NO-ENRICHING-RETREAT",
        ),
        alternative=f"target_serial={powered_alakazam.serial}",
    )


def _retreat_to_preserve_only_active_abra(view) -> Proposal | None:
    if not _is_main_selection(view):
        return None
    active = view.active
    pivot = opening_abra_survival_pivot(view)
    if (
        active is None
        or pivot is None
        or int(CardId.AIR_BALLOON) not in active.tool_ids
    ):
        return None
    retreat = min(
        (
            option
            for option in view.options
            if option.type == int(OptionType.RETREAT)
        ),
        key=lambda option: option.position,
        default=None,
    )
    if retreat is None:
        return None
    return Proposal(
        (retreat.position,),
        OPENING_PIVOT_RETREAT_PRIORITY,
        "最初の場に1体しかいない唯一のケーシィを守り、退避役を前へ出す",
        (
            "PLAYBOOK-PRESERVE-ABRA",
            "PLAYBOOK-AIR-BALLOON",
            "PLAYBOOK-BOARD-MINIMUM",
        ),
        alternative=f"target_serial={pivot.serial}",
    )


def _active_can_complete_hand_power_this_turn(view) -> bool:
    active = view.active
    if active is None or _active_attack_is_blocked(view):
        return False
    if int(active.id) == int(CardId.ALAKAZAM):
        return (
            (
                _hand_power_option(view) is not None
                and _active_alakazam_is_hand_power_ready(view)
            )
            or (
                not view.has_psychic_energy(active)
                and any(
                    option.type == int(OptionType.ATTACH)
                    and option.card_id in (
                        int(CardId.BASIC_PSYCHIC),
                        int(CardId.TELEPATH_PSYCHIC_ENERGY),
                    )
                    and option.target is not None
                    and option.target.serial == active.serial
                    for option in view.options
                )
            )
        )
    if not view.has_psychic_energy(active):
        return False
    if int(active.id) == int(CardId.KADABRA):
        return any(
            option.type == int(OptionType.EVOLVE)
            and option.card_id == int(CardId.ALAKAZAM)
            and option.target is not None
            and option.target.serial == active.serial
            for option in view.options
        )
    return _powered_candy_route_can_evolve_now(view, active)


def _survival_retreat_proposal(view) -> Proposal | None:
    if (
        not _is_main_selection(view)
        or can_hand_power_ko(view)
        or _active_can_complete_hand_power_this_turn(view)
    ):
        return None
    retreat = min(
        (
            option
            for option in view.options
            if option.type == int(OptionType.RETREAT)
        ),
        key=lambda option: option.position,
        default=None,
    )
    target = best_survival_retreat_target(view)
    active = view.active
    if retreat is None or target is None or target.serial is None or active is None:
        return None
    pays_energy = (
        bool(active.energy_cards)
        and int(CardId.AIR_BALLOON) not in active.tool_ids
    )
    contexts = (
        (int(SelectContext.DISCARD_ENERGY), int(SelectContext.SWITCH))
        if pays_energy
        else (int(SelectContext.SWITCH),)
    )
    intent = PendingIntent.effectless_from_view(
        view,
        kind="SURVIVAL_RETREAT",
        target_serial=int(target.serial),
        remaining_contexts=contexts,
        metadata=(("reason", "相手の公開済み攻撃で失うサイドを減らす"),),
    )
    return Proposal(
        (retreat.position,),
        1100,
        "相手の公開済み攻撃によるバトル場とベンチの同時KOを減らすため退避する",
        (
            "PLAYBOOK-PROMOTE-COMPLETE",
            "PLAYBOOK-PRESERVE-ABRA",
            "PLAYBOOK-NO-ENRICHING-RETREAT",
        ),
        intent,
        alternative=f"target_serial={target.serial}",
    )


def _special_energy_candidates(view):
    candidates = []
    for pokemon in view.opponent_field:
        if pokemon.serial is None:
            continue
        blockers = {energy.serial for energy in _blocking_energy_cards(view, pokemon)}
        for energy in pokemon.energy_cards:
            if (
                energy.serial is None
                or not view.catalog.is_special_energy(energy.id)
            ):
                continue
            candidates.append((pokemon, energy, energy.serial in blockers))
    return tuple(candidates)


def hammer_allowed_energy_ids(memory) -> frozenset[int] | None:
    profile = None if memory is None else memory.opponent_profile
    if profile is None:
        return IMMUNITY_ENERGIES
    reserve = profile.reserves_hammer_for_immunity
    if reserve is False:
        return None
    if reserve is None:
        return IMMUNITY_ENERGIES
    allowed = set()
    if profile.mist_energy_counts:
        allowed.add(MIST_ENERGY_ID)
    if profile.rock_fighting_energy_counts:
        allowed.add(ROCK_FIGHTING_ENERGY_ID)
    return frozenset(allowed)


def _is_primary_line_bench(pokemon, profile) -> bool:
    if profile is None or pokemon.area != int(Area.BENCH):
        return False
    visible_ids = {
        int(pokemon.id),
        *(int(card_id) for card_id in pokemon.pre_evolution_ids),
    }
    return any(
        visible_ids.intersection(int(card_id) for card_id in line)
        for line in profile.primary_lines
    )


def _provided_energy_count(view, energy_id: int) -> int:
    meta = view.catalog.card(energy_id)
    if meta is None:
        return 1
    provided = 1
    for text in meta.skill_texts:
        normalized = _normalized_text(text)
        for match in re.finditer(r"\bprovides(?: only)?\s+([2-9])\b", normalized):
            provided = max(provided, int(match.group(1)))
        for match in re.finditer(
            r"\bprovides\s+((?:\{[a-z]+\}){2,})\s+energy\b",
            normalized,
        ):
            provided = max(provided, match.group(1).count("{"))
    return provided


def _boss_play_is_legal(view) -> bool:
    return any(
        option.type == int(OptionType.PLAY)
        and option.card_id == int(CardId.BOSSES_ORDERS)
        and option.card_serial is not None
        for option in view.options
    )


def _hammer_unlocks_hand_power_ko(
    view,
    pokemon,
    energy,
    blocks_hand_power: bool,
    *,
    hand_spent: int,
    planned_hammers: int,
) -> bool:
    if (
        not blocks_hand_power
        or energy.serial is None
        or _hand_power_option(view) is None
    ):
        return False
    if pokemon.area == int(Area.ACTIVE):
        other_cards_spent = max(0, int(hand_spent) - 1)
    elif pokemon.area == int(Area.BENCH) and _boss_play_is_legal(view):
        other_cards_spent = max(0, int(hand_spent) - 1) + 1
    else:
        return False
    return _hand_power_ko_after_public_hammer_chain(
        view,
        pokemon,
        other_cards_spent=other_cards_spent,
        planned_hammers=planned_hammers,
    )


def _best_hammer_target(
    view,
    memory,
    *,
    hand_spent: int,
    planned_hammers: int = 0,
) -> HammerTarget | None:
    candidates = _special_energy_candidates(view)
    if not candidates:
        return None

    hand_after = max(0, view.hand_size - int(hand_spent))
    required_hand = view.required_hand_for_active_ko
    loses_raw_hand_power_ko = (
        _hand_power_option(view) is not None
        and required_hand is not None
        and view.hand_size >= required_hand
        and hand_after < required_hand
    )
    active_is_koed = can_hand_power_ko(view)
    if active_is_koed and loses_raw_hand_power_ko:
        return None

    unlocking_candidates = tuple(
        candidate
        for candidate in candidates
        if _hammer_unlocks_hand_power_ko(
            view,
            *candidate,
            hand_spent=hand_spent,
            planned_hammers=planned_hammers,
        )
    )

    def serial_key(candidate):
        pokemon, energy, _ = candidate
        pokemon_serial = 10**9 if pokemon.serial is None else int(pokemon.serial)
        energy_serial = 10**9 if energy.serial is None else int(energy.serial)
        return pokemon_serial, energy_serial, int(energy.id)

    if unlocking_candidates:
        def unlock_key(candidate):
            pokemon, energy, _ = candidate
            provided_count = _provided_energy_count(view, energy.id)
            active_rank = 0 if pokemon.area == int(Area.ACTIVE) else 1
            return (
                0 if provided_count >= 2 else 1,
                -provided_count,
                active_rank,
                *serial_key(candidate),
            )

        candidates = unlocking_candidates
        key = unlock_key
    else:
        allowed_energy_ids = hammer_allowed_energy_ids(memory)
        candidates = tuple(
            candidate
            for candidate in candidates
            if not (
                active_is_koed
                and candidate[0].area == int(Area.ACTIVE)
            )
            and not (
                loses_raw_hand_power_ko
                and candidate[0].area == int(Area.ACTIVE)
                and candidate[2]
            )
            and (
                allowed_energy_ids is None
                or int(candidate[1].id) in allowed_energy_ids
            )
        )
        if not candidates:
            return None
        profile = None if memory is None else memory.opponent_profile

        def general_key(candidate):
            pokemon, energy, _ = candidate
            provided_count = _provided_energy_count(view, energy.id)
            if _is_primary_line_bench(pokemon, profile):
                target_rank = 0
            elif provided_count >= 2:
                target_rank = 1
            elif pokemon.area == int(Area.ACTIVE):
                target_rank = 2
            else:
                target_rank = 3
            return target_rank, *serial_key(candidate)

        key = general_key

    pokemon, energy, blocks_hand_power = min(candidates, key=key)
    unlocks_ko = _hammer_unlocks_hand_power_ko(
        view,
        pokemon,
        energy,
        blocks_hand_power,
        hand_spent=hand_spent,
        planned_hammers=planned_hammers,
    )
    profile = None if memory is None else memory.opponent_profile
    profile_key = "unknown" if profile is None else profile.key
    if pokemon.serial is None or energy.serial is None:
        return None
    return HammerTarget(
        int(pokemon.serial),
        int(pokemon.id),
        int(energy.serial),
        int(energy.id),
        unlocks_ko,
        profile_key,
    )


@covers("FLOW-ATTACK-HAMMER", "PLAYBOOK-ENHANCED-HAMMER")
def choose_hammer_proposal(view, memory) -> Proposal | None:
    hammer = _hammer_play_option(view)
    if hammer is None:
        return None
    target = _best_hammer_target(view, memory, hand_spent=1)
    if target is None:
        return None
    defensive_opening_hammer = (
        is_opening_attack_phase(view)
        and _opening_hammer_removes_only_attack_energy(view, target)
    )
    if (
        is_opening_attack_phase(view)
        and not target.unlocks_ko
        and not defensive_opening_hammer
    ):
        return None
    hand_after = max(0, view.hand_size - 1)
    generic_priority = (
        840
        if is_opening_attack_phase(view) and not powered_alakazam_exists(view)
        else 870
    )
    intent = PendingIntent.from_view(
        view,
        kind="DISCARD_SPECIAL_ENERGY",
        card_ids=(target.energy_id,),
        target_serial=target.pokemon_serial,
        max_cards=1,
        metadata=(
            ("energy_serial", target.energy_serial),
            ("reason", "Hand Powerのダメカン効果への免疫を外す"
             if target.unlocks_ko else "公開特殊エネルギーを妨害する"),
        ),
        effect_card_id=CardId.ENHANCED_HAMMER,
        effect_serial=hammer.card_serial,
        remaining_contexts=(SelectContext.DISCARD_ENERGY,),
    )
    return Proposal(
        (hammer.position,),
        980 if target.unlocks_ko else generic_priority,
        "Hand Powerのダメカン効果を防ぐ特殊エネルギーを先に外す"
        if target.unlocks_ko else "相手の公開特殊エネルギーを改造ハンマーで外す",
        ("FLOW-ATTACK-HAMMER", "PLAYBOOK-ENHANCED-HAMMER"),
        intent,
        alternative=(
            f"profile_key={target.profile_key},energy_id={target.energy_id},"
            f"target_serial={target.pokemon_serial},hand_after={hand_after}"
        ),
    )


def _opening_hammer_removes_only_attack_energy(
    view,
    target: HammerTarget,
) -> bool:
    pokemon = next(
        (
            candidate
            for candidate in view.opponent_field
            if candidate.serial is not None
            and int(candidate.serial) == int(target.pokemon_serial)
        ),
        None,
    )
    if (
        pokemon is None
        or pokemon.area != int(Area.ACTIVE)
        or len(pokemon.energy_cards) != 1
        or len(pokemon.energies) != 1
    ):
        return False
    card = view.catalog.card(pokemon.id)
    if card is None:
        return False
    return any(
        (attack := view.catalog.attack_meta.get(int(attack_id))) is not None
        and bool(attack.energies)
        and view.public_attack_is_ready(pokemon, attack_id)
        for attack_id in card.attacks
    )


@covers("FLOW-ATTACK-BOSS", "PLAYBOOK-BOSS")
def plan_hammer_target(view, memory, *, hand_spent: int = 1) -> HammerTarget | None:
    return _best_hammer_target(
        view,
        memory,
        hand_spent=hand_spent,
        planned_hammers=1,
    )


def _known_search_group_count(view, memory, groups) -> int:
    known_deck = None if memory is None else memory.known_deck
    complete_deck = view.complete_known_deck_ids
    if known_deck is None and complete_deck is None:
        return 0

    def contains(card_id: int) -> bool:
        if known_deck is not None:
            return known_deck.get(int(card_id), 0) > 0
        return int(card_id) in complete_deck

    return sum(any(contains(card_id) for card_id in group) for group in groups)


def _supporter_can_enable_active_loaded_primary_ko(view, memory) -> bool:
    active = view.opponent_active
    profile = None if memory is None else memory.opponent_profile
    loaded_serial = sole_energy_loaded_primary_serial(view, profile)
    if (
        active is None
        or active.serial is None
        or loaded_serial != int(active.serial)
    ):
        return False

    for option in view.options:
        if option.type != int(OptionType.PLAY):
            continue
        groups = _SUPPORTER_SEARCH_GROUPS.get(option.card_id)
        if groups is None:
            continue
        searched = _known_search_group_count(view, memory, groups)
        projected_hand = max(0, int(view.hand_size) - 1) + searched
        if can_hand_power_ko(view, hand_size=projected_hand):
            return True
    return False


def choose_boss_proposal(view, memory=None) -> Proposal | None:
    if not _is_main_selection(view) or _hand_power_option(view) is None:
        return None
    boss = min(
        (
            option
            for option in view.options
            if option.type == int(OptionType.PLAY)
            and option.card_id == int(CardId.BOSSES_ORDERS)
            and option.card_serial is not None
        ),
        key=lambda option: (int(option.card_serial), option.position),
        default=None,
    )
    if boss is None:
        return None

    active_ko_available = can_hand_power_ko(view)
    active_prizes = _public_prize_value(view, view.opponent_active)
    saves_two_prize_softening = (
        active_prizes == 2
        and _current_attack_leaves_small_followup(view, maximum_hp=60)
    )
    if active_ko_available and _wins_by_knocking_out(view, view.opponent_active):
        return None

    def public_threat(pokemon) -> int:
        meta = view.catalog.card(pokemon.id)
        attached_count = len(pokemon.energy_cards)
        provided_count = len(pokemon.energies)
        if meta is None:
            return attached_count * 100 + provided_count * 10
        public_text = " ".join(
            (*meta.skill_texts, *(
                view.catalog.attack_text.get(int(attack_id), "")
                for attack_id in meta.attacks
            ))
        )
        normalized = _normalized_text(public_text)
        text_threat = sum(
            marker in normalized
            for marker in (
                "knock out",
                "damage counter",
                "benched pokemon",
                "discard",
            )
        )
        return (
            attached_count * 100
            + provided_count * 10
            + len(meta.attacks) * 5
            + len(meta.skill_texts) * 3
            + text_threat
        )

    profile = None if memory is None else memory.opponent_profile
    primary_instances = opponent_primary_line_instances(view, profile)
    sole_primary_serial = (
        int(primary_instances[0].serial)
        if len(primary_instances) == 1 and primary_instances[0].serial is not None
        else None
    )
    loaded_primary_serial = sole_energy_loaded_primary_serial(
        view,
        profile,
    )
    supporter_can_ko_loaded_active = (
        _supporter_can_enable_active_loaded_primary_ko(view, memory)
    )
    candidates: list[BossTarget] = []
    from rules.continuity import has_attack_line_deficit, needs_continuity_setup

    normal_boss_allowed = not (
        needs_continuity_setup(view) or has_attack_line_deficit(view)
    )
    candy_absent = rare_candy_absence_inferred(view, memory, profile)
    stage_one_ids = frozenset(
        int(line[-2])
        for line in (() if profile is None else profile.primary_lines)
        if len(line) >= 3
    )
    visible_stage_one_count = sum(
        int(pokemon.id) in stage_one_ids for pokemon in view.opponent_field
    )
    for pokemon in view.opponent_bench:
        if pokemon.serial is None or _is_hand_power_effect_immune(view, pokemon):
            continue
        needed = ceil(pokemon.hp / 20)
        if view.hand_size - 1 < needed:
            continue
        prizes = _public_prize_value(view, pokemon)
        if prizes >= view.own_prize_count:
            reason = BossReason.FINAL_WIN
        elif loaded_primary_serial == int(pokemon.serial):
            reason = BossReason.SOLE_PRIMARY_LINE
        elif (
            sole_primary_serial == int(pokemon.serial)
            and not remaining_public_attacker_can_ko(
                view,
                excluded_serial=int(pokemon.serial),
            )
        ):
            reason = BossReason.SOLE_PRIMARY_LINE
        elif (
            candy_absent
            and visible_stage_one_count == 1
            and int(pokemon.id) in stage_one_ids
        ):
            reason = BossReason.LAST_STAGE_ONE
        else:
            reason = BossReason.PRIZE_ACCELERATION
        if (
            saves_two_prize_softening
            and prizes == 1
            and reason in (
                BossReason.PRIZE_ACCELERATION,
                BossReason.LAST_STAGE_ONE,
            )
        ):
            continue
        if reason in (
            BossReason.PRIZE_ACCELERATION,
            BossReason.LAST_STAGE_ONE,
        ) and not normal_boss_allowed:
            continue
        candidates.append(BossTarget(
            pokemon,
            reason,
            prizes,
            needed,
            int(pokemon.id) == int(CardId.FEZANDIPITI_EX),
        ))
    if supporter_can_ko_loaded_active:
        candidates = [
            candidate
            for candidate in candidates
            if candidate.reason == BossReason.FINAL_WIN
        ]
    if active_ko_available:
        candidates = [
            candidate for candidate in candidates
            if candidate.reason >= BossReason.SOLE_PRIMARY_LINE
            or candidate.prizes > active_prizes
        ]
    if not candidates:
        return None

    selected = min(
        candidates,
        key=lambda candidate: (
            -int(candidate.reason),
            -candidate.prizes,
            candidate.required_hand,
            -public_threat(candidate.pokemon),
            0 if candidate.is_fezandipiti else 1,
            int(candidate.pokemon.serial),
            int(candidate.pokemon.id),
        ),
    )
    pokemon = selected.pokemon
    prizes = selected.prizes
    needed = selected.required_hand
    threat = public_threat(pokemon)
    priority = {
        BossReason.FINAL_WIN: 1200,
        BossReason.SOLE_PRIMARY_LINE: 1120,
        BossReason.LAST_STAGE_ONE: 970,
        BossReason.PRIZE_ACCELERATION: 970,
    }[selected.reason]
    intent = PendingIntent.from_view(
        view,
        kind="BOSS_KO_TARGET",
        card_ids=(pokemon.id,),
        target_serial=pokemon.serial,
        max_cards=1,
        metadata=(
            ("base_prizes", prizes),
            ("required_hand_after_boss", needed),
            ("public_threat", threat),
            ("boss_reason", selected.reason.name),
            ("reason", "Boss後もHand Powerのダメカン効果でKOできる公開対象"),
        ),
        effect_card_id=CardId.BOSSES_ORDERS,
        effect_serial=boss.card_serial,
        remaining_contexts=(SelectContext.SWITCH,),
    )
    return Proposal(
        (boss.position,),
        priority,
        (
            f"バトル場の{active_prizes}枚取りより、Boss使用後もKOできる"
            f"{prizes}枚取りを優先する"
            if active_ko_available
            else "Boss使用後の手札でもHand Powerのダメカン効果で公開対象をKOできる"
        ),
        ("FLOW-ATTACK-BOSS", "PLAYBOOK-BOSS"),
        intent,
    )


def _current_attack_leaves_small_followup(view, *, maximum_hp: int) -> bool:
    target = view.opponent_active
    if target is None or _is_hand_power_effect_immune(view, target):
        return False
    for option in view.options:
        if option.type != int(OptionType.ATTACK) or option.attack_id is None:
            continue
        if int(option.attack_id) == int(AttackId.HAND_POWER):
            damage = int(view.hand_size) * 20
        else:
            attack = view.catalog.attack_meta.get(int(option.attack_id))
            damage = 0 if attack is None else int(attack.damage)
        remaining = int(target.hp) - damage
        if 0 < remaining <= int(maximum_hp):
            return True
    return False


def _pokemon_has_ready_public_attack(view, pokemon) -> bool:
    card = view.catalog.card(pokemon.id)
    return bool(
        card is not None
        and any(
            view.public_attack_is_ready(pokemon, attack_id)
            for attack_id in card.attacks
        )
    )


def _boss_stall_proposal(view) -> Proposal | None:
    boss = _boss_play_option(view)
    active = view.active
    opponent_active = view.opponent_active
    if (
        boss is None
        or active is None
        or int(active.id) != int(CardId.FEZANDIPITI_EX)
        or len(view.field) != 1
        or opponent_active is None
        or opponent_active.serial is None
        or any(
            option.type == int(OptionType.PLAY)
            and option.card_id != int(CardId.BOSSES_ORDERS)
            for option in view.options
        )
    ):
        return None
    active_lethal = any(
        projection.attacker_serial == opponent_active.serial
        and int(projection.active_damage) >= int(active.hp)
        for projection in view.public_attack_projections()
    )
    if not active_lethal:
        return None
    target = min(
        (
            pokemon
            for pokemon in view.opponent_bench
            if pokemon.serial is not None
            and not _pokemon_has_ready_public_attack(view, pokemon)
        ),
        key=lambda pokemon: (int(pokemon.hp), int(pokemon.serial)),
        default=None,
    )
    if target is None:
        return None
    intent = PendingIntent.from_view(
        view,
        kind="BOSS_STALL_TARGET",
        card_ids=(int(target.id),),
        target_serial=int(target.serial),
        max_cards=1,
        metadata=(("reason", "単騎盤面の公開確定リーサルを攻撃不能なベンチ縛りで遅らせる"),),
        effect_card_id=CardId.BOSSES_ORDERS,
        effect_serial=boss.card_serial,
        remaining_contexts=(SelectContext.SWITCH,),
    )
    return Proposal(
        (boss.position,),
        1000,
        "展開不能なキチキギスex単騎への公開確定リーサルをBossのベンチ縛りで遅らせる",
        ("FLOW-ATTACK-BOSS", "PLAYBOOK-BOSS"),
        intent,
        alternative="narrow-public-lethal-stall",
    )


def _boss_reason(proposal: Proposal | None) -> str | None:
    if proposal is None or proposal.next_intent is None:
        return None
    return dict(proposal.next_intent.metadata).get("boss_reason")


def _boss_should_wait_for_supporter_free_information(view, memory) -> bool:
    """進化・特性ドローを先に行い、その結果を見てBossを再評価する。"""
    from rules.draw_engine import propose_draw
    from rules.evolution import propose_evolution

    for proposal in (propose_draw(view, memory), propose_evolution(view, memory)):
        if proposal is None or not proposal.option_indices:
            continue
        position = int(proposal.option_indices[0])
        option = next(
            (candidate for candidate in view.options if candidate.position == position),
            None,
        )
        if option is None:
            continue
        if option.type in (int(OptionType.ABILITY), int(OptionType.EVOLVE)):
            return True
        if (
            option.type == int(OptionType.PLAY)
            and option.card_id == int(CardId.RARE_CANDY)
        ):
            return True
    return False


@covers(
    "FLOW-ATTACK-ENERGY",
    "FLOW-ATTACK-HAND",
    "FLOW-ATTACK-BOSS",
    "FLOW-ATTACK-HAMMER",
    "PLAYBOOK-HAND-THRESHOLD",
    "PLAYBOOK-STOP-WHEN-KO",
    "PLAYBOOK-PROMOTE-COMPLETE",
    "PLAYBOOK-BASIC-PSYCHIC",
    "PLAYBOOK-TELEPATH-LIMIT",
    "PLAYBOOK-SEARCH-INTENT",
    "PLAYBOOK-ENHANCED-HAMMER",
    "PLAYBOOK-BOSS",
    "PLAYBOOK-BOARD-MINIMUM",
    "PLAYBOOK-AIR-BALLOON",
    "PLAYBOOK-PRESERVE-ABRA",
    "PLAYBOOK-TURN-TWO-NON-KO",
    "PLAYBOOK-TELEPORT-ATTACK",
)
def propose_attack(view, memory) -> Proposal | None:
    hand_power = _hand_power_option(view)
    target = view.opponent_active
    needed = view.required_hand_for_active_ko
    stall_boss = _boss_stall_proposal(view)
    if stall_boss is not None:
        return stall_boss
    boss = choose_boss_proposal(view, memory)
    boss_reason = _boss_reason(boss)
    boss_is_final = boss_reason == BossReason.FINAL_WIN.name
    boss_is_sole_primary = boss_reason == BossReason.SOLE_PRIMARY_LINE.name
    boss_waits = (
        boss is not None
        and not boss_is_final
        and _boss_should_wait_for_supporter_free_information(view, memory)
    )
    if can_hand_power_ko(view):
        if boss_is_final:
            return boss
        if boss_is_sole_primary:
            return None if boss_waits else boss
        hammer = choose_hammer_proposal(view, memory)
        if hammer is not None:
            return hammer
        if boss_waits:
            return None
        if boss is not None:
            return boss
        priority = _attack_priority(view, target)
        return Proposal(
            (hand_power.position,),
            priority,
            f"Hand Powerのダメカン効果は手札{view.hand_size}枚で"
            f"残りHPからの必要{needed}枚を満たす",
            (
                "FLOW-ATTACK-HAND",
                "PLAYBOOK-HAND-THRESHOLD",
                "PLAYBOOK-STOP-WHEN-KO",
                "PLAYBOOK-BOARD-MINIMUM",
            ),
        )

    fan_rotom = _fan_rotom_fast_ko_proposal(view)
    # 70ダメージで今の相手を倒せる時だけは、同じ手貼り権を将来の
    # フーディンへ回して確定KOを失わない。提案優先度は低いままなので、
    # 手貼り権を使わない盤面展開は従来どおり先に行える。
    attach = None if fan_rotom is not None else _psychic_attach_proposal(view, memory)
    retreat_attach = (
        None
        if fan_rotom is not None
        else _turn_three_retreat_energy_attach(view, memory)
    )
    retreat = _retreat_to_powered_alakazam(view)
    preserve_abra_retreat = _retreat_to_preserve_only_active_abra(view)
    survival_retreat = _survival_retreat_proposal(view)
    hammer = choose_hammer_proposal(view, memory)
    non_ko_hand_power = _non_ko_hand_power_proposal(view)
    kadabra_attack = _kadabra_attack_proposal(view)
    teleport = _teleport_attack_proposal(view)
    return max(
        (
            proposal
            for proposal in (
                attach,
                retreat_attach,
                retreat,
                preserve_abra_retreat,
                survival_retreat,
                hammer,
                None if boss_waits else boss,
                fan_rotom,
                non_ko_hand_power,
                kadabra_attack,
                teleport,
            )
            if proposal is not None
        ),
        key=lambda proposal: proposal.priority,
        default=None,
    )
