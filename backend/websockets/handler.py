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
from backend.websockets.openai_client import OpenAIRealtimeClient, MIN_AUDIO_LENGTH_BYTES
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
        while websocket.client_state.name == 'CONNECTED' and openai_client.is_connected and not openai_client.session_ended:
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
                        chunk_size = len(audio_chunk)
                        
                        if chunk_size == 0:
                            logger.warning(f"Received empty audio chunk, skipping, session: {openai_client.session_id}")
                            await websocket.send_json({"type": "input_audio_buffer.append.ack", "event_id": data.get("event_id")})
                            continue
                            
                        audio_buffer.extend(audio_chunk)
                        if openai_client.is_connected and not openai_client.session_ended:
                            await openai_client.process_audio(audio_chunk)
                        await websocket.send_json({"type": "input_audio_buffer.append.ack", "event_id": data.get("event_id")})
                        continue

                    if msg_type == "input_audio_buffer.commit" and not is_processing:
                        is_processing = True
                        
                        # Проверка размера буфера
                        buffer_size = len(audio_buffer)
                        if buffer_size < MIN_AUDIO_LENGTH_BYTES:
                            logger.warning(f"Audio buffer too small to commit: {buffer_size} bytes, session: {openai_client.session_id}")
                            await websocket.send_json({
                                "type": "error",
                                "error": {"code": "buffer_too_small", "message": f"Audio buffer too small ({buffer_size} bytes), need at least {MIN_AUDIO_LENGTH_BYTES} bytes of audio"}
                            })
                            is_processing = False
                            audio_buffer.clear()  # Очистим буфер, чтобы избежать повторных ошибок
                            continue
                        
                        if openai_client.is_connected and not openai_client.session_ended:
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
                                "error": {"code": "openai_not_connected", "message": "Connection to OpenAI lost or session ended"}
                            })

                        audio_buffer.clear()
                        is_processing = False
                        continue

                    if msg_type == "input_audio_buffer.clear":
                        audio_buffer.clear()
                        if openai_client.is_connected and not openai_client.session_ended:
                            await openai_client.clear_audio_buffer()
                        await websocket.send_json({"type": "input_audio_buffer.clear.ack", "event_id": data.get("event_id")})
                        continue

                    if msg_type == "response.cancel":
                        if openai_client.is_connected and not openai_client.session_ended:
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
                                "error": {"code": "openai_not_connected", "message": "Connection to OpenAI lost or session ended"}
                            })
                        continue

                    # Любые остальные типы
                    await websocket.send_json({
                        "type": "error",
                        "error": {"code": "unknown_message_type", "message": f"Unknown message type: {msg_type}"}
                    })

                elif "bytes" in message:
                    # raw-байты от клиента
                    chunk_size = len(message["bytes"])
                    if chunk_size == 0:
                        logger.warning(f"Received empty raw bytes, skipping, session: {openai_client.session_id}")
                        await websocket.send_json({"type": "binary.ack"})
                        continue
                        
                    audio_buffer.extend(message["bytes"])
                    if openai_client.is_connected and not openai_client.session_ended:
                        await openai_client.process_audio(message["bytes"])
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
    
    # Получаем session_id для логов
    session_id = openai_client.session_id
    
    # Буферы для хранения транскрипций и результатов функций
    user_transcript_chunks = []
    assistant_transcript_chunks = []
    current_user_transcript = ""
    current_assistant_transcript = ""
    function_result = None
    
    # Флаг для отслеживания фазы диалога
    in_user_phase = True  # Начинаем в фазе пользовательского ввода
    user_transcript_complete = False
    
    try:
        logger.info(f"[DEBUG] Начало обработки сообщений от OpenAI для клиента {openai_client.client_id}, сессия: {session_id}")
        while openai_client.is_connected and openai_client.ws and not openai_client.session_ended:
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
                    
                    # Продолжаем обработку, не выходя из цикла
                    continue
                
                # Ключевые переходы между фазами диалога
                if msg_type == "input_audio_buffer.speech_started":
                    logger.info(f"[DEBUG] Начало сбора речи пользователя, установка фазы пользователя, сессия: {session_id}")
                    in_user_phase = True
                    continue
                    
                elif msg_type in ["input_audio_buffer.speech_stopped", "response.audio.done", "response.audio_transcript.done"]:
                    if in_user_phase:
                        logger.info(f"[DEBUG] Завершение фазы пользователя, переход к фазе ассистента, сессия: {session_id}")
                        in_user_phase = False
                        user_transcript_complete = True
                        
                        # Сборка полной транскрипции пользователя
                        current_user_transcript = "".join(user_transcript_chunks).strip()
                        logger.info(f"[DEBUG] Окончательная транскрипция пользователя: '{current_user_transcript}', сессия: {session_id}")
                        
                        # Сохраняем транскрипцию пользователя в БД если она не пустая
                        if current_user_transcript and openai_client.db_session and openai_client.conversation_record_id:
                            try:
                                conv = openai_client.db_session.query(Conversation).get(
                                    uuid.UUID(openai_client.conversation_record_id)
                                )
                                if conv:
                                    conv.user_message = current_user_transcript
                                    openai_client.db_session.commit()
                                    logger.info(f"[DEBUG] Сохранена транскрипция пользователя в БД, сессия: {session_id}")
                            except Exception as e:
                                logger.error(f"[DEBUG] Ошибка сохранения транскрипции пользователя в БД: {str(e)}, сессия: {session_id}")
                    continue
                
                # Обработка транскрипций в зависимости от фазы диалога
                if msg_type == "response.audio_transcript.delta":
                    delta_text = response_data.get("delta", "")
                    
                    if in_user_phase:
                        # Мы в фазе пользовательского ввода - это транскрипция речи пользователя
                        user_transcript_chunks.append(delta_text)
                        logger.info(f"[DEBUG] Добавлен фрагмент транскрипции пользователя: '{delta_text}', сессия: {session_id}")
                    else:
                        # Мы в фазе ответа ассистента - это транскрипция ответа ассистента
                        assistant_transcript_chunks.append(delta_text)
                        logger.info(f"[DEBUG] Добавлен фрагмент транскрипции ассистента: '{delta_text}', сессия: {session_id}")
                    continue
                
                # Обработка текстовых дельт (text_delta почти всегда ответ ассистента)
                if msg_type == "text_delta":
                    delta_text = response_data.get("delta", {}).get("text", "")
                    is_final = response_data.get("delta", {}).get("final", False)
                    
                    # В большинстве случаев text_delta - это ответ ассистента
                    assistant_transcript_chunks.append(delta_text)
                    logger.info(f"[DEBUG] Добавлен фрагмент text_delta (ассистент): '{delta_text}', сессия: {session_id}")
                    continue
                
                # Обработка полной транскрипции пользовательского ввода
                if msg_type == "conversation.item.input_audio_transcription.completed":
                    if "transcript" in response_data:
                        full_transcript = response_data.get("transcript", "")
                        if full_transcript:  # Проверяем, что транскрипция не пустая
                            # Заменяем буферы на полную транскрипцию
                            user_transcript_chunks = [full_transcript]
                            current_user_transcript = full_transcript
                            logger.info(f"[DEBUG] Получена полная транскрипция пользователя: '{current_user_transcript}', сессия: {session_id}")
                            
                            # Сохраняем в БД
                            if openai_client.db_session and openai_client.conversation_record_id:
                                try:
                                    conv = openai_client.db_session.query(Conversation).get(
                                        uuid.UUID(openai_client.conversation_record_id)
                                    )
                                    if conv:
                                        conv.user_message = current_user_transcript
                                        openai_client.db_session.commit()
                                        logger.info(f"[DEBUG] Сохранена полная транскрипция пользователя в БД, сессия: {session_id}")
                                except Exception as e:
                                    logger.error(f"[DEBUG] Ошибка сохранения в БД: {str(e)}, сессия: {session_id}")
                    continue
                
                # Получение информации о диалоге - конечный результат содержит полные тексты
                if msg_type == "conversation.item.created":
                    content = response_data.get("content", {})
                    
                    # Получение входа пользователя из диалога
                    if "input" in content and "text" in content.get("input", {}):
                        input_text = content.get("input", {}).get("text", "")
                        if input_text:  # Проверяем, что текст не пустой
                            user_transcript_chunks = [input_text]
                            current_user_transcript = input_text
                            logger.info(f"[DEBUG] Из conversation.item.created получен финальный текст пользователя: '{current_user_transcript}', сессия: {session_id}")
                    
                    # Получение выхода ассистента из диалога
                    if "output" in content:
                        output_list = content.get("output", [])
                        if output_list and len(output_list) > 0:
                            output_content = output_list[0]
                            if isinstance(output_content, dict) and "text" in output_content:
                                output_text = output_content.get("text", "")
                                if output_text:  # Проверяем, что текст не пустой
                                    assistant_transcript_chunks = [output_text]
                                    current_assistant_transcript = output_text
                                    logger.info(f"[DEBUG] Из conversation.item.created получен финальный текст ассистента: '{current_assistant_transcript}', сессия: {session_id}")
                    continue
                
                # Обновление контента ответа ассистента
                if msg_type == "response.content_part.added":
                    if "content" in response_data and "text" in response_data.get("content", {}):
                        response_text = response_data.get("content", {}).get("text", "")
                        if response_text:  # Проверяем, что текст не пустой
                            assistant_transcript_chunks = [response_text]
                            current_assistant_transcript = response_text
                            logger.info(f"[DEBUG] Из response.content_part.added получен обновленный текст ассистента: '{current_assistant_transcript}', сессия: {session_id}")
                    continue
                
                # Отслеживаем состояние ответа
                if msg_type == "response.created":
                    openai_client.response_in_progress = True
                    logger.info(f"[DEBUG] Начало ответа ассистента, сессия: {session_id}")
                    continue
                
                # Обработка вызова функции
                if msg_type == "function_call":
                    # Извлекаем данные вызова функции
                    function_call_id = response_data.get("function_call_id")
                    function_data = response_data.get("function", {})
                    
                    logger.info(f"[DEBUG] Получен вызов функции: {function_data.get('name')}, аргументы: {function_data.get('arguments')}, сессия: {session_id}")
                    
                    # Сообщаем клиенту о том, что выполняется функция
                    if websocket.client_state.name == 'CONNECTED':
                        await websocket.send_json({
                            "type": "function_call.start",
                            "function": function_data.get("name"),
                            "function_call_id": function_call_id
                        })
                    
                    # Выполняем функцию
                    result = await openai_client.handle_function_call(response_data)
                    logger.info(f"[DEBUG] Результат выполнения функции: {result}, сессия: {session_id}")
                    
                    # Сохраняем результат для логирования
                    function_result = result
                    
                    # Отправляем результат в OpenAI
                    await openai_client.send_function_result(function_call_id, result)
                    
                    # Сообщаем клиенту о результате
                    if websocket.client_state.name == 'CONNECTED':
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
                    if websocket.client_state.name == 'CONNECTED':
                        await websocket.send_bytes(chunk)
                    continue

                # Завершение диалога - финализация и запись данных
                if msg_type == "response.done":
                    # Сбрасываем флаг активного ответа
                    openai_client.response_in_progress = False
                    logger.info(f"[DEBUG] Получен сигнал завершения ответа: response.done, сессия: {session_id}")
                    
                    # Сборка окончательных транскрипций
                    if not current_user_transcript:
                        current_user_transcript = "".join(user_transcript_chunks).strip()
                    
                    if not current_assistant_transcript:
                        current_assistant_transcript = "".join(assistant_transcript_chunks).strip()
                    
                    # Выводим финальные тексты для анализа
                    logger.info(f"[DEBUG] Завершен диалог. Пользователь: '{current_user_transcript}', сессия: {session_id}")
                    logger.info(f"[DEBUG] Завершен диалог. Ассистент: '{current_assistant_transcript}', сессия: {session_id}")
                    
                    # Сохраняем сообщение ассистента в БД если оно не пустое
                    if current_assistant_transcript and openai_client.db_session and openai_client.conversation_record_id:
                        logger.info(f"[DEBUG] Сохранение ответа ассистента в БД: {openai_client.conversation_record_id}, сессия: {session_id}")
                        try:
                            conv = openai_client.db_session.query(Conversation).get(
                                uuid.UUID(openai_client.conversation_record_id)
                            )
                            if conv:
                                conv.assistant_message = current_assistant_transcript
                                
                                # Если мы еще не сохранили сообщение пользователя, сохраним его сейчас
                                if current_user_transcript and not conv.user_message:
                                    conv.user_message = current_user_transcript
                                
                                openai_client.db_session.commit()
                                logger.info(f"[DEBUG] Ответ ассистента сохранен в БД, сессия: {session_id}")
                        except Exception as e:
                            logger.error(f"[DEBUG] Ошибка при сохранении ответа ассистента: {str(e)}, сессия: {session_id}")
                    
                    # Если у ассистента есть google_sheet_id, логируем разговор
                    if openai_client.assistant_config and openai_client.assistant_config.google_sheet_id:
                        sheet_id = openai_client.assistant_config.google_sheet_id
                        logger.info(f"[DEBUG] Запись диалога в Google Sheet {sheet_id}, сессия: {session_id}")
                        
                        logger.info(f"[DEBUG] Запись в Google Sheet - Пользователь: '{current_user_transcript}', сессия: {session_id}")
                        logger.info(f"[DEBUG] Запись в Google Sheet - Ассистент: '{current_assistant_transcript}', сессия: {session_id}")
                        
                        # Проверяем наличие текста перед отправкой
                        if not current_user_transcript and not current_assistant_transcript:
                            logger.warning(f"[DEBUG] Пустые тексты диалога, попробуем использовать данные из БД, сессия: {session_id}")
                            # Пробуем получить данные из БД
                            if openai_client.db_session and openai_client.conversation_record_id:
                                try:
                                    conv = openai_client.db_session.query(Conversation).get(
                                        uuid.UUID(openai_client.conversation_record_id)
                                    )
                                    if conv:
                                        current_user_transcript = conv.user_message or ""
                                        current_assistant_transcript = conv.assistant_message or ""
                                        logger.info(f"[DEBUG] Получены данные из БД: пользователь: '{current_user_transcript}', ассистент: '{current_assistant_transcript}', сессия: {session_id}")
                                except Exception as e:
                                    logger.error(f"[DEBUG] Ошибка при получении данных из БД: {str(e)}, сессия: {session_id}")
                        
                        # Используем сохраненные значения для записи в Google Sheets
                        if current_user_transcript or current_assistant_transcript:
                            try:
                                sheets_result = await GoogleSheetsService.log_conversation(
                                    sheet_id=sheet_id,
                                    user_message=current_user_transcript,
                                    assistant_message=current_assistant_transcript,
                                    function_result=function_result
                                )
                                if sheets_result:
                                    logger.info(f"[DEBUG] Успешно записано в Google Sheet, сессия: {session_id}")
                                else:
                                    logger.error(f"[DEBUG] Ошибка при записи в Google Sheet, сессия: {session_id}")
                            except Exception as e:
                                logger.error(f"[DEBUG] Ошибка при записи в Google Sheet: {str(e)}, сессия: {session_id}")
                                logger.error(f"[DEBUG] Трассировка: {traceback.format_exc()}")
                        else:
                            logger.warning(f"[DEBUG] Нет данных для записи в Google Sheet, сессия: {session_id}")
                        
                        # Сбрасываем результат функции после логирования
                        function_result = None
                    else:
                        logger.info(f"[DEBUG] Запись в Google Sheet пропущена - sheet_id не настроен, сессия: {session_id}")
                    
                    # Отмечаем сессию как завершенную
                    openai_client.end_session()
                    break  # Выходим из цикла, так как диалог завершен
                
                # все остальные сообщения — передаём клиенту как JSON
                if websocket.client_state.name == 'CONNECTED':
                    await websocket.send_json(response_data)
                else:
                    logger.warning(f"[DEBUG] Не удалось отправить сообщение: WebSocket уже закрыт, сессия: {session_id}")
                    break
            
            except ConnectionClosed:
                logger.info(f"[DEBUG] Соединение с OpenAI закрыто для сессии: {session_id}")
                break
            except Exception as e:
                logger.error(f"[DEBUG] Ошибка при обработке сообщения от OpenAI: {str(e)}, сессия: {session_id}")
                logger.error(f"[DEBUG] Трассировка: {traceback.format_exc()}")
                # Продолжаем обработку, не выходя из цикла

    except asyncio.CancelledError:
        logger.info(f"[DEBUG] Задача обработки сообщений OpenAI отменена для сессии: {session_id}")
        return
    except Exception as e:
        logger.error(f"[DEBUG] Неожиданная ошибка в обработчике сообщений OpenAI: {e}, сессия: {session_id}")
        logger.error(f"[DEBUG] Трассировка: {traceback.format_exc()}")
    finally:
        # Отмечаем сессию как завершенную
        openai_client.end_session()
        logger.info(f"[DEBUG] Обработчик сообщений OpenAI завершен для сессии: {session_id}")
