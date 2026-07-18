"""公開盤面上の攻撃系統・ドロー系統を数える純粋な共通ヘルパー。"""

from __future__ import annotations

from cards import CardId
from model import SelectContext, SelectType


ATTACK_LINE_IDS = frozenset({
    int(CardId.ABRA),
    int(CardId.KADABRA),
    int(CardId.ALAKAZAM),
})
DRAW_LINE_IDS = frozenset({
    int(CardId.DUNSPARCE),
    int(CardId.DUDUNSPARCE),
})
MINIMUM_ATTACK_LINES = 3
MINIMUM_RESERVE_LINES = 2
MINIMUM_DRAW_LINES = 2
# スピンロトムでは3枚目も手札へ確保するが、最初の場に必須とするのは
# 2系統まで。3体目まで無条件に置くと、退避役や後続ケーシィの枠を塞ぎ、
# 同一乱数の対照評価で先攻・後攻とも3ターン目攻撃率が低下した。
OPENING_DRAW_LINES = 2
OPENING_SURVIVAL_PIVOT_ORDER = (
    int(CardId.SHAYMIN),
    int(CardId.GENESECT),
    int(CardId.PSYDUCK),
    int(CardId.FAN_ROTOM),
    int(CardId.FEZANDIPITI_EX),
)

# 初回攻撃を始める前だけは、将来盤面の準備より「完成済みフーディンを
# 今バトル場へ出す」手順を先に処理する。初回KO後は continuity.py の
# 連続KO用優先度へ戻し、後続2系統とドロー系統の準備を優先できる。
OPENING_ATTACKER_COMPLETION_PRIORITY = 1130
OPENING_PIVOT_BALLOON_PRIORITY = 1120
OPENING_PIVOT_SEARCH_PRIORITY = 1115
OPENING_PIVOT_ATTACH_PRIORITY = 1110
OPENING_PIVOT_RETREAT_PRIORITY = 1105
TURN_THREE_RESCUE_EVOLUTION_PRIORITY = 945
TURN_THREE_RESCUE_PREPARATION_PRIORITY = 905


def attack_line_count(view) -> int:
    """場にあるケーシィ系統を、進化段階を問わず独立した系統として数える。"""
    return sum(int(pokemon.id) in ATTACK_LINE_IDS for pokemon in view.field)


def powered_alakazam_exists(view) -> bool:
    """場に現在攻撃できる超エネルギー付きフーディンがいるか。"""
    return any(
        int(pokemon.id) == int(CardId.ALAKAZAM)
        and view.has_psychic_energy(pokemon)
        for pokemon in view.field
    )


def has_taken_prize(view) -> bool:
    """自分がこの対戦で少なくとも1枚サイドを取ったか。"""
    return int(view.own_prize_count) < 6


def is_turn_three_rescue_phase(view, *, immediate_ko: bool) -> bool:
    """初回KO前の2～3ターン目で、攻撃完成を救済すべきMAINか。"""

    return (
        view.is_own_turn
        and int(view.own_turn_number) in (2, 3)
        and not has_taken_prize(view)
        and not bool(immediate_ko)
        and int(view.select.get("type", -1)) == int(SelectType.MAIN)
        and int(view.select.get("context", -1)) == int(SelectContext.MAIN)
    )


def is_opening_attack_phase(view) -> bool:
    """初回攻撃を2～3ターン目に成立させるための初動フェーズか。"""
    return not has_taken_prize(view) and int(view.own_turn_number) <= 3


def is_opening_setup_turn(view) -> bool:
    """大量ドロー盤面を作る最初の自分の番か。"""
    return (
        is_opening_attack_phase(view)
        and int(view.own_turn_number) == 1
        and not any(
            int(pokemon.id) == int(CardId.ALAKAZAM)
            for pokemon in view.field
        )
    )


def opening_abra_survival_pivot(view):
    """相手の公開攻撃脅威から唯一のケーシィを退避できるベンチを返す。"""

    active = view.active
    if (
        not is_opening_setup_turn(view)
        or active is None
        or int(active.id) != int(CardId.ABRA)
        or attack_line_count(view) != 1
    ):
        return None
    opponent_line_is_powered = any(
        int(pokemon.id) in ATTACK_LINE_IDS
        and view.has_psychic_energy(pokemon)
        for pokemon in view.opponent_field
    )
    opponent_active = view.opponent_active
    opponent_fan_rotom_is_ready = (
        opponent_active is not None
        and int(opponent_active.id) == int(CardId.FAN_ROTOM)
        and view.has_psychic_energy(opponent_active)
        and bool(view.current.get("stadium") or ())
    )
    if not opponent_line_is_powered and not opponent_fan_rotom_is_ready:
        return None
    rank = {
        card_id: index
        for index, card_id in enumerate(OPENING_SURVIVAL_PIVOT_ORDER)
    }
    return min(
        (
            pokemon
            for pokemon in view.bench
            if int(pokemon.id) in rank
        ),
        key=lambda pokemon: (
            rank[int(pokemon.id)],
            10**18 if pokemon.serial is None else int(pokemon.serial),
            int(pokemon.index or 0),
        ),
        default=None,
    )


def draw_line_target(view) -> int:
    """初動・継続とも場の必須ノコッチ系統は2体を目標にする。"""
    return OPENING_DRAW_LINES if is_opening_setup_turn(view) else MINIMUM_DRAW_LINES


def available_bench_slots(view) -> int:
    """現在の公開盤面で使用できるベンチ枠数を返す。"""
    bench_max = int(view.own.get("benchMax", 5))
    return max(0, bench_max - len(view.bench))


def needs_attack_line_setup(view) -> bool:
    """完成済みフーディンを守りながら、次々番までの進化前を補う必要があるか。"""
    return (
        powered_alakazam_exists(view)
        and
        attack_line_count(view) < MINIMUM_ATTACK_LINES
        and available_bench_slots(view) > 0
    )


def reserve_abra_needs_kadabra(view) -> bool:
    """次番用の古いケーシィを、今ターン中にユンゲラーへ進める必要があるか。"""
    if not powered_alakazam_exists(view):
        return False
    old_abras = tuple(
        pokemon
        for pokemon in view.field
        if int(pokemon.id) == int(CardId.ABRA)
        and not pokemon.appear_this_turn
    )
    if not old_abras:
        return False
    # 3本目のケーシィを新しく置くより、今すぐ進化できる古いケーシィを
    # 先にユンゲラーへ進める。無エネでも2枚ドローを得られ、次の番は
    # フーディンへの通常進化とエネルギー付与を同じ番に完了できる。
    # アメがあっても、現在の攻撃役が間に合っている局面では
    # ユンゲラーの2枚ドローを経由してアメを温存する価値がある。
    # 「今ターンの攻撃にアメが必要か」は呼び出し側の優先度で判定する。
    if int(CardId.KADABRA) in view.hand_ids:
        return False
    mature_reserve_exists = any(
        int(pokemon.id) in (int(CardId.KADABRA), int(CardId.ALAKAZAM))
        and not pokemon.appear_this_turn
        and not (
            int(pokemon.id) == int(CardId.ALAKAZAM)
            and view.has_psychic_energy(pokemon)
        )
        for pokemon in view.field
    )
    return not mature_reserve_exists


def can_spend_bench_slots(
    view,
    slots: int = 1,
    *,
    preserve_draw_line: bool = False,
) -> bool:
    """技術ポケモン配置後も、攻撃3系統と必要なノコッチ枠を残せるか。"""
    remaining = max(0, available_bench_slots(view) - max(0, int(slots)))
    draw_slot = int(
        preserve_draw_line
        and draw_line_count(view) == 0
    )
    if remaining < draw_slot:
        return False
    attack_slots = max(0, remaining - draw_slot)
    required_attack_lines = (
        MINIMUM_RESERVE_LINES
        if is_opening_setup_turn(view)
        else MINIMUM_ATTACK_LINES
    )
    return attack_line_count(view) + attack_slots >= required_attack_lines


def draw_line_count(view) -> int:
    """場にある使用待ち・次番のノコッチ系統を数える。"""
    return sum(int(pokemon.id) in DRAW_LINE_IDS for pokemon in view.field)
