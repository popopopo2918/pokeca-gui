from __future__ import annotations

from cards import CardId
from memory import possible_deck_count
from model import Area, OptionType, SelectContext
from proposals import PendingIntent, Proposal, covers
from rules.attack import can_hand_power_ko
from rules.board_plan import (
    MAXIMUM_ATTACK_LINES,
    MINIMUM_ATTACK_LINES,
    MINIMUM_DRAW_LINES,
    OPENING_PIVOT_BALLOON_PRIORITY,
    OPENING_PIVOT_SEARCH_PRIORITY,
    attack_line_count,
    can_spend_bench_slots,
    draw_line_count,
    first_turn_active_survives,
    full_board_plan,
    full_board_plan_for_counts,
    has_taken_prize,
    is_opening_attack_phase,
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
    CONTINUITY_DRAW_SEARCH_PRIORITY,
    CONTINUITY_ENERGY_PRIORITY,
    CONTINUITY_MATURITY_ITEM_PRIORITY,
    CONTINUITY_POFFIN_PRIORITY,
    CONTINUITY_POKE_PAD_PRIORITY,
    immediate_ko_ends_game,
    needs_continuity_setup,
    needs_draw_reserve_setup,
    needs_full_board_setup,
    nonfinal_immediate_ko,
    search_preserves_immediate_ko,
    spend_preserves_immediate_ko,
)
from rules.deck_safety import minimum_deck_reserve, proposal_is_deck_safe
from rules.disruption import (
    DisruptionMode,
    disruption_mode,
    next_attack_is_secured_without_fezandipiti_draw,
    propose_proactive_fezandipiti,
)
from rules.poke_pad import (
    must_reserve_poke_pad_for_opening_chain,
    must_reserve_poke_pad_for_fresh_kadabra,
    plan_poke_pad_targets,
)
from rules.telepath import build_telepath_bench_intent


FULL_BOARD_DIRECT_PRIORITY = 1012
FULL_BOARD_POFFIN_PRIORITY = 1011
FULL_BOARD_POKE_PAD_PRIORITY = 1010
FULL_BOARD_BASIC_IDS = (int(CardId.ABRA), int(CardId.DUNSPARCE))
FULL_BOARD_POKE_PAD_KINDS = frozenset({
    "SEARCH_ABRA_FOR_FULL_BOARD",
    "SEARCH_DUNSPARCE_FOR_FULL_BOARD",
    "SEARCH_BASIC_FOR_FULL_BOARD",
})


def _field_count(view, card_id: int) -> int:
    return sum(int(pokemon.id) == int(card_id) for pokemon in view.field)


def _hand_index(option) -> int:
    value = option.raw.get("index")
    return int(value) if value is not None else option.position


def _full_board_priority(view, preferred: int, fallback: int = 800) -> int:
    if first_turn_active_survives(view):
        return preferred
    return preferred if nonfinal_immediate_ko(view) else fallback


def _full_board_basic_choices(view) -> tuple:
    plan = full_board_plan(view)
    return tuple(sorted(
        (
            option
            for option in view.options
            if option.type == int(OptionType.PLAY)
            and option.card_id in plan.target_basic_ids
        ),
        key=lambda option: (
            10**18 if option.card_serial is None else int(option.card_serial),
            _hand_index(option),
            option.position,
        ),
    ))


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
    current_ko_ready = can_hand_power_ko(view)
    next_attack_ready = next_attack_is_secured_without_fezandipiti_draw(
        view,
        memory,
    )
    if current_ko_ready and next_attack_ready:
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
    if not spend_preserves_immediate_ko(view, 1):
        return None

    attack_lines = attack_line_count(view)
    draw_lines = draw_line_count(view)
    full_board_choices = _full_board_basic_choices(view)
    if not full_board_choices:
        return None

    deck_count = max(0, int(view.own.get("deckCount", 0)))
    emergency_recycle = (
        0 < deck_count <= minimum_deck_reserve(view) + 1
        and draw_lines == 0
        and int(CardId.DUDUNSPARCE) in view.hand_ids
    )
    if emergency_recycle:
        option = next(
            (
                candidate
                for candidate in full_board_choices
                if candidate.card_id == int(CardId.DUNSPARCE)
            ),
            None,
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

    choices = tuple(
        option
        for option in full_board_choices
        if (
            int(option.card_id) != int(CardId.DUNSPARCE)
            or can_spend_bench_slots(view)
        )
        and not (
            int(option.card_id) == int(CardId.ABRA)
            and _fresh_abra_should_wait_for_bench_snipe(view)
        )
    )
    if not choices:
        return None

    continuity_dunsparce = (
        draw_lines < MINIMUM_DRAW_LINES
        and nonfinal_immediate_ko(view)
    )
    if continuity_dunsparce:
        option = next(
            (
                choice for choice in choices
                if int(choice.card_id) == int(CardId.DUNSPARCE)
            ),
            None,
        )
        if option is not None:
            return _proposal_for_play(
                option,
                (
                    "非最終KO前にノコッチを置き、次番の手札妨害後ドローを準備する"
                    if draw_lines == 0
                    else "非最終KO前に不足したノコッチを再展開し、"
                    "次番の手札妨害後ドローを準備する"
                ),
                (
                    "PLAYBOOK-MAX-DRAW",
                    "PLAYBOOK-BOARD-MINIMUM",
                    "PLAYBOOK-STOP-WHEN-KO",
                ),
                FULL_BOARD_DIRECT_PRIORITY,
            )

    option = choices[0]
    rule_ids = {
        int(CardId.ABRA): ("PLAYBOOK-ABRA-LIMIT",),
        int(CardId.DUNSPARCE): ("PLAYBOOK-MAX-DRAW",),
    }[int(option.card_id)]
    continuity_bench = (
        int(option.card_id) == int(CardId.ABRA)
        and needs_continuity_setup(view)
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
    elif int(option.card_id) == int(CardId.ABRA):
        reason = "6枠盤面へ向けて4本目のケーシィ系統を直接展開する"
    else:
        reason = "6枠盤面へ向けてノコッチ系統を直接展開する"

    priority = _full_board_priority(view, FULL_BOARD_DIRECT_PRIORITY)
    if continuity_bench:
        priority = max(priority, CONTINUITY_BENCH_PRIORITY)
    elif proactive_attack_bench:
        priority = max(priority, ATTACK_LINE_BENCH_PRIORITY)
    return _proposal_for_play(
        option,
        reason,
        rule_ids,
        priority,
    )


def _xerosic_abra_protection_play(view, memory) -> Proposal | None:
    if disruption_mode(memory) is not DisruptionMode.XEROSIC:
        return None
    bench_space = max(0, int(view.own.get("benchMax", 5)) - len(view.bench))
    if bench_space <= 0 or attack_line_count(view) >= MAXIMUM_ATTACK_LINES:
        return None
    if not spend_preserves_immediate_ko(view, 1):
        return None

    option = min(
        (
            candidate
            for candidate in view.options
            if candidate.type == int(OptionType.PLAY)
            and candidate.card_id == int(CardId.ABRA)
        ),
        key=lambda candidate: (
            10**18 if candidate.card_serial is None else int(candidate.card_serial),
            _hand_index(candidate),
            candidate.position,
        ),
        default=None,
    )
    if option is None:
        return None
    return _proposal_for_play(
        option,
        "クセロシキで捨てられる前に手札のケーシィを公開領域へ移して守る",
        ("PLAYBOOK-ABRA-LIMIT", "PLAYBOOK-PRESERVE-ABRA"),
        _full_board_priority(view, FULL_BOARD_DIRECT_PRIORITY),
    )


def _poffin_card_groups(
    view,
    memory,
    max_cards: int,
) -> tuple[tuple[tuple[int, ...], ...], tuple[int, ...]]:
    planned_attack_lines = attack_line_count(view)
    planned_draw_lines = draw_line_count(view)
    planned_field_count = len(view.field)
    remaining = {
        card_id: possible_deck_count(view, memory, card_id)
        for card_id in FULL_BOARD_BASIC_IDS
    }
    groups = []
    serial_tie_groups = []
    for _ in range(max_cards):
        plan = full_board_plan_for_counts(
            planned_attack_lines,
            planned_draw_lines,
            planned_field_count,
        )
        opening_draw_first = (
            planned_attack_lines == MINIMUM_ATTACK_LINES - 1
            and planned_draw_lines == 0
            and not has_taken_prize(view)
            and not powered_alakazam_exists(view)
        )
        preferred_floor_card = (
            int(CardId.DUNSPARCE)
            if opening_draw_first
            else int(CardId.ABRA)
            if planned_attack_lines < MINIMUM_ATTACK_LINES
            else int(CardId.DUNSPARCE)
            if planned_draw_lines < MINIMUM_DRAW_LINES
            else None
        )

        def strategic_key(card_id: int) -> tuple[int, int, int, int, int]:
            attack = card_id == int(CardId.ABRA)
            safety_deficit = max(
                0,
                (
                    MINIMUM_ATTACK_LINES - planned_attack_lines
                    if attack
                    else MINIMUM_DRAW_LINES - planned_draw_lines
                ),
            )
            next_stage_ready = (
                int(CardId.KADABRA) in view.hand_ids
                or (
                    int(CardId.RARE_CANDY) in view.hand_ids
                    and int(CardId.ALAKAZAM) in view.hand_ids
                )
                if attack
                else int(CardId.DUDUNSPARCE) in view.hand_ids
            )
            return (
                0 if card_id == preferred_floor_card else 1,
                0 if safety_deficit > 0 else 1,
                -safety_deficit,
                0 if next_stage_ready else 1,
                -remaining.get(card_id, 0),
            )

        priority = tuple(sorted(
            (
                card_id
                for card_id in FULL_BOARD_BASIC_IDS
                if card_id in plan.target_basic_ids
                and remaining.get(card_id, 0) > 0
            ),
            key=lambda card_id: (*strategic_key(card_id), card_id),
        ))
        if not priority:
            break
        if (
            plan.open_slots == 1
            and len(priority) > 1
            and len({strategic_key(card_id) for card_id in priority}) == 1
        ):
            serial_tie_groups.append(len(groups))
        groups.append(priority)
        selected = priority[0]
        remaining[selected] = max(0, remaining.get(selected, 0) - 1)
        if selected == int(CardId.ABRA):
            planned_attack_lines += 1
        else:
            planned_draw_lines += 1
        planned_field_count += 1
    return tuple(groups), tuple(serial_tie_groups)


def _core_basic_can_be_played_or_searched_now(view, memory) -> bool:
    if any(
        option.type == int(OptionType.PLAY)
        and option.card_id in FULL_BOARD_BASIC_IDS
        for option in view.options
    ):
        return True

    bench_space = max(0, int(view.own.get("benchMax", 5)) - len(view.bench))
    if bench_space <= 0:
        return False

    dawn_is_legal = any(
        option.type == int(OptionType.PLAY)
        and option.card_id == int(CardId.DAWN)
        for option in view.options
    )
    if dawn_is_legal and any(
        possible_deck_count(view, memory, card_id) > 0
        for card_id in FULL_BOARD_BASIC_IDS
    ):
        return True

    poffin_is_legal = any(
        option.type == int(OptionType.PLAY)
        and option.card_id == int(CardId.BUDDY_BUDDY_POFFIN)
        for option in view.options
    )
    if poffin_is_legal:
        card_groups, _ = _poffin_card_groups(
            view,
            memory,
            min(2, bench_space),
        )
        if any(
            card_id in FULL_BOARD_BASIC_IDS
            for group in card_groups
            for card_id in group
        ):
            return True

    pad_is_legal = any(
        option.type == int(OptionType.PLAY)
        and option.card_id == int(CardId.POKE_PAD)
        for option in view.options
    )
    return pad_is_legal and any(
        card_id in FULL_BOARD_BASIC_IDS
        for plan in plan_poke_pad_targets(view, memory)
        for card_id in plan.card_ids
    )


def _emergency_fezandipiti_play(view, memory) -> Proposal | None:
    bench_space = max(0, int(view.own.get("benchMax", 5)) - len(view.bench))
    if (
        len(view.field) != 1
        or bench_space <= 0
        or _core_basic_can_be_played_or_searched_now(view, memory)
    ):
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
        995,
        "場が1体だけでコア基本を展開できないため、キチキギスexを出して場切れを防ぐ",
        ("PLAYBOOK-FEZANDIPITI", "PLAYBOOK-FEZANDIPITI-DEPLOY"),
    )


def _poffin_play(view, memory) -> Proposal | None:
    bench_space = max(0, int(view.own.get("benchMax", 5)) - len(view.bench))
    if bench_space <= 0:
        return None
    if not spend_preserves_immediate_ko(view, 1):
        return None
    card_groups, serial_tie_groups = _poffin_card_groups(
        view,
        memory,
        min(2, bench_space),
    )
    if not card_groups:
        return None
    abra_deferred_for_snipe = _fresh_abra_should_wait_for_bench_snipe(view)
    if abra_deferred_for_snipe:
        filtered_groups = []
        filtered_tie_groups = []
        safe_remaining = {
            card_id: possible_deck_count(view, memory, card_id)
            for card_id in FULL_BOARD_BASIC_IDS
        }
        for old_index, group in enumerate(card_groups):
            safe_group = tuple(
                card_id
                for card_id in group
                if int(card_id) != int(CardId.ABRA)
                and safe_remaining.get(int(card_id), 0) > 0
            )
            if not safe_group:
                continue
            new_index = len(filtered_groups)
            filtered_groups.append(safe_group)
            if old_index in serial_tie_groups and len(safe_group) > 1:
                filtered_tie_groups.append(new_index)
            selected = int(safe_group[0])
            safe_remaining[selected] = max(
                0,
                safe_remaining.get(selected, 0) - 1,
            )
        card_groups = tuple(filtered_groups)
        serial_tie_groups = tuple(filtered_tie_groups)
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
    if (
        attack_line_count(view) < MINIMUM_ATTACK_LINES
        and not contains_abra
        and not abra_deferred_for_snipe
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
    option = min(
        options,
        key=lambda item: (
            int(item.card_serial),
            _hand_index(item),
            item.position,
        ),
    )
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
            (
                "reason",
                "公開ベンチ狙撃を避け、POFFINで安全なノコッチをベンチへ置く"
                if abra_deferred_for_snipe
                else "POFFINで不足するケーシィ系たねをベンチへ置く",
            ),
            ("targets", ",".join(str(card_id) for card_id in targets)),
            *(
                ((
                    "serial_tie_groups",
                    ",".join(str(index) for index in serial_tie_groups),
                ),)
                if serial_tie_groups
                else ()
            ),
        ),
        effect_card_id=CardId.BUDDY_BUDDY_POFFIN,
        effect_serial=option.card_serial,
        remaining_contexts=(SelectContext.TO_BENCH,),
    )
    continuity_poffin = (
        contains_abra
        and needs_continuity_setup(view)
    )
    proactive_attack_poffin = (
        contains_abra
        and needs_attack_line_setup(view)
    )
    full_board_poffin = needs_full_board_setup(view)
    ordered_full_board_poffin = (
        full_board_poffin
        and attack_line_count(view) >= MINIMUM_ATTACK_LINES - 1
    )
    priority = _full_board_priority(
        view,
        FULL_BOARD_POFFIN_PRIORITY,
        fallback=810,
    )
    if continuity_poffin and not ordered_full_board_poffin:
        priority = max(priority, CONTINUITY_POFFIN_PRIORITY)
    elif proactive_attack_poffin:
        priority = max(priority, ATTACK_LINE_POFFIN_PRIORITY)
    return Proposal(
        (option.position,),
        priority,
        (
            "非最終KO前になかよしポフィンで後続ケーシィを補い、攻撃系統を合計3体へ戻す"
            if continuity_poffin
            else "次の相手番より前になかよしポフィンで進化前を補い、ケーシィ系統3体を準備する"
            if proactive_attack_poffin
            else "非最終KOを保ちながら、なかよしポフィンで6枠盤面を完成へ近づける"
            if full_board_poffin
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
    draw_evolution_plan = (
        next(
            (
                candidate
                for candidate in plans
                if candidate.kind == "SEARCH_DUDUNSPARCE_FOR_DRAW"
            ),
            None,
        )
        if needs_draw_reserve_setup(view)
        else None
    )
    board_plan = full_board_plan(view)
    full_board_basic_plan = next(
        (
            candidate
            for candidate in plans
            if candidate.kind in FULL_BOARD_POKE_PAD_KINDS
        ),
        None,
    )
    emergency_plan = next(
        (
            candidate
            for candidate in plans
            if candidate.kind not in FULL_BOARD_POKE_PAD_KINDS
            and candidate.kind != "SEARCH_ALAKAZAM_FOR_CONTINUITY"
        ),
        None,
    )
    draw_floor_basic_plan = (
        next(
            (
                candidate
                for candidate in plans
                if candidate.kind in FULL_BOARD_POKE_PAD_KINDS
                and int(CardId.DUNSPARCE) in candidate.card_ids
            ),
            None,
        )
        if draw_line_count(view) < MINIMUM_DRAW_LINES
        else None
    )
    preferred_full_board_basic = (
        full_board_basic_plan
        if attack_line_count(view) >= MINIMUM_ATTACK_LINES
        else None
    )
    urgent_alakazam_plan = (
        alakazam_plan
        if (
            nonfinal_immediate_ko(view)
            or attack_line_count(view) < MINIMUM_ATTACK_LINES
        )
        else None
    )
    plan = (
        opening_pivot_plan
        or urgent_alakazam_plan
        or maturity_plan
        or continuity_plan
        or draw_evolution_plan
        or emergency_plan
        or draw_floor_basic_plan
        or preferred_full_board_basic
        or alakazam_plan
        or plans[0]
    )
    if (
        int(CardId.ABRA) in plan.card_ids
        and _fresh_abra_should_wait_for_bench_snipe(view)
    ):
        return None
    searches_attack_floor_basic = (
        plan.kind in FULL_BOARD_POKE_PAD_KINDS
        and int(CardId.ABRA) in plan.card_ids
        and attack_line_count(view) < MINIMUM_ATTACK_LINES
    )
    searches_draw_floor_basic = (
        plan.kind in FULL_BOARD_POKE_PAD_KINDS
        and int(CardId.DUNSPARCE) in plan.card_ids
        and draw_line_count(view) < MINIMUM_DRAW_LINES
    )
    intent_kind = (
        "SEARCH_ABRA_FOR_CONTINUITY"
        if (
            searches_attack_floor_basic
            or (
                plan.kind == "SEARCH_ABRA_FOR_SAFE_BENCH"
                and needs_attack_line_setup(view)
            )
        )
        else "SEARCH_DUNSPARCE_FOR_SETUP"
        if searches_draw_floor_basic
        else plan.kind
    )
    intent_reason = (
        "攻撃中のフーディンを含めたケーシィ系統3体目を確保する"
        if searches_attack_floor_basic
        else "不足するノコッチをポケパッドで探す"
        if searches_draw_floor_basic
        else plan.reason
    )
    intent_rule_ids = (
        (
            "PLAYBOOK-ABRA-LIMIT",
            "PLAYBOOK-BOARD-MINIMUM",
            "PLAYBOOK-SEARCH-INTENT",
        )
        if searches_attack_floor_basic
        else ("PLAYBOOK-POKE-PAD", "PLAYBOOK-SEARCH-INTENT")
        if searches_draw_floor_basic
        else plan.rule_ids
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
        and not _full_board_basic_choices(view)
    )
    proactive_alakazam_pad = (
        plan.kind == "SEARCH_ALAKAZAM_FOR_CONTINUITY"
        and not continuity_alakazam_pad
    )
    searches_full_board_basic = any(
        int(card_id) in board_plan.target_basic_ids
        for card_id in plan.card_ids
    )
    optional_full_board_pad = (
        opening_pivot_plan is None
        and board_plan.open_slots == 1
        and not searches_attack_floor_basic
        and not searches_draw_floor_basic
        and searches_full_board_basic
        and spend_preserves_immediate_ko(view, 1)
        and (
            first_turn_active_survives(view)
            or needs_full_board_setup(view)
        )
    )
    intent = PendingIntent.from_view(
        view,
        kind=intent_kind,
        card_ids=plan.card_ids,
        card_groups=(plan.card_ids,),
        max_cards=1,
        metadata=(
            ("reason", intent_reason),
            ("targets", ",".join(str(card_id) for card_id in plan.card_ids)),
            *(
                (("serial_tie_groups", "0"),)
                if len(plan.card_ids) > 1
                else ()
            ),
        ),
        effect_card_id=CardId.POKE_PAD,
        effect_serial=option.card_serial,
        remaining_contexts=(SelectContext.TO_HAND,),
    )
    return Proposal(
        (option.position,),
        (
            FULL_BOARD_POKE_PAD_PRIORITY
            if optional_full_board_pad or searches_attack_floor_basic
            else OPENING_PIVOT_SEARCH_PRIORITY
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
            else intent_reason
        ),
        (
            *intent_rule_ids,
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
    telepath_compression_before_draw = (
        int(CardId.RARE_CANDY) not in view.hand_ids
        and sum(
            int(pokemon.id) == int(CardId.ABRA)
            for pokemon in view.field
        ) == 2
        and len(view.bench) < int(view.own.get("benchMax", 5))
    )
    kadabra_draw_available = any(
        option.type == int(OptionType.EVOLVE)
        and option.card_id == int(CardId.KADABRA)
        for option in view.options
    )
    if kadabra_draw_available and not telepath_compression_before_draw:
        return None
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
    intent = build_telepath_bench_intent(
        view,
        option,
        target,
        reason,
        memory,
    )
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
        intent = build_telepath_bench_intent(
            view,
            option,
            target,
            reason,
            memory,
        )
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
        not powered_alakazam_waits
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


def _fresh_abra_should_wait_for_bench_snipe(view) -> bool:
    secured_lines = sum(
        int(pokemon.id) == int(CardId.ALAKAZAM)
        or (
            int(pokemon.id) == int(CardId.KADABRA)
            and view.has_psychic_energy(pokemon)
        )
        for pokemon in view.field
    )
    if secured_lines < 2:
        return False
    return any(
        int(projection.fixed_bench_damage) >= 50
        for projection in view.public_attack_projections()
    )


@covers(
    "PLAYBOOK-ABRA-ZERO",
    "PLAYBOOK-ABRA-LIMIT",
    "PLAYBOOK-POFFIN",
    "PLAYBOOK-POKE-PAD",
    "PLAYBOOK-T1-TELEPATH",
    "PLAYBOOK-TELEPATH-LIMIT",
    "PLAYBOOK-AIR-BALLOON",
    "PLAYBOOK-PRESERVE-ABRA",
    "PLAYBOOK-FEZANDIPITI-DEPLOY",
    "PLAYBOOK-FEZANDIPITI-TERMINAL",
    "FLOW-ATTACK-ENERGY",
    "PLAYBOOK-BASIC-PSYCHIC",
    "PLAYBOOK-BOARD-MINIMUM",
    "PLAYBOOK-DECK-SAFETY",
    "PLAYBOOK-STOP-WHEN-KO",
    "PLAYBOOK-SEARCH-INTENT",
)
def propose_development(view, memory) -> Proposal | None:
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

    terminal_fezandipiti = propose_proactive_fezandipiti(view, memory)
    if (
        terminal_fezandipiti is not None
        and proposal_is_deck_safe(view, terminal_fezandipiti)
    ):
        return terminal_fezandipiti

    # さかてにとるの正味+2枚で現在KOへ届く時は、任意の盤面展開より先に
    # 攻撃成立を回復する。届かない場合は既存の確定展開を先に処理する。
    urgent_fezandipiti = _fezandipiti_play(view, memory)
    if (
        urgent_fezandipiti is not None
        and not can_hand_power_ko(view)
        and can_hand_power_ko(
            view,
            hand_size=int(view.hand_size) + 2,
        )
        and proposal_is_deck_safe(view, urgent_fezandipiti)
    ):
        return urgent_fezandipiti

    poffin = _poffin_play(view, memory)
    if poffin is not None and not proposal_is_deck_safe(view, poffin):
        poffin = None
    pad = _poke_pad_play(view, memory)
    if pad is not None and not proposal_is_deck_safe(view, pad):
        pad = None
    direct = _direct_basic_play(view)

    emergency_fezandipiti = _emergency_fezandipiti_play(view, memory)
    if (
        emergency_fezandipiti is not None
        and proposal_is_deck_safe(view, emergency_fezandipiti)
    ):
        return emergency_fezandipiti

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

    fezandipiti = urgent_fezandipiti
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

    air_balloon = _air_balloon_attach(view)
    if air_balloon is not None:
        return air_balloon
    return _xerosic_abra_protection_play(view, memory)
