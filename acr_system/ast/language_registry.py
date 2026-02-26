"""Language Registry for managing language strategies (Open/Closed Principle)."""
from typing import Dict, List, Optional

from acr_system.ast.strategies.language_strategy import LanguageStrategy
from acr_system.domain.value_objects.value_objects import Language
from acr_system.shared.logging.logger import get_logger

logger = get_logger(__name__)


class LanguageRegistry:
    """Registry wzorzec dla language strategies.
    
    Open/Closed Principle:
    - Zamknięty na modyfikacje (nie trzeba zmieniać tego kodu)
    - Otwarty na rozszerzenia (można rejestrować nowe języki)
    
    Dodanie nowego języka:
    1. Stwórz RustLanguageStrategy(LanguageStrategy)
    2. Dodaj Language.RUST do enum
    3. Zarejestruj: LanguageRegistry.register(Language.RUST, RustLanguageStrategy())
    4. TreeSitterParser automatycznie obsłuży Rust!
    """
    
    _strategies: Dict[Language, LanguageStrategy] = {}
    
    @classmethod
    def register(cls, language: Language, strategy: LanguageStrategy) -> None:
        """Rejestruje strategię dla języka.
        
        Args:
            language: Język programowania (enum)
            strategy: Instancja strategii dla języka
        """
        cls._strategies[language] = strategy
        logger.debug(f"Registered strategy for {language.name}: {strategy.__class__.__name__}")
    
    @classmethod
    def get_strategy(cls, language: Language) -> Optional[LanguageStrategy]:
        """Zwraca strategię dla języka.
        
        Args:
            language: Język programowania
            
        Returns:
            Strategia dla języka lub None jeśli nie zarejestrowana
        """
        return cls._strategies.get(language)
    
    @classmethod
    def is_supported(cls, language: Language) -> bool:
        """Sprawdza czy język jest wspierany.
        
        Args:
            language: Język programowania
            
        Returns:
            True jeśli język ma zarejestrowaną strategię
        """
        return language in cls._strategies
    
    @classmethod
    def list_supported(cls) -> List[Language]:
        """Zwraca listę wspieranych języków.
        
        Returns:
            Lista języków z zarejestrowanymi strategiami
        """
        return list(cls._strategies.keys())
    
    @classmethod
    def clear(cls) -> None:
        """Czyści registry (przydatne w testach)."""
        cls._strategies.clear()


def register_builtin_languages() -> None:
    """Rejestruje wbudowane języki.
    
    Wywoływane automatycznie podczas importu modułu.
    """
    from acr_system.ast.strategies.go_strategy import GoLanguageStrategy
    from acr_system.ast.strategies.javascript_strategy import JavaScriptLanguageStrategy
    from acr_system.ast.strategies.python_strategy import PythonLanguageStrategy
    from acr_system.ast.strategies.typescript_strategy import TypeScriptLanguageStrategy
    
    LanguageRegistry.register(Language(name="python"), PythonLanguageStrategy())
    LanguageRegistry.register(Language(name="javascript"), JavaScriptLanguageStrategy())
    LanguageRegistry.register(Language(name="typescript"), TypeScriptLanguageStrategy())
    LanguageRegistry.register(Language(name="go"), GoLanguageStrategy())
    
    logger.info(f"Registered {len(LanguageRegistry.list_supported())} language strategies")


# Auto-register builtin languages on module import
register_builtin_languages()
