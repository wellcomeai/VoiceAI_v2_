import os
import uuid
from typing import List, Dict, Any, Optional

from pinecone import Pinecone
import openai
from backend.core.logging import get_logger
from backend.core.config import settings

logger = get_logger(__name__)


class PineconeService:
    """Service for working with Pinecone Vector Database (v3 SDK)"""

    _client: Optional[Pinecone] = None

    @classmethod
    def initialize(cls):
        """Initialize Pinecone client (v3 syntax)"""
        if cls._client:
            return

        api_key = os.getenv("PINECONE_API_KEY")
        if not api_key:
            raise ValueError("Missing PINECONE_API_KEY in environment")

        try:
            cls._client = Pinecone(api_key=api_key)
            logger.info("✅ Pinecone v3 client initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Pinecone: {e}")
            raise

    @classmethod
    def get_index(cls, index_name: Optional[str] = None):
        """Return Pinecone index object"""
        cls.initialize()

        index_name = index_name or os.getenv("PINECONE_INDEX", "voicufi")

        try:
            return cls._client.Index(index_name)
        except Exception as e:
            logger.error(f"❌ Failed to get index: {e}")
            raise

    @classmethod
    async def create_embeddings(cls, text: str, model: str = "text-embedding-ada-002", user_api_key: Optional[str] = None) -> List[float]:
        """Create embeddings using OpenAI API and user's key"""
        try:
            api_key = user_api_key or settings.OPENAI_API_KEY
            if not api_key:
                raise ValueError("Missing OpenAI API key")

            client = openai.OpenAI(api_key=api_key)

            response = client.embeddings.create(
                input=text,
                model=model
            )

            return response.data[0].embedding
        except Exception as e:
            logger.error(f"❌ Failed to create embeddings: {e}")
            raise

    @classmethod
    async def upsert_vectors(cls, vectors: List[Dict[str, Any]], namespace: str, index_name: Optional[str] = None) -> bool:
        """Upsert vectors to Pinecone"""
        try:
            index = cls.get_index(index_name)
            index.upsert(vectors=vectors, namespace=namespace)
            return True
        except Exception as e:
            logger.error(f"❌ Failed to upsert vectors: {e}")
            return False

    @classmethod
    async def delete_vectors(cls, filter: Dict[str, Any], namespace: str, index_name: Optional[str] = None, delete_all: bool = False) -> bool:
        """Delete vectors (by filter or all in namespace)"""
        try:
            index = cls.get_index(index_name)
            if delete_all:
                index.delete(delete_all=True, namespace=namespace)
            else:
                index.delete(filter=filter, namespace=namespace)
            return True
        except Exception as e:
            logger.error(f"❌ Failed to delete vectors: {e}")
            return False

    @classmethod
    async def query_vectors(cls, query_embedding: List[float], namespace: str, top_k: int = 5, filter: Optional[Dict[str, Any]] = None, index_name: Optional[str] = None) -> Dict[str, Any]:
        """Query top-k vectors with optional metadata filter"""
        try:
            index = cls.get_index(index_name)
            results = index.query(
                vector=query_embedding,
                top_k=top_k,
                namespace=namespace,
                filter=filter,
                include_metadata=True
            )
            return results
        except Exception as e:
            logger.error(f"❌ Failed to query vectors: {e}")
            raise
