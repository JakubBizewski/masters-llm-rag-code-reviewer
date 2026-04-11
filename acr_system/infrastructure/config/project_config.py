"""Project configuration model."""
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from acr_system.domain.entities.entities import ReviewComment

from acr_system.domain.value_objects.value_objects import (
    FilePatternRule,
    ImpactAnalysisConfig,
    LLMConfig,
    RAGConfig,
    RuleSet,
    Severity,
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
    publish_config: "PublishConfig" = field(default_factory=lambda: PublishConfig())
    
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

    def filter_comments_for_publication(
        self,
        comments: List[ReviewComment],
    ) -> List[ReviewComment]:
        """Filter comments according to publication policy."""
        return [c for c in comments if self.publish_config.should_publish(c)]


@dataclass
class PublishConfig:
    """Policy controlling which comments are eligible for publication."""

    min_severity: str = Severity.INFO
    exclude_rule_names: List[str] = field(default_factory=list)
    exclude_message_patterns: List[str] = field(default_factory=list)
    exclude_positive_feedback: bool = False

    def __post_init__(self) -> None:
        valid = {Severity.INFO, Severity.WARNING, Severity.ERROR}
        if self.min_severity not in valid:
            raise ValueError(f"Invalid min_severity: {self.min_severity}")

    def should_publish(self, comment: ReviewComment) -> bool:
        """Return True if a comment should be published."""
        import re

        if _severity_priority(comment.severity.level) < _severity_priority(self.min_severity):
            return False

        if comment.rule_name and comment.rule_name in self.exclude_rule_names:
            return False

        message = comment.message or ""
        for pattern in self.exclude_message_patterns:
            try:
                if re.search(pattern, message, re.IGNORECASE):
                    return False
            except re.error:
                # Fall back to plain substring if invalid regex is provided.
                if pattern.lower() in message.lower():
                    return False

        if self.exclude_positive_feedback and _looks_like_positive_feedback(message):
            return False

        return True


def _severity_priority(level: str) -> int:
    priorities = {
        Severity.INFO: 1,
        Severity.WARNING: 2,
        Severity.ERROR: 3,
    }
    return priorities.get(level, 1)


def _looks_like_positive_feedback(message: str) -> bool:
    lowered = message.lower()
    markers = (
        "more descriptive",
        "improving code clarity",
        "improves code clarity",
        "improves clarity",
        "looks good",
        "good addition",
        "good change",
    )
    return any(m in lowered for m in markers)
