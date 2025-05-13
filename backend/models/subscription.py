"""
Subscription plan model for WellcomeAI application.
"""

import uuid
from sqlalchemy import Column, String, Boolean, Numeric, Integer, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from backend.models.base import BaseModel

class SubscriptionPlan(BaseModel):
    """
    Model representing subscription plans.
    """
    __tablename__ = "subscription_plans"

    # Удалены id, created_at и updated_at - они уже определены в BaseModel
    name = Column(String(50), nullable=False)
    code = Column(String(20), nullable=False, unique=True)
    price = Column(Numeric(10, 2), nullable=False)
    max_assistants = Column(Integer, nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)

    def __repr__(self):
        """String representation of SubscriptionPlan"""
        return f"<SubscriptionPlan {self.name} (code={self.code})>"
