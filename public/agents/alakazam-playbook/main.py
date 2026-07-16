from __future__ import annotations

from pathlib import Path
import sys


_AGENT_ROOT = str(Path(__file__).resolve().parent)
if _AGENT_ROOT not in sys.path:
    sys.path.insert(0, _AGENT_ROOT)

from cards import DECK
from policy import AgentSession
from strategy_config import PREFER_FIRST


_session: AgentSession | None = None


def _current_session() -> AgentSession:
    global _session
    if _session is None:
        _session = AgentSession(prefer_first=PREFER_FIRST)
    return _session


def agent(obs_dict: dict) -> list[int]:
    """CABT entry point for the deterministic Alakazam rule agent."""
    global _session
    if obs_dict.get("select") is None:
        _session = None
        return list(DECK)
    return _current_session().decide(obs_dict)


def reset_session_for_test() -> None:
    global _session
    _session = None
