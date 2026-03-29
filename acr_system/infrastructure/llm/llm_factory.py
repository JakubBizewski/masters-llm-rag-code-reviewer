"""LLM Provider Factory for creating appropriate LLM adapters."""
import os
from typing import Dict, Optional

from acr_system.shared.utils.token_counter import UsageStats

from acr_system.domain.interfaces.ports import LLMProvider
from acr_system.domain.value_objects.value_objects import LLMConfig
from acr_system.infrastructure.llm.anthropic_adapter import AnthropicAdapter
from acr_system.infrastructure.llm.openai_adapter import OpenAIAdapter
from acr_system.shared.exceptions.infrastructure_exceptions import LLMProviderError
from acr_system.shared.logging.logger import get_logger

logger = get_logger(__name__)


class LLMProviderFactory:
    """Factory for creating LLM provider instances based on configuration.
    
    This factory allows different files/patterns to use different LLM providers
    and models, as configured in .acr-config.yml.
    """
    
    def __init__(
        self,
        openai_api_key: Optional[str] = None,
        anthropic_api_key: Optional[str] = None,
        usage_stats: Optional[UsageStats] = None,
    ):
        """Initialize factory with API keys.
        
        Args:
            openai_api_key: OpenAI API key (from env if not provided)
            anthropic_api_key: Anthropic API key (from env if not provided)
        """
        self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        self.anthropic_api_key = anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")

        # Optional usage collector for experimental evaluation
        self.usage_stats = usage_stats
        
        # Cache providers to avoid recreating for same config
        self._provider_cache: Dict[str, LLMProvider] = {}
    
    def create_provider(self, llm_config: LLMConfig) -> LLMProvider:
        """Create LLM provider based on configuration.
        
        Args:
            llm_config: LLM configuration specifying provider and model
            
        Returns:
            LLM provider instance
            
        Raises:
            LLMProviderError: If provider is unsupported or API key missing
        """
        # Create cache key
        cache_key = f"{llm_config.provider}:{llm_config.model}"
        
        # Return cached provider if available
        if cache_key in self._provider_cache:
            logger.debug(f"Using cached LLM provider: {cache_key}")
            return self._provider_cache[cache_key]
        
        # Create new provider
        provider = self._create_provider_instance(llm_config)
        
        # Cache and return
        self._provider_cache[cache_key] = provider
        logger.info(f"Created LLM provider: {llm_config.provider} with model {llm_config.model}")
        
        return provider
    
    def _create_provider_instance(self, llm_config: LLMConfig) -> LLMProvider:
        """Create new provider instance.
        
        Args:
            llm_config: LLM configuration
            
        Returns:
            New LLM provider instance
            
        Raises:
            LLMProviderError: If provider unsupported or API key missing
        """
        provider_name = llm_config.provider.lower()
        
        if provider_name == "openai":
            if not self.openai_api_key:
                raise LLMProviderError(
                    "OpenAI API key not provided. Set OPENAI_API_KEY environment variable."
                )
            
            return OpenAIAdapter(
                api_key=self.openai_api_key,
                model=llm_config.model,
                ci_parsing_model=os.getenv("OPENAI_CI_MODEL", "gpt-4o-mini"),
                usage_stats=self.usage_stats,
            )
        
        elif provider_name == "anthropic":
            if not self.anthropic_api_key:
                raise LLMProviderError(
                    "Anthropic API key not provided. Set ANTHROPIC_API_KEY environment variable."
                )
            
            return AnthropicAdapter(
                api_key=self.anthropic_api_key,
                model=llm_config.model,
                ci_parsing_model=os.getenv("ANTHROPIC_CI_MODEL", "claude-3-5-haiku-20241022"),
                usage_stats=self.usage_stats,
            )
        
        else:
            raise LLMProviderError(
                f"Unsupported LLM provider: {provider_name}. "
                f"Supported providers: openai, anthropic"
            )
    
    def clear_cache(self) -> None:
        """Clear provider cache. Useful for testing."""
        self._provider_cache.clear()
        logger.debug("Cleared LLM provider cache")
