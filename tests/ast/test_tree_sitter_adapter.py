"""Tests for TreeSitterAdapter."""
import importlib.util
import pytest
from unittest.mock import MagicMock, patch

from acr_system.ast.tree_sitter_adapter import TreeSitterAdapter, TREE_SITTER_AVAILABLE
from acr_system.domain.entities.entities import DiffHunk, FunctionNode
from acr_system.domain.value_objects.value_objects import FilePath, Language


PYTHON_PARSER_AVAILABLE = importlib.util.find_spec("tree_sitter_python") is not None


@pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter not installed")
class TestTreeSitterAdapter:
    """Tests for TreeSitterAdapter.
    
    Note: These tests require tree-sitter and language parsers to be installed.
    In CI/CD, you may want to mock tree-sitter or install required parsers.
    """
    
    def test_adapter_initialization(self):
        """Test that adapter initializes correctly."""
        adapter = TreeSitterAdapter()
        
        assert adapter is not None
        assert hasattr(adapter, 'extract_functions')
        assert hasattr(adapter, 'extract_classes')
        assert hasattr(adapter, 'extract_imports')
    
    def test_extract_functions_returns_list(self):
        """Test that extract_functions returns a list."""
        adapter = TreeSitterAdapter()
        code = "def foo():\n    pass"
        
        # This may fail if python parser not available, which is OK for unit test
        functions = adapter.extract_functions(code, Language(name="python"))
        
        assert isinstance(functions, list)
    
    def test_extract_changed_functions_filters_by_diff_range(self):
        """Test that extract_changed_functions filters to diff range."""
        adapter = TreeSitterAdapter()
        
        # Mock extract_functions to return known functions
        with patch.object(adapter, 'extract_functions') as mock_extract:
            mock_extract.return_value = [
                FunctionNode(
                    name="func_a",
                    file_path=FilePath("test.py"),
                    start_line=1,
                    end_line=3,
                    body="def func_a():\n    pass",
                    language=Language(name="python"),
                ),
                FunctionNode(
                    name="func_b",
                    file_path=FilePath("test.py"),
                    start_line=10,
                    end_line=15,
                    body="def func_b():\n    pass",
                    language=Language(name="python"),
                ),
                FunctionNode(
                    name="func_c",
                    file_path=FilePath("test.py"),
                    start_line=20,
                    end_line=25,
                    body="def func_c():\n    pass",
                    language=Language(name="python"),
                ),
            ]
            
            # Create diff that only overlaps with func_b
            diff = DiffHunk(
                file_path=FilePath("test.py"),
                old_start_line=10,
                old_line_count=5,
                new_start_line=10,
                new_line_count=5,
                content="+ # Modified func_b",
            )
            
            changed = adapter.extract_changed_functions(diff, "code", Language(name="python"))
            
            # Should only return func_b (lines 10-15)
            assert len(changed) == 1
            assert changed[0].name == "func_b"
    
    def test_ranges_overlap_detects_overlap(self):
        """Test _ranges_overlap helper method."""
        # Overlapping ranges
        assert TreeSitterAdapter._ranges_overlap(1, 5, 3, 7) is True
        assert TreeSitterAdapter._ranges_overlap(3, 7, 1, 5) is True
        assert TreeSitterAdapter._ranges_overlap(1, 10, 5, 15) is True
        
        # Non-overlapping ranges
        assert TreeSitterAdapter._ranges_overlap(1, 5, 10, 15) is False
        assert TreeSitterAdapter._ranges_overlap(10, 15, 1, 5) is False
        
        # Adjacent ranges (not overlapping)
        assert TreeSitterAdapter._ranges_overlap(1, 5, 6, 10) is False
        
        # Identical ranges
        assert TreeSitterAdapter._ranges_overlap(1, 5, 1, 5) is True
        
        # One range contains another
        assert TreeSitterAdapter._ranges_overlap(1, 10, 3, 5) is True
        assert TreeSitterAdapter._ranges_overlap(3, 5, 1, 10) is True


@pytest.mark.skipif(TREE_SITTER_AVAILABLE, reason="Testing tree-sitter not installed")
class TestTreeSitterAdapterWithoutDependency:
    """Tests for TreeSitterAdapter when tree-sitter is not installed."""
    
    def test_raises_error_when_tree_sitter_not_installed(self):
        """Test that initialization raises error without tree-sitter."""
        from acr_system.shared.exceptions.infrastructure_exceptions import ASTParseError
        
        with pytest.raises(ASTParseError, match="tree-sitter not installed"):
            TreeSitterAdapter()


class TestTreeSitterIntegration:
    """Integration tests for tree-sitter (with actual parsing).
    
    These tests are more integration-level and may be skipped in unit test suite.
    They require tree-sitter parsers to be built and available.
    """
    
    @pytest.mark.skipif(
        not (TREE_SITTER_AVAILABLE and PYTHON_PARSER_AVAILABLE),
        reason="tree-sitter python parser not installed",
    )
    def test_extract_python_functions_from_real_code(self):
        """Integration test: extract functions from real Python code."""
        adapter = TreeSitterAdapter()
        
        code = """
def calculate_discount(price, rate):
    '''Calculate discount.'''
    if rate < 0 or rate > 1:
        raise ValueError("Invalid rate")
    return price * (1 - rate)

def apply_coupon(order, coupon_code):
    '''Apply coupon to order.'''
    discount_rate = get_discount_rate(coupon_code)
    order.total = calculate_discount(order.total, discount_rate)
    return order
"""
        
        functions = adapter.extract_functions(code, Language(name="python"))
        
        # Should extract 2 functions
        assert len(functions) >= 2
        
        # Check function names
        function_names = [f.name for f in functions]
        assert "calculate_discount" in function_names
        assert "apply_coupon" in function_names
        
        # Check line numbers
        calc_discount_func = next(f for f in functions if f.name == "calculate_discount")
        assert calc_discount_func.start_line >= 2
        assert calc_discount_func.end_line >= calc_discount_func.start_line
        assert "calculate_discount" in calc_discount_func.body
    
    @pytest.mark.skipif(
        not (TREE_SITTER_AVAILABLE and PYTHON_PARSER_AVAILABLE),
        reason="tree-sitter python parser not installed",
    )
    def test_extract_python_classes_from_real_code(self):
        """Integration test: extract classes from real Python code."""
        adapter = TreeSitterAdapter()
        
        code = """
class UserRepository:
    '''Repository for user data.'''
    
    def __init__(self, db):
        self.db = db
    
    def get_user(self, user_id):
        return self.db.query(User).get(user_id)

class AdminUser:
    '''Admin user class.'''
    pass
"""
        
        classes = adapter.extract_classes(code, Language(name="python"))
        
        # Should extract 2 classes
        assert len(classes) >= 2
        
        # Check class names
        class_names = [c["name"] for c in classes]
        assert "UserRepository" in class_names
        assert "AdminUser" in class_names
    
    @pytest.mark.skipif(
        not (TREE_SITTER_AVAILABLE and PYTHON_PARSER_AVAILABLE),
        reason="tree-sitter python parser not installed",
    )
    def test_extract_python_imports_from_real_code(self):
        """Integration test: extract imports from real Python code."""
        adapter = TreeSitterAdapter()
        
        code = """
import os
import sys
from typing import List, Dict
from pathlib import Path
from .models import User, Order
"""
        
        imports = adapter.extract_imports(code, Language(name="python"))
        
        # Should extract imports
        assert len(imports) >= 3
        
        # Check for expected imports
        assert "os" in imports or any("os" in imp for imp in imports)
        assert "typing" in imports or any("typing" in imp for imp in imports)
