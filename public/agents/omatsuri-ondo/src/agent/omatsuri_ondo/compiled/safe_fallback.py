from __future__ import annotations

from common_strategy import GameView, LegalOption, OptionType, SelectContext, SelectType

from ..cards import AttackId, CardId


def fixed_safe_fallback(view: GameView) -> tuple[int, ...]:
    """Return one deterministic legal selection without strategy search."""
    minimum = max(0, int(view.select.get("minCount", 0)))
    maximum = max(0, int(view.select.get("maxCount", len(view.options))))
    if int(view.select.get("type", -1)) != int(SelectType.MAIN):
        if minimum == 0:
            return ()
        ordered = tuple(sorted(view.options, key=lambda option: _prompt_key(view, option)))
        count = min(len(ordered), max(minimum, min(maximum, minimum)))
        return tuple(int(option.position) for option in ordered[:count])

    for attack_id in (
        AttackId.DIPPLIN_DO_THE_WAVE,
        AttackId.BUDEW_ITTY_BITTY_POLLEN,
    ):
        selected = _first(view, lambda option: (
            int(option.type) == int(OptionType.ATTACK)
            and option.attack_id == int(attack_id)
        ))
        if selected is not None:
            return selected

    for option_type, card_ids in (
        (OptionType.EVOLVE, (CardId.DIPPLIN, CardId.THWACKEY, CardId.SEAKING)),
        (OptionType.ATTACH, (CardId.BASIC_GRASS, CardId.BRAVE_BANGLE, CardId.AIR_BALLOON)),
        (OptionType.ABILITY, (CardId.THWACKEY,)),
        (
            OptionType.PLAY,
            (
                CardId.FESTIVAL_GROUNDS,
                CardId.APPLIN,
                CardId.GROOKEY,
                CardId.BUDEW,
            ),
        ),
    ):
        for card_id in card_ids:
            selected = _first(view, lambda option, expected=card_id: (
                int(option.type) == int(option_type)
                and option.card_id == int(expected)
            ))
            if selected is not None:
                return selected
    selected = _first(
        view,
        lambda option: int(option.type) == int(OptionType.END),
    )
    if selected is not None:
        return selected
    return () if minimum == 0 else tuple(
        int(option.position)
        for option in sorted(view.options, key=lambda option: option.position)[:minimum]
    )


def _first(
    view: GameView,
    predicate,
) -> tuple[int, ...] | None:
    candidates = tuple(
        option
        for option in sorted(view.options, key=lambda value: value.position)
        if predicate(option)
    )
    return None if not candidates else (int(candidates[0].position),)


def _prompt_key(view: GameView, option: LegalOption) -> tuple[int, int, int]:
    card_id = 0 if option.card_id is None else int(option.card_id)
    context = int(view.select.get("context", -1))
    if context == int(SelectContext.SETUP_ACTIVE_POKEMON):
        order = (
            CardId.BUDEW,
            CardId.GOLDEEN,
            CardId.APPLIN,
            CardId.GROOKEY,
            CardId.PSYDUCK,
            CardId.SHAYMIN,
        )
    elif context in (int(SelectContext.TO_ACTIVE), int(SelectContext.SWITCH)):
        order = (
            CardId.DIPPLIN,
            CardId.APPLIN,
            CardId.BUDEW,
            CardId.GROOKEY,
            CardId.GOLDEEN,
            CardId.PSYDUCK,
            CardId.SHAYMIN,
            CardId.THWACKEY,
        )
    else:
        order = ()
    try:
        rank = order.index(CardId(card_id))
    except (ValueError, TypeError):
        rank = len(order)
    serial = (
        2**31 - 1
        if option.source is None or option.source.serial is None
        else int(option.source.serial)
    )
    return rank, serial, int(option.position)
