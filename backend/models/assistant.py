import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import Column, String, Text, Boolean, Integer, Float, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, backref

from backend.db.base import BaseModel

class AssistantConfig(BaseModel):
    """Model for AI assistant configuration"""
    __tablename__ = "assistant_configs"
    
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    system_prompt = Column(Text, nullable=False)
    voice = Column(String, nullable=False, default="alloy")
    language = Column(String, nullable=False, default="ru")
    google_sheet_id = Column(String, nullable=True)
    functions = Column(JSON, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    is_public = Column(Boolean, nullable=False, default=False)
    api_access_token = Column(String, nullable=True)
    total_conversations = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    temperature = Column(Float, nullable=False, default=0.7)
    max_tokens = Column(Integer, nullable=False, default=500)
    
    # Relationships
    user = relationship("User", back_populates="assistants")
    # Define relationship with KnowledgeBaseDocument using string reference to avoid circular import
    knowledge_base_documents = relationship("KnowledgeBaseDocument", back_populates="assistant", cascade="all, delete-orphan")
