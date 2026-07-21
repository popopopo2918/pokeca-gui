from dataclasses import dataclass
from enum import Enum

from cards import CardId
from memory import card_may_be_in_deck
from model import Area, OptionType, SelectContext, SelectType
from proposals import IntentUpdate, PendingIntent, Proposal, covers
from rules.attack import can_hand_power_ko, plan_hammer_target
from rules.board_plan import attack_line_count, full_board_plan, is_opening_attack_phase
from rules.continuity import nonfinal_immediate_ko, spend_preserves_immediate_ko
from rules.petrel_critical_path import evaluate_petrel_critical_path
from rules.recovery import (
    night_stretcher_basic_psychic_route,
    plan_proactive_attack_line_recovery,
)


_ATTACK_PSYCHIC_IDS = frozenset({
    int(CardId.BASIC_PSYCHIC),
    int(CardId.TELEPATH_PSYCHIC_ENERGY),
})
_GUARANTEED_DRAW_EVOLUTION_IDS = frozenset({
    int(CardId.DUDUNSPARCE),
    int(CardId.KADABRA),
    int(CardId.ALAKAZAM),
})

PETREL_SAME_TURN_CANDY_PRIORITY = 997
PETREL_SAME_TURN_POKE_PAD_PRIORITY = 996
PETREL_FIRST_TURN_CANDY_PRIORITY = 792
PETREL_FIRST_TURN_POFFIN_PRIORITY = 791
PETREL_FIRST_TURN_POKE_PAD_PRIORITY = 790
PETREL_LATER_TURN_BASIC_SETUP_PRIORITY = 993
PETREL_PROACTIVE_SACRED_ASH_PRIORITY = 1095
PETREL_POKE_PAD_DEFERRED_KIND = "PETREL_POKE_PAD_BASIC_SETUP_DEFERRED"
PETREL_POKE_PAD_INTENT_KIND = "PETREL_POKE_PAD_BASIC_SETUP"
PETREL_RECYCLED_ABRA_DEPLOY_DEFERRED_KIND = (
    "PETREL_RECYCLED_ABRA_DEPLOY_DEFERRED"
)
PETREL_SETUP_BASIC_IDS_METADATA_KEY = "setup_basic_ids"


class PetrelPurpose(str, Enum):
    RARE_CANDY = "rare_candy"
    ENHANCED_HAMMER = "enhanced_hammer"
    NIGHT_STRETCHER = "night_stretcher"
    POKE_PAD = "poke_pad"
    BASIC_SETUP = "basic_setup"
    SACRED_ASH = "sacred_ash"

@dataclass(frozen=True)
class PetrelRoute:
    trainer_id: int
    purpose: PetrelPurpose
    priority: int
    target_serial: int | None = None
    metadata: tuple[tuple[str, int | str | bool], ...] = ()
    def key(self):
        serial = 10**18 if self.target_serial is None else int(self.target_serial)
        return (int(self.priority), -serial, -int(self.trainer_id), self.purpose.value)


def _serial_key(pokemon) -> tuple[int, int, int]:
    return (
        10**9 if pokemon.serial is None else int(pokemon.serial),
        int(pokemon.area),
        int(pokemon.index or 0),
    )


def _is_main(view):
    return int(view.select.get("type", -1)) == int(SelectType.MAIN) and int(view.select.get("context", -1)) == int(SelectContext.MAIN)

def _petrel_options(view):
    return tuple(o for o in view.options if o.type == int(OptionType.PLAY) and o.card_id == int(CardId.TEAM_ROCKETS_PETREL) and o.card_serial is not None)


def _has_planned_guaranteed_draw_evolution(view, memory) -> bool:
    """既存進化規則が今選ぶ確定ドロー進化を、一発検索より先に通す。"""

    from rules.evolution import propose_evolution

    proposal = propose_evolution(view, memory)
    if proposal is None:
        return False
    selected_positions = set(proposal.option_indices)
    return any(
        option.position in selected_positions
        and (
            (
                option.type == int(OptionType.EVOLVE)
                and option.card_id in _GUARANTEED_DRAW_EVOLUTION_IDS
            )
            or (
                option.type == int(OptionType.PLAY)
                and option.card_id == int(CardId.RARE_CANDY)
            )
        )
        for option in view.options
    )


def _has_planned_immediate_candy_search(view, memory) -> bool:
    """トウコ・ヒカリで今番のアメ攻撃を完成できるなら先に通す。"""

    if (
        int(view.own_turn_number) <= 1
        or attack_line_count(view) <= 0
        or int(CardId.RARE_CANDY) not in view.hand_ids
    ):
        return False

    # 場に攻撃系統があるため、propose_search 内の「攻撃系統0本」分岐から
    # petrelへ戻る再帰は発生しない。通常の将来検索ではなく、検索規則自身が
    # PLAYBOOK-CANDY-FIRST と判定した同番完成経路だけを保護する。
    from rules.search import propose_search

    proposal = propose_search(view, memory)
    return (
        proposal is not None
        and "PLAYBOOK-CANDY-FIRST" in proposal.rule_ids
        and proposal.next_intent is not None
        and proposal.next_intent.effect_card_id
        in (int(CardId.HILDA), int(CardId.DAWN))
    )


def _basic_setup_target_group(view, memory) -> tuple[int, ...]:
    from rules.search import rank_full_board_search_candidates

    plan = full_board_plan(view)
    basic_ids = {int(CardId.ABRA), int(CardId.DUNSPARCE)}
    for group in rank_full_board_search_candidates(view, memory, plan):
        available = tuple(
            int(card_id)
            for card_id in group
            if int(card_id) in basic_ids
            and card_may_be_in_deck(view, memory, card_id)
        )
        if available:
            return available
    return ()


def _can_power_this_turn(view, pokemon) -> bool:
    if view.has_psychic_energy(pokemon):
        return True
    return any(
        option.type == int(OptionType.ATTACH)
        and option.card_id in _ATTACK_PSYCHIC_IDS
        and option.target is not None
        and option.target.serial == pokemon.serial
        for option in view.options
    )


def _current_ko_is_nonfinal(view) -> bool:
    if not can_hand_power_ko(view) or len(view.opponent_field) <= 1:
        return False
    target = view.opponent_active
    if target is None:
        return False
    meta = view.catalog.card(target.id)
    prize_value = 1 if meta is None else int(meta.prize_value)
    return view.own_prize_count > prize_value


def _can_move_to_attack_position(view, pokemon) -> bool:
    if pokemon.area == int(Area.ACTIVE):
        return True
    if _current_ko_is_nonfinal(view):
        # 現在のフーディンでKOし、完成した個体を次番用に残す経路。
        return True
    if any(option.type == int(OptionType.RETREAT) for option in view.options):
        return True
    active = view.active
    return active is not None and any(
        option.type in (int(OptionType.ABILITY), int(OptionType.SKILL))
        and option.card_id == int(CardId.DUDUNSPARCE)
        and option.source is not None
        and option.source.serial == active.serial
        for option in view.options
    )


def _attack_candidate(view, candidates):
    eligible = tuple(
        pokemon
        for pokemon in candidates
        if _can_power_this_turn(view, pokemon)
        and _can_move_to_attack_position(view, pokemon)
    )
    return min(
        eligible,
        key=lambda pokemon: (
            0 if pokemon.area == int(Area.ACTIVE) else 1,
            0 if view.has_psychic_energy(pokemon) else 1,
            *_serial_key(pokemon),
        ),
        default=None,
    )


def _normal_alakazam_route_exists(view) -> bool:
    return any(
        option.type == int(OptionType.EVOLVE)
        and option.card_id == int(CardId.ALAKAZAM)
        and option.target is not None
        and int(option.target.id) == int(CardId.KADABRA)
        and _can_power_this_turn(view, option.target)
        and _can_move_to_attack_position(view, option.target)
        for option in view.options
    )


def _alakazam_available_after_candy_search(view, memory) -> bool:
    if int(CardId.ALAKAZAM) in view.hand_ids:
        return True
    return (
        int(CardId.POKE_PAD) in view.hand_ids
        and card_may_be_in_deck(view, memory, CardId.ALAKAZAM)
    )


def _petrel_candy_route(view, memory) -> PetrelRoute | None:
    if (
        int(CardId.RARE_CANDY) in view.hand_ids
        or not card_may_be_in_deck(view, memory, CardId.RARE_CANDY)
        or _normal_alakazam_route_exists(view)
    ):
        return None
    if int(view.own_turn_number) == 1:
        facts = evaluate_petrel_critical_path(view, memory)
        if not facts.next_turn_candy_attack_locked:
            return None
        return PetrelRoute(
            int(CardId.RARE_CANDY),
            PetrelPurpose.RARE_CANDY,
            PETREL_FIRST_TURN_CANDY_PRIORITY,
            facts.target_serial,
            (
                ("route_timing", "next_turn"),
                ("route_mode", "critical_path_candy"),
                *facts.metadata(),
            ),
        )
    if (
        int(view.own_turn_number) < 2
        or not _alakazam_available_after_candy_search(view, memory)
    ):
        return None
    target = _attack_candidate(view, view.eligible_abras)
    if target is None:
        return None
    return PetrelRoute(
        int(CardId.RARE_CANDY),
        PetrelPurpose.RARE_CANDY,
        PETREL_SAME_TURN_CANDY_PRIORITY,
        target.serial,
        (
            ("route_timing", "same_turn"),
            ("route_mode", "same_turn_candy"),
        ),
    )


def _petrel_poke_pad_route(view, memory) -> PetrelRoute | None:
    if (
        int(view.own_turn_number) < 2
        or int(CardId.POKE_PAD) in view.hand_ids
        or int(CardId.ALAKAZAM) in view.hand_ids
        or not card_may_be_in_deck(view, memory, CardId.POKE_PAD)
        or not card_may_be_in_deck(view, memory, CardId.ALAKAZAM)
    ):
        return None

    if int(CardId.RARE_CANDY) in view.hand_ids:
        target = _attack_candidate(view, view.eligible_abras)
    else:
        target = _attack_candidate(
            view,
            (
                pokemon
                for pokemon in view.field
                if int(pokemon.id) == int(CardId.KADABRA)
                and not pokemon.appear_this_turn
            ),
        )
    if target is None:
        return None
    return PetrelRoute(
        int(CardId.POKE_PAD),
        PetrelPurpose.POKE_PAD,
        PETREL_SAME_TURN_POKE_PAD_PRIORITY,
        target.serial,
        (
            ("route_timing", "same_turn"),
            ("route_mode", "same_turn_poke_pad"),
        ),
    )


def _petrel_sacred_ash_route(view, memory) -> PetrelRoute | None:
    if (
        int(CardId.SACRED_ASH) in view.hand_ids
        or not card_may_be_in_deck(view, memory, CardId.SACRED_ASH)
        or not nonfinal_immediate_ko(view)
    ):
        return None
    plan = plan_proactive_attack_line_recovery(
        view,
        memory,
        cards_spent=2,
    )
    if plan is None or plan.follow_up_card_id not in (
        int(CardId.BUDDY_BUDDY_POFFIN),
        int(CardId.POKE_PAD),
    ):
        return None
    return PetrelRoute(
        int(CardId.SACRED_ASH),
        PetrelPurpose.SACRED_ASH,
        PETREL_PROACTIVE_SACRED_ASH_PRIORITY,
        metadata=(
            ("required_lines", plan.required_lines),
            ("missing_lines", plan.missing_lines),
            ("follow_up_card_id", int(plan.follow_up_card_id)),
            ("follow_up_card_serial", int(plan.follow_up_card_serial)),
        ),
    )


def _petrel_basic_setup_route(view, memory) -> PetrelRoute | None:
    """最速攻撃を固定できない時、同番のたね展開へ接続する。"""

    if (
        _has_planned_guaranteed_draw_evolution(view, memory)
        or _has_planned_immediate_candy_search(view, memory)
    ):
        return None
    facts = evaluate_petrel_critical_path(view, memory)
    if (
        facts.next_turn_candy_attack_locked
        or facts.setup_trainer_id is None
        or not spend_preserves_immediate_ko(view, 1)
        or any(
            int(card_id) in view.hand_ids
            for card_id in (
                CardId.ABRA,
                CardId.BUDDY_BUDDY_POFFIN,
                CardId.POKE_PAD,
            )
        )
    ):
        return None
    if int(view.own_turn_number) == 1:
        priority = (
            PETREL_FIRST_TURN_POFFIN_PRIORITY
            if facts.setup_trainer_id == int(CardId.BUDDY_BUDDY_POFFIN)
            else PETREL_FIRST_TURN_POKE_PAD_PRIORITY
        )
    else:
        priority = PETREL_LATER_TURN_BASIC_SETUP_PRIORITY
    setup_metadata: tuple[tuple[str, int | str | bool], ...] = ()
    if facts.setup_trainer_id == int(CardId.POKE_PAD):
        target_group = _basic_setup_target_group(view, memory)
        if not target_group:
            return None
        setup_metadata = (
            (
                PETREL_SETUP_BASIC_IDS_METADATA_KEY,
                ",".join(str(card_id) for card_id in target_group),
            ),
        )
    return PetrelRoute(
        int(facts.setup_trainer_id),
        PetrelPurpose.BASIC_SETUP,
        priority,
        metadata=(
            ("route_timing", "setup_now"),
            ("route_mode", "basic_setup"),
            *setup_metadata,
            *facts.metadata(),
        ),
    )


def first_turn_petrel_places_missing_attack_line(view, memory) -> bool:
    """初回ターン中にラムダ経由で最初のケーシィを置けるか返す。"""

    if (
        int(view.own_turn_number) != 1
        or attack_line_count(view) > 0
        or not _petrel_options(view)
    ):
        return False
    route = _petrel_basic_setup_route(view, memory)
    return route is not None and route.purpose is PetrelPurpose.BASIC_SETUP


def _deferred_poke_pad_proposal(view, memory) -> Proposal | None:
    intent = memory.pending_intent
    if (
        intent is None
        or intent.kind != PETREL_POKE_PAD_DEFERRED_KIND
        or not intent.matches_deferred_main(view)
        or not intent.card_ids
        or any(
            int(card_id) not in (int(CardId.ABRA), int(CardId.DUNSPARCE))
            for card_id in intent.card_ids
        )
    ):
        return None
    option = next(
        (
            candidate
            for candidate in view.options
            if candidate.type == int(OptionType.PLAY)
            and candidate.card_id == int(CardId.POKE_PAD)
            and candidate.card_serial == intent.effect_serial
        ),
        None,
    )
    if option is None:
        return None
    source_purpose = next(
        (
            str(value)
            for name, value in intent.metadata
            if name == "purpose"
        ),
        None,
    )
    priority = (
        PETREL_PROACTIVE_SACRED_ASH_PRIORITY
        if source_purpose == PetrelPurpose.SACRED_ASH.value
        else PETREL_FIRST_TURN_POKE_PAD_PRIORITY
        if int(view.own_turn_number) == 1
        else PETREL_LATER_TURN_BASIC_SETUP_PRIORITY
    )
    poke_pad_metadata = (
        ("reason", "ラムダで予約したたねポケモンをポケパッドで探す"),
        *(
            (("purpose", source_purpose),)
            if source_purpose is not None
            else ()
        ),
    )
    poke_pad_intent = PendingIntent.from_view(
        view,
        kind=PETREL_POKE_PAD_INTENT_KIND,
        card_ids=intent.card_ids,
        card_groups=(intent.card_ids,),
        max_cards=1,
        metadata=poke_pad_metadata,
        effect_card_id=CardId.POKE_PAD,
        effect_serial=option.card_serial,
        remaining_contexts=(SelectContext.TO_HAND,),
    )
    return Proposal(
        (option.position,),
        priority,
        "ラムダで取得したポケパッドから、予約したたね展開を継続する",
        ("PLAYBOOK-SEARCH-INTENT", "PLAYBOOK-PETREL"),
        next_intent=poke_pad_intent,
        facts=(("petrel_purpose", PetrelPurpose.BASIC_SETUP.value),),
    )


def _deferred_recycled_abra_deploy_proposal(view, memory) -> Proposal | None:
    intent = memory.pending_intent
    if (
        intent is None
        or intent.kind != PETREL_RECYCLED_ABRA_DEPLOY_DEFERRED_KIND
        or not intent.matches_deferred_main(view)
        or intent.effect_card_id != int(CardId.ABRA)
        or intent.effect_serial is None
    ):
        return None
    option = next(
        (
            candidate
            for candidate in view.options
            if candidate.type == int(OptionType.PLAY)
            and candidate.card_id == int(CardId.ABRA)
            and candidate.card_serial == int(intent.effect_serial)
        ),
        None,
    )
    if option is None:
        return None
    return Proposal(
        (option.position,),
        PETREL_PROACTIVE_SACRED_ASH_PRIORITY,
        "聖なる灰からポケパッドで戻したケーシィを、進化より先に場へ出す",
        ("PLAYBOOK-SEARCH-INTENT", "PLAYBOOK-SACRED-ASH"),
        intent_update=IntentUpdate.CLEAR,
        facts=(("petrel_purpose", PetrelPurpose.SACRED_ASH.value),),
    )

def plan_petrel_routes(view, memory):
    if not _is_main(view) or not _petrel_options(view):
        return ()
    routes = []
    sacred_ash = _petrel_sacred_ash_route(view, memory)
    if sacred_ash is not None:
        routes.append(sacred_ash)
    candy = _petrel_candy_route(view, memory)
    if candy is not None:
        routes.append(candy)
    poke_pad = _petrel_poke_pad_route(view, memory)
    if poke_pad is not None:
        routes.append(poke_pad)
    basic_setup = _petrel_basic_setup_route(view, memory)
    if basic_setup is not None:
        routes.append(basic_setup)
    if int(CardId.ENHANCED_HAMMER) not in view.hand_ids and card_may_be_in_deck(view, memory, CardId.ENHANCED_HAMMER):
        target = plan_hammer_target(view, memory, hand_spent=1)
        if target is not None and (
            target.unlocks_ko
            or (
                not is_opening_attack_phase(view)
                and attack_line_count(view) >= 3
            )
        ):
            routes.append(PetrelRoute(int(CardId.ENHANCED_HAMMER), PetrelPurpose.ENHANCED_HAMMER, 995, target.pokemon_serial, (("energy_serial", target.energy_serial),)))
    if (
        int(CardId.NIGHT_STRETCHER) not in view.hand_ids
        and card_may_be_in_deck(view, memory, CardId.NIGHT_STRETCHER)
        and night_stretcher_basic_psychic_route(view, memory) is not None
    ):
        routes.append(PetrelRoute(int(CardId.NIGHT_STRETCHER), PetrelPurpose.NIGHT_STRETCHER, 994))
    return tuple(routes)

def choose_petrel_route(view, memory):
    routes = plan_petrel_routes(view, memory)
    return max(routes, key=PetrelRoute.key) if routes else None

@covers("PLAYBOOK-SEARCH-INTENT", "PLAYBOOK-PETREL")
def propose_petrel(view, memory):
    deploy = _deferred_recycled_abra_deploy_proposal(view, memory)
    if deploy is not None:
        return deploy
    deferred = _deferred_poke_pad_proposal(view, memory)
    if deferred is not None:
        return deferred
    route = choose_petrel_route(view, memory)
    if route is None:
        return None
    petrel = min(_petrel_options(view), key=lambda o: (int(o.card_serial), o.position))
    route_facts = (
        ("petrel_purpose", route.purpose.value),
        ("petrel_trainer_id", int(route.trainer_id)),
        *route.metadata,
    )
    intent = PendingIntent.from_view(
        view,
        kind="PETREL_TRAINER_SEARCH",
        card_ids=(route.trainer_id,),
        card_groups=((route.trainer_id,),),
        max_cards=1,
        metadata=(
            ("purpose", route.purpose.value),
            (
                "target_serial",
                -1
                if route.target_serial is None
                else int(route.target_serial),
            ),
            *route.metadata,
        ),
        effect_card_id=CardId.TEAM_ROCKETS_PETREL,
        effect_serial=petrel.card_serial,
        remaining_contexts=(SelectContext.TO_HAND,),
    )
    if route.purpose is PetrelPurpose.SACRED_ASH:
        reason = (
            "進化待ち時間を消化するため、ラムダで聖なる灰を取り、"
            "ポフィンより先にケーシィ系統を戻す"
        )
    elif route.purpose is PetrelPurpose.BASIC_SETUP:
        reason = "ラムダで今番のたね展開を増やし、進化の成熟期限を守る"
    elif dict(route.metadata).get("route_timing") == "next_turn":
        reason = (
            "ラムダで唯一の余裕時間0要素であるアメを確保し、"
            "次番攻撃を固定する"
        )
    else:
        reason = "ラムダで同番攻撃を完成するトレーナーズを検索する"
    return Proposal(
        (petrel.position,),
        route.priority,
        reason,
        ("PLAYBOOK-SEARCH-INTENT", "PLAYBOOK-PETREL"),
        next_intent=intent,
        facts=route_facts,
    )
