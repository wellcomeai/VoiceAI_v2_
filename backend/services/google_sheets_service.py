"""
Google Sheets service for WellcomeAI application.
Handles logging to Google Sheets using the official Google Sheets API.
"""

import os
import json
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, List
import logging
from google.oauth2 import service_account
from googleapiclient.discovery import build

from backend.core.logging import get_logger
from backend.core.config import settings

logger = get_logger(__name__)

# JSON содержимое нового сервисного аккаунта
SERVICE_ACCOUNT_INFO = {
  "type": "service_account",
  "project_id": "voiceai-459203",
  "private_key_id": "ebd256a2b8016bd79ea47a402da57f54a5f02621",
  "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQDG78fw9x5hRmKH\npzJJT8vNJAjcp96qbxaR0WPYqFdhNMZqbAx5fUdZRAQPZBCLnG2EnxuFpLw3y0gE\nuIONaknyVfqsg5JMVNozJXQqczfQDVooATUmSYBkHnfQl9Nkwvgwa0kXLRgg8BWQ\nhJqcQzHPOu38E+1hdnW41YVyRuTuvn0djI8CgfUE7E3l9AHgeUfz/3c9LkpVxTl7\ng4geJZAPTVHMHU5+9iN1bBJzKXdrBkUGyKLxoYK2Eh2WFLpxpJqZLLRRmiJzRYX5\npHUC5m3wHqhg2QXXYWIPoUEczpyZE4ZrN4heN5dKxS9jNH9mkkNpwEbj9XyRPsYP\nZK7wSg+JAgMBAAECggEAToU7IlGvxI5e+pMURpp/4xcLhmid+yCAxIpkwhHj92K4\nxC2kmNlJbaLqhVamLyzNj3CrkMruXYlXgkF/7zPaPxQPrsL53jYJr/FjEhRLHcv/\nX1XmsBeH3TynZwZeMmHAS4A1J7gtU2bf5Bxq2C2vfc+ROpN0+SikG5Hvq6Tu3IpS\nDUmpRxm63wclgXVK21rZMGAqMH7H813BSfKO75+kiKgnoWKBSoqXmMj3jezwQ29Z\ncm1ONAj7rNUaK26qgtjnM/Ia7sAnDtbT8LbnMcQR27mKU3cDjTa42Jr/yNuHenkE\neTO87EVI0+OsD0/D6QXz4Ffq1eYk/qkTFxUxpFyRZwKBgQDsAFGYWsiGZIaZZNaJ\n0dFL5IolUj2UQzDFlxrgM1IIG6QmtWxGK0Aj70s9HkYvwYFxwrpoV9KkrJ74KHUK\nOyj8ACRMDes886jijT8T6qnXAf0kp+mcTZDmDsRJZUAmfIMF5SG+EFJjci3eneLE\nkbIbnz6CM43ogXZWE6YKSvMidwKBgQDXy2c5r+dfVC20dXLz3LN9LIu5qDpIclUR\nhyywTsvAM3eadaITuPMBGUUlP2M2FQeBhGzpyW799xLzi0ueDCk1y15o60LjEus0\nYh61aXSSxpH/qEagMywIPV9XaJaoSYofzV+Dfn2PPUTh47pu+zJRYitR4W1z+pVy\nnofnI/bd/wKBgCJ2QXP//bwyPb10jid97hQpAUtF4RwfW6Xe1NvcYqQwdR357B+q\n/SjCLrh0DUe3+BEGoHXQLUBCvMv8DGs8DFYQJzy745f49LZwbb+YyshM0AxkQKbE\nZN5TVbJqCJ4WHIPl27GHbKB88dnKMG0H4XxLGrOkl5pWHVOgduSV4T8tAoGACEcj\nNJFM3NlLz4pZ2IT01a5pxbtwUOsh3ERFMJY1NrBCvEga6YrEt5wSjPU7hw2TdiJw\nUx+JBHD/5xvG0M9CnW+ptXig3jkRkLba2raq5B5950K7QtXzsHU6PQ4kCVyY0dN9\nAHxPsLj29XtY4Xz9VyXe54swOay5IuZ17CXzCF0CgYEAiXnISoDQ3UCeKMEthHCI\nBJtOBS/SLFbYN1+lH5oVK1oRX6KFaYGbOr5hd94QrNH7AAf6zVQKqH4cVzS49wl5\nBtmRfXOgF4Li2OzlV0l49bVH8PqZ5/e8RlRHev4QjZ8KbeYfOBVBsxqKE/E2CWka\nueB17AwWp3SckmCer8AQU8M=\n-----END PRIVATE KEY-----\n",
  "client_email": "voiceai-856@voiceai-459203.iam.gserviceaccount.com",
  "client_id": "118051709108474225473",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/voiceai-856%40voiceai-459203.iam.gserviceaccount.com",
  "universe_domain": "googleapis.com"
}

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
            # Создаем учетные данные из словаря
            credentials = service_account.Credentials.from_service_account_info(
                SERVICE_ACCOUNT_INFO,
                scopes=['https://www.googleapis.com/auth/spreadsheets']
            )
            
            # Создаем сервис Google Sheets API
            service = build('sheets', 'v4', credentials=credentials, cache_discovery=False)
            cls._service = service
            logger.info("Google Sheets API service initialized successfully")
            return service
        except Exception as e:
            logger.error(f"Error initializing Google Sheets API service: {str(e)}")
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
                return result
            
            result = await loop.run_in_executor(None, append_values)
            
            logger.info(f"Successfully logged conversation to Google Sheet: {sheet_id}")
            return True
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
            
            def get_sheet_info():
                service = GoogleSheetsService._get_sheets_service()
                sheet = service.spreadsheets().get(
                    spreadsheetId=sheet_id,
                    fields='properties.title'
                ).execute()
                return sheet
            
            sheet = await loop.run_in_executor(None, get_sheet_info)
            title = sheet.get('properties', {}).get('title', 'Untitled Spreadsheet')
            
            return {
                "success": True, 
                "message": f"Successfully connected to Google Sheet: {title}",
                "title": title
            }
        except Exception as e:
            logger.error(f"Error verifying Google Sheet access: {str(e)}")
            return {"success": False, "message": f"Error accessing Google Sheet: {str(e)}"}

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
                    return True
                
                return True
            
            result = await loop.run_in_executor(None, check_and_setup)
            
            if result:
                logger.info(f"Successfully set up headers in Google Sheet: {sheet_id}")
                return True
            else:
                logger.error(f"Failed to set up headers in Google Sheet: {sheet_id}")
                return False
        except Exception as e:
            logger.error(f"Error setting up Google Sheet: {str(e)}")
            return False
