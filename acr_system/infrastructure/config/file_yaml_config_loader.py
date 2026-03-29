"""Load project configuration from a local YAML file.

Used by experimental evaluation runs where we want to supply a custom config
path rather than reading `.acr-config.yml` from the repository.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from acr_system.domain.interfaces.ports import ConfigRepository
from acr_system.infrastructure.config.project_config import ProjectConfig
from acr_system.infrastructure.config.yaml_config_loader import YAMLConfigLoader
from acr_system.shared.exceptions.infrastructure_exceptions import ConfigLoadError


class FileYAMLConfigLoader(ConfigRepository):
    def __init__(self, config_path: str):
        self.config_path = Path(config_path)

    async def load_config(self, repo: str, ref: str) -> ProjectConfig:  # noqa: ARG002
        if not self.config_path.exists():
            raise ConfigLoadError(f"Config file not found: {self.config_path}")

        try:
            content = self.config_path.read_text(encoding="utf-8")
            config_data = yaml.safe_load(content) or {}
            # Reuse existing parser logic
            parser = YAMLConfigLoader(vcs_repository=None)  # type: ignore[arg-type]
            return parser._parse_config(config_data)  # pylint: disable=protected-access
        except ConfigLoadError:
            raise
        except Exception as e:
            raise ConfigLoadError(f"Error loading config from file: {e}") from e

    async def get_rules_for_file(self, config: ProjectConfig, file_path: str):
        return config.get_rules_for_file(file_path)
