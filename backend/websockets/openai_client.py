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
            assistant_config: AssistantConfig instance
            client_id: Unique client identifier
            db_session: Optional SQLAlchemy session for conversation logging
        """
        self.api_key = api_key
        self.assistant_config = assistant_config
        self.client_id = client_id
        self.db_session = db_session

        self.session_id: Optional[str] = None
        self.conversation_record_id: Optional[str] = None
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.is_connected = False

    async def connect(self) -> bool:
        """
        Establish WebSocket connection to OpenAI Realtime API.
        """
        try:
            self.ws = await websockets.connect(
                settings.REALTIME_WS_URL,
                extra_headers={"Authorization": f"Bearer {self.api_key}"}
            )
            # Receive initial session.create response
            init = await self.ws.recv()
            data = json.loads(init)
            self.session_id = data["session"]["id"]
            self.is_connected = True
            logger.info(f"Connected to session {self.session_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect: {e}", exc_info=True)
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
            functions: List of functions or dict with key "enabled_functions"
        Returns:
            True if update was successful, else False.
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
        tools: List[Dict[str, Any]] = []
        tool_choice = "none"

        # Normalize function format
        if functions:
            from backend.utils.function_registry import FUNCTION_DEFINITIONS

            # Case: {"enabled_functions": ["send_webhook", ...]}
            if isinstance(functions, dict) and "enabled_functions" in functions:
                enabled = functions["enabled_functions"]
                for func_name in enabled:
                    if func_name in FUNCTION_DEFINITIONS:
                        func_def = FUNCTION_DEFINITIONS[func_name]
                        tools.append({
                            "type": "function",
                            "name": func_name,
                            "description": func_def.get("description"),
                            "parameters": func_def.get("parameters"),
                        })
            else:
                # Case: functions already list of {"name": ..., ...}
                for func in functions:
                    func_name = func.get("name")
                    if func_name and func_name in FUNCTION_DEFINITIONS:
                        func_def = FUNCTION_DEFINITIONS[func_name]
                        tools.append({
                            "type": "function",
                            "name": func_name,
                            "description": func_def.get("description"),
                            "parameters": func_def.get("parameters"),
                        })
                    elif func_name:
                        # Allow custom definitions passed directly
                        tools.append({
                            "type": "function",
                            "name": func_name,
                            "description": func.get("description"),
                            "parameters": func.get("parameters"),
                        })

        if tools:
            tool_choice = "auto"  # Let the model decide when to call functions

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
            logger.info(f"Session settings sent (voice={voice}, tools={len(tools)})")
            return True
        except Exception as e:
            logger.error(f"Error sending session.update: {e}", exc_info=True)
            return False

    async def process_audio(self, audio_buffer: bytes) -> bool:
        """
        Process and send a chunk of audio to the API.
        """
        if not self.is_connected or not self.ws:
            return False
        try:
            await self.ws.send(json.dumps({
                "type": "input_audio_buffer.commit",
                "event_id": f"commit_{time.time()}"
            }))
            return True
        except ConnectionClosed:
            logger.error("Connection closed while committing audio")
            self.is_connected = False
            return False
        except Exception as e:
            logger.error(f"Error committing audio: {e}")
            return False

    async def send_function_result(
        self,
        function_call_id: str,
        result: Dict[str, Any]
    ) -> bool:
        """
        Send the result of a function call back to the session.
        """
        if not self.is_connected or not self.ws:
            return False
        try:
            payload = {
                "type": "function.result",
                "session_id": self.session_id,
                "function_call_id": function_call_id,
                "result": result
            }
            await self.ws.send(json.dumps(payload))
            logger.info(f"Function result sent: {function_call_id}")
            return True
        except Exception as e:
            logger.error(f"Error sending function result: {e}")
            return False

    async def process_messages(self) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Async generator yielding each incoming message (text, function_call, etc.).
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

    async def handle_function_call(self, function_call_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a function call message and return its result.
        """
        from backend.utils.function_registry import execute_function

        function_name = function_call_data.get("function", {}).get("name")
        args = function_call_data.get("function", {}).get("arguments", {})

        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                logger.warning(f"Could not parse function args: {args}")
                args = {}

        logger.info(f"Calling function '{function_name}' with args {args}")
        result = await execute_function(function_name, args)
        return {"name": function_name, "arguments": args, "result": result}

    async def close(self):
        """
        Cleanly close the WebSocket connection.
        """
        if self.ws:
            await self.ws.close()
            self.is_connected = False
            logger.info(f"Session {self.session_id} closed")
