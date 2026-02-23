"""FastAPI application for ACR System."""
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from dotenv import load_dotenv
from fastapi import FastAPI

from acr_system.presentation.api.webhook_handlers import router as webhook_router
from acr_system.shared.logging.logger import configure_logging

# Load environment variables
load_dotenv()

# Configure logging
log_level = os.getenv("ACR_LOG_LEVEL", "INFO")
configure_logging(log_level)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan events."""
    # Startup
    print("ACR System starting up...")
    yield
    # Shutdown
    print("ACR System shutting down...")


# Create FastAPI app
app = FastAPI(
    title="ACR System",
    description="Automated Code Review System using LLM and RAG",
    version="0.1.0",
    lifespan=lifespan,
)

# Include routers
app.include_router(webhook_router, prefix="/webhooks", tags=["webhooks"])


@app.get("/")
async def root() -> dict:
    """Root endpoint."""
    return {
        "service": "ACR System",
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "acr-system",
    }


if __name__ == "__main__":
    import uvicorn
    
    host = os.getenv("ACR_API_HOST", "0.0.0.0")
    port = int(os.getenv("ACR_API_PORT", "8000"))
    
    uvicorn.run(
        "acr_system.presentation.api.main:app",
        host=host,
        port=port,
        reload=True,
    )
