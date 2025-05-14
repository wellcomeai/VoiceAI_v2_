"""
Conversation model for WellcomeAI application.
Represents chat interactions between users and assistants.
"""

import uuid
from sqlalchemy import Column, String, Float, JSON, ForeignKey, DateTime, Text, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy import Boolean, event

from backend.models.base import BaseModel

class Conversation(BaseModel):
    """
    Conversation model representing chat interactions with assistants.
    """
    __tablename__ = "conversations"

    # Более агрессивное исключение поля updated_at из маппинга
    __mapper_args__ = {
        'exclude_properties': ['updated_at']
    }
    
    # Переопределяем метод для предотвращения обновления updated_at
    def _sa_instance_state(self):
        return super()._sa_instance_state()

    assistant_id = Column(UUID(as_uuid=True), ForeignKey("assistant_configs.id", ondelete="CASCADE"), nullable=False)
    session_id = Column(String, nullable=True, index=True)  # Group related messages
    user_message = Column(Text, nullable=True)
    assistant_message = Column(Text, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    client_info = Column(JSON, nullable=True)  # Browser, IP, etc.
    tokens_used = Column(Integer, default=0)  # Token usage for this conversation
    feedback_rating = Column(Integer, nullable=True)  # User feedback (1-5)
    feedback_text = Column(Text, nullable=True)  # Detailed user feedback
    is_flagged = Column(Boolean, default=False)  # Flagged for review
    audio_duration = Column(Float, nullable=True)  # Duration of audio in seconds

    # Relationships - убедись, что имя переменной assistant и back_populates="conversations" совпадает с AssistantConfig
    assistant = relationship("AssistantConfig", back_populates="conversations")

    def __repr__(self):
        """String representation of Conversation"""
        return f"<Conversation {self.id} for assistant {self.assistant_id}>"
    
    def to_dict(self):
        """Convert to dictionary with string ID"""
        data = super().to_dict()
        # Convert UUID to string for JSON serialization
        if isinstance(data.get("id"), uuid.UUID):
            data["id"] = str(data["id"])
        if isinstance(data.get("assistant_id"), uuid.UUID):
            data["assistant_id"] = str(data["assistant_id"])
            
        return data
    
    @classmethod
    def get_recent_conversations(cls, db_session, assistant_id, limit=10):
        """Get recent conversations for an assistant"""
        return db_session.query(cls).filter(
            cls.assistant_id == assistant_id
        ).order_by(cls.created_at.desc()).limit(limit).all()

# Добавляем обработчик события перед обновлением объекта
@event.listens_for(Conversation, 'before_update')
def conversation_before_update(mapper, connection, target):
    # Предотвращаем автоматическое обновление updated_at
    if hasattr(target, '_sa_instance_state'):
        state = target._sa_instance_state
        if 'updated_at' in state.dict:
            del state.dict['updated_at']
