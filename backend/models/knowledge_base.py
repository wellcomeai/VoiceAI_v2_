import uuid
from typing import Optional

from sqlalchemy import Column, String, Integer, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from backend.db.base import BaseModel

class KnowledgeBaseDocument(BaseModel):
    """Model for knowledge base documents associated with an assistant"""
    __tablename__ = "knowledge_base_documents"
    
    assistant_id = Column(UUID(as_uuid=True), ForeignKey("assistants.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    content_type = Column(String, nullable=False)
    size = Column(Integer, nullable=False)
    chars_count = Column(Integer, nullable=False, default=0)
    status = Column(String, nullable=False, default="pending")  # pending, processing, processed, error
    processed = Column(Boolean, nullable=False, default=False)
    error_message = Column(String, nullable=True)
    
    # Relationship with assistant
    assistant = relationship("AssistantConfig", back_populates="knowledge_base_documents")
