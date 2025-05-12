"""
Subscription service for WellcomeAI application.
"""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List, Optional, Dict, Any, Union
from datetime import datetime, timedelta
import uuid

from backend.core.logging import get_logger
from backend.models.subscription import SubscriptionPlan
from backend.models.subscription_log import SubscriptionLog  # Модель логов подписок
from backend.models.user import User
from backend.schemas.subscription import SubscriptionPlanCreate, SubscriptionPlanUpdate

logger = get_logger(__name__)

class SubscriptionService:
    """Service for subscription operations"""
    
    @staticmethod
    async def log_subscription_event(
        db: Session, 
        user_id: str, 
        action: str, 
        plan_id: Optional[str] = None,
        plan_code: Optional[str] = None,
        details: Optional[str] = None
    ) -> None:
        """
        Логирует событие, связанное с подпиской
        
        Args:
            db: Сессия базы данных
            user_id: ID пользователя
            action: Тип события (subscribe, cancel, expire, renew, trial_activate)
            plan_id: ID плана подписки (опционально)
            plan_code: Код плана подписки (опционально)
            details: Детали события (опционально)
        """
        try:
            # Преобразуем строковые ID в UUID, если они предоставлены
            user_uuid = None
            plan_uuid = None
            
            try:
                if user_id:
                    user_uuid = uuid.UUID(user_id)
                if plan_id:
                    plan_uuid = uuid.UUID(plan_id)
            except ValueError as e:
                logger.error(f"Invalid UUID format: {str(e)}")
                # Продолжаем без UUID, если они недействительны
            
            log_entry = SubscriptionLog(
                user_id=user_uuid,
                action=action,
                plan_id=plan_uuid,
                plan_code=plan_code,
                details=details
            )
            
            db.add(log_entry)
            db.commit()
            
            logger.info(f"Subscription event logged: user_id={user_id}, action={action}")
        except Exception as e:
            db.rollback()
            logger.error(f"Error logging subscription event: {str(e)}")
    
    @staticmethod
    async def get_subscription_plans(db: Session, include_inactive: bool = False) -> List[SubscriptionPlan]:
        """
        Get all subscription plans
        
        Args:
            db: Database session
            include_inactive: Whether to include inactive plans
            
        Returns:
            List of subscription plans
        """
        query = db.query(SubscriptionPlan)
        
        if not include_inactive:
            query = query.filter(SubscriptionPlan.is_active.is_(True))
            
        return query.all()
    
    @staticmethod
    async def get_subscription_plan_by_id(db: Session, plan_id: str) -> SubscriptionPlan:
        """
        Get subscription plan by ID
        
        Args:
            db: Database session
            plan_id: Plan ID
            
        Returns:
            Subscription plan
        """
        try:
            # Преобразуем в UUID, если это строка
            if isinstance(plan_id, str):
                plan_id = uuid.UUID(plan_id)
                
            plan = db.query(SubscriptionPlan).get(plan_id)
            
            if not plan:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Subscription plan not found"
                )
                
            return plan
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid plan ID format"
            )
    
    @staticmethod
    async def get_subscription_plan_by_code(db: Session, plan_code: str) -> SubscriptionPlan:
        """
        Get subscription plan by code
        
        Args:
            db: Database session
            plan_code: Plan code
            
        Returns:
            Subscription plan
        """
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.code == plan_code).first()
        
        if not plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Subscription plan with code {plan_code} not found"
            )
            
        return plan
    
    @staticmethod
    async def create_subscription_plan(db: Session, plan_data: SubscriptionPlanCreate) -> SubscriptionPlan:
        """
        Create a new subscription plan
        
        Args:
            db: Database session
            plan_data: Plan creation data
            
        Returns:
            Created subscription plan
        """
        try:
            # Check if a plan with this code already exists
            existing_plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.code == plan_data.code).first()
            if existing_plan:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Subscription plan with code {plan_data.code} already exists"
                )
            
            # Create plan
            # Используем dict для Pydantic v1 или model_dump для v2
            if hasattr(plan_data, 'dict'):
                plan_dict = plan_data.dict()
            else:
                plan_dict = plan_data.model_dump()
                
            plan = SubscriptionPlan(**plan_dict)
            db.add(plan)
            db.commit()
            db.refresh(plan)
            
            logger.info(f"Created subscription plan: {plan.id}, code: {plan.code}")
            return plan
            
        except IntegrityError as e:
            db.rollback()
            logger.error(f"Database integrity error during plan creation: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Subscription plan creation failed due to database constraint"
            )
        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Unexpected error during plan creation: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Subscription plan creation failed due to server error"
            )
    
    @staticmethod
    async def update_subscription_plan(
        db: Session, 
        plan_id: str, 
        plan_data: SubscriptionPlanUpdate
    ) -> SubscriptionPlan:
        """
        Update subscription plan
        
        Args:
            db: Database session
            plan_id: Plan ID
            plan_data: Plan update data
            
        Returns:
            Updated subscription plan
        """
        try:
            plan = await SubscriptionService.get_subscription_plan_by_id(db, plan_id)
            
            # Update only provided fields
            # Используем dict для Pydantic v1 или model_dump для v2
            if hasattr(plan_data, 'dict'):
                update_data = plan_data.dict(exclude_unset=True)
            else:
                update_data = plan_data.model_dump(exclude_unset=True)
                
            for key, value in update_data.items():
                setattr(plan, key, value)
            
            db.commit()
            db.refresh(plan)
            
            logger.info(f"Updated subscription plan: {plan.id}")
            return plan
            
        except IntegrityError as e:
            db.rollback()
            logger.error(f"Database integrity error during plan update: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Subscription plan update failed due to database constraint"
            )
        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Unexpected error during plan update: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Subscription plan update failed due to server error"
            )
    
    @staticmethod
    async def delete_subscription_plan(db: Session, plan_id: str) -> bool:
        """
        Delete subscription plan
        
        Args:
            db: Database session
            plan_id: Plan ID
            
        Returns:
            True if deletion was successful
        """
        try:
            plan = await SubscriptionService.get_subscription_plan_by_id(db, plan_id)
            
            # Check if any users are using this plan
            users_with_plan = db.query(User).filter(User.subscription_plan_id == plan.id).count()
            if users_with_plan > 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot delete plan with active users. Deactivate it instead."
                )
            
            db.delete(plan)
            db.commit()
            
            logger.info(f"Deleted subscription plan: {plan_id}")
            return True
            
        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Error deleting subscription plan: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete subscription plan"
            )
    
    @staticmethod
    async def activate_trial(db: Session, user_id: str, trial_days: int = 3) -> Optional[User]:
        """
        Activate trial period for user
        
        Args:
            db: Database session
            user_id: User ID
            trial_days: Trial period duration in days
            
        Returns:
            Updated user object or None on error
        """
        from backend.services.user_service import UserService
        
        try:
            # Проверяем формат user_id
            user_uuid = None
            try:
                if isinstance(user_id, str):
                    user_uuid = uuid.UUID(user_id)
                    user_id = user_uuid
            except ValueError:
                logger.error(f"Invalid user_id format: {user_id}")
                # Продолжаем с оригинальным user_id
                
            # Пытаемся получить пользователя
            user = None
            try:
                user = await UserService.get_user_by_id(db, user_id)
            except HTTPException as he:
                logger.error(f"Error getting user: {str(he)}")
                # Пытаемся получить напрямую из БД, если сервис не сработал
                user = db.query(User).get(user_id)
                
            if not user:
                logger.error(f"User not found: {user_id}")
                return None
            
            # Get trial plan
            trial_plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.code == "free").first()
            
            # Если план не найден, создаем его
            if not trial_plan:
                logger.warning("Trial plan (code='free') not found, creating one")
                trial_plan = SubscriptionPlan(
                    code="free",
                    name="Free Trial",
                    price=0,
                    max_assistants=1,
                    description="Free trial plan with basic features",
                    is_active=True
                )
                db.add(trial_plan)
                db.flush()  # Получаем ID без коммита
            
            # Set trial period
            now = datetime.now()
            user.is_trial = True
            user.subscription_start_date = now
            user.subscription_end_date = now + timedelta(days=trial_days)
            
            if trial_plan:
                user.subscription_plan_id = trial_plan.id
            
            # Логируем изменения
            logger.info(f"Setting trial: start={now}, end={user.subscription_end_date}, plan_id={trial_plan.id if trial_plan else None}")
            
            db.commit()
            db.refresh(user)
            
            # Логирование активации пробного периода
            await SubscriptionService.log_subscription_event(
                db=db,
                user_id=str(user.id),
                action="trial_activate",
                plan_id=str(trial_plan.id) if trial_plan else None,
                plan_code="free",
                details=f"Trial activated for {trial_days} days until {user.subscription_end_date.strftime('%Y-%m-%d')}"
            )
            
            # Пытаемся отправить уведомление - не критично для работы функции
            try:
                from backend.services.notification_service import NotificationService
                plan_name = trial_plan.name if trial_plan else "Free Trial"
                await NotificationService.send_subscription_started_notice(
                    user=user,
                    plan_name=plan_name,
                    end_date=user.subscription_end_date,
                    is_trial=True
                )
            except Exception as notif_error:
                logger.error(f"Failed to send notification: {str(notif_error)}")
            
            logger.info(f"Activated trial for user {user_id} until {user.subscription_end_date}")
            return user
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error activating trial: {str(e)}")
            # Не выбрасываем исключение, чтобы не блокировать регистрацию
            return None
            
    @staticmethod
    async def check_expired_subscriptions(db: Session) -> int:
        """
        Проверка и обновление истекших подписок
        
        Args:
            db: Сессия базы данных
            
        Returns:
            Количество обновленных подписок
        """
        try:
            now = datetime.now()
            
            # Находим пользователей с истекшими подписками
            expired_users = db.query(User).filter(
                User.subscription_end_date < now,
                User.subscription_end_date.isnot(None),
                User.is_trial.is_(True)  # Пока работаем только с триальными подписками
            ).all()
            
            updated_count = 0
            
            for user in expired_users:
                # Сбрасываем подписку
                user.is_trial = False
                # Оставляем дату окончания для истории
                
                # Логируем событие
                await SubscriptionService.log_subscription_event(
                    db=db,
                    user_id=str(user.id),
                    action="trial_expired",
                    plan_id=str(user.subscription_plan_id) if user.subscription_plan_id else None,
                    details=f"Trial period expired on {user.subscription_end_date.strftime('%Y-%m-%d')}"
                )
                
                updated_count += 1
            
            if updated_count > 0:
                db.commit()
                logger.info(f"Updated {updated_count} expired subscriptions")
                
            return updated_count
                
        except Exception as e:
            db.rollback()
            logger.error(f"Error checking expired subscriptions: {str(e)}")
            return 0
