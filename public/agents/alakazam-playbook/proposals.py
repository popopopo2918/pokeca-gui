from dataclasses import dataclass, replace
from enum import Enum
from typing import Callable


@dataclass(frozen=True)
class PendingIntent:
    kind: str
    card_ids: tuple[int, ...] = ()
    target_serial: int | None = None
    max_cards: int | None = None
    metadata: tuple[tuple[str, int | str | bool], ...] = ()
    card_groups: tuple[tuple[int, ...], ...] = ()
    remaining_contexts: tuple[int, ...] = ()
    effect_card_id: int | None = None
    effect_serial: int | None = None
    created_turn: int | None = None
    created_action_count: int | None = None

    @classmethod
    def from_view(
        cls,
        view,
        *,
        kind: str,
        effect_card_id: int,
        effect_serial: int,
        remaining_contexts: tuple[int, ...],
        card_ids: tuple[int, ...] = (),
        target_serial: int | None = None,
        max_cards: int | None = None,
        metadata: tuple[tuple[str, int | str | bool], ...] = (),
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

    @property
    def has_complete_origin(self) -> bool:
        return (
            self.effect_card_id is not None
            and self.effect_serial is not None
            and self.created_turn is not None
            and self.created_action_count is not None
            and bool(self.remaining_contexts)
        )

    def matches(self, view) -> bool:
        context = int(view.select.get("context", 0))
        if not self.has_complete_origin or context == 0:
            return False
        if context != int(self.remaining_contexts[0]):
            return False
        if int(view.current.get("turn", -1)) != int(self.created_turn):
            return False
        if int(view.current.get("turnActionCount", -1)) != int(self.created_action_count) + 1:
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

    def advance(self, view) -> "PendingIntent | None":
        if not self.matches(view) or len(self.remaining_contexts) <= 1:
            return None
        return replace(
            self,
            remaining_contexts=self.remaining_contexts[1:],
            created_action_count=int(view.current.get("turnActionCount", -1)),
        )


class IntentUpdate(str, Enum):
    UNCHANGED = "unchanged"
    SET = "set"
    CLEAR = "clear"


@dataclass(frozen=True)
class Proposal:
    option_indices: tuple[int, ...]
    priority: int
    reason: str
    rule_ids: tuple[str, ...]
    next_intent: PendingIntent | None = None
    alternative: str = ""
    intent_update: IntentUpdate | None = None

    def __post_init__(self) -> None:
        update = self.intent_update
        if update is None:
            update = (
                IntentUpdate.SET
                if self.next_intent is not None
                else IntentUpdate.UNCHANGED
            )
            object.__setattr__(self, "intent_update", update)
        if update is IntentUpdate.SET and self.next_intent is None:
            raise ValueError("SETにはnext_intentが必要です。")
        if update is IntentUpdate.CLEAR and self.next_intent is not None:
            raise ValueError("CLEARにnext_intentは指定できません。")


def covers(*rule_ids: str) -> Callable:
    def decorate(function: Callable) -> Callable:
        function.source_rule_ids = tuple(rule_ids)
        return function

    return decorate
