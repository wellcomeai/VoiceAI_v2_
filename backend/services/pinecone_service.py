import os
import pinecone
from typing import List, Dict, Any, Optional
import openai
import uuid

from backend.core.logging import get_logger
from backend.core.config import settings

logger = get_logger(__name__)

class PineconeService:
    """Service for working with Pinecone Vector Database"""
    
    _initialized = False
    
    @classmethod
    def initialize(cls):
        """Initialize Pinecone connection"""
        if cls._initialized:
            return
            
        try:
            api_key = os.environ.get("PINECONE_API_KEY")
            environment = os.environ.get("PINECONE_ENVIRONMENT", "us-east-1")
            
            pinecone.init(api_key=api_key, environment=environment)
            cls._initialized = True
            logger.info("Pinecone initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Pinecone: {str(e)}")
            raise
    
    @classmethod
    def get_index(cls, index_name: Optional[str] = None) -> Any:
        """Get Pinecone index"""
        cls.initialize()
        
        index_name = index_name or os.environ.get("PINECONE_INDEX", "voicufi")
        
        try:
            return pinecone.Index(index_name)
        except Exception as e:
            logger.error(f"Failed to get Pinecone index: {str(e)}")
            raise
    
    @classmethod
    async def create_embeddings(cls, text: str, model: str = "text-embedding-ada-002", user_api_key: Optional[str] = None) -> List[float]:
        """Create embeddings for text using OpenAI API"""
        try:
            # Set API key
            api_key = user_api_key or settings.OPENAI_API_KEY
            if not api_key:
                raise ValueError("OpenAI API key is required")
            
            # Create client with the specific API key
            client = openai.OpenAI(api_key=api_key)
            
            # Create embeddings
            response = client.embeddings.create(
                input=text,
                model=model
            )
            
            # Extract embeddings
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Failed to create embeddings: {str(e)}")
            raise
    
    @classmethod
    async def upsert_vectors(cls, vectors: List[Dict[str, Any]], namespace: str, index_name: Optional[str] = None) -> bool:
        """Upsert vectors to Pinecone index"""
        try:
            index = cls.get_index(index_name)
            
            # Upsert vectors
            index.upsert(vectors=vectors, namespace=namespace)
            
            return True
        except Exception as e:
            logger.error(f"Failed to upsert vectors: {str(e)}")
            return False
    
    @classmethod
    async def delete_vectors(cls, filter: Dict[str, Any], namespace: str, index_name: Optional[str] = None, delete_all: bool = False) -> bool:
        """Delete vectors from Pinecone index"""
        try:
            index = cls.get_index(index_name)
            
            if delete_all:
                # Delete all vectors in namespace
                index.delete(delete_all=True, namespace=namespace)
            else:
                # Delete vectors by filter
                index.delete(filter=filter, namespace=namespace)
            
            return True
        except Exception as e:
            logger.error(f"Failed to delete vectors: {str(e)}")
            return False
    
    @classmethod
    async def query_vectors(cls, query_embedding: List[float], namespace: str, top_k: int = 5, filter: Optional[Dict[str, Any]] = None, index_name: Optional[str] = None) -> Dict[str, Any]:
        """Query vectors from Pinecone index"""
        try:
            index = cls.get_index(index_name)
            
            # Query vectors
            results = index.query(
                vector=query_embedding,
                top_k=top_k,
                namespace=namespace,
                filter=filter,
                include_metadata=True
            )
            
            return results
        except Exception as e:
            logger.error(f"Failed to query vectors: {str(e)}")
            raise
