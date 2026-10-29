"""
backend/api/asap_chat.py
API endpoints for interactive recruiter chat with ASAP (AI Screening & Assessment Pipeline).
Supports both standard REST completion and real-time Server-Sent Events (SSE) streaming.
"""

import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Literal, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from backend.api.auth import get_current_user
from backend.agents.asap_chat_agent import AsapChatAgent

logger = logging.getLogger("recruitment_screening.asap_api")

router = APIRouter(prefix="/api/v1/asap", tags=["ASAP Chat Agent"], dependencies=[Depends(get_current_user)])


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    id: Optional[str] = None
    timestamp: Optional[float] = None


class ChatRequest(BaseModel):
    messages: List[ChatMessage] = Field(..., min_length=1, description="Conversation message history")
    context: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Active workspace context (jobId, candidateId, step)")


class ChatResponse(BaseModel):
    reply: str
    model: str
    provider: str
    usage: Dict[str, Any] = Field(default_factory=dict)
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    action: Optional[Dict[str, Any]] = None


GREETINGS = [
    "Hello, I'm ASAP, your candidate screening assistant, how may I assist you today?",
    "Hi! I'm ASAP, your candidate screening assistant. What jobs, candidates, or evaluations can I help you explore today?",
    "Greetings! I'm ASAP, your candidate screening assistant. How can I assist your recruitment workflow today?",
    "Hello there! I'm ASAP, your screening and talent intelligence assistant. How may I help you evaluate your pipeline today?",
    "Hi! I'm ASAP, your candidate screening assistant. Ready to help you review applicant qualifications, match scores, and job criteria. What's on your mind?",
    "Welcome! I'm ASAP, your candidate screening assistant. How may I assist you with your hiring data and candidate files right now?",
    "Hello! I'm ASAP, your AI screening companion. Feel free to ask about any candidate, job description, or evaluation file in the app. How can I help you?",
    "Hi there! I'm ASAP, your candidate screening assistant. How may I assist you with candidate benchmarking and criteria checks today?",
]

_agent_instance: Optional[AsapChatAgent] = None


def get_asap_agent() -> AsapChatAgent:
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = AsapChatAgent()
    return _agent_instance


@router.get("/greetings", response_model=List[str], summary="List of ASAP initial greetings")
async def get_greetings() -> List[str]:
    """Returns curated initial greeting variations for new chat sessions."""
    return GREETINGS


@router.post("/chat", response_model=ChatResponse, summary="Send message to ASAP Screening Agent (Synchronous)")
async def chat_with_asap(
    request: ChatRequest,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    agent: AsapChatAgent = Depends(get_asap_agent),
) -> ChatResponse:
    """Submits a conversational turn to ASAP, executes platform commands if requested, and returns complete response."""
    try:
        messages_dict = [m.model_dump() for m in request.messages]
        result = await agent.chat(messages=messages_dict, context=request.context or {}, background_tasks=background_tasks)
        return ChatResponse(
            reply=result.get("reply", "No response generated."),
            model=result.get("model", "unknown"),
            provider=result.get("provider", "unknown"),
            usage=result.get("usage", {}),
            sources=result.get("sources", []),
            action=result.get("action"),
        )
    except Exception as e:
        logger.error(f"Chat API exception: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"ASAP Chat engine error: {str(e)}",
        )


@router.post("/chat/stream", summary="Stream conversational response token-by-token (SSE)")
async def chat_with_asap_stream(
    request: ChatRequest,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    agent: AsapChatAgent = Depends(get_asap_agent),
) -> StreamingResponse:
    """Streams conversational response from ASAP word-by-word via Server-Sent Events (SSE)."""
    messages_dict = [m.model_dump() for m in request.messages]
    context_dict = request.context or {}

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            async for event in agent.chat_stream(messages=messages_dict, context=context_dict, background_tasks=background_tasks):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            logger.error(f"Streaming error in chat_with_asap_stream: {e}", exc_info=True)
            error_event = {"type": "chunk", "text": f"\n\n⚠️ Error during response streaming: {str(e)}"}
            yield f"data: {json.dumps(error_event)}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'model': 'error', 'provider': 'failover'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
