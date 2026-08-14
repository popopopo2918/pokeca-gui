from __future__ import annotations

from collections.abc import Callable

from common_strategy import (
    GameView,
    LegalOption,
    OptionType,
    SelectContext,
    SelectType,
)

from .boss_patterns import lookup_boss_pattern
from .features import RoleAssignment
from .schema import (
    ActionKind,
    ActionSpec,
    KO_CHAIN_SELECT_ONE_REASON_CODE,
    KO_CHAIN_SELECT_TWO_REASON_CODE,
    PokemonRole,
    TargetRule,
)
from ..cards import CardId


Selection = tuple[int, ...]
Selector = Callable[[GameView, ActionSpec, RoleAssignment], Selection | None]


def select_action(
    view: GameView,
    action: ActionSpec,
    roles: RoleAssignment,
) -> Selection | None:
    selector = _SELECTORS.get(action.kind)
    return None if selector is None else selector(view, action, roles)


def _select_play(
    view: GameView,
    action: ActionSpec,
    roles: RoleAssignment,
) -> Selection | None:
    del roles
    return _one(_matching_options(
        view,
        option_type=OptionType.PLAY,
        card_id=action.source_card_id,
    ))


def _select_evolve_or_attach(
    view: GameView,
    action: ActionSpec,
    roles: RoleAssignment,
) -> Selection | None:
    option_type = (
        OptionType.EVOLVE
        if action.kind is ActionKind.EVOLVE
        else OptionType.ATTACH
    )
    target_serial = _role_serial(roles, action.target_role)
    candidates = _matching_options(
        view,
        option_type=option_type,
        card_id=action.source_card_id,
    )
    if action.target_role is not PokemonRole.NONE:
        candidates = tuple(
            option
            for option in candidates
            if option.target is not None
            and option.target.serial == target_serial
        )
    return _one(candidates)


def _select_attach_tool(
    view: GameView,
    action: ActionSpec,
    roles: RoleAssignment,
) -> Selection | None:
    target_serial = _role_serial(roles, action.target_role)
    candidates = tuple(
        option
        for option in sorted(view.options, key=_semantic_option_key)
        if option.card_id == int(action.source_card_id)
        and int(option.type) in (int(OptionType.PLAY), int(OptionType.ATTACH))
        and (
            action.target_role is PokemonRole.NONE
            or option.target is None
            or option.target.serial == target_serial
        )
    )
    direct = tuple(option for option in candidates if option.target is not None)
    return _one(direct or candidates)


def _select_ability(
    view: GameView,
    action: ActionSpec,
    roles: RoleAssignment,
) -> Selection | None:
    source_serial = _role_serial(roles, action.source_role)
    candidates = _matching_options(
        view,
        option_type=OptionType.ABILITY,
        card_id=action.source_card_id,
    )
    if action.source_role is not PokemonRole.NONE:
        candidates = tuple(
            option
            for option in candidates
            if option.source is not None
            and option.source.serial == source_serial
        )
    return _one(candidates)


def _select_retreat(
    view: GameView,
    action: ActionSpec,
    roles: RoleAssignment,
) -> Selection | None:
    source_serial = _role_serial(roles, action.source_role)
    candidates = _matching_options(view, option_type=OptionType.RETREAT)
    if action.source_role is not PokemonRole.NONE:
        candidates = tuple(
            option
            for option in candidates
            if (
                option.source is not None
                and option.source.serial == source_serial
                or option.source is None
                and view.own_active is not None
                and view.own_active.serial == source_serial
            )
        )
    return _one(candidates)


def _select_attack(
    view: GameView,
    action: ActionSpec,
    roles: RoleAssignment,
) -> Selection | None:
    source_serial = _role_serial(roles, action.source_role)
    candidates = tuple(
        option
        for option in _matching_options(view, option_type=OptionType.ATTACK)
        if option.attack_id == int(action.attack_id)
    )
    if action.source_role is not PokemonRole.NONE:
        candidates = tuple(
            option
            for option in candidates
            if (
                option.source is not None
                and option.source.serial == source_serial
                or option.source is None
                and view.own_active is not None
                and view.own_active.serial == source_serial
            )
        )
    return _one(candidates)


def _select_cards(
    view: GameView,
    action: ActionSpec,
    roles: RoleAssignment,
) -> Selection | None:
    del roles
    candidates_by_id: dict[int, list[LegalOption]] = {}
    for option in sorted(view.options, key=lambda value: value.position):
        if option.card_id is None:
            continue
        candidates_by_id.setdefault(int(option.card_id), []).append(option)

    chain_selection_limit = {
        int(KO_CHAIN_SELECT_ONE_REASON_CODE): 1,
        int(KO_CHAIN_SELECT_TWO_REASON_CODE): 2,
    }.get(int(action.reason_code))
    maximum_selection = _maximum_selection(view)
    if chain_selection_limit is not None:
        maximum_selection = min(maximum_selection, chain_selection_limit)
    preserve_reserve = chain_selection_limit is None

    selected: list[int] = []
    selected_card_ids: list[int] = []
    selected_positions: set[int] = set()
    for card_id in action.card_ids:
        matches = candidates_by_id.get(int(card_id), [])
        if not matches:
            continue
        option = matches.pop(0)
        if preserve_reserve and not preserves_core_bench_reserve(
            view,
            selected_card_ids=selected_card_ids,
            candidate_card_id=int(card_id),
        ):
            continue
        position = int(option.position)
        selected.append(position)
        selected_card_ids.append(int(card_id))
        selected_positions.add(position)
        if len(selected) >= maximum_selection:
            break
    if not selected and action.kind is not ActionKind.SELECT_CARDS_FILL:
        return None
    if action.kind is ActionKind.SELECT_CARDS_FILL:
        for option in sorted(view.options, key=_semantic_option_key):
            if len(selected) >= maximum_selection:
                break
            if int(option.position) in selected_positions:
                continue
            if (
                preserve_reserve
                and option.card_id is not None
                and not preserves_core_bench_reserve(
                    view,
                    selected_card_ids=selected_card_ids,
                    candidate_card_id=int(option.card_id),
                )
            ):
                continue
            selected.append(int(option.position))
            if option.card_id is not None:
                selected_card_ids.append(int(option.card_id))
            selected_positions.add(int(option.position))
    if len(selected) < _minimum_selection(view):
        return None
    return tuple(selected)


def _select_first(
    view: GameView,
    action: ActionSpec,
    roles: RoleAssignment,
) -> Selection | None:
    del action, roles
    minimum = _minimum_selection(view)
    if len(view.options) < minimum:
        return None
    count = max(1, minimum) if view.options else 0
    return tuple(
        int(option.position)
        for option in sorted(view.options, key=_semantic_option_key)[:count]
    )


def _select_none(
    view: GameView,
    action: ActionSpec,
    roles: RoleAssignment,
) -> Selection | None:
    del action, roles
    return () if _minimum_selection(view) == 0 else None


def _select_yes_or_no(
    view: GameView,
    action: ActionSpec,
    roles: RoleAssignment,
) -> Selection | None:
    del roles
    option_type = (
        OptionType.YES if action.kind is ActionKind.CHOOSE_YES else OptionType.NO
    )
    selected = _one(_matching_options(view, option_type=option_type))
    if selected is not None:
        return selected
    return None


def _select_pokemon(
    view: GameView,
    action: ActionSpec,
    roles: RoleAssignment,
) -> Selection | None:
    if action.target_role is not PokemonRole.NONE:
        target_serial = _role_serial(roles, action.target_role)
        for option in view.options:
            if option.source is not None and option.source.serial == target_serial:
                return (int(option.position),)
        return None
    if action.target_rule is TargetRule.FLOWCHART_BOSS:
        pattern = lookup_boss_pattern(view)
        if pattern is not None:
            for option in view.options:
                if (
                    option.source is not None
                    and option.source.serial == pattern.target_serial
                ):
                    return (int(option.position),)
        return None
    return None


def _select_end(
    view: GameView,
    action: ActionSpec,
    roles: RoleAssignment,
) -> Selection | None:
    del action, roles
    return _one(_matching_options(view, option_type=OptionType.END))


def _matching_options(
    view: GameView,
    *,
    option_type: OptionType,
    card_id: int = 0,
) -> tuple[LegalOption, ...]:
    return tuple(
        sorted(
            (
                option
                for option in view.options
                if int(option.type) == int(option_type)
                and (card_id <= 0 or option.card_id == int(card_id))
            ),
            key=lambda option: option.position,
        )
    )


def _one(candidates: tuple[LegalOption, ...]) -> Selection | None:
    return None if not candidates else (int(candidates[0].position),)


def _role_serial(
    roles: RoleAssignment,
    role: PokemonRole,
) -> int | None:
    return None if role is PokemonRole.NONE else roles.serial_for(role)


def _minimum_selection(view: GameView) -> int:
    return max(0, int(view.select.get("minCount", 0)))


def _maximum_selection(view: GameView) -> int:
    maximum = max(0, int(view.select.get("maxCount", len(view.options))))
    return min(maximum, len(view.options))


def preserves_core_bench_reserve(
    view: GameView,
    *,
    selected_card_ids: list[int],
    candidate_card_id: int,
) -> bool:
    """Keep slots for the core and a structurally reachable third attacker.

    The two-by-two board remains the unconditional minimum.  During an
    in-game Bench search, if the current open slots can still hold three
    Dipplin-family lines plus two Thwackey-family lines, optional duplicates
    may not consume that third-attacker slot.  Card availability is resolved
    by the later fixed search/recovery rows; this selector only preserves the
    physical slot they need.
    """

    if int(view.select.get("context", -1)) not in (
        int(SelectContext.TO_BENCH),
        int(SelectContext.SETUP_BENCH_POKEMON),
    ):
        return True
    field_dipplin_lines = sum(
        pokemon.id in (int(CardId.APPLIN), int(CardId.DIPPLIN))
        for pokemon in view.own_field
    )
    field_thwackey_lines = sum(
        pokemon.id in (int(CardId.GROOKEY), int(CardId.THWACKEY))
        for pokemon in view.own_field
    )
    initial_bench_slots = max(
        0,
        int(view.own.get("benchMax", 5)) - len(view.own_bench),
    )
    visible_applin_supply = (
        sum(card_id == int(CardId.APPLIN) for card_id in view.own_hand_ids)
        + sum(card_id == int(CardId.APPLIN) for card_id in view.looking_ids)
        + sum(
            isinstance(card, dict)
            and int(card.get("id", 0)) == int(CardId.APPLIN)
            for card in (view.own.get("discard") or ())
        )
    )
    third_attacker_layout_reachable = bool(
        int(view.select.get("context", -1)) == int(SelectContext.TO_BENCH)
        and field_dipplin_lines + visible_applin_supply >= 3
        and initial_bench_slots
        >= max(0, 3 - field_dipplin_lines)
        + max(0, 2 - field_thwackey_lines)
    )
    dipplin_target = 3 if third_attacker_layout_reachable else 2

    dipplin_lines_before = field_dipplin_lines + sum(
        card_id in (int(CardId.APPLIN), int(CardId.DIPPLIN))
        for card_id in selected_card_ids
    )
    thwackey_lines_before = field_thwackey_lines + sum(
        card_id in (int(CardId.GROOKEY), int(CardId.THWACKEY))
        for card_id in selected_card_ids
    )
    candidate = int(candidate_card_id)
    if (
        candidate in (int(CardId.APPLIN), int(CardId.DIPPLIN))
        and dipplin_lines_before < 2
    ):
        return True
    if (
        candidate in (int(CardId.GROOKEY), int(CardId.THWACKEY))
        and thwackey_lines_before < 2
    ):
        return True
    selected = (*selected_card_ids, candidate)
    dipplin_lines = dipplin_lines_before + int(
        candidate in (int(CardId.APPLIN), int(CardId.DIPPLIN))
    )
    thwackey_lines = thwackey_lines_before + int(
        candidate in (int(CardId.GROOKEY), int(CardId.THWACKEY))
    )
    missing_core_lines = (
        max(0, dipplin_target - dipplin_lines)
        + max(0, 2 - thwackey_lines)
    )
    remaining_bench_slots = max(
        0,
        int(view.own.get("benchMax", 5))
        - len(view.own_bench)
        - len(selected),
    )
    return remaining_bench_slots >= missing_core_lines


def _semantic_option_key(option: LegalOption) -> tuple[int, ...]:
    source_serial = (
        2**31 - 1
        if option.source is None or option.source.serial is None
        else int(option.source.serial)
    )
    target_serial = (
        2**31 - 1
        if option.target is None or option.target.serial is None
        else int(option.target.serial)
    )
    card_serial = 2**31 - 1 if option.card_serial is None else int(option.card_serial)
    card_id = 2**31 - 1 if option.card_id is None else int(option.card_id)
    return (
        int(option.type),
        card_id,
        card_serial,
        source_serial,
        target_serial,
        int(option.position),
    )


_SELECTORS: dict[ActionKind, Selector] = {
    ActionKind.PLAY_CARD: _select_play,
    ActionKind.PLAY_BASIC: _select_play,
    ActionKind.EVOLVE: _select_evolve_or_attach,
    ActionKind.ATTACH_ENERGY: _select_evolve_or_attach,
    ActionKind.ATTACH_TOOL: _select_attach_tool,
    ActionKind.USE_THWACKEY: _select_ability,
    ActionKind.RETREAT: _select_retreat,
    ActionKind.SWITCH: _select_pokemon,
    ActionKind.ATTACK: _select_attack,
    ActionKind.SELECT_CARDS: _select_cards,
    ActionKind.SELECT_CARDS_FILL: _select_cards,
    ActionKind.SELECT_POKEMON: _select_pokemon,
    ActionKind.END: _select_end,
    ActionKind.SELECT_FIRST: _select_first,
    ActionKind.SELECT_NONE: _select_none,
    ActionKind.CHOOSE_YES: _select_yes_or_no,
    ActionKind.CHOOSE_NO: _select_yes_or_no,
}
