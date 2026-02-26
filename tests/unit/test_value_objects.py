"""Tests for domain value objects."""
import pytest

from acr_system.domain.value_objects.value_objects import (
    BreakingChange,
    CallSite,
    FilePath,
    ImpactAnalysisResult,
    ImportSite,
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


# ============================================================
# Tests for Impact Analysis Value Objects
# ============================================================


class TestCallSite:
    """Tests for CallSite value object."""
    
    def test_create_call_site(self):
        """Test creating a call site."""
        call = CallSite(
            file_path=FilePath("handlers/login.py"),
            line_number=156,
            caller_name="handle_login",
            callee_name="validate_token",
            context="result = validate_token(request.token, request.user_id)",
        )
        assert call.file_path.value == "handlers/login.py"
        assert call.line_number == 156
        assert call.caller_name == "handle_login"
        assert call.callee_name == "validate_token"
    
    def test_call_site_string_representation(self):
        """Test CallSite string representation."""
        call = CallSite(
            file_path=FilePath("handlers/login.py"),
            line_number=156,
            caller_name="handle_login",
            callee_name="validate_token",
            context="result = validate_token(request.token)",
        )
        expected = "handlers/login.py:156 - handle_login() calls validate_token()"
        assert str(call) == expected
    
    def test_invalid_line_number_raises_error(self):
        """Test that invalid line number raises ValueError."""
        with pytest.raises(ValueError, match="Line number must be positive"):
            CallSite(
                file_path=FilePath("test.py"),
                line_number=0,
                caller_name="foo",
                callee_name="bar",
                context="bar()",
            )
    
    def test_empty_caller_name_raises_error(self):
        """Test that empty caller_name raises ValueError."""
        with pytest.raises(ValueError, match="caller_name cannot be empty"):
            CallSite(
                file_path=FilePath("test.py"),
                line_number=1,
                caller_name="",
                callee_name="bar",
                context="bar()",
            )
    
    def test_call_site_is_immutable(self):
        """Test that CallSite is immutable (frozen)."""
        call = CallSite(
            file_path=FilePath("test.py"),
            line_number=1,
            caller_name="foo",
            callee_name="bar",
            context="bar()",
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            call.line_number = 2  # type: ignore


class TestImportSite:
    """Tests for ImportSite value object."""
    
    def test_create_import_site(self):
        """Test creating an import site."""
        imp = ImportSite(
            file_path=FilePath("handlers/login.py"),
            line_number=5,
            imported_module="auth",
            imported_names=("validate_token", "refresh_token"),
            context="from auth import validate_token, refresh_token",
        )
        assert imp.file_path.value == "handlers/login.py"
        assert imp.line_number == 5
        assert imp.imported_module == "auth"
        assert len(imp.imported_names) == 2
    
    def test_import_site_string_representation(self):
        """Test ImportSite string representation."""
        imp = ImportSite(
            file_path=FilePath("handlers/login.py"),
            line_number=5,
            imported_module="auth",
            imported_names=("validate_token", "refresh_token"),
            context="from auth import validate_token, refresh_token",
        )
        expected = "handlers/login.py:5 - imports validate_token, refresh_token from auth"
        assert str(imp) == expected
    
    def test_import_site_truncates_many_names(self):
        """Test that ImportSite truncates when many names imported."""
        imp = ImportSite(
            file_path=FilePath("test.py"),
            line_number=1,
            imported_module="utils",
            imported_names=("func1", "func2", "func3", "func4", "func5"),
            context="from utils import *",
        )
        str_repr = str(imp)
        assert "func1, func2, func3, ..." in str_repr
    
    def test_empty_imported_names_raises_error(self):
        """Test that empty imported_names raises ValueError."""
        with pytest.raises(ValueError, match="imported_names cannot be empty"):
            ImportSite(
                file_path=FilePath("test.py"),
                line_number=1,
                imported_module="auth",
                imported_names=(),
                context="import auth",
            )
    
    def test_import_site_is_immutable(self):
        """Test that ImportSite is immutable (frozen)."""
        imp = ImportSite(
            file_path=FilePath("test.py"),
            line_number=1,
            imported_module="auth",
            imported_names=("foo",),
            context="import auth",
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            imp.line_number = 2  # type: ignore


class TestBreakingChange:
    """Tests for BreakingChange value object."""
    
    def test_create_breaking_change(self):
        """Test creating a breaking change."""
        bc = BreakingChange(
            caller_file="handlers/login.py",
            caller_function="handle_login",
            issue="Signature changed - removed user_id parameter",
            suggested_fix="result = validate_token(request.token)",
            severity=Severity(level=Severity.ERROR),
        )
        assert bc.caller_file == "handlers/login.py"
        assert bc.caller_function == "handle_login"
        assert bc.severity.level == Severity.ERROR
    
    def test_empty_caller_file_raises_error(self):
        """Test that empty caller_file raises ValueError."""
        with pytest.raises(ValueError, match="caller_file cannot be empty"):
            BreakingChange(
                caller_file="",
                caller_function="foo",
                issue="Something broke",
                suggested_fix="Fix it",
                severity=Severity(level=Severity.ERROR),
            )


class TestImpactAnalysisResult:
    """Tests for ImpactAnalysisResult value object."""
    
    def test_create_impact_analysis_result(self):
        """Test creating an impact analysis result."""
        callers = [
            CallSite(
                file_path=FilePath("test.py"),
                line_number=10,
                caller_name="foo",
                callee_name="bar",
                context="bar()",
            )
        ]
        breaking_changes = [
            BreakingChange(
                caller_file="test.py",
                caller_function="foo",
                issue="Return type changed",
                suggested_fix="Update caller",
                severity=Severity(level=Severity.ERROR),
            )
        ]
        
        result = ImpactAnalysisResult(
            function_name="bar",
            file_path=FilePath("module.py"),
            callers=callers,
            importers=[],
            breaking_changes=breaking_changes,
            summary="Critical breaking changes detected",
            analysis_duration_ms=4200,
        )
        
        assert result.function_name == "bar"
        assert len(result.callers) == 1
        assert len(result.breaking_changes) == 1
        assert result.analysis_duration_ms == 4200
    
    def test_has_breaking_changes(self):
        """Test has_breaking_changes property."""
        result_with_changes = ImpactAnalysisResult(
            function_name="foo",
            file_path=FilePath("test.py"),
            callers=[],
            importers=[],
            breaking_changes=[
                BreakingChange(
                    caller_file="test.py",
                    caller_function="bar",
                    issue="Issue",
                    suggested_fix="Fix",
                    severity=Severity(level=Severity.ERROR),
                )
            ],
            summary="Has changes",
        )
        assert result_with_changes.has_breaking_changes is True
        
        result_no_changes = ImpactAnalysisResult(
            function_name="foo",
            file_path=FilePath("test.py"),
            callers=[],
            importers=[],
            breaking_changes=[],
            summary="No changes",
        )
        assert result_no_changes.has_breaking_changes is False
    
    def test_max_severity(self):
        """Test max_severity property."""
        result = ImpactAnalysisResult(
            function_name="foo",
            file_path=FilePath("test.py"),
            callers=[],
            importers=[],
            breaking_changes=[
                BreakingChange(
                    caller_file="test1.py",
                    caller_function="bar1",
                    issue="Issue 1",
                    suggested_fix="Fix 1",
                    severity=Severity(level=Severity.WARNING),
                ),
                BreakingChange(
                    caller_file="test2.py",
                    caller_function="bar2",
                    issue="Issue 2",
                    suggested_fix="Fix 2",
                    severity=Severity(level=Severity.ERROR),
                ),
            ],
            summary="Multiple severities",
        )
        assert result.max_severity is not None
        assert result.max_severity.level == Severity.ERROR
    
    def test_max_severity_none_when_no_changes(self):
        """Test max_severity is None when no breaking changes."""
        result = ImpactAnalysisResult(
            function_name="foo",
            file_path=FilePath("test.py"),
            callers=[],
            importers=[],
            breaking_changes=[],
            summary="No changes",
        )
        assert result.max_severity is None
    
    def test_total_affected_sites(self):
        """Test total_affected_sites property."""
        result = ImpactAnalysisResult(
            function_name="foo",
            file_path=FilePath("test.py"),
            callers=[
                CallSite(
                    file_path=FilePath("test1.py"),
                    line_number=1,
                    caller_name="a",
                    callee_name="foo",
                    context="foo()",
                ),
                CallSite(
                    file_path=FilePath("test2.py"),
                    line_number=1,
                    caller_name="b",
                    callee_name="foo",
                    context="foo()",
                ),
            ],
            importers=[
                ImportSite(
                    file_path=FilePath("test3.py"),
                    line_number=1,
                    imported_module="module",
                    imported_names=("foo",),
                    context="from module import foo",
                )
            ],
            breaking_changes=[],
            summary="3 affected sites",
        )
        assert result.total_affected_sites == 3
    
    def test_get_critical_changes(self):
        """Test get_critical_changes method."""
        result = ImpactAnalysisResult(
            function_name="foo",
            file_path=FilePath("test.py"),
            callers=[],
            importers=[],
            breaking_changes=[
                BreakingChange(
                    caller_file="test1.py",
                    caller_function="bar1",
                    issue="Warning issue",
                    suggested_fix="Fix",
                    severity=Severity(level=Severity.WARNING),
                ),
                BreakingChange(
                    caller_file="test2.py",
                    caller_function="bar2",
                    issue="Error issue",
                    suggested_fix="Fix",
                    severity=Severity(level=Severity.ERROR),
                ),
                BreakingChange(
                    caller_file="test3.py",
                    caller_function="bar3",
                    issue="Another error",
                    suggested_fix="Fix",
                    severity=Severity(level=Severity.ERROR),
                ),
            ],
            summary="Mixed severities",
        )
        critical = result.get_critical_changes()
        assert len(critical) == 2
        assert all(bc.severity.level == Severity.ERROR for bc in critical)
    
    def test_negative_duration_raises_error(self):
        """Test that negative analysis_duration_ms raises ValueError."""
        with pytest.raises(ValueError, match="analysis_duration_ms cannot be negative"):
            ImpactAnalysisResult(
                function_name="foo",
                file_path=FilePath("test.py"),
                callers=[],
                importers=[],
                breaking_changes=[],
                summary="Test",
                analysis_duration_ms=-1,
            )
