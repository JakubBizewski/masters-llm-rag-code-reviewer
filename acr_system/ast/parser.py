"""AST Parser interface (port)."""
from abc import ABC, abstractmethod
from typing import List

from acr_system.domain.entities.entities import DiffHunk, FunctionNode
from acr_system.domain.value_objects.value_objects import Language


class ASTParser(ABC):
    """Abstrakcja dla parsowania AST i ekstrakcji struktury kodu (Tree-sitter).
    
    Port w architekturze heksagonalnej - definiuje kontrakt dla parsowania kodu.
    Implementacja: TreeSitterAdapter używa tree-sitter do parsowania różnych języków.
    """
    
    @abstractmethod
    def extract_functions(self, code: str, language: Language) -> List[FunctionNode]:
        """Ekstrakcja funkcji z kodu źródłowego.
        
        Używane do augmentacji kontekstu RAG (izolacja funkcji, call graph).
        
        Args:
            code: Kod źródłowy do parsowania
            language: Język programowania (Python, JavaScript, etc.)
            
        Returns:
            Lista wyekstrahowanych funkcji z metadanymi (nazwa, linie, ciało)
        """
        pass
    
    @abstractmethod
    def extract_changed_functions(
        self,
        diff: DiffHunk,
        code: str,
        language: Language,
    ) -> List[FunctionNode]:
        """Ekstrakcja tylko funkcji zmienionych w diff (context enhancement).
        
        Args:
            diff: Diff hunk z informacjami o zmianach
            code: Pełny kod pliku
            language: Język programowania
            
        Returns:
            Lista funkcji które zawierają zmiany z diffa
        """
        pass
    
    @abstractmethod
    def extract_classes(self, code: str, language: Language) -> List[dict]:
        """Ekstrakcja klas z kodu źródłowego.
        
        Args:
            code: Kod źródłowy
            language: Język programowania
            
        Returns:
            Lista klas z metadanymi (nazwa, metody, linie)
        """
        pass
    
    @abstractmethod
    def extract_imports(self, code: str, language: Language) -> List[str]:
        """Ekstrakcja importów z kodu źródłowego.
        
        Args:
            code: Kod źródłowy
            language: Język programowania
            
        Returns:
            Lista importowanych modułów/pakietów
        """
        pass
