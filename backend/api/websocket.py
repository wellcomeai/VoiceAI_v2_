from fastapi import APIRouter, WebSocket, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from backend.core.logging import get_logger
from backend.db.session import get_db
from backend.api import deps
from backend.models.user import User
from backend.models.assistant import AssistantConfig

# Импортируем handle_websocket_connection напрямую из handler.py
# Избегаем импортирования через __init__.py для предотвращения циклических импортов
from backend.websockets.handler import handle_websocket_connection

logger = get_logger(__name__)

router = APIRouter()

@router.websocket("/ws/{assistant_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    assistant_id: str,
    db: Session = Depends(get_db)
):
    """
    WebSocket endpoint for voice assistant communication
    """
    logger.info(f"WebSocket connection request for assistant_id: {assistant_id}")
    await handle_websocket_connection(websocket, assistant_id, db)
