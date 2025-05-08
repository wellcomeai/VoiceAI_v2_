"""
Google Sheets service для WellcomeAI application.
С расширенной диагностикой JWT подписи для отладки проблем.
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
import hashlib

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
    """Service for Google Sheets logging with enhanced JWT signature debugging"""
    
    _service = None
    
    @classmethod
    def _add_debug_hooks(cls):
        """Добавляет отладочные хуки для перехвата JWT до отправки в Google API"""
        try:
            import google.oauth2._client
            original_jwt_grant = google.oauth2._client.jwt_grant
            
            def debug_jwt_grant(*args, **kwargs):
                """Отладочная обертка для jwt_grant"""
                logger.info("=== Debugging actual JWT about to be sent to Google ===")
                
                # Декодируем JWT для проверки payload
                import jwt
                if len(args) > 1 and isinstance(args[1], str):
                    try:
                        token = args[1]
                        header = jwt.get_unverified_header(token)
                        payload = jwt.decode(token, options={"verify_signature": False})
                        logger.info(f"JWT Header: {header}")
                        logger.info(f"JWT Payload: {payload}")
                        
                        # Проверка времени
                        exp = payload.get('exp', 0)
                        iat = payload.get('iat', 0)
                        if exp and iat:
                            logger.info(f"JWT lifetime: {exp - iat} seconds")
                            
                            # Показываем времена в разных форматах
                            from datetime import datetime
                            iat_dt = datetime.fromtimestamp(iat)
                            exp_dt = datetime.fromtimestamp(exp)
                            logger.info(f"JWT iat: {iat_dt.isoformat()} (timestamp: {iat})")
                            logger.info(f"JWT exp: {exp_dt.isoformat()} (timestamp: {exp})")
                            
                            # Проверка соответствия времени
                            now = time.time()
                            if iat > now + 300:  # Если iat больше текущего времени + 5 минут
                                logger.warning(f"⚠️ JWT iat is in the future! Current time: {datetime.fromtimestamp(now).isoformat()} (timestamp: {now})")
                        
                        # Проверка формата поля aud
                        aud = payload.get('aud', '')
                        logger.info(f"JWT aud: {aud}")
                        if aud != "https://oauth2.googleapis.com/token":
                            logger.warning(f"⚠️ JWT aud field might be incorrect. Expected: https://oauth2.googleapis.com/token")
                        
                        # Проверка формата поля sub и iss
                        sub = payload.get('sub', '')
                        iss = payload.get('iss', '')
                        logger.info(f"JWT sub: {sub}")
                        logger.info(f"JWT iss: {iss}")
                        if iss and iss != SERVICE_ACCOUNT_INFO.get("client_email"):
                            logger.warning(f"⚠️ JWT iss doesn't match client_email. Expected: {SERVICE_ACCOUNT_INFO.get('client_email')}")
                    except Exception as e:
                        logger.error(f"Error decoding JWT: {e}")
                        logger.error(traceback.format_exc())
                
                # Вызываем оригинальную функцию
                try:
                    return original_jwt_grant(*args, **kwargs)
                except Exception as e:
                    logger.error(f"Error in original JWT grant function: {e}")
                    logger.error(traceback.format_exc())
                    raise
            
            # Заменяем оригинальную функцию нашей отладочной версией
            google.oauth2._client.jwt_grant = debug_jwt_grant
            logger.info("JWT debug hooks installed")
        except Exception as e:
            logger.error(f"Failed to install JWT debug hooks: {e}")
            logger.error(traceback.format_exc())
    
    @staticmethod
    async def _deep_jwt_diagnostics():
        """Подробная диагностика проблем с JWT подписью"""
        logger.info("=== ENHANCED JWT SIGNATURE DIAGNOSTICS ===")
        
        # Проверка приватного ключа в SERVICE_ACCOUNT_INFO
        try:
            from cryptography.hazmat.primitives.serialization import load_pem_private_key
            from cryptography.hazmat.backends import default_backend
            
            logger.info("Testing private key format with cryptography...")
            
            # Извлечь приватный ключ
            private_key = SERVICE_ACCOUNT_INFO.get("private_key", "")
            
            # Проверить наличие переносов строк
            real_newlines_count = private_key.count("\n")
            logger.info(f"Real newlines count in private_key: {real_newlines_count}")
            
            # Проверить, корректен ли ключ для парсинга
            try:
                # Попытка загрузить PEM
                key_bytes = private_key.encode('utf-8')
                loaded_key = load_pem_private_key(
                    key_bytes, 
                    password=None, 
                    backend=default_backend()
                )
                logger.info("✅ Successfully parsed private key with cryptography")
                
                # Вычисляем MD5 хеш для идентификации ключа (без прямого логирования)
                key_hash = hashlib.md5(key_bytes).hexdigest()
                logger.info(f"Private key MD5 hash: {key_hash}")
                
            except Exception as e:
                logger.error(f"❌ Failed to parse private key: {e}")
                
                # Показать формат начала и конца ключа для диагностики
                if private_key:
                    start = private_key[:40]
                    end = private_key[-40:]
                    logger.info(f"Key starts with: {start}")
                    logger.info(f"Key ends with: {end}")
        except ImportError:
            logger.info("cryptography library not available for key validation")
        
        # Проверка подписи JWT вручную
        try:
            import jwt
            
            logger.info("Testing manual JWT creation...")
            
            # Создаем простой тестовый токен с правильной аудиторией
            payload = {
                "iss": SERVICE_ACCOUNT_INFO.get("client_email", ""),
                "scope": "https://www.googleapis.com/auth/spreadsheets",
                "aud": "https://oauth2.googleapis.com/token",
                "exp": int(time.time()) + 3600,
                "iat": int(time.time())
            }
            
            try:
                # Попытка подписать JWT
                private_key = SERVICE_ACCOUNT_INFO.get("private_key", "")
                token = jwt.encode(
                    payload,
                    private_key,
                    algorithm="RS256",
                    headers={"kid": SERVICE_ACCOUNT_INFO.get("private_key_id", "")}
                )
                logger.info("✅ Successfully created test JWT token")
                
                # Проверяем корректность алгоритма
                decoded_header = jwt.get_unverified_header(token)
                logger.info(f"JWT header: {decoded_header}")
                
                # Проверяем содержимое токена
                decoded = jwt.decode(token, options={"verify_signature": False})
                logger.info(f"JWT payload: {decoded}")
                
                # Проверка системного времени
                curr_time = int(time.time())
                logger.info(f"Current timestamp: {curr_time}")
                logger.info(f"Token iat timestamp: {decoded.get('iat')}")
                logger.info(f"Token exp timestamp: {decoded.get('exp')}")
                
                # Проверяем отклонение времени
                time_diff = abs(curr_time - decoded.get('iat', 0))
                if time_diff > 300:  # Отличие больше 5 минут
                    logger.warning(f"⚠️ Large time difference detected: {time_diff} seconds")
                
            except Exception as e:
                logger.error(f"❌ Failed to create test JWT: {e}")
                logger.error(traceback.format_exc())
        except ImportError:
            logger.info("PyJWT library not available for manual JWT testing")
            
        # Вывод информации о системном времени
        logger.info(f"System time: {datetime.now().isoformat()}")
        logger.info(f"UTC time: {datetime.utcnow().isoformat()}")
        logger.info(f"Timezone-aware time: {datetime.now(timezone.utc).isoformat()}")
        logger.info(f"Timestamp: {int(time.time())}")
        
        logger.info("=== END JWT DIAGNOSTICS ===")
    
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
                logger.info(f"Last modified: {datetime.fromtimestamp(file_stat.st_mtime).isoformat()}")
                
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
                                if field == "private_key":
                                    # Подробная диагностика приватного ключа
                                    pk = key_data[field]
                                    pk_lines = pk.split("\n")
                                    logger.info(f"Private key contains {len(pk_lines)} lines")
                                    logger.info(f"First line: {pk_lines[0]}")
                                    logger.info(f"Last line: {pk_lines[-1]}")
                                    
                                    # Проверяем наличие переносов строк
                                    has_real_newlines = "\n" in pk
                                    has_backslash_n = "\\n" in pk
                                    logger.info(f"Private key contains \\n: {has_backslash_n}")
                                    logger.info(f"Private key contains real newlines: {has_real_newlines}")
                                    
                                    # Вычисляем MD5 хеш для сравнения
                                    key_hash = hashlib.md5(pk.encode('utf-8')).hexdigest()
                                    logger.info(f"File private key MD5 hash: {key_hash}")
                                    
                                    embedded_key = SERVICE_ACCOUNT_INFO.get("private_key", "")
                                    embedded_key_hash = hashlib.md5(embedded_key.encode('utf-8')).hexdigest()
                                    logger.info(f"Embedded private key MD5 hash: {embedded_key_hash}")
                                    logger.info(f"Keys match: {key_hash == embedded_key_hash}")
                                else:
                                    value = key_data[field]
                                    # Безопасно логируем значения
                                    if field in ["client_email", "project_id", "type"]:
                                        logger.info(f"Key file contains {field}: {value}")
                                    else:
                                        logger.info(f"Key file contains {field}: (value present)")
                            else:
                                logger.error(f"Key file missing required field: {field}")
                    except json.JSONDecodeError as e:
                        logger.error(f"Key file is not valid JSON: {str(e)}")
                        # Показываем часть содержимого для диагностики
                        logger.error(f"Key file content (first 100 chars): {key_content[:100]}")
                except Exception as e:
                    logger.error(f"Error reading key file: {str(e)}")
            else:
                # Попытка найти файлы в текущей директории и родительских
                logger.info("Searching for service account file in accessible directories")
                
                directories_to_check = [
                    ".",
                    "..",
                    os.path.dirname(os.getcwd()),
                    "/app",  # Типичное место для Render
                    os.path.expanduser("~"),
                ]
                
                for directory in directories_to_check:
                    try:
                        if os.path.exists(directory):
                            files = os.listdir(directory)
                            json_files = [f for f in files if f.endswith(".json")]
                            if json_files:
                                logger.info(f"JSON files in {directory}: {json_files}")
                            else:
                                logger.info(f"No JSON files found in {directory}")
                    except (PermissionError, FileNotFoundError) as e:
                        logger.info(f"Cannot access {directory}: {e}")
            
            # Проверка встроенных данных аккаунта
            logger.info("Checking embedded service account data...")
            try:
                # Проверяем наличие всех необходимых полей
                required_fields = ["type", "project_id", "private_key_id", "private_key", 
                                  "client_email", "client_id"]
                
                for field in required_fields:
                    if field in SERVICE_ACCOUNT_INFO:
                        if field == "private_key":
                            private_key = SERVICE_ACCOUNT_INFO["private_key"]
                            has_real_newlines = "\n" in private_key
                            has_backslash_n = "\\n" in private_key
                            logger.info(f"Embedded private key contains \\n: {has_backslash_n}")
                            logger.info(f"Embedded private key contains real newlines: {has_real_newlines}")
                            
                            # Подсчет реальных переносов строк
                            newline_count = private_key.count("\n")
                            logger.info(f"Embedded private key contains {newline_count} newlines")
                            
                            if newline_count < 10:
                                logger.warning("⚠️ Private key has fewer newlines than expected. This may cause JWT signature problems.")
                        elif field in ["client_email", "project_id", "type"]:
                            logger.info(f"Embedded service account {field}: {SERVICE_ACCOUNT_INFO.get(field)}")
                        else:
                            logger.info(f"Embedded service account has {field} field")
                    else:
                        logger.error(f"Embedded service account missing required field: {field}")
            except Exception as e:
                logger.error(f"Error checking embedded service account data: {str(e)}")
            
            # Проверка системного времени
            current_time = datetime.now().astimezone(timezone.utc)
            logger.info(f"System time (UTC): {current_time.isoformat()}")
            logger.info(f"Timestamp: {int(time.time())}")
            
            # Проверка переменных окружения
            env_vars = {k: v for k, v in os.environ.items() if k.startswith(('GOOGLE_', 'RENDER_'))}
            if env_vars:
                logger.info(f"Relevant environment variables: {json.dumps(env_vars)}")
            else:
                logger.info("No Google or Render specific environment variables found")
            
            # Вывод информации о Python ENV
            logger.info(f"Python environment variables:")
            logger.info(f"PYTHONPATH: {os.environ.get('PYTHONPATH', 'Not set')}")
            logger.info(f"sys.path: {sys.path}")
            
            logger.info(f"=== END DIAGNOSTICS ===")
            
        except Exception as e:
            logger.error(f"Error collecting environment info: {str(e)}")
            logger.error(traceback.format_exc())
    
    @classmethod
    def _normalize_private_key(cls, private_key: str) -> str:
        """
        Нормализует приватный ключ, заменяя литералы `\\n` на настоящие переносы строк.
        
        Args:
            private_key: Строка приватного ключа
            
        Returns:
            Нормализованный приватный ключ
        """
        if not private_key:
            return ""
            
        # Если в ключе есть буквальные \n (а не переносы строк), заменяем их
        if "\\n" in private_key and "\n" not in private_key:
            logger.info("Converting literal \\n to real newlines in private key")
            return private_key.replace("\\n", "\n")
            
        return private_key
    
    @classmethod
    def _prepare_temp_sa_file(cls, output_path: str = "temp_service_account.json") -> Optional[str]:
        """
        Создает временный файл сервисного аккаунта с нормализованным приватным ключом.
        
        Args:
            output_path: Путь для создания временного файла
            
        Returns:
            Путь к созданному файлу или None в случае ошибки
        """
        try:
            # Копируем данные аккаунта
            sa_data = dict(SERVICE_ACCOUNT_INFO)
            
            # Нормализуем приватный ключ
            if "private_key" in sa_data:
                sa_data["private_key"] = cls._normalize_private_key(sa_data["private_key"])
            
            # Записываем во временный файл
            with open(output_path, 'w') as f:
                json.dump(sa_data, f, indent=2)
                
            logger.info(f"Created temporary service account file at {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"Error creating temporary service account file: {str(e)}")
            return None
    
    @classmethod
    def _get_sheets_service(cls):
        """
        Получить сервис Google Sheets API с подробным логированием
        
        Returns:
            Resource object для взаимодействия с Google Sheets API
        """
        # Добавляем отладочные хуки в начале
        cls._add_debug_hooks()
        
        if cls._service is not None:
            return cls._service
            
        try:
            logger.info("Creating Google Sheets service...")
            
            # Проверяем наличие файла
            file_exists = os.path.exists(SERVICE_ACCOUNT_FILE)
            logger.info(f"Service account file exists: {file_exists}")
            
            # Попытка создать учетные данные
            logger.info("Creating credentials...")
            
            # Пробуем разные способы создания credentials
            credentials = None
            errors = []
            
            # 1. Пробуем из файла если он существует
            if file_exists:
                try:
                    logger.info("Attempting to create credentials from file...")
                    credentials = service_account.Credentials.from_service_account_file(
                        SERVICE_ACCOUNT_FILE,
                        scopes=['https://www.googleapis.com/auth/spreadsheets']
                    )
                    logger.info("Successfully created credentials from file")
                except Exception as e:
                    errors.append(f"Error from file: {str(e)}")
                    logger.error(f"Failed to create credentials from file: {str(e)}")
            
            # 2. Пробуем из встроенных данных с нормализацией приватного ключа
            if credentials is None:
                try:
                    logger.info("Attempting to create credentials from embedded info...")
                    
                    # Создаем копию с нормализованным ключом
                    sa_info = dict(SERVICE_ACCOUNT_INFO)
                    if "private_key" in sa_info:
                        sa_info["private_key"] = cls._normalize_private_key(sa_info["private_key"])
                    
                    credentials = service_account.Credentials.from_service_account_info(
                        sa_info,
                        scopes=['https://www.googleapis.com/auth/spreadsheets']
                    )
                    logger.info("Successfully created credentials from embedded data")
                except Exception as e:
                    errors.append(f"Error from embedded info: {str(e)}")
                    logger.error(f"Failed to create credentials from embedded info: {str(e)}")
            
            # 3. Пробуем через временный файл
            if credentials is None:
                try:
                    logger.info("Attempting to create credentials via temporary file...")
                    temp_file = cls._prepare_temp_sa_file()
                    if temp_file and os.path.exists(temp_file):
                        credentials = service_account.Credentials.from_service_account_file(
                            temp_file,
                            scopes=['https://www.googleapis.com/auth/spreadsheets']
                        )
                        logger.info("Successfully created credentials from temporary file")
                except Exception as e:
                    errors.append(f"Error from temp file: {str(e)}")
                    logger.error(f"Failed to create credentials from temporary file: {str(e)}")
            
            # Если все способы не сработали, запускаем глубокую диагностику JWT
            if credentials is None:
                logger.error(f"All credential creation methods failed: {errors}")
                
                # Запускаем синхронно (в текущем потоке) для отладки
                loop = asyncio.new_event_loop()
                loop.run_until_complete(cls._deep_jwt_diagnostics())
                loop.close()
                
                raise Exception(f"Failed to create credentials after trying all methods")
            
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
                
                # Добавляем детальную информацию об ошибке
                if hasattr(refresh_error, 'response') and refresh_error.response:
                    try:
                        response = refresh_error.response
                        logger.error(f"Token refresh response status: {response.status}")
                        logger.error(f"Token refresh response headers: {response.headers}")
                        logger.error(f"Token refresh response body: {response.data.decode('utf-8')}")
                    except:
                        logger.error("Could not extract details from refresh error response")
                
                # Запускаем глубокую диагностику JWT при ошибке обновления токена
                loop = asyncio.new_event_loop()
                loop.run_until_complete(cls._deep_jwt_diagnostics())
                loop.close()
                
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
                    
                    # Проверим формат и содержимое приватного ключа
                    loop = asyncio.new_event_loop()
                    loop.run_until_complete(GoogleSheetsService._deep_jwt_diagnostics())
                    loop.close()
                    
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
