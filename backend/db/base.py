"""
Базовые классы и функции для работы с БД.
Содержит импорты базовых классов из модуля models.base.
"""

# Импортируем классы из models.base вместо их определения здесь
from backend.models.base import Base, BaseModel, CRUDBase
from backend.models.base import ModelType, CreateSchemaType, UpdateSchemaType

# Не определяем здесь новые классы, чтобы избежать дублирования

# Экспорт только необходимых классов
__all__ = [
    "Base", 
    "BaseModel", 
    "CRUDBase",
    "ModelType", 
    "CreateSchemaType", 
    "UpdateSchemaType"
]
