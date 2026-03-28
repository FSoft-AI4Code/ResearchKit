"""Configuration loader for .researchkit/config.yaml."""

from pathlib import Path

import yaml

from researchkit.config.schema import ResearchKitConfig

CONFIG_DIR = ".researchkit"
CONFIG_FILE = "config.yaml"


def load_config(project_dir: str | Path) -> ResearchKitConfig:
    """Load ResearchKit config from a LaTeX project directory.

    Reads .researchkit/config.yaml if it exists, otherwise returns defaults.
    """
    config_path = Path(project_dir) / CONFIG_DIR / CONFIG_FILE
    if config_path.exists():
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        return ResearchKitConfig.model_validate(raw)
    return ResearchKitConfig()


def load_config_from_dict(data: dict) -> ResearchKitConfig:
    """Load config from an already-parsed dictionary (e.g. from API request)."""
    return ResearchKitConfig.model_validate(data)


def save_config(config: ResearchKitConfig, project_dir: str | Path) -> Path:
    """Write config to .researchkit/config.yaml."""
    config_dir = Path(project_dir) / CONFIG_DIR
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / CONFIG_FILE
    data = config.model_dump(exclude_none=True)
    config_path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False), encoding="utf-8")
    return config_path
