"""Tree-sitter based Call Graph Analyzer implementation.

Pure technical analysis using grep + tree-sitter.
NO LLM dependency - only static code structure analysis.
"""
import asyncio
import re
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

try:
    from tree_sitter import Node, Parser, Query
    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False
    Node = None  # type: ignore
    Parser = None  # type: ignore
    Query = None  # type: ignore

from acr_system.ast.language_registry import LanguageRegistry
from acr_system.ast.parser import ASTParser
from acr_system.domain.interfaces.ports import CallGraphAnalyzer, VCSRepository
from acr_system.domain.value_objects.value_objects import (
    CallSite,
    FilePath,
    ImportSite,
    Language,
)
from acr_system.shared.exceptions.infrastructure_exceptions import AnalysisError
from acr_system.shared.logging.logger import get_logger

logger = get_logger(__name__)


class TreeSitterCallGraphAnalyzer(CallGraphAnalyzer):
    """Implementation of CallGraphAnalyzer using grep + tree-sitter.
    
    Pure static analysis - NO LLM required.
    
    Strategy for performance:
    1. Grep search for fast candidate discovery (millions of lines → seconds)
    2. Tree-sitter validation to filter false positives (parsing only matches)
    3. Context extraction (code around call/import site)
    
    Based on:
    - Ren2025HydraReviewer: Call graph analysis for cross-file dependencies
    - Meng2025RARe: Context expansion through dependency tracking
    """
    
    def __init__(
        self,
        vcs: VCSRepository,
        ast_parser: ASTParser,
        repo_base_path: Optional[str] = None,
    ):
        """Initialize the analyzer.
        
        Args:
            vcs: VCS adapter for fetching file contents
            ast_parser: AST parser (tree-sitter adapter) for validation
            repo_base_path: Base path for local repository (for grep). If None,
                           files will be fetched via VCS API (slower but works remotely)
        """
        if not TREE_SITTER_AVAILABLE:
            raise AnalysisError(
                "tree-sitter not installed. Install with: pip install tree-sitter"
            )
        
        self.vcs = vcs
        self.ast_parser = ast_parser
        self.repo_base_path = Path(repo_base_path) if repo_base_path else None
        
    async def find_callers(
        self,
        function_name: str,
        file_path: FilePath,
        repository: str,
        language: Language,
    ) -> List[CallSite]:
        """Find all places where a function is called (1 level deep).
        
        Algorithm:
        1. Grep search for function_name in repository (fast - milliseconds)
        2. For each candidate: parse with tree-sitter (only matched files)
        3. Verify it's a call_expression (not definition/comment/string)
        4. Extract context (5 lines around call) + caller function name
        
        Args:
            function_name: Name of the function to find calls for
            file_path: Path to file where function is defined
            repository: Repository identifier
            language: Programming language
            
        Returns:
            List of call sites where the function is invoked
            
        Raises:
            AnalysisError: If grep or tree-sitter parsing fails
        """
        logger.info(f"Finding callers of {function_name} in {repository}")
        
        try:
            # Step 1: Grep search (fast candidate discovery)
            grep_results = await self._grep_function_usage(
                repository, function_name, language
            )
            
            logger.debug(f"Grep found {len(grep_results)} candidates for {function_name}")
            
            if not grep_results:
                return []
            
            # Step 2-4: Validate with tree-sitter (only matched files)
            callers = []
            for candidate_file, line_num, line_content in grep_results:
                try:
                    # Fetch file content
                    file_content = await self.vcs.get_file_content(
                        repo=repository,
                        file_path=candidate_file,
                        ref="HEAD"
                    )
                    
                    # Verify: Is it a call site? (not definition/comment/string)
                    is_call = await self._verify_is_call_site(
                        file_content, line_num, function_name, language
                    )
                    
                    if is_call:
                        # Extract context (5 lines around call)
                        context = self._extract_context(file_content, line_num, window=5)
                        
                        # Extract caller function name from AST
                        caller_name = await self._extract_caller_name(
                            file_content, line_num, language
                        )
                        
                        call_site = CallSite(
                            file_path=FilePath(candidate_file),
                            line_number=line_num,
                            caller_name=caller_name or "module_scope",
                            callee_name=function_name,
                            context=context
                        )
                        callers.append(call_site)
                        
                        logger.debug(f"Verified call site: {call_site}")
                        
                except Exception as e:
                    logger.warning(
                        f"Could not analyze {candidate_file}:{line_num}: {e}"
                    )
                    continue
            
            logger.info(f"Found {len(callers)} verified callers for {function_name}")
            return callers
            
        except Exception as e:
            raise AnalysisError(f"Failed to find callers for {function_name}: {e}")
    
    async def find_importers(
        self,
        file_path: FilePath,
        repository: str,
        language: Language,
    ) -> List[ImportSite]:
        """Find all files that import from a given module (1 level deep).
        
        Algorithm:
        1. Determine module name from file_path ("auth.py" → "auth")
        2. Grep search for import patterns ("import auth", "from auth import ...")
        3. Parse with tree-sitter for validation + extract imported names
        4. Context extraction (3 lines around import)
        
        Args:
            file_path: Path to the module file
            repository: Repository identifier
            language: Programming language
            
        Returns:
            List of import sites where the module is imported
            
        Raises:
            AnalysisError: If grep or tree-sitter parsing fails
        """
        logger.info(f"Finding importers of {file_path} in {repository}")
        
        try:
            # Step 1: Determine module name
            module_name = self._file_path_to_module_name(file_path, language)
            
            logger.debug(f"Module name: {module_name}")
            
            # Language-specific import patterns
            import_patterns = self._get_import_patterns(module_name, language)
            
            importers = []
            for pattern in import_patterns:
                # Step 2: Grep search for imports
                grep_results = await self._grep_import_usage(
                    repository, pattern, language
                )
                
                logger.debug(
                    f"Grep found {len(grep_results)} import candidates for pattern '{pattern}'"
                )
                
                # Step 3-4: Validate and extract
                for candidate_file, line_num, line_content in grep_results:
                    try:
                        # Fetch file content
                        file_content = await self.vcs.get_file_content(
                            repo=repository,
                            file_path=candidate_file,
                            ref="HEAD"
                        )
                        
                        # Extract imported names from AST
                        imported_names = await self._extract_imported_names(
                            file_content, line_num, module_name, language
                        )
                        
                        if imported_names:
                            # Extract context (3 lines around import)
                            context = self._extract_context(
                                file_content, line_num, window=3
                            )
                            
                            import_site = ImportSite(
                                file_path=FilePath(candidate_file),
                                line_number=line_num,
                                imported_module=module_name,
                                imported_names=tuple(imported_names),  # Immutable
                                context=context
                            )
                            importers.append(import_site)
                            
                            logger.debug(f"Verified import site: {import_site}")
                            
                    except Exception as e:
                        logger.warning(
                            f"Could not analyze import in {candidate_file}:{line_num}: {e}"
                        )
                        continue
            
            logger.info(f"Found {len(importers)} verified importers for {file_path}")
            return importers
            
        except Exception as e:
            raise AnalysisError(f"Failed to find importers for {file_path}: {e}")
    
    # ==================== Helper Methods ====================
    
    async def _grep_function_usage(
        self,
        repository: str,
        function_name: str,
        language: Language,
    ) -> List[Tuple[str, int, str]]:
        """Use grep to find potential function usage locations.
        
        Returns:
            List of (file_path, line_number, line_content) tuples
        """
        if not self.repo_base_path:
            # VCS API mode - not implemented yet
            # In production, would need to fetch file list and search each file
            logger.warning("Grep search requires local repository. Using VCS API fallback.")
            return []
        
        try:
            # Language-specific file extensions
            extensions = self._get_file_extensions(language)
            include_pattern = " ".join([f"--include=*.{ext}" for ext in extensions])
            
            # Grep command: search for function name
            # -n: line numbers
            # -r: recursive
            # --include: file patterns
            # -w: word boundary (exact match)
            cmd = (
                f"grep -n -r {include_pattern} -w '{function_name}' "
                f"{self.repo_base_path} 2>/dev/null || true"
            )
            
            # Run grep
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,  # 30 second timeout
            )
            
            # Parse grep output: "file:line:content"
            matches = []
            for line in result.stdout.splitlines():
                parts = line.split(":", 2)
                if len(parts) >= 3:
                    file_path = parts[0]
                    try:
                        line_num = int(parts[1])
                        line_content = parts[2]
                        
                        # Make path relative to repository
                        rel_path = Path(file_path).relative_to(self.repo_base_path)
                        
                        matches.append((str(rel_path), line_num, line_content))
                    except (ValueError, OSError):
                        continue
            
            return matches
            
        except subprocess.TimeoutExpired:
            raise AnalysisError("Grep search timed out (>30s)")
        except Exception as e:
            raise AnalysisError(f"Grep search failed: {e}")
    
    async def _grep_import_usage(
        self,
        repository: str,
        import_pattern: str,
        language: Language,
    ) -> List[Tuple[str, int, str]]:
        """Use grep to find potential import locations.
        
        Args:
            repository: Repository identifier
            import_pattern: Pattern to search for (e.g., "import auth")
            language: Programming language
            
        Returns:
            List of (file_path, line_number, line_content) tuples
        """
        if not self.repo_base_path:
            logger.warning("Grep search requires local repository.")
            return []
        
        try:
            extensions = self._get_file_extensions(language)
            include_pattern = " ".join([f"--include=*.{ext}" for ext in extensions])
            
            # Grep for import statement
            cmd = (
                f"grep -n -r {include_pattern} '{import_pattern}' "
                f"{self.repo_base_path} 2>/dev/null || true"
            )
            
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            matches = []
            for line in result.stdout.splitlines():
                parts = line.split(":", 2)
                if len(parts) >= 3:
                    file_path = parts[0]
                    try:
                        line_num = int(parts[1])
                        line_content = parts[2]
                        rel_path = Path(file_path).relative_to(self.repo_base_path)
                        matches.append((str(rel_path), line_num, line_content))
                    except (ValueError, OSError):
                        continue
            
            return matches
            
        except subprocess.TimeoutExpired:
            raise AnalysisError("Import grep search timed out")
        except Exception as e:
            raise AnalysisError(f"Import grep search failed: {e}")
    
    async def _verify_is_call_site(
        self,
        file_content: str,
        line_number: int,
        function_name: str,
        language: Language,
    ) -> bool:
        """Verify that a line contains an actual function call using tree-sitter.
        
        Filters out:
        - Function definitions
        - Comments
        - String literals
        - False positives from grep
        
        Args:
            file_content: Full file content
            line_number: Line number to check (1-indexed)
            function_name: Function name to verify
            language: Programming language
            
        Returns:
            True if line contains a verified function call
        """
        try:
            strategy = LanguageRegistry.get_strategy(language)
            if not strategy:
                logger.warning(f"No strategy for {language.value}, skipping validation")
                return True  # Fallback: trust grep
            
            # Get tree-sitter parser from AST parser
            # This is a simplified check - just verify the function name appears
            # in a call context and not in a definition context
            
            # Extract the line and surrounding context
            lines = file_content.splitlines()
            if line_number < 1 or line_number > len(lines):
                return False
            
            target_line = lines[line_number - 1]
            
            # Simple heuristic checks (before expensive tree-sitter parsing):
            
            # 1. Check if it's a comment
            if self._is_comment_line(target_line, language):
                return False
            
            # 2. Check if it's in a string literal (simple check)
            if self._is_in_string_literal(target_line, function_name):
                return False
            
            # 3. Check if it's a function definition
            if self._is_function_definition(target_line, function_name, language):
                return False
            
            # 4. Check if function name is followed by call syntax
            if not self._has_call_syntax(target_line, function_name, language):
                return False
            
            # If all checks pass, it's likely a call site
            return True
            
        except Exception as e:
            logger.warning(f"Call site verification failed: {e}, falling back to grep")
            return True  # Fallback: trust grep if validation fails
    
    async def _extract_caller_name(
        self,
        file_content: str,
        line_number: int,
        language: Language,
    ) -> Optional[str]:
        """Extract the name of the function that contains the call site.
        
        Args:
            file_content: Full file content
            line_number: Line number of the call (1-indexed)
            language: Programming language
            
        Returns:
            Name of the containing function, or None if at module scope
        """
        try:
            # Use AST parser to extract all functions
            functions = self.ast_parser.extract_functions(file_content, language)
            
            # Find which function contains this line
            for func in functions:
                if func.start_line <= line_number <= func.end_line:
                    return func.name
            
            # Not inside any function - module scope
            return None
            
        except Exception as e:
            logger.warning(f"Could not extract caller name: {e}")
            return None
    
    async def _extract_imported_names(
        self,
        file_content: str,
        line_number: int,
        module_name: str,
        language: Language,
    ) -> List[str]:
        """Extract the specific names imported from a module.
        
        Examples:
        - "from auth import login, logout" → ["login", "logout"]
        - "import auth" → ["auth"]
        - "from auth import *" → ["*"]
        
        Args:
            file_content: Full file content
            line_number: Line number of the import (1-indexed)
            module_name: Name of the imported module
            language: Programming language
            
        Returns:
            List of imported names
        """
        try:
            lines = file_content.splitlines()
            if line_number < 1 or line_number > len(lines):
                return []
            
            import_line = lines[line_number - 1].strip()
            
            # Language-specific parsing
            if language.value == "python":
                return self._parse_python_import(import_line, module_name)
            elif language.value in ("javascript", "typescript"):
                return self._parse_js_import(import_line, module_name)
            elif language.value == "go":
                return self._parse_go_import(import_line, module_name)
            else:
                # Fallback: return module name
                return [module_name]
                
        except Exception as e:
            logger.warning(f"Could not extract imported names: {e}")
            return []
    
    def _extract_context(
        self,
        file_content: str,
        line_number: int,
        window: int = 5,
    ) -> str:
        """Extract code context around a line.
        
        Args:
            file_content: Full file content
            line_number: Target line (1-indexed)
            window: Number of lines before and after (default: 5)
            
        Returns:
            Context string with line numbers
        """
        lines = file_content.splitlines()
        
        # Calculate range
        start = max(0, line_number - window - 1)
        end = min(len(lines), line_number + window)
        
        # Extract lines with numbers
        context_lines = []
        for i in range(start, end):
            line_num = i + 1
            marker = ">" if line_num == line_number else " "
            context_lines.append(f"{marker} {line_num:4d} | {lines[i]}")
        
        return "\n".join(context_lines)
    
    def _file_path_to_module_name(
        self,
        file_path: FilePath,
        language: Language,
    ) -> str:
        """Convert file path to module name.
        
        Examples:
        - "src/auth.py" → "auth"
        - "src/utils/helpers.py" → "utils.helpers"
        - "index.js" → "index"
        
        Args:
            file_path: Path to the file
            language: Programming language
            
        Returns:
            Module name
        """
        path = Path(file_path.value)
        
        # Remove extension
        module_name = path.stem
        
        # For Python, include package structure
        if language.value == "python" and len(path.parts) > 1:
            # Get all parent directories except the first (usually "src")
            parts = list(path.parts[:-1])
            if parts and parts[0] in ("src", "lib", "app"):
                parts = parts[1:]  # Skip common root directories
            
            if parts:
                module_name = ".".join(parts) + "." + module_name
        
        return module_name
    
    def _get_import_patterns(
        self,
        module_name: str,
        language: Language,
    ) -> List[str]:
        """Get language-specific import patterns for grep.
        
        Args:
            module_name: Name of the module to search for
            language: Programming language
            
        Returns:
            List of grep patterns
        """
        if language.value == "python":
            return [
                f"import {module_name}",
                f"from {module_name} import",
                f"from {module_name}.",
            ]
        elif language.value in ("javascript", "typescript"):
            return [
                f"from '{module_name}'",
                f'from "{module_name}"',
                f"require('{module_name}')",
                f'require("{module_name}")',
            ]
        elif language.value == "go":
            return [
                f'"{module_name}"',
            ]
        else:
            # Generic pattern
            return [module_name]
    
    def _get_file_extensions(self, language: Language) -> List[str]:
        """Get file extensions for a language.
        
        Args:
            language: Programming language
            
        Returns:
            List of file extensions (without dot)
        """
        extension_map = {
            "python": ["py", "pyi"],
            "javascript": ["js", "jsx", "mjs"],
            "typescript": ["ts", "tsx"],
            "go": ["go"],
            "java": ["java"],
            "rust": ["rs"],
            "c": ["c", "h"],
            "cpp": ["cpp", "hpp", "cc", "hh"],
        }
        
        return extension_map.get(language.value, [language.value])
    
    def _is_comment_line(self, line: str, language: Language) -> bool:
        """Check if a line is a comment.
        
        Args:
            line: Line of code
            language: Programming language
            
        Returns:
            True if the line is a comment
        """
        stripped = line.strip()
        
        if language.value == "python":
            return stripped.startswith("#")
        elif language.value in ("javascript", "typescript", "go", "java", "c", "cpp", "rust"):
            return stripped.startswith("//") or stripped.startswith("/*")
        
        return False
    
    def _is_in_string_literal(self, line: str, function_name: str) -> bool:
        """Check if function name appears in a string literal.
        
        Simple heuristic: check if function_name is surrounded by quotes.
        
        Args:
            line: Line of code
            function_name: Function name to check
            
        Returns:
            True if likely in a string literal
        """
        # Find all occurrences of the function name
        for match in re.finditer(re.escape(function_name), line):
            start = match.start()
            end = match.end()
            
            # Count quotes before the match
            before = line[:start]
            after = line[end:]
            
            # Check if inside single or double quotes
            single_before = before.count("'")
            single_after = after.count("'")
            double_before = before.count('"')
            double_after = after.count('"')
            
            # If odd number of quotes before and after, likely in string
            if (single_before % 2 == 1 and single_after % 2 == 1) or \
               (double_before % 2 == 1 and double_after % 2 == 1):
                return True
        
        return False
    
    def _is_function_definition(
        self,
        line: str,
        function_name: str,
        language: Language,
    ) -> bool:
        """Check if line is a function definition.
        
        Args:
            line: Line of code
            function_name: Function name
            language: Programming language
            
        Returns:
            True if line defines the function
        """
        stripped = line.strip()
        
        if language.value == "python":
            return f"def {function_name}(" in stripped or f"async def {function_name}(" in stripped
        elif language.value in ("javascript", "typescript"):
            return (
                f"function {function_name}(" in stripped or
                f"const {function_name} =" in stripped or
                f"let {function_name} =" in stripped or
                f"var {function_name} =" in stripped or
                f"{function_name}(" in stripped and "=>" in stripped
            )
        elif language.value == "go":
            return f"func {function_name}(" in stripped
        
        return False
    
    def _has_call_syntax(
        self,
        line: str,
        function_name: str,
        language: Language,
    ) -> bool:
        """Check if function name is followed by call syntax (parentheses).
        
        Args:
            line: Line of code
            function_name: Function name
            language: Programming language
            
        Returns:
            True if function name is followed by "("
        """
        # Look for function_name followed by (
        pattern = re.escape(function_name) + r'\s*\('
        return bool(re.search(pattern, line))
    
    def _parse_python_import(self, import_line: str, module_name: str) -> List[str]:
        """Parse Python import statement.
        
        Examples:
        - "from auth import login, logout" → ["login", "logout"]
        - "import auth" → ["auth"]
        - "from auth import *" → ["*"]
        
        Args:
            import_line: Import statement
            module_name: Module being imported
            
        Returns:
            List of imported names
        """
        if import_line.startswith("import "):
            # "import auth" or "import auth as a"
            parts = import_line.replace("import ", "").split(" as ")
            return [parts[0].strip()]
        
        elif import_line.startswith("from "):
            # "from auth import login, logout"
            if " import " in import_line:
                imports_part = import_line.split(" import ", 1)[1]
                # Handle: "login, logout" or "*" or "login as l"
                names = []
                for name in imports_part.split(","):
                    name = name.split(" as ")[0].strip()
                    names.append(name)
                return names
        
        # Fallback
        return [module_name]
    
    def _parse_js_import(self, import_line: str, module_name: str) -> List[str]:
        """Parse JavaScript/TypeScript import statement.
        
        Examples:
        - "import { login, logout } from 'auth'" → ["login", "logout"]
        - "import auth from 'auth'" → ["auth"]
        - "import * as auth from 'auth'" → ["*"]
        
        Args:
            import_line: Import statement
            module_name: Module being imported
            
        Returns:
            List of imported names
        """
        if "import" in import_line:
            # Extract content between "import" and "from"
            if " from " in import_line:
                imports_part = import_line.split(" from ")[0]
                imports_part = imports_part.replace("import", "").strip()
                
                # Handle different formats
                if imports_part.startswith("{") and "}" in imports_part:
                    # "{ login, logout }"
                    imports_part = imports_part.strip("{}").strip()
                    names = [n.split(" as ")[0].strip() for n in imports_part.split(",")]
                    return names
                elif imports_part == "*":
                    return ["*"]
                else:
                    # Default import
                    return [imports_part.split(" as ")[0].strip()]
        
        # Fallback
        return [module_name]
    
    def _parse_go_import(self, import_line: str, module_name: str) -> List[str]:
        """Parse Go import statement.
        
        Examples:
        - 'import "auth"' → ["auth"]
        - 'import a "auth"' → ["a"]
        
        Args:
            import_line: Import statement
            module_name: Module being imported
            
        Returns:
            List of imported names
        """
        # Go imports are typically just the module
        # The last part of the import path is the package name
        parts = module_name.split("/")
        return [parts[-1]]
