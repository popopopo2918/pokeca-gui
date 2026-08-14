from dataclasses import dataclass


@dataclass(frozen=True)
class DeckBudget:
    current_deck: int
    forced_draw: int
    normal_draws_until_finish: int
    guaranteed_returns: int
    safety_margin: int

    @property
    def remaining_after_plan(self) -> int:
        return (
            self.current_deck
            - self.forced_draw
            - self.normal_draws_until_finish
            + self.guaranteed_returns
            - self.safety_margin
        )

    @property
    def safe(self) -> bool:
        return self.remaining_after_plan >= 0


def proposal_is_deck_safe(budget: DeckBudget) -> bool:
    """Expose the common safety predicate for a proposal's computed budget."""
    return budget.safe
