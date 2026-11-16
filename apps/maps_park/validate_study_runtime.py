"""Live, zero-token preflight for the MAPS ablation study launchers."""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any


class StudyRuntimeValidator:
    """Verify telemetry credentials and model availability before services start."""

    @staticmethod
    def _required_models() -> list[str]:
        """Return the unique model identifiers declared by the launcher."""
        raw = os.environ.get("MAPS_REQUIRED_MODELS", "")
        return list(dict.fromkeys(model.strip() for model in raw.split(",") if model.strip()))

    @staticmethod
    def _validate_wandb() -> None:
        """Verify an authenticated online W&B session without creating a run."""
        if os.environ.get("MAPS_TELEMETRY_BACKEND") != "wandb":
            raise RuntimeError("study arms require MAPS_TELEMETRY_BACKEND=wandb")
        if os.environ.get("WANDB_MODE", "online").strip().lower() != "online":
            raise RuntimeError("study arms require WANDB_MODE=online")

        import wandb

        api = wandb.Api(timeout=30)
        viewer = api.viewer
        if not viewer:
            raise RuntimeError("W&B authentication preflight returned no viewer")
        print(
            f"[study preflight] W&B authenticated for project={os.environ.get('WANDB_PROJECT', 'maps-park-ablations')}"
        )

    @classmethod
    def _validate_ollama(cls) -> None:
        """Verify every requested Ollama tag is present on the selected server."""
        base_url = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=15) as response:  # noqa: S310
            payload: dict[str, Any] = json.load(response)
        available = {
            str(model.get("name") or model.get("model"))
            for model in payload.get("models", [])
            if model.get("name") or model.get("model")
        }
        missing = sorted(set(cls._required_models()) - available)
        if missing:
            commands = ", ".join(f"ollama pull {model}" for model in missing)
            raise RuntimeError(f"Ollama is missing required models {missing}; run: {commands}")
        print(f"[study preflight] Ollama ready at {base_url}: {', '.join(cls._required_models())}")

    @classmethod
    def _validate_openai(cls) -> None:
        """Verify the API key can retrieve every requested OpenAI model."""
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is required for this study arm")

        from openai import OpenAI

        client = OpenAI()
        model: Any
        for model in cls._required_models():
            client.models.retrieve(model)
        print(f"[study preflight] OpenAI model access ready: {', '.join(cls._required_models())}")

    @classmethod
    def main(cls) -> None:
        """Run the required W&B and provider checks."""
        cls._validate_wandb()
        provider = os.environ.get("MAPS_MODEL_PROVIDER", "").strip().lower()
        if provider == "ollama":
            cls._validate_ollama()
        elif provider == "openai":
            cls._validate_openai()
        else:
            raise RuntimeError(f"unsupported MAPS_MODEL_PROVIDER={provider!r}")


if __name__ == "__main__":
    StudyRuntimeValidator.main()
