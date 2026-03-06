"""Tests for Anthropic Claude adapter."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from acr_system.domain.entities.entities import (
    CIToolResult,
    CodeContext,
    DiffHunk,
    ParsedCIIssue,
)
from acr_system.domain.value_objects.value_objects import FilePath, Language, Severity
from acr_system.infrastructure.llm.anthropic_adapter import AnthropicAdapter
from acr_system.shared.exceptions.infrastructure_exceptions import LLMProviderError


@pytest.fixture
def mock_anthropic_available():
    """Mock anthropic package availability."""
    with patch("acr_system.infrastructure.llm.anthropic_adapter.ANTHROPIC_AVAILABLE", True):
        yield


@pytest.fixture
def anthropic_adapter(mock_anthropic_available):
    """Create AnthropicAdapter instance with mocked client."""
    with patch("acr_system.infrastructure.llm.anthropic_adapter.AsyncAnthropic"):
        adapter = AnthropicAdapter(
            api_key="test-key",
            model="claude-3-5-sonnet-20241022",
            ci_parsing_model="claude-3-5-haiku-20241022",
        )
        return adapter


@pytest.fixture
def sample_diff_hunk():
    """Create a sample diff hunk for testing."""
    return DiffHunk(
        file_path=FilePath("src/main.py"),
        old_start_line=10,
        old_line_count=5,
        new_start_line=10,
        new_line_count=7,
        content="""@@ -10,5 +10,7 @@
 def calculate(x, y):
-    return x + y
+    # Added validation
+    if not isinstance(x, int) or not isinstance(y, int):
+        raise ValueError("Arguments must be integers")
+    return x + y
""",
    )


@pytest.fixture
def sample_ci_result():
    """Create a sample CI result for testing."""
    return CIToolResult(
        tool_name="Ruff",
        status="failure",
        raw_output="""src/main.py:15:1: E501 line too long (120 > 88 characters)
src/main.py:23:5: F401 'os' imported but unused
src/utils.py:10:1: E302 expected 2 blank lines, found 1""",
        files_mentioned={"src/main.py", "src/utils.py"},
        conclusion="failed",
    )


class TestAnthropicAdapter:
    """Tests for AnthropicAdapter."""
    
    def test_init_without_anthropic_raises_error(self):
        """Test that initialization without anthropic package raises error."""
        with patch("acr_system.infrastructure.llm.anthropic_adapter.ANTHROPIC_AVAILABLE", False):
            with pytest.raises(LLMProviderError, match="Anthropic package not installed"):
                AnthropicAdapter(api_key="test-key")
    
    def test_init_with_default_models(self, mock_anthropic_available):
        """Test initialization with default models."""
        with patch("acr_system.infrastructure.llm.anthropic_adapter.AsyncAnthropic"):
            adapter = AnthropicAdapter(api_key="test-key")
            
            assert adapter.model == "claude-3-5-sonnet-20241022"
            assert adapter.ci_parsing_model == "claude-3-5-haiku-20241022"
    
    def test_init_with_custom_models(self, mock_anthropic_available):
        """Test initialization with custom models."""
        with patch("acr_system.infrastructure.llm.anthropic_adapter.AsyncAnthropic"):
            adapter = AnthropicAdapter(
                api_key="test-key",
                model="claude-3-opus-20240229",
                ci_parsing_model="claude-3-5-haiku-20241022",
            )
            
            assert adapter.model == "claude-3-opus-20240229"
            assert adapter.ci_parsing_model == "claude-3-5-haiku-20241022"
    
    @pytest.mark.asyncio
    async def test_generate_review_comments_success(
        self,
        anthropic_adapter,
        sample_diff_hunk,
    ):
        """Test successful generation of review comments."""
        # Mock response with text content
        mock_text_block = MagicMock()
        mock_text_block.text = """{
  "comments": [
    {
      "line": 12,
      "severity": "info",
      "message": "Good addition of input validation",
      "suggestion": null
    },
    {
      "line": 14,
      "severity": "warning",
      "message": "Consider using custom exception class",
      "suggestion": "raise InvalidArgumentError(\\"Arguments must be integers\\")"
    }
  ]
}"""
        
        mock_response = MagicMock()
        mock_response.content = [mock_text_block]
        
        anthropic_adapter.client.messages.create = AsyncMock(return_value=mock_response)
        
        comments = await anthropic_adapter.generate_review_comments(
            diff_hunk=sample_diff_hunk,
            rules_text="Check for proper error handling",
            context=[],
            ci_issues=[],
        )
        
        assert len(comments) == 2
        assert comments[0].line_number == 12
        assert comments[0].severity.level == Severity.INFO
        assert comments[0].message == "Good addition of input validation"
        
        assert comments[1].line_number == 14
        assert comments[1].severity.level == Severity.WARNING
        assert "custom exception" in comments[1].message
    
    @pytest.mark.asyncio
    async def test_generate_review_comments_with_context(
        self,
        anthropic_adapter,
        sample_diff_hunk,
    ):
        """Test review generation with additional context."""
        context = [
            CodeContext(
                content="# Project uses custom exceptions in src/exceptions.py",
                source="documentation",
                file_path=FilePath("docs/ARCHITECTURE.md"),
                relevance_score=0.95,
            )
        ]
        
        mock_text_block = MagicMock()
        mock_text_block.text = '{"comments": []}'
        
        mock_response = MagicMock()
        mock_response.content = [mock_text_block]
        
        anthropic_adapter.client.messages.create = AsyncMock(return_value=mock_response)
        
        await anthropic_adapter.generate_review_comments(
            diff_hunk=sample_diff_hunk,
            rules_text="Follow project conventions",
            context=context,
            ci_issues=[],
        )
        
        # Verify API was called
        anthropic_adapter.client.messages.create.assert_called_once()
        call_args = anthropic_adapter.client.messages.create.call_args
        
        # Check that context was included in prompt
        prompt = call_args.kwargs["messages"][0]["content"]
        assert "Additional Context" in prompt
        assert "custom exceptions" in prompt
    
    @pytest.mark.asyncio
    async def test_generate_review_comments_with_ci_issues(
        self,
        anthropic_adapter,
        sample_diff_hunk,
    ):
        """Test review generation with CI issues."""
        ci_issues = [
            ParsedCIIssue(
                tool_name="Ruff",
                file_path="src/main.py",
                line_number=15,
                severity="error",
                issue_code="E501",
                message="Line too long",
                suggestion="Break into multiple lines",
            )
        ]
        
        mock_text_block = MagicMock()
        mock_text_block.text = '{"comments": []}'
        
        mock_response = MagicMock()
        mock_response.content = [mock_text_block]
        
        anthropic_adapter.client.messages.create = AsyncMock(return_value=mock_response)
        
        await anthropic_adapter.generate_review_comments(
            diff_hunk=sample_diff_hunk,
            rules_text="Fix linting issues",
            context=[],
            ci_issues=ci_issues,
        )
        
        # Verify CI issues are in prompt
        call_args = anthropic_adapter.client.messages.create.call_args
        prompt = call_args.kwargs["messages"][0]["content"]
        assert "CI Tool Issues" in prompt
        assert "Ruff" in prompt
        assert "Line too long" in prompt
    
    @pytest.mark.asyncio
    async def test_generate_review_comments_api_error(
        self,
        anthropic_adapter,
        sample_diff_hunk,
    ):
        """Test handling of API errors."""
        anthropic_adapter.client.messages.create = AsyncMock(
            side_effect=Exception("API Error")
        )
        
        with pytest.raises(LLMProviderError, match="Anthropic API error"):
            await anthropic_adapter.generate_review_comments(
                diff_hunk=sample_diff_hunk,
                rules_text="Review code",
                context=[],
                ci_issues=[],
            )
    
    @pytest.mark.asyncio
    async def test_parse_ci_output_success(
        self,
        anthropic_adapter,
        sample_ci_result,
    ):
        """Test successful CI output parsing."""
        mock_text_block = MagicMock()
        mock_text_block.text = """{
  "issues": [
    {
      "file_path": "src/main.py",
      "line_number": 15,
      "severity": "error",
      "issue_code": "E501",
      "message": "line too long (120 > 88 characters)",
      "suggestion": "Break line into multiple lines"
    },
    {
      "file_path": "src/main.py",
      "line_number": 23,
      "severity": "warning",
      "issue_code": "F401",
      "message": "'os' imported but unused",
      "suggestion": "Remove unused import"
    }
  ]
}"""
        
        mock_response = MagicMock()
        mock_response.content = [mock_text_block]
        
        anthropic_adapter.client.messages.create = AsyncMock(return_value=mock_response)
        
        issues = await anthropic_adapter.parse_ci_output(
            ci_result=sample_ci_result,
            changed_files={"src/main.py", "src/utils.py"},
        )
        
        assert len(issues) == 2
        assert issues[0].file_path == "src/main.py"
        assert issues[0].line_number == 15
        assert issues[0].severity == "error"
        assert issues[0].issue_code == "E501"
        
        # Verify cheaper model was used
        call_args = anthropic_adapter.client.messages.create.call_args
        assert call_args.kwargs["model"] == "claude-3-5-haiku-20241022"
    
    @pytest.mark.asyncio
    async def test_parse_ci_output_filters_by_changed_files(
        self,
        anthropic_adapter,
        sample_ci_result,
    ):
        """Test that CI parsing respects changed files filter."""
        mock_text_block = MagicMock()
        mock_text_block.text = '{"issues": []}'
        
        mock_response = MagicMock()
        mock_response.content = [mock_text_block]
        
        anthropic_adapter.client.messages.create = AsyncMock(return_value=mock_response)
        
        await anthropic_adapter.parse_ci_output(
            ci_result=sample_ci_result,
            changed_files={"src/main.py", "src/utils.py"},
        )
        
        # Verify changed files are in prompt
        call_args = anthropic_adapter.client.messages.create.call_args
        prompt = call_args.kwargs["messages"][0]["content"]
        assert "src/main.py" in prompt
        assert "src/utils.py" in prompt
    
    @pytest.mark.asyncio
    async def test_parse_ci_output_handles_errors(
        self,
        anthropic_adapter,
        sample_ci_result,
    ):
        """Test error handling in CI output parsing."""
        anthropic_adapter.client.messages.create = AsyncMock(
            side_effect=Exception("API Error")
        )
        
        # Should return empty list on error, not raise
        issues = await anthropic_adapter.parse_ci_output(
            ci_result=sample_ci_result,
            changed_files={"src/main.py"},
        )
        
        assert issues == []
    
    @pytest.mark.asyncio
    async def test_generate_completion_success(self, anthropic_adapter):
        """Test successful completion generation."""
        mock_text_block = MagicMock()
        mock_text_block.text = "This is a test response"
        
        mock_response = MagicMock()
        mock_response.content = [mock_text_block]
        
        anthropic_adapter.client.messages.create = AsyncMock(return_value=mock_response)
        
        result = await anthropic_adapter.generate_completion(
            prompt="Test prompt",
            temperature=0.5,
            max_tokens=1000,
        )
        
        assert result == "This is a test response"
        
        # Verify correct parameters
        call_args = anthropic_adapter.client.messages.create.call_args
        assert call_args.kwargs["temperature"] == 0.5
        assert call_args.kwargs["max_tokens"] == 1000
    
    @pytest.mark.asyncio
    async def test_generate_completion_api_error(self, anthropic_adapter):
        """Test handling of API errors in completion."""
        anthropic_adapter.client.messages.create = AsyncMock(
            side_effect=Exception("API Error")
        )
        
        with pytest.raises(LLMProviderError, match="Anthropic API error"):
            await anthropic_adapter.generate_completion(prompt="Test")
    
    def test_parse_review_response_with_valid_json(
        self,
        anthropic_adapter,
        sample_diff_hunk,
    ):
        """Test parsing valid JSON response."""
        response = """{
  "comments": [
    {
      "line": 10,
      "severity": "error",
      "message": "Security issue detected",
      "suggestion": "Use parameterized queries"
    }
  ]
}"""
        
        comments = anthropic_adapter._parse_review_response(response, sample_diff_hunk)
        
        assert len(comments) == 1
        assert comments[0].line_number == 10
        assert comments[0].severity.level == Severity.ERROR
        assert "Security issue" in comments[0].message
        assert comments[0].suggestion == "Use parameterized queries"
    
    def test_parse_review_response_with_embedded_json(
        self,
        anthropic_adapter,
        sample_diff_hunk,
    ):
        """Test parsing JSON embedded in markdown."""
        response = """Here's my review:

```json
{
  "comments": [
    {
      "line": 15,
      "severity": "warning",
      "message": "Consider refactoring"
    }
  ]
}
```

Hope this helps!"""
        
        comments = anthropic_adapter._parse_review_response(response, sample_diff_hunk)
        
        assert len(comments) == 1
        assert comments[0].line_number == 15
    
    def test_parse_review_response_with_no_json(
        self,
        anthropic_adapter,
        sample_diff_hunk,
    ):
        """Test handling response without JSON."""
        response = "This is just plain text without JSON"
        
        comments = anthropic_adapter._parse_review_response(response, sample_diff_hunk)
        
        assert comments == []
    
    def test_parse_review_response_with_invalid_json(
        self,
        anthropic_adapter,
        sample_diff_hunk,
    ):
        """Test handling invalid JSON."""
        response = '{"comments": [invalid json]}'
        
        comments = anthropic_adapter._parse_review_response(response, sample_diff_hunk)
        
        assert comments == []
    
    def test_parse_review_response_empty_comments(
        self,
        anthropic_adapter,
        sample_diff_hunk,
    ):
        """Test parsing response with empty comments array."""
        response = '{"comments": []}'
        
        comments = anthropic_adapter._parse_review_response(response, sample_diff_hunk)
        
        assert comments == []
