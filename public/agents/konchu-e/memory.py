from collections import Counter
from dataclasses import dataclass, field

from cards import CardId, DECK_COUNTS
from environment_profiles import ArchetypeProfile, assess_archetype
from proposals import PendingIntent, covers


_DECK_SEARCH_EFFECT_IDS = frozenset({
    int(CardId.BUDDY_BUDDY_POFFIN),
    int(CardId.POKE_PAD),
    int(CardId.FAN_ROTOM),
    int(CardId.TELEPATH_PSYCHIC_ENERGY),
    int(CardId.HILDA),
    int(CardId.DAWN),
    int(CardId.TEAM_ROCKETS_PETREL),
})
_MULTI_SCREEN_SEARCH_EFFECT_IDS = frozenset({
    int(CardId.HILDA),
    int(CardId.DAWN),
})
_PUBLIC_OPPONENT_LOG_TYPES = frozenset({10, 12, 15})
_ATTACK_LOG_TYPE = 15
_OWN_ATTACK_LINE_IDS = frozenset({
    int(CardId.ABRA),
    int(CardId.KADABRA),
    int(CardId.ALAKAZAM),
})


def known_deck_may_contain(memory, card_id: int | CardId) -> bool:
    """最後に確認した山札で0枚と確定していないカードだけを検索候補にする。"""
    if int(card_id) in memory.known_absent_deck_ids:
        return False
    if memory.known_deck is None:
        return True
    return memory.known_deck.get(int(card_id), 0) > 0


def possible_deck_count(view, memory, card_id: int | CardId) -> int:
    """公開済みカードと最後の山札確認から、山札に残り得る最大枚数を返す。"""
    value = int(card_id)
    if (
        memory is not None
        and value in memory.known_absent_deck_ids
    ):
        return 0
    deck_total = DECK_COUNTS.get(value)
    if deck_total is None:
        return 0
    visible = Counter(int(visible_id) for visible_id in view.own_non_prize_card_ids)
    public_upper_bound = max(0, int(deck_total) - visible[value])
    own = getattr(view, "own", None)
    if isinstance(own, dict):
        public_upper_bound = min(
            public_upper_bound,
            max(0, int(own.get("deckCount", 0))),
        )
    known_deck = None if memory is None else memory.known_deck
    if known_deck is None:
        return public_upper_bound
    return min(public_upper_bound, max(0, known_deck.get(value, 0)))


def card_may_be_in_deck(view, memory, card_id: int | CardId) -> bool:
    return possible_deck_count(view, memory, card_id) > 0


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


def _own_field_ids_by_serial(view) -> dict[int, int]:
    """場のトップカードだけを記録し、1匹の進化系統を1回のKOとして数える。"""
    return {
        int(pokemon.serial): int(pokemon.id)
        for pokemon in getattr(view, "field", ())
        if pokemon.serial is not None
    }


@dataclass(frozen=True)
class PublicOpponentAction:
    turn: int
    log_type: int
    card_id: int | None
    card_serial: int | None
    target_card_id: int | None
    target_serial: int | None
    attack_id: int | None


@dataclass
class AgentMemory:
    last_turn: int | None = None
    pending_intent: PendingIntent | None = None
    reserved_attacker_serial: int | None = None
    protected_abra_serial: int | None = None
    known_deck: Counter[int] | None = None
    known_absent_deck_ids: set[int] = field(default_factory=set)
    known_prize_ids: Counter[int] = field(default_factory=Counter)
    opponent_public_card_ids: set[int] = field(default_factory=set)
    opponent_attacker_ids: set[int] = field(default_factory=set)
    opponent_profile: ArchetypeProfile | None = None
    opponent_profile_candidates: set[str] = field(default_factory=set)
    opponent_actions: list[PublicOpponentAction] = field(default_factory=list)
    seen_public_log_keys: set[tuple] = field(default_factory=set)
    unfair_stamp_possible: bool = True
    trace: list[dict] = field(default_factory=list)
    last_action_count: int | None = None
    last_context: int | None = None
    last_own_deck_count: int | None = None
    last_seen_own_serials: set[int] = field(default_factory=set)
    last_seen_own_field_ids: dict[int, int] = field(default_factory=dict)
    last_own_prize_count: int | None = None
    last_opponent_prize_count: int | None = None
    opponent_prize_drop_pending: bool = False
    fezandipiti_draw_turn: int | None = None
    own_knockout_history_complete: bool = False
    own_total_knockouts: int = 0
    own_attack_line_knockouts: int = 0

    def start_new_game(self) -> None:
        self.last_turn = None
        self.pending_intent = None
        self.reserved_attacker_serial = None
        self.protected_abra_serial = None
        self.known_deck = None
        self.known_absent_deck_ids.clear()
        self.known_prize_ids.clear()
        self.opponent_public_card_ids.clear()
        self.opponent_attacker_ids.clear()
        self.opponent_profile = None
        self.opponent_profile_candidates.clear()
        self.opponent_actions.clear()
        self.seen_public_log_keys.clear()
        self.unfair_stamp_possible = True
        self.trace.clear()
        self.last_action_count = None
        self.last_context = None
        self.last_own_deck_count = None
        self.last_seen_own_serials.clear()
        self.last_seen_own_field_ids.clear()
        self.last_own_prize_count = None
        self.last_opponent_prize_count = None
        self.opponent_prize_drop_pending = False
        self.fezandipiti_draw_turn = None
        self.own_knockout_history_complete = False
        self.own_total_knockouts = 0
        self.own_attack_line_knockouts = 0

    def observe_turn(self, turn: int) -> None:
        if self.last_turn is not None and turn < self.last_turn:
            self.start_new_game()
        self.last_turn = turn

    def discard_stale_intent(self, view) -> None:
        if self.pending_intent is not None and not (
            self.pending_intent.matches(view)
            or self.pending_intent.matches_deferred_main(view)
        ):
            self.pending_intent = None

    def observe_game(self, view) -> None:
        turn = int(view.current.get("turn", 0))
        action_count = int(view.current.get("turnActionCount", 0))
        context = int(view.select.get("context", 0))
        own_deck_count = int(view.own.get("deckCount", 0))
        own_serials = _own_visible_serials(view.own)
        own_field_ids = _own_field_ids_by_serial(view)
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

        if (
            self.last_own_deck_count is not None
            and own_deck_count > self.last_own_deck_count
        ):
            # せいなるはい・手札干渉などで山札へカードが戻ると、
            # 以前の「0枚」という確認結果は正しくなくなる。
            self.known_deck = None
            self.known_absent_deck_ids.clear()

        own_prize_count = len(view.own.get("prize") or ())
        self.last_own_prize_count = own_prize_count

        opponent = getattr(view, "opponent", None)
        opponent_prize_count = (
            None
            if not isinstance(opponent, dict)
            else len(opponent.get("prize") or ())
        )
        if opponent_prize_count is not None:
            if self.last_opponent_prize_count is None:
                self.own_knockout_history_complete = opponent_prize_count == 6
            if (
                self.last_opponent_prize_count is not None
                and opponent_prize_count < self.last_opponent_prize_count
            ):
                self.opponent_prize_drop_pending = True
                if self.own_knockout_history_complete:
                    knocked_out_ids = tuple(
                        card_id
                        for serial, card_id in self.last_seen_own_field_ids.items()
                        if serial not in own_field_ids
                    )
                    if knocked_out_ids:
                        self.own_total_knockouts += len(knocked_out_ids)
                        self.own_attack_line_knockouts += sum(
                            int(card_id) in _OWN_ATTACK_LINE_IDS
                            for card_id in knocked_out_ids
                        )
                    else:
                        # 観測を飛び越してKO対象を特定できなかった場合は、
                        # 不完全な履歴を確定情報として使わない。
                        self.own_knockout_history_complete = False
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
        self.last_own_deck_count = own_deck_count
        self.last_seen_own_serials.clear()
        self.last_seen_own_serials.update(own_serials)
        self.last_seen_own_field_ids.clear()
        self.last_seen_own_field_ids.update(own_field_ids)
        self.observe_search_options(view)
        self.discard_stale_intent(view)

    def observe_search_options(self, view) -> None:
        """公開された検索候補から、要求カードが山札に0枚だった事実を記録する。"""
        intent = self.pending_intent
        if intent is None or not intent.matches(view):
            return
        effect_id = int(intent.effect_card_id or -1)
        if effect_id not in _DECK_SEARCH_EFFECT_IDS:
            return

        target_ids: tuple[int, ...]
        if effect_id in _MULTI_SCREEN_SEARCH_EFFECT_IDS and intent.card_groups:
            group_index = len(intent.card_groups) - len(intent.remaining_contexts)
            if not 0 <= group_index < len(intent.card_groups):
                return
            target_ids = tuple(
                int(card_id) for card_id in intent.card_groups[group_index]
            )
        else:
            target_ids = tuple(int(card_id) for card_id in intent.card_ids)
        if not target_ids:
            return

        available_ids = {
            int(option.card_id)
            for option in view.options
            if option.card_id is not None
        }
        for card_id in target_ids:
            if card_id in available_ids:
                self.known_absent_deck_ids.discard(card_id)
            elif card_id in DECK_COUNTS:
                self.known_absent_deck_ids.add(card_id)

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

    def observe_public_opponent(self, view) -> None:
        # CABTのlogsは直前遷移の増分で、同じ観測が再送される間だけ同じ束が
        # 再掲される。同一serialのポケモンが別ターンに同じワザを使う行動は
        # 別件なので、観測ターンを重複キーに含める。
        turn = int(view.current.get("turn", 0))
        opponent_index = 1 - int(view.own_index)
        for log in view.raw.get("logs") or ():
            if not isinstance(log, dict):
                continue
            try:
                log_type = int(log.get("type", -1))
            except (TypeError, ValueError):
                # GUIの表示専用ログはCABTの公開行動ではないため無視する。
                continue
            if (
                log_type not in _PUBLIC_OPPONENT_LOG_TYPES
                or int(log.get("playerIndex", -1)) != opponent_index
            ):
                continue
            card_id = (
                None if log.get("cardId") is None else int(log["cardId"])
            )
            card_serial = (
                None if log.get("serial") is None else int(log["serial"])
            )
            target_card_id = (
                None
                if log.get("cardIdTarget") is None
                else int(log["cardIdTarget"])
            )
            target_serial = (
                None
                if log.get("serialTarget") is None
                else int(log["serialTarget"])
            )
            attack_id = (
                None if log.get("attackId") is None else int(log["attackId"])
            )
            key = (
                turn,
                log_type,
                card_id,
                card_serial,
                target_card_id,
                target_serial,
                attack_id,
            )
            if key in self.seen_public_log_keys:
                continue
            self.seen_public_log_keys.add(key)
            self.opponent_actions.append(PublicOpponentAction(
                turn=turn,
                log_type=log_type,
                card_id=card_id,
                card_serial=card_serial,
                target_card_id=target_card_id,
                target_serial=target_serial,
                attack_id=attack_id,
            ))
            if log_type == _ATTACK_LOG_TYPE and card_id is not None:
                self.opponent_attacker_ids.add(card_id)

        self.observe_public_opponent_cards(
            set(view.opponent_public_card_ids),
            set(view.opponent_discard_ids),
            set(view.opponent_public_ace_spec_ids),
        )
        assessment = assess_archetype(
            set(self.opponent_public_card_ids),
            set(self.opponent_attacker_ids),
        )
        self.opponent_profile = assessment.profile
        self.opponent_profile_candidates.clear()
        self.opponent_profile_candidates.update(assessment.candidate_keys)


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
    memory.known_absent_deck_ids = {
        int(card_id)
        for card_id in DECK_COUNTS
        if candidate_known_deck.get(int(card_id), 0) <= 0
    }
