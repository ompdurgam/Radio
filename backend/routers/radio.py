"""
Radio Router — /api/radio/*
Handles radio state, song transitions, and now-playing info.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
from fastapi.responses import RedirectResponse
import asyncio
import yt_dlp
from cachetools import TTLCache

stream_cache = TTLCache(maxsize=200, ttl=3600 * 6)

from database import get_db, Song, RadioState as RadioStateModel
from services.radio_service import radio_engine

router = APIRouter(tags=["radio"])


@router.get("/state")
async def get_state(db: Session = Depends(get_db)):
    """Get current radio state — called on page load."""
    state = radio_engine.to_dict()
    return {"success": True, "state": state}

@router.get("/stream/{video_id}")
async def stream_audio(video_id: str):
    """Bypasses YouTube iframe mobile blocks by extracting raw audio stream."""
    if video_id in stream_cache:
        return RedirectResponse(stream_cache[video_id])
    
    def extract():
        ydl_opts = {
            'format': 'bestaudio[ext=m4a]/m4a/bestaudio/best',
            'quiet': True,
            'skip_download': True,
            'nocheckcertificate': True
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
                return info.get('url')
        except Exception as e:
            print(f"yt-dlp extract error: {e}")
            return None

    url = await asyncio.to_thread(extract)
    if url:
        stream_cache[video_id] = url
        return RedirectResponse(url)
    
    raise HTTPException(status_code=500, detail="Could not extract stream")


@router.post("/song-ended")
async def song_ended(db: Session = Depends(get_db)):
    """
    Deprecated — server auto-loop now controls all song transitions.
    Kept for backwards compatibility; always returns current state.
    """
    return {"success": True, "message": "Server controls transitions"}


@router.get("/next")
async def get_next(db: Session = Depends(get_db)):
    """Get what comes next (for admin preview)."""
    if radio_engine.request_queue:
        q = radio_engine.request_queue[0]
        return {"success": True, "type": "request", "data": q}
    song = radio_engine.get_random_song(db)
    return {"success": True, "type": "auto", "song": song}


@router.get("/queue")
async def get_queue():
    """Public queue view — shows upcoming requests."""
    return {
        "success": True,
        "queue": radio_engine.request_queue,
        "pending": radio_engine.pending_queue,
    }
