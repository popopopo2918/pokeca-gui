from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BRIDGE_PATH = ROOT / "src" / "engine" / "cabt_bridge.py"


def load_bridge():
    cg = types.ModuleType("cg")
    cg.__path__ = []

    api = types.ModuleType("cg.api")
    api.all_attack = lambda: []
    api.all_card_data = lambda: []

    game = types.ModuleType("cg.game")
    game.battle_finish = lambda: None
    game.battle_select = lambda _selection: {}
    game.battle_start = lambda *_args, **_kwargs: None
    game.visualize_data = lambda *_args, **_kwargs: ""

    sim = types.ModuleType("cg.sim")
    sim.lib = types.SimpleNamespace()

    sys.modules.update(
        {
            "cg": cg,
            "cg.api": api,
            "cg.game": game,
            "cg.sim": sim,
        }
    )

    spec = importlib.util.spec_from_file_location("cabt_bridge_under_test", BRIDGE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load bridge module: {BRIDGE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeSession:
    active = True

    def snapshot(self):
        return {
            "ok": True,
            "observation": {"turn": 4, "select": {"context": 0}},
            "autoSteps": [],
            "undoCount": 2,
            "trueHands": {"0": [{"id": 1001}]},
            "truePrizes": {"1": [{"id": 2001}]},
        }


class BridgeRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bridge = load_bridge()

    def test_display_ability_log_does_not_mutate_native_observation(self):
        native_log = {"type": 1, "playerIndex": 0}
        native = {"logs": [native_log], "turn": 4}
        ability = {"type": "ability", "playerIndex": 1}

        display = self.bridge.prepend_logs(native, [ability])

        self.assertEqual(native["logs"], [native_log])
        self.assertIsNot(display, native)
        self.assertEqual(display["logs"], [ability, native_log])

    def test_error_response_keeps_latest_session_snapshot(self):
        builder = getattr(self.bridge, "build_error_response", None)
        self.assertTrue(callable(builder), "build_error_response must be implemented")

        try:
            raise ValueError("agent failed")
        except ValueError as error:
            response = builder(FakeSession(), error)

        self.assertFalse(response["ok"])
        self.assertEqual(response["error"], "agent failed")
        self.assertIn("ValueError: agent failed", response["traceback"])
        self.assertEqual(response["observation"]["turn"], 4)
        self.assertEqual(response["undoCount"], 2)
        self.assertEqual(response["trueHands"], {"0": [{"id": 1001}]})
        self.assertEqual(response["truePrizes"], {"1": [{"id": 2001}]})


if __name__ == "__main__":
    unittest.main()
