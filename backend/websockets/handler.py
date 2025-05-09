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

        audio_buffer = bytearray()
        is_processing = False

        # Запускаем приём сообщений от OpenAI
        openai_task = asyncio.create_task(handle_openai_messages(openai_client, websocket))

        # Основной цикл приёма от клиента
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
                            await openai_client.ws.send(json.dumps({
                                "type": "response.cancel",
                                "event_id": data.get("event_id")
                            }))
                        await websocket.send_json({"type": "response.cancel.ack", "event_id": data.get("event_id")})
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
                break
            except Exception as e:
                logger.error(f"Error in WebSocket loop: {e}")
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
    user_message_parts = []
    assistant_message_parts = []
    complete_user_message = ""
    complete_assistant_message = ""
    function_result = None
    current_conversation_id = None
    
    try:
        logger.info(f"[DEBUG] Начало обработки сообщений от OpenAI для клиента {openai_client.client_id}")
        while True:
            raw = await openai_client.ws.recv()
            response_data = json.loads(raw)
            
            # Логирование каждого полученного сообщения
            msg_type = response_data.get("type", "unknown")
            logger.info(f"[DEBUG] Получено сообщение от OpenAI: тип={msg_type}")
            
            # Сбор пользовательского ввода
            if msg_type == "conversation.item.created" and "input" in response_data.get("content", {}):
                # Новый разговор начат, сбрасываем накопленное
                user_message_parts = []
                assistant_message_parts = []
                current_conversation_id = response_data.get("id")
                
                # Получаем транскрипцию, если она есть
                input_content = response_data.get("content", {}).get("input", {})
                if "text" in input_content:
                    text = input_content.get("text", "")
                    user_message_parts.append(text)
                    complete_user_message = text
                    logger.info(f"[DEBUG] Получена начальная транскрипция: '{text[:100]}...'")
                    
                    # Сохраняем сообщение пользователя в БД
                    if openai_client.db_session and openai_client.conversation_record_id:
                        logger.info(f"[DEBUG] Сохранение сообщения пользователя в БД: {openai_client.conversation_record_id}")
                        try:
                            conv = openai_client.db_session.query(Conversation).get(
                                uuid.UUID(openai_client.conversation_record_id)
                            )
                            if conv:
                                conv.user_message = complete_user_message
                                openai_client.db_session.commit()
                        except Exception as e:
                            logger.error(f"[DEBUG] Ошибка при сохранении сообщения пользователя: {str(e)}")
            
            # Дополнительные случаи для пользовательского ввода
            if msg_type == "response.audio_transcript.delta" and "index" in response_data:
                # Проверяем, что это транскрипция пользовательского ввода (на основе индекса)
                if response_data.get("index", 0) == 0:  # Индекс 0 обычно для пользовательского ввода
                    text_delta = response_data.get("delta", "")
                    user_message_parts.append(text_delta)
                    complete_user_message = "".join(user_message_parts)
                    logger.info(f"[DEBUG] Обновлена транскрипция пользователя: '{text_delta}', полный текст: '{complete_user_message[:100]}...'")
                else:
                    # Это часть ответа ассистента
                    text_delta = response_data.get("delta", "")
                    assistant_message_parts.append(text_delta)
                    complete_assistant_message = "".join(assistant_message_parts)
                    logger.info(f"[DEBUG] Получен фрагмент ответа ассистента: '{text_delta}', полный текст: '{complete_assistant_message[:100]}...'")
            
            # Обработка вызова функции
            if msg_type == "function_call":
                # Извлекаем данные вызова функции
                function_call_id = response_data.get("function_call_id")
                function_data = response_data.get("function", {})
                
                logger.info(f"[DEBUG] Получен вызов функции: {function_data.get('name')}, аргументы: {function_data.get('arguments')}")
                
                # Сообщаем клиенту о том, что выполняется функция
                await websocket.send_json({
                    "type": "function_call.start",
                    "function": function_data.get("name"),
                    "function_call_id": function_call_id
                })
                
                # Выполняем функцию
                result = await openai_client.handle_function_call(response_data)
                logger.info(f"[DEBUG] Результат выполнения функции: {result}")
                
                # Сохраняем результат для логирования
                function_result = result
                
                # Отправляем результат в OpenAI
                await openai_client.send_function_result(function_call_id, result)
                
                # Сообщаем клиенту о результате
                await websocket.send_json({
                    "type": "function_call.completed",
                    "function": function_data.get("name"),
                    "function_call_id": function_call_id,
                    "result": result
                })
                
                continue

            # если это аудио-чанк — отдаём как bytes
            if msg_type == "audio":
                b64 = response_data.get("data", "")
                chunk = base64.b64decode(b64)
                await websocket.send_bytes(chunk)
                continue

            # все остальные — JSON
            await websocket.send_json(response_data)

            # Завершение диалога - записываем данные в БД и Google Sheets
            if msg_type == "response.done":
                logger.info(f"[DEBUG] Получен сигнал завершения ответа: response.done")
                
                # На этом этапе у нас уже должен быть полный ответ ассистента в complete_assistant_message
                logger.info(f"[DEBUG] Завершен диалог. Пользователь: '{complete_user_message[:100]}...'")
                logger.info(f"[DEBUG] Завершен диалог. Ассистент: '{complete_assistant_message[:100]}...'")
                
                # Сохраняем сообщение ассистента в БД
                if openai_client.db_session and openai_client.conversation_record_id and complete_assistant_message:
                    logger.info(f"[DEBUG] Сохранение ответа ассистента в БД: {openai_client.conversation_record_id}")
                    try:
                        conv = openai_client.db_session.query(Conversation).get(
                            uuid.UUID(openai_client.conversation_record_id)
                        )
                        if conv:
                            conv.assistant_message = complete_assistant_message
                            openai_client.db_session.commit()
                    except Exception as e:
                        logger.error(f"[DEBUG] Ошибка при сохранении ответа ассистента: {str(e)}")
                
                # Если у ассистента есть google_sheet_id, логируем разговор
                if openai_client.assistant_config and openai_client.assistant_config.google_sheet_id:
                    sheet_id = openai_client.assistant_config.google_sheet_id
                    logger.info(f"[DEBUG] Запись диалога в Google Sheet {sheet_id}")
                    logger.info(f"[DEBUG] Пользователь: '{complete_user_message[:100]}...'")
                    logger.info(f"[DEBUG] Ассистент: '{complete_assistant_message[:100]}...'")
                    
                    # Используем сохраненные значения для записи в Google Sheets
                    try:
                        sheets_result = await GoogleSheetsService.log_conversation(
                            sheet_id=sheet_id,
                            user_message=complete_user_message,
                            assistant_message=complete_assistant_message,
                            function_result=function_result
                        )
                        if sheets_result:
                            logger.info(f"[DEBUG] Успешно записано в Google Sheet")
                        else:
                            logger.error(f"[DEBUG] Ошибка при записи в Google Sheet")
                    except Exception as e:
                        logger.error(f"[DEBUG] Ошибка при записи в Google Sheet: {str(e)}")
                        logger.error(f"[DEBUG] Трассировка: {traceback.format_exc()}")
                    
                    # Сбрасываем результат функции после логирования
                    function_result = None
                else:
                    logger.info(f"[DEBUG] Запись в Google Sheet пропущена - sheet_id не настроен")

    except (ConnectionClosed, asyncio.CancelledError):
        logger.info(f"[DEBUG] Соединение закрыто для клиента {openai_client.client_id}")
        return
    except Exception as e:
        logger.error(f"[DEBUG] Ошибка в обработчике сообщений OpenAI: {e}")
        logger.error(f"[DEBUG] Трассировка: {traceback.format_exc()}")
