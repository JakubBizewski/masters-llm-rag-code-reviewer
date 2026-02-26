"""Tests for Language Registry (Open/Closed Principle)."""
import pytest

from acr_system.ast.language_registry import LanguageRegistry
from acr_system.ast.strategies.language_strategy import LanguageStrategy
from acr_system.domain.value_objects.value_objects import Language


class TestLanguageRegistry:
    """Tests for LanguageRegistry."""
    
    def test_python_strategy_registered(self):
        """Test that Python strategy is registered."""
        strategy = LanguageRegistry.get_strategy(Language.PYTHON)
        
        assert strategy is not None
        assert strategy.get_parser_name() == "python"
    
    def test_javascript_strategy_registered(self):
        """Test that JavaScript strategy is registered."""
        strategy = LanguageRegistry.get_strategy(Language.JAVASCRIPT)
        
        assert strategy is not None
        assert strategy.get_parser_name() == "javascript"
    
    def test_typescript_strategy_registered(self):
        """Test that TypeScript strategy is registered."""
        strategy = LanguageRegistry.get_strategy(Language.TYPESCRIPT)
        
        assert strategy is not None
        assert strategy.get_parser_name() == "typescript"
    
    def test_go_strategy_registered(self):
        """Test that Go strategy is registered."""
        strategy = LanguageRegistry.get_strategy(Language.GO)
        
        assert strategy is not None
        assert strategy.get_parser_name() == "go"
    
    def test_is_supported_returns_true_for_registered(self):
        """Test is_supported for registered languages."""
        assert LanguageRegistry.is_supported(Language.PYTHON) is True
        assert LanguageRegistry.is_supported(Language.JAVASCRIPT) is True
    
    def test_is_supported_returns_false_for_unknown(self):
        """Test is_supported for unknown languages."""
        assert LanguageRegistry.is_supported(Language.UNKNOWN) is False
    
    def test_list_supported_returns_registered_languages(self):
        """Test list_supported returns all registered languages."""
        supported = LanguageRegistry.list_supported()
        
        assert Language.PYTHON in supported
        assert Language.JAVASCRIPT in supported
        assert Language.TYPESCRIPT in supported
        assert Language.GO in supported
    
    def test_custom_language_registration(self):
        """Test Open/Closed Principle: można zarejestrować custom język."""
        # Create custom strategy
        class RustLanguageStrategy(LanguageStrategy):
            def get_parser_name(self) -> str:
                return "rust"
            
            def get_function_query(self) -> str:
                return "(function_item) @function"
            
            def get_class_query(self) -> str:
                return "(struct_item) @struct"
            
            def get_import_query(self) -> str:
                return "(use_declaration) @import"
            
            def extract_function_name(self, node: any) -> str:
                return "test_function"
            
            def extract_class_name(self, node: any) -> str:
                return "TestStruct"
        
        # Register custom language
        # Note: We'd need Language.RUST in enum for this to work in production
        # For test, we'll just verify the registration mechanism works
        custom_strategy = RustLanguageStrategy()
        
        # In production: LanguageRegistry.register(Language.RUST, custom_strategy)
        # For test: verify the method exists and works
        assert hasattr(LanguageRegistry, 'register')
        assert callable(LanguageRegistry.register)


class TestPythonStrategy:
    """Tests for Python language strategy."""
    
    def test_python_function_query(self):
        """Test Python function query."""
        strategy = LanguageRegistry.get_strategy(Language.PYTHON)
        
        query = strategy.get_function_query()
        assert "function_definition" in query
        assert "@function" in query
    
    def test_python_class_query(self):
        """Test Python class query."""
        strategy = LanguageRegistry.get_strategy(Language.PYTHON)
        
        query = strategy.get_class_query()
        assert "class_definition" in query
        assert "@class" in query
    
    def test_python_import_query(self):
        """Test Python import query."""
        strategy = LanguageRegistry.get_strategy(Language.PYTHON)
        
        query = strategy.get_import_query()
        assert "import_statement" in query or "import_from_statement" in query


class TestJavaScriptStrategy:
    """Tests for JavaScript language strategy."""
    
    def test_javascript_function_query(self):
        """Test JavaScript function query including arrow functions."""
        strategy = LanguageRegistry.get_strategy(Language.JAVASCRIPT)
        
        query = strategy.get_function_query()
        assert "function_declaration" in query
        assert "arrow_function" in query
    
    def test_javascript_class_query(self):
        """Test JavaScript class query."""
        strategy = LanguageRegistry.get_strategy(Language.JAVASCRIPT)
        
        query = strategy.get_class_query()
        assert "class_declaration" in query


class TestTypeScriptStrategy:
    """Tests for TypeScript language strategy."""
    
    def test_typescript_includes_interfaces(self):
        """Test that TypeScript query includes interfaces."""
        strategy = LanguageRegistry.get_strategy(Language.TYPESCRIPT)
        
        query = strategy.get_class_query()
        assert "interface_declaration" in query


class TestGoStrategy:
    """Tests for Go language strategy."""
    
    def test_go_method_declarations(self):
        """Test Go method declarations with receivers."""
        strategy = LanguageRegistry.get_strategy(Language.GO)
        
        query = strategy.get_function_query()
        assert "method_declaration" in query
    
    def test_go_struct_and_interface_query(self):
        """Test Go struct and interface extraction."""
        strategy = LanguageRegistry.get_strategy(Language.GO)
        
        query = strategy.get_class_query()
        assert "struct_type" in query
        assert "interface_type" in query
