from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Callable


VIEWER_ROOT = Path(__file__).resolve().parents[1]
DESTINATION_ROOT = VIEWER_ROOT / "public" / "agents"
OMATSURI_DESTINATION_NAME = "omatsuri-ondo"
FORBIDDEN_SUFFIXES = {".dll", ".so", ".dylib", ".pyc"}
FORBIDDEN_NAMES = {
    "build_bundle.py",
    "chance.py",
    "evaluation.py",
    "legacy_policy.py",
    "reachability.py",
    "reachability_model.py",
    "reachability_proof.py",
    "reachability_search.py",
    "reachability_transitions.py",
    "reachability_types.py",
    "rule_manifest.py",
    "solver.py",
    "state.py",
}
RuntimeStager = Callable[..., Path]


def resolve_agent_root(viewer_root: Path, environ: Mapping[str, str]) -> Path:
    override = environ.get("CABT_PROJECT_AGENT_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()

    candidates = (
        viewer_root.parent / "src" / "agent",
        viewer_root.parents[1] / "PTCG-AI-omatsuri-ondo" / "src" / "agent",
        viewer_root.parents[1] / "PTCG-AI" / "src" / "agent",
    )
    for candidate in candidates:
        if (candidate / "omatsuri_ondo" / "build_bundle.py").is_file():
            return candidate.resolve()
    return candidates[0].resolve()


def load_runtime_stager(build_script: Path) -> RuntimeStager:
    spec = importlib.util.spec_from_file_location(
        "_cabt_omatsuri_runtime_bundle",
        build_script,
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"おまつりおんどbundle定義を読めません: {build_script}")
    module = importlib.util.module_from_spec(spec)
    previous = sys.modules.get(spec.name)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        if previous is None:
            sys.modules.pop(spec.name, None)
        else:
            sys.modules[spec.name] = previous
    stager = getattr(module, "stage_python_runtime", None)
    if not callable(stager):
        raise AttributeError(
            "おまつりおんどbundle定義にstage_python_runtimeがありません: "
            f"{build_script}"
        )
    return stager


def validate_deck(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"おまつりおんどのdeck.csvがありません: {path}")
    rows = [
        row.strip()
        for row in path.read_text(encoding="utf-8-sig").splitlines()
        if row.strip()
    ]
    if len(rows) != 60:
        raise ValueError(f"おまつりおんど/deck.csvは60枚である必要があります: {len(rows)}枚")
    if any(not row.isdecimal() or int(row) <= 0 for row in rows):
        raise ValueError("おまつりおんど/deck.csvに不正なカードIDがあります。")


def assert_public_boundary(root: Path) -> None:
    files = tuple(path for path in root.rglob("*") if path.is_file())
    native = next(
        (path for path in files if path.suffix.lower() in FORBIDDEN_SUFFIXES),
        None,
    )
    if native is not None:
        raise ValueError(f"GUI公開領域へネイティブ実行物をコピーできません: {native}")
    if any(path.is_dir() and path.name == "cg" for path in root.rglob("cg")):
        raise ValueError("GUI公開領域へcgディレクトリをコピーできません。")
    forbidden = sorted({path.name for path in files if path.suffix == ".py"} & FORBIDDEN_NAMES)
    if forbidden:
        raise ValueError(f"GUI公開領域へ開発用AIコードをコピーできません: {forbidden[0]}")
    if any("tests" in path.relative_to(root).parts for path in files):
        raise ValueError("GUI公開領域へテストコードをコピーできません。")
    if any(
        "rules" in path.relative_to(root).parts
        for path in files
        if path.suffix == ".py"
    ):
        raise ValueError("GUI公開領域へ動的rulesをコピーできません。")


def sync_omatsuri_agent(
    agent_root: Path,
    destination_root: Path,
) -> tuple[Path, ...]:
    agent_root = agent_root.resolve()
    destination_root = destination_root.resolve()
    source = agent_root / "omatsuri_ondo"
    build_script = source / "build_bundle.py"
    validate_deck(source / "deck.csv")
    stager = load_runtime_stager(build_script)

    destination_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".omatsuri-sync.",
        dir=destination_root.parent,
    ) as work:
        work_root = Path(work)
        staged = work_root / OMATSURI_DESTINATION_NAME
        result = Path(
            stager(staged, top_level_main=True, include_deck=True)
        ).resolve()
        if result != staged.resolve():
            raise ValueError("おまつりおんどruntimeのstage先が一致しません。")
        validate_deck(staged / "deck.csv")
        assert_public_boundary(staged)
        copied = tuple(
            sorted(
                path.relative_to(staged)
                for path in staged.rglob("*")
                if path.is_file()
            )
        )

        destination = destination_root / OMATSURI_DESTINATION_NAME
        previous = work_root / ".previous-omatsuri-ondo"
        if destination.exists():
            os.replace(destination, previous)
        try:
            os.replace(staged, destination)
        except Exception:
            if previous.exists() and not destination.exists():
                os.replace(previous, destination)
            raise
    return copied


def main() -> None:
    source = resolve_agent_root(VIEWER_ROOT, os.environ)
    copied = sync_omatsuri_agent(source, DESTINATION_ROOT)
    print(
        "GUI内蔵AI同期完了: "
        f"{source / 'omatsuri_ondo'} -> "
        f"{DESTINATION_ROOT / OMATSURI_DESTINATION_NAME} ({len(copied)} files)"
    )


if __name__ == "__main__":
    main()
