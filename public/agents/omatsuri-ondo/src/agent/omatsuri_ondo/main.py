from __future__ import annotations

from pathlib import Path
import sys


def _resolve_project_root() -> Path:
    source_path = globals().get("__file__")
    if source_path is not None:
        return Path(source_path).resolve().parents[3]
    candidates = (Path.cwd(), Path("/kaggle_simulations/agent"))
    return next(
        (
            candidate
            for candidate in candidates
            if (candidate / "src" / "agent" / "omatsuri_ondo").is_dir()
        ),
        candidates[-1],
    )


_PROJECT_ROOT = str(_resolve_project_root())
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.agent.omatsuri_ondo.cards import DECK
from src.agent.omatsuri_ondo.policy import AgentSession


_session: AgentSession | None = None


def _current_session() -> AgentSession:
    global _session
    if _session is None:
        _session = AgentSession()
    return _session


def reset_session_for_test() -> None:
    global _session
    _session = None


def agent(obs_dict: dict) -> list[int]:
    global _session
    if obs_dict.get("select") is None:
        _session = None
        return list(DECK)
    return _current_session().decide(obs_dict)
