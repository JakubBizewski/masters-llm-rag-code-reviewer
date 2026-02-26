"""Go language strategy for tree-sitter parsing."""
from acr_system.ast.strategies.language_strategy import LanguageStrategy


class GoLanguageStrategy(LanguageStrategy):
    """Strategia dla parsowania kodu Go."""
    
    def get_parser_name(self) -> str:
        """Zwraca nazwę parsera tree-sitter dla Go."""
        return "go"
    
    def get_function_query(self) -> str:
        """Zwraca query do ekstrakcji funkcji w Go.
        
        Ekstraktuje:
        - function declarations (func foo() {})
        - method declarations (func (r *Receiver) foo() {})
        """
        return """
        [
            (function_declaration
                name: (identifier) @function.name
            ) @function.def
            
            (method_declaration
                name: (field_identifier) @function.name
            ) @function.def
        ]
        """
    
    def get_class_query(self) -> str:
        """Zwraca query do ekstrakcji struktur w Go.
        
        Go nie ma klas, ale ma struktury (structs) i interfejsy.
        """
        return """
        [
            (type_declaration
                (type_spec
                    name: (type_identifier) @type.name
                    type: (struct_type)
                )
            ) @type.struct
            
            (type_declaration
                (type_spec
                    name: (type_identifier) @type.name
                    type: (interface_type)
                )
            ) @type.interface
        ]
        """
    
    def get_import_query(self) -> str:
        """Zwraca query do ekstrakcji importów w Go.
        
        Ekstraktuje:
        - import "fmt"
        - import ("fmt" "os")
        """
        return """
        [
            (import_declaration
                (import_spec
                    path: (interpreted_string_literal) @import.path
                )
            )
        ] @import
        """
    
    def extract_function_name(self, node: any) -> str:
        """Ekstraktuje nazwę funkcji z node'a Go."""
        # For function declarations
        name_node = node.child_by_field_name("name")
        if name_node:
            return name_node.text.decode("utf-8")
        
        # For method declarations (includes receiver)
        if node.type == "method_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                # Get receiver type
                receiver_node = node.child_by_field_name("receiver")
                if receiver_node:
                    # Extract receiver type name
                    receiver_text = receiver_node.text.decode("utf-8")
                    func_name = name_node.text.decode("utf-8")
                    return f"{receiver_text}.{func_name}"
                return name_node.text.decode("utf-8")
        
        return "unknown"
    
    def extract_class_name(self, node: any) -> str:
        """Ekstraktuje nazwę typu (struct/interface) z node'a Go."""
        # Go uses type_spec with nested name
        if node.type == "type_declaration":
            for child in node.children:
                if child.type == "type_spec":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        return name_node.text.decode("utf-8")
        
        return "unknown"
