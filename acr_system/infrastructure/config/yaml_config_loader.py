"""YAML configuration loader."""
from typing import Any, Dict, Optional, Tuple

import yaml

from acr_system.domain.interfaces.ports import ConfigRepository, VCSRepository
from acr_system.domain.value_objects.value_objects import (
    FilePatternRule,
    ImpactAnalysisConfig,
    LLMConfig,
    RAGConfig,
    RuleSet,
)
from acr_system.infrastructure.config.project_config import ProjectConfig
from acr_system.shared.exceptions.infrastructure_exceptions import ConfigLoadError
from acr_system.shared.logging.logger import get_logger

logger = get_logger(__name__)


class YAMLConfigLoader(ConfigRepository):
    """Load project configuration from YAML file in repository."""
    
    CONFIG_FILENAME = ".acr-config.yml"
    
    def __init__(self, vcs_repository: VCSRepository):
        self.vcs_repository = vcs_repository
    
    async def load_config(self, repo: str, ref: str) -> ProjectConfig:
        """Load project configuration from repository.
        
        Args:
            repo: Repository name (owner/repo)
            ref: Git ref (branch/commit)
            
        Returns:
            ProjectConfig instance
        """
        try:
            # Fetch config file from repository
            config_content = await self.vcs_repository.get_file_content(
                repo=repo,
                file_path=self.CONFIG_FILENAME,
                ref=ref,
            )
            
            # Parse YAML
            config_data = yaml.safe_load(config_content)
            
            return self._parse_config(config_data)
            
        except Exception as e:
            logger.warning(f"Could not load config from {repo}: {e}. Using defaults.")
            # Return default config if file not found
            return ProjectConfig()
    
    def _parse_config(self, data: Dict[str, Any]) -> ProjectConfig:
        """Parse configuration data into ProjectConfig."""
        try:
            # Parse review settings
            review_data = data.get("review", {})
            review_enabled = review_data.get("enabled", True)
            
            # Parse global rules
            global_rules = []
            for rule_data in data.get("global_rules", []):
                rule = RuleSet(
                    name=rule_data["name"],
                    enabled=rule_data.get("enabled", True),
                    rules_text=rule_data["rules_text"],
                )
                global_rules.append(rule)
            
            # Parse file patterns
            file_patterns = []
            for pattern_data in data.get("file_patterns", []):
                # Parse optional LLM config
                llm_config = None
                if "llm_config" in pattern_data:
                    llm_data = pattern_data["llm_config"]
                    llm_config = LLMConfig(
                        provider=llm_data.get("provider", "openai"),
                        model=llm_data.get("model", "gpt-4o"),
                        temperature=llm_data.get("temperature", 0.3),
                        max_tokens=llm_data.get("max_tokens", 2000),
                    )
                
                # Parse optional RAG config
                rag_config = None
                if "rag_config" in pattern_data:
                    rag_data = pattern_data["rag_config"]
                    rag_config = RAGConfig(
                        enabled=rag_data.get("enabled", True),
                        top_k=rag_data.get("top_k", 5),
                        documentation_paths=rag_data.get("documentation_paths", []),
                        architectural_docs=rag_data.get("architectural_docs", []),
                    )
                
                pattern = FilePatternRule(
                    pattern=pattern_data["pattern"],
                    rules_text=pattern_data["rules_text"],
                    priority=pattern_data.get("priority", 0),
                    llm_config=llm_config,
                    rag_config=rag_config,
                )
                file_patterns.append(pattern)
            
            # Parse global LLM config
            llm_data = data.get("llm", {})
            llm_config = LLMConfig(
                provider=llm_data.get("provider", "openai"),
                model=llm_data.get("model", "gpt-4o"),
                temperature=llm_data.get("temperature", 0.3),
                max_tokens=llm_data.get("max_tokens", 2000),
            )
            
            # Parse global RAG config
            rag_data = data.get("rag", {})
            rag_config = RAGConfig(
                enabled=rag_data.get("enabled", True),
                top_k=rag_data.get("top_k", 5),
                documentation_paths=rag_data.get("documentation_paths", []),
                architectural_docs=rag_data.get("architectural_docs", []),
            )
            
            # Parse impact analysis config
            impact_data = data.get("impact_analysis", {})
            impact_analysis_config = ImpactAnalysisConfig(
                enabled=impact_data.get("enabled", True),
                max_callers_per_function=impact_data.get("max_callers_per_function", 10),
                depth=impact_data.get("depth", 1),
                analyze_imports=impact_data.get("analyze_imports", True),
                severity_threshold=impact_data.get("severity_threshold", "medium"),
                exclude_patterns=tuple(impact_data.get("exclude_patterns", [])),
            )
            
            return ProjectConfig(
                review_enabled=review_enabled,
                global_rules=global_rules,
                file_patterns=file_patterns,
                llm_config=llm_config,
                rag_config=rag_config,
                impact_analysis_config=impact_analysis_config,
            )
            
        except Exception as e:
            raise ConfigLoadError(f"Error parsing configuration: {e}") from e
    
    async def get_rules_for_file(
        self,
        config: ProjectConfig,
        file_path: str,
    ) -> Tuple[str, Optional[RAGConfig], LLMConfig]:
        """Get applicable rules, RAG config, and LLM config for a file."""
        return config.get_rules_for_file(file_path)
