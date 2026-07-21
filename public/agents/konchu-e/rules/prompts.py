from __future__ import annotations

from collections.abc import Iterable, Sequence

from cards import CardId
from model import LegalOption, OptionType, SelectContext, SelectType
from proposals import IntentUpdate, PendingIntent, Proposal, covers
from rules.board_plan import opening_abra_survival_pivot
from rules.deck_safety import max_safe_deck_removals
from rules.disruption import choose_xerosic_discard
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
    int(CardId.TEAM_ROCKETS_PETREL): int(SelectContext.TO_HAND),
    int(CardId.NIGHT_STRETCHER): int(SelectContext.TO_HAND),
}
_MULTI_SCREEN_GROUP_EFFECTS = {int(CardId.HILDA), int(CardId.DAWN)}
_DECK_SEARCH_EFFECT_IDS = frozenset({
    int(CardId.BUDDY_BUDDY_POFFIN),
    int(CardId.POKE_PAD),
    int(CardId.FAN_ROTOM),
    int(CardId.TELEPATH_PSYCHIC_ENERGY),
    int(CardId.HILDA),
    int(CardId.DAWN),
    int(CardId.TEAM_ROCKETS_PETREL),
})
_ATTACK_PSYCHIC_IDS = frozenset({
    int(CardId.BASIC_PSYCHIC),
    int(CardId.TELEPATH_PSYCHIC_ENERGY),
})
_INTENT_PRIORITY = 1100
_RAW_CONTEXT_IDENTITY_FIELDS = (
    "area",
    "playerIndex",
)
_RAW_ENTITY_IDENTITY_FIELDS = (
    "index",
    "inPlayArea",
    "inPlayIndex",
    "energyIndex",
    "toolIndex",
)
_OptionIdentity = tuple[str, tuple[tuple[str, int], ...]]


def _serial_key(option: LegalOption) -> int:
    return 10**18 if option.card_serial is None else int(option.card_serial)


def _raw_index_key(option: LegalOption) -> int:
    value = option.raw.get("index")
    return int(option.position) if value is None else int(value)


def _option_identity(option: LegalOption) -> _OptionIdentity:
    if option.card_serial is not None:
        return ("serial", (("serial", int(option.card_serial)),))
    entity_identity = tuple(
        (field, int(option.raw[field]))
        for field in _RAW_ENTITY_IDENTITY_FIELDS
        if option.raw.get(field) is not None
    )
    if not entity_identity:
        return (
            "position",
            (("position", int(option.position)),),
        )
    context_identity = tuple(
        (field, int(option.raw[field]))
        for field in _RAW_CONTEXT_IDENTITY_FIELDS
        if option.raw.get(field) is not None
    )
    return ("raw", (*context_identity, *entity_identity))


def _available(
    options: Iterable[LegalOption],
    used_positions: set[int],
    used_cards: set[_OptionIdentity],
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
    used_cards: set[_OptionIdentity],
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


def _choose_one_for_serial_tie(
    options: Sequence[LegalOption],
    group: Sequence[int],
    used_positions: set[int],
    used_cards: set[_OptionIdentity],
) -> LegalOption | None:
    card_ids = frozenset(int(card_id) for card_id in group)
    matching = [
        option
        for option in _available(options, used_positions, used_cards)
        if option.card_id is not None and int(option.card_id) in card_ids
    ]
    if not matching:
        return None
    return min(
        matching,
        key=lambda option: (
            _serial_key(option),
            _raw_index_key(option),
            option.position,
        ),
    )


def _remember_choice(
    option: LegalOption,
    chosen: list[int],
    used_positions: set[int],
    used_cards: set[_OptionIdentity],
) -> None:
    chosen.append(option.position)
    used_positions.add(option.position)
    used_cards.add(_option_identity(option))


def _choose_grouped(
    options: Sequence[LegalOption],
    groups: Sequence[Sequence[int]],
    limit: int,
    serial_tie_groups: frozenset[int] = frozenset(),
) -> tuple[int, ...]:
    chosen: list[int] = []
    used_positions: set[int] = set()
    used_cards: set[_OptionIdentity] = set()
    for group_index, group in enumerate(groups):
        if len(chosen) >= limit:
            break
        option = (
            _choose_one_for_serial_tie(
                options,
                group,
                used_positions,
                used_cards,
            )
            if group_index in serial_tie_groups
            else _choose_one_for_group(
                options,
                group,
                used_positions,
                used_cards,
            )
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
    used_cards: set[_OptionIdentity] = set()
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


def _is_final_ko_energy_screen(view, intent: PendingIntent) -> bool:
    if not any(
        name == "final_ko_energy_search" and bool(value)
        for name, value in intent.metadata
    ):
        return False
    if not intent.card_groups:
        return False
    current_index = len(intent.card_groups) - len(intent.remaining_contexts)
    if current_index < 0 or current_index >= len(intent.card_groups):
        return False
    option_ids = {
        int(option.card_id)
        for option in view.options
        if option.card_id is not None
    }
    group = intent.card_groups[current_index]
    if option_ids and not option_ids.intersection(group):
        for later_group in intent.card_groups[current_index + 1 :]:
            if option_ids.intersection(later_group):
                group = later_group
                break
    return bool(set(int(card_id) for card_id in group) & _ATTACK_PSYCHIC_IDS)


def _limit(view, intent: PendingIntent) -> int:
    view_maximum = max(0, int(view.select.get("maxCount", 0)))
    intent_maximum = (
        view_maximum
        if intent.max_cards is None
        else min(view_maximum, max(0, int(intent.max_cards)))
    )
    if int(intent.effect_card_id or -1) not in _DECK_SEARCH_EFFECT_IDS:
        return intent_maximum
    final_ko_energy_search = any(
        name == "final_ko_energy_search" and bool(value)
        for name, value in intent.metadata
    )
    if final_ko_energy_search:
        return (
            intent_maximum
            if _is_final_ko_energy_screen(view, intent)
            else 0
        )
    cards_to_hand = (
        int(view.select.get("context", -1))
        == int(SelectContext.TO_HAND)
    )
    return max_safe_deck_removals(
        view,
        requested=intent_maximum,
        cards_to_hand=cards_to_hand,
    )


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
    *,
    advance_steps: int = 1,
) -> Proposal:
    next_intent = intent.advance(view, advance_steps)
    reason = f"記録済み意図 {intent.kind} と一致するカードだけを選ぶ"
    if next_intent is not None:
        return Proposal(
            chosen,
            _INTENT_PRIORITY,
            reason,
            _rule_ids(effect_card_id),
            next_intent=next_intent,
            intent_advance_steps=advance_steps,
        )
    return Proposal(
        chosen,
        _INTENT_PRIORITY,
        reason,
        _rule_ids(effect_card_id),
        intent_update=IntentUpdate.CLEAR,
        intent_advance_steps=advance_steps,
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


def _serial_tie_group_indices(intent: PendingIntent) -> frozenset[int]:
    raw_indices = next(
        (
            str(value)
            for name, value in intent.metadata
            if name == "serial_tie_groups"
        ),
        "",
    )
    indices = set()
    for value in raw_indices.split(","):
        try:
            index = int(value)
        except ValueError:
            continue
        if index >= 0:
            indices.add(index)
    return frozenset(indices)


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
    advance_steps = 1
    if effect_card_id in _MULTI_SCREEN_GROUP_EFFECTS and groups:
        current_index = len(intent.card_groups) - len(intent.remaining_contexts)
        option_ids = {
            int(option.card_id)
            for option in options
            if option.card_id is not None
        }
        if not option_ids.intersection(groups[0]):
            for later_index in range(current_index + 1, len(intent.card_groups)):
                later_group = intent.card_groups[later_index]
                if option_ids.intersection(later_group):
                    groups = (later_group,)
                    advance_steps = later_index - current_index + 1
                    break
    if effect_card_id == int(CardId.POKE_PAD):
        groups = _poke_pad_groups(view, intent, groups)
    chosen = (
        _choose_grouped(
            options,
            groups,
            limit,
            serial_tie_groups=(
                _serial_tie_group_indices(intent)
                if effect_card_id == int(CardId.BUDDY_BUDDY_POFFIN)
                else frozenset()
            ),
        )
        if groups
        else _choose_by_card_priority(options, intent.card_ids, limit)
    )
    if len(chosen) < int(view.select.get("minCount", 0)):
        return None
    return _intent_proposal(
        view,
        intent,
        chosen,
        effect_card_id,
        advance_steps=advance_steps,
    )


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


def _resolve_teleport_wall(view, intent: PendingIntent) -> Proposal | None:
    if (
        intent.kind != "TELEPORT_ATTACK_WALL"
        or not intent.matches(view)
        or int(view.select.get("type", -1)) != int(SelectType.CARD)
        or int(view.select.get("context", -1)) != int(SelectContext.SWITCH)
        or intent.target_serial is None
    ):
        return None
    candidates = tuple(
        option
        for option in view.options
        if option.type == int(OptionType.CARD)
        and option.source is not None
        and option.source.serial == int(intent.target_serial)
        and (
            not intent.card_ids
            or int(option.source.id) in {int(card_id) for card_id in intent.card_ids}
        )
    )
    if not candidates:
        return None
    chosen = min(candidates, key=lambda option: option.position)
    return Proposal(
        (chosen.position,),
        _INTENT_PRIORITY,
        "テレポートアタックで記録した次番価値の低い個体を壁として前へ出す",
        (
            "PLAYBOOK-TELEPORT-ATTACK",
            "PLAYBOOK-PRESERVE-ABRA",
        ),
        intent_update=IntentUpdate.CLEAR,
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
    used_cards: set[_OptionIdentity] = set()
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


def _resolve_effectless_promotion(
    view,
    intent: PendingIntent | None = None,
) -> Proposal | None:
    if (
        int(view.select.get("type", -1)) != int(SelectType.CARD)
        or int(view.select.get("context", -1)) not in (
            int(SelectContext.TO_ACTIVE),
            int(SelectContext.SWITCH),
        )
        or view.select.get("effect") is not None
    ):
        return None
    if (
        intent is not None
        and intent.kind == "SURVIVAL_RETREAT"
        and intent.target_serial is not None
    ):
        target_candidates = tuple(
            option
            for option in view.options
            if option.type == int(OptionType.CARD)
            and option.source is not None
            and option.source.serial == int(intent.target_serial)
        )
        if target_candidates:
            option = min(target_candidates, key=lambda candidate: candidate.position)
            return Proposal(
                (option.position,),
                _INTENT_PRIORITY,
                "相手の公開済み攻撃で失うサイドを減らす退避先を選ぶ",
                ("PLAYBOOK-PROMOTE-COMPLETE", "PLAYBOOK-PRESERVE-ABRA"),
                intent_update=IntentUpdate.CLEAR,
            )

    candidates = tuple(
        option
        for option in view.options
        if option.type == int(OptionType.CARD)
        and option.source is not None
        and int(option.source.id) == int(CardId.ALAKAZAM)
        and view.has_psychic_energy(option.source)
    )
    reason = "超エネルギー付きフーディンをバトル場へ出す"
    rule_ids = ("PLAYBOOK-PROMOTE-COMPLETE",)
    if not candidates:
        pivot = opening_abra_survival_pivot(view)
        if (
            int(view.select.get("context", -1)) != int(SelectContext.SWITCH)
            or pivot is None
            or pivot.serial is None
        ):
            return None
        candidates = tuple(
            option
            for option in view.options
            if option.type == int(OptionType.CARD)
            and option.source is not None
            and option.source.serial == pivot.serial
        )
        if not candidates:
            return None
        reason = "唯一のケーシィを守るため退避役をバトル場へ出す"
        rule_ids = (
            "PLAYBOOK-PRESERVE-ABRA",
            "PLAYBOOK-AIR-BALLOON",
        )
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
        reason,
        rule_ids,
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
    "PLAYBOOK-PRESERVE-ABRA",
    "PLAYBOOK-AIR-BALLOON",
    "PLAYBOOK-XEROSIC-KEEP",
    "PLAYBOOK-TELEPORT-ATTACK",
)
def resolve_prompt(view, memory) -> Proposal | None:
    """Resolve only a complete, matching card-effect intent or a retreat cost."""
    xerosic = choose_xerosic_discard(view, memory)
    if xerosic is not None:
        return xerosic
    effect = view.select.get("effect")
    context = int(view.select.get("context", -1))
    intent = memory.pending_intent
    if intent is not None:
        teleport = _resolve_teleport_wall(view, intent)
        if teleport is not None:
            return teleport
    promotion = _resolve_effectless_promotion(view, intent)
    if promotion is not None:
        return promotion
    if effect is None and context == int(SelectContext.DISCARD_ENERGY):
        return _resolve_retreat_cost(view)

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
