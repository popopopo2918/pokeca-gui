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
        if int(view.current.get("turn", -1)) != int(self.created_turn):
            return False
        action_delta = (
            int(view.current.get("turnActionCount", -1))
            - int(self.created_action_count)
        )
        # Hilda/Dawnのような複数画面効果では、該当カテゴリが山札にないと
        # CABTがその画面を内部で飛ばし、actionCountだけを進める。
        # 効果ID・カードserial・手番が一致する間だけ、残り画面数までの
        # 飛び越しを許可する。単一画面の意図は従来どおり厳密に+1のみ。
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

    def advance(self, view, steps: int = 1) -> "PendingIntent | None":
        if steps < 1:
            raise ValueError("意図の進行数は1以上である必要があります。")
        if not self.matches(view) or len(self.remaining_contexts) <= steps:
            return None
        return replace(
            self,
            remaining_contexts=self.remaining_contexts[steps:],
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
    intent_advance_steps: int = 1

    def __post_init__(self) -> None:
        if int(self.intent_advance_steps) < 1:
            raise ValueError("意図の進行数は1以上である必要があります。")
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
