from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel

class KnowledgeBaseDocumentBase(BaseModel):
    """Base schema for knowledge base document"""
    filename: str
    original_filename: str
    content_type: str
    size: int
    chars_count: int = 0
    status: str = "pending"
    processed: bool = False
    error_message: Optional[str] = None

class KnowledgeBaseDocumentCreate(KnowledgeBaseDocumentBase):
    """Schema for creating a knowledge base document"""
    assistant_id: str

class KnowledgeBaseDocumentUpdate(BaseModel):
    """Schema for updating a knowledge base document"""
    status: Optional[str] = None
    processed: Optional[bool] = None
    chars_count: Optional[int] = None
    error_message: Optional[str] = None

class KnowledgeBaseDocumentResponse(KnowledgeBaseDocumentBase):
    """Schema for knowledge base document response"""
    id: str
    assistant_id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class KnowledgeBaseStatus(BaseModel):
    """Schema for knowledge base status"""
    total_documents: int
    total_chars: int
    max_chars: int = 1000000
    max_documents: int = 10
    documents: List[KnowledgeBaseDocumentResponse]
