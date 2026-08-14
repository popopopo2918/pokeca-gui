from .catalog import AttackMeta, CardCatalog, CardMeta
from .contracts import DeckContract
from .deck_safety import DeckBudget, proposal_is_deck_safe
from .inventory import possible_deck_count, update_known_cards
from .model import (
    Area,
    CardRef,
    EnergyType,
    GameView,
    LegalOption,
    OptionType,
    PokemonRef,
    SelectContext,
    SelectType,
)


def __getattr__(name: str) -> object:
    """Load the legacy planner memory only for agents that request it.

    The compiled agents import the package-level public model, but must not
    pull the proposal/search object graph into their runtime bundle.
    """
    if name == "AgentMemory":
        from .memory import AgentMemory

        return AgentMemory
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "Area",
    "AgentMemory",
    "AttackMeta",
    "CardCatalog",
    "CardMeta",
    "CardRef",
    "DeckBudget",
    "DeckContract",
    "EnergyType",
    "GameView",
    "LegalOption",
    "OptionType",
    "PokemonRef",
    "SelectContext",
    "SelectType",
    "possible_deck_count",
    "proposal_is_deck_safe",
    "update_known_cards",
]
