"""Structural and lifecycle guards for the eight-arm MAPS ablation study."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from scripts.create_qwen_transfer_bundle import QwenTransferBundleCreator

from apps.maps_park.no_self_improvement_runner import NoSelfImprovementRunner
from coded_tools.episode_telemetry import EpisodeTelemetry
from coded_tools.promote_trial import PromoteTrial
from coded_tools.run_telemetry import RunTelemetry
from coded_tools.seed_playbooks import SeedPlaybooks
from neuro_san_studio.commands.check_config import extract_llm_configs_from_agent_network
from neuro_san_studio.commands.check_config import load_agent_network


class TestMapsAblationStudy:
    """Keep the checked-in study matrix isolated, reproducible, and executable."""

    ROOT = Path(__file__).resolve().parents[1]
    STUDY = json.loads((ROOT / "config" / "maps_ablation_study.json").read_text(encoding="utf-8"))

    def test_matrix_has_eight_ten_episode_arms(self) -> None:
        """The planned 4 Qwen, 2 fixed-policy, and 2 GPT arms are all present."""
        arms = self.STUDY.get("arms", [])
        assert self.STUDY.get("episodes_per_arm") == 10
        assert len(arms) == 8
        assert {arm.get("topology") for arm in arms} == {"single_agent", "multi_agent"}
        assert sum(arm.get("provider") == "ollama" for arm in arms) == 4
        assert sum(arm.get("self_improvement") is False for arm in arms) == 2
        assert sum(arm.get("macro_closeout") is False for arm in arms) == 2
        assert sum(arm.get("player_model") == "gpt-5-mini" for arm in arms) == 2

    def test_every_launcher_is_executable_isolated_and_wandb_required(self) -> None:
        """Every treatment has unique ports and refuses non-online telemetry."""
        ports: list[int] = []
        arm: Any
        for arm in self.STUDY.get("arms", []):
            launcher = self.ROOT / "apps" / "maps_park" / str(arm.get("launcher"))
            source = launcher.read_text(encoding="utf-8")
            subprocess.run(["bash", "-n", str(launcher)], check=True)
            assert launcher.stat().st_mode & 0o111
            assert "MAPS_WANDB_REQUIRED=1" in source
            assert "MAPS_STUDY_PREFLIGHT" in source
            assert "MAPS_DEFAULT_FRESH=1" in source
            assert "MAPS_EPISODE_LIMIT" in source
            ports.extend(int(port) for port in arm.get("ports", []))
        assert len(ports) == len(set(ports)) == 24

    def test_qwen_effective_models_match_treatments(self, monkeypatch) -> None:
        """Neuro SAN's real overlay chain resolves each role to its assigned model."""
        monkeypatch.setenv("MAPS_STATE_DIR", "__study_state__")
        monkeypatch.setenv("MAPS_SEED_DIR", "__study_seeds__")
        expected = {
            "qwen4b_multi": {"player.hocon": {"qwen3:4b"}, "planner.hocon": {"qwen3:4b"}},
            "qwen4b_single": {"player_solo.hocon": {"qwen3:4b"}, "planner_solo.hocon": {"qwen3:4b"}},
            "qwen4b_strong_planner_multi": {
                "player.hocon": {"qwen3:4b"},
                "planner.hocon": {"qwen3:30b-a3b"},
                "watcher.hocon": {"qwen3:30b-a3b"},
            },
            "qwen4b_strong_planner_single": {
                "player_solo.hocon": {"qwen3:4b"},
                "planner_solo.hocon": {"qwen3:30b-a3b"},
            },
        }
        arm: Any
        files: Any
        for arm, files in expected.items():
            filename: Any
            models: Any
            for filename, models in files.items():
                relative = Path("registries") / "ablations" / arm / filename
                network = load_agent_network(str(relative))
                configs = extract_llm_configs_from_agent_network(network)
                assert {config.get("model_name") for _, config in configs} == models
                assert all(config.get("class") == "ollama" for _, config in configs)
                assert all(config.get("num_ctx") == 32768 for _, config in configs)

    def test_no_carryover_arms_keep_start_planner_and_watcher(self) -> None:
        """Episode planning and periodic strategy remain, without LLM close-out."""
        cases = {
            "no_self_improvement_multi": (
                ("player.hocon", "watcher.hocon", "planner.hocon"),
                ("player", "watcher", "planner"),
                "apps.maps_park.no_self_improvement_runner",
            ),
            "no_self_improvement_single": (
                ("player_solo.hocon", "planner_solo.hocon"),
                ("player_solo", "planner_solo", "planner_solo"),
                "apps.maps_park.solo_no_self_improvement_runner",
            ),
        }
        arm: Any
        for arm, (networks, agents, runner_module) in cases.items():
            manifest = self.ROOT / "registries" / "ablations" / arm / "manifest.hocon"
            manifest_source = manifest.read_text(encoding="utf-8")
            assert all(f'"{network}": true' in manifest_source for network in networks)
            launcher_name = next(
                item.get("launcher") for item in self.STUDY.get("arms", []) if item.get("name") == arm
            )
            source = (self.ROOT / "apps" / "maps_park" / str(launcher_name)).read_text(encoding="utf-8")
            assert f"MAPS_RUNNER_AGENT={agents[0]}" in source
            assert f"MAPS_MICRO_AGENT={agents[1]}" in source
            assert f"MAPS_MACRO_AGENT={agents[2]}" in source
            assert "MAPS_SELF_IMPROVEMENT=0" in source
            assert "MAPS_NO_CROSS_EPISODE=1" in source
            assert "MAPS_SKIP_MACRO_CLOSEOUT=1" in source
            assert "MAPS_PLANNER_MODEL=gpt-5.5" in source
            assert "MAPS_WATCHER_MODEL=gpt-5.5" in source
            assert f"MAPS_RUNNER_MODULE={runner_module}" in source
            assert "MAPS_EPISODE_LIMIT=10" in source

    def test_fixed_policy_reset_removes_carryover(self, tmp_path, monkeypatch) -> None:
        """Episode N+1 starts from byte-identical seeds with empty transient memory."""
        seed_dir = tmp_path / "seeds"
        state_dir = tmp_path / "state"
        seed_dir.mkdir()
        state_dir.mkdir()
        name: Any
        seed_name: Any
        for name, seed_name in SeedPlaybooks.PLAYBOOKS.items():
            (seed_dir / seed_name).write_text(f"immutable {name}\n", encoding="utf-8")
            (state_dir / f"{name}.md").write_text("mutated\n", encoding="utf-8")
        (state_dir / "scratchpad_player.md").write_text("carryover", encoding="utf-8")
        (state_dir / "trial_strategies.md").write_text("- t0_1: learned", encoding="utf-8")
        (state_dir / "status_full.json").write_text("{}\n", encoding="utf-8")

        monkeypatch.setattr(SeedPlaybooks, "SEED_DIR", str(seed_dir))
        monkeypatch.setattr(SeedPlaybooks, "STATE_DIR", str(state_dir))
        monkeypatch.setattr(SeedPlaybooks, "MERGED", False)
        monkeypatch.setattr(
            NoSelfImprovementRunner, "_base_write_episode_cost", lambda _episode, _reward: {"ok": True}
        )
        monkeypatch.setattr("apps.maps_park.no_self_improvement_runner.runner.PLAYBOOK_STATE_DIR", str(state_dir))

        assert NoSelfImprovementRunner.write_episode_cost(0, 123) == {"ok": True}
        assert not (state_dir / "scratchpad_player.md").exists()
        assert not (state_dir / "status_full.json").exists()
        assert (state_dir / "trial_strategies.md").read_text(encoding="utf-8") == ""
        assert (state_dir / "no_carry_episode.txt").read_text(encoding="utf-8") == "1\n"
        for name in SeedPlaybooks.PLAYBOOKS:
            assert (state_dir / f"{name}.md").read_text(encoding="utf-8") == f"immutable {name}\n"

    def test_no_carryover_blocks_seed_learning(self, tmp_path, monkeypatch) -> None:
        """Episode-end trial promotion may edit live state but never immutable seeds."""
        state_dir = tmp_path / "state"
        seed_dir = tmp_path / "seeds"
        state_dir.mkdir()
        seed_dir.mkdir()
        baseline = "# Coordinator\n## Learned rules (promoted from prior runs)\n"
        (state_dir / "playbook_coordinator.md").write_text(baseline, encoding="utf-8")
        seed = seed_dir / "seed_playbook_coordinator.md"
        seed.write_text(baseline, encoding="utf-8")
        monkeypatch.setenv("MAPS_NO_CROSS_EPISODE", "1")
        monkeypatch.setattr(PromoteTrial, "STATE_DIR", str(state_dir))
        monkeypatch.setattr(PromoteTrial, "SEED_DIR", str(seed_dir))
        monkeypatch.setattr(PromoteTrial, "MERGED", False)

        result = PromoteTrial().invoke(
            {
                "domain": "coordinator",
                "edit_type": "add_line",
                "new_text": "Test only within this episode",
                "episode": 0,
                "section": "end",
            },
            {},
        )

        assert isinstance(result, dict)
        assert result.get("action_taken") == "promoted"
        assert result.get("seed_mirror") == "disabled_no_cross_episode"
        assert seed.read_text(encoding="utf-8") == baseline

    def test_no_carryover_hides_prior_episode_telemetry(self, tmp_path, monkeypatch) -> None:
        """Planner and watcher see only the episode currently being played."""
        logs = tmp_path / "logs"
        state = tmp_path / "state"
        logs.mkdir()
        state.mkdir()
        (logs / "run.ep000.jsonl").write_text("{}\n", encoding="utf-8")
        (logs / "run.ep001.jsonl").write_text("{}\n", encoding="utf-8")
        marker = state / "no_carry_episode.txt"
        marker.write_text("1\n", encoding="utf-8")
        monkeypatch.setenv("MAPS_NO_CROSS_EPISODE", "1")
        monkeypatch.setattr(RunTelemetry, "RUN_LOG_DIR", str(logs))
        monkeypatch.setattr(RunTelemetry, "EPISODE_FLOOR_PATH", str(marker))
        monkeypatch.setattr(EpisodeTelemetry, "RUN_LOG_DIR", str(logs))
        monkeypatch.setattr(EpisodeTelemetry, "EPISODE_FLOOR_PATH", str(marker))

        telemetry = RunTelemetry()
        assert telemetry._episode_numbers() == [1]
        discovered = telemetry._discover_runs(include_archived=True)
        assert discovered[0][2] == [(1, str(logs / "run.ep001.jsonl"))]
        hidden = EpisodeTelemetry().invoke({"episode": 0}, {})
        assert hidden.get("exists") is False
        assert "hidden by no-carryover" in str(hidden.get("error"))

    def test_no_carryover_reopens_llm_sessions(self) -> None:
        """Player, planner, and watcher chat histories reset at every boundary."""
        runner_source = (self.ROOT / "apps" / "maps_park" / "runner.py").read_text(encoding="utf-8")
        assert "if _NO_CROSS_EPISODE:" in runner_source
        assert "reset_agent_session_cache()" in runner_source
        assert "runner_session, runner_thread = open_session" in runner_source
        assert "micro_session, micro_thread = open_session" in runner_source
        assert "macro_session, macro_thread = open_session" in runner_source

    def test_no_carryover_skips_planner_closeout(self) -> None:
        """The episode boundary is deterministic and does not invoke the planner LLM."""
        runner_source = (self.ROOT / "apps" / "maps_park" / "runner.py").read_text(encoding="utf-8")
        assert "macro_session is not None and not _SKIP_MACRO_CLOSEOUT" in runner_source
        assert "Skipped planner close-out; committed deterministic episode boundary." in runner_source
        assert '"final_reward": verified_after.get("cumulative_reward")' in runner_source
        assert '"episode": verified_after.get("episode")' in runner_source

    def test_replica_creator_covers_every_arm_without_secrets(self) -> None:
        """The generator snapshots all treatments while excluding local credentials."""
        source = (self.ROOT / "scripts" / "create_maps_ablation_replicas.py").read_text(encoding="utf-8")
        assert "refusing to overwrite existing replica" in source
        assert '".env"' in source and '".git"' in source and '".aws"' in source
        assert ".ablation-instance.env" in source
        assert 'git", "init' in source
        assert all(
            str(arm.get("launcher")) in (self.ROOT / "apps" / "maps_park" / "run_replica_ablation.sh").read_text()
            for arm in self.STUDY.get("arms", [])
        )

    def test_qwen_transfer_bundle_contains_both_systems_without_runtime_state(self, tmp_path, monkeypatch) -> None:
        """The portable Mac bundle includes both codebases but no credentials or dependencies."""
        studio = tmp_path / "studio-source"
        maps = tmp_path / "maps-source"
        launchers = studio / "apps" / "maps_park"
        config = studio / "config"
        launchers.mkdir(parents=True)
        config.mkdir()
        for launcher in (*QwenTransferBundleCreator.QWEN_LAUNCHERS, "run_qwen_ablation_study.sh"):
            (launchers / launcher).write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        (config / "llm_config_qwen4b.hocon").write_text("model_name = qwen3:4b\n", encoding="utf-8")
        (config / "llm_config_qwen30b_a3b.hocon").write_text("model_name = qwen3:30b-a3b\n", encoding="utf-8")
        (studio / ".env").write_text("SECRET=excluded\n", encoding="utf-8")
        (studio / "logs").mkdir()

        (maps / "map_backend").mkdir(parents=True)
        (maps / "map_backend" / "server.js").write_text("", encoding="utf-8")
        (maps / "map_py").mkdir()
        (maps / "package.json").write_text("{}\n", encoding="utf-8")
        (maps / "node_modules").mkdir()

        monkeypatch.setattr(QwenTransferBundleCreator, "STUDIO_ROOT", studio)
        bundle = QwenTransferBundleCreator._create(tmp_path / "bundle", maps)

        assert (bundle / "neuro-san-studio" / "apps" / "maps_park" / "run_qwen_ablation_study.sh").is_file()
        assert (bundle / "MAPs" / "map_backend" / "server.js").is_file()
        assert (bundle / "run_qwen_study.sh").stat().st_mode & 0o111
        assert not (bundle / "neuro-san-studio" / ".env").exists()
        assert not (bundle / "neuro-san-studio" / "logs").exists()
        assert not (bundle / "MAPs" / "node_modules").exists()

    def test_qwen_study_launcher_covers_four_arms(self) -> None:
        """The portable Mac launcher includes all four Ollama treatments."""
        qwen = (self.ROOT / "apps" / "maps_park" / "run_qwen_ablation_study.sh").read_text(encoding="utf-8")
        qwen_arms = [arm for arm in self.STUDY.get("arms", []) if arm.get("provider") == "ollama"]
        assert len(qwen_arms) == 4
        assert all(str(arm.get("launcher")) in qwen for arm in qwen_arms)

    def test_non_qwen_creator_makes_four_manually_started_repositories(self) -> None:
        """The API-backed arms are separate Git roots without a supervisor."""
        creator = (self.ROOT / "apps" / "maps_park" / "create_non_qwen_ablation_repos.sh").read_text(encoding="utf-8")
        other_arms = [arm for arm in self.STUDY.get("arms", []) if arm.get("provider") != "ollama"]
        for arm in other_arms:
            assert f"--arm {arm.get('name')}" in creator
            assert f"$DESTINATION/{arm.get('name')}" in creator
        assert creator.count("run_replica_ablation.sh --fresh") == 4
        assert "run_replica_ablation.sh --fresh &" not in creator
        assert "\nwait" not in creator

    def test_study_never_uses_nonexistent_gpt_5_1_mini_identifier(self) -> None:
        """The requested historical arm uses the real GPT-5 Mini API identifier."""
        config = (self.ROOT / "config" / "maps_ablation_study.json").read_text(encoding="utf-8")
        assert "gpt-5.1-mini" not in config
        assert config.count('"gpt-5-mini"') == 6

    def test_solo_adapter_preserves_arm_specific_roots(self) -> None:
        """Importing Solo behavior must not overwrite a study replica's paths."""
        source = (self.ROOT / "apps" / "maps_park" / "solo_runner.py").read_text(encoding="utf-8")
        assert 'os.environ.setdefault("MAPS_STATE_DIR", "state_solo")' in source
        assert 'os.environ.setdefault("MAPS_LOG_DIR", os.path.join("logs", "maps_park_solo"))' in source
