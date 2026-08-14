from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SYNC_PATH = ROOT / "scripts" / "sync_project_agents.py"


def load_sync_module():
    if not SYNC_PATH.is_file():
        return None
    spec = importlib.util.spec_from_file_location("sync_project_agents_under_test", SYNC_PATH)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SyncProjectAgentsTests(unittest.TestCase):
    @staticmethod
    def make_source(root: Path) -> Path:
        agent_root = root / "src" / "agent"
        omatsuri = agent_root / "omatsuri_ondo"
        omatsuri.mkdir(parents=True)
        (omatsuri / "deck.csv").write_text(
            "\n".join(str(700 + index) for index in range(60)) + "\n",
            encoding="utf-8",
        )
        (omatsuri / "build_bundle.py").write_text(
            "from pathlib import Path\n"
            "import shutil\n"
            "SOURCE = Path(__file__).resolve().parent\n"
            "def stage_python_runtime(destination, *, top_level_main, include_deck):\n"
            "    destination = Path(destination)\n"
            "    package = destination / 'src' / 'agent' / 'omatsuri_ondo'\n"
            "    package.mkdir(parents=True)\n"
            "    (package / '__init__.py').write_text('', encoding='utf-8')\n"
            "    (package / 'main.py').write_text('def agent(obs): return []\\n', encoding='utf-8')\n"
            "    if top_level_main:\n"
            "        (destination / 'main.py').write_text('from src.agent.omatsuri_ondo.main import agent\\n', encoding='utf-8')\n"
            "    if include_deck:\n"
            "        shutil.copy2(SOURCE / 'deck.csv', destination / 'deck.csv')\n"
            "        shutil.copy2(SOURCE / 'deck.csv', package / 'deck.csv')\n"
            "    return destination\n",
            encoding="utf-8",
        )
        return agent_root

    def test_sync_script_stages_exact_gui_safe_canonical_runtime(self):
        sync = load_sync_module()
        self.assertIsNotNone(sync, "scripts/sync_project_agents.py must exist")

        with tempfile.TemporaryDirectory() as work:
            canonical = self.make_source(Path(work))
            destination_root = Path(work) / "public" / "agents"
            copied = sync.sync_omatsuri_agent(canonical, destination_root)
            actual = destination_root / "omatsuri-ondo"

            self.assertEqual(len((actual / "deck.csv").read_text().splitlines()), 60)
            self.assertEqual(
                set(copied),
                {
                    Path("deck.csv"),
                    Path("main.py"),
                    Path("src/agent/omatsuri_ondo/__init__.py"),
                    Path("src/agent/omatsuri_ondo/deck.csv"),
                    Path("src/agent/omatsuri_ondo/main.py"),
                },
            )
            self.assertEqual(
                (actual / "main.py").read_text(encoding="utf-8"),
                "from src.agent.omatsuri_ondo.main import agent\n",
            )
            self.assertFalse((actual / "cg").exists())
            self.assertFalse(any("tests" in path.parts for path in actual.rglob("*")))
            self.assertFalse(any("rules" in path.parts for path in actual.rglob("*.py")))
            self.assertFalse(
                any(
                    path.suffix.lower() in {".dll", ".so", ".dylib", ".pyc"}
                    for path in actual.rglob("*")
                    if path.is_file()
                )
            )

    def test_explicit_source_override_wins(self):
        sync = load_sync_module()
        self.assertIsNotNone(sync, "scripts/sync_project_agents.py must exist")
        expected = Path("C:/canonical-agent-root").resolve()
        self.assertEqual(
            sync.resolve_agent_root(ROOT, {"CABT_PROJECT_AGENT_ROOT": str(expected)}),
            expected,
        )


if __name__ == "__main__":
    unittest.main()
