"""
Integration model for WellcomeAI application.
"""

import uuid
from sqlalchemy import Column, String, Boolean, ForeignKey, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from backend.models.base import BaseModel

class Integration(BaseModel):
    """
    Integration model for external services like n8n webhooks.
    """
    __tablename__ = "integrations"
    
    # Удалены id, created_at и updated_at - они уже определены в BaseModel
    assistant_id = Column(UUID(as_uuid=True), ForeignKey("assistant_configs.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)  # e.g., "n8n"
    webhook_url = Column(String, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Relationship with AssistantConfig - no back_populates here
    assistant = relationship("AssistantConfig")
