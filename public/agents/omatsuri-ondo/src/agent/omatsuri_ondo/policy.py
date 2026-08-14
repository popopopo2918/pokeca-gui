from __future__ import annotations

from pathlib import Path
import sys


_OMATSURI_ROOT = Path(__file__).resolve().parent
_AGENT_ROOT = _OMATSURI_ROOT.parent
for _path in (str(_OMATSURI_ROOT), str(_AGENT_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from common_strategy import CardCatalog, GameView

from omatsuri_ondo.board import OMATSURI_DECK_CONTRACT
from omatsuri_ondo.compiled.memory import CompiledMemory
from omatsuri_ondo.compiled.preparation_policy import PROGRAM
from omatsuri_ondo.compiled.runtime import CompiledPolicyRuntime
from omatsuri_ondo.compiled.schema import PolicyProgram


class AgentSession:
    """One match of the generated policy; no planning runs in this class."""

    def __init__(
        self,
        *,
        catalog: CardCatalog | None = None,
        program: PolicyProgram = PROGRAM,
    ) -> None:
        self.catalog = catalog or CardCatalog.from_cg()
        self.deck_contract = OMATSURI_DECK_CONTRACT
        self.memory = CompiledMemory()
        self.runtime = CompiledPolicyRuntime(program)

    def decide(self, obs_dict: dict) -> list[int]:
        view = GameView.from_observation(obs_dict, self.catalog)
        return list(self.runtime.decide(view, self.memory))


def decision_key(
    view: GameView,
    memory: CompiledMemory,
) -> tuple[object, ...]:
    return memory.decision_key(view)


def validate_selection(
    view: GameView | dict,
    indices: list[int] | tuple[int, ...],
) -> tuple[int, ...]:
    select = view.select if isinstance(view, GameView) else view
    values = tuple(int(index) for index in indices)
    options = tuple(select.get("option") or ())
    minimum = max(0, int(select.get("minCount", 0)))
    maximum = max(0, int(select.get("maxCount", len(options))))
    if not minimum <= len(values) <= maximum:
        raise ValueError("選択枚数がprompt範囲外です。")
    if len(values) != len(set(values)):
        raise ValueError("同じoptionを重複して選んでいます。")
    if any(index < 0 or index >= len(options) for index in values):
        raise ValueError("存在しないoption indexです。")
    return values
