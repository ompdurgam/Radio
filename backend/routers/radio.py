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


def _extract_audio_url(video_id: str) -> str | None:
    ydl_opts = {
        'format': 'bestaudio[ext=m4a]/m4a/bestaudio/best',
        'quiet': True,
        'skip_download': True,
        'nocheckcertificate': True
    }
    try:
        import shutil
        if shutil.which("node"):
            ydl_opts['js_runtimes'] = {'node': {}}
    except Exception:
        pass
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            return info.get('url')
    except Exception as e:
        print(f"[STREAM] yt-dlp extract error for {video_id}: {e}")
        return None


async def prefetch_stream_url(video_id: str):
    """Pre-fetch stream URL so next song starts instantly with 0ms buffering."""
    if not video_id or video_id in stream_cache:
        return
    url = await asyncio.to_thread(_extract_audio_url, video_id)
    if url:
        stream_cache[video_id] = url
        print(f"[STREAM] Pre-cached audio URL for {video_id}")


@router.get("/state")
async def get_state(db: Session = Depends(get_db)):
    """Get current radio state — called on page load."""
    state = radio_engine.to_dict()
    return {"success": True, "state": state}


@router.get("/stream/{video_id}")
async def stream_audio(video_id: str):
    """Extracts raw audio stream for clean HTML5 playback."""
    if video_id in stream_cache:
        return RedirectResponse(stream_cache[video_id])

    url = await asyncio.to_thread(_extract_audio_url, video_id)
    if url:
        stream_cache[video_id] = url
        return RedirectResponse(url)

    raise HTTPException(status_code=500, detail="Could not extract stream")


class SongEndedBody(BaseModel):
    video_id: str | None = None


@router.post("/song-ended")
async def song_ended(body: SongEndedBody = None, db: Session = Depends(get_db)):
    """Client reports song ended locally. Triggers smooth server advance."""
    vid = body.video_id if body else None
    next_play = await radio_engine.client_song_ended(vid)
    return {"success": True, "next": next_play}


@router.get("/next")
async def get_next(db: Session = Depends(get_db)):
    """Get what comes next (for admin preview)."""
    if radio_engine.request_queue:
        q = radio_engine.request_queue[0]
        return {"success": True, "type": "request", "data": q}
    song = radio_engine._pick_random_song(db)
    return {"success": True, "type": "auto", "song": song}


@router.get("/queue")
async def get_queue():
    """Public queue view — shows upcoming requests."""
    return {
        "success": True,
        "queue": radio_engine.request_queue,
        "pending": radio_engine.pending_queue,
    }
