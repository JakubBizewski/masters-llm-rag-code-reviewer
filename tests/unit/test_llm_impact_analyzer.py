"""Tests for LLMImpactAnalyzer."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from acr_system.infrastructure.analysis.llm_impact_analyzer import LLMImpactAnalyzer
from acr_system.domain.entities.entities import DiffHunk, FunctionNode
from acr_system.domain.value_objects.value_objects import (
    CallSite,
    FilePath,
    ImpactAnalysisResult,
    Language,
    Severity,
)
from acr_system.shared.exceptions.infrastructure_exceptions import AnalysisError


@pytest.fixture
def llm_impact_analyzer():
    """Fixture for LLMImpactAnalyzer."""
    mock_llm = AsyncMock()
    return LLMImpactAnalyzer(llm=mock_llm)


@pytest.fixture
def sample_function_node():
    """Sample function node for testing."""
    return FunctionNode(
        name="calculate_discount",
        file_path=FilePath("src/pricing.py"),
        start_line=10,
        end_line=20,
        body="""def calculate_discount(price, customer_type):
    if customer_type == "premium":
        return price * 0.8
    return price * 0.9
""",
        language=Language(name="python"),
        signature="calculate_discount(price, customer_type)",
    )


@pytest.fixture
def sample_diff_hunk():
    """Sample diff hunk showing a breaking change."""
    return DiffHunk(
        file_path=FilePath("src/pricing.py"),
        old_start_line=10,
        old_line_count=4,
        new_start_line=10,
        new_line_count=5,
        content="""@@ -10,4 +10,5 @@
 def calculate_discount(price, customer_type):
-    if customer_type == "premium":
+    # Changed: now requires customer_tier enum
+    if customer_type == CustomerTier.PREMIUM:
         return price * 0.8
     return price * 0.9
""",
    )


@pytest.fixture
def sample_callers():
    """Sample callers for testing."""
    return [
        CallSite(
            file_path=FilePath("src/checkout.py"),
            line_number=45,
            caller_name="process_order",
            callee_name="calculate_discount",
            context='    discount = calculate_discount(order.total, "premium")',
        ),
        CallSite(
            file_path=FilePath("src/api.py"),
            line_number=120,
            caller_name="apply_discount_endpoint",
            callee_name="calculate_discount",
            context='    result = calculate_discount(price, customer.type)',
        ),
    ]


@pytest.fixture
def llm_response_breaking_change():
    """Sample LLM response indicating breaking changes."""
    return {
        "breaking_changes": [
            {
                "description": "Function signature changed from accepting string to CustomerTier enum. All callers passing strings will break.",
                "severity": "high",
                "affected_code": "calculate_discount(order.total, \"premium\")",
                "fix_suggestion": "Update caller to use CustomerTier.PREMIUM instead of string 'premium'",
            }
        ],
        "summary": "Breaking change detected: parameter type changed from string to enum. 2 callers affected.",
    }


@pytest.fixture
def llm_response_no_breaking_change():
    """Sample LLM response with no breaking changes."""
    return {
        "breaking_changes": [],
        "summary": "No breaking changes detected. The internal implementation changed but the interface remains compatible.",
    }


class TestLLMImpactAnalyzer:
    """Tests for LLMImpactAnalyzer."""
    
    @pytest.mark.asyncio
    async def test_analyze_impact_breaking_change_detected(
        self,
        llm_impact_analyzer,
        sample_function_node,
        sample_diff_hunk,
        sample_callers,
        llm_response_breaking_change,
    ):
        """Test impact analysis when breaking change is detected."""
        # Mock LLM response
        llm_impact_analyzer.llm_provider.generate_completion = AsyncMock(
            return_value=json.dumps(llm_response_breaking_change)
        )
        
        result = await llm_impact_analyzer.analyze_impact(
            changed_function=sample_function_node,
            diff=sample_diff_hunk,
            callers=sample_callers,
            language=Language(name="python"),
        )
        
        assert isinstance(result, ImpactAnalysisResult)
        assert len(result.breaking_changes) == 1
        assert result.breaking_changes[0].severity == Severity(level=Severity.ERROR)
        assert "CustomerTier enum" in result.breaking_changes[0].description
        assert "CustomerTier.PREMIUM" in result.breaking_changes[0].fix_suggestion
        assert "2 callers affected" in result.summary
        assert result.duration_ms > 0
    
    @pytest.mark.asyncio
    async def test_analyze_impact_no_breaking_change(
        self,
        llm_impact_analyzer,
        sample_function_node,
        sample_diff_hunk,
        sample_callers,
        llm_response_no_breaking_change,
    ):
        """Test impact analysis when no breaking change is detected."""
        # Mock LLM response
        llm_impact_analyzer.llm_provider.generate_completion = AsyncMock(
            return_value=json.dumps(llm_response_no_breaking_change)
        )
        
        result = await llm_impact_analyzer.analyze_impact(
            changed_function=sample_function_node,
            diff=sample_diff_hunk,
            callers=sample_callers,
            language=Language(name="python"),
        )
        
        assert len(result.breaking_changes) == 0
        assert "No breaking changes" in result.summary
    
    @pytest.mark.asyncio
    async def test_analyze_impact_no_callers(
        self,
        llm_impact_analyzer,
        sample_function_node,
        sample_diff_hunk,
    ):
        """Test impact analysis when function has no callers."""
        result = await llm_impact_analyzer.analyze_impact(
            changed_function=sample_function_node,
            diff=sample_diff_hunk,
            callers=[],
            language=Language(name="python"),
        )
        
        assert len(result.breaking_changes) == 0
        assert "no callers found" in result.summary.lower()
        # LLM should not be called when there are no callers
        llm_impact_analyzer.llm_provider.generate_completion.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_analyze_impact_invalid_json_response(
        self,
        llm_impact_analyzer,
        sample_function_node,
        sample_diff_hunk,
        sample_callers,
    ):
        """Test handling of invalid JSON from LLM."""
        # Mock LLM response with invalid JSON
        llm_impact_analyzer.llm_provider.generate_completion = AsyncMock(
            return_value="This is not valid JSON{invalid}"
        )
        
        with pytest.raises(AnalysisError) as exc_info:
            await llm_impact_analyzer.analyze_impact(
                changed_function=sample_function_node,
                diff=sample_diff_hunk,
                callers=sample_callers,
                language=Language(name="python"),
            )
        
        assert "Failed to parse LLM response" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_analyze_impact_llm_error(
        self,
        llm_impact_analyzer,
        sample_function_node,
        sample_diff_hunk,
        sample_callers,
    ):
        """Test handling of LLM provider errors."""
        # Mock LLM provider to raise an error
        llm_impact_analyzer.llm_provider.generate_completion = AsyncMock(
            side_effect=Exception("LLM API timeout")
        )
        
        with pytest.raises(AnalysisError) as exc_info:
            await llm_impact_analyzer.analyze_impact(
                changed_function=sample_function_node,
                diff=sample_diff_hunk,
                callers=sample_callers,
                language=Language(name="python"),
            )
        
        assert "Impact analysis failed" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_build_impact_analysis_prompt(
        self,
        llm_impact_analyzer,
        sample_function_node,
        sample_diff_hunk,
        sample_callers,
    ):
        """Test prompt building for impact analysis."""
        prompt = llm_impact_analyzer._build_impact_analysis_prompt(
            changed_function=sample_function_node,
            diff=sample_diff_hunk,
            callers=sample_callers,
            language=Language(name="python"),
        )
        
        # Check that prompt contains all necessary components
        assert "calculate_discount" in prompt
        assert "src/pricing.py" in prompt
        assert "CustomerTier.PREMIUM" in prompt  # From diff
        assert "process_order" in prompt  # Caller name
        assert "apply_discount_endpoint" in prompt  # Another caller
        assert "src/checkout.py:45" in prompt  # Caller location
        assert "breaking_changes" in prompt  # JSON schema
        assert "severity" in prompt
        assert "fix_suggestion" in prompt
    
    @pytest.mark.asyncio
    async def test_format_callers(self, llm_impact_analyzer, sample_callers):
        """Test formatting callers for prompt."""
        formatted = llm_impact_analyzer._format_callers(sample_callers)
        
        assert "src/checkout.py:45" in formatted
        assert "process_order" in formatted
        assert "src/api.py:120" in formatted
        assert "apply_discount_endpoint" in formatted
        assert "calculate_discount" in formatted
    
    def test_parse_severity_critical(self, llm_impact_analyzer):
        """Test parsing 'critical' severity."""
        severity = llm_impact_analyzer._parse_severity("critical")
        assert severity == Severity(level=Severity.ERROR)
    
    def test_parse_severity_high(self, llm_impact_analyzer):
        """Test parsing 'high' severity."""
        severity = llm_impact_analyzer._parse_severity("high")
        assert severity == Severity(level=Severity.ERROR)
    
    def test_parse_severity_medium(self, llm_impact_analyzer):
        """Test parsing 'medium' severity."""
        severity = llm_impact_analyzer._parse_severity("medium")
        assert severity == Severity(level=Severity.WARNING)
    
    def test_parse_severity_low(self, llm_impact_analyzer):
        """Test parsing 'low' severity."""
        severity = llm_impact_analyzer._parse_severity("low")
        assert severity == Severity(level=Severity.INFO)
    
    def test_parse_severity_unknown(self, llm_impact_analyzer):
        """Test parsing unknown severity defaults to INFO."""
        severity = llm_impact_analyzer._parse_severity("unknown")
        assert severity == Severity(level=Severity.INFO)
    
    @pytest.mark.asyncio
    async def test_analyze_impact_multiple_breaking_changes(
        self,
        llm_impact_analyzer,
        sample_function_node,
        sample_diff_hunk,
        sample_callers,
    ):
        """Test impact analysis with multiple breaking changes."""
        llm_response = {
            "breaking_changes": [
                {
                    "description": "Parameter type changed",
                    "severity": "critical",
                    "affected_code": "calculate_discount(price, 'premium')",
                    "fix_suggestion": "Use CustomerTier.PREMIUM",
                },
                {
                    "description": "Return type changed",
                    "severity": "medium",
                    "affected_code": "discount = calculate_discount(...)",
                    "fix_suggestion": "Handle new DiscountResult type",
                },
            ],
            "summary": "Multiple breaking changes detected",
        }
        
        llm_impact_analyzer.llm_provider.generate_completion = AsyncMock(
            return_value=json.dumps(llm_response)
        )
        
        result = await llm_impact_analyzer.analyze_impact(
            changed_function=sample_function_node,
            diff=sample_diff_hunk,
            callers=sample_callers,
            language=Language(name="python"),
        )
        
        assert len(result.breaking_changes) == 2
        assert result.breaking_changes[0].severity == Severity(level=Severity.ERROR)
        assert result.breaking_changes[1].severity == Severity(level=Severity.WARNING)
    
    @pytest.mark.asyncio
    async def test_analyze_impact_with_low_temperature(
        self,
        llm_impact_analyzer,
        sample_function_node,
        sample_diff_hunk,
        sample_callers,
        llm_response_breaking_change,
    ):
        """Test that LLM is called with low temperature for consistency."""
        llm_impact_analyzer.llm_provider.generate_completion = AsyncMock(
            return_value=json.dumps(llm_response_breaking_change)
        )
        
        await llm_impact_analyzer.analyze_impact(
            changed_function=sample_function_node,
            diff=sample_diff_hunk,
            callers=sample_callers,
            language=Language(name="python"),
        )
        
        # Verify LLM was called with temperature=0.2
        call_args = llm_impact_analyzer.llm_provider.generate_completion.call_args
        assert call_args.kwargs.get("temperature") == 0.2
    
    @pytest.mark.asyncio
    async def test_analyze_impact_javascript(
        self,
        llm_impact_analyzer,
        llm_response_breaking_change,
    ):
        """Test impact analysis for JavaScript code."""
        function_node = FunctionNode(
            name="calculateDiscount",
            file_path=FilePath("src/pricing.js"),
            start_line=10,
            end_line=15,
            body="""function calculateDiscount(price, customerType) {
    return price * 0.9;
}""",
            language=Language(name="javascript"),
            signature="calculateDiscount(price, customerType)",
        )
        
        diff_hunk = DiffHunk(
            file_path=FilePath("src/pricing.js"),
            old_start_line=10,
            old_line_count=3,
            new_start_line=10,
            new_line_count=3,
            content="@@ -10,3 +10,3 @@\n-    return price * 0.9;\n+    return { discount: price * 0.9 };",
        )
        
        callers = [
            CallSite(
                file_path=FilePath("src/checkout.js"),
                line_number=50,
                caller_name="processOrder",
                callee_name="calculateDiscount",
                context="const discount = calculateDiscount(price, type);",
            )
        ]
        
        llm_impact_analyzer.llm_provider.generate_completion = AsyncMock(
            return_value=json.dumps(llm_response_breaking_change)
        )
        
        result = await llm_impact_analyzer.analyze_impact(
            changed_function=function_node,
            diff=diff_hunk,
            callers=callers,
            language=Language(name="javascript"),
        )
        
        assert len(result.breaking_changes) == 1
        # Verify prompt was built for JavaScript
        call_args = llm_impact_analyzer.llm_provider.generate_completion.call_args
        prompt = call_args.args[0]
        assert "javascript" in prompt.lower() or "calculateDiscount" in prompt
