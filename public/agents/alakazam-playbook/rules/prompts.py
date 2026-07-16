from __future__ import annotations

from collections.abc import Iterable, Sequence

from cards import CardId
from model import LegalOption, OptionType, SelectContext, SelectType
from proposals import IntentUpdate, PendingIntent, Proposal, covers
from rules.poke_pad import plan_poke_pad_targets


_CARD_PROMPT_CONTEXTS = {
    int(CardId.BUDDY_BUDDY_POFFIN): int(SelectContext.TO_BENCH),
    int(CardId.POKE_PAD): int(SelectContext.TO_HAND),
    int(CardId.FAN_ROTOM): int(SelectContext.TO_HAND),
    int(CardId.TELEPATH_PSYCHIC_ENERGY): int(SelectContext.TO_BENCH),
    int(CardId.SACRED_ASH): int(SelectContext.TO_DECK),
    int(CardId.LANAS_AID): int(SelectContext.TO_HAND),
    int(CardId.HILDA): int(SelectContext.TO_HAND),
    int(CardId.DAWN): int(SelectContext.TO_HAND),
}
_MULTI_SCREEN_GROUP_EFFECTS = {int(CardId.HILDA), int(CardId.DAWN)}
_INTENT_PRIORITY = 1100


def _serial_key(option: LegalOption) -> int:
    return 10**18 if option.card_serial is None else int(option.card_serial)


def _option_identity(option: LegalOption) -> tuple[str, int]:
    if option.card_serial is not None:
        return ("serial", int(option.card_serial))
    return ("position", int(option.position))


def _available(
    options: Iterable[LegalOption],
    used_positions: set[int],
    used_cards: set[tuple[str, int]],
) -> tuple[LegalOption, ...]:
    return tuple(
        option
        for option in options
        if option.position not in used_positions
        and _option_identity(option) not in used_cards
    )


def _choose_one_for_group(
    options: Sequence[LegalOption],
    group: Sequence[int],
    used_positions: set[int],
    used_cards: set[tuple[str, int]],
) -> LegalOption | None:
    available = _available(options, used_positions, used_cards)
    for card_id in group:
        matching = [
            option
            for option in available
            if option.card_id is not None and int(option.card_id) == int(card_id)
        ]
        if matching:
            return min(matching, key=lambda option: (_serial_key(option), option.position))
    return None


def _remember_choice(
    option: LegalOption,
    chosen: list[int],
    used_positions: set[int],
    used_cards: set[tuple[str, int]],
) -> None:
    chosen.append(option.position)
    used_positions.add(option.position)
    used_cards.add(_option_identity(option))


def _choose_grouped(
    options: Sequence[LegalOption],
    groups: Sequence[Sequence[int]],
    limit: int,
) -> tuple[int, ...]:
    chosen: list[int] = []
    used_positions: set[int] = set()
    used_cards: set[tuple[str, int]] = set()
    for group in groups:
        if len(chosen) >= limit:
            break
        option = _choose_one_for_group(
            options, group, used_positions, used_cards
        )
        if option is not None:
            _remember_choice(option, chosen, used_positions, used_cards)
    return tuple(chosen)


def _choose_by_card_priority(
    options: Sequence[LegalOption],
    card_ids: Sequence[int],
    limit: int,
) -> tuple[int, ...]:
    if limit <= 0:
        return ()
    rank = {int(card_id): position for position, card_id in enumerate(card_ids)}
    candidates = [
        option
        for option in options
        if option.card_id is not None
        and (not rank or int(option.card_id) in rank)
    ]
    candidates.sort(
        key=lambda option: (
            rank.get(int(option.card_id), len(rank)),
            _serial_key(option),
            option.position,
        )
    )
    chosen: list[int] = []
    used_positions: set[int] = set()
    used_cards: set[tuple[str, int]] = set()
    for option in candidates:
        if len(chosen) >= limit:
            break
        if (
            option.position in used_positions
            or _option_identity(option) in used_cards
        ):
            continue
        _remember_choice(option, chosen, used_positions, used_cards)
    return tuple(chosen)


def _limit(view, intent: PendingIntent) -> int:
    view_maximum = max(0, int(view.select.get("maxCount", 0)))
    if intent.max_cards is None:
        return view_maximum
    return min(view_maximum, max(0, int(intent.max_cards)))


def _rule_ids(effect_card_id: int) -> tuple[str, ...]:
    extra = {
        int(CardId.RARE_CANDY): "PLAYBOOK-RARE-CANDY",
        int(CardId.ENHANCED_HAMMER): "PLAYBOOK-ENHANCED-HAMMER",
        int(CardId.BOSSES_ORDERS): "PLAYBOOK-BOSS",
        int(CardId.SACRED_ASH): "PLAYBOOK-SACRED-ASH",
        int(CardId.LANAS_AID): "PLAYBOOK-LANAS-AID",
        int(CardId.HILDA): "PLAYBOOK-HILDA",
        int(CardId.DAWN): "PLAYBOOK-DAWN",
    }.get(effect_card_id)
    return (
        ("PLAYBOOK-SEARCH-INTENT",)
        if extra is None
        else ("PLAYBOOK-SEARCH-INTENT", extra)
    )


def _intent_proposal(
    view,
    intent: PendingIntent,
    chosen: tuple[int, ...],
    effect_card_id: int,
) -> Proposal:
    next_intent = intent.advance(view)
    reason = f"記録済み意図 {intent.kind} と一致するカードだけを選ぶ"
    if next_intent is not None:
        return Proposal(
            chosen,
            _INTENT_PRIORITY,
            reason,
            _rule_ids(effect_card_id),
            next_intent=next_intent,
        )
    return Proposal(
        chosen,
        _INTENT_PRIORITY,
        reason,
        _rule_ids(effect_card_id),
        intent_update=IntentUpdate.CLEAR,
    )


def _current_groups(
    intent: PendingIntent, effect_card_id: int
) -> tuple[tuple[int, ...], ...] | None:
    if effect_card_id not in _MULTI_SCREEN_GROUP_EFFECTS:
        return intent.card_groups
    group_index = len(intent.card_groups) - len(intent.remaining_contexts)
    if group_index < 0 or group_index >= len(intent.card_groups):
        return None
    return (intent.card_groups[group_index],)


def _deduplicate_groups(
    groups: Sequence[Sequence[int]],
) -> tuple[tuple[int, ...], ...]:
    result: list[tuple[int, ...]] = []
    seen: set[tuple[int, ...]] = set()
    for group in groups:
        normalized = tuple(int(card_id) for card_id in group)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return tuple(result)


def _poke_pad_groups(
    view,
    intent: PendingIntent,
    current_groups: tuple[tuple[int, ...], ...],
) -> tuple[tuple[int, ...], ...]:
    recorded = current_groups
    if not recorded and intent.card_ids:
        recorded = (tuple(int(card_id) for card_id in intent.card_ids),)
    replanned = tuple(
        plan.card_ids for plan in plan_poke_pad_targets(view)
    )
    return _deduplicate_groups((*recorded, *replanned))


def _resolve_card_selection(
    view,
    intent: PendingIntent,
    effect_card_id: int,
) -> Proposal | None:
    if (
        int(view.select.get("type", -1)) != int(SelectType.CARD)
        or int(view.select.get("context", -1))
        != _CARD_PROMPT_CONTEXTS[effect_card_id]
    ):
        return None
    options = tuple(
        option
        for option in view.options
        if option.type == int(OptionType.CARD)
    )
    limit = _limit(view, intent)
    groups = _current_groups(intent, effect_card_id)
    if groups is None:
        return None
    if effect_card_id == int(CardId.POKE_PAD):
        groups = _poke_pad_groups(view, intent, groups)
    chosen = (
        _choose_grouped(options, groups, limit)
        if groups
        else _choose_by_card_priority(options, intent.card_ids, limit)
    )
    if len(chosen) < int(view.select.get("minCount", 0)):
        return None
    return _intent_proposal(view, intent, chosen, effect_card_id)


def _resolve_rare_candy(view, intent: PendingIntent) -> Proposal | None:
    if (
        int(view.select.get("type", -1)) != int(SelectType.EVOLVE)
        or int(view.select.get("context", -1)) != int(SelectContext.EVOLVE)
        or intent.target_serial is None
    ):
        return None
    candidates = [
        option
        for option in view.options
        if option.type == int(OptionType.EVOLVE)
        and option.card_id is not None
        and int(option.card_id) == int(CardId.ALAKAZAM)
        and (not intent.card_ids or int(option.card_id) in intent.card_ids)
        and option.target is not None
        and option.target.serial == int(intent.target_serial)
    ]
    if not candidates:
        return None
    chosen = min(candidates, key=lambda option: (_serial_key(option), option.position))
    return _intent_proposal(
        view, intent, (chosen.position,), int(CardId.RARE_CANDY)
    )


def _resolve_boss(view, intent: PendingIntent) -> Proposal | None:
    if (
        int(view.select.get("type", -1)) != int(SelectType.CARD)
        or int(view.select.get("context", -1)) != int(SelectContext.SWITCH)
        or intent.target_serial is None
    ):
        return None
    candidates = [
        option
        for option in view.options
        if option.type == int(OptionType.CARD)
        and option.source is not None
        and option.source.serial == int(intent.target_serial)
        and (
            not intent.card_ids
            or (
                option.card_id is not None
                and int(option.card_id) in intent.card_ids
            )
        )
    ]
    if not candidates:
        return None
    chosen = min(candidates, key=lambda option: (_serial_key(option), option.position))
    return _intent_proposal(
        view, intent, (chosen.position,), int(CardId.BOSSES_ORDERS)
    )


def _metadata_int(intent: PendingIntent, key: str) -> int | None:
    for name, value in intent.metadata:
        if name == key:
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
    return None


def _resolve_hammer(view, intent: PendingIntent) -> Proposal | None:
    energy_serial = _metadata_int(intent, "energy_serial")
    if (
        int(view.select.get("type", -1)) != int(SelectType.ENERGY)
        or int(view.select.get("context", -1))
        != int(SelectContext.DISCARD_ENERGY)
        or intent.target_serial is None
        or energy_serial is None
        or not intent.card_ids
    ):
        return None
    candidates = [
        option
        for option in view.options
        if option.type == int(OptionType.ENERGY)
        and option.source is not None
        and option.source.serial == int(intent.target_serial)
        and option.card_id is not None
        and int(option.card_id) in intent.card_ids
        and option.card_serial == energy_serial
    ]
    if not candidates:
        return None
    chosen = min(candidates, key=lambda option: option.position)
    return _intent_proposal(
        view, intent, (chosen.position,), int(CardId.ENHANCED_HAMMER)
    )


def _resolve_retreat_cost(view) -> Proposal | None:
    if (
        int(view.select.get("type", -1)) != int(SelectType.ENERGY)
        or int(view.select.get("context", -1))
        != int(SelectContext.DISCARD_ENERGY)
        or view.select.get("effect") is not None
    ):
        return None
    minimum = max(0, int(view.select.get("minCount", 0)))
    maximum = max(0, int(view.select.get("maxCount", 0)))
    candidates = sorted(
        (
            option
            for option in view.options
            if option.type == int(OptionType.ENERGY)
            and option.card_id is not None
        ),
        key=lambda option: (
            int(option.card_id) == int(CardId.ENRICHING_ENERGY),
            int(option.card_id),
            _serial_key(option),
            option.position,
        ),
    )
    chosen: list[int] = []
    used_cards: set[tuple[str, int]] = set()
    for option in candidates:
        if len(chosen) >= minimum or len(chosen) >= maximum:
            break
        identity = _option_identity(option)
        if identity in used_cards:
            continue
        chosen.append(option.position)
        used_cards.add(identity)
    if len(chosen) < minimum:
        return None
    only_rich = bool(chosen) and all(
        view.options[position].card_id == int(CardId.ENRICHING_ENERGY)
        for position in chosen
    )
    reason = (
        "にげるコストにリッチエネルギーしかなく、MAINでにげるを開始すべきではなかったが必須選択として払う"
        if only_rich
        else "にげるコストはリッチエネルギーを温存し、非リッチを優先して払う"
    )
    return Proposal(
        tuple(chosen),
        _INTENT_PRIORITY,
        reason,
        ("PLAYBOOK-NO-ENRICHING-RETREAT",),
    )


def _resolve_effectless_promotion(view) -> Proposal | None:
    if (
        int(view.select.get("type", -1)) != int(SelectType.CARD)
        or int(view.select.get("context", -1)) not in (
            int(SelectContext.TO_ACTIVE),
            int(SelectContext.SWITCH),
        )
        or view.select.get("effect") is not None
    ):
        return None
    candidates = tuple(
        option
        for option in view.options
        if option.type == int(OptionType.CARD)
        and option.source is not None
        and int(option.source.id) == int(CardId.ALAKAZAM)
        and view.has_psychic_energy(option.source)
    )
    if not candidates:
        return None
    option = min(
        candidates,
        key=lambda candidate: (
            10**18
            if candidate.source is None or candidate.source.serial is None
            else int(candidate.source.serial),
            candidate.position,
        ),
    )
    return Proposal(
        (option.position,),
        _INTENT_PRIORITY,
        "超エネルギー付きフーディンをバトル場へ出す",
        ("PLAYBOOK-PROMOTE-COMPLETE",),
    )


@covers(
    "PLAYBOOK-SEARCH-INTENT",
    "PLAYBOOK-DAWN",
    "PLAYBOOK-HILDA",
    "PLAYBOOK-RARE-CANDY",
    "PLAYBOOK-ENHANCED-HAMMER",
    "PLAYBOOK-BOSS",
    "PLAYBOOK-SACRED-ASH",
    "PLAYBOOK-LANAS-AID",
    "PLAYBOOK-NO-ENRICHING-RETREAT",
    "PLAYBOOK-PROMOTE-COMPLETE",
)
def resolve_prompt(view, memory) -> Proposal | None:
    """Resolve only a complete, matching card-effect intent or a retreat cost."""
    effect = view.select.get("effect")
    context = int(view.select.get("context", -1))
    promotion = _resolve_effectless_promotion(view)
    if promotion is not None:
        return promotion
    if effect is None and context == int(SelectContext.DISCARD_ENERGY):
        return _resolve_retreat_cost(view)

    intent = memory.pending_intent
    if intent is None or not intent.matches(view):
        return None
    if not isinstance(effect, dict) or effect.get("id") is None:
        return None
    effect_card_id = int(effect["id"])
    if effect_card_id in _CARD_PROMPT_CONTEXTS:
        return _resolve_card_selection(view, intent, effect_card_id)
    if effect_card_id == int(CardId.RARE_CANDY):
        return _resolve_rare_candy(view, intent)
    if effect_card_id == int(CardId.BOSSES_ORDERS):
        return _resolve_boss(view, intent)
    if effect_card_id == int(CardId.ENHANCED_HAMMER):
        return _resolve_hammer(view, intent)
    return None
