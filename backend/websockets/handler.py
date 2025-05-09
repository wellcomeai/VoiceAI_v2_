# backend/websockets/handler.py
from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
import json
import asyncio
import uuid
import base64
import traceback
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

# Активные соединения по каждому assistant_id
active_connections: Dict[str, List[WebSocket]] = {}


async def handle_websocket_connection(
    websocket: WebSocket,
    assistant_id: str,
    db: Session
) -> None:
    client_id = str(uuid.uuid4())
    openai_client = None
    audio_buffer = bytearray()

    try:
        await websocket.accept()
        logger.info(f"WebSocket connection accepted: client_id={client_id}, assistant_id={assistant_id}")

        # Регистрируем соединение
        active_connections.setdefault(assistant_id, []).append(websocket)

        # Загружаем конфиг ассистента
        if assistant_id == "demo":
            assistant = db.query(AssistantConfig).filter(AssistantConfig.is_public.is_(True)).first()
            if not assistant:
                assistant = db.query(AssistantConfig).first()
            logger.info(f"Using assistant {assistant.id if assistant else 'None'} for demo")
        else:
            try:
                uuid_obj = uuid.UUID(assistant_id)
                assistant = db.query(AssistantConfig).get(uuid_obj)
            except ValueError:
                assistant = db.query(AssistantConfig).filter(AssistantConfig.id.cast(str) == assistant_id).first()

        if not assistant:
            await websocket.send_json({
                "type": "error",
                "error": {"code": "assistant_not_found", "message": "Assistant not found"}
            })
            await websocket.close(code=1008)
            return

        # Определяем API-ключ
        api_key = None
        if assistant.user_id:
            user = db.query(User).get(assistant.user_id)
            if user and user.openai_api_key:
                api_key = user.openai_api_key
        # Удаляем использование глобального ключа и сразу выдаем ошибку
        if not api_key:
            await websocket.send_json({
                "type": "error",
                "error": {"code": "no_api_key", "message": "Отсутствует ключ API OpenAI. Пожалуйста, добавьте ключ в настройках личного кабинета."}
            })
            await websocket.close(code=1008)
            return

        # Подключаемся к OpenAI
        openai_client = OpenAIRealtimeClient(api_key, assistant, client_id, db)
        if not await openai_client.connect():
            await websocket.send_json({
                "type": "error",
                "error": {"code": "openai_connection_failed", "message": "Failed to connect to OpenAI"}
            })
            await websocket.close(code=1008)
            return

        # Сообщаем клиенту об успешном подключении
        await websocket.send_json({"type": "connection_status", "status": "connected", "message": "Connection established"})

        is_processing = False

        # Запускаем приём сообщений от OpenAI
        openai_task = asyncio.create_task(handle_openai_messages(openai_client, websocket))

        # Основной цикл приёма от клиента
        while websocket.client_state.name == 'CONNECTED' and openai_client.is_connected:
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
                        
                        # Проверка размера буфера
                        buffer_size = len(audio_buffer)
                        if buffer_size < 2000:  # минимум ~100мс аудио (16KHz, 16-bit)
                            logger.warning(f"Audio buffer too small to commit: {buffer_size} bytes, session: {openai_client.session_id}")
                            await websocket.send_json({
                                "type": "error",
                                "error": {"code": "buffer_too_small", "message": "Audio buffer too small, need at least 100ms of audio"}
                            })
                            is_processing = False
                            continue
                        
                        if openai_client.is_connected:
                            logger.info(f"Committing audio buffer ({buffer_size} bytes) for session: {openai_client.session_id}")
                            commit_result = await openai_client.commit_audio()
                            if commit_result:
                                await websocket.send_json({"type": "input_audio_buffer.commit.ack", "event_id": data.get("event_id")})
                            else:
                                await websocket.send_json({
                                    "type": "error",
                                    "error": {"code": "commit_failed", "message": "Failed to commit audio buffer"}
                                })
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
                            # Используем новый метод для отмены с проверкой активного ответа
                            cancel_result = await openai_client.cancel_response()
                            if cancel_result:
                                await websocket.send_json({"type": "response.cancel.ack", "event_id": data.get("event_id")})
                            else:
                                await websocket.send_json({
                                    "type": "error",
                                    "error": {"code": "cancel_failed", "message": "No active response to cancel"}
                                })
                        else:
                            await websocket.send_json({
                                "type": "error",
                                "error": {"code": "openai_not_connected", "message": "Connection to OpenAI lost"}
                            })
                        continue

                    # Любые остальные типы
                    await websocket.send_json({
                        "type": "error",
                        "error": {"code": "unknown_message_type", "message": f"Unknown message type: {msg_type}"}
                    })

                elif "bytes" in message:
                    # raw-байты от клиента
                    audio_buffer.extend(message["bytes"])
                    await websocket.send_json({"type": "binary.ack"})

            except (WebSocketDisconnect, ConnectionClosed):
                logger.info(f"WebSocket disconnected for client_id={client_id}")
                break
            except RuntimeError as e:
                if "Cannot call \"receive\" once a disconnect message has been received" in str(e):
                    logger.info(f"WebSocket already disconnected for client_id={client_id}")
                else:
                    logger.error(f"RuntimeError in WebSocket loop: {e}")
                    logger.error(traceback.format_exc())
                break
            except Exception as e:
                logger.error(f"Error in WebSocket loop: {e}")
                logger.error(traceback.format_exc())
                break

        # завершение
        if not openai_task.done():
            openai_task.cancel()
            await asyncio.sleep(0)  # даём задаче отмениться

    finally:
        if openai_client:
            await openai_client.close()
        # убираем из active_connections
        conns = active_connections.get(assistant_id, [])
        if websocket in conns:
            conns.remove(websocket)
        logger.info(f"Removed WebSocket connection: client_id={client_id}")


async def handle_openai_messages(openai_client: OpenAIRealtimeClient, websocket: WebSocket):
    if not openai_client.is_connected or not openai_client.ws:
        logger.error("OpenAI клиент не подключен.")
        return
    
    # Переменные для хранения текста диалога и результата функции
    user_transcript = ""
    assistant_transcript = ""
    function_result = None
    
    # Переменные для сбора текста
    current_transcript = ""
    collecting_user_input = False
    last_item_type = None
    session_id = openai_client.session_id
    
    try:
        logger.info(f"[DEBUG] Начало обработки сообщений от OpenAI для клиента {openai_client.client_id}, сессия: {session_id}")
        while openai_client.is_connected and openai_client.ws:
            try:
                raw = await openai_client.ws.recv()
                response_data = json.loads(raw)
                
                # Логирование каждого полученного сообщения
                msg_type = response_data.get("type", "unknown")
                logger.info(f"[DEBUG] Получено сообщение от OpenAI: тип={msg_type}, сессия: {session_id}")
                
                # Логирование ошибок от OpenAI
                if msg_type == "error":
                    error_data = response_data.get("error", {})
                    error_code = error_data.get("code", "unknown")
                    error_message = error_data.get("message", "No message")
                    logger.error(f"[DEBUG] OpenAI error: code={error_code}, message={error_message}, сессия: {session_id}")
                
                # Отслеживаем состояние ответа
                if msg_type == "response.created":
                    openai_client.response_in_progress = True
                    logger.info(f"[DEBUG] Начало ответа ассистента, сессия: {session_id}")
                
                # Обработка начала ввода пользователя
                if msg_type == "input_audio_buffer.speech_started":
                    collecting_user_input = True
                    current_transcript = ""
                    logger.info(f"[DEBUG] Начало сбора речи пользователя, сессия: {session_id}")
                
                # Обработка text_delta - новое событие для текстового ввода пользователя
                if msg_type == "text_delta":
                    delta_text = response_data.get("delta", {}).get("text", "")
                    is_final = response_data.get("delta", {}).get("final", False)
                    
                    logger.info(f"[DEBUG] text_delta: '{delta_text}', is_final: {is_final}, сессия: {session_id}")
                    
                    # Собираем текст пользователя
                    if collecting_user_input:
                        current_transcript += delta_text
                        if is_final:
                            user_transcript = current_transcript
                            collecting_user_input = False
                            logger.info(f"[DEBUG] Финальная транскрипция пользователя: '{user_transcript}', сессия: {session_id}")
                            
                            # Сохраняем сообщение пользователя в БД
                            if openai_client.db_session and openai_client.conversation_record_id:
                                try:
                                    conv = openai_client.db_session.query(Conversation).get(
                                        uuid.UUID(openai_client.conversation_record_id)
                                    )
                                    if conv:
                                        conv.user_message = user_transcript
                                        openai_client.db_session.commit()
                                        logger.info(f"[DEBUG] Сохранено сообщение пользователя в БД, сессия: {session_id}")
                                except Exception as e:
                                    logger.error(f"[DEBUG] Ошибка сохранения в БД: {str(e)}, сессия: {session_id}")
                
                # Обработка события транскрипции
                if msg_type == "conversation.item.input_audio_transcription.completed":
                    if "transcript" in response_data:
                        user_transcript = response_data.get("transcript", "")
                        logger.info(f"[DEBUG] Полная транскрипция пользователя: '{user_transcript}', сессия: {session_id}")
                        
                        # Сохраняем сообщение пользователя в БД
                        if openai_client.db_session and openai_client.conversation_record_id:
                            try:
                                conv = openai_client.db_session.query(Conversation).get(
                                    uuid.UUID(openai_client.conversation_record_id)
                                )
                                if conv:
                                    conv.user_message = user_transcript
                                    openai_client.db_session.commit()
                                    logger.info(f"[DEBUG] Сохранено сообщение пользователя в БД, сессия: {session_id}")
                            except Exception as e:
                                logger.error(f"[DEBUG] Ошибка сохранения в БД: {str(e)}, сессия: {session_id}")
                
                # Обработка частей транскрипции и построение полного текста
                if msg_type == "response.audio_transcript.delta":
                    delta_text = response_data.get("delta", "")
                    
                    # Печатаем больше информации для отладки
                    logger.info(f"[DEBUG] Delta текст: '{delta_text}', index: {response_data.get('index')}, is_final: {response_data.get('is_final')}, сессия: {session_id}")
                    
                    # Собираем транскрипцию на основе индекса (0 обычно для пользователя, 1 для ассистента)
                    if "index" in response_data:
                        if response_data.get("index") == 0:
                            if not user_transcript and delta_text:
                                user_transcript = delta_text
                            else:
                                user_transcript += delta_text
                            logger.info(f"[DEBUG] Обновлена транскрипция пользователя: '{user_transcript}', сессия: {session_id}")
                        else:
                            if not assistant_transcript and delta_text:
                               try:
    assistant_transcript = delta_text
except Exception as e:
    logger.error(f"Ошибка обработки delta_text: {e}")

