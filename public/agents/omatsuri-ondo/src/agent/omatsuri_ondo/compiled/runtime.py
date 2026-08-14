from __future__ import annotations

from common_strategy import GameView

from .action_selectors import select_action
from .features import assign_roles, extract_policy_features
from .ko_chain import KoChainClass
from .memory import CompiledMemory
from .safe_fallback import fixed_safe_fallback
from .schema import (
    ActionKind,
    ActionSpec,
    BENCH_KO_DOMINANCE_REASON_CODE,
    CardZone,
    FeatureKind,
    FeatureQuery,
    LeafNode,
    PolicyFeatures,
    PolicyProgram,
    ScalarFeature,
)
from ..cards import CardId


class CompiledPolicyRuntime:
    def __init__(self, program: PolicyProgram) -> None:
        self.program = program
        self.last_visited_node_count = 0
        self.last_features: PolicyFeatures | None = None

    def action_for(
        self,
        features: PolicyFeatures,
        continuation_id: int,
    ) -> tuple[ActionSpec | None, str | None, int | None]:
        node_id = self.program.root_for(int(continuation_id))
        if node_id is None:
            self.last_visited_node_count = 0
            return None, "missing_policy_root", None
        visited: set[int] = set()
        while 0 <= node_id < len(self.program.nodes):
            if node_id in visited:
                self.last_visited_node_count = len(visited)
                return None, "invalid_policy_graph", node_id
            visited.add(node_id)
            node = self.program.nodes[node_id]
            if isinstance(node, LeafNode):
                self.last_visited_node_count = len(visited)
                return self.program.actions[node.action_index], None, node_id
            if not 0 <= node.query_index < len(self.program.queries):
                self.last_visited_node_count = len(visited)
                return None, "invalid_policy_graph", node_id
            value = features.read(self.program.queries[node.query_index])
            node_id = dict(node.cases).get(value, node.default_node)
        self.last_visited_node_count = len(visited)
        return None, "invalid_policy_graph", node_id

    def decide(
        self,
        view: GameView,
        memory: CompiledMemory,
    ) -> tuple[int, ...]:
        memory.observe(view)
        key = memory.decision_key(view)
        features = extract_policy_features(view, memory)
        self.last_features = features
        replayed = memory.replay(key)
        if replayed is not None:
            return replayed

        roles = assign_roles(view, memory)
        action, fallback_reason, node_id = self.action_for(
            features,
            memory.continuation_id,
        )
        selected: tuple[int, ...] | None = None
        if action is not None and action.kind is not ActionKind.SAFE_FALLBACK:
            selected = select_action(view, action, roles)
            if selected is None:
                fallback_reason = "semantic_action_not_legal"
        elif action is not None:
            fallback_reason = "compiled_safe_fallback"

        if fallback_reason is not None:
            memory.fallback_count += 1
            if fallback_reason != "compiled_safe_fallback":
                memory.unknown_state_count += 1
            selected = fixed_safe_fallback(view)
        assert selected is not None
        if not _selection_is_legal(view, selected):
            memory.fallback_count += 1
            memory.unknown_state_count += 1
            fallback_reason = "selector_returned_illegal_indices"
            selected = fixed_safe_fallback(view)

        if action is not None and fallback_reason is None:
            _commit_action(memory, view, action, selected)
        else:
            _abandon_action(memory, action)
            memory.continuation_id = 0
        memory.remember(key, selected)
        executed_action_kind = (
            ActionKind.SAFE_FALLBACK
            if fallback_reason is not None
            else None if action is None else action.kind
        )
        trace_event: dict[str, object] = {
            "turn": int(view.current.get("turn", 0)),
            "own_turn_number": int(view.own_turn_number),
            "turn_action_count": int(view.current.get("turnActionCount", 0)),
            "policy_node_id": node_id,
            "continuation_id": int(memory.continuation_id),
            "action_kind": (
                None if executed_action_kind is None else int(executed_action_kind)
            ),
            "planned_action_kind": None if action is None else int(action.kind),
            "reason_code": (
                None
                if action is None or fallback_reason is not None
                else int(action.reason_code)
            ),
            "pattern_id": (
                "fixed-safe-fallback"
                if fallback_reason is not None
                else None
                if action is None
                else f"compiled-reason-{int(action.reason_code)}"
            ),
            "next_attack_preparation_class": features.read(FeatureQuery(
                FeatureKind.SCALAR,
                int(ScalarFeature.NEXT_ATTACK_PREPARATION_CLASS),
            )),
            "ko_chain_class": features.read(FeatureQuery(
                FeatureKind.SCALAR,
                int(ScalarFeature.KO_CHAIN_CLASS),
            )),
            "ko_chain_guaranteed_prizes": features.read(FeatureQuery(
                FeatureKind.SCALAR,
                int(ScalarFeature.KO_CHAIN_GUARANTEED_PRIZES),
            )),
            "ko_chain_second_hit_damage": features.read(FeatureQuery(
                FeatureKind.SCALAR,
                int(ScalarFeature.KO_CHAIN_SECOND_HIT_DAMAGE),
            )),
            "ko_chain_worst_remaining_hp": features.read(FeatureQuery(
                FeatureKind.SCALAR,
                int(ScalarFeature.KO_CHAIN_WORST_REMAINING_HP),
            )),
            "selected": selected,
            "fallback_reason": fallback_reason,
        }
        trace_event["source_turn_chain_prepared"] = int(
            int(trace_event["ko_chain_class"])
            in (
                int(KoChainClass.GAME_END_GUARANTEED),
                int(KoChainClass.GAME_WIN_THIS_TURN),
            )
        )
        if (
            fallback_reason is None
            and action is not None
            and action.kind is ActionKind.ATTACK
        ):
            trace_event["preparation_facts"] = _preparation_facts(features)
        memory.trace.append(trace_event)
        return selected


def _preparation_facts(features: PolicyFeatures) -> dict[str, int]:
    """Expose the source attack turn's finite preparation-table inputs."""

    scalars = {
        "class": ScalarFeature.NEXT_ATTACK_PREPARATION_CLASS,
        "minimum_board": ScalarFeature.MINIMUM_BOARD_COMPLETE,
        "dipplin_lines": ScalarFeature.DIPPLIN_FAMILY_LINES,
        "thwackey_lines": ScalarFeature.THWACKEY_FAMILY_LINES,
        "mature_applin": ScalarFeature.MATURE_APPLIN,
        "mature_grookey": ScalarFeature.MATURE_GROOKEY,
        "ready_bench_dipplin": ScalarFeature.READY_BENCH_DIPPLIN,
        "next_attacker_needs_energy": ScalarFeature.NEXT_ATTACKER_NEEDS_ENERGY,
        "second_next_attacker_needs_energy": (
            ScalarFeature.SECOND_NEXT_ATTACKER_NEEDS_ENERGY
        ),
        "can_use_thwackey": ScalarFeature.CAN_USE_THWACKEY,
        "festival_active": ScalarFeature.FESTIVAL_ACTIVE,
        "bench_free": ScalarFeature.BENCH_FREE,
        "attachment_available": ScalarFeature.ATTACHMENT_AVAILABLE,
        "supporter_available": ScalarFeature.SUPPORTER_AVAILABLE,
        "retreat_available": ScalarFeature.RETREAT_AVAILABLE,
    }
    facts = {
        name: features.read(FeatureQuery(FeatureKind.SCALAR, int(feature)))
        for name, feature in scalars.items()
    }
    cards = {
        "grass": CardId.BASIC_GRASS,
        "applin": CardId.APPLIN,
        "dipplin": CardId.DIPPLIN,
        "grookey": CardId.GROOKEY,
        "thwackey": CardId.THWACKEY,
        "festival": CardId.FESTIVAL_GROUNDS,
        "poke_pad": CardId.POKE_PAD,
        "bug_set": CardId.BUG_CATCHING_SET,
        "poffin": CardId.BUDDY_BUDDY_POFFIN,
        "night_stretcher": CardId.NIGHT_STRETCHER,
        "lana": CardId.LANAS_AID,
        "sacred_ash": CardId.SACRED_ASH,
        "air_balloon": CardId.AIR_BALLOON,
        "kieran": CardId.KIERAN,
        "brock": CardId.BROCKS_SCOUTING,
        "lillie": CardId.LILLIES_DETERMINATION,
        "judge": CardId.JUDGE,
    }
    for name, card_id in cards.items():
        facts[f"hand_{name}"] = features.read(FeatureQuery(
            FeatureKind.CARD_COUNT,
            int(CardZone.HAND),
            int(card_id),
        ))
        facts[f"deck_min_{name}"] = features.read(FeatureQuery(
            FeatureKind.CARD_COUNT,
            int(CardZone.DECK_MIN),
            int(card_id),
        ))
        facts[f"deck_max_{name}"] = features.read(FeatureQuery(
            FeatureKind.CARD_COUNT,
            int(CardZone.DECK_MAX),
            int(card_id),
        ))
        facts[f"discard_{name}"] = features.read(FeatureQuery(
            FeatureKind.CARD_COUNT,
            int(CardZone.DISCARD),
            int(card_id),
        ))
    return facts


def _selection_is_legal(view: GameView, selected: tuple[int, ...]) -> bool:
    minimum = max(0, int(view.select.get("minCount", 0)))
    maximum = max(0, int(view.select.get("maxCount", len(view.options))))
    return (
        minimum <= len(selected) <= maximum
        and len(selected) == len(set(selected))
        and all(0 <= int(position) < len(view.options) for position in selected)
    )


def _commit_action(
    memory: CompiledMemory,
    view: GameView,
    action: ActionSpec,
    selected: tuple[int, ...],
) -> None:
    memory.continuation_id = int(action.continuation_id)
    if int(action.reason_code) == int(BENCH_KO_DOMINANCE_REASON_CODE):
        memory.bench_ko_dominance_committed = True
    if (
        action.kind is ActionKind.PLAY_CARD
        and action.source_card_id == int(CardId.KIERAN)
    ):
        memory.damage_support = 1
    elif (
        action.kind is ActionKind.PLAY_CARD
        and action.source_card_id == int(CardId.BLACK_BELTS_TRAINING)
    ):
        memory.damage_support = 2
    elif action.kind is ActionKind.CHOOSE_YES:
        memory.damage_support = 0
    if action.kind in (ActionKind.PLAY_CARD, ActionKind.PLAY_BASIC):
        memory.record_card_played(action.source_card_id)
    if len(selected) != 1:
        return
    option = view.options[selected[0]]
    if (
        action.kind is ActionKind.USE_THWACKEY
        and option.source is not None
        and option.source.serial is not None
    ):
        memory.record_thwackey_used(int(option.source.serial))
    if (
        action.kind is ActionKind.ATTACK
        and option.source is not None
        and option.source.serial is not None
    ):
        memory.record_attack_selected(
            int(option.source.serial),
            attack_id=int(action.attack_id),
        )


def _abandon_action(
    memory: CompiledMemory,
    action: ActionSpec | None,
) -> None:
    """Clear state that would only be true if the planned semantic action ran."""

    if action is not None and action.kind in (
        ActionKind.CHOOSE_YES,
        ActionKind.CHOOSE_NO,
    ):
        memory.damage_support = 0
