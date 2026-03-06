"""Project configuration model."""
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from acr_system.domain.value_objects.value_objects import (
    FilePatternRule,
    ImpactAnalysisConfig,
    LLMConfig,
    RAGConfig,
    RuleSet,
)


@dataclass
class ProjectConfig:
    """Project configuration loaded from .acr-config.yml"""
    
    review_enabled: bool = True
    global_rules: List[RuleSet] = field(default_factory=list)
    file_patterns: List[FilePatternRule] = field(default_factory=list)
    llm_config: LLMConfig = field(default_factory=LLMConfig)
    rag_config: RAGConfig = field(default_factory=RAGConfig)
    impact_analysis_config: ImpactAnalysisConfig = field(default_factory=ImpactAnalysisConfig)
    
    def get_rules_for_file(self, file_path: str) -> Tuple[str, Optional[RAGConfig], LLMConfig]:
        """Get applicable rules, RAG config, and LLM config for a file.
        
        Returns:
            Tuple of (rules_text, rag_config, llm_config)
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
        
        # Add file-specific rules and collect config overrides
        rag_config_override: Optional[RAGConfig] = None
        llm_config_override: Optional[LLMConfig] = None
        
        for pattern in matching_patterns:
            rules_parts.append(f"## File-specific: {pattern.pattern}\n{pattern.rules_text}")
            
            # Use highest priority pattern's RAG config if available
            if pattern.rag_config and not rag_config_override:
                rag_config_override = pattern.rag_config
            
            # Use highest priority pattern's LLM config if available
            if pattern.llm_config and not llm_config_override:
                llm_config_override = pattern.llm_config
        
        rules_text = "\n\n".join(rules_parts)
        
        # Use pattern-specific configs or fall back to global
        final_rag_config = rag_config_override or self.rag_config
        final_llm_config = llm_config_override or self.llm_config
        
        return rules_text, final_rag_config, final_llm_config
