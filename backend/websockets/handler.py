# backend/websockets/handler.py
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
                                "type": "cancel",
                                "data": {}
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
    user_transcript = ""
    assistant_transcript = ""
    function_result = None
    
    # Переменные для сбора текста
    current_transcript = ""
    collecting_user_input = False
    last_item_type = None
    
    try:
        logger.info(f"[DEBUG] Начало обработки сообщений от OpenAI для клиента {openai_client.client_id}")
        while True:
            try:
                raw = await openai_client.ws.recv()
                response_data = json.loads(raw)
                
                # Логирование каждого полученного сообщения
                msg_type = response_data.get("type", "unknown")
                logger.info(f"[DEBUG] Получено сообщение от OpenAI: тип={msg_type}, полные данные: {json.dumps(response_data)[:200]}...")
                
                # Добавляем более детальное логирование для отладки ошибок
                if msg_type == "error":
                    error_data = response_data.get("data", {})
                    error_message = error_data.get("message", "Неизвестная ошибка")
                    logger.error(f"[DEBUG] Получена ошибка от OpenAI: {error_message}")
                    logger.error(f"[DEBUG] Полное сообщение об ошибке: {json.dumps(response_data)}")
                    
                    # Отправляем ошибку клиенту для отладки
                    await websocket.send_json({
                        "type": "error",
                        "error": {
                            "code": "openai_error",
                            "message": error_message,
                            "details": error_data
                        }
                    })
                    continue
                
                # Обработка стандартных событий session
                if msg_type in ["session.created", "session.updated", "session.initialized"]:
                    # Пересылаем клиенту в формате, который он ожидает
                    await websocket.send_json({
                        "type": msg_type,
                        "session": response_data.get("data", {})
                    })
                    continue
                
                # Транскрипция текста пользователя
                if msg_type == "transcript" or msg_type == "text":
                    if "data" in response_data:
                        transcript = response_data["data"].get("text", "")
                        is_final = response_data["data"].get("final", False)
                        
                        if transcript:
                            user_transcript = transcript  # Заменяем полностью, так как это полная транскрипция
                            logger.info(f"[DEBUG] Получена транскрипция пользователя: '{transcript}'")
                        
                        if is_final:
                            logger.info(f"[DEBUG] Финальная транскрипция пользователя: '{user_transcript}'")
                            
                            # Сохраняем сообщение пользователя в БД
                            if openai_client.db_session and openai_client.conversation_record_id:
                                try:
                                    conv = openai_client.db_session.query(Conversation).get(
                                        uuid.UUID(openai_client.conversation_record_id)
                                    )
                                    if conv:
                                        conv.user_message = user_transcript
                                        openai_client.db_session.commit()
                                        logger.info(f"[DEBUG] Сохранено сообщение пользователя в БД")
                                except Exception as e:
                                    logger.error(f"[DEBUG] Ошибка сохранения в БД: {str(e)}")
                        
                        # Отправляем информацию клиенту в формате, который он ожидает
                        await websocket.send_json({
                            "type": "response.audio_transcript.delta",
                            "delta": transcript,
                            "index": 0,  # 0 для пользователя
                            "is_final": is_final
                        })
                    continue
                
                # Обработка событий текста от ассистента
                if msg_type == "content" or msg_type == "content.text":
                    if "data" in response_data:
                        text_content = response_data["data"].get("text", "")
                        
                        if text_content:
                            if not assistant_transcript:
                                assistant_transcript = text_content
                            else:
                                assistant_transcript += text_content
                            
                            logger.info(f"[DEBUG] Получен текст ассистента: '{text_content}'")
                            
                            # Отправляем клиенту в формате, который он ожидает
                            await websocket.send_json({
                                "type": "response.content_part.added",
                                "content": {
                                    "text": text_content
                                }
                            })
                            
                            # Если это завершающее сообщение, сохраняем в БД
                            if response_data["data"].get("final", False):
                                if openai_client.db_session and openai_client.conversation_record_id:
                                    try:
                                        conv = openai_client.db_session.query(Conversation).get(
                                            uuid.UUID(openai_client.conversation_record_id)
                                        )
                                        if conv:
                                            conv.assistant_message = assistant_transcript
                                            openai_client.db_session.commit()
                                            logger.info(f"[DEBUG] Сохранен текст ассистента в БД")
                                    except Exception as e:
                                        logger.error(f"[DEBUG] Ошибка сохранения ответа в БД: {str(e)}")
                    continue
                
                # Обработка аудио
                if msg_type == "audio":
                    if "data" in response_data and "audio" in response_data["data"]:
                        audio_base64 = response_data["data"]["audio"]
                        audio_bytes = base64.b64decode(audio_base64)
                        await websocket.send_bytes(audio_bytes)
                    continue
                
                # Обработка вызова функции
                if msg_type == "tool" or msg_type == "tool_call":
                    # Извлекаем данные вызова функции
                    tool_data = response_data.get("data", {})
                    function_call_id = tool_data.get("id")
                    
                    # Извлекаем имя функции и аргументы
                    function_name = None
                    function_args = {}
                    
                    for tool in tool_data.get("tools", []):
                        if tool.get("type") == "function":
                            function_data = tool.get("function", {})
                            function_name = function_data.get("name")
                            function_args = function_data.get("arguments", {})
                            break
                    
                    if not function_name:
                        logger.error(f"[DEBUG] Не удалось извлечь имя функции из данных: {tool_data}")
                        continue
                    
                    logger.info(f"[DEBUG] Получен вызов функции: {function_name}, аргументы: {function_args}")
                    
                    # Сообщаем клиенту о том, что выполняется функция
                    await websocket.send_json({
                        "type": "function_call.start",
                        "function": function_name,
                        "function_call_id": function_call_id
                    })
                    
                    # Создаем объект для обработки функции
                    converted_data = {
                        "function": {
                            "name": function_name,
                            "arguments": function_args
                        },
                        "function_call_id": function_call_id
                    }
                    
                    # Выполняем функцию
                    result = await openai_client.handle_function_call(converted_data)
                    logger.info(f"[DEBUG] Результат выполнения функции: {result}")
                    
                    # Сохраняем результат для логирования
                    function_result = result
                    
                    # Отправляем результат в OpenAI
                    await openai_client.send_function_result(function_call_id, result)
                    
                    # Сообщаем клиенту о результате
                    await websocket.send_json({
                        "type": "function_call.completed",
                        "function": function_name,
                        "function_call_id": function_call_id,
                        "result": result
                    })
                    
                    continue
                
                # Завершение сессии
                if msg_type == "done" or msg_type == "end":
                    logger.info(f"[DEBUG] Получен сигнал завершения сессии: {msg_type}")
                    
                    # Отправляем клиенту сигнал завершения
                    await websocket.send_json({
                        "type": "response.done"
                    })
                    
                    # Вызываем логику записи диалога
                    await log_conversation(openai_client, user_transcript, assistant_transcript, function_result)
                    
                    continue
                
                # Преобразуем остальные сообщения в формат, ожидаемый клиентом
                client_message = {
                    "type": f"openai.{msg_type}",  # Префикс для отличия
                    "data": response_data.get("data", {})
                }
                
                # Отправляем клиенту
                await websocket.send_json(client_message)
                
            except (ConnectionClosed, asyncio.CancelledError):
                logger.info(f"[DEBUG] Соединение закрыто для клиента {openai_client.client_id}")
                return
            except Exception as e:
                logger.error(f"[DEBUG] Ошибка при обработке сообщения от OpenAI: {e}")
                logger.error(f"[DEBUG] Трассировка: {traceback.format_exc()}")

    except Exception as e:
        logger.error(f"[DEBUG] Ошибка в обработчике сообщений OpenAI: {e}")
        logger.error(f"[DEBUG] Трассировка: {traceback.format_exc()}")


async def log_conversation(openai_client, user_transcript, assistant_transcript, function_result):
    """
    Отдельная функция для логирования диалога
    """
    try:
        # Проверяем наличие текста пользователя и пробуем получить из БД если отсутствует
        if not user_transcript and openai_client.db_session and openai_client.conversation_record_id:
            try:
                conv = openai_client.db_session.query(Conversation).get(
                    uuid.UUID(openai_client.conversation_record_id)
                )
                if conv and conv.user_message:
                    user_transcript = conv.user_message
                    logger.info(f"[DEBUG] Получен текст пользователя из БД при завершении: '{user_transcript}'")
            except Exception as e:
                logger.error(f"[DEBUG] Ошибка при получении данных из БД: {str(e)}")
        
        # Выводим финальные собранные тексты для анализа
        logger.info(f"[DEBUG] Завершен диалог. Пользователь: '{user_transcript}'")
        logger.info(f"[DEBUG] Завершен диалог. Ассистент: '{assistant_transcript}'")
        logger.info(f"[DEBUG] Результат функции: {function_result}")
        
        # Извлекаем текст пользователя из ответа ассистента, если он все еще не найден
        if not user_transcript and assistant_transcript:
            # Ищем фразы, которые могут указывать на запрос пользователя
            possible_indicators = [
                "вы спросили", "ваш вопрос", "вы хотите", "вы запросили", 
                "вы интересуетесь", "вы сказали", "по вашему запросу"
            ]
            
            assistant_text_lower = assistant_transcript.lower()
            for indicator in possible_indicators:
                if indicator in assistant_text_lower:
                    position = assistant_text_lower.find(indicator)
                    end_position = assistant_text_lower.find(".", position)
                    if end_position > position:
                        extracted_text = assistant_transcript[position:end_position+1]
                        logger.info(f"[DEBUG] Извлечен текст пользователя из ответа ассистента: '{extracted_text}'")
                        user_transcript = f"[Извлечено из ответа] {extracted_text}"
                        break
                        
            # Если ничего не нашли, но есть упоминание о функции
            if not user_transcript and function_result:
                user_transcript = f"[Запрос функции] {function_result.get('type', 'unknown_function')}"
                logger.info(f"[DEBUG] Создан запрос пользователя на основе функции: '{user_transcript}'")
        
        # Сохраняем сообщение ассистента в БД
        if openai_client.db_session and openai_client.conversation_record_id and assistant_transcript:
            logger.info(f"[DEBUG] Сохранение ответа ассистента в БД: {openai_client.conversation_record_id}")
            try:
                conv = openai_client.db_session.query(Conversation).get(
                    uuid.UUID(openai_client.conversation_record_id)
                )
                if conv:
                    conv.assistant_message = assistant_transcript
                    # Также обновляем пользовательское сообщение, если оно есть
                    if user_transcript and not conv.user_message:
                        conv.user_message = user_transcript
                    openai_client.db_session.commit()
            except Exception as e:
                logger.error(f"[DEBUG] Ошибка при сохранении ответа ассистента: {str(e)}")
        
        # Если у ассистента есть google_sheet_id, логируем разговор
        if openai_client.assistant_config and openai_client.assistant_config.google_sheet_id:
            sheet_id = openai_client.assistant_config.google_sheet_id
            logger.info(f"[DEBUG] Запись диалога в Google Sheet {sheet_id}")
            logger.info(f"[DEBUG] Пользователь: '{user_transcript}'")
            logger.info(f"[DEBUG] Ассистент: '{assistant_transcript}'")
            
            # Используем сохраненные значения для записи в Google Sheets
            if user_transcript or assistant_transcript:
                try:
                    sheets_result = await GoogleSheetsService.log_conversation(
                        sheet_id=sheet_id,
                        user_message=user_transcript,
                        assistant_message=assistant_transcript,
                        function_result=function_result
                    )
                    if sheets_result:
                        logger.info(f"[DEBUG] Успешно записано в Google Sheet")
                    else:
                        logger.error(f"[DEBUG] Ошибка при записи в Google Sheet")
                except Exception as e:
                    logger.error(f"[DEBUG] Ошибка при записи в Google Sheet: {str(e)}")
                    logger.error(f"[DEBUG] Трассировка: {traceback.format_exc()}")
            else:
                logger.warning(f"[DEBUG] Нет данных для записи в Google Sheet")
        else:
            logger.info(f"[DEBUG] Запись в Google Sheet пропущена - sheet_id не настроен")
            
    except Exception as e:
        logger.error(f"[DEBUG] Ошибка при логировании диалога: {e}")
        logger.error(f"[DEBUG] Трассировка: {traceback.format_exc()}")
