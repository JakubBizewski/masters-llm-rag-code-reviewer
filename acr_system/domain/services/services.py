"""Domain services for orchestrating code review."""
import asyncio
import os
from typing import List, Optional

from acr_system.ast.parser import ASTParser
from acr_system.domain.entities.entities import (
    CodeContext,
    DiffHunk,
    FunctionNode,
    ParsedCIIssue,
    PullRequest,
    ReviewComment,
)
from acr_system.domain.interfaces.ports import (
    CallGraphAnalyzer,
    EmbeddingStore,
    ImpactAnalyzer,
    LLMProvider,
    StaticAnalyzer,
    VCSRepository,
)
from acr_system.domain.value_objects.value_objects import (
    CommentSource,
    LLMConfig,
    RAGConfig,
    Severity,
)
from acr_system.shared.logging.logger import get_logger


logger = get_logger(__name__)

class ContextBuilder:
    """Service for building context for LLM from RAG and other sources."""
    
    def __init__(
        self,
        embedding_store: EmbeddingStore,
        vcs_repository: VCSRepository,
    ):
        self.embedding_store = embedding_store
        self.vcs_repository = vcs_repository
        # Bigger default context window to reduce missing nearby signals.
        self.surrounding_lines = max(10, int(os.getenv("RAG_SURROUNDING_LINES", "200")))
    
    async def build_context(
        self,
        diff_hunk: DiffHunk,
        pr: PullRequest,
        rag_config: Optional[RAGConfig] = None,
    ) -> List[CodeContext]:
        """Build context for a diff hunk.
        
        Context includes:
        - RAG retrieval from documentation
        - Surrounding code context
        - Previous review history
        """
        context: List[CodeContext] = []
        
        # RAG retrieval if enabled
        if rag_config and rag_config.enabled:
            query = self._build_rag_query(diff_hunk)
            rag_results = await self.embedding_store.search_similar(
                query=query,
                top_k=rag_config.top_k,
                min_relevance=rag_config.min_relevance,
                max_per_source=rag_config.max_chunks_per_source,
            )

            # Also retrieve similar historical PR changes (diff + discussion)
            history_results = await self.embedding_store.search_similar(
                query=query,
                top_k=min(2, rag_config.top_k),
                filters={
                    "source": "pr_history",
                    "repo": pr.repository,
                    "exclude_pr_number": str(pr.pr_number),
                },
                min_relevance=rag_config.min_relevance,
                max_per_source=rag_config.max_chunks_per_source,
            )

            # Documentation gets its own retrieval call. Without it, project
            # convention docs are hopelessly outnumbered in the index by historical
            # PR threads and effectively never surface, which is exactly what the
            # first evaluation batch showed: zero documentation chunks retrieved
            # across 1070 hits.
            doc_results = await self.embedding_store.search_similar(
                query=query,
                top_k=min(2, rag_config.top_k),
                filters={"source": "documentation"},
                min_relevance=rag_config.min_relevance,
            )

            # Merge, drop duplicates, rerank on relevance + lexical overlap with the
            # hunk, then keep only the strongest top_k. If nothing survives, no RAG
            # context is injected at all: an empty context is strictly better than a
            # loosely-related one, and makes the prompt identical to a no-RAG run.
            retrieved: List[CodeContext] = []
            seen_contents: set[str] = set()
            for item in list(doc_results) + list(rag_results) + list(history_results):
                if item.content in seen_contents:
                    continue
                seen_contents.add(item.content)
                retrieved.append(item)

            selected = self._rerank_contexts(retrieved, query, rag_config)
            if selected:
                context.extend(selected)
            else:
                logger.info(
                    f"No retrieved context cleared the relevance floor "
                    f"({rag_config.min_relevance:.2f}) for "
                    f"{diff_hunk.file_path.value}; reviewing without RAG context"
                )
        
        # Add surrounding code context
        surrounding_context = await self._get_surrounding_context(diff_hunk, pr)
        if surrounding_context:
            context.append(surrounding_context)

        logger.info(f"Built context with {len(context)} items for hunk in {diff_hunk.file_path.value}")
        for c in context:
            logger.info(f"Context item from {c.source} with relevance {c.relevance_score:.2f}: {c.content}...\n\n")
        
        return context
    
    # Ranking bonus applied to documentation chunks during reranking.
    DOCUMENTATION_RANK_BONUS = 0.05
    # Number of changed lines fed into the retrieval query. Ten was too few to
    # characterise a hunk: for many hunks the query was a single import line, which
    # matches essentially anything in the index.
    QUERY_MAX_CHANGED_LINES = 30
    # Identifiers that carry no discriminative signal in a retrieval query.
    _QUERY_STOP_TOKENS = frozenset({
        "the", "and", "for", "not", "with", "this", "that", "from", "import",
        "return", "const", "let", "var", "def", "class", "self", "true", "false",
        "none", "null", "if", "else", "async", "await", "await_", "function",
    })

    def _build_rag_query(self, diff_hunk: DiffHunk) -> str:
        """Build search query for RAG from diff hunk."""
        # Extract key information from diff for better RAG retrieval
        lines = diff_hunk.content.split('\n')
        
        # Focus on added lines (they contain new code to review), but keep a few
        # removed lines too: what a change replaced is often what makes it findable.
        added_lines = [line[1:] for line in lines if line.startswith('+') and not line.startswith('+++')]
        removed_lines = [line[1:] for line in lines if line.startswith('-') and not line.startswith('---')]

        query = f"File: {diff_hunk.file_path.value}\n"
        query += f"Language: {diff_hunk.language.name}\n"
        query += "Changes:\n" + '\n'.join(added_lines[:self.QUERY_MAX_CHANGED_LINES])
        if removed_lines:
            query += "\nReplaced:\n" + '\n'.join(
                removed_lines[:max(5, self.QUERY_MAX_CHANGED_LINES // 3)]
            )

        # Symbols are what make a hunk identifiable across PRs, so state them
        # explicitly instead of relying on them surviving the mean-pooled embedding.
        symbols = self._extract_identifiers('\n'.join(added_lines + removed_lines))
        if symbols:
            query += "\nSymbols: " + ", ".join(sorted(symbols)[:20])

        return query

    def _extract_identifiers(self, text: str) -> set:
        """Extract discriminative identifiers (function/class/variable names)."""
        import re

        tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text)
        out = set()
        for token in tokens:
            lowered = token.lower()
            if lowered in self._QUERY_STOP_TOKENS:
                continue
            out.add(token)
            # camelCase / snake_case parts retrieve better than the whole symbol
            for part in re.split(r"_|(?<=[a-z0-9])(?=[A-Z])", token):
                if len(part) > 2 and part.lower() not in self._QUERY_STOP_TOKENS:
                    out.add(part)
        return out

    def _lexical_overlap(self, query_identifiers: set, content: str) -> float:
        """Fraction of the hunk's identifiers that also appear in a context chunk.

        Embedding similarity alone cannot tell "same subsystem" from "same general
        topic"; shared identifiers can. Used only to rerank candidates that already
        cleared the relevance floor.
        """
        if not query_identifiers:
            return 0.0
        content_identifiers = self._extract_identifiers(content)
        if not content_identifiers:
            return 0.0
        shared = query_identifiers & content_identifiers
        return len(shared) / len(query_identifiers)

    def _rerank_contexts(
        self,
        contexts: List[CodeContext],
        query: str,
        rag_config: RAGConfig,
    ) -> List[CodeContext]:
        """Rerank retrieved contexts and keep the strongest top_k.

        Score is a blend of the calibrated embedding similarity and the identifier
        overlap with the hunk, so a chunk that merely shares vocabulary with the
        file loses to one that mentions the same symbols.
        """
        if not contexts:
            return []

        query_identifiers = self._extract_identifiers(query)
        weight = rag_config.lexical_weight
        scored = []
        for ctx in contexts:
            lexical = self._lexical_overlap(query_identifiers, ctx.content)
            blended = (1.0 - weight) * ctx.relevance_score + weight * lexical
            # Documentation states project conventions explicitly, which is what
            # human reviewers cite and what a diff-only reviewer cannot know.
            if ctx.source == "documentation":
                blended += self.DOCUMENTATION_RANK_BONUS
            scored.append((blended, lexical, ctx))

        scored.sort(key=lambda item: item[0], reverse=True)
        selected = [ctx for _, _, ctx in scored[: rag_config.top_k]]
        for blended, lexical, ctx in scored[: rag_config.top_k]:
            logger.info(
                f"Selected context from {ctx.source}: similarity="
                f"{ctx.relevance_score:.3f} lexical_overlap={lexical:.3f} "
                f"blended={blended:.3f}"
            )
        return selected
    
    async def _get_surrounding_context(
        self,
        diff_hunk: DiffHunk,
        pr: PullRequest,
    ) -> Optional[CodeContext]:
        """Get surrounding code context for a diff hunk."""
        try:
            # Get full file content from the branch/commit being reviewed.
            # Using target branch can return stale code and mismatched line context.
            ref = pr.head_sha or pr.source_branch
            file_content = await self.vcs_repository.get_file_content(
                repo=pr.repository,
                file_path=diff_hunk.file_path.value,
                ref=ref,
            )
            
            # Extract relevant portion (wider window before and after the hunk)
            lines = file_content.split('\n')
            window = self.surrounding_lines
            start = max(0, diff_hunk.new_start_line - window)
            end = min(
                len(lines),
                diff_hunk.new_start_line + diff_hunk.new_line_count + window,
            )
            
            context_lines = lines[start:end]
            context_content = '\n'.join(context_lines)
            
            return CodeContext(
                content=context_content,
                source="surrounding_code",
                file_path=diff_hunk.file_path,
                relevance_score=1.0,  # High relevance for immediate context
            )
        except Exception:
            # If we can't get context, return None (non-critical)
            return None


class ReviewOrchestrator:
    """Main service for orchestrating code review process."""
    
    def __init__(
        self,
        llm_factory,  # LLMProviderFactory
        context_builder: ContextBuilder,
        vcs_repository: VCSRepository,
        ast_parser: ASTParser,
        static_analyzer: Optional[StaticAnalyzer] = None,
        call_graph_analyzer: Optional[CallGraphAnalyzer] = None,
        impact_analyzer: Optional[ImpactAnalyzer] = None,
    ):
        self.llm_factory = llm_factory
        self.context_builder = context_builder
        self.vcs_repository = vcs_repository
        self.ast_parser = ast_parser
        self.static_analyzer = static_analyzer
        self.call_graph_analyzer = call_graph_analyzer
        self.impact_analyzer = impact_analyzer
    
    async def review_pull_request(
        self,
        pr: PullRequest,
        rules_text: str,
        llm_config: LLMConfig,
        rag_config: Optional[RAGConfig] = None,
    ) -> List[ReviewComment]:
        """Review a pull request and generate comments.
        
        Args:
            pr: Pull request to review
            rules_text: Rules to apply for review
            llm_config: LLM configuration for this review
            rag_config: RAG configuration
            
        Returns:
            List of review comments
        """
        all_comments: List[ReviewComment] = []
        
        # Get LLM provider from factory
        llm_provider = self.llm_factory.create_provider(llm_config)
        
        # Fetch CI results if analyzer available
        ci_issues: List[ParsedCIIssue] = []
        if self.static_analyzer:
            ci_results = await self.static_analyzer.fetch_ci_results(
                repo=pr.repository,
                pr_number=pr.pr_number,
            )
            
            # Parse CI results with LLM
            for ci_result in ci_results:
                parsed = await llm_provider.parse_ci_output(
                    ci_result=ci_result,
                    changed_files=pr.changed_files,
                )
                ci_issues.extend(parsed)
        
        # Review each diff hunk in parallel
        async def review_single_hunk(hunk: DiffHunk) -> List[ReviewComment]:
            """Review a single diff hunk - helper for parallel processing."""
            # Build context for this hunk
            context = await self.context_builder.build_context(
                diff_hunk=hunk,
                pr=pr,
                rag_config=rag_config,
            )
            
            # Filter CI issues relevant to this hunk
            relevant_ci_issues = [
                issue for issue in ci_issues
                if issue.file_path == hunk.file_path.value
                and (issue.line_number is None or hunk.is_line_in_hunk(issue.line_number))
            ]

            logger.info(f"Reviewing hunk in {hunk.file_path.value} with {len(context)} context items and {len(relevant_ci_issues)} relevant CI issues\nBefore: {hunk.context_before}\nAfter: {hunk.context_after}\n\n")
            
            # Generate review comments with LLM
            comments = await llm_provider.generate_review_comments(
                diff_hunk=hunk,
                rules_text=rules_text,
                context=context,
                ci_issues=relevant_ci_issues,
            )
            
            return comments
        
        # Process all hunks in parallel using asyncio.gather
        hunk_review_tasks = [review_single_hunk(hunk) for hunk in pr.diff_hunks]
        hunk_comments_lists = await asyncio.gather(*hunk_review_tasks, return_exceptions=True)
        
        # Flatten results and handle exceptions
        for result in hunk_comments_lists:
            if isinstance(result, Exception):
                # Log exception but continue with other hunks
                # TODO: Add proper logging
                continue
            all_comments.extend(result)
        
        # Step 4b-4d: Impact Analysis (breaking changes detection)
        if self.call_graph_analyzer and self.impact_analyzer:
            impact_comments = await self._perform_impact_analysis(pr)
            all_comments.extend(impact_comments)
        
        return all_comments
    
    async def _extract_changed_functions(
        self,
        diff_hunk: DiffHunk,
        pr: PullRequest,
    ) -> List[FunctionNode]:
        """Extract functions that were changed in a diff hunk.
        
        Args:
            diff_hunk: The diff hunk to analyze
            pr: Pull request context
            
        Returns:
            List of changed functions
        """
        try:
            # Get file content at the PR's head commit, not the current branch tip.
            file_content = await self.vcs_repository.get_file_content(
                repo=pr.repository,
                file_path=diff_hunk.file_path.value,
                ref=pr.head_sha or pr.source_branch,
            )
            
            # Extract changed functions using AST parser
            changed_functions = self.ast_parser.extract_changed_functions(
                diff=diff_hunk,
                code=file_content,
                language=diff_hunk.language,
            )
            
            return changed_functions
        except Exception:
            # If we can't extract functions, return empty list (non-critical)
            return []
    
    async def _perform_impact_analysis(self, pr: PullRequest) -> List[ReviewComment]:
        """Perform impact analysis on changed functions to detect breaking changes.
        
        Args:
            pr: Pull request to analyze
            
        Returns:
            List of warning comments for potential breaking changes
        """
        impact_comments: List[ReviewComment] = []
        
        # Helper function to analyze a single function in parallel
        async def analyze_single_function(func: FunctionNode, hunk: DiffHunk) -> List[ReviewComment]:
            """Analyze impact of a single changed function - helper for parallel processing."""
            try:
                # Step 4b: Find callers of this function
                callers = await self.call_graph_analyzer.find_callers(
                    function_name=func.name,
                    file_path=func.file_path,
                    language=func.language,
                    repository=pr.repository,
                    ref=pr.head_sha or pr.source_branch,
                )
                
                # Skip if no callers found (not used elsewhere)
                if not callers:
                    return []
                
                # Step 4c: Analyze impact with LLM
                impact_result = await self.impact_analyzer.analyze_impact(
                    changed_function=func,
                    diff_hunk=hunk,
                    callers=callers,
                    repository=pr.repository,
                )
                
                # Step 4d: Create warning comments for breaking changes
                comments = []
                if impact_result.breaking_changes:
                    for breaking_change in impact_result.breaking_changes:
                        # Only create comments for medium+ severity
                        if breaking_change.severity.priority >= Severity(level=Severity.WARNING).priority:
                            comment = ReviewComment(
                                file_path=func.file_path,
                                line_number=func.start_line,
                                severity=breaking_change.severity,
                                message=f"⚠️ Potential Breaking Change in `{func.name}()`:\n\n"
                                        f"{breaking_change.issue}\n\n"
                                        f"**Affected callers:** {len(callers)}\n"
                                        f"**Impact:** {impact_result.summary}",
                                suggestion=breaking_change.suggested_fix,
                                rule_name="impact_analysis",
                                source=CommentSource(source=CommentSource.IMPACT_ANALYSIS),
                            )
                            comments.append(comment)
                
                return comments
            
            except Exception:
                # Continue with other functions if one fails
                return []
        
        # Extract changed functions from all diff hunks and collect analysis tasks
        analysis_tasks = []
        for hunk in pr.diff_hunks:
            changed_functions = await self._extract_changed_functions(hunk, pr)
            
            # Create tasks for all functions in this hunk
            for func in changed_functions:
                analysis_tasks.append(analyze_single_function(func, hunk))
        
        # Process all functions in parallel using asyncio.gather
        if analysis_tasks:
            function_comments_lists = await asyncio.gather(*analysis_tasks, return_exceptions=True)
            
            # Flatten results and handle exceptions
            for result in function_comments_lists:
                if isinstance(result, Exception):
                    # Log exception but continue with other functions
                    # TODO: Add proper logging
                    continue
                impact_comments.extend(result)
        
        return impact_comments
    
    async def review_diff_hunk(
        self,
        hunk: DiffHunk,
        pr: PullRequest,
        rules_text: str,
        llm_config: LLMConfig,
        ci_issues: List[ParsedCIIssue],
        rag_config: Optional[RAGConfig] = None,
    ) -> List[ReviewComment]:
        """Review a single diff hunk.
        
        This method allows more granular control over the review process.
        """
        # Get LLM provider from factory
        llm_provider = self.llm_factory.create_provider(llm_config)
        
        # Build context
        context = await self.context_builder.build_context(
            diff_hunk=hunk,
            pr=pr,
            rag_config=rag_config,
        )
        
        # Generate comments
        comments = await llm_provider.generate_review_comments(
            diff_hunk=hunk,
            rules_text=rules_text,
            context=context,
            ci_issues=ci_issues,
        )
        
        return comments
