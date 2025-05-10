import json
import inspect
import asyncio
import importlib.util
from typing import Dict, Any, Callable, Optional, List
import sys
import traceback
import re

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
                    "description": "URL вебхука для отправки данных (если не указан, будет извлечен из системных инструкций)"
                },
                "event": {
                    "type": "string",
                    "description": "Код события (если не указан, будет извлечен из системных инструкций или использовано значение по умолчанию)"
                },
                "payload": {
                    "type": "object",
                    "description": "Произвольные данные для отправки. Например: {\"name\": \"John\", \"age\": 30}"
                }
            },
            "required": []  // URL и event могут быть извлечены из системных инструкций
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
        # Логируем детали выполнения функции
        logger.info(f"Выполнение функции '{function_name}' с аргументами: {json.dumps(arguments, ensure_ascii=False)}")
        
        # Проверяем, является ли функция асинхронной
        if inspect.iscoroutinefunction(func):
            result = await func(arguments, assistant_config, client_id)
        else:
            # Запускаем синхронную функцию в отдельном потоке
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, lambda: func(arguments, assistant_config, client_id)
            )
        
        # Логируем результат выполнения
        logger.info(f"Результат выполнения функции '{function_name}': {json.dumps(result, ensure_ascii=False)}")
        
        return result
    except Exception as e:
        logger.error(f"Ошибка выполнения функции '{function_name}': {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {"error": str(e)}

# Проверка доступности модулей
def is_module_available(module_name):
    """Проверяет, доступен ли модуль для импорта"""
    try:
        # Проверка на уже импортированные модули
        if module_name in sys.modules:
            return True
            
        # Проверка возможности импорта без фактического импорта
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, AttributeError):
        return False

# Функция для отправки HTTP-запроса с использованием доступных библиотек
async def send_http_request(url, data, timeout=10):
    """
    Отправляет HTTP POST запрос, используя доступные библиотеки
    
    Args:
        url: URL для запроса
        data: Данные для отправки (будут преобразованы в JSON)
        timeout: Таймаут в секундах
        
    Returns:
        Результат запроса
    """
    logger.info(f"Sending HTTP request to URL: {url}")
    logger.info(f"Request data: {json.dumps(data, ensure_ascii=False)}")
    
    # Пробуем использовать aiohttp
    if is_module_available("aiohttp"):
        import aiohttp
        try:
            logger.info("Using aiohttp for the request")
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data, timeout=timeout) as response:
                    response_text = await response.text()
                    result = {
                        "status": response.status,
                        "message": "Webhook sent successfully",
                        "response": response_text[:200]  # Ограничиваем размер ответа
                    }
                    logger.info(f"Request result: {json.dumps(result, ensure_ascii=False)}")
                    return result
        except Exception as e:
            logger.error(f"Ошибка при отправке запроса через aiohttp: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            # Если возникла ошибка, продолжаем с другими методами
    
    # Пробуем использовать requests
    if is_module_available("requests"):
        import requests
        try:
            logger.info("Using requests for the request")
            # Выполняем синхронный запрос в отдельном потоке
            loop = asyncio.get_event_loop()
            def make_request():
                try:
                    response = requests.post(
                        url, 
                        json=data,
                        timeout=timeout,
                        headers={"Content-Type": "application/json"}
                    )
                    return {
                        "status": response.status_code,
                        "message": "Webhook sent successfully",
                        "response": response.text[:200]  # Ограничиваем размер ответа
                    }
                except Exception as e:
                    logger.error(f"Error in requests.post: {e}")
                    return {"error": str(e)}
                    
            result = await loop.run_in_executor(None, make_request)
            logger.info(f"Request result: {json.dumps(result, ensure_ascii=False)}")
            return result
        except Exception as e:
            logger.error(f"Ошибка при отправке запроса через requests: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            # Если возникла ошибка, продолжаем с другими методами
    
    # Запасной вариант: используем стандартную библиотеку urllib
    try:
        import urllib.request
        import urllib.error
        import ssl
        
        logger.info("Using urllib for the request")
        # Преобразуем данные в JSON
        data_json = json.dumps(data).encode('utf-8')
        
        # Создаем запрос
        req = urllib.request.Request(
            url,
            data=data_json,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        
        # Создаем контекст SSL (игнорируем проверку сертификатов)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        # Выполняем запрос в отдельном потоке
        loop = asyncio.get_event_loop()
        
        def make_request():
            try:
                with urllib.request.urlopen(req, timeout=timeout, context=ctx) as response:
                    response_data = response.read().decode('utf-8')
                    result = {
                        "status": response.status,
                        "message": "Webhook sent successfully",
                        "response": response_data[:200]  # Ограничиваем размер ответа
                    }
                    return result
            except urllib.error.HTTPError as e:
                logger.error(f"HTTPError with urllib: {e}")
                return {
                    "status": e.code,
                    "error": str(e),
                    "response": e.read().decode('utf-8')[:200] if hasattr(e, 'read') else ""
                }
            except Exception as e:
                logger.error(f"General error with urllib: {e}")
                return {
                    "status": 0,
                    "error": str(e),
                    "response": ""
                }
                
        result = await loop.run_in_executor(None, make_request)
        logger.info(f"Request result: {json.dumps(result, ensure_ascii=False)}")
        return result
    except Exception as e:
        logger.error(f"Ошибка при использовании urllib: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {
            "status": 0,
            "error": f"Failed to send webhook: {str(e)}",
            "response": ""
        }

# Регистрация встроенных функций
@register_function("send_webhook")
async def send_webhook(args, assistant_config=None, client_id=None):
    """
    Отправляет данные на внешний сервер через указанный URL.
    
    Args:
        args: Словарь аргументов:
            - url: Полный URL вебхука (опционально, если указан в системных инструкциях)
            - event: Код события (опционально, если указан в системных инструкциях)
            - payload: Произвольные данные (опционально)
            
    Returns:
        Результат выполнения вебхука
    """
    try:
        # Извлечение URL и event из аргументов или системных инструкций
        url = args.get("url")
        event = args.get("event")
        payload = args.get("payload", {})
        
        logger.info(f"send_webhook вызван с аргументами: url={url}, event={event}, payload={payload}")
        
        # Извлечение URL из системных инструкций, если он не указан в аргументах
        if not url and assistant_config and hasattr(assistant_config, "system_prompt"):
            system_prompt = assistant_config.system_prompt
            
            # Попытка найти URL в системных инструкциях с помощью регулярного выражения
            url_match = re.search(r'https?://[^\s"\']+', system_prompt)
            if url_match:
                url = url_match.group(0)
                logger.info(f"URL извлечен из системных инструкций: {url}")
                
        # Проверка обязательных параметров
        if not url:
            logger.error("URL is required for send_webhook")
            return {"error": "URL is required", "status": "error"}
            
        # Извлечение event из системных инструкций, если он не указан в аргументах
        if not event and assistant_config and hasattr(assistant_config, "system_prompt"):
            system_prompt = assistant_config.system_prompt
            
            # Попытка найти event в системных инструкциях
            event_match = re.search(r'event\s*[-–—:]\s*(\w+(?:\s+\w+)*)', system_prompt)
            if event_match:
                event = event_match.group(1).strip()
                logger.info(f"Event извлечен из системных инструкций: {event}")
        
        if not event:
            # Значение event по умолчанию, если не удалось извлечь из инструкций
            event = "webhook_triggered"
            logger.info(f"Используется event по умолчанию: {event}")
            
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
        
        logger.info(f"Отправка вебхука на URL: {url}")
        logger.info(f"Данные вебхука: {json.dumps(data, ensure_ascii=False)}")
        
        # Отправляем запрос с помощью доступных библиотек
        result = await send_http_request(url, data)
        logger.info(f"Результат отправки вебхука: {json.dumps(result, ensure_ascii=False)}")
        
        # Добавляем оригинальные аргументы в результат
        result["original_args"] = {
            "url": url,
            "event": event,
            "payload": payload
        }
        
        return result
        
    except Exception as e:
        logger.error(f"Ошибка при отправке вебхука: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {"error": f"Webhook error: {str(e)}", "status": "error"}
