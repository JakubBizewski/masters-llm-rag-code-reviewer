"""OpenAI adapter for LLM operations."""
from typing import Optional

try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    AsyncOpenAI = None  # type: ignore

from acr_system.domain.entities.entities import (
    CIToolResult,
    CodeContext,
    DiffHunk,
    ParsedCIIssue,
    ReviewComment,
)
from acr_system.domain.interfaces.ports import LLMProvider
from acr_system.domain.value_objects.value_objects import FilePath, Severity
from acr_system.shared.exceptions.infrastructure_exceptions import LLMProviderError
from acr_system.shared.logging.logger import get_logger

logger = get_logger(__name__)


class OpenAIAdapter(LLMProvider):
    """Adapter for OpenAI GPT models."""
    
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        ci_parsing_model: str = "gpt-4o-mini",
    ):
        """Initialize OpenAI adapter.
        
        Args:
            api_key: OpenAI API key
            model: Main model for code reviews (default: gpt-4o)
            ci_parsing_model: Cheaper model for CI parsing (default: gpt-4o-mini)
        """
        if not OPENAI_AVAILABLE:
            raise LLMProviderError(
                "OpenAI package not installed. Install with: pip install openai"
            )
        
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self.ci_parsing_model = ci_parsing_model
    
    async def generate_review_comments(
        self,
        diff_hunk: DiffHunk,
        rules_text: str,
        context: list[CodeContext],
        ci_issues: list[ParsedCIIssue],
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> list[ReviewComment]:
        """Generate review comments for a diff hunk."""
        try:
            prompt = self._build_review_prompt(
                diff_hunk=diff_hunk,
                rules_text=rules_text,
                context=context,
                ci_issues=ci_issues,
            )
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert code reviewer. Provide constructive, "
                                 "specific feedback on code changes.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            
            result = response.choices[0].message.content
            
            # Parse LLM response into ReviewComment objects
            comments = self._parse_review_response(result, diff_hunk)
            
            return comments
            
        except Exception as e:
            logger.error(f"Error generating review comments: {e}", exc_info=True)
            raise LLMProviderError(f"OpenAI API error: {e}") from e
    
    def _build_review_prompt(
        self,
        diff_hunk: DiffHunk,
        rules_text: str,
        context: list[CodeContext],
        ci_issues: list[ParsedCIIssue],
    ) -> str:
        """Build prompt for code review."""
        prompt = f"""# Code Review Task

## File: {diff_hunk.file_path.value}
Language: {diff_hunk.language.name}

## Review Rules
{rules_text}

## Code Changes (Unified Diff)
```
{diff_hunk.content}
```

"""
        
        # Add context if available
        if context:
            prompt += "## Additional Context\n"
            for ctx in context[:3]:  # Limit to top 3 contexts
                prompt += f"### From {ctx.source}\n```\n{ctx.content[:500]}\n```\n\n"
        
        # Add CI issues if available
        if ci_issues:
            prompt += "## CI Tool Issues\n"
            for issue in ci_issues:
                prompt += f"- [{issue.tool_name}] Line {issue.line_number}: {issue.message}\n"
            prompt += "\n"
        
        prompt += """## Instructions
Review the code changes and provide feedback in the following JSON format:

{
  "comments": [
    {
      "line": <line_number>,
      "severity": "error|warning|info",
      "message": "<concise feedback>",
      "suggestion": "<optional: specific code suggestion>"
    }
  ]
}

Only include comments for actual issues. If the code looks good, return an empty comments array.
Focus on: correctness, security, performance, maintainability, and adherence to the rules above.
"""
        
        return prompt
    
    def _parse_review_response(
        self,
        response: Optional[str],
        diff_hunk: DiffHunk,
    ) -> list[ReviewComment]:
        """Parse LLM response into ReviewComment objects."""
        import json
        
        if not response:
            return []
        
        try:
            # Try to extract JSON from response
            start = response.find('{')
            end = response.rfind('}') + 1
            
            if start == -1 or end == 0:
                logger.warning("No JSON found in LLM response")
                return []
            
            json_str = response[start:end]
            data = json.loads(json_str)
            
            comments = []
            for comment_data in data.get("comments", []):
                severity_map = {
                    "error": Severity.ERROR,
                    "warning": Severity.WARNING,
                    "info": Severity.INFO,
                }
                
                severity = severity_map.get(
                    comment_data.get("severity", "info"),
                    Severity.INFO
                )
                
                comment = ReviewComment(
                    file_path=diff_hunk.file_path,
                    line_number=comment_data.get("line"),
                    severity=Severity(level=severity),
                    message=comment_data["message"],
                    suggestion=comment_data.get("suggestion"),
                    rule_name="llm_review",
                )
                comments.append(comment)
            
            return comments
            
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing LLM JSON response: {e}")
            return []
    
    async def parse_ci_output(
        self,
        ci_result: CIToolResult,
        changed_files: set[str],
    ) -> list[ParsedCIIssue]:
        """Parse CI tool output and extract relevant issues.
        
        Uses cheaper GPT-4o-mini model for parsing raw CI outputs.
        Filters issues to only include those related to changed files.
        """
        try:
            prompt = f"""You are a CI output parser. Extract issues from the tool output below that are relevant to the changed files.

## Changed Files
{', '.join(sorted(changed_files))}

## CI Tool Output
**Tool**: {ci_result.tool_name}
**Status**: {ci_result.status}
**Conclusion**: {ci_result.conclusion}

```
{ci_result.raw_output[:3000]}
```

## Task
1. Parse the output above (any format: JSON, text, logs)
2. Extract only issues related to the changed files listed above
3. Return structured JSON with the following format:

{{
  "issues": [
    {{
      "file_path": "path/to/file.py",
      "line_number": 42,  // or null if not available
      "severity": "error",  // error, warning, or info
      "issue_code": "E501",  // tool-specific code, or null
      "message": "Line too long (120 > 88 characters)",
      "suggestion": "Break line into multiple lines"  // or null
    }}
  ]
}}

**Important**: Only include issues for files in the changed files list. Ignore issues for other files.
"""
            
            response = await self.client.chat.completions.create(
                model=self.ci_parsing_model,  # Use cheaper model
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at parsing CI/CD tool outputs in any format. "
                                 "Extract structured issue information accurately.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,  # Low temperature for structured output
                max_tokens=2000,
            )
            
            result = response.choices[0].message.content
            
            # Parse response
            import json
            start = result.find('{')  # type: ignore
            end = result.rfind('}') + 1  # type: ignore
            json_str = result[start:end]  # type: ignore
            data = json.loads(json_str)
            
            issues = []
            for issue_data in data.get("issues", []):
                issue = ParsedCIIssue(
                    tool_name=ci_result.tool_name,
                    file_path=issue_data["file_path"],
                    line_number=issue_data.get("line_number"),
                    severity=issue_data["severity"],
                    issue_code=issue_data.get("issue_code"),
                    message=issue_data["message"],
                    suggestion=issue_data.get("suggestion"),
                )
                issues.append(issue)
            
            return issues
            
        except Exception as e:
            logger.error(f"Error parsing CI output: {e}", exc_info=True)
            return []
    
    async def generate_completion(
        self,
        prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> str:
        """Generate a completion for a prompt."""
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            
            return response.choices[0].message.content or ""
            
        except Exception as e:
            raise LLMProviderError(f"OpenAI API error: {e}") from e
