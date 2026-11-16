"""Create one portable M4 bundle containing MAPS, Studio, and all Qwen arms."""

from __future__ import annotations

import argparse
import logging
import shutil
from pathlib import Path
from typing import ClassVar


class QwenTransferBundleCreator:
    """Copy the two required source trees without credentials or build outputs."""

    STUDIO_ROOT: ClassVar[Path] = Path(__file__).resolve().parents[1]
    STUDIO_EXCLUDES: ClassVar[set[str]] = {
        ".ablation-instance.env",
        ".agents",
        ".aws",
        ".claude",
        ".codex",
        ".env",
        ".git",
        ".pytest_cache",
        ".ruff_cache",
        ".vscode",
        "ablation_seeds",
        "artifacts",
        "credentials.json",
        "images",
        "logs",
        "memory",
        "node_modules",
        "nss_local.db",
        "state",
        "state_ablations",
        "state_solo",
        "token.json",
        "venv",
    }
    MAPS_EXCLUDES: ClassVar[set[str]] = {
        ".env",
        ".env.production",
        ".git",
        ".idea",
        ".svelte-kit",
        ".terraform",
        ".vscode",
        "build",
        "gifs",
        "localdocs",
        "logged_trajectories",
        "logs",
        "node_modules",
        "optuna_studies.db",
        "terraform.tfvars",
        "trajectories",
        "venv",
    }
    QWEN_LAUNCHERS: ClassVar[tuple[str, ...]] = (
        "run_study_qwen4b_multi.sh",
        "run_study_qwen4b_single.sh",
        "run_study_qwen4b_strong_planner_multi.sh",
        "run_study_qwen4b_strong_planner_single.sh",
    )

    @classmethod
    def _studio_ignore(cls, _directory: str, names: list[str]) -> set[str]:
        """Exclude local state, secrets, dependencies, and source Git metadata."""
        ignored = cls.STUDIO_EXCLUDES.intersection(names)
        ignored.update(name for name in names if name == "__pycache__" or name.endswith((".pyc", ".pyo")))
        ignored.update(name for name in names if name.startswith("state_"))
        return ignored

    @classmethod
    def _maps_ignore(cls, _directory: str, names: list[str]) -> set[str]:
        """Exclude MAPS dependencies, runtime data, secrets, and build outputs."""
        ignored = cls.MAPS_EXCLUDES.intersection(names)
        ignored.update(name for name in names if name == "__pycache__" or name.endswith((".pyc", ".pyo")))
        ignored.update(name for name in names if name.endswith((".egg-info", ".pem", ".key", ".tfstate")))
        return ignored

    @classmethod
    def _validate_source(cls, maps_repo: Path) -> None:
        """Verify both source trees contain the Qwen study and simulator entry points."""
        required_studio = [
            cls.STUDIO_ROOT / "apps" / "maps_park" / "run_qwen_ablation_study.sh",
            cls.STUDIO_ROOT / "config" / "llm_config_qwen4b.hocon",
            cls.STUDIO_ROOT / "config" / "llm_config_qwen30b_a3b.hocon",
        ]
        required_studio.extend(cls.STUDIO_ROOT / "apps" / "maps_park" / launcher for launcher in cls.QWEN_LAUNCHERS)
        required_maps = [maps_repo / "map_backend" / "server.js", maps_repo / "map_py", maps_repo / "package.json"]
        missing = [path for path in required_studio + required_maps if not path.exists()]
        if missing:
            rendered = ", ".join(str(path) for path in missing)
            raise FileNotFoundError(f"cannot create Qwen transfer bundle; missing: {rendered}")

    @staticmethod
    def _readme() -> str:
        """Render M4 setup and execution instructions for the portable bundle."""
        return """# Portable MAPS Qwen study

This bundle contains the MAPS simulator and the Neuro SAN Studio source needed
for the four Qwen arms. It deliberately excludes credentials, Git histories,
virtual environments, installed Node modules, logs, and experiment state.

On the 64 GB Apple Silicon Mac:

```bash
./setup_macos.sh
source neuro-san-studio/venv/bin/activate
wandb login
export WANDB_ENTITY=<your-wandb-entity>
./run_qwen_study.sh
```

Start the Ollama application or `ollama serve` before running the setup script.
`WANDB_ENTITY` is optional; omit it to use the account or team selected by your
default W&B login.

The setup installs MAPS and Studio dependencies and pulls `qwen3:4b` plus
`qwen3:30b-a3b`. The run command executes four fresh ten-episode arms and
requires successful online W&B telemetry. Run one arm directly from the
`neuro-san-studio` directory when a partial rerun is needed.
"""

    @staticmethod
    def _setup_script() -> str:
        """Render the one-time macOS dependency and model setup script."""
        return """#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

command -v python3.12 >/dev/null || { echo "ERROR: install Python 3.12 first."; exit 1; }
command -v node >/dev/null || { echo "ERROR: install Node.js 22.15 or newer first."; exit 1; }
command -v npm >/dev/null || { echo "ERROR: npm is required."; exit 1; }
command -v ollama >/dev/null || { echo "ERROR: install Ollama first."; exit 1; }

cd "$ROOT/MAPs"
npm install

cd "$ROOT/neuro-san-studio"
python3.12 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e "$ROOT/MAPs"

ollama pull qwen3:4b
ollama pull qwen3:30b-a3b

echo "Setup complete. Run: source neuro-san-studio/venv/bin/activate && wandb login"
"""

    @staticmethod
    def _launcher_script() -> str:
        """Render the bundle-level Qwen study launcher."""
        return """#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export MAPS_REPO="${MAPS_REPO:-$ROOT/MAPs}"
export OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://127.0.0.1:11434}"

cd "$ROOT/neuro-san-studio"
exec apps/maps_park/run_qwen_ablation_study.sh "$@"
"""

    @classmethod
    def _create(cls, destination: Path, maps_repo: Path) -> Path:
        """Create a complete portable directory without overwriting a prior bundle."""
        cls._validate_source(maps_repo)
        if destination.exists():
            raise FileExistsError(f"refusing to overwrite existing bundle: {destination}")
        destination.mkdir(parents=True)
        shutil.copytree(
            cls.STUDIO_ROOT,
            destination / "neuro-san-studio",
            ignore=cls._studio_ignore,
            symlinks=True,
        )
        shutil.copytree(maps_repo, destination / "MAPs", ignore=cls._maps_ignore, symlinks=True)
        (destination / "README.md").write_text(cls._readme(), encoding="utf-8")
        setup = destination / "setup_macos.sh"
        setup.write_text(cls._setup_script(), encoding="utf-8")
        setup.chmod(0o755)
        launcher = destination / "run_qwen_study.sh"
        launcher.write_text(cls._launcher_script(), encoding="utf-8")
        launcher.chmod(0o755)
        return destination

    @staticmethod
    def _archive(destination: Path) -> Path:
        """Create a gzip tar archive next to the portable directory."""
        archive = shutil.make_archive(
            str(destination),
            "gztar",
            root_dir=destination.parent,
            base_dir=destination.name,
        )
        return Path(archive)

    @classmethod
    def main(cls) -> None:
        """Parse command-line options and create the requested transfer bundle."""
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument(
            "--destination",
            type=Path,
            default=cls.STUDIO_ROOT.parent / "maps-qwen-m4-transfer",
            help="Exact path for the new portable directory.",
        )
        parser.add_argument(
            "--maps-repo",
            type=Path,
            default=Path.home() / "MAPs",
            help="Source MAPS simulator repository.",
        )
        parser.add_argument("--archive", action="store_true", help="Also create a .tar.gz beside the directory.")
        args = parser.parse_args()
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        created = cls._create(args.destination.expanduser().resolve(), args.maps_repo.expanduser().resolve())
        logging.info("[qwen bundle] created %s", created)
        if args.archive:
            logging.info("[qwen bundle] archived %s", cls._archive(created))


if __name__ == "__main__":
    QwenTransferBundleCreator.main()
