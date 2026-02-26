# AST Parsing Module

Moduł parsowania AST (Abstract Syntax Tree) używający tree-sitter do ekstrakcji struktury kodu.

## Architektura

System wykorzystuje **wzorzec Strategy + Registry** zgodnie z **Open/Closed Principle**:

```
ASTParser (port interface)
    ↓
TreeSitterAdapter (implementacja)
    ↓
LanguageRegistry (OCP registry)
    ↓
LanguageStrategy (abstrakcja per język)
    ↓
[PythonStrategy, JavaScriptStrategy, TypeScriptStrategy, GoStrategy, ...]
```

## Funkcjonalność

### ASTParser Interface

Port w Clean Architecture definiujący kontrakt dla parsowania kodu:

- `extract_functions()` - ekstrakcja funkcji z kodu
- `extract_changed_functions()` - funkcje zawierające zmiany z diff
- `extract_classes()` - ekstrakcja klas/struktur
- `extract_imports()` - ekstrakcja importów

### TreeSitterAdapter

Implementacja używająca tree-sitter:

- Parsowanie kodu w różnych językach
- Query execution (S-expressions)
- Cache parserów per język
- Error recovery dla niepełnego kodu

### LanguageStrategy

Abstrakcja strategii per język:

- `get_parser_name()` - nazwa parsera tree-sitter
- `get_function_query()` - query do ekstrakcji funkcji
- `get_class_query()` - query do ekstrakcji klas
- `get_import_query()` - query do ekstrakcji importów
- `extract_function_name()` - ekstrakcja nazwy z node'a
- `extract_class_name()` - ekstrakcja nazwy klasy

### LanguageRegistry

Registry do zarządzania strategiami (OCP):

- `register()` - rejestracja strategii
- `get_strategy()` - pobieranie strategii
- `is_supported()` - sprawdzenie wsparcia
- `list_supported()` - lista wspieranych języków

## Użycie

### Podstawowe parsowanie

```python
from acr_system.ast.tree_sitter_adapter import TreeSitterAdapter
from acr_system.domain.value_objects.value_objects import Language

adapter = TreeSitterAdapter()

# Ekstrakcja funkcji
code = """
def calculate_discount(price, rate):
    return price * (1 - rate)

def apply_coupon(order, coupon_code):
    discount_rate = get_discount_rate(coupon_code)
    return calculate_discount(order.total, discount_rate)
"""

functions = adapter.extract_functions(code, Language.PYTHON)

for func in functions:
    print(f"{func.name} (lines {func.start_line}-{func.end_line})")
    # calculate_discount (lines 2-3)
    # apply_coupon (lines 5-7)
```

### Ekstrakcja funkcji zmienionych w diff

```python
from acr_system.domain.entities.entities import DiffHunk
from acr_system.domain.value_objects.value_objects import FilePath

# Diff zmieniający tylko apply_coupon
diff = DiffHunk(
    file_path=FilePath("discount.py"),
    old_start_line=5,
    old_line_count=3,
    new_start_line=5,
    new_line_count=4,
    content="+ # Added comment\n  discount_rate = get_discount_rate(coupon_code)",
)

# Pełny kod pliku
full_code = """..."""

# Ekstrakcja tylko zmienionych funkcji
changed = adapter.extract_changed_functions(diff, full_code, Language.PYTHON)

# Zwraca tylko apply_coupon (linies 5-7 overlap z diffem)
assert len(changed) == 1
assert changed[0].name == "apply_coupon"
```

### Ekstrakcja klas

```python
code = """
class UserRepository:
    def __init__(self, db):
        self.db = db
    
    def get_user(self, user_id):
        return self.db.query(User).get(user_id)
"""

classes = adapter.extract_classes(code, Language.PYTHON)

for cls in classes:
    print(f"{cls['name']} (lines {cls['start_line']}-{cls['end_line']})")
    # UserRepository (lines 2-6)
```

### Ekstrakcja importów

```python
code = """
import os
from typing import List, Dict
from .models import User
"""

imports = adapter.extract_imports(code, Language.PYTHON)

print(imports)
# ['os', 'typing', '.models']
```

## Open/Closed Principle - Dodawanie nowego języka

### Krok 1: Dodaj enum value

```python
# domain/value_objects/value_objects.py

class Language(Enum):
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    GO = "go"
    RUST = "rust"  # ← Nowy język
    UNKNOWN = "unknown"
```

### Krok 2: Stwórz strategię

```python
# ast/strategies/rust_strategy.py

from acr_system.ast.strategies.language_strategy import LanguageStrategy

class RustLanguageStrategy(LanguageStrategy):
    """Strategia dla parsowania kodu Rust."""
    
    def get_parser_name(self) -> str:
        return "rust"
    
    def get_function_query(self) -> str:
        return """
        (function_item
            name: (identifier) @function.name
        ) @function.def
        """
    
    def get_class_query(self) -> str:
        return """
        [
            (struct_item
                name: (type_identifier) @struct.name
            ) @struct.def
            
            (impl_item
                type: (type_identifier) @impl.name
            ) @impl.def
        ]
        """
    
    def get_import_query(self) -> str:
        return """
        (use_declaration
            argument: (use_clause) @import.clause
        ) @import
        """
    
    def extract_function_name(self, node: any) -> str:
        name_node = node.child_by_field_name("name")
        if name_node:
            return name_node.text.decode("utf-8")
        return "unknown"
    
    def extract_class_name(self, node: any) -> str:
        # Rust uses different terminology (struct, impl)
        if node.type == "struct_item":
            name_node = node.child_by_field_name("name")
            if name_node:
                return name_node.text.decode("utf-8")
        elif node.type == "impl_item":
            type_node = node.child_by_field_name("type")
            if type_node:
                return type_node.text.decode("utf-8")
        return "unknown"
```

### Krok 3: Zarejestruj strategię

```python
# ast/language_registry.py

def register_builtin_languages() -> None:
    """Rejestruje wbudowane języki."""
    from acr_system.ast.strategies.go_strategy import GoLanguageStrategy
    from acr_system.ast.strategies.javascript_strategy import JavaScriptLanguageStrategy
    from acr_system.ast.strategies.python_strategy import PythonLanguageStrategy
    from acr_system.ast.strategies.rust_strategy import RustLanguageStrategy  # ← Import
    from acr_system.ast.strategies.typescript_strategy import TypeScriptLanguageStrategy
    
    LanguageRegistry.register(Language.PYTHON, PythonLanguageStrategy())
    LanguageRegistry.register(Language.JAVASCRIPT, JavaScriptLanguageStrategy())
    LanguageRegistry.register(Language.TYPESCRIPT, TypeScriptLanguageStrategy())
    LanguageRegistry.register(Language.GO, GoLanguageStrategy())
    LanguageRegistry.register(Language.RUST, RustLanguageStrategy())  # ← Rejestracja
```

### Gotowe!

**Brak modyfikacji w TreeSitterAdapter** (300+ linii kodu nie dotykane)!

```python
# Rust działa automatycznie
adapter = TreeSitterAdapter()
rust_code = """
fn calculate_discount(price: f64, rate: f64) -> f64 {
    price * (1.0 - rate)
}
"""

functions = adapter.extract_functions(rust_code, Language.RUST)
# Zwraca: [FunctionNode(name="calculate_discount", ...)]
```

## Wspierane języki

| Język | Status | Strategy |
|-------|--------|----------|
| Python | ✅ | `PythonLanguageStrategy` |
| JavaScript | ✅ | `JavaScriptLanguageStrategy` |
| TypeScript | ✅ | `TypeScriptLanguageStrategy` |
| Go | ✅ | `GoLanguageStrategy` |
| Rust | ⚠️ | Przykład (do zaimplementowania) |
| Java | ⚠️ | Do zaimplementowania |
| C# | ⚠️ | Do zaimplementowania |

## Integracja z ReviewOrchestrator

AST parsing używany do **augmentacji kontekstu RAG**:

```python
# domain/services/services.py

class ReviewOrchestrator:
    def _extract_functions_from_diff(self, pr: PullRequest) -> List[FunctionNode]:
        """
        Ekstrakcja funkcji ze zmienionych plików.
        Context enhancement - LLM widzi pełne funkcje, nie tylko diff fragments.
        """
        extracted = []
        
        for hunk in pr.diff_hunks:
            try:
                # Get full file content
                code = self.vcs.fetch_file(pr.repository, hunk.file_path, pr.target_branch)
                language = hunk.file_path.detect_language()
                
                # Extract changed functions
                functions = self.ast_parser.extract_changed_functions(hunk, code, language)
                extracted.extend(functions)
            except Exception as e:
                logger.warning(f"Could not extract functions from {hunk.file_path}: {e}")
        
        # Limit to prevent context overflow (top-5 most changed)
        return sorted(extracted, key=lambda f: f.size(), reverse=True)[:5]
```

Funkcje dodawane do `CodeContext.extracted_functions` i przekazywane do LLM:

```markdown
## Extracted Functions from Changed Files (AST)

Function: apply_coupon (lines 5-8)
```python
def apply_coupon(order, coupon_code):
    '''Apply coupon to order.'''
    discount_rate = get_discount_rate(coupon_code)
    order.total = calculate_discount(order.total, discount_rate)
    return order
```

Use this to understand the full context of changed code.
```

## Testowanie

```bash
# Testy jednostkowe
pytest tests/ast/ -v

# Testy integracyjne (wymagają tree-sitter parserów)
pytest tests/ast/ -v -m integration

# Coverage
pytest tests/ast/ --cov=acr_system.ast --cov-report=term-missing
```

## Instalacja tree-sitter parserów

```bash
# Instalacja core library
pip install tree-sitter

# Budowanie parserów (przykład dla Python)
git clone https://github.com/tree-sitter/tree-sitter-python
cd tree-sitter-python
# Build .so file
# Instrukcje na: https://tree-sitter.github.io/tree-sitter/

# Lub użyj pre-built binaries
```

W produkcji, parsery powinny być pre-built i dystrybuowane z aplikacją.

## Literatura

System AST parsing inspirowany:

- **Pornprasit2024FineTuningPromptingCR**: Tree-sitter do ekstrakcji funkcji dla context enhancement
- **Ren2025HydraReviewer**: Call graph + izolacja funkcji dla lepszego kontekstu LLM
- **Meng2025RARe**: AST-based context augmentation dla RAG retrieval

## Korzyści

1. **Open/Closed Principle**: Dodanie języka = tylko nowy plik strategii
2. **Separation of Concerns**: Każdy język ma izolowaną logikę
3. **Testowalność**: Strategy można testować w izolacji
4. **Rozszerzalność**: Registry pattern pozwala na runtime registration
5. **Context Enhancement**: Pełne funkcje zamiast diff fragments dla LLM
6. **Univerzalność**: Wspiera dowolny język z tree-sitter parser
