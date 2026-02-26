"""TypeScript language strategy for tree-sitter parsing."""
from acr_system.ast.strategies.language_strategy import LanguageStrategy


class TypeScriptLanguageStrategy(LanguageStrategy):
    """Strategia dla parsowania kodu TypeScript."""
    
    def get_parser_name(self) -> str:
        """Zwraca nazwę parsera tree-sitter dla TypeScript."""
        return "typescript"
    
    def get_function_query(self) -> str:
        """Zwraca query do ekstrakcji funkcji w TypeScript.
        
        Ekstraktuje:
        - function declarations (function foo(): Type {})
        - arrow functions (const foo = (): Type => {})
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
            
            (method_signature
                name: (property_identifier) @function.name
            ) @function.sig
        ]
        """
    
    def get_class_query(self) -> str:
        """Zwraca query do ekstrakcji klas w TypeScript."""
        return """
        [
            (class_declaration
                name: (type_identifier) @class.name
            ) @class.def
            
            (interface_declaration
                name: (type_identifier) @class.name
            ) @interface.def
        ]
        """
    
    def get_import_query(self) -> str:
        """Zwraca query do ekstrakcji importów w TypeScript.
        
        Ekstraktuje:
        - import { foo } from 'bar'
        - import type { Foo } from 'bar'
        - import * as foo from 'bar'
        """
        return """
        [
            (import_statement
                source: (string) @import.source
            )
        ] @import
        """
    
    def extract_function_name(self, node: any) -> str:
        """Ekstraktuje nazwę funkcji z node'a TypeScript."""
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
        if node.type == "method_definition" or node.type == "method_signature":
            name_node = node.child_by_field_name("name")
            if name_node:
                return name_node.text.decode("utf-8")
        
        return "anonymous"
    
    def extract_class_name(self, node: any) -> str:
        """Ekstraktuje nazwę klasy z node'a TypeScript."""
        name_node = node.child_by_field_name("name")
        if name_node:
            return name_node.text.decode("utf-8")
        return "unknown"
