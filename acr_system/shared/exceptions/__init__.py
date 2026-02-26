"""Shared exceptions for ACR system."""

from acr_system.shared.exceptions.domain_exceptions import (
    DomainException,
)
from acr_system.shared.exceptions.infrastructure_exceptions import (
    AnalysisError,
    ASTParseError,
    CIFetchError,
    ConfigLoadError,
    EmbeddingStoreError,
    InfrastructureException,
    LLMProviderError,
    VCSAPIError,
)

__all__ = [
    # Domain exceptions
    "DomainException",
    # Infrastructure exceptions
    "InfrastructureException",
    "VCSAPIError",
    "LLMProviderError",
    "EmbeddingStoreError",
    "ConfigLoadError",
    "CIFetchError",
    "ASTParseError",
    "AnalysisError",
]
