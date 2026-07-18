from __future__ import annotations

from math import ceil
import re

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


MIST_ENERGY_ID = 11
ROCK_FIGHTING_ENERGY_ID = 20
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
    board_ready = (
        view.is_own_turn
        and active is not None
        and int(active.id) == int(CardId.ALAKAZAM)
        and (
            view.has_psychic_energy(active)
            or assume_active_psychic
        )
        and not bool(view.own.get("asleep"))
        and not bool(view.own.get("paralyzed"))
        and not bool(view.own.get("confused"))
    )
    attack_ready = (
        _hand_power_option(view) is not None
        if require_legal_option
        else board_ready
    )
    return (
        attack_ready
        and target is not None
        and needed is not None
        and available_hand >= needed
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


def _opening_powered_candy_route_can_evolve_now(view) -> bool:
    return (
        is_opening_attack_phase(view)
        and not any(
            int(pokemon.id) == int(CardId.ALAKAZAM)
            and view.has_psychic_energy(pokemon)
            for pokemon in view.field
        )
        and int(CardId.RARE_CANDY) in view.hand_ids
        and int(CardId.ALAKAZAM) in view.hand_ids
        and any(
            option.type == int(OptionType.PLAY)
            and option.card_id == int(CardId.RARE_CANDY)
            for option in view.options
        )
        and any(
            int(pokemon.id) == int(CardId.ABRA)
            and pokemon.area == int(Area.BENCH)
            and view.has_psychic_energy(pokemon)
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
    defer_basic_until_kadabra_draw = (
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
                defer_basic_until_kadabra_draw
                and option.card_id == int(CardId.BASIC_PSYCHIC)
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
        )
    return Proposal(
        (option.position,),
        priority,
        reason,
        tuple(rule_ids),
        next_intent,
    )


def _turn_three_retreat_energy_attach(view) -> Proposal | None:
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

    options = tuple(
        candidate
        for candidate in view.options
        if candidate.type == int(OptionType.ATTACH)
        and candidate.card_id in (
            int(CardId.BASIC_PSYCHIC),
            int(CardId.TELEPATH_PSYCHIC_ENERGY),
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
            0 if candidate.card_id == int(CardId.BASIC_PSYCHIC) else 1,
            candidate.position,
        ),
        default=None,
    )
    if option is None:
        return None
    emergency_telepath = option.card_id == int(CardId.TELEPATH_PSYCHIC_ENERGY)
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
    ):
        return None
    reason = (
        f"{view.own_turn_number}ターン目の攻撃を開始するため、"
        + (
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
        alternative="リッチは逃げコスト用に貼らず、テレパス超も他の退避・ドロー経路を使い切ってから使う",
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
    if only_enriching_would_be_spent:
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


def _immunity_remains_after_discard(view, pokemon, energy_serial: int) -> bool:
    if _has_self_effect_immunity(view, pokemon):
        return True
    if _has_public_field_effect_immunity(view, pokemon):
        return True
    return any(
        energy.serial != energy_serial
        for energy in _blocking_energy_cards(view, pokemon)
    )


def _boss_play_is_legal(view) -> bool:
    return any(
        option.type == int(OptionType.PLAY)
        and option.card_id == int(CardId.BOSSES_ORDERS)
        and option.card_serial is not None
        for option in view.options
    )


def _hammer_unlocks_hand_power_ko(
    view, pokemon, energy, blocks_hand_power: bool
) -> bool:
    if (
        not blocks_hand_power
        or energy.serial is None
        or _hand_power_option(view) is None
        or _immunity_remains_after_discard(view, pokemon, int(energy.serial))
    ):
        return False
    if pokemon.area == int(Area.ACTIVE):
        cards_spent = 1
    elif pokemon.area == int(Area.BENCH) and _boss_play_is_legal(view):
        cards_spent = 2
    else:
        return False
    return view.hand_size - cards_spent >= ceil(pokemon.hp / 20)


@covers("FLOW-ATTACK-HAMMER", "PLAYBOOK-ENHANCED-HAMMER")
def choose_hammer_proposal(view) -> Proposal | None:
    hammer = _hammer_play_option(view)
    if hammer is None:
        return None
    candidates = _special_energy_candidates(view)
    if not candidates:
        return None
    def key(candidate):
        pokemon, energy, blocks_hand_power = candidate
        unlocks_ko = _hammer_unlocks_hand_power_ko(
            view, pokemon, energy, blocks_hand_power
        )
        provided_count = _provided_energy_count(view, energy.id)
        active_rank = 0 if pokemon.area == int(Area.ACTIVE) else 1
        pokemon_serial = 10**9 if pokemon.serial is None else int(pokemon.serial)
        energy_serial = 10**9 if energy.serial is None else int(energy.serial)
        return (
            0 if unlocks_ko else 1,
            0 if blocks_hand_power else 1,
            0 if provided_count >= 2 else 1,
            -provided_count,
            active_rank,
            pokemon_serial,
            energy_serial,
            int(energy.id),
        )

    pokemon, energy, blocks_hand_power = min(candidates, key=key)
    unlocks_ko = _hammer_unlocks_hand_power_ko(
        view, pokemon, energy, blocks_hand_power
    )
    generic_priority = (
        840
        if is_opening_attack_phase(view) and not powered_alakazam_exists(view)
        else 870
    )
    intent = PendingIntent.from_view(
        view,
        kind="DISCARD_SPECIAL_ENERGY",
        card_ids=(energy.id,),
        target_serial=pokemon.serial,
        max_cards=1,
        metadata=(
            ("energy_serial", int(energy.serial)),
            ("reason", "Hand Powerのダメカン効果への免疫を外す"
             if blocks_hand_power else "公開特殊エネルギーを妨害する"),
        ),
        effect_card_id=CardId.ENHANCED_HAMMER,
        effect_serial=hammer.card_serial,
        remaining_contexts=(SelectContext.DISCARD_ENERGY,),
    )
    return Proposal(
        (hammer.position,),
        980 if unlocks_ko else generic_priority,
        "Hand Powerのダメカン効果を防ぐ特殊エネルギーを先に外す"
        if blocks_hand_power else "相手の公開特殊エネルギーを改造ハンマーで外す",
        ("FLOW-ATTACK-HAMMER", "PLAYBOOK-ENHANCED-HAMMER"),
        intent,
    )


@covers("FLOW-ATTACK-BOSS", "PLAYBOOK-BOSS")
def choose_boss_proposal(view) -> Proposal | None:
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

    candidates = []
    for pokemon in view.opponent_bench:
        if pokemon.serial is None or _is_hand_power_effect_immune(view, pokemon):
            continue
        needed = ceil(pokemon.hp / 20)
        if view.hand_size - 1 < needed:
            continue
        candidates.append((
            pokemon,
            _public_prize_value(view, pokemon),
            needed,
            public_threat(pokemon),
        ))
    if active_ko_available:
        candidates = [
            candidate for candidate in candidates
            if candidate[1] > active_prizes
        ]
    if not candidates:
        return None

    pokemon, prizes, needed, threat = min(
        candidates,
        key=lambda candidate: (
            -candidate[1],
            candidate[2],
            -candidate[3],
            int(candidate[0].serial),
            int(candidate[0].id),
        ),
    )
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
            ("reason", "Boss後もHand Powerのダメカン効果でKOできる公開対象"),
        ),
        effect_card_id=CardId.BOSSES_ORDERS,
        effect_serial=boss.card_serial,
        remaining_contexts=(SelectContext.SWITCH,),
    )
    return Proposal(
        (boss.position,),
        970,
        (
            f"バトル場の{active_prizes}枚取りより、Boss使用後もKOできる"
            f"{prizes}枚取りを優先する"
            if active_ko_available
            else "Boss使用後の手札でもHand Powerのダメカン効果で公開対象をKOできる"
        ),
        ("FLOW-ATTACK-BOSS", "PLAYBOOK-BOSS"),
        intent,
    )


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
)
def propose_attack(view, memory) -> Proposal | None:
    hand_power = _hand_power_option(view)
    target = view.opponent_active
    needed = view.required_hand_for_active_ko
    boss = choose_boss_proposal(view)
    if can_hand_power_ko(view):
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
        None if fan_rotom is not None else _turn_three_retreat_energy_attach(view)
    )
    retreat = _retreat_to_powered_alakazam(view)
    preserve_abra_retreat = _retreat_to_preserve_only_active_abra(view)
    hammer = choose_hammer_proposal(view)
    return max(
        (
            proposal
            for proposal in (
                attach,
                retreat_attach,
                retreat,
                preserve_abra_retreat,
                hammer,
                boss,
                fan_rotom,
            )
            if proposal is not None
        ),
        key=lambda proposal: proposal.priority,
        default=None,
    )
