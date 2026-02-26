"""Language Strategy abstraction for tree-sitter queries."""
from abc import ABC, abstractmethod
from typing import List


class LanguageStrategy(ABC):
    """Abstrakcja strategii dla parsowania języka programowania.
    
    Wzorzec Strategy + Open/Closed Principle:
    - Każdy język ma swoją strategię z queries specyficznymi dla tree-sitter
    - Dodanie nowego języka = nowy plik strategii (brak modyfikacji TreeSitterParser)
    - Registry pattern do zarządzania strategiami
    """
    
    @abstractmethod
    def get_parser_name(self) -> str:
        """Zwraca nazwę parsera tree-sitter dla tego języka.
        
        Returns:
            Nazwa parsera (np. "python", "javascript", "typescript")
        """
        pass
    
    @abstractmethod
    def get_function_query(self) -> str:
        """Zwraca tree-sitter query do ekstrakcji funkcji.
        
        Returns:
            S-expression query dla tree-sitter
        """
        pass
    
    @abstractmethod
    def get_class_query(self) -> str:
        """Zwraca tree-sitter query do ekstrakcji klas.
        
        Returns:
            S-expression query dla tree-sitter
        """
        pass
    
    @abstractmethod
    def get_import_query(self) -> str:
        """Zwraca tree-sitter query do ekstrakcji importów.
        
        Returns:
            S-expression query dla tree-sitter
        """
        pass
    
    @abstractmethod
    def extract_function_name(self, node: any) -> str:
        """Ekstraktuje nazwę funkcji z node'a tree-sitter.
        
        Args:
            node: Tree-sitter node reprezentujący funkcję
            
        Returns:
            Nazwa funkcji
        """
        pass
    
    @abstractmethod
    def extract_class_name(self, node: any) -> str:
        """Ekstraktuje nazwę klasy z node'a tree-sitter.
        
        Args:
            node: Tree-sitter node reprezentujący klasę
            
        Returns:
            Nazwa klasy
        """
        pass
