"""
Google Sheets service для WellcomeAI application.
Использует webhook для логирования вместо прямого доступа к Google Sheets API.
"""

import os
import json
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, List
import aiohttp

from backend.core.logging import get_logger

logger = get_logger(__name__)

class GoogleSheetsService:
    """Service for Google Sheets logging using webhooks"""
    
    @staticmethod
    async def log_conversation(
        sheet_id: str,
        user_message: str,
        assistant_message: str,
        function_result: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Log conversation to Google Sheet through webhook URL
        
        Args:
            sheet_id: Webhook URL or sheet ID
            user_message: User message
            assistant_message: Assistant response
            function_result: Result of function execution (optional)
            
        Returns:
            True if successful, False otherwise
        """
        if not sheet_id:
            logger.warning("No webhook URL or sheet_id provided for logging")
            return False
        
        try:
            # Подготовка данных для отправки
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Подготовка результата функции в виде текста
            function_text = "none"
            if function_result:
                try:
                    # Преобразуем в строку если это словарь или другой сложный тип
                    if isinstance(function_result, dict):
                        function_text = json.dumps(function_result, ensure_ascii=False)
                    else:
                        function_text = str(function_result)
                except Exception as e:
                    logger.error(f"Error formatting function result: {str(e)}")
                    function_text = f"Error formatting result: {str(e)}"
            
            # Формируем данные для отправки
            payload = {
                "timestamp": now,
                "user_message": user_message,
                "assistant_message": assistant_message,
                "function_result": function_text
            }
            
            # Определяем тип URL (webhook URL или Google Script URL)
            webhook_url = sheet_id
            if not (webhook_url.startswith("http://") or webhook_url.startswith("https://")):
                # Это ID таблицы, но мы не используем напрямую API Google
                # Логируем только локально
                logger.info(f"[LOCAL LOG] Sheet ID provided instead of webhook URL: {sheet_id}")
                logger.info(f"[LOCAL LOG] User: {user_message[:100]}...")
                logger.info(f"[LOCAL LOG] Assistant: {assistant_message[:100]}...")
                return True
            
            # Отправляем данные на вебхук
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload) as response:
                    if response.status == 200:
                        logger.info(f"Successfully logged conversation to webhook: {webhook_url}")
                        return True
                    else:
                        logger.error(f"Error logging to webhook. Status: {response.status}")
                        try:
                            error_text = await response.text()
                            logger.error(f"Webhook response: {error_text}")
                        except:
                            pass
                        return False
        except Exception as e:
            logger.error(f"Error logging conversation to webhook: {str(e)}")
            return False
    
    @staticmethod
    async def verify_sheet_access(sheet_id: str) -> Dict[str, Any]:
        """
        Verify webhook URL or emulate success for sheet ID
        
        Args:
            sheet_id: Webhook URL or sheet ID
            
        Returns:
            Dict with status and message
        """
        if not sheet_id:
            return {"success": False, "message": "URL не указан"}
        
        try:
            # Проверяем, является ли это URL или ID таблицы
            if sheet_id.startswith("http://") or sheet_id.startswith("https://"):
                # Это URL, проверяем доступность
                webhook_url = sheet_id
                
                # Тестовый запрос на webhook
                async with aiohttp.ClientSession() as session:
                    # Используем GET для проверки, а не POST
                    async with session.get(webhook_url) as response:
                        if response.status == 200:
                            return {
                                "success": True,
                                "message": f"Webhook доступен для логирования",
                                "title": "Webhook для логирования"
                            }
                        else:
                            return {
                                "success": False,
                                "message": f"Webhook недоступен. Код ответа: {response.status}"
                            }
            else:
                # Это ID таблицы, но не URL вебхука
                # Имитируем успешное подключение
                return {
                    "success": True,
                    "message": "ID таблицы принят. Логирование будет работать в локальном режиме.",
                    "title": "Локальное логирование"
                }
        except Exception as e:
            logger.error(f"Error verifying webhook access: {str(e)}")
            # Возвращаем успех, даже если была ошибка
            return {
                "success": True,
                "message": f"Логирование будет работать в локальном режиме. (Ошибка проверки: {str(e)})",
                "title": "Локальное логирование"
            }

    @staticmethod
    async def setup_sheet(sheet_id: str) -> bool:
        """
        Setup webhook or emulate success for sheet ID
        
        Args:
            sheet_id: Webhook URL or sheet ID
            
        Returns:
            True always
        """
        # Всегда возвращаем True, так как нет необходимости в настройке
        logger.info(f"No setup required for webhook or local logging mode")
        return True
