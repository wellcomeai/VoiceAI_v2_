"""
WebSocket module for WellcomeAI application.
Handles real-time communication with clients.
"""

# Не импортируем обработчики напрямую, чтобы избежать циклических импортов
# Вместо этого объявляем, какие модули и классы доступны через пакет

__all__ = ["handler", "openai_client"]
