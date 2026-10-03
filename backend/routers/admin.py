"""
Admin Router — Delux Radio
Password-protected endpoints for the admin dashboard.
"""
import os
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel

from services.radio_service import radio_engine
from database import Song, SessionLocal, AdminUser, Request
import bcrypt
import httpx

router = APIRouter(tags=["admin"])


def _require_auth(x_admin_username: str = Header(None), x_admin_password: str = Header(None)):
    if not x_admin_username or not x_admin_password:
        raise HTTPException(status_code=401, detail="Missing admin credentials")
    db = SessionLocal()
    try:
        user = db.query(AdminUser).filter(AdminUser.username == x_admin_username).first()
        if not user or not bcrypt.checkpw(x_admin_password.encode('utf-8'), user.password_hash.encode('utf-8')):
            raise HTTPException(status_code=401, detail="Invalid admin credentials")
    finally:
        db.close()


class AuthBody(BaseModel):
    username: str
    password: str

# ── Auth ───────────────────────────────────────────────────────────────────────
@router.post("/auth")
def auth_check(body: AuthBody):
    username = body.username
    password = body.password
    if not username or not password:
        raise HTTPException(status_code=401, detail="Missing credentials")
    
    db = SessionLocal()
    try:
        user = db.query(AdminUser).filter(AdminUser.username == username).first()
        if not user or not bcrypt.checkpw(password.encode('utf-8'), user.password_hash.encode('utf-8')):
            raise HTTPException(status_code=401, detail="Wrong credentials")
    finally:
        db.close()
    return {"success": True}


# ── Status ─────────────────────────────────────────────────────────────────────
@router.get("/status")
def get_status(x_admin_username: str = Header(None), x_admin_password: str = Header(None)):
    _require_auth(x_admin_username, x_admin_password)
    return {"success": True, "data": radio_engine.to_dict()}


# ── Upcoming queue ─────────────────────────────────────────────────────────────
@router.get("/upcoming")
def get_upcoming(x_admin_username: str = Header(None), x_admin_password: str = Header(None)):
    _require_auth(x_admin_username, x_admin_password)
    return {
        "success":  True,
        "upcoming": radio_engine.upcoming_queue,
        "current":  radio_engine.current_song,
    }


class ReorderBody(BaseModel):
    song_ids: List[int]


@router.put("/upcoming/reorder")
async def reorder_upcoming(body: ReorderBody, x_admin_username: str = Header(None), x_admin_password: str = Header(None)):
    _require_auth(x_admin_username, x_admin_password)
    radio_engine.admin_reorder_upcoming(body.song_ids)
    await radio_engine.broadcast_state()
    return {"success": True, "upcoming": radio_engine.upcoming_queue}


class AddSongBody(BaseModel):
    song_id: int
    position: int = -1


@router.post("/upcoming/add")
async def add_to_upcoming(body: AddSongBody, x_admin_username: str = Header(None), x_admin_password: str = Header(None)):
    _require_auth(x_admin_username, x_admin_password)
    ok = await radio_engine.admin_add_to_upcoming(body.song_id, body.position)
    if not ok:
        raise HTTPException(status_code=404, detail="Song not found")
    await radio_engine.broadcast_state()
    return {"success": True, "upcoming": radio_engine.upcoming_queue}


@router.delete("/upcoming/{song_id}")
async def remove_from_upcoming(song_id: int, x_admin_username: str = Header(None), x_admin_password: str = Header(None)):
    _require_auth(x_admin_username, x_admin_password)
    ok = radio_engine.admin_remove_from_upcoming(song_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Song not in upcoming queue")
    await radio_engine.broadcast_state()
    return {"success": True, "upcoming": radio_engine.upcoming_queue}


# ── Skip ───────────────────────────────────────────────────────────────────────
@router.post("/skip")
async def skip_song(x_admin_username: str = Header(None), x_admin_password: str = Header(None)):
    _require_auth(x_admin_username, x_admin_password)
    next_play = await radio_engine.admin_skip()
    return {"success": True, "next": next_play}


# ── RJ Toggle ──────────────────────────────────────────────────────────────────
@router.post("/rj/toggle")
async def toggle_rj(x_admin_username: str = Header(None), x_admin_password: str = Header(None)):
    _require_auth(x_admin_username, x_admin_password)
    new_state = radio_engine.admin_toggle_rj()
    await radio_engine.broadcast_state()
    return {"success": True, "rj_enabled": new_state}


# ── Song Requests Queue ────────────────────────────────────────────────────────
@router.get("/requests")
def get_requests(all: bool = False, x_admin_username: str = Header(None), x_admin_password: str = Header(None)):
    _require_auth(x_admin_username, x_admin_password)
    db = SessionLocal()
    try:
        query = db.query(Request)
        if not all:
            query = query.filter(Request.status.in_(["pending", "processing", "queued", "playing"]))
            reqs = query.order_by((Request.status == "playing").desc(), Request.created_at.asc()).all()
        else:
            reqs = query.order_by(Request.created_at.desc()).limit(50).all()
        result = []
        for r in reqs:
            song = r.song
            result.append({
                "id": r.id,
                "song_id": r.song_id,
                "song_title": song.title if song else r.song_name_raw,
                "song_artist": song.artist if song else "Unknown",
                "movie": song.movie if song else "",
                "requester_name": r.requester_name,
                "dedicated_to": r.dedicated_to,
                "story": r.story,
                "status": r.status,
                "emotion_tag": r.emotion_tag,
                "rj_script": r.rj_script,
                "rj_audio_url": f"/audio/rj_{r.id}.mp3" if (r.rj_audio_path and os.path.exists(r.rj_audio_path)) else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            })
        return {"success": True, "requests": result}
    finally:
        db.close()


@router.post("/requests/{request_id}/play-next")
async def play_next_request(request_id: int, x_admin_username: str = Header(None), x_admin_password: str = Header(None)):
    _require_auth(x_admin_username, x_admin_password)
    db = SessionLocal()
    try:
        req = db.query(Request).filter(Request.id == request_id).first()
        if not req or not req.song:
            raise HTTPException(status_code=404, detail="Request or song not found")

        audio_path = req.rj_audio_path
        item = {
            "request_id": req.id,
            "song": radio_engine._song_to_dict(req.song),
            "rj_audio_url": f"/audio/rj_{req.id}.mp3" if (audio_path and os.path.exists(audio_path)) else None,
            "ready": True
        }
        radio_engine.request_queue = [q for q in radio_engine.request_queue if q.get("request_id") != request_id]
        radio_engine.request_queue.insert(0, item)
        req.status = "queued"
        db.commit()
        await radio_engine.broadcast_state()
        return {"success": True, "message": f"Request #{request_id} scheduled to play next"}
    finally:
        db.close()


@router.delete("/requests/{request_id}")
async def delete_request(request_id: int, x_admin_username: str = Header(None), x_admin_password: str = Header(None)):
    _require_auth(x_admin_username, x_admin_password)
    db = SessionLocal()
    try:
        req = db.query(Request).filter(Request.id == request_id).first()
        if not req:
            raise HTTPException(status_code=404, detail="Request not found")

        radio_engine.request_queue = [q for q in radio_engine.request_queue if q.get("request_id") != request_id]
        if request_id in radio_engine.pending_queue:
            radio_engine.pending_queue.remove(request_id)
        if radio_engine.current_request_id == request_id:
            radio_engine.current_request_id = None

        db.delete(req)
        db.commit()
        await radio_engine.broadcast_state()
        return {"success": True, "message": f"Request #{request_id} removed"}
    finally:
        db.close()


# ── Catalog ────────────────────────────────────────────────────────────────────
@router.get("/songs")
def get_all_songs(x_admin_username: str = Header(None), x_admin_password: str = Header(None)):
    _require_auth(x_admin_username, x_admin_password)
    db = SessionLocal()
    try:
        songs = db.query(Song).filter(Song.active == True).order_by(Song.title).all()
        return {
            "success": True,
            "songs": [
                {
                    "id": s.id, "title": s.title, "artist": s.artist,
                    "movie": s.movie or "", "release_year": s.release_year,
                    "youtube_video_id": s.youtube_video_id,
                }
                for s in songs
            ],
        }
    finally:
        db.close()

class NewSongBody(BaseModel):
    title: str
    artist: str
    movie: Optional[str] = ""
    release_year: int
    youtube_video_id: str

@router.post("/songs")
def add_new_song(body: NewSongBody, x_admin_username: str = Header(None), x_admin_password: str = Header(None)):
    _require_auth(x_admin_username, x_admin_password)
    db = SessionLocal()
    try:
        new_song = Song(
            title=body.title,
            artist=body.artist,
            movie=body.movie,
            release_year=body.release_year,
            youtube_video_id=body.youtube_video_id,
            duration=240,
            active=True
        )
        db.add(new_song)
        db.commit()
        db.refresh(new_song)
        return {"success": True, "song_id": new_song.id}
    finally:
        db.close()


def _remove_from_csv(video_id: str):
    if not video_id:
        return
    from pathlib import Path
    import csv
    candidates = [
        Path(__file__).parent.parent.parent / "songs_links.csv",
        Path(__file__).parent.parent / "songs_links.csv",
    ]
    for csv_file in candidates:
        if csv_file.exists():
            try:
                rows = []
                with open(csv_file, 'r', encoding='utf-8', errors='ignore') as f:
                    reader = csv.reader(f)
                    for r in reader:
                        if not r:
                            continue
                        if len(r) >= 2 and video_id in r[1]:
                            continue
                        rows.append(r)
                with open(csv_file, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerows(rows)
            except Exception as e:
                print(f"[WARN] Could not update CSV: {e}")


@router.delete("/songs/{song_id}")
async def delete_song(song_id: int, x_admin_username: str = Header(None), x_admin_password: str = Header(None)):
    _require_auth(x_admin_username, x_admin_password)
    db = SessionLocal()
    try:
        song = db.query(Song).filter(Song.id == song_id).first()
        if not song:
            raise HTTPException(status_code=404, detail="Song not found")

        song_title = song.title
        video_id = song.youtube_video_id

        # 1. Remove from upcoming queue if it's there
        radio_engine.admin_remove_from_upcoming(song_id)

        # 2. If it's currently playing, skip to next song
        if radio_engine.current_song and radio_engine.current_song.get("id") == song_id:
            await radio_engine.admin_skip()

        # 3. Disassociate any requests referencing this song_id
        db.query(Request).filter(Request.song_id == song_id).update({"song_id": None})

        # 4. Delete the song from database
        db.delete(song)
        db.commit()

        # 5. Also remove from songs_links.csv so it won't be reseeded
        _remove_from_csv(video_id)

        await radio_engine.broadcast_state()
        return {"success": True, "message": f"Deleted '{song_title}'"}
    finally:
        db.close()


@router.get("/yt-info")
async def get_yt_info(url: str, x_admin_username: str = Header(None), x_admin_password: str = Header(None)):
    _require_auth(x_admin_username, x_admin_password)
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"https://www.youtube.com/oembed?url={url}&format=json")
        if resp.status_code == 200:
            data = resp.json()
            return {"success": True, "title": data.get("title"), "author": data.get("author_name")}
        else:
            raise HTTPException(status_code=400, detail="Invalid YouTube URL or video unavailable")
