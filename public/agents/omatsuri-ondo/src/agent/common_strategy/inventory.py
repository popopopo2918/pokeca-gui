from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from .contracts import DeckContract
from .model import GameView

if TYPE_CHECKING:
    from .memory import AgentMemory


def update_known_cards(
    view: GameView,
    memory: AgentMemory,
    contract: DeckContract,
) -> None:
    """Update only facts visible to the player or publicly revealed."""
    direct_prizes = _visible_own_prize_counts(view)
    complete_deck = view.complete_known_deck_ids

    if complete_deck is not None:
        memory.known_deck_counts = Counter(complete_deck)
        memory.known_absent_deck_ids = {
            card_id
            for card_id in contract.counts
            if memory.known_deck_counts[card_id] == 0
        }
        memory.known_snapshot_deck_count = _own_deck_count(view)
        memory.known_snapshot_prize_count = view.own_prize_count
        memory.known_snapshot_generation = _observation_generation(view)
        inferred_prizes = _infer_prize_counts(
            contract,
            view.own_non_prize_card_ids,
            complete_deck,
            view.own_prize_count,
        )
        memory.known_prize_counts = (
            direct_prizes if inferred_prizes is None else inferred_prizes
        )
    elif _reconcile_exact_snapshot(view, memory, contract):
        pass
    else:
        _invalidate_exact_snapshot(memory)
        memory.known_prize_counts = direct_prizes

    memory.opponent_public_card_ids.update(view.opponent_public_card_ids)
    memory.opponent_public_card_ids.update(view.opponent_discard_ids)


def possible_deck_count(
    card_id: int,
    view: GameView,
    memory: AgentMemory,
    contract: DeckContract,
) -> int:
    """Return the possible count in the own deck from legally known facts."""
    card_id = int(card_id)
    if _exact_snapshot_is_current(view, memory):
        assert memory.known_deck_counts is not None
        return memory.known_deck_counts[card_id]
    if memory.known_deck_counts is not None:
        _invalidate_exact_snapshot(memory)
        memory.known_prize_counts = _visible_own_prize_counts(view)

    known_outside_deck = Counter(view.own_non_prize_card_ids)
    known_outside_deck.update(memory.known_prize_counts)
    return max(0, int(contract.counts.get(card_id, 0)) - known_outside_deck[card_id])


def _visible_own_prize_counts(view: GameView) -> Counter[int]:
    return Counter(
        int(card["id"])
        for card in (view.own.get("prize") or [])
        if isinstance(card, dict) and card.get("id") is not None
    )


def _infer_prize_counts(
    contract: DeckContract,
    own_non_prize_card_ids: tuple[int, ...],
    complete_deck_ids: tuple[int, ...],
    own_prize_count: int,
) -> Counter[int] | None:
    remaining = Counter(contract.deck)
    remaining.subtract(own_non_prize_card_ids)
    remaining.subtract(complete_deck_ids)
    if any(count < 0 for count in remaining.values()):
        return None
    if sum(remaining.values()) != int(own_prize_count):
        return None
    return Counter({card_id: count for card_id, count in remaining.items() if count > 0})


def _reconcile_exact_snapshot(
    view: GameView,
    memory: AgentMemory,
    contract: DeckContract,
) -> bool:
    """Carry a legally seen full-deck snapshot through public card moves.

    Once a search exposes the complete own deck, the prize identities are
    deducible from the registered deck and every other own card is visible to
    its controller.  While the prize count is unchanged, subtracting those
    exact prize cards and the current public zones from the deck contract
    yields the exact post-draw/search deck multiset without hidden input.
    """

    if (
        memory.known_deck_counts is None
        or memory.known_snapshot_prize_count != view.own_prize_count
        or sum(memory.known_prize_counts.values()) != view.own_prize_count
    ):
        return False

    remaining = Counter(contract.deck)
    remaining.subtract(view.own_non_prize_card_ids)
    remaining.subtract(memory.known_prize_counts)
    if any(count < 0 for count in remaining.values()):
        return False
    if sum(remaining.values()) != _own_deck_count(view):
        return False

    memory.known_deck_counts = Counter({
        card_id: count
        for card_id, count in remaining.items()
        if count > 0
    })
    memory.known_absent_deck_ids = {
        card_id
        for card_id in contract.counts
        if memory.known_deck_counts[card_id] == 0
    }
    memory.known_snapshot_deck_count = _own_deck_count(view)
    memory.known_snapshot_prize_count = view.own_prize_count
    memory.known_snapshot_generation = _observation_generation(view)
    return True


def _exact_snapshot_is_current(
    view: GameView,
    memory: AgentMemory,
) -> bool:
    return (
        memory.known_deck_counts is not None
        and memory.known_snapshot_deck_count == _own_deck_count(view)
        and memory.known_snapshot_prize_count == view.own_prize_count
        and memory.known_snapshot_generation == _observation_generation(view)
    )


def _invalidate_exact_snapshot(memory: AgentMemory) -> None:
    memory.known_deck_counts = None
    memory.known_absent_deck_ids.clear()
    memory.known_snapshot_deck_count = None
    memory.known_snapshot_prize_count = None
    memory.known_snapshot_generation = None
    memory.known_prize_counts.clear()


def _own_deck_count(view: GameView) -> int:
    return int(view.own.get("deckCount", 0))


def _observation_generation(view: GameView) -> tuple[object, ...]:
    own_non_prize_counts = Counter(view.own_non_prize_card_ids)
    visible_prize_counts = _visible_own_prize_counts(view)
    return (
        int(view.current.get("turn", 0)),
        int(view.current.get("turnActionCount", 0)),
        _own_deck_count(view),
        view.own_prize_count,
        tuple(sorted(own_non_prize_counts.items())),
        tuple(sorted(visible_prize_counts.items())),
        view.complete_known_deck_ids,
    )
