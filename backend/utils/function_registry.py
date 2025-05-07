import json
import inspect
import asyncio
from typing import Dict, Any, Callable, Optional, List
import requests
import aiohttp

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
        
        # Используем aiohttp для асинхронных запросов
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data, timeout=10) as response:
                    response_text = await response.text()
                    return {
                        "status": response.status,
                        "message": "Webhook sent successfully",
                        "response": response_text[:200]  # Ограничиваем размер ответа
                    }
        except:
            # Если aiohttp не работает, используем обычный requests
            response = requests.post(
                url, 
                json=data,
                timeout=10,
                headers={"Content-Type": "application/json"}
            )
            
            # Возвращаем результат
            return {
                "status": response.status_code,
                "message": "Webhook sent successfully",
                "response": response.text[:200]  # Ограничиваем размер ответа
            }
    except Exception as e:
        logger.error(f"Ошибка при отправке вебхука: {e}")
        return {"error": f"Webhook error: {str(e)}"}
