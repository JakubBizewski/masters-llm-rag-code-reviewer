"""Project configuration model."""
from dataclasses import dataclass, field
from typing import Optional

from acr_system.domain.value_objects.value_objects import (
    FilePatternRule,
    LLMConfig,
    RAGConfig,
    RuleSet,
)


@dataclass
class ProjectConfig:
    """Project configuration loaded from .acr-config.yml"""
    
    review_enabled: bool = True
    global_rules: list[RuleSet] = field(default_factory=list)
    file_patterns: list[FilePatternRule] = field(default_factory=list)
    llm_config: LLMConfig = field(default_factory=LLMConfig)
    rag_config: RAGConfig = field(default_factory=RAGConfig)
    
    def get_rules_for_file(self, file_path: str) -> tuple[str, Optional[RAGConfig]]:
        """Get applicable rules and RAG config for a file.
        
        Returns:
            Tuple of (rules_text, rag_config)
        """
        import fnmatch
        
        # Start with global rules
        rules_parts = []
        for rule_set in self.global_rules:
            if rule_set.enabled:
                rules_parts.append(f"## {rule_set.name}\n{rule_set.rules_text}")
        
        # Find matching file pattern rules (sorted by priority, descending)
        matching_patterns = [
            pattern for pattern in self.file_patterns
            if fnmatch.fnmatch(file_path, pattern.pattern)
        ]
        matching_patterns.sort(key=lambda p: p.priority, reverse=True)
        
        # Add file-specific rules
        rag_config_override: Optional[RAGConfig] = None
        
        for pattern in matching_patterns:
            rules_parts.append(f"## File-specific: {pattern.pattern}\n{pattern.rules_text}")
            
            # Use highest priority pattern's RAG config if available
            if pattern.rag_config and not rag_config_override:
                rag_config_override = pattern.rag_config
        
        rules_text = "\n\n".join(rules_parts)
        
        # Use pattern-specific RAG config or fall back to global
        final_rag_config = rag_config_override or self.rag_config
        
        return rules_text, final_rag_config
