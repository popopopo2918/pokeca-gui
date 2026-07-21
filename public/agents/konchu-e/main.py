from __future__ import annotations

from pathlib import Path
import sys


def _resolve_agent_root() -> Path:
    source_path = globals().get("__file__")
    if source_path is None:
        return Path("/kaggle_simulations/agent")
    return Path(source_path).resolve().parent


_AGENT_ROOT = str(_resolve_agent_root())


def _ensure_agent_root_on_path() -> None:
    if _AGENT_ROOT not in sys.path:
        sys.path.insert(0, _AGENT_ROOT)


_ensure_agent_root_on_path()

from cards import DECK
from policy import AgentSession
from strategy_config import PREFER_FIRST


_session: AgentSession | None = None


def _current_session() -> AgentSession:
    global _session
    if _session is None:
        _session = AgentSession(prefer_first=PREFER_FIRST)
    return _session


def reset_session_for_test() -> None:
    global _session
    _session = None


def agent(obs_dict: dict) -> list[int]:
    """CABT entry point for the deterministic Alakazam rule agent."""
    global _session
    _ensure_agent_root_on_path()
    if obs_dict.get("select") is None:
        _session = None
        return list(DECK)
    return _current_session().decide(obs_dict)
