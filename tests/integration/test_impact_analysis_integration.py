"""Integration tests for Impact Analysis system."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from acr_system.domain.services.services import ReviewOrchestrator
from acr_system.domain.entities.entities import DiffHunk, FunctionNode, PullRequest
from acr_system.domain.value_objects.value_objects import (
    CallSite,
    CommentSource,
    FilePath,
    Language,
    RAGConfig,
    Severity,
)
from acr_system.infrastructure.analysis.llm_impact_analyzer import LLMImpactAnalyzer
from acr_system.infrastructure.analysis.tree_sitter_call_graph_analyzer import (
    TreeSitterCallGraphAnalyzer,
)


@pytest.fixture
def mock_llm_provider():
    """Mock LLM provider."""
    mock = AsyncMock()
    mock.generate_review_comments = AsyncMock(return_value=[])
    mock.parse_ci_output = AsyncMock(return_value=[])
    mock.generate_completion = AsyncMock()
    return mock


@pytest.fixture
def mock_vcs_repository():
    """Mock VCS repository."""
    mock = AsyncMock()
    mock.get_file_content = AsyncMock()
    return mock


@pytest.fixture
def mock_ast_parser():
    """Mock AST parser."""
    mock = MagicMock()
    mock.extract_changed_functions = MagicMock(return_value=[])
    return mock


@pytest.fixture
def mock_context_builder():
    """Mock context builder."""
    mock = AsyncMock()
    mock.build_context = AsyncMock(return_value=[])
    return mock


@pytest.fixture
def call_graph_analyzer(mock_vcs_repository, mock_ast_parser):
    """Call graph analyzer instance."""
    with patch('acr_system.infrastructure.analysis.tree_sitter_call_graph_analyzer.TREE_SITTER_AVAILABLE', True):
        return TreeSitterCallGraphAnalyzer(
            vcs=mock_vcs_repository,
            ast_parser=mock_ast_parser,
            repo_base_path="/test/repo",
        )


@pytest.fixture
def impact_analyzer(mock_llm_provider):
    """Impact analyzer instance."""
    return LLMImpactAnalyzer(llm=mock_llm_provider)


@pytest.fixture
def review_orchestrator(
    mock_llm_provider,
    mock_context_builder,
    mock_vcs_repository,
    mock_ast_parser,
    call_graph_analyzer,
    impact_analyzer,
):
    """Review orchestrator with impact analysis enabled."""
    return ReviewOrchestrator(
        llm_provider=mock_llm_provider,
        context_builder=mock_context_builder,
        vcs_repository=mock_vcs_repository,
        ast_parser=mock_ast_parser,
        static_analyzer=None,
        call_graph_analyzer=call_graph_analyzer,
        impact_analyzer=impact_analyzer,
    )


@pytest.fixture
def sample_pr_with_breaking_change():
    """Sample PR with a breaking change."""
    pr = PullRequest(
        pr_number=123,
        repository="test/repo",
        title="Refactor discount calculation",
        description="Changed parameter types",
        author="developer",
        source_branch="feature/refactor",
        target_branch="main",
    )
    
    # Add diff hunk
    diff_hunk = DiffHunk(
        file_path=FilePath("src/pricing.py"),
        old_start_line=10,
        old_line_count=4,
        new_start_line=10,
        new_line_count=5,
        content="""@@ -10,4 +10,5 @@
 def calculate_discount(price, customer_type):
-    if customer_type == "premium":
+    # Breaking: now requires CustomerTier enum
+    if customer_type == CustomerTier.PREMIUM:
         return price * 0.8
     return price * 0.9
""",
    )
    pr.add_diff_hunk(diff_hunk)
    
    return pr


class TestImpactAnalysisIntegration:
    """Integration tests for Impact Analysis."""
    
    @pytest.mark.asyncio
    async def test_full_review_with_breaking_change_detection(
        self,
        review_orchestrator,
        sample_pr_with_breaking_change,
        mock_ast_parser,
        mock_vcs_repository,
        mock_llm_provider,
    ):
        """Test complete review flow with breaking change detection."""
        # Setup: Mock changed function extraction
        changed_function = FunctionNode(
            name="calculate_discount",
            file_path=FilePath("src/pricing.py"),
            start_line=10,
            end_line=20,
            body="def calculate_discount(price, customer_type):\n    ...",
            language=Language(name="python"),
            signature="calculate_discount(price, customer_type)",
        )
        mock_ast_parser.extract_changed_functions.return_value = [changed_function]
        
        # Setup: Mock file content for VCS
        mock_vcs_repository.get_file_content.return_value = "def calculate_discount(...):\n    pass"
        
        # Setup: Mock grep to find callers
        with patch("subprocess.run") as mock_run:
            grep_output = b"src/checkout.py:45:    discount = calculate_discount(total, 'premium')"
            mock_run.return_value = MagicMock(stdout=grep_output, returncode=0)
            
            # Setup: Mock tree-sitter validation
            with patch.object(review_orchestrator.call_graph_analyzer, "_verify_is_call_site", return_value=True):
                with patch.object(review_orchestrator.call_graph_analyzer, "_extract_caller_name", return_value="process_order"):
                    with patch("builtins.open", create=True) as mock_open:
                        mock_open.return_value.__enter__.return_value.readlines.return_value = [""] * 50
                        
                        # Setup: Mock LLM response for impact analysis
                        llm_response = {
                            "breaking_changes": [
                                {
                                    "description": "Parameter type changed from string to CustomerTier enum",
                                    "severity": "high",
                                    "affected_code": "calculate_discount(total, 'premium')",
                                    "fix_suggestion": "Use CustomerTier.PREMIUM instead of string 'premium'",
                                }
                            ],
                            "summary": "Breaking change: 1 caller affected by type change",
                        }
                        mock_llm_provider.generate_completion.return_value = json.dumps(llm_response)
                        
                        # Execute review
                        comments = await review_orchestrator.review_pull_request(
                            pr=sample_pr_with_breaking_change,
                            rules_text="Check for breaking changes",
                            rag_config=RAGConfig(enabled=False),
                        )
        
        # Verify: Should have impact analysis comment
        impact_comments = [c for c in comments if c.source.source == CommentSource.IMPACT_ANALYSIS]
        assert len(impact_comments) > 0
        
        # Verify: Comment contains expected information
        impact_comment = impact_comments[0]
        assert "calculate_discount" in impact_comment.message
        assert "Breaking Change" in impact_comment.message or "breaking" in impact_comment.message.lower()
        assert impact_comment.severity == Severity(level=Severity.ERROR)
        assert "CustomerTier.PREMIUM" in impact_comment.suggestion
        assert impact_comment.file_path.value == "src/pricing.py"
    
    @pytest.mark.asyncio
    async def test_review_skips_impact_analysis_when_disabled(
        self,
        mock_llm_provider,
        mock_context_builder,
        mock_vcs_repository,
        mock_ast_parser,
        sample_pr_with_breaking_change,
    ):
        """Test that impact analysis is skipped when analyzers not injected."""
        # Create orchestrator WITHOUT impact analyzers
        orchestrator = ReviewOrchestrator(
            llm_provider=mock_llm_provider,
            context_builder=mock_context_builder,
            vcs_repository=mock_vcs_repository,
            ast_parser=mock_ast_parser,
            static_analyzer=None,
            call_graph_analyzer=None,  # Not injected
            impact_analyzer=None,  # Not injected
        )
        
        comments = await orchestrator.review_pull_request(
            pr=sample_pr_with_breaking_change,
            rules_text="Check for issues",
            rag_config=RAGConfig(enabled=False),
        )
        
        # Verify: No impact analysis comments
        impact_comments = [c for c in comments if c.source.source == CommentSource.IMPACT_ANALYSIS]
        assert len(impact_comments) == 0
    
    @pytest.mark.asyncio
    async def test_review_with_no_callers_found(
        self,
        review_orchestrator,
        sample_pr_with_breaking_change,
        mock_ast_parser,
        mock_vcs_repository,
    ):
        """Test review when changed function has no callers."""
        # Setup: Mock changed function
        changed_function = FunctionNode(
            name="calculate_discount",
            file_path=FilePath("src/pricing.py"),
            start_line=10,
            end_line=20,
            body="def calculate_discount(...):\n    pass",
            language=Language(name="python"),
        )
        mock_ast_parser.extract_changed_functions.return_value = [changed_function]
        mock_vcs_repository.get_file_content.return_value = "def calculate_discount(...):\n    pass"
        
        # Setup: Mock grep to find no callers
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=b"", returncode=1)
            
            comments = await review_orchestrator.review_pull_request(
                pr=sample_pr_with_breaking_change,
                rules_text="Check for issues",
                rag_config=RAGConfig(enabled=False),
            )
        
        # Verify: No impact analysis comments since no callers
        impact_comments = [c for c in comments if c.source.source == CommentSource.IMPACT_ANALYSIS]
        assert len(impact_comments) == 0
    
    @pytest.mark.asyncio
    async def test_review_with_multiple_changed_functions(
        self,
        review_orchestrator,
        sample_pr_with_breaking_change,
        mock_ast_parser,
        mock_vcs_repository,
        mock_llm_provider,
    ):
        """Test review with multiple changed functions."""
        # Setup: Multiple changed functions
        functions = [
            FunctionNode(
                name="calculate_discount",
                file_path=FilePath("src/pricing.py"),
                start_line=10,
                end_line=20,
                body="def calculate_discount(...):\n    pass",
                language=Language(name="python"),
            ),
            FunctionNode(
                name="apply_tax",
                file_path=FilePath("src/pricing.py"),
                start_line=25,
                end_line=35,
                body="def apply_tax(...):\n    pass",
                language=Language(name="python"),
            ),
        ]
        mock_ast_parser.extract_changed_functions.return_value = functions
        mock_vcs_repository.get_file_content.return_value = "functions here"
        
        # Setup: Mock callers for both functions
        with patch("subprocess.run") as mock_run:
            # First call for calculate_discount, second for apply_tax
            mock_run.side_effect = [
                MagicMock(stdout=b"src/checkout.py:45:discount = calculate_discount()", returncode=0),
                MagicMock(stdout=b"src/invoice.py:30:tax = apply_tax()", returncode=0),
            ]
            
            with patch.object(review_orchestrator.call_graph_analyzer, "_verify_is_call_site", return_value=True):
                with patch.object(review_orchestrator.call_graph_analyzer, "_extract_caller_name") as mock_caller:
                    mock_caller.side_effect = ["process_order", "generate_invoice"]
                    
                    with patch("builtins.open", create=True) as mock_open:
                        mock_open.return_value.__enter__.return_value.readlines.return_value = [""] * 50
                        
                        # Mock LLM responses for both
                        llm_responses = [
                            json.dumps({
                                "breaking_changes": [{
                                    "description": "Breaking change in calculate_discount",
                                    "severity": "high",
                                    "affected_code": "calculate_discount()",
                                    "fix_suggestion": "Update caller",
                                }],
                                "summary": "Breaking change detected",
                            }),
                            json.dumps({
                                "breaking_changes": [{
                                    "description": "Breaking change in apply_tax",
                                    "severity": "medium",
                                    "affected_code": "apply_tax()",
                                    "fix_suggestion": "Update caller",
                                }],
                                "summary": "Breaking change detected",
                            }),
                        ]
                        mock_llm_provider.generate_completion.side_effect = llm_responses
                        
                        comments = await review_orchestrator.review_pull_request(
                            pr=sample_pr_with_breaking_change,
                            rules_text="Check for issues",
                            rag_config=RAGConfig(enabled=False),
                        )
        
        # Verify: Should have 2 impact analysis comments
        impact_comments = [c for c in comments if c.source.source == CommentSource.IMPACT_ANALYSIS]
        assert len(impact_comments) == 2
        assert any("calculate_discount" in c.message for c in impact_comments)
        assert any("apply_tax" in c.message for c in impact_comments)
    
    @pytest.mark.asyncio
    async def test_impact_analysis_error_handling(
        self,
        review_orchestrator,
        sample_pr_with_breaking_change,
        mock_ast_parser,
        mock_vcs_repository,
        mock_llm_provider,
    ):
        """Test that errors in impact analysis don't break the review."""
        # Setup: Mock changed function
        changed_function = FunctionNode(
            name="calculate_discount",
            file_path=FilePath("src/pricing.py"),
            start_line=10,
            end_line=20,
            body="def calculate_discount(...):\n    pass",
            language=Language(name="python"),
        )
        mock_ast_parser.extract_changed_functions.return_value = [changed_function]
        mock_vcs_repository.get_file_content.return_value = "def calculate_discount(...):\n    pass"
        
        # Setup: Mock grep to return caller
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=b"src/checkout.py:45:discount = calculate_discount()", returncode=0)
            
            with patch.object(review_orchestrator.call_graph_analyzer, "_verify_is_call_site", return_value=True):
                with patch.object(review_orchestrator.call_graph_analyzer, "_extract_caller_name", return_value="process_order"):
                    with patch("builtins.open", create=True) as mock_open:
                        mock_open.return_value.__enter__.return_value.readlines.return_value = [""] * 50
                        
                        # Setup: LLM raises an error
                        mock_llm_provider.generate_completion.side_effect = Exception("LLM timeout")
                        
                        # Execute review - should not raise exception
                        comments = await review_orchestrator.review_pull_request(
                            pr=sample_pr_with_breaking_change,
                            rules_text="Check for issues",
                            rag_config=RAGConfig(enabled=False),
                        )
        
        # Verify: Review should complete despite error
        # No impact comments due to error, but review didn't crash
        impact_comments = [c for c in comments if c.source.source == CommentSource.IMPACT_ANALYSIS]
        assert len(impact_comments) == 0  # Error was caught and handled
    
    @pytest.mark.asyncio
    async def test_llm_prompt_generation_quality(
        self,
        impact_analyzer,
        mock_llm_provider,
    ):
        """Test that LLM prompt contains all necessary context."""
        function_node = FunctionNode(
            name="process_payment",
            file_path=FilePath("src/payments.py"),
            start_line=100,
            end_line=120,
            body="""def process_payment(amount, currency, method):
    if method == "card":
        return charge_card(amount, currency)
    elif method == "paypal":
        return charge_paypal(amount, currency)
    else:
        raise ValueError("Invalid payment method")
""",
            language=Language(name="python"),
            signature="process_payment(amount, currency, method)",
        )
        
        diff_hunk = DiffHunk(
            file_path=FilePath("src/payments.py"),
            old_start_line=100,
            old_line_count=7,
            new_start_line=100,
            new_line_count=8,
            content="""@@ -100,7 +100,8 @@
 def process_payment(amount, currency, method):
-    if method == "card":
+    # Breaking: method is now PaymentMethod enum
+    if method == PaymentMethod.CARD:
         return charge_card(amount, currency)
""",
        )
        
        callers = [
            CallSite(
                file_path=FilePath("src/checkout.py"),
                line_number=200,
                caller_name="complete_order",
                callee_name="process_payment",
                context='result = process_payment(100.0, "USD", "card")',
            ),
            CallSite(
                file_path=FilePath("src/api.py"),
                line_number=50,
                caller_name="payment_endpoint",
                callee_name="process_payment",
                context='outcome = process_payment(req.amount, req.currency, req.method)',
            ),
        ]
        
        mock_llm_provider.generate_completion.return_value = json.dumps({
            "breaking_changes": [],
            "summary": "No breaking changes",
        })
        
        await impact_analyzer.analyze_impact(
            changed_function=function_node,
            diff=diff_hunk,
            callers=callers,
            language=Language(name="python"),
        )
        
        # Verify prompt content
        call_args = mock_llm_provider.generate_completion.call_args
        prompt = call_args.args[0]
        
        # Check all critical components are in prompt
        assert "process_payment" in prompt
        assert "src/payments.py" in prompt
        assert "PaymentMethod.CARD" in prompt or "PaymentMethod" in prompt
        assert "complete_order" in prompt
        assert "payment_endpoint" in prompt
        assert "src/checkout.py:200" in prompt
        assert "src/api.py:50" in prompt
        assert "breaking_changes" in prompt
        assert "severity" in prompt.lower()
        assert "fix_suggestion" in prompt.lower()
    
    @pytest.mark.asyncio
    async def test_warning_comment_formatting(
        self,
        review_orchestrator,
        sample_pr_with_breaking_change,
        mock_ast_parser,
        mock_vcs_repository,
        mock_llm_provider,
    ):
        """Test that warning comments are properly formatted."""
        # Setup mocks
        changed_function = FunctionNode(
            name="calculate_discount",
            file_path=FilePath("src/pricing.py"),
            start_line=10,
            end_line=20,
            body="def calculate_discount(...):\n    pass",
            language=Language(name="python"),
        )
        mock_ast_parser.extract_changed_functions.return_value = [changed_function]
        mock_vcs_repository.get_file_content.return_value = "function body"
        
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout=b"src/checkout.py:45:discount = calculate_discount()\nsrc/api.py:30:result = calculate_discount()",
                returncode=0,
            )
            
            with patch.object(review_orchestrator.call_graph_analyzer, "_verify_is_call_site", return_value=True):
                with patch.object(review_orchestrator.call_graph_analyzer, "_extract_caller_name") as mock_caller:
                    mock_caller.side_effect = ["process_order", "api_handler"]
                    
                    with patch("builtins.open", create=True) as mock_open:
                        mock_open.return_value.__enter__.return_value.readlines.return_value = [""] * 50
                        
                        llm_response = {
                            "breaking_changes": [{
                                "description": "Parameter type changed from string to enum",
                                "severity": "high",
                                "affected_code": "calculate_discount(100, 'premium')",
                                "fix_suggestion": "Use CustomerTier.PREMIUM instead",
                            }],
                            "summary": "Breaking change: type incompatibility",
                        }
                        mock_llm_provider.generate_completion.return_value = json.dumps(llm_response)
                        
                        comments = await review_orchestrator.review_pull_request(
                            pr=sample_pr_with_breaking_change,
                            rules_text="Check for issues",
                            rag_config=RAGConfig(enabled=False),
                        )
        
        # Verify comment formatting
        impact_comment = [c for c in comments if c.source.source == CommentSource.IMPACT_ANALYSIS][0]
        
        # Should have warning emoji or indicator
        assert "⚠" in impact_comment.message or "WARNING" in impact_comment.message.upper()
        
        # Should mention function name
        assert "calculate_discount" in impact_comment.message
        
        # Should mention number of affected callers
        assert "2" in impact_comment.message or "Affected callers: 2" in impact_comment.message
        
        # Should have the breaking change description
        assert "type" in impact_comment.message.lower() and "enum" in impact_comment.message.lower()
        
        # Should have fix suggestion
        assert "CustomerTier.PREMIUM" in impact_comment.suggestion
        
        # Should be at the function start line
        assert impact_comment.line_number == 10
        
        # Should have correct severity
        assert impact_comment.severity == Severity(level=Severity.ERROR)
        
        # Should have rule name
        assert impact_comment.rule_name == "impact_analysis"
