from __future__ import annotations

import importlib.util
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any, Callable


FRONTEND_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = FRONTEND_ROOT.parent
SAMPLE_SUBMISSION = Path(
    os.environ.get(
        "CABT_SAMPLE_SUBMISSION_DIR",
        FRONTEND_ROOT / "sample_submission",
    )
).resolve()
sys.path.insert(0, str(SAMPLE_SUBMISSION))

from cg.api import all_attack, all_card_data  # noqa: E402
from cg.game import battle_finish, battle_select, battle_start  # noqa: E402


AgentFn = Callable[[dict[str, Any]], list[int]]
MAX_AUTO_STEPS = 10000

# CABT does not emit a dedicated "ability used" log, so we synthesize one whenever an ABILITY option
# is selected (by a human or an agent). The option's area/index locate the source Pokemon.
CABT_OPTION_ABILITY = 10
CABT_AREA_ACTIVE = 4
CABT_AREA_BENCH = 5


def ability_logs_for(obs_before: dict[str, Any] | None, action: Any) -> list[dict[str, Any]]:
    select = (obs_before or {}).get("select")
    if not select or not isinstance(action, list):
        return []
    options = select.get("option") or []
    current = (obs_before or {}).get("current") or {}
    players = current.get("players") or []
    default_pi = current.get("yourIndex")
    logs: list[dict[str, Any]] = []
    for idx in action:
        if not isinstance(idx, int) or idx < 0 or idx >= len(options):
            continue
        opt = options[idx]
        if opt.get("type") != CABT_OPTION_ABILITY:
            continue
        pi = opt.get("playerIndex")
        if pi is None:
            pi = default_pi
        card = None
        area = opt.get("area")
        index = opt.get("index")
        if isinstance(pi, int) and 0 <= pi < len(players) and isinstance(index, int):
            zone = None
            if area == CABT_AREA_ACTIVE:
                zone = players[pi].get("active")
            elif area == CABT_AREA_BENCH:
                zone = players[pi].get("bench")
            if zone and 0 <= index < len(zone):
                card = zone[index]
        entry: dict[str, Any] = {"type": "ability", "playerIndex": pi}
        if card and card.get("id") is not None:
            entry["cardId"] = card.get("id")
        elif opt.get("cardId") is not None:
            entry["cardId"] = opt.get("cardId")
        if card and card.get("serial") is not None:
            entry["serial"] = card.get("serial")
        logs.append(entry)
    return logs


def prepend_logs(obs: dict[str, Any] | None, logs: list[dict[str, Any]]) -> None:
    if obs is not None and logs:
        obs["logs"] = logs + (obs.get("logs") or [])


def to_jsonable(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return {field: to_jsonable(getattr(value, field)) for field in value.__dataclass_fields__}
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if hasattr(value, "value"):
        return value.value
    return value


def first_legal_agent(obs: dict[str, Any]) -> list[int]:
    select = obs.get("select")
    if select is None:
        raise RuntimeError("The bridge expected preselected decks before battle start.")
    return list(range(select["maxCount"]))


def load_agent(agent_path: str | None) -> AgentFn:
    if not agent_path:
        return first_legal_agent

    raw_path = Path(agent_path)
    if raw_path.is_absolute():
        path = raw_path.resolve()
    else:
        frontend_path = (FRONTEND_ROOT / raw_path).resolve()
        path = frontend_path if frontend_path.exists() else (WORKSPACE_ROOT / raw_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Agent file not found: {path}")

    old_cwd = Path.cwd()
    sys.path.insert(0, str(path.parent))
    try:
        os.chdir(path.parent)
        module_name = f"cabt_agent_{abs(hash(str(path)))}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not import agent: {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    finally:
        os.chdir(old_cwd)
        try:
            sys.path.remove(str(path.parent))
        except ValueError:
            pass

    agent = getattr(module, "agent", None)
    if not callable(agent):
        raise AttributeError(f"{path} does not export callable agent(obs)")
    return agent


class Session:
    def __init__(self) -> None:
        self.obs: dict[str, Any] | None = None
        self.agents: list[AgentFn] = [first_legal_agent, first_legal_agent]
        self.agent_controlled = [False, True]
        self.active = False

    def start(
        self,
        deck0: list[int],
        deck1: list[int],
        agent_paths: list[str | None],
        agent_controlled: list[bool],
    ) -> dict[str, Any]:
        self.close()
        self.agent_controlled = normalize_agent_controlled(agent_controlled)
        self.agents = [load_agent(path) for path in normalize_agent_paths(agent_paths)]
        obs, start_data = battle_start(deck0, deck1)
        if obs is None or not start_data.battlePtr:
            return {
                "ok": False,
                "error": (
                    "battle_start failed: "
                    f"errorPlayer={start_data.errorPlayer}, errorType={start_data.errorType}"
                ),
            }

        self.obs = obs
        self.active = True
        auto_steps = self.play_ai_turns()
        return self.snapshot([obs, *auto_steps])

    def select(self, selection: list[int]) -> dict[str, Any]:
        if not self.active:
            raise RuntimeError("No active CABT battle.")
        ability = ability_logs_for(self.obs, selection)
        selected_step = battle_select(selection)
        prepend_logs(selected_step, ability)
        self.obs = selected_step
        auto_steps = self.play_ai_turns()
        return self.snapshot([selected_step, *auto_steps])

    def state(self) -> dict[str, Any]:
        return self.snapshot()

    def play_ai_turns(self) -> list[dict[str, Any]]:
        auto_steps: list[dict[str, Any]] = []
        for _ in range(MAX_AUTO_STEPS):
            if not self.obs:
                return auto_steps
            current = self.obs.get("current")
            select = self.obs.get("select")
            if not current or current.get("result", -1) >= 0 or select is None:
                return auto_steps
            player_index = current.get("yourIndex")
            if player_index not in (0, 1) or not self.agent_controlled[player_index]:
                return auto_steps
            action = self.agents[player_index](self.obs)
            ability = ability_logs_for(self.obs, action)
            self.obs = battle_select(action)
            prepend_logs(self.obs, ability)
            auto_steps.append(self.obs)
        raise RuntimeError(f"AI auto-play limit exceeded ({MAX_AUTO_STEPS} selections).")

    def snapshot(self, auto_steps: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        return {
            "ok": True,
            "observation": self.obs,
            "autoSteps": auto_steps or [],
            "cards": [to_jsonable(card) for card in all_card_data()],
            "attacks": [to_jsonable(attack) for attack in all_attack()],
        }

    def close(self) -> None:
        if self.active:
            try:
                battle_finish()
            except Exception:
                pass
        self.obs = None
        self.agent_controlled = [False, True]
        self.active = False


def normalize_agent_paths(agent_paths: Any) -> list[str | None]:
    if not isinstance(agent_paths, list):
        return [None, None]
    return [
        agent_paths[0] if len(agent_paths) > 0 and isinstance(agent_paths[0], str) else None,
        agent_paths[1] if len(agent_paths) > 1 and isinstance(agent_paths[1], str) else None,
    ]


def normalize_agent_controlled(agent_controlled: Any) -> list[bool]:
    if not isinstance(agent_controlled, list):
        return [False, True]
    return [
        bool(agent_controlled[0]) if len(agent_controlled) > 0 else False,
        bool(agent_controlled[1]) if len(agent_controlled) > 1 else True,
    ]


def handle(session: Session, message: dict[str, Any]) -> dict[str, Any]:
    command = message.get("command")
    if command == "start":
        agent_paths = message.get("agentPaths")
        agent_controlled = message.get("agentControlled")
        if not isinstance(agent_paths, list):
            agent_paths = [None, message.get("agentPath")]
        if not isinstance(agent_controlled, list):
            agent_controlled = [False, not bool(message.get("manualOpponent"))]
        return session.start(
            message["deck0"],
            message["deck1"],
            agent_paths,
            agent_controlled,
        )
    if command == "select":
        return session.select(message["selection"])
    if command == "state":
        return session.state()
    if command == "close":
        session.close()
        return {"ok": True}
    raise ValueError(f"Unknown bridge command: {command}")


def main() -> None:
    session = Session()
    for line in sys.stdin:
        try:
            message = json.loads(line)
            response = handle(session, message)
        except Exception as error:
            response = {
                "ok": False,
                "error": str(error),
                "traceback": traceback.format_exc(),
            }
        response["id"] = message.get("id") if "message" in locals() else None
        print(json.dumps(response, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
