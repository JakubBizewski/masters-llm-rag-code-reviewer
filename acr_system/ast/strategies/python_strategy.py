"""Python language strategy for tree-sitter parsing."""
from acr_system.ast.strategies.language_strategy import LanguageStrategy


class PythonLanguageStrategy(LanguageStrategy):
    """Strategia dla parsowania kodu Python."""
    
    def get_parser_name(self) -> str:
        """Zwraca nazwę parsera tree-sitter dla Python."""
        return "python"
    
    def get_function_query(self) -> str:
        """Zwraca query do ekstrakcji funkcji w Python.
        
        Ekstraktuje:
        - function_definition (def foo():)
        - async function (async def foo():)
        """
        return """
        (function_definition
            name: (identifier) @function.name
        ) @function.def
        """
    
    def get_class_query(self) -> str:
        """Zwraca query do ekstrakcji klas w Python."""
        return """
        (class_definition
            name: (identifier) @class.name
        ) @class.def
        """
    
    def get_import_query(self) -> str:
        """Zwraca query do ekstrakcji importów w Python.
        
        Ekstraktuje:
        - import foo
        - from foo import bar
        - from foo.bar import baz
        """
        return """
        [
            (import_statement
                name: (dotted_name) @import.module
            )
            (import_from_statement
                module_name: (dotted_name) @import.module
            )
        ]
        """
    
    def extract_function_name(self, node: any) -> str:
        """Ekstraktuje nazwę funkcji z node'a Python."""
        # Node structure: function_definition -> name (identifier)
        name_node = node.child_by_field_name("name")
        if name_node:
            return name_node.text.decode("utf-8")
        return "unknown"
    
    def extract_class_name(self, node: any) -> str:
        """Ekstraktuje nazwę klasy z node'a Python."""
        # Node structure: class_definition -> name (identifier)
        name_node = node.child_by_field_name("name")
        if name_node:
            return name_node.text.decode("utf-8")
        return "unknown"
