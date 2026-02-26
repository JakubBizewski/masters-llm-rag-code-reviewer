"""Tests for TreeSitterCallGraphAnalyzer."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from acr_system.infrastructure.analysis.tree_sitter_call_graph_analyzer import (
    TreeSitterCallGraphAnalyzer,
)
from acr_system.domain.value_objects.value_objects import CallSite, FilePath, ImportSite, Language
from acr_system.shared.exceptions.infrastructure_exceptions import AnalysisError


@pytest.fixture
def call_graph_analyzer():
    """Fixture for TreeSitterCallGraphAnalyzer."""
    mock_vcs = AsyncMock()
    mock_ast = MagicMock()
    # Mock tree-sitter availability check
    with patch('acr_system.infrastructure.analysis.tree_sitter_call_graph_analyzer.TREE_SITTER_AVAILABLE', True):
        return TreeSitterCallGraphAnalyzer(
            vcs=mock_vcs,
            ast_parser=mock_ast,
            repo_base_path="/test/repo",
        )


@pytest.fixture
def python_sample_code():
    """Sample Python code with function calls."""
    return """
def greet(name):
    return f"Hello, {name}!"

def main():
    # Call greet function
    result = greet("World")
    print(result)
    
def test_greet():
    assert greet("Test") == "Hello, Test!"
"""


@pytest.fixture
def javascript_sample_code():
    """Sample JavaScript code with function calls."""
    return """
function greet(name) {
    return `Hello, ${name}!`;
}

function main() {
    // Call greet function
    const result = greet("World");
    console.log(result);
}

function testGreet() {
    assertEquals(greet("Test"), "Hello, Test!");
}
"""


@pytest.fixture
def python_import_code():
    """Sample Python code with imports."""
    return """
from utils import helper_function
import os
from typing import List, Optional

def process():
    helper_function()
    os.path.join("a", "b")
"""


class TestTreeSitterCallGraphAnalyzer:
    """Tests for TreeSitterCallGraphAnalyzer."""
    
    @pytest.mark.asyncio
    async def test_find_callers_python_success(self, call_graph_analyzer, python_sample_code):
        """Test finding callers of a Python function."""
        language = Language(name="python")
        
        # Mock grep output
        grep_output = "src/main.py:7:    result = greet(\"World\")\nsrc/main.py:11:    assert greet(\"Test\") == \"Hello, Test!\""
        
        # Mock subprocess run
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout=grep_output,
                returncode=0,
            )
            
            # Mock file reading to get code context
            with patch("builtins.open", create=True) as mock_open:
                mock_open.return_value.__enter__.return_value.readlines.return_value = python_sample_code.splitlines(True)
                
                # Mock tree-sitter parsing
                with patch.object(call_graph_analyzer, "_verify_is_call_site", return_value=True):
                    with patch.object(call_graph_analyzer, "_extract_caller_name") as mock_caller:
                        mock_caller.side_effect = ["main", "test_greet"]
                        
                        callers = await call_graph_analyzer.find_callers(
                            function_name="greet",
                            file_path=FilePath("src/main.py"),
                            language=language,
                            repository="/test/repo",
                        )
        
        assert len(callers) == 2
        assert callers[0].callee_name == "greet"
        assert callers[0].caller_name == "main"
        assert callers[1].caller_name == "test_greet"
        assert callers[0].file_path.value == "src/main.py"
    
    @pytest.mark.asyncio
    async def test_find_callers_javascript_success(self, call_graph_analyzer, javascript_sample_code):
        """Test finding callers of a JavaScript function."""
        language = Language(name="javascript")
        
        # Mock grep output
        grep_output = "src/app.js:7:    const result = greet(\"World\");\nsrc/app.js:12:    assertEquals(greet(\"Test\"), \"Hello, Test!\");"
        
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout=grep_output,
                returncode=0,
            )
            
            with patch("builtins.open", create=True) as mock_open:
                mock_open.return_value.__enter__.return_value.readlines.return_value = javascript_sample_code.splitlines(True)
                
                with patch.object(call_graph_analyzer, "_verify_is_call_site", return_value=True):
                    with patch.object(call_graph_analyzer, "_extract_caller_name") as mock_caller:
                        mock_caller.side_effect = ["main", "testGreet"]
                        
                        callers = await call_graph_analyzer.find_callers(
                            function_name="greet",
                            file_path=FilePath("src/app.js"),
                            language=language,
                            repository="/test/repo",
                        )
        
        assert len(callers) == 2
        assert callers[0].caller_name == "main"
        assert callers[1].caller_name == "testGreet"
    
    @pytest.mark.asyncio
    async def test_find_callers_false_positive_filtering(self, call_graph_analyzer):
        """Test that false positives are filtered out."""
        language = Language(name="python")
        
        # Mock grep output with false positives
        grep_output = """src/main.py:1:# This is a comment about greet()
src/main.py:5:    result = greet("World")
src/main.py:10:def greet(name):
src/main.py:15:"Call greet function"
"""
        
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout=grep_output,
                returncode=0,
            )
            
            with patch("builtins.open", create=True) as mock_open:
                mock_open.return_value.__enter__.return_value.readlines.return_value = [""] * 20
                
                # Only the actual call on line 5 should be verified as true
                def verify_side_effect(code, line_num, func_name, lang):
                    return line_num == 5
                
                with patch.object(call_graph_analyzer, "_verify_is_call_site", side_effect=verify_side_effect):
                    with patch.object(call_graph_analyzer, "_extract_caller_name", return_value="main"):
                        callers = await call_graph_analyzer.find_callers(
                            function_name="greet",
                            file_path=FilePath("src/main.py"),
                            language=language,
                            repository="/test/repo",
                        )
        
        # Should only have 1 caller (line 5), not 4
        assert len(callers) == 1
        assert callers[0].line_number == 5
    
    @pytest.mark.asyncio
    async def test_find_callers_no_matches(self, call_graph_analyzer):
        """Test when no callers are found."""
        language = Language(name="python")
        
        # Mock grep output (no matches)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout=b"",
                returncode=1,
            )
            
            callers = await call_graph_analyzer.find_callers(
                function_name="nonexistent_function",
                file_path=FilePath("src/main.py"),
                language=language,
                repository="/test/repo",
            )
        
        assert len(callers) == 0
    
    @pytest.mark.asyncio
    async def test_find_importers_python_from_import(self, call_graph_analyzer, python_import_code):
        """Test finding importers with Python 'from ... import ...' syntax."""
        language = Language(name="python")
        
        # Mock grep output
        grep_output = "src/main.py:1:from utils import helper_function\nsrc/test.py:3:from utils import helper_function, another_func"
        
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout=grep_output,
                returncode=0,
            )
            
            with patch("builtins.open", create=True) as mock_open:
                mock_open.return_value.__enter__.return_value.readlines.return_value = python_import_code.splitlines(True)
                
                with patch.object(call_graph_analyzer, "_parse_python_import") as mock_parse:
                    mock_parse.side_effect = [
                        ("helper_function",),
                        ("helper_function", "another_func"),
                    ]
                    
                    importers = await call_graph_analyzer.find_importers(
                        file_path=FilePath("utils.py"),
                        language=language,
                        repository="/test/repo",
                    )
        
        assert len(importers) == 2
        assert importers[0].file_path.value == "src/main.py"
        assert "helper_function" in importers[0].imported_names
        assert importers[1].file_path.value == "src/test.py"
        assert "helper_function" in importers[1].imported_names
        assert "another_func" in importers[1].imported_names
    
    @pytest.mark.asyncio
    async def test_find_importers_javascript_import(self, call_graph_analyzer):
        """Test finding importers with JavaScript 'import' syntax."""
        language = Language(name="javascript")
        
        # Mock grep output
        grep_output = "src/main.js:1:import { helper } from './utils';\nsrc/test.js:2:import * as utils from './utils';"
        
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout=grep_output,
                returncode=0,
            )
            
            with patch("builtins.open", create=True) as mock_open:
                mock_open.return_value.__enter__.return_value.readlines.return_value = ["import { helper } from './utils';"]
                
                with patch.object(call_graph_analyzer, "_parse_js_import") as mock_parse:
                    mock_parse.side_effect = [
                        ("helper",),
                        ("*",),
                    ]
                    
                    importers = await call_graph_analyzer.find_importers(
                        file_path=FilePath("utils.js"),
                        language=language,
                        repository="/test/repo",
                    )
        
        assert len(importers) == 2
        assert importers[0].file_path.value == "src/main.js"
        assert "helper" in importers[0].imported_names
    
    @pytest.mark.asyncio
    async def test_find_importers_no_matches(self, call_graph_analyzer):
        """Test when no importers are found."""
        language = Language(name="python")
        
        # Mock grep output (no matches)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout=b"",
                returncode=1,
            )
            
            importers = await call_graph_analyzer.find_importers(
                file_path=FilePath("utils.py"),
                language=language,
                repository="/test/repo",
            )
        
        assert len(importers) == 0
    
    @pytest.mark.asyncio
    async def test_find_callers_grep_error(self, call_graph_analyzer):
        """Test handling of grep errors."""
        language = Language(name="python")
        
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = Exception("Grep failed")
            
            with pytest.raises(AnalysisError) as exc_info:
                await call_graph_analyzer.find_callers(
                    function_name="greet",
                    file_path=FilePath("src/main.py"),
                    language=language,
                    repository="/test/repo",
                )
            
            assert "Failed to find callers" in str(exc_info.value)
    
    def test_is_comment_line_python(self, call_graph_analyzer):
        """Test comment detection in Python."""
        assert call_graph_analyzer._is_comment_line("# This is a comment", Language(name="python"))
        assert call_graph_analyzer._is_comment_line("    # Indented comment", Language(name="python"))
        assert not call_graph_analyzer._is_comment_line("code()  # comment", Language(name="python"))
        assert not call_graph_analyzer._is_comment_line("print('hello')", Language(name="python"))
    
    def test_is_comment_line_javascript(self, call_graph_analyzer):
        """Test comment detection in JavaScript."""
        assert call_graph_analyzer._is_comment_line("// This is a comment", Language(name="javascript"))
        assert call_graph_analyzer._is_comment_line("    // Indented comment", Language(name="javascript"))
        assert not call_graph_analyzer._is_comment_line("code();  // comment", Language(name="javascript"))
        assert not call_graph_analyzer._is_comment_line("console.log('hello');", Language(name="javascript"))
    
    def test_is_in_string_literal(self, call_graph_analyzer):
        """Test string literal detection."""
        assert call_graph_analyzer._is_in_string_literal('"Call greet()"', "greet")
        assert call_graph_analyzer._is_in_string_literal("'Call greet()'", "greet")
        assert call_graph_analyzer._is_in_string_literal('f"Call {greet()}"', "greet")
        assert not call_graph_analyzer._is_in_string_literal("result = greet()", "greet")
    
    def test_is_function_definition_python(self, call_graph_analyzer):
        """Test function definition detection in Python."""
        assert call_graph_analyzer._is_function_definition("def greet(name):", "greet", Language(name="python"))
        assert call_graph_analyzer._is_function_definition("    def greet(name):", "greet", Language(name="python"))
        assert call_graph_analyzer._is_function_definition("async def greet(name):", "greet", Language(name="python"))
        assert not call_graph_analyzer._is_function_definition("    result = greet()", "greet", Language(name="python"))
    
    def test_is_function_definition_javascript(self, call_graph_analyzer):
        """Test function definition detection in JavaScript."""
        assert call_graph_analyzer._is_function_definition("function greet(name) {", "greet", Language(name="javascript"))
        assert call_graph_analyzer._is_function_definition("  function greet(name) {", "greet", Language(name="javascript"))
        assert call_graph_analyzer._is_function_definition("const greet = (name) => {", "greet", Language(name="javascript"))
        assert not call_graph_analyzer._is_function_definition("  const result = greet();", "greet", Language(name="javascript"))
    
    def test_has_call_syntax(self, call_graph_analyzer):
        """Test call syntax detection."""
        lang = Language(name="python")
        assert call_graph_analyzer._has_call_syntax("result = greet()", "greet", lang)
        assert call_graph_analyzer._has_call_syntax("greet('hello')", "greet", lang)
        assert call_graph_analyzer._has_call_syntax("obj.greet()", "greet", lang)
        assert not call_graph_analyzer._has_call_syntax("greet", "greet", lang)
        assert not call_graph_analyzer._has_call_syntax("greet_user", "greet", lang)
    
    def test_extract_context(self, call_graph_analyzer):
        """Test context extraction around a line."""
        file_content = "line 1\nline 2\nline 3\nline 4\nline 5\nline 6\nline 7\n"
        
        # Line 4, context of 2 lines before and after
        context = call_graph_analyzer._extract_context(file_content, 4, window=2)
        
        assert "line 2" in context
        assert "line 3" in context
        assert "line 4" in context
        assert "line 5" in context
        assert "line 6" in context
        assert "line 1" not in context
        assert "line 7" not in context
    
    def test_file_path_to_module_name_python(self, call_graph_analyzer):
        """Test converting file path to Python module name."""
        # src is stripped from the beginning
        assert call_graph_analyzer._file_path_to_module_name("src/utils.py", Language(name="python")) == "utils"
        assert call_graph_analyzer._file_path_to_module_name("utils.py", Language(name="python")) == "utils"
        # src is stripped, but lib is kept as a package (only first-level src/lib/app are stripped)
        assert call_graph_analyzer._file_path_to_module_name("src/lib/helper.py", Language(name="python")) == "lib.helper"
        # lib is stripped if it's the first level
        assert call_graph_analyzer._file_path_to_module_name("lib/helper.py", Language(name="python")) == "helper"
        # Subdirectories (excluding src/lib/app) are kept
        assert call_graph_analyzer._file_path_to_module_name("src/auth/services.py", Language(name="python")) == "auth.services"
    
    def test_file_path_to_module_name_javascript(self, call_graph_analyzer):
        """Test converting file path to JavaScript module name."""
        # JavaScript just returns the file stem (no special root stripping for JS)
        result = call_graph_analyzer._file_path_to_module_name("src/utils.js", Language(name="javascript"))
        assert result == "utils"  # JS doesn't use the full path unless multi-part    
    def test_get_import_patterns_python(self, call_graph_analyzer):
        """Test import pattern generation for Python."""
        patterns = call_graph_analyzer._get_import_patterns("utils", Language(name="python"))
        
        assert "from utils import" in patterns
        assert "import utils" in patterns
    
    def test_get_import_patterns_javascript(self, call_graph_analyzer):
        """Test import pattern generation for JavaScript."""
        patterns = call_graph_analyzer._get_import_patterns("utils", Language(name="javascript"))
        
        assert any("from" in p or "require" in p for p in patterns)
        assert any("utils" in p for p in patterns)
    
    def test_get_file_extensions(self, call_graph_analyzer):
        """Test file extension retrieval."""
        assert "py" in call_graph_analyzer._get_file_extensions(Language(name="python"))
        assert "js" in call_graph_analyzer._get_file_extensions(Language(name="javascript"))
        assert "ts" in call_graph_analyzer._get_file_extensions(Language(name="typescript"))
        assert "go" in call_graph_analyzer._get_file_extensions(Language(name="go"))
