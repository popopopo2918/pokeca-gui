from __future__ import annotations

import ctypes
import importlib.util
import json
import os
import random
import sys
import traceback
from collections import Counter
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
from cg.sim import lib  # noqa: E402


AgentFn = Callable[[dict[str, Any]], list[int]]
MAX_AUTO_STEPS = 10000

# Shared search context used to branch a battle for undo ("指し直し"). Created lazily
# because AgentStart allocates native memory even when undo is never used.
AGENT_PTR: int | None = None


def agent_ptr() -> int:
    global AGENT_PTR
    if AGENT_PTR is None:
        AGENT_PTR = lib.AgentStart()
    return AGENT_PTR

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
        # Undo support. Each history entry is the state right before one selection:
        # {"obs": dict, "search_id": int | None, "human": bool, "main": bool}
        self.history: list[dict[str, Any]] = []
        # None while the real battle is live; a search node id once the game has been
        # branched by an undo (play then continues inside the search tree).
        self.search_id: int | None = None
        self.search_used = False
        self.deck_lists: list[list[int]] = [[], []]
        # Last hand actually observed per player, used to rebuild hidden info on undo.
        self.known_hands: dict[int, list[int]] = {}

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

        self.deck_lists = [list(deck0), list(deck1)]
        self.set_obs(obs)
        self.active = True
        auto_steps = self.play_ai_turns()
        return self.snapshot([obs, *auto_steps])

    def select(self, selection: list[int]) -> dict[str, Any]:
        if not self.active:
            raise RuntimeError("No active CABT battle.")
        ability = ability_logs_for(self.obs, selection)
        selected_step = self.do_select(selection, human=True)
        prepend_logs(selected_step, ability)
        auto_steps = self.play_ai_turns()
        return self.snapshot([selected_step, *auto_steps])

    def state(self) -> dict[str, Any]:
        return self.snapshot()

    def do_select(self, selection: list[int], human: bool) -> dict[str, Any]:
        """Apply one selection (live battle or search branch) and record undo history."""
        entry = {
            "obs": self.obs,
            "search_id": self.search_id,
            "human": human,
            "main": is_main_select(self.obs),
        }
        if self.search_id is None:
            new_obs = battle_select(selection)
        else:
            new_obs = self.search_select(selection)
        self.history.append(entry)
        self.set_obs(new_obs)
        return new_obs

    def search_select(self, selection: list[int]) -> dict[str, Any]:
        raw = lib.SearchStep(
            agent_ptr(),
            self.search_id,
            (ctypes.c_int * len(selection))(*selection),
            len(selection),
        )
        result = json.loads(raw)
        if result.get("error", 0) != 0:
            raise RuntimeError(search_error_message(result["error"]))
        state = result["state"]
        self.search_id = state["searchId"]
        return state["observation"]

    def undo(self, count: int = 1) -> dict[str, Any]:
        """Rewind to the player's Nth previous main-phase decision and resume play there.

        The native engine cannot restore a battle, so the game is re-seeded into the
        search tree (SearchBegin) from the recorded observation. Hidden information
        (deck order, prizes, unseen hands) is re-randomized consistently with the
        known deck lists.
        """
        if not self.active:
            raise RuntimeError("No active CABT battle.")
        count = max(1, int(count))
        popped = 0
        last_error: Exception | None = None
        for index in range(len(self.history) - 1, -1, -1):
            entry = self.history[index]
            if not (entry["human"] and entry["main"]):
                continue
            popped += 1
            if popped < count:
                continue
            try:
                restored = self.restore(entry)
            except Exception as error:  # try an earlier decision point instead
                last_error = error
                continue
            self.history = self.history[:index]
            return self.snapshot([restored])
        if last_error is not None:
            raise RuntimeError(f"指し直しできる場面が見つかりませんでした: {last_error}")
        raise RuntimeError("これ以上戻せる手がありません。")

    def restore(self, entry: dict[str, Any]) -> dict[str, Any]:
        if entry["search_id"] is not None:
            obs = dict(entry["obs"])
            obs["logs"] = []
            self.search_id = entry["search_id"]
            self.set_obs(obs)
            return obs
        obs, search_id = self.search_begin_from(entry["obs"])
        obs = dict(obs)
        obs["logs"] = []
        self.search_id = search_id
        self.search_used = True
        self.set_obs(obs)
        return obs

    def search_begin_from(self, obs: dict[str, Any]) -> tuple[dict[str, Any], int]:
        """Branch the recorded battle state into the search tree, predicting hidden zones."""
        sbi = obs.get("search_begin_input")
        current = obs.get("current")
        if not sbi or not current:
            raise RuntimeError("この場面には局面データがありません。")
        if current.get("looking"):
            raise RuntimeError("カードを公開中の場面には戻せません。")
        you = current["yourIndex"]
        opp = 1 - you
        players = current["players"]
        rng = random.Random()
        pools = [self.remaining_pool(pi, current) for pi in (0, 1)]

        opp_hand = self.predict_hand(opp, players[opp], pools[opp], rng)
        your_prize = predict_prize(players[you], pools[you], rng)
        opp_prize = predict_prize(players[opp], pools[opp], rng)
        your_deck = drain_pool(pools[you], rng)
        opp_deck = drain_pool(pools[opp], rng)
        if len(your_deck) != players[you]["deckCount"] or len(opp_deck) != players[opp]["deckCount"]:
            raise RuntimeError("山札の枚数を再構成できませんでした。")

        opp_active = []
        active = players[opp].get("active") or []
        if active and active[0] is None:
            opp_active = [pick_basic_pokemon([*opp_hand, *opp_deck])]

        raw = lib.SearchBegin(
            agent_ptr(),
            sbi.encode("ascii"),
            len(sbi),
            (ctypes.c_int * len(your_deck))(*your_deck),
            (ctypes.c_int * len(your_prize))(*your_prize),
            (ctypes.c_int * len(opp_deck))(*opp_deck),
            (ctypes.c_int * len(opp_prize))(*opp_prize),
            (ctypes.c_int * len(opp_hand))(*opp_hand),
            (ctypes.c_int * len(opp_active))(*opp_active),
            0,
        )
        result = json.loads(raw)
        if result.get("error", 0) != 0:
            raise RuntimeError(search_error_message(result["error"], begin=True))
        state = result["state"]
        return state["observation"], state["searchId"]

    def remaining_pool(self, player_index: int, current: dict[str, Any]) -> Counter:
        """Cards of a player's deck list not visible on the board: deck + prizes + unseen hand."""
        counts = Counter(self.deck_lists[player_index])

        def take(card: dict[str, Any] | None) -> None:
            if not card:
                return
            card_id = card.get("id")
            if isinstance(card_id, int) and card_id >= 0:
                if counts[card_id] <= 0:
                    raise RuntimeError(f"カードID {card_id} がデッキリストと一致しません。")
                counts[card_id] -= 1
            for key in ("energyCards", "tools", "preEvolution"):
                for sub in card.get(key) or []:
                    take(sub)

        player = current["players"][player_index]
        for zone in ("active", "bench"):
            for card in player.get(zone) or []:
                take(card)
        for card in player.get("discard") or []:
            take(card)
        for card in player.get("hand") or []:
            take(card)
        for card in player.get("prize") or []:
            if card:
                take(card)
        for card in current.get("stadium") or []:
            if card and card.get("playerIndex") == player_index:
                take(card)
        return counts

    def predict_hand(self, player_index: int, player: dict[str, Any], pool: Counter, rng: random.Random) -> list[int]:
        """Predict a hidden hand: prefer the hand last seen for that player, fill randomly."""
        if player.get("hand"):
            hand = [card["id"] for card in player["hand"] if card and isinstance(card.get("id"), int)]
            for card_id in hand:
                if pool[card_id] > 0:
                    pool[card_id] -= 1
            return hand
        hand_count = player.get("handCount", 0)
        hand: list[int] = []
        for card_id in self.known_hands.get(player_index, []):
            if len(hand) >= hand_count:
                break
            if pool[card_id] > 0:
                pool[card_id] -= 1
                hand.append(card_id)
        while len(hand) < hand_count:
            hand.append(draw_random(pool, rng))
        return hand

    def set_obs(self, obs: dict[str, Any] | None) -> None:
        self.obs = obs
        current = (obs or {}).get("current")
        for player_index, player in enumerate((current or {}).get("players") or []):
            hand = player.get("hand")
            if hand is not None:
                self.known_hands[player_index] = [
                    card["id"] for card in hand if card and isinstance(card.get("id"), int)
                ]

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
            step = self.do_select(action, human=False)
            prepend_logs(step, ability)
            auto_steps.append(step)
        raise RuntimeError(f"AI auto-play limit exceeded ({MAX_AUTO_STEPS} selections).")

    def undo_count(self) -> int:
        return sum(1 for entry in self.history if entry["human"] and entry["main"])

    def snapshot(self, auto_steps: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        return {
            "ok": True,
            "observation": self.obs,
            "autoSteps": auto_steps or [],
            "undoCount": self.undo_count(),
            "cards": [to_jsonable(card) for card in all_card_data()],
            "attacks": [to_jsonable(attack) for attack in all_attack()],
        }

    def close(self) -> None:
        if self.active:
            try:
                battle_finish()
            except Exception:
                pass
        if self.search_used and AGENT_PTR is not None:
            try:
                lib.SearchEnd(AGENT_PTR)
            except Exception:
                pass
        self.obs = None
        self.agent_controlled = [False, True]
        self.active = False
        self.history = []
        self.search_id = None
        self.search_used = False
        self.deck_lists = [[], []]
        self.known_hands = {}


def is_main_select(obs: dict[str, Any] | None) -> bool:
    select = (obs or {}).get("select")
    return bool(select) and select.get("type") == 0 and select.get("context") == 0


def predict_prize(player: dict[str, Any], pool: Counter, rng: random.Random) -> list[int]:
    prize: list[int] = []
    for card in player.get("prize") or []:
        card_id = (card or {}).get("id")
        if isinstance(card_id, int) and card_id >= 0:
            prize.append(card_id)
        else:
            prize.append(draw_random(pool, rng))
    return prize


def drain_pool(pool: Counter, rng: random.Random) -> list[int]:
    cards = list(pool.elements())
    rng.shuffle(cards)
    pool.clear()
    return cards


def draw_random(pool: Counter, rng: random.Random) -> int:
    cards = list(pool.elements())
    if not cards:
        raise RuntimeError("非公開カードの再構成に必要なカードが不足しています。")
    card_id = rng.choice(cards)
    pool[card_id] -= 1
    return card_id


BASIC_POKEMON_IDS: set[int] | None = None


def pick_basic_pokemon(candidates: list[int]) -> int:
    global BASIC_POKEMON_IDS
    if BASIC_POKEMON_IDS is None:
        BASIC_POKEMON_IDS = {card.cardId for card in all_card_data() if getattr(card, "basic", False)}
    for card_id in candidates:
        if card_id in BASIC_POKEMON_IDS:
            return card_id
    raise RuntimeError("相手のバトルポケモンを推定できませんでした。")


def search_error_message(code: int, begin: bool = False) -> str:
    if begin:
        messages = {
            1: "無効なカードIDが含まれています。",
            2: "バトル場のカードはポケモンである必要があります。",
            30: "検索コンテキストが壊れています。",
        }
    else:
        messages = {
            1: "指定した局面が見つかりません。",
            2: "解放済みの局面です。",
            3: "対戦が終了しているため選択できません。",
            4: "選択数が範囲外です。",
            5: "選択肢の番号が範囲外です。",
            6: "選択肢の番号が重複しています。",
            30: "検索コンテキストが壊れています。",
        }
    return messages.get(code, f"検索エンジンでエラーが発生しました (code {code})。")


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
    if command == "undo":
        return session.undo(message.get("count", 1))
    if command == "state":
        return session.state()
    if command == "close":
        session.close()
        return {"ok": True}
    raise ValueError(f"Unknown bridge command: {command}")


def main() -> None:
    # The bridge speaks JSON over stdio with a Node parent that reads/writes UTF-8;
    # never rely on the platform default (cp932 on Japanese Windows breaks card names).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")
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
