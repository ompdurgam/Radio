"""
WebSocket Connection Manager — Delux Radio
Handles real-time broadcast to all connected listeners.
"""
import json
import asyncio
from typing import Dict, Set, Optional
from fastapi import WebSocket
from datetime import datetime


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.usernames: Dict[str, str] = {}  # client_id → display_name

    async def connect(self, websocket: WebSocket, client_id: str, username: str = "Listener"):
        await websocket.accept()
        self.active_connections[client_id] = websocket
        self.usernames[client_id] = username
        print(f"🔌 Connected: {username} ({client_id}) | Total: {len(self.active_connections)}")

    def disconnect(self, client_id: str):
        name = self.usernames.get(client_id, client_id)
        self.active_connections.pop(client_id, None)
        self.usernames.pop(client_id, None)
        print(f"🔌 Disconnected: {name} | Total: {len(self.active_connections)}")

    @property
    def listener_count(self) -> int:
        return len(self.active_connections)

    async def send_personal(self, message: dict, client_id: str):
        ws = self.active_connections.get(client_id)
        if ws:
            try:
                await ws.send_text(json.dumps(message))
            except Exception:
                self.disconnect(client_id)

    async def broadcast(self, message: dict, exclude: str | None = None):
        """Send to all connected clients. Optionally exclude one client_id."""
        dead = []
        payload = json.dumps(message)
        for cid, ws in list(self.active_connections.items()):
            if cid == exclude:
                continue
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(cid)
        for cid in dead:
            self.disconnect(cid)

    async def broadcast_radio_state(self, state: dict):
        await self.broadcast({"type": "radio_state", "data": state, "ts": datetime.utcnow().isoformat()})

    async def broadcast_chat(self, display_name: str, message: str, client_id: str, msg_id: int | None = None):
        await self.broadcast({
            "type": "chat_message",
            "data": {
                "id": msg_id,
                "display_name": display_name,
                "message": message,
                "client_id": client_id,
                "ts": datetime.utcnow().isoformat()
            }
        })

    async def broadcast_notification(self, title: str, body: str, notif_type: str = "info"):
        await self.broadcast({
            "type": "notification",
            "data": {"title": title, "body": body, "notif_type": notif_type},
            "ts": datetime.utcnow().isoformat()
        })


# Global singleton
manager = ConnectionManager()
