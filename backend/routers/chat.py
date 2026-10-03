"""
Chat Router — /api/chat/*
REST endpoints for chat history. Real-time chat is via WebSocket in main.py.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from datetime import datetime

from database import get_db, ChatMessage

router = APIRouter(tags=["chat"])


@router.get("/recent")
async def get_recent_messages(db: Session = Depends(get_db), limit: int = 50):
    """Get recent chat history for new joiners."""
    messages = db.query(ChatMessage).filter(
        ChatMessage.moderation_status == "approved"
    ).order_by(ChatMessage.created_at.desc()).limit(limit).all()

    return {
        "success": True,
        "messages": [
            {
                "id": m.id,
                "display_name": m.display_name,
                "message": m.message,
                "ts": m.created_at.isoformat(),
            }
            for m in reversed(messages)
        ]
    }
