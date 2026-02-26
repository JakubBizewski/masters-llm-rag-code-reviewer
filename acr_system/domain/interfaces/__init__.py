"""Domain interfaces (Ports) - abstractions for infrastructure adapters."""

from acr_system.domain.interfaces.ports import (
    CallGraphAnalyzer,
    ConfigRepository,
    EmbeddingStore,
    ImpactAnalyzer,
    LLMProvider,
    StaticAnalyzer,
    VCSRepository,
)

__all__ = [
    "VCSRepository",
    "LLMProvider",
    "EmbeddingStore",
    "StaticAnalyzer",
    "ConfigRepository",
    "CallGraphAnalyzer",
    "ImpactAnalyzer",
]
