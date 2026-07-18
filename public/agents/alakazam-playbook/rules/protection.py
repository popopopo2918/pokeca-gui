from __future__ import annotations

from cards import CardId
from model import OptionType, SelectContext, SelectType
from proposals import Proposal, covers
from rules.attack import can_hand_power_ko
from rules.board_plan import can_spend_bench_slots
from rules.continuity import (
    CONTINUITY_PROTECTION_PRIORITY,
    nonfinal_immediate_ko,
)


def _is_main_selection(view) -> bool:
    return (
        int(view.select.get("type", -1)) == int(SelectType.MAIN)
        and int(view.select.get("context", -1)) == int(SelectContext.MAIN)
    )


def _play_option(view, card_id: int):
    return min(
        (
            option
            for option in view.options
            if option.type == int(OptionType.PLAY)
            and option.card_id == int(card_id)
            and option.card_serial is not None
        ),
        key=lambda option: (int(option.card_serial), option.position),
        default=None,
    )


def _play_proposal(
    view,
    card_id: int,
    priority: int,
    reason: str,
    rule_ids: tuple[str, ...],
) -> Proposal | None:
    option = _play_option(view, card_id)
    if option is None:
        return None
    return Proposal((option.position,), priority, reason, rule_ids)


def _spend_preserves_immediate_ko(view, cards_spent: int) -> bool:
    if not can_hand_power_ko(view):
        return True
    return can_hand_power_ko(
        view,
        hand_size=max(0, view.hand_size - int(cards_spent)),
    )


def _has_ruleless_bench_target(view) -> bool:
    for pokemon in view.bench:
        meta = view.catalog.card(pokemon.id)
        if meta is not None and not (meta.ex or meta.mega_ex or meta.tera):
            return True
    return False


def _battle_cage_is_in_play(view) -> bool:
    return any(
        card is not None
        and int(card.get("id", -1)) == int(CardId.BATTLE_CAGE)
        for card in (view.current.get("stadium") or [])
    )


def _own_public_self_ko_ability_exists(view) -> bool:
    # 固定フーディンリストに自身をきぜつさせる特性はない。
    # 将来リストが変わってもコダックで自分の公開プランを止めないよう保守的に確認する。
    return any(
        type(view)._is_self_ko_text(text)
        for pokemon in view.field
        for text in (
            view.catalog.card(pokemon.id).skill_texts
            if view.catalog.card(pokemon.id) is not None
            else ()
        )
    )


def _genesect_proposal(view, memory) -> Proposal | None:
    if not memory.unfair_stamp_possible or not can_hand_power_ko(view):
        return None

    genesects = sorted(
        (pokemon for pokemon in view.field if pokemon.id == int(CardId.GENESECT)),
        key=lambda pokemon: (
            pokemon.serial is None,
            10**9 if pokemon.serial is None else int(pokemon.serial),
        ),
    )
    genesect = genesects[0] if genesects else None

    if genesect is not None:
        if int(CardId.AIR_BALLOON) in genesect.tool_ids:
            return None
        if len(view.field) < 2 or not _spend_preserves_immediate_ko(view, 1):
            return None
        options = [
            option
            for option in view.options
            if option.type == int(OptionType.ATTACH)
            and option.card_id == int(CardId.AIR_BALLOON)
            and option.card_serial is not None
            and option.target is not None
            and option.target.serial == genesect.serial
        ]
        if not options:
            return None
        option = min(
            options,
            key=lambda candidate: (
                int(candidate.card_serial),
                10**9
                if candidate.target.serial is None
                else int(candidate.target.serial),
                candidate.position,
            ),
        )
        return Proposal(
            (option.position,),
            1015,
            "Hand PowerのKO打点と盤面を保ったままゲノセクトへふうせんを付ける",
            ("FLOW-PROTECT-GENESECT", "PLAYBOOK-GENESECT"),
        )

    play = _play_option(view, CardId.GENESECT)
    if (
        play is None
        or int(CardId.AIR_BALLOON) not in view.hand_ids
        or len(view.field) + 1 < 2
        or not can_spend_bench_slots(view, preserve_draw_line=True)
        or not _spend_preserves_immediate_ko(view, 2)
    ):
        return None
    return Proposal(
        (play.position,),
        1010,
        "Hand Power後のアンフェアスタンプを止めるゲノセクトを展開する",
        ("FLOW-PROTECT-GENESECT", "PLAYBOOK-GENESECT"),
    )


@covers(
    "FLOW-PROTECT-SHAYMIN",
    "FLOW-PROTECT-PSYDUCK",
    "FLOW-PROTECT-GENESECT",
    "PLAYBOOK-BATTLE-CAGE",
    "PLAYBOOK-SHAYMIN-DAMAGE",
    "PLAYBOOK-PSYDUCK",
    "PLAYBOOK-GENESECT",
    "PLAYBOOK-STOP-WHEN-KO",
    "PLAYBOOK-BOARD-MINIMUM",
)
def propose_protection(view, memory) -> Proposal | None:
    if not _is_main_selection(view):
        return None

    proposals: list[Proposal] = []
    genesect = _genesect_proposal(view, memory)
    if genesect is not None:
        proposals.append(genesect)

    if _spend_preserves_immediate_ko(view, 1):
        continuity_protection = nonfinal_immediate_ko(view)
        defensive_priority = (
            CONTINUITY_PROTECTION_PRIORITY if continuity_protection else 930
        )
        continuity_rule_ids = (
            ("PLAYBOOK-BOARD-MINIMUM", "PLAYBOOK-STOP-WHEN-KO")
            if continuity_protection
            else ()
        )
        if (
            view.opponent_has_public_bench_damage_attack
            and _has_ruleless_bench_target(view)
            and can_spend_bench_slots(view, preserve_draw_line=True)
        ):
            shaymin = _play_proposal(
                view,
                CardId.SHAYMIN,
                defensive_priority,
                "公開ワザの通常ダメージからルールなしベンチを守る",
                (
                    "FLOW-PROTECT-SHAYMIN",
                    "PLAYBOOK-SHAYMIN-DAMAGE",
                    *continuity_rule_ids,
                ),
            )
            if shaymin is not None:
                proposals.append(shaymin)

        if (
            view.opponent_has_public_bench_counter_effect
            and bool(view.bench)
            and not _battle_cage_is_in_play(view)
        ):
            battle_cage = _play_proposal(
                view,
                CardId.BATTLE_CAGE,
                defensive_priority,
                "公開ワザ・特性のベンチへのダメカンをバトルコロシアムで防ぐ",
                ("PLAYBOOK-BATTLE-CAGE", *continuity_rule_ids),
            )
            if battle_cage is not None:
                proposals.append(battle_cage)

        if (
            view.opponent_has_public_self_ko_ability
            and not _own_public_self_ko_ability_exists(view)
            and can_spend_bench_slots(view, preserve_draw_line=True)
        ):
            psyduck = _play_proposal(
                view,
                CardId.PSYDUCK,
                925,
                "相手公開盤面の自身をきぜつさせる特性をコダックで止める",
                ("FLOW-PROTECT-PSYDUCK", "PLAYBOOK-PSYDUCK"),
            )
            if psyduck is not None:
                proposals.append(psyduck)

    return max(
        proposals,
        key=lambda proposal: proposal.priority,
        default=None,
    )
