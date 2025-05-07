"""
Subscription API endpoints for WellcomeAI application.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from backend.core.logging import get_logger
from backend.core.dependencies import get_current_user
from backend.db.session import get_db
from backend.models.user import User
from backend.models.subscription import SubscriptionPlan
from backend.schemas.subscription import UserSubscriptionInfo

# Initialize logger
logger = get_logger(__name__)

# Create router
router = APIRouter()

@router.get("/my-subscription", response_model=Dict[str, Any])
async def get_my_subscription(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get current user's subscription information.
    
    Args:
        current_user: Current authenticated user
        db: Database session dependency
    
    Returns:
        User subscription information
    """
    try:
        # Check if user has subscription plan
        subscription_plan = None
        if current_user.subscription_plan_id:
            subscription_plan = db.query(SubscriptionPlan).get(current_user.subscription_plan_id)
        
        # Calculate days left
        days_left = None
        if current_user.subscription_end_date and current_user.subscription_end_date > datetime.now():
            delta = current_user.subscription_end_date - datetime.now()
            days_left = delta.days
        
        # Provide fallback values for empty database
        max_assistants = 1
        if subscription_plan:
            max_assistants = subscription_plan.max_assistants
        elif current_user.is_admin:
            max_assistants = 999
        
        # Default trial plan if no plan is set
        plan_info = {
            "code": "free",
            "name": "Free Trial",
            "price": 0,
            "max_assistants": max_assistants
        }
        
        if subscription_plan:
            plan_info = {
                "id": str(subscription_plan.id),
                "code": subscription_plan.code,
                "name": subscription_plan.name,
                "price": float(subscription_plan.price) if hasattr(subscription_plan, "price") else 0,
                "max_assistants": subscription_plan.max_assistants,
                "description": subscription_plan.description
            }
            
        # Return complete subscription info
        return {
            "subscription_plan": plan_info,
            "subscription_start_date": current_user.subscription_start_date,
            "subscription_end_date": current_user.subscription_end_date,
            "is_trial": current_user.is_trial,
            "days_left": days_left,
            "active": True if days_left or current_user.is_admin else False
        }
    except Exception as e:
        logger.error(f"Unexpected error in get_my_subscription: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve subscription information"
        )

@router.get("/plans", response_model=List[Dict[str, Any]])
async def get_subscription_plans(
    include_inactive: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get available subscription plans.
    
    Args:
        include_inactive: Whether to include inactive plans
        current_user: Current authenticated user
        db: Database session dependency
    
    Returns:
        List of subscription plans
    """
    try:
        # Get plans from database
        query = db.query(SubscriptionPlan)
        if not include_inactive:
            query = query.filter(SubscriptionPlan.is_active.is_(True))
            
        plans = query.all()
        
        # If no plans in database, provide defaults
        if not plans:
            return [
                {
                    "code": "free",
                    "name": "Free Trial",
                    "price": 0,
                    "max_assistants": 1,
                    "description": "Free trial plan with basic features",
                    "is_active": True
                },
                {
                    "code": "start",
                    "name": "Start",
                    "price": 19.99,
                    "max_assistants": 5,
                    "description": "Start plan with extended features",
                    "is_active": True
                },
                {
                    "code": "pro",
                    "name": "Professional",
                    "price": 49.99,
                    "max_assistants": 20,
                    "description": "Professional plan with all features",
                    "is_active": True
                }
            ]
            
        # Format plans
        result = []
        for plan in plans:
            result.append({
                "id": str(plan.id),
                "code": plan.code,
                "name": plan.name,
                "price": float(plan.price) if hasattr(plan, "price") else 0,
                "max_assistants": plan.max_assistants,
                "description": plan.description,
                "is_active": plan.is_active
            })
            
        return result
    except Exception as e:
        logger.error(f"Unexpected error in get_subscription_plans: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve subscription plans"
        )

@router.post("/subscribe/{plan_code}", response_model=Dict[str, Any])
async def subscribe_to_plan(
    plan_code: str,
    duration_days: int = 30,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Subscribe user to a plan.
    
    Args:
        plan_code: Plan code to subscribe to
        duration_days: Duration of subscription in days
        current_user: Current authenticated user
        db: Database session dependency
    
    Returns:
        Updated user subscription information
    """
    try:
        # Find plan by code
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.code == plan_code).first()
        
        # If plan not found in database, use defaults
        if not plan:
            if plan_code == "free":
                max_assistants = 1
                is_trial = True
            elif plan_code == "start":
                max_assistants = 5
                is_trial = False
            elif plan_code == "pro":
                max_assistants = 20
                is_trial = False
            else:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Plan with code {plan_code} not found"
                )
        else:
            max_assistants = plan.max_assistants
            is_trial = plan_code == "free"
        
        # Update user subscription
        now = datetime.now()
        current_user.subscription_start_date = now
        current_user.subscription_end_date = now + timedelta(days=duration_days)
        current_user.is_trial = is_trial
        
        if plan:
            current_user.subscription_plan_id = plan.id
        
        db.commit()
        
        # Get updated subscription info
        return await get_my_subscription(current_user, db)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error in subscribe_to_plan: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to subscribe to plan"
        )
