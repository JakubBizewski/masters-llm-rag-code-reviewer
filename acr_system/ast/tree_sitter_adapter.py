"""Tree-sitter adapter for AST parsing."""
from typing import List, Optional

try:
    import tree_sitter
    from tree_sitter import Language as TSLanguage, Parser
    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False
    tree_sitter = None  # type: ignore
    TSLanguage = None  # type: ignore
    Parser = None  # type: ignore

from acr_system.ast.language_registry import LanguageRegistry
from acr_system.ast.parser import ASTParser
from acr_system.domain.entities.entities import DiffHunk, FunctionNode
from acr_system.domain.value_objects.value_objects import FilePath, Language
from acr_system.shared.exceptions.infrastructure_exceptions import ASTParseError
from acr_system.shared.logging.logger import get_logger

logger = get_logger(__name__)


class TreeSitterAdapter(ASTParser):
    """Implementacja ASTParser używając tree-sitter.
    
    Tree-sitter: incremental parsing library wspierająca wiele języków.
    - Szybkie parsowanie (incremental updates)
    - Robust error recovery (toleruje niepełny kod)
    - Query language (S-expressions) do ekstrakcji struktur
    
    Wzorzec Strategy + Registry:
    - Nie zawiera hardcoded queries dla języków
    - Używa LanguageRegistry do pobierania strategii
    - Dodanie nowego języka nie wymaga modyfikacji tego kodu (OCP)
    """
    
    def __init__(self):
        """Initialize tree-sitter adapter.
        
        Raises:
            ASTParseError: If tree-sitter is not installed
        """
        if not TREE_SITTER_AVAILABLE:
            raise ASTParseError(
                "tree-sitter not installed. Install with: pip install tree-sitter"
            )
        
        self._parsers = {}  # Cache dla parserów per język
        self._languages = {}  # Cache dla language objects
    
    def _get_parser(self, language: Language) -> Optional[Parser]:
        """Pobiera lub tworzy parser dla języka.
        
        Args:
            language: Język programowania
            
        Returns:
            Parser tree-sitter lub None jeśli język nie wspierany
        """
        if language in self._parsers:
            return self._parsers[language]
        
        strategy = LanguageRegistry.get_strategy(language)
        if not strategy:
            logger.warning(f"No strategy registered for {language.name}")
            return None
        
        try:
            # Get parser name from strategy
            parser_name = strategy.get_parser_name()
            
            # Create parser
            parser = Parser()
            
            # Load language (requires tree-sitter-{language} to be installed)
            # Try to import the language module dynamically
            try:
                # Import tree_sitter_{language} module and get language()
                import importlib
                module_name = f"tree_sitter_{parser_name}"
                language_module = importlib.import_module(module_name)
                
                # Get language function and wrap in tree_sitter.Language
                language_capsule = language_module.language()
                ts_language = TSLanguage(language_capsule)
                parser.language = ts_language
                
                # Cache
                self._parsers[language] = parser
                self._languages[language] = ts_language
                
                logger.debug(f"Initialized tree-sitter parser for {language.name}")
                return parser
                
            except Exception as e:
                logger.warning(
                    f"Could not load tree-sitter language for {parser_name}: {e}. "
                    f"Make sure tree-sitter-{parser_name} is installed."
                )
                return None
                
        except Exception as e:
            logger.error(f"Error creating parser for {language.name}: {e}")
            return None
    
    def extract_functions(self, code: str, language: Language, file_path: Optional[FilePath] = None) -> List[FunctionNode]:
        """Ekstrakcja funkcji z kodu źródłowego.
        
        Args:
            code: Kod źródłowy
            language: Język programowania
            file_path: Ścieżka do pliku (opcjonalna, domyślnie "unknown")
            
        Returns:
            Lista funkcji z metadanymi
        """
        if file_path is None:
            file_path = FilePath("unknown")
        
        parser = self._get_parser(language)
        if not parser:
            logger.warning(f"Parser not available for {language.name}")
            return []
        
        strategy = LanguageRegistry.get_strategy(language)
        if not strategy:
            return []
        
        try:
            # Parse code
            tree = parser.parse(bytes(code, "utf-8"))
            root_node = tree.root_node
            
            # Get function query from strategy
            query_string = strategy.get_function_query()
            ts_language = self._languages[language]
            
            # Use Query() and QueryCursor() for tree-sitter 0.25.x
            from tree_sitter import Query, QueryCursor
            query = Query(ts_language, query_string)
            cursor = QueryCursor(query)
            
            # Execute query - matches returns iter of (pattern_idx, captures_dict)
            matches = cursor.matches(root_node)
            
            functions = []
            for pattern_idx, captures_dict in matches:
                # captures_dict is {capture_name: [nodes]}
                for capture_name, nodes in captures_dict.items():
                    if "function.def" in capture_name or "function" in capture_name:
                        for node in nodes:
                            # Extract function metadata
                            func_name = strategy.extract_function_name(node)
                            start_line = node.start_point[0] + 1  # 1-indexed
                            end_line = node.end_point[0] + 1
                            body = node.text.decode("utf-8")
                            
                            function = FunctionNode(
                                name=func_name,
                                file_path=file_path,
                                start_line=start_line,
                                end_line=end_line,
                                body=body,
                                language=language,
                            )
                            functions.append(function)
            
            logger.debug(f"Extracted {len(functions)} functions from {language.name} code")
            return functions
            
        except Exception as e:
            logger.error(f"Error extracting functions: {e}", exc_info=True)
            return []
    
    def extract_changed_functions(
        self,
        diff: DiffHunk,
        code: str,
        language: Language,
    ) -> List[FunctionNode]:
        """Ekstrakcja tylko funkcji zmienionych w diff.
        
        Args:
            diff: Diff hunk
            code: Pełny kod pliku
            language: Język programowania
            
        Returns:
            Lista funkcji zawierających zmiany
        """
        # Extract all functions
        all_functions = self.extract_functions(code, language, diff.file_path)
        
        # Filter to only functions that overlap with diff
        changed_functions = []
        for func in all_functions:
            # Check if function overlaps with diff range
            diff_start = diff.new_start_line
            diff_end = diff.new_start_line + diff.new_line_count
            
            if self._ranges_overlap(
                func.start_line, func.end_line,
                diff_start, diff_end
            ):
                changed_functions.append(func)
        
        logger.debug(
            f"Filtered {len(changed_functions)} changed functions "
            f"from {len(all_functions)} total"
        )
        return changed_functions
    
    def extract_classes(self, code: str, language: Language) -> List[dict]:
        """Ekstrakcja klas z kodu źródłowego.
        
        Args:
            code: Kod źródłowy
            language: Język programowania
            
        Returns:
            Lista klas z metadanymi
        """
        parser = self._get_parser(language)
        if not parser:
            return []
        
        strategy = LanguageRegistry.get_strategy(language)
        if not strategy:
            return []
        
        try:
            # Parse code
            tree = parser.parse(bytes(code, "utf-8"))
            root_node = tree.root_node
            
            # Get class query from strategy
            query_string = strategy.get_class_query()
            ts_language = self._languages[language]
            
            # Use Query() and QueryCursor() for tree-sitter 0.25.x
            from tree_sitter import Query, QueryCursor
            query = Query(ts_language, query_string)
            cursor = QueryCursor(query)
            
            # Execute query - matches returns iter of (pattern_idx, captures_dict)
            matches = cursor.matches(root_node)
            
            classes = []
            for pattern_idx, captures_dict in matches:
                # captures_dict is {capture_name: [nodes]}
                for capture_name, nodes in captures_dict.items():
                    if "class" in capture_name or "type" in capture_name or "interface" in capture_name:
                        for node in nodes:
                            class_name = strategy.extract_class_name(node)
                            start_line = node.start_point[0] + 1
                            end_line = node.end_point[0] + 1
                            body = node.text.decode("utf-8")
                            
                            classes.append({
                                "name": class_name,
                                "start_line": start_line,
                                "end_line": end_line,
                                "body": body,
                                "type": capture_name,
                            })
            
            logger.debug(f"Extracted {len(classes)} classes from {language.name} code")
            return classes
            
        except Exception as e:
            logger.error(f"Error extracting classes: {e}", exc_info=True)
            return []
    
    def extract_imports(self, code: str, language: Language) -> List[str]:
        """Ekstrakcja importów z kodu źródłowego.
        
        Args:
            code: Kod źródłowy
            language: Język programowania
            
        Returns:
            Lista importowanych modułów
        """
        parser = self._get_parser(language)
        if not parser:
            return []
        
        strategy = LanguageRegistry.get_strategy(language)
        if not strategy:
            return []
        
        try:
            # Parse code
            tree = parser.parse(bytes(code, "utf-8"))
            root_node = tree.root_node
            
            # Get import query from strategy
            query_string = strategy.get_import_query()
            ts_language = self._languages[language]
            
            # Use Query() and QueryCursor() for tree-sitter 0.25.x
            from tree_sitter import Query, QueryCursor
            query = Query(ts_language, query_string)
            cursor = QueryCursor(query)
            
            # Execute query - matches returns iter of (pattern_idx, captures_dict)
            matches = cursor.matches(root_node)
            
            imports = []
            for pattern_idx, captures_dict in matches:
                # captures_dict is {capture_name: [nodes]}
                for capture_name, nodes in captures_dict.items():
                    if "import" in capture_name or "module" in capture_name or "source" in capture_name:
                        for node in nodes:
                            import_text = node.text.decode("utf-8").strip('"\'')
                            if import_text and import_text not in imports:
                                imports.append(import_text)
            
            logger.debug(f"Extracted {len(imports)} imports from {language.name} code")
            return imports
            
        except Exception as e:
            logger.error(f"Error extracting imports: {e}", exc_info=True)
            return []
    
    @staticmethod
    def _ranges_overlap(
        start1: int, end1: int,
        start2: int, end2: int
    ) -> bool:
        """Check if two line ranges overlap.
        
        Args:
            start1: Start line of range 1
            end1: End line of range 1
            start2: Start line of range 2
            end2: End line of range 2
            
        Returns:
            True if ranges overlap
        """
        return not (end1 < start2 or end2 < start1)
