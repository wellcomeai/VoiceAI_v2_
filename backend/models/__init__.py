"""
Models module for WellcomeAI application.
Contains SQLAlchemy models for database tables.
"""

# Импортируем Base и BaseModel напрямую из .base вместо из db.base
from .base import Base, BaseModel

# Импортируем модели в правильном порядке для избежания циклических зависимостей
from .user import User
from .assistant import AssistantConfig
from .conversation import Conversation
from .file import File
from .integration import Integration
from .subscription import SubscriptionPlan
from .subscription_log import SubscriptionLog
from .knowledge_base import KnowledgeBaseDocument

# Export models
__all__ = [
    "Base",
    "BaseModel",
    "User",
    "AssistantConfig", 
    "Conversation",
    "File",
    "Integration",
    "SubscriptionPlan",
    "SubscriptionLog",
    "KnowledgeBaseDocument"
]
