"""
Инициализация модуля базы данных.
Содержит общие функции и объекты для работы с базой данных.
"""

# Импортируем get_db и другие компоненты из session
from backend.db.session import get_db, SessionLocal, engine

# Импортируем Base из models.base вместо из db.base
from backend.models.base import Base

__all__ = ["get_db", "SessionLocal", "engine", "Base"]
