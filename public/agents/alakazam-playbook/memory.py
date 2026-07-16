from collections import Counter
from dataclasses import dataclass, field

from cards import CardId, DECK_COUNTS
from proposals import PendingIntent, covers


def _own_visible_serials(value: object) -> set[int]:
    serials: set[int] = set()
    if isinstance(value, dict):
        serial = value.get("serial")
        if serial is not None:
            serials.add(int(serial))
        for child in value.values():
            serials.update(_own_visible_serials(child))
    elif isinstance(value, (list, tuple)):
        for child in value:
            serials.update(_own_visible_serials(child))
    return serials


@dataclass
class AgentMemory:
    last_turn: int | None = None
    pending_intent: PendingIntent | None = None
    reserved_attacker_serial: int | None = None
    protected_abra_serial: int | None = None
    known_deck: Counter[int] | None = None
    known_prize_ids: Counter[int] = field(default_factory=Counter)
    opponent_public_card_ids: set[int] = field(default_factory=set)
    unfair_stamp_possible: bool = True
    trace: list[dict] = field(default_factory=list)
    last_action_count: int | None = None
    last_context: int | None = None
    last_seen_own_serials: set[int] = field(default_factory=set)
    last_opponent_prize_count: int | None = None
    opponent_prize_drop_pending: bool = False
    fezandipiti_draw_turn: int | None = None

    def start_new_game(self) -> None:
        self.last_turn = None
        self.pending_intent = None
        self.reserved_attacker_serial = None
        self.protected_abra_serial = None
        self.known_deck = None
        self.known_prize_ids.clear()
        self.opponent_public_card_ids.clear()
        self.unfair_stamp_possible = True
        self.trace.clear()
        self.last_action_count = None
        self.last_context = None
        self.last_seen_own_serials.clear()
        self.last_opponent_prize_count = None
        self.opponent_prize_drop_pending = False
        self.fezandipiti_draw_turn = None

    def observe_turn(self, turn: int) -> None:
        if self.last_turn is not None and turn < self.last_turn:
            self.start_new_game()
        self.last_turn = turn

    def discard_stale_intent(self, view) -> None:
        if self.pending_intent is not None and not self.pending_intent.matches(view):
            self.pending_intent = None

    def observe_game(self, view) -> None:
        turn = int(view.current.get("turn", 0))
        action_count = int(view.current.get("turnActionCount", 0))
        context = int(view.select.get("context", 0))
        own_serials = _own_visible_serials(view.own)
        same_observation = (
            self.last_turn == turn
            and self.last_action_count == action_count
            and self.last_context == context
            and self.last_seen_own_serials == own_serials
        )
        timeline_regressed = (
            self.last_turn is not None
            and (
                turn < self.last_turn
                or (
                    turn == self.last_turn
                    and self.last_action_count is not None
                    and action_count < self.last_action_count
                )
            )
        )
        is_first_restarted = (
            context == 41
            and self.last_turn is not None
            and not same_observation
        )
        own_serials_refreshed = (
            turn == 0
            and self.last_turn == 0
            and bool(self.last_seen_own_serials)
            and bool(own_serials)
            and self.last_seen_own_serials.isdisjoint(own_serials)
        )
        if timeline_regressed or is_first_restarted or own_serials_refreshed:
            self.start_new_game()

        opponent = getattr(view, "opponent", None)
        opponent_prize_count = (
            None
            if not isinstance(opponent, dict)
            else len(opponent.get("prize") or ())
        )
        if opponent_prize_count is not None:
            if (
                self.last_opponent_prize_count is not None
                and opponent_prize_count < self.last_opponent_prize_count
            ):
                self.opponent_prize_drop_pending = True
            self.last_opponent_prize_count = opponent_prize_count

        if bool(getattr(view, "is_own_turn", False)):
            own_turn = int(getattr(view, "own_turn_number", 0))
            if self.opponent_prize_drop_pending:
                self.fezandipiti_draw_turn = own_turn
                self.opponent_prize_drop_pending = False
            elif self.fezandipiti_draw_turn != own_turn:
                self.fezandipiti_draw_turn = None

        self.last_turn = turn
        self.last_action_count = action_count
        self.last_context = context
        self.last_seen_own_serials.clear()
        self.last_seen_own_serials.update(own_serials)
        self.discard_stale_intent(view)

    def observe_public_opponent_cards(
        self,
        card_ids: set[int],
        discard_ids: set[int],
        ace_spec_ids: set[int],
    ) -> None:
        self.opponent_public_card_ids.update(card_ids, discard_ids, ace_spec_ids)
        if int(CardId.UNFAIR_STAMP) in discard_ids or any(
            int(card_id) != int(CardId.UNFAIR_STAMP) for card_id in ace_spec_ids
        ):
            self.unfair_stamp_possible = False


@covers("PLAYBOOK-PRIZE-INFERENCE")
def update_known_deck_and_prizes(view, memory: AgentMemory) -> None:
    complete_deck = view.complete_known_deck_ids
    if complete_deck is None:
        return

    full_deck = Counter(
        {int(card_id): count for card_id, count in DECK_COUNTS.items()}
    )
    candidate_known_deck = Counter(int(card_id) for card_id in complete_deck)
    accounted = Counter(int(card_id) for card_id in view.own_non_prize_card_ids)
    accounted.update(candidate_known_deck)
    candidate_prizes = full_deck.copy()
    candidate_prizes.subtract(accounted)
    invalid = (
        any(card_id not in full_deck for card_id in accounted)
        or any(count > full_deck[card_id] for card_id, count in accounted.items())
        or any(count < 0 for count in candidate_prizes.values())
        or sum(candidate_prizes.values()) != int(view.own_prize_count)
    )
    if invalid:
        memory.known_deck = None
        memory.known_prize_ids.clear()
        return
    memory.known_deck, memory.known_prize_ids = (
        candidate_known_deck,
        +candidate_prizes,
    )
