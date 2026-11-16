"""Create one isolated local Git repository for every MAPS study arm."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any
from typing import ClassVar


class MapsAblationReplicaCreator:
    """Snapshot the current workspace into reproducible arm-specific repositories."""

    ROOT: ClassVar[Path] = Path(__file__).resolve().parents[1]
    MANIFEST: ClassVar[Path] = ROOT / "config" / "maps_ablation_study.json"
    ROOT_EXCLUDES: ClassVar[set[str]] = {
        ".agents",
        ".ablation-instance.env",
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
        "nss_local.db",
        "state",
        "state_ablations",
        "state_solo",
        "token.json",
        "venv",
    }

    @classmethod
    def _study(cls) -> dict[str, Any]:
        """Load the checked-in experiment matrix."""
        return json.loads(cls.MANIFEST.read_text(encoding="utf-8"))

    @classmethod
    def _ignore(cls, directory: str, names: list[str]) -> set[str]:
        """Exclude secrets, runtime outputs, caches, and the source Git database."""
        relative = Path(directory).resolve().relative_to(cls.ROOT)
        ignored = {name for name in names if name == "__pycache__" or name.endswith((".pyc", ".pyo"))}
        if relative == Path("."):
            ignored.update(cls.ROOT_EXCLUDES.intersection(names))
            ignored.update(name for name in names if name.startswith("state_"))
        return ignored

    @staticmethod
    def _instance_env(study: dict[str, Any], arm: dict[str, Any]) -> str:
        """Render non-secret replica identity consumed by the shared launcher."""
        node_port, mcp_port, studio_port = arm.get("ports")
        values = {
            "MAPS_REPLICA_ID": f"{arm.get('name')}-r1",
            "MAPS_ABLATION_ARM": arm.get("name"),
            "MAPS_ARM_SCRIPT": arm.get("launcher"),
            "MAPS_NODE_PORT": node_port,
            "MAPS_MCP_PORT": mcp_port,
            "MAPS_STUDIO_PORT": studio_port,
            "MAPS_EPISODE_LIMIT": study.get("episodes_per_arm"),
            "MAPS_LOG_RELATIVE": arm.get("log_dir"),
            "WANDB_PROJECT": study.get("wandb_project"),
            "WANDB_RUN_GROUP": arm.get("name"),
        }
        return "".join(f"{key}={value}\n" for key, value in values.items())

    @staticmethod
    def _replica_readme(study: dict[str, Any], arm: dict[str, Any]) -> str:
        """Describe the frozen treatment assigned to one generated repository."""
        return (
            f"# MAPS ablation replica: {arm.get('name')}\n\n"
            f"Study: `{study.get('study_id')}`  \n"
            f"Episodes: `{study.get('episodes_per_arm')}`  \n"
            f"Topology: `{arm.get('topology')}`  \n"
            f"Self improvement: `{str(arm.get('self_improvement')).lower()}`  \n"
            f"Player model: `{arm.get('player_model')}`  \n"
            f"Planner model: `{arm.get('planner_model')}`  \n"
            f"Watcher model: `{arm.get('watcher_model')}`\n\n"
            "Run from this repository root:\n\n"
            "```bash\n"
            "apps/maps_park/run_replica_ablation.sh\n"
            "```\n"
        )

    @staticmethod
    def _initialize_git(destination: Path, arm_name: str) -> None:
        """Create a self-contained Git history for the generated snapshot."""
        subprocess.run(
            ["git", "init", "--initial-branch", f"ablation/{arm_name}"],
            cwd=destination,
            check=True,
        )
        subprocess.run(["git", "add", "."], cwd=destination, check=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=MAPS Study Builder",
                "-c",
                "user.email=maps-study@local",
                "commit",
                "-m",
                f"Initialize MAPS ablation replica: {arm_name}",
            ],
            cwd=destination,
            check=True,
        )

    @classmethod
    def _create(cls, root: Path, study: dict[str, Any], arm: dict[str, Any], link_venv: bool) -> Path:
        """Create one replica without overwriting any existing path."""
        destination = root / str(arm.get("name"))
        if destination.exists():
            raise FileExistsError(f"refusing to overwrite existing replica: {destination}")
        shutil.copytree(cls.ROOT, destination, ignore=cls._ignore)
        if link_venv and (cls.ROOT / "venv").is_dir():
            os.symlink(cls.ROOT / "venv", destination / "venv", target_is_directory=True)
        (destination / ".ablation-instance.env").write_text(
            cls._instance_env(study, arm),
            encoding="utf-8",
        )
        (destination / "REPLICA.md").write_text(cls._replica_readme(study, arm), encoding="utf-8")
        cls._initialize_git(destination, str(arm.get("name")))
        return destination

    @classmethod
    def main(cls) -> None:
        """Parse CLI options and create the requested study replicas."""
        study = cls._study()
        arms = {str(arm.get("name")): arm for arm in study.get("arms", [])}
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument(
            "--destination",
            type=Path,
            default=cls.ROOT.parent / "maps-ablation-replicas",
            help="Parent directory for the isolated repositories.",
        )
        parser.add_argument("--arm", action="append", choices=sorted(arms), help="Create only this arm; repeatable.")
        parser.add_argument(
            "--link-venv",
            action="store_true",
            help="Symlink this checkout's virtual environment into each replica on the same machine.",
        )
        args = parser.parse_args()
        selected = args.arm or list(arms)
        args.destination.mkdir(parents=True, exist_ok=True)
        name: Any
        for name in selected:
            created = cls._create(args.destination, study, arms.get(name), args.link_venv)
            print(f"[replica] created {name}: {created}")


if __name__ == "__main__":
    MapsAblationReplicaCreator.main()
