"""Tests for OpenAI Adapter - LLM CI parsing."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from acr_system.domain.entities.entities import CIToolResult, DiffHunk, ParsedCIIssue
from acr_system.domain.value_objects.value_objects import FilePath
from acr_system.infrastructure.llm.openai_adapter import OpenAIAdapter


@pytest.fixture
def openai_adapter():
    """Fixture for OpenAIAdapter."""
    return OpenAIAdapter(api_key="test-key", model="gpt-4o", ci_parsing_model="gpt-4o-mini")


@pytest.fixture
def mock_ci_result_ruff():
    """Mock CI result from Ruff."""
    return CIToolResult(
        tool_name="Ruff",
        status="failure",
        raw_output="""src/main.py:10:1: F401 'typing.Optional' imported but unused
src/main.py:25:5: E501 line too long (92 > 88 characters)
src/utils.py:15:10: W291 trailing whitespace""",
        files_mentioned={"src/main.py", "src/utils.py"},
        conclusion="failure",
    )


@pytest.fixture
def mock_ci_result_mypy():
    """Mock CI result from MyPy."""
    return CIToolResult(
        tool_name="mypy",
        status="failure",
        raw_output="""src/main.py:15: error: Incompatible return value type (got "str", expected "int")
src/config.py:30: warning: Unused 'type: ignore' comment
tests/test_utils.py:5: note: See https://mypy.readthedocs.io/""",
        files_mentioned={"src/main.py", "src/config.py", "tests/test_utils.py"},
        conclusion="failure",
    )


@pytest.fixture
def mock_ci_result_eslint():
    """Mock CI result from ESLint (JSON format)."""
    return CIToolResult(
        tool_name="ESLint",
        status="failure",
        raw_output="""{
  "files": [
    {
      "path": "src/app.js",
      "messages": [
        {"line": 10, "column": 5, "severity": "error", "message": "Prefer const", "ruleId": "prefer-const"}
      ]
    }
  ]
}""",
        files_mentioned={"src/app.js"},
        conclusion="failure",
    )


class TestOpenAIAdapterCIParsing:
    """Tests for OpenAI adapter CI parsing with small LLM."""
    
    @pytest.mark.asyncio
    async def test_parse_ci_output_ruff(self, openai_adapter, mock_ci_result_ruff):
        """Test parsing Ruff output with LLM."""
        # Mock OpenAI response
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content="""{
  "issues": [
    {
      "file_path": "src/main.py",
      "line_number": 10,
      "severity": "error",
      "issue_code": "F401",
      "message": "'typing.Optional' imported but unused",
      "suggestion": "Remove unused import"
    },
    {
      "file_path": "src/main.py",
      "line_number": 25,
      "severity": "warning",
      "issue_code": "E501",
      "message": "line too long (92 > 88 characters)",
      "suggestion": "Break line into multiple lines"
    }
  ]
}"""
                )
            )
        ]
        
        with patch.object(
            openai_adapter.client.chat.completions,
            'create',
            new=AsyncMock(return_value=mock_response),
        ) as mock_create:
            changed_files = {"src/main.py", "src/utils.py"}
            
            issues = await openai_adapter.parse_ci_output(
                ci_result=mock_ci_result_ruff,
                changed_files=changed_files,
            )
            
            # Verify correct model used (gpt-4o-mini)
            assert mock_create.called
            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["model"] == "gpt-4o-mini"
            assert call_kwargs["temperature"] == 0.1
            
            # Verify parsed issues
            assert len(issues) == 2
            assert issues[0].tool_name == "Ruff"
            assert issues[0].file_path == "src/main.py"
            assert issues[0].line_number == 10
            assert issues[0].severity == "error"
            assert issues[0].issue_code == "F401"
            assert "unused" in issues[0].message.lower()
    
    @pytest.mark.asyncio
    async def test_parse_ci_output_mypy(self, openai_adapter, mock_ci_result_mypy):
        """Test parsing MyPy output with LLM."""
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content="""{
  "issues": [
    {
      "file_path": "src/main.py",
      "line_number": 15,
      "severity": "error",
      "issue_code": null,
      "message": "Incompatible return value type (got 'str', expected 'int')",
      "suggestion": "Change return type or fix return value"
    },
    {
      "file_path": "src/config.py",
      "line_number": 30,
      "severity": "warning",
      "issue_code": null,
      "message": "Unused 'type: ignore' comment",
      "suggestion": "Remove unnecessary type ignore comment"
    }
  ]
}"""
                )
            )
        ]
        
        with patch.object(
            openai_adapter.client.chat.completions,
            'create',
            new=AsyncMock(return_value=mock_response),
        ):
            changed_files = {"src/main.py", "src/config.py"}
            
            issues = await openai_adapter.parse_ci_output(
                ci_result=mock_ci_result_mypy,
                changed_files=changed_files,
            )
            
            assert len(issues) == 2
            assert issues[0].tool_name == "mypy"
            assert issues[0].severity == "error"
            assert "Incompatible" in issues[0].message
            assert issues[1].severity == "warning"
    
    @pytest.mark.asyncio
    async def test_parse_ci_output_filters_changed_files(self, openai_adapter, mock_ci_result_mypy):
        """Test that LLM filters issues to only changed files."""
        # LLM should only return issues for changed files
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content="""{
  "issues": [
    {
      "file_path": "src/main.py",
      "line_number": 15,
      "severity": "error",
      "issue_code": null,
      "message": "Incompatible return value type",
      "suggestion": null
    }
  ]
}"""
                )
            )
        ]
        
        with patch.object(
            openai_adapter.client.chat.completions,
            'create',
            new=AsyncMock(return_value=mock_response),
        ):
            # Only one file changed
            changed_files = {"src/main.py"}
            
            issues = await openai_adapter.parse_ci_output(
                ci_result=mock_ci_result_mypy,
                changed_files=changed_files,
            )
            
            # LLM should filter out issues from src/config.py and tests/test_utils.py
            assert len(issues) == 1
            assert issues[0].file_path == "src/main.py"
    
    @pytest.mark.asyncio
    async def test_parse_ci_output_handles_json_format(self, openai_adapter, mock_ci_result_eslint):
        """Test parsing JSON-formatted CI output."""
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content="""{
  "issues": [
    {
      "file_path": "src/app.js",
      "line_number": 10,
      "severity": "error",
      "issue_code": "prefer-const",
      "message": "Prefer const over let",
      "suggestion": "Change 'let' to 'const'"
    }
  ]
}"""
                )
            )
        ]
        
        with patch.object(
            openai_adapter.client.chat.completions,
            'create',
            new=AsyncMock(return_value=mock_response),
        ):
            changed_files = {"src/app.js"}
            
            issues = await openai_adapter.parse_ci_output(
                ci_result=mock_ci_result_eslint,
                changed_files=changed_files,
            )
            
            assert len(issues) == 1
            assert issues[0].file_path == "src/app.js"
            assert issues[0].line_number == 10
            assert issues[0].issue_code == "prefer-const"
    
    @pytest.mark.asyncio
    async def test_parse_ci_output_handles_no_line_numbers(self, openai_adapter):
        """Test parsing CI output without line numbers (e.g., coverage reports)."""
        ci_result = CIToolResult(
            tool_name="pytest-coverage",
            status="failure",
            raw_output="""Coverage report:
TOTAL: 42% coverage

Missing coverage in:
- src/handlers/auth.py
- src/utils/validation.py
Required minimum: 80%""",
            files_mentioned={"src/handlers/auth.py", "src/utils/validation.py"},
            conclusion="failure",
        )
        
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content="""{
  "issues": [
    {
      "file_path": "src/handlers/auth.py",
      "line_number": null,
      "severity": "warning",
      "issue_code": null,
      "message": "Missing test coverage (current: 42%, required: 80%)",
      "suggestion": "Add unit tests for this module"
    }
  ]
}"""
                )
            )
        ]
        
        with patch.object(
            openai_adapter.client.chat.completions,
            'create',
            new=AsyncMock(return_value=mock_response),
        ):
            changed_files = {"src/handlers/auth.py"}
            
            issues = await openai_adapter.parse_ci_output(
                ci_result=ci_result,
                changed_files=changed_files,
            )
            
            assert len(issues) == 1
            assert issues[0].line_number is None
            assert "coverage" in issues[0].message.lower()
    
    @pytest.mark.asyncio
    async def test_parse_ci_output_handles_errors(self, openai_adapter, mock_ci_result_ruff):
        """Test error handling for LLM parsing failures."""
        with patch.object(
            openai_adapter.client.chat.completions,
            'create',
            new=AsyncMock(side_effect=Exception("API error")),
        ):
            changed_files = {"src/main.py"}
            
            # Should return empty list on error, not raise
            issues = await openai_adapter.parse_ci_output(
                ci_result=mock_ci_result_ruff,
                changed_files=changed_files,
            )
            
            assert issues == []
    
    @pytest.mark.asyncio
    async def test_parse_ci_output_handles_invalid_json_response(self, openai_adapter, mock_ci_result_ruff):
        """Test handling of invalid JSON from LLM."""
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content="This is not valid JSON at all, just plain text"
                )
            )
        ]
        
        with patch.object(
            openai_adapter.client.chat.completions,
            'create',
            new=AsyncMock(return_value=mock_response),
        ):
            changed_files = {"src/main.py"}
            
            issues = await openai_adapter.parse_ci_output(
                ci_result=mock_ci_result_ruff,
                changed_files=changed_files,
            )
            
            # Should handle gracefully and return empty list
            assert issues == []


class TestOpenAIAdapterReviewParsing:
        def test_parse_review_response_anchors_method_rename_to_definition_line(self, openai_adapter):
                hunk = DiffHunk(
                        file_path=FilePath("acr_system/domain/services/services.py"),
                        old_start_line=35,
                        old_line_count=8,
                        new_start_line=35,
                        new_line_count=10,
                        content="""@@ -35,8 +35,10 @@
 class ContextBuilder:
         def helper(self):
                 pass

         async def build_full_context(self, diff_hunk, pr, rag_config=None):
                 return []

 usage = obj.build_full_context(diff_hunk, pr)
 """,
                )

                response = """{
    "comments": [
        {
            "line": 38,
            "severity": "warning",
            "message": "Method rename from 'build_context' to 'build_full_context' changed a public symbol and all call sites must use the new name."
        }
    ]
}"""

                comments = openai_adapter._parse_review_response(response, hunk)

                assert len(comments) == 1
                assert comments[0].line_number == 39

        def test_parse_review_response_filters_speculative_comments(self, openai_adapter):
                hunk = DiffHunk(
                        file_path=FilePath("src/main.py"),
                        old_start_line=1,
                        old_line_count=1,
                        new_start_line=1,
                        new_line_count=4,
                        content="""@@ -1,1 +1,4 @@
def run():
        value = 1 / 0
        return value
""",
                )

                response = """{
    "comments": [
        {
            "line": 1,
            "severity": "warning",
            "message": "This appears to be risky and may break at runtime; requires verification."
        },
        {
            "line": 2,
            "severity": "error",
            "message": "Division by zero is guaranteed at runtime on line 2."
        }
    ]
}"""

                comments = openai_adapter._parse_review_response(response, hunk)

                assert len(comments) == 1
                assert comments[0].severity.level == "error"
                assert "Division by zero is guaranteed" in comments[0].message
