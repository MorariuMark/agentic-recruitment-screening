"""
backend/main.py
FastAPI application entry point for the Agentic Recruitment Screening system.
Configures CORS, OpenTelemetry / Arize Phoenix instrumentation, and mounts API routers.
"""

from contextlib import asynccontextmanager
import logging
from typing import Any, AsyncGenerator, Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import router as api_router
from backend.config import settings

logger = logging.getLogger("recruitment_screening")
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager: sets up observability on startup, cleans up on shutdown."""
    logger.info("Initializing Agentic Recruitment Screening Backend...")

    # Optional Arize Phoenix OpenTelemetry tracing setup (fast socket check to avoid hanging if offline)
    if settings.phoenix_collector_endpoint:
        try:
            import socket
            from urllib.parse import urlparse

            parsed = urlparse(settings.phoenix_collector_endpoint)
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port or (443 if parsed.scheme == "https" else 6006)
            
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.15)
                result = sock.connect_ex((host, port))
            
            if result != 0:
                logger.info("Arize Phoenix collector unreachable at %s:%d; skipping tracing initialization.", host, port)
            else:
                try:
                    from phoenix.trace.openai import OpenAIInstrumentor
                    OpenAIInstrumentor().instrument()
                    logger.info("Arize Phoenix OpenAI instrumentation initialized.")
                except Exception as trace_err:
                    logger.warning(f"Phoenix instrumentation skipped or failed: {trace_err}")
        except Exception as e:
            logger.warning(f"Phoenix health check failed: {e}")

    yield

    logger.info("Shutting down Agentic Recruitment Screening Backend...")


app = FastAPI(
    title=settings.app_name,
    description="Agentic Recruitment Screening, Semantic Matching & Human-in-the-Loop Validation API",
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows Streamlit frontend and local testing tools
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(api_router)


# ---------------------------------------------------------------------------
# Health & Root Endpoints
# ---------------------------------------------------------------------------
@app.get("/health", tags=["Monitoring"], summary="Health check endpoint")
async def health_check() -> Dict[str, Any]:
    """Basic health check endpoint confirming API availability and inference engine metadata."""
    from backend.api.routes import _get_active_model_for_provider
    from backend.agents.llm_factory import get_last_fallback_event

    return {
        "status": "ok",
        "app_name": settings.app_name,
        "environment": settings.environment,
        "llm_provider": settings.llm_provider,
        "model": _get_active_model_for_provider(settings.llm_provider),
        "compatibility_mode": settings.compatibility_mode,
        "fallback_enabled": True,
        "last_fallback_event": get_last_fallback_event(),
    }


@app.get("/", tags=["Monitoring"], summary="Root service metadata")
async def root() -> Dict[str, str]:
    """Root endpoint providing links to documentation."""
    return {
        "message": "Welcome to Agentic Recruitment Screening API",
        "docs_url": "/docs",
        "health_check": "/health",
    }
