from fastapi import APIRouter, Depends, HTTPException, status, Path, UploadFile, File
from sqlalchemy.orm import Session
from typing import Dict, Any

from backend.core.logging import get_logger
from backend.core.dependencies import get_current_user, check_subscription_active
from backend.db.session import get_db
from backend.models.user import User
from backend.schemas.knowledge_base import KnowledgeBaseStatus, KnowledgeBaseDocumentResponse
from backend.services.knowledge_base_service import KnowledgeBaseService

logger = get_logger(__name__)

router = APIRouter()

@router.get("/{assistant_id}/status", response_model=KnowledgeBaseStatus)
async def get_knowledge_base_status(
    assistant_id: str = Path(..., description="Assistant ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get knowledge base status for an assistant
    
    Args:
        assistant_id: Assistant ID
        current_user: Current user
        db: Database session
        
    Returns:
        Knowledge base status
    """
    try:
        return await KnowledgeBaseService.get_knowledge_base_status(db, assistant_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting knowledge base status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get knowledge base status: {str(e)}"
        )

@router.post("/{assistant_id}/upload", response_model=KnowledgeBaseDocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    assistant_id: str = Path(..., description="Assistant ID"),
    current_user: User = Depends(check_subscription_active),
    db: Session = Depends(get_db)
):
    """
    Upload document to knowledge base
    
    Args:
        file: File to upload
        assistant_id: Assistant ID
        current_user: Current user
        db: Database session
        
    Returns:
        Uploaded document info
    """
    try:
        return await KnowledgeBaseService.upload_document(
            db=db,
            file=file,
            assistant_id=assistant_id,
            user_id=str(current_user.id)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading document: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload document: {str(e)}"
        )

@router.delete("/{assistant_id}/documents/{document_id}", response_model=Dict[str, Any])
async def delete_document(
    assistant_id: str = Path(..., description="Assistant ID"),
    document_id: str = Path(..., description="Document ID"),
    current_user: User = Depends(check_subscription_active),
    db: Session = Depends(get_db)
):
    """
    Delete document from knowledge base
    
    Args:
        assistant_id: Assistant ID
        document_id: Document ID
        current_user: Current user
        db: Database session
        
    Returns:
        Success message
    """
    try:
        result = await KnowledgeBaseService.delete_document(
            db=db,
            document_id=document_id,
            assistant_id=assistant_id,
            user_id=str(current_user.id)
        )
        
        return {"success": result, "message": "Document deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting document: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete document: {str(e)}"
        )

@router.post("/{assistant_id}/sync", response_model=Dict[str, Any])
async def sync_knowledge_base(
    assistant_id: str = Path(..., description="Assistant ID"),
    current_user: User = Depends(check_subscription_active),
    db: Session = Depends(get_db)
):
    """
    Synchronize knowledge base (reprocess all documents)
    
    Args:
        assistant_id: Assistant ID
        current_user: Current user
        db: Database session
        
    Returns:
        Success message
    """
    try:
        result = await KnowledgeBaseService.sync_knowledge_base(
            db=db,
            assistant_id=assistant_id,
            user_id=str(current_user.id)
        )
        
        return {"success": result, "message": "Knowledge base synchronization started"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error synchronizing knowledge base: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to synchronize knowledge base: {str(e)}"
        )
