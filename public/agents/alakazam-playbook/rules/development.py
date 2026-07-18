from __future__ import annotations

from cards import CardId
from memory import possible_deck_count
from model import Area, OptionType, SelectContext
from proposals import PendingIntent, Proposal, covers
from rules.board_plan import (
    MINIMUM_ATTACK_LINES,
    MINIMUM_DRAW_LINES,
    MINIMUM_RESERVE_LINES,
    OPENING_PIVOT_BALLOON_PRIORITY,
    OPENING_PIVOT_SEARCH_PRIORITY,
    attack_line_count,
    can_spend_bench_slots,
    draw_line_target,
    draw_line_count,
    has_taken_prize,
    is_opening_attack_phase,
    is_opening_setup_turn,
    needs_attack_line_setup,
    opening_abra_survival_pivot,
    powered_alakazam_exists,
    reserve_abra_needs_kadabra,
)
from rules.continuity import (
    ATTACK_LINE_BENCH_PRIORITY,
    ATTACK_LINE_ENERGY_PRIORITY,
    ATTACK_LINE_MATURITY_PRIORITY,
    ATTACK_LINE_POFFIN_PRIORITY,
    ATTACK_LINE_POKE_PAD_PRIORITY,
    CONTINUITY_BENCH_PRIORITY,
    CONTINUITY_DRAW_BENCH_PRIORITY,
    CONTINUITY_DRAW_SEARCH_PRIORITY,
    CONTINUITY_ENERGY_PRIORITY,
    CONTINUITY_MATURITY_ITEM_PRIORITY,
    CONTINUITY_POFFIN_PRIORITY,
    CONTINUITY_POKE_PAD_PRIORITY,
    immediate_ko_ends_game,
    needs_continuity_setup,
    needs_draw_reserve_setup,
    nonfinal_immediate_ko,
    search_preserves_immediate_ko,
    spend_preserves_immediate_ko,
)
from rules.deck_safety import minimum_deck_reserve, proposal_is_deck_safe
from rules.poke_pad import (
    must_reserve_poke_pad_for_opening_chain,
    must_reserve_poke_pad_for_fresh_kadabra,
    plan_poke_pad_targets,
)
from rules.telepath import build_telepath_bench_intent


PIVOT_IDS = frozenset(
    {
        int(CardId.FAN_ROTOM),
        int(CardId.FEZANDIPITI_EX),
        int(CardId.SHAYMIN),
        int(CardId.GENESECT),
        int(CardId.PSYDUCK),
    }
)
SURVIVAL_BASIC_PRIORITY = (
    CardId.SHAYMIN,
    CardId.GENESECT,
    CardId.PSYDUCK,
    CardId.FEZANDIPITI_EX,
)


def _field_count(view, card_id: int) -> int:
    return sum(int(pokemon.id) == int(card_id) for pokemon in view.field)


def _field_or_hand_count(view, card_id: int) -> int:
    return _field_count(view, card_id) + sum(
        int(hand_id) == int(card_id) for hand_id in view.hand_ids
    )


def _hand_index(option) -> int:
    value = option.raw.get("index")
    return int(value) if value is not None else option.position


def _proposal_for_play(
    option,
    reason: str,
    rule_ids: tuple[str, ...],
    priority: int = 800,
) -> Proposal:
    return Proposal((option.position,), priority, reason, rule_ids)


def _fezandipiti_play(view, memory) -> Proposal | None:
    if (
        not view.is_own_turn
        or memory.fezandipiti_draw_turn != view.own_turn_number
    ):
        return None
    bench_max = int(view.own.get("benchMax", 5))
    bench_space = max(0, bench_max - len(view.bench))
    if bench_space <= 0:
        return None
    if not can_spend_bench_slots(view):
        return None
    option = min(
        (
            candidate
            for candidate in view.options
            if candidate.type == int(OptionType.PLAY)
            and candidate.card_id == int(CardId.FEZANDIPITI_EX)
        ),
        key=lambda candidate: (_hand_index(candidate), candidate.position),
        default=None,
    )
    if option is None:
        return None
    return Proposal(
        (option.position,),
        925,
        "前の相手番のきぜつ後にキチキギスexを出し、さかてにとる3枚へつなげる",
        ("PLAYBOOK-FEZANDIPITI", "PLAYBOOK-FEZANDIPITI-DEPLOY"),
    )


def _direct_basic_play(view) -> Proposal | None:
    bench_space = max(0, int(view.own.get("benchMax", 5)) - len(view.bench))
    if bench_space <= 0:
        return None
    attack_lines = attack_line_count(view)
    draw_lines = draw_line_count(view)
    deck_count = max(0, int(view.own.get("deckCount", 0)))
    emergency_recycle = (
        0 < deck_count <= minimum_deck_reserve(view) + 1
        and draw_lines == 0
        and int(CardId.DUDUNSPARCE) in view.hand_ids
    )
    if emergency_recycle:
        option = min(
            (
                candidate
                for candidate in view.options
                if candidate.type == int(OptionType.PLAY)
                and candidate.card_id == int(CardId.DUNSPARCE)
            ),
            key=lambda candidate: (_hand_index(candidate), candidate.position),
            default=None,
        )
        if option is not None:
            return _proposal_for_play(
                option,
                "山切れを防ぐため次の通常ドローより前にノコッチを置き、"
                "次のノココッチで山札を減らさない循環を準備する",
                (
                    "PLAYBOOK-DECK-SAFETY",
                    "PLAYBOOK-MAX-DRAW",
                    "PLAYBOOK-BOARD-MINIMUM",
                ),
                1200,
            )
    field_fan_rotom = _field_count(view, CardId.FAN_ROTOM)
    opening_setup = is_opening_setup_turn(view)
    opening_attack_target = (
        MINIMUM_RESERVE_LINES if opening_setup else MINIMUM_ATTACK_LINES
    )
    wanted_draw_lines = draw_line_target(view)
    choices = []
    for option in view.options:
        if option.type != int(OptionType.PLAY) or option.card_id is None:
            continue
        card_id = int(option.card_id)
        if card_id == int(CardId.ABRA) and attack_lines < opening_attack_target:
            choices.append((0, _hand_index(option), option.position, option, "ケーシィを直接展開する"))
        elif (
            card_id == int(CardId.FAN_ROTOM)
            and view.is_own_turn
            and view.own_turn_number == 1
            and field_fan_rotom == 0
            and can_spend_bench_slots(view, preserve_draw_line=True)
        ):
            choices.append((1, _hand_index(option), option.position, option, "初ターンにスピンロトムを展開する"))
        elif (
            card_id == int(CardId.DUNSPARCE)
            and draw_lines < wanted_draw_lines
            and can_spend_bench_slots(view)
        ):
            choices.append((2, _hand_index(option), option.position, option, "使用待ちと次番のノコッチ系統を展開する"))
        elif card_id == int(CardId.ABRA) and attack_lines < MINIMUM_ATTACK_LINES:
            choices.append((3, _hand_index(option), option.position, option, "ドロー盤面の後に3体目のケーシィを展開する"))
    if not choices:
        survival_rank = {
            int(card_id): index
            for index, card_id in enumerate(SURVIVAL_BASIC_PRIORITY)
        }
        survival = min(
            (
                option
                for option in view.options
                if len(view.field) <= 1
                and option.type == int(OptionType.PLAY)
                and option.card_id in survival_rank
            ),
            key=lambda option: (
                survival_rank[int(option.card_id)],
                _hand_index(option),
                option.position,
            ),
            default=None,
        )
        if survival is None:
            return None
        return _proposal_for_play(
            survival,
            "単騎きぜつによる即敗北を防ぐため、役割持ちのたねを1体だけ残す",
            ("PLAYBOOK-BOARD-MINIMUM",),
            800,
        )
    continuity_dunsparce = (
        draw_lines == 0
        and nonfinal_immediate_ko(view)
        and spend_preserves_immediate_ko(view)
    )
    if continuity_dunsparce:
        dunsparce_choice = min(
            (
                choice
                for choice in choices
                if int(choice[3].card_id) == int(CardId.DUNSPARCE)
            ),
            key=lambda item: item[:3],
            default=None,
        )
        if dunsparce_choice is not None:
            option = dunsparce_choice[3]
            return _proposal_for_play(
                option,
                "非最終KO前にノコッチを置き、次番の手札妨害後ドローを準備する",
                (
                    "PLAYBOOK-MAX-DRAW",
                    "PLAYBOOK-BOARD-MINIMUM",
                    "PLAYBOOK-STOP-WHEN-KO",
                ),
                CONTINUITY_DRAW_BENCH_PRIORITY,
            )
    _, _, _, option, reason = min(choices, key=lambda item: item[:3])
    rule_ids = {
        int(CardId.ABRA): ("PLAYBOOK-ABRA-LIMIT",),
        int(CardId.FAN_ROTOM): ("FLOW-SETUP-FAN-CALL",),
        int(CardId.DUNSPARCE): ("PLAYBOOK-MAX-DRAW",),
    }[int(option.card_id)]
    continuity_bench = (
        int(option.card_id) == int(CardId.ABRA)
        and needs_continuity_setup(view)
        and spend_preserves_immediate_ko(view)
    )
    proactive_attack_bench = (
        int(option.card_id) == int(CardId.ABRA)
        and needs_attack_line_setup(view)
    )
    if continuity_bench:
        reason = "非最終KO前に2本目の後続ケーシィをベンチへ置く"
        rule_ids = (
            *rule_ids,
            "PLAYBOOK-BOARD-MINIMUM",
            "PLAYBOOK-STOP-WHEN-KO",
        )
    elif proactive_attack_bench:
        reason = "次の相手番より前にケーシィを置き、攻撃系統を合計3体へ近づける"
        rule_ids = (*rule_ids, "PLAYBOOK-BOARD-MINIMUM")
    return _proposal_for_play(
        option,
        reason,
        rule_ids,
        (
            CONTINUITY_BENCH_PRIORITY
            if continuity_bench
            else ATTACK_LINE_BENCH_PRIORITY
            if proactive_attack_bench
            else 800
        ),
    )


def _poffin_attack_line_target(view) -> int:
    if is_opening_setup_turn(view):
        return MINIMUM_ATTACK_LINES
    if (
        has_taken_prize(view)
        or powered_alakazam_exists(view)
        or attack_line_count(view) >= 2
    ):
        return MINIMUM_ATTACK_LINES
    return 2


def _poffin_card_groups(
    view,
    memory,
    max_cards: int,
) -> tuple[tuple[int, ...], ...]:
    attack_line_target = _poffin_attack_line_target(view)
    wanted_draw_lines = draw_line_target(view)
    planned_attack_lines = attack_line_count(view)
    planned_draw_lines = draw_line_count(view)
    fan_rotom_count = _field_or_hand_count(view, CardId.FAN_ROTOM)
    fan_is_useful = view.is_own_turn and view.own_turn_number == 1
    remaining = {
        int(card_id): possible_deck_count(view, memory, card_id)
        for card_id in (CardId.ABRA, CardId.FAN_ROTOM, CardId.DUNSPARCE)
    }
    groups = []
    for _ in range(max_cards):
        priority = []

        def add(card_id: CardId, needed: bool) -> None:
            value = int(card_id)
            if needed and remaining.get(value, 0) > 0 and value not in priority:
                priority.append(value)

        opening_setup_fan_first = (
            is_opening_setup_turn(view)
            and planned_attack_lines >= MINIMUM_RESERVE_LINES
            and fan_is_useful
            and fan_rotom_count == 0
        )
        opening_two_line_draw_first = (
            not has_taken_prize(view)
            and not powered_alakazam_exists(view)
            and planned_attack_lines == 2
            and planned_draw_lines < wanted_draw_lines
        )
        if opening_setup_fan_first:
            add(CardId.FAN_ROTOM, True)
        elif opening_two_line_draw_first:
            add(CardId.DUNSPARCE, True)
        elif planned_attack_lines < attack_line_target:
            add(CardId.ABRA, True)
        elif fan_is_useful and fan_rotom_count == 0:
            add(CardId.FAN_ROTOM, True)
        elif planned_draw_lines < wanted_draw_lines:
            add(CardId.DUNSPARCE, True)

        add(CardId.ABRA, planned_attack_lines < attack_line_target)
        add(CardId.FAN_ROTOM, fan_is_useful and fan_rotom_count < 1)
        add(CardId.DUNSPARCE, planned_draw_lines < wanted_draw_lines)
        if not priority:
            break
        groups.append(tuple(priority))
        selected = priority[0]
        remaining[selected] = max(0, remaining.get(selected, 0) - 1)
        if selected == int(CardId.ABRA):
            planned_attack_lines += 1
        elif selected == int(CardId.DUNSPARCE):
            planned_draw_lines += 1
        elif selected == int(CardId.FAN_ROTOM):
            fan_rotom_count += 1
    return tuple(groups)


def _poffin_play(view, memory) -> Proposal | None:
    bench_space = max(0, int(view.own.get("benchMax", 5)) - len(view.bench))
    if bench_space <= 0:
        return None
    card_groups = _poffin_card_groups(view, memory, min(2, bench_space))
    if not card_groups:
        return None
    contains_abra = any(
        int(CardId.ABRA) in group
        for group in card_groups
    )
    low_deck_recycle_buffer = (
        int(view.own.get("deckCount", 0)) <= minimum_deck_reserve(view) + 1
        and draw_line_count(view) > 0
    )
    if low_deck_recycle_buffer and not contains_abra:
        # 最低残数ちょうどまでポフィンで2本目のノコッチを抜くと、次の
        # 通常ドローで山札が0枚になり、特性自体が提示されず循環できない。
        # 既存の1本をノココッチへ進化できるよう、最後の1枚を残す。
        return None
    poffin_attack_line_target = _poffin_attack_line_target(view)
    if (
        attack_line_count(view) < poffin_attack_line_target
        and not contains_abra
        and view.hand_ids.count(int(CardId.BUDDY_BUDDY_POFFIN)) <= 1
    ):
        return None
    options = [
        option for option in view.options
        if option.type == int(OptionType.PLAY)
        and option.card_id == int(CardId.BUDDY_BUDDY_POFFIN)
        and option.card_serial is not None
    ]
    if not options:
        return None
    option = min(options, key=lambda item: (_hand_index(item), item.position))
    targets = tuple(dict.fromkeys(
        card_id for group in card_groups for card_id in group
    ))
    intent = PendingIntent.from_view(
        view,
        kind="SEARCH_BASICS_FOR_POFFIN",
        card_ids=targets,
        card_groups=card_groups,
        max_cards=len(card_groups),
        metadata=(
            ("reason", "POFFINで不足するケーシィ系たねをベンチへ置く"),
            ("targets", ",".join(str(card_id) for card_id in targets)),
        ),
        effect_card_id=CardId.BUDDY_BUDDY_POFFIN,
        effect_serial=option.card_serial,
        remaining_contexts=(SelectContext.TO_BENCH,),
    )
    continuity_poffin = (
        contains_abra
        and needs_continuity_setup(view)
        and spend_preserves_immediate_ko(view)
    )
    proactive_attack_poffin = (
        contains_abra
        and needs_attack_line_setup(view)
    )
    return Proposal(
        (option.position,),
        (
            CONTINUITY_POFFIN_PRIORITY
            if continuity_poffin
            else ATTACK_LINE_POFFIN_PRIORITY
            if proactive_attack_poffin
            else 810
        ),
        (
            "非最終KO前になかよしポフィンで後続ケーシィを補い、攻撃系統を合計3体へ戻す"
            if continuity_poffin
            else "次の相手番より前になかよしポフィンで進化前を補い、ケーシィ系統3体を準備する"
            if proactive_attack_poffin
            else "不足するケーシィ・ノコッチをなかよしポフィンで展開する"
        ),
        (
            "PLAYBOOK-POFFIN",
            "PLAYBOOK-SEARCH-INTENT",
            *(
                ("PLAYBOOK-BOARD-MINIMUM", "PLAYBOOK-STOP-WHEN-KO")
                if continuity_poffin
                else ()
            ),
            *(("PLAYBOOK-BOARD-MINIMUM",) if proactive_attack_poffin and not continuity_poffin else ()),
        ),
        intent,
    )


def _poke_pad_play(view, memory) -> Proposal | None:
    options = [
        option for option in view.options
        if option.type == int(OptionType.PLAY)
        and option.card_id == int(CardId.POKE_PAD)
        and option.card_serial is not None
    ]
    if not options:
        return None
    option = min(options, key=lambda item: (_hand_index(item), item.position))
    plans = plan_poke_pad_targets(view, memory)
    if not plans:
        return None
    active = view.active
    opening_pivot_plan = (
        next(
            (
                candidate
                for candidate in plans
                if candidate.kind == "SEARCH_DUDUNSPARCE_FOR_DRAW"
            ),
            None,
        )
        if (
            is_opening_attack_phase(view)
            and active is not None
            and int(active.id) == int(CardId.DUNSPARCE)
            and any(
                int(pokemon.id) == int(CardId.ALAKAZAM)
                and view.has_psychic_energy(pokemon)
                for pokemon in view.bench
            )
        )
        else None
    )
    if (
        must_reserve_poke_pad_for_fresh_kadabra(view, memory)
        and opening_pivot_plan is None
    ):
        return None
    maturity_needed = reserve_abra_needs_kadabra(view)
    maturity_plan = next(
        (
            candidate
            for candidate in plans
            if candidate.card_ids == (int(CardId.KADABRA),)
        ),
        None,
    ) if maturity_needed else None
    alakazam_plan = next(
        (
            candidate
            for candidate in plans
            if candidate.kind == "SEARCH_ALAKAZAM_FOR_CONTINUITY"
        ),
        None,
    )
    continuity_plan = (
        next(
            (
                candidate
                for candidate in plans
                if int(CardId.ABRA) in candidate.card_ids
            ),
            None,
        )
        if needs_attack_line_setup(view)
        else None
    )
    plan = (
        opening_pivot_plan
        or alakazam_plan
        or maturity_plan
        or continuity_plan
        or plans[0]
    )
    if must_reserve_poke_pad_for_opening_chain(
        view,
        plan.card_ids,
        memory,
    ):
        return None
    searches_kadabra_for_maturity = (
        maturity_needed
        and plan.card_ids == (int(CardId.KADABRA),)
    )
    maturity_pad = (
        searches_kadabra_for_maturity
        and nonfinal_immediate_ko(view)
        and search_preserves_immediate_ko(view, 1)
    )
    proactive_maturity_pad = (
        searches_kadabra_for_maturity
        and (
            maturity_needed
            or needs_attack_line_setup(view)
        )
    )
    continuity_pad = (
        int(CardId.ABRA) in plan.card_ids
        and needs_continuity_setup(view)
        and spend_preserves_immediate_ko(view)
    )
    proactive_attack_pad = (
        int(CardId.ABRA) in plan.card_ids
        and needs_attack_line_setup(view)
    )
    continuity_draw_pad = (
        int(CardId.DUDUNSPARCE) in plan.card_ids
        and needs_draw_reserve_setup(view)
        and spend_preserves_immediate_ko(view)
    )
    continuity_alakazam_pad = (
        plan.kind == "SEARCH_ALAKAZAM_FOR_CONTINUITY"
        and nonfinal_immediate_ko(view)
        and spend_preserves_immediate_ko(view)
    )
    proactive_alakazam_pad = (
        plan.kind == "SEARCH_ALAKAZAM_FOR_CONTINUITY"
        and not continuity_alakazam_pad
    )
    intent = PendingIntent.from_view(
        view,
        kind=plan.kind,
        card_ids=plan.card_ids,
        card_groups=(plan.card_ids,),
        max_cards=1,
        metadata=(
            ("reason", plan.reason),
            ("targets", ",".join(str(card_id) for card_id in plan.card_ids)),
        ),
        effect_card_id=CardId.POKE_PAD,
        effect_serial=option.card_serial,
        remaining_contexts=(SelectContext.TO_HAND,),
    )
    return Proposal(
        (option.position,),
        (
            OPENING_PIVOT_SEARCH_PRIORITY
            if opening_pivot_plan is not None
            else CONTINUITY_POKE_PAD_PRIORITY
            if continuity_pad
            else CONTINUITY_MATURITY_ITEM_PRIORITY
            if maturity_pad
            else CONTINUITY_POKE_PAD_PRIORITY
            if continuity_alakazam_pad
            else ATTACK_LINE_MATURITY_PRIORITY
            if proactive_maturity_pad or proactive_alakazam_pad
            else ATTACK_LINE_POKE_PAD_PRIORITY
            if proactive_attack_pad
            else CONTINUITY_DRAW_SEARCH_PRIORITY
            if continuity_draw_pad
            else 805
        ),
        (
             "バトル場のノコッチをノココッチへ進化させて前を空け、完成済みフーディンを攻撃位置へ出す"
             if opening_pivot_plan is not None
             else "非最終KO前にポケパッドで不足する後続ケーシィを確保する"
            if continuity_pad
            else "非最終KO前にポケパッドでユンゲラーを確保し、古い後続ケーシィを今すぐ進化させる"
            if maturity_pad
            else "非最終KO前にポケパッドで次番ユンゲラー用のフーディンを確保する"
            if continuity_alakazam_pad
            else "完成済みフーディンがいる間にポケパッドで後続ケーシィ用ユンゲラーを確保する"
            if proactive_maturity_pad
            else plan.reason
            if proactive_alakazam_pad
            else "次の相手番より前にポケパッドで3本目の進化前ケーシィを確保する"
            if proactive_attack_pad
            else "非最終KO前にポケパッドでノココッチを確保し、妨害後ドローを予約する"
            if continuity_draw_pad
            else plan.reason
        ),
        (
            *plan.rule_ids,
            *(
                ("PLAYBOOK-BOARD-MINIMUM", "PLAYBOOK-STOP-WHEN-KO")
                if continuity_pad or continuity_draw_pad
                else ()
            ),
            *(("PLAYBOOK-BOARD-MINIMUM",) if proactive_attack_pad and not continuity_pad else ()),
            *(("PLAYBOOK-BOARD-MINIMUM", "PLAYBOOK-T3-KADABRA") if proactive_maturity_pad else ()),
            *(
                ("PLAYBOOK-MAX-DRAW",)
                if continuity_draw_pad
                else ()
            ),
        ),
        intent,
    )


def _telepath_attach(view, memory) -> Proposal | None:
    powered_alakazam_waits = (
        view.own_turn_number >= 2
        and any(
            int(pokemon.id) == int(CardId.ALAKAZAM)
            and view.has_psychic_energy(pokemon)
            for pokemon in view.bench
        )
    )
    options = [
        option for option in view.options
        if (
            option.type == int(OptionType.ATTACH)
            and option.card_id == int(CardId.TELEPATH_PSYCHIC_ENERGY)
            and option.card_serial is not None
            and option.target is not None
            and option.target.id == int(CardId.ABRA)
            and not view.has_psychic_energy(option.target)
            and (
                not powered_alakazam_waits
                or option.target.area == int(Area.ACTIVE)
            )
        )
    ]
    if not options:
        return None

    reserved = memory.reserved_attacker_serial

    def key(option):
        target = option.target
        if view.own_turn_number >= 2 and target.area == int(Area.ACTIVE):
            group = 0
        elif reserved is not None and target.serial == reserved:
            group = 1
        elif target.area == int(Area.BENCH):
            group = 2
        elif target.area == int(Area.ACTIVE):
            group = 3
        else:
            group = 4
        return (group, target.index if target.index is not None else 10**9, option.position)

    option = min(options, key=key)
    target = option.target
    turn_two_active = (
        view.own_turn_number >= 2
        and target.area == int(Area.ACTIVE)
    )
    reason = (
        "2ターン目以降は前のケーシィへテレパス超を付け、そのまま進化・攻撃を狙う"
        if turn_two_active
        else "予約した攻撃役ケーシィへテレパス超を優先し、残り枠だけ展開する"
    )
    intent = build_telepath_bench_intent(view, option, target, reason)
    return Proposal(
        (option.position,),
        790,
        reason,
        (
            "FLOW-ATTACK-ENERGY"
            if view.own_turn_number >= 2
            else "PLAYBOOK-T1-TELEPATH",
            "PLAYBOOK-TELEPATH-LIMIT",
            "PLAYBOOK-SEARCH-INTENT",
        ),
        intent,
    )


def _continuity_energy_attach(view, memory) -> Proposal | None:
    urgent = (
        nonfinal_immediate_ko(view)
        and spend_preserves_immediate_ko(view)
    )
    active = view.active
    proactive = (
        active is not None
        and int(active.id) == int(CardId.ALAKAZAM)
        and view.has_psychic_energy(active)
        and not nonfinal_immediate_ko(view)
        and not immediate_ko_ends_game(view)
    )
    if not urgent and not proactive:
        return None
    current_attack_lines = attack_line_count(view)
    active_serial = None if view.active is None else view.active.serial

    def telepath_rebuild_from_current(option) -> bool:
        return (
            urgent
            and current_attack_lines == 1
            and option.card_id == int(CardId.TELEPATH_PSYCHIC_ENERGY)
            and option.target is not None
            and option.target.serial == active_serial
            and int(option.target.id) == int(CardId.ALAKAZAM)
            and possible_deck_count(view, memory, CardId.ABRA) > 0
            and len(view.bench) < int(view.own.get("benchMax", 5))
        )

    def hold_telepath_for_next_turn(option) -> bool:
        if (
            not urgent
            or option.card_id != int(CardId.TELEPATH_PSYCHIC_ENERGY)
            or option.target is None
        ):
            return False
        return not telepath_rebuild_from_current(option) and (
            current_attack_lines >= MINIMUM_ATTACK_LINES
            or int(option.target.id) != int(CardId.ABRA)
        )

    options = [
        option
        for option in view.options
        if (
            option.type == int(OptionType.ATTACH)
            and option.card_id in (
                int(CardId.BASIC_PSYCHIC),
                int(CardId.TELEPATH_PSYCHIC_ENERGY),
            )
            and not hold_telepath_for_next_turn(option)
            and option.card_serial is not None
            and option.target is not None
            and (
                telepath_rebuild_from_current(option)
                or (
                    option.target.serial != active_serial
                    and int(option.target.id) in (
                        int(CardId.ABRA),
                        int(CardId.KADABRA),
                        int(CardId.ALAKAZAM),
                    )
                    and not view.has_psychic_energy(option.target)
                )
            )
        )
    ]
    if not options:
        return None

    stage_rank = {
        int(CardId.ALAKAZAM): 0,
        int(CardId.KADABRA): 1,
        int(CardId.ABRA): 2,
    }
    reserved = memory.reserved_attacker_serial

    def key(option):
        target = option.target
        telepath_on_abra = (
            option.card_id == int(CardId.TELEPATH_PSYCHIC_ENERGY)
            and int(target.id) == int(CardId.ABRA)
        )
        return (
            stage_rank[int(target.id)],
            0 if not target.appear_this_turn else 1,
            0 if reserved is not None and target.serial == reserved else 1,
            0 if option.card_id == int(CardId.BASIC_PSYCHIC) else 1,
            0 if telepath_on_abra else 1,
            10**9 if target.serial is None else int(target.serial),
            int(option.card_serial),
            option.position,
        )

    option = min(options, key=key)
    target = option.target
    rebuilds_from_current = telepath_rebuild_from_current(option)
    reason = (
        "非最終KO前に現在のフーディンへテレパス超を重ね、ケーシィ2体を後続として出す"
        if rebuilds_from_current
        else
        "非最終KO前に次の攻撃役へ超エネルギーを付け、連続KOのエネルギーを先払いする"
        if urgent
        else "現在の攻撃役がいる間に次番の進化前へ超エネルギーを先払いする"
    )
    intent = None
    rule_ids = [
        "FLOW-ATTACK-ENERGY",
        "PLAYBOOK-BASIC-PSYCHIC",
        "PLAYBOOK-BOARD-MINIMUM",
        *(("PLAYBOOK-STOP-WHEN-KO",) if urgent else ()),
    ]
    if (
        option.card_id == int(CardId.TELEPATH_PSYCHIC_ENERGY)
        and (
            int(target.id) == int(CardId.ABRA)
            or rebuilds_from_current
        )
    ):
        intent = build_telepath_bench_intent(view, option, target, reason)
        rule_ids.extend(("PLAYBOOK-TELEPATH-LIMIT", "PLAYBOOK-SEARCH-INTENT"))
    return Proposal(
        (option.position,),
        CONTINUITY_ENERGY_PRIORITY if urgent else ATTACK_LINE_ENERGY_PRIORITY,
        reason,
        tuple(rule_ids),
        intent,
    )


def _air_balloon_attach(view) -> Proposal | None:
    active = view.active
    if active is None:
        return None
    survival_pivot = opening_abra_survival_pivot(view)
    powered_alakazam_waits = any(
        int(pokemon.id) == int(CardId.ALAKAZAM)
        and view.has_psychic_energy(pokemon)
        for pokemon in view.bench
    )
    if (
        int(active.id) not in PIVOT_IDS
        and not powered_alakazam_waits
        and survival_pivot is None
    ):
        return None
    options = [
        option for option in view.options
        if (
            option.type == int(OptionType.ATTACH)
            and option.card_id == int(CardId.AIR_BALLOON)
            and option.target is not None
            and option.target.area == int(Area.ACTIVE)
            and option.target.index == 0
            and option.target.serial == active.serial
        )
    ]
    if not options:
        return None
    option = min(options, key=lambda item: item.position)
    return Proposal(
        (option.position,),
        (
            OPENING_PIVOT_BALLOON_PRIORITY
            if (
                is_opening_attack_phase(view)
                and (powered_alakazam_waits or survival_pivot is not None)
            )
            else 780
        ),
        (
            "唯一のケーシィを次の相手番から守るため、ふうせんで退避できるようにする"
            if survival_pivot is not None
            else "攻撃可能なフーディンを前へ出すため、現在のバトルポケモンへふうせんを付ける"
            if powered_alakazam_waits
            else "前の退避役へふうせんを付ける"
        ),
        (
            ("PLAYBOOK-AIR-BALLOON", "PLAYBOOK-PRESERVE-ABRA")
            if survival_pivot is not None
            else ("PLAYBOOK-AIR-BALLOON",)
        ),
    )


@covers(
    "PLAYBOOK-ABRA-ZERO",
    "PLAYBOOK-ABRA-LIMIT",
    "PLAYBOOK-POFFIN",
    "PLAYBOOK-POKE-PAD",
    "FLOW-SETUP-FAN-CALL",
    "PLAYBOOK-T1-TELEPATH",
    "PLAYBOOK-TELEPATH-LIMIT",
    "PLAYBOOK-AIR-BALLOON",
    "PLAYBOOK-PRESERVE-ABRA",
    "PLAYBOOK-FEZANDIPITI-DEPLOY",
    "FLOW-ATTACK-ENERGY",
    "PLAYBOOK-BASIC-PSYCHIC",
    "PLAYBOOK-BOARD-MINIMUM",
    "PLAYBOOK-DECK-SAFETY",
    "PLAYBOOK-STOP-WHEN-KO",
    "PLAYBOOK-SEARCH-INTENT",
)
def propose_development(view, memory) -> Proposal | None:
    if view.is_own_turn and view.own_turn_number == 1:
        fan_calls = [
            option for option in view.options
            if option.type == int(OptionType.ABILITY)
            and option.card_id == int(CardId.FAN_ROTOM)
            and option.source is not None
            and option.source.serial is not None
        ]
        if fan_calls:
            option = min(fan_calls, key=lambda item: (_hand_index(item), item.position))
            shortage = max(0, min(3, 3 - _field_or_hand_count(view, CardId.DUNSPARCE)))
            if shortage == 0:
                fan_calls = []
            else:
                intent = PendingIntent.from_view(
                    view,
                    kind="SEARCH_DUNSPARCE_FOR_FAN_CALL",
                    card_ids=(int(CardId.DUNSPARCE),),
                    card_groups=tuple(
                        (int(CardId.DUNSPARCE),) for _ in range(shortage)
                    ),
                    max_cards=shortage,
                    metadata=(("reason", "最初の自分の番にファンコールで不足するノコッチを集める"),),
                    effect_card_id=CardId.FAN_ROTOM,
                    effect_serial=None if option.source is None else option.source.serial,
                    remaining_contexts=(SelectContext.TO_HAND,),
                )
                return Proposal(
                    (option.position,),
                    820,
                    "最初の自分の番にノコッチを集める",
                    ("FLOW-SETUP-FAN-CALL", "PLAYBOOK-SEARCH-INTENT"),
                    intent,
                )

    opening_balloon = _air_balloon_attach(view)
    powered_alakazam_waits = any(
        int(pokemon.id) == int(CardId.ALAKAZAM)
        and view.has_psychic_energy(pokemon)
        for pokemon in view.bench
    )
    if (
        opening_balloon is not None
        and is_opening_attack_phase(view)
        and powered_alakazam_waits
    ):
        # 提案関数内の早期returnで低優先度の任意展開が先に選ばれると、
        # ハンドパワーの打点を失う。完成済み攻撃役への退避導線を先に作る。
        return opening_balloon

    poffin = _poffin_play(view, memory)
    if poffin is not None and not proposal_is_deck_safe(view, poffin):
        poffin = None
    pad = _poke_pad_play(view, memory)
    if pad is not None and not proposal_is_deck_safe(view, pad):
        pad = None
    direct = _direct_basic_play(view)

    line_setup = [
        proposal
        for proposal in (poffin, direct, pad)
        if proposal is not None and proposal.priority >= ATTACK_LINE_POKE_PAD_PRIORITY
    ]
    continuity_energy = _continuity_energy_attach(view, memory)
    if (
        continuity_energy is not None
        and not proposal_is_deck_safe(view, continuity_energy)
    ):
        continuity_energy = None
    priority_development = [
        *line_setup,
        *(() if continuity_energy is None else (continuity_energy,)),
    ]
    if priority_development:
        return max(
            priority_development,
            key=lambda proposal: proposal.priority,
        )

    fezandipiti = _fezandipiti_play(view, memory)
    if (
        fezandipiti is not None
        and proposal_is_deck_safe(view, fezandipiti)
    ):
        return fezandipiti

    if _field_count(view, CardId.ABRA) > 0:
        telepath = _telepath_attach(view, memory)
        if telepath is not None and proposal_is_deck_safe(view, telepath):
            return telepath

    if direct is not None:
        return direct

    if poffin is not None:
        return poffin

    if pad is not None:
        return pad

    return _air_balloon_attach(view)
