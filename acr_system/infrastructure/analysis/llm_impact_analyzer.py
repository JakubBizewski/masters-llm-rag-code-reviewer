"""LLM-based Impact Analyzer implementation.

Uses LLM for semantic analysis of breaking changes.
Requires LLMProvider for reasoning about code impact.
"""
import json
import time
from typing import Dict, List, Optional

from acr_system.domain.entities.entities import DiffHunk, FunctionNode
from acr_system.domain.interfaces.ports import ImpactAnalyzer, LLMProvider
from acr_system.domain.value_objects.value_objects import (
    BreakingChange,
    CallSite,
    FilePath,
    ImpactAnalysisResult,
    ImportSite,
    Severity,
)
from acr_system.shared.exceptions.infrastructure_exceptions import AnalysisError
from acr_system.shared.logging.logger import get_logger

logger = get_logger(__name__)


class LLMImpactAnalyzer(ImpactAnalyzer):
    """Implementation of ImpactAnalyzer using LLM reasoning.
    
    Requires LLMProvider (GPT-4, Claude, local LLM).
    
    Prompt Strategy (from literature):
    - Pornprasit2024FineTuningPromptingCR: Function isolation for context enhancement
    - Ren2025HydraReviewer: Call graph context detection for breaking changes
    - Tao2024DELTA: Diff-based reasoning for API changes
    
    LLM tasks:
    - Signature analysis (parameters, return type changes)
    - Semantic analysis (logic changes, edge cases)
    - Contract analysis (preconditions, postconditions)
    - Fix generation (how to update callers)
    """
    
    def __init__(
        self,
        llm: LLMProvider,
        prompt_template: Optional[str] = None,
    ):
        """Initialize the analyzer.
        
        Args:
            llm: LLM provider for semantic analysis
            prompt_template: Optional custom prompt template
        """
        self.llm = llm
        self.prompt_template = prompt_template
        
    async def analyze_impact(
        self,
        changed_function: FunctionNode,
        diff_hunk: DiffHunk,
        callers: List[CallSite],
        repository: str,
    ) -> ImpactAnalysisResult:
        """Analyze impact of a function change using LLM reasoning.
        
        Workflow:
        1. Build comprehensive prompt (function diff + callers context)
        2. LLM call (temperature=0.2 for consistency)
        3. Parse JSON response (breaking_changes, severity, fixes)
        4. Build ImpactAnalysisResult
        
        LLM receives:
        - Changed function: before/after diff
        - Full function body (with signature)
        - All callers: code context (5 lines around call site)
        - Caller function names
        
        LLM produces:
        - Per-caller analysis (affected? why? what breaks? how to fix?)
        - Severity assessment (critical/high/medium/low)
        - Overall summary
        
        Args:
            changed_function: Function that was modified (from AST)
            diff_hunk: Diff showing the changes
            callers: List of places where function is called (from CallGraphAnalyzer)
            repository: Repository identifier
            
        Returns:
            Impact analysis result with breaking changes and fix suggestions
            
        Raises:
            AnalysisError: If LLM call fails or response is invalid JSON
        """
        start_time = time.time()
        
        logger.info(
            f"Analyzing impact of {changed_function.name} with {len(callers)} callers"
        )
        
        try:
            # Step 1: Build comprehensive prompt
            prompt = self._build_impact_analysis_prompt(
                changed_function, diff_hunk, callers
            )
            
            # Step 2: LLM call (low temperature for consistent reasoning)
            try:
                llm_response = await self.llm.generate_completion(
                    prompt=prompt,
                    temperature=0.2,  # Low variance for factual analysis
                    max_tokens=2000
                )
            except Exception as e:
                raise AnalysisError(f"LLM call failed for impact analysis: {e}")
            
            # Step 3: Parse JSON response
            try:
                analysis = json.loads(llm_response)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON from LLM: {llm_response}")
                raise AnalysisError(f"Invalid JSON from LLM: {e}")
            
            # Step 4: Build ImpactAnalysisResult
            breaking_changes = []
            for change_dict in analysis.get("breaking_changes", []):
                try:
                    breaking_change = BreakingChange(
                        caller_file=change_dict["caller_file"],
                        caller_function=change_dict["caller_function"],
                        issue=change_dict["issue"],
                        suggested_fix=change_dict.get("suggested_fix", ""),
                        severity=self._parse_severity(change_dict.get("severity", "medium"))
                    )
                    breaking_changes.append(breaking_change)
                except (KeyError, ValueError) as e:
                    logger.warning(f"Could not parse breaking change: {e}, skipping")
                    continue
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            result = ImpactAnalysisResult(
                function_name=changed_function.name,
                file_path=changed_function.file_path,
                callers=callers,
                importers=[],  # Not analyzed here (future enhancement)
                breaking_changes=breaking_changes,
                summary=analysis.get(
                    "summary",
                    f"Impact analysis completed. {len(breaking_changes)} breaking changes detected."
                ),
                analysis_duration_ms=duration_ms
            )
            
            logger.info(
                f"Impact analysis completed in {duration_ms}ms. "
                f"Found {len(breaking_changes)} breaking changes."
            )
            
            return result
            
        except AnalysisError:
            raise
        except Exception as e:
            raise AnalysisError(f"Impact analysis failed: {e}")
    
    def _build_impact_analysis_prompt(
        self,
        changed_function: FunctionNode,
        diff_hunk: DiffHunk,
        callers: List[CallSite],
    ) -> str:
        """Build prompt for LLM.
        
        Format (from Pornprasit2024 + Ren2025):
        - Clear structure (## headings)
        - Code blocks (diff + function body + callers)
        - Explicit instructions (what to analyze, output format)
        - JSON schema (strict output format)
        
        Args:
            changed_function: Modified function
            diff_hunk: Diff showing changes
            callers: List of call sites
            
        Returns:
            Formatted prompt string
        """
        if self.prompt_template:
            # Use custom template if provided
            return self.prompt_template.format(
                function_name=changed_function.name,
                file_path=changed_function.file_path.value,
                language=changed_function.language.value,
                start_line=changed_function.start_line,
                end_line=changed_function.end_line,
                diff_content=diff_hunk.content,
                function_body=changed_function.body,
                callers=self._format_callers(callers),
                num_callers=len(callers)
            )
        
        # Default template
        return f"""# Impact Analysis for Code Change

## Changed Function: `{changed_function.name}` ({changed_function.language.value})

**File:** {changed_function.file_path.value}  
**Lines:** {changed_function.start_line}-{changed_function.end_line}

---

### Diff (What Changed):
```diff
{diff_hunk.content}
```

---

### Full Function Body (After Change):
```{changed_function.language.value}
{changed_function.body}
```

---

## Call Sites (Who Uses This Function): {len(callers)} caller(s) found

{self._format_callers(callers)}

---

## Your Task:

Analyze whether this change can **break the calling code**. Consider:

### 1. **Signature Changes**
- Parameters added/removed/renamed/reordered?
- Return type changed?
- Default values changed?

### 2. **Semantic Changes**
- Core logic altered?
- Edge cases handled differently?
- New error conditions?

### 3. **Contract Changes**
- Preconditions (input validation) changed?
- Postconditions (guarantees) changed?
- Invariants violated?

### 4. **Side Effects**
- New exceptions thrown?
- New external dependencies?
- Performance characteristics changed?

---

### For Each Caller:

Determine:
1. **Affected?** (yes/no)
2. **Why?** (explanation of the issue)
3. **What can break?** (specific failure scenario)
4. **How to fix?** (code suggestion for caller)

---

## Output Format (JSON):

```json
{{
  "severity": "critical" | "high" | "medium" | "low",
  "breaking_changes": [
    {{
      "caller_file": "path/to/file.py",
      "caller_function": "function_name",
      "issue": "Concise description of what can break",
      "suggested_fix": "How to fix the caller (code suggestion)",
      "severity": "critical" | "high" | "medium" | "low"
    }}
  ],
  "summary": "Overall impact assessment (1-2 sentences)"
}}
```

**Rules:**
- Output ONLY valid JSON (no markdown, no extra text)
- If no breaking changes: `{{"severity": "low", "breaking_changes": [], "summary": "No breaking changes detected."}}`
- Be specific in `issue` and `suggested_fix`
- Focus on actual breaking changes, not style or minor improvements
"""
    
    def _format_callers(self, callers: List[CallSite]) -> str:
        """Format callers for prompt.
        
        Args:
            callers: List of call sites
            
        Returns:
            Formatted string with caller information
        """
        if not callers:
            return "_No callers found. Function may be unused or private API._"
        
        formatted = []
        for i, caller in enumerate(callers, 1):
            formatted.append(f"""
### Caller {i}: `{caller.caller_name}()` in `{caller.file_path.value}`

**Line {caller.line_number}:**
```
{caller.context}
```
""")
        return "\n".join(formatted)
    
    def _parse_severity(self, severity_str: str) -> Severity:
        """Parse severity string from LLM response.
        
        Maps LLM severity strings to Severity enum values.
        
        Args:
            severity_str: Severity string from LLM ("critical", "high", "medium", "low")
            
        Returns:
            Severity object
        """
        severity_map = {
            "critical": Severity(level=Severity.ERROR),
            "high": Severity(level=Severity.ERROR),
            "medium": Severity(level=Severity.WARNING),
            "low": Severity(level=Severity.INFO)
        }
        
        severity_lower = severity_str.lower()
        if severity_lower not in severity_map:
            logger.warning(
                f"Unknown severity '{severity_str}', defaulting to WARNING"
            )
            return Severity(level=Severity.WARNING)
        
        return severity_map[severity_lower]
