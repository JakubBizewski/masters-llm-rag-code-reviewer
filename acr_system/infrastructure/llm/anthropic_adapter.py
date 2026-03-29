"""Anthropic Claude adapter for LLM operations."""
from typing import List, Optional, Set

from acr_system.shared.utils.token_counter import UsageStats, approx_token_count

try:
    from anthropic import AsyncAnthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    AsyncAnthropic = None  # type: ignore

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


class AnthropicAdapter(LLMProvider):
    """Adapter for Anthropic Claude models."""
    
    def __init__(
        self,
        api_key: str,
        model: str = "claude-3-5-sonnet-20241022",
        ci_parsing_model: str = "claude-3-5-haiku-20241022",
        usage_stats: Optional[UsageStats] = None,
    ):
        """Initialize Anthropic adapter.
        
        Args:
            api_key: Anthropic API key
            model: Main model for code reviews (default: claude-3-5-sonnet)
            ci_parsing_model: Cheaper model for CI parsing (default: claude-3-5-haiku)
        """
        if not ANTHROPIC_AVAILABLE:
            raise LLMProviderError(
                "Anthropic package not installed. Install with: pip install anthropic"
            )
        
        self.client = AsyncAnthropic(api_key=api_key)
        self.model = model
        self.ci_parsing_model = ci_parsing_model
        self.usage_stats = usage_stats
        
        logger.info(f"Initialized Anthropic adapter with model={model}")
    
    async def generate_review_comments(
        self,
        diff_hunk: DiffHunk,
        rules_text: str,
        context: List[CodeContext],
        ci_issues: List[ParsedCIIssue],
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> List[ReviewComment]:
        """Generate review comments for a diff hunk."""
        try:
            prompt = self._build_review_prompt(
                diff_hunk=diff_hunk,
                rules_text=rules_text,
                context=context,
                ci_issues=ci_issues,
            )
            
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                system="You are an expert code reviewer. Provide constructive, "
                       "specific feedback on code changes.",
                messages=[
                    {"role": "user", "content": prompt},
                ],
            )
            
            # Extract text from response
            result = ""
            for block in response.content:
                if hasattr(block, 'text'):
                    result += block.text

            self._account_usage(
                prompt_text=(
                    "You are an expert code reviewer. Provide constructive, specific feedback on code changes.\n"
                    + prompt
                ),
                completion_text=result,
                response=response,
            )
            
            # Parse LLM response into ReviewComment objects
            comments = self._parse_review_response(result, diff_hunk)
            
            logger.info(
                f"Generated {len(comments)} review comments for {diff_hunk.file_path.value}"
            )
            
            return comments
            
        except Exception as e:
            logger.error(f"Error generating review comments: {e}", exc_info=True)
            raise LLMProviderError(f"Anthropic API error: {e}") from e

    def _account_usage(self, prompt_text: str, completion_text: str, response) -> None:  # type: ignore
        if self.usage_stats is None:
            return

        usage = getattr(response, "usage", None)
        if usage is not None:
            input_tokens = getattr(usage, "input_tokens", None)
            output_tokens = getattr(usage, "output_tokens", None)
            if input_tokens is not None or output_tokens is not None:
                self.usage_stats.add(
                    prompt_tokens=int(input_tokens or 0),
                    completion_tokens=int(output_tokens or 0),
                )
                return

        self.usage_stats.add(
            prompt_tokens=approx_token_count(prompt_text),
            completion_tokens=approx_token_count(completion_text),
        )
    
    def _build_review_prompt(
        self,
        diff_hunk: DiffHunk,
        rules_text: str,
        context: List[CodeContext],
        ci_issues: List[ParsedCIIssue],
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
    ) -> List[ReviewComment]:
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
                
                # Convert line number: LLM often returns relative line numbers (1, 2, 3...)
                # within the diff, but GitHub needs absolute line numbers from the file
                raw_line = comment_data.get("line")
                if raw_line is not None:
                    # If line number is small (< new_start_line), treat as relative to hunk
                    if raw_line < diff_hunk.new_start_line:
                        absolute_line = diff_hunk.new_start_line + raw_line - 1
                    else:
                        absolute_line = raw_line
                    
                    # Validate line is within hunk range, otherwise make it a general comment
                    if not diff_hunk.is_line_in_hunk(absolute_line):
                        logger.warning(
                            f"Line {raw_line} (absolute: {absolute_line}) outside hunk range "
                            f"{diff_hunk.new_start_line}-{diff_hunk.new_start_line + diff_hunk.new_line_count - 1}"
                        )
                        absolute_line = None
                else:
                    absolute_line = None
                
                comment = ReviewComment(
                    file_path=diff_hunk.file_path,
                    line_number=absolute_line,
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
        changed_files: Set[str],
    ) -> List[ParsedCIIssue]:
        """Parse CI tool output and extract relevant issues.
        
        Uses cheaper Claude Haiku model for parsing raw CI outputs.
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
            
            response = await self.client.messages.create(
                model=self.ci_parsing_model,  # Use cheaper model
                max_tokens=2000,
                temperature=0.1,  # Low temperature for structured output
                system="You are an expert at parsing CI/CD tool outputs in any format. "
                       "Extract structured issue information accurately.",
                messages=[
                    {"role": "user", "content": prompt},
                ],
            )
            
            # Extract text from response
            result = ""
            for block in response.content:
                if hasattr(block, 'text'):
                    result += block.text

            self._account_usage(
                prompt_text=(
                    "You are an expert at parsing CI/CD tool outputs in any format. Extract structured issue information accurately.\n"
                    + prompt
                ),
                completion_text=result,
                response=response,
            )
            
            # Parse response
            import json
            start = result.find('{')
            end = result.rfind('}') + 1
            json_str = result[start:end]
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
            
            logger.info(
                f"Parsed {len(issues)} CI issues from {ci_result.tool_name}"
            )
            
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
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
            )
            
            # Extract text from response
            result = ""
            for block in response.content:
                if hasattr(block, 'text'):
                    result += block.text

            self._account_usage(prompt_text=prompt, completion_text=result, response=response)
            
            return result
            
        except Exception as e:
            raise LLMProviderError(f"Anthropic API error: {e}") from e
