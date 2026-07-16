from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path


VIEWER_ROOT = Path(__file__).resolve().parents[1]
DESTINATION = VIEWER_ROOT / "public" / "agents" / "alakazam-playbook"
TOP_LEVEL_FILES = (
    "main.py",
    "cards.py",
    "catalog.py",
    "memory.py",
    "model.py",
    "policy.py",
    "proposals.py",
    "rule_manifest.py",
    "strategy_config.py",
    "deck.csv",
)
REQUIRED_RULE_FILES = (
    "__init__.py",
    "attack.py",
    "development.py",
    "draw_engine.py",
    "evolution.py",
    "fallback.py",
    "poke_pad.py",
    "prompts.py",
    "protection.py",
    "recovery.py",
    "search.py",
    "setup.py",
    "telepath.py",
)


def resolve_source(viewer_root: Path, environ: Mapping[str, str]) -> Path:
    override = environ.get("CABT_SAMPLE_A_SOURCE_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (
        viewer_root
        / ".."
        / ".."
        / "PTCG-AI"
        / "src"
        / "agent"
        / "sample_a"
    ).resolve()


def validate_source(source: Path) -> tuple[Path, ...]:
    required = [source / name for name in TOP_LEVEL_FILES]
    required.extend(source / "rules" / name for name in REQUIRED_RULE_FILES)
    missing = [path for path in required if not path.is_file()]
    if missing:
        rendered = "\n".join(f"- {path}" for path in missing)
        raise FileNotFoundError(f"sample_aの必須ファイルがありません:\n{rendered}")

    deck_rows = [
        line.strip()
        for line in (source / "deck.csv").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(deck_rows) != 60:
        raise ValueError(
            f"sample_a/deck.csvは60枚である必要があります: {len(deck_rows)}枚"
        )
    invalid = [row for row in deck_rows if not row.isdecimal() or int(row) <= 0]
    if invalid:
        raise ValueError(
            f"sample_a/deck.csvに不正なカードIDがあります: {invalid[0]}"
        )

    runtime_files = [source / name for name in TOP_LEVEL_FILES]
    runtime_files.extend(sorted((source / "rules").glob("*.py")))
    return tuple(runtime_files)


def sync_agent(source: Path, destination: Path) -> tuple[Path, ...]:
    source = source.resolve()
    runtime_files = validate_source(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    backup = destination.with_name(f".{destination.name}.backup")

    with tempfile.TemporaryDirectory(
        prefix=f".{destination.name}.",
        dir=destination.parent,
    ) as work:
        staged = Path(work) / destination.name
        staged.mkdir()
        for source_file in runtime_files:
            relative = source_file.relative_to(source)
            target = staged / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, target)

        if backup.exists():
            shutil.rmtree(backup)
        if destination.exists():
            os.replace(destination, backup)
        try:
            os.replace(staged, destination)
        except Exception:
            if backup.exists() and not destination.exists():
                os.replace(backup, destination)
            raise
        if backup.exists():
            shutil.rmtree(backup)

    return tuple(
        sorted(
            path.relative_to(destination)
            for path in destination.rglob("*")
            if path.is_file()
        )
    )


def main() -> None:
    source = resolve_source(VIEWER_ROOT, os.environ)
    copied = sync_agent(source, DESTINATION)
    print(
        f"sample_a同期完了: {source} -> {DESTINATION} "
        f"({len(copied)} files)"
    )


if __name__ == "__main__":
    main()
