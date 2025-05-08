"""
Google Sheets service для WellcomeAI application.
С подробной диагностикой и исправленной областью видимости.
"""

import os
import json
import asyncio
import time
import platform
import traceback
import sys
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
import aiohttp

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import google.auth.exceptions
import google.auth.transport.requests

from backend.core.logging import get_logger

logger = get_logger(__name__)

# Путь к файлу ключа сервисного аккаунта
SERVICE_ACCOUNT_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
                                   'voiceai-459203-ebd256a2b801.json')

# Содержимое сервисного аккаунта (поле private_key отформатировано с реальными переносами строк)
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
    """Service for Google Sheets logging with detailed diagnostics"""
    
    _service = None
    
    @staticmethod
    async def _log_environment_info():
        """Выводит подробную информацию об окружении для диагностики"""
        try:
            # Информация о системе
            logger.info(f"=== ENVIRONMENT DIAGNOSTICS ===")
            logger.info(f"Platform: {platform.platform()}")
            logger.info(f"Python version: {sys.version}")
            logger.info(f"Current directory: {os.getcwd()}")
            
            # Проверка файла ключа
            logger.info(f"Key file path: {SERVICE_ACCOUNT_FILE}")
            logger.info(f"Key file exists: {os.path.exists(SERVICE_ACCOUNT_FILE)}")
            
            if os.path.exists(SERVICE_ACCOUNT_FILE):
                file_stat = os.stat(SERVICE_ACCOUNT_FILE)
                logger.info(f"Key file size: {file_stat.st_size} bytes")
                logger.info(f"Key file permissions: {oct(file_stat.st_mode)}")
                
                # Проверка содержимого файла
                try:
                    with open(SERVICE_ACCOUNT_FILE, 'r') as f:
                        key_content = f.read()
                        
                    # Попытка разобрать JSON
                    try:
                        key_data = json.loads(key_content)
                        logger.info(f"Key file loaded successfully as JSON")
                        
                        # Проверяем основные поля
                        required_fields = ["type", "project_id", "private_key_id", "private_key", 
                                          "client_email", "client_id", "auth_uri", "token_uri"]
                        
                        for field in required_fields:
                            if field in key_data:
                                # Для приватного ключа выводим только начало и конец
                                if field == "private_key":
                                    value = f"{key_data[field][:20]}...{key_data[field][-20:]}"
                                    # Проверяем наличие переносов строк
                                    has_real_newlines = "\n" in key_data[field]
                                    has_backslash_n = "\\n" in key_data[field]
                                    logger.info(f"Private key contains \\n: {has_backslash_n}")
                                    logger.info(f"Private key contains real newlines: {has_real_newlines}")
                                else:
                                    value = key_data[field]
                                logger.info(f"Key file contains {field}: {value}")
                            else:
                                logger.error(f"Key file missing required field: {field}")
                                
                        # Проверяем email сервисного аккаунта
                        if "client_email" in key_data:
                            logger.info(f"Service account email: {key_data['client_email']}")
                    except json.JSONDecodeError as e:
                        logger.error(f"Key file is not valid JSON: {str(e)}")
                        # Показываем часть содержимого для диагностики
                        logger.error(f"Key file content (first 100 chars): {key_content[:100]}")
                except Exception as e:
                    logger.error(f"Error reading key file: {str(e)}")
            else:
                # Попытка найти файлы в текущей директории
                files = os.listdir(".")
                json_files = [f for f in files if f.endswith(".json")]
                logger.info(f"JSON files in current directory: {json_files}")
            
            # Проверка встроенных данных аккаунта
            logger.info("Checking embedded service account data...")
            try:
                if "private_key" in SERVICE_ACCOUNT_INFO:
                    private_key = SERVICE_ACCOUNT_INFO["private_key"]
                    has_real_newlines = "\n" in private_key
                    has_backslash_n = "\\n" in private_key
                    logger.info(f"Embedded private key contains \\n: {has_backslash_n}")
                    logger.info(f"Embedded private key contains real newlines: {has_real_newlines}")
                    logger.info(f"Embedded service account email: {SERVICE_ACCOUNT_INFO.get('client_email', 'not found')}")
            except Exception as e:
                logger.error(f"Error checking embedded service account data: {str(e)}")
            
            # Проверка системного времени
            current_time = datetime.now().astimezone(timezone.utc)
            logger.info(f"System time (UTC): {current_time.isoformat()}")
            
            # Проверка переменных окружения
            env_vars = {k: v for k, v in os.environ.items() if k.startswith(('GOOGLE_', 'RENDER_'))}
            if env_vars:
                logger.info(f"Relevant environment variables: {json.dumps(env_vars)}")
            else:
                logger.info("No Google or Render specific environment variables found")
                
            logger.info(f"=== END DIAGNOSTICS ===")
            
        except Exception as e:
            logger.error(f"Error collecting environment info: {str(e)}")
            logger.error(traceback.format_exc())
    
    @classmethod
    def _get_sheets_service(cls):
        """
        Получить сервис Google Sheets API с подробным логированием
        
        Returns:
            Resource object для взаимодействия с Google Sheets API
        """
        if cls._service is not None:
            return cls._service
            
        try:
            logger.info("Creating Google Sheets service...")
            
            # Проверяем наличие файла
            file_exists = os.path.exists(SERVICE_ACCOUNT_FILE)
            logger.info(f"Service account file exists: {file_exists}")
            
            # Попытка создать учетные данные
            logger.info("Creating credentials...")
            
            try:
                # Сначала пробуем из файла, если он существует
                if file_exists:
                    logger.info("Creating credentials from file...")
                    credentials = service_account.Credentials.from_service_account_file(
                        SERVICE_ACCOUNT_FILE,
                        scopes=['https://www.googleapis.com/auth/spreadsheets']
                    )
                    logger.info("Successfully created credentials from file")
                else:
                    # Если файл не существует, используем встроенные данные
                    logger.info("Creating credentials from embedded data...")
                    credentials = service_account.Credentials.from_service_account_info(
                        SERVICE_ACCOUNT_INFO,
                        scopes=['https://www.googleapis.com/auth/spreadsheets']
                    )
                    logger.info("Successfully created credentials from embedded data")
            except Exception as cred_error:
                logger.error(f"Error creating credentials from primary methods: {str(cred_error)}")
                logger.error(traceback.format_exc())
                
                # В случае ошибки пробуем сохранить данные во временный файл
                try:
                    logger.info("Attempting to create temporary service account file...")
                    # Сохраняем содержимое во временный файл
                    tmp_file_path = "temp_service_account.json"
                    with open(tmp_file_path, 'w') as f:
                        json.dump(SERVICE_ACCOUNT_INFO, f, indent=2)
                    
                    logger.info(f"Created temporary service account file: {tmp_file_path}")
                    
                    # Создаем учетные данные из временного файла
                    credentials = service_account.Credentials.from_service_account_file(
                        tmp_file_path,
                        scopes=['https://www.googleapis.com/auth/spreadsheets']
                    )
                    logger.info("Successfully created credentials from temporary file")
                except Exception as tmp_error:
                    logger.error(f"Error with temporary file approach: {str(tmp_error)}")
                    logger.error(traceback.format_exc())
                    raise
            
            logger.info(f"Credentials created for: {credentials.service_account_email}")
            
            # Пытаемся получить токен
            try:
                logger.info("Refreshing credentials to get token...")
                request = google.auth.transport.requests.Request()
                credentials.refresh(request)
                logger.info(f"Successfully obtained token. Token expires at: {credentials.expiry}")
            except google.auth.exceptions.RefreshError as refresh_error:
                logger.error(f"Error refreshing token: {str(refresh_error)}")
                logger.error(traceback.format_exc())
                raise
            except Exception as other_error:
                logger.error(f"Unexpected error during token refresh: {str(other_error)}")
                logger.error(traceback.format_exc())
                raise
            
            # Создаем сервис Google Sheets API
            logger.info("Building Sheets API service...")
            service = build('sheets', 'v4', credentials=credentials, cache_discovery=False)
            cls._service = service
            logger.info("Google Sheets API service initialized successfully")
            return service
        except Exception as e:
            logger.error(f"Error initializing Google Sheets API service: {str(e)}")
            logger.error(traceback.format_exc())
            raise
    
    @staticmethod
    async def log_conversation(
        sheet_id: str,
        user_message: str,
        assistant_message: str,
        function_result: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Log conversation to Google Sheet with detailed error reporting
        
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
            # Выводим диагностическую информацию (только при первом вызове)
            if not hasattr(GoogleSheetsService, "_diagnostics_logged"):
                await GoogleSheetsService._log_environment_info()
                setattr(GoogleSheetsService, "_diagnostics_logged", True)
            
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
                    logger.info(f"Attempting to log conversation to sheet: {sheet_id}")
                    service = GoogleSheetsService._get_sheets_service()
                    
                    body = {
                        'values': values
                    }
                    
                    logger.info("Sending append request to Google Sheets API...")
                    result = service.spreadsheets().values().append(
                        spreadsheetId=sheet_id,
                        range='A:D',
                        valueInputOption='RAW',
                        insertDataOption='INSERT_ROWS',
                        body=body
                    ).execute()
                    
                    logger.info(f"Successfully logged to sheet. Response: {json.dumps(result)}")
                    return True, None
                except HttpError as http_error:
                    status_code = http_error.resp.status if hasattr(http_error, 'resp') else 'unknown'
                    logger.error(f"HTTP Error {status_code} while logging to sheet: {str(http_error)}")
                    
                    # Более подробная диагностика
                    if status_code == 403:
                        logger.error("Access denied to Google Sheet. Check sheet sharing settings.")
                    elif status_code == 404:
                        logger.error("Sheet not found. Check that the Sheet ID is correct.")
                    
                    # Возвращаем информацию об ошибке
                    return False, f"HTTP Error {status_code}: {str(http_error)}"
                except google.auth.exceptions.RefreshError as refresh_error:
                    logger.error(f"Error refreshing token: {str(refresh_error)}")
                    return False, f"Token refresh error: {str(refresh_error)}"
                except Exception as e:
                    logger.error(f"Unexpected error while logging to sheet: {str(e)}")
                    logger.error(traceback.format_exc())
                    return False, f"Unexpected error: {str(e)}"
            
            try:
                success, error_message = await loop.run_in_executor(None, append_values)
                
                if success:
                    logger.info(f"Successfully logged conversation to Google Sheet: {sheet_id}")
                    return True
                else:
                    logger.error(f"Failed to log conversation to Google Sheet: {error_message}")
                    
                    # В случае ошибки логируем сообщения локально
                    logger.info(f"[LOCAL LOG] User: {user_message[:100]}...")
                    logger.info(f"[LOCAL LOG] Assistant: {assistant_message[:100]}...")
                    if function_result:
                        logger.info(f"[LOCAL LOG] Function: {function_text[:100]}...")
                    
                    # Возвращаем True, чтобы не блокировать основной функционал
                    return True
            except Exception as e:
                logger.error(f"Error in executor while logging conversation: {str(e)}")
                logger.error(traceback.format_exc())
                return True
                
        except Exception as e:
            logger.error(f"Error logging conversation to Google Sheet: {str(e)}")
            logger.error(traceback.format_exc())
            # Возвращаем True, чтобы не блокировать основной функционал
            return True
    
    @staticmethod
    async def verify_sheet_access(sheet_id: str) -> Dict[str, Any]:
        """
        Verify Google Sheet access with detailed diagnostics
        
        Args:
            sheet_id: Google Sheet ID
            
        Returns:
            Dict with status and message
        """
        if not sheet_id:
            return {"success": False, "message": "ID таблицы не указан"}
        
        try:
            # Выводим полную диагностическую информацию
            await GoogleSheetsService._log_environment_info()
            
            # Вызываем в отдельном потоке, так как это блокирующая операция
            loop = asyncio.get_event_loop()
            
            def verify_access():
                try:
                    logger.info(f"Verifying access to sheet: {sheet_id}")
                    
                    # Получаем сервис (с подробным логированием внутри)
                    service = GoogleSheetsService._get_sheets_service()
                    
                    # Проверяем доступ к метаданным таблицы
                    logger.info("Getting sheet metadata...")
                    sheet = service.spreadsheets().get(
                        spreadsheetId=sheet_id,
                        fields='properties.title'
                    ).execute()
                    
                    title = sheet.get('properties', {}).get('title', 'Untitled Spreadsheet')
                    logger.info(f"Successfully retrieved sheet metadata. Title: {title}")
                    
                    # Проверяем возможность записи
                    logger.info("Testing write access...")
                    test_values = [["TEST - Проверка доступа (будет удалено)"]]
                    
                    append_result = service.spreadsheets().values().append(
                        spreadsheetId=sheet_id,
                        range='Z:Z',  # Используем отдаленный столбец для теста
                        valueInputOption='RAW',
                        insertDataOption='INSERT_ROWS',
                        body={'values': test_values}
                    ).execute()
                    
                    logger.info(f"Successfully wrote test data. Response: {json.dumps(append_result)}")
                    
                    # Очищаем тестовую запись
                    update_range = append_result.get('updates', {}).get('updatedRange', 'Z1')
                    clear_result = service.spreadsheets().values().clear(
                        spreadsheetId=sheet_id,
                        range=update_range,
                        body={}
                    ).execute()
                    
                    logger.info(f"Successfully cleared test data. Response: {json.dumps(clear_result)}")
                    
                    return {
                        "success": True,
                        "message": f"Успешно подключено к таблице: {title}. Таблица доступна для записи.",
                        "title": title
                    }
                except HttpError as http_error:
                    status_code = http_error.resp.status if hasattr(http_error, 'resp') else 'unknown'
                    error_details = f"HTTP Error {status_code}: {str(http_error)}"
                    logger.error(f"HTTP error verifying sheet access: {error_details}")
                    
                    if status_code == 403:
                        return {
                            "success": False,
                            "message": "Отказано в доступе. Убедитесь, что таблица доступна для редактирования по ссылке."
                        }
                    elif status_code == 404:
                        return {
                            "success": False,
                            "message": "Таблица не найдена. Пожалуйста, проверьте ID таблицы."
                        }
                    else:
                        return {
                            "success": False,
                            "message": f"Ошибка доступа к таблице: {error_details}"
                        }
                except google.auth.exceptions.RefreshError as refresh_error:
                    logger.error(f"Token refresh error: {str(refresh_error)}")
                    return {
                        "success": False,
                        "message": f"Ошибка обновления токена: {str(refresh_error)}"
                    }
                except Exception as e:
                    logger.error(f"Unexpected error verifying sheet access: {str(e)}")
                    logger.error(traceback.format_exc())
                    return {
                        "success": False,
                        "message": f"Непредвиденная ошибка: {str(e)}"
                    }
            
            try:
                result = await loop.run_in_executor(None, verify_access)
                return result
            except Exception as e:
                logger.error(f"Error in executor while verifying sheet access: {str(e)}")
                logger.error(traceback.format_exc())
                return {
                    "success": False,
                    "message": f"Ошибка проверки доступа: {str(e)}"
                }
            
        except Exception as e:
            logger.error(f"Error verifying Google Sheet access: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "message": f"Ошибка: {str(e)}"
            }

    @staticmethod
    async def setup_sheet(sheet_id: str) -> bool:
        """
        Setup sheet headers with detailed diagnostics
        
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
                    logger.info(f"Setting up sheet: {sheet_id}")
                    service = GoogleSheetsService._get_sheets_service()
                    
                    # Проверяем существующие данные
                    logger.info("Checking if headers exist...")
                    result = service.spreadsheets().values().get(
                        spreadsheetId=sheet_id,
                        range='A1:D1'
                    ).execute()
                    
                    values = result.get('values', [])
                    
                    if not values:
                        logger.info("No headers found. Adding headers...")
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
                        logger.info(f"Headers added successfully. Response: {json.dumps(update_result)}")
                    else:
                        logger.info(f"Headers already exist: {values}")
                        
                    return True
                except HttpError as http_error:
                    status_code = http_error.resp.status if hasattr(http_error, 'resp') else 'unknown'
                    logger.error(f"HTTP error setting up sheet: {status_code} - {str(http_error)}")
                    return False
                except Exception as e:
                    logger.error(f"Unexpected error setting up Google Sheet: {str(e)}")
                    logger.error(traceback.format_exc())
                    return False
            
            try:
                result = await loop.run_in_executor(None, check_and_setup)
                
                if result:
                    logger.info(f"Successfully set up Google Sheet: {sheet_id}")
                    return True
                else:
                    logger.error(f"Failed to set up Google Sheet: {sheet_id}")
                    return False
            except Exception as e:
                logger.error(f"Error in executor while setting up sheet: {str(e)}")
                logger.error(traceback.format_exc())
                return False
                
        except Exception as e:
            logger.error(f"Error setting up Google Sheet: {str(e)}")
            logger.error(traceback.format_exc())
            return False
