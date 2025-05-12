"""
Subscription log model for WellcomeAI application.
Model for tracking subscription-related events.
"""

import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from backend.db.base import Base, BaseModel

class SubscriptionLog(Base, BaseModel):
    """
    Model for logging subscription related events
    """
    __tablename__ = "subscription_logs"
    
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    action = Column(String(50), nullable=False)  # subscribe, cancel, expire, renew, etc.
    plan_id = Column(UUID(as_uuid=True), ForeignKey("subscription_plans.id"), nullable=True)
    plan_code = Column(String(20), nullable=True)
    details = Column(Text, nullable=True)  # JSON or text description of the operation
    
    def __repr__(self):
        """String representation of SubscriptionLog"""
        return f"<SubscriptionLog user_id={self.user_id}, action={self.action}>"
