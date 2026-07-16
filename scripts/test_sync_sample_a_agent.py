from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sync_sample_a_agent import (
    REQUIRED_RULE_FILES,
    TOP_LEVEL_FILES,
    resolve_source,
    sync_agent,
)


class SyncSampleAAgentTest(unittest.TestCase):
    def make_source(self, root: Path, deck_size: int = 60) -> Path:
        source = root / "sample_a"
        source.mkdir()
        for name in TOP_LEVEL_FILES:
            target = source / name
            if name == "deck.csv":
                target.write_text(
                    "\n".join(str(700 + index) for index in range(deck_size)) + "\n",
                    encoding="utf-8",
                )
            else:
                target.write_text(f"# {name}\n", encoding="utf-8")
        rules = source / "rules"
        rules.mkdir()
        for name in REQUIRED_RULE_FILES:
            (rules / name).write_text(f"# rules/{name}\n", encoding="utf-8")
        (source / "evaluate.py").write_text(
            "raise RuntimeError('excluded')\n",
            encoding="utf-8",
        )
        (source / "artifacts").mkdir()
        (source / "artifacts" / "report.json").write_text("{}\n", encoding="utf-8")
        (source / "cg").mkdir()
        (source / "cg" / "cg.dll").write_bytes(b"native-binary")
        (rules / "__pycache__").mkdir()
        return source

    def test_resolve_source_uses_explicit_environment_override(self) -> None:
        viewer = Path("C:/viewer")
        expected = Path("C:/agent-source").resolve()
        self.assertEqual(
            resolve_source(viewer, {"CABT_SAMPLE_A_SOURCE_DIR": str(expected)}),
            expected,
        )

    def test_sync_copies_only_runtime_python_and_sixty_card_deck(self) -> None:
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            source = self.make_source(root)
            destination = root / "public" / "agents" / "alakazam-playbook"
            copied = sync_agent(source, destination)

            self.assertEqual(
                len(
                    (destination / "deck.csv")
                    .read_text(encoding="utf-8")
                    .splitlines()
                ),
                60,
            )
            self.assertTrue((destination / "main.py").is_file())
            self.assertTrue((destination / "rules" / "attack.py").is_file())
            self.assertFalse((destination / "evaluate.py").exists())
            self.assertFalse((destination / "artifacts").exists())
            self.assertFalse((destination / "cg").exists())
            self.assertFalse((destination / "rules" / "__pycache__").exists())
            self.assertEqual(
                copied,
                tuple(
                    sorted(
                        path.relative_to(destination)
                        for path in destination.rglob("*")
                        if path.is_file()
                    )
                ),
            )

    def test_missing_runtime_file_is_reported_before_destination_changes(self) -> None:
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            source = self.make_source(root)
            (source / "policy.py").unlink()
            destination = root / "public" / "agents" / "alakazam-playbook"
            destination.mkdir(parents=True)
            marker = destination / "keep.txt"
            marker.write_text("existing\n", encoding="utf-8")

            with self.assertRaisesRegex(FileNotFoundError, "policy.py"):
                sync_agent(source, destination)

            self.assertEqual(marker.read_text(encoding="utf-8"), "existing\n")

    def test_invalid_deck_does_not_replace_existing_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            source = self.make_source(root, deck_size=59)
            destination = root / "public" / "agents" / "alakazam-playbook"
            destination.mkdir(parents=True)
            marker = destination / "keep.txt"
            marker.write_text("existing\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "60枚"):
                sync_agent(source, destination)

            self.assertEqual(marker.read_text(encoding="utf-8"), "existing\n")


if __name__ == "__main__":
    unittest.main()
