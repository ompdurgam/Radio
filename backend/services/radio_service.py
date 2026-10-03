"""
Radio Service — Delux Radio
True server-controlled streaming with pre-planned upcoming queue.
"""
import asyncio
from datetime import datetime
import random
import time
from typing import Optional, Dict, List
from pathlib import Path

from database import Song, Request, SessionLocal
from ws.manager import manager

_DEFAULT_SONG_DURATION = 240   # fallback until client reports actual duration
_UPCOMING_QUEUE_SIZE   = 5     # how many songs to pre-plan


class RadioEngine:
    def __init__(self):
        self.current_song: Optional[Dict] = None
        self.song_started_at: float = 0.0
        self.song_duration:   float = _DEFAULT_SONG_DURATION
        self._duration_confirmed: bool = False
        self.current_rj_url: Optional[str] = None
        self.rj_ends_at: float = 0.0
        self.rj_enabled: bool = True
        self.current_request_id: Optional[int] = None

        # Pre-planned upcoming songs (admin can reorder these)
        self.upcoming_queue: List[Dict] = []

        # Song requests processed by AI pipeline
        self.request_queue: List[Dict] = []
        self.pending_queue: List[int]  = []

        self.mode: str       = "auto"
        self.auto_plays_count: int = 0
        self.is_playing: bool = False
        self._processing_lock = asyncio.Lock()
        self._auto_loop_task: Optional[asyncio.Task] = None

    def _get_audio_file_duration(self, audio_url: Optional[str]) -> float:
        """Measure length of RJ audio in seconds so song start time is accurately delayed."""
        if not audio_url:
            return 0.0
        try:
            filename = Path(audio_url).name
            file_path = Path(__file__).parent.parent / "audio" / filename
            if file_path.exists():
                import mutagen.mp3
                audio = mutagen.mp3.MP3(file_path)
                return float(audio.info.length)
        except Exception as e:
            print(f"[RJ] Could not read audio length ({audio_url}): {e}")
        return 14.0

    def _get_station_rj_interlude(self) -> Optional[str]:
        """Return a station RJ interlude audio URL from pre-rendered RJ clips."""
        if not self.rj_enabled:
            return None
        audio_dir = Path(__file__).parent.parent / "audio"
        available = sorted(list(audio_dir.glob("station_rj_*.mp3")))
        if not available:
            return None
        clip = random.choice(available)
        return f"/audio/{clip.name}"

    # ── State snapshot ─────────────────────────────────────────────────────────
    def to_dict(self) -> Dict:
        now = time.time()
        is_rj_active = bool(self.current_rj_url and (now < self.song_started_at))
        return {
            "current_song":    self.current_song,
            "song_started_at": self.song_started_at,
            "song_duration":   self.song_duration,
            "server_time":     now,
            "rj_audio_url":    self.current_rj_url if is_rj_active else None,
            "rj_enabled":      self.rj_enabled,
            "upcoming_queue":  self.upcoming_queue[:_UPCOMING_QUEUE_SIZE],
            "request_queue":   self.request_queue,
            "pending_count":   len(self.pending_queue),
            "listener_count":  manager.listener_count,
            "mode":            self.mode,
            "is_playing":      self.is_playing,
        }

    # ── Song helpers ───────────────────────────────────────────────────────────
    def _song_to_dict(self, song: Song) -> Dict:
        return {
            "id":               song.id,
            "title":            song.title,
            "artist":           song.artist,
            "movie":            song.movie or "",
            "release_year":     song.release_year,
            "youtube_video_id": song.youtube_video_id,
            "duration":         song.duration or _DEFAULT_SONG_DURATION,
        }

    def _pick_random_song(self, db, exclude_ids: List[str] = None) -> Optional[Dict]:
        """Pick a random active song, avoiding recently played IDs."""
        songs = db.query(Song).filter(Song.active == True).all()
        if not songs:
            return None
        if exclude_ids and len(songs) > len(exclude_ids):
            songs = [s for s in songs if s.youtube_video_id not in exclude_ids]
        return self._song_to_dict(random.choice(songs))

    # ── Pre-fill upcoming queue ────────────────────────────────────────────────
    def _refill_upcoming(self, db):
        """Keep upcoming_queue topped up to _UPCOMING_QUEUE_SIZE."""
        used_ids = []
        if self.current_song:
            used_ids.append(self.current_song["youtube_video_id"])
        used_ids += [s["youtube_video_id"] for s in self.upcoming_queue]

        while len(self.upcoming_queue) < _UPCOMING_QUEUE_SIZE:
            song = self._pick_random_song(db, exclude_ids=used_ids)
            if not song:
                break
            self.upcoming_queue.append(song)
            used_ids.append(song["youtube_video_id"])

    # ── Startup ────────────────────────────────────────────────────────────────
    def boot_with_song(self):
        """
        Called once at server start.
        Immediately picks a song to stream AND pre-fills the upcoming queue.
        """
        db = SessionLocal()
        try:
            # Clean up any leftover 'playing' requests from prior process run
            db.query(Request).filter(Request.status == "playing").update({
                "status": "completed",
                "processed_at": datetime.utcnow()
            })
            db.commit()

            # Start playing
            song = self._pick_random_song(db)
            if song:
                self.current_song      = song
                self.song_started_at   = time.time()
                self.song_duration     = float(song.get("duration") or _DEFAULT_SONG_DURATION)
                self.current_rj_url    = None
                self._duration_confirmed = False
                self.is_playing        = True
                self.mode              = "auto"
                print(f"[RADIO ON AIR] {song['title']} -- {song['artist']} ({self.song_duration:.0f}s)")
            else:
                self.current_song      = None
                self.is_playing        = False
                print("[RADIO] No songs in catalog. Ready for song requests.")

            # Pre-fill upcoming queue
            self._refill_upcoming(db)
            if self.upcoming_queue:
                titles = [s["title"] for s in self.upcoming_queue]
                print(f"[QUEUE] Upcoming: {' -> '.join(titles)}")
        finally:
            db.close()

    # ── Duration reporting ─────────────────────────────────────────────────────
    def update_song_duration(self, video_id: str, duration_seconds: float):
        if not self.current_song:
            return
        if self.current_song.get("youtube_video_id") != video_id:
            return
        if duration_seconds < 10:
            return
        if not self._duration_confirmed or abs(self.song_duration - duration_seconds) > 5:
            print(f"[DURATION] Confirmed: {duration_seconds:.0f}s for \"{self.current_song['title']}\"")
            self.song_duration       = duration_seconds
            self._duration_confirmed = True

            # Save confirmed duration to DB so future plays know it right away
            db = SessionLocal()
            try:
                song_db = db.query(Song).filter(Song.youtube_video_id == video_id).first()
                if song_db and song_db.duration != int(duration_seconds):
                    song_db.duration = int(duration_seconds)
                    db.commit()
            except Exception as e:
                print(f"[DURATION] DB update error: {e}")
            finally:
                db.close()

    # ── Server auto-loop (THE authoritative clock) ─────────────────────────────
    async def start_auto_loop(self):
        """
        Runs forever. Every second, checks if current song is done.
        The server — not any client — decides when to advance.
        """
        print("[LOOP] Server auto-loop started (1-second resolution)")
        while True:
            await asyncio.sleep(1)
            if not self.is_playing or not self.song_started_at:
                continue
            now = time.time()
            if now < self.song_started_at:
                # RJ sound is currently on air; song has not started yet
                continue
            elapsed = now - self.song_started_at
            if elapsed >= self.song_duration + 1:
                print(f"[SKIP] [{elapsed:.0f}s/{self.song_duration:.0f}s] Advancing...")
                next_play = await self._advance()
                await self.broadcast_state()
                await manager.broadcast({"type": "play_next", "data": next_play})

    # ── Advance to next song ───────────────────────────────────────────────────
    async def _advance(self) -> Dict:
        """Internal: pick the next song from request_queue or upcoming_queue."""
        db = SessionLocal()
        try:
            # Complete the previous playing request if one was on air
            if self.current_request_id:
                prev_req = db.query(Request).filter(Request.id == self.current_request_id).first()
                if prev_req and prev_req.status == "playing":
                    prev_req.status = "completed"
                    prev_req.processed_at = datetime.utcnow()
                    db.commit()
                    print(f"[REQUEST] Request #{self.current_request_id} finished playing -> completed.")
                self.current_request_id = None

            # 1) Listener requests take priority
            if self.request_queue:
                req = self.request_queue[0]
                if req.get("ready"):
                    self.request_queue.pop(0)
                    self.mode = "request"
                    song = req.get("song")
                    if song:
                        self.current_song = song

                    # Tag request as 'playing' while on air until song completes
                    req_id = req.get("request_id")
                    if req_id:
                        self.current_request_id = req_id
                        db_req = db.query(Request).filter(Request.id == req_id).first()
                        if db_req:
                            db_req.status = "playing"
                            db.commit()
                            print(f"[REQUEST] Request #{req_id} status tagged as PLAYING.")

                    rj_url = req.get("rj_audio_url") if self.rj_enabled else None
                    rj_dur = self._get_audio_file_duration(rj_url) if rj_url else 0.0
                    self.current_rj_url = rj_url
                    now = time.time()
                    self.rj_ends_at          = now + rj_dur if rj_dur > 0 else 0.0
                    self.song_started_at     = self.rj_ends_at if rj_dur > 0 else now
                    self.song_duration       = float(song.get("duration") or _DEFAULT_SONG_DURATION) if song else _DEFAULT_SONG_DURATION
                    self._duration_confirmed = False
                    self._refill_upcoming(db)
                    return {
                        "type":         "request",
                        "request_id":   req["request_id"],
                        "rj_audio_url": rj_url,
                        "song":         song,
                        "started_at":   self.song_started_at,
                    }

            # 2) Pre-planned upcoming queue
            self.mode = "auto"
            self.auto_plays_count += 1
            if self.upcoming_queue:
                song = self.upcoming_queue.pop(0)
            else:
                song = self._pick_random_song(db)

            if not song:
                self.current_song = None
                self.is_playing = False
                return {"type": "error", "message": "No songs in catalog"}

            # Auto mode station RJ: play an announcement on 1st song and every 3rd song
            rj_audio_url = None
            if self.rj_enabled and (self.auto_plays_count == 1 or (self.auto_plays_count % 3 == 0)):
                rj_audio_url = self._get_station_rj_interlude()
                if rj_audio_url:
                    print(f"[RJ] Station RJ interlude selected: {rj_audio_url}")

            rj_dur = self._get_audio_file_duration(rj_audio_url) if rj_audio_url else 0.0
            self.current_rj_url = rj_audio_url
            now = time.time()
            self.rj_ends_at          = now + rj_dur if rj_dur > 0 else 0.0
            self.song_started_at     = self.rj_ends_at if rj_dur > 0 else now

            self.current_song        = song
            self.song_duration       = float(song.get("duration") or _DEFAULT_SONG_DURATION)
            self._duration_confirmed = False

            # Top up the queue after consuming one
            self._refill_upcoming(db)

            return {
                "type":         "auto",
                "song":         song,
                "started_at":   self.song_started_at,
                "rj_audio_url": rj_audio_url,
            }
        finally:
            db.close()

    # ── Public API used by WS handler and admin ────────────────────────────────
    async def get_next(self) -> Dict:
        """Alias used by existing code."""
        return await self._advance()

    async def admin_skip(self) -> Dict:
        """Admin: immediately skip to next song."""
        next_play = await self._advance()
        await self.broadcast_state()
        await manager.broadcast({"type": "play_next", "data": next_play})
        return next_play

    def admin_toggle_rj(self, enabled: Optional[bool] = None) -> bool:
        """Admin: toggle or set RJ announcements on/off."""
        if enabled is not None:
            self.rj_enabled = bool(enabled)
        else:
            self.rj_enabled = not self.rj_enabled
        print(f"[RJ] Station RJ announcements are now: {'ON' if self.rj_enabled else 'OFF'}")
        return self.rj_enabled

    def admin_reorder_upcoming(self, song_ids: List[int]) -> bool:
        """
        Admin: reorder upcoming_queue by a new list of song IDs.
        Only songs already in the queue can be reordered.
        Returns True on success.
        """
        id_to_song = {s["id"]: s for s in self.upcoming_queue}
        new_queue = []
        for sid in song_ids:
            if sid in id_to_song:
                new_queue.append(id_to_song[sid])

        # Keep any songs not in the new order (e.g. if partial list sent)
        reordered_ids = set(song_ids)
        for s in self.upcoming_queue:
            if s["id"] not in reordered_ids:
                new_queue.append(s)

        self.upcoming_queue = new_queue[:_UPCOMING_QUEUE_SIZE]
        print(f"[QUEUE] Admin reordered: {[s['title'] for s in self.upcoming_queue]}")
        return True

    async def admin_add_to_upcoming(self, song_id: int, position: int = -1) -> bool:
        """Admin: insert a specific song into the upcoming queue."""
        db = SessionLocal()
        try:
            song = db.query(Song).filter(Song.id == song_id, Song.active == True).first()
            if not song:
                return False
            song_dict = self._song_to_dict(song)
            # Remove if already in queue
            self.upcoming_queue = [s for s in self.upcoming_queue if s["id"] != song_id]
            if position < 0 or position >= len(self.upcoming_queue):
                self.upcoming_queue.append(song_dict)
            else:
                self.upcoming_queue.insert(position, song_dict)
            self.upcoming_queue = self.upcoming_queue[:_UPCOMING_QUEUE_SIZE]
            return True
        finally:
            db.close()

    def admin_remove_from_upcoming(self, song_id: int) -> bool:
        """Admin: remove a song from upcoming queue and add a fresh random one."""
        before = len(self.upcoming_queue)
        self.upcoming_queue = [s for s in self.upcoming_queue if s["id"] != song_id]
        if len(self.upcoming_queue) < before:
            db = SessionLocal()
            try:
                self._refill_upcoming(db)
            finally:
                db.close()
            return True
        return False

    # ── Request queue management ───────────────────────────────────────────────
    def add_to_ready_queue(
        self,
        request_id: int,
        song: Dict,
        rj_audio_url: Optional[str],
        requester_name: str,
        dedicated_to: Optional[str],
    ):
        self.request_queue.append({
            "request_id":     request_id,
            "song":           song,
            "rj_audio_url":   rj_audio_url,
            "requester_name": requester_name,
            "dedicated_to":   dedicated_to,
            "ready":          True,
        })
        if request_id in self.pending_queue:
            self.pending_queue.remove(request_id)

    # ── Broadcast ──────────────────────────────────────────────────────────────
    async def broadcast_state(self):
        await manager.broadcast_radio_state(self.to_dict())


# Singleton
radio_engine = RadioEngine()


# ── Request AI pipeline ────────────────────────────────────────────────────────
async def process_request_pipeline(request_id: int):
    from services.ai_service import generate_rj_script, classify_emotion
    from services.tts_service import generate_voice, get_audio_path, get_audio_url
    from services.audio_mixer import mix_rj_announcement

    db = SessionLocal()
    try:
        req = db.query(Request).filter(Request.id == request_id).first()
        if not req:
            return
        song = req.song
        if not song:
            return

        song_data = {
            "id": song.id, "title": song.title, "artist": song.artist,
            "movie": song.movie or "", "release_year": song.release_year,
            "youtube_video_id": song.youtube_video_id,
        }

        emotion = classify_emotion(req.story or "")
        req.emotion_tag = emotion

        print(f"[RJ] Generating script for request #{request_id}...")
        script = await generate_rj_script(
            song_title=song.title, artist=song.artist,
            requester_name=req.requester_name, dedicated_to=req.dedicated_to,
            story=req.story, emotion=emotion,
        )
        req.rj_script = script
        db.commit()

        voice_path = get_audio_path(request_id).replace(".mp3", "_voice.mp3")
        tts_ok = await generate_voice(script, voice_path)

        rj_audio_url = None
        if tts_ok:
            final_path = get_audio_path(request_id)
            if await mix_rj_announcement(voice_path, final_path):
                rj_audio_url = get_audio_url(request_id)
                req.rj_audio_path = final_path
            else:
                import shutil
                shutil.copy2(voice_path, final_path)
                rj_audio_url = get_audio_url(request_id)
                req.rj_audio_path = final_path
            print(f"[RJ] Request #{request_id} audio ready at {rj_audio_url}")
        else:
            print(f"[RJ] Warning: Voice generation failed for request #{request_id}")

        req.status = "queued"
        db.commit()

        radio_engine.add_to_ready_queue(
            request_id=request_id, song=song_data, rj_audio_url=rj_audio_url,
            requester_name=req.requester_name, dedicated_to=req.dedicated_to,
        )

        queue_pos = len(radio_engine.request_queue)
        await manager.broadcast_notification(
            title="Request Queued!",
            body=f"{req.requester_name} requested '{song.title}' -- #{queue_pos} in queue",
            notif_type="request",
        )
        await radio_engine.broadcast_state()
        print(f"[OK] Request #{request_id} ready in queue (pos {queue_pos})")

    except Exception as e:
        print(f"[ERR] Pipeline error for request #{request_id}: {e}")
    finally:
        db.close()
