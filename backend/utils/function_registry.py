import json
import inspect
import asyncio
from typing import Dict, Any, Callable, Optional, List
import urllib.request
import urllib.error
import urllib.parse
import ssl
import socket
import sys

from backend.core.logging import get_logger
logger = get_logger(__name__)

# Реестр зарегистрированных функций
FUNCTION_REGISTRY = {}

# Описания функций для отображения в интерфейсе
FUNCTION_DEFINITIONS = {
    "send_webhook": {
        "name": "send_webhook",
        "description": "Отправляет данные на внешний вебхук (например, для n8n)",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL вебхука для отправки данных"
                },
                "event": {
                    "type": "string",
                    "description": "Код события (например, 'booking', 'request', 'notification')"
                },
                "payload": {
                    "type": "object",
                    "description": "Произвольные данные для отправки"
                }
            },
            "required": ["url", "event"]
        }
    }
}

def register_function(name: str):
    """
    Декоратор для регистрации функции.
    
    Args:
        name: Имя функции для регистрации
    """
    def decorator(func):
        FUNCTION_REGISTRY[name] = func
        logger.info(f"Функция '{name}' зарегистрирована")
        return func
    return decorator

def get_function_definitions() -> Dict[str, Dict[str, Any]]:
    """
    Возвращает определения всех зарегистрированных функций.
    
    Returns:
        Словарь с определениями функций
    """
    return FUNCTION_DEFINITIONS

def get_enabled_functions(assistant_functions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Формирует список описаний включенных функций для OpenAI API.
    
    Args:
        assistant_functions: Список функций ассистента
        
    Returns:
        Список описаний функций для OpenAI
    """
    if not assistant_functions:
        return []
    
    enabled_functions = []
    
    # Преобразуем формат для OpenAI API
    for func in assistant_functions:
        function_name = func.get("name")
        if function_name in FUNCTION_DEFINITIONS:
            enabled_functions.append(FUNCTION_DEFINITIONS[function_name])
    
    return enabled_functions

async def execute_function(
    function_name: str, 
    arguments: Dict[str, Any],
    assistant_config=None,
    client_id=None
) -> Dict[str, Any]:
    """
    Выполнить функцию из реестра.
    
    Args:
        function_name: Имя функции
        arguments: Аргументы функции
        assistant_config: Конфигурация ассистента
        client_id: ID клиента
        
    Returns:
        Результат выполнения функции
    """
    if function_name not in FUNCTION_REGISTRY:
        logger.error(f"Функция '{function_name}' не найдена в реестре")
        return {"error": f"Function '{function_name}' not found"}
    
    func = FUNCTION_REGISTRY[function_name]
    
    try:
        # Проверяем, является ли функция асинхронной
        if inspect.iscoroutinefunction(func):
            result = await func(arguments, assistant_config, client_id)
        else:
            # Запускаем синхронную функцию в отдельном потоке
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, lambda: func(arguments, assistant_config, client_id)
            )
        
        return result
    except Exception as e:
        logger.error(f"Ошибка выполнения функции '{function_name}': {e}")
        return {"error": str(e)}

# Функция для HTTP запросов с использованием стандартной библиотеки Python
def http_request(url, data=None, headers=None, method="GET", timeout=10):
    """
    Выполняет HTTP запрос с использованием стандартной библиотеки Python.
    
    Args:
        url: URL для запроса
        data: Данные для отправки
        headers: Заголовки запроса
        method: HTTP метод
        timeout: Таймаут в секундах
        
    Returns:
        Словарь с ответом сервера
    """
    try:
        headers = headers or {}
        
        # Подготовка данных
        if data is not None and isinstance(data, dict):
            data = json.dumps(data).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        
        # Создание запроса
        req = urllib.request.Request(
            url,
            data=data,
            headers=headers,
            method=method
        )
        
        # Игнорирование проверки SSL сертификатов (не рекомендуется для продакшена)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        # Выполнение запроса
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as response:
            # Чтение ответа
            response_data = response.read().decode('utf-8')
            status_code = response.status
            return {
                "status": status_code,
                "text": response_data,
                "headers": dict(response.info())
            }
            
    except urllib.error.HTTPError as e:
        # Обработка HTTP ошибок
        return {
            "status": e.code,
            "text": e.read().decode('utf-8') if hasattr(e, 'read') else str(e),
            "error": str(e)
        }
    except (urllib.error.URLError, socket.timeout) as e:
        # Обработка ошибок соединения
        return {
            "status": 0,
            "text": "",
            "error": str(e)
        }
    except Exception as e:
        # Обработка прочих ошибок
        return {
            "status": 0,
            "text": "",
            "error": str(e)
        }

# Асинхронная обертка для HTTP запросов
async def async_http_request(url, data=None, headers=None, method="GET", timeout=10):
    """
    Асинхронная обертка для HTTP запросов.
    
    Args:
        url: URL для запроса
        data: Данные для отправки
        headers: Заголовки запроса
        method: HTTP метод
        timeout: Таймаут в секундах
        
    Returns:
        Словарь с ответом сервера
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, 
        lambda: http_request(url, data, headers, method, timeout)
    )

# Регистрация встроенных функций
@register_function("send_webhook")
async def send_webhook(args, assistant_config=None, client_id=None):
    """
    Отправляет данные на внешний сервер через указанный URL.
    
    Args:
        args: Словарь аргументов:
            - url: Полный URL вебхука
            - event: Код события
            - payload: Произвольные данные (опционально)
            
    Returns:
        Результат выполнения вебхука
    """
    try:
        url = args.get("url")
        event = args.get("event")
        payload = args.get("payload", {})
        
        if not url:
            return {"error": "URL is required"}
        
        if not event:
            return {"error": "Event is required"}
            
        # Формируем данные для отправки
        data = {
            "event": event,
            "data": payload
        }
        
        # Добавляем информацию об ассистенте и клиенте, если доступно
        if assistant_config:
            data["assistant_id"] = str(assistant_config.id)
            data["assistant_name"] = assistant_config.name
            
        if client_id:
            data["client_id"] = client_id
        
        # Попытка использовать aiohttp, если доступен
        try:
            if 'aiohttp' in sys.modules or importlib.util.find_spec('aiohttp'):
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json=data, timeout=10) as response:
                        response_text = await response.text()
                        return {
                            "status": response.status,
                            "message": "Webhook sent successfully using aiohttp",
                            "response": response_text[:200]  # Ограничиваем размер ответа
                        }
        except (ImportError, NameError):
            logger.info("aiohttp не установлен, используем стандартную библиотеку")
        
        # Попытка использовать requests, если доступен
        try:
            if 'requests' in sys.modules or importlib.util.find_spec('requests'):
                import requests
                response = requests.post(
                    url, 
                    json=data,
                    timeout=10,
                    headers={"Content-Type": "application/json"}
                )
                return {
                    "status": response.status_code,
                    "message": "Webhook sent successfully using requests",
                    "response": response.text[:200]  # Ограничиваем размер ответа
                }
        except (ImportError, NameError):
            logger.info("requests не установлен, используем стандартную библиотеку")
        
        # Использование стандартной библиотеки как запасной вариант
        response = await async_http_request(
            url=url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        
        return {
            "status": response.get("status", 0),
            "message": "Webhook sent successfully using urllib",
            "response": response.get("text", "")[:200]  # Ограничиваем размер ответа
        }
    except Exception as e:
        logger.error(f"Ошибка при отправке вебхука: {e}")
        return {"error": f"Webhook error: {str(e)}"}
