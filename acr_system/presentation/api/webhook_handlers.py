"""Webhook handlers for VCS (GitHub/GitLab)."""
import os
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from acr_system.application.dto.dto import PRReviewRequest, ReviewPublishRequest
from acr_system.application.use_cases.process_pull_request import ProcessPullRequestUseCase
from acr_system.application.use_cases.publish_review import PublishReviewUseCase
from acr_system.ast.tree_sitter_adapter import TreeSitterAdapter
from acr_system.domain.services.services import ContextBuilder, ReviewOrchestrator
from acr_system.infrastructure.auth.github_jwt import GitHubAppAuth
from acr_system.infrastructure.ci.github_checks_adapter import GitHubChecksAdapter
from acr_system.infrastructure.config.yaml_config_loader import YAMLConfigLoader
from acr_system.infrastructure.llm.openai_adapter import OpenAIAdapter
from acr_system.infrastructure.rag.faiss_store import FAISSStore
from acr_system.infrastructure.vcs.github_adapter import GitHubAdapter
from acr_system.shared.logging.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


async def process_pr_review_task(repo: str, pr_number: int) -> None:
    """Background task to process PR review."""
    try:
        logger.info(f"Starting background review for PR #{pr_number} in {repo}")
        
        # Initialize services
        app_id = os.getenv("GITHUB_APP_ID")
        private_key_path = os.getenv("GITHUB_APP_PRIVATE_KEY_PATH")
        installation_id = os.getenv("GITHUB_APP_INSTALLATION_ID")
        openai_key = os.getenv("OPENAI_API_KEY")
        
        if not app_id or not private_key_path or not openai_key:
            logger.error("Missing required API keys/credentials")
            return
        
        auth = GitHubAppAuth(
            app_id=app_id,
            private_key_path=private_key_path,
            installation_id=installation_id,
        )
        vcs_adapter = GitHubAdapter(auth=auth)
        llm_adapter = OpenAIAdapter(
            api_key=openai_key,
            model=os.getenv("DEFAULT_LLM_MODEL", "gpt-4o")
        )
        rag_store = FAISSStore(
            embedding_model_name=os.getenv(
                "RAG_EMBEDDING_MODEL",
                "sentence-transformers/all-MiniLM-L6-v2"
            )
        )
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
        
        # Process review
        process_pr = ProcessPullRequestUseCase(
            vcs_repository=vcs_adapter,
            llm_provider=llm_adapter,
            embedding_store=rag_store,
            config_repository=config_loader,
            context_builder=context_builder,
            review_orchestrator=review_orchestrator,
        )
        
        request = PRReviewRequest(repository=repo, pr_number=pr_number)
        result = await process_pr.execute(request)
        
        if not result.success:
            logger.error(f"Review failed: {result.error_message}")
            return
        
        logger.info(f"Review completed with {result.comment_count} comments")
        
        # Publish comments
        publish_use_case = PublishReviewUseCase(vcs_repository=vcs_adapter)
        publish_request = ReviewPublishRequest(
            repository=repo,
            pr_number=pr_number,
            comments=result.comments,
        )
        
        success = await publish_use_case.execute(publish_request)
        
        if success:
            logger.info(f"Comments published successfully for PR #{pr_number}")
        else:
            logger.error(f"Failed to publish comments for PR #{pr_number}")
        
        # Cleanup
        await vcs_adapter.close()
        await ci_analyzer.close()
        
    except Exception as e:
        logger.error(f"Error in background review task: {e}", exc_info=True)


@router.post("/github")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    """Handle GitHub webhook events."""
    try:
        payload = await request.json()
        event_type = request.headers.get("X-GitHub-Event")
        
        logger.info(f"Received GitHub webhook: {event_type}")
        
        # Handle pull request events
        if event_type == "pull_request":
            action = payload.get("action")
            
            # Trigger review on opened or synchronized (new commits)
            if action in ["opened", "synchronize"]:
                pr_data = payload["pull_request"]
                pr_number = pr_data["number"]
                repo = payload["repository"]["full_name"]
                
                logger.info(f"Triggering review for PR #{pr_number} in {repo}")
                
                # Schedule background task
                background_tasks.add_task(
                    process_pr_review_task,
                    repo=repo,
                    pr_number=pr_number,
                )
                
                return {"status": "review_scheduled", "pr": pr_number}
        
        return {"status": "ignored", "event": event_type}
        
    except Exception as e:
        logger.error(f"Error handling GitHub webhook: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/gitlab")
async def gitlab_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    """Handle GitLab webhook events."""
    try:
        payload = await request.json()
        event_type = payload.get("object_kind")
        
        logger.info(f"Received GitLab webhook: {event_type}")
        
        # Handle merge request events
        if event_type == "merge_request":
            action = payload["object_attributes"]["action"]
            
            if action in ["open", "update"]:
                mr_data = payload["object_attributes"]
                mr_iid = mr_data["iid"]
                project = payload["project"]["path_with_namespace"]
                
                logger.info(f"Triggering review for MR !{mr_iid} in {project}")
                
                # Schedule background task (similar to GitHub)
                # Note: GitLab adapter not implemented yet
                
                return {"status": "review_scheduled", "mr": mr_iid}
        
        return {"status": "ignored", "event": event_type}
        
    except Exception as e:
        logger.error(f"Error handling GitLab webhook: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/test")
async def test_webhook() -> dict[str, str]:
    """Test endpoint for webhooks."""
    return {"status": "ok", "message": "Webhook endpoint is working"}
