import asyncio
import json
import uuid
import base64
import time
from typing import Optional, List, Dict, Any
import websockets
from websockets.exceptions import ConnectionClosed

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.models.assistant import AssistantConfig
from backend.models.conversation import Conversation

logger = get_logger(__name__)

DEFAULT_VOICE = "alloy"
DEFAULT_SYSTEM_MESSAGE = "You are a helpful voice assistant."

class OpenAIRealtimeClient:
    def __init__(
        self,
        api_key: str,
        assistant_config: AssistantConfig,
        client_id: str,
        db_session=None
    ):
        self.api_key = api_key
        self.assistant_config = assistant_config
        self.client_id = client_id
        self.db_session = db_session
        self.ws = None
        self.is_connected = False
        self.openai_url = settings.REALTIME_WS_URL
        self.session_id = str(uuid.uuid4())
        self.conversation_record_id: Optional[str] = None

    async def connect(self) -> bool:
        """
        Establish WebSocket connection to OpenAI Realtime API
        and immediately send up-to-date session settings,
        including the system_prompt from the database.
        """
        if not self.api_key:
            logger.error("API ключ OpenAI не предоставлен")
            return False

        headers = [
            ("Authorization", f"Bearer {self.api_key}"),
            ("OpenAI-Beta", "realtime=v1"),
            ("User-Agent", "WellcomeAI/1.0")
        ]
        try:
            self.ws = await asyncio.wait_for(
                websockets.connect(
                    self.openai_url,
                    extra_headers=headers,
                    max_size=15*1024*1024,
                    ping_interval=30,
                    ping_timeout=120,
                    close_timeout=15
                ),
                timeout=30
            )
            self.is_connected = True
            logger.info(f"Connected to OpenAI for client {self.client_id}")

            # Fetch fresh settings from assistant_config
            voice = self.assistant_config.voice or DEFAULT_VOICE
            system_message = getattr(self.assistant_config, "system_prompt", None) or DEFAULT_SYSTEM_MESSAGE
            functions = getattr(self.assistant_config, "functions", None)

            # Send updated session settings with actual system_prompt
            if not await self.update_session(
                voice=voice,
                system_message=system_message,
                functions=functions
            ):
                await self.close()
                return False

            return True
        except Exception as e:
            logger.error(f"Failed to connect to OpenAI: {e}")
            return False

    async def update_session(
        self,
        voice: str = DEFAULT_VOICE,
        system_message: str = DEFAULT_SYSTEM_MESSAGE,
        functions: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """
        Update session settings on the OpenAI Realtime API side.
        """
        if not self.is_connected or not self.ws:
            return False
        turn_detection = {
            "type": "server_vad",
            "threshold": 0.25,
            "prefix_padding_ms": 200,
            "silence_duration_ms": 300,
            "create_response": True,
        }
        tools = []
        tool_choice = "none"
        
        # Нормализация формата функций
        if functions:
            # Обрабатываем случай, когда функции в формате {enabled_functions: [...]}
            if isinstance(functions, dict) and "enabled_functions" in functions:
                enabled_functions = functions.get("enabled_functions", [])
                
                # Формат для Realtime API
                for func_name in enabled_functions:
                    # Проверяем, есть ли функция в нашем реестре
                    from backend.utils.function_registry import FUNCTION_REGISTRY
                    if func_name in FUNCTION_REGISTRY:
                        # Получаем информацию о функции из реестра или используем базовое описание
                        tools.append({
                            "type": "function",
                            "function": {
                                "name": func_name,
                                "description": f"Function {func_name}",
                                "parameters": {
                                    "type": "object",
                                    "properties": {},
                                    "required": []
                                }
                            }
                        })
            else:
                # Обрабатываем случай, когда функции уже в нужном формате
                for func in functions:
                    tools.append({
                        "type": "function",
                        "function": func
                    })
        
        # Устанавливаем tool_choice
        if tools:
            tool_choice = "auto"  # Позволяем модели решать, когда вызывать функции
        payload = {
            "type": "session.update",
            "session": {
                "turn_detection": turn_detection,
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "voice": voice,
                "instructions": system_message,
                "modalities": ["text", "audio"],
                "temperature": 0.7,
                "max_response_output_tokens": 500,
                "tools": tools,
                "tool_choice": tool_choice
            }
        }
        try:
            await self.ws.send(json.dumps(payload))
            logger.info(f"Настройки сессии отправлены (voice={voice}, tools={len(tools)})")
        except Exception as e:
            logger.error(f"Error sending session.update: {e}")
            return False

        # Create a conversation record in the database if available
        if self.db_session:
            try:
                conv = Conversation(
                    assistant_id=self.assistant_config.id,
                    session_id=self.session_id,
                    user_message="",
                    assistant_message="",
                )
                self.db_session.add(conv)
                self.db_session.commit()
                self.db_session.refresh(conv)
                self.conversation_record_id = str(conv.id)
                logger.info(f"Created conversation record: {self.conversation_record_id}")
            except Exception as e:
                logger.error(f"Error creating Conversation in DB: {e}")

        return True

    async def handle_function_call(self, function_call_data):
        """
        Обработать вызов функции от OpenAI.
        
        Args:
            function_call_data: Данные вызова функции от OpenAI
            
        Returns:
            Результат выполнения функции
        """
        try:
            from backend.utils.function_registry import execute_function
            
            function_name = function_call_data.get("function", {}).get("name")
            arguments = function_call_data.get("function", {}).get("arguments", {})
            
            # Если аргументы в формате строки (JSON), преобразуем их в словарь
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except:
                    arguments = {}
            
            logger.info(f"Обработка вызова функции: {function_name} с аргументами: {arguments}")
            
            # Выполнение функции
            result = await execute_function(
                function_name=function_name, 
                arguments=arguments,
                assistant_config=self.assistant_config,
                client_id=self.client_id
            )
            
            return result
        except Exception as e:
            logger.error(f"Ошибка при обработке вызова функции: {e}")
            return {"error": str(e)}

    async def send_function_result(self, function_call_id, result):
        """
        Отправить результат выполнения функции обратно в OpenAI.
        
        Args:
            function_call_id: ID вызова функции
            result: Результат выполнения функции
            
        Returns:
            True если успешно, False в противном случае
        """
        if not self.is_connected or not self.ws:
            return False
        
        try:
            payload = {
                "type": "function_call_output",
                "function_call_id": function_call_id,
                "content": result
            }
            
            await self.ws.send(json.dumps(payload))
            logger.info(f"Результат функции отправлен: {function_call_id}")
            return True
        except Exception as e:
            logger.error(f"Ошибка отправки результата функции: {e}")
            return False

    async def process_audio(self, audio_buffer: bytes) -> bool:
        if not self.is_connected or not self.ws or not audio_buffer:
            return False
        try:
            data_b64 = base64.b64encode(audio_buffer).decode("utf-8")
            await self.ws.send(json.dumps({
                "type": "input_audio_buffer.append",
                "audio": data_b64,
                "event_id": f"audio_{time.time()}"
            }))
            return True
        except ConnectionClosed:
            self.is_connected = False
            return False

    async def commit_audio(self) -> bool:
        if not self.is_connected or not self.ws:
            return False
        try:
            await self.ws.send(json.dumps({
                "type": "input_audio_buffer.commit",
                "event_id": f"commit_{time.time()}"
            }))
            return True
        except ConnectionClosed:
            self.is_connected = False
            return False

    async def clear_audio_buffer(self) -> bool:
        if not self.is_connected or not self.ws:
            return False
        try:
            await self.ws.send(json.dumps({
                "type": "input_audio_buffer.clear",
                "event_id": f"clear_{time.time()}"
            }))
            return True
        except ConnectionClosed:
            self.is_connected = False
            return False

    async def close(self) -> None:
        if self.ws:
            try:
                await self.ws.close()
            except Exception as e:
                logger.error(f"Error closing OpenAI WS: {e}")
        self.is_connected = False
