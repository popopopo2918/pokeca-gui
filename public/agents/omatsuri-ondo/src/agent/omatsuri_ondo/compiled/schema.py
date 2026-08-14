from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Mapping


BENCH_KO_DOMINANCE_REASON_CODE = 1144


class FeatureKind(IntEnum):
    SCALAR = 1
    CARD_COUNT = 2


class CardZone(IntEnum):
    HAND = 1
    DECK_MIN = 2
    DECK_MAX = 3
    DISCARD = 4
    LOOKING = 5
    LEGAL_PLAY = 6


class ScalarFeature(IntEnum):
    SELECT_TYPE = 1
    SELECT_CONTEXT = 2
    SELECT_MIN = 3
    SELECT_MAX = 4
    OWN_TURN_NUMBER = 5
    FIRST_PLAYER = 6
    ACTIVE_ROLE = 7
    APPLIN_LINES = 8
    DIPPLIN_LINES = 9
    GROOKEY_LINES = 10
    THWACKEY_LINES = 11
    BENCH_FREE = 12
    EVOLVABLE_APPLIN = 13
    EVOLVABLE_GROOKEY = 14
    READY_DIPPLIN = 15
    UNUSED_THWACKEY = 16
    SUPPORTER_AVAILABLE = 17
    ATTACHMENT_AVAILABLE = 18
    RETREAT_AVAILABLE = 19
    FESTIVAL_ACTIVE = 20
    FIRST_HIT_RESOLVED = 21
    PREVIOUS_OPPONENT_KO = 22
    CAN_DIPPLIN_ATTACK = 23
    CAN_BUDEW_ATTACK = 24
    CAN_RETREAT = 25
    CAN_END = 26
    EFFECT_CARD_ID = 27
    OPPONENT_ACTIVE_HP = 28
    OPPONENT_ACTIVE_GRASS_WEAK = 29
    OPPONENT_ACTIVE_EX = 30
    OPPONENT_BENCH_COUNT = 31
    OWN_PRIZES = 32
    OPPONENT_PRIZES = 33
    OPPONENT_TARGET_CLASS = 34
    TURN_ACTION_COUNT = 35
    HAND_SIZE = 36
    DECK_COUNT = 37
    OWN_FIELD_COUNT = 38
    OWN_BENCH_COUNT = 39
    ACTIVE_CARD_ID = 40
    DIPPLIN_FAMILY_LINES = 41
    THWACKEY_FAMILY_LINES = 42
    MINIMUM_BOARD_COMPLETE = 43
    NEED_DIPPLIN_LINE = 44
    NEED_THWACKEY_LINE = 45
    SAFE_EXTRA_SLOT = 46
    READY_BENCH_DIPPLIN = 47
    ATTACKER_NEEDS_ENERGY = 48
    NEXT_ATTACKER_NEEDS_ENERGY = 49
    SECOND_NEXT_ATTACKER_NEEDS_ENERGY = 50
    ATTACKER_ON_BENCH = 51
    NEXT_SEARCHER_EVOLVABLE = 52
    SECOND_NEXT_SEARCHER_EVOLVABLE = 53
    CAN_USE_THWACKEY = 54
    ACTIVE_HAS_BALLOON = 55
    ACTIVE_RETREAT_COST = 56
    OPPONENT_BENCH_DAMAGE_THREAT = 57
    OPPONENT_SELF_KO_THREAT = 58
    SHAYMIN_DEPLOYED = 59
    PSYDUCK_DEPLOYED = 60
    CURRENT_HIT_COUNT = 61
    CURRENT_DAMAGE = 62
    CAN_KO_NOW = 63
    CAN_KO_WITH_FESTIVAL = 64
    CAN_KO_WITH_BANGLE = 65
    CAN_KO_WITH_KIERAN = 66
    CAN_KO_WITH_BLACK_BELT = 67
    CAN_KO_WITH_ONE_MORE_BENCH = 68
    DAMAGE_GAIN_WITH_FESTIVAL = 69
    DAMAGE_GAIN_WITH_BANGLE = 70
    DAMAGE_GAIN_WITH_KIERAN = 71
    DAMAGE_GAIN_WITH_BLACK_BELT = 72
    DAMAGE_GAIN_WITH_ONE_MORE_BENCH = 73
    KOABLE_OPPONENT_BENCH = 74
    OPPONENT_HAND_SIZE = 75
    ACTIVE_APPLIN_EVOLVABLE = 76
    BACKUP_APPLIN_EVOLVABLE = 77
    ACTIVE_DIPPLIN_READY = 78
    BUG_SET_USED_THIS_TURN = 79
    POFFIN_USED_THIS_TURN = 80
    MATURE_APPLIN = 81
    MATURE_GROOKEY = 82
    ACTIVE_APPLIN_MATURE = 83
    BALLOON_SEARCHER_TARGET = 84
    BALLOON_SHAYMIN_TARGET = 85
    BALLOON_GOLDEEN_TARGET = 86
    BALLOON_PSYDUCK_TARGET = 87
    BALLOON_GOLDEEN_READY = 88
    BOSS_PREFERRED = 89
    BEST_KOABLE_BENCH_PRIZES = 90
    BOSS_DECISION_CLASS = 91
    BUDEW_DEPLOYED = 92
    BUDEW_ON_BENCH = 93
    ACTIVE_FESTIVAL_LEAD = 94
    THWACKEY_UNLOCK_ROUTE = 95
    SAFE_SURVIVAL_SLOT = 96
    PROMOTABLE_APPLIN_ROUTE = 97
    NEXT_TURN_ATTACK_ROUTE = 98
    CAN_KO_WITH_FULL_BENCH = 99
    BENCH_KO_STRICTLY_DOMINATES_BOSS = 100
    BENCH_KO_DOMINANCE_COMMITTED = 101
    ACTIVE_TOOL_FREE = 102
    CAN_KO_WITH_TWO_MORE_BENCH = 103
    SAFE_COUNTER_SLOT = 104
    ENERGY_RETREAT_PREP_ROUTE = 105
    ENERGY_RETREAT_ATTACK_ROUTE = 106
    NEXT_ATTACK_PREPARATION_CLASS = 107


class ActionKind(IntEnum):
    PLAY_CARD = 1
    PLAY_BASIC = 2
    EVOLVE = 3
    ATTACH_ENERGY = 4
    ATTACH_TOOL = 5
    USE_THWACKEY = 6
    RETREAT = 7
    SWITCH = 8
    ATTACK = 9
    SELECT_CARDS = 10
    SELECT_POKEMON = 11
    END = 12
    SAFE_FALLBACK = 13
    SELECT_CARDS_FILL = 14
    SELECT_FIRST = 15
    SELECT_NONE = 16
    CHOOSE_YES = 17
    CHOOSE_NO = 18


class PokemonRole(IntEnum):
    NONE = 0
    ACTIVE = 1
    ATTACKER = 2
    NEXT_ATTACKER = 3
    SECOND_NEXT_ATTACKER = 4
    SEARCHER_ONE = 5
    SEARCHER_TWO = 6
    BUDEW = 7
    GOLDEEN = 8
    SHAYMIN = 9
    PSYDUCK = 10
    NEXT_SEARCHER = 11
    SECOND_NEXT_SEARCHER = 12
    MOVEMENT_ACTIVE = 13
    FESTIVAL_LEAD = 14


class TargetRule(IntEnum):
    EXACT_ROLE = 1
    MOST_PRIZES_THEN_LOWEST_HP = 2
    LOWEST_HP_THEN_SERIAL = 3
    LOWEST_SERIAL = 4
    KOABLE_MOST_PRIZES_THEN_HP = 5
    FLOWCHART_BOSS = 6


@dataclass(frozen=True, order=True)
class FeatureQuery:
    kind: FeatureKind
    key: int
    card_id: int = 0

    def __post_init__(self) -> None:
        if self.kind is FeatureKind.CARD_COUNT and self.card_id <= 0:
            raise ValueError("CARD_COUNT requires a positive card_id")
        if self.kind is FeatureKind.SCALAR and self.card_id != 0:
            raise ValueError("SCALAR cannot carry card_id")


@dataclass(frozen=True)
class PolicyFeatures:
    values: tuple[tuple[FeatureQuery, int], ...]

    def __post_init__(self) -> None:
        queries = tuple(query for query, _ in self.values)
        if queries != tuple(sorted(queries)) or len(queries) != len(set(queries)):
            raise ValueError("feature values must be unique and canonically sorted")
        for query, value in self.values:
            if query.kind is FeatureKind.CARD_COUNT and int(value) < 0:
                raise ValueError("card counts cannot be negative")

    @classmethod
    def from_maps(
        cls,
        *,
        scalars: Mapping[ScalarFeature | int, int],
        card_counts: Mapping[tuple[CardZone | int, int], int],
    ) -> PolicyFeatures:
        pairs = [
            (
                FeatureQuery(FeatureKind.SCALAR, int(key)),
                int(value),
            )
            for key, value in scalars.items()
        ]
        pairs.extend(
            (
                FeatureQuery(
                    FeatureKind.CARD_COUNT,
                    int(zone),
                    int(card_id),
                ),
                int(value),
            )
            for (zone, card_id), value in card_counts.items()
        )
        return cls(tuple(sorted(pairs, key=lambda item: item[0])))

    def read(self, query: FeatureQuery) -> int:
        for candidate, value in self.values:
            if candidate == query:
                return int(value)
            if candidate > query:
                break
        return 0

    def vector(self, queries: tuple[FeatureQuery, ...]) -> tuple[int, ...]:
        return tuple(self.read(query) for query in queries)


@dataclass(frozen=True)
class ActionSpec:
    kind: ActionKind
    source_card_id: int = 0
    card_ids: tuple[int, ...] = ()
    attack_id: int = 0
    source_role: PokemonRole = PokemonRole.NONE
    target_role: PokemonRole = PokemonRole.NONE
    target_rule: TargetRule = TargetRule.LOWEST_SERIAL
    continuation_id: int = 0
    reason_code: int = 0

    def __post_init__(self) -> None:
        if self.kind is ActionKind.ATTACK and self.attack_id <= 0:
            raise ValueError("ATTACK requires attack_id")
        if self.kind in (ActionKind.SELECT_CARDS, ActionKind.SELECT_CARDS_FILL) and not self.card_ids:
            raise ValueError("SELECT_CARDS requires card_ids")
        if any(int(card_id) <= 0 for card_id in self.card_ids):
            raise ValueError("card_ids must be positive")
        if self.continuation_id < 0:
            raise ValueError("continuation_id cannot be negative")


@dataclass(frozen=True)
class SwitchNode:
    query_index: int
    cases: tuple[tuple[int, int], ...]
    default_node: int

    def __post_init__(self) -> None:
        if self.query_index < 0 or self.default_node < 0:
            raise ValueError("switch indices cannot be negative")
        if self.cases != tuple(sorted(self.cases)):
            raise ValueError("switch cases must be sorted")
        values = tuple(value for value, _ in self.cases)
        if len(values) != len(set(values)):
            raise ValueError("switch case values must be unique")
        if any(node_id < 0 for _, node_id in self.cases):
            raise ValueError("node reference cannot be negative")


@dataclass(frozen=True)
class LeafNode:
    action_index: int

    def __post_init__(self) -> None:
        if self.action_index < 0:
            raise ValueError("action reference cannot be negative")


@dataclass(frozen=True)
class PolicyProgram:
    queries: tuple[FeatureQuery, ...]
    nodes: tuple[SwitchNode | LeafNode, ...]
    actions: tuple[ActionSpec, ...]
    roots: tuple[tuple[int, int], ...]

    def __post_init__(self) -> None:
        if not self.nodes or not self.actions or not self.roots:
            raise ValueError("policy program cannot be empty")
        if len(self.queries) != len(set(self.queries)):
            raise ValueError("policy queries must be unique")
        continuation_ids = tuple(continuation for continuation, _ in self.roots)
        if self.roots != tuple(sorted(self.roots)):
            raise ValueError("policy roots must be sorted")
        if len(continuation_ids) != len(set(continuation_ids)):
            raise ValueError("continuation roots must be unique")
        for _, node_id in self.roots:
            self._validate_node_reference(node_id)
        for node in self.nodes:
            if isinstance(node, LeafNode):
                if node.action_index >= len(self.actions):
                    raise ValueError("action reference is outside the action table")
                continue
            if node.query_index >= len(self.queries):
                raise ValueError("query reference is outside the query table")
            self._validate_node_reference(node.default_node)
            for _, node_id in node.cases:
                self._validate_node_reference(node_id)

    def _validate_node_reference(self, node_id: int) -> None:
        if node_id < 0 or node_id >= len(self.nodes):
            raise ValueError("node reference is outside the node table")

    def root_for(self, continuation_id: int) -> int | None:
        return dict(self.roots).get(int(continuation_id))

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def action_count(self) -> int:
        return len(self.actions)
