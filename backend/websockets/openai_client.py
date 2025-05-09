import asyncio
import json
import uuid
import base64
import time
import websockets
from websockets.exceptions import ConnectionClosed

from typing import Optional, List, Dict, Any, Union, AsyncGenerator

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
        db_session: Any = None
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
        if not self.api_key:
            logger.error("OpenAI API key not provided")
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

            voice = self.assistant_config.voice or DEFAULT_VOICE
            system_message = getattr(self.assistant_config, "system_prompt", None) or DEFAULT_SYSTEM_MESSAGE
            functions = getattr(self.assistant_config, "functions", None)

            if not await self.update_session(
                voice=voice,
                system_message=system_message,
                functions=functions
            ):
                logger.error("Failed to update session settings")
                await self.close()
                return False

            return True
        except asyncio.TimeoutError:
            logger.error(f"Connection timeout to OpenAI for client {self.client_id}")
            return False
        except Exception as e:
            logger.error(f"Failed to connect to OpenAI: {e}")
            return False

    async def update_session(
        self,
        voice: str = DEFAULT_VOICE,
        system_message: str = DEFAULT_SYSTEM_MESSAGE,
        functions: Optional[Union[List[Dict[str, Any]], Dict[str, Any]]] = None
    ) -> bool:
        if not self.is_connected or not self.ws:
            logger.error("Cannot update session: not connected")
            return False

        tools = []
        tool_choice = "none"

        if functions:
            from backend.utils.function_registry import FUNCTION_DEFINITIONS

            if isinstance(functions, dict) and "enabled_functions" in functions:
                enabled_functions = functions.get("enabled_functions", [])
                for func_name in enabled_functions:
                    if func_name in FUNCTION_DEFINITIONS:
                        func_def = FUNCTION_DEFINITIONS[func_name]
                        tools.append({
                            "type": "function",
                            "function": {
                                "name": func_name,
                                "description": func_def.get("description", f"Function {func_name}"),
                                "parameters": func_def.get("parameters", {
                                    "type": "object",
                                    "properties": {},
                                    "required": []
                                })
                            }
                        })
            else:
                for func in functions:
                    func_name = func.get("name")
                    if func_name:
                        tools.append({
                            "type": "function",
                            "function": {
                                "name": func_name,
                                "description": func.get("description", f"Function {func_name}"),
                                "parameters": func.get("parameters", {
                                    "type": "object",
                                    "properties": {},
                                    "required": []
                                })
                            }
                        })

        if tools:
            tool_choice = "auto"

        payload = {
            "type": "session.update",
            "data": {
                "instructions": system_message,
                "voice": voice,
                "capabilities": ["audio", "text", "voice_transcription"],
                "tools": tools,
                "tool_choice": tool_choice
            }
        }

        try:
            logger.info(f"Sending update with payload: {json.dumps(payload)[:200]}...")
            await self.ws.send(json.dumps(payload))
            logger.info(f"Session settings sent (voice={voice}, tools={len(tools)})")

            response = await asyncio.wait_for(self.ws.recv(), timeout=5)
            response_data = json.loads(response)
            logger.info(f"Response after update: {json.dumps(response_data)}")

            if response_data.get("type") == "session.updated":
                logger.info("Session updated successfully")
            elif response_data.get("type") == "error":
                error_message = response_data.get("data", {}).get("message", "Unknown error")
                logger.error(f"Error updating session: {error_message}")
            else:
                logger.warning(f"Unexpected response after session.update: {response_data.get('type')}")

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
        except Exception as e:
            logger.error(f"Error sending session.update: {e}")
            return False

    # Остальная логика оставлена без изменений

                # Handle case when functions are already in the right format
                for func in functions:
                    func_name = func.get("name")
                    if func_name:
                        tools.append({
                            "type": "function",
                            "function": {
                                "name": func_name,
                                "description": func.get("description", f"Function {func_name}"),
                                "parameters": func.get("parameters", {
                                    "type": "object",
                                    "properties": {},
                                    "required": []
                                })
                            }
                        })
        
        # Set tool_choice
        if tools:
            tool_choice = "auto"  # Allow model to decide when to call functions
            
        # Согласно документации Microsoft и OpenAI
        # https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/realtime-audio-websockets
        # Строим правильный формат сообщения
        payload = {
            "type": "update",
            "data": {
                "instructions": system_message,
                "voice": voice,
                "tools": tools,
                "tool_choice": tool_choice if tools else "none"
            }
        }
        
        try:
            logger.info(f"Sending update with payload: {json.dumps(payload)[:200]}...")
            await self.ws.send(json.dumps(payload))
            logger.info(f"Session settings sent (voice={voice}, tools={len(tools)})")
            
            # Ожидаем ответ от сервера
            response = await asyncio.wait_for(self.ws.recv(), timeout=5)
            response_data = json.loads(response)
            
            # Логируем полный ответ для отладки
            logger.info(f"Response after update: {json.dumps(response_data)}")
            
            # Проверяем ответ (может быть как session.updated, так и error)
            if response_data.get("type") == "session.updated":
                logger.info("Session updated successfully")
            elif response_data.get("type") == "error":
                error_message = response_data.get("data", {}).get("message", "Unknown error")
                logger.error(f"Error updating session: {error_message}")
                # Тем не менее, продолжаем - иногда API выдает ошибку, но сессия всё равно работает
            else:
                logger.warning(f"Unexpected response after session.update: {response_data.get('type')}")
            
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
        except Exception as e:
            logger.error(f"Error sending session.update: {e}")
            return False

    async def handle_function_call(self, function_call_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a function call from OpenAI.
        
        Args:
            function_call_data: Function call data from OpenAI
            
        Returns:
            Dict: Result of the function execution
        """
        try:
            from backend.utils.function_registry import execute_function
            
            function_name = function_call_data.get("function", {}).get("name")
            arguments = function_call_data.get("function", {}).get("arguments", {})
            
            # If arguments are in string format (JSON), convert to dictionary
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse function arguments as JSON: {arguments}")
                    arguments = {}
            
            logger.info(f"Processing function call: {function_name} with arguments: {arguments}")
            
            # Execute the function
            result = await execute_function(
                function_name=function_name, 
                arguments=arguments,
                assistant_config=self.assistant_config,
                client_id=self.client_id
            )
            
            return result
        except Exception as e:
            logger.error(f"Error processing function call: {e}")
            return {"error": str(e)}

    async def send_function_result(self, function_call_id: str, result: Dict[str, Any]) -> bool:
        """
        Send the result of a function execution back to OpenAI.
        
        Args:
            function_call_id: ID of the function call
            result: Result of the function execution
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.is_connected or not self.ws:
            logger.error("Cannot send function result: not connected")
            return False
        
        try:
            # Обновляем формат сообщения согласно документации
            payload = {
                "type": "tool_result",
                "data": {
                    "id": function_call_id,
                    "result": result
                }
            }
            
            await self.ws.send(json.dumps(payload))
            logger.info(f"Function result sent: {function_call_id}")
            return True
        except Exception as e:
            logger.error(f"Error sending function result: {e}")
            return False

    async def process_audio(self, audio_buffer: bytes) -> bool:
        """
        Process and send audio data to the OpenAI API.
        
        Args:
            audio_buffer: Binary audio data in PCM16 format
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.is_connected or not self.ws or not audio_buffer:
            return False
        try:
            data_b64 = base64.b64encode(audio_buffer).decode("utf-8")
            
            # Обновляем формат согласно документации
            await self.ws.send(json.dumps({
                "type": "audio",
                "data": {
                    "audio": data_b64,
                    "sequence": int(time.time() * 1000)  # Используем timestamp в качестве sequence number
                }
            }))
            return True
        except ConnectionClosed:
            logger.error("Connection closed while sending audio data")
            self.is_connected = False
            return False
        except Exception as e:
            logger.error(f"Error processing audio: {e}")
            return False

    async def commit_audio(self) -> bool:
        """
        Commit the audio buffer, indicating that the user has finished speaking.
        
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.is_connected or not self.ws:
            return False
        try:
            # Обновляем формат согласно документации
            await self.ws.send(json.dumps({
                "type": "audio_end",
                "data": {}
            }))
            return True
        except ConnectionClosed:
            logger.error("Connection closed while committing audio")
            self.is_connected = False
            return False
        except Exception as e:
            logger.error(f"Error committing audio: {e}")
            return False

    async def clear_audio_buffer(self) -> bool:
        """
        Clear the audio buffer, removing any pending audio data.
        
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.is_connected or not self.ws:
            return False
        try:
            # Обновляем формат согласно документации
            await self.ws.send(json.dumps({
                "type": "reset",
                "data": {}
            }))
            return True
        except ConnectionClosed:
            logger.error("Connection closed while clearing audio buffer")
            self.is_connected = False
            return False
        except Exception as e:
            logger.error(f"Error clearing audio buffer: {e}")
            return False

    async def close(self) -> None:
        """
        Close the WebSocket connection.
        """
        if self.ws:
            try:
                # Отправляем сообщение о завершении сессии
                await self.ws.send(json.dumps({
                    "type": "end",
                    "data": {}
                }))
                await self.ws.close()
                logger.info(f"WebSocket connection closed for client {self.client_id}")
            except Exception as e:
                logger.error(f"Error closing OpenAI WebSocket: {e}")
        self.is_connected = False

    async def receive_messages(self) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Receive and yield messages from the OpenAI WebSocket.
        
        Yields:
            Dict: Message received from the OpenAI WebSocket
        """
        if not self.is_connected or not self.ws:
            return
            
        try:
            async for message in self.ws:
                try:
                    data = json.loads(message)
                    yield data
                except json.JSONDecodeError:
                    logger.error(f"Failed to decode message: {message[:100]}...")
        except ConnectionClosed:
            logger.info(f"WebSocket connection closed for client {self.client_id}")
            self.is_connected = False
        except Exception as e:
            logger.error(f"Error receiving messages: {e}")
            self.is_connected = False
