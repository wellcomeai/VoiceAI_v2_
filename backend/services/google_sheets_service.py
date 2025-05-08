"""
Google Sheets service for WellcomeAI application.
Handles logging to Google Sheets using the official Google Sheets API.
Использует файл ключа сервисного аккаунта.
"""

import os
import json
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, List
import logging
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from backend.core.logging import get_logger
from backend.core.config import settings

logger = get_logger(__name__)

# Путь к файлу ключа сервисного аккаунта
# Расположите файл ключа в корне проекта или укажите полный путь
SERVICE_ACCOUNT_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
                                   'voiceai-459203-ebd256a2b801.json')

class GoogleSheetsService:
    """Service for working with Google Sheets using official Google client libraries"""
    
    _service = None
    
    @classmethod
    def _get_sheets_service(cls):
        """
        Получить сервис Google Sheets API
        
        Returns:
            Resource object для взаимодействия с Google Sheets API
        """
        if cls._service is not None:
            return cls._service
            
        try:
            # Создаем учетные данные из файла
            credentials = service_account.Credentials.from_service_account_file(
                SERVICE_ACCOUNT_FILE,
                scopes=['https://www.googleapis.com/auth/spreadsheets']
            )
            
            # Создаем сервис Google Sheets API
            service = build('sheets', 'v4', credentials=credentials, cache_discovery=False)
            cls._service = service
            logger.info("Google Sheets API service initialized successfully")
            return service
        except Exception as e:
            logger.error(f"Error initializing Google Sheets API service: {str(e)}")
            # Более подробный лог для диагностики
            if not os.path.exists(SERVICE_ACCOUNT_FILE):
                logger.error(f"Service account file not found at path: {SERVICE_ACCOUNT_FILE}")
            raise Exception(f"Sheets API service error: {str(e)}")
    
    @staticmethod
    async def log_conversation(
        sheet_id: str,
        user_message: str,
        assistant_message: str,
        function_result: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Log conversation to Google Sheet
        
        Args:
            sheet_id: Google Sheet ID
            user_message: User message
            assistant_message: Assistant response
            function_result: Result of function execution (optional)
            
        Returns:
            True if successful, False otherwise
        """
        if not sheet_id:
            logger.warning("No sheet_id provided for logging")
            return False
        
        try:
            # Prepare values to append
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Prepare function result text
            function_text = "none"
            if function_result:
                try:
                    # Convert to string if dict or other complex type
                    if isinstance(function_result, dict):
                        function_text = json.dumps(function_result, ensure_ascii=False)
                    else:
                        function_text = str(function_result)
                except Exception as e:
                    logger.error(f"Error formatting function result: {str(e)}")
                    function_text = f"Error formatting result: {str(e)}"
            
            # Values row
            values = [[now, user_message, assistant_message, function_text]]
            
            # Вызываем в отдельном потоке, так как это блокирующая операция
            loop = asyncio.get_event_loop()
            
            def append_values():
                try:
                    service = GoogleSheetsService._get_sheets_service()
                    body = {
                        'values': values
                    }
                    result = service.spreadsheets().values().append(
                        spreadsheetId=sheet_id,
                        range='A:D',
                        valueInputOption='RAW',
                        insertDataOption='INSERT_ROWS',
                        body=body
                    ).execute()
                    return True, None
                except HttpError as e:
                    # Проверяем на ошибки доступа (403)
                    if hasattr(e, 'resp') and e.resp.status == 403:
                        logger.error(f"Access denied to Google Sheet: {sheet_id}. Make sure the sheet is publicly editable.")
                        return False, "Access denied. Make sure the Google Sheet is publicly editable with the link."
                    else:
                        logger.error(f"HTTP Error when appending values to Google Sheet: {str(e)}")
                        return False, f"Error: {str(e)}"
                except Exception as e:
                    logger.error(f"Unexpected error appending values to Google Sheet: {str(e)}")
                    return False, f"Unexpected error: {str(e)}"
            
            success, error_message = await loop.run_in_executor(None, append_values)
            
            if success:
                logger.info(f"Successfully logged conversation to Google Sheet: {sheet_id}")
                return True
            else:
                logger.error(f"Failed to log conversation to Google Sheet: {error_message}")
                return False
        except Exception as e:
            logger.error(f"Error logging conversation to Google Sheet: {str(e)}")
            return False
    
    @staticmethod
    async def verify_sheet_access(sheet_id: str) -> Dict[str, Any]:
        """
        Verify access to Google Sheet
        
        Args:
            sheet_id: Google Sheet ID
            
        Returns:
            Dict with status and message
        """
        if not sheet_id:
            return {"success": False, "message": "No sheet ID provided"}
        
        try:
            # Вызываем в отдельном потоке, так как это блокирующая операция
            loop = asyncio.get_event_loop()
            
            def verify_access():
                try:
                    service = GoogleSheetsService._get_sheets_service()
                    
                    # Проверяем доступ к метаданным таблицы
                    sheet = service.spreadsheets().get(
                        spreadsheetId=sheet_id,
                        fields='properties.title'
                    ).execute()
                    
                    title = sheet.get('properties', {}).get('title', 'Untitled Spreadsheet')
                    
                    # Проверяем возможность записи
                    test_values = [["TEST - Проверка доступа (будет удалено)"]]
                    append_result = service.spreadsheets().values().append(
                        spreadsheetId=sheet_id,
                        range='Z:Z',  # Используем отдаленный столбец для теста
                        valueInputOption='RAW',
                        insertDataOption='INSERT_ROWS',
                        body={'values': test_values}
                    ).execute()
                    
                    # Очищаем тестовую запись
                    update_range = append_result.get('updates', {}).get('updatedRange', 'Z1')
                    service.spreadsheets().values().clear(
                        spreadsheetId=sheet_id,
                        range=update_range,
                        body={}
                    ).execute()
                    
                    return {
                        "success": True,
                        "message": f"Successfully connected to Google Sheet: {title}. Sheet is accessible.",
                        "title": title
                    }
                except HttpError as e:
                    status_code = e.resp.status if hasattr(e, 'resp') else 'unknown'
                    error_details = f"HTTP Error {status_code}: {str(e)}"
                    logger.error(f"HTTP error verifying sheet access: {error_details}")
                    
                    if status_code == 403:
                        return {
                            "success": False,
                            "message": "Access denied. Make sure the Google Sheet is publicly editable with the link."
                        }
                    elif status_code == 404:
                        return {
                            "success": False,
                            "message": "Google Sheet not found. Please check the Sheet ID."
                        }
                    else:
                        return {
                            "success": False,
                            "message": f"Error accessing Google Sheet: {error_details}"
                        }
                except Exception as e:
                    logger.error(f"Unexpected error verifying sheet access: {str(e)}")
                    return {
                        "success": False,
                        "message": f"Unexpected error: {str(e)}"
                    }
            
            result = await loop.run_in_executor(None, verify_access)
            return result
            
        except Exception as e:
            logger.error(f"Error verifying Google Sheet access: {str(e)}")
            return {"success": False, "message": f"Error: {str(e)}"}

    @staticmethod
    async def setup_sheet(sheet_id: str) -> bool:
        """
        Set up sheet with headers if it's empty
        
        Args:
            sheet_id: Google Sheet ID
            
        Returns:
            True if successful, False otherwise
        """
        if not sheet_id:
            return False
            
        try:
            # Вызываем в отдельном потоке, так как это блокирующая операция
            loop = asyncio.get_event_loop()
            
            def check_and_setup():
                try:
                    service = GoogleSheetsService._get_sheets_service()
                    
                    # Проверяем существующие данные
                    result = service.spreadsheets().values().get(
                        spreadsheetId=sheet_id,
                        range='A1:D1'
                    ).execute()
                    
                    values = result.get('values', [])
                    
                    # Если заголовков нет, добавляем их
                    if not values:
                        headers = [["Дата и время", "Пользователь", "Ассистент", "Результат функции"]]
                        body = {
                            'values': headers
                        }
                        update_result = service.spreadsheets().values().update(
                            spreadsheetId=sheet_id,
                            range='A1:D1',
                            valueInputOption='RAW',
                            body=body
                        ).execute()
                        logger.info(f"Added headers to Google Sheet: {sheet_id}")
                        
                    return True
                except HttpError as e:
                    status_code = e.resp.status if hasattr(e, 'resp') else 'unknown'
                    logger.error(f"HTTP error setting up sheet: {status_code} - {str(e)}")
                    return False
                except Exception as e:
                    logger.error(f"Unexpected error setting up Google Sheet: {str(e)}")
                    return False
            
            result = await loop.run_in_executor(None, check_and_setup)
            
            if result:
                logger.info(f"Successfully set up Google Sheet: {sheet_id}")
                return True
            else:
                logger.error(f"Failed to set up Google Sheet: {sheet_id}")
                return False
        except Exception as e:
            logger.error(f"Error setting up Google Sheet: {str(e)}")
            return False
