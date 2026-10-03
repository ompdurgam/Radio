"""
Delux Radio — FastAPI Main Application
"""
import json
import uuid
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from database import create_tables, SessionLocal, ChatMessage
from ws.manager import manager
from services.radio_service import radio_engine
from services.moderation import moderate_chat
from routers import radio, requests, chat, admin

AUDIO_DIR = Path(__file__).parent / "audio"
AUDIO_DIR.mkdir(exist_ok=True)
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    create_tables()
    from seed_songs import seed
    import os
    should_seed = os.getenv("DELUX_NO_SEED", "0") != "1"
    seed(seed_songs=should_seed)
    # Auto-start the radio with a song immediately
    radio_engine.boot_with_song()
    # Launch background loop to keep song clock ticking server-side
    asyncio.create_task(radio_engine.start_auto_loop())
    print("[RADIO] Delux Radio is ON AIR -- http://localhost:8000")
    yield
    # Shutdown
    print("[RADIO] Delux Radio signing off.")


app = FastAPI(
    title="Delux Radio",
    description="90s Indian music radio station",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── API Routers ──────────────────────────────────────────────────────────────
app.include_router(radio.router, prefix="/api/radio")
app.include_router(requests.router, prefix="/api/requests")
app.include_router(chat.router, prefix="/api/chat")
app.include_router(admin.router, prefix="/api/admin")

# ─── Static audio files (RJ announcements) ────────────────────────────────────
app.mount("/audio", StaticFiles(directory=str(AUDIO_DIR)), name="audio")


# ─── WebSocket ────────────────────────────────────────────────────────────────

# Rate limiting for chat
_chat_rate: dict = {}  # session_id → [timestamps]

async def check_rate_limit(session_id: str) -> bool:
    import time
    now = time.time()
    history = _chat_rate.get(session_id, [])
    # Keep only messages in last 5 seconds
    history = [t for t in history if now - t < 5]
    if len(history) >= 4:
        return False  # Too many messages
    history.append(now)
    _chat_rate[session_id] = history
    return True


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    client_id = str(uuid.uuid4())
    username = "Listener"

    await manager.connect(websocket, client_id, username)

    # Send current radio state immediately on connect
    await manager.send_personal(
        {"type": "radio_state", "data": radio_engine.to_dict()},
        client_id
    )

    # Send recent chat history
    db = SessionLocal()
    try:
        recent = db.query(ChatMessage).filter(
            ChatMessage.moderation_status == "approved"
        ).order_by(ChatMessage.created_at.desc()).limit(30).all()
        recent.reverse()
        history = [
            {"display_name": m.display_name, "message": m.message, "ts": m.created_at.isoformat()}
            for m in recent
        ]
        await manager.send_personal(
            {"type": "chat_history", "data": history},
            client_id
        )
    finally:
        db.close()

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except Exception:
                continue

            msg_type = data.get("type")

            # ── Set username ──────────────────────────────────────────────────
            if msg_type == "set_username":
                new_name = str(data.get("username", "Listener"))[:50].strip()
                if new_name:
                    is_first = (manager.usernames.get(client_id) == "Listener")
                    username = new_name
                    manager.usernames[client_id] = username
                    # Announce join to other listeners
                    if is_first and username != "Listener":
                        await manager.broadcast(
                            {"type": "user_joined", "data": {"display_name": username}},
                            exclude=client_id
                        )
                # Broadcast updated listener count
                await radio_engine.broadcast_state()

            # ── Chat message ──────────────────────────────────────────────────
            elif msg_type == "chat":
                message = str(data.get("message", "")).strip()
                if not message:
                    continue

                # Rate limiting
                if not await check_rate_limit(client_id):
                    await manager.send_personal(
                        {"type": "error", "message": "⏳ Slow down! Max 4 messages per 5 seconds."},
                        client_id
                    )
                    continue

                # Moderate
                safe, reason = await moderate_chat(message)
                if not safe:
                    await manager.send_personal(
                        {"type": "error", "message": f"🚫 {reason}"},
                        client_id
                    )
                    continue

                # Save to DB
                db = SessionLocal()
                msg_id = None
                try:
                    chat_msg = ChatMessage(
                        session_id=client_id,
                        display_name=username,
                        message=message,
                        moderation_status="approved"
                    )
                    db.add(chat_msg)
                    db.commit()
                    db.refresh(chat_msg)
                    msg_id = chat_msg.id
                finally:
                    db.close()

                # Broadcast (include id for reactions)
                await manager.broadcast_chat(username, message, client_id, msg_id=msg_id)

            # ── Typing indicator ──────────────────────────────────────────────
            elif msg_type == "typing":
                await manager.broadcast(
                    {"type": "typing", "data": {"display_name": username}},
                    exclude=client_id
                )

            elif msg_type == "stop_typing":
                await manager.broadcast(
                    {"type": "stop_typing", "data": {"display_name": username}},
                    exclude=client_id
                )

            # ── Listener ping (heartbeat) ─────────────────────────────────────
            elif msg_type == "ping":
                await manager.send_personal({"type": "pong"}, client_id)

            # ── Song duration report (client reads getDuration() and tells server) ─────
            # This lets the server know the real song length for its auto-loop.
            # Clients do NOT send 'song_ended' — the server decides when to advance.
            elif msg_type == "song_duration_report":
                video_id = str(data.get("video_id", ""))
                duration = float(data.get("duration", 0))
                if video_id and duration > 10:
                    radio_engine.update_song_duration(video_id, duration)

            # ── Ignored: clients must NOT trigger song changes ────────────────────
            elif msg_type == "song_ended":
                pass  # Server auto-loop handles this — ignore client requests

    except WebSocketDisconnect:
        manager.disconnect(client_id)
        await radio_engine.broadcast_state()
    except Exception as e:
        print(f"WS error ({client_id}): {e}")
        manager.disconnect(client_id)
        await radio_engine.broadcast_state()


# ─── Frontend Static Files ─────────────────────────────────────────────────────
if FRONTEND_DIR.exists():
    @app.get("/admin")
    async def admin_page():
        return FileResponse(str(FRONTEND_DIR / "admin.html"))

    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
else:
    @app.get("/")
    async def root():
        return {"message": "Delux Radio API running. Frontend not found."}

