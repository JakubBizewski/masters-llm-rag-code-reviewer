"""Infrastructure exceptions for ACR system."""


class InfrastructureException(Exception):
    """Base exception for infrastructure layer."""
    pass


class VCSAPIError(InfrastructureException):
    """Error communicating with VCS API."""
    pass


class LLMProviderError(InfrastructureException):
    """Error communicating with LLM provider."""
    pass


class EmbeddingStoreError(InfrastructureException):
    """Error with embedding store operations."""
    pass


class ConfigLoadError(InfrastructureException):
    """Error loading configuration."""
    pass


class CIFetchError(InfrastructureException):
    """Error fetching CI results."""
    pass


class ASTParseError(InfrastructureException):
    """Error parsing code with AST parser."""
    pass


class AnalysisError(InfrastructureException):
    """Error during code analysis (dependency analysis, impact analysis).
    
    Raised when:
    - Grep search fails
    - Tree-sitter parsing fails
    - LLM analysis fails
    - Invalid analysis results
    """
    pass
