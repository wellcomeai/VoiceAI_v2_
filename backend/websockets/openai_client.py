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
    """
    Client for interacting with OpenAI's Realtime API through WebSockets.
    Handles voice interactions, function calling, and conversation tracking.
    """
    
    def __init__(
        self,
        api_key: str,
        assistant_config: AssistantConfig,
        client_id: str,
        db_session: Any = None
    ):
        """
        Initialize the OpenAI Realtime client.
        
        Args:
            api_key: OpenAI API key
            assistant_config: Configuration for the assistant
            client_id: Unique identifier for the client
            db_session: Database session for persistence (optional)
        """
        self.api_key = api_key
        self.assistant_config = assistant_config
        self.client_id = client_id
        self.db_session = db_session
        self.ws = None
        self.is_connected = False
        self.openai_url = settings.REALTIME_WS_URL
        self.session_id = str(uuid.uuid4())
        self.conversation_record_id: Optional[str] = None
        self.audio_buffer_size = 0
        self.response_in_progress = False

    async def connect(self) -> bool:
        """
        Establish WebSocket connection to OpenAI Realtime API
        and immediately send up-to-date session settings,
        including the system_prompt from the database.
        
        Returns:
            bool: True if connection was successful, False otherwise
        """
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
                    max_size=15*1024*1024,  # 15 MB max message size
                    ping_interval=30,
                    ping_timeout=120,
                    close_timeout=15
                ),
                timeout=30
            )
            self.is_connected = True
            logger.info(f"Connected to OpenAI for client {self.client_id}, session: {self.session_id}")

            # Fetch fresh settings from assistant_config
            voice = self.assistant_config.voice or DEFAULT_VOICE
            system_message = getattr(self.assistant_config, "system_prompt", None) or DEFAULT_SYSTEM_MESSAGE
            functions = getattr(self.assistant_config, "functions", None)

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
                    logger.info(f"Created conversation record: {self.conversation_record_id} for session: {self.session_id}")
                except Exception as e:
                    logger.error(f"Error creating Conversation in DB: {e}")

            # Send updated session settings with actual system_prompt
            if not await self.update_session(
                voice=voice,
                system_message=system_message,
                functions=functions
            ):
                logger.error(f"Failed to update session settings for session: {self.session_id}")
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
        """
        Update session settings on the OpenAI Realtime API side.
        
        Args:
            voice: Voice ID to use for speech synthesis
            system_message: System instructions for the assistant
            functions: List of functions or dictionary with enabled_functions key
            
        Returns:
            bool: True if update was successful, False otherwise
        """
        if not self.is_connected or not self.ws:
            logger.error("Cannot update session: not connected")
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
        
        # Normalize function format
        if functions:
            # Import function definitions
            from backend.utils.function_registry import FUNCTION_DEFINITIONS
            
            # Handle case when functions are in {enabled_functions: [...]} format
            if isinstance(functions, dict) and "enabled_functions" in functions:
                enabled_functions = functions.get("enabled_functions", [])
                
                # Format for Realtime API
                for func_name in enabled_functions:
                    # Check if function exists in our definitions
                    if func_name in FUNCTION_DEFINITIONS:
                        # Get function info from definitions
                        func_def = FUNCTION_DEFINITIONS[func_name]
                        tools.append({
                            "type": "function",
                            "name": func_name,
                            "description": func_def.get("description", f"Function {func_name}"),
                            "parameters": func_def.get("parameters", {
                                "type": "object",
                                "properties": {},
                                "required": []
                            })
                        })
            else:
                # Handle case when functions are already in the right format
                for func in functions:
                    func_name = func.get("name")
                    if func_name:
                        tools.append({
                            "type": "function",
                            "name": func_name,
                            "description": func.get("description", f"Function {func_name}"),
                            "parameters": func.get("parameters", {
                                "type": "object",
                                "properties": {},
                                "required": []
                            })
                        })
        
        # Set tool_choice
        if tools:
            tool_choice = "auto"  # Allow model to decide when to call functions
            
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
            logger.info(f"Session settings sent for session: {self.session_id} (voice={voice}, tools={len(tools)})")
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
            
            logger.info(f"Processing function call: {function_name} with arguments: {arguments} for session: {self.session_id}")
            
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
            payload = {
                "type": "function_call_output",
                "function_call_id": function_call_id,
                "content": result
            }
            
            await self.ws.send(json.dumps(payload))
            logger.info(f"Function result sent: {function_call_id} for session: {self.session_id}")
            return True
        except Exception as e:
            logger.error(f"Error sending function result: {e}")
            return False

    async def process_audio(self, audio_chunk: bytes) -> bool:
        """
        Process and send audio data to the OpenAI API.
        
        Args:
            audio_chunk: Binary audio data in PCM16 format
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.is_connected or not self.ws or not audio_chunk:
            return False
        try:
            # Отслеживаем размер буфера
            self.audio_buffer_size += len(audio_chunk)
            
            data_b64 = base64.b64encode(audio_chunk).decode("utf-8")
            await self.ws.send(json.dumps({
                "type": "input_audio_buffer.append",
                "audio": data_b64,
                "event_id": f"audio_{time.time()}"
            }))
            return True
        except ConnectionClosed:
            logger.error(f"Connection closed while sending audio data for session: {self.session_id}")
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
            
        # Проверка размера буфера: 16-битный PCM, 16KHz
        # 2000 байт ~ 100мс (минимальное требование OpenAI)
        if self.audio_buffer_size < 2000:
            logger.warning(f"Audio buffer too small to commit ({self.audio_buffer_size} bytes, need at least 2000 bytes) for session: {self.session_id}")
            return False
            
        try:
            await self.ws.send(json.dumps({
                "type": "input_audio_buffer.commit",
                "event_id": f"commit_{time.time()}"
            }))
            logger.info(f"Audio buffer committed ({self.audio_buffer_size} bytes) for session: {self.session_id}")
            # Сбрасываем счетчик размера буфера
            self.audio_buffer_size = 0
            return True
        except ConnectionClosed:
            logger.error(f"Connection closed while committing audio for session: {self.session_id}")
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
            await self.ws.send(json.dumps({
                "type": "input_audio_buffer.clear",
                "event_id": f"clear_{time.time()}"
            }))
            # Сбрасываем счетчик размера буфера
            self.audio_buffer_size = 0
            logger.info(f"Audio buffer cleared for session: {self.session_id}")
            return True
        except ConnectionClosed:
            logger.error(f"Connection closed while clearing audio buffer for session: {self.session_id}")
            self.is_connected = False
            return False
        except Exception as e:
            logger.error(f"Error clearing audio buffer: {e}")
            return False

    async def cancel_response(self) -> bool:
        """
        Cancel the current response if it is in progress.
        
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.is_connected or not self.ws:
            return False
            
        if not self.response_in_progress:
            logger.warning(f"No active response to cancel for session: {self.session_id}")
            return False
            
        try:
            await self.ws.send(json.dumps({
                "type": "response.cancel",
                "event_id": f"cancel_{time.time()}"
            }))
            logger.info(f"Response cancellation requested for session: {self.session_id}")
            return True
        except ConnectionClosed:
            logger.error(f"Connection closed while cancelling response for session: {self.session_id}")
            self.is_connected = False
            return False
        except Exception as e:
            logger.error(f"Error cancelling response: {e}")
            return False

    async def close(self) -> None:
        """
        Close the WebSocket connection.
        """
        if self.ws:
            try:
                await self.ws.close()
                logger.info(f"WebSocket connection closed for client {self.client_id}, session: {self.session_id}")
            except Exception as e:
                logger.error(f"Error closing OpenAI WebSocket: {e}")
        self.is_connected = False
