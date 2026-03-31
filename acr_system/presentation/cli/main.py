"""CLI for ACR System."""
import asyncio
import os
from typing import Optional
from urllib.parse import urlparse

import click
from dotenv import load_dotenv

from acr_system.application.dto.dto import PRReviewRequest, ReviewPublishRequest
from acr_system.application.dto.dto import PRHistoryIndexRequest
from acr_system.application.use_cases.index_pr_history import IndexPRHistoryUseCase
from acr_system.application.use_cases.evaluate_pull_request import (
    EvaluatePullRequestUseCase,
    EvaluationRequest,
)
from acr_system.application.use_cases.process_pull_request import ProcessPullRequestUseCase
from acr_system.application.use_cases.publish_review import PublishReviewUseCase
from acr_system.ast.tree_sitter_adapter import TreeSitterAdapter
from acr_system.domain.services.services import ContextBuilder, ReviewOrchestrator
from acr_system.infrastructure.auth.github_jwt import GitHubAppAuth
from acr_system.infrastructure.ci.github_checks_adapter import GitHubChecksAdapter
from acr_system.infrastructure.ci.gitlab_ci_adapter import GitLabCIAdapter
from acr_system.infrastructure.config.yaml_config_loader import YAMLConfigLoader
from acr_system.infrastructure.config.file_yaml_config_loader import FileYAMLConfigLoader
from acr_system.infrastructure.llm.llm_factory import LLMProviderFactory
from acr_system.infrastructure.rag.faiss_store import FAISSStore
from acr_system.infrastructure.vcs import GitHubAdapter, GitLabAdapter
from acr_system.shared.logging.logger import configure_logging, get_logger
from acr_system.shared.utils.token_counter import UsageStats
from acr_system.experimental.reporting import write_json_report

# Load environment variables
load_dotenv()

logger = get_logger(__name__)


@click.group()
@click.option("--log-level", default="INFO", help="Log level (DEBUG, INFO, WARNING, ERROR)")
def cli(log_level: str) -> None:
    """ACR - Automated Code Review System."""
    configure_logging(log_level)


@cli.command()
@click.option("--pr-url", required=True, help="Pull request URL (e.g., https://github.com/owner/repo/pull/123)")
@click.option("--publish/--no-publish", default=False, help="Publish comments to PR")
def review(
    pr_url: str,
    publish: bool
) -> None:
    """Review a pull request."""
    asyncio.run(_review_async(pr_url, publish))


@cli.command("index-history")
@click.option("--repo", required=True, help="Repository (e.g., owner/repo or https://github.com/owner/repo)")
@click.option("--max-prs", default=50, show_default=True, type=int, help="Max merged PRs to index")
@click.option(
    "--provider",
    type=click.Choice(["github", "gitlab"], case_sensitive=False),
    default=None,
    show_default=False,
    help="Optional provider override; otherwise inferred from --repo when it's a URL",
)
def index_history(repo: str, max_prs: int, provider: Optional[str]) -> None:
    """Index historical merged PR changes (diff + comments) for a repository."""
    chosen_provider = provider.lower() if provider else _infer_provider_from_repo_arg(repo)
    asyncio.run(_index_history_async(repo, max_prs, chosen_provider))


@cli.command("evaluate")
@click.option("--pr-url", required=True, help="PR/MR URL (GitHub/GitLab)")
@click.option("--config-path", required=True, type=click.Path(exists=True, dir_okay=False), help="Path to YAML config file")
@click.option("--report-path", default="./acr_eval_report.json", show_default=True, help="Where to write JSON report")
@click.option("--history-window-days", default=365, show_default=True, type=int, help="Index only PRs up to N days older than target")
@click.option("--max-history-prs", default=200, show_default=True, type=int, help="Max merged PRs to consider for history indexing")
def evaluate(pr_url: str, config_path: str, report_path: str, history_window_days: int, max_history_prs: int) -> None:
    """Experimental evaluation: index PR history, run review, write report."""
    asyncio.run(_evaluate_async(pr_url, config_path, report_path, history_window_days, max_history_prs))


async def _review_async(
    pr_url: str,
    publish: bool
) -> None:
    """Async implementation of review command."""
    try:
        # Parse PR/MR URL
        repo, pr_number, provider = _parse_pr_url(pr_url)
        click.echo(f"Reviewing PR #{pr_number} in {repo}")

        vcs_adapter, ci_analyzer = _create_adapters(provider)
        
        # Initialize LLM provider factory
        # Note: --provider and --model flags are deprecated, use .acr-config.yml instead
        llm_factory = LLMProviderFactory(
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        )
        
        # Initialize RAG store
        embedding_model = os.getenv("RAG_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
        rag_storage_path = os.getenv("RAG_FAISS_INDEX_PATH", "./faiss_index")
        rag_store = FAISSStore(
            embedding_model_name=embedding_model,
            storage_path=rag_storage_path,
        )
        
        # Initialize config loader
        config_loader = YAMLConfigLoader(vcs_repository=vcs_adapter)
        
        # Initialize AST parser
        ast_parser = TreeSitterAdapter()
        
        # Create domain services
        context_builder = ContextBuilder(
            embedding_store=rag_store,
            vcs_repository=vcs_adapter,
        )
        
        review_orchestrator = ReviewOrchestrator(
            llm_factory=llm_factory,
            context_builder=context_builder,
            vcs_repository=vcs_adapter,
            ast_parser=ast_parser,
            static_analyzer=ci_analyzer,
        )
        
        # Create use case
        process_pr = ProcessPullRequestUseCase(
            vcs_repository=vcs_adapter,
            embedding_store=rag_store,
            config_repository=config_loader,
            context_builder=context_builder,
            review_orchestrator=review_orchestrator,
        )
        
        # Execute review
        click.echo("Analyzing pull request...")
        request = PRReviewRequest(repository=repo, pr_number=pr_number)
        result = await process_pr.execute(request)
        
        if not result.success:
            click.echo(f"Error: {result.error_message}", err=True)
            return
        
        # Display results
        click.echo(f"\n✓ Review completed!")
        click.echo(f"  Total comments: {result.comment_count}")
        click.echo(f"  Errors: {result.error_count}")
        click.echo(f"  Warnings: {result.warning_count}")
        click.echo(f"  Info: {result.info_count}")
        
        if result.comments:
            click.echo("\nComments:")
            for comment in result.comments[:10]:  # Show first 10
                severity_color = {
                    "error": "red",
                    "warning": "yellow",
                    "info": "blue",
                }
                line_info = f"L{comment.line_number}" if comment.line_number else "general"
                click.echo(
                    f"  [{click.style(comment.severity.level, fg=severity_color.get(comment.severity.level))}] "
                    f"{comment.file_path} ({line_info}): {comment.message[:80]}..."
                )
        
        # Publish if requested
        if publish:
            click.echo("\nPublishing comments to PR...")
            publish_use_case = PublishReviewUseCase(vcs_repository=vcs_adapter)
            publish_request = ReviewPublishRequest(
                repository=repo,
                pr_number=pr_number,
                comments=result.comments,
            )
            success = await publish_use_case.execute(publish_request)
            
            if success:
                click.echo("✓ Comments published successfully!")
            else:
                click.echo("✗ Error publishing comments", err=True)
        
        # Cleanup
        await vcs_adapter.close()
        await ci_analyzer.close()
        
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        logger.error(f"Review failed: {e}", exc_info=True)


def _parse_pr_url(url: str) -> tuple[str, int, str]:
    """Parse PR/MR URL into (repo, pr_number, provider)."""
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    path_parts = [p for p in (parsed.path or "").strip("/").split("/") if p]

    if host.endswith("github.com"):
        # Example: https://github.com/owner/repo/pull/123
        try:
            pull_idx = path_parts.index("pull")
            owner = path_parts[pull_idx - 2]
            repo_name = path_parts[pull_idx - 1]
            pr_number = int(path_parts[pull_idx + 1])
            return f"{owner}/{repo_name}", pr_number, "github"
        except (ValueError, IndexError):
            raise ValueError(f"Invalid GitHub PR URL: {url}")

    if "gitlab" in host:
        # Example: https://gitlab.com/group/project/-/merge_requests/123
        try:
            mr_idx = path_parts.index("merge_requests")
            pr_number = int(path_parts[mr_idx + 1])

            repo_parts = path_parts[:mr_idx]
            if repo_parts and repo_parts[-1] == "-":
                repo_parts = repo_parts[:-1]
            if not repo_parts:
                raise ValueError("Missing repo path")

            return "/".join(repo_parts), pr_number, "gitlab"
        except (ValueError, IndexError):
            raise ValueError(f"Invalid GitLab MR URL: {url}")

    raise ValueError(f"Unsupported VCS URL: {url}")


def _infer_provider_from_repo_arg(repo: str) -> str:
    """Infer VCS provider from repo argument.

    - If repo is a URL: detect provider from host.
    - If repo is a slug (owner/repo or group/project): default to github.
    """
    value = (repo or "").strip()
    if not value:
        raise ValueError("Empty repo")

    if value.startswith("http://") or value.startswith("https://"):
        parsed = urlparse(value)
        host = (parsed.netloc or "").lower()
        if host.endswith("github.com"):
            return "github"
        if "gitlab" in host:
            return "gitlab"
        raise ValueError(f"Unsupported repo URL host: {host}")

    return "github"


async def _index_history_async(repo: str, max_prs: int, provider: str) -> None:
    try:
        canonical_repo = _parse_repo_arg(repo, provider)
        click.echo(f"Indexing merged PR history for {canonical_repo} (max {max_prs})")

        vcs_adapter, _ = _create_adapters(provider)

        embedding_model = os.getenv("RAG_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
        rag_storage_path = os.getenv("RAG_FAISS_INDEX_PATH", "./faiss_index")
        rag_store = FAISSStore(
            embedding_model_name=embedding_model,
            storage_path=rag_storage_path,
        )

        use_case = IndexPRHistoryUseCase(
            vcs_repository=vcs_adapter,
            embedding_store=rag_store,
        )

        result = await use_case.execute(
            PRHistoryIndexRequest(repository=canonical_repo, max_prs=max_prs)
        )

        if not result.success:
            click.echo(f"✗ Indexing failed: {result.error_message}", err=True)
            return

        click.echo(f"✓ Indexed: {result.indexed_count}, skipped: {result.skipped_count}")
        click.echo(f"Stored in: {rag_storage_path}")

        await vcs_adapter.close()
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        logger.error(f"Index history failed: {e}", exc_info=True)


def _parse_repo_arg(repo: str, provider: str) -> str:
    """Accept repo as either canonical path (owner/repo) or full URL.

    Examples:
    - github: https://github.com/owner/repo -> owner/repo
    - gitlab: https://gitlab.com/group/project -> group/project
    """
    value = (repo or "").strip()
    if not value:
        raise ValueError("Empty repo")

    if value.startswith("http://") or value.startswith("https://"):
        parsed = urlparse(value)
        path_parts = [p for p in (parsed.path or "").strip("/").split("/") if p]

        if path_parts and path_parts[-1].endswith(".git"):
            path_parts[-1] = path_parts[-1][:-4]

        if provider == "github":
            # https://github.com/owner/repo
            if len(path_parts) < 2:
                raise ValueError(f"Invalid GitHub repo URL: {value}")
            return f"{path_parts[0]}/{path_parts[1]}"

        if provider == "gitlab":
            # https://gitlab.com/group/project (can be nested groups)
            if not path_parts:
                raise ValueError(f"Invalid GitLab repo URL: {value}")
            # drop possible '/-/' segment if present
            if "-" in path_parts:
                dash = path_parts.index("-")
                path_parts = path_parts[:dash]
            return "/".join(path_parts)

        raise ValueError(f"Unsupported provider: {provider}")

    # Already in canonical form
    return value


def _create_adapters(provider: str) -> tuple[GitHubAdapter | GitLabAdapter, GitHubChecksAdapter | GitLabCIAdapter]:
    """Create VCS + CI adapters based on provider."""
    if provider == "github":
        app_id = os.getenv("GITHUB_APP_ID")
        private_key_path = os.getenv("GITHUB_APP_PRIVATE_KEY_PATH")
        installation_id = os.getenv("GITHUB_APP_INSTALLATION_ID")

        if not app_id or not private_key_path:
            raise ValueError("GITHUB_APP_ID and GITHUB_APP_PRIVATE_KEY_PATH must be set")

        auth = GitHubAppAuth(
            app_id=app_id,
            private_key_path=private_key_path,
            installation_id=installation_id,
        )

        return GitHubAdapter(auth=auth), GitHubChecksAdapter(auth=auth)

    if provider == "gitlab":
        token = os.getenv("GITLAB_TOKEN")
        api_base = os.getenv("GITLAB_API_BASE", "https://gitlab.com/api/v4")
        if not token:
            raise ValueError("GITLAB_TOKEN must be set")

        return GitLabAdapter(token=token, api_base=api_base), GitLabCIAdapter(token=token, api_base=api_base)

    raise ValueError(f"Unsupported provider: {provider}")


async def _evaluate_async(
    pr_url: str,
    config_path: str,
    report_path: str,
    history_window_days: int,
    max_history_prs: int,
) -> None:
    try:
        repo, pr_number, provider = _parse_pr_url(pr_url)
        click.echo(f"Evaluating historical PR #{pr_number} in {repo} ({provider})")

        # Experimental evaluation intentionally skips CI fetching to keep metrics focused
        # on RAG/indexing + LLM review quality/cost.
        if provider == "github":
            gh_token = os.getenv("GITHUB_TOKEN")
            if gh_token:
                vcs_adapter = GitHubAdapter(token=gh_token)
            else:
                app_id = os.getenv("GITHUB_APP_ID")
                private_key_path = os.getenv("GITHUB_APP_PRIVATE_KEY_PATH")
                installation_id = os.getenv("GITHUB_APP_INSTALLATION_ID")
                if not app_id or not private_key_path:
                    raise ValueError(
                        "For GitHub evaluation set either GITHUB_TOKEN or (GITHUB_APP_ID and GITHUB_APP_PRIVATE_KEY_PATH)"
                    )
                auth = GitHubAppAuth(
                    app_id=app_id,
                    private_key_path=private_key_path,
                    installation_id=installation_id,
                )
                vcs_adapter = GitHubAdapter(auth=auth)
        elif provider == "gitlab":
            token = os.getenv("GITLAB_TOKEN")
            api_base = os.getenv("GITLAB_API_BASE", "https://gitlab.com/api/v4")
            if not token:
                raise ValueError("GITLAB_TOKEN must be set")
            vcs_adapter = GitLabAdapter(token=token, api_base=api_base)
        else:
            raise ValueError(f"Unsupported provider: {provider}")

        # Local config override
        config_loader = FileYAMLConfigLoader(config_path=config_path)

        # RAG store (persistent)
        embedding_model = os.getenv("RAG_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
        rag_storage_path = os.getenv("RAG_FAISS_INDEX_PATH", "./faiss_index")
        rag_store = FAISSStore(
            embedding_model_name=embedding_model,
            storage_path=rag_storage_path,
        )

        # Usage accounting
        llm_usage = UsageStats()

        llm_factory = LLMProviderFactory(
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
            usage_stats=llm_usage,
        )

        ast_parser = TreeSitterAdapter()
        context_builder = ContextBuilder(
            embedding_store=rag_store,
            vcs_repository=vcs_adapter,
        )
        review_orchestrator = ReviewOrchestrator(
            llm_factory=llm_factory,
            context_builder=context_builder,
            vcs_repository=vcs_adapter,
            ast_parser=ast_parser,
            static_analyzer=None,
        )

        process_pr = ProcessPullRequestUseCase(
            vcs_repository=vcs_adapter,
            embedding_store=rag_store,
            config_repository=config_loader,
            context_builder=context_builder,
            review_orchestrator=review_orchestrator,
        )

        evaluator = EvaluatePullRequestUseCase(
            vcs_repository=vcs_adapter,
            embedding_store=rag_store,
            process_pr_use_case=process_pr,
            llm_usage_stats=llm_usage,
        )

        result = await evaluator.execute(
            EvaluationRequest(
                repository=repo,
                pr_number=pr_number,
                history_window_days=history_window_days,
                max_history_prs=max_history_prs,
            )
        )

        write_json_report(report_path, result)
        click.echo(f"✓ Report written to: {report_path}")

        await vcs_adapter.close()

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        logger.error(f"Evaluate failed: {e}", exc_info=True)


@cli.command()
def version() -> None:
    """Show version information."""
    click.echo("ACR System v0.1.0")


if __name__ == "__main__":
    cli()
