"""Tests for domain value objects."""
import pytest

from acr_system.domain.value_objects.value_objects import (
    FilePath,
    Language,
    LLMConfig,
    RAGConfig,
    RuleSet,
    Severity,
)


class TestFilePath:
    """Tests for FilePath value object."""
    
    def test_create_file_path(self):
        """Test creating a file path."""
        path = FilePath("src/main.py")
        assert path.value == "src/main.py"
        assert str(path) == "src/main.py"
    
    def test_file_extension(self):
        """Test getting file extension."""
        path = FilePath("src/main.py")
        assert path.extension == ".py"
    
    def test_filename(self):
        """Test getting filename."""
        path = FilePath("src/main.py")
        assert path.filename == "main.py"
    
    def test_empty_path_raises_error(self):
        """Test that empty path raises ValueError."""
        with pytest.raises(ValueError, match="File path cannot be empty"):
            FilePath("")


class TestLanguage:
    """Tests for Language value object."""
    
    def test_create_language(self):
        """Test creating a language."""
        lang = Language("python")
        assert lang.name == "python"
    
    def test_language_normalized_to_lowercase(self):
        """Test that language name is normalized to lowercase."""
        lang = Language("Python")
        assert lang.name == "python"
    
    def test_from_extension(self):
        """Test creating language from file extension."""
        lang = Language.from_extension(".py")
        assert lang.name == "python"
        
        lang = Language.from_extension(".js")
        assert lang.name == "javascript"
    
    def test_unknown_extension(self):
        """Test unknown extension returns 'unknown'."""
        lang = Language.from_extension(".xyz")
        assert lang.name == "unknown"


class TestSeverity:
    """Tests for Severity value object."""
    
    def test_create_severity(self):
        """Test creating severity."""
        sev = Severity(level=Severity.ERROR)
        assert sev.level == "error"
    
    def test_priority(self):
        """Test severity priority."""
        error = Severity(level=Severity.ERROR)
        warning = Severity(level=Severity.WARNING)
        info = Severity(level=Severity.INFO)
        
        assert error.priority > warning.priority
        assert warning.priority > info.priority
    
    def test_invalid_severity_raises_error(self):
        """Test that invalid severity raises ValueError."""
        with pytest.raises(ValueError, match="Invalid severity level"):
            Severity(level="critical")


class TestRuleSet:
    """Tests for RuleSet value object."""
    
    def test_create_ruleset(self):
        """Test creating a rule set."""
        rules = RuleSet(
            name="security",
            enabled=True,
            rules_text="Check for SQL injection",
        )
        assert rules.name == "security"
        assert rules.enabled is True
    
    def test_empty_name_raises_error(self):
        """Test that empty name raises ValueError."""
        with pytest.raises(ValueError, match="name cannot be empty"):
            RuleSet(name="", enabled=True, rules_text="Some rules")


class TestLLMConfig:
    """Tests for LLMConfig value object."""
    
    def test_create_llm_config(self):
        """Test creating LLM config."""
        config = LLMConfig(
            provider="openai",
            model="gpt-4o",
            temperature=0.3,
            max_tokens=2000,
        )
        assert config.provider == "openai"
        assert config.model == "gpt-4o"
    
    def test_invalid_temperature_raises_error(self):
        """Test that invalid temperature raises ValueError."""
        with pytest.raises(ValueError, match="Temperature must be between"):
            LLMConfig(temperature=3.0)
    
    def test_invalid_max_tokens_raises_error(self):
        """Test that invalid max_tokens raises ValueError."""
        with pytest.raises(ValueError, match="max_tokens must be positive"):
            LLMConfig(max_tokens=0)


class TestRAGConfig:
    """Tests for RAGConfig value object."""
    
    def test_create_rag_config(self):
        """Test creating RAG config."""
        config = RAGConfig(
            enabled=True,
            top_k=5,
            documentation_paths=["docs/"],
            architectural_docs=["ARCHITECTURE.md"],
        )
        assert config.enabled is True
        assert config.top_k == 5
    
    def test_default_values(self):
        """Test default values for RAG config."""
        config = RAGConfig()
        assert config.enabled is True
        assert config.top_k == 5
        assert config.documentation_paths == []
    
    def test_invalid_top_k_raises_error(self):
        """Test that invalid top_k raises ValueError."""
        with pytest.raises(ValueError, match="top_k must be positive"):
            RAGConfig(top_k=0)
