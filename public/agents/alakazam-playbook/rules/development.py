from __future__ import annotations

from cards import CardId
from model import Area, OptionType, SelectContext
from proposals import PendingIntent, Proposal, covers
from rules.poke_pad import plan_poke_pad_targets
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


def _field_count(view, card_id: int) -> int:
    return sum(int(pokemon.id) == int(card_id) for pokemon in view.field)


def _field_or_hand_count(view, card_id: int) -> int:
    return _field_count(view, card_id) + sum(
        int(hand_id) == int(card_id) for hand_id in view.hand_ids
    )


def _hand_index(option) -> int:
    value = option.raw.get("index")
    return int(value) if value is not None else option.position


def _proposal_for_play(option, reason: str, rule_ids: tuple[str, ...]) -> Proposal:
    return Proposal((option.position,), 800, reason, rule_ids)


def _fezandipiti_play(view, memory) -> Proposal | None:
    if (
        not view.is_own_turn
        or memory.fezandipiti_draw_turn != view.own_turn_number
    ):
        return None
    if len(view.bench) >= int(view.own.get("benchMax", 5)):
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
    field_abra = _field_count(view, CardId.ABRA)
    field_dunsparce = _field_count(view, CardId.DUNSPARCE)
    field_fan_rotom = _field_count(view, CardId.FAN_ROTOM)
    choices = []
    for option in view.options:
        if option.type != int(OptionType.PLAY) or option.card_id is None:
            continue
        card_id = int(option.card_id)
        if card_id == int(CardId.ABRA) and field_abra < 3:
            choices.append((0, _hand_index(option), option.position, option, "ケーシィを直接展開する"))
        elif card_id == int(CardId.FAN_ROTOM) and view.is_own_turn and view.own_turn_number == 1 and field_fan_rotom == 0:
            choices.append((1, _hand_index(option), option.position, option, "初ターンにスピンロトムを展開する"))
        elif card_id == int(CardId.DUNSPARCE) and field_dunsparce < 3:
            choices.append((2, _hand_index(option), option.position, option, "ノコッチを最大数まで展開する"))
    if not choices:
        return None
    _, _, _, option, reason = min(choices, key=lambda item: item[:3])
    rule_ids = {
        int(CardId.ABRA): ("PLAYBOOK-ABRA-LIMIT",),
        int(CardId.FAN_ROTOM): ("FLOW-SETUP-FAN-CALL",),
        int(CardId.DUNSPARCE): ("PLAYBOOK-MAX-DRAW",),
    }[int(option.card_id)]
    return _proposal_for_play(option, reason, rule_ids)


def _poffin_card_groups(view, max_cards: int) -> tuple[tuple[int, ...], ...]:
    counts = {
        int(CardId.ABRA): _field_or_hand_count(view, CardId.ABRA),
        int(CardId.DUNSPARCE): _field_or_hand_count(view, CardId.DUNSPARCE),
        int(CardId.FAN_ROTOM): _field_or_hand_count(view, CardId.FAN_ROTOM),
    }
    fan_is_useful = view.is_own_turn and view.own_turn_number == 1
    groups = []
    for _ in range(max_cards):
        priority = []

        def add(card_id: CardId, needed: bool) -> None:
            value = int(card_id)
            if needed and value not in priority:
                priority.append(value)

        if counts[int(CardId.ABRA)] == 0:
            add(CardId.ABRA, True)
        elif fan_is_useful and counts[int(CardId.FAN_ROTOM)] == 0:
            add(CardId.FAN_ROTOM, True)
        elif counts[int(CardId.ABRA)] < 2:
            add(CardId.ABRA, True)
        elif counts[int(CardId.DUNSPARCE)] < 3:
            add(CardId.DUNSPARCE, True)
        else:
            add(CardId.ABRA, counts[int(CardId.ABRA)] < 3)

        add(CardId.ABRA, counts[int(CardId.ABRA)] < 3)
        add(CardId.FAN_ROTOM, fan_is_useful and counts[int(CardId.FAN_ROTOM)] < 1)
        add(CardId.DUNSPARCE, counts[int(CardId.DUNSPARCE)] < 3)
        if not priority:
            break
        groups.append(tuple(priority))
        counts[priority[0]] += 1
    return tuple(groups)


def _poffin_play(view) -> Proposal | None:
    bench_space = max(0, int(view.own.get("benchMax", 5)) - len(view.bench))
    if bench_space <= 0:
        return None
    card_groups = _poffin_card_groups(view, min(2, bench_space))
    if not card_groups:
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
    return Proposal(
        (option.position,),
        810,
        "不足するケーシィ・ノコッチをなかよしポフィンで展開する",
        ("PLAYBOOK-POFFIN", "PLAYBOOK-SEARCH-INTENT"),
        intent,
    )


def _poke_pad_play(view) -> Proposal | None:
    options = [
        option for option in view.options
        if option.type == int(OptionType.PLAY)
        and option.card_id == int(CardId.POKE_PAD)
        and option.card_serial is not None
    ]
    if not options:
        return None
    option = min(options, key=lambda item: (_hand_index(item), item.position))
    plans = plan_poke_pad_targets(view)
    if not plans:
        return None
    plan = plans[0]
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
        805,
        plan.reason,
        plan.rule_ids,
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


def _air_balloon_attach(view) -> Proposal | None:
    active = view.active
    if active is None:
        return None
    powered_alakazam_waits = any(
        int(pokemon.id) == int(CardId.ALAKAZAM)
        and view.has_psychic_energy(pokemon)
        for pokemon in view.bench
    )
    if int(active.id) not in PIVOT_IDS and not powered_alakazam_waits:
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
        780,
        "攻撃可能なフーディンを前へ出すため、現在のバトルポケモンへふうせんを付ける"
        if powered_alakazam_waits
        else "前の退避役へふうせんを付ける",
        ("PLAYBOOK-AIR-BALLOON",),
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
    "PLAYBOOK-FEZANDIPITI-DEPLOY",
    "FLOW-ATTACK-ENERGY",
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

    fezandipiti = _fezandipiti_play(view, memory)
    if fezandipiti is not None:
        return fezandipiti

    if _field_count(view, CardId.ABRA) > 0:
        telepath = _telepath_attach(view, memory)
        if telepath is not None:
            return telepath

    direct = _direct_basic_play(view)
    if direct is not None:
        return direct

    poffin = _poffin_play(view)
    if poffin is not None:
        return poffin

    pad = _poke_pad_play(view)
    if pad is not None:
        return pad

    return _air_balloon_attach(view)
