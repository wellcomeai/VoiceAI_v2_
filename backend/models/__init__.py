"""
Models module for WellcomeAI application.
Contains SQLAlchemy models for database tables.
"""

# Import base model first
from backend.db.base import Base, BaseModel

# Import models in the correct order to avoid circular dependencies
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
