from typing import Dict, List
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, execution_id: int, websocket: WebSocket):
        await websocket.accept()
        self.connections.setdefault(execution_id, []).append(websocket)

    def disconnect(self, execution_id: int, websocket: WebSocket):
        conns = self.connections.get(execution_id, [])
        if websocket in conns:
            conns.remove(websocket)
        if not conns:
            self.connections.pop(execution_id, None)

    async def send_log(self, execution_id: int, message: str):
        conns = self.connections.get(execution_id, [])
        for conn in conns[:]:
            try:
                await conn.send_text(message)
            except Exception:
                self.disconnect(execution_id, conn)


manager = ConnectionManager()
