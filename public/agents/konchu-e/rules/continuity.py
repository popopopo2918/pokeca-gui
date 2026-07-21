"""KO打点を保ったまま、次々ターンまでの攻撃役を準備する判定。"""

from __future__ import annotations

from dataclasses import dataclass

from cards import CardId
from rules.board_plan import (
    ATTACK_LINE_IDS,
    MINIMUM_ATTACK_LINES,
    MINIMUM_DRAW_LINES,
    MINIMUM_RESERVE_LINES,
    attack_line_count,
    draw_line_count,
    full_board_plan,
    has_taken_prize,
    needs_attack_line_setup,
)
from rules.attack import can_hand_power_ko


CONTINUITY_RECOVERY_PRIORITY = 1020
CONTINUITY_BENCH_PRIORITY = 1010
CONTINUITY_EVOLUTION_PRIORITY = 1040
CONTINUITY_ENERGY_PRIORITY = 1055
CONTINUITY_SEARCH_PRIORITY = 1050
CONTINUITY_SUPPORT_SEARCH_PRIORITY = 1060
CONTINUITY_DRAW_RESERVE_PRIORITY = 1025
CONTINUITY_RECYCLE_PRIORITY = 1080
CONTINUITY_DIRECT_RECOVERY_PRIORITY = 1070
CONTINUITY_GUARANTEED_RECOVERY_PRIORITY = 1085
CONTINUITY_BULK_RECYCLE_PRIORITY = 1090
CONTINUITY_MATURITY_ITEM_PRIORITY = 1078
CONTINUITY_MATURITY_SEARCH_PRIORITY = 1075
CONTINUITY_POFFIN_PRIORITY = 1045
CONTINUITY_POKE_PAD_PRIORITY = 1035
CONTINUITY_DRAW_SEARCH_PRIORITY = 1015
CONTINUITY_DRAW_BENCH_PRIORITY = 1005
CONTINUITY_LINE_DRAW_PRIORITY = 1008
CONTINUITY_SPACE_PRIORITY = 1048
CONTINUITY_PROTECTION_PRIORITY = 1090
# 現在の超付きユンゲラーを攻撃役へ完成させながら、古い後続ケーシィも
# 同じ検索でユンゲラー化できる経路。回収だけの行動より先に実行する。
CURRENT_AND_RESERVE_EVOLUTION_SEARCH_PRIORITY = 1095
CURRENT_AND_RESERVE_DIRECT_RECOVERY_PRIORITY = 1096
ATTACK_LINE_POFFIN_PRIORITY = 945
ATTACK_LINE_BENCH_PRIORITY = 940
ATTACK_LINE_POKE_PAD_PRIORITY = 905
ATTACK_LINE_SUPPORT_PRIORITY = 905
# ポケパッドは手札に残せる柔軟な検索札なので、キチキギスex・リッチ・
# ノココッチの確定ドローを先に使い、自然に引けなかった進化札だけを取る。
ATTACK_LINE_MATURITY_PRIORITY = 909
ATTACK_LINE_ENERGY_PRIORITY = 955


def reserve_attack_line_count(view) -> int:
    """現在の攻撃役を除き、ベンチに残るフーディン系統を数える。"""
    return sum(int(pokemon.id) in ATTACK_LINE_IDS for pokemon in view.bench)


def has_attack_line_deficit(view) -> bool:
    """現在のバトル場とは独立した、次番用のケーシィ系統がないか。"""
    return reserve_attack_line_count(view) == 0


def immediate_ko_ends_game(view) -> bool:
    """公開情報だけで、今のKOがサイドまたは盤面切れ勝利になるか判定する。"""
    if not can_hand_power_ko(view):
        return False
    if len(view.opponent_field) <= 1:
        return True
    target = view.opponent_active
    if target is None:
        return False
    meta = view.catalog.card(target.id)
    prize_value = 1 if meta is None else int(meta.prize_value)
    return view.own_prize_count <= prize_value


def nonfinal_immediate_ko(view) -> bool:
    """今すぐKOでき、かつそのKOだけでは試合が終わらないか。"""
    return can_hand_power_ko(view) and not immediate_ko_ends_game(view)


def needs_continuity_setup(view) -> bool:
    """非最終KO前に、独立した後続系統をもう1本以上作る必要があるか。"""
    return nonfinal_immediate_ko(view) and needs_attack_line_setup(view)


def needs_full_board_setup(view) -> bool:
    """非最終KOを保ったまま、6枠完成へ進められる余地があるか。"""
    plan = full_board_plan(view)
    return (
        nonfinal_immediate_ko(view)
        and not plan.complete
        and bool(plan.target_basic_ids)
    )


def continuity_space_release_needed(view) -> bool:
    """満員盤面からノココッチを戻し、3本目の攻撃系統用の枠を空けるか。"""
    bench_max = int(view.own.get("benchMax", 5))
    return (
        nonfinal_immediate_ko(view)
        and len(view.bench) >= bench_max
        and attack_line_count(view) < MINIMUM_ATTACK_LINES
    )


def needs_draw_reserve_setup(view) -> bool:
    """攻撃系統3体を確保した上で、妨害後用ノココッチが不足しているか。"""
    return (
        nonfinal_immediate_ko(view)
        and has_taken_prize(view)
        and attack_line_count(view) >= MINIMUM_ATTACK_LINES
        and (
            draw_line_count(view) < MINIMUM_DRAW_LINES
            or not any(
                int(pokemon.id) == int(CardId.DUDUNSPARCE)
                for pokemon in view.field
            )
        )
    )


def spend_preserves_immediate_ko(view, cards_spent: int = 1) -> bool:
    """指定枚数を手札から使っても、現在のハンドパワーKO打点を維持するか。"""
    if not can_hand_power_ko(view):
        return True
    return can_hand_power_ko(
        view,
        hand_size=max(0, view.hand_size - int(cards_spent)),
    )


def search_preserves_immediate_ko(view, cards_added: int) -> bool:
    """検索札1枚を使い、公開情報上確実に加わる枚数を反映してKO打点を判定する。"""
    searchable_cards = min(
        max(0, int(cards_added)),
        max(0, int(view.own.get("deckCount", 0))),
    )
    resulting_hand = max(0, view.hand_size - 1 + searchable_cards)
    return can_hand_power_ko(view, hand_size=resulting_hand)


def evolution_draw_preserves_immediate_ko(view, draw_count: int) -> bool:
    """進化札を1枚使い、公開山札から所定枚数引いた後もKO打点を保つか。"""
    available_draws = min(
        max(0, int(draw_count)),
        max(0, int(view.own.get("deckCount", 0))),
    )
    resulting_hand = max(0, view.hand_size - 1 + available_draws)
    return can_hand_power_ko(view, hand_size=resulting_hand)


@dataclass(frozen=True)
class ImmediatePlanPreservation:
    attack: bool
    ko: bool
    next_attacker: bool
    hand_threshold: bool

    @property
    def all(self) -> bool:
        return self.attack and self.ko and self.next_attacker and self.hand_threshold


def optional_resource_spend_allowed(
    view,
    *,
    hand_spent: int = 0,
    uses_supporter: bool = False,
    uses_attachment: bool = False,
) -> bool:
    """任意資源の支出が、攻撃・KO・次番継続を壊さないか判定する。"""
    if not spend_preserves_immediate_ko(view, hand_spent):
        return False
    if uses_supporter and not can_hand_power_ko(view, hand_size=view.hand_size - hand_spent):
        return False
    if uses_attachment and needs_attack_line_setup(view) and not can_hand_power_ko(view):
        return False
    return True


def rich_retreat_enables_priority_goal(view, memory, *, attach_from_hand: bool) -> bool:
    """リッチ退避を許すのは、同番の攻撃/KOまたは連続KO維持に直結する場合だけ。"""
    target = view.opponent_active
    immediate_ko = target is not None and can_hand_power_ko(view)
    if immediate_ko:
        return True
    powered_bench_alakazam = any(
        int(pokemon.id) == int(CardId.ALAKAZAM)
        and view.has_psychic_energy(pokemon)
        for pokemon in view.bench
    )
    if powered_bench_alakazam:
        projected_hand = int(view.hand_size)
        if attach_from_hand:
            projected_hand = max(0, projected_hand - 1) + min(
                4,
                max(0, int(view.own.get("deckCount", 0))),
            )
        return (
            target is not None
            and projected_hand >= int(view.required_hand_for_active_ko)
        )
    if not needs_continuity_setup(view):
        return False
    return True
