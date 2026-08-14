from dataclasses import dataclass, replace
from enum import Enum

from .contracts import CapabilityVector, DecisionTier
from .model import GameView, OptionType, SelectContext, SelectType


_DEFERRED_MAIN_METADATA_KEY = "deferred_main"


@dataclass(frozen=True)
class PendingIntent:
    kind: str
    card_ids: tuple[int, ...] = ()
    target_serial: int | None = None
    max_cards: int | None = None
    metadata: tuple[tuple[str, int | str | bool], ...] = ()
    metadata_slots: tuple[str, ...] = ()
    card_groups: tuple[tuple[int, ...], ...] = ()
    remaining_contexts: tuple[int, ...] = ()
    effect_card_id: int | None = None
    effect_serial: int | None = None
    created_turn: int | None = None
    created_action_count: int | None = None
    origin_option_position: int | None = None

    @classmethod
    def from_view(
        cls,
        view: GameView,
        *,
        kind: str,
        effect_card_id: int,
        effect_serial: int,
        remaining_contexts: tuple[int, ...],
        card_ids: tuple[int, ...] = (),
        target_serial: int | None = None,
        max_cards: int | None = None,
        metadata: tuple[tuple[str, int | str | bool], ...] = (),
        metadata_slots: tuple[str, ...] = (),
        card_groups: tuple[tuple[int, ...], ...] = (),
    ) -> "PendingIntent":
        contexts = tuple(int(context) for context in remaining_contexts)
        if effect_card_id is None or effect_serial is None or not contexts:
            raise ValueError("意図の発生元には効果ID・シリアル・選択contextが必要です。")
        return cls(
            kind=kind,
            card_ids=tuple(int(card_id) for card_id in card_ids),
            target_serial=target_serial,
            max_cards=max_cards,
            metadata=metadata,
            metadata_slots=tuple(str(key) for key in metadata_slots),
            card_groups=tuple(
                tuple(int(card_id) for card_id in group)
                for group in card_groups
            ),
            remaining_contexts=contexts,
            effect_card_id=int(effect_card_id),
            effect_serial=int(effect_serial),
            created_turn=int(view.current.get("turn", 0)),
            created_action_count=int(view.current.get("turnActionCount", 0)),
        )

    @classmethod
    def deferred_main_from_view(
        cls,
        view: GameView,
        *,
        kind: str,
        effect_card_id: int,
        effect_serial: int,
        main_context: int,
        card_ids: tuple[int, ...] = (),
        max_cards: int | None = None,
        metadata: tuple[tuple[str, int | str | bool], ...] = (),
        card_groups: tuple[tuple[int, ...], ...] = (),
    ) -> "PendingIntent":
        return cls.from_view(
            view,
            kind=kind,
            card_ids=card_ids,
            max_cards=max_cards,
            metadata=((_DEFERRED_MAIN_METADATA_KEY, True), *metadata),
            card_groups=card_groups,
            effect_card_id=effect_card_id,
            effect_serial=effect_serial,
            remaining_contexts=(int(main_context),),
        )

    @classmethod
    def retreat_from_view(
        cls,
        view: GameView,
        *,
        origin_option_position: int,
        target_serial: int,
        retreat_cost: int,
        metadata: tuple[tuple[str, int | str | bool], ...] = (),
    ) -> "PendingIntent":
        option = next(
            (
                candidate
                for candidate in view.options
                if candidate.position == int(origin_option_position)
            ),
            None,
        )
        if option is None or option.type != int(OptionType.RETREAT):
            raise ValueError("退却意図は選択済みRETREAT optionからのみ作成できます。")
        cost = int(retreat_cost)
        if cost < 0:
            raise ValueError("退却コストは0以上である必要があります。")
        contexts = (
            (int(SelectContext.SWITCH),)
            if cost == 0
            else (int(SelectContext.DISCARD_ENERGY), int(SelectContext.SWITCH))
        )
        return cls(
            kind="RETREAT",
            target_serial=int(target_serial),
            metadata=(("retreat_cost", cost), *metadata),
            remaining_contexts=contexts,
            created_turn=int(view.current.get("turn", 0)),
            created_action_count=int(view.current.get("turnActionCount", 0)),
            origin_option_position=int(origin_option_position),
        )

    @property
    def is_retreat_provenance(self) -> bool:
        return (
            self.kind == "RETREAT"
            and self.effect_card_id is None
            and self.effect_serial is None
            and self.origin_option_position is not None
        )

    @property
    def has_complete_origin(self) -> bool:
        return (
            (
                self.is_retreat_provenance
                or (
                    self.effect_card_id is not None
                    and self.effect_serial is not None
                )
            )
            and self.created_turn is not None
            and self.created_action_count is not None
            and bool(self.remaining_contexts)
        )

    @property
    def is_deferred_main(self) -> bool:
        return (
            len(self.remaining_contexts) == 1
            and any(
                name == _DEFERRED_MAIN_METADATA_KEY and value is True
                for name, value in self.metadata
            )
        )

    def matches_deferred_main(self, view: GameView) -> bool:
        if not self.has_complete_origin or not self.is_deferred_main:
            return False
        context = int(view.select.get("context", -1))
        if (
            int(view.select.get("type", -1)) != int(SelectType.MAIN)
            or context != int(SelectContext.MAIN)
            or context != int(self.remaining_contexts[0])
            or int(view.current.get("turn", -1)) != int(self.created_turn)
            or (
                int(view.current.get("turnActionCount", -1))
                - int(self.created_action_count)
            )
            != 1
        ):
            return False
        return any(
            option.type == int(OptionType.PLAY)
            and option.card_id == int(self.effect_card_id)
            and option.card_serial == int(self.effect_serial)
            for option in view.options
        )

    def matches(self, view: GameView) -> bool:
        if self.is_retreat_provenance:
            return False
        context = int(view.select.get("context", 0))
        if not self.has_complete_origin or context == 0:
            return False
        if int(view.current.get("turn", -1)) != int(self.created_turn):
            return False
        action_delta = (
            int(view.current.get("turnActionCount", -1))
            - int(self.created_action_count)
        )
        if action_delta < 1 or action_delta > len(self.remaining_contexts):
            return False
        if context != int(self.remaining_contexts[action_delta - 1]):
            return False
        effect = view.select.get("effect")
        if self.effect_card_id is not None and (
            not isinstance(effect, dict)
            or effect.get("id") is None
            or int(effect["id"]) != int(self.effect_card_id)
        ):
            return False
        if self.effect_serial is not None and (
            not isinstance(effect, dict)
            or effect.get("serial") is None
            or int(effect["serial"]) != int(self.effect_serial)
        ):
            return False
        return True

    def matches_retreat(self, view: GameView) -> bool:
        if not self.has_complete_origin or not self.is_retreat_provenance:
            return False
        if view.select.get("effect") is not None:
            return False
        if int(view.current.get("turn", -1)) != int(self.created_turn):
            return False
        action_delta = (
            int(view.current.get("turnActionCount", -1))
            - int(self.created_action_count)
        )
        if action_delta < 1 or action_delta > len(self.remaining_contexts):
            return False
        context = int(view.select.get("context", -1))
        if context != int(self.remaining_contexts[action_delta - 1]):
            return False
        metadata = dict(self.metadata)
        cost = int(metadata.get("retreat_cost", -1))
        if context == int(SelectContext.DISCARD_ENERGY):
            return (
                int(view.select.get("type", -1)) == int(SelectType.ENERGY)
                and cost > 0
                and int(view.select.get("minCount", -1)) == cost
                and int(view.select.get("maxCount", -1)) == cost
            )
        if context == int(SelectContext.SWITCH):
            return (
                int(view.select.get("type", -1)) == int(SelectType.CARD)
                and int(view.select.get("minCount", -1)) == 1
                and int(view.select.get("maxCount", -1)) == 1
            )
        return False

    def advance(
        self,
        view: GameView,
        steps: int = 1,
        *,
        metadata_additions: tuple[tuple[str, int | str | bool], ...] = (),
    ) -> "PendingIntent | None":
        if steps < 1:
            raise ValueError("意図の進行数は1以上である必要があります。")
        if not self.matches(view) or len(self.remaining_contexts) <= steps:
            return None
        additions = tuple((str(key), value) for key, value in metadata_additions)
        keys = tuple(key for key, _ in additions)
        if len(keys) != len(set(keys)):
            raise ValueError("継続意図のmetadataキーが重複しています。")
        existing_keys = {key for key, _ in self.metadata}
        if any(key in existing_keys or key not in self.metadata_slots for key in keys):
            raise ValueError("継続意図に許可されていないmetadata更新があります。")
        return replace(
            self,
            metadata=(*self.metadata, *additions),
            metadata_slots=tuple(
                key for key in self.metadata_slots if key not in keys
            ),
            remaining_contexts=self.remaining_contexts[steps:],
            created_action_count=int(view.current.get("turnActionCount", -1)),
        )

    def matches_continuation(
        self,
        view: GameView,
        continuation: "PendingIntent",
    ) -> bool:
        if continuation.metadata[:len(self.metadata)] != self.metadata:
            return False
        additions = continuation.metadata[len(self.metadata):]
        try:
            expected = self.advance(view, metadata_additions=additions)
        except ValueError:
            return False
        return expected is not None and continuation == expected


class IntentUpdate(str, Enum):
    UNCHANGED = "unchanged"
    SET = "set"
    CLEAR = "clear"


@dataclass(frozen=True)
class Proposal:
    option_indices: tuple[int, ...]
    tier: DecisionTier
    score: int
    reason: str
    rule_ids: tuple[str, ...]
    capability: CapabilityVector = CapabilityVector()
    next_intent: PendingIntent | None = None
    intent_update: IntentUpdate = IntentUpdate.UNCHANGED
    facts: tuple[tuple[str, int | str | bool], ...] = ()
    memory_update: object | None = None

    def __post_init__(self) -> None:
        if self.intent_update is IntentUpdate.SET:
            if self.next_intent is None:
                raise ValueError("IntentUpdate.SETにはnext_intentが必要です。")
            if not self.next_intent.has_complete_origin:
                raise ValueError("SETする意図には完全な発生元が必要です。")
        elif self.next_intent is not None:
            raise ValueError(
                f"IntentUpdate.{self.intent_update.name}には"
                "next_intentを指定できません。"
            )
