from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
import json
import asyncio
import uuid
import base64
import traceback
import time
from typing import Dict, List
from websockets.exceptions import ConnectionClosed

from backend.core.logging import get_logger
from backend.core.config import settings
from backend.models.user import User
from backend.models.assistant import AssistantConfig
from backend.models.conversation import Conversation
from backend.utils.audio_utils import base64_to_audio_buffer
from backend.websockets.openai_client import OpenAIRealtimeClient
from backend.services.google_sheets_service import GoogleSheetsService

logger = get_logger(__name__)

active_connections: Dict[str, List[WebSocket]] = {}

# исправление завершено, остальной код не изменился

async def handle_websocket_connection(
    websocket: WebSocket,
    assistant_id: str,
    db: Session
) -> None:
    client_id = str(uuid.uuid4())
    openai_client = None

    try:
        await websocket.accept()
        logger.info(f"WebSocket connection accepted: client_id={client_id}, assistant_id={assistant_id}")
        active_connections.setdefault(assistant_id, []).append(websocket)

        assistant = db.query(AssistantConfig).get(assistant_id)
        if not assistant:
            await websocket.send_json({
                "type": "error",
                "error": {"code": "assistant_not_found", "message": "Assistant not found"}
            })
            await websocket.close(code=1008)
            return

        api_key = None
        if assistant.user_id:
            user = db.query(User).get(assistant.user_id)
            if user and user.openai_api_key:
                api_key = user.openai_api_key

        if not api_key:
            await websocket.send_json({
                "type": "error",
                "error": {"code": "no_api_key", "message": "OpenAI API key is missing"}
            })
            await websocket.close(code=1008)
            return

        openai_client = OpenAIRealtimeClient(api_key, assistant, client_id, db)
        if not await openai_client.connect():
            await websocket.send_json({
                "type": "error",
                "error": {"code": "openai_connection_failed", "message": "Failed to connect to OpenAI"}
            })
            await websocket.close(code=1008)
            return

        await websocket.send_json({"type": "connection_status", "status": "connected", "message": "Connection established"})

        audio_buffer = bytearray()
        is_processing = False

        openai_task = asyncio.create_task(handle_openai_messages(openai_client, websocket))

        while True:
            try:
                message = await websocket.receive()

                if "text" in message:
                    data = json.loads(message["text"])
                    msg_type = data.get("type", "")

                    if msg_type == "ping":
                        await websocket.send_json({"type": "pong"})
                        continue

                    if msg_type == "input_audio_buffer.append":
                        audio_chunk = base64_to_audio_buffer(data["audio"])
                        audio_buffer.extend(audio_chunk)
                        if openai_client.is_connected:
                            await openai_client.process_audio(audio_chunk)
                        await websocket.send_json({"type": "input_audio_buffer.append.ack", "event_id": data.get("event_id")})
                        continue

                    if msg_type == "input_audio_buffer.commit" and not is_processing:
                        is_processing = True
                        if not audio_buffer:
                            await websocket.send_json({
                                "type": "error",
                                "error": {"code": "input_audio_buffer_commit_empty", "message": "Audio buffer is empty"}
                            })
                            is_processing = False
                            continue

                        if openai_client.is_connected:
                            await openai_client.commit_audio()
                            await websocket.send_json({"type": "input_audio_buffer.commit.ack", "event_id": data.get("event_id")})
                        else:
                            await websocket.send_json({
                                "type": "error",
                                "error": {"code": "openai_not_connected", "message": "Connection to OpenAI lost"}
                            })

                        audio_buffer.clear()
                        is_processing = False
                        continue

                    if msg_type == "input_audio_buffer.clear":
                        audio_buffer.clear()
                        if openai_client.is_connected:
                            await openai_client.clear_audio_buffer()
                        await websocket.send_json({"type": "input_audio_buffer.clear.ack", "event_id": data.get("event_id")})
                        continue

                    if msg_type == "response.cancel":
                        if openai_client.is_connected:
                            await openai_client.ws.send(json.dumps({"type": "cancel", "data": {}}))
                        await websocket.send_json({"type": "response.cancel.ack", "event_id": data.get("event_id")})
                        continue

                    await websocket.send_json({
                        "type": "error",
                        "error": {"code": "unknown_message_type", "message": f"Unknown message type: {msg_type}"}
                    })

                elif "bytes" in message:
                    audio_buffer.extend(message["bytes"])
                    await websocket.send_json({"type": "binary.ack"})

            except (WebSocketDisconnect, ConnectionClosed):
                break
            except Exception as e:
                logger.error(f"Error in WebSocket loop: {e}")
                break

        if not openai_task.done():
            openai_task.cancel()
            await asyncio.sleep(0)

    finally:
        if openai_client:
            await openai_client.close()
        conns = active_connections.get(assistant_id, [])
        if websocket in conns:
            conns.remove(websocket)
        logger.info(f"Removed WebSocket connection: client_id={client_id}")


async def handle_openai_messages(openai_client: OpenAIRealtimeClient, websocket: WebSocket):
    if not openai_client.is_connected or not openai_client.ws:
        logger.error("OpenAI client not connected.")
        return

    try:
        while True:
            raw = await openai_client.ws.recv()
            response_data = json.loads(raw)
            msg_type = response_data.get("type", "unknown")
            logger.info(f"[DEBUG] Received message type={msg_type}")

            if msg_type == "text_delta":
                delta = response_data["data"].get("value", "")
                is_final = response_data["data"].get("final", False)
                await websocket.send_json({
                    "type": "text_delta",
                    "value": delta,
                    "is_final": is_final
                })
                continue

            if msg_type == "response":
                text = response_data["data"].get("text", "")
                audio = response_data["data"].get("audio")
                await websocket.send_json({"type": "response.text", "text": text})
                if audio:
                    await websocket.send_json({"type": "response.audio", "audio": audio})
                continue

            if msg_type == "error":
                await websocket.send_json({
                    "type": "error",
                    "error": response_data.get("data")
                })
                continue

            if msg_type == "done":
                await websocket.send_json({"type": "done"})
                return

    except Exception as e:
        logger.error(f"Error receiving from OpenAI: {e}")
