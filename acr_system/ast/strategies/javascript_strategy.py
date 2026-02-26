"""JavaScript language strategy for tree-sitter parsing."""
from acr_system.ast.strategies.language_strategy import LanguageStrategy


class JavaScriptLanguageStrategy(LanguageStrategy):
    """Strategia dla parsowania kodu JavaScript."""
    
    def get_parser_name(self) -> str:
        """Zwraca nazwę parsera tree-sitter dla JavaScript."""
        return "javascript"
    
    def get_function_query(self) -> str:
        """Zwraca query do ekstrakcji funkcji w JavaScript.
        
        Ekstraktuje:
        - function declarations (function foo() {})
        - arrow functions (const foo = () => {})
        - method definitions (class methods)
        - async functions
        """
        return """
        [
            (function_declaration
                name: (identifier) @function.name
            ) @function.def
            
            (variable_declarator
                name: (identifier) @function.name
                value: (arrow_function) @function.def
            )
            
            (variable_declarator
                name: (identifier) @function.name
                value: (function) @function.def
            )
            
            (method_definition
                name: (property_identifier) @function.name
            ) @function.def
        ]
        """
    
    def get_class_query(self) -> str:
        """Zwraca query do ekstrakcji klas w JavaScript."""
        return """
        (class_declaration
            name: (identifier) @class.name
        ) @class.def
        """
    
    def get_import_query(self) -> str:
        """Zwraca query do ekstrakcji importów w JavaScript.
        
        Ekstraktuje:
        - import foo from 'bar'
        - import { foo } from 'bar'
        - const foo = require('bar')
        """
        return """
        [
            (import_statement
                source: (string) @import.source
            )
            
            (variable_declarator
                value: (call_expression
                    function: (identifier) @require
                    arguments: (arguments (string) @import.source)
                )
            )
        ] @import
        """
    
    def extract_function_name(self, node: any) -> str:
        """Ekstraktuje nazwę funkcji z node'a JavaScript."""
        # For function declarations
        name_node = node.child_by_field_name("name")
        if name_node:
            return name_node.text.decode("utf-8")
        
        # For arrow functions in variable declarations
        if node.type == "variable_declarator":
            name_node = node.child_by_field_name("name")
            if name_node:
                return name_node.text.decode("utf-8")
        
        # For method definitions
        if node.type == "method_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                return name_node.text.decode("utf-8")
        
        return "anonymous"
    
    def extract_class_name(self, node: any) -> str:
        """Ekstraktuje nazwę klasy z node'a JavaScript."""
        name_node = node.child_by_field_name("name")
        if name_node:
            return name_node.text.decode("utf-8")
        return "unknown"
