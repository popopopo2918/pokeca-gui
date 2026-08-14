from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from common_strategy import (
    Area,
    DeckContract,
    GameView,
    OptionType,
    update_known_cards,
)
from common_strategy.model import LogType

from ..board import OMATSURI_DECK_CONTRACT
from ..cards import AttackId, CardId


@dataclass
class CompiledMemory:
    """Only public, finite runtime state used by the compiled policy.

    This object deliberately has no reachability goal, proposal, score, or rule
    callback.  It can therefore be shipped with the generated decision DAG
    without bringing the development-time planner into a match.
    """

    known_deck_counts: Counter[int] | None = None
    known_prize_counts: Counter[int] = field(default_factory=Counter)
    known_absent_deck_ids: set[int] = field(default_factory=set)
    known_snapshot_deck_count: int | None = None
    known_snapshot_prize_count: int | None = None
    known_snapshot_generation: tuple[object, ...] | None = None
    opponent_public_card_ids: set[int] = field(default_factory=set)
    trace: list[dict[str, object]] = field(default_factory=list)
    continuation_id: int = 0
    supporter_available: bool = True
    attachment_available: bool = True
    retreat_available: bool = True
    unused_thwackey_serials: tuple[int, ...] = ()
    first_attack_source_serial: int | None = None
    first_hit_resolved: bool = False
    damage_support: int = 0
    played_card_ids_this_turn: tuple[int, ...] = ()
    bench_ko_dominance_committed: bool = False
    attacker_generations_used: int = 0
    previous_opponent_knockout_turn: int | None = None
    replay_cache: dict[tuple[object, ...], tuple[int, ...]] = field(
        default_factory=dict
    )
    unknown_state_count: int = 0
    fallback_count: int = 0
    _observed_own_turn: int | None = field(default=None, repr=False, compare=False)
    _used_thwackey_serials: set[int] = field(
        default_factory=set,
        repr=False,
        compare=False,
    )
    _seen_public_events: set[tuple[object, ...]] = field(
        default_factory=set,
        repr=False,
        compare=False,
    )

    def observe(
        self,
        view: GameView,
        contract: DeckContract = OMATSURI_DECK_CONTRACT,
    ) -> None:
        update_known_cards(view, self, contract)
        self._reconcile_turn_resources(view)
        self._observe_previous_opponent_knockout(view)
        self._observe_dipplin_attack(view)

    def record_thwackey_used(self, serial: int) -> None:
        serial = int(serial)
        if self._observed_own_turn is None:
            return
        self._used_thwackey_serials.add(serial)
        self.unused_thwackey_serials = tuple(
            value for value in self.unused_thwackey_serials if value != serial
        )

    def record_attack_selected(
        self,
        source_serial: int,
        *,
        attack_id: int = int(AttackId.DIPPLIN_DO_THE_WAVE),
    ) -> None:
        if self._observed_own_turn is None:
            return
        if self.first_attack_source_serial is None:
            self.first_attack_source_serial = int(source_serial)
            if int(attack_id) == int(AttackId.DIPPLIN_DO_THE_WAVE):
                self.attacker_generations_used += 1

    def record_card_played(self, card_id: int) -> None:
        value = int(card_id)
        self.played_card_ids_this_turn = tuple(sorted((
            *self.played_card_ids_this_turn,
            value,
        )))

    def record_first_hit_resolved(self, source_serial: int) -> None:
        self.record_attack_selected(source_serial)
        if self.first_attack_source_serial == int(source_serial):
            self.first_hit_resolved = True

    def remember(
        self,
        key: tuple[object, ...],
        selected: tuple[int, ...] | list[int],
    ) -> None:
        self.replay_cache[key] = tuple(int(value) for value in selected)

    def replay(self, key: tuple[object, ...]) -> tuple[int, ...] | None:
        return self.replay_cache.get(key)

    def decision_key(self, view: GameView) -> tuple[object, ...]:
        """Fingerprint one prompt without consuming opponent hidden identity."""
        return (
            "omatsuri-compiled-prompt-v1",
            int(view.current.get("turn", 0)),
            int(view.current.get("turnActionCount", 0)),
            int(view.select.get("type", -1)),
            int(view.select.get("context", -1)),
            int(view.select.get("minCount", 0)),
            int(view.select.get("maxCount", 0)),
            _effect_fingerprint(view.select.get("effect")),
            tuple(_public_option_fingerprint(option) for option in view.options),
        )

    def public_fingerprint(self) -> tuple[object, ...]:
        return (
            "omatsuri-compiled-memory-v1",
            int(self.continuation_id),
            _counter_fingerprint(self.known_deck_counts),
            _counter_fingerprint(self.known_prize_counts),
            tuple(sorted(int(value) for value in self.known_absent_deck_ids)),
            self.known_snapshot_deck_count,
            self.known_snapshot_prize_count,
            bool(self.supporter_available),
            bool(self.attachment_available),
            bool(self.retreat_available),
            len(self.unused_thwackey_serials),
            bool(self.first_attack_source_serial is not None),
            bool(self.first_hit_resolved),
            int(self.damage_support),
            tuple(int(value) for value in self.played_card_ids_this_turn),
            bool(self.bench_ko_dominance_committed),
            int(self.attacker_generations_used),
            self.previous_opponent_knockout_turn,
            int(self.unknown_state_count),
            int(self.fallback_count),
        )

    def _reconcile_turn_resources(self, view: GameView) -> None:
        if not view.is_own_turn:
            return
        current_turn = int(view.current.get("turn", 0))
        new_turn = current_turn != self._observed_own_turn
        if new_turn:
            self._observed_own_turn = current_turn
            self._used_thwackey_serials.clear()
            self.first_attack_source_serial = None
            self.first_hit_resolved = False
            self.damage_support = 0
            self.played_card_ids_this_turn = ()
            self.bench_ko_dominance_committed = False

        supporter_unused = not bool(view.current.get("supporterPlayed", False))
        attachment_unused = not bool(view.current.get("energyAttached", False))
        retreat_unused = not bool(view.current.get("retreated", False))
        self.supporter_available = (
            supporter_unused
            if new_turn
            else self.supporter_available and supporter_unused
        )
        self.attachment_available = (
            attachment_unused
            if new_turn
            else self.attachment_available and attachment_unused
        )
        self.retreat_available = (
            retreat_unused
            if new_turn
            else self.retreat_available and retreat_unused
        )
        current_searchers = {
            int(pokemon.serial)
            for pokemon in view.own_field
            if (
                pokemon.id == int(CardId.THWACKEY)
                and pokemon.serial is not None
            )
        }
        self.unused_thwackey_serials = tuple(
            sorted(current_searchers - self._used_thwackey_serials)
        )

    def _observe_previous_opponent_knockout(self, view: GameView) -> None:
        opponent_index = 1 - int(view.own_index)
        opponent_attack_seen = False
        own_knockout_seen = False
        for log in view.raw.get("logs") or ():
            if not isinstance(log, dict):
                continue
            if (
                int(log.get("type", -1)) == int(LogType.ATTACK)
                and int(log.get("playerIndex", -1)) == opponent_index
            ):
                opponent_attack_seen = True
                continue
            if (
                opponent_attack_seen
                and int(log.get("type", -1)) == int(LogType.MOVE_CARD)
                and int(log.get("playerIndex", -1)) == int(view.own_index)
                and int(log.get("fromArea", -1))
                in (int(Area.ACTIVE), int(Area.BENCH))
                and int(log.get("toArea", -1)) == int(Area.DISCARD)
            ):
                own_knockout_seen = True
        if own_knockout_seen:
            current_turn = int(view.current.get("turn", 0))
            self.previous_opponent_knockout_turn = (
                current_turn - 1 if view.is_own_turn else current_turn
            )

    def _observe_dipplin_attack(self, view: GameView) -> None:
        # The first observation of a new own turn contains the previous own
        # attack followed by the opponent's whole turn.  Do not reinterpret
        # that historical log as this turn's first hit.  A current attack is
        # eligible to resolve only after this runtime selected its source in
        # the current turn.
        selected_source = self.first_attack_source_serial
        if not view.is_own_turn or selected_source is None:
            return
        for log in view.raw.get("logs") or ():
            if not isinstance(log, dict):
                continue
            if not (
                int(log.get("type", -1)) == int(LogType.ATTACK)
                and int(log.get("playerIndex", -1)) == int(view.own_index)
                and int(log.get("cardId", -1)) == int(CardId.DIPPLIN)
                and int(log.get("attackId", -1))
                == int(AttackId.DIPPLIN_DO_THE_WAVE)
            ):
                continue
            serial = int(log.get("serial", -1))
            if serial != int(selected_source):
                continue
            event = (
                "dipplin-attack",
                int(view.current.get("turn", 0)),
                serial,
                int(log.get("attackId", -1)),
            )
            if event in self._seen_public_events:
                continue
            self._seen_public_events.add(event)
            self.record_first_hit_resolved(serial)


def _public_option_fingerprint(option: object) -> tuple[object, ...]:
    raw = getattr(option, "raw")
    source = getattr(option, "source")
    target = getattr(option, "target")
    return (
        int(getattr(option, "type")),
        getattr(option, "card_id"),
        getattr(option, "card_serial"),
        None if source is None else int(source.id),
        None if source is None else source.serial,
        None if target is None else int(target.id),
        None if target is None else target.serial,
        getattr(option, "attack_id"),
        _optional_int(raw.get("area")),
        _optional_int(raw.get("index")),
        _optional_int(raw.get("inPlayArea")),
        _optional_int(raw.get("inPlayIndex")),
        _optional_int(raw.get("energyIndex")),
        _optional_int(raw.get("toolIndex")),
        _optional_int(raw.get("count")),
        int(getattr(option, "type")) == int(OptionType.END),
    )


def _optional_int(value: object) -> int | None:
    return None if value is None else int(value)


def _effect_fingerprint(value: object) -> tuple[int | None, int | None] | None:
    if not isinstance(value, dict):
        return None
    card_id = value.get("id", value.get("cardId"))
    serial = value.get("serial")
    return _optional_int(card_id), _optional_int(serial)


def _counter_fingerprint(counter: object) -> tuple[tuple[int, int], ...] | None:
    if counter is None:
        return None
    return tuple(
        sorted(
            (int(card_id), int(count))
            for card_id, count in getattr(counter, "items")()
            if int(count) > 0
        )
    )
