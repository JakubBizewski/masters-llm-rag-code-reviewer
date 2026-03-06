"""CLI for ACR System."""
import asyncio
import os
from typing import Optional

import click
from dotenv import load_dotenv

from acr_system.application.dto.dto import PRReviewRequest, ReviewPublishRequest
from acr_system.application.use_cases.process_pull_request import ProcessPullRequestUseCase
from acr_system.application.use_cases.publish_review import PublishReviewUseCase
from acr_system.ast.tree_sitter_adapter import TreeSitterAdapter
from acr_system.domain.services.services import ContextBuilder, ReviewOrchestrator
from acr_system.infrastructure.auth.github_jwt import GitHubAppAuth
from acr_system.infrastructure.ci.github_checks_adapter import GitHubChecksAdapter
from acr_system.infrastructure.config.yaml_config_loader import YAMLConfigLoader
from acr_system.infrastructure.llm.anthropic_adapter import AnthropicAdapter
from acr_system.infrastructure.llm.openai_adapter import OpenAIAdapter
from acr_system.infrastructure.rag.faiss_store import FAISSStore
from acr_system.infrastructure.vcs.github_adapter import GitHubAdapter
from acr_system.shared.logging.logger import configure_logging, get_logger

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
@click.option("--config", help="Path to .acr-config.yml (optional, will fetch from repo)")
@click.option("--publish/--no-publish", default=False, help="Publish comments to PR")
@click.option("--provider", default="openai", help="LLM provider (openai, anthropic)")
@click.option("--model", help="LLM model to use")
def review(
    pr_url: str,
    config: Optional[str],
    publish: bool,
    provider: str,
    model: Optional[str],
) -> None:
    """Review a pull request."""
    asyncio.run(_review_async(pr_url, config, publish, provider, model))


async def _review_async(
    pr_url: str,
    config_path: Optional[str],
    publish: bool,
    provider: str,
    model: Optional[str],
) -> None:
    """Async implementation of review command."""
    try:
        # Parse PR URL
        repo, pr_number = _parse_pr_url(pr_url)
        click.echo(f"Reviewing PR #{pr_number} in {repo}")
        
        # Initialize GitHub App authentication
        app_id = os.getenv("GITHUB_APP_ID")
        private_key_path = os.getenv("GITHUB_APP_PRIVATE_KEY_PATH")
        installation_id = os.getenv("GITHUB_APP_INSTALLATION_ID")
        
        if not app_id or not private_key_path:
            click.echo("Error: GITHUB_APP_ID and GITHUB_APP_PRIVATE_KEY_PATH must be set", err=True)
            return
        
        auth = GitHubAppAuth(
            app_id=app_id,
            private_key_path=private_key_path,
            installation_id=installation_id,
        )
        vcs_adapter = GitHubAdapter(auth=auth)
        
        # Initialize LLM provider
        if provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                click.echo("Error: OPENAI_API_KEY not set in environment", err=True)
                return
            
            llm_model = model or os.getenv("DEFAULT_LLM_MODEL", "gpt-4o")
            llm_adapter = OpenAIAdapter(api_key=api_key, model=llm_model)
        elif provider == "anthropic":
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                click.echo("Error: ANTHROPIC_API_KEY not set in environment", err=True)
                return
            
            llm_model = model or os.getenv("DEFAULT_LLM_MODEL", "claude-3-5-sonnet-20241022")
            llm_adapter = AnthropicAdapter(api_key=api_key, model=llm_model)
        else:
            click.echo(f"Error: Provider '{provider}' not supported. Use 'openai' or 'anthropic'", err=True)
            return
        
        # Initialize RAG store
        embedding_model = os.getenv("RAG_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
        rag_store = FAISSStore(embedding_model_name=embedding_model)
        
        # Initialize config loader
        config_loader = YAMLConfigLoader(vcs_repository=vcs_adapter)
        
        # Initialize CI analyzer
        ci_analyzer = GitHubChecksAdapter(auth=auth)
        
        # Initialize AST parser
        ast_parser = TreeSitterAdapter()
        
        # Create domain services
        context_builder = ContextBuilder(
            embedding_store=rag_store,
            vcs_repository=vcs_adapter,
        )
        
        review_orchestrator = ReviewOrchestrator(
            llm_provider=llm_adapter,
            context_builder=context_builder,
            vcs_repository=vcs_adapter,
            ast_parser=ast_parser,
            static_analyzer=ci_analyzer,
        )
        
        # Create use case
        process_pr = ProcessPullRequestUseCase(
            vcs_repository=vcs_adapter,
            llm_provider=llm_adapter,
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


def _parse_pr_url(url: str) -> tuple[str, int]:
    """Parse GitHub PR URL into (repo, pr_number)."""
    # Example: https://github.com/owner/repo/pull/123
    parts = url.rstrip('/').split('/')
    
    if 'github.com' in url:
        # Find 'pull' index
        try:
            pull_idx = parts.index('pull')
            owner = parts[pull_idx - 2]
            repo_name = parts[pull_idx - 1]
            pr_number = int(parts[pull_idx + 1])
            
            return f"{owner}/{repo_name}", pr_number
        except (ValueError, IndexError):
            raise ValueError(f"Invalid GitHub PR URL: {url}")
    
    raise ValueError(f"Unsupported VCS URL: {url}")


@cli.command()
def version() -> None:
    """Show version information."""
    click.echo("ACR System v0.1.0")


if __name__ == "__main__":
    cli()
